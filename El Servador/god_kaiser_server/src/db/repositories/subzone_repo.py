"""
Subzone Repository: Database Operations for Subzone Configurations

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Provides CRUD operations and specialized queries for SubzoneConfig model.
Follows the same patterns as ESPRepository for consistency.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.subzone import SubzoneConfig
from .base_repo import BaseRepository


class SubzoneRepository(BaseRepository[SubzoneConfig]):
    """
    Subzone Repository with subzone-specific queries.

    Extends BaseRepository with Subzone-specific operations like
    ESP lookups, GPIO conflict detection, and safe-mode management.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(SubzoneConfig, session)

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_by_esp_and_subzone(self, esp_id: str, subzone_id: str) -> Optional[SubzoneConfig]:
        """
        Get subzone by ESP device ID and subzone ID.

        Args:
            esp_id: ESP device ID (e.g., ESP_AB12CD)
            subzone_id: Subzone identifier

        Returns:
            SubzoneConfig or None if not found
        """
        stmt = select(SubzoneConfig).where(
            and_(
                SubzoneConfig.esp_id == esp_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_esp(self, esp_id: str) -> List[SubzoneConfig]:
        """
        Get all subzones for an ESP device.

        Args:
            esp_id: ESP device ID

        Returns:
            List of SubzoneConfig instances
        """
        stmt = select(SubzoneConfig).where(SubzoneConfig.esp_id == esp_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_esp_and_zone(self, esp_id: str, zone_id: str) -> List[SubzoneConfig]:
        """
        Get all subzones for an ESP device in a specific zone.

        Used by ZoneService._handle_subzone_strategy() to only affect subzones
        belonging to the old zone during zone changes (not subzones from other zones).

        Args:
            esp_id: ESP device ID
            zone_id: Parent zone identifier

        Returns:
            List of SubzoneConfig instances
        """
        stmt = select(SubzoneConfig).where(
            and_(
                SubzoneConfig.esp_id == esp_id,
                SubzoneConfig.parent_zone_id == zone_id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_zone(self, zone_id: str) -> List[SubzoneConfig]:
        """
        Get all subzones in a parent zone.

        Args:
            zone_id: Parent zone identifier

        Returns:
            List of SubzoneConfig instances
        """
        stmt = select(SubzoneConfig).where(SubzoneConfig.parent_zone_id == zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_safe_mode_active(self) -> List[SubzoneConfig]:
        """
        Get all subzones with safe-mode active.

        Returns:
            List of SubzoneConfig instances in safe-mode
        """
        stmt = select(SubzoneConfig).where(SubzoneConfig.safe_mode_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # GPIO Conflict Detection
    # =========================================================================

    async def check_gpio_conflict(
        self, esp_id: str, gpios: List[int], exclude_subzone_id: Optional[str] = None
    ) -> Optional[SubzoneConfig]:
        """
        Check if any GPIO is already assigned to another subzone.

        Args:
            esp_id: ESP device ID
            gpios: List of GPIO pins to check
            exclude_subzone_id: Subzone ID to exclude (for updates)

        Returns:
            SubzoneConfig with conflict or None if no conflict
        """
        stmt = select(SubzoneConfig).where(SubzoneConfig.esp_id == esp_id)
        if exclude_subzone_id:
            stmt = stmt.where(SubzoneConfig.subzone_id != exclude_subzone_id)

        result = await self.session.execute(stmt)
        existing_subzones = result.scalars().all()

        for subzone in existing_subzones:
            if subzone.assigned_gpios:
                for gpio in gpios:
                    if gpio in subzone.assigned_gpios:
                        return subzone

        return None

    async def get_subzone_by_gpio(self, esp_id: str, gpio: int) -> Optional[SubzoneConfig]:
        """
        Find which subzone a GPIO belongs to.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number

        Returns:
            SubzoneConfig that owns this GPIO or None
        """
        subzones = await self.get_by_esp(esp_id)
        for subzone in subzones:
            if subzone.assigned_gpios and gpio in subzone.assigned_gpios:
                return subzone
        return None

    # =========================================================================
    # Create/Update Methods
    # =========================================================================

    async def create_subzone(
        self,
        esp_id: str,
        subzone_id: str,
        parent_zone_id: str,
        assigned_gpios: List[int],
        subzone_name: Optional[str] = None,
        safe_mode_active: bool = True,
    ) -> SubzoneConfig:
        """
        Create a new subzone configuration.

        Args:
            esp_id: ESP device ID
            subzone_id: Unique subzone identifier
            parent_zone_id: Parent zone ID
            assigned_gpios: List of GPIO pin numbers
            subzone_name: Human-readable name (optional)
            safe_mode_active: Whether subzone starts in safe-mode

        Returns:
            Created SubzoneConfig instance
        """
        return await self.create(
            esp_id=esp_id,
            subzone_id=subzone_id,
            subzone_name=subzone_name,
            parent_zone_id=parent_zone_id,
            assigned_gpios=assigned_gpios,
            safe_mode_active=safe_mode_active,
        )

    async def update_subzone(
        self,
        esp_id: str,
        subzone_id: str,
        **data,
    ) -> Optional[SubzoneConfig]:
        """
        Update subzone configuration.

        Args:
            esp_id: ESP device ID
            subzone_id: Subzone identifier
            **data: Fields to update

        Returns:
            Updated SubzoneConfig or None if not found
        """
        subzone = await self.get_by_esp_and_subzone(esp_id, subzone_id)
        if subzone is None:
            return None

        for key, value in data.items():
            if hasattr(subzone, key):
                setattr(subzone, key, value)

        await self.session.flush()
        await self.session.refresh(subzone)
        return subzone

    async def update_last_ack(self, esp_id: str, subzone_id: str) -> Optional[SubzoneConfig]:
        """
        Update last ACK timestamp for a subzone.

        Args:
            esp_id: ESP device ID
            subzone_id: Subzone identifier

        Returns:
            Updated SubzoneConfig or None if not found
        """
        return await self.update_subzone(esp_id, subzone_id, last_ack_at=datetime.now(timezone.utc))

    # =========================================================================
    # Safe-Mode Methods
    # =========================================================================

    async def enable_safe_mode(self, esp_id: str, subzone_id: str) -> Optional[SubzoneConfig]:
        """
        Enable safe-mode for a subzone.

        Args:
            esp_id: ESP device ID
            subzone_id: Subzone identifier

        Returns:
            Updated SubzoneConfig or None if not found
        """
        return await self.update_subzone(esp_id, subzone_id, safe_mode_active=True)

    async def disable_safe_mode(self, esp_id: str, subzone_id: str) -> Optional[SubzoneConfig]:
        """
        Disable safe-mode for a subzone.

        WARNING: This allows actuators to be controlled.

        Args:
            esp_id: ESP device ID
            subzone_id: Subzone identifier

        Returns:
            Updated SubzoneConfig or None if not found
        """
        return await self.update_subzone(esp_id, subzone_id, safe_mode_active=False)

    # =========================================================================
    # Delete Methods
    # =========================================================================

    async def delete_by_esp_and_subzone(self, esp_id: str, subzone_id: str) -> bool:
        """
        Delete a subzone by ESP and subzone ID.

        Args:
            esp_id: ESP device ID
            subzone_id: Subzone identifier

        Returns:
            True if deleted, False if not found
        """
        subzone = await self.get_by_esp_and_subzone(esp_id, subzone_id)
        if subzone is None:
            return False

        await self.session.delete(subzone)
        await self.session.flush()
        return True

    async def delete_all_by_esp(self, esp_id: str) -> int:
        """
        Delete all subzones for an ESP device.

        Args:
            esp_id: ESP device ID

        Returns:
            Number of subzones deleted
        """
        subzones = await self.get_by_esp(esp_id)
        count = len(subzones)

        for subzone in subzones:
            await self.session.delete(subzone)

        await self.session.flush()
        return count

    async def delete_all_by_zone(self, zone_id: str) -> int:
        """
        Delete all subzones for a zone.

        This is used during zone removal to cascade-delete subzones
        and maintain consistency with ESP32 behavior.

        Args:
            zone_id: Parent zone identifier

        Returns:
            Number of subzones deleted
        """
        subzones = await self.get_by_zone(zone_id)
        count = len(subzones)

        for subzone in subzones:
            await self.session.delete(subzone)

        await self.session.flush()
        return count

    # =========================================================================
    # Zone Transfer Methods (T13-R1)
    # =========================================================================

    async def update_parent_zone(
        self,
        esp_id: str,
        new_zone_id: str,
    ) -> List[SubzoneConfig]:
        """
        Transfer all subzones for an ESP to a new parent zone.

        Used by ZoneService.assign_zone() with strategy='transfer'.

        Args:
            esp_id: ESP device ID (String, e.g., 'ESP_12AB34CD')
            new_zone_id: New parent zone ID

        Returns:
            List of updated SubzoneConfig instances
        """
        subzones = await self.get_by_esp(esp_id)
        for subzone in subzones:
            subzone.parent_zone_id = new_zone_id
        await self.session.flush()
        return subzones

    async def deactivate_by_zone(self, zone_id: str) -> int:
        """
        Deactivate all subzones in a zone (used when archiving zone).

        Args:
            zone_id: Parent zone identifier

        Returns:
            Number of subzones deactivated
        """
        subzones = await self.get_by_zone(zone_id)
        count = 0
        for subzone in subzones:
            if subzone.is_active:
                subzone.is_active = False
                count += 1
        await self.session.flush()
        return count

    async def get_subzone_by_sensor_config_id(
        self,
        esp_id: str,
        sensor_config_id: str,
    ) -> Optional[SubzoneConfig]:
        """
        Find which subzone a sensor_config_id is assigned to (I2C sensors).

        Args:
            esp_id: ESP device ID
            sensor_config_id: UUID string of the sensor_config

        Returns:
            SubzoneConfig that contains this sensor_config_id or None
        """
        subzones = await self.get_by_esp(esp_id)
        for subzone in subzones:
            if (
                subzone.assigned_sensor_config_ids
                and sensor_config_id in subzone.assigned_sensor_config_ids
            ):
                return subzone
        return None

    # =========================================================================
    # Count Methods
    # =========================================================================

    async def count_by_esp(self, esp_id: str) -> int:
        """
        Count subzones for an ESP device.

        Args:
            esp_id: ESP device ID

        Returns:
            Number of subzones
        """
        subzones = await self.get_by_esp(esp_id)
        return len(subzones)

    async def count_gpios_by_esp(self, esp_id: str) -> int:
        """
        Count total GPIOs assigned across all subzones for an ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            Total number of assigned GPIOs
        """
        subzones = await self.get_by_esp(esp_id)
        total = 0
        for subzone in subzones:
            if subzone.assigned_gpios:
                total += len(subzone.assigned_gpios)
        return total

    async def sync_subzone_counts(
        self,
        device_id: str,
        esp_uuid: "uuid.UUID",
    ) -> int:
        """
        Sync sensor_count and actuator_count for all subzones of a device.

        JOIN path (FK-Typ-Mismatch workaround):
        subzone_configs.esp_id (String) -> esp_devices.device_id
        esp_devices.id (UUID) <- sensor_configs.esp_id (UUID)
        esp_devices.id (UUID) <- actuator_configs.esp_id (UUID)

        Args:
            device_id: ESP device_id string (e.g., 'ESP_12AB34CD')
            esp_uuid: UUID of the esp_device (esp_devices.id)

        Returns:
            Number of subzones updated
        """
        from ..models.actuator import ActuatorConfig
        from ..models.sensor import SensorConfig

        subzones = await self.get_by_esp(device_id)
        if not subzones:
            return 0

        # Load all sensor and actuator configs for this device (by UUID)
        sensor_stmt = select(SensorConfig).where(SensorConfig.esp_id == esp_uuid)
        sensor_result = await self.session.execute(sensor_stmt)
        all_sensors = list(sensor_result.scalars().all())

        actuator_stmt = select(ActuatorConfig).where(ActuatorConfig.esp_id == esp_uuid)
        actuator_result = await self.session.execute(actuator_stmt)
        all_actuators = list(actuator_result.scalars().all())

        updated = 0
        for subzone in subzones:
            gpios = set(subzone.assigned_gpios or [])
            config_ids = set(subzone.assigned_sensor_config_ids or [])

            # Count sensors: by GPIO match OR by sensor_config_id match
            s_count = sum(1 for s in all_sensors if s.gpio in gpios or str(s.id) in config_ids)
            # Count actuators: by GPIO match only
            a_count = sum(1 for a in all_actuators if a.gpio in gpios)

            if subzone.sensor_count != s_count or subzone.actuator_count != a_count:
                subzone.sensor_count = s_count
                subzone.actuator_count = a_count
                updated += 1

        if updated:
            await self.session.flush()

        return updated
