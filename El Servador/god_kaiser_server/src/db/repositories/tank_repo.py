"""
Tank Repository

AUT-1217 — CRUD for nutrient-solution tanks (zone-scoped reservoirs).
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tank import Tank
from .base_repo import BaseRepository


class TankRepository(BaseRepository[Tank]):
    """Repository for Tank entity records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tank, session)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Tank]:
        """Return all tanks ordered by name (deterministic listing, AUT-1223 Q3)."""
        stmt = select(Tank).order_by(Tank.name).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_zone(self, zone_id: str) -> List[Tank]:
        """Return all tanks belonging to a zone."""
        stmt = select(Tank).where(Tank.zone_id == zone_id).order_by(Tank.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_zone_and_name(self, zone_id: str, name: str) -> Optional[Tank]:
        """Return a tank by zone + name, or None."""
        stmt = select(Tank).where(Tank.zone_id == zone_id, Tank.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
