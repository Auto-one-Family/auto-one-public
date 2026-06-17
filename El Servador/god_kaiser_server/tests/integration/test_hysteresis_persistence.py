"""
Integration Tests: Hysteresis State Persistence + Compound Rules

L2 Hysterese-Härtung:
- TEST-2: State persistence after simulated restart (mock session_factory)
- TEST-3: Compound rule with hysteresis condition_index correctness
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.logic.conditions.hysteresis_evaluator import (
    HysteresisConditionEvaluator,
    HysteresisState,
)
from src.services.logic.conditions.compound_evaluator import CompoundConditionEvaluator
from src.services.logic.conditions.sensor_evaluator import SensorConditionEvaluator
from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator

# =============================================================================
# TEST-2: State Persistence After Restart (Simulated)
# =============================================================================


class TestHysteresisPersistence:
    """Test that hysteresis states survive simulated server restarts."""

    @pytest.mark.asyncio
    async def test_persist_called_on_activation(self):
        """_persist_state is called when state changes to active."""
        evaluator = HysteresisConditionEvaluator()
        # Patch _persist_state to track calls
        evaluator._persist_state = AsyncMock()

        rule_id = str(uuid.uuid4())
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }
        ctx = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }

        result = await evaluator.evaluate(cond, ctx)

        assert result is True
        evaluator._persist_state.assert_called_once()
        call_args = evaluator._persist_state.call_args
        assert call_args[0][0] == f"{rule_id}:0"
        assert call_args[0][1].is_active is True

    @pytest.mark.asyncio
    async def test_persist_called_on_deactivation(self):
        """_persist_state is called when state changes to inactive."""
        evaluator = HysteresisConditionEvaluator()
        evaluator._persist_state = AsyncMock()

        rule_id = str(uuid.uuid4())
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }

        # Activate (1 persist call)
        ctx1 = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        await evaluator.evaluate(cond, ctx1)
        assert evaluator._persist_state.call_count == 1

        # Deactivate (2nd persist call)
        ctx2 = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 23.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        await evaluator.evaluate(cond, ctx2)
        assert evaluator._persist_state.call_count == 2

    @pytest.mark.asyncio
    async def test_persist_not_called_when_no_state_change(self):
        """_persist_state is NOT called when state doesn't change (deadband)."""
        evaluator = HysteresisConditionEvaluator()
        evaluator._persist_state = AsyncMock()

        rule_id = str(uuid.uuid4())
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }

        # Activate
        ctx1 = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        await evaluator.evaluate(cond, ctx1)
        assert evaluator._persist_state.call_count == 1

        # Deadband value (no state change)
        ctx2 = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 26.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        await evaluator.evaluate(cond, ctx2)
        assert evaluator._persist_state.call_count == 1  # Still 1, no new persist

    @pytest.mark.asyncio
    async def test_simulated_restart_restores_state(self):
        """After simulated restart, manually loaded state is preserved."""
        rule_id = str(uuid.uuid4())

        # Step 1: Evaluator A activates hysteresis
        eval_a = HysteresisConditionEvaluator()
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }
        ctx = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        result = await eval_a.evaluate(cond, ctx)
        assert result is True

        # Capture the state
        state_a = eval_a.get_state_for_rule(rule_id, 0)
        assert state_a.is_active is True

        # Step 2: Simulate restart — new evaluator instance
        eval_b = HysteresisConditionEvaluator()

        # Without loading, state is lost
        state_b_before = eval_b.get_state_for_rule(rule_id, 0)
        assert state_b_before is None

        # Manually restore state (simulates load_states_from_db)
        eval_b._states[f"{rule_id}:0"] = HysteresisState(
            is_active=state_a.is_active,
            last_activation=state_a.last_activation,
            last_deactivation=state_a.last_deactivation,
            last_value=state_a.last_value,
        )

        # Step 3: Verify restored state works correctly in deadband
        ctx_deadband = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 26.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        result = await eval_b.evaluate(cond, ctx_deadband)
        assert result is True  # Still active — state was restored!

    @pytest.mark.asyncio
    async def test_simulated_restart_without_restore_causes_issue(self):
        """Without state restore, actuator stays running in deadband after restart."""
        rule_id = str(uuid.uuid4())

        # Evaluator activates
        eval_a = HysteresisConditionEvaluator()
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }
        ctx = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        await eval_a.evaluate(cond, ctx)

        # Simulate restart without restore
        eval_b = HysteresisConditionEvaluator()

        # Deadband value: won't re-activate or deactivate
        ctx_deadband = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 26.0},
            "rule_id": rule_id,
            "condition_index": 0,
        }
        result = await eval_b.evaluate(cond, ctx_deadband)
        assert result is False  # BUG without persistence: should be True!


# =============================================================================
# TEST-3: Compound Rule with Hysteresis (condition_index correctness)
# =============================================================================


class TestCompoundHysteresisConditionIndex:
    """Test that compound evaluator sets condition_index per sub-condition."""

    @pytest.fixture
    def hysteresis_evaluator(self):
        return HysteresisConditionEvaluator()

    @pytest.fixture
    def sensor_evaluator(self):
        return SensorConditionEvaluator()

    @pytest.fixture
    def time_evaluator(self):
        return TimeConditionEvaluator()

    @pytest.mark.asyncio
    async def test_hysteresis_at_index_0_gets_correct_key(
        self, hysteresis_evaluator, time_evaluator
    ):
        """Compound AND(Hysteresis[0], Time[1]) — hysteresis gets condition_index=0."""
        compound_eval = CompoundConditionEvaluator([hysteresis_evaluator, time_evaluator])

        rule_id = str(uuid.uuid4())
        compound_cond = {
            "type": "compound",
            "logic": "AND",
            "conditions": [
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_01",
                    "gpio": 4,
                    "activate_above": 28.0,
                    "deactivate_below": 24.0,
                },
                {
                    "type": "time_window",
                    "start_hour": 6,
                    "end_hour": 22,
                },
            ],
        }

        # Use real datetime (12:00 UTC on a Wednesday) so TimeEvaluator works
        context = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 99,  # This will be overridden by compound
            "current_time": datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
        }

        await compound_eval.evaluate(compound_cond, context)

        # Hysteresis state key should be rule_id:0 (index 0 in compound)
        state = hysteresis_evaluator.get_state_for_rule(rule_id, 0)
        assert state is not None
        assert state.is_active is True

    @pytest.mark.asyncio
    async def test_hysteresis_at_index_1_gets_correct_key(
        self, hysteresis_evaluator, time_evaluator
    ):
        """Compound AND(Time[0], Hysteresis[1]) — hysteresis gets condition_index=1."""
        compound_eval = CompoundConditionEvaluator([hysteresis_evaluator, time_evaluator])

        rule_id = str(uuid.uuid4())
        compound_cond = {
            "type": "compound",
            "logic": "AND",
            "conditions": [
                {
                    "type": "time_window",
                    "start_hour": 6,
                    "end_hour": 22,
                },
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_01",
                    "gpio": 4,
                    "activate_above": 28.0,
                    "deactivate_below": 24.0,
                },
            ],
        }

        # Use real datetime (12:00 UTC on a Wednesday) so TimeEvaluator works
        context = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_id,
            "condition_index": 99,
            "current_time": datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
        }

        await compound_eval.evaluate(compound_cond, context)

        # Hysteresis state key should be rule_id:1 (index 1 in compound)
        state_0 = hysteresis_evaluator.get_state_for_rule(rule_id, 0)
        state_1 = hysteresis_evaluator.get_state_for_rule(rule_id, 1)
        assert state_0 is None  # Not at index 0
        assert state_1 is not None
        assert state_1.is_active is True

    @pytest.mark.asyncio
    async def test_two_hysteresis_in_compound_have_separate_keys(self, hysteresis_evaluator):
        """Two hysteresis conditions in same compound get different state keys."""
        compound_eval = CompoundConditionEvaluator([hysteresis_evaluator])

        rule_id = str(uuid.uuid4())
        compound_cond = {
            "type": "compound",
            "logic": "OR",
            "conditions": [
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_01",
                    "gpio": 4,
                    "activate_above": 28.0,
                    "deactivate_below": 24.0,
                },
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_01",
                    "gpio": 5,
                    "activate_below": 45.0,
                    "deactivate_above": 55.0,
                },
            ],
        }

        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 4,
                "value": 30.0,
            },
            "rule_id": rule_id,
            "condition_index": 0,
        }

        await compound_eval.evaluate(compound_cond, context)

        # Both conditions evaluated, separate state keys
        state_0 = hysteresis_evaluator.get_state_for_rule(rule_id, 0)
        state_1 = hysteresis_evaluator.get_state_for_rule(rule_id, 1)

        # GPIO 4 matches condition 0 → activated
        assert state_0 is not None
        assert state_0.is_active is True

        # GPIO 5 does not match sensor_data GPIO 4 → stays inactive
        assert state_1 is not None
        assert state_1.is_active is False

    @pytest.mark.asyncio
    async def test_no_key_collision_between_rules(self, hysteresis_evaluator):
        """Different rules with same condition structure get separate state keys."""
        rule_a = str(uuid.uuid4())
        rule_b = str(uuid.uuid4())

        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }

        # Rule A activates
        ctx_a = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 30.0},
            "rule_id": rule_a,
            "condition_index": 0,
        }
        result_a = await hysteresis_evaluator.evaluate(cond, ctx_a)
        assert result_a is True

        # Rule B with same sensor in deadband — should NOT be affected by Rule A
        ctx_b = {
            "sensor_data": {"esp_id": "ESP_01", "gpio": 4, "value": 26.0},
            "rule_id": rule_b,
            "condition_index": 0,
        }
        result_b = await hysteresis_evaluator.evaluate(cond, ctx_b)
        assert result_b is False  # Rule B has its own state
