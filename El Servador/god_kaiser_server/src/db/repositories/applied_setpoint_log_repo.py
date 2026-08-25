"""
Applied Setpoint Log Repository (AUT-1232)

Append-only access for applied_setpoint_logs. Write path used by T3;
read path (list_filtered) used by T6 past-overlay / AUT-1243 origin display.
"""

from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.applied_setpoint_log import AppliedSetpointLog
from .base_repo import BaseRepository


class AppliedSetpointLogRepository(BaseRepository[AppliedSetpointLog]):
    """Repository for immutable AppliedSetpointLog rows."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AppliedSetpointLog, session)

    async def list_filtered(
        self,
        *,
        zone_id: Optional[str] = None,
        subzone_config_id: Optional[uuid.UUID] = None,
        domain: Optional[str] = None,
        measure: Optional[str] = None,
        rule_id: Optional[uuid.UUID] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[AppliedSetpointLog]:
        """
        List immutable applied rows (read-only).

        Zeitfenster: half-open [from_ts, to_ts) on ``effective_at``.
        Ordered by effective_at ascending (stable for overlay stitching).
        """
        conditions = []
        if zone_id is not None:
            conditions.append(AppliedSetpointLog.zone_id == zone_id)
        if subzone_config_id is not None:
            conditions.append(AppliedSetpointLog.subzone_config_id == subzone_config_id)
        if domain is not None:
            conditions.append(AppliedSetpointLog.domain == domain)
        if measure is not None:
            conditions.append(AppliedSetpointLog.measure == measure)
        if rule_id is not None:
            conditions.append(AppliedSetpointLog.rule_id == rule_id)
        if from_ts is not None:
            conditions.append(AppliedSetpointLog.effective_at >= from_ts)
        if to_ts is not None:
            conditions.append(AppliedSetpointLog.effective_at < to_ts)

        stmt = (
            select(AppliedSetpointLog)
            .order_by(AppliedSetpointLog.effective_at.asc())
            .limit(max(1, min(limit, 2000)))
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
