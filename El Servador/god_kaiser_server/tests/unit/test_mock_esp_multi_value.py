"""
Unit tests for Mock-ESP Multi-Value Sensor Split.

Tests that multi-value sensors (SHT31, BMP280) are correctly expanded
into individual value types when creating mock ESPs, and that the
simulation_config dict keys use "{gpio}_{sensor_type}" format.
"""

import pytest

from src.sensors.sensor_type_registry import (
    is_multi_value_sensor,
    get_all_value_types_for_device,
)


def _build_expanded_sensors(sensors: list[dict]) -> tuple[dict, list[tuple]]:
    """
    Replicate the expansion logic from debug.py create_mock_esp().

    Returns:
        (expanded_sensors dict, expanded_sensor_configs list of (gpio, type, orig))
    """
    expanded_sensors: dict[str, dict] = {}
    expanded_sensor_configs: list[tuple] = []

    for sensor in sensors:
        sensor_type = sensor["sensor_type"]
        gpio = sensor["gpio"]

        if is_multi_value_sensor(sensor_type):
            value_types = get_all_value_types_for_device(sensor_type)
            for vt in value_types:
                sensor_key = f"{gpio}_{vt}"
                expanded_sensors[sensor_key] = {
                    "sensor_type": vt,
                    "raw_value": sensor.get("raw_value", 0.0),
                    "base_value": sensor.get("raw_value", 0.0),
                    "gpio": gpio,
                }
                expanded_sensor_configs.append((gpio, vt, sensor))
        else:
            sensor_key = f"{gpio}_{sensor_type}"
            expanded_sensors[sensor_key] = {
                "sensor_type": sensor_type,
                "raw_value": sensor.get("raw_value", 0.0),
                "base_value": sensor.get("raw_value", 0.0),
                "gpio": gpio,
            }
            expanded_sensor_configs.append((gpio, sensor_type, sensor))

    return expanded_sensors, expanded_sensor_configs


class TestMultiValueDictKeyExpansion:
    """Test that simulation_config.sensors uses {gpio}_{sensor_type} keys."""

    def test_single_value_sensor_key_format(self):
        """Single-value sensor (DS18B20) uses '{gpio}_{type}' key."""
        sensors = [{"gpio": 4, "sensor_type": "ds18b20", "raw_value": 22.5}]
        expanded, configs = _build_expanded_sensors(sensors)

        assert "4_ds18b20" in expanded
        assert len(expanded) == 1
        assert expanded["4_ds18b20"]["sensor_type"] == "ds18b20"

    def test_multi_value_sht31_creates_two_keys(self):
        """SHT31 on GPIO 21 creates '21_sht31_temp' and '21_sht31_humidity'."""
        sensors = [{"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0}]
        expanded, configs = _build_expanded_sensors(sensors)

        assert len(expanded) == 2
        assert "21_sht31_temp" in expanded
        assert "21_sht31_humidity" in expanded
        assert expanded["21_sht31_temp"]["sensor_type"] == "sht31_temp"
        assert expanded["21_sht31_humidity"]["sensor_type"] == "sht31_humidity"

    def test_multi_value_bmp280_creates_two_keys(self):
        """BMP280 on GPIO 21 creates '21_bmp280_pressure' and '21_bmp280_temp'."""
        sensors = [{"gpio": 21, "sensor_type": "bmp280", "raw_value": 1013.0}]
        expanded, configs = _build_expanded_sensors(sensors)

        assert len(expanded) == 2
        assert "21_bmp280_pressure" in expanded
        assert "21_bmp280_temp" in expanded

    def test_no_key_overwrite_same_gpio(self):
        """Two sensors on same GPIO (sht31_temp + sht31_humidity) don't overwrite."""
        sensors = [{"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0}]
        expanded, configs = _build_expanded_sensors(sensors)

        # Both keys must exist - the old bug was str(21) overwriting
        assert len(expanded) == 2
        keys = list(expanded.keys())
        assert keys[0] != keys[1]

    def test_already_split_types_not_double_expanded(self):
        """Already split types (sht31_temp) are NOT further expanded."""
        sensors = [
            {"gpio": 21, "sensor_type": "sht31_temp", "raw_value": 23.0},
            {"gpio": 21, "sensor_type": "sht31_humidity", "raw_value": 55.0},
        ]
        expanded, configs = _build_expanded_sensors(sensors)

        # sht31_temp and sht31_humidity are NOT multi-value base types
        assert len(expanded) == 2
        assert "21_sht31_temp" in expanded
        assert "21_sht31_humidity" in expanded


class TestMultiValueSensorConfigExpansion:
    """Test that SensorConfig DB entries are expanded correctly."""

    def test_sht31_creates_two_sensor_configs(self):
        """1 SHT31 input → 2 SensorConfig entries (sht31_temp, sht31_humidity)."""
        sensors = [{"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0}]
        _, configs = _build_expanded_sensors(sensors)

        assert len(configs) == 2
        config_types = [(gpio, st) for gpio, st, _ in configs]
        assert (21, "sht31_temp") in config_types
        assert (21, "sht31_humidity") in config_types

    def test_ds18b20_creates_one_sensor_config(self):
        """1 DS18B20 input → 1 SensorConfig entry."""
        sensors = [{"gpio": 4, "sensor_type": "ds18b20", "raw_value": 22.5}]
        _, configs = _build_expanded_sensors(sensors)

        assert len(configs) == 1
        assert configs[0][0] == 4
        assert configs[0][1] == "ds18b20"

    def test_mixed_sensors_correct_count(self):
        """DS18B20 + SHT31 + pH → 1 + 2 + 1 = 4 SensorConfig entries."""
        sensors = [
            {"gpio": 4, "sensor_type": "ds18b20", "raw_value": 22.5},
            {"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0},
            {"gpio": 34, "sensor_type": "ph", "raw_value": 6.8},
        ]
        expanded, configs = _build_expanded_sensors(sensors)

        assert len(expanded) == 4
        assert len(configs) == 4

        # Verify all keys
        assert "4_ds18b20" in expanded
        assert "21_sht31_temp" in expanded
        assert "21_sht31_humidity" in expanded
        assert "34_ph" in expanded

    def test_raw_value_preserved_in_expanded(self):
        """Original raw_value is preserved in all expanded entries."""
        sensors = [{"gpio": 21, "sensor_type": "sht31", "raw_value": 25.5}]
        expanded, _ = _build_expanded_sensors(sensors)

        assert expanded["21_sht31_temp"]["raw_value"] == 25.5
        assert expanded["21_sht31_temp"]["base_value"] == 25.5
        assert expanded["21_sht31_humidity"]["raw_value"] == 25.5
        assert expanded["21_sht31_humidity"]["base_value"] == 25.5

    def test_gpio_stored_in_expanded_config(self):
        """GPIO number is stored inside each expanded sensor config."""
        sensors = [{"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0}]
        expanded, _ = _build_expanded_sensors(sensors)

        assert expanded["21_sht31_temp"]["gpio"] == 21
        assert expanded["21_sht31_humidity"]["gpio"] == 21


class TestSchedulerKeyCompatibility:
    """Test that expanded keys work with scheduler's key parsing logic."""

    def _parse_key_like_scheduler(self, sensor_key: str) -> tuple[int, str]:
        """Replicate scheduler._start_sensor_jobs_from_db key parsing."""
        if "_" in sensor_key and not sensor_key.isdigit():
            gpio = int(sensor_key.split("_")[0])
        else:
            gpio = int(sensor_key)
        return gpio, sensor_key

    def test_new_format_key_parsed_correctly(self):
        """Scheduler can parse '21_sht31_temp' → GPIO 21."""
        gpio, _ = self._parse_key_like_scheduler("21_sht31_temp")
        assert gpio == 21

    def test_new_format_humidity_parsed_correctly(self):
        """Scheduler can parse '21_sht31_humidity' → GPIO 21."""
        gpio, _ = self._parse_key_like_scheduler("21_sht31_humidity")
        assert gpio == 21

    def test_single_value_key_parsed_correctly(self):
        """Scheduler can parse '4_ds18b20' → GPIO 4."""
        gpio, _ = self._parse_key_like_scheduler("4_ds18b20")
        assert gpio == 4

    def test_all_expanded_keys_parseable(self):
        """All keys from a mixed expansion are parseable by scheduler."""
        sensors = [
            {"gpio": 4, "sensor_type": "ds18b20", "raw_value": 22.5},
            {"gpio": 21, "sensor_type": "sht31", "raw_value": 23.0},
            {"gpio": 34, "sensor_type": "ph", "raw_value": 6.8},
        ]
        expanded, _ = _build_expanded_sensors(sensors)

        expected_gpios = {
            "4_ds18b20": 4,
            "21_sht31_temp": 21,
            "21_sht31_humidity": 21,
            "34_ph": 34,
        }

        for key, expected_gpio in expected_gpios.items():
            gpio, _ = self._parse_key_like_scheduler(key)
            assert (
                gpio == expected_gpio
            ), f"Key '{key}' parsed to GPIO {gpio}, expected {expected_gpio}"


class TestDeleteGuardMultipleSensorsOnGpio:
    """Test that GPIO-based delete is guarded when multiple sensors share a GPIO.

    The debug endpoint DELETE /mock-esp/{esp_id}/sensors/{gpio} must NOT
    mass-delete all sensors on a shared GPIO (e.g. I2C bus on GPIO 0).
    When >1 sensor exists on the GPIO and no sensor_type is specified,
    the endpoint should return 409 Conflict.
    """

    def _should_guard(self, sensor_count_on_gpio: int, sensor_type_specified: bool) -> bool:
        """Replicate the guard logic from debug.py remove_sensor()."""
        if sensor_type_specified:
            return False  # Targeted delete — always allowed
        return sensor_count_on_gpio > 1  # Guard: refuse mass-delete

    def test_single_sensor_no_type_allowed(self):
        """1 sensor on GPIO, no sensor_type → delete allowed (no guard)."""
        assert not self._should_guard(sensor_count_on_gpio=1, sensor_type_specified=False)

    def test_multiple_sensors_no_type_guarded(self):
        """2+ sensors on GPIO, no sensor_type → 409 guard triggered."""
        assert self._should_guard(sensor_count_on_gpio=2, sensor_type_specified=False)
        assert self._should_guard(sensor_count_on_gpio=6, sensor_type_specified=False)

    def test_multiple_sensors_with_type_allowed(self):
        """2+ sensors on GPIO, sensor_type specified → targeted delete allowed."""
        assert not self._should_guard(sensor_count_on_gpio=2, sensor_type_specified=True)
        assert not self._should_guard(sensor_count_on_gpio=6, sensor_type_specified=True)

    def test_zero_sensors_no_guard(self):
        """0 sensors on GPIO → no guard (404 handled elsewhere)."""
        assert not self._should_guard(sensor_count_on_gpio=0, sensor_type_specified=False)

    def test_sht31_scenario_on_gpio0(self):
        """Real scenario: 6 I2C sensors on GPIO 0 (2x SHT31 + BMP280)."""
        # SHT31 (2 value types each) + BMP280 (2 value types) = 6 sensor_configs on GPIO 0
        assert self._should_guard(sensor_count_on_gpio=6, sensor_type_specified=False)
        # Targeted delete with sensor_type should still work
        assert not self._should_guard(sensor_count_on_gpio=6, sensor_type_specified=True)
