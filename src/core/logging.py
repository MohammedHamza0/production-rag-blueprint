"""Structured logging with correlation ID context propagation."""

import contextvars
import logging
import sys
from typing import Any, Optional
import structlog

# Context variable for request correlation ID
correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> Optional[str]:
    """Retrieves current request correlation ID from context."""
    return correlation_id_ctx.get()


def bind_correlation_id(correlation_id: str) -> None:
    """Binds correlation ID to current asyncio context."""
    correlation_id_ctx.set(correlation_id)


def clear_correlation_id() -> None:
    """Clears correlation ID from current asyncio context."""
    correlation_id_ctx.set(None)


set_correlation_id = bind_correlation_id


def add_correlation_id_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Processor to inject correlation ID into every log event."""
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def setup_logging(environment: str = "production", log_level: str = "INFO") -> None:
    """Configures structured JSON logging for production or colored console for dev."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id_processor,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if environment == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Returns a structured bound logger."""
    return structlog.get_logger(name or "rag_blueprint")
