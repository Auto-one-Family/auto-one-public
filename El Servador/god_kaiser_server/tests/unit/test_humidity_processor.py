"""
Unit Tests for Humidity Sensor Processors.

Tests SHT31HumidityProcessor.
"""

import pytest

from src.sensors.sensor_libraries.active.humidity import (
    SHT31HumidityProcessor,
)


class TestSHT31HumidityProcessor:
    """Unit tests for SHT31 humidity processor."""

    @pytest.fixture
    def processor(self):
        """Create SHT31 humidity processor instance."""
        return SHT31HumidityProcessor()

    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "sht31_humidity"

    def test_process_valid_humidity(self, processor):
        """Test processing valid humidity reading."""
        result = processor.process(raw_value=65.5)
        assert result.value == 65.5
        assert result.unit == "%RH"
        assert result.quality == "good"
        assert result.metadata["raw_humidity"] == 65.5
        assert result.metadata["calibrated"] is False

    def test_process_with_offset_calibration(self, processor):
        """Test processing with calibration offset."""
        calibration = {"offset": -2.0}
        result = processor.process(raw_value=65.5, calibration=calibration)
        assert result.value == 63.5
        assert result.metadata["calibrated"] is True

    def test_process_positive_calibration_offset(self, processor):
        """Test processing with positive calibration offset."""
        calibration = {"offset": 1.5}
        result = processor.process(raw_value=50.0, calibration=calibration)
        assert result.value == 51.5

    def test_process_decimal_places(self, processor):
        """Test custom decimal places."""
        params = {"decimal_places": 0}
        result = processor.process(raw_value=65.789, params=params)
        assert result.value == 66

    def test_process_default_decimal_places(self, processor):
        """Test default decimal places (1 for SHT31)."""
        result = processor.process(raw_value=65.789)
        assert result.value == 65.8

    def test_validate_valid_humidity(self, processor):
        """Test validation of valid humidity."""
        validation = processor.validate(50.0)
        assert validation.valid is True
        assert validation.error is None

    def test_validate_humidity_below_minimum(self, processor):
        """Test validation of humidity below physical range."""
        validation = processor.validate(-5.0)
        assert validation.valid is False
        assert "out of physical range" in validation.error

    def test_validate_humidity_above_maximum(self, processor):
        """Test validation of humidity above physical range."""
        validation = processor.validate(105.0)
        assert validation.valid is False
        assert "out of physical range" in validation.error

    def test_validate_very_low_humidity(self, processor):
        """Test validation warning for very low humidity (<5%)."""
        validation = processor.validate(3.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very low humidity" in w for w in validation.warnings)

    def test_validate_very_high_humidity(self, processor):
        """Test validation warning for very high humidity (>95%)."""
        validation = processor.validate(97.0)
        assert validation.valid is True
        assert validation.warnings is not None
        assert any("Very high humidity" in w for w in validation.warnings)

    def test_validate_outside_typical_range_low(self, processor):
        """Test validation warning for humidity below typical accuracy range."""
        validation = processor.validate(15.0)
        assert validation.valid is True
        assert any("outside typical accuracy range" in w for w in validation.warnings)

    def test_validate_outside_typical_range_high(self, processor):
        """Test validation warning for humidity above typical accuracy range."""
        validation = processor.validate(85.0)
        assert validation.valid is True
        assert any("outside typical accuracy range" in w for w in validation.warnings)

    def test_process_condensation_warning(self, processor):
        """Test condensation warning for high humidity."""
        result = processor.process(raw_value=96.5)
        assert "warnings" in result.metadata
        assert any("condensation" in w.lower() for w in result.metadata["warnings"])

    def test_process_condensation_warning_disabled(self, processor):
        """Test disabling condensation warning."""
        params = {"condensation_warning": False}
        result = processor.process(raw_value=96.5, params=params)

        # Should not have condensation warning from process step
        # (validation warnings still present)
        condensation_warnings = [
            w for w in (result.metadata.get("warnings") or []) if "Consider activating heater" in w
        ]
        assert len(condensation_warnings) == 0

    def test_process_humidity_clamping_above_max(self, processor):
        """Test humidity clamping after calibration (above 100%)."""
        calibration = {"offset": 5.0}
        result = processor.process(raw_value=98.0, calibration=calibration)

        # 98 + 5 = 103, but should be clamped to 100
        assert result.value == 100.0

    def test_process_humidity_clamping_below_min(self, processor):
        """Test humidity clamping after calibration (below 0%)."""
        calibration = {"offset": -10.0}
        result = processor.process(raw_value=5.0, calibration=calibration)

        # 5 - 10 = -5, but should be clamped to 0
        assert result.value == 0.0

    def test_calibrate_single_point_offset(self, processor):
        """Test single-point offset calibration."""
        # Calibration using NaCl salt solution (75% RH reference)
        calibration_points = [{"raw": 76.5, "reference": 75.0}]
        calibration = processor.calibrate(calibration_points, method="offset")

        assert calibration["offset"] == -1.5
        assert calibration["method"] == "offset"
        assert calibration["points"] == 1

    def test_calibrate_multi_point_average(self, processor):
        """Test multi-point calibration (average offset)."""
        calibration_points = [
            {"raw": 34.0, "reference": 33.0},  # MgCl2
            {"raw": 76.5, "reference": 75.0},  # NaCl
        ]
        calibration = processor.calibrate(calibration_points, method="offset")

        # Avg offset: ((-1.0) + (-1.5)) / 2 = -1.25
        assert calibration["offset"] == -1.25
        assert calibration["points"] == 2

    def test_calibrate_invalid_method(self, processor):
        """Test calibration with invalid method."""
        calibration_points = [{"raw": 76.5, "reference": 75.0}]
        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(calibration_points, method="linear")

    def test_calibrate_insufficient_points(self, processor):
        """Test calibration with insufficient points."""
        with pytest.raises(ValueError, match="at least 1 point"):
            processor.calibrate([], method="offset")

    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert params["decimal_places"] == 1
        assert params["condensation_warning"] is True

    def test_get_value_range(self, processor):
        """Test value range."""
        range_data = processor.get_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 100.0

    def test_get_raw_value_range(self, processor):
        """Test raw value range (same as value range)."""
        range_data = processor.get_raw_value_range()
        assert range_data["min"] == 0.0
        assert range_data["max"] == 100.0

    def test_process_quality_good(self, processor):
        """Test quality assessment for typical range (20-80% RH)."""
        result = processor.process(raw_value=50.0)
        assert result.quality == "good"

    def test_process_quality_fair_low(self, processor):
        """Test quality assessment for low but acceptable humidity."""
        result = processor.process(raw_value=10.0)
        assert result.quality == "fair"

    def test_process_quality_fair_high(self, processor):
        """Test quality assessment for high but acceptable humidity."""
        result = processor.process(raw_value=90.0)
        assert result.quality == "fair"

    def test_process_quality_poor_very_low(self, processor):
        """Test quality assessment for very low humidity (<5%)."""
        result = processor.process(raw_value=3.0)
        assert result.quality == "poor"

    def test_process_quality_poor_very_high(self, processor):
        """Test quality assessment for very high humidity (>95%)."""
        result = processor.process(raw_value=97.0)
        assert result.quality == "poor"

    def test_process_typical_range_edges(self, processor):
        """Test processing at edges of typical accuracy range."""
        # Lower edge
        result = processor.process(raw_value=20.0)
        assert result.quality == "good"

        # Upper edge
        result = processor.process(raw_value=80.0)
        assert result.quality == "good"

    def test_process_with_calibration_and_params(self, processor):
        """Test processing with both calibration and parameters."""
        calibration = {"offset": -1.0}
        params = {"decimal_places": 0, "condensation_warning": False}

        result = processor.process(raw_value=75.5, calibration=calibration, params=params)

        # 75.5 - 1.0 = 74.5, rounded to 0 decimal places = 74 (banker's rounding)
        assert result.value == 74
        assert result.metadata["calibrated"] is True

    # =========================================================================
    # SHT31 RAW MODE TESTS (Pi-Enhanced Mode - 16-bit Integer)
    # Formula: humidity_rh = 100 * raw_value / 65535.0
    # =========================================================================

    def test_raw_mode_humidity_conversion_formula(self, processor):
        """Test Sensirion Datasheet Formula: 100 * raw / 65535."""
        params = {"raw_mode": True}
        # raw=32768 → 100 * 32768 / 65535 = 50.0%
        result = processor.process(raw_value=32768, params=params)

        assert result.value == pytest.approx(50.0, abs=0.1)
        assert result.quality == "good"
        assert result.metadata["raw_mode"] is True
        assert result.metadata["original_raw_value"] == 32768

    def test_raw_mode_humidity_zero(self, processor):
        """Test RAW=0 → 0% RH."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=0, params=params)

        assert result.value == 0.0
        # 0% is very low → poor quality
        assert result.quality == "poor"

    def test_raw_mode_humidity_max(self, processor):
        """Test RAW=65535 → 100% RH."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=65535, params=params)

        assert result.value == 100.0
        # 100% is very high → poor quality (condensation)
        assert result.quality == "poor"

    def test_raw_mode_humidity_60_percent(self, processor):
        """Test RAW=39321 → ~60% RH."""
        params = {"raw_mode": True}
        # 100 * 39321 / 65535 = 60.0%
        result = processor.process(raw_value=39321, params=params)

        assert result.value == pytest.approx(60.0, abs=0.1)
        assert result.quality == "good"

    def test_raw_mode_humidity_typical_greenhouse(self, processor):
        """Test RAW value for typical greenhouse humidity (75%)."""
        params = {"raw_mode": True}
        # Solving: 75 = 100 * raw / 65535
        # raw = 75 * 65535 / 100 = 49151
        result = processor.process(raw_value=49151, params=params)

        assert result.value == pytest.approx(75.0, abs=0.1)
        assert result.quality == "good"

    def test_raw_mode_humidity_out_of_range_negative(self, processor):
        """Test negative RAW value rejected."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=-100, params=params)

        assert result.quality == "error"
        assert "out of range" in result.metadata.get("error", "")

    def test_raw_mode_humidity_out_of_range_high(self, processor):
        """Test RAW value > 65535 rejected."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=70000, params=params)

        assert result.quality == "error"
        assert "out of range" in result.metadata.get("error", "")

    def test_raw_mode_humidity_with_calibration(self, processor):
        """Test SHT31 Humidity RAW mode with calibration offset."""
        params = {"raw_mode": True}
        calibration = {"offset": -2.0}
        # raw=32768 → 50.0% - 2.0% = 48.0%
        result = processor.process(raw_value=32768, params=params, calibration=calibration)

        assert result.value == pytest.approx(48.0, abs=0.1)
        assert result.metadata["calibrated"] is True

    def test_raw_mode_humidity_clamping_after_calibration(self, processor):
        """Test humidity clamping to 0-100% after calibration in RAW mode."""
        params = {"raw_mode": True}
        calibration = {"offset": 10.0}
        # raw=62259 → 95% + 10% = 105% → clamped to 100%
        # 95 = 100 * raw / 65535 → raw = 62259
        result = processor.process(raw_value=62259, params=params, calibration=calibration)

        assert result.value == 100.0  # Clamped

    def test_raw_mode_humidity_metadata_conversion_formula(self, processor):
        """Test metadata includes conversion formula for SHT31 humidity."""
        params = {"raw_mode": True}
        result = processor.process(raw_value=32768, params=params)

        assert result.metadata["raw_mode"] is True
        assert result.metadata["original_raw_value"] == 32768
        assert result.metadata["conversion_formula"] is not None
        assert "32768" in result.metadata["conversion_formula"]

    def test_raw_mode_humidity_condensation_warning(self, processor):
        """Test condensation warning triggers in RAW mode for high humidity."""
        params = {"raw_mode": True}
        # raw=64225 → ~98% RH (above 95% condensation threshold)
        # 98 = 100 * raw / 65535 → raw = 64225
        result = processor.process(raw_value=64225, params=params)

        assert result.value == pytest.approx(98.0, abs=0.2)
        assert result.metadata.get("warnings") is not None
        assert any("condensation" in w.lower() for w in result.metadata["warnings"])
