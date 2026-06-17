"""
Unit Tests: AUT-41 — Freshness-Aware Sensor Condition Evaluation

Tests require_fresh_data flag behavior in SensorConditionEvaluator
and stale_reasons propagation in CompoundConditionEvaluator.
"""

import pytest

from src.services.logic.conditions.sensor_evaluator import SensorConditionEvaluator
from src.services.logic.conditions.compound_evaluator import CompoundConditionEvaluator


class TestSensorConditionEvaluatorFreshness:
    """AUT-41: require_fresh_data flag on SensorConditionEvaluator."""

    @pytest.fixture
    def evaluator(self):
        return SensorConditionEvaluator()

    # ── require_fresh_data=False (default) ──────────────────────────

    @pytest.mark.asyncio
    async def test_require_fresh_data_false_ignores_stale(self, evaluator):
        """require_fresh_data=False: stale data does NOT block condition (backward compat)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": False,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 7200,  # 2h > 1h freshness
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context

    @pytest.mark.asyncio
    async def test_no_require_fresh_data_field_behaves_as_false(self, evaluator):
        """Omitting require_fresh_data entirely is the same as False (backward compat)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 7200,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    # ── require_fresh_data=True + stale → False ────────────────────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_stale_returns_false(self, evaluator):
        """require_fresh_data=True with stale on_demand sensor → condition False + stale reason."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
            "sensor_type": "ph",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "sensor_type": "ph",
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 7200,  # 2h > 1h
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False
        assert "_stale_reasons" in context
        assert len(context["_stale_reasons"]) == 1
        reason = context["_stale_reasons"][0]
        assert reason["esp_id"] == "ESP_01"
        assert reason["gpio"] == 5
        assert reason["operating_mode"] == "on_demand"
        assert reason["age_seconds"] == 7200
        assert reason["freshness_limit_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_stale_scheduled(self, evaluator):
        """require_fresh_data=True with stale scheduled sensor → condition False."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_02",
            "gpio": 10,
            "operator": "<",
            "value": 50.0,
            "require_fresh_data": True,
            "sensor_type": "moisture",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_02",
                "gpio": 10,
                "value": 30.0,
                "sensor_type": "moisture",
                "operating_mode": "scheduled",
                "measurement_freshness_hours": 2,
                "age_seconds": 10000,  # ~2.8h > 2h
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False
        assert len(context["_stale_reasons"]) == 1

    # ── require_fresh_data=True + fresh → True ─────────────────────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_fresh_returns_true(self, evaluator):
        """require_fresh_data=True with fresh on_demand sensor → condition evaluates normally."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
            "sensor_type": "ph",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "sensor_type": "ph",
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 600,  # 10min < 1h
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context

    # ── Continuous mode: require_fresh_data=True has no effect ──────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_continuous_mode_not_blocked(self, evaluator):
        """Continuous sensors are never blocked by require_fresh_data (backward compat)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "continuous",
                "measurement_freshness_hours": 1,
                "age_seconds": 99999,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context

    # ── No freshness config: require_fresh_data=True does not hard-block ──

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_no_freshness_config_not_blocked(self, evaluator):
        """No measurement_freshness_hours configured → no hard block even with require_fresh_data."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": None,
                "age_seconds": 99999,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_freshness_hours_zero_not_blocked(self, evaluator):
        """measurement_freshness_hours=0 → no hard block (treated as unconfigured)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 0,
                "age_seconds": 99999,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    # ── Cross-sensor freshness check ────────────────────────────────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_cross_sensor_stale(self, evaluator):
        """require_fresh_data=True with stale cross-sensor data → condition False."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_02",
            "gpio": 10,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
            "sensor_type": "temperature",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 50.0,
            },
            "sensor_values": {
                "ESP_02:10:temperature": {
                    "value": 30.0,
                    "sensor_type": "temperature",
                    "operating_mode": "on_demand",
                    "measurement_freshness_hours": 1,
                    "age_seconds": 7200,
                },
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False
        assert len(context["_stale_reasons"]) == 1
        assert context["_stale_reasons"][0]["esp_id"] == "ESP_02"

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_cross_sensor_fresh(self, evaluator):
        """require_fresh_data=True with fresh cross-sensor data → evaluates normally."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_02",
            "gpio": 10,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
            "sensor_type": "temperature",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 50.0,
            },
            "sensor_values": {
                "ESP_02:10:temperature": {
                    "value": 30.0,
                    "sensor_type": "temperature",
                    "operating_mode": "on_demand",
                    "measurement_freshness_hours": 2,
                    "age_seconds": 3600,  # 1h < 2h
                },
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context

    # ── No age_seconds in meta: do not block ─────────────────────────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_no_age_seconds_not_blocked(self, evaluator):
        """Missing age_seconds in meta → no stale determination possible, don't block."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                # age_seconds intentionally missing
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    # ── Edge: value exactly at freshness limit → still fresh ──────

    @pytest.mark.asyncio
    async def test_require_fresh_data_true_exactly_at_limit_is_fresh(self, evaluator):
        """age_seconds == freshness_limit_seconds → still considered fresh (<=)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "require_fresh_data": True,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 3600,  # exactly at limit
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context


class TestCompoundEvaluatorStaleReasonPropagation:
    """AUT-41: Stale reasons propagation through CompoundConditionEvaluator."""

    @pytest.fixture
    def evaluator(self):
        sensor_eval = SensorConditionEvaluator()
        compound_eval = CompoundConditionEvaluator([sensor_eval])
        return compound_eval

    @pytest.mark.asyncio
    async def test_compound_and_propagates_stale_reasons(self, evaluator):
        """AND compound: stale reason from sub-condition is visible in parent context."""
        condition = {
            "logic": "AND",
            "conditions": [
                {
                    "type": "sensor",
                    "esp_id": "ESP_01",
                    "gpio": 5,
                    "operator": ">",
                    "value": 25.0,
                    "require_fresh_data": True,
                },
                {
                    "type": "sensor",
                    "esp_id": "ESP_01",
                    "gpio": 10,
                    "operator": "<",
                    "value": 50.0,
                },
            ],
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 1,
                "age_seconds": 7200,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False
        assert "_stale_reasons" in context
        assert len(context["_stale_reasons"]) == 1
        assert context["_stale_reasons"][0]["esp_id"] == "ESP_01"
        assert context["_stale_reasons"][0]["gpio"] == 5

    @pytest.mark.asyncio
    async def test_compound_or_propagates_stale_reasons(self, evaluator):
        """OR compound: stale reasons are propagated even when other condition passes."""
        condition = {
            "logic": "OR",
            "conditions": [
                {
                    "type": "sensor",
                    "esp_id": "ESP_01",
                    "gpio": 5,
                    "operator": ">",
                    "value": 25.0,
                    "require_fresh_data": True,
                },
                {
                    "type": "sensor",
                    "esp_id": "ESP_01",
                    "gpio": 10,
                    "operator": "<",
                    "value": 50.0,
                },
            ],
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 10,
                "value": 30.0,
            },
            "sensor_values": {
                "ESP_01:5": {
                    "value": 30.0,
                    "sensor_type": None,
                    "operating_mode": "on_demand",
                    "measurement_freshness_hours": 1,
                    "age_seconds": 7200,
                },
            },
        }
        result = await evaluator.evaluate(condition, context)
        # OR: second condition passes (30 < 50), so overall True
        assert result is True
        # But stale reasons from first condition should still be propagated
        assert "_stale_reasons" in context
        assert len(context["_stale_reasons"]) == 1

    @pytest.mark.asyncio
    async def test_compound_no_stale_when_all_fresh(self, evaluator):
        """Compound with all fresh data: no stale reasons set."""
        condition = {
            "logic": "AND",
            "conditions": [
                {
                    "type": "sensor",
                    "esp_id": "ESP_01",
                    "gpio": 5,
                    "operator": ">",
                    "value": 25.0,
                    "require_fresh_data": True,
                },
            ],
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "operating_mode": "on_demand",
                "measurement_freshness_hours": 2,
                "age_seconds": 600,
            },
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True
        assert "_stale_reasons" not in context
