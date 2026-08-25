"""
AUT-1124: POST /logic/rules/{id}/test must evaluate hysteresis via the same
HysteresisConditionEvaluator used by the live path — both activate and deactivate.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.schemas.logic import RuleTestRequest
from src.services.logic.conditions.hysteresis_evaluator import HysteresisConditionEvaluator
from src.services.logic_service import LogicService


def _ph_raise_rule() -> SimpleNamespace:
    """Heating-mode hysteresis as used by pH-raise dosing rules (activate_below)."""
    return SimpleNamespace(
        id=uuid4(),
        name="pH Anheben",
        conditions=[
            {
                "type": "hysteresis",
                "esp_id": "ESP_12AB34",
                "gpio": 34,
                "sensor_type": "ph",
                "activate_below": 6.5,
                "deactivate_above": 7.0,
            }
        ],
        actions=[
            {
                "type": "actuator",
                "esp_id": "ESP_AABBCC",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
            }
        ],
        logic_operator="AND",
    )


def _ec_control_rule_us_cm() -> SimpleNamespace:
    """AUT-1270: EC Steuerung after µS/cm migration (activate_below=1600)."""
    return SimpleNamespace(
        id=uuid4(),
        name="EC Steuerung",
        conditions=[
            {
                "type": "hysteresis",
                "esp_id": "ESP_AEAE64",
                "gpio": 0,
                "sensor_type": "ec",
                "activate_below": 1600,
                "deactivate_above": 1700,
            }
        ],
        actions=[
            {
                "type": "actuator",
                "esp_id": "ESP_AEAE64",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
            }
        ],
        logic_operator="AND",
    )


@pytest.fixture
def logic_service() -> LogicService:
    """LogicService with default evaluators (incl. HysteresisConditionEvaluator)."""
    return LogicService(logic_repo=MagicMock())


@pytest.mark.asyncio
class TestLogicServiceHysteresisDryRun:
    """Dry-run must match live hysteresis evaluator semantics (Schwelle ein / aus)."""

    async def test_hysteresis_activate_below_triggers(self, logic_service: LogicService):
        """Schwelle ein: mock value below activate_below → would_trigger True."""
        rule = _ph_raise_rule()
        response = await logic_service.test_rule(
            rule,
            RuleTestRequest(
                mock_sensor_values={"ESP_12AB34:34": 6.2},
                dry_run=True,
            ),
        )

        assert response.would_trigger is True
        assert len(response.condition_results) == 1
        cond = response.condition_results[0]
        assert cond.condition_type == "hysteresis"
        assert cond.result is True
        assert cond.actual_value == 6.2

    async def test_ec_steuerung_triggers_at_989_us_cm_after_migration(
        self, logic_service: LogicService
    ):
        """AUT-1270: processed=989 µS/cm < activate_below=1600 → would_trigger True."""
        rule = _ec_control_rule_us_cm()
        response = await logic_service.test_rule(
            rule,
            RuleTestRequest(
                mock_sensor_values={"ESP_AEAE64:0": 989},
                dry_run=True,
            ),
        )
        assert response.would_trigger is True
        assert response.condition_results[0].result is True
        assert response.condition_results[0].actual_value == 989

    async def test_hysteresis_deactivate_above_releases(self, logic_service: LogicService):
        """Schwelle aus: after activate, value above deactivate_above → would_trigger False."""
        rule = _ph_raise_rule()

        # Same LogicService instance keeps hysteresis in-memory state across calls
        # (mirrors successive live evaluations on one HysteresisConditionEvaluator).
        activated = await logic_service.test_rule(
            rule,
            RuleTestRequest(
                mock_sensor_values={"ESP_12AB34:34": 6.2},
                dry_run=True,
            ),
        )
        assert activated.would_trigger is True

        released = await logic_service.test_rule(
            rule,
            RuleTestRequest(
                mock_sensor_values={"ESP_12AB34:34": 7.2},
                dry_run=True,
            ),
        )

        assert released.would_trigger is False
        assert released.condition_results[0].condition_type == "hysteresis"
        assert released.condition_results[0].result is False
        assert released.condition_results[0].actual_value == 7.2

    async def test_dry_run_matches_live_evaluator_activate_and_deactivate(self):
        """Parity: LogicService.test_rule result == bare HysteresisConditionEvaluator."""
        rule = _ph_raise_rule()
        condition = rule.conditions[0]
        live_eval = HysteresisConditionEvaluator()
        service = LogicService(logic_repo=MagicMock())

        # Activate
        live_on = await live_eval.evaluate(
            condition,
            {
                "rule_id": str(rule.id),
                "condition_index": 0,
                "sensor_data": {
                    "esp_id": "ESP_12AB34",
                    "gpio": 34,
                    "value": 6.2,
                    "sensor_type": "ph",
                },
            },
        )
        dry_on = await service.test_rule(
            rule,
            RuleTestRequest(mock_sensor_values={"ESP_12AB34:34": 6.2}, dry_run=True),
        )
        assert dry_on.would_trigger is live_on is True

        # Deactivate
        live_off = await live_eval.evaluate(
            condition,
            {
                "rule_id": str(rule.id),
                "condition_index": 0,
                "sensor_data": {
                    "esp_id": "ESP_12AB34",
                    "gpio": 34,
                    "value": 7.2,
                    "sensor_type": "ph",
                },
            },
        )
        dry_off = await service.test_rule(
            rule,
            RuleTestRequest(mock_sensor_values={"ESP_12AB34:34": 7.2}, dry_run=True),
        )
        assert dry_off.would_trigger is live_off is False
