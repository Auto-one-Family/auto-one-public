"""
Salt Composition Repository (AUT-1418 / B1).
"""

from __future__ import annotations

from typing import List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.salt_composition import SaltComposition
from .base_repo import BaseRepository


class SaltCompositionRepository(BaseRepository[SaltComposition]):
    """Data access for salt_compositions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SaltComposition, session)

    async def list_filtered(
        self,
        *,
        source_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[SaltComposition]:
        conditions = []
        if active_only:
            conditions.append(SaltComposition.active.is_(True))
        if source_type is not None:
            conditions.append(SaltComposition.source_type == source_type)

        stmt = select(SaltComposition)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(SaltComposition.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(
        self,
        name: str,
        *,
        active_only: bool = True,
    ) -> Optional[SaltComposition]:
        conditions = [SaltComposition.name == name]
        if active_only:
            conditions.append(SaltComposition.active.is_(True))
        stmt = select(SaltComposition).where(*conditions).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_fields(
        self,
        salt_id: uuid.UUID,
        **fields: object,
    ) -> Optional[SaltComposition]:
        """Patch provided fields (caller passes exclude_unset dump)."""
        row = await self.get_by_id(salt_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        await self.session.flush()
        await self.session.refresh(row)
        return row
