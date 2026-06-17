"""
WebSocket utility functions for consistent device ID handling.

CRITICAL ARCHITECTURE RULE:
All WebSocket broadcasts to Frontend MUST use device_id, NOT UUID!

Reason:
- Frontend stores ESPs indexed by device_id (e.g., "ESP_00000001")
- PostgreSQL stores esp_id as UUID (internal foreign key)
- Sending UUID in WebSocket messages causes Frontend lookup failures
- Result: Sensors/Actuators don't appear in UI despite being configured

This module provides helpers to ensure consistent ID handling across all
WebSocket broadcasts.
"""

from typing import TYPE_CHECKING, Dict, Optional
from uuid import UUID

from ..core.logging_config import get_logger

if TYPE_CHECKING:
    from ..db.repositories.esp_repo import ESPRepository

logger = get_logger(__name__)


async def get_device_id_for_broadcast(
    esp_uuid: UUID,
    esp_repo: "ESPRepository",
) -> Optional[str]:
    """
    Get device_id for WebSocket broadcast from ESP UUID.

    CRITICAL: All WebSocket messages to Frontend must use device_id!
    Frontend indexes ESPs by device_id (e.g., "ESP_00000001"), not by UUID.

    Args:
        esp_uuid: ESP UUID from database (Foreign Key in SensorConfig/ActuatorConfig)
        esp_repo: ESP repository instance (for database lookup)

    Returns:
        device_id string (e.g., "ESP_00000001") or None if not found

    Example:
        ```python
        device_id = await get_device_id_for_broadcast(sensor.esp_id, esp_repo)
        if device_id:
            await ws_manager.broadcast("sensor_data", {
                "esp_id": device_id,  # ✅ Correct!
                ...
            })
        ```

    Warning:
        Never use str(sensor.esp_id) directly in WebSocket broadcasts!
        That converts UUID to string (e.g., "8f67d252-8aaa-4a87-9577-fb18e7ad7979")
        which Frontend cannot match to any device.
    """
    try:
        esp_device = await esp_repo.get_by_id(esp_uuid)

        if not esp_device:
            logger.warning(
                f"[websocket_utils] ESP device not found for UUID {esp_uuid}. "
                f"WebSocket broadcast will be skipped."
            )
            return None

        return esp_device.device_id

    except Exception as e:
        logger.error(f"[websocket_utils] Error looking up device_id for UUID {esp_uuid}: {e}")
        return None


async def build_device_id_cache(
    esp_uuids: list[UUID],
    esp_repo: "ESPRepository",
) -> Dict[UUID, str]:
    """
    Build a cache of UUID -> device_id mappings for batch operations.

    Useful for maintenance jobs that need to broadcast multiple events
    (e.g., sensor_health check for many sensors).

    Args:
        esp_uuids: List of ESP UUIDs to lookup
        esp_repo: ESP repository instance

    Returns:
        Dict mapping UUID to device_id. Missing entries are not included.

    Example:
        ```python
        # Build cache once
        device_id_cache = await build_device_id_cache(
            [sensor.esp_id for sensor in sensors],
            esp_repo
        )

        # Use cache for each broadcast
        for sensor in sensors:
            device_id = device_id_cache.get(sensor.esp_id)
            if device_id:
                await ws_manager.broadcast("sensor_health", {
                    "esp_id": device_id,  # ✅ Correct!
                    ...
                })
        ```
    """
    cache: Dict[UUID, str] = {}

    # Deduplicate UUIDs
    unique_uuids = list(set(esp_uuids))

    if not unique_uuids:
        return cache

    try:
        # Batch query all ESPs at once
        for esp_uuid in unique_uuids:
            esp_device = await esp_repo.get_by_id(esp_uuid)
            if esp_device:
                cache[esp_uuid] = esp_device.device_id

        logger.debug(
            f"[websocket_utils] Built device_id cache: "
            f"{len(cache)}/{len(unique_uuids)} UUIDs resolved"
        )

    except Exception as e:
        logger.error(f"[websocket_utils] Error building device_id cache: {e}")

    return cache
