"""Two-tier semantic cache coordinator implementing the SemanticCacheStore protocol."""

from typing import Any, Dict, List, Optional
from src.caching.equivalence_verifier import CacheEquivalenceVerifier
from src.caching.l1_redis import L1RedisCache
from src.caching.l2_vector import L2VectorSemanticCache
from src.caching.single_flight import SingleFlightMutex
from src.core.logging import get_logger
from src.domain.protocols import SemanticCacheStore
from src.ingestion.normalizers import normalize_for_lexical

logger = get_logger("caching.coordinator")


class SemanticCacheCoordinator(SemanticCacheStore):
    """Orchestrates L1 Redis and L2 pgvector caching with equivalence verification and stampede protection."""

    def __init__(
        self,
        l1_cache: L1RedisCache,
        l2_cache: L2VectorSemanticCache,
        verifier: CacheEquivalenceVerifier,
        single_flight: Optional[SingleFlightMutex] = None,
    ):
        self.l1 = l1_cache
        self.l2 = l2_cache
        self.verifier = verifier
        self.single_flight = single_flight

    async def find_hit(
        self,
        query_text: str,
        query_embedding: List[float],
        persona: str = "standard",
        language: str = "ar",
        answer_shape: str = "standard",
        filter_hash: str = "ALL",
    ) -> Optional[Dict[str, Any]]:
        """Searches L1 and L2 cache tiers with multi-dimensional partition filtering and equivalence verification."""
        normalized_q = normalize_for_lexical(query_text, lang=language)

        # 1. Tier 1: Exact Redis Cache lookup (<5ms)
        l1_hit = await self.l1.get(
            normalized_query=normalized_q,
            persona=persona,
            language=language,
            answer_shape=answer_shape,
            filter_hash=filter_hash,
        )
        if l1_hit is not None:
            logger.info("cache_hit_tier1", query=query_text[:40])
            return l1_hit

        # 2. Tier 2: Vector Semantic Cache lookup (pgvector HNSW)
        if not query_embedding:
            return None

        l2_candidate = await self.l2.find_candidate(
            query_embedding=query_embedding,
            persona=persona,
            language=language,
            answer_shape=answer_shape,
            filter_hash=filter_hash,
        )

        if not l2_candidate:
            return None

        # 3. Equivalence Verification Gate (Prevents False Positives in [0.87, 0.97) band)
        stored_q = l2_candidate["query_text"]
        similarity = l2_candidate["similarity"]

        is_equiv = await self.verifier.is_equivalent(
            stored_query=stored_q,
            incoming_query=query_text,
            cosine_similarity=similarity,
        )

        if not is_equiv:
            logger.info(
                "cache_near_miss_rejected_by_verifier",
                stored=stored_q[:40],
                incoming=query_text[:40],
                similarity=similarity,
            )
            return None

        # 4. Validated L2 Hit -> Populate L1 for future fast replays
        l2_candidate["cached"] = True
        l2_candidate["tier"] = "L2"
        await self.l1.set(
            normalized_query=normalized_q,
            persona=persona,
            language=language,
            answer_shape=answer_shape,
            filter_hash=filter_hash,
            payload=l2_candidate,
        )

        logger.info(
            "cache_hit_tier2_verified",
            stored=stored_q[:40],
            incoming=query_text[:40],
            similarity=similarity,
        )
        return l2_candidate

    async def store(
        self,
        query_text: str,
        normalized_query: str,
        query_embedding: List[float],
        response_text: str,
        sources: List[Dict[str, Any]],
        suggestions: List[str],
        persona: str = "standard",
        language: str = "ar",
        answer_shape: str = "standard",
        filter_hash: str = "ALL",
        grounding_audit: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stores a validated grounded answer in both L1 and L2 cache tiers."""
        audit = grounding_audit or {"status": "VERIFIED"}
        norm_q = normalized_query or normalize_for_lexical(query_text, lang=language)

        payload = {
            "query_text": query_text,
            "normalized_query": norm_q,
            "response_text": response_text,
            "sources": sources,
            "suggestions": suggestions,
            "persona": persona,
            "language": language,
            "answer_shape": answer_shape,
            "filter_hash": filter_hash,
            "grounding_audit": audit,
        }

        # 1. Write-through to L1 Redis (24h)
        l1_success = await self.l1.set(
            normalized_query=norm_q,
            persona=persona,
            language=language,
            answer_shape=answer_shape,
            filter_hash=filter_hash,
            payload=payload,
        )

        # 2. Persist in L2 pgvector (7d)
        l2_success = False
        if query_embedding:
            l2_success = await self.l2.store(
                query_text=query_text,
                normalized_query=norm_q,
                query_embedding=query_embedding,
                response_text=response_text,
                sources=sources,
                suggestions=suggestions,
                persona=persona,
                language=language,
                answer_shape=answer_shape,
                filter_hash=filter_hash,
                grounding_audit=audit,
            )

        # 3. Release any single-flight mutex lock if held
        if self.single_flight:
            lock_key = self.single_flight.compute_lock_key(
                normalized_query=norm_q,
                persona=persona,
                language=language,
                answer_shape=answer_shape,
                filter_hash=filter_hash,
            )
            await self.single_flight.release_leader(lock_key)

        return l1_success or l2_success
