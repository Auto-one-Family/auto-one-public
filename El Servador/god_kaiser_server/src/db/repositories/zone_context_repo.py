"""
Zone Context Repository: Database Operations for ZoneContext

Phase: K3 → Phase 2 Refactoring
Status: IMPLEMENTED

Provides CRUD operations and specialized queries for ZoneContext model.
Follows the same patterns as other repositories for consistency.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.zone_context import ZoneContext


class ZoneContextRepository:
    """
    Zone Context Repository with zone-specific queries.

    ZoneContext uses integer auto-increment PK but zone_id (unique string)
    is the primary lookup key, so this doesn't extend BaseRepository
    (which expects UUID PKs).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_zone_id(self, zone_id: str) -> Optional[ZoneContext]:
        stmt = select(ZoneContext).where(ZoneContext.zone_id == zone_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> List[ZoneContext]:
        """Return all ZoneContext rows without pagination."""
        stmt = select(ZoneContext).order_by(ZoneContext.zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self, page: int = 1, page_size: int = 50) -> tuple[List[ZoneContext], int]:
        """Return paginated list and total count."""
        count_stmt = select(func.count()).select_from(ZoneContext)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = select(ZoneContext).order_by(ZoneContext.zone_id).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        contexts = list(result.scalars().all())
        return contexts, total

    async def upsert(self, zone_id: str, data: Dict[str, Any]) -> ZoneContext:
        """Create or fully replace zone context."""
        ctx = await self.get_by_zone_id(zone_id)

        if ctx:
            for key, value in data.items():
                setattr(ctx, key, value)
        else:
            ctx = ZoneContext(zone_id=zone_id, **data)
            self.session.add(ctx)

        await self.session.flush()
        await self.session.refresh(ctx)
        return ctx

    async def patch(self, zone_id: str, data: Dict[str, Any]) -> Optional[ZoneContext]:
        """Partial update — only provided fields."""
        ctx = await self.get_by_zone_id(zone_id)
        if not ctx:
            return None

        for key, value in data.items():
            setattr(ctx, key, value)

        await self.session.flush()
        await self.session.refresh(ctx)
        return ctx

    async def sync_zone_name(self, zone_id: str, zone_name: Optional[str]) -> None:
        """Update zone_name on existing context (no-op if context doesn't exist)."""
        ctx = await self.get_by_zone_id(zone_id)
        if ctx and zone_name and ctx.zone_name != zone_name:
            ctx.zone_name = zone_name
            await self.session.flush()

    async def archive_cycle(self, zone_id: str, archived_by: str) -> Optional[dict]:
        """Archive current cycle and reset cycle-specific fields.

        Returns the archived cycle dict, or None if zone not found.
        """
        ctx = await self.get_by_zone_id(zone_id)
        if not ctx:
            return None

        archived_cycle = {
            "variety": ctx.variety,
            "substrate": ctx.substrate,
            "growth_phase": ctx.growth_phase,
            "planted_date": ctx.planted_date.isoformat() if ctx.planted_date else None,
            "expected_harvest": ctx.expected_harvest.isoformat() if ctx.expected_harvest else None,
            "plant_count": ctx.plant_count,
            "notes": ctx.notes,
            "custom_data": ctx.custom_data or {},
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": archived_by,
            "plant_age_days": ctx.plant_age_days,
        }

        history = list(ctx.cycle_history or [])
        history.append(archived_cycle)
        ctx.cycle_history = history

        ctx.variety = None
        ctx.substrate = None
        ctx.growth_phase = None
        ctx.planted_date = None
        ctx.expected_harvest = None
        ctx.plant_count = None
        ctx.notes = None
        ctx.custom_data = {}

        await self.session.flush()
        await self.session.refresh(ctx)
        return archived_cycle

    async def get_zones_by_growth_phase(self, phase: str) -> List[ZoneContext]:
        stmt = select(ZoneContext).where(ZoneContext.growth_phase == phase)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_context_summary(self, zone_id: str) -> Optional[dict]:
        """Lightweight summary for device context inheritance."""
        ctx = await self.get_by_zone_id(zone_id)
        if not ctx:
            return None
        return {
            "zone_id": ctx.zone_id,
            "zone_name": ctx.zone_name,
            "variety": ctx.variety,
            "substrate": ctx.substrate,
            "growth_phase": ctx.growth_phase,
            "plant_count": ctx.plant_count,
            "plant_age_days": ctx.plant_age_days,
            "days_to_harvest": ctx.days_to_harvest,
            "responsible_person": ctx.responsible_person,
        }

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ZoneContext)
        result = await self.session.execute(stmt)
        return result.scalar_one()
