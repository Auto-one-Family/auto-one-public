"""
Plan Segment Repository (AUT-1232)

Data-layer access for interval setpoints. Includes a pure read-at-tick
helper for segment uniqueness (GWT-1). Rule-engine wiring remains T3.
"""

from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plan_segment import PlanSegment
from .base_repo import BaseRepository


class PlanSegmentRepository(BaseRepository[PlanSegment]):
    """Repository for PlanSegment records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PlanSegment, session)

    async def list_for_zone_domain_measure(
        self,
        zone_id: str,
        domain: str,
        measure: str,
    ) -> List[PlanSegment]:
        """Return all segments for a zone×domain×measure, ordered by from_ts."""
        stmt = (
            select(PlanSegment)
            .where(
                PlanSegment.zone_id == zone_id,
                PlanSegment.domain == domain,
                PlanSegment.measure == measure,
            )
            .order_by(PlanSegment.from_ts.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        *,
        zone_id: Optional[str] = None,
        subzone_config_id: Optional[uuid.UUID] = None,
        domain: Optional[str] = None,
        measure: Optional[str] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
    ) -> List[PlanSegment]:
        """
        List segments with optional filters (zone / subzone / domain / measure / window).

        Zeitfenster: overlapping segments for half-open [from_ts, to_ts).
        Subzone: assigned to ``subzone_config_id`` OR zone-wide (no assignments),
        same applicability idea as ``resolve_at``.
        """
        from ..models.plan_segment import PlanSegmentSubzoneAssignment

        conditions = []
        if zone_id is not None:
            conditions.append(PlanSegment.zone_id == zone_id)
        if domain is not None:
            conditions.append(PlanSegment.domain == domain)
        if measure is not None:
            conditions.append(PlanSegment.measure == measure)
        if from_ts is not None:
            conditions.append(
                or_(PlanSegment.to_ts.is_(None), PlanSegment.to_ts > from_ts)
            )
        if to_ts is not None:
            conditions.append(PlanSegment.from_ts < to_ts)
        if subzone_config_id is not None:
            assigned_ids = select(PlanSegmentSubzoneAssignment.plan_segment_id).where(
                PlanSegmentSubzoneAssignment.subzone_config_id == subzone_config_id
            )
            has_any_assignment = (
                select(PlanSegmentSubzoneAssignment.id)
                .where(PlanSegmentSubzoneAssignment.plan_segment_id == PlanSegment.id)
                .exists()
            )
            conditions.append(
                or_(PlanSegment.id.in_(assigned_ids), ~has_any_assignment)
            )

        stmt = select(PlanSegment).order_by(PlanSegment.from_ts.asc())
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_at(
        self,
        *,
        zone_id: str,
        domain: str,
        measure: str,
        at: datetime,
        subzone_config_id: Optional[uuid.UUID] = None,
    ) -> Optional[PlanSegment]:
        """
        Resolve the single covering segment at ``at`` (half-open [from_ts, to_ts)).

        Zone-wide segments (no subzone assignments) always match. When
        ``subzone_config_id`` is given, segments assigned to that subzone also
        match. If multiple cover ``at``, the latest ``from_ts`` wins (stable
        uniqueness for abutting intervals).
        """
        # Local import avoids circular model import at module load.
        from ..models.plan_segment import PlanSegmentSubzoneAssignment

        covering = and_(
            PlanSegment.from_ts <= at,
            or_(PlanSegment.to_ts.is_(None), PlanSegment.to_ts > at),
        )

        if subzone_config_id is None:
            stmt = (
                select(PlanSegment)
                .where(
                    PlanSegment.zone_id == zone_id,
                    PlanSegment.domain == domain,
                    PlanSegment.measure == measure,
                    covering,
                )
                .order_by(PlanSegment.from_ts.desc())
                .limit(1)
            )
        else:
            # Zone-wide (no assignments) OR assigned to this subzone.
            assigned_ids = (
                select(PlanSegmentSubzoneAssignment.plan_segment_id)
                .where(
                    PlanSegmentSubzoneAssignment.subzone_config_id == subzone_config_id
                )
            )
            has_any_assignment = (
                select(PlanSegmentSubzoneAssignment.id)
                .where(PlanSegmentSubzoneAssignment.plan_segment_id == PlanSegment.id)
                .exists()
            )
            stmt = (
                select(PlanSegment)
                .where(
                    PlanSegment.zone_id == zone_id,
                    PlanSegment.domain == domain,
                    PlanSegment.measure == measure,
                    covering,
                    or_(
                        PlanSegment.id.in_(assigned_ids),
                        ~has_any_assignment,
                    ),
                )
                .order_by(PlanSegment.from_ts.desc())
                .limit(1)
            )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_subzone_assignment_ids(
        self, plan_segment_id: uuid.UUID
    ) -> List[uuid.UUID]:
        """
        Return the subzone_config_ids a segment is explicitly assigned to.

        Empty list means the segment applies zone-wide (no assignments).
        Used by callers (e.g. TankService.get_targets_at_now) to distinguish
        a zone-wide match from a subzone-specific match after resolve_at().
        """
        from ..models.plan_segment import PlanSegmentSubzoneAssignment

        stmt = select(PlanSegmentSubzoneAssignment.subzone_config_id).where(
            PlanSegmentSubzoneAssignment.plan_segment_id == plan_segment_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
