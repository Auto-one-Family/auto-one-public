"""
Plant Repository: CRUD + lookup methods for the Plant entity.

AUT-222 — Phyta Plants Schema. Pattern parallels :class:`ESPRepository`:
soft-delete-aware listing helpers and explicit ``include_deleted`` flags
on lookups.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plant import Plant
from ..models.sensor import SensorData
from .base_repo import BaseRepository


class PlantRepository(BaseRepository[Plant]):
    """
    Plant Repository with plant-specific queries.

    Extends BaseRepository with QR code / external ID lookups and
    soft-delete-aware listing.

    Soft-Delete:
    - All listing methods exclude soft-deleted plants by default.
    - ``include_deleted=True`` is provided for audit / admin queries.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Plant, session)

    @staticmethod
    def _not_deleted():
        """Filter clause to exclude soft-deleted plants."""
        return Plant.deleted_at.is_(None)

    async def get_by_plant_id(
        self,
        plant_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its primary key.

        Args:
            plant_id: Plant UUID.
            include_deleted: If True, also return soft-deleted plants.

        Returns:
            ``Plant`` instance or ``None`` if not found.
        """
        stmt = select(Plant).where(Plant.plant_id == plant_id)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_qr_code(
        self,
        qr_code: str,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its QR code (e.g. ``PL-A1B2C3D4``).

        QR codes are unique per ``(kaiser_id, qr_code)`` for active rows;
        for lookup we treat the code as globally unique among active plants.
        """
        stmt = select(Plant).where(Plant.qr_code == qr_code)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self,
        external_id: str,
        kaiser_id: Optional[str] = None,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its ``external_plant_id``.

        Args:
            external_id: External plant ID (PhotosynQ etc.).
            kaiser_id: Optional tenant filter.
            include_deleted: If True, also return soft-deleted plants.
        """
        conditions = [Plant.external_plant_id == external_id]
        if kaiser_id is not None:
            conditions.append(Plant.kaiser_id == kaiser_id)
        if not include_deleted:
            conditions.append(self._not_deleted())

        stmt = select(Plant).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(
        self,
        kaiser_id: Optional[str] = None,
        phase: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Plant]:
        """
        List active (non-soft-deleted) plants.

        Args:
            kaiser_id: Optional tenant filter.
            phase: Optional phase filter (e.g. ``'veg-frueh'``).
            skip: Pagination offset.
            limit: Maximum number of rows.
        """
        conditions = [self._not_deleted()]
        if kaiser_id is not None:
            conditions.append(Plant.kaiser_id == kaiser_id)
        if phase is not None:
            conditions.append(Plant.phase == phase)

        stmt = (
            select(Plant)
            .where(and_(*conditions))
            .order_by(Plant.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_sensor_data_for_plant(
        self,
        plant_id: uuid.UUID,
        cutoff: datetime,
        limit: int,
    ) -> list[SensorData]:
        """
        Get sensor_data rows for a plant within a time window.

        Args:
            plant_id: Plant UUID (matches ``sensor_data.plant_id``).
            cutoff: Earliest timestamp to include (inclusive).
            limit: Maximum number of rows to return (newest first).

        Returns:
            List of ``SensorData`` instances ordered by timestamp descending.
        """
        stmt = (
            select(SensorData)
            .where(
                and_(
                    SensorData.plant_id == plant_id,
                    SensorData.timestamp >= cutoff,
                )
            )
            .order_by(SensorData.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_zone_phase_histogram(
        self,
        zone_id: str,
    ) -> dict[str, int]:
        """
        Return a phase-count histogram for all active plants in a zone.

        Plants are resolved via ``SubzoneConfig.parent_zone_id`` joined on
        ``Plant.subzone_id``.  Only non-soft-deleted plants are counted.

        Args:
            zone_id: Zone identifier string.

        Returns:
            Dict mapping ``phase`` (str) to count (int).  Empty dict when
            the zone has no active plants.
        """
        # Local import — SubzoneConfig is used only here and in the one
        # other zone-plant method to avoid polluting the module-level imports.
        from ..models.subzone import SubzoneConfig

        stmt = (
            select(Plant.phase, func.count(Plant.plant_id))
            .join(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(
                and_(
                    SubzoneConfig.parent_zone_id == zone_id,
                    Plant.deleted_at.is_(None),
                )
            )
            .group_by(Plant.phase)
        )
        result = await self.session.execute(stmt)
        return {phase: int(count) for phase, count in result.all()}

    async def get_zone_avg_phi2(
        self,
        zone_id: str,
        phi2_sensor_type: str,
        cutoff: datetime,
    ) -> Optional[float]:
        """
        Return the average ``processed_value`` of phi2 sensor readings for
        plants in a given zone over a time window.

        Uses a subquery to collect relevant plant IDs first, then aggregates
        ``sensor_data`` to avoid accidental cross-products.

        Args:
            zone_id: Zone identifier string.
            phi2_sensor_type: ``sensor_type`` value to filter on (e.g. ``"phi2"``).
            cutoff: Only include readings at or after this timestamp.

        Returns:
            Average as ``float`` or ``None`` if no matching rows exist.
        """
        from ..models.subzone import SubzoneConfig

        plant_id_stmt = (
            select(Plant.plant_id)
            .join(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(
                and_(
                    SubzoneConfig.parent_zone_id == zone_id,
                    Plant.deleted_at.is_(None),
                )
            )
        )
        avg_stmt = select(func.avg(SensorData.processed_value)).where(
            and_(
                SensorData.plant_id.in_(plant_id_stmt),
                SensorData.sensor_type == phi2_sensor_type,
                SensorData.timestamp >= cutoff,
                SensorData.processed_value.isnot(None),
            )
        )
        result = await self.session.execute(avg_stmt)
        avg_value = result.scalar_one_or_none()
        return float(avg_value) if avg_value is not None else None

    async def soft_delete(
        self,
        plant_id: uuid.UUID,
        deleted_by: int,
    ) -> Optional[Plant]:
        """
        Soft-delete a plant by setting ``deleted_at`` and ``deleted_by``.

        Args:
            plant_id: Plant UUID.
            deleted_by: ``user_accounts.id`` of the deleting user.

        Returns:
            Updated ``Plant`` instance or ``None`` if not found.
        """
        plant = await self.get_by_plant_id(plant_id, include_deleted=False)
        if plant is None:
            return None

        plant.deleted_at = datetime.now(timezone.utc)
        plant.deleted_by = deleted_by

        await self.session.flush()
        await self.session.refresh(plant)
        return plant
