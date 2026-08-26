"""
Unit Tests: LE-01 — _extract_offline_rule() extensions

Covers the new sensor_threshold → hysteresis conversion, OR-compound rejection,
time_filter extraction, and P4-GUARD fixes added as part of LE-01.

Test matrix (8 tests):
1. sensor_threshold >  → cooling mode (activate_above / deactivate_below)
2. sensor_threshold <  → heating mode (activate_below / deactivate_above)
3. Compound AND (hysteresis + time_window) → offline_rule includes time_filter
4. OR-compound with multiple conditions → return None + logger.info
5. soil_moisture sensor_threshold → exported RAW without calibration_data (AUT-1565)
6. "between" operator → return None + logger.info
7. Cross-ESP sensor condition (sensor on ESP_B, query for ESP_A) → return None
8. Midnight time window 22:00–06:00 UTC → time_filter preserved correctly
"""

import logging

import pytest
from unittest.mock import MagicMock

from src.services.config_builder import ConfigPayloadBuilder

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

ESP_ID_A = "ESP_AABB11CC"
ESP_ID_B = "ESP_DDEE22FF"


# ---------------------------------------------------------------------------
# Helper factories (mirror existing test_config_builder_offline_rules.py style)
# ---------------------------------------------------------------------------


def _make_rule(
    rule_name: str,
    trigger_conditions: object,
    actions: list,
) -> MagicMock:
    rule = MagicMock()
    rule.rule_name = rule_name
    rule.trigger_conditions = trigger_conditions
    rule.actions = actions
    rule.priority = 100
    return rule


def _hysteresis_cooling(esp_id: str, gpio: int = 4, sensor_type: str = "sht31_temp") -> dict:
    return {
        "type": "hysteresis",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "activate_above": 28.0,
        "deactivate_below": 24.0,
    }


def _threshold_condition(
    esp_id: str,
    sensor_type: str,
    operator: str,
    value: float,
    gpio: int = 4,
) -> dict:
    return {
        "type": "sensor_threshold",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "operator": operator,
        "value": value,
    }


def _actuator_action(esp_id: str, gpio: int = 18) -> dict:
    return {
        "type": "actuator_command",
        "esp_id": esp_id,
        "gpio": gpio,
        "command": "ON",
        "value": 1.0,
        "duration_seconds": 0,
    }


def _builder() -> ConfigPayloadBuilder:
    return ConfigPayloadBuilder()


# ---------------------------------------------------------------------------
# Test 1 — sensor_threshold > 28 → cooling-mode offline rule
# ---------------------------------------------------------------------------


class TestThresholdAboveConversion:
    def test_threshold_above_28_converts_to_cooling_mode(self):
        """sensor_threshold > 28°C (sht31_temp) → activate_above=28, deactivate_below=26."""
        rule = _make_rule(
            rule_name="fan_over_temp",
            trigger_conditions=_threshold_condition(ESP_ID_A, "sht31_temp", ">", 28.0),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["activate_above"] == 28.0
        assert r["deactivate_below"] == 26.0  # 28.0 − 2.0 (sht31_temp deadband)
        assert r["activate_below"] == 0.0
        assert r["deactivate_above"] == 0.0
        assert r["sensor_gpio"] == 4
        assert r["actuator_gpio"] == 18


# ---------------------------------------------------------------------------
# Test 2 — sensor_threshold < 10 → heating-mode offline rule
# ---------------------------------------------------------------------------


class TestThresholdBelowConversion:
    def test_threshold_below_10_converts_to_heating_mode(self):
        """sensor_threshold < 10°C (ds18b20) → activate_below=10, deactivate_above=12."""
        rule = _make_rule(
            rule_name="frost_heater",
            trigger_conditions=_threshold_condition(ESP_ID_A, "ds18b20", "<", 10.0),
            actions=[_actuator_action(ESP_ID_A, gpio=22)],
        )

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["activate_below"] == 10.0
        assert r["deactivate_above"] == 12.0  # 10.0 + 2.0 (ds18b20 deadband)
        assert r["activate_above"] == 0.0
        assert r["deactivate_below"] == 0.0
        assert r["sensor_gpio"] == 4
        assert r["actuator_gpio"] == 22


# ---------------------------------------------------------------------------
# Test 3 — Compound AND (hysteresis + time_window) → time_filter dict
# ---------------------------------------------------------------------------


class TestCompoundAndWithTimeWindow:
    def test_compound_and_hysteresis_plus_time_window_adds_time_filter(self):
        """AND-compound of hysteresis + time_window → offline_rule includes time_filter."""
        rule = _make_rule(
            rule_name="daytime_cooling",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 8,
                    "end_hour": 20,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert "time_filter" in r
        tf = r["time_filter"]
        assert tf["enabled"] is True
        assert tf["start_hour"] == 8
        assert tf["start_minute"] == 0
        assert tf["end_hour"] == 20
        assert tf["end_minute"] == 0
        assert tf["timezone"] == "UTC"

    def test_time_window_preserves_local_timezone_without_utc_conversion(self):
        """time_window keeps local wall-clock values and carries timezone to ESP."""
        rule = _make_rule(
            rule_name="berlin_daytime_cooling",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 9,
                    "end_hour": 17,
                    "start_minute": 30,
                    "end_minute": 15,
                    "timezone": "Europe/Berlin",
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        tf = result[0]["time_filter"]
        assert tf["start_hour"] == 9
        assert tf["start_minute"] == 30
        assert tf["end_hour"] == 17
        assert tf["end_minute"] == 15
        assert tf["timezone"] == "Europe/Berlin"

    def test_time_window_fallback_from_start_end_time_strings(self):
        """Legacy start_time/end_time strings are parsed into time_filter minutes."""
        rule = _make_rule(
            rule_name="legacy_time_strings",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_time": "09:45",
                    "end_time": "17:05",
                    "timezone": "UTC",
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        tf = result[0]["time_filter"]
        assert tf["start_hour"] == 9
        assert tf["start_minute"] == 45
        assert tf["end_hour"] == 17
        assert tf["end_minute"] == 5


# ---------------------------------------------------------------------------
# Test 3b — AUT-1531: AND classifier (representable vs. non-representable)
# ---------------------------------------------------------------------------


class TestAndCompoundClassifier:
    """AUT-1531: AND-compounds are exported only when representable in the struct."""

    def test_representable_and_exports_its_own_hysteresis_not_a_list_head(self):
        """One sensor condition + time_window → exactly one struct with that hysteresis."""
        rule = _make_rule(
            rule_name="daytime_cooling_single_sensor",
            trigger_conditions=[
                {
                    "type": "time_window",
                    "start_hour": 8,
                    "end_hour": 20,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                },
                _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 7
        assert result[0]["sensor_value_type"] == "ds18b20"
        assert result[0]["activate_above"] == 28.0
        assert result[0]["deactivate_below"] == 24.0
        assert result[0]["time_filter"]["start_hour"] == 8
        assert result[0]["time_filter"]["end_hour"] == 20

    def test_and_two_hysteresis_same_esp_not_exported(self):
        """Sensor A AND Sensor B on the same ESP → no offline export, skip diagnostic."""
        rule = _make_rule(
            rule_name="and_two_sensors",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4, sensor_type="sht31_temp"),
                _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"
        skip_collector: list = []

        result = _builder()._extract_offline_rule(
            rule, ESP_ID_A, skip_collector=skip_collector
        )

        assert result == []
        assert len(skip_collector) == 1
        assert skip_collector[0]["reason_code"] == ConfigPayloadBuilder.REASON_UNSUPPORTED_CONDITION
        assert "2 sensor conditions" in skip_collector[0]["reason_detail"]
        assert "resolution_hint" in skip_collector[0]

    def test_and_cross_esp_sensors_does_not_export_local_condition(self):
        """Cross-ESP AND → the local hysteresis is not exported as a lone struct."""
        rule = _make_rule(
            rule_name="and_cross_esp_sensors",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_B, gpio=4, sensor_type="sht31_temp"),
                _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    def test_and_hysteresis_plus_threshold_not_exported(self):
        """Mixed sensor condition types still count as two sensor conditions."""
        rule = _make_rule(
            rule_name="and_hysteresis_plus_threshold",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4, sensor_type="sht31_temp"),
                _threshold_condition(ESP_ID_A, "ds18b20", ">", 28.0, gpio=7),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    def test_and_with_nested_compound_not_exported(self):
        """A nested compound hides further sensor conditions → no export."""
        rule = _make_rule(
            rule_name="and_nested_compound",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4, sensor_type="sht31_temp"),
                {
                    "type": "compound",
                    "logic": "OR",
                    "conditions": [
                        _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
                    ],
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    def test_or_branch_that_is_a_nested_and_is_skipped_per_branch(self):
        """OR-DNF is untouched: the simple branch exports, the nested AND branch does not."""
        rule = _make_rule(
            rule_name="or_with_nested_and_branch",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4, sensor_type="sht31_temp"),
                {
                    "type": "compound",
                    "logic": "AND",
                    "conditions": [
                        _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
                        _hysteresis_cooling(ESP_ID_A, gpio=8, sensor_type="sht31_humidity"),
                    ],
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "OR"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 4


# ---------------------------------------------------------------------------
# Test 4 — OR-compound → DNF-flattened (AUT-739)
# ---------------------------------------------------------------------------


class TestOrCompoundRejection:
    def test_or_compound_dnf_flattened(self, caplog):
        """OR-compound with multiple non-calibration conditions → DNF-flattened into N rules (AUT-739)."""
        rule = _make_rule(
            rule_name="or_temp_rule",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                _hysteresis_cooling(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "OR"

        with caplog.at_level(logging.INFO):
            result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        # AUT-739: OR-compounds are now DNF-flattened — one rule per branch
        assert len(result) == 2
        assert all(r["actuator_gpio"] == 18 for r in result)
        assert "OR compound" in caplog.text


# ---------------------------------------------------------------------------
# Test 5 — AUT-1565: soil_moisture exports RAW without calibration_data
# ---------------------------------------------------------------------------


class TestRawComparableOfflineExport:
    """AUT-1565: ph / ec / moisture / soil_moisture export without calibration_data."""

    def test_soil_moisture_threshold_exported_without_calibration_data(self):
        """soil_moisture sensor_threshold → offline struct, no CALIBRATION_REQUIRED skip."""
        rule = _make_rule(
            rule_name="irrigation_trigger",
            trigger_conditions=_threshold_condition(ESP_ID_A, "soil_moisture", "<", 30.0, gpio=32),
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )
        skip_collector: list = []

        result = _builder()._extract_offline_rule(
            rule, ESP_ID_A, skip_collector=skip_collector, calibrated_sensors=set()
        )

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 32
        assert result[0]["sensor_value_type"] == "moisture"
        assert result[0]["actuator_gpio"] == 25
        assert skip_collector == []

    def test_and_two_raw_comparable_sensors_still_not_exported(self):
        """AUT-1531 stays intact: ph AND ec is not representable, so no export."""
        rule = _make_rule(
            rule_name="ph_and_ec",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=34, sensor_type="ph"),
                _hysteresis_cooling(ESP_ID_A, gpio=35, sensor_type="ec"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )
        rule.logic_operator = "AND"
        skip_collector: list = []

        result = _builder()._extract_offline_rule(
            rule, ESP_ID_A, skip_collector=skip_collector, calibrated_sensors=set()
        )

        assert result == []
        assert len(skip_collector) == 1
        assert skip_collector[0]["reason_code"] == ConfigPayloadBuilder.REASON_UNSUPPORTED_CONDITION
        assert "2 sensor conditions" in skip_collector[0]["reason_detail"]

    def test_threshold_value_is_exported_untransformed(self):
        """The RAW threshold reaches the struct unchanged — no slope/offset/ATC applied."""
        rule = _make_rule(
            rule_name="ph_raw_threshold",
            trigger_conditions=_threshold_condition(ESP_ID_A, "ph", ">", 2100.0, gpio=34),
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )

        result = _builder()._extract_offline_rule(rule, ESP_ID_A, calibrated_sensors=set())

        assert len(result) == 1
        assert result[0]["activate_above"] == 2100.0


# ---------------------------------------------------------------------------
# Test 6 — "between" operator → None + logger.info
# ---------------------------------------------------------------------------


class TestUnsupportedOperator:
    def test_between_operator_returns_none_with_info_log(self, caplog):
        """threshold condition with 'between' operator → None and an INFO log entry."""
        rule = _make_rule(
            rule_name="between_temp_rule",
            trigger_conditions={
                "type": "sensor_threshold",
                "esp_id": ESP_ID_A,
                "gpio": 4,
                "sensor_type": "sht31_temp",
                "operator": "between",
                "value": 20.0,
            },
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )

        with caplog.at_level(logging.INFO):
            result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert result == []
        assert "not convertible" in caplog.text


# ---------------------------------------------------------------------------
# Test 7 — Cross-ESP condition → None
# ---------------------------------------------------------------------------


class TestCrossEspThresholdCondition:
    def test_cross_esp_threshold_sensor_on_wrong_esp_returns_none(self):
        """sensor_threshold condition referencing ESP_B while querying ESP_A → None."""
        rule = _make_rule(
            rule_name="cross_esp_threshold",
            trigger_conditions=_threshold_condition(ESP_ID_B, "sht31_temp", ">", 28.0, gpio=4),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert result == []


# ---------------------------------------------------------------------------
# Test 8 — Midnight time window 22:00–06:00 UTC
# ---------------------------------------------------------------------------


class TestMidnightTimeWindow:
    def test_midnight_time_window_22_to_06_preserved_in_time_filter(self):
        """AND-compound with 22:00–06:00 UTC time_window → time_filter start=22, end=6."""
        rule = _make_rule(
            rule_name="night_ventilation",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 22,
                    "end_hour": 6,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert "time_filter" in r
        tf = r["time_filter"]
        assert tf["enabled"] is True
        assert tf["start_hour"] == 22
        assert tf["end_hour"] == 6
        assert tf["start_minute"] == 0
        assert tf["end_minute"] == 0


# ---------------------------------------------------------------------------
# Test 9-11 — days_of_week → days_of_week_mask mapping
# ---------------------------------------------------------------------------


class TestDaysOfWeekMaskExtraction:
    def test_days_of_week_maps_to_tm_wday_mask(self):
        """DB days [0,1,3,4,5,6] -> mask with bits 1,2,4,5,6,0 set (0x77)."""
        rule = _make_rule(
            rule_name="weekday_window",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 8,
                    "end_hour": 20,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                    "days_of_week": [0, 1, 3, 4, 5, 6],
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        tf = result[0]["time_filter"]
        assert tf["days_of_week_mask"] == 0x77

    def test_missing_days_of_week_defaults_to_all_days(self):
        """Missing days_of_week field -> default mask 0x7F."""
        rule = _make_rule(
            rule_name="window_without_days",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 9,
                    "end_hour": 17,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        tf = result[0]["time_filter"]
        assert tf["days_of_week_mask"] == 0x7F

    def test_db_day_index_conversion_monday_and_sunday(self):
        """DB 0=Mon maps to bit1, DB 6=Sun maps to bit0 => mask 0x03."""
        rule = _make_rule(
            rule_name="monday_and_sunday",
            trigger_conditions=[
                _hysteresis_cooling(ESP_ID_A, gpio=4),
                {
                    "type": "time_window",
                    "start_hour": 10,
                    "end_hour": 12,
                    "start_minute": 0,
                    "end_minute": 0,
                    "timezone": "UTC",
                    "days_of_week": [0, 6],
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = _builder()._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        tf = result[0]["time_filter"]
        assert tf["days_of_week_mask"] == 0x03
