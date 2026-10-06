"""Correlation ID middleware for end-to-end distributed tracing across requests."""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from src.core.logging import clear_correlation_id, set_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensures every incoming HTTP request has a unique correlation ID for structured logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        set_correlation_id(corr_id)
        request.state.correlation_id = corr_id

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            clear_correlation_id()
