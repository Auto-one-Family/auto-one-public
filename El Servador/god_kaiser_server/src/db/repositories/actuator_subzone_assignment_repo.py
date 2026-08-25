"""
Actuator Subzone Assignment Repository

n:m Actuator-Subzone-Zuordnung (Verortung / Auswertung)

Provides CRUD operations and lookup queries for the ActuatorSubzoneAssignment
junction table. Pattern: 1:1 after SensorSubzoneAssignmentRepository (AUT-1155).
"""

import uuid
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.actuator_subzone_assignment import ActuatorSubzoneAssignment
from .base_repo import BaseRepository


class ActuatorSubzoneAssignmentRepository(BaseRepository[ActuatorSubzoneAssignment]):
    """
    Repository for ActuatorSubzoneAssignment junction-table records.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ActuatorSubzoneAssignment, session)

    async def get_by_actuator(
        self, actuator_config_id: uuid.UUID
    ) -> List[ActuatorSubzoneAssignment]:
        """Return all assignments for a given actuator config."""
        stmt = select(ActuatorSubzoneAssignment).where(
            ActuatorSubzoneAssignment.actuator_config_id == actuator_config_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_subzone(self, subzone_config_id: uuid.UUID) -> List[ActuatorSubzoneAssignment]:
        """Return all assignments for a given subzone config."""
        stmt = select(ActuatorSubzoneAssignment).where(
            ActuatorSubzoneAssignment.subzone_config_id == subzone_config_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignments_for_subzones(
        self, subzone_config_ids: List[uuid.UUID]
    ) -> List[ActuatorSubzoneAssignment]:
        """
        Return all n:m assignments where subzone_config_id is in the given list.

        Used by MonitorDataService for zone monitor aggregation (Verortung).
        """
        if not subzone_config_ids:
            return []
        stmt = select(ActuatorSubzoneAssignment).where(
            ActuatorSubzoneAssignment.subzone_config_id.in_(subzone_config_ids)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignment(
        self,
        actuator_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> Optional[ActuatorSubzoneAssignment]:
        """Return a specific assignment, or None if it does not exist."""
        stmt = select(ActuatorSubzoneAssignment).where(
            and_(
                ActuatorSubzoneAssignment.actuator_config_id == actuator_config_id,
                ActuatorSubzoneAssignment.subzone_config_id == subzone_config_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign(
        self,
        actuator_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
        assigned_by: Optional[int] = None,
    ) -> ActuatorSubzoneAssignment:
        """Create a new actuator→subzone assignment."""
        row = ActuatorSubzoneAssignment(
            actuator_config_id=actuator_config_id,
            subzone_config_id=subzone_config_id,
            assigned_by=assigned_by,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def unassign(
        self,
        actuator_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> bool:
        """Delete a specific assignment. Returns True if a row was deleted."""
        row = await self.get_assignment(actuator_config_id, subzone_config_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def unassign_all_for_actuator(self, actuator_config_id: uuid.UUID) -> int:
        """Delete all assignments for an actuator config."""
        rows = await self.get_by_actuator(actuator_config_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)

    async def unassign_all_for_subzone(self, subzone_config_id: uuid.UUID) -> int:
        """Delete all assignments for a subzone config."""
        rows = await self.get_by_subzone(subzone_config_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)
