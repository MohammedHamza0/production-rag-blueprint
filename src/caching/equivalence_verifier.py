"""CacheEquivalenceVerifier protecting against semantic false positives with fail-closed safety."""

import asyncio
import hashlib
from typing import Optional
from src.core.logging import get_logger
from src.domain.protocols import LLMProvider

logger = get_logger("caching.equivalence_verifier")

VERIFIER_SYSTEM_PROMPT = """You are a strict factual semantic equivalence verifier for a production RAG system.
Your job is to determine whether two queries require the EXACT same factual answer.
Rules:
1. If the queries ask about different conditions, rules, chapters, volumes, people, or opposite actions (e.g. 'conditions' vs 'pillars', 'fasting' vs 'breaking fast'), they are NOT equivalent.
2. Minor wording or grammatical variations asking the exact same question ARE equivalent.
3. Respond ONLY with a valid JSON object:
{"equivalent": boolean, "reason": "concise explanation"}
"""


class CacheEquivalenceVerifier:
    """Zero-shot equivalence verifier with pair-hash caching in Redis and fail-closed safety."""

    def __init__(
        self,
        redis_client=None,
        llm_provider: Optional[LLMProvider] = None,
        pair_ttl_seconds: int = 604800,  # 7 days
        timeout_seconds: float = 2.0,
    ):
        self.redis = redis_client
        self.llm_provider = llm_provider
        self.pair_ttl = pair_ttl_seconds
        self.timeout = timeout_seconds

    @staticmethod
    def compute_pair_key(query1: str, query2: str) -> str:
        """Computes symmetric pair-hash key for the two normalized queries."""
        sorted_pair = "::".join(sorted([query1.strip().lower(), query2.strip().lower()]))
        pair_hash = hashlib.sha256(sorted_pair.encode("utf-8")).hexdigest()[:24]
        return f"rag:verdict:{pair_hash}"

    async def is_equivalent(
        self,
        stored_query: str,
        incoming_query: str,
        cosine_similarity: float,
    ) -> bool:
        """Determines if the incoming query is semantically equivalent to the cached query.

        - If cosine similarity >= 0.97: high confidence direct match (True).
        - If cosine similarity < 0.87: below threshold (False).
        - If 0.87 <= similarity < 0.97: ambiguous band evaluated via pair-hash cache or LLM.
        """
        # Exact string match
        if stored_query.strip().lower() == incoming_query.strip().lower():
            return True

        # Extremely high vector confidence
        if cosine_similarity >= 0.97:
            logger.debug(
                "equivalence_high_confidence_bypass",
                similarity=cosine_similarity,
                stored=stored_query[:30],
                incoming=incoming_query[:30],
            )
            return True

        # Below threshold
        if cosine_similarity < 0.87:
            return False

        # Ambiguous band [0.87, 0.97): check Redis pair verdict cache first
        pair_key = self.compute_pair_key(stored_query, incoming_query)
        if self.redis:
            try:
                cached_verdict = await self.redis.get(pair_key)
                if cached_verdict is not None:
                    is_eq = (cached_verdict == "1" or cached_verdict == b"1")
                    logger.debug("equivalence_pair_cache_hit", key=pair_key, verdict=is_eq)
                    return is_eq
            except Exception as exc:
                logger.warning("equivalence_pair_cache_read_error", error=str(exc))

        # If LLM provider is not available, fail-closed for safety
        if not self.llm_provider:
            logger.warning("equivalence_llm_missing_fail_closed")
            return False

        # Perform zero-shot LLM verification with strict timeout
        user_prompt = f"""Stored Query: {stored_query}
Incoming Query: {incoming_query}
Determine if they have the exact same semantic intent and require the exact same answer."""

        try:
            result = await asyncio.wait_for(
                self.llm_provider.generate_json(
                    system_instruction=VERIFIER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                ),
                timeout=self.timeout,
            )

            is_eq = bool(result.get("equivalent", False))
            reason = result.get("reason", "")
            logger.info("equivalence_llm_verdict", verdict=is_eq, reason=reason)

            # Cache the verdict in Redis
            if self.redis:
                try:
                    await self.redis.set(pair_key, "1" if is_eq else "0", ex=self.pair_ttl)
                except Exception as exc:
                    logger.warning("equivalence_pair_cache_write_error", error=str(exc))

            return is_eq

        except asyncio.TimeoutError:
            logger.warning("equivalence_verification_timeout_fail_closed", timeout=self.timeout)
            return False
        except Exception as exc:
            logger.warning("equivalence_verification_error_fail_closed", error=str(exc))
            return False
