"""
Zone Service - Business Logic for Zone Assignment Operations

Phase: 7 - Zone Management
Updated: T13-R1 — Zone Consolidation, Subzone Transfer, Audit

Provides:
- Zone assignment via MQTT (with subzone_strategy)
- Zone removal via MQTT
- Zone ACK handling from ESP32
- Zone status queries
- Subzone transfer/copy/reset on zone change
- Zone change audit logging

T13-R1 Changes:
- Zone must exist in zones table before assignment (no more auto-create)
- Archived zones reject new device assignments
- subzone_strategy parameter: 'transfer' | 'copy' | 'reset'
- Audit entries written to device_zone_changes table
"""

import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from ..core import constants
from ..core.logging_config import get_logger
from ..db.models.device_zone_change import DeviceZoneChange
from ..db.models.esp import ESPDevice
from ..db.repositories import ESPRepository
from ..db.repositories.subzone_repo import SubzoneRepository
from ..db.repositories.zone_repo import ZoneRepository
from ..mqtt.publisher import Publisher
from ..mqtt.topics import TopicBuilder
from ..schemas.zone import ZoneAssignResponse, ZoneRemoveResponse

if TYPE_CHECKING:
    from .mqtt_command_bridge import MQTTCommandBridge

logger = get_logger(__name__)


def _is_mock_esp(device_id: str) -> bool:
    """Check if device ID indicates a mock ESP.

    Only matches explicit MOCK_ or ESP_MOCK_ prefixes.
    Wokwi and physical ESPs (e.g. ESP_472204, ESP_00000001) must NOT match.
    """
    return device_id.startswith("ESP_MOCK_") or device_id.startswith("MOCK_")


class ZoneService:
    """
    Zone assignment business logic service.

    Handles zone assignment, removal, and ACK processing.
    T13-R1: Added subzone transfer strategies and zone validation.
    """

    def __init__(
        self,
        esp_repo: ESPRepository,
        publisher: Optional[Publisher] = None,
        command_bridge: Optional["MQTTCommandBridge"] = None,
    ):
        self.esp_repo = esp_repo
        self.publisher = publisher or Publisher()
        self.command_bridge = command_bridge
        self.kaiser_id = constants.get_kaiser_id()

    # =========================================================================
    # Zone Assignment
    # =========================================================================

    async def assign_zone(
        self,
        device_id: str,
        zone_id: str,
        master_zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        subzone_strategy: str = "transfer",
        changed_by: str = "system",
    ) -> ZoneAssignResponse:
        """
        Assign ESP device to a zone via MQTT.

        T13-R1 Flow:
        1. Validate ESP exists
        2. Validate zone exists in zones table and is active
        3. Handle subzone transfer/copy/reset if zone is changing
        4. Update ESP zone fields
        5. Write audit entry to device_zone_changes
        6. Publish MQTT assignment
        7. Sync ZoneContext
        8. Update mock ESP if applicable

        Args:
            device_id: ESP device ID (e.g., "ESP_12AB34CD")
            zone_id: Primary zone identifier (must exist in zones table)
            master_zone_id: Parent master zone ID (optional)
            zone_name: Human-readable zone name (optional)
            subzone_strategy: 'transfer' | 'copy' | 'reset' (default: 'transfer')
            changed_by: Username who initiated the change

        Returns:
            ZoneAssignResponse with assignment status

        Raises:
            ValueError: If ESP device or zone not found, or zone is archived/deleted
        """
        # 1. Find ESP device
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            logger.warning("Zone assignment failed: ESP %s not found", device_id)
            raise ValueError(f"ESP device '{device_id}' not found")

        # 2. Validate zone exists and is active (T13-R1: no more auto-create)
        zone_repo = ZoneRepository(self.esp_repo.session)
        zone = await zone_repo.get_by_zone_id(zone_id)
        if not zone:
            raise ValueError(f"Zone '{zone_id}' not found. Create it first via POST /v1/zones")
        if zone.status != "active":
            raise ValueError(
                f"Zone '{zone_id}' is {zone.status}. Only active zones accept devices."
            )

        # Use zone name from zones table if not provided
        if not zone_name:
            zone_name = zone.name

        # 3. Handle subzone strategy if zone is changing
        old_zone_id = device.zone_id
        subzone_repo = SubzoneRepository(self.esp_repo.session)
        affected_subzones: List[dict] = []

        if old_zone_id and old_zone_id != zone_id:
            affected_subzones = await self._handle_subzone_strategy(
                device_id=device_id,
                old_zone_id=old_zone_id,
                new_zone_id=zone_id,
                strategy=subzone_strategy,
                subzone_repo=subzone_repo,
            )

        # 4. Update ESP record with zone assignment
        device.zone_id = zone_id
        device.master_zone_id = master_zone_id
        device.zone_name = zone_name
        device.kaiser_id = self.kaiser_id

        # Store pending assignment in metadata for tracking
        if device.device_metadata is None:
            device.device_metadata = {}
        device.device_metadata["pending_zone_assignment"] = {
            "zone_id": zone_id,
            "master_zone_id": master_zone_id,
            "zone_name": zone_name,
            "sent_at": int(time.time()),
        }
        flag_modified(device, "device_metadata")

        # 5. Write audit entry (T13-R1: device_zone_changes)
        if old_zone_id != zone_id:
            audit_entry = DeviceZoneChange(
                esp_id=device_id,
                old_zone_id=old_zone_id,
                new_zone_id=zone_id,
                subzone_strategy=subzone_strategy,
                affected_subzones=affected_subzones if affected_subzones else None,
                changed_by=changed_by,
            )
            self.esp_repo.session.add(audit_entry)

        # 6. Build and publish MQTT
        topic = TopicBuilder.build_zone_assign_topic(device_id)
        payload = {
            "zone_id": zone_id,
            "master_zone_id": master_zone_id or "",
            "zone_name": zone_name or "",
            "kaiser_id": self.kaiser_id,
            "timestamp": int(time.time()),
        }

        # Collect transferred subzones for MQTT after zone ACK
        transferred_subzones: List[dict] = []
        if subzone_strategy == "transfer" and affected_subzones:
            transferred_subzones = affected_subzones

        ack_received: Optional[bool] = None
        warning_msg: Optional[str] = None

        if self.command_bridge and not _is_mock_esp(device_id):
            # ACK-gesteuert fuer echte ESPs
            from .mqtt_command_bridge import MQTTACKTimeoutError

            ack_timeout = self.command_bridge.DEFAULT_TIMEOUT
            try:
                zone_ack = await self.command_bridge.send_and_wait_ack(
                    topic=topic,
                    payload=payload,
                    esp_id=device_id,
                    command_type="zone",
                    timeout=ack_timeout,
                )
                mqtt_sent = True
                ack_received = True

                if zone_ack.get("status") == "error":
                    logger.error(
                        "ESP %s rejected zone assignment: %s",
                        device_id,
                        zone_ack.get("message", "unknown error"),
                    )
                    mqtt_sent = False
                elif transferred_subzones:
                    # Subzone-Transfer-MQTT: ERST nach erfolgreichem Zone-ACK
                    await self._send_transferred_subzones(device_id, transferred_subzones)

            except MQTTACKTimeoutError as e:
                logger.warning("Zone assignment ACK timeout for %s: %s", device_id, e)
                mqtt_sent = False
                ack_received = False
                warning_msg = (
                    f"ACK-Timeout: ESP {device_id} hat nicht innerhalb "
                    f"{ack_timeout}s bestätigt. "
                    f"Zone-Zuweisung wurde in DB gespeichert."
                )
        else:
            # Fire-and-forget fuer Mock-ESPs oder wenn keine Bridge vorhanden
            mqtt_sent = self._publish_zone_assignment(topic, payload)

        if mqtt_sent:
            logger.info(
                "Zone assignment sent to %s: zone_id=%s, strategy=%s",
                device_id,
                zone_id,
                subzone_strategy,
            )
        elif ack_received is False:
            logger.warning(
                "Zone assignment ACK timeout for %s (DB updated, ESP may not have confirmed)",
                device_id,
            )
        else:
            logger.warning(
                "Zone assignment MQTT publish failed for %s (DB updated, ESP may be offline)",
                device_id,
            )

        # 7. Sync zone name to ZoneContext (if it exists)
        try:
            from .zone_context_service import ZoneContextService

            zone_ctx_svc = ZoneContextService(self.esp_repo.session)
            await zone_ctx_svc.sync_zone_name(zone_id, zone_name)
        except Exception as e:
            logger.warning("Zone-name sync to ZoneContext failed for %s: %s", zone_id, e)

        # 8. Update MockESPManager if this is a mock device
        if _is_mock_esp(device_id):
            await self._update_mock_esp_zone(device_id, zone_id, zone_name, master_zone_id)

        if mqtt_sent:
            msg = "Zone assignment saved"
        elif ack_received is False:
            msg = "Zone assignment saved (ACK timeout)"
        else:
            msg = "Zone assignment saved (MQTT offline)"

        return ZoneAssignResponse(
            success=True,
            message=msg,
            device_id=device_id,
            zone_id=zone_id,
            master_zone_id=master_zone_id,
            zone_name=zone_name,
            mqtt_topic=topic,
            mqtt_sent=mqtt_sent,
            ack_received=ack_received,
            warning=warning_msg,
        )

    async def remove_zone(
        self,
        device_id: str,
        changed_by: str = "system",
    ) -> ZoneRemoveResponse:
        """
        Remove zone assignment from ESP device.

        Args:
            device_id: ESP device ID
            changed_by: Username who initiated the change

        Returns:
            ZoneRemoveResponse with removal status

        Raises:
            ValueError: If ESP device not found
        """
        # 1. Find ESP device
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            logger.warning("Zone removal failed: ESP %s not found", device_id)
            raise ValueError(f"ESP device '{device_id}' not found")

        # 2. Build MQTT topic
        topic = TopicBuilder.build_zone_assign_topic(device_id)

        # 3. Build empty payload to clear zone
        payload = {
            "zone_id": "",
            "master_zone_id": "",
            "zone_name": "",
            "kaiser_id": self.kaiser_id,
            "timestamp": int(time.time()),
        }

        # Store old zone_id before clearing
        old_zone_id = device.zone_id

        # 4. Update ESP record to clear zone assignment
        device.zone_id = None
        device.master_zone_id = None
        device.zone_name = None

        # Clear pending assignment from metadata
        if device.device_metadata and "pending_zone_assignment" in device.device_metadata:
            del device.device_metadata["pending_zone_assignment"]
            flag_modified(device, "device_metadata")

        # 4a. Cascade-delete subzones for THIS device only
        # (other devices in the same zone keep their subzones)
        subzone_repo = SubzoneRepository(self.esp_repo.session)
        deleted_count = await subzone_repo.delete_all_by_esp(device_id)
        if deleted_count > 0:
            logger.info(
                "Cascade-deleted %d subzone(s) for device %s (was in zone %s)",
                deleted_count,
                device_id,
                old_zone_id or "none",
            )

        # 4b. Write audit entry (T13-R1)
        if old_zone_id:
            audit_entry = DeviceZoneChange(
                esp_id=device_id,
                old_zone_id=old_zone_id,
                new_zone_id="",
                subzone_strategy="reset",
                changed_by=changed_by,
            )
            self.esp_repo.session.add(audit_entry)

        # 5. Publish via MQTT
        ack_received: Optional[bool] = None
        warning_msg: Optional[str] = None
        ack_timeout = self.command_bridge.DEFAULT_TIMEOUT if self.command_bridge else 15.0

        if self.command_bridge and not _is_mock_esp(device_id):
            from .mqtt_command_bridge import MQTTACKTimeoutError

            try:
                ack = await self.command_bridge.send_and_wait_ack(
                    topic=topic,
                    payload=payload,
                    esp_id=device_id,
                    command_type="zone",
                    timeout=ack_timeout,
                )
                mqtt_sent = True
                ack_received = True
                if ack.get("status") == "error":
                    logger.error(
                        "ESP %s rejected zone removal: %s",
                        device_id,
                        ack.get("message"),
                    )
                    mqtt_sent = False
            except MQTTACKTimeoutError as e:
                logger.error("Zone removal ACK timeout for %s: %s", device_id, e)
                mqtt_sent = False
                ack_received = False
                warning_msg = (
                    f"ACK-Timeout: ESP {device_id} hat nicht innerhalb "
                    f"{ack_timeout}s bestätigt. "
                    f"Zone wurde in der DB entfernt."
                )
        else:
            mqtt_sent = self._publish_zone_assignment(topic, payload)

        if mqtt_sent:
            logger.info("Zone removal sent to %s", device_id)
        elif ack_received is False:
            logger.warning(
                "Zone removal ACK timeout for %s (DB updated, ESP may not have confirmed)",
                device_id,
            )
        else:
            logger.warning(
                "Zone removal MQTT publish failed for %s (DB updated, ESP may be offline)",
                device_id,
            )

        # 6. Update MockESPManager if this is a mock device
        if _is_mock_esp(device_id):
            await self._update_mock_esp_zone(device_id, None, None, None)

        if mqtt_sent:
            remove_msg = "Zone removed"
        elif ack_received is False:
            remove_msg = "Zone removed (ACK timeout)"
        else:
            remove_msg = "Zone removed (MQTT offline)"

        return ZoneRemoveResponse(
            success=True,
            message=remove_msg,
            device_id=device_id,
            mqtt_topic=topic,
            mqtt_sent=mqtt_sent,
            ack_received=ack_received,
            warning=warning_msg,
        )

    # =========================================================================
    # Zone ACK Handling
    # =========================================================================

    async def handle_zone_ack(
        self,
        device_id: str,
        status: str,
        zone_id: str,
        master_zone_id: Optional[str] = None,
        timestamp: int = 0,
        message: Optional[str] = None,
    ) -> bool:
        """
        Handle zone assignment acknowledgment from ESP.

        Called by zone_ack_handler when ESP confirms zone assignment.

        Args:
            device_id: ESP device ID
            status: "zone_assigned" or "error"
            zone_id: Assigned zone ID
            master_zone_id: Assigned master zone ID
            timestamp: ACK timestamp (Unix seconds)
            message: Error message (if status == "error")

        Returns:
            True if ACK processed successfully
        """
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            logger.warning("Zone ACK from unknown ESP: %s", device_id)
            return False

        if status == "zone_assigned":
            device.zone_id = zone_id if zone_id else None
            device.master_zone_id = master_zone_id if master_zone_id else None

            if device.device_metadata and "pending_zone_assignment" in device.device_metadata:
                del device.device_metadata["pending_zone_assignment"]
                flag_modified(device, "device_metadata")

            logger.info(
                "Zone assignment confirmed for %s: zone_id=%s, master_zone_id=%s",
                device_id,
                zone_id,
                master_zone_id,
            )
            return True

        elif status == "error":
            logger.error("Zone assignment failed for %s: %s", device_id, message or "Unknown error")
            return False

        else:
            logger.warning("Unknown zone ACK status from %s: %s", device_id, status)
            return False

    # =========================================================================
    # Zone Queries
    # =========================================================================

    async def get_zone_esps(self, zone_id: str) -> list[ESPDevice]:
        """Get all ESPs assigned to a specific zone."""
        return await self.esp_repo.get_by_zone(zone_id)

    async def get_master_zone_esps(self, master_zone_id: str) -> list[ESPDevice]:
        """Get all ESPs in a master zone hierarchy."""
        return await self.esp_repo.get_by_master_zone(master_zone_id)

    async def get_unassigned_esps(self) -> list[ESPDevice]:
        """Get all ESPs without zone assignment."""
        all_esps = await self.esp_repo.get_all()
        return [esp for esp in all_esps if not esp.zone_id]

    # =========================================================================
    # Subzone Transfer Strategies (T13-R1)
    # =========================================================================

    async def _handle_subzone_strategy(
        self,
        device_id: str,
        old_zone_id: str,
        new_zone_id: str,
        strategy: str,
        subzone_repo: SubzoneRepository,
    ) -> List[dict]:
        """
        Handle subzone transfer/copy/reset when device changes zone.

        Args:
            device_id: ESP device_id (String)
            old_zone_id: Previous zone_id
            new_zone_id: New zone_id
            strategy: 'transfer' | 'copy' | 'reset'
            subzone_repo: SubzoneRepository instance

        Returns:
            List of affected subzone dicts for audit logging
        """
        # Get ALL subzones for this ESP — not filtered by zone.
        # Subzones belong to the ESP, not a zone. Filtering by parent_zone_id
        # causes a self-reinforcing orphan bug: after a zone transfer updates
        # parent_zone_id, the next transfer can't find subzones under the old zone.
        subzones = await subzone_repo.get_by_esp(device_id)
        if not subzones:
            return []

        affected: List[dict] = []

        if strategy == "transfer":
            # Move subzones from old zone to new zone
            for sz in subzones:
                affected.append(
                    {
                        "subzone_id": sz.subzone_id,
                        "subzone_name": sz.subzone_name or "",
                        "assigned_gpios": list(sz.assigned_gpios) if sz.assigned_gpios else [],
                        "old_parent": sz.parent_zone_id,
                        "new_parent": new_zone_id,
                        "action": "transferred",
                    }
                )
                sz.parent_zone_id = new_zone_id
            await self.esp_repo.session.flush()
            logger.info(
                "Transferred %d subzone(s) from %s to %s for device %s",
                len(subzones),
                old_zone_id,
                new_zone_id,
                device_id,
            )

        elif strategy == "copy":
            # Clone subzones to new zone (originals stay in old zone)
            for sz in subzones:
                new_id = await self._generate_unique_copy_id(sz.subzone_id, device_id, subzone_repo)
                base_name = (
                    re.sub(r"( \(Copy\))+$", "", sz.subzone_name) if sz.subzone_name else None
                )
                affected.append(
                    {
                        "subzone_id": sz.subzone_id,
                        "copied_as": new_id,
                        "old_parent": sz.parent_zone_id,
                        "new_parent": new_zone_id,
                        "action": "copied",
                    }
                )
                await subzone_repo.create_subzone(
                    esp_id=device_id,
                    subzone_id=new_id,
                    parent_zone_id=new_zone_id,
                    assigned_gpios=list(sz.assigned_gpios) if sz.assigned_gpios else [],
                    subzone_name=f"{base_name} (Copy)" if base_name else None,
                    safe_mode_active=sz.safe_mode_active,
                )
            logger.info(
                "Copied %d subzone(s) to %s for device %s",
                len(subzones),
                new_zone_id,
                device_id,
            )

        elif strategy == "reset":
            # Delete all subzones for this ESP from DB.
            # The ESP does NOT cascade-remove subzones during zone change
            # (only during zone removal). Server DB must be authoritative.
            for sz in subzones:
                affected.append(
                    {
                        "subzone_id": sz.subzone_id,
                        "old_parent": sz.parent_zone_id,
                        "action": "deleted",
                    }
                )
            deleted_count = await subzone_repo.delete_all_by_esp(device_id)
            logger.info(
                "Reset: Deleted %d subzone(s) for device %s (zone change %s → %s)",
                deleted_count,
                device_id,
                old_zone_id,
                new_zone_id,
            )

        else:
            valid = {"transfer", "copy", "reset"}
            raise ValueError(f"Unknown subzone_strategy '{strategy}'. Must be one of: {valid}")

        return affected

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _generate_unique_copy_id(
        self,
        source_subzone_id: str,
        device_id: str,
        subzone_repo: SubzoneRepository,
    ) -> str:
        """
        Generate a unique subzone_id for copy strategy.

        Strips existing _copy/_copy_N suffixes first, then finds the next
        free counter to avoid UniqueConstraint(esp_id, subzone_id) collisions.

        Examples:
            subzone_a         → subzone_a_copy
            subzone_a_copy    → subzone_a_copy_2
            subzone_a_copy_2  → subzone_a_copy_3

        Args:
            source_subzone_id: Original subzone_id to copy from
            device_id: ESP device_id (for uniqueness check)
            subzone_repo: SubzoneRepository instance

        Returns:
            Unique subzone_id string
        """
        # Strip existing _copy or _copy_N suffix to get clean base
        clean_id = re.sub(r"_copy(_\d+)?$", "", source_subzone_id)

        # Try _copy first
        candidate = f"{clean_id}_copy"
        existing = await subzone_repo.get_by_esp_and_subzone(device_id, candidate)
        if not existing:
            return candidate

        # Try _copy_2, _copy_3, ...
        counter = 2
        while counter <= 99:
            candidate = f"{clean_id}_copy_{counter}"
            existing = await subzone_repo.get_by_esp_and_subzone(device_id, candidate)
            if not existing:
                return candidate
            counter += 1

        # Safety fallback: UUID suffix (should never happen in practice)
        from uuid import uuid4

        return f"{clean_id}_copy_{uuid4().hex[:6]}"

    async def _send_transferred_subzones(
        self,
        device_id: str,
        transferred_subzones: List[dict],
    ) -> None:
        """Send subzone/assign MQTT for each transferred subzone after zone ACK.

        Called ONLY after successful zone ACK — the ESP has the new zone in NVS.
        parent_zone_id is sent EMPTY — the firmware automatically uses its current
        zone_id (which is now the new zone after zone/assign was processed).
        This eliminates any race condition.
        """
        from .mqtt_command_bridge import MQTTACKTimeoutError

        for sz in transferred_subzones:
            sz_topic = TopicBuilder.build_subzone_assign_topic(device_id)
            sz_payload = {
                "subzone_id": sz.get("subzone_id", ""),
                "subzone_name": sz.get("subzone_name", ""),
                "parent_zone_id": "",  # EMPTY — firmware sets current zone
                "assigned_gpios": sz.get("assigned_gpios", []),
                "timestamp": int(time.time()),
            }

            # Filter GPIO 0 (I2C placeholder, triggers Error 2506 on ESP)
            sz_payload["assigned_gpios"] = [g for g in sz_payload["assigned_gpios"] if g != 0]

            try:
                sz_ack = await self.command_bridge.send_and_wait_ack(
                    topic=sz_topic,
                    payload=sz_payload,
                    esp_id=device_id,
                    command_type="subzone",
                    timeout=15.0,
                )
                if sz_ack.get("status") == "error":
                    logger.warning(
                        "Subzone %s transfer ACK error for %s: code=%s, msg=%s",
                        sz["subzone_id"],
                        device_id,
                        sz_ack.get("error_code"),
                        sz_ack.get("message"),
                    )
            except MQTTACKTimeoutError as e:
                logger.error(
                    "Subzone %s transfer timeout for %s: %s",
                    sz["subzone_id"],
                    device_id,
                    e,
                )
                # Continue with next subzone — partial success is better than abort

    def _publish_zone_assignment(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Publish zone assignment message via MQTT."""
        import json

        try:
            payload_str = json.dumps(payload)
        except Exception as e:
            logger.error("Failed to serialize zone payload: %s", e)
            return False

        qos = constants.QOS_SENSOR_DATA  # QoS 1
        success = self.publisher.publish_raw(topic, payload_str, qos=qos)

        if success:
            logger.debug("Zone assignment published to %s", topic)
        else:
            logger.error("Zone assignment publish failed to %s", topic)

        return success

    async def _update_mock_esp_zone(
        self,
        device_id: str,
        zone_id: Optional[str],
        zone_name: Optional[str],
        master_zone_id: Optional[str],
    ) -> None:
        """Update zone in SimulationScheduler for mock devices."""
        try:
            from .simulation import get_simulation_scheduler

            scheduler = get_simulation_scheduler()

            if scheduler.is_mock_active(device_id):
                scheduler.update_zone(
                    esp_id=device_id,
                    zone_id=zone_id or "",
                    kaiser_id=master_zone_id or "god",
                )
                logger.debug("Updated SimulationScheduler zone for %s", device_id)
            else:
                logger.debug(
                    "Mock ESP %s not running in SimulationScheduler "
                    "(may be stopped or server restarted)",
                    device_id,
                )
        except Exception as e:
            logger.warning("Failed to update SimulationScheduler for %s: %s", device_id, e)
