"""
MQTT Handler: Actuator Alert Messages

Processes emergency and alert messages from ESP32 actuators:
- Emergency stop notifications
- Runtime timeout alerts
- Safety constraint violations
- Critical error conditions

Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert
QoS: 1 (At Least Once)

Expected Payload:
{
    "esp_id": "ESP_12AB34CD",
    "zone_id": "zone_main",
    "ts": 1733000000,          // Unix timestamp (seconds)
    "gpio": 25,
    "alert_type": "emergency_stop",
    "message": "Actuator stopped due to safety constraint"
}

Alert Types:
- emergency_stop: Manual or automatic emergency stop triggered
- runtime_protection: Actuator exceeded max runtime, auto-stopped
- safety_violation: Safety constraint violated
- hardware_error: Hardware malfunction detected
"""

from datetime import datetime, timezone
from typing import Optional

from ...core.esp32_error_mapping import get_actuator_alert_info
from ...core.logging_config import get_logger
from ...core.request_context import generate_mqtt_correlation_id, get_request_id
from ...db.repositories import ActuatorRepository, ESPRepository
from ...db.session import resilient_session

logger = get_logger(__name__)

# Timestamp validation constants
MIN_VALID_TIMESTAMP = 1700000000  # ~2023-11-14
MAX_VALID_TIMESTAMP = 2500000000  # ~2049-03-22

# FIX-15: Severity mapping uses only ISA-18.2 levels (critical/warning/info)
ALERT_SEVERITY = {
    "emergency_stop": "critical",
    "runtime_protection": "warning",
    "safety_violation": "critical",
    "hardware_error": "warning",
}

# FIX-15: Category mapping for NotificationRouter
ALERT_CATEGORY = {
    "emergency_stop": "system",
    "runtime_protection": "maintenance",
    "safety_violation": "security",
    "hardware_error": "infrastructure",
}


class ActuatorAlertHandler:
    """
    Handles actuator alert messages from ESP32 devices.

    Flow:
    1. Parse topic → extract esp_id, gpio
    2. Validate payload structure
    3. Convert ESP32 timestamp to datetime
    4. Lookup ESP device
    5. Log alert to actuator history
    6. Update actuator state (if emergency)
    7. Broadcast via WebSocket for real-time dashboard updates
    """

    async def handle_actuator_alert(self, topic: str, payload: dict) -> bool:
        """
        Handle actuator alert message.

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Step 1: Validate payload
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                logger.error(f"Invalid actuator alert payload: {validation_result['error']}")
                return False

            esp_id_str = payload["esp_id"]
            gpio = payload["gpio"]
            alert_type = payload.get("alert_type", payload.get("type", "unknown"))
            message = payload.get("message", "")
            zone_id = payload.get("zone_id", "")

            # Determine alert severity
            severity = ALERT_SEVERITY.get(alert_type, "warning")

            # Log with appropriate level based on severity
            if severity == "critical":
                logger.critical(
                    f"ACTUATOR ALERT [{alert_type.upper()}]: "
                    f"esp_id={esp_id_str}, gpio={gpio}, zone={zone_id}"
                )
                logger.critical(f"   Message: {message}")
            else:
                logger.warning(
                    f"ACTUATOR ALERT [{alert_type}]: "
                    f"esp_id={esp_id_str}, gpio={gpio}, message={message}"
                )

            # Step 2: Convert ESP32 timestamp
            esp32_timestamp = self._convert_timestamp(payload.get("ts", 0))

            # MQTT ingress correlation (subscriber ContextVar); fallback matches Subscriber logic
            topic_suffix = topic.rsplit("/", 1)[-1] if "/" in topic else topic
            ingress_cid = get_request_id()
            if not ingress_cid:
                ingress_cid = generate_mqtt_correlation_id(
                    esp_id_str, topic_suffix, payload.get("seq")
                )

            # Step 3: Get database session and repositories
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                actuator_repo = ActuatorRepository(session)

                # Step 4: Lookup ESP device
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if not esp_device:
                    logger.warning(
                        f"ESP device not found for alert: {esp_id_str}. "
                        "Alert will be logged without device reference."
                    )
                    # Don't fail - still process the alert
                    return True

                # Step 5: Log alert to command history
                await actuator_repo.log_command(
                    esp_id=esp_device.id,
                    gpio=gpio,
                    actuator_type="unknown",  # May not be available in alert
                    command_type=f"ALERT_{alert_type.upper()}",
                    value=0.0,
                    success=False,  # Alerts typically indicate issues
                    issued_by="esp32_alert",
                    error_message=message,
                    timestamp=esp32_timestamp,
                    metadata={
                        "alert_type": alert_type,
                        "severity": severity,
                        "zone_id": zone_id,
                        "raw_payload": payload,
                    },
                )

                # Step 6: Update actuator state if emergency stop
                if alert_type in ["emergency_stop", "runtime_protection", "safety_violation"]:
                    try:
                        await actuator_repo.update_state(
                            esp_id=esp_device.id,
                            gpio=gpio,
                            actuator_type="unknown",
                            current_value=0.0,
                            state="off",
                            timestamp=esp32_timestamp,
                            last_command=f"ALERT_{alert_type.upper()}",
                            error_message=message,
                        )
                        logger.info(
                            f"Actuator state updated to OFF due to alert: "
                            f"esp_id={esp_id_str}, gpio={gpio}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update actuator state: {e}")

                # Commit transaction
                await session.commit()

                # Step 7: WebSocket broadcast (non-blocking, critical for dashboard)
                # Mit deutschen Übersetzungen für das Frontend
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()

                    # Hole deutsche Alert-Informationen
                    alert_info = get_actuator_alert_info(alert_type)

                    # Deutsche Message verwenden, falls ESP-Message leer oder generisch
                    german_message = alert_info["message"] if alert_info else message
                    # Falls ESP eine spezifische Message hat, diese anhängen
                    if message and message != alert_type:
                        german_message = (
                            f"{alert_info['message']} - {message}" if alert_info else message
                        )

                    await ws_manager.broadcast(
                        "actuator_alert",
                        {
                            "esp_id": esp_id_str,
                            "gpio": gpio,
                            "alert_type": alert_type,
                            "severity": alert_info["severity"].lower() if alert_info else severity,
                            "category": alert_info["category"] if alert_info else "SYSTEM",
                            # Deutsche Meldung
                            "message": german_message,
                            # Deutsche Troubleshooting-Schritte
                            "troubleshooting": alert_info["troubleshooting"] if alert_info else [],
                            "recoverable": alert_info["recoverable"] if alert_info else True,
                            "user_action_required": (
                                alert_info["user_action_required"] if alert_info else False
                            ),
                            "zone_id": zone_id,
                            "timestamp": payload.get("ts", 0),
                            "correlation_id": ingress_cid,
                        },
                    )
                    logger.debug(f"Alert broadcast via WebSocket: {alert_type}")
                except Exception as e:
                    logger.debug(f"WebSocket broadcast skipped: {e}")

                # FIX-15: Route through NotificationRouter for persistence + inbox
                try:
                    from ...schemas.notification import NotificationCreate
                    from ...services.notification_router import NotificationRouter

                    alert_info = get_actuator_alert_info(alert_type)
                    category = ALERT_CATEGORY.get(alert_type, "system")
                    title = alert_info["message"] if alert_info else f"Actuator Alert: {alert_type}"
                    body = message if message and message != alert_type else None

                    dev_corr = payload.get("correlation_id")
                    meta = {
                        "esp_id": esp_id_str,
                        "gpio": gpio,
                        "alert_type": alert_type,
                        "zone_id": zone_id,
                        "mqtt_ingress_correlation_id": ingress_cid,
                    }
                    if isinstance(dev_corr, str) and dev_corr.strip():
                        meta["device_correlation_id"] = dev_corr.strip()

                    notification = NotificationCreate(
                        user_id=None,  # Broadcast to all users
                        channel="websocket",
                        severity=severity,
                        category=category,
                        title=title[:255],
                        body=body,
                        metadata=meta,
                        source="mqtt_handler",
                        correlation_id=ingress_cid,
                    )

                    notification_router = NotificationRouter(session)
                    await notification_router.route(notification)
                    logger.debug(f"Actuator alert routed via NotificationRouter: {alert_type}")
                except Exception as e:
                    # NotificationRouter failure MUST NOT block MQTT processing
                    logger.warning(f"NotificationRouter routing failed: {e}")

                return True

        except Exception as e:
            logger.error(
                f"Error handling actuator alert: {e}",
                exc_info=True,
            )
            return False

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate actuator alert payload structure.

        Required fields: ts, esp_id, gpio, alert_type OR type

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str}
        """
        # Check required fields
        if "ts" not in payload:
            return {"valid": False, "error": "Missing required field: ts"}

        if "esp_id" not in payload:
            return {"valid": False, "error": "Missing required field: esp_id"}

        if "gpio" not in payload:
            return {"valid": False, "error": "Missing required field: gpio"}

        # Accept both "alert_type" and "type"
        if "alert_type" not in payload and "type" not in payload:
            return {"valid": False, "error": "Missing required field: alert_type or type"}

        # Type validation
        if not isinstance(payload["ts"], (int, float)):
            return {
                "valid": False,
                "error": "Field 'ts' must be numeric (Unix timestamp)",
            }

        if not isinstance(payload["gpio"], int):
            return {"valid": False, "error": "Field 'gpio' must be integer"}

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


# Global handler instance
_handler_instance: Optional[ActuatorAlertHandler] = None


def get_actuator_alert_handler() -> ActuatorAlertHandler:
    """
    Get singleton actuator alert handler instance.

    Returns:
        ActuatorAlertHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ActuatorAlertHandler()
    return _handler_instance


async def handle_actuator_alert(topic: str, payload: dict) -> bool:
    """
    Handle actuator alert message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_actuator_alert_handler()
    return await handler.handle_actuator_alert(topic, payload)
