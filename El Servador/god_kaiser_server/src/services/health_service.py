"""Health Monitoring Service.

Phase: AUT-224 Server Cleanup A (API-Konsistenz)
Status: IMPLEMENTED

Hosts shared query helpers used by ``api/v1/health.py``. Keeping these
queries here means the API layer no longer needs raw ``select`` /
``and_``/``desc`` imports.
"""

from typing import Dict, List

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import AuditLog, AuditSourceType

logger = get_logger(__name__)


class HealthService:
    """Light-weight read-only helpers for the health router."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_recent_esp_errors(
        self,
        esp_device_ids: List[str],
        *,
        max_per_device: int = 5,
        limit: int = 50,
    ) -> Dict[str, List[AuditLog]]:
        """Return ``{esp_id: [audit_log, ...]}`` for the given problem ESPs.

        Picks ESP32-sourced audit entries with severity warning/error/critical,
        capped at ``max_per_device`` rows per ESP and ``limit`` rows total.
        """
        if not esp_device_ids:
            return {}

        stmt = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.source_type == AuditSourceType.ESP32,
                    AuditLog.source_id.in_(esp_device_ids),
                    AuditLog.severity.in_(["warning", "error", "critical"]),
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        entries = list(result.scalars().all())

        grouped: Dict[str, List[AuditLog]] = {}
        for entry in entries:
            did = entry.source_id
            if did is None:
                continue
            bucket = grouped.setdefault(did, [])
            if len(bucket) < max_per_device:
                bucket.append(entry)
        return grouped
