"""Tier 1: Ultra-fast in-memory exact semantic cache using Redis."""

import hashlib
import json
from typing import Any, Dict, Optional
from src.core.logging import get_logger

logger = get_logger("caching.l1_redis")


class L1RedisCache:
    """Redis-backed L1 exact-match cache operating with sub-5ms latency."""

    def __init__(self, redis_client, default_ttl_seconds: int = 86400):
        self.redis = redis_client
        self.default_ttl = default_ttl_seconds

    @staticmethod
    def compute_cache_key(
        normalized_query: str,
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
    ) -> str:
        """Constructs deterministic multi-dimensional cache partition key."""
        q_hash = hashlib.sha256(normalized_query.strip().encode("utf-8")).hexdigest()[:24]
        return f"rag:l1:{persona}:{language}:{answer_shape}:{filter_hash}:{q_hash}"

    async def get(
        self,
        normalized_query: str,
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves cached response from L1 Redis tier."""
        if not self.redis:
            return None

        key = self.compute_cache_key(normalized_query, persona, language, answer_shape, filter_hash)
        try:
            val = await self.redis.get(key)
            if not val:
                return None

            data = json.loads(val)
            # Increment hit counter asynchronously (best effort)
            try:
                await self.redis.incr(f"{key}:hits")
            except Exception:
                pass

            data["cached"] = True
            data["tier"] = "L1"
            logger.debug("l1_cache_hit", key=key)
            return data

        except Exception as exc:
            logger.warning("l1_cache_read_error", key=key, error=str(exc))
            return None

    async def set(
        self,
        normalized_query: str,
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
        payload: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Stores grounded answer in L1 Redis tier with TTL."""
        if not self.redis:
            return False

        key = self.compute_cache_key(normalized_query, persona, language, answer_shape, filter_hash)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

        try:
            # Clean payload serialization
            serialized = json.dumps(payload, ensure_ascii=False)
            await self.redis.set(key, serialized, ex=ttl)
            logger.debug("l1_cache_stored", key=key, ttl=ttl)
            return True
        except Exception as exc:
            logger.warning("l1_cache_write_error", key=key, error=str(exc))
            return False

    async def invalidate(self, pattern: str = "rag:l1:*") -> int:
        """Invalidates keys matching the specified pattern."""
        if not self.redis:
            return 0

        try:
            count = 0
            cur = b"0"
            while True:
                cur, keys = await self.redis.scan(cursor=cur, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                    count += len(keys)
                if cur == 0 or cur == b"0":
                    break
            logger.info("l1_cache_invalidated", pattern=pattern, count=count)
            return count
        except Exception as exc:
            logger.warning("l1_cache_invalidation_failed", error=str(exc))
            return 0
