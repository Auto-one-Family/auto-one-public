"""
Sensor Type Auto-Registration Service.

Automatically registers sensor types from loaded libraries into the
sensor_type_defaults database table on server startup.

This ensures that every sensor library has a corresponding database entry
with appropriate default operating mode settings, even for dynamically
added libraries.

Phase: 2A - Sensor Operating Modes (Auto-Registration Extension)

Features:
- Scans all loaded sensor processors from LibraryLoader
- Creates missing entries in sensor_type_defaults table
- Uses RECOMMENDED_* class attributes from sensor libraries
- Idempotent: Safe to run on every server startup
- Non-blocking: Errors don't prevent server startup
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.sensor_type_defaults_repo import SensorTypeDefaultsRepository
from ..sensors.library_loader import get_library_loader

logger = get_logger(__name__)


class SensorTypeRegistrationService:
    """
    Service for automatic sensor type registration.

    Scans LibraryLoader for loaded sensor processors and ensures each one
    has a corresponding entry in the sensor_type_defaults table.

    Attributes from sensor processor classes (BaseSensorProcessor subclasses):
    - RECOMMENDED_MODE: str - Default operating mode (e.g., "continuous", "on_demand")
    - RECOMMENDED_TIMEOUT_SECONDS: int - Default timeout in seconds
    - RECOMMENDED_INTERVAL_SECONDS: int - Default measurement interval
    - SUPPORTS_ON_DEMAND: bool - Whether sensor supports manual triggering

    Usage:
        async with get_session() as session:
            service = SensorTypeRegistrationService(session)
            results = await service.register_all_libraries()
            print(f"Registered {results['newly_registered']} new sensor types")
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session
        self.repo = SensorTypeDefaultsRepository(session)

    async def register_all_libraries(self) -> Dict[str, Any]:
        """
        Scan and register all loaded sensor libraries.

        For each processor class found in LibraryLoader:
        1. Check if entry exists in sensor_type_defaults
        2. If not, create entry using class attributes
        3. Skip existing entries (no overwrite)

        Returns:
            Dict with registration statistics:
            {
                "scanned": int,           # Total processors found
                "already_registered": int, # Already in database
                "newly_registered": int,   # Newly created entries
                "failed": int,            # Registration failures
                "details": dict           # Per-sensor-type results
            }
        """
        results = {
            "scanned": 0,
            "already_registered": 0,
            "newly_registered": 0,
            "failed": 0,
            "details": {},
        }

        # Get LibraryLoader instance
        try:
            loader = get_library_loader()
        except Exception as e:
            logger.error(f"Failed to get LibraryLoader: {e}")
            return results

        # Get all processor classes
        processor_classes = loader.get_all_processor_classes()

        if not processor_classes:
            logger.warning("No sensor processors found in LibraryLoader")
            return results

        logger.info(f"Scanning {len(processor_classes)} sensor processors for auto-registration")

        # Process each sensor type
        for sensor_type, processor_class in processor_classes.items():
            results["scanned"] += 1

            try:
                result = await self._register_single_library(sensor_type, processor_class)
                results["details"][sensor_type] = result

                if result["status"] == "already_registered":
                    results["already_registered"] += 1
                elif result["status"] == "newly_registered":
                    results["newly_registered"] += 1
                elif result["status"] == "failed":
                    results["failed"] += 1

            except Exception as e:
                results["failed"] += 1
                results["details"][sensor_type] = {
                    "status": "failed",
                    "error": str(e),
                }
                logger.error(
                    f"Failed to register sensor type '{sensor_type}': {e}",
                    exc_info=True,
                )

        # Commit all changes at once
        await self.session.commit()

        # Log summary
        logger.info(
            f"Sensor type auto-registration complete: "
            f"{results['newly_registered']} new, "
            f"{results['already_registered']} existing, "
            f"{results['failed']} failed "
            f"(out of {results['scanned']} total)"
        )

        return results

    async def _register_single_library(
        self,
        sensor_type: str,
        processor_class: type,
    ) -> Dict[str, Any]:
        """
        Register a single sensor type from its processor class.

        Args:
            sensor_type: Sensor type identifier (e.g., "ph", "temperature")
            processor_class: The processor class (BaseSensorProcessor subclass)

        Returns:
            Dict with registration result:
            {
                "status": str,  # "already_registered", "newly_registered", or "failed"
                "mode": str,    # Operating mode (if registered)
                "error": str,   # Error message (if failed)
            }
        """
        # Check if already exists
        existing = await self.repo.get_by_sensor_type(sensor_type)

        if existing:
            logger.debug(
                f"Sensor type '{sensor_type}' already registered "
                f"(mode={existing.operating_mode})"
            )
            return {
                "status": "already_registered",
                "mode": existing.operating_mode,
            }

        # Extract attributes from processor class with defaults
        mode = getattr(processor_class, "RECOMMENDED_MODE", "continuous")
        timeout = getattr(processor_class, "RECOMMENDED_TIMEOUT_SECONDS", 180)
        interval = getattr(processor_class, "RECOMMENDED_INTERVAL_SECONDS", 30)
        supports_on_demand = getattr(processor_class, "SUPPORTS_ON_DEMAND", False)
        freshness_hours = getattr(processor_class, "RECOMMENDED_FRESHNESS_HOURS", None)
        calibration_days = getattr(processor_class, "RECOMMENDED_CALIBRATION_INTERVAL_DAYS", None)

        # Derive timeout_warning_enabled from timeout value
        # If timeout > 0, warnings should be enabled
        timeout_warning_enabled = timeout > 0

        # Generate description from class name
        class_name = processor_class.__name__
        description = f"Auto-registered from {class_name}"

        # Create new entry
        try:
            await self.repo.create(
                sensor_type=sensor_type,
                operating_mode=mode,
                measurement_interval_seconds=interval,
                timeout_seconds=timeout,
                timeout_warning_enabled=timeout_warning_enabled,
                supports_on_demand=supports_on_demand,
                description=description,
                measurement_freshness_hours=freshness_hours,
                calibration_interval_days=calibration_days,
            )

            logger.info(
                f"Auto-registered sensor type '{sensor_type}': "
                f"mode={mode}, timeout={timeout}s, interval={interval}s, "
                f"on_demand={supports_on_demand}, "
                f"freshness={freshness_hours}h, calibration={calibration_days}d"
            )

            return {
                "status": "newly_registered",
                "mode": mode,
                "timeout": timeout,
                "interval": interval,
                "supports_on_demand": supports_on_demand,
                "freshness_hours": freshness_hours,
                "calibration_days": calibration_days,
            }

        except Exception as e:
            logger.error(f"Failed to create defaults for '{sensor_type}': {e}")
            return {
                "status": "failed",
                "error": str(e),
            }


async def auto_register_sensor_types(session: AsyncSession) -> Dict[str, Any]:
    """
    Convenience function for automatic sensor type registration.

    Use this in server startup to ensure all loaded sensor libraries
    have corresponding database entries.

    This function is idempotent - it can be called on every startup
    without creating duplicate entries.

    Args:
        session: Async SQLAlchemy session

    Returns:
        Dict with registration statistics

    Example:
        # In main.py startup:
        async for session in get_session():
            results = await auto_register_sensor_types(session)
            logger.info(f"Registered {results['newly_registered']} sensor types")
            break
    """
    service = SensorTypeRegistrationService(session)
    return await service.register_all_libraries()
