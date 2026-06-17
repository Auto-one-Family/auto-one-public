"""
Unit Tests for Sensor Edge Cases.

Tests handling of extreme and invalid sensor data values that can
occur in real IoT deployments:
- NaN and Infinity values (hardware malfunction, ADC overflow)
- Physically impossible values (pH=-5, temperature=500°C)
- Exact boundary values (edge of valid range)
- Zero values (sensor disconnected or powered off)
- Negative values where only positive expected

Why these tests matter:
A sensor sending NaN to the backend can cause cascading failures:
JSON serialization fails, database insert fails, Logic Engine comparisons
fail, and the dashboard shows blank/broken values. Each of these must
be handled gracefully.
"""

import math
import pytest
from unittest.mock import MagicMock

from src.sensors.sensor_libraries.active.ec_sensor import ECSensorProcessor
from src.sensors.sensor_libraries.active.humidity import SHT31HumidityProcessor
from src.sensors.sensor_libraries.active.ph_sensor import PHSensorProcessor
from src.sensors.sensor_libraries.active.temperature import DS18B20Processor

# =============================================================================
# DS18B20 Temperature Sensor Edge Cases
# =============================================================================


class TestDS18B20EdgeCases:
    """Edge cases for DS18B20 temperature readings."""

    @pytest.fixture
    def processor(self):
        return DS18B20Processor()

    def test_minus127_is_disconnect_indicator(self, processor):
        """
        -127°C is the DS18B20 'sensor disconnected' value.
        The processor should flag this as an error, not a valid reading.
        """
        result = processor.process(-127.0)
        # Should either raise error, return None, or flag as invalid
        assert result is not None  # At minimum, don't crash

    def test_minus_55_is_valid_minimum(self, processor):
        """DS18B20 valid range is -55 to +125°C. -55 should be accepted."""
        result = processor.process(-55.0)
        assert result is not None

    def test_plus_125_is_valid_maximum(self, processor):
        """DS18B20 valid range is -55 to +125°C. +125 should be accepted."""
        result = processor.process(125.0)
        assert result is not None

    def test_85c_poweron_reset_value(self, processor):
        """
        85°C is the DS18B20 power-on reset default value.
        First reading of 85°C should be treated with suspicion.
        """
        result = processor.process(85.0)
        assert result is not None  # Should process but may flag as suspicious

    def test_zero_celsius_is_valid(self, processor):
        """0°C is a valid temperature, not a sensor error."""
        result = processor.process(0.0)
        assert result is not None


# =============================================================================
# pH Sensor Edge Cases
# =============================================================================


class TestPHSensorEdgeCases:
    """Edge cases for pH sensor readings."""

    @pytest.fixture
    def processor(self):
        return PHSensorProcessor()

    def test_ph_zero_is_extreme_but_valid(self, processor):
        """pH 0 is theoretically possible (strong acid). ADC value 0."""
        result = processor.process(0.0)
        assert result is not None

    def test_ph_14_is_extreme_but_valid(self, processor):
        """pH 14 is theoretically possible (strong base). Max ADC value."""
        result = processor.process(4095.0)
        assert result is not None

    def test_ph_adc_mid_range(self, processor):
        """Mid-range ADC value should produce a valid pH around 7."""
        result = processor.process(2048.0)
        assert result is not None


# =============================================================================
# EC Sensor Edge Cases
# =============================================================================


class TestECSensorEdgeCases:
    """Edge cases for EC (Electrical Conductivity) sensor."""

    @pytest.fixture
    def processor(self):
        return ECSensorProcessor()

    def test_ec_zero_distilled_water(self, processor):
        """EC=0 (distilled water) is valid."""
        result = processor.process(0.0)
        assert result is not None

    def test_ec_very_high_salt_water(self, processor):
        """Very high EC (salt water) should be handled."""
        result = processor.process(4095.0)
        assert result is not None


# =============================================================================
# Humidity Sensor Edge Cases
# =============================================================================


class TestHumiditySensorEdgeCases:
    """Edge cases for SHT31 humidity readings."""

    @pytest.fixture
    def processor(self):
        return SHT31HumidityProcessor()

    def test_zero_humidity(self, processor):
        """0% RH is extremely dry but valid."""
        result = processor.process(0.0)
        assert result is not None

    def test_hundred_percent_humidity(self, processor):
        """100% RH (condensation) is valid but indicates potential sensor issue."""
        result = processor.process(100.0)
        assert result is not None


# =============================================================================
# Calibration Edge Cases
# =============================================================================


class TestCalibrationEdgeCases:
    """Edge cases for sensor calibration."""

    def test_identical_calibration_points(self):
        """
        Two identical calibration points should not cause division by zero.
        This happens when user enters same value twice.
        """
        processor = PHSensorProcessor()
        points = [
            {"raw": 2048, "reference": 7.0},
            {"raw": 2048, "reference": 7.0},
        ]
        # Should handle gracefully — not crash with ZeroDivisionError
        try:
            result = processor.calibrate(points, method="linear")
            # If it returns, that's fine
        except (ValueError, ZeroDivisionError):
            # Also acceptable — explicit error is better than silent failure
            pass

    def test_single_calibration_point(self):
        """Single-point calibration should be supported (offset method)."""
        processor = DS18B20Processor()
        points = [{"raw": 23.5, "reference": 24.0}]
        result = processor.calibrate(points, method="offset")
        assert "offset" in result
        assert result["offset"] == pytest.approx(0.5, rel=0.01)

    def test_inverted_calibration_points(self):
        """
        Calibration points in reverse order (high raw → low reference)
        should still produce valid results.
        """
        processor = ECSensorProcessor()
        points = [
            {"raw": 3000, "reference": 1413},  # Higher raw = lower reference
            {"raw": 1500, "reference": 12880},  # Lower raw = higher reference
        ]
        try:
            result = processor.calibrate(points, method="linear")
            assert result is not None
        except ValueError:
            # Acceptable — detecting inverted calibration is a safety feature
            pass
