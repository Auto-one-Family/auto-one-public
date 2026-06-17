"""
MQTT Handler: ESP32 Configuration Response Messages

Logs configuration acknowledgements from ESP devices and stores in audit log.

Topic: kaiser/god/esp/{esp_id}/config_response
QoS: 2 (Exactly Once)

Note: ESP32 uses 'config_response' topic (not 'config/ack').
Server adapts to ESP32 protocol.

Error Codes (ESP32 → Server):
- NONE: Success
- JSON_PARSE_ERROR: Invalid JSON received
- VALIDATION_FAILED: Config validation failed
- GPIO_CONFLICT: GPIO already in use
- NVS_WRITE_FAILED: NVS storage full or corrupted
- TYPE_MISMATCH: Wrong data type
- MISSING_FIELD: Required field missing
- OUT_OF_RANGE: Value out of valid range
- UNKNOWN_ERROR: Unexpected error

Phase 4 Enhancement:
- Support for partial_success status (some items OK, some failed)
- failures array with detailed per-item error information
- DB update for config_status on sensors/actuators

Audit Logging:
- All config responses are stored in audit_logs table
- Provides history tracking for debugging and compliance
"""

from datetime import datetime, timezone
import inspect
from typing import List, Optional


from ...core.esp32_error_mapping import get_config_error_info
from ...core.metrics import (
    increment_contract_terminalization_blocked,
    increment_contract_unknown_code,
)
from ...core.logging_config import get_logger
from ...db.repositories.command_contract_repo import CommandContractRepository
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.repositories.esp_repo import ESPRepository
from ...db.repositories.sensor_repo import SensorRepository
from ...db.repositories.actuator_repo import ActuatorRepository
from ...db.session import resilient_session
from ...services.device_response_contract import canonicalize_config_response
from ...services.event_contract_serializers import serialize_config_response_event
from ..topics import TopicBuilder

logger = get_logger(__name__)


# ESP32 Config Error Code mapping
# Deutsche Übersetzungen aus esp32_error_mapping.py (get_config_error_info)


class ConfigHandler:
    """
    Handles configuration acknowledgement messages from ESP devices.

    Flow:
    1. Parse topic → extract esp_id
    2. Validate payload structure
    3. Log ACK status (success/failed)
    4. Optional: Store in DB for audit log
    """

    async def handle_config_ack(self, topic: str, payload: dict) -> bool:
        """
        Handle config response message from ESP32.

        Expected topic: kaiser/god/esp/{esp_id}/config_response

        Expected payload (Phase 4 - Extended format):
        {
            "status": "success" | "partial_success" | "error",
            "type": "sensor" | "actuator" | "zone" | "system",
            "count": 2,
            "failed_count": 1,
            "message": "2 configured, 1 failed",
            "failures": [
                {
                    "type": "sensor",
                    "gpio": 5,
                    "error_code": 1002,
                    "error": "GPIO_CONFLICT",
                    "detail": "GPIO 5 reserved by actuator (pump_1)"
                }
            ]
        }

        Also supports legacy format (single failed_item) for backward compatibility.

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully
        """
        try:
            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_config_response_topic(topic)
            if not parsed_topic:
                logger.error(f"Failed to parse config ACK topic: {topic}")
                return False

            esp_id = parsed_topic["esp_id"]
            payload = dict(payload)
            canonical = canonicalize_config_response(payload, esp_id=esp_id)

            # Step 2: Canonical-first extraction
            config_type = canonical.config_type
            status = canonical.status
            count = canonical.count
            failed_count = canonical.failed_count
            message = canonical.message
            error_code = canonical.error_code
            failures = canonical.failures
            failed_item = canonical.failed_item
            correlation_id = canonical.correlation_id
            request_id = payload.get("request_id")

            if canonical.is_contract_violation:
                increment_contract_unknown_code("config_response")
                logger.warning(
                    "Contract violation normalized on config_response: esp_id=%s raw_status=%s raw_type=%s raw_error_code=%s",
                    esp_id,
                    canonical.raw_status,
                    canonical.raw_type,
                    canonical.raw_error_code,
                )

            authority_key = self._build_terminal_authority_key(
                esp_id=esp_id,
                config_type=config_type,
                correlation_id=correlation_id,
                status=status,
                payload=payload,
            )
            async with resilient_session() as session:
                contract_repo = CommandContractRepository(session)
                _, was_stale = await contract_repo.upsert_terminal_event_authority(
                    event_class="config_response",
                    dedup_key=authority_key,
                    esp_id=esp_id,
                    outcome=status,
                    correlation_id=correlation_id,
                    is_final=canonical.is_final,
                    code=canonical.code,
                    reason=canonical.reason,
                    retryable=(canonical.retry_policy != "forbidden"),
                    generation=payload.get("generation"),
                    seq=payload.get("seq"),
                    payload_ts=payload.get("ts"),
                )
                await self._commit_session(session)
            if was_stale:
                increment_contract_terminalization_blocked(
                    event_class="config_response",
                    reason="terminal_authority_guard",
                )
                logger.info(
                    "Skipping stale config_response due to terminal authority guard: esp_id=%s status=%s key=%s",
                    esp_id,
                    status,
                    authority_key,
                    extra={
                        "event_class": "CONFIG_GUARD",
                        "action": "skip_stale_response",
                        "reason": "terminal_authority",
                        "status": "expected",
                        "esp_id": esp_id,
                        "config_type": config_type,
                        "authority_key": authority_key,
                    },
                )
                # Frontend recovery lane:
                # If the first terminal event was missed by the client (reconnect/window),
                # a duplicate/stale config_response can still be used to finalize
                # pending UI intents as long as correlation_id is present.
                if correlation_id:
                    try:
                        from ...websocket.manager import WebSocketManager

                        ws_manager = await WebSocketManager.get_instance()
                        replay_payload = serialize_config_response_event(
                            esp_id=esp_id,
                            config_type=config_type,
                            status=status,
                            count=count,
                            failed_count=failed_count,
                            message=message,
                            timestamp=int(datetime.now(timezone.utc).timestamp()),
                            correlation_id=correlation_id,
                            request_id=request_id,
                            reason_code=payload.get("reason_code"),
                            generation=payload.get("generation"),
                            config_fingerprint=payload.get("config_fingerprint"),
                            trigger_source=payload.get("trigger_source"),
                        )
                        # PKG-04a: distinct event type for guard-replay + correlation_id_source metadata.
                        # Frontend can treat guard-replay as a finalization-only signal without
                        # confusing it with a fresh ESP config_response.
                        correlation_id_source = (
                            "correlation_id"
                            if payload.get("correlation_id") is not None
                            else (
                                "request_id"
                                if payload.get("request_id") is not None
                                else "fallback_synthetic"
                            )
                        )
                        replay_payload.update(
                            {
                                "domain": canonical.domain,
                                "severity": canonical.severity,
                                "terminality": canonical.terminality,
                                "retry_policy": canonical.retry_policy,
                                "is_final": canonical.is_final,
                                "contract_violation": canonical.is_contract_violation,
                                "raw_status": canonical.raw_status,
                                "raw_type": canonical.raw_type,
                                "raw_error_code": canonical.raw_error_code,
                                "terminal_authority_replay": True,
                                "correlation_id_source": correlation_id_source,
                            }
                        )
                        await ws_manager.broadcast(
                            "config_response_guard_replay",
                            replay_payload,
                            correlation_id=correlation_id,
                        )
                    except Exception as replay_error:
                        logger.warning(
                            "Failed to broadcast stale config_response replay for %s: %s",
                            esp_id,
                            replay_error,
                        )
                return True

            # Step 3: Log response based on canonical status
            if status == "success":
                logger.info(
                    f"✅ Config Response from {esp_id}: {config_type} "
                    f"({count} items) - {message}"
                )
            elif status == "partial_success":
                # Phase 4: Partial success handling
                logger.warning(
                    f"⚠️ Config PARTIAL SUCCESS on {esp_id}: {config_type} "
                    f"- {count} OK, {failed_count} failed - {message}"
                )
                # Log each failure
                for failure in failures:
                    logger.warning(
                        f"   ↳ GPIO {failure.get('gpio', 'N/A')}: "
                        f"{failure.get('error', 'UNKNOWN')} - {failure.get('detail', 'No details')}"
                    )
            else:
                # Full failure - Hole deutsche Übersetzung
                error_info = get_config_error_info(error_code) if error_code else None
                error_description = (
                    error_info["message"] if error_info else f"Unbekannter Fehler: {error_code}"
                )
                failed_item = payload.get("failed_item", {})

                logger.error(
                    f"❌ Config FAILED on {esp_id}: {config_type} "
                    f"- {message} (Error: {error_code} - {error_description})"
                )

                # Log failures from Phase 4 format
                if failures:
                    for failure in failures:
                        logger.error(
                            f"   ↳ GPIO {failure.get('gpio', 'N/A')}: "
                            f"{failure.get('error', 'UNKNOWN')} - {failure.get('detail', 'No details')}"
                        )
                # Legacy: Log single failed_item
                elif failed_item:
                    logger.error(
                        f"   Failed item details: GPIO={failed_item.get('gpio', 'N/A')}, "
                        f"Type={failed_item.get('sensor_type', failed_item.get('actuator_type', 'N/A'))}"
                    )

            # Step 4: Update DB config_status based on canonical response
            db_update_ok = True
            if status == "success":
                # All items configured successfully → mark as "applied"
                db_update_ok = await self._mark_config_applied(esp_id, config_type)
            elif status == "partial_success":
                # Some succeeded, some failed → mark successes as applied, failures as failed
                db_update_ok = await self._mark_config_applied(esp_id, config_type)
                if failures:
                    db_update_ok = db_update_ok and await self._process_config_failures(
                        esp_id, config_type, failures
                    )
            elif failures:
                # Full failure with details → mark as failed
                db_update_ok = await self._process_config_failures(esp_id, config_type, failures)

            if not db_update_ok:
                logger.error("Config response persistence failed for %s - replay required", esp_id)
                return False

            # Step 5: Store in audit_log table for history tracking
            try:
                async with resilient_session() as session:
                    audit_repo = AuditLogRepository(session)
                    # Hole deutsche Beschreibung für Audit-Log
                    audit_error_info = get_config_error_info(error_code) if error_code else None
                    audit_error_desc = audit_error_info["message"] if audit_error_info else None

                    await audit_repo.log_config_response(
                        esp_id=esp_id,
                        config_type=config_type,
                        status=status,
                        count=count,
                        message=message,
                        error_code=error_code if status != "success" else None,
                        error_description=audit_error_desc,
                        failed_item=failed_item if status != "success" else None,
                        correlation_id=correlation_id,
                    )
                    await self._commit_session(session)
                    logger.debug(f"Config response stored in audit log: {esp_id}")
            except Exception as audit_error:
                # Don't fail the handler if audit logging fails, but log as error
                # (audit trail loss is compliance-relevant in industrial environments)
                logger.error(f"Failed to store config response in audit log: {audit_error}")
                return False

            # Step 6: WebSocket Broadcast (Phase 4 extended) - Mit deutschen Übersetzungen
            try:
                from ...websocket.manager import WebSocketManager

                ws_manager = await WebSocketManager.get_instance()

                # Hole deutsche Error-Info für WebSocket-Broadcast
                ws_error_info = get_config_error_info(error_code) if error_code else None

                broadcast_payload = serialize_config_response_event(
                    esp_id=esp_id,
                    config_type=config_type,
                    status=status,
                    count=count,
                    failed_count=failed_count,
                    message=(
                        ws_error_info["message"]
                        if ws_error_info and status != "success"
                        else message
                    ),
                    timestamp=int(datetime.now(timezone.utc).timestamp()),
                    correlation_id=correlation_id,
                    request_id=request_id,
                    reason_code=payload.get("reason_code"),
                    generation=payload.get("generation"),
                    config_fingerprint=payload.get("config_fingerprint"),
                    trigger_source=payload.get("trigger_source"),
                )
                broadcast_payload.update(
                    {
                        "domain": canonical.domain,
                        "severity": canonical.severity,
                        "terminality": canonical.terminality,
                        "retry_policy": canonical.retry_policy,
                        "is_final": canonical.is_final,
                        "contract_violation": canonical.is_contract_violation,
                        "raw_status": canonical.raw_status,
                        "raw_type": canonical.raw_type,
                        "raw_error_code": canonical.raw_error_code,
                    }
                )

                # Include error details for failed/partial configs - DEUTSCHE TEXTE
                if status != "success":
                    broadcast_payload.update(
                        serialize_config_response_event(
                            esp_id=esp_id,
                            config_type=config_type,
                            status=status,
                            count=count,
                            failed_count=failed_count,
                            message=broadcast_payload["message"],
                            timestamp=broadcast_payload["timestamp"],
                            correlation_id=correlation_id,
                            error_code=error_code,
                            error_description=(
                                ws_error_info["message"]
                                if ws_error_info
                                else f"Unbekannter Fehler: {error_code}"
                            ),
                            severity=(
                                ws_error_info["severity"].lower() if ws_error_info else "error"
                            ),
                            troubleshooting=(
                                ws_error_info["troubleshooting"] if ws_error_info else []
                            ),
                            recoverable=(ws_error_info["recoverable"] if ws_error_info else True),
                            user_action_required=(
                                ws_error_info["user_action_required"] if ws_error_info else True
                            ),
                            failures=failures if failures else None,
                            failed_item=failed_item if failed_item else None,
                            request_id=request_id,
                            reason_code=payload.get("reason_code"),
                            generation=payload.get("generation"),
                            config_fingerprint=payload.get("config_fingerprint"),
                            trigger_source=payload.get("trigger_source"),
                        )
                    )

                await ws_manager.broadcast(
                    "config_response",
                    broadcast_payload,
                    correlation_id=correlation_id,
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast config response via WebSocket: {e}")

            return True

        except Exception as e:
            logger.error(f"Error handling config ACK: {e}", exc_info=True)
            return False

    @staticmethod
    def _build_terminal_authority_key(
        *,
        esp_id: str,
        config_type: str,
        correlation_id: Optional[str],
        status: str,
        payload: dict,
    ) -> str:
        """
        Build stable dedup key for config_response terminal authority.

        Prefer correlation_id. Fallback includes immutable response shape to keep
        replay-idempotency without collapsing unrelated events.
        """
        if correlation_id:
            return f"corr:{str(correlation_id).strip().lower()}"
        ts_part = str(payload.get("ts", "na"))
        return (
            f"esp:{esp_id.strip().lower()}:cfg:{str(config_type).strip().lower()}:"
            f"status:{str(status).strip().lower()}:ts:{ts_part}"
        )

    @staticmethod
    async def _commit_session(session) -> None:
        """Commit helper tolerant to mocked sessions in tests."""
        commit_fn = getattr(session, "commit", None)
        if commit_fn is None:
            return
        result = commit_fn()
        if inspect.isawaitable(result):
            await result

    async def _mark_config_applied(
        self,
        esp_id: str,
        config_type: str,
    ) -> bool:
        """
        Mark all pending sensor/actuator configs as "applied" after successful ESP response.

        Only updates items with config_status="pending" to avoid overwriting
        items that were already marked as "failed" by a partial_success response.

        Args:
            esp_id: ESP device ID
            config_type: Configuration type (sensor/actuator)
        """
        try:
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                esp = await esp_repo.get_by_device_id(esp_id)

                if not esp:
                    logger.warning(
                        "ESP not found for config applied update: %s "
                        "(device may have been removed or is not yet registered, skipping)",
                        esp_id,
                    )
                    return True  # ACK: unregistered device cannot be updated, do not replay

                updated_count = 0

                if config_type in ("sensor", "system"):
                    sensor_repo = SensorRepository(session)
                    sensors = await sensor_repo.get_by_esp(esp.id)
                    for sensor in sensors:
                        if sensor.config_status == "pending":
                            sensor.config_status = "applied"
                            sensor.config_error = None
                            sensor.config_error_detail = None
                            updated_count += 1

                if config_type in ("actuator", "system"):
                    actuator_repo = ActuatorRepository(session)
                    actuators = await actuator_repo.get_by_esp(esp.id)
                    for actuator in actuators:
                        if actuator.config_status == "pending":
                            actuator.config_status = "applied"
                            actuator.config_error = None
                            actuator.config_error_detail = None
                            updated_count += 1

                if updated_count > 0:
                    await session.commit()
                    logger.info(
                        f"Marked {updated_count} {config_type} config(s) as applied for {esp_id}"
                    )
                return True

        except Exception as e:
            logger.error(f"Failed to mark config as applied: {e}", exc_info=True)
            return False

    async def _process_config_failures(
        self, esp_id: str, config_type: str, failures: List[dict]
    ) -> bool:
        """
        Phase 4: Process configuration failures and update database.

        Updates sensor/actuator records with config_status="failed" and
        stores the error details for UI display.

        Args:
            esp_id: ESP device ID
            config_type: Configuration type (sensor/actuator)
            failures: List of failure dicts from ESP
        """
        try:
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                esp = await esp_repo.get_by_device_id(esp_id)

                if not esp:
                    logger.warning(
                        "ESP not found for config failures: %s "
                        "(device may have been removed or is not yet registered, skipping)",
                        esp_id,
                    )
                    return True  # ACK: unregistered device cannot be updated, do not replay

                sensor_repo = SensorRepository(session)
                actuator_repo = ActuatorRepository(session)

                for failure in failures:
                    failure_type = failure.get("type", config_type)
                    gpio = failure.get("gpio")
                    error_name = failure.get("error", "UNKNOWN")
                    error_detail = failure.get("detail", "")

                    if gpio is None:
                        logger.warning(f"Failure without GPIO, skipping: {failure}")
                        continue

                    logger.info(
                        f"Processing config failure: {esp_id} {failure_type} "
                        f"GPIO {gpio} - {error_name}"
                    )

                    if failure_type == "sensor":
                        # Use sensor_type + address from failure for multi-value disambiguation
                        failure_sensor_type = failure.get("sensor_type")
                        failure_i2c_address = failure.get("i2c_address")
                        failure_onewire_address = failure.get("onewire_address")
                        if failure_sensor_type:
                            if failure_i2c_address:
                                sensor = await sensor_repo.get_by_esp_gpio_type_and_i2c(
                                    esp.id, gpio, failure_sensor_type, failure_i2c_address
                                )
                            elif failure_onewire_address:
                                sensor = await sensor_repo.get_by_esp_gpio_type_and_onewire(
                                    esp.id, gpio, failure_sensor_type, failure_onewire_address
                                )
                            else:
                                sensor = await sensor_repo.get_by_esp_gpio_and_type(
                                    esp.id, gpio, failure_sensor_type
                                )
                            sensors_to_update = [sensor] if sensor else []
                        else:
                            # No sensor_type in failure: update ALL sensors on this GPIO
                            sensors_to_update = await sensor_repo.get_all_by_esp_and_gpio(
                                esp.id, gpio
                            )
                        if sensors_to_update:
                            for sensor in sensors_to_update:
                                await sensor_repo.update(
                                    sensor.id,
                                    config_status="failed",
                                    config_error=error_name,
                                    config_error_detail=(
                                        error_detail[:200] if error_detail else None
                                    ),
                                )
                            logger.debug(
                                f"Updated {len(sensors_to_update)} sensor config_status=failed "
                                f"for GPIO {gpio}"
                            )
                        else:
                            logger.warning(f"Sensor not found for ESP {esp_id} GPIO {gpio}")

                    elif failure_type == "actuator":
                        actuator = await actuator_repo.get_by_esp_and_gpio(esp.id, gpio)
                        if actuator:
                            await actuator_repo.update(
                                actuator.id,
                                config_status="failed",
                                config_error=error_name,
                                config_error_detail=error_detail[:200] if error_detail else None,
                            )
                            logger.debug(f"Updated actuator config_status=failed for GPIO {gpio}")
                        else:
                            logger.warning(f"Actuator not found for ESP {esp_id} GPIO {gpio}")

                await session.commit()
                logger.info(f"Processed {len(failures)} config failures for {esp_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to process config failures: {e}", exc_info=True)
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """Validate config response payload structure.

        ESP32 ConfigResponseBuilder sends (Phase 4 extended):
        - status: "success", "partial_success", or "error"
        - type: "sensor", "actuator", "zone", "system"
        - count: number of successfully configured items
        - failed_count: (Phase 4) number of failed items
        - message: human-readable message
        - error_code: (on error) error code string
        - failed_item: (legacy) single failed config item
        - failures: (Phase 4) array of failure details
        """
        # Required fields: status and type
        if "status" not in payload:
            return {"valid": False, "error": "Missing required field: status"}

        # Accept both "type" (ESP32) and "config_type" (legacy)
        if "type" not in payload and "config_type" not in payload:
            return {"valid": False, "error": "Missing required field: type"}

        # Type validation
        valid_config_types = ["sensor", "actuator", "zone", "system"]
        config_type = payload.get("type", payload.get("config_type"))
        if config_type not in valid_config_types:
            return {
                "valid": False,
                "error": f"Invalid type. Must be one of: {valid_config_types}",
            }

        # Status validation - Phase 4: Added "partial_success"
        valid_statuses = ["success", "partial_success", "error", "failed"]
        if payload["status"] not in valid_statuses:
            return {
                "valid": False,
                "error": f"Invalid status. Must be one of: {valid_statuses}",
            }

        return {"valid": True, "error": ""}


# Global handler instance
_handler_instance: Optional[ConfigHandler] = None


def get_config_handler() -> ConfigHandler:
    """Get singleton config handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ConfigHandler()
    return _handler_instance


async def handle_config_ack(topic: str, payload: dict) -> bool:
    """Handle config ACK message (convenience function)."""
    handler = get_config_handler()
    return await handler.handle_config_ack(topic, payload)
