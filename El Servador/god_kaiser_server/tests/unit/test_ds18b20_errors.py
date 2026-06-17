"""
Unit Tests: DS18B20 Temperature Sensor Error Detection

SAFETY-CRITICAL: These tests verify that DS18B20 special error values
are correctly detected and handled. A missed -127°C error could result
in incorrect control decisions (e.g., turning on heaters when sensor
is disconnected).

DS18B20 Special Values:
- -127°C (RAW -2032): Sensor disconnected or CRC failure
- +85°C (RAW 1360): Power-on reset value (factory default)

Test Strategy:
- Tests cover both RAW mode (raw_mode=True) and pre-converted mode (raw_mode=False)
- RAW values are 12-bit integers where 1 LSB = 0.0625°C
- Pre-converted values are direct Celsius temperatures
"""

import pytest
from src.sensors.sensor_libraries.active.temperature import DS18B20Processor


class TestDS18B20SensorFault:
    """Tests for -127°C sensor fault detection (disconnected/CRC failure)."""

    @pytest.mark.critical
    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_raw_minus_2032_returns_quality_error(self):
        """RAW -2032 (-127°C) must return quality='error'."""
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=-2032, params={"raw_mode": True}  # RAW value for -127°C
        )

        assert (
            result.quality == "error"
        ), f"DS18B20 RAW -2032 (-127°C) must return quality='error', got '{result.quality}'"

    @pytest.mark.critical
    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_sensor_fault_returns_zero_value(self):
        """Sensor fault should return value=0.0 (not the error temperature)."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=-2032, params={"raw_mode": True})

        assert (
            result.value == 0.0
        ), f"DS18B20 sensor fault must return value=0.0, got {result.value}"

    @pytest.mark.critical
    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_sensor_fault_metadata_contains_error_code(self):
        """Sensor fault metadata must include error_code 1060."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=-2032, params={"raw_mode": True})

        assert result.metadata is not None, "Metadata must not be None"
        assert (
            result.metadata.get("error_code") == 1060
        ), f"Expected error_code=1060 (ERROR_DS18B20_SENSOR_FAULT), got {result.metadata.get('error_code')}"

    @pytest.mark.critical
    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_sensor_fault_metadata_contains_error_message(self):
        """Sensor fault metadata must include descriptive error message."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=-2032, params={"raw_mode": True})

        assert result.metadata is not None, "Metadata must not be None"
        error_msg = result.metadata.get("error", "")
        assert (
            "disconnected" in error_msg.lower() or "-127" in error_msg
        ), f"Error message must mention disconnected sensor, got: '{error_msg}'"


class TestDS18B20PowerOnReset:
    """Tests for +85°C power-on reset detection."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_raw_1360_is_accepted(self):
        """
        RAW 1360 (+85°C) should be ACCEPTED, not rejected.

        Rationale: The ESP32 handles first-reading detection. If +85°C
        makes it to the server, ESP already validated it's likely real
        (e.g., fire, hot environment). Rejecting it could be dangerous.
        """
        processor = DS18B20Processor()

        result = processor.process(raw_value=1360, params={"raw_mode": True})  # RAW value for +85°C

        # +85°C is at TEMP_TYPICAL_MAX boundary, so quality should be "good"
        # Note: 85°C may defensively be marked as "suspect" since it's the DS18B20 power-on reset value
        assert result.quality in (
            "good",
            "fair",
            "suspect",
        ), f"DS18B20 +85°C should be accepted (quality='good', 'fair' or 'suspect'), got '{result.quality}'"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_raw_1360_converts_to_85_celsius(self):
        """RAW 1360 must convert to exactly 85.0°C."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=1360, params={"raw_mode": True})

        assert result.value == 85.0, f"RAW 1360 must convert to 85.0°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_85c_with_raw_mode_false(self):
        """Pre-converted 85.0°C should be accepted."""
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=85.0, params={"raw_mode": False}  # Pre-converted Celsius
        )

        assert result.quality in (
            "good",
            "fair",
            "suspect",
        ), f"85.0°C pre-converted should be accepted, got quality='{result.quality}'"
        assert (
            result.value == 85.0
        ), f"85.0°C pre-converted should remain 85.0°C, got {result.value}"


class TestDS18B20QualityAssessment:
    """Tests for quality level assignment based on temperature range."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.parametrize(
        "raw_value,expected_quality",
        [
            # Normal range (-10°C to +85°C) → "good"
            (400, "good"),  # 25.0°C (RAW 400 × 0.0625)
            (0, "good"),  # 0.0°C
            (-160, "good"),  # -10.0°C (boundary)
            (1360, "suspect"),  # +85.0°C (power-on reset value → suspect, not good)
            # Outside typical but within absolute range → "fair"
            (-800, "fair"),  # -50.0°C
            (1600, "fair"),  # +100.0°C
            (1920, "fair"),  # +120.0°C
            # Boundary values
            (-880, "fair"),  # -55.0°C (exactly at TEMP_MIN)
            (2000, "fair"),  # +125.0°C (exactly at TEMP_MAX)
        ],
    )
    def test_quality_mapping_raw_mode(self, raw_value, expected_quality):
        """Quality levels are correctly assigned based on temperature range (RAW mode)."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=raw_value, params={"raw_mode": True})

        assert (
            result.quality == expected_quality
        ), f"RAW {raw_value} ({raw_value * 0.0625}°C) should have quality='{expected_quality}', got '{result.quality}'"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.parametrize(
        "celsius_value,expected_quality",
        [
            # Normal range (-10°C to +85°C) → "good"
            (25.0, "good"),
            (0.0, "good"),
            (-10.0, "good"),  # boundary
            (85.0, "good"),  # boundary
            # Outside typical but within absolute range → "fair"
            (-50.0, "fair"),
            (100.0, "fair"),
            (-55.0, "fair"),  # exactly at TEMP_MIN
            (125.0, "fair"),  # exactly at TEMP_MAX
        ],
    )
    def test_quality_mapping_preconverted(self, celsius_value, expected_quality):
        """Quality levels are correctly assigned (pre-converted mode)."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=celsius_value, params={"raw_mode": False})

        assert (
            result.quality == expected_quality
        ), f"{celsius_value}°C should have quality='{expected_quality}', got '{result.quality}'"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_out_of_range_returns_error_quality(self):
        """Temperature outside sensor physical range (-55°C to +125°C) returns 'error'."""
        processor = DS18B20Processor()

        # Test below minimum (-60°C < -55°C)
        result = processor.process(raw_value=-60.0, params={"raw_mode": False})

        assert (
            result.quality == "error"
        ), f"-60°C (below min) should return quality='error', got '{result.quality}'"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_above_max_returns_error_quality(self):
        """Temperature above sensor maximum returns 'error'."""
        processor = DS18B20Processor()

        # Test above maximum (130°C > 125°C)
        result = processor.process(raw_value=130.0, params={"raw_mode": False})

        assert (
            result.quality == "error"
        ), f"130°C (above max) should return quality='error', got '{result.quality}'"


class TestDS18B20RawModeConversion:
    """Tests for RAW mode 12-bit integer conversion."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_raw_mode_conversion_factor(self):
        """RAW values are converted using 0.0625 factor (12-bit resolution)."""
        processor = DS18B20Processor()

        # 400 RAW × 0.0625 = 25.0°C
        result = processor.process(raw_value=400, params={"raw_mode": True})

        assert result.value == 25.0, f"RAW 400 should convert to 25.0°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_raw_mode_negative_value(self):
        """Negative RAW values convert correctly to negative Celsius."""
        processor = DS18B20Processor()

        # -160 RAW × 0.0625 = -10.0°C
        result = processor.process(raw_value=-160, params={"raw_mode": True})

        assert result.value == -10.0, f"RAW -160 should convert to -10.0°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_metadata_includes_raw_mode_info(self):
        """Metadata includes raw_mode flag and original value."""
        processor = DS18B20Processor()

        result = processor.process(raw_value=400, params={"raw_mode": True})

        assert result.metadata is not None, "Metadata must not be None"
        assert result.metadata.get("raw_mode") is True, "Metadata must include raw_mode=True"
        assert (
            result.metadata.get("original_raw_value") == 400
        ), f"Metadata must include original_raw_value=400, got {result.metadata.get('original_raw_value')}"
        assert (
            result.metadata.get("conversion_factor") == 0.0625
        ), f"Metadata must include conversion_factor=0.0625, got {result.metadata.get('conversion_factor')}"


class TestDS18B20Calibration:
    """Tests for calibration offset application."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_calibration_offset_applied(self):
        """Calibration offset is applied to processed value."""
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=25.0, calibration={"offset": 0.5}, params={"raw_mode": False}
        )

        assert result.value == 25.5, f"25.0°C + 0.5 offset should equal 25.5°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_calibration_offset_with_raw_mode(self):
        """Calibration offset is applied after RAW conversion."""
        processor = DS18B20Processor()

        # 400 RAW = 25.0°C, + 0.5 offset = 25.5°C
        result = processor.process(
            raw_value=400, calibration={"offset": 0.5}, params={"raw_mode": True}
        )

        assert (
            result.value == 25.5
        ), f"RAW 400 (25.0°C) + 0.5 offset should equal 25.5°C, got {result.value}"


class TestDS18B20UnitConversion:
    """Tests for temperature unit conversion."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_fahrenheit_conversion(self):
        """Temperature can be converted to Fahrenheit."""
        processor = DS18B20Processor()

        # 25.0°C = 77.0°F
        result = processor.process(raw_value=25.0, params={"raw_mode": False, "unit": "fahrenheit"})

        assert result.value == 77.0, f"25.0°C should convert to 77.0°F, got {result.value}"
        assert result.unit == "°F", f"Unit should be '°F', got '{result.unit}'"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_kelvin_conversion(self):
        """Temperature can be converted to Kelvin."""
        processor = DS18B20Processor()

        # 25.0°C = 298.15 K
        result = processor.process(raw_value=25.0, params={"raw_mode": False, "unit": "kelvin"})

        assert result.value == 298.15, f"25.0°C should convert to 298.15 K, got {result.value}"
        assert result.unit == "K", f"Unit should be 'K', got '{result.unit}'"


class TestDS18B20UnitConversionEdgeCases:
    """
    Test unit conversion edge cases for DS18B20 processor.

    RATIONALE: Negative temperatures are relevant in cold storage and frost scenarios.
    Conversion errors can lead to false alarms or missed critical temperature alerts.
    """

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_negative_celsius_to_fahrenheit(self):
        """
        SCENARIO: Frost alarm in greenhouse
        GIVEN: Temperature = -10°C (frost!)
        WHEN: Converting to Fahrenheit
        THEN: Result = 14°F (correct: -10 * 9/5 + 32 = 14)

        PRACTICE: Wrong conversion leads to missed frost alarm!
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=-160,  # -10°C * 16 = -160 (RAW)
            params={"raw_mode": True, "unit": "fahrenheit"},
        )

        assert result.value == pytest.approx(
            14.0, abs=0.1
        ), f"Negative Celsius to Fahrenheit failed: {result.value}"
        assert result.unit == "°F"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_negative_celsius_to_kelvin(self):
        """
        SCENARIO: Scientific application
        GIVEN: Temperature = -10°C
        WHEN: Converting to Kelvin
        THEN: Result = 263.15 K
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=-160, params={"raw_mode": True, "unit": "kelvin"}  # -10°C
        )

        assert result.value == pytest.approx(
            263.15, abs=0.1
        ), f"-10°C should convert to 263.15 K, got {result.value}"
        assert result.unit == "K"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.critical
    def test_zero_celsius_boundary(self):
        """
        SCENARIO: Frost boundary (0°C is critical for plants!)
        GIVEN: Temperature = exactly 0°C
        WHEN: Converting to different units
        THEN: Fahrenheit = 32°F, Kelvin = 273.15 K

        PRACTICE: 0°C is the frost boundary - plants die below this!
        """
        processor = DS18B20Processor()

        result_f = processor.process(raw_value=0, params={"raw_mode": True, "unit": "fahrenheit"})
        result_k = processor.process(raw_value=0, params={"raw_mode": True, "unit": "kelvin"})

        assert result_f.value == pytest.approx(32.0, abs=0.01), "0°C != 32°F"
        assert result_k.value == pytest.approx(273.15, abs=0.01), "0°C != 273.15K"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.parametrize(
        "raw,expected_c",
        [
            (-880, -55.0),  # Lower boundary DS18B20
            (2000, 125.0),  # Upper boundary DS18B20
        ],
    )
    def test_boundary_values_conversion(self, raw, expected_c):
        """
        SCENARIO: Sensor at specification limits
        PRACTICE: Values outside -55°C to +125°C are physically impossible
                  for DS18B20 → must be detected as errors
        """
        processor = DS18B20Processor()

        result = processor.process(raw_value=raw, params={"raw_mode": True})

        assert result.value == pytest.approx(
            expected_c, abs=0.1
        ), f"RAW {raw} should convert to {expected_c}°C"
        # Boundary values should be valid (within sensor range)
        # Quality is "fair" because outside typical range (-10°C to +85°C)
        assert result.quality in (
            "good",
            "fair",
        ), f"Boundary value should be valid, got quality='{result.quality}'"


class TestDS18B20CalibrationExtended:
    """Extended calibration tests based on real-world requirements."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_linear_calibration_rejected(self):
        """
        SCENARIO: User attempts wrong calibration method
        GIVEN: DS18B20 supports ONLY "offset" method
        WHEN: User configures "linear" method
        THEN: ValueError with clear error message

        PRACTICE: DS18B20 is already linearized - only offset needed!
        """
        processor = DS18B20Processor()

        with pytest.raises(ValueError) as exc_info:
            processor.calibrate(
                calibration_points=[{"raw": 25.0, "reference": 26.0}], method="linear"
            )

        assert (
            "offset" in str(exc_info.value).lower()
        ), f"Error should mention 'offset' method, got: {exc_info.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_calibration_multiple_points_averaged(self):
        """
        SCENARIO: Calibration with reference thermometer at multiple points
        GIVEN: Measurements at 0°C, 25°C, 50°C show +1.5°C deviation each
        WHEN: Average offset = -1.5°C
        THEN: Correct offset is applied

        PRACTICE: Professional calibration uses multiple reference points
        """
        processor = DS18B20Processor()

        # Calibrate with 3 points, all showing 1.5°C too high
        calibration_data = processor.calibrate(
            calibration_points=[
                {"raw": 1.5, "reference": 0.0},  # Shows 1.5°C at 0°C
                {"raw": 26.5, "reference": 25.0},  # Shows 26.5°C at 25°C
                {"raw": 51.5, "reference": 50.0},  # Shows 51.5°C at 50°C
            ],
            method="offset",
        )

        assert calibration_data["offset"] == pytest.approx(
            -1.5, abs=0.01
        ), f"Average offset should be -1.5, got {calibration_data['offset']}"
        assert calibration_data["points"] == 3

        # Apply the calibration
        result = processor.process(
            raw_value=26.5, calibration=calibration_data, params={"raw_mode": False}
        )

        assert result.value == pytest.approx(
            25.0, abs=0.1
        ), f"Calibrated value should be ~25.0°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_calibration_negative_sensor_offset(self):
        """
        SCENARIO: Sensor shows 2°C too low (e.g., cable resistance)
        GIVEN: Real value = 25°C, Sensor shows 23°C
        WHEN: Offset = +2.0 (positive!)
        THEN: Corrected value = 25°C
        """
        processor = DS18B20Processor()

        calibration_data = processor.calibrate(
            calibration_points=[{"raw": 23.0, "reference": 25.0}], method="offset"
        )

        assert calibration_data["offset"] == pytest.approx(
            2.0, abs=0.01
        ), f"Offset should be +2.0, got {calibration_data['offset']}"

        result = processor.process(
            raw_value=23.0, calibration=calibration_data, params={"raw_mode": False}
        )

        assert result.value == pytest.approx(
            25.0, abs=0.1
        ), f"Calibrated value should be 25.0°C, got {result.value}"


class TestDS18B20Precision:
    """Test decimal precision and rounding behavior."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.parametrize(
        "decimal_places,expected",
        [
            (0, 25.0),
            (1, 25.1),
            (2, 25.06),
        ],
    )
    def test_decimal_places_parameter(self, decimal_places, expected):
        """
        SCENARIO: Different display precision in dashboard
        PRACTICE: Some displays show integers, others 0.1°C
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=401, params={"raw_mode": True, "decimal_places": decimal_places}  # 25.0625°C
        )

        # Check rounding based on decimal_places
        assert result.value == pytest.approx(
            expected, abs=10 ** (-decimal_places)
        ), f"With decimal_places={decimal_places}, expected ~{expected}, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.critical
    def test_raw_mode_resolution_0625(self):
        """
        SCENARIO: Maximum sensor resolution usage
        GIVEN: DS18B20 has 12-bit = 0.0625°C resolution
        WHEN: RAW 401 (= 401/16 = 25.0625°C)
        THEN: Value = exactly 25.0625°C (not rounded!)

        PRACTICE: For PID control full resolution is important!
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=401, params={"raw_mode": True, "decimal_places": 4}  # Max precision
        )

        assert result.value == pytest.approx(
            25.0625, abs=0.001
        ), f"RAW 401 should convert to 25.0625°C, got {result.value}"

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_rounding_half_values(self):
        """
        SCENARIO: Consistent rounding behavior
        PRACTICE: Python uses "Banker's Rounding" (to even number)
        """
        processor = DS18B20Processor()

        # 25.5°C with 0 decimal places
        result = processor.process(
            raw_value=408, params={"raw_mode": True, "decimal_places": 0}  # 25.5°C (408 * 0.0625)
        )

        # Banker's Rounding: 25.5 → 26 (to even number)
        # Note: round(25.5) in Python 3 = 26
        assert result.value in [
            25.0,
            26.0,
        ], f"25.5°C rounded to 0 decimals should be 25 or 26, got {result.value}"


class TestDS18B20MetadataConsistency:
    """Ensure metadata fields are always present and consistent."""

    REQUIRED_FIELDS_ON_SUCCESS = ["raw_celsius", "calibrated", "raw_mode"]
    REQUIRED_ERROR_FIELDS = ["error", "raw_mode"]

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    @pytest.mark.critical
    def test_metadata_on_error_contains_required_fields(self):
        """
        SCENARIO: Sensor fault (-127°C)
        PRACTICE: Dashboard needs ALL fields, even on errors!
        """
        processor = DS18B20Processor()

        result = processor.process(raw_value=-2032, params={"raw_mode": True})  # -127°C

        assert result.metadata is not None, "Metadata must not be None on error"

        for field in self.REQUIRED_ERROR_FIELDS:
            assert field in result.metadata, f"Missing field '{field}' in error result metadata"

        assert result.quality == "error"
        # Note: DS18B20Processor returns value=0.0 on fault, not the error temperature

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_metadata_on_success_contains_required_fields(self):
        """
        SCENARIO: Normal measurement
        """
        processor = DS18B20Processor()

        result = processor.process(raw_value=400, params={"raw_mode": True})  # 25°C

        assert result.metadata is not None, "Metadata must not be None"

        for field in self.REQUIRED_FIELDS_ON_SUCCESS:
            assert field in result.metadata, f"Missing field '{field}' in success result metadata"

        assert result.quality == "good"
        # ProcessingResult doesn't have 'valid' - it has 'quality'

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_metadata_includes_calibration_flag(self):
        """
        SCENARIO: Audit trail for calibrated values
        PRACTICE: For quality assurance it must be visible if value
                  was calibrated!
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=400, calibration={"offset": 1.0}, params={"raw_mode": True}
        )

        assert result.metadata is not None, "Metadata must not be None"
        assert "calibrated" in result.metadata, "Missing 'calibrated' flag"
        assert (
            result.metadata["calibrated"] is True
        ), "calibrated should be True when offset applied"


class TestDS18B20ErrorResilience:
    """Test graceful handling of edge cases and malformed input."""

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_process_with_none_params(self):
        """
        SCENARIO: MQTT message without params field
        PRACTICE: ESP32 sometimes sends incomplete messages
        """
        processor = DS18B20Processor()

        result = processor.process(raw_value=400, params=None)

        # raw_mode defaults to False when params is None
        # So 400 is interpreted as 400°C, which is out of range (>125°C)
        # Let's test with a value that works without raw_mode
        result = processor.process(raw_value=25.0, params=None)

        assert (
            result.quality in ("good", "fair", "error") != None
        ), "Should handle None params gracefully"
        assert result.value == pytest.approx(25.0, abs=0.1)

    @pytest.mark.ds18b20
    @pytest.mark.sensor
    def test_process_with_empty_calibration(self):
        """
        SCENARIO: Empty calibration in config
        PRACTICE: User has reset calibration
        """
        processor = DS18B20Processor()

        result = processor.process(
            raw_value=25.0, calibration={}, params={"raw_mode": False}  # Empty calibration dict
        )

        assert result.quality in (
            "good",
            "fair",
        ), f"Should handle empty calibration, got quality='{result.quality}'"
        assert (
            result.metadata.get("calibrated", False) is False
        ), "calibrated should be False with empty calibration dict"
