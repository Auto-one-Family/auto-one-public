"""
Subzone Service - Business Logic for Subzone Operations

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Provides:
- Subzone assignment via MQTT
- Subzone removal via MQTT
- Subzone ACK handling from ESP32
- Safe-mode control for subzones
- Subzone queries

This service provides shared business logic used by:
- REST API endpoints (api/v1/subzone.py)
- MQTT handlers (mqtt/handlers/subzone_ack_handler.py)

MQTT Protocol:
- Assignment: kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign
- Removal: kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove
- ACK: kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack
- Safe: kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe

References:
- El Trabajante/docs/system-flows/09-subzone-management-flow.md
- .claude/CLAUDE_SERVER.md
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core import constants
from ..core.logging_config import get_logger
from ..db.models.subzone import SubzoneConfig
from ..db.repositories import ESPRepository
from ..mqtt.publisher import Publisher
from ..mqtt.topics import TopicBuilder
from ..schemas.subzone import (
    SafeModeResponse,
    SubzoneAssignResponse,
    SubzoneInfo,
    SubzoneListResponse,
    SubzoneRemoveResponse,
)

logger = get_logger(__name__)


def _is_mock_esp(device_id: str) -> bool:
    """Check if device ID indicates a mock ESP (consistent with zone_service).

    Only matches explicit MOCK_ or ESP_MOCK_ prefixes.
    Wokwi and physical ESPs (e.g. ESP_472204, ESP_00000001) must NOT match.
    """
    return device_id.startswith("ESP_MOCK_") or device_id.startswith("MOCK_")


class SubzoneService:
    """
    Subzone assignment and management business logic service.

    Handles subzone assignment, removal, safe-mode control, and ACK processing.
    Follows the same patterns as ZoneService for consistency.
    """

    def __init__(
        self,
        esp_repo: ESPRepository,
        session: Optional[AsyncSession] = None,
        publisher: Optional[Publisher] = None,
    ):
        """
        Initialize SubzoneService.

        Args:
            esp_repo: ESP repository for database operations
            session: SQLAlchemy async session (for subzone queries)
            publisher: MQTT publisher (optional, created if not provided)
        """
        self.esp_repo = esp_repo
        self.session = session or esp_repo.session
        self.publisher = publisher or Publisher()
        # Get kaiser_id from constants helper
        self.kaiser_id = constants.get_kaiser_id()

    # =========================================================================
    # Subzone Assignment
    # =========================================================================

    async def assign_subzone(
        self,
        device_id: str,
        subzone_id: str,
        assigned_gpios: List[int],
        subzone_name: Optional[str] = None,
        parent_zone_id: Optional[str] = None,
        safe_mode_active: bool = True,
    ) -> SubzoneAssignResponse:
        """
        Assign GPIO pins to a subzone via MQTT.

        Flow:
        1. Validate ESP exists and has zone assigned
        2. Build and publish MQTT subzone assignment message
        3. Store pending assignment in DB (confirmed on ACK)
        4. Return response (actual confirmation comes via subzone/ack topic)

        Args:
            device_id: ESP device ID (e.g., "ESP_AB12CD")
            subzone_id: Unique subzone identifier
            assigned_gpios: List of GPIO pin numbers
            subzone_name: Human-readable subzone name (optional)
            parent_zone_id: Parent zone ID (optional, defaults to ESP's zone_id)
            safe_mode_active: Whether subzone starts in safe-mode (default: True)

        Returns:
            SubzoneAssignResponse with assignment status

        Raises:
            ValueError: If ESP device not found or has no zone assigned
        """
        # 1. Find ESP device
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            logger.warning(f"Subzone assignment failed: ESP {device_id} not found")
            raise ValueError(f"ESP device '{device_id}' not found")

        # 2. Validate zone is assigned (CRITICAL - Subzone requires Zone)
        if not device.zone_id:
            logger.warning(f"Subzone assignment failed: ESP {device_id} has no zone assigned")
            raise ValueError(
                f"ESP device '{device_id}' has no zone assigned. "
                "Assign a zone before creating subzones."
            )

        # 3. Use ESP's zone_id if parent_zone_id not provided
        actual_parent_zone_id = parent_zone_id or device.zone_id

        # 4. Validate parent_zone_id matches ESP's zone_id
        if actual_parent_zone_id != device.zone_id:
            logger.warning(
                f"Subzone assignment: parent_zone_id '{actual_parent_zone_id}' "
                f"doesn't match ESP zone_id '{device.zone_id}'"
            )
            raise ValueError(
                f"parent_zone_id '{actual_parent_zone_id}' must match "
                f"ESP's zone_id '{device.zone_id}'"
            )

        # 4b. Mock devices: DB-only, no MQTT (no hardware to acknowledge)
        if _is_mock_esp(device_id):
            await self._upsert_subzone_config(
                device_id=device_id,
                subzone_id=subzone_id,
                subzone_name=subzone_name,
                parent_zone_id=actual_parent_zone_id,
                assigned_gpios=assigned_gpios,
                safe_mode_active=safe_mode_active,
            )
            logger.info(
                f"Subzone assignment (mock) for {device_id}: "
                f"subzone_id={subzone_id}, gpios={assigned_gpios}"
            )
            return SubzoneAssignResponse(
                success=True,
                message="Subzone assigned (mock device, no MQTT)",
                device_id=device_id,
                subzone_id=subzone_id,
                assigned_gpios=assigned_gpios,
                mqtt_topic="",
                mqtt_sent=False,
            )

        # 5. Build MQTT topic
        topic = TopicBuilder.build_subzone_assign_topic(device_id)

        # 6. Build payload (matches ESP32 expectations from system_types.h)
        # Filter GPIO 0 (I2C placeholder) from MQTT payload — triggers Error 2506 on ESP.
        # GPIO 0 stays in DB (assigned_gpios) for server-side I2C sensor resolution.
        mqtt_gpios = [g for g in assigned_gpios if g != 0]
        if len(mqtt_gpios) != len(assigned_gpios):
            logger.debug(
                "Filtered GPIO 0 (I2C placeholder) from subzone/assign payload for %s",
                device_id,
            )
        payload = {
            "subzone_id": subzone_id,
            "subzone_name": subzone_name or "",
            "parent_zone_id": actual_parent_zone_id,
            "assigned_gpios": mqtt_gpios,
            "safe_mode_active": safe_mode_active,
            "sensor_count": 0,  # Will be updated by ESP
            "actuator_count": 0,  # Will be updated by ESP
            "timestamp": int(time.time()),
        }

        # 7. Publish via MQTT (QoS 1 - At least once)
        mqtt_sent = self._publish_subzone_message(topic, payload)

        if mqtt_sent:
            # 8. Create or update pending subzone in DB
            await self._upsert_subzone_config(
                device_id=device_id,
                subzone_id=subzone_id,
                subzone_name=subzone_name,
                parent_zone_id=actual_parent_zone_id,
                assigned_gpios=assigned_gpios,
                safe_mode_active=safe_mode_active,
            )

            logger.info(
                f"Subzone assignment sent to {device_id}: "
                f"subzone_id={subzone_id}, gpios={assigned_gpios}"
            )
        else:
            logger.error(f"Subzone assignment MQTT publish failed for {device_id}")

        return SubzoneAssignResponse(
            success=mqtt_sent,
            message=("Subzone assignment sent to ESP" if mqtt_sent else "MQTT publish failed"),
            device_id=device_id,
            subzone_id=subzone_id,
            assigned_gpios=assigned_gpios,
            mqtt_topic=topic,
            mqtt_sent=mqtt_sent,
        )

    async def remove_subzone(
        self,
        device_id: str,
        subzone_id: str,
        reason: str = "manual",
    ) -> SubzoneRemoveResponse:
        """
        Remove a subzone from ESP device.

        Args:
            device_id: ESP device ID
            subzone_id: Subzone to remove
            reason: Reason for removal

        Returns:
            SubzoneRemoveResponse with removal status
        """
        # 1. Find ESP device
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            raise ValueError(f"ESP device '{device_id}' not found")

        # 1a. Check subzone exists (return 404 on second DELETE — not idempotent 200)
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        if not result.scalar_one_or_none():
            raise ValueError(f"Subzone '{subzone_id}' not found on device '{device_id}'")

        # 1b. Mock devices: DB-only, no MQTT
        if _is_mock_esp(device_id):
            await self._delete_subzone_config(device_id, subzone_id)
            logger.info(f"Subzone removal (mock) for {device_id}: subzone_id={subzone_id}")
            return SubzoneRemoveResponse(
                success=True,
                message="Subzone removed (mock device, no MQTT)",
                device_id=device_id,
                subzone_id=subzone_id,
                mqtt_topic="",
                mqtt_sent=False,
            )

        # 2. DB-DELETE first (DB is authoritative — before MQTT)
        await self._delete_subzone_config(device_id, subzone_id)

        # 3. Build MQTT topic
        topic = TopicBuilder.build_subzone_remove_topic(device_id)

        # 4. Build payload
        payload = {
            "subzone_id": subzone_id,
            "reason": reason,
            "timestamp": int(time.time()),
        }

        # 5. Publish via MQTT (fire-and-forget — ESP will sync on reconnect if this fails)
        mqtt_sent = self._publish_subzone_message(topic, payload)

        if mqtt_sent:
            logger.info(f"Subzone removed from DB and ESP notified: {device_id}/{subzone_id}")
        else:
            logger.warning(
                f"Subzone removed from DB but MQTT failed for {device_id}/{subzone_id} "
                f"(ESP will sync on next reconnect)"
            )

        return SubzoneRemoveResponse(
            success=True,  # DB deletion succeeded; MQTT is fire-and-forget
            message=(
                "Subzone removed; ESP notified"
                if mqtt_sent
                else "Subzone removed from DB; ESP will sync on reconnect"
            ),
            device_id=device_id,
            subzone_id=subzone_id,
            mqtt_topic=topic,
            mqtt_sent=mqtt_sent,
        )

    # =========================================================================
    # Safe-Mode Control
    # =========================================================================

    async def enable_safe_mode(
        self,
        device_id: str,
        subzone_id: str,
        reason: str = "manual",
    ) -> SafeModeResponse:
        """
        Enable safe-mode for a subzone.

        All GPIO pins in the subzone will be set to INPUT_PULLUP.

        Args:
            device_id: ESP device ID
            subzone_id: Subzone to put in safe-mode
            reason: Reason for safe-mode activation

        Returns:
            SafeModeResponse with result
        """
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            raise ValueError(f"ESP device '{device_id}' not found")

        if _is_mock_esp(device_id):
            await self._update_subzone_safe_mode(device_id, subzone_id, active=True)
            logger.info(f"Safe-mode ENABLE (mock) for {device_id}/{subzone_id}")
            return SafeModeResponse(
                success=True,
                message="Safe-mode enabled (mock device, no MQTT)",
                device_id=device_id,
                subzone_id=subzone_id,
                safe_mode_active=True,
                mqtt_sent=False,
            )

        topic = TopicBuilder.build_subzone_safe_topic(device_id)
        payload = {
            "subzone_id": subzone_id,
            "action": "enable",
            "reason": reason,
            "timestamp": int(time.time()),
        }

        mqtt_sent = self._publish_subzone_message(topic, payload)

        return SafeModeResponse(
            success=mqtt_sent,
            message="Safe-mode enable sent to ESP" if mqtt_sent else "MQTT publish failed",
            device_id=device_id,
            subzone_id=subzone_id,
            safe_mode_active=True,
            mqtt_sent=mqtt_sent,
        )

    async def disable_safe_mode(
        self,
        device_id: str,
        subzone_id: str,
        reason: str = "manual",
    ) -> SafeModeResponse:
        """
        Disable safe-mode for a subzone.

        WARNING: This allows actuators to be controlled. Use with caution.

        Args:
            device_id: ESP device ID
            subzone_id: Subzone to take out of safe-mode
            reason: Reason for safe-mode deactivation

        Returns:
            SafeModeResponse with result
        """
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            raise ValueError(f"ESP device '{device_id}' not found")

        if _is_mock_esp(device_id):
            await self._update_subzone_safe_mode(device_id, subzone_id, active=False)
            logger.info(f"Safe-mode DISABLE (mock) for {device_id}/{subzone_id}")
            return SafeModeResponse(
                success=True,
                message="Safe-mode disabled (mock device, no MQTT)",
                device_id=device_id,
                subzone_id=subzone_id,
                safe_mode_active=False,
                mqtt_sent=False,
            )

        topic = TopicBuilder.build_subzone_safe_topic(device_id)
        payload = {
            "subzone_id": subzone_id,
            "action": "disable",
            "reason": reason,
            "timestamp": int(time.time()),
        }

        mqtt_sent = self._publish_subzone_message(topic, payload)

        return SafeModeResponse(
            success=mqtt_sent,
            message="Safe-mode disable sent to ESP" if mqtt_sent else "MQTT publish failed",
            device_id=device_id,
            subzone_id=subzone_id,
            safe_mode_active=False,
            mqtt_sent=mqtt_sent,
        )

    # =========================================================================
    # Subzone ACK Handling
    # =========================================================================

    async def handle_subzone_ack(
        self,
        device_id: str,
        status: str,
        subzone_id: str,
        timestamp: int = 0,
        error_code: Optional[int] = None,
        message: Optional[str] = None,
    ) -> bool:
        """
        Handle subzone assignment acknowledgment from ESP.

        Called by subzone_ack_handler when ESP confirms subzone assignment.

        Args:
            device_id: ESP device ID
            status: "subzone_assigned", "subzone_removed", or "error"
            subzone_id: Processed subzone ID
            timestamp: ACK timestamp (Unix seconds)
            error_code: Error code (if status == "error")
            message: Error message (if status == "error")

        Returns:
            True if ACK processed successfully
        """
        if status == "subzone_assigned":
            # Update subzone record to confirm assignment
            await self._confirm_subzone_assignment(device_id, subzone_id)
            logger.info(f"Subzone assignment confirmed for {device_id}: subzone_id={subzone_id}")
            return True

        elif status == "subzone_removed":
            # Delete subzone record (no-op if already deleted by remove_subzone())
            await self._delete_subzone_config(device_id, subzone_id)
            logger.info(f"Subzone removal confirmed for {device_id}: subzone_id={subzone_id}")
            return True

        elif status == "error":
            logger.warning(
                f"Subzone operation failed for {device_id}: "
                f"subzone_id={subzone_id}, error_code={error_code}, message={message}"
            )
            # Keep the record for retry, but mark as failed
            return False

        else:
            logger.warning(f"Unknown subzone ACK status from {device_id}: {status}")
            return False

    # =========================================================================
    # Subzone Queries
    # =========================================================================

    async def get_esp_subzones(self, device_id: str) -> SubzoneListResponse:
        """
        Get all subzones for an ESP device.

        Args:
            device_id: ESP device ID

        Returns:
            SubzoneListResponse with all subzones
        """
        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            raise ValueError(f"ESP device '{device_id}' not found")

        # Query subzones from DB
        result = await self.session.execute(
            select(SubzoneConfig).where(SubzoneConfig.esp_id == device_id)
        )
        subzone_configs = result.scalars().all()

        def _safe_custom_data(sc: SubzoneConfig) -> dict:
            try:
                val = getattr(sc, "custom_data", None)
                if val is None:
                    return {}
                return dict(val) if isinstance(val, dict) else {}
            except (TypeError, AttributeError):
                return {}

        subzones = [
            SubzoneInfo(
                subzone_id=sc.subzone_id,
                subzone_name=sc.subzone_name,
                parent_zone_id=sc.parent_zone_id or "",
                assigned_gpios=sc.assigned_gpios or [],
                safe_mode_active=bool(sc.safe_mode_active),
                sensor_count=int(sc.sensor_count) if sc.sensor_count is not None else 0,
                actuator_count=int(sc.actuator_count) if sc.actuator_count is not None else 0,
                custom_data=_safe_custom_data(sc),
                created_at=sc.created_at.isoformat() if sc.created_at else None,
            )
            for sc in subzone_configs
        ]

        return SubzoneListResponse(
            success=True,
            message=f"Found {len(subzones)} subzones",
            device_id=device_id,
            zone_id=device.zone_id or None,
            subzones=subzones,
            total_count=len(subzones),
        )

    async def get_subzone(self, device_id: str, subzone_id: str) -> Optional[SubzoneInfo]:
        """
        Get a specific subzone.

        Args:
            device_id: ESP device ID
            subzone_id: Subzone ID

        Returns:
            SubzoneInfo or None if not found
        """
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        sc = result.scalar_one_or_none()

        if not sc:
            return None

        return SubzoneInfo(
            subzone_id=sc.subzone_id,
            subzone_name=sc.subzone_name,
            parent_zone_id=sc.parent_zone_id or "",
            assigned_gpios=sc.assigned_gpios or [],
            safe_mode_active=bool(sc.safe_mode_active),
            sensor_count=int(sc.sensor_count) if sc.sensor_count is not None else 0,
            actuator_count=int(sc.actuator_count) if sc.actuator_count is not None else 0,
            custom_data=dict(sc.custom_data) if getattr(sc, "custom_data", None) else {},
            created_at=sc.created_at.isoformat() if sc.created_at else None,
        )

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _publish_subzone_message(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Publish subzone message via MQTT.

        Args:
            topic: MQTT topic
            payload: Message payload

        Returns:
            True if publish successful
        """
        try:
            payload_str = json.dumps(payload)
        except Exception as e:
            logger.error(f"Failed to serialize subzone payload: {e}")
            return False

        # Use QoS 1 (At least once) for subzone operations
        qos = constants.QOS_SENSOR_DATA  # QoS 1

        success = self.publisher.publish_raw(topic, payload_str, qos=qos)

        if success:
            logger.debug(f"Subzone message published to {topic}")
        else:
            logger.error(f"Subzone message publish failed to {topic}")

        return success

    async def _upsert_subzone_config(
        self,
        device_id: str,
        subzone_id: str,
        subzone_name: Optional[str],
        parent_zone_id: str,
        assigned_gpios: List[int],
        safe_mode_active: bool,
    ) -> None:
        """
        Create or update subzone configuration in DB.

        When updating an EXISTING subzone: MERGE assigned_gpios (union with existing)
        instead of replacing. This prevents losing other sensors when assigning
        a single sensor via SubzoneAssignmentSection or SensorConfigPanel.

        Also removes the assigned GPIOs from all OTHER subzones of this ESP
        (a GPIO can only belong to one subzone).

        Note: Flushes to make changes visible for subsequent queries.
        Caller is responsible for commit() or rollback().
        """
        # Check if subzone exists
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # MERGE: union of existing + new (don't replace - preserves other sensors)
            current = set(existing.assigned_gpios or [])
            merged = current | set(assigned_gpios)
            final_gpios = sorted(merged)

            # BUG-09: Only overwrite subzone_name if a non-empty name is provided.
            # Prevents clearing existing names when caller omits the parameter.
            if subzone_name and subzone_name.strip():
                existing.subzone_name = subzone_name
            existing.parent_zone_id = parent_zone_id
            existing.assigned_gpios = final_gpios
            existing.safe_mode_active = safe_mode_active

            # Remove these GPIOs from OTHER subzones of this ESP
            gpios_to_remove = set(assigned_gpios)
            if gpios_to_remove:
                other_result = await self.session.execute(
                    select(SubzoneConfig).where(
                        SubzoneConfig.esp_id == device_id,
                        SubzoneConfig.subzone_id != subzone_id,
                    )
                )
                for other in other_result.scalars().all():
                    if other.assigned_gpios:
                        other.assigned_gpios = [
                            g for g in other.assigned_gpios if g not in gpios_to_remove
                        ]
        else:
            # BUG-09: Auto-generate subzone name if not provided
            effective_name = subzone_name
            if not effective_name or not effective_name.strip():
                # Count existing subzones for this ESP to generate sequential name
                count_result = await self.session.execute(
                    select(SubzoneConfig).where(SubzoneConfig.esp_id == device_id)
                )
                existing_count = len(list(count_result.scalars().all()))
                effective_name = f"Subzone {existing_count + 1}"

            # Create new subzone
            new_config = SubzoneConfig(
                esp_id=device_id,
                subzone_id=subzone_id,
                subzone_name=effective_name,
                parent_zone_id=parent_zone_id,
                assigned_gpios=assigned_gpios,
                safe_mode_active=safe_mode_active,
            )
            self.session.add(new_config)

            # Remove these GPIOs from any OTHER subzones of this ESP
            if assigned_gpios:
                other_result = await self.session.execute(
                    select(SubzoneConfig).where(SubzoneConfig.esp_id == device_id)
                )
                for other in other_result.scalars().all():
                    if other.assigned_gpios:
                        other.assigned_gpios = [
                            g for g in other.assigned_gpios if g not in assigned_gpios
                        ]

        # Flush to make changes visible for subsequent queries
        await self.session.flush()

        # R20-P5: Sync assigned_sensor_config_ids (before counts, so counts use updated IDs)
        await self.sync_assigned_config_ids(device_id)

        # T13-R1: Sync sensor_count/actuator_count after subzone GPIO change
        await self._sync_counts_for_device(device_id)

    async def _sync_counts_for_device(self, device_id: str) -> None:
        """
        Sync sensor_count/actuator_count for all subzones of a device.

        Resolves the FK-Typ-Mismatch (subzone_configs.esp_id=String vs
        sensor_configs.esp_id=UUID) by looking up the ESP UUID first.
        """
        from ..db.repositories.subzone_repo import SubzoneRepository

        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            return

        subzone_repo = SubzoneRepository(self.session)
        try:
            updated = await subzone_repo.sync_subzone_counts(device_id, device.id)
            if updated:
                logger.debug(
                    "Synced subzone counts for %s: %d subzone(s) updated",
                    device_id,
                    updated,
                )
        except Exception as e:
            logger.warning("Failed to sync subzone counts for %s: %s", device_id, e)

    async def _confirm_subzone_assignment(self, device_id: str, subzone_id: str) -> None:
        """
        Confirm subzone assignment (update last_ack_at).

        Note: Flushes to make changes visible for subsequent queries.
        Caller is responsible for commit() or rollback().
        """
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        config = result.scalar_one_or_none()

        if config:
            config.last_ack_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def _delete_subzone_config(self, device_id: str, subzone_id: str) -> None:
        """
        Delete subzone configuration from DB.

        Note: Flushes to make changes visible for subsequent queries.
        Caller is responsible for commit() or rollback().
        """
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        config = result.scalar_one_or_none()

        if config:
            await self.session.delete(config)
            await self.session.flush()

    async def _update_subzone_safe_mode(
        self, device_id: str, subzone_id: str, active: bool
    ) -> None:
        """
        Update safe_mode_active for a subzone (used for mock devices).

        Note: Flushes to make changes visible. Caller is responsible for commit().
        """
        result = await self.session.execute(
            select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device_id,
                SubzoneConfig.subzone_id == subzone_id,
            )
        )
        config = result.scalar_one_or_none()
        if config:
            config.safe_mode_active = active
            await self.session.flush()

    async def remove_gpio_from_all_subzones(self, device_id: str, gpio: int) -> None:
        """
        Remove a GPIO from all subzones of an ESP.

        Used when: sensor is deleted, or sensor is assigned to "Keine Subzone".

        Note: Flushes to make changes visible. Caller is responsible for commit().
        """
        result = await self.session.execute(
            select(SubzoneConfig).where(SubzoneConfig.esp_id == device_id)
        )
        for subzone in result.scalars().all():
            if subzone.assigned_gpios and gpio in subzone.assigned_gpios:
                subzone.assigned_gpios = [g for g in subzone.assigned_gpios if g != gpio]
        await self.session.flush()

        # R20-P5: Sync assigned_sensor_config_ids after GPIO removal
        await self.sync_assigned_config_ids(device_id)

    async def sync_assigned_config_ids(self, device_id: str) -> None:
        """
        Recompute assigned_sensor_config_ids for all subzones of a device.

        Resolves the FK type mismatch (SubzoneConfig.esp_id=String vs
        SensorConfig.esp_id=UUID) by looking up the ESP UUID first.

        This ensures I2C sensors (GPIO=0) are correctly tracked by UUID
        rather than just GPIO number. Without this, all I2C sensors on
        GPIO 0 would be indistinguishable in subzone assignment.

        Note: Flushes if changes detected. Caller is responsible for commit().
        """
        from ..db.models.sensor import SensorConfig

        device = await self.esp_repo.get_by_device_id(device_id)
        if not device:
            return

        # Load all subzones for this device
        result = await self.session.execute(
            select(SubzoneConfig).where(SubzoneConfig.esp_id == device_id)
        )
        subzones = list(result.scalars().all())
        if not subzones:
            return

        # Load all sensor configs for this device (by UUID — FK type mismatch)
        sensor_result = await self.session.execute(
            select(SensorConfig).where(SensorConfig.esp_id == device.id)
        )
        all_sensors = list(sensor_result.scalars().all())

        changed = False
        for subzone in subzones:
            gpios = set(subzone.assigned_gpios or [])
            new_ids = sorted(str(s.id) for s in all_sensors if s.gpio in gpios)
            old_ids = sorted(subzone.assigned_sensor_config_ids or [])
            if new_ids != old_ids:
                subzone.assigned_sensor_config_ids = new_ids
                flag_modified(subzone, "assigned_sensor_config_ids")
                changed = True

        if changed:
            await self.session.flush()
