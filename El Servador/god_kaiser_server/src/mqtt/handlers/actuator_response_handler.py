"""
MQTT Handler: Actuator Command Response Messages

Processes command response confirmations from ESP32 devices:
- Validates command execution success/failure
- Updates actuator command history
- Logs success/failure metrics
- Triggers WebSocket notifications

Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response
QoS: 1 (At Least Once)

Expected Payload:
{
    "esp_id": "ESP_12AB34CD",
    "zone_id": "zone_main",
    "ts": 1733000000,          // Unix timestamp (seconds)
    "gpio": 25,
    "command": "ON",
    "value": 1.0,
    "duration": 0,
    "success": true,
    "message": "Command executed"
}
"""

from datetime import datetime, timezone
import json
import time
from typing import Optional

from ...core.metrics import (
    increment_contract_terminalization_blocked,
    increment_contract_unknown_code,
)
from ...core.logging_config import get_logger
from ...db.repositories import ActuatorRepository, CommandContractRepository, ESPRepository
from ...db.session import resilient_session
from ...services.device_response_contract import canonicalize_actuator_response
from ...services.event_contract_serializers import serialize_actuator_response_event
from ..topics import TopicBuilder

logger = get_logger(__name__)

# Timestamp validation constants
MIN_VALID_TIMESTAMP = 1700000000  # ~2023-11-14
MAX_VALID_TIMESTAMP = 2500000000  # ~2049-03-22


def _agent_debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
) -> None:
    try:
        entry = {
            "sessionId": "eea42f",
            "id": f"log_{time.time_ns()}",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        line = json.dumps(entry, ensure_ascii=True) + "\n"
        for candidate_path in (
            "/home/robin/.cursor/debug-eea42f.log",
            "/app/logs/debug-eea42f.log",
        ):
            try:
                with open(candidate_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                break
            except Exception:
                continue
    except Exception:
        pass


class ActuatorResponseHandler:
    """
    Handles actuator command response messages from ESP32 devices.

    Flow:
    1. Parse topic → extract esp_id, gpio
    2. Validate payload structure
    3. Convert ESP32 timestamp to datetime
    4. Lookup ESP device
    5. Log command response to history
    6. Broadcast via WebSocket (optional)
    """

    async def handle_actuator_response(self, topic: str, payload: dict) -> bool:
        """
        Handle actuator command response message.

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_actuator_response_topic(topic)
            if not parsed_topic:
                logger.error("Failed to parse actuator response topic: %s", topic)
                return False

            # Step 2: Canonical-first normalization
            canonical = canonicalize_actuator_response(
                payload,
                topic_esp_id=parsed_topic["esp_id"],
                topic_gpio=parsed_topic["gpio"],
            )
            esp_id_str = canonical.esp_id
            gpio = canonical.gpio
            command = canonical.command
            value = canonical.value
            success = canonical.success
            message = canonical.message
            correlation_id = canonical.correlation_id
            t3_seen_ms = int(time.time() * 1000)
            issued_by_raw = payload.get("issued_by")
            issued_by = (
                issued_by_raw.strip()
                if isinstance(issued_by_raw, str) and issued_by_raw.strip()
                else None
            )

            if canonical.is_contract_violation:
                increment_contract_unknown_code("actuator_response")
                logger.warning(
                    "Contract violation normalized on actuator_response: esp_id=%s raw_esp_id=%s raw_gpio=%s raw_success=%s",
                    esp_id_str,
                    canonical.raw_esp_id,
                    canonical.raw_gpio,
                    canonical.raw_success,
                )

            logger.debug(
                f"Processing actuator response: esp_id={esp_id_str}, gpio={gpio}, "
                f"command={command}, success={success}"
            )
            is_off_response = str(command).upper() == "OFF"
            # #region agent log
            if is_off_response:
                _agent_debug_log(
                    run_id="off-latency-r1",
                    hypothesis_id="H3_HANDLER_DB_WS",
                    location="actuator_response_handler.py:handle:start",
                    message="OFF response entered actuator response handler",
                    data={
                        "topic": topic,
                        "esp_id": esp_id_str,
                        "gpio": gpio,
                        "correlation_id": correlation_id,
                        "payload_ts": canonical.ts,
                    },
                )
            # #endregion

            # Step 3: Convert ESP32 timestamp
            esp32_timestamp = self._convert_timestamp(canonical.ts)
            if correlation_id:
                logger.warning(
                    "latency_stage stage=t3_actuator_response_seen correlation_id=%s esp_id=%s gpio=%s observed_at_ms=%s payload_ts=%s",
                    correlation_id,
                    esp_id_str,
                    gpio,
                    t3_seen_ms,
                    canonical.ts,
                )

            # Step 4: Get database session and repositories
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                actuator_repo = ActuatorRepository(session)
                contract_repo = CommandContractRepository(session)

                authority_key = self._build_terminal_authority_key(
                    esp_id=esp_id_str,
                    gpio=gpio,
                    command=command,
                    correlation_id=correlation_id,
                    payload=payload,
                )
                _, was_stale = await contract_repo.upsert_terminal_event_authority(
                    event_class="actuator_response",
                    dedup_key=authority_key,
                    esp_id=esp_id_str,
                    outcome="success" if bool(success) else "failed",
                    correlation_id=correlation_id,
                    is_final=canonical.is_final,
                    code=canonical.code,
                    reason=canonical.message,
                    retryable=(canonical.retry_policy != "forbidden"),
                    generation=payload.get("generation"),
                    seq=payload.get("seq"),
                    payload_ts=canonical.ts,
                )
                if was_stale:
                    increment_contract_terminalization_blocked(
                        event_class="actuator_response",
                        reason="terminal_authority_guard",
                    )
                    logger.info(
                        "Skipping stale actuator_response due to terminal authority guard: esp_id=%s gpio=%s key=%s",
                        esp_id_str,
                        gpio,
                        authority_key,
                    )
                    return True

                # Step 5: Lookup ESP device
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if not esp_device:
                    logger.warning(
                        f"ESP device not found for response: {esp_id_str}. "
                        "Response will be logged without device reference."
                    )
                    # Don't fail - still log the response for debugging
                    return True

                # Step 6: Log command response to history
                await actuator_repo.log_command(
                    esp_id=esp_device.id,
                    gpio=gpio,
                    actuator_type=payload.get("actuator_type", "unknown"),
                    command_type=command,
                    value=value,
                    success=success,
                    issued_by="esp32_response",
                    error_message=None if success else message,
                    timestamp=esp32_timestamp,
                    metadata={
                        "duration": payload.get("duration", 0),
                        "response_message": message,
                        "zone_id": payload.get("zone_id", ""),
                        "correlation_id": correlation_id,
                        "issued_by": issued_by,
                        "code": canonical.code,
                        "domain": canonical.domain,
                        "severity": canonical.severity,
                        "terminality": canonical.terminality,
                        "retry_policy": canonical.retry_policy,
                        "is_final": canonical.is_final,
                        "contract_violation": canonical.is_contract_violation,
                        "raw_esp_id": canonical.raw_esp_id,
                        "raw_gpio": canonical.raw_gpio,
                        "raw_success": canonical.raw_success,
                    },
                )

                # Step 6b: Audit log with correlation_id for event linking
                if correlation_id:
                    from ...db.repositories.audit_log_repo import AuditLogRepository

                    audit_repo = AuditLogRepository(session)
                    await audit_repo.log_actuator_command(
                        esp_id=esp_id_str,
                        gpio=gpio,
                        command=command,
                        value=value,
                        issued_by="esp32_response",
                        success=success,
                        error_message=None if success else message,
                        correlation_id=correlation_id,
                    )

                # Commit transaction
                await session.commit()
                # #region agent log
                if is_off_response:
                    _agent_debug_log(
                        run_id="off-latency-r1",
                        hypothesis_id="H3_HANDLER_DB_WS",
                        location="actuator_response_handler.py:handle:post_commit",
                        message="OFF response DB transaction committed",
                        data={
                            "esp_id": esp_id_str,
                            "gpio": gpio,
                            "correlation_id": correlation_id,
                        },
                    )
                # #endregion

                # Step 7: Log result
                if success:
                    logger.info(
                        f"✅ Actuator command confirmed: esp_id={esp_id_str}, gpio={gpio}, "
                        f"command={command}, value={value}"
                    )
                else:
                    logger.warning(
                        f"❌ Actuator command failed: esp_id={esp_id_str}, gpio={gpio}, "
                        f"command={command}, error={message}"
                    )

                # Step 8: WebSocket broadcast (non-blocking)
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()
                    broadcast_data = serialize_actuator_response_event(
                        esp_id=esp_id_str,
                        gpio=gpio,
                        command=command,
                        value=value,
                        success=success,
                        message=message,
                        timestamp=canonical.ts,
                        correlation_id=correlation_id,
                        issued_by=issued_by,
                    )
                    broadcast_data.update(
                        {
                            "code": canonical.code,
                            "domain": canonical.domain,
                            "severity": canonical.severity,
                            "terminality": canonical.terminality,
                            "retry_policy": canonical.retry_policy,
                            "is_final": canonical.is_final,
                            "contract_violation": canonical.is_contract_violation,
                            "raw_esp_id": canonical.raw_esp_id,
                            "raw_gpio": canonical.raw_gpio,
                            "raw_success": canonical.raw_success,
                        }
                    )
                    await ws_manager.broadcast(
                        "actuator_response",
                        broadcast_data,
                        correlation_id=correlation_id,
                    )
                    # #region agent log
                    if is_off_response:
                        _agent_debug_log(
                            run_id="off-latency-r1",
                            hypothesis_id="H3_HANDLER_DB_WS",
                            location="actuator_response_handler.py:handle:post_ws_broadcast",
                            message="OFF response websocket broadcast sent",
                            data={
                                "esp_id": esp_id_str,
                                "gpio": gpio,
                                "correlation_id": correlation_id,
                            },
                        )
                    # #endregion
                except Exception as e:
                    logger.debug(f"WebSocket broadcast skipped: {e}")

                return True

        except Exception as e:
            logger.error(
                f"Error handling actuator response: {e}",
                exc_info=True,
            )
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate actuator response payload structure.

        Required fields: ts, esp_id, gpio, command, success

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str}
        """
        # Check required fields
        required_fields = ["ts", "esp_id", "gpio", "command", "success"]
        for field in required_fields:
            if field not in payload:
                return {"valid": False, "error": f"Missing required field: {field}"}

        # Type validation
        if not isinstance(payload["ts"], (int, float)):
            return {
                "valid": False,
                "error": "Field 'ts' must be numeric (Unix timestamp)",
            }

        if not isinstance(payload["gpio"], int):
            return {"valid": False, "error": "Field 'gpio' must be integer"}

        if not isinstance(payload["success"], bool):
            return {"valid": False, "error": "Field 'success' must be boolean"}

        return {"valid": True, "error": ""}

    def _convert_timestamp(self, ts_raw: int) -> datetime:
        """
        Convert ESP32 timestamp to datetime.

        Handles:
        - Unix seconds (10-digit): Use directly
        - Unix milliseconds (13-digit): Divide by 1000
        - Invalid/zero: Use server time

        Args:
            ts_raw: Raw timestamp value

        Returns:
            datetime object in UTC
        """
        if not ts_raw or ts_raw == 0:
            logger.debug("No timestamp provided, using server time")
            return datetime.now(timezone.utc)

        # Auto-detect milliseconds vs seconds
        if ts_raw > 1e12:  # Milliseconds (13+ digits)
            ts_seconds = ts_raw / 1000
        else:
            ts_seconds = ts_raw

        # Validate timestamp is reasonable
        if MIN_VALID_TIMESTAMP <= ts_seconds <= MAX_VALID_TIMESTAMP:
            return datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
        else:
            logger.warning(f"Invalid timestamp {ts_raw} (out of range), using server time")
            return datetime.now(timezone.utc)

    @staticmethod
    def _build_terminal_authority_key(
        *,
        esp_id: str,
        gpio: int,
        command: str,
        correlation_id: Optional[str],
        payload: dict,
    ) -> str:
        """Build stable dedup key for actuator_response terminal events."""
        if correlation_id:
            return f"corr:{str(correlation_id).strip().lower()}"
        ts_part = str(payload.get("ts", "na"))
        return (
            f"esp:{esp_id.strip().lower()}:gpio:{int(gpio)}:"
            f"cmd:{str(command).strip().lower()}:ts:{ts_part}"
        )


# Global handler instance
_handler_instance: Optional[ActuatorResponseHandler] = None


def get_actuator_response_handler() -> ActuatorResponseHandler:
    """
    Get singleton actuator response handler instance.

    Returns:
        ActuatorResponseHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ActuatorResponseHandler()
    return _handler_instance


async def handle_actuator_response(topic: str, payload: dict) -> bool:
    """
    Handle actuator response message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_actuator_response_handler()
    return await handler.handle_actuator_response(topic, payload)
