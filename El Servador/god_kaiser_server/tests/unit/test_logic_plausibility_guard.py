"""
Unit Tests: AUT-994 B2 — Plausibility Guard in SensorConditionEvaluator

A trigger reading flagged quality="critical" (SENSOR_PHYSICAL_LIMITS violation,
sensor_handler.py) must never dispatch an action — even when the raw comparison
would otherwise evaluate True. This guards the "pH=268 (cable fault) starts a
dosing pump" failure mode.

Scope note (AUT-994 narrowed 3-file trigger path): the guard covers the TRIGGER
sensor only (context["sensor_data"]["quality"]). Critical values referenced as
cross-sensor values are not yet blocked — that is the fuller AUT-645 coupling and
is intentionally out of scope here.
"""

import pytest

from src.services.logic.conditions.hysteresis_evaluator import HysteresisConditionEvaluator
from src.services.logic.conditions.sensor_evaluator import SensorConditionEvaluator


class TestSensorConditionEvaluatorPlausibilityGuard:
    """AUT-994 B2: quality="critical" guard on the trigger reading."""

    @pytest.fixture
    def evaluator(self):
        return SensorConditionEvaluator()

    # ── quality="critical" on trigger → never dispatch ──────────────

    @pytest.mark.asyncio
    async def test_critical_trigger_blocks_even_when_condition_would_trigger(self, evaluator):
        """pH=268 (>6.5 → would fire a dose) but quality="critical" → condition False."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 34,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 268.0,  # cable-fault reading, way outside 0..14
                "quality": "critical",
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_critical_trigger_blocks_wins_over_fresh_data(self, evaluator):
        """Guard runs BEFORE the freshness check.

        The sensor is on_demand + stale (age > freshness), so if the AUT-41 freshness
        check ran first it would append a `_stale_reason`. Asserting that no stale reason
        was recorded proves the quality guard short-circuited first.
        """
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 34,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 268.0,
                "quality": "critical",
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 7200,  # 2h > 1h → would be flagged stale if reached
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False
        # Guard short-circuits before freshness bookkeeping — no stale reason recorded.
        assert "_stale_reasons" not in context

    # ── Non-critical quality → evaluate normally ────────────────────

    @pytest.mark.asyncio
    async def test_good_quality_evaluates_normally(self, evaluator):
        """quality="good" with a real over-threshold reading → condition True."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 34,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 7.2,
                "quality": "good",
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_quality_evaluates_normally(self, evaluator):
        """No quality key present → backward-compatible, evaluate normally."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 34,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 7.2,
                # quality intentionally absent
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_other_quality_levels_do_not_block(self, evaluator):
        """Only "critical" blocks; "degraded"/"warming_up" still evaluate normally."""
        for quality in ("degraded", "warming_up", "stale", "unknown"):
            condition = {
                "type": "sensor",
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "operator": ">",
                "value": 6.5,
            }
            context = {
                "sensor_data": {
                    "esp_id": "ESP_01",
                    "gpio": 34,
                    "sensor_type": "ph",
                    "value": 7.2,
                    "quality": quality,
                },
            }
            result = await evaluator.evaluate(condition, context)
            assert result is True, f"quality={quality!r} must not block dispatch"

    # ── Scope boundary: cross-sensor critical value is NOT guarded ──

    @pytest.mark.asyncio
    async def test_critical_cross_sensor_value_not_blocked_trigger_scope(self, evaluator):
        """AUT-994 narrowed scope: the guard is trigger-only.

        A critical flag carried on a CROSS-sensor reading is not consulted (the
        cross-sensor loader does not yet propagate quality). Documents the known
        boundary so a future extension to the cross-sensor path is a deliberate change.
        """
        condition = {
            "type": "sensor",
            "esp_id": "ESP_02",
            "gpio": 10,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
            "require_fresh_data": False,
        }
        context = {
            # Trigger is a different, healthy sensor.
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "sensor_type": "temperature",
                "value": 22.0,
                "quality": "good",
            },
            "sensor_values": {
                "ESP_02:10:ph": {
                    "value": 268.0,
                    "sensor_type": "ph",
                    "quality": "critical",  # ignored by the trigger-scoped guard
                },
            },
        }
        result = await evaluator.evaluate(condition, context)
        # Cross-sensor value 268 > 6.5 → True, guard does not intervene here.
        assert result is True


class TestHysteresisEvaluatorPlausibilityGuard:
    """AUT-994 B2: quality="critical" guard also covers the hysteresis trigger path.

    A hysteresis condition on the trigger sensor must not ACTIVATE (spurious dose start)
    nor DEACTIVATE (spurious OFF) on an implausible reading — it holds the current state.
    """

    @pytest.fixture
    def evaluator(self):
        return HysteresisConditionEvaluator()  # in-memory only, no DB

    def _cooling_condition(self):
        return {
            "type": "hysteresis",
            "esp_id": "ESP_01",
            "gpio": 34,
            "sensor_type": "ph",
            "activate_above": 6.5,
            "deactivate_below": 6.0,
        }

    @pytest.mark.asyncio
    async def test_critical_reading_does_not_activate(self, evaluator):
        """State inactive + critical pH=268 (>6.5) → must NOT activate (no dose start)."""
        context = {
            "rule_id": "rule-crit-1",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 268.0,
                "quality": "critical",
            },
        }
        result = await evaluator.evaluate(self._cooling_condition(), context)
        assert result is False  # held inactive
        assert "_hysteresis_just_deactivated" not in context
        assert evaluator.get_state_for_rule("rule-crit-1", 0) is None or (
            evaluator.get_state_for_rule("rule-crit-1", 0).is_active is False
        )

    @pytest.mark.asyncio
    async def test_critical_reading_does_not_deactivate_active_state(self, evaluator):
        """State active + critical value below deactivate → hold active, NO OFF signal."""
        # Prime state to active via a legitimate reading (value 7.0 > 6.5).
        good_ctx = {
            "rule_id": "rule-crit-2",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 7.0,
                "quality": "good",
            },
        }
        assert await evaluator.evaluate(self._cooling_condition(), good_ctx) is True

        # Now a critical (implausible) reading arrives.
        crit_ctx = {
            "rule_id": "rule-crit-2",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": -999.0,
                "quality": "critical",
            },
        }
        result = await evaluator.evaluate(self._cooling_condition(), crit_ctx)
        assert result is True  # held active
        # Crucially: no deactivation signal → _evaluate_rule will not dispatch OFF.
        assert "_hysteresis_just_deactivated" not in crit_ctx
        assert evaluator.get_state_for_rule("rule-crit-2", 0).is_active is True

    @pytest.mark.asyncio
    async def test_good_reading_still_activates(self, evaluator):
        """Backward compat: a good over-threshold reading still activates normally."""
        context = {
            "rule_id": "rule-good-1",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 34,
                "sensor_type": "ph",
                "value": 7.0,
                "quality": "good",
            },
        }
        result = await evaluator.evaluate(self._cooling_condition(), context)
        assert result is True
