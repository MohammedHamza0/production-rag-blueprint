"""Async Redis connection management, pool lifecycle, and health checking."""

from typing import Optional
import redis.asyncio as aioredis
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger("redis")

_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Returns singleton async Redis client."""
    global _redis_pool, _redis_client
    if _redis_client is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,
        )
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)
    return _redis_client


async def check_redis_connection() -> bool:
    """Checks whether Redis is reachable and responds to PING."""
    client = get_redis_client()
    try:
        res = await client.ping()
        return bool(res)
    except Exception as e:
        logger.error("redis_connection_check_failed", error=str(e))
        return False


async def init_redis_pool() -> None:
    """Initializes Redis connection pool."""
    get_redis_client()


async def close_redis() -> None:
    """Closes Redis client and connection pool cleanly on shutdown."""
    global _redis_pool, _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("redis_connection_pool_closed")


close_redis_pool = close_redis

