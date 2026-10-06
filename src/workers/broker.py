"""Taskiq Redis asynchronous worker broker and lifecycle management."""

from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.config import settings
from src.core.logging import get_logger
from src.infrastructure.database import close_db_engine, init_db_engine
from src.infrastructure.redis_client import close_redis_pool, init_redis_pool

logger = get_logger("workers.broker")

# Result backend for tracking task outcomes
result_backend = RedisAsyncResultBackend(redis_url=settings.redis_url)

# Core ListQueueBroker over Redis
broker = ListQueueBroker(
    url=settings.redis_url,
    queue_name="rag_ingestion_queue",
).with_result_backend(result_backend)



@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def worker_startup(state: TaskiqState) -> None:
    """Initializes database engine and Redis pools on worker launch."""
    logger.info("taskiq_worker_starting_up", queue="rag_ingestion_queue")
    try:
        init_db_engine()
        await init_redis_pool()
        logger.info("taskiq_worker_initialized_successfully")
    except Exception as exc:
        logger.error("taskiq_worker_startup_failed", error=str(exc))
        raise


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def worker_shutdown(state: TaskiqState) -> None:
    """Closes all network pools gracefully when worker terminates."""
    logger.info("taskiq_worker_shutting_down")
    try:
        await close_db_engine()
        await close_redis_pool()
        logger.info("taskiq_worker_shutdown_complete")
    except Exception as exc:
        logger.warning("taskiq_worker_shutdown_warning", error=str(exc))
