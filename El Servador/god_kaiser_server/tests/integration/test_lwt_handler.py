"""
Integration Tests für LWTHandler.

Location: tests/integration/test_lwt_handler.py
Benötigt: DB-Session, Repositories

Phase 3 Test-Suite: Instant Offline Detection, Idempotency, Unknown Device Handling.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.mqtt.handlers.lwt_handler import LWTHandler, get_lwt_handler


@pytest.fixture(autouse=True)
def mock_terminal_authority_repo():
    """Mock terminal authority repository for all LWTHandler tests."""
    with patch("src.mqtt.handlers.lwt_handler.CommandContractRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.upsert_terminal_event_authority = AsyncMock(return_value=(MagicMock(), False))
        mock_repo.list_open_intents_for_esp = AsyncMock(return_value=[])
        mock_outcome_row = MagicMock()
        mock_outcome_row.intent_id = "intent-1"
        mock_outcome_row.correlation_id = "corr-1"
        mock_outcome_row.esp_id = "ESP_TEST"
        mock_outcome_row.flow = "command"
        mock_outcome_row.outcome = "failed"
        mock_outcome_row.contract_version = 2
        mock_outcome_row.semantic_mode = "target"
        mock_outcome_row.legacy_status = "failed"
        mock_outcome_row.target_status = "failed"
        mock_outcome_row.is_final = True
        mock_outcome_row.code = "ESP_DISCONNECTED_BEFORE_OUTCOME"
        mock_outcome_row.reason = "ESP disconnected before terminal outcome"
        mock_outcome_row.retryable = False
        mock_outcome_row.generation = None
        mock_outcome_row.seq = None
        mock_outcome_row.epoch = None
        mock_outcome_row.ttl_ms = None
        mock_outcome_row.ts = int(datetime.now(timezone.utc).timestamp())
        mock_outcome_row.first_seen_at = datetime.now(timezone.utc)
        mock_outcome_row.terminal_at = datetime.now(timezone.utc)
        mock_repo.upsert_outcome = AsyncMock(return_value=(mock_outcome_row, False))
        mock_repo_class.return_value = mock_repo
        yield mock_repo


class TestLWTInstantOffline:
    """Test instant offline detection via LWT."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    @pytest.fixture
    def valid_lwt_payload(self):
        """Gültiges LWT Payload."""
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

    @pytest.mark.asyncio
    async def test_retained_lwt_skips_db_aut341(self, handler, valid_lwt_payload):
        """AUT-341: retain=True means broker replayed a retained message — no DB writes."""
        topic = "kaiser/god/esp/ESP_RETAIN/system/will"
        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            result = await handler.handle_lwt(topic, valid_lwt_payload, retain=True)
            assert result is True
            mock_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_lwt_marks_device_offline(self, handler, valid_lwt_payload):
        """LWT message marks device offline immediately."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"  # Currently online
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                        result = await handler.handle_lwt(topic, valid_lwt_payload)

                        assert result is True
                        mock_repo.update_status.assert_called_once_with("ESP_ONLINE", "offline")

    @pytest.mark.asyncio
    async def test_lwt_updates_device_metadata(self, handler, valid_lwt_payload):
        """LWT message updates device_metadata with disconnect info."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                        result = await handler.handle_lwt(topic, valid_lwt_payload)

                        assert result is True
                        # Device metadata should be updated
                        assert "last_disconnect" in mock_device.device_metadata
                        assert mock_device.device_metadata["last_disconnect"]["source"] == "lwt"
                        assert (
                            mock_device.device_metadata["last_disconnect"]["reason"]
                            == "unexpected_disconnect"
                        )

    @pytest.mark.asyncio
    async def test_lwt_normalizes_timestamp_zero_in_metadata_and_broadcast(self, handler):
        """timestamp=0 in payload must never persist as 0 in last_disconnect."""
        topic = "kaiser/god/esp/ESP_ZERO_TS/system/will"
        payload = {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": 0,
        }

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ZERO_TS"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        result = await handler.handle_lwt(topic, payload)

        assert result is True
        metadata_ts = mock_device.device_metadata["last_disconnect"]["timestamp"]
        assert isinstance(metadata_ts, int)
        assert metadata_ts > 0
        ws_payload = mock_ws.broadcast.call_args.args[1]
        assert ws_payload["timestamp"] == metadata_ts

    @pytest.mark.asyncio
    async def test_lwt_broadcasts_websocket_event(self, handler, valid_lwt_payload):
        """LWT message triggers WebSocket broadcast."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        result = await handler.handle_lwt(topic, valid_lwt_payload)

                        assert result is True
                        # WebSocket broadcast should be called
                        mock_ws.broadcast.assert_called_once()
                        call_args = mock_ws.broadcast.call_args
                        assert call_args.args[0] == "esp_health"
                        assert call_args.args[1]["status"] == "offline"
                        assert call_args.args[1]["source"] == "lwt"

    @pytest.mark.asyncio
    async def test_lwt_sweeps_open_intents_and_broadcasts_intent_outcome(
        self,
        handler,
        valid_lwt_payload,
        mock_terminal_authority_repo,
    ):
        topic = "kaiser/god/esp/ESP_SWEEP/system/will"
        open_intent = MagicMock()
        open_intent.intent_id = "intent-open-1"
        open_intent.correlation_id = "corr-open-1"
        open_intent.flow = "command"
        mock_terminal_authority_repo.list_open_intents_for_esp = AsyncMock(
            return_value=[open_intent]
        )

        mock_outcome_row = MagicMock()
        mock_outcome_row.intent_id = "intent-open-1"
        mock_outcome_row.correlation_id = "corr-open-1"
        mock_outcome_row.esp_id = "ESP_SWEEP"
        mock_outcome_row.flow = "command"
        mock_outcome_row.outcome = "failed"
        mock_outcome_row.contract_version = 2
        mock_outcome_row.semantic_mode = "target"
        mock_outcome_row.legacy_status = "failed"
        mock_outcome_row.target_status = "failed"
        mock_outcome_row.is_final = True
        mock_outcome_row.code = "ESP_DISCONNECTED_BEFORE_OUTCOME"
        mock_outcome_row.reason = "ESP disconnected before terminal outcome"
        mock_outcome_row.retryable = False
        mock_outcome_row.generation = None
        mock_outcome_row.seq = None
        mock_outcome_row.epoch = None
        mock_outcome_row.ttl_ms = None
        mock_outcome_row.ts = int(datetime.now(timezone.utc).timestamp())
        mock_outcome_row.first_seen_at = datetime.now(timezone.utc)
        mock_outcome_row.terminal_at = datetime.now(timezone.utc)
        mock_terminal_authority_repo.upsert_outcome = AsyncMock(
            return_value=(mock_outcome_row, False)
        )

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_SWEEP"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        result = await handler.handle_lwt(topic, valid_lwt_payload)

        assert result is True
        mock_terminal_authority_repo.upsert_outcome.assert_awaited()
        intent_calls = [
            call for call in mock_ws.broadcast.call_args_list if call.args and call.args[0] == "intent_outcome"
        ]
        assert len(intent_calls) == 1
        assert intent_calls[0].args[1]["code"] == "ESP_DISCONNECTED_BEFORE_OUTCOME"


class TestLWTIdempotency:
    """Test LWT idempotency handling."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    @pytest.fixture
    def valid_lwt_payload(self):
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
        }

    @pytest.mark.asyncio
    async def test_lwt_ignored_if_already_offline(self, handler, valid_lwt_payload):
        """LWT is ignored if device is already offline (idempotency)."""
        topic = "kaiser/god/esp/ESP_OFFLINE/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_OFFLINE"
                mock_device.status = "offline"  # Already offline
                mock_device.device_metadata = {}

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                result = await handler.handle_lwt(topic, valid_lwt_payload)

                assert result is True
                # Should NOT update status (already offline)
                mock_repo.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_lwt_sets_offline_if_pending_approval(self, handler, valid_lwt_payload):
        """LWT transitions pending_approval devices to offline immediately."""
        topic = "kaiser/god/esp/ESP_PENDING/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_PENDING"
                mock_device.status = "pending_approval"
                mock_device.device_metadata = {}

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                result = await handler.handle_lwt(topic, valid_lwt_payload)

                assert result is True
                mock_repo.update_status.assert_called_once_with("ESP_PENDING", "offline")

    @pytest.mark.asyncio
    async def test_stale_terminal_event_skips_offline_transition(self, handler, valid_lwt_payload):
        """Stale terminal event should not re-apply offline transition."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.lwt_handler.CommandContractRepository"
                ) as mock_contract:
                    mock_contract_repo = MagicMock()
                    mock_contract_repo.upsert_terminal_event_authority = AsyncMock(
                        return_value=(MagicMock(), True)
                    )
                    mock_contract.return_value = mock_contract_repo

                    result = await handler.handle_lwt(topic, valid_lwt_payload)

                    assert result is True
                    mock_repo.update_status.assert_not_called()

    def test_terminal_authority_key_uses_last_seen_when_timestamp_invalid(self, handler):
        """timestamp=0 must not produce a permanent ts:0 dedup key."""
        base_last_seen = datetime.now(timezone.utc)
        key = handler._build_terminal_authority_key(
            esp_id="ESP_ONLINE",
            reason="unexpected_disconnect",
            correlation_id=None,
            payload={"timestamp": 0},
            epoch_hint=None,
            last_seen=base_last_seen,
        )
        assert "ts:0" not in key
        assert f"ts:{int(base_last_seen.timestamp())}" in key

    def test_terminal_authority_key_changes_with_new_session_last_seen(self, handler):
        """Two real disconnect sessions with timestamp=0 should not collapse to one key."""
        first_last_seen = datetime.now(timezone.utc)
        second_last_seen = first_last_seen + timedelta(seconds=75)

        first_key = handler._build_terminal_authority_key(
            esp_id="ESP_ONLINE",
            reason="unexpected_disconnect",
            correlation_id=None,
            payload={"timestamp": 0},
            epoch_hint=None,
            last_seen=first_last_seen,
        )
        second_key = handler._build_terminal_authority_key(
            esp_id="ESP_ONLINE",
            reason="unexpected_disconnect",
            correlation_id=None,
            payload={"timestamp": 0},
            epoch_hint=None,
            last_seen=second_last_seen,
        )

        assert first_key != second_key


class TestLWTUnknownDevice:
    """Test LWT for unknown devices."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    @pytest.fixture
    def valid_lwt_payload(self):
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
        }

    @pytest.mark.asyncio
    async def test_lwt_for_unknown_device_ignored(self, handler, valid_lwt_payload):
        """LWT for unknown device is silently ignored."""
        topic = "kaiser/god/esp/ESP_UNKNOWN/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=None)  # Device not found
                mock_repo_class.return_value = mock_repo

                result = await handler.handle_lwt(topic, valid_lwt_payload)

                # Handler should acknowledge but not fail
                assert result is True


class TestLWTTopicParsing:
    """Test LWT topic parsing."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    @pytest.fixture
    def valid_lwt_payload(self):
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
        }

    @pytest.mark.asyncio
    async def test_invalid_topic_returns_false(self, handler, valid_lwt_payload):
        """Invalid topic format causes handler to return False."""
        topic = "invalid/topic/format"

        result = await handler.handle_lwt(topic, valid_lwt_payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_topic_returns_false(self, handler, valid_lwt_payload):
        """Empty topic returns False."""
        topic = ""

        result = await handler.handle_lwt(topic, valid_lwt_payload)
        assert result is False


class TestLWTPayloadHandling:
    """Test LWT payload handling edge cases."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    @pytest.mark.asyncio
    async def test_lwt_without_status_field(self, handler):
        """LWT without status field is still processed (assumes offline)."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"
        payload = {
            "reason": "unexpected_disconnect",
            # Missing "status" field
        }

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                        result = await handler.handle_lwt(topic, payload)

                        # Handler should still work
                        assert result is True

    @pytest.mark.asyncio
    async def test_lwt_with_custom_reason(self, handler):
        """LWT with custom reason is preserved in metadata."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/will"
        payload = {
            "status": "offline",
            "reason": "power_loss",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()  # session.commit() is awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                    mock_audit.return_value.log_device_event = AsyncMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                        result = await handler.handle_lwt(topic, payload)

                        assert result is True
                        # Custom reason should be preserved
                        assert (
                            mock_device.device_metadata["last_disconnect"]["reason"] == "power_loss"
                        )


class TestLWTFlappingDetection:
    """PKG-19: Flapping detection in LWT handler."""

    @pytest.fixture
    def handler(self):
        return LWTHandler()

    def test_first_lwt_is_not_flapping(self, handler):
        """First LWT for a device should not be flagged as flapping."""
        count = handler._record_lwt_event("ESP_FLAP_01")
        assert count == 1

    def test_second_lwt_triggers_flapping(self, handler):
        """Second LWT within the window triggers flapping."""
        handler._record_lwt_event("ESP_FLAP_02")
        count = handler._record_lwt_event("ESP_FLAP_02")
        assert count >= 2

    def test_different_esps_tracked_independently(self, handler):
        """LWT events for different ESPs are tracked independently."""
        handler._record_lwt_event("ESP_A")
        handler._record_lwt_event("ESP_A")
        count_b = handler._record_lwt_event("ESP_B")
        assert count_b == 1

    def test_get_lwt_count_returns_zero_for_unknown(self, handler):
        """get_lwt_count returns 0 for unknown ESP."""
        assert handler.get_lwt_count("ESP_NEVER_SEEN") == 0

    @pytest.mark.asyncio
    async def test_flapping_lwt_skips_actuator_reset(self, handler):
        """PKG-19: When flapping, actuator reset is skipped."""
        topic = "kaiser/god/esp/ESP_FLAP/system/will"
        payload = {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        handler._record_lwt_event("ESP_FLAP")

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_FLAP"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.ActuatorRepository") as mock_act_class:
                    mock_act_repo = MagicMock()
                    mock_act_repo.get_active_actuators_for_device = AsyncMock(return_value=[])
                    mock_act_repo.reset_states_for_device = AsyncMock(return_value=0)
                    mock_act_class.return_value = mock_act_repo

                    with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                        mock_audit.return_value.log_device_event = AsyncMock()

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                            mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                            result = await handler.handle_lwt(topic, payload)

                            assert result is True
                            mock_repo.update_status.assert_called_once_with("ESP_FLAP", "offline")
                            mock_act_repo.reset_states_for_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_flapping_flag_in_metadata_and_broadcast(self, handler):
        """PKG-19: Flapping flag appears in device_metadata and WS broadcast."""
        topic = "kaiser/god/esp/ESP_FLAP2/system/will"
        payload = {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        handler._record_lwt_event("ESP_FLAP2")

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_FLAP2"
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.ActuatorRepository") as mock_act_class:
                    mock_act_repo = MagicMock()
                    mock_act_class.return_value = mock_act_repo

                    with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                        mock_audit.return_value.log_device_event = AsyncMock()

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            result = await handler.handle_lwt(topic, payload)

                            assert result is True
                            last_disc = mock_device.device_metadata["last_disconnect"]
                            assert last_disc["is_flapping"] is True
                            assert last_disc["lwt_count_5m"] >= 2

                            call_args = mock_ws.broadcast.call_args
                            ws_payload = call_args.args[1]
                            assert ws_payload["is_flapping"] is True
                            assert ws_payload["lwt_count_5m"] >= 2


class TestLWTGlobalHandler:
    """Test global handler instance."""

    def test_get_lwt_handler_returns_singleton(self):
        """get_lwt_handler returns singleton instance."""
        handler1 = get_lwt_handler()
        handler2 = get_lwt_handler()
        assert handler1 is handler2

    def test_handler_is_lwt_handler_instance(self):
        """Handler is an LWTHandler instance."""
        handler = get_lwt_handler()
        assert isinstance(handler, LWTHandler)
