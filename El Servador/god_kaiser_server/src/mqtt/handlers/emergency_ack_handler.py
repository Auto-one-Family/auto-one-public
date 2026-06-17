"""
MQTT Handler: ESP emergency application ACK (AUT-118).

Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency/ack
QoS: 1

Parallel transport to ``intent_outcome`` so the server can correlate execution
when offline buffering dropped intent_outcome delivery.
"""

from typing import Optional

from ...core.logging_config import get_logger
from ..topics import TopicBuilder

logger = get_logger(__name__)


class EmergencyAckHandler:
    async def handle_emergency_ack(self, topic: str, payload: dict) -> bool:
        try:
            parsed = TopicBuilder.parse_emergency_ack_topic(topic)
            if not parsed:
                logger.error("Failed to parse emergency_ack topic: %s", topic)
                return False

            esp_id = parsed["esp_id"]
            safe = payload if isinstance(payload, dict) else {}
            corr = safe.get("correlation_id")
            cmd = safe.get("command", "emergency_stop")
            outcome = safe.get("outcome", "unknown")
            seq = safe.get("seq")

            logger.info(
                "Emergency application ACK: esp_id=%s command=%s outcome=%s correlation_id=%s seq=%s",
                esp_id,
                cmd,
                outcome,
                corr,
                seq,
                extra={
                    "event_class": "EMERGENCY_ACK",
                    "esp_id": esp_id,
                    "correlation_id": corr,
                    "command": cmd,
                },
            )
            return True
        except Exception as exc:
            logger.error("Error handling emergency_ack: %s", exc, exc_info=True)
            return False


_handler_instance: Optional[EmergencyAckHandler] = None


def get_emergency_ack_handler() -> EmergencyAckHandler:
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = EmergencyAckHandler()
    return _handler_instance


async def handle_emergency_ack(topic: str, payload: dict) -> bool:
    return await get_emergency_ack_handler().handle_emergency_ack(topic, payload)
