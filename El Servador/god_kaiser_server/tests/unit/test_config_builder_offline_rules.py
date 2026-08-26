"""
Unit Tests: ConfigPayloadBuilder._build_offline_rules / _extract_offline_rule

Tests the offline hysteresis rule extraction added as part of SAFETY-P4.

Scenarios covered:
1. Local hysteresis rule (sensor + actuator on same ESP) → included
2. Cross-ESP rule (sensor on ESP-A, actuator on ESP-B) → excluded
3. ESP with no matching rules → offline_rules is empty list
4. More than MAX_OFFLINE_RULES matching rules → truncated to 8
5. Cooling-mode rule → thresholds mapped correctly
6. Heating-mode rule → thresholds mapped correctly
7. Hysteresis condition without valid threshold pair → excluded
8. Logic-repo failure → graceful fallback to empty list
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.config_builder import ConfigPayloadBuilder

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

ESP_ID_A = "ESP_AABB11CC"
ESP_ID_B = "ESP_DDEE22FF"


def _make_esp(device_id: str = ESP_ID_A) -> MagicMock:
    esp = MagicMock()
    esp.device_id = device_id
    esp.id = uuid.uuid4()
    esp.zone_id = "zone_greenhouse"
    esp.zone_name = "Greenhouse"
    return esp


def _make_rule(
    rule_name: str,
    trigger_conditions: object,
    actions: list,
    enabled: bool = True,
) -> MagicMock:
    rule = MagicMock()
    rule.rule_name = rule_name
    rule.trigger_conditions = trigger_conditions
    rule.actions = actions
    rule.enabled = enabled
    rule.priority = 100
    return rule


def _heating_condition(esp_id: str, gpio: int = 4, sensor_type: str = "ds18b20") -> dict:
    return {
        "type": "hysteresis",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "activate_below": 18.0,
        "deactivate_above": 22.0,
    }


def _cooling_condition(esp_id: str, gpio: int = 4, sensor_type: str = "sht31_temp") -> dict:
    return {
        "type": "hysteresis",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "activate_above": 28.0,
        "deactivate_below": 24.0,
    }


def _actuator_action(esp_id: str, gpio: int = 18, duration_seconds: int = 0) -> dict:
    return {
        "type": "actuator_command",
        "esp_id": esp_id,
        "gpio": gpio,
        "command": "ON",
        "value": 1.0,
        "duration_seconds": duration_seconds,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractOfflineRuleUnit:
    """Pure unit tests for _extract_offline_rule (no DB needed)."""

    def _builder(self) -> ConfigPayloadBuilder:
        return ConfigPayloadBuilder()

    # ------------------------------------------------------------------
    # 1. Local heating rule
    # ------------------------------------------------------------------

    def test_local_heating_rule_included(self):
        """Heating rule with sensor + actuator on same ESP → returned."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="heat_rule",
            trigger_conditions=_heating_condition(ESP_ID_A),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["sensor_gpio"] == 4
        assert r["actuator_gpio"] == 18
        assert r["sensor_value_type"] == "ds18b20"
        assert r["activate_below"] == 18.0
        assert r["deactivate_above"] == 22.0
        # Cooling fields must be zero (heating mode)
        assert r["activate_above"] == 0.0
        assert r["deactivate_below"] == 0.0
        assert r["max_on_seconds"] == 0

    # ------------------------------------------------------------------
    # 2. Local cooling rule
    # ------------------------------------------------------------------

    def test_local_cooling_rule_included(self):
        """Cooling rule with sensor + actuator on same ESP → returned."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="cool_rule",
            trigger_conditions=_cooling_condition(ESP_ID_A),
            actions=[_actuator_action(ESP_ID_A, gpio=22)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["sensor_gpio"] == 4
        assert r["actuator_gpio"] == 22
        assert r["sensor_value_type"] == "sht31_temp"
        assert r["activate_above"] == 28.0
        assert r["deactivate_below"] == 24.0
        # Heating fields must be zero (cooling mode)
        assert r["activate_below"] == 0.0
        assert r["deactivate_above"] == 0.0
        assert r["max_on_seconds"] == 0

    # ------------------------------------------------------------------
    # 3. Cross-ESP rule: sensor on ESP_A, actuator on ESP_B → excluded
    # ------------------------------------------------------------------

    def test_cross_esp_rule_excluded(self):
        """Rule where actuator is on a different ESP → not included."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="cross_esp_rule",
            trigger_conditions=_heating_condition(ESP_ID_A),
            actions=[_actuator_action(ESP_ID_B, gpio=5)],  # different ESP!
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert result == [], "Cross-ESP rules must not appear in offline_rules"

    # ------------------------------------------------------------------
    # 4. Hysteresis condition references wrong ESP → excluded
    # ------------------------------------------------------------------

    def test_sensor_on_wrong_esp_excluded(self):
        """Hysteresis condition for ESP_B queried from perspective of ESP_A → None."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="wrong_esp_rule",
            trigger_conditions=_heating_condition(ESP_ID_B),  # sensor on B
            actions=[_actuator_action(ESP_ID_B, gpio=5)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    # ------------------------------------------------------------------
    # 5. Conditions stored as list (multi-condition rule)
    # ------------------------------------------------------------------

    def test_list_conditions_with_hysteresis_included(self):
        """trigger_conditions as list containing a hysteresis entry → included."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="list_cond_rule",
            trigger_conditions=[
                {"type": "time_window", "start_hour": 6, "end_hour": 22},
                _heating_condition(ESP_ID_A, gpio=7, sensor_type="ds18b20"),
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=12)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["sensor_gpio"] == 7
        assert r["actuator_gpio"] == 12

    def test_time_window_only_rule_converted_to_offline_rule(self):
        """Pure time_window + local actuator ON command becomes time-window offline rule."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="light_schedule_offline",
            trigger_conditions={
                "type": "time_window",
                "start_hour": 6,
                "start_minute": 0,
                "end_hour": 18,
                "end_minute": 0,
                "timezone": "Europe/Berlin",
            },
            actions=[_actuator_action(ESP_ID_A, gpio=25, duration_seconds=7)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["actuator_gpio"] == 25
        assert r["sensor_gpio"] == ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_GPIO
        assert r["sensor_value_type"] == ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_TYPE_ON
        assert r["time_filter"]["enabled"] is True
        assert r["time_filter"]["start_hour"] == 6
        assert r["time_filter"]["end_hour"] == 18
        assert r["max_on_seconds"] == 7

    def test_time_window_only_rule_uses_legacy_duration_alias(self):
        """Legacy action field `duration` is mapped to max_on_seconds in offline rule."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="irrigation_schedule_legacy_duration",
            trigger_conditions={
                "type": "time_window",
                "start_hour": 13,
                "start_minute": 0,
                "end_hour": 13,
                "end_minute": 1,
                "timezone": "Europe/Berlin",
            },
            actions=[
                {
                    "type": "actuator_command",
                    "esp_id": ESP_ID_A,
                    "gpio": 15,
                    "command": "ON",
                    "value": 1.0,
                    "duration": 5,
                }
            ],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert r["sensor_value_type"] == ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_TYPE_ON
        assert r["max_on_seconds"] == 5

    def test_time_window_only_rule_without_on_action_is_skipped(self):
        """time_window-only with OFF action is skipped to avoid ambiguous inverse behavior."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="night_off_only",
            trigger_conditions={
                "type": "time_window",
                "start_hour": 22,
                "start_minute": 0,
                "end_hour": 6,
                "end_minute": 0,
                "timezone": "UTC",
            },
            actions=[
                {
                    "type": "actuator_command",
                    "esp_id": ESP_ID_A,
                    "gpio": 25,
                    "command": "OFF",
                    "value": 0.0,
                    "duration_seconds": 0,
                }
            ],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    # ------------------------------------------------------------------
    # 6. Hysteresis condition without valid threshold pair → excluded
    # ------------------------------------------------------------------

    def test_incomplete_thresholds_excluded(self):
        """Hysteresis condition with only activate_below (no deactivate_above) → None."""
        builder = self._builder()
        incomplete_cond = {
            "type": "hysteresis",
            "esp_id": ESP_ID_A,
            "gpio": 4,
            "sensor_type": "ds18b20",
            "activate_below": 18.0,
            # deactivate_above intentionally missing
        }
        rule = _make_rule(
            rule_name="incomplete_rule",
            trigger_conditions=incomplete_cond,
            actions=[_actuator_action(ESP_ID_A)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    # ------------------------------------------------------------------
    # 7. sensor_value_type field name (NOT sensor_type in output)
    # ------------------------------------------------------------------

    def test_output_field_name_is_sensor_value_type(self):
        """Result dict must use 'sensor_value_type', not 'sensor_type'."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="field_name_rule",
            trigger_conditions=_cooling_condition(ESP_ID_A, sensor_type="sht31_humidity"),
            actions=[_actuator_action(ESP_ID_A)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        r = result[0]
        assert "sensor_value_type" in r, "Field must be named 'sensor_value_type'"
        assert "sensor_type" not in r, "Field must NOT be named 'sensor_type'"
        assert r["sensor_value_type"] == "sht31_humidity"

    # ------------------------------------------------------------------
    # 8. actions not a list → excluded
    # ------------------------------------------------------------------

    def test_actions_not_list_excluded(self):
        """If actions field is not a list, rule is skipped gracefully."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="bad_actions_rule",
            trigger_conditions=_heating_condition(ESP_ID_A),
            actions=None,  # type: ignore[arg-type]
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert result == []

    # ------------------------------------------------------------------
    # 9. RAW-comparable sensor types → exported without calibration (AUT-1565)
    # ------------------------------------------------------------------

    def test_offline_rule_exports_ph_sensor_without_calibration(self):
        """Rule with pH sensor → exported; ESP compares its RAW cache (AUT-1565)."""
        builder = self._builder()
        skip_collector: list = []
        rule = _make_rule(
            rule_name="ph_dosing_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=34, sensor_type="ph"),
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )

        result = builder._extract_offline_rule(
            rule, ESP_ID_A, skip_collector=skip_collector, calibrated_sensors=set()
        )

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 34
        assert result[0]["sensor_value_type"] == "ph"
        assert result[0]["activate_below"] == 18.0
        assert result[0]["deactivate_above"] == 22.0
        assert skip_collector == []

    def test_offline_rule_exports_ec_sensor_without_calibration(self):
        """Rule with EC sensor → exported; ESP compares its RAW cache (AUT-1565)."""
        builder = self._builder()
        skip_collector: list = []
        rule = _make_rule(
            rule_name="ec_dosing_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=35, sensor_type="ec"),
            actions=[_actuator_action(ESP_ID_A, gpio=26)],
        )

        result = builder._extract_offline_rule(
            rule, ESP_ID_A, skip_collector=skip_collector, calibrated_sensors=set()
        )

        assert len(result) == 1
        assert result[0]["sensor_value_type"] == "ec"
        assert result[0]["actuator_gpio"] == 26
        assert skip_collector == []

    def test_offline_rule_allows_sht31_sensor(self):
        """Rule with sht31_humidity sensor → included (digital sensor, real physical values)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="humidity_rule",
            trigger_conditions=_cooling_condition(ESP_ID_A, gpio=21, sensor_type="sht31_humidity"),
            actions=[_actuator_action(ESP_ID_A, gpio=27)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        assert result[0]["sensor_value_type"] == "sht31_humidity"

    def test_offline_rule_exports_soil_moisture_alias(self):
        """soil_moisture alias normalizes to moisture and is exported RAW (AUT-1565)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="irrigation_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=32, sensor_type="soil_moisture"),
            actions=[_actuator_action(ESP_ID_A, gpio=28)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A, calibrated_sensors=set())

        assert len(result) == 1
        assert result[0]["sensor_value_type"] == "moisture"

    def test_offline_rule_exports_ph_sensor_alias(self):
        """ph_sensor alias normalizes to ph and is exported RAW (AUT-1565)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="ph_dosing_alias_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=33, sensor_type="ph_sensor"),
            actions=[_actuator_action(ESP_ID_A, gpio=29)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A, calibrated_sensors=set())

        assert len(result) == 1
        assert result[0]["sensor_value_type"] == "ph"

    def test_calibration_gate_still_blocks_non_raw_comparable_type(self):
        """The gate is key-scoped: a calibration type outside the RAW set still skips."""
        builder = self._builder()
        skip_collector: list = []
        rule = _make_rule(
            rule_name="hypothetical_analog_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=36, sensor_type="ds18b20"),
            actions=[_actuator_action(ESP_ID_A, gpio=30)],
        )

        with patch.object(
            ConfigPayloadBuilder,
            "CALIBRATION_REQUIRED_SENSOR_TYPES",
            ConfigPayloadBuilder.CALIBRATION_REQUIRED_SENSOR_TYPES | {"ds18b20"},
        ):
            result = builder._extract_offline_rule(
                rule, ESP_ID_A, skip_collector=skip_collector, calibrated_sensors=set()
            )

        assert result == []
        assert len(skip_collector) == 1
        assert skip_collector[0]["reason_code"] == ConfigPayloadBuilder.REASON_CALIBRATION_REQUIRED

    def test_raw_comparable_types_are_a_subset_of_the_calibration_gate(self):
        """AUT-1565 exemption covers exactly the four contract keys and nothing else."""
        assert ConfigPayloadBuilder.OFFLINE_RAW_COMPARABLE_SENSOR_TYPES == {
            "ph",
            "ec",
            "moisture",
            "soil_moisture",
        }
        assert ConfigPayloadBuilder.OFFLINE_RAW_COMPARABLE_SENSOR_TYPES.issubset(
            ConfigPayloadBuilder.CALIBRATION_REQUIRED_SENSOR_TYPES
        )

    def test_normalized_type_in_returned_dict(self):
        """After normalization, sensor_value_type in result uses canonical form."""
        builder = self._builder()
        # "temperature_sht31" is an alias → normalizes to "sht31_temp"
        rule = _make_rule(
            rule_name="temp_alias_rule",
            trigger_conditions=_heating_condition(
                ESP_ID_A, gpio=4, sensor_type="temperature_sht31"
            ),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        assert result[0]["sensor_value_type"] == "sht31_temp"

    # ------------------------------------------------------------------
    # AUT-664: Multi-actuator rule → one offline_rule entry per actuator
    # ------------------------------------------------------------------

    def test_multi_actuator_rule_produces_one_entry_per_actuator(self):
        """Rule with 2 local actuator actions → 2 offline_rule entries (AUT-664 fix)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="timmsregen",
            trigger_conditions=_cooling_condition(
                ESP_ID_A, gpio=5, sensor_type="sht31_humidity"
            ),
            actions=[
                _actuator_action(ESP_ID_A, gpio=25, duration_seconds=8),
                _actuator_action(ESP_ID_A, gpio=14, duration_seconds=8),
            ],
        )

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 2
        gpios = {r["actuator_gpio"] for r in result}
        assert gpios == {25, 14}
        for r in result:
            assert r["sensor_gpio"] == 5
            assert r["sensor_value_type"] == "sht31_humidity"
            assert r["max_on_seconds"] == 8
            assert r["activate_above"] == 28.0
            assert r["deactivate_below"] == 24.0


    # ------------------------------------------------------------------
    # AUT-739: OR-compound DNF-flattening
    # ------------------------------------------------------------------

    def test_or_compound_two_hysteresis_conditions_flattened(self):
        """OR compound with 2 hysteresis conditions → 2 offline rules (DNF, AUT-739)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="moisture_or_rule",
            trigger_conditions=[
                {
                    "type": "hysteresis",
                    "esp_id": ESP_ID_A,
                    "gpio": 33,
                    "sensor_type": "sht31_humidity",
                    "activate_below": 50.0,
                    "deactivate_above": 60.0,
                },
                {
                    "type": "hysteresis",
                    "esp_id": ESP_ID_A,
                    "gpio": 32,
                    "sensor_type": "sht31_humidity",
                    "activate_below": 30.0,
                    "deactivate_above": 40.0,
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )
        rule.logic_operator = "OR"

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 2, "OR compound with 2 branches must produce 2 offline rules"
        gpios = {r["sensor_gpio"] for r in result}
        assert gpios == {33, 32}
        for r in result:
            assert r["actuator_gpio"] == 25
            assert r["sensor_value_type"] == "sht31_humidity"
            assert r["activate_below"] > 0.0
            assert r["deactivate_above"] > 0.0
            assert r["activate_above"] == 0.0   # heating mode — cooling fields zero
            assert r["deactivate_below"] == 0.0

    def test_or_compound_threshold_conditions_flattened(self):
        """OR compound with sensor_threshold conditions → 2 offline rules with synthetic deadband."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="temp_or_threshold_rule",
            trigger_conditions=[
                {
                    "type": "sensor_threshold",
                    "esp_id": ESP_ID_A,
                    "gpio": 4,
                    "sensor_type": "ds18b20",
                    "operator": "<",
                    "value": 18.0,
                },
                {
                    "type": "sensor_threshold",
                    "esp_id": ESP_ID_A,
                    "gpio": 7,
                    "sensor_type": "ds18b20",
                    "operator": "<",
                    "value": 15.0,
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "OR"

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 2
        sensor_gpios = {r["sensor_gpio"] for r in result}
        assert sensor_gpios == {4, 7}
        for r in result:
            assert r["actuator_gpio"] == 18
            assert r["activate_below"] > 0.0     # heating threshold set
            assert r["deactivate_above"] > 0.0   # deadband added
            assert r["activate_above"] == 0.0
            assert r["deactivate_below"] == 0.0

    def test_or_compound_raw_comparable_branch_also_exports(self):
        """OR compound with a pH branch → both branches export RAW (AUT-1565)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="ph_or_temp_rule",
            trigger_conditions=[
                {
                    "type": "hysteresis",
                    "esp_id": ESP_ID_A,
                    "gpio": 34,
                    "sensor_type": "ph",        # RAW-comparable → no longer skipped
                    "activate_below": 6.0,
                    "deactivate_above": 7.0,
                },
                {
                    "type": "hysteresis",
                    "esp_id": ESP_ID_A,
                    "gpio": 4,
                    "sensor_type": "ds18b20",   # valid
                    "activate_below": 18.0,
                    "deactivate_above": 22.0,
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )
        rule.logic_operator = "OR"

        result = builder._extract_offline_rule(rule, ESP_ID_A, calibrated_sensors=set())

        assert len(result) == 2
        assert {r["sensor_value_type"] for r in result} == {"ph", "ds18b20"}

    def test_or_compound_all_branches_invalid_returns_empty_with_skip_entry(self):
        """OR compound where no branch has a convertible operator → empty list + skip entry."""
        builder = self._builder()
        skip_collector: list = []
        rule = _make_rule(
            rule_name="between_or_between_rule",
            trigger_conditions=[
                {
                    "type": "sensor_threshold",
                    "esp_id": ESP_ID_A,
                    "gpio": 4,
                    "sensor_type": "ds18b20",
                    "operator": "between",
                    "value": 6.0,
                },
                {
                    "type": "sensor_threshold",
                    "esp_id": ESP_ID_A,
                    "gpio": 7,
                    "sensor_type": "ds18b20",
                    "operator": "between",
                    "value": 1.0,
                },
            ],
            actions=[_actuator_action(ESP_ID_A, gpio=25)],
        )
        rule.logic_operator = "OR"

        result = builder._extract_offline_rule(rule, ESP_ID_A, skip_collector=skip_collector)

        assert result == []
        assert len(skip_collector) == 1
        assert skip_collector[0]["reason_code"] == ConfigPayloadBuilder.REASON_UNSUPPORTED_CONDITION

    def test_and_compound_single_hysteresis_still_works(self):
        """AND-compound with single hysteresis condition (and no OR) still produces one rule."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="and_single_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=4),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        rule.logic_operator = "AND"

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 4
        assert result[0]["actuator_gpio"] == 18

    def test_or_compound_multi_actuator_produces_n_times_m_rules(self):
        """OR compound with 2 conditions × 2 actuators → 4 offline rules (N×M)."""
        builder = self._builder()
        rule = _make_rule(
            rule_name="or_multi_act_rule",
            trigger_conditions=[
                _heating_condition(ESP_ID_A, gpio=33, sensor_type="sht31_humidity"),
                _heating_condition(ESP_ID_A, gpio=32, sensor_type="sht31_humidity"),
            ],
            actions=[
                _actuator_action(ESP_ID_A, gpio=25, duration_seconds=120),
                _actuator_action(ESP_ID_A, gpio=26, duration_seconds=120),
            ],
        )
        rule.logic_operator = "OR"

        result = builder._extract_offline_rule(rule, ESP_ID_A)

        assert len(result) == 4, "2 OR branches × 2 actuators = 4 offline rules"
        actuator_gpios = [r["actuator_gpio"] for r in result]
        assert actuator_gpios.count(25) == 2
        assert actuator_gpios.count(26) == 2


class TestBuildOfflineRulesAsync:
    """Async integration-style tests for _build_offline_rules."""

    def _builder(self) -> ConfigPayloadBuilder:
        return ConfigPayloadBuilder()

    # ------------------------------------------------------------------
    # 9. No matching rules → offline_rules is empty list
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_matching_rules_returns_empty_list(self):
        """ESP with only non-convertible rules → offline_rules == [].

        Uses a "between" operator, which has no offline hysteresis representation.
        """
        builder = self._builder()
        mock_logic_repo = AsyncMock()
        non_hysteresis_rule = _make_rule(
            rule_name="between_threshold_rule",
            trigger_conditions={
                "type": "sensor_threshold",
                "esp_id": ESP_ID_A,
                "gpio": 34,
                "sensor_type": "ds18b20",
                "operator": "between",
                "value": 7.5,
            },
            actions=[_actuator_action(ESP_ID_A)],
        )
        mock_logic_repo.get_enabled_rules = AsyncMock(return_value=[non_hysteresis_rule])
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        mock_db = MagicMock()

        result = await builder._build_offline_rules(mock_db, esp)

        assert result == []

    # ------------------------------------------------------------------
    # 10. One matching local rule → single entry
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_single_local_rule_included(self):
        """One enabled local heating rule → exactly one entry in result."""
        builder = self._builder()
        mock_logic_repo = AsyncMock()
        rule = _make_rule(
            rule_name="local_heat",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=4),
            actions=[_actuator_action(ESP_ID_A, gpio=18)],
        )
        mock_logic_repo.get_enabled_rules = AsyncMock(return_value=[rule])
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        mock_db = MagicMock()

        result = await builder._build_offline_rules(mock_db, esp)

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == 4
        assert result[0]["actuator_gpio"] == 18

    # ------------------------------------------------------------------
    # 11. Cross-ESP rule mixed with local rule → only local included
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cross_esp_rule_filtered_out(self):
        """Cross-ESP rule is excluded; local rule is still included."""
        builder = self._builder()
        mock_logic_repo = AsyncMock()

        local_rule = _make_rule(
            rule_name="local_cool",
            trigger_conditions=_cooling_condition(ESP_ID_A, gpio=4),
            actions=[_actuator_action(ESP_ID_A, gpio=22)],
        )
        cross_rule = _make_rule(
            rule_name="cross_rule",
            trigger_conditions=_heating_condition(ESP_ID_A, gpio=7),
            actions=[_actuator_action(ESP_ID_B, gpio=5)],  # actuator on different ESP
        )
        mock_logic_repo.get_enabled_rules = AsyncMock(return_value=[local_rule, cross_rule])
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        mock_db = MagicMock()

        result = await builder._build_offline_rules(mock_db, esp)

        assert len(result) == 1
        assert result[0]["actuator_gpio"] == 22

    # ------------------------------------------------------------------
    # 12. More than MAX_OFFLINE_RULES rules → truncated to MAX_OFFLINE_RULES
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_truncation_at_max_limit(self):
        """10 matching rules → truncated to MAX_OFFLINE_RULES (8) with warning logged."""
        builder = self._builder()
        mock_logic_repo = AsyncMock()

        rules = [
            _make_rule(
                rule_name=f"rule_{i}",
                trigger_conditions=_heating_condition(ESP_ID_A, gpio=i + 10),
                actions=[_actuator_action(ESP_ID_A, gpio=i + 20)],
            )
            for i in range(10)  # 10 rules > MAX_OFFLINE_RULES (8)
        ]
        mock_logic_repo.get_enabled_rules = AsyncMock(return_value=rules)
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        mock_db = MagicMock()

        with patch.object(builder.__class__._build_offline_rules, "__wrapped__", None, create=True):
            result = await builder._build_offline_rules(mock_db, esp)

        assert len(result) == ConfigPayloadBuilder.MAX_OFFLINE_RULES

    # ------------------------------------------------------------------
    # 13. Logic repo raises exception → graceful fallback to []
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_logic_repo_failure_returns_empty_list(self):
        """If get_enabled_rules raises, _build_offline_rules returns [] without propagating."""
        builder = self._builder()
        mock_logic_repo = AsyncMock()
        mock_logic_repo.get_enabled_rules = AsyncMock(side_effect=Exception("DB connection lost"))
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        mock_db = MagicMock()

        result = await builder._build_offline_rules(mock_db, esp)

        assert result == [], "Should return empty list on DB failure, not propagate exception"


class TestValidateOfflineRulesConsistency:
    """AUT-59: Tests for _validate_offline_rules_consistency."""

    def _builder(self) -> ConfigPayloadBuilder:
        return ConfigPayloadBuilder()

    def test_consistent_rules_pass_through(self):
        """Rules whose GPIOs exist in the config frame are kept."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 4, "sensor_type": "ds18b20"}]
        actuator_payloads = [{"gpio": 18, "actuator_type": "relay"}]
        offline_rules = [
            {
                "actuator_gpio": 18,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 22.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            }
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 1
        assert result[0]["actuator_gpio"] == 18

    def test_missing_actuator_gpio_strips_rule(self):
        """Rule referencing actuator_gpio absent from actuator payloads is removed."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 4, "sensor_type": "ds18b20"}]
        actuator_payloads = [{"gpio": 22, "actuator_type": "relay"}]
        offline_rules = [
            {
                "actuator_gpio": 18,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 22.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            }
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 0

    def test_missing_sensor_gpio_strips_rule(self):
        """Rule referencing sensor_gpio absent from sensor payloads is removed."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 7, "sensor_type": "sht31_temp"}]
        actuator_payloads = [{"gpio": 18, "actuator_type": "relay"}]
        offline_rules = [
            {
                "actuator_gpio": 18,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 22.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            }
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 0

    def test_empty_actuators_strips_all_rules(self):
        """No actuators in config frame → all offline_rules stripped."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 4, "sensor_type": "ds18b20"}]
        actuator_payloads = []
        offline_rules = [
            {
                "actuator_gpio": 18,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 22.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            }
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 0

    def test_empty_offline_rules_returns_empty(self):
        """No offline_rules → empty list returned directly."""
        builder = self._builder()

        result = builder._validate_offline_rules_consistency(
            [], [{"gpio": 4}], [{"gpio": 18}], ESP_ID_A
        )

        assert result == []

    def test_mixed_consistent_and_inconsistent(self):
        """Only inconsistent rules are stripped, consistent ones kept."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 4, "sensor_type": "ds18b20"}]
        actuator_payloads = [{"gpio": 18, "actuator_type": "relay"}]
        offline_rules = [
            {
                "actuator_gpio": 18,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 22.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            },
            {
                "actuator_gpio": 99,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 20.0,
                "deactivate_above": 25.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
            },
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 1
        assert result[0]["actuator_gpio"] == 18

    def test_time_window_only_rule_ignores_sensor_gpio_membership(self):
        """time-window-only rule with synthetic sensor_gpio=255 must not be stripped."""
        builder = self._builder()
        sensor_payloads = [{"gpio": 4, "sensor_type": "sht31_temp"}]
        actuator_payloads = [{"gpio": 25, "actuator_type": "relay"}]
        offline_rules = [
            {
                "actuator_gpio": 25,
                "sensor_gpio": ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_GPIO,
                "sensor_value_type": ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_TYPE_ON,
                "activate_below": 0.0,
                "deactivate_above": 0.0,
                "activate_above": 1.0,
                "deactivate_below": 0.0,
                "time_filter": {
                    "enabled": True,
                    "start_hour": 6,
                    "start_minute": 0,
                    "end_hour": 18,
                    "end_minute": 0,
                    "days_of_week_mask": 0x7F,
                    "timezone": "Europe/Berlin",
                },
            }
        ]

        result = builder._validate_offline_rules_consistency(
            offline_rules, sensor_payloads, actuator_payloads, ESP_ID_A
        )

        assert len(result) == 1
        assert result[0]["sensor_gpio"] == ConfigPayloadBuilder.TIME_WINDOW_ONLY_SENSOR_GPIO


# ---------------------------------------------------------------------------
# AUT-1141 L1: packed-struct wire encoding for the offline_rules scope
# ---------------------------------------------------------------------------


class TestOfflineRulesPackedEncoding:
    """Server-side struct.pack/CRC8/base64 encoder + per-device dispatch."""

    def test_pack_offline_rule_produces_56_bytes_with_expected_field_layout(self):
        import struct

        from src.services.config_builder import OFFLINE_RULE_PACK_FORMAT_V5, _pack_offline_rule

        rule = {
            "actuator_gpio": 25,
            "sensor_gpio": 4,
            "sensor_value_type": "bme280_humidity",
            "activate_below": 30.5,
            "deactivate_above": 45.0,
            "activate_above": 0.0,
            "deactivate_below": 0.0,
            "current_state_active": True,
            "max_on_seconds": 120,
            "cooldown_seconds": 30,
            "time_filter": {
                "enabled": True,
                "start_hour": 22,
                "start_minute": 0,
                "end_hour": 6,
                "end_minute": 30,
                "days_of_week_mask": 0x7F,
                "timezone": "Europe/Berlin",
            },
        }

        packed = _pack_offline_rule(rule)

        assert len(packed) == 56
        fields = struct.unpack(OFFLINE_RULE_PACK_FORMAT_V5, packed)
        (
            enabled,
            actuator_gpio,
            sensor_gpio,
            sensor_value_type,
            activate_below,
            deactivate_above,
            activate_above,
            deactivate_below,
            is_active,
            server_override,
            time_filter_enabled,
            start_hour,
            start_minute,
            end_hour,
            end_minute,
            days_of_week_mask,
            timezone_mode,
            max_on_seconds,
            cooldown_seconds,
        ) = fields

        assert enabled == 1
        assert actuator_gpio == 25
        assert sensor_gpio == 4
        assert sensor_value_type.split(b"\x00", 1)[0].decode() == "bme280_humidity"
        assert activate_below == pytest.approx(30.5)
        assert deactivate_above == pytest.approx(45.0)
        assert activate_above == pytest.approx(0.0)
        assert deactivate_below == pytest.approx(0.0)
        assert is_active == 1
        assert server_override == 0  # parseOfflineRules always forces this false
        assert time_filter_enabled == 1
        assert (start_hour, start_minute, end_hour, end_minute) == (22, 0, 6, 30)
        assert days_of_week_mask == 0x7F
        assert timezone_mode == 1  # Europe/Berlin -> OfflineRuleTimezone::EUROPE_BERLIN
        assert max_on_seconds == 120
        assert cooldown_seconds == 30

    def test_pack_offline_rule_defaults_for_minimal_rule(self):
        """A rule dict without time_filter/cooldown_seconds (today's server output,
        see config_builder.py _extract_offline_rule) must still pack to 56 B with
        firmware-matching zero-defaults, not raise."""
        from src.services.config_builder import _pack_offline_rule

        rule = {
            "actuator_gpio": 12,
            "sensor_gpio": 255,
            "sensor_value_type": "temperature",
            "activate_below": 0.0,
            "deactivate_above": 0.0,
            "activate_above": 0.0,
            "deactivate_below": 0.0,
            "current_state_active": False,
            "max_on_seconds": 0,
        }

        packed = _pack_offline_rule(rule)
        assert len(packed) == 56

    def test_pack_offline_rule_oversized_sensor_value_type_disables_rule(self):
        """Mirrors parseOfflineRules' defensive fallback (offline_mode_manager.cpp
        parseOfflineRules): a sensor_value_type > 20 chars disables the rule
        instead of corrupting the wire format or raising."""
        import struct

        from src.services.config_builder import OFFLINE_RULE_PACK_FORMAT_V5, _pack_offline_rule

        rule = {
            "actuator_gpio": 12,
            "sensor_gpio": 4,
            "sensor_value_type": "x" * 30,
            "activate_below": 0.0,
            "deactivate_above": 0.0,
            "activate_above": 0.0,
            "deactivate_below": 0.0,
            "current_state_active": False,
            "max_on_seconds": 0,
        }

        packed = _pack_offline_rule(rule)
        assert len(packed) == 56
        enabled = struct.unpack(OFFLINE_RULE_PACK_FORMAT_V5, packed)[0]
        assert enabled == 0

    def test_crc8_matches_known_reference_vectors(self):
        """CRC-8/SMBUS (poly 0x07, init 0x00, no reflect/xor-out) — same
        bit-for-bit algorithm as offline_mode_manager.cpp crc8() (verified by
        independently computing these vectors, not by re-deriving the formula
        under test)."""
        from src.services.config_builder import _crc8_smbus

        assert _crc8_smbus(b"") == 0x00
        assert _crc8_smbus(b"\x01\x02\x03") == 0x48
        assert _crc8_smbus(b"123456789") == 0xF4

    def test_encode_offline_rules_packed_round_trip(self):
        import base64
        import struct

        from src.services.config_builder import (
            OFFLINE_RULE_PACK_FORMAT_V5,
            _crc8_smbus,
            _encode_offline_rules_packed,
        )

        rules = [
            {
                "actuator_gpio": 25,
                "sensor_gpio": 4,
                "sensor_value_type": "ds18b20",
                "activate_below": 18.0,
                "deactivate_above": 24.0,
                "activate_above": 0.0,
                "deactivate_below": 0.0,
                "current_state_active": False,
                "max_on_seconds": 0,
            },
            {
                "actuator_gpio": 26,
                "sensor_gpio": 5,
                "sensor_value_type": "sht31_humidity",
                "activate_below": 0.0,
                "deactivate_above": 0.0,
                "activate_above": 70.0,
                "deactivate_below": 55.0,
                "current_state_active": True,
                "max_on_seconds": 300,
                "cooldown_seconds": 60,
            },
        ]

        encoded = _encode_offline_rules_packed(rules)

        assert encoded["encoding"] == "packed"
        assert encoded["count"] == 2
        raw = base64.b64decode(encoded["blob"])
        assert len(raw) == 2 * 56 + 1
        body, trailer = raw[:-1], raw[-1]
        assert _crc8_smbus(body) == trailer
        # Wire size is a fraction of the ~214 B/rule JSON form (AUT-1139 §2).
        assert len(encoded["blob"]) < 2 * 100

        # Each 56 B record round-trips through the same format the firmware decodes.
        first = struct.unpack(OFFLINE_RULE_PACK_FORMAT_V5, body[:56])
        assert first[1] == 25 and first[2] == 4  # actuator_gpio, sensor_gpio

    @pytest.mark.parametrize(
        "hardware_type,firmware_version,expected",
        [
            ("MOCK_ESP32", None, "packed"),
            ("MOCK_ESP32", "1.0.0", "packed"),
            ("ESP32_WROOM", "4.0.0", "json"),
            ("ESP32_WROOM", "4.1.0", "packed"),
            ("ESP32_S3_DEVKITC1", "4.2.0", "packed"),
            ("ESP32_S3_DEVKITC1", None, "json"),
            ("XIAO_ESP32_C3", "3.9.9", "json"),
            (None, None, "json"),
        ],
    )
    def test_resolve_offline_rules_encoding_dispatch_matrix(
        self, hardware_type, firmware_version, expected
    ):
        from src.services.config_builder import resolve_offline_rules_encoding

        assert resolve_offline_rules_encoding(hardware_type, firmware_version) == expected

    def test_resolve_offline_rules_encoding_guards_non_string_mock_attributes(self):
        """_make_esp() fixtures across this test module leave hardware_type/
        firmware_version as bare MagicMock attributes (no explicit string) —
        the dispatch must fall back to 'json' instead of raising."""
        from src.services.config_builder import resolve_offline_rules_encoding

        mock_esp = MagicMock()
        assert (
            resolve_offline_rules_encoding(mock_esp.hardware_type, mock_esp.firmware_version)
            == "json"
        )


# ---------------------------------------------------------------------------
# AUT-1143: Board-differentiated resolve_max_offline_rules
# ---------------------------------------------------------------------------


class TestResolveMaxOfflineRules:
    """Unit tests for resolve_max_offline_rules (AUT-1143)."""

    @pytest.mark.parametrize(
        "hardware_type,expected",
        [
            ("ESP32_WROOM", 8),
            ("ESP32_S3_DEVKITC1", 16),
            ("XIAO_ESP32_C3", 8),
            ("MOCK_ESP32", 16),
            (None, 8),
            ("UNKNOWN_BOARD_XYZ", 8),
        ],
    )
    def test_known_and_fallback_values(self, hardware_type, expected):
        """Known board strings return their budgeted capacity; None and unknown
        strings fall back to ConfigPayloadBuilder.MAX_OFFLINE_RULES (8)."""
        from src.services.config_builder import resolve_max_offline_rules

        assert resolve_max_offline_rules(hardware_type) == expected

    def test_non_string_mock_object_returns_fallback(self):
        """A bare MagicMock() object (not a string) — as produced by _make_esp()
        in this test module — must trigger the isinstance guard and return 8."""
        from src.services.config_builder import resolve_max_offline_rules

        mock_obj = MagicMock()
        assert resolve_max_offline_rules(mock_obj) == 8

    def test_make_esp_fixture_produces_fallback(self):
        """Regression: _make_esp() leaves hardware_type as a MagicMock attribute.
        resolve_max_offline_rules must fall back to 8 (== ConfigPayloadBuilder.MAX_OFFLINE_RULES),
        ensuring test_truncation_at_max_limit stays unaffected."""
        from src.services.config_builder import resolve_max_offline_rules

        esp = _make_esp(ESP_ID_A)
        assert resolve_max_offline_rules(esp.hardware_type) == ConfigPayloadBuilder.MAX_OFFLINE_RULES


class TestBuildOfflineRulesS3BoardDifferentiation:
    """AUT-1143: End-to-end board differentiation inside _build_offline_rules."""

    def _builder(self) -> ConfigPayloadBuilder:
        return ConfigPayloadBuilder()

    @pytest.mark.asyncio
    async def test_s3_board_accepts_16_rules(self):
        """ESP32_S3_DEVKITC1 with 20 candidate rules → result truncated to 16."""
        builder = self._builder()
        mock_logic_repo = AsyncMock()

        rules = [
            _make_rule(
                rule_name=f"rule_{i}",
                trigger_conditions=_heating_condition(ESP_ID_A, gpio=i + 10),
                actions=[_actuator_action(ESP_ID_A, gpio=i + 30)],
            )
            for i in range(20)  # 20 rules > S3 budget (16) > WROOM budget (8)
        ]
        mock_logic_repo.get_enabled_rules = AsyncMock(return_value=rules)
        builder.logic_repo = mock_logic_repo

        esp = _make_esp(ESP_ID_A)
        esp.hardware_type = "ESP32_S3_DEVKITC1"
        mock_db = MagicMock()

        result = await builder._build_offline_rules(mock_db, esp)

        assert len(result) == 16, (
            f"S3 board must accept up to 16 offline rules, got {len(result)}"
        )
