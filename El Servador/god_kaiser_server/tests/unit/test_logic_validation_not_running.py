"""AUT-1333: Persistenz-Naht für not_running (Validation-Whitelist)."""

import pytest
from pydantic import ValidationError

from src.db.models.logic_validation import NotRunningCondition, validate_condition


class TestNotRunningValidation:
    def test_accepts_actuator_target(self):
        cond = validate_condition(
            {
                "type": "not_running",
                "target": "actuator",
                "esp_id": "af2fc332-dc7f-4cea-b32d-758a4508361e",
                "gpio": 25,
            }
        )
        assert isinstance(cond, NotRunningCondition)
        assert cond.target == "actuator"
        assert cond.gpio == 25

    def test_accepts_sequence_target(self):
        cond = validate_condition(
            {
                "type": "not_running",
                "target": "sequence",
                "rule_id": "4df64c75-17e2-4f57-8772-24f71663f6f0",
            }
        )
        assert isinstance(cond, NotRunningCondition)
        assert cond.target == "sequence"
        assert cond.rule_id == "4df64c75-17e2-4f57-8772-24f71663f6f0"

    def test_accepts_and_compound_with_not_running(self):
        cond = validate_condition(
            {
                "logic": "AND",
                "conditions": [
                    {
                        "type": "hysteresis",
                        "esp_id": "ESP_AEAE64",
                        "gpio": 0,
                        "sensor_type": "ec",
                        "activate_below": 1300,
                        "deactivate_above": 1400,
                    },
                    {
                        "type": "not_running",
                        "target": "actuator",
                        "esp_id": "af2fc332-dc7f-4cea-b32d-758a4508361e",
                        "gpio": 25,
                    },
                ],
            }
        )
        assert cond.logic == "AND"
        assert any(isinstance(c, NotRunningCondition) for c in cond.conditions)

    def test_rejects_unknown_before_fix_was_the_gap(self):
        # Smoke: still rejects truly unknown types
        with pytest.raises(ValueError, match="Unknown condition type"):
            validate_condition({"type": "totally_unknown_type"})

    def test_rejects_actuator_without_gpio(self):
        with pytest.raises(ValidationError):
            validate_condition(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": "af2fc332-dc7f-4cea-b32d-758a4508361e",
                }
            )

    def test_rejects_sequence_without_rule_id(self):
        with pytest.raises(ValidationError):
            validate_condition({"type": "not_running", "target": "sequence"})

    def test_rejects_esp_xxxx_string_for_actuator(self):
        with pytest.raises(ValidationError):
            validate_condition(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": "ESP_57E1D4",
                    "gpio": 25,
                }
            )
