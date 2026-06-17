"""Error Reporting Service — Aggregates audit-log error events for the API layer.

Phase: AUT-224 Server Cleanup A (API-Konsistenz)
Status: IMPLEMENTED

Responsibilities:
- ESP-scoped error event listing (paginated)
- System-wide error summary (severity, category, ESP, top error codes)

Design notes:
- Reads ``audit_log`` rows of type ``MQTT_ERROR`` (already populated by the
  MQTT error-event handler). No direct ORM access leaks into ``api/v1/errors.py``.
- Uses ``AsyncSession.execute()`` with explicit ``select`` statements (consistent
  with other services that need aggregations beyond what BaseRepository provides).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import (
    AuditEventType,
    AuditLog,
    AuditSeverity,
    AuditSourceType,
)

logger = get_logger(__name__)


class ErrorService:
    """Service-layer wrapper around audit-log error queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_esp_errors(
        self,
        esp_id: str,
        *,
        hours: int = 24,
        severity: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[AuditLog], int, int]:
        """Return (logs, total_count, unacknowledged_count) for an ESP.

        ``unacknowledged_count`` is approximated by counting events with
        severity ERROR or CRITICAL — same heuristic as the previous inline
        implementation in ``api/v1/errors.py``.
        """
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        conditions = [
            AuditLog.source_type == AuditSourceType.MQTT,
            AuditLog.source_id == esp_id,
            AuditLog.event_type == AuditEventType.MQTT_ERROR,
            AuditLog.created_at >= start_time,
        ]

        if severity:
            conditions.append(AuditLog.severity == severity.lower())

        # Total count
        count_stmt = select(func.count(AuditLog.id)).where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total_count = int(count_result.scalar_one())

        # Unacknowledged (severity >= warning)
        unack_conditions = conditions + [
            AuditLog.severity.in_([AuditSeverity.ERROR, AuditSeverity.CRITICAL])
        ]
        unack_stmt = select(func.count(AuditLog.id)).where(and_(*unack_conditions))
        unack_result = await self.session.execute(unack_stmt)
        unacknowledged_count = int(unack_result.scalar_one())

        # Page slice
        offset = max(0, (page - 1) * page_size)
        logs_stmt = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(desc(AuditLog.created_at))
            .offset(offset)
            .limit(page_size)
        )
        logs_result = await self.session.execute(logs_stmt)
        logs = list(logs_result.scalars().all())

        return logs, total_count, unacknowledged_count

    async def get_error_summary(self, *, hours: int = 24) -> Dict[str, Any]:
        """Aggregate error statistics across all ESPs over the given window.

        Returns a dict with the keys consumed by ``ErrorSummaryResponse``:
        ``total_errors``, ``errors_by_severity``, ``errors_by_category``,
        ``errors_by_esp``, ``error_code_counts`` and ``action_required_count``.
        """
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        base_conditions = [
            AuditLog.source_type == AuditSourceType.MQTT,
            AuditLog.event_type == AuditEventType.MQTT_ERROR,
            AuditLog.created_at >= start_time,
        ]

        # Total errors
        total_stmt = select(func.count(AuditLog.id)).where(and_(*base_conditions))
        total_result = await self.session.execute(total_stmt)
        total_errors = int(total_result.scalar_one())

        # By severity
        severity_stmt = (
            select(AuditLog.severity, func.count(AuditLog.id).label("count"))
            .where(and_(*base_conditions))
            .group_by(AuditLog.severity)
        )
        severity_result = await self.session.execute(severity_stmt)
        errors_by_severity: Dict[str, int] = {
            row.severity: int(row.count) for row in severity_result.all() if row.severity
        }

        # By ESP
        esp_stmt = (
            select(AuditLog.source_id, func.count(AuditLog.id).label("count"))
            .where(and_(*base_conditions))
            .group_by(AuditLog.source_id)
        )
        esp_result = await self.session.execute(esp_stmt)
        errors_by_esp: Dict[str, int] = {
            row.source_id: int(row.count) for row in esp_result.all() if row.source_id
        }

        # Walk all logs once to extract category + error_code from JSON details
        logs_stmt = select(AuditLog).where(and_(*base_conditions))
        logs_result = await self.session.execute(logs_stmt)
        logs = list(logs_result.scalars().all())

        errors_by_category: Dict[str, int] = {}
        error_code_counts: Dict[int, int] = {}
        action_required_count = 0

        for log in logs:
            details = log.details or {}
            category = details.get("category")
            if category:
                errors_by_category[category] = errors_by_category.get(category, 0) + 1
            error_code = details.get("error_code")
            if error_code:
                error_code_counts[error_code] = error_code_counts.get(error_code, 0) + 1
            if details.get("user_action_required"):
                action_required_count += 1

        return {
            "total_errors": total_errors,
            "errors_by_severity": errors_by_severity,
            "errors_by_esp": errors_by_esp,
            "errors_by_category": errors_by_category,
            "error_code_counts": error_code_counts,
            "action_required_count": action_required_count,
        }
