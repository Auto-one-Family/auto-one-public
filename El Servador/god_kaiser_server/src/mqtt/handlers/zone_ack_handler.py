"""
MQTT Handler: Zone Assignment Acknowledgment Messages

Processes zone ACK messages from ESP32 devices:
- Confirms zone assignment was saved to ESP NVS
- Updates ESP device record in database
- Broadcasts WebSocket event for frontend update

Zone assignment flow:
1. Server publishes zone/assign to ESP
2. ESP saves zone config to NVS
3. ESP sends zone/ack to confirm
4. This handler processes ACK and broadcasts to frontend

Topic: kaiser/{kaiser_id}/esp/{esp_id}/zone/ack

Payload (from ESP32):
{
    "esp_id": "ESP_12AB34CD",
    "status": "zone_assigned" | "error",
    "zone_id": "greenhouse_zone_1",
    "master_zone_id": "greenhouse_master",
    "ts": 1734523800,
    "message": "..." (only on error)
}

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from ...core.error_codes import (
    ConfigErrorCode,
    ValidationErrorCode,
)
from ...core.logging_config import get_logger
from ...core.metrics import increment_mqtt_ack_reason_code
from ...db.repositories import ESPRepository
from ...db.repositories.zone_repo import ZoneRepository
from ...db.session import resilient_session
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


class ZoneAckHandler:
    """
    Handles incoming zone assignment acknowledgment messages from ESP32 devices.

    Flow:
    1. Parse topic -> extract esp_id
    2. Validate payload structure
    3. Check if ESP exists in DB
    4. Update ESP zone fields based on ACK status
    5. Broadcast WebSocket event to frontend
    """

    async def handle_zone_ack(self, topic: str, payload: dict) -> bool:
        """
        Handle zone ACK message from ESP.

        Expected topic: kaiser/{kaiser_id}/esp/{esp_id}/zone/ack

        Expected payload (from ESP32):
        {
            "esp_id": "ESP_12AB34CD",
            "status": "zone_assigned" | "error",
            "zone_id": "greenhouse_zone_1",
            "master_zone_id": "greenhouse_master",
            "ts": 1734523800,
            "message": "..." (optional, only on error)
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_zone_ack_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse zone/ack topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]

            logger.debug(f"Processing zone ACK: esp_id={esp_id_str}")

            # Step 2: Validate payload
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid zone/ack payload from {esp_id_str}: "
                    f"{validation_result['error']}"
                )
                return False

            # Extract payload fields
            status = payload.get("status")
            zone_id = payload.get("zone_id", "")
            master_zone_id = payload.get("master_zone_id", "")
            timestamp = payload.get("ts", 0)
            error_message = payload.get("message", "")
            reason_code = payload.get("reason_code")
            if reason_code:
                increment_mqtt_ack_reason_code("zone", str(reason_code))
                logger.info(
                    "zone/ack reason_code=%s esp_id=%s status=%s correlation_id=%s",
                    reason_code,
                    esp_id_str,
                    status,
                    extract_ack_correlation_id(payload),
                )

            # Step 3: Process ACK via database session
            async with resilient_session() as session:
                esp_repo = ESPRepository(session)

                # Step 4: Get ESP device
                device = await esp_repo.get_by_device_id(esp_id_str)
                if not device:
                    logger.warning(
                        f"[{ConfigErrorCode.ESP_DEVICE_NOT_FOUND}] "
                        f"Zone ACK from unknown device: {esp_id_str}"
                    )
                    return False

                # Step 4.5: Validate zone exists before writing FK
                # Prevents ForeignKeyViolationError on server restart when ESP
                # sends ACK with a zone_id that no longer exists in DB
                if status == "zone_assigned" and zone_id:
                    zone_repo = ZoneRepository(session)
                    zone = await zone_repo.get_by_zone_id(zone_id)
                    if zone is None:
                        logger.warning(
                            "Zone ACK from %s: zone '%s' not found in DB. "
                            "Ignoring — will be resolved on next heartbeat cycle.",
                            esp_id_str,
                            zone_id,
                        )
                        return False

                # Step 5: Update ESP based on ACK status
                if status == "zone_assigned":
                    # Update zone fields
                    device.zone_id = zone_id if zone_id else None
                    device.master_zone_id = master_zone_id if master_zone_id else None

                    # Clear pending assignment from metadata
                    if (
                        device.device_metadata
                        and "pending_zone_assignment" in device.device_metadata
                    ):
                        del device.device_metadata["pending_zone_assignment"]
                        # SQLAlchemy doesn't detect in-place JSON dict mutations
                        flag_modified(device, "device_metadata")

                    logger.info(
                        f"Zone assignment confirmed for {esp_id_str}: "
                        f"zone_id={zone_id}, master_zone_id={master_zone_id}"
                    )

                elif status == "zone_removed":
                    # WP1-Fix6: Handle zone removal confirmation
                    device.zone_id = None
                    device.master_zone_id = None
                    device.zone_name = None
                    # device.kaiser_id remains unchanged (by design, F24)

                    # Clear pending assignment from metadata
                    if (
                        device.device_metadata
                        and "pending_zone_assignment" in device.device_metadata
                    ):
                        del device.device_metadata["pending_zone_assignment"]
                        # SQLAlchemy doesn't detect in-place JSON dict mutations
                        flag_modified(device, "device_metadata")

                    logger.info(f"Zone removal confirmed for {esp_id_str}")

                elif status == "error":
                    logger.error(f"Zone assignment failed for {esp_id_str}: {error_message}")
                    # Keep pending assignment for retry

                else:
                    logger.warning(f"Unknown zone ACK status from {esp_id_str}: {status}")

                try:
                    await session.commit()
                except IntegrityError as e:
                    await session.rollback()
                    # INV-1a/Fix4: Check SQLSTATE code for ForeignKeyViolation
                    # instead of fragile string matching. SQLSTATE 23503 is
                    # the standard code for foreign_key_violation, portable
                    # across asyncpg and psycopg2.
                    orig = getattr(e, "orig", None)
                    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
                    if sqlstate == "23503":
                        logger.warning(
                            "Zone ACK commit failed for %s (FK violation, zone_id='%s'). "
                            "Ignoring — will be resolved on next heartbeat cycle.",
                            esp_id_str,
                            zone_id,
                        )
                        return False
                    raise

                # Step 5.1: Resolve pending ACK Future (if any)
                if _command_bridge:
                    ack_cid = extract_ack_correlation_id(payload)
                    resolved = _command_bridge.resolve_ack(
                        ack_data={
                            "status": status,
                            "zone_id": zone_id,
                            "master_zone_id": master_zone_id,
                            "esp_id": esp_id_str,
                            "ts": timestamp,
                            "correlation_id": ack_cid,
                            "reason_code": reason_code,
                        },
                        esp_id=esp_id_str,
                        command_type="zone",
                    )
                    if resolved:
                        logger.info(
                            "zone/ack resolved for %s (correlation_id=%s)",
                            esp_id_str,
                            ack_cid or "none",
                        )
                    else:
                        logger.debug(
                            "zone/ack from %s: no pending Future (unsolicited ACK)",
                            esp_id_str,
                        )

                # Step 6: Broadcast WebSocket event to frontend
                await self._broadcast_zone_update(
                    esp_id=esp_id_str,
                    status=status,
                    zone_id=zone_id,
                    master_zone_id=master_zone_id,
                    zone_name=device.zone_name,  # WP4: Add zone_name for frontend
                    kaiser_id=device.kaiser_id,  # WP4: Add kaiser_id for frontend
                    timestamp=timestamp,
                    message=error_message,
                    reason_code=reason_code,
                )

                return True

        except Exception as e:
            logger.error(f"Error processing zone ACK: {e}", exc_info=True)
            return False

    def _validate_payload(self, payload: dict) -> Dict[str, Any]:
        """
        Validate zone ACK payload structure.

        Required fields:
        - status: "zone_assigned" or "error"
        - ts: Unix timestamp

        Optional fields:
        - esp_id: Device ID (also extracted from topic)
        - zone_id: Assigned zone
        - master_zone_id: Assigned master zone
        - message: Error message (if status == "error")

        Args:
            payload: Raw payload dict

        Returns:
            {
                "valid": bool,
                "error": str | None,
                "error_code": int | None
            }
        """
        # Check for required fields
        if "status" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: status",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "ts" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: ts",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # Validate status value (WP1-Fix7: added "zone_removed")
        status = payload.get("status")
        if status not in ("zone_assigned", "zone_removed", "error"):
            return {
                "valid": False,
                "error": f"Invalid status value: {status}",
                "error_code": ValidationErrorCode.INVALID_PAYLOAD_FORMAT,
            }

        # Validate timestamp
        ts = payload.get("ts")
        if not isinstance(ts, (int, float)):
            return {
                "valid": False,
                "error": f"Invalid timestamp type: {type(ts).__name__}",
                "error_code": ValidationErrorCode.INVALID_PAYLOAD_FORMAT,
            }

        return {"valid": True, "error": None, "error_code": None}

    async def _broadcast_zone_update(
        self,
        esp_id: str,
        status: str,
        zone_id: str,
        master_zone_id: str,
        zone_name: str,
        kaiser_id: str,
        timestamp: int,
        message: str,
        reason_code: Optional[str] = None,
    ) -> None:
        """
        Broadcast zone assignment update via WebSocket.

        Args:
            esp_id: ESP device ID
            status: "zone_assigned", "zone_removed", or "error"
            zone_id: Assigned zone ID
            master_zone_id: Assigned master zone ID
            zone_name: Zone name (WP4: added for frontend display)
            kaiser_id: Kaiser ID (WP4: added for frontend display)
            timestamp: ACK timestamp
            message: Error message (if any)
        """
        try:
            ws_manager = await WebSocketManager.get_instance()

            event_data = {
                "esp_id": esp_id,
                "status": status,
                "zone_id": zone_id,
                "master_zone_id": master_zone_id,
                "zone_name": zone_name,  # WP4: Added zone_name
                "kaiser_id": kaiser_id,  # WP4: Added kaiser_id
                "timestamp": timestamp,
            }

            if message:
                event_data["message"] = message
            if reason_code:
                event_data["reason_code"] = reason_code

            await ws_manager.broadcast("zone_assignment", event_data)

            logger.debug(f"Broadcasted zone_assignment event for {esp_id}")

        except Exception as e:
            logger.error(f"Failed to broadcast zone update: {e}")


# Module-level instance for handler registration
_handler = ZoneAckHandler()


async def handle_zone_ack(topic: str, payload: dict) -> bool:
    """
    Module-level handler function for MQTT subscriber registration.

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if processed successfully
    """
    return await _handler.handle_zone_ack(topic, payload)
