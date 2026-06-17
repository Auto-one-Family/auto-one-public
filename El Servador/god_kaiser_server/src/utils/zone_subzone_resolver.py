"""
Zone/Subzone Resolver for Sensor Data (Phase 0.1)

Updated: T13-R2 — Multi-Zone Device Scope (3-Way Resolution)

Resolves zone_id and subzone_id for a sensor at measurement time.
Used by sensor_handler and Logic Engine for Subzone-Matching.

T13-R1: I2C sensors with gpio=0 are resolved via sensor_config_id
instead of GPIO matching (gpio=0 is a placeholder, not a real pin).

T13-R2: 3-way resolution based on device_scope:
  - zone_local: Zone from ESP device (existing behavior)
  - multi_zone: Zone from active context (or NULL for static)
  - mobile: Zone from active context (fallback to ESP zone)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..db.models.sensor import SensorConfig
    from ..db.repositories.esp_repo import ESPRepository
    from ..db.repositories.subzone_repo import SubzoneRepository
    from ..services.device_scope_service import DeviceScopeService

logger = logging.getLogger(__name__)

# I2C sensor types that use gpio=0 as placeholder
I2C_SENSOR_TYPES = frozenset(
    {
        "sht31_temp",
        "sht31_humidity",
        "bmp280_temp",
        "bmp280_pressure",
        "bme280_temp",
        "bme280_humidity",
        "bme280_pressure",
    }
)


async def resolve_zone_subzone_for_sensor(
    esp_id_str: str,
    gpio: int,
    esp_repo: "ESPRepository",
    subzone_repo: "SubzoneRepository",
    sensor_config_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
    sensor_config: Optional["SensorConfig"] = None,
    scope_service: Optional["DeviceScopeService"] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve zone_id and subzone_id for a sensor at measurement time.

    T13-R2: 3-way resolution based on device_scope attribute on sensor_config.

    Args:
        esp_id_str: device_id of the ESP (e.g. "ESP_12AB34CD"), NOT UUID
        gpio: GPIO pin number (0 = I2C placeholder)
        esp_repo: ESPRepository instance (with session)
        subzone_repo: SubzoneRepository instance (with session)
        sensor_config_id: UUID string of sensor_config (for I2C resolution)
        sensor_type: Sensor type string (for I2C detection)
        sensor_config: SensorConfig model instance (T13-R2, for device_scope)
        scope_service: DeviceScopeService (T13-R2, cached active context lookups)

    Returns:
        (zone_id, subzone_id) — both can be None
    """
    scope = getattr(sensor_config, "device_scope", "zone_local") if sensor_config else "zone_local"

    if scope == "zone_local":
        return await _resolve_zone_local(
            esp_id_str,
            gpio,
            esp_repo,
            subzone_repo,
            sensor_config_id,
            sensor_type,
        )

    elif scope == "multi_zone":
        return await _resolve_multi_zone(
            esp_id_str,
            gpio,
            esp_repo,
            subzone_repo,
            sensor_config,
            scope_service,
            sensor_config_id,
            sensor_type,
        )

    elif scope == "mobile":
        return await _resolve_mobile(
            esp_id_str,
            gpio,
            esp_repo,
            subzone_repo,
            sensor_config,
            scope_service,
            sensor_config_id,
            sensor_type,
        )

    # Unknown scope — fallback to zone_local
    logger.warning("Unknown device_scope '%s' — falling back to zone_local", scope)
    return await _resolve_zone_local(
        esp_id_str,
        gpio,
        esp_repo,
        subzone_repo,
        sensor_config_id,
        sensor_type,
    )


async def _resolve_zone_local(
    esp_id_str: str,
    gpio: int,
    esp_repo: "ESPRepository",
    subzone_repo: "SubzoneRepository",
    sensor_config_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Original zone_local resolution: zone from ESP device, subzone from GPIO/config."""
    zone_id: Optional[str] = None
    subzone_id: Optional[str] = None

    esp_device = await esp_repo.get_by_device_id(esp_id_str)
    if esp_device:
        zone_id = esp_device.zone_id

    # subzone_id resolution
    try:
        is_i2c = gpio == 0 and (sensor_type in I2C_SENSOR_TYPES if sensor_type else True)

        if is_i2c and sensor_config_id:
            subzone_config = await subzone_repo.get_subzone_by_sensor_config_id(
                esp_id_str,
                sensor_config_id,
            )
            if subzone_config:
                subzone_id = subzone_config.subzone_id
        else:
            subzone_config = await subzone_repo.get_subzone_by_gpio(esp_id_str, gpio)
            if subzone_config:
                subzone_id = subzone_config.subzone_id
    except Exception:
        subzone_id = None

    return (zone_id, subzone_id)


async def _resolve_multi_zone(
    esp_id_str: str,
    gpio: int,
    esp_repo: "ESPRepository",
    subzone_repo: "SubzoneRepository",
    sensor_config: Optional["SensorConfig"],
    scope_service: Optional["DeviceScopeService"],
    sensor_config_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Multi-zone resolution: zone from active context (cached via DeviceScopeService).

    If active context has active_zone_id → use it.
    If no active context (static multi-zone) → zone_id = None (applies to all assigned zones).
    """
    if scope_service and sensor_config:
        try:
            context = await scope_service.get_active_context(
                config_type="sensor",
                config_id=sensor_config.id,
            )
            if context and context.active_zone_id:
                return context.active_zone_id, context.active_subzone_id
        except Exception:
            logger.warning(
                "Failed to get active context for multi_zone sensor %s",
                sensor_config.id,
                exc_info=True,
            )

    # Static multi-zone: zone_id = None (measurement applies to all assigned zones)
    return None, None


async def _resolve_mobile(
    esp_id_str: str,
    gpio: int,
    esp_repo: "ESPRepository",
    subzone_repo: "SubzoneRepository",
    sensor_config: Optional["SensorConfig"],
    scope_service: Optional["DeviceScopeService"],
    sensor_config_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Mobile resolution: zone from active context (cached), fallback to ESP zone.

    Mobile sensors should have their context set manually before measuring.
    If no context is set, fall back to the ESP's zone with a warning.
    """
    if scope_service and sensor_config:
        try:
            context = await scope_service.get_active_context(
                config_type="sensor",
                config_id=sensor_config.id,
            )
            if context and context.active_zone_id:
                return context.active_zone_id, context.active_subzone_id
        except Exception:
            logger.warning(
                "Failed to get active context for mobile sensor %s",
                sensor_config.id,
                exc_info=True,
            )

    # Fallback: use ESP zone + warning
    logger.warning(
        "Mobile sensor %s (esp=%s, gpio=%d) has no active_context — fallback to ESP zone",
        sensor_config.id if sensor_config else "unknown",
        esp_id_str,
        gpio,
    )
    return await _resolve_zone_local(
        esp_id_str,
        gpio,
        esp_repo,
        subzone_repo,
        sensor_config_id,
        sensor_type,
    )
