"""
MQTT Handler: Actuator Status Messages

Processes actuator status updates from ESP32 devices:
- Parses actuator status topics
- Validates payloads (with structured error codes)
- Updates actuator state in database
- Logs state changes to history

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
"""

from datetime import datetime, timezone
from typing import Optional

from ...core.error_codes import (
    ConfigErrorCode,
    ValidationErrorCode,
    get_error_code_description,
)
from ...core.logging_config import get_logger
from ...db.models.enums import DataSource
from ...db.repositories import ActuatorRepository, ESPRepository
from ...db.session import resilient_session
from ...services.state_adoption_service import get_state_adoption_service
from ...schemas.actuator import normalize_actuator_type
from ..topics import TopicBuilder

logger = get_logger(__name__)


class ActuatorStatusHandler:
    """
    Handles incoming actuator status messages from ESP32 devices.

    Flow:
    1. Parse topic → extract esp_id, gpio
    2. Validate payload structure
    3. Lookup ESP device and actuator config
    4. Update actuator state
    5. Log state change to history
    """

    async def handle_actuator_status(self, topic: str, payload: dict) -> bool:
        """
        Handle actuator status message.

        Expected topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/status

        Expected payload:
        {
            "ts": 1735818000,
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "on",               // or true/false (boolean) - both accepted
            "value": 255,                // or "pwm": 255 - both accepted
            "last_command": "on",
            "runtime_ms": 3600000,       // or "uptime": 3600
            "error": null
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_actuator_status_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse actuator status topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]
            gpio = parsed_topic["gpio"]

            logger.debug(
                f"Processing actuator status: esp_id={esp_id_str}, gpio={gpio}, "
                f"actuator_type={payload.get('actuator_type')}"
            )

            # Step 2: Validate payload
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid actuator status payload from {esp_id_str}: "
                    f"{validation_result['error']}"
                )
                return False

            # Step 3: Get database session and repositories
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                actuator_repo = ActuatorRepository(session)

                # Step 4: Lookup ESP device
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if not esp_device:
                    logger.error(
                        f"[{ConfigErrorCode.ESP_DEVICE_NOT_FOUND}] "
                        f"ESP device not found: {esp_id_str} - "
                        f"{get_error_code_description(ConfigErrorCode.ESP_DEVICE_NOT_FOUND)}"
                    )
                    return False

                # Step 5: Lookup actuator config
                actuator_config = await actuator_repo.get_by_esp_and_gpio(esp_device.id, gpio)
                if not actuator_config:
                    logger.warning(
                        f"Actuator config not found: esp_id={esp_id_str}, gpio={gpio}. "
                        "Updating state without config."
                    )

                # Step 6: Extract data from payload
                # Use server-normalized type from DB config as source of truth.
                # ESP32 sends its own logical type (relay/pump/valve) which differs from
                # the server's interface type (digital/pwm). Using the config avoids
                # storing raw ESP32 types in actuator_states/actuator_history.
                raw_esp32_type = payload.get("actuator_type", payload.get("type", None))
                if actuator_config:
                    actuator_type = (
                        actuator_config.actuator_type
                    )  # server-normalized (e.g. "digital")
                elif raw_esp32_type and raw_esp32_type != "unknown":
                    actuator_type = normalize_actuator_type(raw_esp32_type)
                else:
                    actuator_type = "unknown"

                # Update hardware_type on config if ESP32 reported a known logical type
                # that differs from what's stored (e.g. first status after Stufe-2 migration).
                if (
                    actuator_config
                    and raw_esp32_type
                    and raw_esp32_type not in ("unknown", None)
                    and actuator_config.hardware_type != raw_esp32_type
                ):
                    actuator_config.hardware_type = raw_esp32_type

                # Convert boolean state to string (ESP32 sends true/false)
                state = payload.get("state", "unknown")
                if isinstance(state, bool):
                    state = "on" if state else "off"

                # Accept both "value" and "pwm" for PWM value
                value = float(payload.get("value", payload.get("pwm", 0.0)))
                last_command = payload.get("last_command", payload.get("command", ""))
                error = payload.get("error", None)

                # Convert ESP32 timestamp (millis since boot) to UTC datetime
                # Same pattern as heartbeat_handler: auto-detect millis vs seconds
                esp32_timestamp_raw = payload.get("ts")
                esp32_timestamp = datetime.fromtimestamp(
                    (
                        esp32_timestamp_raw / 1000
                        if esp32_timestamp_raw > 1e10
                        else esp32_timestamp_raw
                    ),
                    tz=timezone.utc,
                )

                # Step 7: Detect data source (mock/test/production)
                data_source = self._detect_data_source(esp_device, payload)

                # Step 7a: Capture current state BEFORE update for state-change detection (Fix L1)
                prev_state_obj = await actuator_repo.get_state(esp_device.id, gpio)
                prev_state = prev_state_obj.state if prev_state_obj else None

                # Step 8: Update actuator state
                actuator_state = await actuator_repo.update_state(
                    esp_id=esp_device.id,
                    gpio=gpio,
                    actuator_type=actuator_type,
                    current_value=value,
                    state=state,
                    timestamp=esp32_timestamp,
                    last_command=last_command,
                    error_message=error,
                    data_source=data_source,
                )

                # During reconnect handover, actuator status events feed the adoption snapshot.
                adoption_service = get_state_adoption_service()
                await adoption_service.record_adopted_state(
                    esp_id=esp_id_str,
                    gpio=gpio,
                    state=state,
                    value=value,
                )

                # Step 9: Log to history if command was executed
                if last_command:
                    success = error is None
                    await actuator_repo.log_command(
                        esp_id=esp_device.id,
                        gpio=gpio,
                        actuator_type=actuator_type,
                        command_type=last_command,
                        value=value,
                        success=success,
                        issued_by="esp32",
                        error_message=error,
                        timestamp=esp32_timestamp,
                        metadata={
                            "uptime": payload.get("uptime"),
                        },
                        data_source=data_source,
                    )
                # Fix L1: State-change fallback — logs when state transitions without last_command
                elif prev_state is not None and prev_state != state:
                    command_type = state.upper()
                    await actuator_repo.log_command(
                        esp_id=esp_device.id,
                        gpio=gpio,
                        actuator_type=actuator_type,
                        command_type=command_type,
                        value=value,
                        success=True,
                        issued_by="state_sync",
                        error_message=None,
                        timestamp=esp32_timestamp,
                        metadata={
                            "trigger": "state_change_detected",
                            "prev_state": prev_state,
                            "source": "status_handler",
                        },
                        data_source=data_source,
                    )
                    logger.info(
                        "Actuator history logged",
                        extra={
                            "esp_id": esp_id_str,
                            "gpio": gpio,
                            "command_type": command_type,
                            "issued_by": "state_sync",
                            "trigger": "state_change_detected",
                        },
                    )

                # Commit transaction
                await session.commit()

                logger.info(
                    f"Actuator status updated: id={actuator_state.id}, "
                    f"esp_id={esp_id_str}, gpio={gpio}, state={state}, value={value}"
                )

                # Log error if present
                if error:
                    logger.error(
                        f"Actuator error reported: esp_id={esp_id_str}, "
                        f"gpio={gpio}, error={error}"
                    )

                # Extract correlation_id for end-to-end command tracking
                correlation_id = payload.get("correlation_id")

                # Audit log: actuator status with correlation
                if correlation_id:
                    from ...db.repositories.audit_log_repo import AuditLogRepository

                    audit_repo = AuditLogRepository(session)
                    await audit_repo.log_actuator_command(
                        esp_id=esp_id_str,
                        gpio=gpio,
                        command=last_command or state,
                        value=value,
                        issued_by="esp32_status",
                        success=error is None,
                        error_message=error,
                        correlation_id=correlation_id,
                    )
                    await session.commit()

                # WebSocket Broadcast
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()
                    hardware_type = (
                        actuator_config.hardware_type if actuator_config else raw_esp32_type
                    )
                    broadcast_data = {
                        "esp_id": esp_id_str,
                        "gpio": gpio,
                        "actuator_type": actuator_type,
                        "hardware_type": hardware_type,
                        # String "on"|"off"|"pwm"|… (frontend must not treat as boolean).
                        # value: ESP sendet typisch 8-Bit-PWM 0–255; 0–1 Duty nur bei normalisierten Pfaden.
                        "state": state,
                        "value": value,
                        "emergency": payload.get("emergency", "normal"),
                        "timestamp": esp32_timestamp_raw,
                    }
                    command_source = payload.get("command_source")
                    if isinstance(command_source, str) and command_source.strip():
                        broadcast_data["command_source"] = command_source.strip()
                    if correlation_id:
                        broadcast_data["correlation_id"] = correlation_id
                    await ws_manager.broadcast("actuator_status", broadcast_data)
                except Exception as e:
                    logger.warning(f"Failed to broadcast actuator status via WebSocket: {e}")

                return True

        except Exception as e:
            logger.error(
                f"Error handling actuator status: {e}",
                exc_info=True,
            )
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate actuator status payload structure.

        Required fields: ts, esp_id, gpio, actuator_type OR type, state, value OR pwm

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str, "error_code": int}
        """
        # Check required fields
        if "ts" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: ts",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "esp_id" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: esp_id",
                "error_code": ValidationErrorCode.INVALID_ESP_ID,
            }

        if "gpio" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: gpio",
                "error_code": ValidationErrorCode.INVALID_GPIO,
            }

        # Accept both "actuator_type" and "type"
        if "actuator_type" not in payload and "type" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: actuator_type or type",
                "error_code": ValidationErrorCode.INVALID_ACTUATOR_TYPE,
            }

        if "state" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: state",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Accept both "value" and "pwm"
        if "value" not in payload and "pwm" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: value or pwm",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Type validation
        if not isinstance(payload["ts"], int):
            return {
                "valid": False,
                "error": "Field 'ts' must be integer (Unix timestamp)",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if not isinstance(payload["gpio"], int):
            return {
                "valid": False,
                "error": "Field 'gpio' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate value (should be numeric)
        value = payload.get("value", payload.get("pwm"))
        try:
            float(value)
        except (ValueError, TypeError):
            return {
                "valid": False,
                "error": "Field 'value/pwm' must be numeric",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate state (accepts boolean true/false OR string on/off/pwm/error/unknown)
        state = payload["state"]
        if isinstance(state, bool):
            # Boolean is valid (will be converted to on/off in handler)
            pass
        elif isinstance(state, str):
            valid_states = ["on", "off", "pwm", "error", "unknown"]
            if state not in valid_states:
                return {
                    "valid": False,
                    "error": f"Field 'state' must be boolean or one of: {valid_states}",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }
        else:
            return {
                "valid": False,
                "error": "Field 'state' must be boolean or string",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        return {"valid": True, "error": "", "error_code": ValidationErrorCode.NONE}

    def _detect_data_source(self, esp_device, payload: dict) -> str:
        """
        Detect the data source based on device and payload.

        Detection priority:
        1. Explicit _test_mode flag in payload → TEST
        2. Explicit _source field in payload → use value
        3. Device hardware_type == "MOCK_ESP32" → MOCK
        4. Device capabilities.mock == True → MOCK
        5. ESP ID starts with "MOCK_" → MOCK
        6. ESP ID starts with "TEST_" → TEST
        7. ESP ID starts with "SIM_" → SIMULATION
        8. Default → PRODUCTION

        Args:
            esp_device: ESPDevice instance
            payload: MQTT payload dict

        Returns:
            Data source string value
        """
        esp_id = payload.get("esp_id", getattr(esp_device, "device_id", "unknown"))
        detection_reason = None

        # Priority 1: Explicit test mode flag
        if payload.get("_test_mode"):
            detection_reason = "payload._test_mode=True"
            result = DataSource.TEST.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Priority 2: Explicit source field
        if "_source" in payload:
            source_value = payload["_source"].lower()
            try:
                result = DataSource(source_value).value
                detection_reason = f"payload._source='{source_value}'"
                logger.debug(
                    f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})"
                )
                return result
            except ValueError:
                logger.warning(f"Unknown data source: {source_value}, defaulting to production")
                return DataSource.PRODUCTION.value

        # Priority 3: Device hardware_type
        if hasattr(esp_device, "hardware_type") and esp_device.hardware_type == "MOCK_ESP32":
            detection_reason = "esp_device.hardware_type='MOCK_ESP32'"
            result = DataSource.MOCK.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Priority 4: Device capabilities flag
        if hasattr(esp_device, "capabilities") and esp_device.capabilities:
            if esp_device.capabilities.get("mock"):
                detection_reason = "esp_device.capabilities.mock=True"
                result = DataSource.MOCK.value
                logger.debug(
                    f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})"
                )
                return result

        # Priority 5-7: ESP ID prefix detection
        if esp_id.startswith("MOCK_"):
            detection_reason = f"esp_id prefix 'MOCK_'"
            result = DataSource.MOCK.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result
        if esp_id.startswith("TEST_"):
            detection_reason = f"esp_id prefix 'TEST_'"
            result = DataSource.TEST.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result
        if esp_id.startswith("SIM_"):
            detection_reason = f"esp_id prefix 'SIM_'"
            result = DataSource.SIMULATION.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Default
        detection_reason = "default (no matching criteria)"
        result = DataSource.PRODUCTION.value
        logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
        return result


# Global handler instance
_handler_instance: Optional[ActuatorStatusHandler] = None


def get_actuator_handler() -> ActuatorStatusHandler:
    """
    Get singleton actuator status handler instance.

    Returns:
        ActuatorStatusHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ActuatorStatusHandler()
    return _handler_instance


async def handle_actuator_status(topic: str, payload: dict) -> bool:
    """
    Handle actuator status message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_actuator_handler()
    return await handler.handle_actuator_status(topic, payload)
