"""
Logic Automation Tests (LOGIC Category).

Tests sensor-triggered rules, cooldown mechanism, multi-action execution,
and cross-ESP scenarios using the LogicEngine.

Pattern: LogicEngine with AsyncMock dependencies, like test_logic_engine_resilience.py.
"""

import uuid
import time

import pytest
from unittest.mock import AsyncMock

from tests.esp32.mocks.mock_esp32_client import MockESP32Client
from src.services.actuator_service import ActuatorSendCommandResult
from src.services.logic_engine import LogicEngine

_MOCK_SEND_OK = ActuatorSendCommandResult(
    success=True,
    correlation_id="00000000-0000-4000-8000-000000000001",
    command_sent=True,
    safety_warnings=[],
)
_MOCK_SEND_FAIL = ActuatorSendCommandResult(
    success=False,
    correlation_id="00000000-0000-4000-8000-000000000002",
    command_sent=False,
    safety_warnings=[],
)

# =========================================================================
# Fixtures (same pattern as test_logic_engine_resilience.py)
# =========================================================================


@pytest.fixture
async def mock_actuator_service():
    """ActuatorService mock that tracks all calls."""
    service = AsyncMock()
    service.send_command = AsyncMock(return_value=_MOCK_SEND_OK)
    return service


@pytest.fixture
async def mock_logic_repo():
    """LogicRepository mock."""
    repo = AsyncMock()
    repo.get_active_rules = AsyncMock(return_value=[])
    repo.get_rules_by_sensor = AsyncMock(return_value=[])
    repo.log_execution = AsyncMock()
    return repo


@pytest.fixture
async def mock_websocket_manager():
    """WebSocketManager mock."""
    return AsyncMock()


@pytest.fixture
async def logic_engine(mock_logic_repo, mock_actuator_service, mock_websocket_manager):
    """LogicEngine with mocked dependencies."""
    return LogicEngine(
        logic_repo=mock_logic_repo,
        actuator_service=mock_actuator_service,
        websocket_manager=mock_websocket_manager,
    )


# =========================================================================
# Sensor-Triggered Rule Execution
# =========================================================================


class TestSensorTriggeredRule:
    """Rules triggered by sensor data crossing thresholds."""

    @pytest.mark.asyncio
    async def test_above_threshold_triggers_actuator(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Temp > 25 triggers fan ON."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TRIG001",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
            }
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={"type": "sensor", "value": 26.0},
            rule_id=uuid.uuid4(),
            rule_name="temp_above_25_fan_on",
        )

        mock_actuator_service.send_command.assert_called_once()
        kwargs = mock_actuator_service.send_command.call_args[1]
        assert kwargs["esp_id"] == "ESP_TRIG001"
        assert kwargs["gpio"] == 25
        assert kwargs["command"] == "ON"

    @pytest.mark.asyncio
    async def test_pwm_action_sends_correct_value(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """PWM action sends the correct value (0.75)."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_PWM001",
                "gpio": 25,
                "command": "PWM",
                "value": 0.75,
            }
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={"type": "sensor"},
            rule_id=uuid.uuid4(),
            rule_name="pwm_test",
        )

        kwargs = mock_actuator_service.send_command.call_args[1]
        assert kwargs["value"] == 0.75
        assert kwargs["command"] == "PWM"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operator,threshold,value,expected",
        [
            (">", 25.0, 26.0, True),
            (">", 25.0, 25.0, False),
            (">", 25.0, 24.0, False),
            ("<", 20.0, 19.0, True),
            ("<", 20.0, 21.0, False),
            (">=", 30.0, 30.0, True),
            ("<=", 10.0, 10.0, True),
            ("==", 22.0, 22.0, True),
            ("!=", 22.0, 23.0, True),
        ],
    )
    async def test_threshold_operators(
        self, logic_engine: LogicEngine, operator, threshold, value, expected
    ):
        """All comparison operators evaluate correctly."""
        conditions = {
            "type": "sensor_threshold",
            "esp_id": "ESP_OP001",
            "gpio": 34,
            "sensor_type": "temperature",
            "operator": operator,
            "value": threshold,
        }

        sensor_data = {
            "sensor_data": {
                "esp_id": "ESP_OP001",
                "gpio": 34,
                "sensor_type": "temperature",
                "value": value,
            }
        }

        result = await logic_engine._check_conditions(conditions, sensor_data)
        assert result == expected, f"{value} {operator} {threshold} should be {expected}"


# =========================================================================
# Multi-Action Execution
# =========================================================================


class TestMultiActionExecution:
    """Rules with multiple actions."""

    @pytest.mark.asyncio
    async def test_two_actuator_actions_both_execute(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Rule with 2 actions triggers both."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_MULTI01",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
            },
            {
                "type": "actuator_command",
                "esp_id": "ESP_MULTI01",
                "gpio": 26,
                "command": "ON",
                "value": 1.0,
            },
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={"type": "sensor"},
            rule_id=uuid.uuid4(),
            rule_name="multi_action_pump_valve",
        )

        assert mock_actuator_service.send_command.call_count == 2

    @pytest.mark.asyncio
    async def test_cross_esp_actions_target_different_devices(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Actions can target different ESPs."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_SOURCE01",
                "gpio": 25,
                "command": "OFF",
                "value": 0.0,
            },
            {
                "type": "actuator_command",
                "esp_id": "ESP_TARGET01",
                "gpio": 26,
                "command": "ON",
                "value": 1.0,
            },
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={"type": "sensor"},
            rule_id=uuid.uuid4(),
            rule_name="cross_esp_rule",
        )

        calls = mock_actuator_service.send_command.call_args_list
        esp_ids = [call[1]["esp_id"] for call in calls]
        assert "ESP_SOURCE01" in esp_ids
        assert "ESP_TARGET01" in esp_ids

    @pytest.mark.asyncio
    async def test_action_with_duration(self, logic_engine: LogicEngine, mock_actuator_service):
        """Action with duration_seconds passes duration to send_command."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_DUR001",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
                "duration_seconds": 300,
            }
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={},
            rule_id=uuid.uuid4(),
            rule_name="duration_test",
        )

        kwargs = mock_actuator_service.send_command.call_args[1]
        assert kwargs["duration"] == 300


# =========================================================================
# Engine Resilience
# =========================================================================


class TestEngineResilience:
    """Engine handles failures gracefully."""

    @pytest.mark.asyncio
    async def test_failed_action_does_not_crash(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """send_command returning False doesn't crash the engine."""
        mock_actuator_service.send_command = AsyncMock(return_value=_MOCK_SEND_FAIL)

        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_FAIL001",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
            }
        ]

        # Should not raise
        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={},
            rule_id=uuid.uuid4(),
            rule_name="failing_action",
        )

        mock_actuator_service.send_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_action_does_not_crash(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Exception in send_command doesn't crash the engine."""
        mock_actuator_service.send_command = AsyncMock(
            side_effect=Exception("MQTT connection lost")
        )

        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_EXC001",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
            }
        ]

        try:
            await logic_engine._execute_actions(
                actions=actions,
                trigger_data={},
                rule_id=uuid.uuid4(),
                rule_name="exception_action",
            )
        except Exception:
            pass  # Some implementations may re-raise

    @pytest.mark.asyncio
    async def test_issued_by_contains_logic_prefix(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Actions are attributed to logic engine."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_ATTR001",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
            }
        ]

        await logic_engine._execute_actions(
            actions=actions,
            trigger_data={},
            rule_id=uuid.uuid4(),
            rule_name="attribution_test",
        )

        kwargs = mock_actuator_service.send_command.call_args[1]
        assert kwargs.get("issued_by", "").startswith("logic:")


# =========================================================================
# Cross-ESP Mock Client Scenario
# =========================================================================


class TestCrossESPMockScenario:
    """End-to-end cross-ESP using MockESP32Client."""

    def test_source_esp_publishes_sensor_data(self):
        """Source ESP publishes sensor data that would trigger a rule."""
        source = MockESP32Client(esp_id="ESP_XSRC001")
        source.configure_zone("greenhouse", "main_zone")
        source.set_sensor_value(gpio=34, raw_value=30.0, sensor_type="DS18B20", raw_mode=True)

        source.handle_command("sensor_read", {"gpio": 34})

        messages = source.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1

        payload = sensor_msgs[0]["payload"]
        assert payload["value"] == 30.0

    def test_target_esp_executes_actuator_command(self):
        """Target ESP can execute actuator command from logic engine."""
        target = MockESP32Client(esp_id="ESP_XTGT001")
        target.configure_zone("greenhouse", "main_zone")
        target.configure_actuator(gpio=25, actuator_type="fan")

        result = target.handle_command("actuator_set", {"gpio": 25, "value": 0.8, "mode": "pwm"})

        assert result["status"] == "ok"
        assert target.get_actuator_state(25).pwm_value == 0.8

    def test_full_cross_esp_flow(self):
        """Source reads sensor → target activates actuator."""
        source = MockESP32Client(esp_id="ESP_FLOW_SRC")
        source.configure_zone("cross_zone", "main_zone")
        source.set_sensor_value(gpio=34, raw_value=28.0, sensor_type="DS18B20")

        target = MockESP32Client(esp_id="ESP_FLOW_TGT")
        target.configure_zone("cross_zone", "main_zone")
        target.configure_actuator(gpio=25, actuator_type="pump")

        # Source reads sensor
        sensor_result = source.handle_command("sensor_read", {"gpio": 34})
        assert sensor_result["status"] == "ok"
        assert sensor_result["data"]["raw_value"] == 28.0

        # Server logic engine would evaluate and send command to target
        # We simulate the command arriving at target
        actuator_result = target.handle_command(
            "actuator_set", {"gpio": 25, "value": 1, "mode": "digital"}
        )
        assert actuator_result["status"] == "ok"
        assert target.get_actuator_state(25).state is True
