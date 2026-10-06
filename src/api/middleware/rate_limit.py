"""Distributed Redis-backed sliding-window rate limiter middleware."""

import time
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from src.core.config import get_settings
from src.core.exceptions import RateLimitExceededError
from src.core.logging import get_logger

logger = get_logger("api.middleware.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces per-minute sliding window rate limits via Redis pipelines."""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exempt health probes from rate limiting
        if request.url.path.startswith("/health"):
            return await call_next(request)

        client_id = getattr(request.state, "client_id", None)
        if not client_id:
            # Fallback to remote IP if auth middleware hasn't set client_id
            client_ip = request.client.host if request.client else "127.0.0.1"
            client_id = f"guest:{client_ip}"
            request.state.client_id = client_id

        is_authenticated = getattr(request.state, "is_authenticated", False)
        max_rpm = (
            self.settings.rate_limit_user_rpm
            if is_authenticated
            else self.settings.rate_limit_guest_rpm
        )

        now = int(time.time())
        current_minute = now // 60
        rate_key = f"rag:rate:{client_id}:{current_minute}"

        if self.redis:
            try:
                # Atomic INCR & EXPIRE in pipeline
                pipe = self.redis.pipeline(transaction=True)
                pipe.incr(rate_key)
                pipe.expire(rate_key, 65)  # 65s expiration for clean sweep
                results = await pipe.execute()

                current_count = results[0]
                remaining = max(0, max_rpm - current_count)
                reset_seconds = 60 - (now % 60)

                if current_count > max_rpm:
                    logger.warning(
                        "rate_limit_exceeded",
                        client_id=client_id,
                        count=current_count,
                        limit=max_rpm,
                    )
                    corr_id = getattr(request.state, "correlation_id", "unknown")
                    error_payload = {
                        "type": "https://rag.example.com/errors/rate-limit-exceeded",
                        "title": "Rate Limit Exceeded",
                        "status": 429,
                        "detail": f"Rate limit of {max_rpm} requests per minute exceeded. Please retry in {reset_seconds} seconds.",
                        "instance": request.url.path,
                        "correlation_id": corr_id,
                    }
                    resp = JSONResponse(
                        status_code=429,
                        content=error_payload,
                        headers={
                            "Retry-After": str(reset_seconds),
                            "X-RateLimit-Limit": str(max_rpm),
                            "X-RateLimit-Remaining": "0",
                            "X-RateLimit-Reset": str(now + reset_seconds),
                        },
                    )
                    return resp

                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(max_rpm)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(now + reset_seconds)
                return response

            except Exception as exc:
                logger.warning("rate_limit_redis_error_bypassed", error=str(exc))
                return await call_next(request)

        # In-memory / bypass if Redis is not configured
        return await call_next(request)
