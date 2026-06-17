"""
MQTT Handler: ESP recovery_confirm after clear_emergency (AUT-118).

Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/recovery_confirm
QoS: 1
"""

from typing import Optional

from ...core.logging_config import get_logger
from ..topics import TopicBuilder

logger = get_logger(__name__)


class RecoveryConfirmHandler:
    async def handle_recovery_confirm(self, topic: str, payload: dict) -> bool:
        try:
            parsed = TopicBuilder.parse_recovery_confirm_topic(topic)
            if not parsed:
                logger.error("Failed to parse recovery_confirm topic: %s", topic)
                return False

            esp_id = parsed["esp_id"]
            safe = payload if isinstance(payload, dict) else {}
            corr = safe.get("correlation_id")
            cmd = safe.get("command", "clear_emergency")
            state = safe.get("state", "unknown")

            logger.info(
                "Recovery confirm: esp_id=%s command=%s state=%s correlation_id=%s",
                esp_id,
                cmd,
                state,
                corr,
                extra={
                    "event_class": "RECOVERY_CONFIRM",
                    "esp_id": esp_id,
                    "correlation_id": corr,
                },
            )
            return True
        except Exception as exc:
            logger.error("Error handling recovery_confirm: %s", exc, exc_info=True)
            return False


_handler_instance: Optional[RecoveryConfirmHandler] = None


def get_recovery_confirm_handler() -> RecoveryConfirmHandler:
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = RecoveryConfirmHandler()
    return _handler_instance


async def handle_recovery_confirm(topic: str, payload: dict) -> bool:
    return await get_recovery_confirm_handler().handle_recovery_confirm(topic, payload)
