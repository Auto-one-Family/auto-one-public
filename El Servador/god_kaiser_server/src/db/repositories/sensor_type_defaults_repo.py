"""
Repository for SensorTypeDefaults CRUD operations.

Provides database access methods for sensor type default configurations.

Phase: 2A - Sensor Operating Modes
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.sensor_type_defaults import SensorTypeDefaults
from ...core.logging_config import get_logger

logger = get_logger(__name__)


class SensorTypeDefaultsRepository:
    """
    Repository for SensorTypeDefaults database operations.

    Provides CRUD operations for sensor type default configurations.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    # =========================================================================
    # CREATE
    # =========================================================================

    async def create(
        self,
        sensor_type: str,
        operating_mode: str = "continuous",
        measurement_interval_seconds: int = 30,
        timeout_seconds: int = 180,
        timeout_warning_enabled: bool = True,
        supports_on_demand: bool = False,
        description: Optional[str] = None,
        schedule_config: Optional[dict] = None,
        measurement_freshness_hours: Optional[int] = None,
        calibration_interval_days: Optional[int] = None,
    ) -> SensorTypeDefaults:
        """
        Create a new sensor type default configuration.

        Args:
            sensor_type: Unique sensor type identifier
            operating_mode: Default operating mode
            measurement_interval_seconds: Default measurement interval
            timeout_seconds: Default timeout (0 = no timeout)
            timeout_warning_enabled: Whether to show timeout warnings
            supports_on_demand: Whether sensor supports manual triggering
            description: User-facing description
            schedule_config: Default schedule configuration
            measurement_freshness_hours: Freshness limit in hours
            calibration_interval_days: Calibration interval in days

        Returns:
            Created SensorTypeDefaults instance

        Raises:
            IntegrityError: If sensor_type already exists
        """
        defaults = SensorTypeDefaults(
            sensor_type=sensor_type,
            operating_mode=operating_mode,
            measurement_interval_seconds=measurement_interval_seconds,
            timeout_seconds=timeout_seconds,
            timeout_warning_enabled=timeout_warning_enabled,
            supports_on_demand=supports_on_demand,
            description=description,
            schedule_config=schedule_config,
            measurement_freshness_hours=measurement_freshness_hours,
            calibration_interval_days=calibration_interval_days,
        )

        self.session.add(defaults)
        await self.session.flush()
        await self.session.refresh(defaults)

        logger.info(f"Created sensor type defaults: {sensor_type} (mode={operating_mode})")
        return defaults

    # =========================================================================
    # READ
    # =========================================================================

    async def get_by_id(self, defaults_id: UUID) -> Optional[SensorTypeDefaults]:
        """
        Get sensor type defaults by ID.

        Args:
            defaults_id: UUID of the defaults entry

        Returns:
            SensorTypeDefaults or None if not found
        """
        result = await self.session.execute(
            select(SensorTypeDefaults).where(SensorTypeDefaults.id == defaults_id)
        )
        return result.scalar_one_or_none()

    async def get_by_sensor_type(self, sensor_type: str) -> Optional[SensorTypeDefaults]:
        """
        Get defaults for a specific sensor type.

        Args:
            sensor_type: Sensor type identifier (e.g., "ph", "temperature")

        Returns:
            SensorTypeDefaults or None if not found
        """
        result = await self.session.execute(
            select(SensorTypeDefaults).where(SensorTypeDefaults.sensor_type == sensor_type.lower())
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[SensorTypeDefaults]:
        """
        Get all sensor type defaults.

        Returns:
            List of all SensorTypeDefaults entries
        """
        result = await self.session.execute(
            select(SensorTypeDefaults).order_by(SensorTypeDefaults.sensor_type)
        )
        return list(result.scalars().all())

    async def get_on_demand_types(self) -> list[SensorTypeDefaults]:
        """
        Get all sensor types configured for on_demand mode.

        Returns:
            List of SensorTypeDefaults with operating_mode='on_demand'
        """
        result = await self.session.execute(
            select(SensorTypeDefaults).where(SensorTypeDefaults.operating_mode == "on_demand")
        )
        return list(result.scalars().all())

    async def get_continuous_types(self) -> list[SensorTypeDefaults]:
        """
        Get all sensor types configured for continuous mode.

        Returns:
            List of SensorTypeDefaults with operating_mode='continuous'
        """
        result = await self.session.execute(
            select(SensorTypeDefaults).where(SensorTypeDefaults.operating_mode == "continuous")
        )
        return list(result.scalars().all())

    # =========================================================================
    # UPDATE
    # =========================================================================

    async def update(
        self,
        sensor_type: str,
        operating_mode: Optional[str] = None,
        measurement_interval_seconds: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        timeout_warning_enabled: Optional[bool] = None,
        supports_on_demand: Optional[bool] = None,
        description: Optional[str] = None,
        schedule_config: Optional[dict] = None,
        measurement_freshness_hours: Optional[int] = None,
        calibration_interval_days: Optional[int] = None,
    ) -> Optional[SensorTypeDefaults]:
        """
        Update sensor type defaults.

        Args:
            sensor_type: Sensor type to update
            **kwargs: Fields to update (None = don't change)

        Returns:
            Updated SensorTypeDefaults or None if not found
        """
        defaults = await self.get_by_sensor_type(sensor_type)
        if not defaults:
            return None

        if operating_mode is not None:
            defaults.operating_mode = operating_mode
        if measurement_interval_seconds is not None:
            defaults.measurement_interval_seconds = measurement_interval_seconds
        if timeout_seconds is not None:
            defaults.timeout_seconds = timeout_seconds
        if timeout_warning_enabled is not None:
            defaults.timeout_warning_enabled = timeout_warning_enabled
        if supports_on_demand is not None:
            defaults.supports_on_demand = supports_on_demand
        if description is not None:
            defaults.description = description
        if schedule_config is not None:
            defaults.schedule_config = schedule_config
        if measurement_freshness_hours is not None:
            defaults.measurement_freshness_hours = measurement_freshness_hours
        if calibration_interval_days is not None:
            defaults.calibration_interval_days = calibration_interval_days

        await self.session.flush()
        await self.session.refresh(defaults)

        logger.info(f"Updated sensor type defaults: {sensor_type}")
        return defaults

    # =========================================================================
    # DELETE
    # =========================================================================

    async def delete(self, sensor_type: str) -> bool:
        """
        Delete sensor type defaults.

        Args:
            sensor_type: Sensor type to delete

        Returns:
            True if deleted, False if not found
        """
        defaults = await self.get_by_sensor_type(sensor_type)
        if not defaults:
            return False

        await self.session.delete(defaults)
        await self.session.flush()

        logger.info(f"Deleted sensor type defaults: {sensor_type}")
        return True

    # =========================================================================
    # UTILITY
    # =========================================================================

    async def get_effective_config(
        self,
        sensor_type: str,
        instance_override: Optional[dict] = None,
    ) -> dict:
        """
        Get effective configuration with fallback chain.

        Priority: instance_override > type_defaults > system_defaults

        Args:
            sensor_type: Sensor type identifier
            instance_override: Override values from SensorConfig instance

        Returns:
            Dict with effective configuration values including 'source' field
        """
        # System defaults (lowest priority)
        effective = {
            "operating_mode": "continuous",
            "measurement_interval_seconds": 30,
            "timeout_seconds": 180,
            "timeout_warning_enabled": True,
            "supports_on_demand": False,
            "measurement_freshness_hours": None,
            "calibration_interval_days": None,
        }
        source = "system_default"

        # Type defaults (medium priority)
        type_defaults = await self.get_by_sensor_type(sensor_type)
        if type_defaults:
            effective["operating_mode"] = type_defaults.operating_mode
            effective["measurement_interval_seconds"] = type_defaults.measurement_interval_seconds
            effective["timeout_seconds"] = type_defaults.timeout_seconds
            effective["timeout_warning_enabled"] = type_defaults.timeout_warning_enabled
            effective["supports_on_demand"] = type_defaults.supports_on_demand
            if hasattr(type_defaults, "measurement_freshness_hours"):
                effective["measurement_freshness_hours"] = type_defaults.measurement_freshness_hours
            if hasattr(type_defaults, "calibration_interval_days"):
                effective["calibration_interval_days"] = type_defaults.calibration_interval_days
            source = "type_default"

        # Instance override (highest priority)
        if instance_override:
            for key in [
                "operating_mode",
                "timeout_seconds",
                "timeout_warning_enabled",
                "measurement_freshness_hours",
                "calibration_interval_days",
            ]:
                if instance_override.get(key) is not None:
                    effective[key] = instance_override[key]
                    source = "instance"

        effective["source"] = source
        return effective

    async def exists(self, sensor_type: str) -> bool:
        """
        Check if defaults exist for a sensor type.

        Args:
            sensor_type: Sensor type identifier

        Returns:
            True if defaults exist, False otherwise
        """
        defaults = await self.get_by_sensor_type(sensor_type)
        return defaults is not None
