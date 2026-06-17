"""
MQTT Handler: ESP32 Error Events

Processes error events from ESP32 devices:
- Parses error event topics
- Validates payloads
- Enriches with error-code mapping
- Saves to audit log
- Broadcasts via WebSocket

Architecture Philosophy (CRITICAL):
- Server TRUSTS ESP32 hardware status COMPLETELY
- NO re-validation of ESP error codes
- Error info is for ENRICHMENT only (user messages, troubleshooting)
- Unknown error codes are stored with generic message (system MUST NOT break)
- ESP RAW message is always preserved for debugging

Flow (follows sensor_handler pattern):
1. Parse topic → extract esp_id
2. Validate payload structure
3. Lookup ESP device (with resilience)
4. Enrich error info via error-code mapping
5. Save to audit log
6. Broadcast via WebSocket

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
"""

import asyncio
from typing import Optional

from ...core.esp32_error_mapping import get_error_info
from ...core.error_codes import (
    ConfigErrorCode,
    ValidationErrorCode,
)
from ...core.logging_config import get_logger
from ...core.metrics import increment_contract_unknown_code, increment_esp_error
from ...core.resilience import ServiceUnavailableError
from ...db.repositories import AuditLogRepository, ESPRepository
from ...db.session import resilient_session
from ...services.ai_service import ErrorAnalysisRequest, ai_service
from ...services.event_contract_serializers import serialize_error_event
from ...services.system_event_contract import canonicalize_error_event
from ..topics import TopicBuilder

logger = get_logger(__name__)


class ErrorEventHandler:
    """
    Handles incoming error events from ESP32 devices.

    Flow (follows sensor_handler pattern):
    1. Parse topic → extract esp_id
    2. Validate payload structure
    3. Lookup ESP device (with resilience)
    4. Enrich error info via error-code mapping
    5. Save to audit log
    6. Broadcast via WebSocket

    Architecture Philosophy:
    - ESP32 Hardware Status = TRUTH
    - Server TRUSTS error codes completely
    - NO re-validation, NO auto-retry
    - Enrichment only for user-friendly messages
    """

    @staticmethod
    def _extract_context_fields(payload_context: object) -> dict:
        """
        Extract AUT-456 correlation fields from payload context.

        Backwards compatibility:
        - Missing/non-dict context returns an empty mapping.
        """
        if not isinstance(payload_context, dict):
            return {}
        return {
            "topic": payload_context.get("topic"),
            "gpio": payload_context.get("gpio"),
            "sensor_type": payload_context.get("sensor_type"),
            "reason_class": payload_context.get("reason_class"),
        }

    async def handle_error_event(self, topic: str, payload: dict) -> bool:
        """
        Handle error event message.

        Expected topic: kaiser/god/esp/{esp_id}/system/error

        Expected payload:
        {
            "error_code": 1023,
            "severity": 2,  # 0=INFO, 1=WARNING, 2=ERROR, 3=CRITICAL
            "category": "HARDWARE",
            "message": "Invalid OneWire ROM-Code length",
            "context": {"gpio": 4, "sensor_type": "ds18b20"},
            "timestamp": 1735818000
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            payload = dict(payload)
            canonical = canonicalize_error_event(payload)
            payload = canonical.payload
            if canonical.is_contract_violation:
                increment_contract_unknown_code("error")
                logger.warning(
                    "Error-event contract violation normalized: %s (raw=%s)",
                    canonical.contract_reason,
                    canonical.raw_fields,
                )

            # Step 1: Parse topic (follows sensor_handler pattern)
            parsed_topic = TopicBuilder.parse_system_error_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse error event topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]

            logger.debug(
                f"Processing error event: esp_id={esp_id_str}, "
                f"error_code={payload.get('error_code')}"
            )

            # Step 2: Validate payload (follows sensor_handler._validate_payload pattern)
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid error event payload from {esp_id_str}: "
                    f"{validation_result['error']}"
                )
                return False

            # Step 3: Get database session (follows sensor_handler pattern)
            try:
                async with resilient_session() as session:
                    esp_repo = ESPRepository(session)
                    audit_repo = AuditLogRepository(session)

                    # Step 4: Lookup ESP device (follows sensor_handler pattern)
                    esp_device = await esp_repo.get_by_device_id(esp_id_str)
                    if not esp_device:
                        logger.error(
                            f"[{ConfigErrorCode.ESP_DEVICE_NOT_FOUND}] "
                            f"ESP device not found: {esp_id_str}"
                        )
                        return False

                    # Step 5: Enrich error info via mapping
                    # CRITICAL: Server TRUSTS ESP-Error-Code COMPLETELY!
                    # NO Re-Validation, NO doubts about ESP hardware status!
                    error_code_int = payload.get("error_code")
                    error_info = get_error_info(error_code_int) if error_code_int else None

                    # Step 6: Map severity (ESP32: 0-3 → AuditLog: info/warning/error/critical)
                    # IMPORTANT: ESP severity is TRUTH, server only maps format!
                    severity = str(payload.get("severity_label", "error"))

                    # Step 7: Save to audit log (follows audit_log_repo pattern)
                    # CRITICAL: Store ESP error COMPLETELY, even if unknown code!
                    # System MUST NOT break on unknown error codes!
                    error_description = (
                        error_info["message"]
                        if error_info
                        else payload.get("message", f"Unknown ESP32 error: {error_code_int}")
                    )

                    context_payload = payload.get("context", {})
                    context_fields = self._extract_context_fields(context_payload)
                    details = {
                        "error_code": error_code_int,
                        "category": payload.get("category"),
                        "context": context_payload if isinstance(context_payload, dict) else {},
                        "context_topic": context_fields.get("topic"),
                        "context_gpio": context_fields.get("gpio"),
                        "context_sensor_type": context_fields.get("sensor_type"),
                        "context_reason_class": context_fields.get("reason_class"),
                        "troubleshooting": (error_info["troubleshooting"] if error_info else []),
                        "docs_link": error_info["docs_link"] if error_info else None,
                        "user_action_required": (
                            error_info["user_action_required"] if error_info else False
                        ),
                        "recoverable": error_info["recoverable"] if error_info else True,
                        # IMPORTANT: Store RAW ESP message for debugging
                        "esp_raw_message": payload.get("message"),
                        "esp_severity": payload.get("severity"),
                        "esp_severity_label": severity,
                        "esp_timestamp": payload.get("timestamp"),
                        "contract_violation": canonical.is_contract_violation,
                        "contract_code": canonical.contract_code,
                        "contract_reason": canonical.contract_reason,
                        "raw_severity": canonical.raw_fields.get("raw_severity"),
                        "raw_category": canonical.raw_fields.get("raw_category"),
                    }

                    error_log = await audit_repo.log_mqtt_error(
                        source_id=esp_id_str,
                        error_code=str(canonical.contract_code or error_code_int),
                        error_description=error_description,
                        details=details,
                    )

                    # Commit transaction
                    await session.commit()

                    # AI enrichment — fire-and-forget, non-blocking
                    if ai_service.is_available():
                        asyncio.create_task(
                            _enrich_error_with_ai(
                                error_code_int,
                                esp_id_str,
                                payload.get("context", {}),
                            )
                        )

                    # Update Prometheus metrics for Grafana alerting
                    increment_esp_error(esp_id_str)

                    logger.info(
                        f"Error event saved: id={error_log.id}, esp_id={esp_id_str}, "
                        f"error_code={error_code_int}, severity={severity}"
                    )

                    # Step 8: WebSocket Broadcast (follows sensor_handler pattern)
                    try:
                        from ...websocket.manager import WebSocketManager

                        ws_manager = await WebSocketManager.get_instance()
                        # Build title: short German label (message_de) or fallback
                        error_title = (
                            error_info.get("message_de", f"Fehler {error_code_int}")
                            if error_info
                            else f"Fehler {error_code_int}"
                        )

                        broadcast_payload = serialize_error_event(
                            esp_id=esp_id_str,
                            esp_name=esp_device.name or esp_id_str,
                            error_log_id=error_log.id,
                            error_code=error_code_int,
                            severity=severity,
                            category=payload.get("category"),
                            title=error_title,
                            message=error_description,
                            troubleshooting=(error_info["troubleshooting"] if error_info else []),
                            user_action_required=(
                                error_info["user_action_required"] if error_info else False
                            ),
                            recoverable=(error_info["recoverable"] if error_info else True),
                            docs_link=(error_info.get("docs_link") if error_info else None),
                            context=payload.get("context", {}),
                            timestamp=payload.get("timestamp"),
                        )
                        broadcast_payload.update(
                            {
                                "contract_violation": canonical.is_contract_violation,
                                "contract_code": canonical.contract_code,
                                "contract_reason": canonical.contract_reason,
                                "raw_severity": canonical.raw_fields.get("raw_severity"),
                                "raw_category": canonical.raw_fields.get("raw_category"),
                            }
                        )
                        await ws_manager.broadcast("error_event", broadcast_payload)
                        logger.debug(f"WebSocket broadcast completed for error_event: {esp_id_str}")
                    except Exception as e:
                        logger.warning(f"Failed to broadcast error event via WebSocket: {e}")

                    return True

            except ServiceUnavailableError as e:
                logger.warning(
                    f"[resilience] Error event handling blocked: {e.service_name} unavailable. "
                    f"Error from {esp_id_str} will be dropped."
                )
                return False

        except Exception as e:
            logger.error(
                f"Error handling error event: {e}",
                exc_info=True,
            )
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate error event payload structure.

        Required fields: error_code, severity
        Optional fields: message, category, context, timestamp

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str, "error_code": int}
        """
        # Required fields: error_code, severity
        if "error_code" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: error_code",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "severity" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: severity",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Type validation
        if not isinstance(payload["error_code"], int):
            return {
                "valid": False,
                "error": "Field 'error_code' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if not isinstance(payload["severity"], int):
            return {
                "valid": False,
                "error": "Field 'severity' must be integer (0-3)",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Range validation for severity
        if payload["severity"] not in (0, 1, 2, 3):
            return {
                "valid": False,
                "error": "Field 'severity' must be 0 (INFO), 1 (WARNING), 2 (ERROR), or 3 (CRITICAL)",
                "error_code": ValidationErrorCode.VALUE_OUT_OF_RANGE,
            }

        return {"valid": True, "error": "", "error_code": ValidationErrorCode.NONE}


async def _enrich_error_with_ai(error_code: int, esp_id: str, context: dict) -> None:
    """
    Fire-and-forget AI enrichment for error events.

    Non-critical: exceptions are swallowed to never affect the main handler flow.
    """
    try:
        finding = await ai_service.analyze_error(
            ErrorAnalysisRequest(
                error_code=error_code,
                context={"esp_id": esp_id, **context},
                recent_errors=[],
                system_state={},
            )
        )
        logger.info(
            "AI finding for error %d (ESP %s): %s",
            error_code,
            esp_id,
            finding.root_cause,
        )
    except Exception:
        logger.debug("AI error enrichment failed (non-critical)", exc_info=True)


# Global handler instance (follows sensor_handler pattern)
_handler_instance: Optional[ErrorEventHandler] = None


def get_error_handler() -> ErrorEventHandler:
    """
    Get singleton error event handler instance.

    Returns:
        ErrorEventHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ErrorEventHandler()
    return _handler_instance


async def handle_error_event(topic: str, payload: dict) -> bool:
    """
    Handle error event message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_error_handler()
    return await handler.handle_error_event(topic, payload)
