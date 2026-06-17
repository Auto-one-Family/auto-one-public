"""
Integration Tests: Logic Engine

Tests Logic Engine action execution with schema compatibility fixes.
Tests timer-triggered compound rule evaluation (R1-FIX2).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic_engine import LogicEngine
from src.services.actuator_service import ActuatorSendCommandResult

_MOCK_SEND_OK = ActuatorSendCommandResult(
    success=True,
    correlation_id="00000000-0000-4000-8000-000000000001",
    command_sent=True,
    safety_warnings=[],
)


def _logic_repo_session_mock_online_esp():
    """logic_repo.session: ESPRepository pre-check in _execute_actions must see an online ESP."""
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    exec_result = MagicMock()
    esp = MagicMock()
    esp.is_online = True
    esp.config_pending = False
    exec_result.scalar_one_or_none.return_value = esp
    session.execute = AsyncMock(return_value=exec_result)
    return session


@pytest.fixture
async def mock_actuator_service():
    """Create a mock ActuatorService."""
    service = AsyncMock()
    service.send_command = AsyncMock(return_value=_MOCK_SEND_OK)
    return service


@pytest.fixture
async def mock_logic_repo():
    """Create a mock LogicRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
async def mock_websocket_manager():
    """Create a mock WebSocketManager."""
    manager = AsyncMock()
    return manager


@pytest.fixture
async def logic_engine(mock_logic_repo, mock_actuator_service, mock_websocket_manager):
    """Create LogicEngine instance with mocked dependencies."""
    engine = LogicEngine(
        logic_repo=mock_logic_repo,
        actuator_service=mock_actuator_service,
        websocket_manager=mock_websocket_manager,
    )
    return engine


class TestLogicHotpathContractStabilization:
    """P0: _execute_actions/_evaluate_rule contract and error-path hardening."""

    @pytest.mark.asyncio
    async def test_execute_actions_returns_stable_dict_on_success(self, logic_engine: LogicEngine):
        fake_executor = MagicMock()
        fake_executor.supports = MagicMock(return_value=True)
        fake_executor.execute = AsyncMock(
            return_value=MagicMock(success=True, message="ok", data={"noop": False})
        )
        logic_engine.action_executors = [fake_executor]

        result = await logic_engine._execute_actions(
            actions=[{"type": "custom_action"}],
            trigger_data={"timestamp": 1},
            rule_id=uuid.uuid4(),
            rule_name="contract-success",
        )

        assert isinstance(result, dict)
        assert result["blocked_by_conflict"] is False
        assert result["conflict_info"] is None
        assert isinstance(result.get("action_results"), list)
        assert result["action_results"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_execute_actions_returns_stable_dict_on_conflict(self, logic_engine: LogicEngine):
        resolution = MagicMock()
        resolution.value = "blocked"
        conflict = MagicMock()
        conflict.actuator_key = "ESP_CONFLICT:5"
        conflict.winner_rule_id = "rule-winner"
        conflict.competing_rules = ["rule-winner", "rule-loser"]
        conflict.resolution = resolution
        conflict.message = "conflict"

        logic_engine.conflict_manager.has_active_lock_for_rule = MagicMock(return_value=False)
        logic_engine.conflict_manager.acquire_actuator = AsyncMock(return_value=(False, conflict))
        logic_engine.conflict_manager.release_actuator = AsyncMock()

        result = await logic_engine._execute_actions(
            actions=[
                {
                    "type": "actuator_command",
                    "esp_id": "ESP_CONFLICT",
                    "gpio": 5,
                    "command": "ON",
                }
            ],
            trigger_data={"timestamp": 1},
            rule_id=uuid.uuid4(),
            rule_name="contract-conflict",
        )

        assert isinstance(result, dict)
        assert result["blocked_by_conflict"] is True
        assert isinstance(result.get("conflict_info"), dict)
        assert isinstance(result.get("action_results"), list)

    @pytest.mark.asyncio
    async def test_evaluate_rule_error_path_logs_with_snapshots(self, logic_engine: LogicEngine):
        mock_rule = MagicMock()
        mock_rule.id = uuid.uuid4()
        mock_rule.rule_name = "snapshot-rule"
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.priority = 1
        mock_rule.trigger_conditions = {"type": "sensor", "esp_id": "ESP_1", "gpio": 4}
        mock_rule.actions = [{"type": "actuator_command", "esp_id": "ESP_1", "gpio": 5}]

        mock_logic_repo = AsyncMock()
        mock_logic_repo.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo.log_execution = AsyncMock()

        trigger_data = {
            "esp_id": "ESP_1",
            "gpio": 4,
            "sensor_type": "humidity",
            "value": 42.0,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        logic_engine._load_cross_sensor_values = AsyncMock(
            return_value={"ESP_1:4:humidity": {"value": 42.0}}
        )
        logic_engine._check_conditions = AsyncMock(return_value=True)
        logic_engine._execute_actions = AsyncMock(side_effect=RuntimeError("boom"))

        await logic_engine._evaluate_rule(mock_rule, trigger_data, mock_logic_repo)

        mock_logic_repo.session.rollback.assert_awaited_once()
        mock_logic_repo.log_execution.assert_awaited_once()
        kwargs = mock_logic_repo.log_execution.call_args.kwargs
        assert kwargs["rule_id"] == mock_rule.id
        assert kwargs["trigger_data"] == trigger_data
        assert kwargs["actions"] == mock_rule.actions


class TestLogicEngineSchemaCompatibility:
    """Test Logic Engine schema compatibility fixes."""

    @pytest.mark.asyncio
    async def test_action_type_actuator_command(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Test that action_type 'actuator_command' works (existing behavior)."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration_seconds": 10,
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify actuator service was called
        mock_actuator_service.send_command.assert_called_once()
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["esp_id"] == "ESP_TEST_001"
        assert call_kwargs["gpio"] == 5
        assert call_kwargs["command"] == "ON"
        assert call_kwargs["value"] == 1.0
        assert call_kwargs["duration"] == 10

    @pytest.mark.asyncio
    async def test_action_type_actuator(self, logic_engine: LogicEngine, mock_actuator_service):
        """Test that action_type 'actuator' works (schema compatibility fix)."""
        actions = [
            {
                "type": "actuator",  # Schema allows this, not just "actuator_command"
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration_seconds": 10,
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify actuator service was called
        mock_actuator_service.send_command.assert_called_once()
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["esp_id"] == "ESP_TEST_001"
        assert call_kwargs["gpio"] == 5
        assert call_kwargs["duration"] == 10

    @pytest.mark.asyncio
    async def test_duration_seconds(self, logic_engine: LogicEngine, mock_actuator_service):
        """Test that duration_seconds works (existing behavior)."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration_seconds": 30,  # Existing field name
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify duration was read correctly
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["duration"] == 30

    @pytest.mark.asyncio
    async def test_duration_field(self, logic_engine: LogicEngine, mock_actuator_service):
        """Test that duration field works (schema compatibility fix)."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration": 60,  # Schema allows this, not just "duration_seconds"
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify duration was read correctly
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["duration"] == 60

    @pytest.mark.asyncio
    async def test_duration_fallback(self, logic_engine: LogicEngine, mock_actuator_service):
        """Test that duration_seconds takes precedence over duration."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration_seconds": 30,  # Should take precedence
                "duration": 60,  # Should be ignored
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify duration_seconds was used
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["duration"] == 30

    @pytest.mark.asyncio
    async def test_duration_default_zero(self, logic_engine: LogicEngine, mock_actuator_service):
        """Test that duration defaults to 0 if neither field is provided."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                # No duration fields
            }
        ]

        rule_id = uuid.uuid4()
        trigger_data = {"type": "sensor", "timestamp": 1234567890}
        rule_name = "test_rule"

        await logic_engine._execute_actions(
            actions=actions, trigger_data=trigger_data, rule_id=rule_id, rule_name=rule_name
        )

        # Verify duration defaults to 0
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["duration"] == 0

    @pytest.mark.asyncio
    async def test_reconnect_gate_blocks_enforce_until_adoption_complete(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Actuator enforce is skipped while reconnect adoption is still open."""
        actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_TEST_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
            }
        ]
        trigger_data = {"type": "reconnect", "timestamp": 1234567890}

        fake_session = MagicMock()
        with patch("src.services.logic_engine.get_state_adoption_service") as mock_adoption:
            adoption_service = MagicMock()
            adoption_service.is_adoption_completed = AsyncMock(return_value=False)
            mock_adoption.return_value = adoption_service

            await logic_engine._execute_actions(
                actions=actions,
                trigger_data=trigger_data,
                rule_id=uuid.uuid4(),
                rule_name="gate_test_rule",
                session=fake_session,
            )

        mock_actuator_service.send_command.assert_not_called()


class TestExtractSensorRefsFromConditions:
    """Tests for LogicEngine._extract_sensor_refs_from_conditions (R1-FIX2)."""

    def test_sensor_condition_extracted(self, logic_engine: LogicEngine):
        """Sensor conditions produce refs."""
        conditions = {
            "type": "sensor",
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "humidity",
        }
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert len(refs) == 1
        assert refs[0] == {"esp_id": "ESP_001", "gpio": 4, "sensor_type": "humidity"}

    def test_hysteresis_condition_extracted(self, logic_engine: LogicEngine):
        """Hysteresis conditions produce refs (was previously skipped)."""
        conditions = {
            "type": "hysteresis",
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "temperature",
            "activate_below": 15.0,
            "deactivate_above": 20.0,
        }
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert len(refs) == 1
        assert refs[0]["sensor_type"] == "temperature"

    def test_time_condition_excluded(self, logic_engine: LogicEngine):
        """Time conditions do not produce sensor refs."""
        conditions = {"type": "time_window", "start": "22:00", "end": "06:00"}
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert refs == []

    def test_compound_logic_and_extracts_sensor_refs(self, logic_engine: LogicEngine):
        """Compound AND with time_window + hysteresis returns only sensor refs."""
        conditions = {
            "logic": "AND",
            "conditions": [
                {"type": "time_window", "start": "22:00", "end": "06:00"},
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_001",
                    "gpio": 4,
                    "sensor_type": "temperature",
                    "activate_below": 10.0,
                    "deactivate_above": 14.0,
                },
            ],
        }
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert len(refs) == 1
        assert refs[0]["esp_id"] == "ESP_001"
        assert refs[0]["sensor_type"] == "temperature"

    def test_nested_compound_type_extracted(self, logic_engine: LogicEngine):
        """Conditions with type=compound recurse into sub-conditions."""
        conditions = {
            "type": "compound",
            "conditions": [
                {
                    "type": "sensor_threshold",
                    "esp_id": "ESP_002",
                    "gpio": 6,
                    "sensor_type": "humidity",
                },
            ],
        }
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert len(refs) == 1
        assert refs[0]["esp_id"] == "ESP_002"

    def test_list_conditions_multiple_refs(self, logic_engine: LogicEngine):
        """List of mixed conditions extracts all sensor refs."""
        conditions = [
            {"type": "sensor", "esp_id": "ESP_001", "gpio": 4, "sensor_type": "humidity"},
            {"type": "time_window", "start": "08:00", "end": "20:00"},
            {
                "type": "sensor_threshold",
                "esp_id": "ESP_002",
                "gpio": 6,
                "sensor_type": "temperature",
            },
        ]
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert len(refs) == 2
        esp_ids = [r["esp_id"] for r in refs]
        assert "ESP_001" in esp_ids
        assert "ESP_002" in esp_ids

    def test_condition_without_esp_id_skipped(self, logic_engine: LogicEngine):
        """Sensor conditions missing esp_id are silently skipped."""
        conditions = {"type": "sensor", "gpio": 4, "sensor_type": "humidity"}  # no esp_id
        refs = logic_engine._extract_sensor_refs_from_conditions(conditions)
        assert refs == []


class TestTimerCompoundRuleEvaluation:
    """Tests for timer-triggered compound rule evaluation (R1-FIX2)."""

    @pytest.mark.asyncio
    async def test_context_includes_sensor_values_and_sensor_data(self, logic_engine: LogicEngine):
        """evaluate_timer_triggered_rules builds Phase-1 context with sensor_values + sensor_data."""
        rule_id = uuid.uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "Night Heating"
        mock_rule.logic_operator = "AND"
        mock_rule.trigger_conditions = {
            "logic": "AND",
            "conditions": [
                {"type": "time_window", "start": "00:00", "end": "23:59"},
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_001",
                    "gpio": 4,
                    "sensor_type": "temperature",
                    "activate_below": 15.0,
                    "deactivate_above": 20.0,
                },
            ],
        }

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_enabled_rules = AsyncMock(return_value=[mock_rule])
        mock_session = AsyncMock()

        fake_sensor_values = {
            "ESP_001:4:temperature": {
                "esp_id": "ESP_001",
                "gpio": 4,
                "sensor_type": "temperature",
                "value": 10.0,
            }
        }

        async def fake_get_session():
            yield mock_session

        captured_contexts: list[dict] = []

        async def spy_check_conditions(conditions, context, **kwargs):
            captured_contexts.append(dict(context))
            return False  # don't fire — just capture the context

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(
                    return_value=(fake_sensor_values, [])
                )
                logic_engine._check_conditions = AsyncMock(side_effect=spy_check_conditions)

                await logic_engine.evaluate_timer_triggered_rules()

        assert len(captured_contexts) == 1, "Expected exactly one Phase-1 context capture"
        ctx = captured_contexts[0]

        assert "sensor_values" in ctx, "sensor_values must be in Phase-1 context"
        assert ctx["sensor_values"] == fake_sensor_values
        assert "sensor_data" in ctx, "sensor_data must be in Phase-1 context"
        assert ctx["sensor_data"]["value"] == 10.0
        assert ctx["sensor_data"]["sensor_type"] == "temperature"
        assert ctx["rule_id"] == str(rule_id)
        assert ctx["condition_index"] == 0
        assert "current_time" in ctx

    @pytest.mark.asyncio
    async def test_context_sensor_data_empty_when_no_sensor_refs(self, logic_engine: LogicEngine):
        """Pure time-window rules get empty sensor context — evaluate_timer still runs."""
        rule_id = uuid.uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "Pure Time Rule"
        mock_rule.logic_operator = "AND"
        mock_rule.trigger_conditions = {
            "type": "time_window",
            "start": "00:00",
            "end": "23:59",
        }

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_enabled_rules = AsyncMock(return_value=[mock_rule])
        mock_session = AsyncMock()

        async def fake_get_session():
            yield mock_session

        captured_contexts: list[dict] = []

        async def spy_check_conditions(conditions, context, **kwargs):
            captured_contexts.append(dict(context))
            return False

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                logic_engine._check_conditions = AsyncMock(side_effect=spy_check_conditions)

                await logic_engine.evaluate_timer_triggered_rules()

        assert len(captured_contexts) == 1
        ctx = captured_contexts[0]
        assert ctx["sensor_values"] == {}
        assert ctx["sensor_data"] == {}
        assert ctx["rule_id"] == str(rule_id)


class TestB1FlagPropagation:
    """B1-fix: _hysteresis_just_deactivated flag propagates through CompoundConditionEvaluator."""

    @pytest.mark.asyncio
    async def test_hysteresis_deactivated_flag_propagates_in_compound(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Compound rule (hysteresis + time_window, AND): deactivation sends OFF command.

        Simulates the exact scenario from the live log:
        - Rule has hysteresis (activate_below=50, deactivate_above=60) + time_window
        - Hysteresis state is pre-seeded as active (is_active=True)
        - Sensor value 75 triggers deactivation (> 60)
        - Expected: actuator receives OFF command via the bypass path in _evaluate_rule
        """
        rule_id = uuid.uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "TestTimmsRegen"
        mock_rule.logic_operator = "AND"
        mock_rule.priority = 1
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = [
            {
                "type": "hysteresis",
                "esp_id": "ESP_EA5484",
                "gpio": 0,
                "sensor_type": "sht31_humidity",
                "activate_below": 50,
                "deactivate_above": 60,
            },
            {
                "type": "time_window",
                "start_hour": 0,
                "end_hour": 24,
                "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            },
        ]
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_EA5484",
                "gpio": 1,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]

        # Pre-seed hysteresis state as active so deactivation can fire
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        state_key = f"{rule_id}:0"
        hysteresis_eval._states[state_key] = HysteresisState(is_active=True)

        # Trigger with value > deactivate_above (75 > 60)
        trigger_data = {
            "esp_id": "ESP_EA5484",
            "gpio": 0,
            "sensor_type": "sht31_humidity",
            "value": 75.0,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo_inst.log_execution = AsyncMock()

        await logic_engine._evaluate_rule(
            mock_rule, trigger_data, mock_logic_repo_inst, batch_locks=[]
        )

        # The bypass path must have fired: actuator gets OFF (not ON)
        mock_actuator_service.send_command.assert_called_once()
        call_kwargs = mock_actuator_service.send_command.call_args[1]
        assert call_kwargs["command"] == "OFF", (
            "Expected OFF command from hysteresis deactivation bypass — "
            "flag may not have propagated through CompoundConditionEvaluator"
        )


class TestB2TimezoneSupport:
    """B2-fix: TimeConditionEvaluator interprets hours in the condition's timezone."""

    @pytest.mark.asyncio
    async def test_time_window_with_europe_berlin_timezone(self, logic_engine: LogicEngine):
        """Zeitfenster 23:00–24:00 mit timezone=Europe/Berlin öffnet bei 23:00 CEST.

        CEST = UTC+2, so 23:00 CEST = 21:00 UTC.
        Test checks that the evaluator returns True at 21:00 UTC when timezone is set.
        """
        from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator

        evaluator = TimeConditionEvaluator()
        condition = {
            "type": "time_window",
            "start_hour": 23,
            "end_hour": 24,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "timezone": "Europe/Berlin",
        }

        # 21:00 UTC = 23:00 CEST → window should be open
        from datetime import datetime, timezone

        utc_21 = datetime(2026, 7, 1, 21, 0, 0, tzinfo=timezone.utc)
        result = await evaluator.evaluate(condition, {"current_time": utc_21})
        assert (
            result is True
        ), "21:00 UTC should be inside 23:00-24:00 window for Europe/Berlin (CEST)"

        # 23:00 UTC = 01:00 CEST next day → window should be closed
        utc_23 = datetime(2026, 7, 1, 23, 0, 0, tzinfo=timezone.utc)
        result = await evaluator.evaluate(condition, {"current_time": utc_23})
        assert (
            result is False
        ), "23:00 UTC should be outside 23:00-24:00 window for Europe/Berlin (CEST)"

    @pytest.mark.asyncio
    async def test_time_window_without_timezone_uses_utc(self, logic_engine: LogicEngine):
        """Existing rules without timezone field keep UTC behaviour (backward-compatible)."""
        from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator
        from datetime import datetime, timezone

        evaluator = TimeConditionEvaluator()
        condition = {
            "type": "time_window",
            "start_hour": 23,
            "end_hour": 24,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            # no "timezone" field
        }

        utc_23 = datetime(2026, 7, 1, 23, 0, 0, tzinfo=timezone.utc)
        result = await evaluator.evaluate(condition, {"current_time": utc_23})
        assert (
            result is True
        ), "23:00 UTC should be inside 23:00-24:00 window when no timezone is set"

    @pytest.mark.asyncio
    async def test_invalid_timezone_falls_back_to_utc(self, logic_engine: LogicEngine):
        """Invalid timezone name logs a warning and falls back to UTC (no crash)."""
        from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator
        from datetime import datetime, timezone

        evaluator = TimeConditionEvaluator()
        condition = {
            "type": "time_window",
            "start_hour": 23,
            "end_hour": 24,
            "timezone": "Not/A_Valid_Timezone",
        }

        utc_23 = datetime(2026, 7, 1, 23, 0, 0, tzinfo=timezone.utc)
        # Must not raise — falls back to UTC
        result = await evaluator.evaluate(condition, {"current_time": utc_23})
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_time_window_uses_start_end_minute_fields(self, logic_engine: LogicEngine):
        """Minute fields on time_window must be evaluated directly."""
        from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator

        evaluator = TimeConditionEvaluator()
        condition = {
            "type": "time_window",
            "start_hour": 7,
            "start_minute": 30,
            "end_hour": 8,
            "end_minute": 15,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        }

        inside = datetime(2026, 7, 1, 7, 45, 0, tzinfo=timezone.utc)
        outside = datetime(2026, 7, 1, 8, 16, 0, tzinfo=timezone.utc)

        assert await evaluator.evaluate(condition, {"current_time": inside}) is True
        assert await evaluator.evaluate(condition, {"current_time": outside}) is False

    @pytest.mark.asyncio
    async def test_time_window_falls_back_to_start_end_time_strings(
        self, logic_engine: LogicEngine
    ):
        """Legacy start_time/end_time remains supported when hour fields are absent."""
        from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator

        evaluator = TimeConditionEvaluator()
        condition = {
            "type": "time_window",
            "start_time": "07:05",
            "end_time": "07:10",
        }

        inside = datetime(2026, 7, 1, 7, 6, 0, tzinfo=timezone.utc)
        outside = datetime(2026, 7, 1, 7, 11, 0, tzinfo=timezone.utc)

        assert await evaluator.evaluate(condition, {"current_time": inside}) is True
        assert await evaluator.evaluate(condition, {"current_time": outside}) is False


class TestB3RuleUpdateTrigger:
    """B3-fix: on_rule_updated resets hysteresis state and sends OFF when actuator was active."""

    @pytest.mark.asyncio
    async def test_on_rule_updated_sends_off_when_hysteresis_was_active(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Rule update while actuator is ON → OFF command sent immediately."""
        rule_id = uuid.uuid4()

        # Pre-seed hysteresis state as active
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        hysteresis_eval._states[f"{rule_id}:0"] = HysteresisState(is_active=True)

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "TestRule"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = [
            {
                "type": "hysteresis",
                "esp_id": "ESP_001",
                "gpio": 0,
                "sensor_type": "humidity",
                "activate_below": 50,
                "deactivate_above": 60,
            }
        ]
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 1,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_by_id = AsyncMock(return_value=mock_rule)
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                await logic_engine.on_rule_updated(str(rule_id))

        # OFF must have been sent for the actuator that was active
        mock_actuator_service.send_command.assert_called()
        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) >= 1
        ), "Expected at least one OFF command after rule update with active hysteresis"

    @pytest.mark.asyncio
    async def test_on_rule_updated_no_off_when_hysteresis_was_inactive(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Rule update while actuator is OFF → no phantom OFF command sent."""
        rule_id = uuid.uuid4()

        # Hysteresis state is inactive (no state in dict = inactive)
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        # Ensure no state exists for this rule
        hysteresis_eval._states.pop(f"{rule_id}:0", None)

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "TestRule"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = [{"type": "time_window", "start_hour": 0, "end_hour": 24}]
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 1,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_by_id = AsyncMock(return_value=mock_rule)
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                await logic_engine.on_rule_updated(str(rule_id))

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert len(off_calls) == 0, "No OFF command expected when hysteresis was not active"


class TestBumplessTransfer:
    """Fix 1: Bumpless Transfer — removing a time_window must not disrupt hysteresis state."""

    def _make_mock_rule(self, rule_id, trigger_conditions):
        """Build a minimal MagicMock rule suitable for on_rule_updated tests."""
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "TestHumidityRule"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = trigger_conditions
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]
        return mock_rule

    def _patch_session_and_repo(self, mock_rule):
        """Return context managers that patch get_session and LogicRepository."""
        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_by_id = AsyncMock(return_value=mock_rule)
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        return fake_get_session, mock_logic_repo_inst

    @pytest.mark.asyncio
    async def test_bumpless_transfer_time_window_removed_state_preserved(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Removing a time_window from a Hysteresis+TimeWindow rule must NOT reset
        hysteresis state or send a phantom OFF command."""
        rule_id = uuid.uuid4()

        hysteresis_cond = {
            "type": "hysteresis",
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "humidity",
            "activate_below": 60,
            "deactivate_above": 70,
        }
        time_window_cond = {"type": "time_window", "start_hour": 6, "end_hour": 22}

        # Pre-seed state: hysteresis active (sensor in deadband at 63%)
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        hysteresis_eval._states[f"{rule_id}:0"] = HysteresisState(is_active=True, last_value=63.0)

        # New rule: time_window removed, hysteresis identical
        new_conditions = [hysteresis_cond]
        mock_rule = self._make_mock_rule(rule_id, new_conditions)
        fake_get_session, mock_logic_repo_inst = self._patch_session_and_repo(mock_rule)

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository",
                return_value=mock_logic_repo_inst,
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                await logic_engine.on_rule_updated(
                    str(rule_id),
                    old_trigger_conditions=[hysteresis_cond, time_window_cond],
                )

        # State must be preserved
        preserved = hysteresis_eval._states.get(f"{rule_id}:0")
        assert preserved is not None, "Hysteresis state must not be deleted on orthogonal change"
        assert (
            preserved.is_active is True
        ), "Hysteresis must remain active after time_window removal"

        # No OFF command must have been sent
        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert len(off_calls) == 0, "No phantom OFF expected when orthogonal condition removed"

    @pytest.mark.asyncio
    async def test_bumpless_transfer_threshold_change_resets_state(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Changing hysteresis thresholds must reset state and send OFF."""
        rule_id = uuid.uuid4()

        old_hysteresis = {
            "type": "hysteresis",
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "humidity",
            "activate_below": 60,
            "deactivate_above": 70,
        }
        new_hysteresis = {
            **old_hysteresis,
            "activate_below": 50,
            "deactivate_above": 65,
        }

        # Pre-seed state as active
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        hysteresis_eval._states[f"{rule_id}:0"] = HysteresisState(is_active=True, last_value=63.0)

        mock_rule = self._make_mock_rule(rule_id, [new_hysteresis])
        fake_get_session, mock_logic_repo_inst = self._patch_session_and_repo(mock_rule)

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository",
                return_value=mock_logic_repo_inst,
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                await logic_engine.on_rule_updated(
                    str(rule_id),
                    old_trigger_conditions=[old_hysteresis],
                )

        # State must be cleared (thresholds changed)
        assert (
            f"{rule_id}:0" not in hysteresis_eval._states
        ), "Hysteresis state must be reset when thresholds change"

        # OFF must have been sent
        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert len(off_calls) >= 1, "OFF must be sent when active hysteresis thresholds change"

    @pytest.mark.asyncio
    async def test_cooldown_bypassed_for_rule_update_trigger(
        self, logic_engine: LogicEngine, mock_logic_repo, mock_actuator_service
    ):
        """Rule-update triggers must bypass the cooldown check so the new
        configuration takes effect immediately even if the rule just fired."""
        from datetime import timedelta

        rule_id = uuid.uuid4()
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "CooldownTestRule"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = 60  # 60s cooldown
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = {
            "type": "sensor",
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "humidity",
            "operator": "<",
            "value": 70,
        }
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]

        # Simulate last execution 30s ago (within cooldown window)
        last_exec = MagicMock()
        last_exec.timestamp = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_logic_repo.get_last_execution = AsyncMock(return_value=last_exec)
        mock_logic_repo.log_execution = AsyncMock()
        mock_logic_repo.session = _logic_repo_session_mock_online_esp()

        # Sensor value matches condition (should trigger ON if cooldown is bypassed)
        trigger_data = {
            "type": "rule_update",
            "rule_id": str(rule_id),
            "esp_id": "ESP_001",
            "gpio": 4,
            "sensor_type": "humidity",
            "value": 65.0,  # < 70 → condition met
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        await logic_engine._evaluate_rule(mock_rule, trigger_data, mock_logic_repo)

        # Actuator must have been called despite cooldown
        mock_actuator_service.send_command.assert_called()
        on_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "ON"
        ]
        assert len(on_calls) >= 1, "rule_update trigger must bypass cooldown and execute actions"


class TestCompoundPostReEvalOFFGuard:
    """BUG 1 fix: Post-Re-Eval OFF-Guard for compound Hysteresis+TimeWindow rules.

    Scenario: Bumpless Transfer preserves hysteresis state (correct). After re-eval
    _evaluate_rule returns without OFF because _hysteresis_just_deactivated==False
    (sensor in deadband). Step 4 checks conditions_met directly and sends OFF if needed.
    """

    _HYSTERESIS_COND = {
        "type": "hysteresis",
        "esp_id": "ESP_001",
        "gpio": 0,
        "sensor_type": "humidity",
        "activate_below": 60,
        "deactivate_above": 70,
    }
    _TIME_WINDOW_COND = {
        "type": "time_window",
        "start_hour": 22,
        "end_hour": 6,
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
    }

    def _make_compound_rule(self, rule_id):
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "CompoundHumidityRule"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.enabled = True
        mock_rule.trigger_conditions = [self._HYSTERESIS_COND, self._TIME_WINDOW_COND]
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 1,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]
        return mock_rule

    def _patch_env(self, mock_rule):
        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_by_id = AsyncMock(return_value=mock_rule)
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=None)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        return fake_get_session, mock_logic_repo_inst, mock_session

    @pytest.mark.asyncio
    async def test_off_guard_fires_when_tw_becomes_inactive(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Compound rule (Hyst active, TW now inactive after save) → OFF sent by Step 4."""
        rule_id = uuid.uuid4()
        mock_rule = self._make_compound_rule(rule_id)

        # Pre-seed: hysteresis active, sensor 63% in deadband (60–70)
        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        hysteresis_eval._states[f"{rule_id}:0"] = HysteresisState(is_active=True, last_value=63.0)

        fake_get_session, mock_logic_repo_inst, mock_session = self._patch_env(mock_rule)
        fake_sensor_values = {
            "ESP_001:0:humidity": {
                "esp_id": "ESP_001",
                "gpio": 0,
                "sensor_type": "humidity",
                "value": 63.0,
            }
        }

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(
                    return_value=(fake_sensor_values, [])
                )
                # _evaluate_rule does nothing — simulates the bug: no OFF from re-eval
                logic_engine._evaluate_rule = AsyncMock()
                # Step 4 re-check: TW now inactive → conditions_met=False
                logic_engine._check_conditions = AsyncMock(return_value=False)

                await logic_engine.on_rule_updated(
                    str(rule_id),
                    old_trigger_conditions=[self._HYSTERESIS_COND, self._TIME_WINDOW_COND],
                )

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) >= 1
        ), "Post-Re-Eval OFF-Guard must send OFF when TW inactive + hysteresis in deadband"
        assert (
            f"{rule_id}:0" not in hysteresis_eval._states
        ), "Hysteresis state must be cleared by OFF-Guard"

    @pytest.mark.asyncio
    async def test_no_spurious_off_when_tw_still_active(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Compound rule (Hyst active, TW still active) → NO spurious OFF (bumpless correct)."""
        rule_id = uuid.uuid4()
        mock_rule = self._make_compound_rule(rule_id)

        hysteresis_eval = logic_engine._get_hysteresis_evaluator()
        assert hysteresis_eval is not None
        from src.services.logic.conditions.hysteresis_evaluator import HysteresisState

        hysteresis_eval._states[f"{rule_id}:0"] = HysteresisState(is_active=True, last_value=63.0)

        fake_get_session, mock_logic_repo_inst, mock_session = self._patch_env(mock_rule)
        fake_sensor_values = {
            "ESP_001:0:humidity": {
                "esp_id": "ESP_001",
                "gpio": 0,
                "sensor_type": "humidity",
                "value": 63.0,
            }
        }

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(
                    return_value=(fake_sensor_values, [])
                )
                logic_engine._evaluate_rule = AsyncMock()
                # Step 4 re-check: TW still active → conditions_met=True → guard must NOT fire
                logic_engine._check_conditions = AsyncMock(return_value=True)

                await logic_engine.on_rule_updated(
                    str(rule_id),
                    old_trigger_conditions=[self._HYSTERESIS_COND, self._TIME_WINDOW_COND],
                )

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) == 0
        ), "No spurious OFF when TW is still active (bumpless transfer must be preserved)"
        state = hysteresis_eval._states.get(f"{rule_id}:0")
        assert (
            state is not None and state.is_active
        ), "Hysteresis state must remain active when compound conditions are still met"


class TestPureTimeWindowRuleUpdate:
    """BUG 2 fix: on_rule_updated() handles pure time-window rules (no sensor refs)."""

    def _make_tw_rule(self, rule_id, *, enabled=True):
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "NightLight"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.enabled = enabled
        mock_rule.trigger_conditions = {
            "type": "time_window",
            "start_hour": 22,
            "end_hour": 6,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        }
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 1,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]
        return mock_rule

    def _patch_env(self, mock_rule, last_execution=None):
        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_by_id = AsyncMock(return_value=mock_rule)
        mock_logic_repo_inst.session = _logic_repo_session_mock_online_esp()
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=last_execution)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        return fake_get_session, mock_logic_repo_inst, mock_session

    def _make_last_exec(self):
        from datetime import timedelta

        last_exec = MagicMock()
        last_exec.timestamp = datetime.now(timezone.utc) - timedelta(seconds=30)
        return last_exec

    @pytest.mark.asyncio
    async def test_off_sent_when_tw_becomes_inactive(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Pure TW rule: after save with TW now inactive + previous execution → OFF sent."""
        rule_id = uuid.uuid4()
        mock_rule = self._make_tw_rule(rule_id)
        last_exec = self._make_last_exec()
        fake_get_session, mock_logic_repo_inst, mock_session = self._patch_env(
            mock_rule, last_execution=last_exec
        )

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                # TW now outside window → conditions_met=False
                logic_engine._check_conditions = AsyncMock(return_value=False)

                await logic_engine.on_rule_updated(str(rule_id))

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) >= 1
        ), "OFF must be sent when pure TW rule is saved with window now inactive"

    @pytest.mark.asyncio
    async def test_on_sent_when_tw_becomes_active(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Pure TW rule: after save with TW now active → ON action executed."""
        rule_id = uuid.uuid4()
        mock_rule = self._make_tw_rule(rule_id)
        fake_get_session, mock_logic_repo_inst, mock_session = self._patch_env(mock_rule)

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                # TW now inside window → conditions_met=True
                logic_engine._check_conditions = AsyncMock(return_value=True)

                await logic_engine.on_rule_updated(str(rule_id))

        on_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "ON"
        ]
        assert (
            len(on_calls) >= 1
        ), "ON must be sent when pure TW rule is saved with window now active"

    @pytest.mark.asyncio
    async def test_no_spurious_off_when_never_executed(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Pure TW rule: TW inactive but rule never executed → no spurious OFF."""
        rule_id = uuid.uuid4()
        mock_rule = self._make_tw_rule(rule_id)
        # last_execution=None → rule was never executed
        fake_get_session, mock_logic_repo_inst, mock_session = self._patch_env(
            mock_rule, last_execution=None
        )

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._check_conditions = AsyncMock(return_value=False)

                await logic_engine.on_rule_updated(str(rule_id))

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) == 0
        ), "No spurious OFF when rule was never executed (avoid phantom OFF for new rules)"


class TestTimerSchedulerOFF:
    """BUG 2 fix: evaluate_timer_triggered_rules() sends OFF when TW expires."""

    def _make_tw_rule(self, rule_id):
        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.rule_name = "NightPump"
        mock_rule.priority = 1
        mock_rule.logic_operator = "AND"
        mock_rule.cooldown_seconds = None
        mock_rule.max_executions_per_hour = None
        mock_rule.trigger_conditions = {
            "type": "time_window",
            "start_hour": 22,
            "end_hour": 6,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        }
        mock_rule.actions = [
            {
                "type": "actuator_command",
                "esp_id": "ESP_001",
                "gpio": 2,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ]
        return mock_rule

    @pytest.mark.asyncio
    async def test_off_sent_when_tw_expired_and_recently_executed(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Timer tick: TW just expired, last execution 60s ago (< 120s) → OFF sent once."""
        from datetime import timedelta

        rule_id = uuid.uuid4()
        mock_rule = self._make_tw_rule(rule_id)

        last_exec = MagicMock()
        last_exec.timestamp = datetime.now(timezone.utc) - timedelta(seconds=60)

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_enabled_rules = AsyncMock(return_value=[mock_rule])
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=last_exec)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                # TW just expired → conditions_met=False
                logic_engine._check_conditions = AsyncMock(return_value=False)

                await logic_engine.evaluate_timer_triggered_rules()

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) >= 1
        ), "Timer must send OFF when TW expired and rule was recently executed"

    @pytest.mark.asyncio
    async def test_no_off_spam_when_stale_execution(
        self, logic_engine: LogicEngine, mock_actuator_service
    ):
        """Timer tick: TW expired, last execution > 120s ago → no OFF spam."""
        from datetime import timedelta

        rule_id = uuid.uuid4()
        mock_rule = self._make_tw_rule(rule_id)

        last_exec = MagicMock()
        # 10 minutes ago — well outside the 120s window
        last_exec.timestamp = datetime.now(timezone.utc) - timedelta(seconds=600)

        mock_logic_repo_inst = AsyncMock()
        mock_logic_repo_inst.get_enabled_rules = AsyncMock(return_value=[mock_rule])
        mock_logic_repo_inst.get_last_execution = AsyncMock(return_value=last_exec)
        mock_logic_repo_inst.log_execution = AsyncMock()
        mock_session = _logic_repo_session_mock_online_esp()

        async def fake_get_session():
            yield mock_session

        with patch("src.services.logic_engine.get_session", fake_get_session):
            with patch(
                "src.services.logic_engine.LogicRepository", return_value=mock_logic_repo_inst
            ):
                logic_engine._load_sensor_values_for_timer = AsyncMock(return_value=({}, []))
                logic_engine._check_conditions = AsyncMock(return_value=False)

                await logic_engine.evaluate_timer_triggered_rules()

        off_calls = [
            call
            for call in mock_actuator_service.send_command.call_args_list
            if call[1].get("command") == "OFF"
        ]
        assert (
            len(off_calls) == 0
        ), "No OFF spam when last execution was > 120s ago (rule is long-inactive)"
