"""
Unit Tests: AUT-60 Cross-ESP Command-Readiness-Gate (CONFIG_PENDING_AFTER_RESET)

Tests:
- ESPDevice.config_pending property (derives from device_metadata.system_state)
- LogicEngine._config_pending_skip backoff cache
- LogicEngine.invalidate_config_pending_backoff()
- Modern path (_execute_actions): config_pending ESP skipped, rejected intent-outcome generated
- Legacy path (_execute_action_legacy): config_pending ESP skipped
- Regression: is_online=True, config_pending=False -> command dispatched
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models.esp import ESPDevice
from src.services.logic_engine import (
    LogicEngine,
    _CONFIG_PENDING_BACKOFF_SECONDS,
    _OFFLINE_BACKOFF_SECONDS,
)


@pytest.fixture
def engine():
    """Minimal LogicEngine instance for unit testing the config_pending gate."""
    logic_repo = MagicMock()
    actuator_service = MagicMock()
    ws_manager = AsyncMock()
    instance = LogicEngine(
        logic_repo=logic_repo,
        actuator_service=actuator_service,
        websocket_manager=ws_manager,
        condition_evaluators=[],
        action_executors=[],
    )
    return instance


class TestESPDeviceConfigPending:
    """ESPDevice.config_pending property derives from device_metadata.system_state."""

    def test_config_pending_true_when_state_is_config_pending(self):
        device = ESPDevice(
            device_id="ESP_TEST_CP",
            hardware_type="ESP32_WROOM",
            status="online",
            capabilities={},
            device_metadata={"system_state": "CONFIG_PENDING_AFTER_RESET"},
        )
        assert device.config_pending is True

    def test_config_pending_false_when_operational(self):
        device = ESPDevice(
            device_id="ESP_TEST_OP",
            hardware_type="ESP32_WROOM",
            status="online",
            capabilities={},
            device_metadata={"system_state": "OPERATIONAL"},
        )
        assert device.config_pending is False

    def test_config_pending_false_when_no_system_state(self):
        device = ESPDevice(
            device_id="ESP_TEST_NS",
            hardware_type="ESP32_WROOM",
            status="online",
            capabilities={},
            device_metadata={},
        )
        assert device.config_pending is False

    def test_config_pending_false_when_no_metadata(self):
        device = ESPDevice(
            device_id="ESP_TEST_NM",
            hardware_type="ESP32_WROOM",
            status="online",
            capabilities={},
            device_metadata={},
        )
        assert device.config_pending is False

    def test_config_pending_false_for_other_states(self):
        for state in ("BOOT", "WIFI_SETUP", "SAFE_MODE", "ERROR", "UNKNOWN"):
            device = ESPDevice(
                device_id=f"ESP_TEST_{state}",
                hardware_type="ESP32_WROOM",
                status="online",
                capabilities={},
                device_metadata={"system_state": state},
            )
            assert device.config_pending is False, f"Expected False for state={state}"


class TestInvalidateConfigPendingBackoff:
    """LogicEngine.invalidate_config_pending_backoff() clears _config_pending_skip correctly."""

    def test_clears_existing_cache_entry(self, engine):
        esp_id = "ESP_CP_001"
        engine._config_pending_skip[esp_id] = datetime.now(timezone.utc) + timedelta(seconds=60)

        engine.invalidate_config_pending_backoff(esp_id)

        assert esp_id not in engine._config_pending_skip

    def test_noop_for_unknown_esp_id(self, engine):
        assert len(engine._config_pending_skip) == 0
        engine.invalidate_config_pending_backoff("ESP_UNKNOWN_CP")
        assert len(engine._config_pending_skip) == 0

    def test_only_clears_targeted_esp(self, engine):
        esp_a = "ESP_CP_A"
        esp_b = "ESP_CP_B"
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        engine._config_pending_skip[esp_a] = future
        engine._config_pending_skip[esp_b] = future

        engine.invalidate_config_pending_backoff(esp_a)

        assert esp_a not in engine._config_pending_skip
        assert esp_b in engine._config_pending_skip

    def test_does_not_affect_offline_skip(self, engine):
        esp_id = "ESP_CP_OL"
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        engine._offline_esp_skip[esp_id] = future
        engine._config_pending_skip[esp_id] = future

        engine.invalidate_config_pending_backoff(esp_id)

        assert esp_id not in engine._config_pending_skip
        assert esp_id in engine._offline_esp_skip


class TestConfigPendingBackoffTTL:
    """_CONFIG_PENDING_BACKOFF_SECONDS constant and TTL behaviour."""

    def test_backoff_constant_is_15_seconds(self):
        assert _CONFIG_PENDING_BACKOFF_SECONDS == 15

    def test_active_cache_entry_blocks_before_expiry(self, engine):
        esp_id = "ESP_CP_TTL"
        skip_until = datetime.now(timezone.utc) + timedelta(seconds=_CONFIG_PENDING_BACKOFF_SECONDS)
        engine._config_pending_skip[esp_id] = skip_until

        assert datetime.now(timezone.utc) < engine._config_pending_skip[esp_id]

    def test_expired_cache_entry_is_past(self, engine):
        esp_id = "ESP_CP_TTL"
        engine._config_pending_skip[esp_id] = datetime.now(timezone.utc) - timedelta(seconds=1)

        assert datetime.now(timezone.utc) >= engine._config_pending_skip[esp_id]


class TestModernPathConfigPendingGate:
    """_execute_actions skips actuator dispatch and records rejected outcome when config_pending."""

    @pytest.mark.asyncio
    async def test_config_pending_esp_skipped(self, engine):
        """is_online=True, config_pending=True -> action NOT dispatched, rejected outcome."""
        esp_id = "ESP_CP_MOD"
        rule_id = uuid.uuid4()
        actions = [{"type": "actuator_command", "esp_id": esp_id, "gpio": 26, "command": "ON"}]
        trigger_data = {"timestamp": datetime.now(timezone.utc).isoformat()}

        mock_esp = MagicMock()
        mock_esp.is_online = True
        mock_esp.config_pending = True
        mock_esp.device_id = esp_id

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()
        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            result = await engine._execute_actions(
                actions=actions,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_cp",
                session=mock_session,
            )

        assert len(result["action_results"]) == 1
        assert result["action_results"][0]["success"] is False
        assert "CONFIG_PENDING_AFTER_RESET" in result["action_results"][0]["message"]
        assert result["action_results"][0]["data"]["reason"] == "config_pending"

    @pytest.mark.asyncio
    async def test_online_not_config_pending_dispatched(self, engine):
        """is_online=True, config_pending=False -> action dispatched (regression safety)."""
        esp_id = "ESP_OP_MOD"
        rule_id = uuid.uuid4()
        actions = [{"type": "actuator_command", "esp_id": esp_id, "gpio": 26, "command": "ON"}]
        trigger_data = {"timestamp": datetime.now(timezone.utc).isoformat()}

        mock_esp = MagicMock()
        mock_esp.is_online = True
        mock_esp.config_pending = False
        mock_esp.device_id = esp_id

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()
        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        mock_executor = MagicMock()
        mock_executor.supports = MagicMock(return_value=True)
        mock_action_result = MagicMock()
        mock_action_result.success = True
        mock_action_result.message = "OK"
        mock_action_result.data = {"noop": False}
        mock_executor.execute = AsyncMock(return_value=mock_action_result)
        engine.action_executors = [mock_executor]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            result = await engine._execute_actions(
                actions=actions,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_op",
                session=mock_session,
            )

        mock_executor.execute.assert_awaited_once()
        assert any(r["success"] is True for r in result["action_results"])

    @pytest.mark.asyncio
    async def test_config_pending_sets_backoff(self, engine):
        """After config_pending skip, backoff cache is populated."""
        esp_id = "ESP_CP_BO"
        rule_id = uuid.uuid4()
        actions = [{"type": "actuator_command", "esp_id": esp_id, "gpio": 26}]
        trigger_data = {}

        mock_esp = MagicMock()
        mock_esp.is_online = True
        mock_esp.config_pending = True

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()
        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            await engine._execute_actions(
                actions=actions,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_bo",
                session=mock_session,
            )

        assert esp_id in engine._config_pending_skip
        assert engine._config_pending_skip[esp_id] > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_offline_esp_still_skipped(self, engine):
        """is_online=False -> still skipped (regression: offline gate preserved)."""
        esp_id = "ESP_OFF_REG"
        rule_id = uuid.uuid4()
        actions = [{"type": "actuator_command", "esp_id": esp_id, "gpio": 26}]
        trigger_data = {}

        mock_esp = MagicMock()
        mock_esp.is_online = False
        mock_esp.config_pending = False

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()
        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            result = await engine._execute_actions(
                actions=actions,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_off",
                session=mock_session,
            )

        assert esp_id in engine._offline_esp_skip
        assert len(result["action_results"]) == 0


class TestLegacyPathConfigPendingGate:
    """_execute_action_legacy skips actuator dispatch when config_pending."""

    @pytest.mark.asyncio
    async def test_config_pending_esp_skipped_legacy(self, engine):
        """Legacy path: is_online=True, config_pending=True -> return early, no command."""
        esp_id = "ESP_CP_LEG"
        rule_id = uuid.uuid4()
        action = {"type": "actuator_command", "esp_id": esp_id, "gpio": 26, "command": "ON"}
        trigger_data = {}

        mock_esp = MagicMock()
        mock_esp.is_online = True
        mock_esp.config_pending = True

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()

        async def mock_get_session():
            yield mock_session

        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        engine.actuator_service.send_command = AsyncMock()

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch("src.services.logic_engine.get_session", return_value=mock_get_session()),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            await engine._execute_action_legacy(
                action=action,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_leg",
            )

        engine.actuator_service.send_command.assert_not_awaited()
        assert esp_id in engine._config_pending_skip

    @pytest.mark.asyncio
    async def test_operational_esp_dispatched_legacy(self, engine):
        """Legacy path: is_online=True, config_pending=False -> command dispatched."""
        esp_id = "ESP_OP_LEG"
        rule_id = uuid.uuid4()
        action = {
            "type": "actuator_command",
            "esp_id": esp_id,
            "gpio": 26,
            "command": "ON",
            "value": 1.0,
        }
        trigger_data = {}

        mock_esp = MagicMock()
        mock_esp.is_online = True
        mock_esp.config_pending = False

        mock_repo = AsyncMock()
        mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_session = AsyncMock()

        async def mock_get_session():
            yield mock_session

        mock_adoption = AsyncMock()
        mock_adoption.is_adoption_completed = AsyncMock(return_value=True)

        cmd_result = MagicMock()
        cmd_result.success = True
        engine.actuator_service.send_command = AsyncMock(return_value=cmd_result)

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
            patch("src.services.logic_engine.get_session", return_value=mock_get_session()),
            patch(
                "src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption
            ),
        ):
            await engine._execute_action_legacy(
                action=action,
                trigger_data=trigger_data,
                rule_id=rule_id,
                rule_name="test_rule_leg_ok",
            )

        engine.actuator_service.send_command.assert_awaited_once()
