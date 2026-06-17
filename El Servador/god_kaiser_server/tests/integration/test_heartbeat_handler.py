"""
Integration Tests für HeartbeatHandler.

Location: tests/integration/test_heartbeat_handler.py
Benötigt: DB-Session, Repositories, Event Loop

Phase 3 Test-Suite: Heartbeat Processing, Auto-Discovery, Status Transitions.
"""

import json
import os
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.mqtt.handlers.heartbeat_handler import (
    HeartbeatHandler,
    get_heartbeat_handler,
    set_command_bridge,
)
from src.schemas.esp import SessionAnnouncePayload


class TestHeartbeatPayloadValidation:
    """Test payload validation - 4 Required Fields!"""

    @pytest.fixture
    def handler(self):
        """Get HeartbeatHandler instance."""
        return get_heartbeat_handler()

    def test_valid_payload_passes_validation(self, handler):
        """Valid payload with ALL 4 required fields passes."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True
        assert result["error"] == ""

    def test_valid_payload_with_optional_fields(self, handler):
        """Valid payload with optional fields passes."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
            "esp_id": "ESP_TEST_001",
            "zone_id": "test_zone",
            "master_zone_id": "main_zone",
            "zone_assigned": True,
            "sensor_count": 3,
            "actuator_count": 2,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True

    def test_pkg17_slim_payload_without_gpio_fields_passes_validation(self, handler):
        """PKG-17 regression: Payload without any gpio-related fields must pass validation.

        PKG-17 removes the following fields from firmware heartbeats to reduce payload size:
          - gpio_status, gpio_reserved_count, gpio_status_cached,
            gpio_status_cache_age_ms, payload_degraded, degraded_fields,
            heartbeat_degraded_count

        Server must tolerate all of these being absent without treating it as an error.
        """
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
            # PKG-17: none of the gpio-related fields are present
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True
        assert result["error"] == ""

    def test_missing_ts_fails(self, handler):
        """Missing ts field fails validation."""
        payload = {
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "ts" in result["error"].lower()

    def test_missing_uptime_fails(self, handler):
        """Missing uptime field fails validation."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "uptime" in result["error"].lower()

    def test_missing_heap_free_fails(self, handler):
        """Missing heap_free field fails validation."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        # Accepts either heap_free or free_heap
        assert "heap" in result["error"].lower()

    def test_free_heap_accepted_alternative(self, handler):
        """free_heap is accepted as alternative to heap_free."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "free_heap": 98304,  # Alternative name
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True

    def test_missing_wifi_rssi_fails(self, handler):
        """Missing wifi_rssi field fails validation."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "rssi" in result["error"].lower()

    def test_ts_must_be_int(self, handler):
        """ts field must be integer."""
        payload = {
            "ts": "1704722400",  # String instead of int
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "integer" in result["error"].lower() or "int" in result["error"].lower()

    def test_uptime_must_be_int(self, handler):
        """uptime field must be integer."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": "3600",  # String instead of int
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "integer" in result["error"].lower() or "int" in result["error"].lower()

    def test_heap_free_must_be_int(self, handler):
        """heap_free field must be integer."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": "98304",  # String instead of int
            "wifi_rssi": -45,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "integer" in result["error"].lower() or "int" in result["error"].lower()

    def test_wifi_rssi_must_be_int(self, handler):
        """wifi_rssi field must be integer."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": "-45",  # String instead of int
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "integer" in result["error"].lower() or "int" in result["error"].lower()

    def test_empty_payload_fails(self, handler):
        """Empty payload fails validation."""
        payload = {}
        result = handler._validate_payload(payload)
        assert result["valid"] is False


class TestContractRejectCounterSplit:
    """AUT-69: startup/runtime split for handover contract rejects."""

    @pytest.fixture
    def handler(self):
        return HeartbeatHandler()

    def test_reject_within_startup_window_increments_startup_counter(self, handler):
        esp_id = "ESP_AUT69_STARTUP"
        handler._last_session_connected_ts_by_esp[esp_id] = time.monotonic()
        payload = {
            "handover_contract_reject_count": 1,
            "handover_contract_last_reject": "MISSING_ACTIVE_SESSION_EPOCH",
        }
        metadata = {}

        handler._track_contract_reject_metrics(esp_id, payload, metadata)

        assert metadata["handover_contract_reject_startup"] == 1
        assert metadata["handover_contract_reject_runtime"] == 0
        assert metadata["handover_contract_reject"] == 1

    def test_reject_after_startup_window_increments_runtime_counter(self, handler):
        esp_id = "ESP_AUT69_RUNTIME"
        handler._last_session_connected_ts_by_esp[esp_id] = time.monotonic() - 1.5
        payload = {
            "handover_contract_reject_count": 2,
            "handover_contract_last_reject": "MISSING_ACTIVE_SESSION_EPOCH",
        }
        metadata = {
            "handover_contract_reject_count_last": 1,
            "handover_contract_reject_startup": 1,
            "handover_contract_reject_runtime": 0,
        }

        handler._track_contract_reject_metrics(esp_id, payload, metadata)

        assert metadata["handover_contract_reject_startup"] == 1
        assert metadata["handover_contract_reject_runtime"] == 1
        assert metadata["handover_contract_reject"] == 2

    def test_payload_without_new_fields_keeps_backward_compatibility(self, handler):
        metadata = {"stable_key": "stable_value"}
        payload = {"ts": int(datetime.now(timezone.utc).timestamp())}

        handler._track_contract_reject_metrics("ESP_AUT69_COMPAT", payload, metadata)

        assert metadata == {"stable_key": "stable_value"}

    def test_alias_mapping_accepts_both_handover_and_session_epoch(self):
        from_handover = SessionAnnouncePayload.from_payload(
            {"handover_epoch": 5, "reason": "reconnect", "ts_ms": 1000}
        )
        from_session = SessionAnnouncePayload.from_payload(
            {"session_epoch": 6, "reason": "boot", "ts_ms": 2000}
        )

        assert from_handover.handover_epoch == 5
        assert from_session.handover_epoch == 6


class TestHeartbeatMetadataDegradedFlags:
    """AUT-68: Metadata persistence for PKG-17 slim-payload flags.

    Covers edge cases for payload_degraded, degraded_fields and the
    stale-gpio_status semantics when a follow-up heartbeat omits
    gpio_status.
    """

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.fixture
    def esp_device(self):
        device = MagicMock()
        device.device_id = "ESP_DEGRADED_001"
        device.device_metadata = {}
        device.zone_id = None
        return device

    @pytest.fixture
    def mock_session(self):
        s = MagicMock()
        s.commit = AsyncMock()
        s.flush = AsyncMock()
        return s

    @pytest.mark.asyncio
    async def test_payload_degraded_flag_persisted_without_gpio_status(
        self, handler, esp_device, mock_session
    ):
        """payload_degraded=true alone (no gpio_status) is accepted and persisted."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
            "payload_degraded": True,
            # Intentionally no gpio_status, no degraded_fields
        }

        await handler._update_esp_metadata(esp_device, payload, mock_session)

        assert esp_device.device_metadata.get("payload_degraded") is True
        # No gpio_status written when payload does not contain it.
        assert "gpio_status" not in esp_device.device_metadata

    @pytest.mark.asyncio
    async def test_degraded_fields_list_validated_and_persisted(
        self, handler, esp_device, mock_session
    ):
        """degraded_fields=[...] is accepted, filtered to str, and persisted as a list."""
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
            "payload_degraded": True,
            "degraded_fields": ["gpio_status", "", 42, None, "other"],  # mixed types
        }

        await handler._update_esp_metadata(esp_device, payload, mock_session)

        stored = esp_device.device_metadata.get("degraded_fields")
        assert isinstance(stored, list)
        # Only non-empty string entries are kept (see _update_esp_metadata filter).
        assert stored == ["gpio_status", "other"]

    @pytest.mark.asyncio
    async def test_gpio_status_is_not_cleared_when_next_heartbeat_omits_it(
        self, handler, esp_device, mock_session
    ):
        """Second heartbeat without gpio_status does NOT delete stored gpio_status.

        Documented behavior (AUT-68): The handler updates metadata additively —
        if a later heartbeat drops gpio_status (PKG-17 slim payload), the
        previously stored gpio_status REMAINS in device_metadata (stale-tolerant).
        This is intentional: firmware only resends gpio_status on change, so the
        server keeps the last-known authoritative snapshot.
        """
        # Heartbeat #1: carries a gpio_status entry
        payload1 = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
            "gpio_status": [
                {
                    "gpio": 18,
                    "owner": "actuator",
                    "component": "pump_1",
                    "mode": 2,  # Arduino OUTPUT → normalized to 1
                    "safe": False,
                }
            ],
            "gpio_reserved_count": 1,
        }
        await handler._update_esp_metadata(esp_device, payload1, mock_session)

        first_snapshot = esp_device.device_metadata.get("gpio_status")
        assert isinstance(first_snapshot, list)
        assert len(first_snapshot) == 1
        assert first_snapshot[0]["gpio"] == 18

        # Heartbeat #2: PKG-17 slim payload — no gpio_status, no degraded flags
        payload2 = {
            "ts": int(datetime.now(timezone.utc).timestamp()) + 10,
            "uptime": 110,
            "heap_free": 49000,
            "wifi_rssi": -62,
        }
        await handler._update_esp_metadata(esp_device, payload2, mock_session)

        # Stale semantics: gpio_status from heartbeat #1 is RETAINED.
        retained = esp_device.device_metadata.get("gpio_status")
        assert retained == first_snapshot, (
            "gpio_status must be retained across heartbeats that omit it "
            "(AUT-68 stale-tolerant semantics, PKG-17 slim payload)"
        )


class TestHeartbeatWithoutGpioFieldsAccepted:
    """PKG-17 regression: handle_heartbeat accepts payload without gpio-related fields."""

    @pytest.fixture
    def handler(self):
        return HeartbeatHandler()

    @pytest.mark.asyncio
    async def test_heartbeat_without_gpio_fields_accepted(self, handler):
        """Full heartbeat flow without gpio_status, payload_degraded etc. succeeds."""
        topic = "kaiser/god/esp/ESP_PKG17/system/heartbeat"
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 600,
            "heap_free": 48000,
            "wifi_rssi": -52,
            "sensor_count": 2,
            "actuator_count": 1,
        }

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_db.begin_nested = AsyncMock()
            nested_ctx = MagicMock()
            nested_ctx.commit = AsyncMock()
            mock_db.begin_nested.return_value = nested_ctx

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_PKG17"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)
                mock_device.zone_id = None
                mock_device.master_zone_id = None
                mock_device.zone_name = None
                mock_device.kaiser_id = "god"

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"):
                    with patch("src.mqtt.client.MQTTClient.get_instance") as mock_mqtt:
                        mock_mqtt.return_value = MagicMock()

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                            mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                            with patch(
                                "src.services.logic_engine.get_logic_engine",
                                return_value=None,
                            ):
                                result = await handler.handle_heartbeat(topic, payload)

                                assert result is True
                                mock_repo.update_status.assert_called_once()
                                call_args = mock_repo.update_status.call_args
                                assert call_args.args[0] == "ESP_PKG17"
                                assert call_args.args[1] == "online"


class TestHeartbeatTopicParsing:
    """Test heartbeat topic parsing."""

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.mark.asyncio
    async def test_invalid_topic_returns_false(self, handler):
        """Invalid topic format causes handler to return False."""
        topic = "invalid/topic/format"
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
        }
        result = await handler.handle_heartbeat(topic, payload)
        assert result is False


class TestDeviceStatusTransitions:
    """Test device status state machine.

    Status Flow:
    NEW → pending_approval → (Admin Approval) → approved → (Heartbeat) → online ↔ offline
                           ↘ (Admin Reject) → rejected → (Cooldown 300s) → pending_approval ↗
    """

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.fixture
    def valid_payload(self):
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
        }

    @pytest.mark.asyncio
    async def test_approved_device_goes_online(self, handler, valid_payload):
        """Approved device transitions to online on first heartbeat."""
        topic = "kaiser/god/esp/ESP_APPROVED/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_APPROVED"
                mock_device.status = "approved"  # Approved but not yet online
                mock_device.device_metadata = {}
                mock_device.last_seen = None
                mock_device.id = 1

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"):
                    with patch("src.mqtt.handlers.heartbeat_handler.AuditLogRepository"):
                        with patch.object(handler, "_send_heartbeat_ack", new_callable=AsyncMock):
                            with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                                mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                                result = await handler.handle_heartbeat(topic, valid_payload)

                                # Handler should succeed
                                assert result is True
                                # Device status should be set to online
                                assert mock_device.status == "online"

    @pytest.mark.asyncio
    async def test_pending_device_stays_pending(self, handler, valid_payload):
        """Pending device heartbeat is recorded but status stays pending."""
        topic = "kaiser/god/esp/ESP_PENDING/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_PENDING"
                mock_device.status = "pending_approval"
                mock_device.device_metadata = {}
                mock_device.id = 1

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo_class.return_value = mock_repo

                with patch.object(handler, "_update_pending_heartbeat", new_callable=AsyncMock):
                    with patch.object(handler, "_send_heartbeat_ack", new_callable=AsyncMock):
                        result = await handler.handle_heartbeat(topic, valid_payload)

                        # Handler should succeed
                        assert result is True
                        # Status should remain pending_approval
                        assert mock_device.status == "pending_approval"


class TestDeviceDiscovery:
    """Test auto-discovery of new devices.

    WICHTIG: Auto-Discovery IST AKTIV!
    Neue Geräte werden mit status='pending_approval' registriert.
    """

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.fixture
    def valid_payload(self):
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
        }

    @pytest.mark.asyncio
    async def test_new_device_triggers_discovery(self, handler, valid_payload):
        """New device heartbeat triggers auto-discovery flow."""
        topic = "kaiser/god/esp/ESP_NEW_DEVICE/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=None)  # Device not found
                mock_repo_class.return_value = mock_repo

                # Mock the discovery method
                with patch.object(
                    handler, "_discover_new_device", new_callable=AsyncMock
                ) as mock_discover:
                    mock_new_device = MagicMock()
                    mock_new_device.status = "pending_approval"
                    mock_discover.return_value = (mock_new_device, "discovered")

                    with patch.object(
                        handler, "_broadcast_device_discovered", new_callable=AsyncMock
                    ):
                        with patch.object(
                            handler, "_send_heartbeat_ack", new_callable=AsyncMock
                        ) as mock_ack:
                            result = await handler.handle_heartbeat(topic, valid_payload)

                            # Handler should succeed
                            assert result is True
                            # Discovery should have been called
                            mock_discover.assert_called_once()
                            # ACK should be sent with pending_approval status
                            mock_ack.assert_called_once()
                            ack_kwargs = mock_ack.call_args.kwargs
                            assert ack_kwargs["esp_id"] == "ESP_NEW_DEVICE"
                            assert ack_kwargs["status"] == "pending_approval"
                            assert ack_kwargs["config_available"] is False
                            assert ack_kwargs["handover_epoch"] >= 1
                            assert "session_id" in ack_kwargs

    @pytest.mark.asyncio
    async def test_soft_deleted_device_restored_on_heartbeat(self, handler, valid_payload):
        """Heartbeat for soft-deleted device_id restores row instead of failing INSERT."""
        topic = "kaiser/god/esp/ESP_SOFT_DEL/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                tombstone = MagicMock()
                tombstone.device_id = "ESP_SOFT_DEL"
                tombstone.deleted_at = datetime.now(timezone.utc)
                tombstone.deleted_by = "admin"
                tombstone.status = "deleted"
                tombstone.device_metadata = {"heartbeat_count": 0}

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(side_effect=[None, tombstone])
                mock_repo_class.return_value = mock_repo

                with patch.object(
                    handler, "_discover_new_device", new_callable=AsyncMock
                ) as mock_discover:
                    with patch.object(
                        handler, "_broadcast_device_discovered", new_callable=AsyncMock
                    ):
                        with patch.object(
                            handler, "_send_heartbeat_ack", new_callable=AsyncMock
                        ) as mock_ack:
                            result = await handler.handle_heartbeat(topic, valid_payload)

                            assert result is True
                            mock_discover.assert_not_called()
                            assert tombstone.deleted_at is None
                            assert tombstone.deleted_by is None
                            assert tombstone.status == "pending_approval"
                            mock_ack.assert_called_once()
                            assert mock_ack.call_args.kwargs["status"] == "pending_approval"

    @pytest.mark.asyncio
    async def test_soft_deleted_device_restore_blocked_by_policy(self, handler, valid_payload):
        """Restore can be blocked with ESP_SOFT_DELETE_RESTORE_POLICY=deny."""
        topic = "kaiser/god/esp/ESP_SOFT_DEL/system/heartbeat"

        with patch.dict(os.environ, {"ESP_SOFT_DELETE_RESTORE_POLICY": "deny"}, clear=False):
            with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
                mock_db = MagicMock()
                mock_db.commit = AsyncMock()
                mock_db.flush = AsyncMock()
                mock_db.rollback = AsyncMock()
                mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

                with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                    tombstone = MagicMock()
                    tombstone.device_id = "ESP_SOFT_DEL"
                    tombstone.deleted_at = datetime.now(timezone.utc)
                    tombstone.deleted_by = "admin"
                    tombstone.status = "deleted"
                    tombstone.device_metadata = {"heartbeat_count": 0}

                    mock_repo = MagicMock()
                    mock_repo.get_by_device_id = AsyncMock(side_effect=[None, tombstone])
                    mock_repo_class.return_value = mock_repo

                    with patch.object(
                        handler, "_broadcast_device_discovered", new_callable=AsyncMock
                    ) as mock_broadcast:
                        with patch.object(
                            handler, "_send_heartbeat_ack", new_callable=AsyncMock
                        ) as mock_ack:
                            result = await handler.handle_heartbeat(topic, valid_payload)

                            assert result is True
                            assert tombstone.deleted_at is not None
                            mock_broadcast.assert_not_called()
                            mock_ack.assert_not_called()


class TestTimeoutDetection:
    """Test device timeout detection."""

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.mark.asyncio
    async def test_check_device_timeouts_returns_dict(self, handler):
        """check_device_timeouts returns proper structure."""
        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_status = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                result = await handler.check_device_timeouts()

                assert "checked" in result
                assert "timed_out" in result
                assert "offline_devices" in result


class TestRejectedDeviceHandling:
    """Test handling of rejected devices."""

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.fixture
    def valid_payload(self):
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -60,
        }

    @pytest.mark.asyncio
    async def test_rejected_device_in_cooldown(self, handler, valid_payload):
        """Rejected device in cooldown gets rejected ACK."""
        topic = "kaiser/god/esp/ESP_REJECTED/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_REJECTED"
                mock_device.status = "rejected"
                mock_device.device_metadata = {}
                mock_device.id = 1

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo_class.return_value = mock_repo

                # Device is still in cooldown
                with patch.object(
                    handler, "_check_rejection_cooldown", new_callable=AsyncMock
                ) as mock_cooldown:
                    mock_cooldown.return_value = False  # Still in cooldown

                    with patch.object(
                        handler, "_send_heartbeat_ack", new_callable=AsyncMock
                    ) as mock_ack:
                        result = await handler.handle_heartbeat(topic, valid_payload)

                        assert result is True
                        mock_ack.assert_called_once()
                        ack_kwargs = mock_ack.call_args.kwargs
                        assert ack_kwargs["esp_id"] == "ESP_REJECTED"
                        assert ack_kwargs["status"] == "rejected"
                        assert ack_kwargs["config_available"] is False
                        assert ack_kwargs["handover_epoch"] >= 1


class TestOnlineDeviceHeartbeat:
    """Test heartbeat handling for online devices."""

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    @pytest.fixture
    def valid_payload(self):
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 3600,
            "heap_free": 98304,
            "wifi_rssi": -45,
            "sensor_count": 3,
            "actuator_count": 2,
        }

    @pytest.mark.asyncio
    async def test_online_device_updates_last_seen(self, handler, valid_payload):
        """Online device heartbeat updates last_seen timestamp."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)
                mock_device.id = 1

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"):
                    with patch.object(handler, "_update_esp_metadata", new_callable=AsyncMock):
                        with patch.object(handler, "_log_health_metrics"):
                            with patch.object(
                                handler, "_send_heartbeat_ack", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    handler, "_has_pending_config", new_callable=AsyncMock
                                ) as mock_config:
                                    mock_config.return_value = False
                                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                                        result = await handler.handle_heartbeat(
                                            topic, valid_payload
                                        )

                                        assert result is True
                                        mock_repo.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_payload_ts_uses_server_last_seen(self, handler, valid_payload):
        """Stale payload ts with time_valid=true must not write stale last_seen."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/heartbeat"
        stale_epoch = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
        payload = {**valid_payload, "ts": stale_epoch, "time_valid": True}

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)
                mock_device.id = 1

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"):
                    with patch.object(handler, "_update_esp_metadata", new_callable=AsyncMock):
                        with patch.object(handler, "_log_health_metrics"):
                            with patch.object(
                                handler, "_send_heartbeat_ack", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    handler, "_has_pending_config", new_callable=AsyncMock
                                ) as mock_config:
                                    mock_config.return_value = False
                                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                                        before_call = datetime.now(timezone.utc)
                                        result = await handler.handle_heartbeat(topic, payload)
                                        after_call = datetime.now(timezone.utc)

                                        assert result is True
                                        mock_repo.update_status.assert_called_once()
                                        args = mock_repo.update_status.call_args.args
                                        assert args[0] == "ESP_ONLINE"
                                        assert args[1] == "online"
                                        assert isinstance(args[2], datetime)
                                        assert before_call <= args[2] <= after_call


class TestZoneMismatchDetection:
    """Test zone mismatch detection and auto-reassignment.

    Bug 3 (ZONE_MISMATCH): After ESP reboot (especially in Wokwi without
    persistent NVS), the ESP loses its zone config. The server should detect
    this via heartbeat and auto-resend the zone assignment.
    """

    @pytest.fixture
    def handler(self):
        return get_heartbeat_handler()

    def test_zone_mismatch_detected_via_zone_id(self, handler):
        """Zone mismatch detected when ESP sends empty zone_id but DB has zone."""
        # Simulate ESP device with zone in DB
        mock_device = MagicMock()
        mock_device.device_id = "ESP_ZONE_TEST"
        mock_device.zone_id = "greenhouse"
        mock_device.master_zone_id = "main_zone"
        mock_device.zone_name = "Greenhouse"
        mock_device.kaiser_id = "god"
        mock_device.device_metadata = {}

        # ESP heartbeat payload with empty zone_id (lost after reboot)
        payload = {
            "zone_id": "",
            "zone_assigned": False,
        }

        # Extract detection logic values
        heartbeat_zone_id = payload.get("zone_id", "")
        heartbeat_zone_assigned = payload.get("zone_assigned", True)
        db_zone_id = mock_device.zone_id or ""

        esp_has_zone = bool(heartbeat_zone_id)
        db_has_zone = bool(db_zone_id)
        esp_lost_zone = not heartbeat_zone_assigned and db_has_zone

        # Assertions
        assert heartbeat_zone_id == ""
        assert db_zone_id == "greenhouse"
        assert not esp_has_zone
        assert db_has_zone
        assert esp_lost_zone  # zone_assigned=false + DB has zone
        assert heartbeat_zone_id != db_zone_id  # String mismatch triggers detection

    def test_zone_mismatch_detected_via_zone_assigned_flag(self, handler):
        """Zone mismatch detected via zone_assigned=false even if zone_id comparison would miss it."""
        # Scenario: ESP has matching zone_id string but zone_assigned=false
        # This can happen if zone_id is stale in payload but NVS is cleared
        mock_device = MagicMock()
        mock_device.zone_id = "greenhouse"
        mock_device.device_metadata = {}

        payload = {
            "zone_id": "greenhouse",  # Stale value from previous session
            "zone_assigned": False,  # But flag says NOT assigned
        }

        heartbeat_zone_id = payload.get("zone_id", "")
        heartbeat_zone_assigned = payload.get("zone_assigned", True)
        db_zone_id = mock_device.zone_id or ""

        db_has_zone = bool(db_zone_id)
        esp_lost_zone = not heartbeat_zone_assigned and db_has_zone

        # zone_id strings match, but zone_assigned=false triggers detection
        assert heartbeat_zone_id == db_zone_id  # Strings match
        assert esp_lost_zone  # But flag detects the loss

    def test_no_mismatch_when_both_unassigned(self, handler):
        """No mismatch when both ESP and DB have no zone."""
        payload = {
            "zone_id": "",
            "zone_assigned": False,
        }

        mock_device = MagicMock()
        mock_device.zone_id = None
        mock_device.device_metadata = {}

        heartbeat_zone_id = payload.get("zone_id", "")
        heartbeat_zone_assigned = payload.get("zone_assigned", True)
        db_zone_id = mock_device.zone_id or ""

        db_has_zone = bool(db_zone_id)
        esp_lost_zone = not heartbeat_zone_assigned and db_has_zone

        # No mismatch: both sides have no zone
        assert heartbeat_zone_id == db_zone_id  # Both ""
        assert not esp_lost_zone  # DB has no zone, so no loss detected

    def test_no_mismatch_when_zones_match(self, handler):
        """No mismatch when ESP and DB zones match."""
        payload = {
            "zone_id": "greenhouse",
            "zone_assigned": True,
        }

        mock_device = MagicMock()
        mock_device.zone_id = "greenhouse"
        mock_device.device_metadata = {}

        heartbeat_zone_id = payload.get("zone_id", "")
        heartbeat_zone_assigned = payload.get("zone_assigned", True)
        db_zone_id = mock_device.zone_id or ""

        db_has_zone = bool(db_zone_id)
        esp_lost_zone = not heartbeat_zone_assigned and db_has_zone

        assert heartbeat_zone_id == db_zone_id  # Match
        assert not esp_lost_zone  # zone_assigned=True

    def test_resync_cooldown_logic(self, handler):
        """Zone resync respects cooldown period (60s)."""
        import time as time_module

        now_ts = int(time_module.time())
        zone_resync_cooldown_seconds = 60

        # Case 1: No previous resync - should resync
        current_metadata_no_resync = {}
        last_resync = current_metadata_no_resync.get("zone_resync_sent_at")
        should_resync = True
        if last_resync:
            elapsed = now_ts - last_resync
            if elapsed < zone_resync_cooldown_seconds:
                should_resync = False
        assert should_resync is True

        # Case 2: Recent resync (10s ago) - should NOT resync
        current_metadata_recent = {"zone_resync_sent_at": now_ts - 10}
        last_resync = current_metadata_recent.get("zone_resync_sent_at")
        should_resync = True
        if last_resync:
            elapsed = now_ts - last_resync
            if elapsed < zone_resync_cooldown_seconds:
                should_resync = False
        assert should_resync is False

        # Case 3: Old resync (120s ago) - should resync
        current_metadata_old = {"zone_resync_sent_at": now_ts - 120}
        last_resync = current_metadata_old.get("zone_resync_sent_at")
        should_resync = True
        if last_resync:
            elapsed = now_ts - last_resync
            if elapsed < zone_resync_cooldown_seconds:
                should_resync = False
        assert should_resync is True

    @pytest.mark.asyncio
    async def test_zone_resync_sets_pending_zone_assignment_marker(self, handler):
        """WP7 auto-resync must set pending_zone_assignment like ZoneService."""
        set_command_bridge(None)
        mock_device = MagicMock()
        mock_device.device_id = "ESP_ZONE_PENDING"
        mock_device.zone_id = "zone_a"
        mock_device.master_zone_id = "master_a"
        mock_device.zone_name = "Zone A"
        mock_device.kaiser_id = "god"
        mock_device.status = "online"
        mock_device.device_metadata = {}
        mock_device.ip_address = None

        payload = {"zone_id": "", "zone_assigned": False}

        mock_session = MagicMock()
        mock_client = MagicMock()
        with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_client):
            await handler._update_esp_metadata(mock_device, payload, mock_session)

        assert mock_client.publish.call_count == 1
        pending = mock_device.device_metadata.get("pending_zone_assignment")
        assert isinstance(pending, dict)
        assert pending.get("zone_id") == "zone_a"
        assert pending.get("source") == "heartbeat_zone_resync"
        assert isinstance(pending.get("sent_at"), int)

    @pytest.mark.asyncio
    async def test_zone_resync_skipped_when_zone_command_pending(self, handler):
        """No duplicate auto-resync publish while bridge has pending zone command."""
        mock_bridge = MagicMock()
        mock_bridge.has_pending.return_value = True
        set_command_bridge(mock_bridge)
        try:
            mock_device = MagicMock()
            mock_device.device_id = "ESP_ZONE_PENDING_CMD"
            mock_device.zone_id = "zone_b"
            mock_device.master_zone_id = "master_b"
            mock_device.zone_name = "Zone B"
            mock_device.kaiser_id = "god"
            mock_device.status = "online"
            mock_device.device_metadata = {}
            mock_device.ip_address = None

            payload = {"zone_id": "", "zone_assigned": False}
            mock_session = MagicMock()
            mock_client = MagicMock()
            with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_client):
                await handler._update_esp_metadata(mock_device, payload, mock_session)

            assert mock_client.publish.call_count == 0
            assert "zone_resync_sent_at" not in mock_device.device_metadata
            assert "pending_zone_assignment" not in mock_device.device_metadata
            mock_bridge.has_pending.assert_called_once_with("ESP_ZONE_PENDING_CMD", "zone")
        finally:
            set_command_bridge(None)


class TestHeartbeatTimeoutAntiDuplicateEscalation:
    """PKG-19: check_device_timeouts skips devices already handled by LWT."""

    @pytest.fixture
    def handler(self):
        return HeartbeatHandler()

    @pytest.mark.asyncio
    async def test_timeout_skips_device_with_recent_lwt(self, handler):
        """Device recently marked offline by LWT should not be timed out again."""
        import time as time_module

        now_ts = int(time_module.time())
        mock_device = MagicMock()
        mock_device.device_id = "ESP_SKIP_LWT"
        mock_device.status = "online"
        mock_device.last_seen = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_device.device_metadata = {
            "last_disconnect": {
                "source": "lwt",
                "timestamp": now_ts - 30,
            }
        }

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_status = AsyncMock(return_value=[mock_device])
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                result = await handler.check_device_timeouts()

                mock_repo.update_status.assert_not_called()
                assert result["timed_out"] == 0

    @pytest.mark.asyncio
    async def test_timeout_proceeds_when_lwt_is_old(self, handler):
        """Device with old LWT should still be timed out normally."""
        mock_device = MagicMock()
        mock_device.device_id = "ESP_OLD_LWT"
        mock_device.id = "uuid-old-lwt"
        mock_device.status = "online"
        mock_device.last_seen = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_device.device_metadata = {
            "last_disconnect": {
                "source": "lwt",
                "timestamp": 1000000,
            }
        }

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_status = AsyncMock(return_value=[mock_device])
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.heartbeat_handler.ActuatorRepository") as mock_act:
                    mock_act_repo = MagicMock()
                    mock_act_repo.get_active_actuators_for_device = AsyncMock(return_value=[])
                    mock_act_repo.reset_states_for_device = AsyncMock(return_value=0)
                    mock_act.return_value = mock_act_repo

                    with patch(
                        "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                    ) as mock_audit:
                        mock_audit.return_value.log_device_event = AsyncMock()

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                            mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                            result = await handler.check_device_timeouts()

                            mock_repo.update_status.assert_called_once()
                            assert result["timed_out"] == 1


class TestHeartbeatReconnectMetadataConsistency:
    """Regression tests for reconnect cleanup of stale LWT metadata."""

    @pytest.fixture
    def handler(self):
        return HeartbeatHandler()

    @pytest.mark.asyncio
    async def test_online_heartbeat_clears_stale_lwt_last_disconnect(self, handler):
        topic = "kaiser/god/esp/ESP_STALE/system/heartbeat"
        payload = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 7200,
            "heap_free": 47000,
            "wifi_rssi": -48,
            "sensor_count": 1,
            "actuator_count": 1,
        }

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.id = "uuid-esp-stale"
                mock_device.device_id = "ESP_STALE"
                mock_device.status = "online"
                mock_device.last_seen = datetime.now(timezone.utc)
                mock_device.zone_id = None
                mock_device.master_zone_id = None
                mock_device.zone_name = None
                mock_device.kaiser_id = "god"
                mock_device.device_metadata = {
                    "last_disconnect": {
                        "source": "lwt",
                        "timestamp": 0,
                        "reason": "unexpected_disconnect",
                    }
                }

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch.object(
                    handler,
                    "_log_heartbeat_entry",
                    new_callable=AsyncMock,
                    return_value="production",
                ):
                    with patch("src.mqtt.client.MQTTClient.get_instance") as mock_mqtt:
                        mock_mqtt.return_value = MagicMock()
                        with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                            mock_ws.get_instance = AsyncMock(return_value=AsyncMock())
                            with patch(
                                "src.services.logic_engine.get_logic_engine",
                                return_value=None,
                            ):
                                result = await handler.handle_heartbeat(topic, payload)

        assert result is True
        assert "last_disconnect" not in mock_device.device_metadata
        assert "last_disconnect_stale_cleared_at" in mock_device.device_metadata
        assert (
            mock_device.device_metadata.get("last_disconnect_stale_cleared_reason")
            == "online_recovery_after_invalid_lwt"
        )

    @pytest.mark.asyncio
    async def test_log_heartbeat_entry_commits_isolated_session(self, handler):
        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            heartbeat_db = MagicMock()
            heartbeat_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=heartbeat_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.log_heartbeat = AsyncMock()
                mock_repo_class.return_value = mock_repo

                mock_device = MagicMock()
                mock_device.id = "uuid-esp-heartbeat"
                mock_device.device_id = "ESP_HEARTBEAT"
                mock_device.hardware_type = "ESP32_WROOM"
                mock_device.mac_address = "AA:BB:CC:DD:EE:FF"
                mock_device.device_metadata = {}

                resolved_source = await handler._log_heartbeat_entry(
                    esp_device=mock_device,
                    esp_id_str="ESP_HEARTBEAT",
                    payload={"ts": int(datetime.now(timezone.utc).timestamp())},
                )

        assert resolved_source
        mock_repo.log_heartbeat.assert_called_once()
        heartbeat_db.commit.assert_called_once()


class TestHeartbeatErrorAckContract:
    """Error-ACK must satisfy the same fail-closed contract as normal ACKs."""

    @pytest.fixture
    def handler(self):
        return HeartbeatHandler()

    @pytest.mark.asyncio
    async def test_error_ack_contains_handover_epoch_and_contract_fields(self, handler):
        with patch("src.mqtt.client.MQTTClient.get_instance") as mock_get_instance:
            mock_mqtt_client = MagicMock()
            mock_mqtt_client.publish.return_value = True
            mock_get_instance.return_value = mock_mqtt_client

            success = await handler._send_heartbeat_error_ack("ESP_TEST", "internal_error")

            assert success is True
            mock_mqtt_client.publish.assert_called_once()
            topic, payload_json = mock_mqtt_client.publish.call_args.args[:2]
            payload = json.loads(payload_json)

            assert topic.endswith("/system/heartbeat/ack")
            assert payload["status"] == "error"
            assert payload["error"] == "internal_error"
            assert payload["handover_epoch"] >= 1
            assert payload["ack_type"] == "heartbeat"
            assert payload["contract_version"] == 2

    @pytest.mark.asyncio
    async def test_error_ack_uses_explicit_contract_context_when_given(self, handler):
        with patch("src.mqtt.client.MQTTClient.get_instance") as mock_get_instance:
            mock_mqtt_client = MagicMock()
            mock_mqtt_client.publish.return_value = True
            mock_get_instance.return_value = mock_mqtt_client

            success = await handler._send_heartbeat_error_ack(
                "ESP_TEST",
                "invalid_payload",
                handover_epoch=7,
                session_id="ESP_TEST:handover:7:1234",
            )

            assert success is True
            topic, payload_json = mock_mqtt_client.publish.call_args.args[:2]
            payload = json.loads(payload_json)

            assert topic.endswith("/system/heartbeat/ack")
            assert payload["handover_epoch"] == 7
            assert payload["session_id"] == "ESP_TEST:handover:7:1234"
