"""
Unit Tests: AUT-994 B1 — pump-freshness helper functions

These pure static helpers back the pump-freshness guard (LogicService):
- _iter_actuator_actions: enumerates actuator actions, descending one level into
  sequence steps (a pump hidden inside a sequence must still be detected).
- _flatten_sensor_conditions: recursively collects sensor conditions from nested
  compound structures (a sensor condition inside a compound must still be checked
  for require_fresh_data).
"""

from src.services.logic_service import LogicService


class TestIterActuatorActions:
    """_iter_actuator_actions descends into sequence steps."""

    def test_top_level_actuator_yielded(self):
        actions = [{"type": "actuator", "esp_id": "ESP_AABBCC01", "gpio": 5, "command": "ON"}]
        result = list(LogicService._iter_actuator_actions(actions))
        assert result == actions

    def test_actuator_command_alias_yielded(self):
        actions = [{"type": "actuator_command", "esp_id": "ESP_AABBCC01", "gpio": 5}]
        result = list(LogicService._iter_actuator_actions(actions))
        assert len(result) == 1

    def test_pump_inside_sequence_step_is_yielded(self):
        """AUT-994 bugfix: a pump addressed inside a sequence step must be detected."""
        actions = [
            {
                "type": "sequence",
                "steps": [
                    {"delay_seconds": 2},
                    {
                        "action": {
                            "type": "actuator",
                            "esp_id": "ESP_AABBCC01",
                            "gpio": 5,
                            "command": "ON",
                        }
                    },
                ],
            }
        ]
        result = list(LogicService._iter_actuator_actions(actions))
        assert len(result) == 1
        assert result[0]["esp_id"] == "ESP_AABBCC01"
        assert result[0]["gpio"] == 5

    def test_non_actuator_actions_ignored(self):
        actions = [
            {"type": "notification", "channel": "email"},
            {"type": "delay", "seconds": 5},
        ]
        result = list(LogicService._iter_actuator_actions(actions))
        assert result == []

    def test_sequence_step_without_action_ignored(self):
        actions = [{"type": "sequence", "steps": [{"delay_seconds": 1}]}]
        result = list(LogicService._iter_actuator_actions(actions))
        assert result == []


class TestFlattenSensorConditions:
    """_flatten_sensor_conditions recurses into nested compound conditions."""

    def test_single_sensor_condition(self):
        cond = {"type": "sensor", "esp_id": "ESP_DDEE0034", "gpio": 34}
        result = LogicService._flatten_sensor_conditions(cond)
        assert result == [cond]

    def test_flat_list_of_sensor_conditions(self):
        conds = [
            {"type": "sensor", "esp_id": "ESP_DDEE0034", "gpio": 34},
            {"type": "time_window", "start_hour": 8, "end_hour": 9},
            {"type": "sensor_threshold", "esp_id": "ESP_DDEE0035", "gpio": 35},
        ]
        result = LogicService._flatten_sensor_conditions(conds)
        assert len(result) == 2
        assert all(c["type"] in ("sensor", "sensor_threshold") for c in result)

    def test_top_level_compound(self):
        cond = {
            "logic": "AND",
            "conditions": [
                {"type": "sensor", "esp_id": "ESP_DDEE0034", "gpio": 34},
                {"type": "time_window", "start_hour": 8, "end_hour": 9},
            ],
        }
        result = LogicService._flatten_sensor_conditions(cond)
        assert len(result) == 1
        assert result[0]["gpio"] == 34

    def test_compound_nested_inside_list_is_recursed(self):
        """AUT-994 bugfix: a sensor condition inside a compound inside a list is found."""
        conds = [
            {
                "logic": "AND",
                "conditions": [
                    {
                        "type": "sensor",
                        "esp_id": "ESP_DDEE0034",
                        "gpio": 34,
                        "require_fresh_data": False,
                    },
                ],
            }
        ]
        result = LogicService._flatten_sensor_conditions(conds)
        assert len(result) == 1
        assert result[0]["esp_id"] == "ESP_DDEE0034"
        assert result[0].get("require_fresh_data") is False

    def test_deeply_nested_compounds(self):
        cond = {
            "logic": "OR",
            "conditions": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "sensor", "esp_id": "ESP_DDEE0034", "gpio": 34},
                        {"type": "hysteresis", "esp_id": "ESP_DDEE0034", "gpio": 34},
                    ],
                },
                {"type": "sensor", "esp_id": "ESP_DDEE0035", "gpio": 35},
            ],
        }
        result = LogicService._flatten_sensor_conditions(cond)
        assert len(result) == 2
        gpios = sorted(c["gpio"] for c in result)
        assert gpios == [34, 35]
