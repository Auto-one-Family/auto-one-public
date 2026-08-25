"""
Unit Tests: AUT-1145 (S0) — LogicService._patch_quick_field_conditions()

Pure pre-processing step for the bulk quick-field endpoint: applies An/Aus,
Schwellwert/Zielwert or Zeiten onto a rule's existing (possibly compound)
conditions list. NOT a persistence path — the caller feeds the result into a
normal LogicRuleUpdate(conditions=...) and persists via update_rule() like
any other PUT /rules/{id} payload. No DB/MQTT/HTTP, no mocking needed.
"""

import pytest

from src.services.logic_service import LogicService


class TestPatchThresholdValue:
    def test_replaces_value_on_sensor_threshold_condition(self):
        result = LogicService._patch_quick_field_conditions(
            [{"type": "sensor", "esp_id": "ESP_001", "gpio": 34, "operator": ">", "value": 7.0}],
            threshold_value=8.5,
        )
        assert result == [
            {"type": "sensor", "esp_id": "ESP_001", "gpio": 34, "operator": ">", "value": 8.5}
        ]

    def test_no_threshold_condition_raises_value_error(self):
        with pytest.raises(ValueError):
            LogicService._patch_quick_field_conditions(
                [{"type": "time_window", "start_hour": 8, "end_hour": 18}],
                threshold_value=8.5,
            )


class TestPatchHysteresisPair:
    def test_cooling_mode_replaces_activate_above_and_deactivate_below(self):
        result = LogicService._patch_quick_field_conditions(
            [
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_001",
                    "gpio": 4,
                    "activate_above": 28.0,
                    "deactivate_below": 24.0,
                }
            ],
            hysteresis_on_value=29.0,
            hysteresis_off_value=25.0,
        )
        assert result[0]["activate_above"] == 29.0
        assert result[0]["deactivate_below"] == 25.0

    def test_heating_mode_replaces_activate_below_and_deactivate_above(self):
        result = LogicService._patch_quick_field_conditions(
            [
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_001",
                    "gpio": 4,
                    "activate_below": 18.0,
                    "deactivate_above": 22.0,
                }
            ],
            hysteresis_on_value=17.0,
            hysteresis_off_value=21.0,
        )
        assert result[0]["activate_below"] == 17.0
        assert result[0]["deactivate_above"] == 21.0

    def test_only_on_value_leaves_off_value_untouched(self):
        result = LogicService._patch_quick_field_conditions(
            [
                {
                    "type": "hysteresis",
                    "esp_id": "ESP_001",
                    "gpio": 4,
                    "activate_above": 28.0,
                    "deactivate_below": 24.0,
                }
            ],
            hysteresis_on_value=30.0,
        )
        assert result[0]["activate_above"] == 30.0
        assert result[0]["deactivate_below"] == 24.0


class TestPatchTimeWindow:
    def test_replaces_only_provided_time_fields(self):
        result = LogicService._patch_quick_field_conditions(
            [
                {
                    "type": "time_window",
                    "start_hour": 8,
                    "start_minute": 0,
                    "end_hour": 18,
                    "end_minute": 0,
                    "days_of_week": [0, 1, 2, 3, 4],
                }
            ],
            start_hour=9,
            end_hour=17,
        )
        assert result[0]["start_hour"] == 9
        assert result[0]["end_hour"] == 17
        assert result[0]["start_minute"] == 0
        assert result[0]["days_of_week"] == [0, 1, 2, 3, 4]

    def test_replaces_days_of_week(self):
        result = LogicService._patch_quick_field_conditions(
            [{"type": "time", "start_hour": 8, "end_hour": 18, "days_of_week": [0]}],
            days_of_week=[0, 1, 2, 3, 4, 5, 6],
        )
        assert result[0]["days_of_week"] == [0, 1, 2, 3, 4, 5, 6]


class TestPatchCompoundConditions:
    def test_descends_into_and_or_nested_conditions(self):
        result = LogicService._patch_quick_field_conditions(
            {
                "logic": "AND",
                "conditions": [
                    {
                        "type": "sensor",
                        "esp_id": "ESP_001",
                        "gpio": 34,
                        "operator": ">",
                        "value": 7.0,
                    },
                    {"type": "time_window", "start_hour": 8, "end_hour": 18},
                ],
            },
            threshold_value=9.0,
        )
        nested = result[0]["conditions"]
        assert nested[0]["value"] == 9.0
        assert nested[1]["start_hour"] == 8  # untouched — no time field requested


class TestPatchNoFieldsRequested:
    def test_no_quick_fields_returns_conditions_unchanged(self):
        conditions = [
            {"type": "sensor", "esp_id": "ESP_001", "gpio": 34, "operator": ">", "value": 7.0}
        ]
        result = LogicService._patch_quick_field_conditions(conditions)
        assert result == conditions
