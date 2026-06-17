"""
Unit Tests for EC Sensor Processor.

Tests ECSensorProcessor for analog electrical conductivity sensors.
"""

import pytest

from src.sensors.sensor_libraries.active.ec_sensor import (
    ECSensorProcessor,
)


class TestECSensorProcessor:
    """Unit tests for EC sensor processor."""

    @pytest.fixture
    def processor(self):
        """Create EC sensor processor instance."""
        return ECSensorProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "ec"

    def test_process_valid_ec(self, processor):
        """Test processing valid EC reading without calibration."""
        # Default mapping: 0-3.3V → 0-20000 µS/cm (slope ~6060)
        # ADC 1800 → 1.45V → ~8787 µS/cm
        result = processor.process(raw_value=1800)
        assert result.unit == "µS/cm"
        assert result.quality in ["good", "fair"]
        assert result.metadata["raw_value"] == 1800
        assert result.metadata["calibrated"] is False

    def test_process_with_calibration(self, processor):
        """Test processing with two-point calibration."""
        # Calibration: slope=5000, offset=-2000
        # ADC 1800 → 1.45V → EC = 5000*1.45 - 2000 = 5250 µS/cm
        calibration = {"slope": 5000, "offset": -2000}
        result = processor.process(raw_value=1800, calibration=calibration)

        expected_voltage = (1800 / 4095) * 3.3
        expected_ec = 5000 * expected_voltage - 2000
        assert result.value == pytest.approx(expected_ec, rel=0.01)
        assert result.metadata["calibrated"] is True

    def test_process_temperature_compensation_at_reference_temp(self, processor):
        """Test that temperature compensation at 25°C doesn't change value."""
        calibration = {"slope": 5000, "offset": -2000}
        params = {"temperature_compensation": 25.0}

        result = processor.process(raw_value=1800, calibration=calibration, params=params)
        result_no_temp = processor.process(raw_value=1800, calibration=calibration)

        # At reference temp, compensation factor = 1, no change
        assert result.value == pytest.approx(result_no_temp.value, rel=0.01)

    def test_process_temperature_compensation_higher_temp(self, processor):
        """Test temperature compensation at higher temperature (30°C)."""
        calibration = {"slope": 5000, "offset": -2000}
        params = {"temperature_compensation": 30.0}

        result_with_temp = processor.process(raw_value=1800, calibration=calibration, params=params)
        result_no_temp = processor.process(raw_value=1800, calibration=calibration)

        # At 30°C, temp_factor = 1 + 0.02 * (30 - 25) = 1.1
        # EC_compensated = EC_raw / 1.1 (should be lower)
        assert result_with_temp.value < result_no_temp.value

    def test_process_temperature_compensation_lower_temp(self, processor):
        """Test temperature compensation at lower temperature (15°C)."""
        calibration = {"slope": 5000, "offset": -2000}
        params = {"temperature_compensation": 15.0}

        result_with_temp = processor.process(raw_value=1800, calibration=calibration, params=params)
        result_no_temp = processor.process(raw_value=1800, calibration=calibration)

        # At 15°C, temp_factor = 1 + 0.02 * (15 - 25) = 0.8
        # EC_compensated = EC_raw / 0.8 (should be higher)
        assert result_with_temp.value > result_no_temp.value

    def test_process_unit_conversion_ms_cm(self, processor):
        """Test unit conversion to mS/cm."""
        calibration = {"slope": 5000, "offset": -2000}
        params = {"unit": "ms_cm"}

        result = processor.process(raw_value=1800, calibration=calibration, params=params)

        # Should be in mS/cm (divided by 1000)
        assert result.unit == "mS/cm"
        # Value should be ~1000x smaller
        result_us_cm = processor.process(raw_value=1800, calibration=calibration)
        assert result.value == pytest.approx(result_us_cm.value / 1000, rel=0.01)

    def test_process_unit_conversion_ppm(self, processor):
        """Test unit conversion to ppm (TDS)."""
        calibration = {"slope": 5000, "offset": -2000}
        params = {"unit": "ppm"}

        result = processor.process(raw_value=1800, calibration=calibration, params=params)

        # Should be in ppm (multiplied by 0.5)
        assert result.unit == "ppm"
        # Value should be ~0.5x of µS/cm
        result_us_cm = processor.process(raw_value=1800, calibration=calibration)
        assert result.value == pytest.approx(result_us_cm.value * 0.5, rel=0.01)

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 0}
        result = processor.process(raw_value=1800, params=params)

        # Should have no decimal places
        assert result.value == round(result.value)

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (1 for EC)."""
        result = processor.process(raw_value=1800)
        # Check that value has at most 1 decimal place
        assert result.value == round(result.value, 1)

    def test_process_clamping_above_max(self, processor):
        """Test EC clamping to 20000 µS/cm maximum."""
        # Very high calibration to force >20000 µS/cm
        calibration = {"slope": 10000, "offset": 0}
        result = processor.process(raw_value=4095, calibration=calibration)

        # Should clamp to 20000 µS/cm
        assert result.value <= 20000.0

    def test_process_clamping_below_min(self, processor):
        """Test EC clamping to 0 µS/cm minimum."""
        # Negative offset to force negative EC
        calibration = {"slope": 1000, "offset": -10000}
        result = processor.process(raw_value=100, calibration=calibration)

        # Should clamp to 0 µS/cm
        assert result.value >= 0.0

    def test_validate_valid_adc_12bit(self, processor):
        """Test validation of valid 12-bit ADC value."""
        validation = processor.validate(2048)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_valid_adc_16bit(self, processor):
        """Test validation of valid 16-bit ADC value."""
        validation = processor.validate(16000)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_adc_below_minimum(self, processor):
        """Test validation of ADC below range."""
        validation = processor.validate(-100)
        assert validation.valid is False
        assert "out of range" in validation.error

    def test_validate_adc_above_maximum_12bit(self, processor):
        """Test validation of ADC above 12-bit range but valid for 16-bit."""
        # 5000 is above 12-bit max (4095) but valid for 16-bit (max 32767)
        validation = processor.validate(5000)
        # Should be valid (processor auto-detects 16-bit)
        assert validation.valid is True

    def test_validate_adc_above_maximum_16bit(self, processor):
        """Test validation of ADC above 16-bit range."""
        validation = processor.validate(40000)
        assert validation.valid is False
        assert "out of range" in validation.error

    def test_validate_warning_very_low_adc(self, processor):
        """Test validation warning for very low ADC (<100)."""
        validation = processor.validate(50)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very low ADC" in w for w in validation.warnings)

    def test_validate_warning_very_high_adc_12bit(self, processor):
        """Test validation warning for very high 12-bit ADC (>3995)."""
        validation = processor.validate(4000)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very high ADC" in w for w in validation.warnings)

    def test_validate_warning_very_high_adc_16bit(self, processor):
        """Test validation warning for very high 16-bit ADC (>32667)."""
        validation = processor.validate(32700)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very high ADC" in w for w in validation.warnings)

    def test_calibrate_two_point_12bit(self, processor):
        """Test two-point calibration with 12-bit ADC."""
        calibration_points = [
            {"raw": 1500, "reference": 1413},  # Low: 1413 µS/cm
            {"raw": 3000, "reference": 12880},  # High: 12880 µS/cm
        ]
        calibration = processor.calibrate(calibration_points, method="linear")

        assert "slope" in calibration
        assert "offset" in calibration
        assert calibration["method"] == "linear"
        assert calibration["points"] == 2
        assert calibration["adc_type"] == "12bit"

        # Verify slope and offset calculation
        voltage1 = (1500 / 4095) * 3.3
        voltage2 = (3000 / 4095) * 3.3
        expected_slope = (12880 - 1413) / (voltage2 - voltage1)
        expected_offset = 1413 - (expected_slope * voltage1)

        assert calibration["slope"] == pytest.approx(expected_slope, rel=0.01)
        assert calibration["offset"] == pytest.approx(expected_offset, rel=0.01)

    def test_calibrate_two_point_16bit(self, processor):
        """Test two-point calibration with 16-bit ADC."""
        calibration_points = [
            {"raw": 10000, "reference": 1413},  # Low (16-bit ADC)
            {"raw": 20000, "reference": 12880},  # High (16-bit ADC)
        ]
        calibration = processor.calibrate(calibration_points, method="linear")

        assert calibration["adc_type"] == "16bit"
        assert "slope" in calibration
        assert "offset" in calibration

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 2 points"):
            processor.calibrate([{"raw": 1500, "reference": 1413}], method="linear")

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [
            {"raw": 1500, "reference": 1413},
            {"raw": 3000, "reference": 12880},
        ]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="offset")

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["unit"] == "us_cm"
        assert params["temperature_compensation"] is None
        assert params["decimal_places"] == 1

    def test_get_value_range(self, processor):
        """Test value range (0-20000 µS/cm)."""
        range_data = processor.get_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 20000.0

    def test_get_raw_value_range(self, processor):
        """Test raw ADC value range (0-4095 for 12-bit)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 4095.0

    def test_process_quality_good_calibrated(self, processor):
        """Test quality assessment for typical range with calibration."""
        # EC in typical range (100-15000 µS/cm)
        calibration = {"slope": 3000, "offset": 0}
        result = processor.process(raw_value=1800, calibration=calibration)
        # Should be "good" if calibrated and in typical range
        assert result.quality in ["good", "fair"]

    def test_process_quality_fair_uncalibrated(self, processor):
        """Test quality assessment for uncalibrated measurement."""
        result = processor.process(raw_value=1800)
        # Should be "fair" or "good" if in typical range but uncalibrated
        assert result.quality in ["good", "fair"]

    def test_process_quality_poor_extreme_uncalibrated(self, processor):
        """Test quality assessment for extreme value without calibration."""
        # Very low EC, uncalibrated
        result = processor.process(raw_value=50)
        # Should be "poor" if uncalibrated and at extremes
        assert result.quality in ["poor", "fair"]

    def test_process_metadata_voltage(self, processor):
        """Test that voltage is included in metadata."""
        result = processor.process(raw_value=2048)

        # 2048 / 4095 * 3.3V ≈ 1.65V
        expected_voltage = (2048 / 4095) * 3.3
        assert "voltage" in result.metadata
        assert result.metadata["voltage"] == pytest.approx(expected_voltage, rel=0.01)

    def test_process_metadata_adc_type(self, processor):
        """Test that ADC type is included in metadata."""
        result = processor.process(raw_value=2048)
        assert "adc_type" in result.metadata
        assert result.metadata["adc_type"] == "12bit"

    def test_process_invalid_adc_returns_error_quality(self, processor):
        """Test that invalid ADC value returns error quality."""
        result = processor.process(raw_value=50000)  # Above 16-bit max
        assert result.quality == "error"
        assert "error" in result.metadata

    def test_process_16bit_adc_type_in_calibration(self, processor):
        """Test that ADC type from calibration is used."""
        calibration = {"slope": 5000, "offset": -2000, "adc_type": "16bit"}
        result = processor.process(raw_value=16000, calibration=calibration)

        # Should use 16-bit voltage range (0-5V)
        expected_voltage = (16000 / 32767) * 5.0
        assert result.metadata["voltage"] == pytest.approx(expected_voltage, rel=0.01)
        assert result.metadata["adc_type"] == "16bit"

    def test_temperature_compensation_formula_accuracy(self, processor):
        """Test temperature compensation formula accuracy."""
        calibration = {"slope": 5000, "offset": -2000}

        # Get EC at reference temp (25°C)
        result_25c = processor.process(raw_value=1800, calibration=calibration)

        # Get EC at 30°C with temp compensation
        params = {"temperature_compensation": 30.0}
        result_30c = processor.process(raw_value=1800, calibration=calibration, params=params)

        # Manual calculation:
        # temp_factor = 1 + 0.02 * (30 - 25) = 1.1
        # EC_compensated = EC_raw / 1.1
        expected_ec_compensated = result_25c.value / 1.1

        assert result_30c.value == pytest.approx(expected_ec_compensated, rel=0.01)

    def test_process_unstable_reading_downgrades_quality(self, processor):
        """Unstable ADC sampling should downgrade good quality to fair."""
        calibration = {"slope": 3000, "offset": 0}
        params = {"stable": False, "adc_stddev": 25.0, "sample_count": 30}
        result = processor.process(raw_value=1800, calibration=calibration, params=params)
        assert result.quality == "fair"
        assert result.metadata["stable"] is False
        assert result.metadata["sample_count"] == 30

    def test_process_stable_reading_keeps_good_quality(self, processor):
        """Stable sampling metadata should preserve good quality when calibrated."""
        calibration = {"slope": 3000, "offset": 0}
        params = {"stable": True, "adc_stddev": 5.0, "sample_count": 30}
        result = processor.process(raw_value=1800, calibration=calibration, params=params)
        assert result.quality == "good"
        assert result.metadata["stable"] is True
        assert "ec_stddev" in result.metadata
