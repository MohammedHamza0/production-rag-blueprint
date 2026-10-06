"""Health and readiness probe endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.dependencies import get_db_session
from src.domain.schemas import HealthResponse
from src.infrastructure.redis_client import get_redis_client

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthResponse)
async def liveness_probe():
    """Liveness probe: returns 200 if ASGI application server is running."""
    return HealthResponse(
        status="live",
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
        database="unknown",
        redis="unknown",
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_probe(session: AsyncSession = Depends(get_db_session)):
    """Readiness probe: validates connectivity to PostgreSQL and Redis."""
    db_status = "unhealthy"
    redis_status = "unhealthy"

    # Check PostgreSQL
    try:
        await session.execute(text("SELECT 1;"))
        db_status = "healthy"
    except Exception:
        db_status = "down"

    # Check Redis
    try:
        redis = get_redis_client()
        if redis:
            pong = await redis.ping()
            if pong:
                redis_status = "healthy"
        else:
            redis_status = "not_configured"
    except Exception:
        redis_status = "down"

    is_ready = (db_status == "healthy") and (redis_status in ["healthy", "not_configured"])
    res = HealthResponse(
        status="ready" if is_ready else "degraded",
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
        database=db_status,
        redis=redis_status,
    )

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=res.model_dump(),
        )

    return res
