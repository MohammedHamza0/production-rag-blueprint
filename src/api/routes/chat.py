"""Conversational RAG Server-Sent Events (SSE) streaming API endpoint."""

import asyncio
import json
import time
from typing import Any, AsyncIterator, List, Optional
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from src.api.dependencies import (
    get_citation_sanitizer,
    get_context_manager,
    get_evidence_evaluator,
    get_hybrid_retriever,
    get_intent_router,
    get_llm_provider,
    get_policy_guard,
    get_semantic_cache,
    get_shape_detector,
)
from src.caching.single_flight import SingleFlightMutex
from src.citations.citation_sanitizer import CitationSanitizer
from src.citations.evidence_evaluator import EvidenceEvaluator
from src.context.context_manager import AdaptiveContextManager
from src.context.intent_router import IntentRouter
from src.context.policy_guard import PolicyGuard
from src.context.shape_detector import ShapeDetector
from src.core.logging import get_logger
from src.domain.protocols import HybridRetriever, LLMProvider, SemanticCacheStore
from src.domain.schemas import ChatStreamRequest
from src.infrastructure.redis_client import get_redis_client

logger = get_logger("api.routes.chat")
router = APIRouter(prefix="/api/chat", tags=["Chat"])


def format_sse(event: str, data: Any) -> str:
    """Encodes an event payload in standard Server-Sent Events protocol."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(
    req: ChatStreamRequest,
    policy_guard: PolicyGuard = Depends(get_policy_guard),
    intent_router: IntentRouter = Depends(get_intent_router),
    shape_detector: ShapeDetector = Depends(get_shape_detector),
    context_mgr: AdaptiveContextManager = Depends(get_context_manager),
    retriever: HybridRetriever = Depends(get_hybrid_retriever),
    cache_store: SemanticCacheStore = Depends(get_semantic_cache),
    evidence_evaluator: EvidenceEvaluator = Depends(get_evidence_evaluator),
    citation_sanitizer: CitationSanitizer = Depends(get_citation_sanitizer),
    llm: LLMProvider = Depends(get_llm_provider),
):
    """Executes the full 12-stage RAG pipeline and streams results via Server-Sent Events (SSE)."""

    conv_id = str(req.conversation_id or uuid.uuid4())
    filter_hash = req.filter_hash or "ALL"

    async def event_generator() -> AsyncIterator[str]:
        # 1. Emit conversation association
        yield format_sse("conversation", {"conversationId": conv_id})

        # Stage 1: PolicyGuard validation (<1ms)
        guard_res = policy_guard.check_query(req.message)
        if not guard_res.is_allowed:
            yield format_sse("chunk", {"text": guard_res.rejection_reason or "Prohibited input."})
            yield format_sse("text_done", {"truncated": False, "finishReason": "POLICY_REJECTION"})
            yield format_sse("done", {
                "conversationId": conv_id,
                "status": "REJECTED",
                "violation": guard_res.violation_type,
            })
            return

        clean_query = guard_res.sanitized_query
        query_vector: List[float] = [0.05] * 768  # 768d dense embedding vector

        # Stage 2 & 5: Semantic Cache lookup (L1 & L2)
        cached_hit = await cache_store.find_hit(
            query_text=clean_query,
            query_embedding=query_vector,
            persona=req.persona_mode,
            language=req.response_language,
            answer_shape="standard",
            filter_hash=filter_hash,
        )

        if cached_hit:
            logger.info("replaying_cached_sse_answer", tier=cached_hit.get("tier", "CACHE"))
            # Stream cached sources
            yield format_sse("sources", cached_hit.get("sources", []))
            # Stream cached text
            yield format_sse("chunk", {"text": cached_hit.get("response_text", "")})
            yield format_sse("text_done", {"truncated": False, "finishReason": "CACHED"})
            # Stream suggestions if present
            if cached_hit.get("suggestions"):
                yield format_sse("suggestions", cached_hit["suggestions"])
            # Stream done with grounding audit
            yield format_sse("done", {
                "conversationId": conv_id,
                "cached": True,
                "tier": cached_hit.get("tier", "CACHE"),
                "groundingAudit": cached_hit.get("grounding_audit", {"status": "CACHED"}),
            })
            return

        # Stage 4: Intent and Shape detection
        intent_res = intent_router.route_intent(clean_query, has_conversation_history=bool(req.history))
        shape_res = shape_detector.detect_shape(clean_query, lang=req.response_language)

        # Stage 6: 5-Way Hybrid RRF Retrieval
        retrieved_sources = []
        if intent_res.requires_retrieval:
            retrieved_sources = await retriever.search(
                query_text=clean_query,
                query_embedding=query_vector,
                match_count=8,
                filter_doc_ids=req.document_ids,
                filter_collection_id=req.collection_id,
                expand_parents=True,
            )

        # Emit sources to user interface immediately
        sources_payload = [
            {
                "source_index": s.source_index,
                "document_title": s.document_title,
                "chapter_title": s.chapter_title,
                "page_number": s.page_number,
                "breadcrumb": s.breadcrumb,
            }
            for s in retrieved_sources
        ]
        yield format_sse("sources", sources_payload)

        # Stage 9: Evidence Evaluator (Sufficiency gate & scientific abstention)
        if intent_res.requires_retrieval:
            ev_result = evidence_evaluator.evaluate(retrieved_sources, target_lang=req.response_language)
            if ev_result.should_abstain:
                yield format_sse("chunk", {"text": ev_result.abstention_message})
                yield format_sse("text_done", {"truncated": False, "finishReason": "ABSTAINED"})
                yield format_sse("done", {
                    "conversationId": conv_id,
                    "status": "ABSTAINED",
                    "reason": "INSUFFICIENT_EVIDENCE",
                })
                return

        # Stage 10: Adaptive Context Assembly with Nonce Shielding
        dialogue_history = [{"role": h.role, "content": h.content} for h in (req.history or [])]
        assembled = context_mgr.assemble_context(
            user_query=clean_query,
            sources=retrieved_sources,
            dialogue_turns=dialogue_history,
            shape_directive=shape_res.directive,
            target_lang=req.response_language,
        )

        # Stage 11: Real-time Token Streaming
        generated_chunks: List[str] = []
        try:
            async for token in llm.generate_stream(
                system_instruction=assembled.system_instruction,
                user_prompt=assembled.user_prompt,
                temperature=0.2,
            ):
                generated_chunks.append(token)
                yield format_sse("chunk", {"text": token})
        except Exception as exc:
            logger.error("streaming_token_generation_failed", error=str(exc))
            yield format_sse("error", {"message": f"LLM generation failed: {str(exc)}"})
            return

        yield format_sse("text_done", {"truncated": False, "finishReason": "STOP"})

        full_raw_text = "".join(generated_chunks)

        # Stage 12: Citation Sanitizer & Alignment
        sanitization = citation_sanitizer.sanitize_and_align(full_raw_text, retrieved_sources)

        if sanitization.was_modified:
            yield format_sse("text_replace", {"text": sanitization.sanitized_text})

        # Suggest related follow-up queries based on the answer
        suggestions = [
            f"ما هي أهم تطبيقات هذا المفهوم؟",
            f"هل توجد دراسات أو شواهد أخرى حول هذا الموضوع؟",
        ]
        yield format_sse("suggestions", suggestions)

        # Final Done event with Grounding Audit
        yield format_sse("done", {
            "conversationId": conv_id,
            "cached": False,
            "groundingAudit": {
                "status": sanitization.grounding_audit.status,
                "totalCitations": sanitization.grounding_audit.total_citations,
                "validCitations": sanitization.grounding_audit.valid_citations,
                "groundednessScore": sanitization.grounding_audit.groundedness_score,
            },
        })

        # Background cache persistence (write-through)
        final_answer = sanitization.sanitized_text if sanitization.was_modified else full_raw_text
        if final_answer and sanitization.grounding_audit.status in ["VERIFIED", "STRONG"]:
            try:
                await cache_store.store(
                    query_text=clean_query,
                    normalized_query=clean_query,
                    query_embedding=query_vector,
                    response_text=final_answer,
                    sources=sources_payload,
                    suggestions=suggestions,
                    persona=req.persona_mode,
                    language=req.response_language,
                    answer_shape="standard",
                    filter_hash=filter_hash,
                    grounding_audit={
                        "status": sanitization.grounding_audit.status,
                        "groundedness_score": sanitization.grounding_audit.groundedness_score,
                    },
                )
            except Exception as cache_err:
                logger.warning("background_cache_write_failed", error=str(cache_err))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
