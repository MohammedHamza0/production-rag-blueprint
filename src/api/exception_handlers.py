"""Global RFC 7807 Problem Details exception handlers for FastAPI."""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.core.exceptions import RAGBaseException
from src.core.logging import get_logger

logger = get_logger("api.exceptions")


async def rag_base_exception_handler(request: Request, exc: RAGBaseException) -> JSONResponse:
    """Handles all domain RAGBaseException hierarchy instances."""
    corr_id = getattr(request.state, "correlation_id", "unknown")
    logger.warning(
        "rag_domain_exception",
        code=exc.code,
        status_code=exc.status_code,
        message=exc.message,
        path=request.url.path,
        correlation_id=corr_id,
    )

    payload = {
        "type": f"https://rag.example.com/errors/{exc.code.lower().replace('_', '-')}",
        "title": exc.code.replace("_", " ").title(),
        "status": exc.status_code,
        "detail": exc.message,
        "instance": request.url.path,
        "correlation_id": corr_id,
        "details": exc.details,
    }
    return JSONResponse(status_code=exc.status_code, content=payload)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Converts FastAPI standard HTTPExceptions to RFC 7807."""
    corr_id = getattr(request.state, "correlation_id", "unknown")
    payload = {
        "type": f"https://rag.example.com/errors/http-{exc.status_code}",
        "title": "HTTP Error",
        "status": exc.status_code,
        "detail": str(exc.detail),
        "instance": request.url.path,
        "correlation_id": corr_id,
    }
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles Pydantic request body and query param validation errors."""
    corr_id = getattr(request.state, "correlation_id", "unknown")
    payload = {
        "type": "https://rag.example.com/errors/validation-error",
        "title": "Validation Error",
        "status": 422,
        "detail": "Request body or parameters failed validation schema.",
        "instance": request.url.path,
        "correlation_id": corr_id,
        "errors": exc.errors(),
    }
    return JSONResponse(status_code=422, content=payload)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler preventing stack trace leaks on unexpected crashes."""
    corr_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(
        "unhandled_server_exception",
        error=str(exc),
        path=request.url.path,
        correlation_id=corr_id,
        exc_info=True,
    )

    payload = {
        "type": "https://rag.example.com/errors/internal-server-error",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected server error occurred. Please contact administrator with the correlation ID.",
        "instance": request.url.path,
        "correlation_id": corr_id,
    }
    return JSONResponse(status_code=500, content=payload)
