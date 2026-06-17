"""
MQTT Handler: ESP32 System Diagnostics

Processes diagnostics snapshots from ESP32 devices:
- Parses system/diagnostics topics
- Validates HealthSnapshot payloads
- Logs diagnostics metrics to database
- Broadcasts via WebSocket for real-time dashboard

The ESP32 HealthMonitor publishes diagnostics every 60s with:
heap_free, heap_min_free, heap_fragmentation, uptime, error_count,
wifi_rssi, sensor_count, actuator_count, system_state,
boot_reason, mqtt_cb_state, mqtt_cb_failures, wdt_mode,
wdt_timeouts_24h, wdt_timeout_pending.

Architecture:
- ESP32 publishes to kaiser/{kaiser_id}/esp/{esp_id}/system/diagnostics
- Server receives, validates, stores, and forwards to Frontend
- QoS 0 (best-effort, non-critical telemetry)

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm.attributes import flag_modified

from ...core.error_codes import (
    ConfigErrorCode,
    ValidationErrorCode,
)
from ...core.logging_config import get_logger
from ...core.metrics import increment_contract_unknown_code
from ...db.repositories import ESPRepository
from ...db.session import resilient_session
from ...services.event_contract_serializers import serialize_diagnostics_event
from ...services.system_event_contract import canonicalize_diagnostics
from ..topics import TopicBuilder

logger = get_logger(__name__)


class DiagnosticsHandler:
    """
    Handles incoming system diagnostics messages from ESP32 devices.

    Flow:
    1. Parse topic -> extract esp_id
    2. Validate payload structure
    3. Lookup ESP device
    4. Update device diagnostics metadata
    5. Broadcast via WebSocket
    """

    async def handle_diagnostics(self, topic: str, payload: dict) -> bool:
        """
        Handle diagnostics snapshot message.

        Expected topic: kaiser/god/esp/{esp_id}/system/diagnostics

        Expected payload (from ESP32 HealthMonitor):
        {
            "ts": 1735818000,
            "esp_id": "ESP_12AB34CD",
            "heap_free": 150000,
            "heap_min_free": 120000,
            "heap_fragmentation": 15,
            "uptime_seconds": 3600,
            "error_count": 3,
            "wifi_connected": true,
            "wifi_rssi": -65,
            "mqtt_connected": true,
            "sensor_count": 4,
            "actuator_count": 2,
            "system_state": "OPERATIONAL"
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            payload = dict(payload)
            canonical = canonicalize_diagnostics(payload)
            payload = canonical.payload
            if canonical.is_contract_violation:
                increment_contract_unknown_code("diagnostics")
                logger.warning(
                    "Diagnostics contract violation normalized: %s (raw=%s)",
                    canonical.contract_reason,
                    canonical.raw_fields,
                )

            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_system_diagnostics_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse diagnostics topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]

            logger.debug(f"Processing diagnostics: esp_id={esp_id_str}")

            # Step 2: Validate payload
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid diagnostics payload from {esp_id_str}: "
                    f"{validation_result['error']}"
                )
                return False

            # Step 3: Get database session and update device
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)

                # Step 4: Lookup ESP device
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if not esp_device:
                    logger.warning(
                        f"[{ConfigErrorCode.ESP_DEVICE_NOT_FOUND}] "
                        f"Diagnostics from unknown ESP: {esp_id_str}"
                    )
                    return False

                # Step 5: Update device diagnostics metadata
                current_metadata = esp_device.device_metadata or {}
                current_metadata["diagnostics"] = {
                    "heap_free": payload.get("heap_free"),
                    "heap_min_free": payload.get("heap_min_free"),
                    "heap_fragmentation": payload.get("heap_fragmentation"),
                    "uptime_seconds": payload.get("uptime_seconds"),
                    "error_count": payload.get("error_count", 0),
                    "wifi_connected": payload.get("wifi_connected"),
                    "wifi_rssi": payload.get("wifi_rssi"),
                    "mqtt_connected": payload.get("mqtt_connected"),
                    "sensor_count": payload.get("sensor_count"),
                    "actuator_count": payload.get("actuator_count"),
                    "system_state": payload.get("system_state"),
                    "boot_reason": payload.get("boot_reason"),
                    "mqtt_cb_state": payload.get("mqtt_cb_state"),
                    "mqtt_cb_failures": payload.get("mqtt_cb_failures"),
                    "wdt_mode": payload.get("wdt_mode"),
                    "wdt_timeouts_24h": payload.get("wdt_timeouts_24h"),
                    "wdt_timeout_pending": payload.get("wdt_timeout_pending"),
                    "boot_sequence_id": payload.get("boot_sequence_id"),
                    "reset_reason": payload.get("reset_reason"),
                    "segment_start_ts": payload.get("segment_start_ts"),
                    "metrics_schema_version": payload.get("metrics_schema_version"),
                    "contract_violation": canonical.is_contract_violation,
                    "contract_code": canonical.contract_code,
                    "contract_reason": canonical.contract_reason,
                    "raw_system_state": canonical.raw_fields.get("raw_system_state"),
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
                esp_device.device_metadata = current_metadata
                flag_modified(esp_device, "device_metadata")

                await session.commit()

                logger.debug(
                    f"Diagnostics processed: esp_id={esp_id_str}, "
                    f"heap_free={payload.get('heap_free')}B, "
                    f"rssi={payload.get('wifi_rssi')}dBm, "
                    f"state={payload.get('system_state')}"
                )

                # Step 6: WebSocket Broadcast
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()
                    broadcast_payload = serialize_diagnostics_event(
                        esp_id=esp_id_str,
                        payload=payload,
                    )
                    broadcast_payload.update(
                        {
                            "contract_violation": canonical.is_contract_violation,
                            "contract_code": canonical.contract_code,
                            "contract_reason": canonical.contract_reason,
                            "raw_system_state": canonical.raw_fields.get("raw_system_state"),
                        }
                    )
                    await ws_manager.broadcast("esp_diagnostics", broadcast_payload)
                except Exception as e:
                    logger.warning(f"Failed to broadcast diagnostics via WebSocket: {e}")

                return True

        except Exception as e:
            logger.error(
                f"Error handling diagnostics: {e}",
                exc_info=True,
            )
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate diagnostics payload structure.

        Required fields: heap_free, wifi_rssi
        Optional fields: all others (graceful degradation)

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str, "error_code": int}
        """
        if "heap_free" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: heap_free",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "wifi_rssi" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: wifi_rssi",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Type validation
        if not isinstance(payload["heap_free"], int):
            return {
                "valid": False,
                "error": "Field 'heap_free' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if not isinstance(payload["wifi_rssi"], int):
            return {
                "valid": False,
                "error": "Field 'wifi_rssi' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Contract upgrade path:
        # - metrics_schema_version missing/1 => segment fields optional (backward compatible)
        # - metrics_schema_version >=2 => segment fields mandatory (fail-closed)
        metrics_schema_version = payload.get("metrics_schema_version")
        if metrics_schema_version is not None and not isinstance(metrics_schema_version, int):
            return {
                "valid": False,
                "error": "Field 'metrics_schema_version' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if isinstance(metrics_schema_version, int) and metrics_schema_version >= 2:
            required_segment_fields = ("boot_sequence_id", "reset_reason", "segment_start_ts")
            for field in required_segment_fields:
                if field not in payload:
                    return {
                        "valid": False,
                        "error": f"Missing required field for schema>=2: {field}",
                        "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    }

            if not isinstance(payload.get("boot_sequence_id"), str):
                return {
                    "valid": False,
                    "error": "Field 'boot_sequence_id' must be string for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            if not isinstance(payload.get("reset_reason"), str):
                return {
                    "valid": False,
                    "error": "Field 'reset_reason' must be string for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            if not isinstance(payload.get("segment_start_ts"), int):
                return {
                    "valid": False,
                    "error": "Field 'segment_start_ts' must be integer for schema>=2",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

        return {"valid": True, "error": "", "error_code": ValidationErrorCode.NONE}


# Global handler instance (follows sensor_handler pattern)
_handler_instance: Optional[DiagnosticsHandler] = None


def get_diagnostics_handler() -> DiagnosticsHandler:
    """
    Get singleton diagnostics handler instance.

    Returns:
        DiagnosticsHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = DiagnosticsHandler()
    return _handler_instance


async def handle_diagnostics(topic: str, payload: dict) -> bool:
    """
    Handle diagnostics message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_diagnostics_handler()
    return await handler.handle_diagnostics(topic, payload)
