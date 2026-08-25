"""
Unit Tests: AUT-1173 (TAX-5) — LogicService.derive_rule_group() (Variante C)

Single source of truth for a rule's display group (Gruppenkarten). An explicit
rule_group override always wins; otherwise the group is derived in fixed axis
order: Sicherheit (actuator-OFF, independent of condition shape) -> Messgröße
(sensor_type category) -> Zeitplan (time-only) -> Sonstiges. Pure function —
no DB/MQTT/HTTP, no mocking needed. Mirrors test_logic_rule_behavior_changed.py's
style (AUT-1135).
"""

from src.services.logic_service import LogicService

_HYSTERESIS_TEMPERATURE = {
    "type": "hysteresis",
    "esp_id": "ESP_001",
    "gpio": 4,
    "sensor_type": "temperature",
    "activate_above": 28.0,
    "deactivate_below": 24.0,
}
_TIME_WINDOW = {"type": "time_window", "start_hour": 8, "end_hour": 18}
_SENSOR_THRESHOLD_PH = {
    "type": "sensor",
    "esp_id": "ESP_001",
    "gpio": 34,
    "operator": ">",
    "value": 7.5,
    "sensor_type": "ph",
}
_ACTUATOR_ON = {"type": "actuator", "esp_id": "ESP_002", "gpio": 5, "command": "ON"}
_ACTUATOR_OFF = {"type": "actuator", "esp_id": "ESP_002", "gpio": 5, "command": "OFF"}
_NOTIFICATION = {
    "type": "notification",
    "channel": "email",
    "target": "ops@example.com",
    "message_template": "Alert!",
}
_DELAY_ACTION = {"type": "delay", "seconds": 5}
_SENSOR_DIFF = {
    "type": "sensor_diff",
    "sensor_a_id": "a" * 36,
    "sensor_b_id": "b" * 36,
    "operator": ">",
    "value": 1.0,
}


class TestDeriveRuleGroup:
    def test_hysteresis_plus_actuator_on_returns_measurement_category(self):
        """Messgröße-Achse: eine Hysterese-Regel ohne Abschalt-Aktion landet in
        ihrer Messgrößen-Kategorie, nicht mehr in der alten Sammel-Gruppe 'klima'."""
        assert (
            LogicService.derive_rule_group(None, [_HYSTERESIS_TEMPERATURE], [_ACTUATOR_ON])
            == "temperatur"
        )

    def test_hysteresis_plus_actuator_off_returns_sicherheit(self):
        """AUT-1163 Root Cause (KRITISCH): eine hysterese-förmige Notfall-Abschaltung
        darf NICHT von der Messgrößen-Achse verschluckt werden — Sicherheit prüft
        zuerst, unabhängig von der Bedingungsform. Das ist exakt der Fehler, den
        der alte Zweig 1 (Hysterese+Aktor->klima) vor dem Sicherheits-Zweig hatte."""
        assert (
            LogicService.derive_rule_group(None, [_HYSTERESIS_TEMPERATURE], [_ACTUATOR_OFF])
            == "sicherheit"
        )

    def test_time_window_only_returns_zeitplan(self):
        assert LogicService.derive_rule_group(None, [_TIME_WINDOW], [_ACTUATOR_ON]) == "zeitplan"

    def test_threshold_plus_notification_returns_measurement_category(self):
        """AUT-1163 (L4, Option a): eine Schwellwert+Benachrichtigung-Regel bekommt
        keine eigene 'alarm'-Gruppe mehr — sie landet in ihrer Messgrößen-Kategorie,
        die Benachrichtigung wird ein Kennzeichen innerhalb der Gruppe (AUT-1176)."""
        assert LogicService.derive_rule_group(None, [_SENSOR_THRESHOLD_PH], [_NOTIFICATION]) == "ph"

    def test_threshold_plus_actuator_off_returns_sicherheit(self):
        assert (
            LogicService.derive_rule_group(None, [_SENSOR_THRESHOLD_PH], [_ACTUATOR_OFF])
            == "sicherheit"
        )

    def test_dose_config_metadata_no_longer_yields_dosierung(self):
        """AUT-1163 (L4, Option a): 'dosierung' entfällt als eigene Gruppe — auch
        eine Regel mit rule_metadata.dose_config landet jetzt in ihrer
        Messgrößen-Kategorie, rule_metadata wird von derive_rule_group() nicht
        mehr inspiziert."""
        assert (
            LogicService.derive_rule_group(
                None,
                [_HYSTERESIS_TEMPERATURE],
                [_ACTUATOR_ON],
                rule_metadata={"dose_config": {"target_value": 6.0}},
            )
            == "temperatur"
        )

    def test_everything_else_returns_sonstiges(self):
        assert LogicService.derive_rule_group(None, [_SENSOR_DIFF], [_DELAY_ACTION]) == (
            "sonstiges"
        )

    def test_explicit_override_wins_over_derivation(self):
        """Given/When/Then (Nutzer-Override): eine Regel, deren Mechanik zu
        'temperatur' abgeleitet würde, aber ein explizites rule_group hat, muss
        den Override liefern, unverändert — die Ableitung darf gar nicht laufen."""
        assert (
            LogicService.derive_rule_group("sonstiges", [_HYSTERESIS_TEMPERATURE], [_ACTUATOR_ON])
            == "sonstiges"
        )

    def test_null_override_falls_back_to_derivation(self):
        """Given/When/Then (Ableitung): rule_group=NULL -> effective value is
        derived, nothing is written to the DB by this pure function."""
        assert (
            LogicService.derive_rule_group(None, [_HYSTERESIS_TEMPERATURE], [_ACTUATOR_ON])
            == "temperatur"
        )
