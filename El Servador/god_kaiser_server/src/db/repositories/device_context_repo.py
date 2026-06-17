"""
Device Active Context Repository

T13-R2: CRUD operations for device_active_context table.
Manages runtime zone context for multi-zone and mobile devices.
"""

import uuid
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.device_context import DeviceActiveContext
from .base_repo import BaseRepository


class DeviceActiveContextRepository(BaseRepository[DeviceActiveContext]):
    """Repository for DeviceActiveContext CRUD operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(DeviceActiveContext, session)

    async def get_active_context(
        self, config_type: str, config_id: uuid.UUID
    ) -> Optional[DeviceActiveContext]:
        """
        Get the active context for a sensor or actuator config.

        Args:
            config_type: 'sensor' or 'actuator'
            config_id: UUID of the sensor_config or actuator_config

        Returns:
            DeviceActiveContext or None
        """
        stmt = select(self.model).where(
            and_(
                self.model.config_type == config_type,
                self.model.config_id == config_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_context(
        self,
        config_type: str,
        config_id: uuid.UUID,
        active_zone_id: Optional[str],
        active_subzone_id: Optional[str] = None,
        context_source: str = "manual",
    ) -> DeviceActiveContext:
        """
        Create or update the active context (upsert).

        Uses UNIQUE(config_type, config_id) constraint.
        """
        existing = await self.get_active_context(config_type, config_id)
        if existing:
            existing.active_zone_id = active_zone_id
            existing.active_subzone_id = active_subzone_id
            existing.context_source = context_source
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        return await self.create(
            config_type=config_type,
            config_id=config_id,
            active_zone_id=active_zone_id,
            active_subzone_id=active_subzone_id,
            context_source=context_source,
        )

    async def delete_context(self, config_type: str, config_id: uuid.UUID) -> bool:
        """
        Delete the active context for a sensor or actuator.

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(self.model).where(
            and_(
                self.model.config_type == config_type,
                self.model.config_id == config_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_all_for_config_type(self, config_type: str) -> list[DeviceActiveContext]:
        """Get all active contexts for a config type ('sensor' or 'actuator')."""
        stmt = select(self.model).where(self.model.config_type == config_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
