"""
Subzone ACK Handler

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Handles subzone assignment acknowledgments from ESP32 devices.

Topic Pattern: kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack

ACK Payload:
{
    "esp_id": "ESP_AB12CD",
    "status": "subzone_assigned" | "subzone_removed" | "error",
    "subzone_id": "irrigation_section_A",
    "ts": 1734523800,
    "error_code": 2501,  // optional, only on error
    "message": "GPIO conflict"  // optional, only on error
}

References:
- El Trabajante/docs/system-flows/09-subzone-management-flow.md
- El Servador/god_kaiser_server/src/mqtt/handlers/zone_ack_handler.py (Pattern)
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from pydantic import ValidationError

from ...core.logging_config import get_logger
from ...core.metrics import increment_mqtt_ack_reason_code
from ...db.session import resilient_session
from ...db.repositories import ESPRepository
from ...schemas.subzone import SubzoneAckPayload
from ...services.subzone_service import SubzoneService
from ...websocket.manager import WebSocketManager
from ..topics import TopicBuilder

if TYPE_CHECKING:
    from ...services.mqtt_command_bridge import MQTTCommandBridge

from ...services.mqtt_command_bridge import extract_ack_correlation_id

logger = get_logger(__name__)

# MQTTCommandBridge reference — set via set_command_bridge() from main.py
_command_bridge: Optional["MQTTCommandBridge"] = None


def set_command_bridge(bridge: "MQTTCommandBridge") -> None:
    """Set the MQTTCommandBridge reference. Called from main.py during startup."""
    global _command_bridge
    _command_bridge = bridge


class SubzoneAckHandler:
    """
    Handler for subzone assignment ACK messages from ESP devices.

    Processes subzone assignment/removal confirmations and broadcasts
    updates to connected WebSocket clients.
    """

    def __init__(self):
        """Initialize handler with WebSocket manager."""
        self.ws_manager = WebSocketManager()

    async def handle(self, topic: str, payload: dict) -> bool:
        """
        Handle incoming subzone ACK message.

        Args:
            topic: MQTT topic (kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack)
            payload: Parsed JSON payload dict (already parsed by subscriber)

        Returns:
            True if processed successfully, False otherwise
        """
        # Parse topic to extract ESP ID
        topic_info = TopicBuilder.parse_subzone_ack_topic(topic)
        if not topic_info:
            logger.warning(f"Could not parse subzone ACK topic: {topic}")
            return False

        esp_id = topic_info.get("esp_id")
        if not esp_id:
            logger.warning(f"No esp_id in subzone ACK topic: {topic}")
            return False

        # Validate payload (payload is already a dict from subscriber)
        ack_payload = self._validate_payload(payload)
        if not ack_payload:
            logger.warning(f"Subzone ACK payload validation failed from {esp_id}")
            return False

        logger.info(
            f"Received subzone ACK from {esp_id}: "
            f"status={ack_payload.status}, subzone_id={ack_payload.subzone_id}"
        )
        if ack_payload.reason_code:
            increment_mqtt_ack_reason_code("subzone", str(ack_payload.reason_code))

        # Process ACK with database session
        async with resilient_session() as session:
            esp_repo = ESPRepository(session)
            service = SubzoneService(esp_repo=esp_repo, session=session)

            success = await service.handle_subzone_ack(
                device_id=ack_payload.esp_id,
                status=ack_payload.status,
                subzone_id=ack_payload.subzone_id,
                timestamp=ack_payload.timestamp,
                error_code=ack_payload.error_code,
                message=ack_payload.message,
            )

            if success:
                await session.commit()

            # Resolve pending ACK Future for ALL statuses (including error)
            # so the caller gets immediate feedback instead of waiting for timeout
            if _command_bridge:
                ack_cid = extract_ack_correlation_id(payload)
                _command_bridge.resolve_ack(
                    ack_data={
                        "status": ack_payload.status,
                        "subzone_id": ack_payload.subzone_id,
                        "esp_id": esp_id,
                        "ts": ack_payload.timestamp,
                        "error_code": getattr(ack_payload, "error_code", None),
                        "correlation_id": ack_cid,
                        "reason_code": ack_payload.reason_code,
                    },
                    esp_id=esp_id,
                    command_type="subzone",
                )

            if success:
                # Broadcast to WebSocket clients
                await self._broadcast_subzone_update(ack_payload)
                return True
            else:
                logger.warning(f"Subzone ACK processing failed for {esp_id}")
                return False

    def _validate_payload(self, payload_data: Dict[str, Any]) -> Optional[SubzoneAckPayload]:
        """
        Validate payload against schema.

        Args:
            payload_data: Parsed JSON dict

        Returns:
            SubzoneAckPayload or None
        """
        try:
            return SubzoneAckPayload.model_validate(payload_data)
        except ValidationError as e:
            logger.error(f"Subzone ACK validation error: {e}")
            return None

    async def _broadcast_subzone_update(self, ack_payload: SubzoneAckPayload) -> None:
        """
        Broadcast subzone update to WebSocket clients.

        Args:
            ack_payload: Validated ACK payload
        """
        # WP9-F23: Unified WebSocket broadcast API (matches zone_ack_handler pattern)
        event_data = {
            "esp_id": ack_payload.esp_id,
            "subzone_id": ack_payload.subzone_id,
            "status": ack_payload.status,
            "timestamp": ack_payload.timestamp,
        }

        # Add error info if present
        if ack_payload.error_code is not None:
            event_data["error_code"] = ack_payload.error_code
            event_data["message"] = ack_payload.message
        if ack_payload.reason_code:
            event_data["reason_code"] = ack_payload.reason_code

        # Use broadcast() instead of broadcast_thread_safe() for consistency
        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast("subzone_assignment", event_data)
        logger.debug(f"Broadcasted subzone_assignment event for {ack_payload.esp_id}")


# =============================================================================
# Module-level handler function (for MQTT subscriber registration)
# =============================================================================

# Module-level instance for handler registration (matches zone_ack_handler pattern)
_handler = SubzoneAckHandler()


async def handle_subzone_ack(topic: str, payload: dict) -> bool:
    """
    Module-level handler function for MQTT subscriber registration.

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if processed successfully
    """
    return await _handler.handle(topic, payload)
