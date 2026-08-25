"""
Sensor Subzone Assignment Repository

AUT-1155 [B1] n:m Sensor-Subzone-Zuordnung

Provides CRUD operations and lookup queries for the SensorSubzoneAssignment
junction table.  Follows the same patterns as DashboardUserAssignmentRepository
(if present) and SubzoneRepository for consistency.
"""

import uuid
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.sensor_subzone_assignment import SensorSubzoneAssignment
from .base_repo import BaseRepository


class SensorSubzoneAssignmentRepository(BaseRepository[SensorSubzoneAssignment]):
    """
    Repository for SensorSubzoneAssignment junction-table records.

    Extends BaseRepository with assignment-specific lookup and
    upsert/delete helpers.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SensorSubzoneAssignment, session)

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_by_sensor(self, sensor_config_id: uuid.UUID) -> List[SensorSubzoneAssignment]:
        """
        Return all assignments for a given sensor config.

        Args:
            sensor_config_id: UUID of the sensor_config row

        Returns:
            List of SensorSubzoneAssignment instances (may be empty)
        """
        stmt = select(SensorSubzoneAssignment).where(
            SensorSubzoneAssignment.sensor_config_id == sensor_config_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_subzone(self, subzone_config_id: uuid.UUID) -> List[SensorSubzoneAssignment]:
        """
        Return all assignments for a given subzone config.

        Args:
            subzone_config_id: UUID of the subzone_config row

        Returns:
            List of SensorSubzoneAssignment instances (may be empty)
        """
        stmt = select(SensorSubzoneAssignment).where(
            SensorSubzoneAssignment.subzone_config_id == subzone_config_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignments_for_subzones(
        self, subzone_config_ids: List[uuid.UUID]
    ) -> List[SensorSubzoneAssignment]:
        """
        Return all n:m assignments where subzone_config_id is in the given list.

        Used by MonitorDataService to load all sensor→subzone assignments for a
        zone in a single IN-query (pass the subzone_config.id primary-key values
        collected during the SubzoneConfig load step).

        AUT-1179: Enables the zone monitor aggregation to resolve sensors via the
        n:m junction table in addition to the legacy GPIO-based path.

        Args:
            subzone_config_ids: List of subzone_config primary-key UUIDs

        Returns:
            List of SensorSubzoneAssignment instances (may be empty)
        """
        if not subzone_config_ids:
            return []
        stmt = select(SensorSubzoneAssignment).where(
            SensorSubzoneAssignment.subzone_config_id.in_(subzone_config_ids)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_assignment(
        self,
        sensor_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> Optional[SensorSubzoneAssignment]:
        """
        Return a specific assignment, or None if it does not exist.

        Args:
            sensor_config_id: UUID of the sensor_config row
            subzone_config_id: UUID of the subzone_config row

        Returns:
            SensorSubzoneAssignment or None
        """
        stmt = select(SensorSubzoneAssignment).where(
            and_(
                SensorSubzoneAssignment.sensor_config_id == sensor_config_id,
                SensorSubzoneAssignment.subzone_config_id == subzone_config_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Write Methods
    # =========================================================================

    async def assign(
        self,
        sensor_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
        assigned_by: Optional[int] = None,
    ) -> SensorSubzoneAssignment:
        """
        Create a new sensor→subzone assignment.

        Caller is responsible for checking duplicates (UniqueConstraint raises
        IntegrityError on the DB layer) and for commit/rollback.

        Args:
            sensor_config_id: UUID of the sensor_config row
            subzone_config_id: UUID of the subzone_config row
            assigned_by: User ID of the operator performing the assignment

        Returns:
            The newly created SensorSubzoneAssignment instance
        """
        row = SensorSubzoneAssignment(
            sensor_config_id=sensor_config_id,
            subzone_config_id=subzone_config_id,
            assigned_by=assigned_by,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def unassign(
        self,
        sensor_config_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> bool:
        """
        Delete a specific assignment.

        Args:
            sensor_config_id: UUID of the sensor_config row
            subzone_config_id: UUID of the subzone_config row

        Returns:
            True if the row was found and deleted, False if it did not exist
        """
        row = await self.get_assignment(sensor_config_id, subzone_config_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def unassign_all_for_sensor(self, sensor_config_id: uuid.UUID) -> int:
        """
        Delete all assignments for a sensor config (e.g. on sensor deletion).

        Args:
            sensor_config_id: UUID of the sensor_config row

        Returns:
            Number of rows deleted
        """
        rows = await self.get_by_sensor(sensor_config_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)

    async def unassign_all_for_subzone(self, subzone_config_id: uuid.UUID) -> int:
        """
        Delete all assignments for a subzone config (e.g. on subzone deletion).

        Args:
            subzone_config_id: UUID of the subzone_config row

        Returns:
            Number of rows deleted
        """
        rows = await self.get_by_subzone(subzone_config_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)
