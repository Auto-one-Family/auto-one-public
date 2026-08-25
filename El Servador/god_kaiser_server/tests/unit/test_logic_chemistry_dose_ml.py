"""
Unit Tests: AUT-1112 — LogicEngine._compute_chemistry_dose_ml()

Tests:
- No-op when rule.rule_metadata has no dose_config (default for existing rules)
- dose_ml computed for a top-level actuator action (1 component)
- dose_ml computed for sequence-step actions (2 components, split across steps)
- Fail-open: exception in calculate_dose_ml skips only that action, no crash,
  other actions in the same rule are unaffected (Fehler-Injektions-Test)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.logic_engine import LogicEngine


@pytest.fixture
def engine():
    """Minimal LogicEngine instance for unit testing _compute_chemistry_dose_ml."""
    logic_repo = MagicMock()
    actuator_service = MagicMock()
    ws_manager = AsyncMock()
    return LogicEngine(
        logic_repo=logic_repo,
        actuator_service=actuator_service,
        websocket_manager=ws_manager,
        condition_evaluators=[],
        action_executors=[],
    )


def _make_rule(rule_metadata: dict | None) -> MagicMock:
    rule = MagicMock()
    rule.rule_name = "Test Rule"
    rule.rule_metadata = rule_metadata
    return rule


class TestNoOpWithoutDoseConfig:
    @pytest.mark.asyncio
    async def test_no_op_without_dose_config(self, engine):
        rule = _make_rule({})
        action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5, "command": "ON"}
        actions = [action]

        result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 5.0})

        assert result is actions
        assert "dose_ml" not in action


class TestTopLevelActionSingleComponent:
    @pytest.mark.asyncio
    async def test_top_level_action_single_component(self, engine):
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 7.0,
                    "volume_l": 10.0,
                    "components": [{"concentration": 5.0, "ratio_share": 1.0}],
                }
            }
        )
        action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5, "command": "ON"}
        actions = [action]

        result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 5.0})

        assert len(result) == 1
        # delta=2.0, volume=10, ratio=1.0, concentration=5.0 -> 4.0 ml
        assert result[0]["dose_ml"] == pytest.approx(4.0)
        # Original action dict must not be mutated in place
        assert "dose_ml" not in action


class TestSequenceStepsTwoComponents:
    @pytest.mark.asyncio
    async def test_sequence_steps_two_components(self, engine):
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 2.0,
                    "volume_l": 20.0,
                    "components": [
                        {"concentration": 2.0, "ratio_share": 0.5},
                        {"concentration": 2.0, "ratio_share": 0.5},
                    ],
                }
            }
        )
        sequence_action = {
            "type": "sequence",
            "steps": [
                {"action": {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}},
                {"delay_seconds": 5},
            ],
        }
        actions = [sequence_action]

        result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 1.0})

        assert len(result) == 1
        # delta=1.0, volume=20, ratio=0.5, concentration=2.0 -> per-component 5.0 ml
        assert result[0]["steps"][0]["action"]["dose_ml"] == pytest.approx(5.0)
        assert result[0]["steps"][1] == {"delay_seconds": 5}


class TestFailOpenSkipsOnlyFailingAction:
    @pytest.mark.asyncio
    async def test_fail_open_skips_only_failing_action(self, engine):
        # volume_l=0 makes calculate_dose_ml raise ValueError for every action
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 7.0,
                    "volume_l": 0,
                    "components": [{"concentration": 5.0, "ratio_share": 1.0}],
                }
            }
        )
        dosing_action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}
        other_action = {"type": "notification", "channel": "email"}
        actions = [dosing_action, other_action]

        result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 5.0})

        assert len(result) == 2
        # Dosing action falls back unchanged (no dose_ml) — engine did not crash
        assert "dose_ml" not in result[0]
        assert result[0]["esp_id"] == "ESP_A"
        # Unrelated action passes through untouched
        assert result[1] == other_action


class TestPumpConcentrationSsotAut1355:
    """AUT-1355: Divisor from pump SSOT; runtime fallback to dose_config."""

    @pytest.mark.asyncio
    async def test_pump_concentration_overrides_dose_config(self, engine):
        """Same formula — only divisor source changes (pump wins when set)."""
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 7.0,
                    "volume_l": 10.0,
                    "components": [{"concentration": 5.0, "ratio_share": 1.0}],
                }
            }
        )
        action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}
        session = MagicMock()

        esp = MagicMock()
        esp.id = "esp-uuid"
        act = MagicMock()
        act.concentration = 10.0  # pump SSOT — doubles divisor vs dose_config 5.0

        with (pytest.MonkeyPatch.context() as mp,):
            # Patch repositories used inside _compute_chemistry_dose_ml
            from src.services import logic_engine as le_mod

            esp_repo = MagicMock()
            esp_repo.get_by_device_id = AsyncMock(return_value=esp)
            act_repo = MagicMock()
            act_repo.get_by_esp_and_gpio = AsyncMock(return_value=act)
            mp.setattr(le_mod, "ESPRepository", lambda _s: esp_repo)
            mp.setattr(le_mod, "ActuatorRepository", lambda _s: act_repo)

            result = await engine._compute_chemistry_dose_ml(
                rule, [action], {"value": 5.0}, session=session
            )

        # delta=2, V=10, ratio=1, conc=10 → 2.0 ml (not 4.0 from dose_config 5.0)
        assert result[0]["dose_ml"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_fallback_when_pump_concentration_null(self, engine):
        """Pump NULL → dose_config.components[i].concentration (no backfill)."""
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 7.0,
                    "volume_l": 10.0,
                    "components": [{"concentration": 5.0, "ratio_share": 1.0}],
                }
            }
        )
        action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}
        session = MagicMock()

        esp = MagicMock()
        esp.id = "esp-uuid"
        act = MagicMock()
        act.concentration = None

        from src.services import logic_engine as le_mod

        esp_repo = MagicMock()
        esp_repo.get_by_device_id = AsyncMock(return_value=esp)
        act_repo = MagicMock()
        act_repo.get_by_esp_and_gpio = AsyncMock(return_value=act)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(le_mod, "ESPRepository", lambda _s: esp_repo)
            mp.setattr(le_mod, "ActuatorRepository", lambda _s: act_repo)
            result = await engine._compute_chemistry_dose_ml(
                rule, [action], {"value": 5.0}, session=session
            )

        # Identical to pre-AUT-1355 result with dose_config concentration=5.0
        assert result[0]["dose_ml"] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_no_session_keeps_dose_config_formula_regression(self, engine):
        """Without session (unit path): same dose as before AUT-1355."""
        rule = _make_rule(
            {
                "dose_config": {
                    "target_value": 7.0,
                    "volume_l": 10.0,
                    "components": [{"concentration": 5.0, "ratio_share": 1.0}],
                }
            }
        )
        action = {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}
        result = await engine._compute_chemistry_dose_ml(rule, [action], {"value": 5.0})
        assert result[0]["dose_ml"] == pytest.approx(4.0)
