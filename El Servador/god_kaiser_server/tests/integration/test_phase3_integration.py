"""
Phase 3 Integration Tests - End-to-End Flows.

Location: tests/integration/test_phase3_integration.py
Benötigt: DB-Session, Repositories, MQTT Handlers

Test-Szenarien:
1. Full Config Cycle: Server → ESP → Config Response → DB Update
2. Discovery → Approval → Online: Device Lifecycle
3. Network Partition Recovery: Offline → Reconnect → Online
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler, get_heartbeat_handler
from src.mqtt.handlers.config_handler import ConfigHandler, get_config_handler
from src.mqtt.handlers.lwt_handler import LWTHandler, get_lwt_handler
from src.db.models.esp import ESPDevice


class TestFullConfigCycle:
    """
    E2E Test: Full Configuration Cycle.

    Flow:
    1. Device is online
    2. Server sends sensor config (mocked via ConfigBuilder)
    3. ESP receives config and sends config_response
    4. ConfigHandler processes response
    5. DB is updated with config status
    6. WebSocket broadcasts config result
    """

    @pytest_asyncio.fixture
    async def config_handler(self):
        """Get ConfigHandler instance."""
        return get_config_handler()

    @pytest.fixture
    def mock_esp_device(self):
        """Create mock ESP device that is online."""
        device = MagicMock()
        device.id = 1
        device.device_id = "ESP_CONFIG_TEST"
        device.status = "online"
        device.name = "Config Test ESP"
        device.hardware_type = "ESP32_WROOM"
        device.firmware_version = "1.0.0"
        device.device_metadata = {}
        return device

    @pytest.mark.asyncio
    async def test_config_success_cycle(self, config_handler, mock_esp_device):
        """Full config cycle with success response updates DB."""
        topic = "kaiser/god/esp/ESP_CONFIG_TEST/config_response"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 2,
            "message": "2 sensors configured successfully",
            "correlation_id": "test-corr-123",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.mqtt.handlers.config_handler.CommandContractRepository"
            ) as mock_contract_class:
                mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                    return_value=(MagicMock(), False)
                )

                with patch(
                    "src.mqtt.handlers.config_handler.AuditLogRepository"
                ) as mock_audit_class:
                    mock_audit = MagicMock()
                    mock_audit.log_config_response = AsyncMock()
                    mock_audit_class.return_value = mock_audit

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws.broadcast = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        result = await config_handler.handle_config_ack(topic, payload)

                    # Handler should succeed
                    assert result is True

                    # Audit log should be called
                    mock_audit.log_config_response.assert_called_once()
                    call_kwargs = mock_audit.log_config_response.call_args
                    assert call_kwargs.kwargs["esp_id"] == "ESP_CONFIG_TEST"
                    assert call_kwargs.kwargs["status"] == "success"
                    assert call_kwargs.kwargs["correlation_id"] == "test-corr-123"

                    # WebSocket should broadcast
                    mock_ws.broadcast.assert_called_once()
                    ws_call = mock_ws.broadcast.call_args
                    assert ws_call.args[0] == "config_response"
                    assert ws_call.args[1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_config_partial_success_updates_failed_items(self, config_handler):
        """Partial success updates failed items in DB."""
        topic = "kaiser/god/esp/ESP_PARTIAL_TEST/config_response"
        payload = {
            "status": "partial_success",
            "type": "sensor",
            "count": 2,
            "failed_count": 1,
            "message": "2 configured, 1 failed",
            "failures": [
                {
                    "type": "sensor",
                    "gpio": 5,
                    "error_code": 1002,
                    "error": "GPIO_CONFLICT",
                    "detail": "GPIO 5 reserved by actuator (pump_1)",
                }
            ],
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.mqtt.handlers.config_handler.CommandContractRepository"
            ) as mock_contract_class:
                mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                    return_value=(MagicMock(), False)
                )

                with patch("src.mqtt.handlers.config_handler.ESPRepository") as mock_esp_repo_class:
                    mock_esp = MagicMock()
                    mock_esp.id = 1
                    mock_esp.device_id = "ESP_PARTIAL_TEST"
                    mock_esp_repo = MagicMock()
                    mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)
                    mock_esp_repo_class.return_value = mock_esp_repo

                    with patch(
                        "src.mqtt.handlers.config_handler.SensorRepository"
                    ) as mock_sensor_repo_class:
                        mock_sensor = MagicMock()
                        mock_sensor.id = 100
                        mock_sensor_repo = MagicMock()
                        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_sensor)
                        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(
                            return_value=[mock_sensor]
                        )
                        mock_sensor_repo.get_by_esp = AsyncMock(return_value=[mock_sensor])
                        mock_sensor_repo.update = AsyncMock()
                        mock_sensor_repo_class.return_value = mock_sensor_repo

                        with patch("src.mqtt.handlers.config_handler.ActuatorRepository"):
                            with patch(
                                "src.mqtt.handlers.config_handler.AuditLogRepository"
                            ) as mock_audit_class:
                                mock_audit = MagicMock()
                                mock_audit.log_config_response = AsyncMock()
                                mock_audit_class.return_value = mock_audit

                                with patch(
                                    "src.websocket.manager.WebSocketManager"
                                ) as mock_ws_class:
                                    mock_ws = AsyncMock()
                                    mock_ws.broadcast = AsyncMock()
                                    mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                                    result = await config_handler.handle_config_ack(topic, payload)

                                    assert result is True

                                    # Sensor should be updated with failed status
                                    mock_sensor_repo.update.assert_called_once()
                                    update_call = mock_sensor_repo.update.call_args
                                    assert update_call.args[0] == 100  # sensor id
                                    assert update_call.kwargs["config_status"] == "failed"
                                    assert update_call.kwargs["config_error"] == "GPIO_CONFLICT"


class TestDiscoveryApprovalOnlineFlow:
    """
    E2E Test: Device Lifecycle from Discovery to Online.

    Flow:
    1. New ESP sends heartbeat
    2. HeartbeatHandler creates device with pending_approval
    3. Admin approves device (simulated)
    4. ESP sends another heartbeat
    5. Device transitions to online
    """

    @pytest_asyncio.fixture
    async def heartbeat_handler(self):
        """Get HeartbeatHandler instance."""
        return get_heartbeat_handler()

    @pytest.fixture
    def new_device_payload(self):
        """Payload for a new device heartbeat."""
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 100,
            "heap_free": 50000,
            "wifi_rssi": -55,
            "sensor_count": 0,
            "actuator_count": 0,
        }

    @pytest.mark.asyncio
    async def test_new_device_discovery_creates_pending(
        self, heartbeat_handler, new_device_payload
    ):
        """New device heartbeat triggers discovery with pending_approval status."""
        topic = "kaiser/god/esp/ESP_BRAND_NEW/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()  # session.flush() is awaited during auto-register
            mock_db.refresh = AsyncMock()  # session.refresh() may be awaited
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                # Create a mock device that will be returned after "create"
                mock_new_device = MagicMock()
                mock_new_device.id = 99
                mock_new_device.device_id = "ESP_BRAND_NEW"
                mock_new_device.status = "pending_approval"

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=None)  # New device
                mock_repo.create = AsyncMock(return_value=mock_new_device)
                mock_repo_class.return_value = mock_repo

                with patch("src.services.esp_service._discovery_rate_limiter") as mock_limiter:
                    mock_limiter.can_discover.return_value = (True, "")
                    mock_limiter.record_discovery = MagicMock()

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws.broadcast = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        with patch.object(heartbeat_handler, "_send_heartbeat_ack", AsyncMock()):
                            result = await heartbeat_handler.handle_heartbeat(
                                topic, new_device_payload
                            )

                            assert result is True

                            # Rate limiter should be checked
                            mock_limiter.can_discover.assert_called_with("ESP_BRAND_NEW")

                            # Discovery event should be broadcast
                            mock_ws.broadcast.assert_called()
                            ws_call = mock_ws.broadcast.call_args
                            assert ws_call.args[0] == "device_discovered"
                            assert ws_call.args[1]["esp_id"] == "ESP_BRAND_NEW"

    @pytest.mark.asyncio
    async def test_approved_device_transitions_to_online(
        self, heartbeat_handler, new_device_payload
    ):
        """Approved device heartbeat transitions status to online."""
        topic = "kaiser/god/esp/ESP_APPROVED/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                # Device exists with approved status
                mock_device = MagicMock()
                mock_device.id = 1
                mock_device.device_id = "ESP_APPROVED"
                mock_device.status = "approved"  # Was approved by admin
                mock_device.name = "Approved ESP"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc) - timedelta(minutes=5)
                mock_device.zone_id = None
                mock_device.master_zone_id = None
                mock_device.kaiser_id = None

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo.update_last_seen = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"
                ) as mock_hb_repo_class:
                    mock_hb_repo = MagicMock()
                    mock_hb_repo.create = AsyncMock()
                    mock_hb_repo.log_heartbeat = AsyncMock()
                    mock_hb_repo_class.return_value = mock_hb_repo

                    with patch(
                        "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            with patch.object(
                                heartbeat_handler, "_send_heartbeat_ack", AsyncMock()
                            ):
                                result = await heartbeat_handler.handle_heartbeat(
                                    topic, new_device_payload
                                )

                                assert result is True

                                # Status should be updated to online
                                mock_repo.update_status.assert_called()
                                update_call = mock_repo.update_status.call_args
                                assert update_call.args[0] == "ESP_APPROVED"
                                assert update_call.args[1] == "online"

    @pytest.mark.asyncio
    async def test_online_device_stays_online(self, heartbeat_handler, new_device_payload):
        """Already online device stays online on heartbeat."""
        topic = "kaiser/god/esp/ESP_ONLINE/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.id = 1
                mock_device.device_id = "ESP_ONLINE"
                mock_device.status = "online"
                mock_device.name = "Online ESP"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc) - timedelta(seconds=30)
                mock_device.zone_id = "zone_1"
                mock_device.master_zone_id = "master"
                mock_device.kaiser_id = "god"

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()  # Called for all online devices
                mock_repo.update_last_seen = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"
                ) as mock_hb_repo_class:
                    mock_hb_repo = MagicMock()
                    mock_hb_repo.create = AsyncMock()
                    mock_hb_repo.log_heartbeat = AsyncMock()
                    mock_hb_repo_class.return_value = mock_hb_repo

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws.broadcast = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        with patch.object(heartbeat_handler, "_send_heartbeat_ack", AsyncMock()):
                            result = await heartbeat_handler.handle_heartbeat(
                                topic, new_device_payload
                            )

                            assert result is True

                            # update_status is called even for already online devices
                            mock_repo.update_status.assert_called()

                            # esp_health broadcast
                            mock_ws.broadcast.assert_called()


class TestNetworkPartitionRecovery:
    """
    E2E Test: Network Partition Recovery.

    Flow:
    1. Device is online
    2. Network partition occurs → LWT triggers → Device offline
    3. Network recovers → ESP reconnects → Heartbeat sent
    4. Device transitions back to online
    """

    @pytest_asyncio.fixture
    async def lwt_handler(self):
        """Get LWTHandler instance."""
        return get_lwt_handler()

    @pytest_asyncio.fixture
    async def heartbeat_handler(self):
        """Get HeartbeatHandler instance."""
        return get_heartbeat_handler()

    @pytest.fixture
    def lwt_payload(self):
        """LWT payload for unexpected disconnect."""
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

    @pytest.fixture
    def heartbeat_payload(self):
        """Heartbeat payload for reconnection."""
        return {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "uptime": 50,  # Short uptime indicates recent reboot
            "heap_free": 55000,
            "wifi_rssi": -50,
        }

    @pytest.mark.asyncio
    async def test_lwt_marks_device_offline(self, lwt_handler, lwt_payload):
        """LWT message marks online device as offline."""
        topic = "kaiser/god/esp/ESP_PARTITION/system/will"

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = "ESP_PARTITION"
                mock_device.status = "online"  # Was online before partition
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.lwt_handler.CommandContractRepository"
                ) as mock_contract_class:
                    mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                        return_value=(MagicMock(), False)
                    )

                    with patch(
                        "src.mqtt.handlers.lwt_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            result = await lwt_handler.handle_lwt(topic, lwt_payload)

                            assert result is True

                            # Status should be updated to offline
                            mock_repo.update_status.assert_called_once_with(
                                "ESP_PARTITION", "offline"
                            )

                            # WebSocket should broadcast offline status
                            mock_ws.broadcast.assert_called()
                            ws_call = mock_ws.broadcast.call_args
                            assert ws_call.args[0] == "esp_health"
                            assert ws_call.args[1]["status"] == "offline"
                            assert ws_call.args[1]["source"] == "lwt"

    @pytest.mark.asyncio
    async def test_reconnect_heartbeat_brings_device_online(
        self, heartbeat_handler, heartbeat_payload
    ):
        """Heartbeat after partition recovery brings device back online."""
        topic = "kaiser/god/esp/ESP_RECOVERED/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                # Device was offline (from LWT)
                mock_device = MagicMock()
                mock_device.id = 1
                mock_device.device_id = "ESP_RECOVERED"
                mock_device.status = "offline"  # Was marked offline by LWT
                mock_device.name = "Recovered ESP"
                mock_device.device_metadata = {
                    "last_disconnect": {
                        "source": "lwt",
                        "reason": "unexpected_disconnect",
                    }
                }
                mock_device.last_seen = datetime.now(timezone.utc) - timedelta(minutes=2)
                mock_device.zone_id = "zone_1"
                mock_device.zone_name = "Test Zone"  # Required by _update_esp_metadata zone resync
                mock_device.master_zone_id = "master"
                mock_device.kaiser_id = "god"
                mock_device.ip_address = (
                    None  # Explicitly set to avoid MagicMock attribute side-effects
                )

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo.update_last_seen = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"
                ) as mock_hb_repo_class:
                    mock_hb_repo = MagicMock()
                    mock_hb_repo.create = AsyncMock()
                    mock_hb_repo.log_heartbeat = AsyncMock()
                    mock_hb_repo_class.return_value = mock_hb_repo

                    with patch(
                        "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            with patch.object(
                                heartbeat_handler, "_send_heartbeat_ack", AsyncMock()
                            ):
                                result = await heartbeat_handler.handle_heartbeat(
                                    topic, heartbeat_payload
                                )

                                assert result is True

                                # Status should be updated back to online
                                mock_repo.update_status.assert_called()
                                update_call = mock_repo.update_status.call_args
                                assert update_call.args[0] == "ESP_RECOVERED"
                                assert update_call.args[1] == "online"

    @pytest.mark.asyncio
    async def test_reconnect_heartbeat_starts_adoption_phase(
        self, heartbeat_handler, heartbeat_payload
    ):
        """Reconnect triggers explicit ADOPTING phase before delta evaluation."""
        topic = "kaiser/god/esp/ESP_ADOPT/system/heartbeat"

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.rollback = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.id = 1
                mock_device.device_id = "ESP_ADOPT"
                mock_device.status = "offline"
                mock_device.name = "Adoption ESP"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc) - timedelta(minutes=3)
                mock_device.zone_id = "zone_1"
                mock_device.zone_name = "Test Zone"
                mock_device.master_zone_id = "master"
                mock_device.kaiser_id = "god"
                mock_device.ip_address = None

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo.update_last_seen = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"
                ) as mock_hb_repo_class:
                    mock_hb_repo = MagicMock()
                    mock_hb_repo.log_heartbeat = AsyncMock()
                    mock_hb_repo_class.return_value = mock_hb_repo

                    with patch(
                        "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            mock_adoption = MagicMock()
                            mock_adoption.start_reconnect_cycle = AsyncMock()
                            with patch(
                                "src.mqtt.handlers.heartbeat_handler.get_state_adoption_service",
                                return_value=mock_adoption,
                            ):
                                with patch.object(
                                    heartbeat_handler, "_send_heartbeat_ack", AsyncMock()
                                ):
                                    with patch.object(
                                        heartbeat_handler,
                                        "_complete_adoption_and_trigger_reconnect_eval",
                                        AsyncMock(),
                                    ):
                                        with patch(
                                            "src.mqtt.handlers.heartbeat_handler.asyncio.create_task",
                                            return_value=MagicMock(),
                                        ):
                                            result = await heartbeat_handler.handle_heartbeat(
                                                topic, heartbeat_payload
                                            )

                                            assert result is True
                                            mock_adoption.start_reconnect_cycle.assert_called_once()
                                            # Reconnect phase must be visible as adopting in WS.
                                            reconnect_calls = [
                                                c
                                                for c in mock_ws.broadcast.call_args_list
                                                if c.args and c.args[0] == "esp_reconnect_phase"
                                            ]
                                            assert (
                                                reconnect_calls
                                            ), "esp_reconnect_phase not broadcasted"
                                            phase_payload = reconnect_calls[0].args[1]
                                            assert phase_payload["esp_id"] == "ESP_ADOPT"
                                            assert phase_payload["phase"] == "adopting"
                                            assert "offline_seconds" in phase_payload

    @pytest.mark.asyncio
    async def test_full_partition_recovery_cycle(
        self, lwt_handler, heartbeat_handler, lwt_payload, heartbeat_payload
    ):
        """Full cycle: online → LWT → offline → heartbeat → online."""
        esp_id = "ESP_FULL_CYCLE"
        lwt_topic = f"kaiser/god/esp/{esp_id}/system/will"
        heartbeat_topic = f"kaiser/god/esp/{esp_id}/system/heartbeat"

        # Track status changes
        status_history = []

        def track_status_update(device_id, new_status):
            status_history.append(new_status)

        # Step 1: Device is online, LWT arrives
        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_lwt_session:
            mock_lwt_result = MagicMock()
            mock_lwt_result.scalar_one_or_none.return_value = None
            mock_lwt_result.scalars.return_value.all.return_value = []
            mock_lwt_db = MagicMock()
            mock_lwt_db.execute = AsyncMock(return_value=mock_lwt_result)
            mock_lwt_db.commit = AsyncMock()
            mock_lwt_db.flush = AsyncMock()
            mock_lwt_db.refresh = AsyncMock()
            mock_lwt_session.return_value.__aenter__ = AsyncMock(return_value=mock_lwt_db)
            mock_lwt_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = esp_id
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)

                def lwt_update_status(device_id, status):
                    track_status_update(device_id, status)
                    mock_device.status = status

                mock_repo.update_status = AsyncMock(side_effect=lwt_update_status)
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.lwt_handler.CommandContractRepository"
                ) as mock_contract_class:
                    mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                        return_value=(MagicMock(), False)
                    )

                    with patch(
                        "src.mqtt.handlers.lwt_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            lwt_result = await lwt_handler.handle_lwt(lwt_topic, lwt_payload)
                            assert lwt_result is True

        assert "offline" in status_history

        # Step 2: Device reconnects with heartbeat
        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session") as mock_hb_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_hb_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_hb_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.heartbeat_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.id = 1
                mock_device.device_id = esp_id
                mock_device.status = "offline"  # Now offline from LWT
                mock_device.name = "Full Cycle ESP"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc) - timedelta(minutes=1)
                mock_device.zone_id = "zone_1"
                mock_device.master_zone_id = "master"
                mock_device.kaiser_id = "god"

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)

                def hb_update_status(device_id, status, last_seen=None):
                    track_status_update(device_id, status)

                mock_repo.update_status = AsyncMock(side_effect=hb_update_status)
                mock_repo.update_last_seen = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch(
                    "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository"
                ) as mock_hb_repo_class:
                    mock_hb_repo = MagicMock()
                    mock_hb_repo.create = AsyncMock()
                    mock_hb_repo.log_heartbeat = AsyncMock()
                    mock_hb_repo_class.return_value = mock_hb_repo

                    with patch(
                        "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                    ) as mock_audit_class:
                        mock_audit = MagicMock()
                        mock_audit.log_device_event = AsyncMock()
                        mock_audit_class.return_value = mock_audit

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            with patch.object(
                                heartbeat_handler, "_send_heartbeat_ack", AsyncMock()
                            ):
                                hb_result = await heartbeat_handler.handle_heartbeat(
                                    heartbeat_topic, heartbeat_payload
                                )
                                assert hb_result is True

        # Verify full cycle
        assert status_history == ["offline", "online"]


class TestCrossHandlerInteraction:
    """
    Test interactions between different MQTT handlers.
    """

    @pytest.mark.asyncio
    async def test_config_response_after_heartbeat_approval(self):
        """Config response works after device is approved via heartbeat."""
        esp_id = "ESP_CROSS_TEST"

        # Simulate: Device was discovered, approved, now sends config response
        config_handler = get_config_handler()
        config_topic = f"kaiser/god/esp/{esp_id}/config_response"
        config_payload = {
            "status": "success",
            "type": "sensor",
            "count": 3,
            "message": "3 sensors configured",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.mqtt.handlers.config_handler.CommandContractRepository"
            ) as mock_contract_class:
                mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                    return_value=(MagicMock(), False)
                )

                with patch(
                    "src.mqtt.handlers.config_handler.AuditLogRepository"
                ) as mock_audit_class:
                    mock_audit = MagicMock()
                    mock_audit.log_config_response = AsyncMock()
                    mock_audit_class.return_value = mock_audit

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws.broadcast = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        result = await config_handler.handle_config_ack(
                            config_topic, config_payload
                        )

                        assert result is True

                        # WebSocket should broadcast config_response event
                        ws_calls = mock_ws.broadcast.call_args_list
                        assert len(ws_calls) == 1
                        assert ws_calls[0].args[0] == "config_response"

    @pytest.mark.asyncio
    async def test_lwt_after_config_error_doesnt_conflict(self):
        """LWT arriving after config error doesn't cause conflicts."""
        esp_id = "ESP_ERROR_LWT"

        # First: Config error occurs
        config_handler = get_config_handler()
        config_topic = f"kaiser/god/esp/{esp_id}/config_response"
        config_payload = {
            "status": "error",
            "type": "sensor",
            "count": 0,
            "message": "Configuration failed",
            "error_code": "GPIO_CONFLICT",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.mqtt.handlers.config_handler.CommandContractRepository"
            ) as mock_contract_class:
                mock_contract_class.return_value.upsert_terminal_event_authority = AsyncMock(
                    return_value=(MagicMock(), False)
                )

                with patch(
                    "src.mqtt.handlers.config_handler.AuditLogRepository"
                ) as mock_audit_class:
                    mock_audit = MagicMock()
                    mock_audit.log_config_response = AsyncMock()
                    mock_audit_class.return_value = mock_audit

                    with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                        mock_ws = AsyncMock()
                        mock_ws.broadcast = AsyncMock()
                        mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                        config_result = await config_handler.handle_config_ack(
                            config_topic, config_payload
                        )
                        assert config_result is True

        # Then: LWT arrives (device disconnected during error handling)
        lwt_handler = get_lwt_handler()
        lwt_topic = f"kaiser/god/esp/{esp_id}/system/will"
        lwt_payload = {
            "status": "offline",
            "reason": "unexpected_disconnect",
        }

        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_db = MagicMock()
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository") as mock_repo_class:
                mock_device = MagicMock()
                mock_device.device_id = esp_id
                mock_device.status = "online"
                mock_device.device_metadata = {}
                mock_device.last_seen = datetime.now(timezone.utc)

                mock_repo = MagicMock()
                mock_repo.get_by_device_id = AsyncMock(return_value=mock_device)
                mock_repo.update_status = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit_class:
                    mock_audit = MagicMock()
                    mock_audit.log_device_event = AsyncMock()
                    mock_audit_class.return_value = mock_audit

                    with patch(
                        "src.mqtt.handlers.lwt_handler.CommandContractRepository"
                    ) as mock_contract_class:
                        mock_contract_class.return_value.upsert_terminal_event_authority = (
                            AsyncMock(return_value=(None, False))
                        )

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws.broadcast = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            lwt_result = await lwt_handler.handle_lwt(lwt_topic, lwt_payload)

                            # Both handlers should succeed independently
                            assert lwt_result is True
                            mock_repo.update_status.assert_called_once_with(esp_id, "offline")
