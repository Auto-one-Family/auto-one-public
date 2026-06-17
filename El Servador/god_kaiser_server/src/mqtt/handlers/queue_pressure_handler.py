"""
MQTT Handler: ESP32 Publish-Queue Pressure Events (PKG-01b / AUT-456)

Observability handler for queue-pressure lifecycle events published by
El Trabajante (ESP32) on ``kaiser/{kaiser_id}/esp/{esp_id}/system/queue_pressure``.

Scope:
- Parse the topic to extract the ESP identifier.
- Increment a Prometheus counter labelled by (esp_id, event).
- Emit a structured log line for Loki/Grafana correlation.
- Mirror transition events into audit logs for SQL-level correlation with
  `mqtt_error` context data.
- Broadcast lightweight `queue_pressure` WebSocket events (best effort).
"""

from typing import Optional

from ...core.error_codes import ValidationErrorCode
from ...core.logging_config import get_logger
from ...core.metrics import increment_queue_pressure_event
from ...db.repositories import AuditLogRepository
from ...db.session import resilient_session
from ..topics import TopicBuilder

logger = get_logger(__name__)


class QueuePressureHandler:
    """
    Handles queue-pressure events from ESP32 devices.

    Flow:
    1. Parse topic -> extract esp_id.
    2. Read event label + telemetry fields (defensive, missing-tolerant).
    3. Increment Prometheus counter for (esp_id, event).
    4. Emit structured log for downstream analysis.
    5. Set/clear in-memory pressure flag consumed by heartbeat handler and
       sensor scheduler to gate automated server→ESP publishes under pressure.
    """

    def __init__(self) -> None:
        # R1 — AUT-590: ESPs currently under FreeRTOS publish-queue pressure.
        # Set on "entered_pressure", cleared on "recovered".
        self._esp_under_pressure: set[str] = set()

    @staticmethod
    def _normalize_event(event: str) -> str:
        if event == "recovered":
            return "exited_pressure"
        return event

    async def _persist_transition(
        self,
        esp_id: str,
        topic: str,
        event: str,
        payload: dict,
    ) -> None:
        normalized_event = self._normalize_event(event)
        severity = "warning" if normalized_event == "entered_pressure" else "info"
        details = {
            "topic": topic,
            "event": normalized_event,
            "raw_event": event,
            "fill_level": payload.get("fill_level"),
            "high_watermark": payload.get("high_watermark"),
            "shed_count": payload.get("shed_count"),
            "drop_count": payload.get("drop_count"),
            "ts": payload.get("ts"),
        }
        try:
            async with resilient_session() as session:
                audit_repo = AuditLogRepository(session)
                await audit_repo.log_device_event(
                    esp_id=esp_id,
                    event_type="queue_pressure_transition",
                    status="observed",
                    message=f"queue_pressure:{normalized_event}",
                    details=details,
                    severity=severity,
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Failed queue_pressure audit mirror: %s", exc)

    async def _broadcast_transition(self, esp_id: str, event: str, payload: dict) -> None:
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "queue_pressure",
                {
                    "esp_id": esp_id,
                    "event": self._normalize_event(event),
                    "raw_event": event,
                    "fill_level": payload.get("fill_level"),
                    "high_watermark": payload.get("high_watermark"),
                    "shed_count": payload.get("shed_count"),
                    "drop_count": payload.get("drop_count"),
                    "timestamp": payload.get("ts"),
                },
            )
        except Exception as exc:
            logger.warning("Failed queue_pressure websocket broadcast: %s", exc)

    async def handle_queue_pressure(self, topic: str, payload: dict) -> bool:
        """
        Handle a queue-pressure event message.

        Args:
            topic: MQTT topic string
                   (``kaiser/{kaiser_id}/esp/{esp_id}/system/queue_pressure``)
            payload: Parsed JSON payload dict

        Returns:
            True if the event was processed (even if payload was incomplete),
            False only for unrecoverable errors (topic parse failure or
            unexpected exception).
        """
        try:
            parsed_topic = TopicBuilder.parse_queue_pressure_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse queue_pressure topic: {topic}"
                )
                return False

            esp_id = parsed_topic["esp_id"]
            safe_payload = payload if isinstance(payload, dict) else {}
            event = str(safe_payload.get("event", "unknown"))

            increment_queue_pressure_event(esp_id, event)

            # R1 — AUT-590: Maintain in-memory pressure state for downstream gates.
            if event == "entered_pressure":
                self._esp_under_pressure.add(esp_id)
            elif event == "recovered":
                self._esp_under_pressure.discard(esp_id)

            log_msg = (
                "Queue pressure event: esp_id=%s event=%s fill_level=%s "
                "high_watermark=%s shed_count=%s drop_count=%s"
            )
            log_args = (
                esp_id,
                event,
                safe_payload.get("fill_level"),
                safe_payload.get("high_watermark"),
                safe_payload.get("shed_count"),
                safe_payload.get("drop_count"),
            )
            log_extra = {
                "event_class": "QUEUE_PRESSURE",
                "result": event,
                "classification": "observability",
                "esp_id": esp_id,
                "fill_level": safe_payload.get("fill_level"),
                "high_watermark": safe_payload.get("high_watermark"),
                "shed_count": safe_payload.get("shed_count"),
                "drop_count": safe_payload.get("drop_count"),
            }
            if event == "entered_pressure":
                logger.warning(log_msg, *log_args, extra=log_extra)
            else:
                logger.info(log_msg, *log_args, extra=log_extra)

            await self._persist_transition(esp_id, topic, event, safe_payload)
            await self._broadcast_transition(esp_id, event, safe_payload)
            return True

        except Exception as e:
            logger.error(
                f"Error handling queue_pressure event: {e}",
                exc_info=True,
            )
            return False


# Global handler instance (follows diagnostics_handler pattern)
_handler_instance: Optional[QueuePressureHandler] = None


def get_queue_pressure_handler() -> QueuePressureHandler:
    """
    Get singleton queue-pressure handler instance.

    Returns:
        QueuePressureHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = QueuePressureHandler()
    return _handler_instance


def is_esp_under_pressure(esp_id: str) -> bool:
    """
    Return True if the ESP is currently under FreeRTOS publish-queue pressure.

    Consumed by heartbeat_handler._has_pending_config() and
    sensor_scheduler_service._execute_scheduled_measurement() to gate
    automated server→ESP publishes when the ESP queue is full.
    """
    return esp_id in get_queue_pressure_handler()._esp_under_pressure


async def handle_queue_pressure(topic: str, payload: dict) -> bool:
    """
    Handle queue-pressure message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_queue_pressure_handler()
    return await handler.handle_queue_pressure(topic, payload)
