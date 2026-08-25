"""
Tank Subzone Assignment Repository

AUT-1217 — n:m tank↔subzone assignments.

Modelled 1:1 after SensorSubzoneAssignmentRepository (AUT-1155).
"""

import uuid
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tank_subzone_assignment import TankSubzoneAssignment
from .base_repo import BaseRepository


class TankSubzoneAssignmentRepository(BaseRepository[TankSubzoneAssignment]):
    """Repository for TankSubzoneAssignment junction-table records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TankSubzoneAssignment, session)

    async def get_by_tank(self, tank_id: uuid.UUID) -> List[TankSubzoneAssignment]:
        """Return all assignments for a given tank."""
        stmt = select(TankSubzoneAssignment).where(TankSubzoneAssignment.tank_id == tank_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_subzone(self, subzone_config_id: uuid.UUID) -> List[TankSubzoneAssignment]:
        """Return all assignments for a given subzone config."""
        stmt = select(TankSubzoneAssignment).where(
            TankSubzoneAssignment.subzone_config_id == subzone_config_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignment(
        self,
        tank_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> Optional[TankSubzoneAssignment]:
        """Return a specific assignment, or None if it does not exist."""
        stmt = select(TankSubzoneAssignment).where(
            and_(
                TankSubzoneAssignment.tank_id == tank_id,
                TankSubzoneAssignment.subzone_config_id == subzone_config_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign(
        self,
        tank_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
        assigned_by: Optional[int] = None,
    ) -> TankSubzoneAssignment:
        """
        Create a new tank→subzone assignment.

        Caller is responsible for checking duplicates and for commit/rollback.
        """
        row = TankSubzoneAssignment(
            tank_id=tank_id,
            subzone_config_id=subzone_config_id,
            assigned_by=assigned_by,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def unassign(
        self,
        tank_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> bool:
        """Delete a specific assignment. Returns True if deleted."""
        row = await self.get_assignment(tank_id, subzone_config_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
