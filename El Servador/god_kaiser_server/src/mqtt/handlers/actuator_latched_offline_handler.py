"""
MQTT Handler: Actuator Latched-Offline Telemetry (AUT-117)

Pure observability handler for actuator latch decisions emitted by El
Trabajante (ESP32) when MQTT disconnects. Topic:
``kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/latched_offline``.

Scope:
- Parse the topic (extract ``esp_id`` and ``gpio``).
- Validate the payload defensively (missing fields are tolerated, but
  the canonical shape is logged for forensic correlation).
- Emit a structured log line for Loki/Grafana.
- Broadcast a WebSocket event ``actuator_latched_offline`` so the
  Operator Dashboard can surface latch decisions in real time.

Explicitly NOT in scope:
- No database writes. Actuator state authority remains
  ``actuator_history`` (commands) and the ``actuator/{gpio}/status``
  topic stream (telemetry).
- No notification routing. The companion ``actuator/{gpio}/alert`` topic
  feeds the human-readable notification inbox; this handler is the
  machine-readable counterpart.

Expected payload (SSOT — see ``MQTT_TOPICS.md`` §2.8):

    {
        "esp_id": "ESP_12AB34CD",
        "gpio": 25,
        "ts": 1735818000,
        "reason": "offline_rule_hold" | "safety_forced_off" | "manual_override",
        "actuator_state": "on" | "off",
        "offline_rule_count": 1
    }
"""

from typing import Any, Dict, Optional

from ...core.error_codes import ValidationErrorCode
from ...core.logging_config import get_logger
from ..topics import TopicBuilder

logger = get_logger(__name__)

# SSOT reason values — keep in sync with MQTT_TOPICS.md §2.8 and
# El Trabajante/src/services/actuator/actuator_manager.cpp:publishLatchedOffline.
_VALID_REASONS = frozenset(
    {"offline_rule_hold", "safety_forced_off", "manual_override"}
)


class ActuatorLatchedOfflineHandler:
    """
    Handles actuator latched-offline telemetry messages from ESP32 devices.

    Flow:
    1. Parse topic -> extract esp_id, gpio.
    2. Read structured payload fields with defensive defaults.
    3. Emit structured log line.
    4. Broadcast WebSocket event ``actuator_latched_offline`` to the
       Operator Dashboard.
    """

    async def handle_actuator_latched_offline(
        self, topic: str, payload: dict
    ) -> bool:
        """
        Handle a latched-offline telemetry message.

        Args:
            topic: MQTT topic string.
            payload: Parsed JSON payload dict.

        Returns:
            True if the event was processed (even if payload was incomplete),
            False only for unrecoverable errors (topic parse failure or
            unexpected exception).
        """
        try:
            parsed = TopicBuilder.parse_actuator_latched_offline_topic(topic)
            if not parsed:
                logger.error(
                    "[%s] Failed to parse actuator_latched_offline topic: %s",
                    ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    topic,
                )
                return False

            esp_id_topic: str = parsed["esp_id"]
            gpio_topic: int = parsed["gpio"]

            safe_payload: Dict[str, Any] = (
                payload if isinstance(payload, dict) else {}
            )

            # Topic is authoritative for esp_id/gpio (defense-in-depth):
            # use topic values for routing, but expose payload values
            # downstream so contract drift remains visible.
            esp_id = esp_id_topic
            gpio = gpio_topic

            reason = str(safe_payload.get("reason", "unknown"))
            actuator_state = str(safe_payload.get("actuator_state", "unknown"))
            offline_rule_count = safe_payload.get("offline_rule_count")
            ts = safe_payload.get("ts")

            if reason not in _VALID_REASONS:
                # Unknown reason is not fatal — log for contract observability.
                logger.warning(
                    "actuator_latched_offline received with unknown reason "
                    "(esp_id=%s gpio=%s reason=%s)",
                    esp_id,
                    gpio,
                    reason,
                )

            logger.info(
                "actuator_latched_offline: esp_id=%s gpio=%s reason=%s "
                "actuator_state=%s offline_rule_count=%s ts=%s",
                esp_id,
                gpio,
                reason,
                actuator_state,
                offline_rule_count,
                ts,
                extra={
                    "event_class": "ACTUATOR_LATCHED_OFFLINE",
                    "esp_id": esp_id,
                    "gpio": gpio,
                    "reason": reason,
                    "actuator_state": actuator_state,
                    "offline_rule_count": offline_rule_count,
                    "ts": ts,
                },
            )

            # WebSocket broadcast for the Operator Dashboard. Failures here
            # MUST NOT block MQTT processing — telemetry is best-effort.
            try:
                from ...websocket.manager import WebSocketManager

                ws_manager = await WebSocketManager.get_instance()
                await ws_manager.broadcast(
                    "actuator_latched_offline",
                    {
                        "esp_id": esp_id,
                        "gpio": gpio,
                        "reason": reason,
                        "actuator_state": actuator_state,
                        "offline_rule_count": offline_rule_count,
                        "ts": ts,
                    },
                )
                logger.debug(
                    "actuator_latched_offline broadcast via WebSocket "
                    "(esp_id=%s gpio=%s)",
                    esp_id,
                    gpio,
                )
            except Exception as ws_err:
                logger.debug(
                    "WebSocket broadcast for actuator_latched_offline skipped: %s",
                    ws_err,
                )

            return True

        except Exception as exc:
            logger.error(
                "Error handling actuator_latched_offline: %s",
                exc,
                exc_info=True,
            )
            return False


# Global handler instance (follows queue_pressure_handler pattern).
_handler_instance: Optional[ActuatorLatchedOfflineHandler] = None


def get_actuator_latched_offline_handler() -> ActuatorLatchedOfflineHandler:
    """Get singleton actuator latched-offline handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ActuatorLatchedOfflineHandler()
    return _handler_instance


async def handle_actuator_latched_offline(topic: str, payload: dict) -> bool:
    """Handle actuator latched-offline message (convenience function)."""
    handler = get_actuator_latched_offline_handler()
    return await handler.handle_actuator_latched_offline(topic, payload)
