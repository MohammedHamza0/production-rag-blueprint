"""Main ASGI FastAPI application entrypoint for the Production RAG Blueprint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from src.api.exception_handlers import (
    http_exception_handler,
    rag_base_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.api.middleware.correlation import CorrelationIdMiddleware
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.routes import chat, documents, health, search
from src.core.config import get_settings
from src.core.exceptions import RAGBaseException
from src.core.logging import get_logger, setup_logging
from src.infrastructure.database import close_db_engine
from src.infrastructure.redis_client import close_redis_pool, get_redis_client, init_redis_pool

# Initialize structured logging subsystem
setup_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager initializing and closing connection pools."""
    settings = get_settings()
    logger.info(
        "application_starting",
        environment=settings.environment,
        chat_model=settings.gemini_default_model,
        embedding_model=settings.default_embedding_model,
    )

    # Initialize Redis pool
    try:
        await init_redis_pool()
        logger.info("redis_pool_initialized")
    except Exception as exc:
        logger.warning("redis_pool_init_failed", error=str(exc))

    yield

    # Graceful shutdown
    logger.info("application_shutting_down")
    try:
        await close_redis_pool()
        await close_db_engine()
        logger.info("connection_pools_closed_cleanly")
    except Exception as exc:
        logger.error("shutdown_cleanup_error", error=str(exc))


def create_app() -> FastAPI:
    """Factory creating and configuring the production FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title="Production RAG Blueprint API",
        description="Enterprise-grade generalized multilingual RAG blueprint with 5-way hybrid RRF, 2-tier semantic cache, and parent-child chunking.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # 1. Register Exception Handlers (RFC 7807)
    app.add_exception_handler(RAGBaseException, rag_base_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 2. Register Middleware (Order: Outer to Inner)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    redis = get_redis_client()
    app.add_middleware(RateLimitMiddleware, redis_client=redis)

    # 3. Include API Routers
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(search.router)
    app.include_router(documents.router)

    # 4. Prometheus Metrics Endpoint
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        from fastapi.responses import Response
        from src.observability.metrics import metrics_collector
        content = metrics_collector.generate_prometheus_exposition()
        return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")

    return app



app = create_app()
