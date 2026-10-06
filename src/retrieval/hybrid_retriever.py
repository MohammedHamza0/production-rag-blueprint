"""5-Way Hybrid RRF Retriever combining pgvector HNSW and multilingual GIN indexes."""

import json
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import DatabaseError, RetrievalError
from src.core.logging import get_logger
from src.domain.entities import RetrievedSource
from src.domain.protocols import HybridRetriever
from src.retrieval.context_expander import ContextExpander
from src.retrieval.diversity_guard import DiversityGuard
from src.retrieval.language_router import LanguageRouter
from src.retrieval.query_transformer import QueryTransformer

logger = get_logger("retrieval.hybrid_retriever")


class HybridRRFRetriever(HybridRetriever):
    """Production 5-Way Hybrid Retriever using true Reciprocal Rank Fusion (k=60)."""

    def __init__(
        self,
        session_factory,
        router: Optional[LanguageRouter] = None,
        transformer: Optional[QueryTransformer] = None,
        diversity_guard: Optional[DiversityGuard] = None,
        context_expander: Optional[ContextExpander] = None,
    ):
        self.session_factory = session_factory
        self.router = router or LanguageRouter()
        self.transformer = transformer or QueryTransformer()
        self.diversity_guard = diversity_guard or DiversityGuard()
        self.context_expander = context_expander or ContextExpander()

    async def search(
        self,
        query_text: str,
        query_embedding: List[float],
        match_count: int = 8,
        filter_doc_ids: Optional[List[uuid.UUID]] = None,
        filter_collection_id: Optional[uuid.UUID] = None,
        vector_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
        filter_languages: Optional[List[str]] = None,
        preferred_languages: Optional[List[str]] = None,
        expand_parents: bool = True,
        group_pages: bool = False,
    ) -> List[RetrievedSource]:
        """Executes 5-way hybrid search via PostgreSQL stored function search_chunks_hybrid."""
        # 1. Transform query and strip conversational boilerplate
        transformed = self.transformer.transform(query_text)
        search_query_text = transformed.cleaned_query or query_text

        # 2. Classify query language and dynamically compute RRF weights if not explicitly provided
        classification = self.router.classify_query(search_query_text)
        v_weight = vector_weight if vector_weight is not None else classification.vector_weight
        k_weight = keyword_weight if keyword_weight is not None else classification.keyword_weight
        prefs = preferred_languages or classification.preferred_languages

        logger.debug(
            "retrieval_query_prepared",
            query=search_query_text,
            lang=classification.detected_language,
            query_type=classification.query_type,
            v_weight=v_weight,
            k_weight=k_weight,
        )

        # 3. Format pgvector string representation: '[0.123, 0.456, ...]'
        embedding_str = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"

        # Format UUID arrays for PostgreSQL
        doc_ids_param = (
            "{" + ",".join(str(d) for d in filter_doc_ids) + "}"
            if filter_doc_ids
            else None
        )
        filter_langs_param = (
            "{" + ",".join(filter_languages) + "}"
            if filter_languages
            else None
        )
        pref_langs_param = (
            "{" + ",".join(prefs) + "}"
            if prefs
            else None
        )

        query_sql = text("""
            SELECT 
                id,
                document_id,
                document_title,
                document_author,
                work_id,
                work_title,
                edition_id,
                edition_title,
                edition_language,
                chunk_language,
                content,
                chapter_title,
                page_number,
                chunk_index,
                chunk_type,
                parent_chunk_id,
                depth,
                volume_number,
                breadcrumb,
                vector_similarity,
                text_score,
                combined_score
            FROM search_chunks_hybrid(
                query_embedding := :query_embedding::vector,
                query_text := :query_text,
                match_count := :match_count,
                filter_doc_ids := :filter_doc_ids,
                filter_collection_id := :filter_collection_id,
                vector_weight := :vector_weight,
                keyword_weight := :keyword_weight,
                filter_languages := :filter_languages,
                preferred_languages := :preferred_languages,
                language_boost := 0.05
            );
        """)

        async with self.session_factory() as session:
            try:
                # Set local HNSW ef_search for high-recall index probe
                await session.execute(text("SET LOCAL hnsw.ef_search = 100;"))

                res = await session.execute(
                    query_sql,
                    {
                        "query_embedding": embedding_str,
                        "query_text": search_query_text,
                        "match_count": match_count * 2,  # Fetch pool for diversity guarding
                        "filter_doc_ids": doc_ids_param,
                        "filter_collection_id": filter_collection_id,
                        "vector_weight": v_weight,
                        "keyword_weight": k_weight,
                        "filter_languages": filter_langs_param,
                        "preferred_languages": pref_langs_param,
                    },
                )
                rows = res.all()

            except Exception as exc:
                logger.error("hybrid_search_query_failed", error=str(exc))
                raise RetrievalError(
                    f"Hybrid search execution failed: {str(exc)}",
                    details={"query": search_query_text, "error": str(exc)},
                )

            # 4. Map SQL rows to domain RetrievedSource entities
            candidate_sources: List[RetrievedSource] = []
            for rank_idx, r in enumerate(rows, start=1):
                candidate_sources.append(
                    RetrievedSource(
                        source_index=rank_idx,
                        document_id=r.document_id,
                        document_title=r.document_title or "Untitled Document",
                        document_author=r.document_author or "Unknown",
                        work_id=r.work_id,
                        work_title=r.work_title,
                        edition_id=r.edition_id,
                        edition_title=r.edition_title,
                        edition_language=r.edition_language or "ar",
                        chunk_language=r.chunk_language or "ar",
                        content=r.content,
                        page_number=r.page_number,
                        chapter_title=r.chapter_title,
                        chunk_id=r.id,
                        chunk_index=r.chunk_index or 0,
                        chunk_type=r.chunk_type or "CHILD",
                        parent_chunk_id=r.parent_chunk_id,
                        depth=r.depth or 1,
                        volume_number=r.volume_number,
                        breadcrumb=r.breadcrumb,
                        vector_similarity=float(r.vector_similarity or 0.0),
                        text_score=float(r.text_score or 0.0),
                        combined_score=float(r.combined_score or 0.0),
                    )
                )

            # 5. Apply diversity guard to prevent document monopolization
            diversified = self.diversity_guard.enforce_diversity(
                candidate_sources,
                target_count=match_count,
            )

            # 6. Optionally expand parent chunks
            if expand_parents and diversified:
                diversified = await self.context_expander.expand_parents(diversified, session)

            # 7. Optionally group pages
            if group_pages and diversified:
                diversified = self.context_expander.group_by_page(diversified)

            return diversified
