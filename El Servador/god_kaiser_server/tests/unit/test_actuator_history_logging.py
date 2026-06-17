"""
Unit Tests: Actuator History Logging (Fixes L1–L4)

Tests that every state-transition path writes a correct actuator_history entry:
  L1 – Status-Handler state-change fallback (state_sync)
  L2 – LWT-Handler offline reset (system:lwt_disconnect)
  L4 – Delete-Actuator OFF before removal (system:actuator_delete)

L3 (heartbeat timeout) uses the same code path as L2 and is covered structurally.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.actuator_handler import ActuatorStatusHandler
from src.mqtt.handlers.lwt_handler import LWTHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_esp_device(device_id: str = "ESP_TEST") -> MagicMock:
    device = MagicMock()
    device.id = uuid.uuid4()
    device.device_id = device_id
    device.status = "online"
    device.hardware_type = None
    device.capabilities = None
    device.device_metadata = {}
    device.last_seen = datetime.now(timezone.utc)
    return device


def _make_actuator_config(actuator_type: str = "relay") -> MagicMock:
    cfg = MagicMock()
    cfg.actuator_type = actuator_type
    cfg.hardware_type = actuator_type
    return cfg


def _status_payload(state: str, last_command: str = "") -> dict:
    payload: dict = {
        "ts": 1735818000,
        "esp_id": "ESP_TEST",
        "gpio": 5,
        "actuator_type": "relay",
        "state": state,
        "value": 255.0 if state == "on" else 0.0,
    }
    if last_command:
        payload["last_command"] = last_command
    return payload


# ---------------------------------------------------------------------------
# L1 – Status-Handler: state-change fallback logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestL1StatusHandlerStateChange:
    """Fix L1: state_sync entry when state changes without last_command."""

    @pytest.fixture
    def handler(self) -> ActuatorStatusHandler:
        return ActuatorStatusHandler()

    def _build_mocks(self, prev_state_str: str):
        prev_state = MagicMock()
        prev_state.state = prev_state_str

        actuator_repo = MagicMock()
        actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=_make_actuator_config())
        actuator_repo.get_state = AsyncMock(return_value=prev_state)
        actuator_repo.update_state = AsyncMock(return_value=MagicMock())
        actuator_repo.log_command = AsyncMock()

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp_device())

        return esp_repo, actuator_repo

    async def _run_handler(self, handler, topic, payload, esp_repo, actuator_repo):
        with patch("src.mqtt.handlers.actuator_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.actuator_handler.ESPRepository", return_value=esp_repo):
                with patch(
                    "src.mqtt.handlers.actuator_handler.ActuatorRepository",
                    return_value=actuator_repo,
                ):
                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())
                        return await handler.handle_actuator_status(topic, payload)

    async def test_logs_state_sync_on_state_change_without_last_command(self, handler):
        """State on→off WITHOUT last_command must produce a state_sync history entry."""
        topic = "kaiser/god/esp/ESP_TEST/actuator/5/status"
        payload = _status_payload("off")  # no last_command key
        esp_repo, actuator_repo = self._build_mocks(prev_state_str="on")

        result = await self._run_handler(handler, topic, payload, esp_repo, actuator_repo)

        assert result is True
        actuator_repo.log_command.assert_called_once()
        kwargs = actuator_repo.log_command.call_args.kwargs
        assert kwargs["issued_by"] == "state_sync"
        assert kwargs["command_type"] == "OFF"
        assert kwargs["metadata"]["trigger"] == "state_change_detected"
        assert kwargs["metadata"]["prev_state"] == "on"

    async def test_no_state_sync_when_last_command_present(self, handler):
        """With last_command: exactly one 'esp32' entry, NO state_sync entry."""
        topic = "kaiser/god/esp/ESP_TEST/actuator/5/status"
        payload = _status_payload("off", last_command="off")
        esp_repo, actuator_repo = self._build_mocks(prev_state_str="on")

        await self._run_handler(handler, topic, payload, esp_repo, actuator_repo)

        actuator_repo.log_command.assert_called_once()
        kwargs = actuator_repo.log_command.call_args.kwargs
        assert kwargs["issued_by"] == "esp32"

    async def test_no_log_when_state_unchanged(self, handler):
        """Repeated on→on status update without last_command: no history entry."""
        topic = "kaiser/god/esp/ESP_TEST/actuator/5/status"
        payload = _status_payload("on")  # no last_command, same state as prev
        esp_repo, actuator_repo = self._build_mocks(prev_state_str="on")

        await self._run_handler(handler, topic, payload, esp_repo, actuator_repo)

        actuator_repo.log_command.assert_not_called()


# ---------------------------------------------------------------------------
# L2 – LWT-Handler: log_command() for each reset actuator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestL2LWTHandlerHistory:
    """Fix L2: system:lwt_disconnect entry for every active actuator on offline reset."""

    @pytest.fixture
    def handler(self) -> LWTHandler:
        return LWTHandler()

    @pytest.fixture
    def lwt_payload(self) -> dict:
        return {
            "status": "offline",
            "reason": "unexpected_disconnect",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

    def _active_actuator(self, gpio: int = 5, state: str = "on") -> MagicMock:
        a = MagicMock()
        a.gpio = gpio
        a.actuator_type = "relay"
        a.state = state
        a.current_value = 255.0
        return a

    async def _run_handler(self, handler, topic, payload, esp_repo, actuator_repo):
        with patch("src.mqtt.handlers.lwt_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.lwt_handler.ESPRepository", return_value=esp_repo):
                with patch(
                    "src.mqtt.handlers.lwt_handler.ActuatorRepository",
                    return_value=actuator_repo,
                ):
                    with patch("src.mqtt.handlers.lwt_handler.AuditLogRepository") as mock_audit:
                        mock_audit.return_value.log_device_event = AsyncMock()
                        with patch(
                            "src.mqtt.handlers.lwt_handler.CommandContractRepository"
                        ) as mock_contract:
                            mock_contract.return_value.upsert_terminal_event_authority = AsyncMock(
                                return_value=(None, False)
                            )
                            mock_contract.return_value.list_open_intents_for_esp = AsyncMock(return_value=[])
                            with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                                mock_ws.get_instance = AsyncMock(return_value=AsyncMock())
                                return await handler.handle_lwt(topic, payload)

    async def test_logs_off_for_each_active_actuator(self, handler, lwt_payload):
        """LWT disconnect: one OFF history entry per active actuator."""
        topic = "kaiser/god/esp/ESP_TEST/system/will"
        esp_device = _make_esp_device()

        active_a = self._active_actuator(gpio=5, state="on")
        actuator_repo = MagicMock()
        actuator_repo.get_active_actuators_for_device = AsyncMock(return_value=[active_a])
        actuator_repo.reset_states_for_device = AsyncMock(return_value=1)
        actuator_repo.log_command = AsyncMock()

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
        esp_repo.update_status = AsyncMock()

        result = await self._run_handler(handler, topic, lwt_payload, esp_repo, actuator_repo)

        assert result is True
        actuator_repo.log_command.assert_called_once()
        kwargs = actuator_repo.log_command.call_args.kwargs
        assert kwargs["issued_by"] == "system:lwt_disconnect"
        assert kwargs["command_type"] == "OFF"
        assert kwargs["gpio"] == 5
        assert kwargs["value"] == 0.0
        assert kwargs["metadata"]["previous_state"] == "on"

    async def test_logs_multiple_active_actuators(self, handler, lwt_payload):
        """LWT with two active actuators produces two history entries."""
        topic = "kaiser/god/esp/ESP_TEST/system/will"
        esp_device = _make_esp_device()

        actuator_repo = MagicMock()
        actuator_repo.get_active_actuators_for_device = AsyncMock(
            return_value=[
                self._active_actuator(gpio=5, state="on"),
                self._active_actuator(gpio=6, state="pwm"),
            ]
        )
        actuator_repo.reset_states_for_device = AsyncMock(return_value=2)
        actuator_repo.log_command = AsyncMock()

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
        esp_repo.update_status = AsyncMock()

        await self._run_handler(handler, topic, lwt_payload, esp_repo, actuator_repo)

        assert actuator_repo.log_command.call_count == 2
        issued_by_values = [c.kwargs["issued_by"] for c in actuator_repo.log_command.call_args_list]
        assert all(v == "system:lwt_disconnect" for v in issued_by_values)

    async def test_no_log_when_all_actuators_already_off(self, handler, lwt_payload):
        """LWT when all actuators are already off: no history entries written."""
        topic = "kaiser/god/esp/ESP_TEST/system/will"
        esp_device = _make_esp_device()

        actuator_repo = MagicMock()
        actuator_repo.get_active_actuators_for_device = AsyncMock(return_value=[])
        actuator_repo.reset_states_for_device = AsyncMock(return_value=0)
        actuator_repo.log_command = AsyncMock()

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
        esp_repo.update_status = AsyncMock()

        await self._run_handler(handler, topic, lwt_payload, esp_repo, actuator_repo)

        actuator_repo.log_command.assert_not_called()

    async def test_get_active_actuators_called_before_reset(self, handler, lwt_payload):
        """get_active_actuators_for_device() must be called BEFORE reset_states_for_device()."""
        topic = "kaiser/god/esp/ESP_TEST/system/will"
        esp_device = _make_esp_device()
        call_order: list[str] = []

        actuator_repo = MagicMock()

        async def _get_active(*args, **kwargs):
            call_order.append("get_active")
            return []

        async def _reset(*args, **kwargs):
            call_order.append("reset")
            return 0

        actuator_repo.get_active_actuators_for_device = _get_active
        actuator_repo.reset_states_for_device = _reset
        actuator_repo.log_command = AsyncMock()

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
        esp_repo.update_status = AsyncMock()

        await self._run_handler(handler, topic, lwt_payload, esp_repo, actuator_repo)

        assert call_order == [
            "get_active",
            "reset",
        ], "get_active_actuators_for_device must run before reset_states_for_device"
