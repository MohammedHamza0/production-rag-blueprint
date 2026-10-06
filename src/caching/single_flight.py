"""Single-flight stampede mutex preventing duplicate concurrent execution for identical queries."""

import asyncio
import hashlib
from typing import Any, Callable, Coroutine, Dict, Optional
from src.core.logging import get_logger

logger = get_logger("caching.single_flight")


class SingleFlightMutex:
    """Distributed single-flight coordinator using Redis atomic lock with wait-coalescing."""

    def __init__(self, redis_client, lock_timeout_seconds: int = 35):
        self.redis = redis_client
        self.lock_timeout = lock_timeout_seconds

    @staticmethod
    def compute_lock_key(
        normalized_query: str,
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
    ) -> str:
        """Constructs deterministic single-flight mutex key."""
        q_hash = hashlib.sha256(normalized_query.strip().encode("utf-8")).hexdigest()[:24]
        return f"rag:sf:{persona}:{language}:{answer_shape}:{filter_hash}:{q_hash}"

    async def try_acquire_leader(self, lock_key: str) -> bool:
        """Attempts to acquire single-flight leadership. Returns True if leader, False if follower."""
        if not self.redis:
            return True  # Fallback: allow execution if Redis is unavailable

        try:
            # SET lock_key "in_flight" NX EX timeout
            acquired = await self.redis.set(lock_key, "in_flight", ex=self.lock_timeout, nx=True)
            return bool(acquired)
        except Exception as exc:
            logger.warning("single_flight_acquire_error", error=str(exc))
            return True

    async def release_leader(self, lock_key: str) -> None:
        """Releases the leadership lock once execution and cache write have completed."""
        if not self.redis:
            return

        try:
            await self.redis.delete(lock_key)
        except Exception as exc:
            logger.warning("single_flight_release_error", error=str(exc))

    async def wait_for_leader(
        self,
        lookup_fn: Callable[[], Coroutine[Any, Any, Optional[Dict[str, Any]]]],
        max_wait_ms: int = 6000,
        poll_interval_ms: int = 150,
    ) -> Optional[Dict[str, Any]]:
        """Followers poll the cache while the leader executes to coalesce on the leader's output."""
        elapsed_ms = 0
        poll_interval_sec = poll_interval_ms / 1000.0

        while elapsed_ms < max_wait_ms:
            await asyncio.sleep(poll_interval_sec)
            elapsed_ms += poll_interval_ms

            result = await lookup_fn()
            if result is not None:
                logger.debug("single_flight_coalesced_success", elapsed_ms=elapsed_ms)
                result["coalesced"] = True
                return result

        logger.warning("single_flight_wait_timeout", max_wait_ms=max_wait_ms)
        return None
