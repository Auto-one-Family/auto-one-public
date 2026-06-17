"""
Unit-Tests: Compound-Regel mit Hysterese-Conditions (D3)

Verifiziert dass CompoundConditionEvaluator den condition_index
pro Sub-Condition korrekt setzt — keine Key-Kollision bei
mehreren Hysterese-Conditions in einer Compound-Regel.

Abgedeckte Szenarien (D3 aus Auftrag ED-3):
1. Hysterese an Position idx=0 nutzt Key rule_id:0
2. Hysterese an Position idx=1 nutzt Key rule_id:1
3. Zwei Hysterese-Conditions → unabhängige State-Maschinen
4. Compound-Regeln verschiedener Rules haben separate State-Keys
"""

import pytest
import uuid
from datetime import datetime, timezone

from src.services.logic.conditions.hysteresis_evaluator import HysteresisConditionEvaluator
from src.services.logic.conditions.compound_evaluator import CompoundConditionEvaluator
from src.services.logic.conditions.time_evaluator import TimeConditionEvaluator


@pytest.fixture
def hysteresis_eval():
    return HysteresisConditionEvaluator()


@pytest.fixture
def time_eval():
    return TimeConditionEvaluator()


def make_context(rule_id: str, esp_id: str = "ESP_01", gpio: int = 4, value: float = 30.0) -> dict:
    return {
        "sensor_data": {"esp_id": esp_id, "gpio": gpio, "value": value},
        "rule_id": rule_id,
        "condition_index": 99,  # Compound must override this
        "current_time": datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
    }


class TestCompoundHysteresisConditionIndex:
    """
    D3: Hysterese-Condition in Compound-Regel erhält korrekten condition_index.

    Kernaussage: CompoundConditionEvaluator setzt sub_context["condition_index"] = idx
    für jede Sub-Condition. HysteresisEvaluator nutzt diesen Index als Teil des State-Keys.
    """

    @pytest.mark.asyncio
    async def test_hysteresis_at_index_0_uses_key_0(self, hysteresis_eval, time_eval):
        """AND(Hysteresis[0], Time[1]) — Hysterese-State-Key ist rule_id:0."""
        compound = CompoundConditionEvaluator([hysteresis_eval, time_eval])
        rule_id = str(uuid.uuid4())

        cond = {
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
        await compound.evaluate(cond, make_context(rule_id))

        state_0 = hysteresis_eval.get_state_for_rule(rule_id, 0)
        assert state_0 is not None, "Hysterese-State bei idx=0 muss existieren"
        assert state_0.is_active is True

    @pytest.mark.asyncio
    async def test_hysteresis_at_index_1_uses_key_1(self, hysteresis_eval, time_eval):
        """AND(Time[0], Hysteresis[1]) — Hysterese-State-Key ist rule_id:1, NICHT rule_id:0."""
        compound = CompoundConditionEvaluator([hysteresis_eval, time_eval])
        rule_id = str(uuid.uuid4())

        cond = {
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
        await compound.evaluate(cond, make_context(rule_id))

        # State muss bei Index 1 sein, NICHT bei 0
        state_0 = hysteresis_eval.get_state_for_rule(rule_id, 0)
        state_1 = hysteresis_eval.get_state_for_rule(rule_id, 1)
        assert state_0 is None, "Index 0 muss leer sein (Hysterese ist an Position 1)"
        assert state_1 is not None, "Hysterese-State bei idx=1 muss existieren"
        assert state_1.is_active is True

    @pytest.mark.asyncio
    async def test_two_hysteresis_conditions_have_independent_states(self, hysteresis_eval):
        """OR(Hysteresis[0 gpio4], Hysteresis[1 gpio5]) — separate States, keine Kollision."""
        compound = CompoundConditionEvaluator([hysteresis_eval])
        rule_id = str(uuid.uuid4())

        cond = {
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

        # Sensor-Daten passen nur zu gpio=4
        ctx = make_context(rule_id, gpio=4, value=30.0)
        await compound.evaluate(cond, ctx)

        state_0 = hysteresis_eval.get_state_for_rule(rule_id, 0)
        state_1 = hysteresis_eval.get_state_for_rule(rule_id, 1)

        # gpio=4 → Condition 0 aktiv
        assert state_0 is not None
        assert state_0.is_active is True

        # gpio=5 → keine Aktivierung (Sensor-Match schlug fehl)
        assert state_1 is not None
        assert state_1.is_active is False

    @pytest.mark.asyncio
    async def test_condition_index_99_in_outer_context_is_overridden(self, hysteresis_eval):
        """Äußerer context["condition_index"]=99 wird von Compound auf 0 überschrieben."""
        compound = CompoundConditionEvaluator([hysteresis_eval])
        rule_id = str(uuid.uuid4())

        cond = {
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
            ],
        }

        ctx = make_context(rule_id, value=30.0)
        assert ctx["condition_index"] == 99  # Sicherstellen dass Outer-Context 99 hat

        await compound.evaluate(cond, ctx)

        # State-Key muss rule_id:0 sein (nicht rule_id:99)
        state_99 = hysteresis_eval.get_state_for_rule(rule_id, 99)
        state_0 = hysteresis_eval.get_state_for_rule(rule_id, 0)
        assert state_99 is None, "State für Index 99 darf nicht existieren"
        assert state_0 is not None
        assert state_0.is_active is True
