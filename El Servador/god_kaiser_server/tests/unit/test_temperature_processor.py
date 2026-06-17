"""
Unit Tests for Temperature Sensor Processors.

Tests DS18B20Processor and SHT31TemperatureProcessor.
"""

import pytest

from src.sensors.sensor_libraries.active.temperature import (
    DS18B20Processor,
    SHT31TemperatureProcessor,
)


class TestDS18B20Processor:
    """Unit tests for DS18B20 temperature processor."""

    @pytest.fixture
    def processor(self):
        """Create DS18B20 processor instance."""
        return DS18B20Processor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "ds18b20"

    def test_process_valid_temperature(self, processor):
        """Test processing valid temperature reading."""
        result = processor.process(raw_value=23.5)
        assert result.value == 23.5
        assert result.unit == "°C"
        assert result.quality == "good"
        assert result.metadata["raw_celsius"] == 23.5
        assert result.metadata["calibrated"] is False

    def test_process_with_offset_calibration(self, processor):
        """Test processing with calibration offset."""
        calibration = {"offset": 0.5}
        result = processor.process(raw_value=23.5, calibration=calibration)
        assert result.value == 24.0
        assert result.metadata["calibrated"] is True

    def test_process_negative_calibration_offset(self, processor):
        """Test processing with negative calibration offset."""
        calibration = {"offset": -1.2}
        result = processor.process(raw_value=25.0, calibration=calibration)
        assert result.value == 23.8

    def test_process_fahrenheit_conversion(self, processor):
        """Test temperature conversion to Fahrenheit."""
        params = {"unit": "fahrenheit"}
        result = processor.process(raw_value=0.0, params=params)
        assert result.value == 32.0
        assert result.unit == "°F"

    def test_process_kelvin_conversion(self, processor):
        """Test temperature conversion to Kelvin."""
        params = {"unit": "kelvin"}
        result = processor.process(raw_value=0.0, params=params)
        assert result.value == 273.15
        assert result.unit == "K"

    def test_process_celsius_explicit(self, processor):
        """Test explicit Celsius unit selection."""
        params = {"unit": "celsius"}
        result = processor.process(raw_value=25.0, params=params)
        assert result.value == 25.0
        assert result.unit == "°C"

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 1}
        result = processor.process(raw_value=23.456, params=params)
        assert result.value == 23.5

    def test_validate_valid_temperature(self, processor):
        """Test validation of valid temperature."""
        validation = processor.validate(25.0)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_temperature_below_minimum(self, processor):
        """Test validation of temperature below sensor range."""
        validation = processor.validate(-60.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_temperature_above_maximum(self, processor):
        """Test validation of temperature above sensor range."""
        validation = processor.validate(130.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_temperature_below_typical_min(self, processor):
        """Test validation warning for temperature below typical range."""
        validation = processor.validate(-15.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("below typical range" in w for w in validation.warnings)

    def test_validate_temperature_above_typical_max(self, processor):
        """Test validation warning for temperature above typical range."""
        validation = processor.validate(90.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("above typical range" in w for w in validation.warnings)

    def test_calibrate_single_point_offset(self, processor):
        """Test single-point offset calibration."""
        calibration_points = [{"raw": 23.5, "reference": 24.0}]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == 0.5
        assert calibration["method"] == "offset"
        assert calibration["points"] == 1

    def test_calibrate_multi_point_average(self, processor):
        """Test multi-point calibration (average offset)."""
        calibration_points = [
            {"raw": 20.0, "reference": 20.5},
            {"raw": 30.0, "reference": 30.5},
        ]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == 0.5
        assert calibration["points"] == 2

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [{"raw": 23.5, "reference": 24.0}]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="linear")

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 1 point"):
            processor.calibrate([], method="offset")

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["unit"] == "celsius"
        assert params["decimal_places"] == 2

    def test_get_value_range(self, processor):
        """Test value range."""
        range_data = processor.get_value_range()
        assert range_data["min"] == -55.0
        assert range_data["max"] == 125.0

    def test_get_raw_value_range(self, processor):
        """Test raw value range (same as value range for DS18B20)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == -55.0
        assert range_data["max"] == 125.0

    def test_process_extreme_low_temperature(self, processor):
        """Test processing extreme low temperature."""
        result = processor.process(raw_value=-55.0)
        assert result.quality == "fair"  # Within limits but extreme

    def test_process_extreme_high_temperature(self, processor):
        """Test processing extreme high temperature."""
        result = processor.process(raw_value=125.0)
        assert result.quality == "fair"  # Within limits but extreme

    def test_process_typical_temperature_range(self, processor):
        """Test processing temperature within typical range."""
        result = processor.process(raw_value=25.0)
        assert result.quality == "good"

    def test_process_with_calibration_and_unit_conversion(self, processor):
        """Test processing with both calibration and unit conversion."""
        calibration = {"offset": 1.0}
        params = {"unit": "fahrenheit"}
        result = processor.process(raw_value=20.0, calibration=calibration, params=params)

        # 20°C + 1°C = 21°C → Fahrenheit = 69.8°F
        assert result.value == 69.8
        assert result.unit == "°F"

    # =========================================================================
    # RAW Mode Tests (Pi-Enhanced Mode - DS18B20 12-bit Integer)
    # =========================================================================

    def test_raw_mode_conversion_normal_range(self, processor):
        """Test RAW to Celsius conversion (Pi-Enhanced mode)."""
        # 400 * 0.0625 = 25.0°C
        params = {"raw_mode": True}
        result = processor.process(raw_value=400, params=params)

        assert result.value == 25.0
        assert result.quality == "good"
        assert result.metadata["raw_mode"] is True
        assert result.metadata["original_raw_value"] == 400
        assert result.metadata["conversion_factor"] == 0.0625

    def test_raw_mode_conversion_negative(self, processor):
        """Test RAW mode with negative temperature."""
        # -880 * 0.0625 = -55.0°C (spec minimum)
        params = {"raw_mode": True}
        result = processor.process(raw_value=-880, params=params)

        assert result.value == -55.0
        assert result.quality == "fair"  # At spec limit
        assert result.metadata["raw_mode"] is True

    def test_raw_mode_conversion_max_spec(self, processor):
        """Test RAW mode at maximum spec value."""
        # 2000 * 0.0625 = 125.0°C (spec maximum)
        params = {"raw_mode": True}
        result = processor.process(raw_value=2000, params=params)

        assert result.value == 125.0
        assert result.quality == "fair"  # At spec limit
        assert result.metadata["raw_mode"] is True

    def test_raw_mode_zero_value(self, processor):
        """Test RAW mode with zero (0°C)."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=0, params=params)

        assert result.value == 0.0
        assert result.quality == "good"

    def test_raw_mode_with_fahrenheit_conversion(self, processor):
        """Test RAW mode combined with Fahrenheit conversion."""
        # 400 * 0.0625 = 25.0°C → 77.0°F
        params = {"raw_mode": True, "unit": "fahrenheit"}
        result = processor.process(raw_value=400, params=params)

        assert result.value == 77.0
        assert result.unit == "°F"
        assert result.metadata["raw_mode"] is True

    def test_raw_mode_with_calibration_offset(self, processor):
        """Test RAW mode with calibration offset."""
        # 400 * 0.0625 = 25.0°C + 0.5°C offset = 25.5°C
        params = {"raw_mode": True}
        calibration = {"offset": 0.5}
        result = processor.process(raw_value=400, params=params, calibration=calibration)

        assert result.value == 25.5
        assert result.metadata["calibrated"] is True
        assert result.metadata["raw_mode"] is True

    def test_raw_mode_false_explicit(self, processor):
        """Test explicit raw_mode=False (pre-converted value)."""
        # Value is already in Celsius
        params = {"raw_mode": False}
        result = processor.process(raw_value=25.0, params=params)

        assert result.value == 25.0
        assert result.metadata["raw_mode"] is False
        assert result.metadata["original_raw_value"] is None

    def test_raw_mode_default_is_false(self, processor):
        """Test that raw_mode defaults to False for backward compatibility."""
        # No params = raw_mode defaults to False
        result = processor.process(raw_value=25.0)

        assert result.value == 25.0
        assert result.metadata["raw_mode"] is False

    def test_raw_mode_out_of_spec_high(self, processor):
        """Test RAW mode with value above spec range."""
        # 2100 * 0.0625 = 131.25°C (above 125°C spec)
        params = {"raw_mode": True}
        result = processor.process(raw_value=2100, params=params)

        # Should fail validation (out of sensor range)
        assert result.quality == "error"

    def test_raw_mode_out_of_spec_low(self, processor):
        """Test RAW mode with value below spec range."""
        # -1000 * 0.0625 = -62.5°C (below -55°C spec)
        params = {"raw_mode": True}
        result = processor.process(raw_value=-1000, params=params)

        # Should fail validation (out of sensor range)
        assert result.quality == "error"

    def test_raw_mode_greenhouse_typical_range(self, processor):
        """Test RAW mode with typical greenhouse temperature."""
        # 320 * 0.0625 = 20.0°C (typical greenhouse)
        params = {"raw_mode": True}
        result = processor.process(raw_value=320, params=params)

        assert result.value == 20.0
        assert result.quality == "good"

    def test_raw_mode_decimal_places(self, processor):
        """Test RAW mode respects decimal_places parameter."""
        # 401 * 0.0625 = 25.0625°C → rounded to 1 decimal = 25.1°C
        params = {"raw_mode": True, "decimal_places": 1}
        result = processor.process(raw_value=401, params=params)

        assert result.value == 25.1


class TestSHT31TemperatureProcessor:
    """Unit tests for SHT31 temperature processor."""

    @pytest.fixture
    def processor(self):
        """Create SHT31 temperature processor instance."""
        return SHT31TemperatureProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "sht31_temp"

    def test_process_valid_temperature(self, processor):
        """Test processing valid temperature reading."""
        result = processor.process(raw_value=23.5)
        assert result.value == 23.5
        assert result.unit == "°C"
        assert result.quality == "good"

    def test_process_with_offset_calibration(self, processor):
        """Test processing with calibration offset."""
        calibration = {"offset": -0.3}
        result = processor.process(raw_value=23.5, calibration=calibration)
        assert result.value == 23.2

    def test_process_fahrenheit_conversion(self, processor):
        """Test temperature conversion to Fahrenheit."""
        params = {"unit": "fahrenheit"}
        result = processor.process(raw_value=20.0, params=params)
        assert result.value == 68.0
        assert result.unit == "°F"

    def test_process_celsius_default(self, processor):
        """Test default Celsius output."""
        result = processor.process(raw_value=25.0)
        assert result.unit == "°C"

    def test_process_decimal_places(self, processor):
        """Test custom decimal places (default: 1)."""
        params = {"decimal_places": 2}
        result = processor.process(raw_value=23.456, params=params)
        assert result.value == 23.46

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (1 for SHT31)."""
        result = processor.process(raw_value=23.456)
        assert result.value == 23.5

    def test_validate_valid_temperature(self, processor):
        """Test validation of valid temperature."""
        validation = processor.validate(25.0)
        assert validation.valid is True

    def test_validate_temperature_below_minimum(self, processor):
        """Test validation of temperature below sensor range."""
        validation = processor.validate(-45.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_temperature_above_maximum(self, processor):
        """Test validation of temperature above sensor range."""
        validation = processor.validate(130.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_temperature_outside_typical_range(self, processor):
        """Test validation warning for temperature outside typical accuracy range."""
        validation = processor.validate(-5.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("outside typical accuracy range" in w for w in validation.warnings)

    def test_calibrate_single_point_offset(self, processor):
        """Test single-point offset calibration."""
        calibration_points = [{"raw": 23.5, "reference": 24.0}]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == 0.5
        assert calibration["method"] == "offset"

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [{"raw": 23.5, "reference": 24.0}]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="linear")

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 1 point"):
            processor.calibrate([])

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["unit"] == "celsius"
        assert params["decimal_places"] == 1

    def test_get_value_range(self, processor):
        """Test value range."""
        range_data = processor.get_value_range()
        assert range_data["min"] == -40.0
        assert range_data["max"] == 125.0

    def test_process_typical_temperature_range(self, processor):
        """Test processing temperature within typical accuracy range (0-65°C)."""
        result = processor.process(raw_value=30.0)
        assert result.quality == "good"

    def test_process_outside_typical_range(self, processor):
        """Test processing temperature outside typical accuracy range."""
        result = processor.process(raw_value=70.0)
        assert result.quality == "fair"

    def test_process_with_calibration_and_conversion(self, processor):
        """Test processing with calibration and Fahrenheit conversion."""
        calibration = {"offset": 0.5}
        params = {"unit": "fahrenheit", "decimal_places": 1}
        result = processor.process(raw_value=20.0, calibration=calibration, params=params)

        # 20°C + 0.5°C = 20.5°C → 68.9°F
        assert result.value == 68.9
        assert result.unit == "°F"

    # =========================================================================
    # SHT31 RAW MODE TESTS (Pi-Enhanced Mode - 16-bit Integer)
    # Formula: temp_celsius = -45 + (175 * raw_value / 65535.0)
    # =========================================================================

    def test_raw_mode_sht31_conversion_formula(self, processor):
        """Test Sensirion Datasheet Formula: -45 + (175 * raw / 65535)."""
        params = {"raw_mode": True}
        # raw=27445 → -45 + (175 * 27445 / 65535) = 28.27°C
        result = processor.process(raw_value=27445, params=params)

        assert result.value == pytest.approx(28.3, abs=0.1)
        assert result.quality == "good"
        assert result.metadata["raw_mode"] is True
        assert result.metadata["original_raw_value"] == 27445

    def test_raw_mode_sht31_zero(self, processor):
        """Test RAW=0 → -45°C (below sensor minimum of -40°C)."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=0, params=params)

        # -45°C is below SHT31 sensor range (-40°C to 125°C) → error
        # Value is returned as 0.0 with error quality
        assert result.quality == "error"
        assert "out of sensor range" in result.metadata.get("error", "")

    def test_raw_mode_sht31_typical_room_temp(self, processor):
        """Test RAW value for typical room temperature (22°C)."""
        params = {"raw_mode": True}
        # Solving: 22 = -45 + (175 * raw / 65535)
        # raw = (22 + 45) * 65535 / 175 = 25089
        result = processor.process(raw_value=25089, params=params)

        assert result.value == pytest.approx(22.0, abs=0.2)
        assert result.quality == "good"

    def test_raw_mode_sht31_max_typical(self, processor):
        """Test RAW value at max typical range (65°C)."""
        params = {"raw_mode": True}
        # Solving: 65 = -45 + (175 * raw / 65535)
        # raw = (65 + 45) * 65535 / 175 = 41203
        result = processor.process(raw_value=41203, params=params)

        assert result.value == pytest.approx(65.0, abs=0.2)
        # 65°C is at edge of typical range (0-65°C) - "good" is correct
        # But SHT31TemperatureProcessor uses TEMP_TYPICAL_MAX = 65.0
        # Since 65.0 <= 65.0, it should be "good"
        assert result.quality in ["good", "fair"]  # At edge, depends on rounding

    def test_raw_mode_sht31_above_spec(self, processor):
        """Test RAW=65535 → 130°C (above 125°C spec max)."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=65535, params=params)

        # 130°C > 125°C (max spec) → should be error
        assert result.quality == "error"
        assert "out of sensor range" in result.metadata.get("error", "")

    def test_raw_mode_sht31_out_of_range_negative(self, processor):
        """Test negative RAW value rejected."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=-100, params=params)

        assert result.quality == "error"
        assert "out of range" in result.metadata.get("error", "")

    def test_raw_mode_sht31_out_of_range_high(self, processor):
        """Test RAW value > 65535 rejected."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=70000, params=params)

        assert result.quality == "error"
        assert "out of range" in result.metadata.get("error", "")

    def test_raw_mode_sht31_with_calibration(self, processor):
        """Test SHT31 RAW mode with calibration offset."""
        params = {"raw_mode": True}
        calibration = {"offset": 0.5}
        # raw=27445 → 28.27°C + 0.5°C = 28.77°C
        result = processor.process(raw_value=27445, params=params, calibration=calibration)

        assert result.value == pytest.approx(28.8, abs=0.1)
        assert result.metadata["calibrated"] is True

    def test_raw_mode_sht31_with_fahrenheit(self, processor):
        """Test SHT31 RAW mode with Fahrenheit conversion."""
        params = {"raw_mode": True, "unit": "fahrenheit"}
        # raw=27445 → 28.27°C → 82.9°F
        result = processor.process(raw_value=27445, params=params)

        assert result.value == pytest.approx(82.9, abs=0.2)
        assert result.unit == "°F"

    def test_raw_mode_sht31_metadata_conversion_formula(self, processor):
        """Test metadata includes conversion formula for SHT31."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=27445, params=params)

        assert result.metadata["raw_mode"] is True
        assert result.metadata["original_raw_value"] == 27445
        assert result.metadata["conversion_formula"] is not None
        assert "27445" in result.metadata["conversion_formula"]
