"""
AUT-1317 (R-S2): action-level condition_refs / condition_op + safety OFF helpers.

Pure unit tests — no DB/MQTT. Covers D4 absenz, Fall 1/2 gating, validation
round-trip, and safety-critical routed OFF classification.
"""

from src.db.models.logic_validation import (
    ActuatorCommandAction,
    NotificationAction,
    validate_action,
    validate_actions,
)
from src.services.logic_engine import LogicEngine


class TestActionRoutingValidation:
    def test_actuator_accepts_condition_refs_and_op(self):
        action = validate_action(
            {
                "type": "actuator_command",
                "esp_id": "ESP_12AB34",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
                "condition_refs": [0],
                "condition_op": "AND",
            }
        )
        assert isinstance(action, ActuatorCommandAction)
        assert action.condition_refs == [0]
        assert action.condition_op == "AND"
        dumped = action.model_dump()
        assert dumped["condition_refs"] == [0]
        assert dumped["condition_op"] == "AND"

    def test_notification_accepts_condition_refs(self):
        action = validate_action(
            {
                "type": "notification",
                "channel": "websocket",
                "target": "alerts",
                "message_template": "hi",
                "condition_refs": [3],
                "condition_op": "OR",
            }
        )
        assert isinstance(action, NotificationAction)
        assert action.condition_refs == [3]
        assert action.condition_op == "OR"

    def test_absent_refs_round_trip_defaults_null(self):
        action = validate_action(
            {
                "type": "actuator_command",
                "esp_id": "ESP_12AB34",
                "gpio": 25,
                "command": "OFF",
                "value": 0.0,
            }
        )
        dumped = action.model_dump()
        assert dumped["condition_refs"] is None
        assert dumped["condition_op"] is None
        assert dumped["is_safety_critical"] is False

    def test_is_safety_critical_persists_on_actuator(self):
        action = validate_action(
            {
                "type": "actuator",
                "esp_id": "ESP_12AB34",
                "gpio": 25,
                "command": "OFF",
                "value": 0.0,
                "condition_refs": [1],
                "is_safety_critical": True,
            }
        )
        assert action.is_safety_critical is True
        assert action.model_dump()["is_safety_critical"] is True

    def test_invalid_condition_op_rejected(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            validate_action(
                {
                    "type": "actuator_command",
                    "esp_id": "ESP_12AB34",
                    "gpio": 25,
                    "command": "ON",
                    "value": 1.0,
                    "condition_op": "XOR",
                }
            )

    def test_validate_actions_mixed_routed_and_flat(self):
        validated = validate_actions(
            [
                {
                    "type": "actuator_command",
                    "esp_id": "ESP_12AB34",
                    "gpio": 25,
                    "command": "ON",
                    "value": 1.0,
                    "condition_refs": [0],
                },
                {
                    "type": "actuator_command",
                    "esp_id": "ESP_12AB34",
                    "gpio": 25,
                    "command": "OFF",
                    "value": 0.0,
                },
            ]
        )
        assert validated[0].condition_refs == [0]
        assert validated[1].condition_refs is None


class TestConditionGateHelpers:
    def test_d4_absent_and_empty_use_global_gate(self):
        results = [True, False]
        assert (
            LogicEngine._action_passes_condition_gate({}, results, True, "AND") is True
        )
        assert (
            LogicEngine._action_passes_condition_gate(
                {"condition_refs": None}, results, False, "AND"
            )
            is False
        )
        assert (
            LogicEngine._action_passes_condition_gate(
                {"condition_refs": []}, results, True, "AND"
            )
            is True
        )

    def test_fall1_on_c0_off_c1(self):
        """A_ON←C0 / A_OFF←C1 — only matching action fires."""
        results = [True, False]  # C0 start true, C1 stop false
        on_action = {"condition_refs": [0], "command": "ON"}
        off_action = {
            "condition_refs": [1],
            "command": "OFF",
            "is_safety_critical": True,
            "type": "actuator_command",
        }
        gated = LogicEngine._filter_actions_by_condition_gate(
            [on_action, off_action], results, False, "OR"
        )
        assert gated == [on_action]

        results_stop = [False, True]
        gated_stop = LogicEngine._filter_actions_by_condition_gate(
            [on_action, off_action], results_stop, True, "OR"
        )
        assert gated_stop == [off_action]

    def test_fall2_or_over_time_refs(self):
        """One irrigation action with OR over three time_window refs."""
        results = [False, True, False]
        irrigation = {"condition_refs": [0, 1, 2], "condition_op": "OR", "type": "actuator"}
        notification = {
            "condition_refs": [3],
            "type": "notification",
        }
        # index 3 missing → notification fail-closed; irrigation passes via C1
        gated = LogicEngine._filter_actions_by_condition_gate(
            [irrigation, notification], results, False, "AND"
        )
        assert gated == [irrigation]

        results_with_alert = [False, False, False, True]
        gated2 = LogicEngine._filter_actions_by_condition_gate(
            [irrigation, notification], results_with_alert, False, "AND"
        )
        assert gated2 == [notification]

    def test_condition_op_defaults_to_rule_operator(self):
        results = [True, False]
        action = {"condition_refs": [0, 1]}  # no condition_op
        assert (
            LogicEngine._action_passes_condition_gate(action, results, False, "OR")
            is True
        )
        assert (
            LogicEngine._action_passes_condition_gate(action, results, False, "AND")
            is False
        )

    def test_invalid_index_fails_closed(self):
        results = [True]
        assert (
            LogicEngine._action_passes_condition_gate(
                {"condition_refs": [5]}, results, True, "AND"
            )
            is False
        )

    def test_mixed_routed_and_flat(self):
        results = [True, False]
        flat = {"command": "ON"}  # global gate
        routed = {"condition_refs": [1], "command": "OFF"}
        gated = LogicEngine._filter_actions_by_condition_gate(
            [flat, routed], results, True, "OR"
        )
        assert gated == [flat]  # global true; C1 false

    def test_rule_has_routed_actions(self):
        assert LogicEngine._rule_has_routed_actions([{"command": "ON"}]) is False
        assert (
            LogicEngine._rule_has_routed_actions(
                [{"command": "ON"}, {"condition_refs": [0]}]
            )
            is True
        )

    def test_safety_critical_routed_off_classification(self):
        assert (
            LogicEngine._is_safety_critical_routed_off(
                {
                    "type": "actuator_command",
                    "command": "OFF",
                    "condition_refs": [1],
                    "is_safety_critical": True,
                }
            )
            is True
        )
        # ON must not bypass
        assert (
            LogicEngine._is_safety_critical_routed_off(
                {
                    "type": "actuator_command",
                    "command": "ON",
                    "condition_refs": [0],
                    "is_safety_critical": True,
                }
            )
            is False
        )
        # missing safety flag
        assert (
            LogicEngine._is_safety_critical_routed_off(
                {
                    "type": "actuator_command",
                    "command": "OFF",
                    "condition_refs": [1],
                }
            )
            is False
        )
        # not routed
        assert (
            LogicEngine._is_safety_critical_routed_off(
                {
                    "type": "actuator_command",
                    "command": "OFF",
                    "is_safety_critical": True,
                }
            )
            is False
        )

    def test_combine_condition_results(self):
        assert LogicEngine._combine_condition_results([True, False], "AND") is False
        assert LogicEngine._combine_condition_results([True, False], "OR") is True
        assert LogicEngine._combine_condition_results([], "AND") is False
