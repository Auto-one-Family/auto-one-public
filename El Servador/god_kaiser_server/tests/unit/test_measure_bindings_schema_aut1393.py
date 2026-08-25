"""
AUT-1393 [M-1]: measure_bindings[] schema + never enters trigger index.

Given/When/Then from issue:
- Without binding → unchanged metadata path
- With binding only (no sensor trigger) → not in get_rules_by_trigger_sensor
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.db.repositories.logic_repo import LogicRepository
from src.schemas.logic import (
    LogicRuleCreate,
    LogicRuleUpdate,
    MeasureBinding,
    _validate_rule_metadata_measure_bindings,
)


def _valid_binding(**overrides):
    base = {
        "sensor_refs": [
            {"esp_id": "ESP_12AB34CD", "gpio": 34, "sensor_type": "ec"},
        ],
        "hooks": ["on_start", "after_settle"],
        "formula_id": "difference",
        "formula_params": {},
        "output_target": "execution_metadata",
    }
    base.update(overrides)
    return base


def test_measure_binding_model_accepts_live_refs():
    binding = MeasureBinding.model_validate(_valid_binding())
    assert binding.sensor_refs[0].esp_id == "ESP_12AB34CD"
    assert binding.hooks == ["on_start", "after_settle"]
    assert binding.formula_id == "difference"


def test_measure_binding_rejects_unknown_hook():
    with pytest.raises(ValidationError):
        MeasureBinding.model_validate(_valid_binding(hooks=["whenever"]))


def test_measure_binding_rejects_config_uuid_as_esp_id():
    with pytest.raises(ValidationError):
        MeasureBinding.model_validate(
            _valid_binding(
                sensor_refs=[
                    {
                        "esp_id": "550e8400-e29b-41d4-a716-446655440000",
                        "gpio": 34,
                        "sensor_type": "ec",
                    }
                ]
            )
        )


def test_rule_metadata_without_measure_bindings_passthrough():
    meta = {"dose_config": {"target_value": 1.8}}
    assert _validate_rule_metadata_measure_bindings(meta) == meta


def test_logic_rule_create_validates_measure_bindings():
    payload = {
        "name": "Measure binding schema rule",
        "conditions": [
            {
                "type": "time",
                "start_time": "06:00",
                "end_time": "22:00",
            }
        ],
        "actions": [
            {
                "type": "actuator",
                "esp_id": "ESP_AABBCCDD",
                "gpio": 5,
                "command": "OFF",
                "value": 0.0,
            }
        ],
        "rule_metadata": {"measure_bindings": [_valid_binding()]},
    }
    created = LogicRuleCreate.model_validate(payload)
    assert created.rule_metadata["measure_bindings"][0]["formula_id"] == "difference"


def test_logic_rule_create_rejects_invalid_measure_bindings():
    payload = {
        "name": "Bad measure binding",
        "conditions": [
            {"type": "time", "start_time": "06:00", "end_time": "22:00"},
        ],
        "actions": [
            {
                "type": "actuator",
                "esp_id": "ESP_AABBCCDD",
                "gpio": 5,
                "command": "OFF",
                "value": 0.0,
            }
        ],
        "rule_metadata": {
            "measure_bindings": [_valid_binding(formula_id="not_a_formula")],
        },
    }
    with pytest.raises(ValidationError):
        LogicRuleCreate.model_validate(payload)


def test_logic_rule_update_validates_measure_bindings():
    updated = LogicRuleUpdate.model_validate(
        {"rule_metadata": {"measure_bindings": [_valid_binding(formula_id="delta_over_event")]}}
    )
    assert updated.rule_metadata["measure_bindings"][0]["formula_id"] == "delta_over_event"


@pytest.mark.asyncio
async def test_measure_bindings_do_not_enter_trigger_index():
    """
    Given a rule with measure_bindings for ESP:GPIO:ec but no sensor trigger.
    When get_rules_by_trigger_sensor is queried for that sensor.
    Then the rule is NOT returned.
    """
    repo = LogicRepository(session=MagicMock())
    rule = MagicMock()
    rule.trigger_conditions = [
        {"type": "time", "start_time": "06:00", "end_time": "22:00"},
    ]
    rule.rule_metadata = {"measure_bindings": [_valid_binding()]}
    rule.enabled = True
    repo.get_enabled_rules = AsyncMock(return_value=[rule])

    matched = await repo.get_rules_by_trigger_sensor("ESP_12AB34CD", 34, "ec")
    assert matched == []


@pytest.mark.asyncio
async def test_sensor_trigger_still_matches_without_measure_bindings():
    """Given classic sensor trigger and empty metadata — still matches (bit-identical)."""
    repo = LogicRepository(session=MagicMock())
    rule = MagicMock()
    rule.trigger_conditions = [
        {
            "type": "sensor",
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ec",
            "operator": ">",
            "value": 1.0,
        }
    ]
    rule.rule_metadata = {}
    rule.enabled = True
    repo.get_enabled_rules = AsyncMock(return_value=[rule])

    matched = await repo.get_rules_by_trigger_sensor("ESP_12AB34CD", 34, "ec")
    assert matched == [rule]
