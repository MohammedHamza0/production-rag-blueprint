"""Security and data compliance audit logger."""

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.domain.schemas import utc_now
from src.infrastructure.models import SecurityAuditLogModel

logger = get_logger("observability.audit")


class SecurityAuditLogger:
    """Records security-critical events, authorization verdicts, and compliance actions."""

    @staticmethod
    async def record_event(
        actor_id: str,
        actor_role: str,
        action: str,
        target_resource: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> SecurityAuditLogModel:
        """Emits a structured audit log and persists to database when session is provided."""
        event_details = details or {}

        # 1. Structured log emission
        logger.info(
            "security_audit_event",
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_resource=target_resource,
            ip_address=ip_address,
            details=event_details,
        )

        record = SecurityAuditLogModel(
            timestamp=utc_now(),
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_resource=target_resource,
            ip_address=ip_address,
            user_agent=user_agent,
            details=event_details,
        )

        # 2. Database persistence if session is available
        if session is not None:
            try:
                session.add(record)
                await session.commit()
            except Exception as exc:
                logger.error("audit_log_database_write_failed", error=str(exc))
                # Do not raise to ensure audit persistence failure doesn't crash user flow

        return record
