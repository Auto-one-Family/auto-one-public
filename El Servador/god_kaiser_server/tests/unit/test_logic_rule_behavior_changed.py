"""
Unit Tests: AUT-1135 (A4) — LogicService._rule_behavior_changed()

Single source of truth for "did this update change what the rule DOES"
(conditions, actions, or the AND/OR combinator) vs. a save that only touched
timer/limit parameters (cooldown_seconds, settle_seconds, ...). Drives the
force-flag that decides whether a rule_update trigger may bypass the rule's
cooldown/settle window (see logic_service.update_rule() / logic_engine.py
_evaluate_rule()). Pure function — no DB/MQTT/HTTP, no mocking needed.
"""

from src.services.logic_service import LogicService

_CONDITIONS = [{"type": "sensor", "esp_id": "ESP_001", "gpio": 4, "operator": ">", "value": 7.5}]
_ACTIONS = [{"type": "actuator_command", "esp_id": "ESP_001", "gpio": 5, "command": "ON"}]


class TestRuleBehaviorChanged:
    def test_no_change_returns_false(self):
        """Pure timer-only save (cooldown_seconds/settle_seconds/...) never touches
        conditions/actions/logic_operator -> must not force-bypass cooldown/settle."""
        assert (
            LogicService._rule_behavior_changed(
                old_conditions=_CONDITIONS,
                old_actions=_ACTIONS,
                old_logic_operator="AND",
                new_conditions=_CONDITIONS,
                new_actions=_ACTIONS,
                new_logic_operator="AND",
            )
            is False
        )

    def test_condition_change_returns_true(self):
        new_conditions = [{**_CONDITIONS[0], "value": 8.0}]
        assert (
            LogicService._rule_behavior_changed(
                old_conditions=_CONDITIONS,
                old_actions=_ACTIONS,
                old_logic_operator="AND",
                new_conditions=new_conditions,
                new_actions=_ACTIONS,
                new_logic_operator="AND",
            )
            is True
        )

    def test_action_change_returns_true(self):
        new_actions = [{**_ACTIONS[0], "command": "OFF"}]
        assert (
            LogicService._rule_behavior_changed(
                old_conditions=_CONDITIONS,
                old_actions=_ACTIONS,
                old_logic_operator="AND",
                new_conditions=_CONDITIONS,
                new_actions=new_actions,
                new_logic_operator="AND",
            )
            is True
        )

    def test_logic_operator_change_returns_true(self):
        """Regression: AND->OR changes trigger semantics just as much as a
        condition/action edit — must force-bypass like any other behavior change.
        (Found in code review: was missing from the initial AUT-1135 diff.)"""
        assert (
            LogicService._rule_behavior_changed(
                old_conditions=_CONDITIONS,
                old_actions=_ACTIONS,
                old_logic_operator="AND",
                new_conditions=_CONDITIONS,
                new_actions=_ACTIONS,
                new_logic_operator="OR",
            )
            is True
        )

    def test_old_conditions_as_single_dict_normalizes_like_list(self):
        """CrossESPLogic.conditions property wraps a non-list trigger_conditions
        value in a single-element list — old_conditions may arrive either shape
        depending on legacy storage format; must compare equal when unchanged."""
        single_dict = _CONDITIONS[0]
        assert (
            LogicService._rule_behavior_changed(
                old_conditions=single_dict,
                old_actions=_ACTIONS,
                old_logic_operator="AND",
                new_conditions=[single_dict],
                new_actions=_ACTIONS,
                new_logic_operator="AND",
            )
            is False
        )
