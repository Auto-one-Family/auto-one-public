"""
Unit Tests for BMP280 Sensor Processors.

Tests BMP280PressureProcessor and BMP280TemperatureProcessor.
"""

import pytest

from src.sensors.sensor_libraries.active.pressure import (
    BMP280PressureProcessor,
    BMP280TemperatureProcessor,
)


class TestBMP280PressureProcessor:
    """Unit tests for BMP280 pressure processor."""

    @pytest.fixture
    def processor(self):
        """Create BMP280 pressure processor instance."""
        return BMP280PressureProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "bmp280_pressure"

    def test_process_valid_pressure(self, processor):
        """Test processing valid pressure reading."""
        result = processor.process(raw_value=1013.25)
        assert result.value == 1013.2  # Rounded to 1 decimal place
        assert result.unit == "hPa"
        assert result.quality == "good"
        assert result.metadata["raw_hpa"] == 1013.25
        assert result.metadata["calibrated"] is False

    def test_process_with_offset_calibration(self, processor):
        """Test processing with offset calibration."""
        calibration = {"offset": 2.0}
        result = processor.process(raw_value=1013.25, calibration=calibration)

        assert result.value == 1015.2  # 1013.25 + 2.0, rounded to 1 decimal
        assert result.metadata["calibrated"] is True

    def test_process_unit_conversion_pa(self, processor):
        """Test unit conversion to Pascal."""
        params = {"unit": "pa"}
        result = processor.process(raw_value=1013.25, params=params)

        # 1013.25 hPa * 100 = 101325 Pa
        assert result.value == 101325.0
        assert result.unit == "Pa"

    def test_process_unit_conversion_mmhg(self, processor):
        """Test unit conversion to mmHg."""
        params = {"unit": "mmhg"}
        result = processor.process(raw_value=1013.25, params=params)

        # 1013.25 hPa * 0.750062 ≈ 760.0 mmHg
        expected = 1013.25 * 0.750062
        assert result.value == pytest.approx(expected, rel=0.01)
        assert result.unit == "mmHg"

    def test_process_unit_conversion_inhg(self, processor):
        """Test unit conversion to inHg."""
        params = {"unit": "inhg"}
        result = processor.process(raw_value=1013.25, params=params)

        # 1013.25 hPa * 0.02953 ≈ 29.92 inHg
        expected = 1013.25 * 0.02953
        assert result.value == pytest.approx(expected, rel=0.01)
        assert result.unit == "inHg"

    def test_process_sea_level_correction(self, processor):
        """Test sea-level pressure correction at altitude."""
        # At 500m altitude, pressure ~950 hPa
        # Sea-level corrected: ~1013 hPa
        params = {"altitude": 500.0}
        result = processor.process(raw_value=950.0, params=params)

        # Should increase pressure (sea level higher than station)
        assert result.value > 950.0

    def test_process_sea_level_correction_formula(self, processor):
        """Test sea-level correction formula accuracy."""
        # Formula: P_sealevel = P / (1 - alt/44330)^5.255
        altitude = 500.0
        pressure_measured = 950.0

        params = {"altitude": altitude}
        result = processor.process(raw_value=pressure_measured, params=params)

        # Manual calculation
        factor = 1 - (altitude / 44330.0)
        expected_pressure = pressure_measured / (factor**5.255)

        assert result.value == pytest.approx(expected_pressure, rel=0.01)

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 0}
        result = processor.process(raw_value=1013.789, params=params)

        # Should round to integer
        assert result.value == 1014

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (1 for pressure)."""
        result = processor.process(raw_value=1013.789)
        assert result.value == 1013.8

    def test_validate_valid_pressure(self, processor):
        """Test validation of valid pressure."""
        validation = processor.validate(1013.25)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_pressure_below_minimum(self, processor):
        """Test validation of pressure below sensor range."""
        validation = processor.validate(250.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_pressure_above_maximum(self, processor):
        """Test validation of pressure above sensor range."""
        validation = processor.validate(1200.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_warning_low_pressure(self, processor):
        """Test validation warning for low pressure (<950 hPa)."""
        validation = processor.validate(900.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("below typical range" in w for w in validation.warnings)

    def test_validate_warning_high_pressure(self, processor):
        """Test validation warning for high pressure (>1050 hPa)."""
        validation = processor.validate(1070.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("above typical range" in w for w in validation.warnings)

    def test_calibrate_single_point_offset(self, processor):
        """Test single-point offset calibration."""
        calibration_points = [{"raw": 1013.25, "reference": 1015.0}]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == 1.75  # 1015 - 1013.25
        assert calibration["method"] == "offset"
        assert calibration["points"] == 1

    def test_calibrate_multi_point_average(self, processor):
        """Test multi-point calibration (average offset)."""
        calibration_points = [
            {"raw": 1013.0, "reference": 1015.0},  # +2.0
            {"raw": 1010.0, "reference": 1013.0},  # +3.0
        ]
        calibration = processor.calibrate(calibration_points, method="offset")

        # Average offset: (2.0 + 3.0) / 2 = 2.5
        assert calibration["offset"] == 2.5
        assert calibration["points"] == 2

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [{"raw": 1013.25, "reference": 1015.0}]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="linear")

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 1 point"):
            processor.calibrate([], method="offset")

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["unit"] == "hpa"
        assert params["altitude"] is None
        assert params["decimal_places"] == 1

    def test_get_value_range(self, processor):
        """Test value range (300-1100 hPa)."""
        range_data = processor.get_value_range()
        assert range_data["min"] == 300.0
        assert range_data["max"] == 1100.0

    def test_get_raw_value_range(self, processor):
        """Test raw value range (same as value range for digital sensor)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == 300.0
        assert range_data["max"] == 1100.0

    def test_process_quality_good(self, processor):
        """Test quality assessment for typical pressure (950-1050 hPa)."""
        result = processor.process(raw_value=1013.25)
        assert result.quality == "good"

    def test_process_quality_fair_low(self, processor):
        """Test quality assessment for low but valid pressure."""
        result = processor.process(raw_value=900.0)
        assert result.quality == "fair"

    def test_process_quality_fair_high(self, processor):
        """Test quality assessment for high but valid pressure."""
        result = processor.process(raw_value=1070.0)
        assert result.quality == "fair"

    def test_process_metadata_raw_hpa(self, processor):
        """Test that raw hPa is included in metadata."""
        result = processor.process(raw_value=1013.25)
        assert "raw_hpa" in result.metadata
        assert result.metadata["raw_hpa"] == 1013.25

    def test_process_invalid_pressure_returns_error_quality(self, processor):
        """Test that invalid pressure returns error quality."""
        result = processor.process(raw_value=1200.0)  # Above max
        assert result.quality == "error"
        assert "error" in result.metadata


class TestBMP280TemperatureProcessor:
    """Unit tests for BMP280 temperature processor."""

    @pytest.fixture
    def processor(self):
        """Create BMP280 temperature processor instance."""
        return BMP280TemperatureProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "bmp280_temp"

    def test_process_valid_temperature(self, processor):
        """Test processing valid temperature reading."""
        result = processor.process(raw_value=23.5)
        assert result.value == 23.5
        assert result.unit == "°C"
        assert result.quality == "good"
        assert result.metadata["raw_celsius"] == 23.5
        assert result.metadata["calibrated"] is False

    def test_process_with_offset_calibration(self, processor):
        """Test processing with offset calibration."""
        calibration = {"offset": 0.5}
        result = processor.process(raw_value=23.5, calibration=calibration)

        assert result.value == 24.0  # 23.5 + 0.5
        assert result.metadata["calibrated"] is True

    def test_process_unit_conversion_fahrenheit(self, processor):
        """Test unit conversion to Fahrenheit."""
        params = {"unit": "fahrenheit"}
        result = processor.process(raw_value=0.0, params=params)

        # 0°C = 32°F
        assert result.value == 32.0
        assert result.unit == "°F"

    def test_process_unit_conversion_kelvin(self, processor):
        """Test unit conversion to Kelvin."""
        params = {"unit": "kelvin"}
        result = processor.process(raw_value=0.0, params=params)

        # 0°C = 273.15 K
        assert result.value == 273.15
        assert result.unit == "K"

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 0}
        result = processor.process(raw_value=23.789, params=params)

        # Should round to integer
        assert result.value == 24

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (2 for temperature)."""
        result = processor.process(raw_value=23.789)
        assert result.value == 23.79

    def test_validate_valid_temperature(self, processor):
        """Test validation of valid temperature."""
        validation = processor.validate(23.5)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_temperature_below_minimum(self, processor):
        """Test validation of temperature below sensor range."""
        validation = processor.validate(-50.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_temperature_above_maximum(self, processor):
        """Test validation of temperature above sensor range."""
        validation = processor.validate(100.0)
        assert validation.valid is False
        assert "out of sensor range" in validation.error

    def test_validate_warning_low_temperature(self, processor):
        """Test validation warning for low temperature (<-20°C)."""
        validation = processor.validate(-30.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("below typical range" in w for w in validation.warnings)

    def test_calibrate_single_point_offset(self, processor):
        """Test single-point offset calibration."""
        calibration_points = [{"raw": 23.5, "reference": 24.0}]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == 0.5  # 24.0 - 23.5
        assert calibration["method"] == "offset"
        assert calibration["points"] == 1

    def test_calibrate_multi_point_average(self, processor):
        """Test multi-point calibration (average offset)."""
        calibration_points = [
            {"raw": 23.0, "reference": 24.0},  # +1.0
            {"raw": 19.0, "reference": 20.0},  # +1.0
        ]
        calibration = processor.calibrate(calibration_points, method="offset")

        # Average offset: (1.0 + 1.0) / 2 = 1.0
        assert calibration["offset"] == 1.0
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
        """Test value range (-40°C to +85°C)."""
        range_data = processor.get_value_range()
        assert range_data["min"] == -40.0
        assert range_data["max"] == 85.0

    def test_get_raw_value_range(self, processor):
        """Test raw value range (same as value range for digital sensor)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == -40.0
        assert range_data["max"] == 85.0

    def test_process_quality_good(self, processor):
        """Test quality assessment for typical temperature (-20°C to 85°C)."""
        result = processor.process(raw_value=23.5)
        assert result.quality == "good"

    def test_process_quality_fair_low(self, processor):
        """Test quality assessment for low but valid temperature."""
        result = processor.process(raw_value=-30.0)
        assert result.quality == "fair"

    def test_process_metadata_raw_celsius(self, processor):
        """Test that raw Celsius is included in metadata."""
        result = processor.process(raw_value=23.5)
        assert "raw_celsius" in result.metadata
        assert result.metadata["raw_celsius"] == 23.5

    def test_process_invalid_temperature_returns_error_quality(self, processor):
        """Test that invalid temperature returns error quality."""
        result = processor.process(raw_value=100.0)  # Above max
        assert result.quality == "error"
        assert "error" in result.metadata
