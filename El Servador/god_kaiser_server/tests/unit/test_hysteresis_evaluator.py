"""
Unit-Tests für HysteresisConditionEvaluator

Teste:
- Mode A (Kühlung): activate_above / deactivate_below
- Mode B (Heizung): activate_below / deactivate_above
- State-Isolation zwischen Rules
- State bleibt zwischen Schwellen
- Edge Cases und Fehlerbehandlung

Phase: Logic Engine Phase 2
Author: AutomationOne Development Team
"""

import pytest

from src.services.logic.conditions.hysteresis_evaluator import (
    HysteresisConditionEvaluator,
    HysteresisState,
)


class TestHysteresisEvaluator:
    """Tests für Hysterese-Logik."""

    @pytest.fixture
    def evaluator(self):
        """Frischer Evaluator für jeden Test."""
        return HysteresisConditionEvaluator()

    @pytest.fixture
    def cooling_condition(self):
        """Kühlung: AN bei >28°C, AUS bei <24°C"""
        return {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }

    @pytest.fixture
    def heating_condition(self):
        """Heizung: AN bei <18°C, AUS bei >22°C"""
        return {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 4,
            "activate_below": 18.0,
            "deactivate_above": 22.0,
        }

    def make_context(self, rule_id: str, value: float, gpio: int = 4) -> dict:
        """
        Helper: Erstellt Context mit Sensor-Daten.

        Args:
            rule_id: Regel-UUID
            value: Sensor-Wert
            gpio: GPIO Pin (default: 4)

        Returns:
            Context dictionary
        """
        return {
            "rule_id": rule_id,
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_TEST",
                "gpio": gpio,
                "value": value,
            },
        }

    # === Mode A Tests (Kühlung) ===

    @pytest.mark.asyncio
    async def test_cooling_activation(self, evaluator, cooling_condition):
        """Aktiviert bei Überschreiten von activate_above."""
        context = self.make_context("rule-1", 29.0)

        result = await evaluator.evaluate(cooling_condition, context)

        assert result is True
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state is not None
        assert state.is_active is True
        assert state.last_value == 29.0

    @pytest.mark.asyncio
    async def test_cooling_deactivation(self, evaluator, cooling_condition):
        """Deaktiviert bei Unterschreiten von deactivate_below."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Deaktivieren
        context = self.make_context("rule-1", 23.0)
        result = await evaluator.evaluate(cooling_condition, context)

        assert result is False
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state.is_active is False
        assert state.last_value == 23.0

    @pytest.mark.asyncio
    async def test_cooling_stays_active_between_thresholds(self, evaluator, cooling_condition):
        """Bleibt aktiv zwischen den Schwellen."""
        # Aktivieren bei 29°C
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Zwischen 24 und 28 - sollte aktiv bleiben
        context = self.make_context("rule-1", 26.0)
        result = await evaluator.evaluate(cooling_condition, context)

        assert result is True  # Immer noch aktiv!
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state.is_active is True

    @pytest.mark.asyncio
    async def test_cooling_stays_inactive_between_thresholds(self, evaluator, cooling_condition):
        """Bleibt inaktiv zwischen den Schwellen."""
        # Start: inaktiv, Wert zwischen Schwellen
        context = self.make_context("rule-1", 26.0)
        result = await evaluator.evaluate(cooling_condition, context)

        assert result is False  # Bleibt inaktiv
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state.is_active is False

    @pytest.mark.asyncio
    async def test_cooling_multiple_activations(self, evaluator, cooling_condition):
        """Mehrfache Aktivierung/Deaktivierung funktioniert."""
        rule_id = "rule-1"

        # Zyklus 1: Aktivieren
        context = self.make_context(rule_id, 30.0)
        assert await evaluator.evaluate(cooling_condition, context) is True

        # Zyklus 1: Deaktivieren
        context = self.make_context(rule_id, 22.0)
        assert await evaluator.evaluate(cooling_condition, context) is False

        # Zyklus 2: Aktivieren
        context = self.make_context(rule_id, 29.0)
        assert await evaluator.evaluate(cooling_condition, context) is True

        # Zyklus 2: Deaktivieren
        context = self.make_context(rule_id, 23.0)
        assert await evaluator.evaluate(cooling_condition, context) is False

    # === Mode B Tests (Heizung) ===

    @pytest.mark.asyncio
    async def test_heating_activation(self, evaluator, heating_condition):
        """Aktiviert bei Unterschreiten von activate_below."""
        context = self.make_context("rule-2", 17.0)

        result = await evaluator.evaluate(heating_condition, context)

        assert result is True
        state = evaluator.get_state_for_rule("rule-2", 0)
        assert state.is_active is True

    @pytest.mark.asyncio
    async def test_heating_deactivation(self, evaluator, heating_condition):
        """Deaktiviert bei Überschreiten von deactivate_above."""
        # Aktivieren
        context = self.make_context("rule-2", 17.0)
        await evaluator.evaluate(heating_condition, context)

        # Deaktivieren
        context = self.make_context("rule-2", 23.0)
        result = await evaluator.evaluate(heating_condition, context)

        assert result is False
        state = evaluator.get_state_for_rule("rule-2", 0)
        assert state.is_active is False

    @pytest.mark.asyncio
    async def test_heating_stays_active_between_thresholds(self, evaluator, heating_condition):
        """Bleibt aktiv zwischen den Schwellen (Heizung)."""
        # Aktivieren bei 17°C
        context = self.make_context("rule-2", 17.0)
        await evaluator.evaluate(heating_condition, context)

        # Zwischen 18 und 22 - sollte aktiv bleiben
        context = self.make_context("rule-2", 20.0)
        result = await evaluator.evaluate(heating_condition, context)

        assert result is True
        state = evaluator.get_state_for_rule("rule-2", 0)
        assert state.is_active is True

    @pytest.mark.asyncio
    async def test_heating_stays_inactive_between_thresholds(self, evaluator, heating_condition):
        """Bleibt inaktiv zwischen den Schwellen (Heizung)."""
        # Start: inaktiv, Wert zwischen Schwellen
        context = self.make_context("rule-2", 20.0)
        result = await evaluator.evaluate(heating_condition, context)

        assert result is False
        state = evaluator.get_state_for_rule("rule-2", 0)
        assert state.is_active is False

    # === State-Isolation Tests ===

    @pytest.mark.asyncio
    async def test_state_isolation_between_rules(self, evaluator, cooling_condition):
        """Verschiedene Rules haben isolierte States."""
        # Rule 1 aktivieren
        context1 = self.make_context("rule-1", 29.0)
        result1 = await evaluator.evaluate(cooling_condition, context1)
        assert result1 is True

        # Rule 2 sollte NICHT aktiviert sein (eigener State!)
        context2 = self.make_context("rule-2", 26.0)
        result2 = await evaluator.evaluate(cooling_condition, context2)
        assert result2 is False  # Rule 2 hat eigenen State

        # Prüfe States direkt
        state1 = evaluator.get_state_for_rule("rule-1", 0)
        state2 = evaluator.get_state_for_rule("rule-2", 0)
        assert state1.is_active is True
        assert state2.is_active is False

    @pytest.mark.asyncio
    async def test_state_isolation_different_condition_indices(self, evaluator, cooling_condition):
        """Verschiedene Condition-Indizes in derselben Regel haben isolierte States."""
        # Condition 0 aktivieren
        context0 = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 4, "value": 29.0},
        }
        await evaluator.evaluate(cooling_condition, context0)

        # Condition 1 sollte eigenen State haben
        context1 = {
            "rule_id": "rule-1",
            "condition_index": 1,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 4, "value": 26.0},
        }
        result1 = await evaluator.evaluate(cooling_condition, context1)

        assert result1 is False  # Condition 1 hat eigenen State

    # === Edge Cases ===

    @pytest.mark.asyncio
    async def test_wrong_sensor_keeps_state(self, evaluator, cooling_condition):
        """Falscher Sensor ändert State nicht, gibt aktuellen zurück."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Anderer Sensor (andere GPIO)
        context_other = self.make_context("rule-1", 10.0, gpio=999)
        result = await evaluator.evaluate(cooling_condition, context_other)

        # Sollte aktuellen State zurückgeben (True), nicht ändern
        assert result is True
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state.is_active is True
        assert state.last_value == 29.0  # Alter Wert bleibt

    @pytest.mark.asyncio
    async def test_wrong_esp_id_keeps_state(self, evaluator, cooling_condition):
        """Falsche ESP-ID ändert State nicht."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Andere ESP-ID
        context_other = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_OTHER", "gpio": 4, "value": 10.0},
        }
        result = await evaluator.evaluate(cooling_condition, context_other)

        assert result is True  # State bleibt True
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state.last_value == 29.0  # Alter Wert bleibt

    @pytest.mark.asyncio
    async def test_offline_source_override_returns_false_for_non_matching_sensor(
        self, evaluator, cooling_condition
    ):
        """Offline-Quelle überstimmt Hold-State (kein True bei fehlender Sensorquelle)."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Non-matching sensor_data (wie timer-trigger ohne passenden Sensor)
        # + offline ref für die Condition-Quelle
        context_offline = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_OTHER", "gpio": 4, "value": 10.0},
            "_offline_sensor_refs": [
                {"esp_id": "ESP_TEST", "gpio": 4, "sensor_type": None, "reason": "esp_offline"}
            ],
        }
        result = await evaluator.evaluate(cooling_condition, context_offline)

        # Vor Fix: True (Hold-State), jetzt korrekt False bei offline Source
        assert result is False

        # State selbst wird dabei nicht mutiert (bleibt aktiv, bis LogicEngine ihn gezielt cleared)
        state = evaluator.get_state_for_rule("rule-1", 0)
        assert state is not None
        assert state.is_active is True

    @pytest.mark.asyncio
    async def test_missing_value_keeps_state(self, evaluator, cooling_condition):
        """Fehlender Wert ändert State nicht."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Sensor-Daten ohne value
        context_no_value = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 4},  # Kein value!
        }
        result = await evaluator.evaluate(cooling_condition, context_no_value)

        assert result is True  # State bleibt True

    @pytest.mark.asyncio
    async def test_invalid_value_keeps_state(self, evaluator, cooling_condition):
        """Invalider Wert ändert State nicht."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)

        # Invalid value
        context_invalid = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 4, "value": "not_a_number"},
        }
        result = await evaluator.evaluate(cooling_condition, context_invalid)

        assert result is True  # State bleibt True

    @pytest.mark.asyncio
    async def test_supports_method(self, evaluator):
        """supports() gibt True nur für 'hysteresis'."""
        assert evaluator.supports("hysteresis") is True
        assert evaluator.supports("sensor") is False
        assert evaluator.supports("time") is False
        assert evaluator.supports("sensor_threshold") is False

    @pytest.mark.asyncio
    async def test_invalid_config_both_modes(self, evaluator):
        """Ungültige Config (beide Modi gleichzeitig) gibt False zurück."""
        invalid_condition = {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 4,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
            "activate_below": 18.0,  # Beide Modi!
            "deactivate_above": 22.0,
        }
        context = self.make_context("rule-1", 25.0)

        result = await evaluator.evaluate(invalid_condition, context)

        # Kühlung-Modus hat Vorrang (wird zuerst geprüft)
        assert result is False  # Wert ist zwischen Schwellen

    @pytest.mark.asyncio
    async def test_invalid_config_no_thresholds(self, evaluator):
        """Ungültige Config (keine Schwellwerte) gibt False zurück."""
        invalid_condition = {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 4,
            # Keine activate/deactivate Schwellwerte!
        }
        context = self.make_context("rule-1", 25.0)

        result = await evaluator.evaluate(invalid_condition, context)

        assert result is False

    @pytest.mark.asyncio
    async def test_reset_state(self, evaluator, cooling_condition):
        """reset_state() löscht den State."""
        # Aktivieren
        context = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context)
        assert evaluator.get_state_for_rule("rule-1", 0).is_active is True

        # Reset
        evaluator.reset_state("rule-1", 0)

        # Nach Reset: State sollte gelöscht sein
        assert evaluator.get_state_for_rule("rule-1", 0) is None

        # Neue Evaluation erstellt neuen State (inaktiv)
        context = self.make_context("rule-1", 26.0)
        result = await evaluator.evaluate(cooling_condition, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_nonexistent_state(self, evaluator):
        """reset_state() für nicht-existenten State funktioniert ohne Fehler."""
        # Sollte nicht crashen
        evaluator.reset_state("nonexistent-rule", 0)

    @pytest.mark.asyncio
    async def test_get_all_states(self, evaluator, cooling_condition):
        """get_all_states() gibt alle States zurück."""
        # Erstelle mehrere States
        context1 = self.make_context("rule-1", 29.0)
        await evaluator.evaluate(cooling_condition, context1)

        context2 = self.make_context("rule-2", 30.0)
        await evaluator.evaluate(cooling_condition, context2)

        # Hole alle States
        states = evaluator.get_all_states()

        assert len(states) == 2
        assert "rule-1:0" in states
        assert "rule-2:0" in states
        assert states["rule-1:0"].is_active is True
        assert states["rule-2:0"].is_active is True

    @pytest.mark.asyncio
    async def test_sensor_type_filter(self, evaluator):
        """Optional sensor_type Filter funktioniert."""
        condition_with_type = {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 4,
            "sensor_type": "DS18B20",  # Nur DS18B20
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }

        # Richtiger Sensor-Type
        context_correct = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_TEST",
                "gpio": 4,
                "sensor_type": "DS18B20",
                "value": 29.0,
            },
        }
        result = await evaluator.evaluate(condition_with_type, context_correct)
        assert result is True

        # Falscher Sensor-Type
        context_wrong = {
            "rule_id": "rule-1",
            "condition_index": 0,
            "sensor_data": {
                "esp_id": "ESP_TEST",
                "gpio": 4,
                "sensor_type": "SHT31",  # Falsch!
                "value": 30.0,
            },
        }
        result = await evaluator.evaluate(condition_with_type, context_wrong)
        assert result is True  # State bleibt True (nicht geändert)

    @pytest.mark.asyncio
    async def test_exact_threshold_values_cooling(self, evaluator, cooling_condition):
        """Exakte Schwellwerte (Grenzfälle) für Kühlung."""
        rule_id = "rule-1"

        # Wert genau auf activate_above (28.0) - sollte NICHT aktivieren (>)
        context = self.make_context(rule_id, 28.0)
        result = await evaluator.evaluate(cooling_condition, context)
        assert result is False

        # Wert genau auf deactivate_below (24.0) - sollte NICHT deaktivieren (<)
        # Zuerst aktivieren
        context = self.make_context(rule_id, 29.0)
        await evaluator.evaluate(cooling_condition, context)
        # Dann auf Grenze
        context = self.make_context(rule_id, 24.0)
        result = await evaluator.evaluate(cooling_condition, context)
        assert result is True  # Bleibt aktiv

    @pytest.mark.asyncio
    async def test_exact_threshold_values_heating(self, evaluator, heating_condition):
        """Exakte Schwellwerte (Grenzfälle) für Heizung."""
        rule_id = "rule-2"

        # Wert genau auf activate_below (18.0) - sollte NICHT aktivieren (<)
        context = self.make_context(rule_id, 18.0)
        result = await evaluator.evaluate(heating_condition, context)
        assert result is False

        # Wert genau auf deactivate_above (22.0) - sollte NICHT deaktivieren (>)
        # Zuerst aktivieren
        context = self.make_context(rule_id, 17.0)
        await evaluator.evaluate(heating_condition, context)
        # Dann auf Grenze
        context = self.make_context(rule_id, 22.0)
        result = await evaluator.evaluate(heating_condition, context)
        assert result is True  # Bleibt aktiv

    # === GPIO int() Coercion Tests (L2 Fix N5) ===

    @pytest.mark.asyncio
    async def test_gpio_float_vs_int_matches(self, evaluator, cooling_condition):
        """GPIO as float(4.0) in data matches int(4) in condition."""
        context = {
            "rule_id": "rule-gpio",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 4.0, "value": 30.0},
        }
        result = await evaluator.evaluate(cooling_condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_gpio_string_vs_int_matches(self, evaluator, cooling_condition):
        """GPIO as string '4' in data matches int(4) in condition."""
        context = {
            "rule_id": "rule-gpio",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": "4", "value": 30.0},
        }
        result = await evaluator.evaluate(cooling_condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_gpio_zero_matches(self, evaluator):
        """GPIO 0 (I2C convention for SHT31) matches correctly."""
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 0,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }
        context = {
            "rule_id": "rule-gpio0",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 0, "value": 30.0},
        }
        result = await evaluator.evaluate(cond, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_gpio_float_in_condition_matches(self, evaluator):
        """GPIO as float(5.0) in condition matches int(5) in data."""
        cond = {
            "type": "hysteresis",
            "esp_id": "ESP_TEST",
            "gpio": 5.0,
            "activate_above": 28.0,
            "deactivate_below": 24.0,
        }
        context = {
            "rule_id": "rule-gpio-float",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_TEST", "gpio": 5, "value": 30.0},
        }
        result = await evaluator.evaluate(cond, context)
        assert result is True

    # === _hysteresis_just_deactivated Flag Tests (L2) ===

    @pytest.mark.asyncio
    async def test_deactivation_flag_set_on_cooling(self, evaluator, cooling_condition):
        """_hysteresis_just_deactivated flag set when cooling deactivates."""
        # Activate
        ctx1 = self.make_context("rule-flag", 30.0)
        await evaluator.evaluate(cooling_condition, ctx1)
        assert "_hysteresis_just_deactivated" not in ctx1

        # Deactivate
        ctx2 = self.make_context("rule-flag", 23.0)
        await evaluator.evaluate(cooling_condition, ctx2)
        assert ctx2.get("_hysteresis_just_deactivated") is True

    @pytest.mark.asyncio
    async def test_deactivation_flag_set_on_heating(self, evaluator, heating_condition):
        """_hysteresis_just_deactivated flag set when heating deactivates."""
        # Activate
        ctx1 = self.make_context("rule-flag-h", 16.0)
        await evaluator.evaluate(heating_condition, ctx1)
        assert "_hysteresis_just_deactivated" not in ctx1

        # Deactivate
        ctx2 = self.make_context("rule-flag-h", 23.0)
        await evaluator.evaluate(heating_condition, ctx2)
        assert ctx2.get("_hysteresis_just_deactivated") is True

    @pytest.mark.asyncio
    async def test_deactivation_flag_not_set_on_activation(self, evaluator, cooling_condition):
        """Flag is NOT set when activating."""
        ctx = self.make_context("rule-flag-act", 30.0)
        await evaluator.evaluate(cooling_condition, ctx)
        assert "_hysteresis_just_deactivated" not in ctx

    @pytest.mark.asyncio
    async def test_deactivation_flag_not_set_on_non_matching_sensor(
        self, evaluator, cooling_condition
    ):
        """Flag is NOT set for non-matching sensor."""
        # Activate first
        ctx1 = self.make_context("rule-flag-nm", 30.0)
        await evaluator.evaluate(cooling_condition, ctx1)

        # Non-matching sensor
        ctx2 = {
            "rule_id": "rule-flag-nm",
            "condition_index": 0,
            "sensor_data": {"esp_id": "ESP_OTHER", "gpio": 4, "value": 10.0},
        }
        await evaluator.evaluate(cooling_condition, ctx2)
        assert "_hysteresis_just_deactivated" not in ctx2
