"""
Unit Tests for Moisture Sensor Processor.

Tests MoistureSensorProcessor for capacitive soil moisture sensors.
"""

import pytest

from src.sensors.sensor_libraries.active.moisture import (
    MoistureSensorProcessor,
)


class TestMoistureSensorProcessor:
    """Unit tests for Moisture sensor processor."""

    @pytest.fixture
    def processor(self):
        """Create Moisture sensor processor instance."""
        return MoistureSensorProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "moisture"

    def test_process_valid_moisture(self, processor):
        """Test processing valid moisture reading without calibration."""
        # Default mapping: dry=3200, wet=1500
        # ADC 2350 → moisture = (2350 - 3200) / (1500 - 3200) * 100 = 50%
        result = processor.process(raw_value=2350)
        assert result.value == 50.0
        assert result.unit == "%"
        assert result.quality == "good"
        assert result.metadata["raw_value"] == 2350
        assert result.metadata["calibrated"] is False
        assert result.metadata["inverted"] is False

    def test_process_with_calibration(self, processor):
        """Test processing with dry/wet calibration."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        result = processor.process(raw_value=2350, calibration=calibration)

        # moisture = (2350 - 3200) / (1500 - 3200) * 100 = 50%
        assert result.value == 50.0
        assert result.metadata["calibrated"] is True

    def test_process_dry_calibration(self, processor):
        """Test processing at dry calibration point."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        result = processor.process(raw_value=3200, calibration=calibration)

        # At dry point → 0%
        assert result.value == 0.0

    def test_process_wet_calibration(self, processor):
        """Test processing at wet calibration point."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        result = processor.process(raw_value=1500, calibration=calibration)

        # At wet point → 100%
        assert result.value == 100.0

    def test_process_inverted_logic(self, processor):
        """Test processing with inverted logic (HIGH voltage = DRY)."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        params = {"invert": True}
        result = processor.process(raw_value=2350, calibration=calibration, params=params)

        # Normal: 50%, Inverted: 100 - 50 = 50% (coincidentally same)
        # Let's use dry point: 0% → inverted = 100%
        result_dry = processor.process(raw_value=3200, calibration=calibration, params=params)
        assert result_dry.value == 100.0  # Inverted from 0%
        assert result_dry.metadata["inverted"] is True

    def test_process_no_invert_by_default(self, processor):
        """Test that invert is False by default."""
        result = processor.process(raw_value=2350)
        assert result.metadata["inverted"] is False

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 0}
        result = processor.process(raw_value=2350, params=params)
        assert result.value == 50  # No decimal places

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (1 for moisture)."""
        # ADC 2360 → moisture = (2360 - 3200) / (1500 - 3200) * 100 = 49.41%
        result = processor.process(raw_value=2360)
        assert result.value == 49.4  # Rounded to 1 decimal place

    def test_process_clamping_above_max(self, processor):
        """Test moisture clamping to 100% maximum."""
        # ADC below wet_value → would be >100%, should clamp to 100%
        calibration = {"dry_value": 3200, "wet_value": 1500}
        result = processor.process(raw_value=1000, calibration=calibration)

        # (1000 - 3200) / (1500 - 3200) * 100 = 129.4%, clamped to 100%
        assert result.value == 100.0

    def test_process_clamping_below_min(self, processor):
        """Test moisture clamping to 0% minimum."""
        # ADC above dry_value → would be <0%, should clamp to 0%
        calibration = {"dry_value": 3200, "wet_value": 1500}
        result = processor.process(raw_value=3500, calibration=calibration)

        # (3500 - 3200) / (1500 - 3200) * 100 = -17.6%, clamped to 0%
        assert result.value == 0.0

    def test_validate_valid_adc(self, processor):
        """Test validation of valid ADC value."""
        validation = processor.validate(2048)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_adc_below_minimum(self, processor):
        """Test validation of ADC below range."""
        validation = processor.validate(-100)
        assert validation.valid is False
        assert "out of range" in validation.error

    def test_validate_adc_above_maximum(self, processor):
        """Test validation of ADC above range."""
        validation = processor.validate(5000)
        assert validation.valid is False
        assert "out of range" in validation.error

    def test_validate_warning_very_low_adc(self, processor):
        """Test validation warning for very low ADC (<100)."""
        validation = processor.validate(50)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very low ADC" in w for w in validation.warnings)

    def test_validate_warning_very_high_adc(self, processor):
        """Test validation warning for very high ADC (>4000)."""
        validation = processor.validate(4050)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very high ADC" in w for w in validation.warnings)

    def test_calibrate_two_point(self, processor):
        """Test two-point dry/wet calibration."""
        calibration_points = [
            {"raw": 3200, "reference": 0.0},  # Dry (in air)
            {"raw": 1500, "reference": 100.0},  # Wet (in water)
        ]
        calibration = processor.calibrate(calibration_points, method="linear")

        assert calibration["dry_value"] == 3200
        assert calibration["wet_value"] == 1500
        assert calibration["method"] == "linear"
        assert calibration["points"] == 2

    def test_calibrate_reference_marked_points(self, processor):
        """Test calibration with explicitly marked reference values."""
        calibration_points = [
            {"raw": 1500, "reference": 100.0},  # Wet (order doesn't matter)
            {"raw": 3200, "reference": 0.0},  # Dry
        ]
        calibration = processor.calibrate(calibration_points, method="linear")

        # Should correctly identify dry and wet points
        assert calibration["dry_value"] == 3200
        assert calibration["wet_value"] == 1500

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 2 points"):
            processor.calibrate([{"raw": 3200, "reference": 0.0}], method="linear")

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [
            {"raw": 3200, "reference": 0.0},
            {"raw": 1500, "reference": 100.0},
        ]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="offset")

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["invert"] is False
        assert params["decimal_places"] == 1

    def test_get_value_range(self, processor):
        """Test value range (0-100%)."""
        range_data = processor.get_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 100.0

    def test_get_raw_value_range(self, processor):
        """Test raw ADC value range (0-4095)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 4095.0

    def test_process_quality_good(self, processor):
        """Test quality assessment for typical range (20-80%)."""
        result = processor.process(raw_value=2350)  # 50%
        assert result.quality == "good"

    def test_process_quality_fair_low(self, processor):
        """Test quality assessment for low but acceptable moisture (10-20%)."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        # 15% moisture: raw = 3200 + 0.15 * (1500 - 3200) = 3200 - 255 = 2945
        result = processor.process(raw_value=2945, calibration=calibration)
        assert result.quality == "fair"

    def test_process_quality_fair_high(self, processor):
        """Test quality assessment for high but acceptable moisture (80-95%)."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        # 85% moisture: raw = 3200 + 0.85 * (1500 - 3200) = 3200 - 1445 = 1755
        result = processor.process(raw_value=1755, calibration=calibration)
        assert result.quality == "fair"

    def test_process_quality_poor_very_dry(self, processor):
        """Test quality assessment for very dry soil (<10%)."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        # 5% moisture: raw = 3200 + 0.05 * (1500 - 3200) = 3200 - 85 = 3115
        result = processor.process(raw_value=3115, calibration=calibration)
        assert result.quality == "poor"

    def test_process_quality_poor_saturated(self, processor):
        """Test quality assessment for saturated soil (>95%)."""
        calibration = {"dry_value": 3200, "wet_value": 1500}
        # 97% moisture: raw = 3200 + 0.97 * (1500 - 3200) = 3200 - 1649 = 1551
        result = processor.process(raw_value=1551, calibration=calibration)
        assert result.quality == "poor"

    def test_process_metadata_voltage(self, processor):
        """Test that voltage is included in metadata."""
        result = processor.process(raw_value=2048)

        # 2048 / 4095 * 3.3V ≈ 1.65V
        expected_voltage = (2048 / 4095) * 3.3
        assert "voltage" in result.metadata
        assert result.metadata["voltage"] == pytest.approx(expected_voltage, rel=0.01)

    def test_process_invalid_adc_returns_error_quality(self, processor):
        """Test that invalid ADC value returns error quality."""
        result = processor.process(raw_value=5000)  # Above max
        assert result.quality == "error"
        assert "error" in result.metadata

    def test_calibrate_division_by_zero_protection(self, processor):
        """Test that identical dry/wet values don't crash (returns 50%)."""
        calibration = {"dry_value": 2000, "wet_value": 2000}
        result = processor.process(raw_value=2000, calibration=calibration)

        # Should handle gracefully and return 50% (middle value)
        assert result.value == 50.0
