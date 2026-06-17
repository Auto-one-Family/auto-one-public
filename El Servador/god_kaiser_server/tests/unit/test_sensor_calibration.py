"""
Unit Tests for Sensor Calibration API and Functions.

Tests:
- Calibration schemas validation
- Calibration endpoint logic
- All sensor types: pH, EC, Moisture, Temperature, Pressure, Humidity
"""

import pytest

from src.api.schemas import (
    CalibrationPoint,
    SensorCalibrateRequest,
    SensorCalibrateResponse,
)

# Direct imports to avoid LibraryLoader module issues
from src.sensors.sensor_libraries.active.ec_sensor import ECSensorProcessor
from src.sensors.sensor_libraries.active.moisture import MoistureSensorProcessor
from src.sensors.sensor_libraries.active.ph_sensor import PHSensorProcessor
from src.sensors.sensor_libraries.active.pressure import (
    BMP280PressureProcessor,
    BMP280TemperatureProcessor,
)
from src.sensors.sensor_libraries.active.temperature import (
    DS18B20Processor,
    SHT31TemperatureProcessor,
)
from src.sensors.sensor_libraries.active.humidity import SHT31HumidityProcessor


class TestCalibrationSchemas:
    """Tests for calibration Pydantic schemas."""

    def test_calibration_point_valid(self):
        """Test valid calibration point."""
        point = CalibrationPoint(raw=1500, reference=1413)
        assert point.raw == 1500
        assert point.reference == 1413

    def test_calibration_point_floats(self):
        """Test calibration point with float values."""
        point = CalibrationPoint(raw=2150.5, reference=7.0)
        assert point.raw == 2150.5
        assert point.reference == 7.0

    def test_calibrate_request_valid(self):
        """Test valid calibration request."""
        request = SensorCalibrateRequest(
            esp_id="ESP_12AB34CD",
            gpio=34,
            sensor_type="ec",
            calibration_points=[
                CalibrationPoint(raw=1500, reference=1413),
                CalibrationPoint(raw=3000, reference=12880),
            ],
            method="linear",
            save_to_config=True,
        )
        assert request.esp_id == "ESP_12AB34CD"
        assert request.gpio == 34
        assert request.sensor_type == "ec"
        assert len(request.calibration_points) == 2

    def test_calibrate_request_sensor_type_normalized(self):
        """Test that sensor type is normalized to lowercase."""
        request = SensorCalibrateRequest(
            esp_id="ESP_12AB34CD",
            gpio=34,
            sensor_type="  EC  ",
            calibration_points=[CalibrationPoint(raw=1500, reference=1413)],
        )
        assert request.sensor_type == "ec"

    def test_calibrate_request_invalid_esp_id(self):
        """Test invalid ESP ID format."""
        with pytest.raises(ValueError):
            SensorCalibrateRequest(
                esp_id="invalid",
                gpio=34,
                sensor_type="ec",
                calibration_points=[CalibrationPoint(raw=1500, reference=1413)],
            )

    def test_calibrate_request_invalid_gpio(self):
        """Test invalid GPIO (out of range)."""
        with pytest.raises(ValueError):
            SensorCalibrateRequest(
                esp_id="ESP_12AB34CD",
                gpio=50,  # ESP32 max is 39
                sensor_type="ec",
                calibration_points=[CalibrationPoint(raw=1500, reference=1413)],
            )

    def test_calibrate_request_empty_points(self):
        """Test empty calibration points (should fail)."""
        with pytest.raises(ValueError):
            SensorCalibrateRequest(
                esp_id="ESP_12AB34CD",
                gpio=34,
                sensor_type="ec",
                calibration_points=[],
            )

    def test_calibrate_response_valid(self):
        """Test valid calibration response."""
        response = SensorCalibrateResponse(
            success=True,
            calibration={"slope": 15210.9, "offset": -4876.2},
            sensor_type="ec",
            method="linear",
            saved=True,
            message="Calibration saved.",
        )
        assert response.success is True
        assert response.calibration["slope"] == 15210.9
        assert response.saved is True


class TestSensorCalibrationFunctions:
    """Tests for sensor calibration functions across all sensor types."""

    # -------------------------------------------------------------------------
    # pH Sensor Calibration
    # -------------------------------------------------------------------------
    def test_ph_calibration_two_point(self):
        """Test pH two-point calibration (pH 4.0 + pH 7.0)."""
        processor = PHSensorProcessor()

        calibration_points = [
            {"raw": 2150, "reference": 7.0},
            {"raw": 1800, "reference": 4.0},
        ]

        result = processor.calibrate(calibration_points, method="linear")

        assert "slope" in result
        assert "offset" in result
        assert result["method"] == "linear"
        assert result["points"] == 2

    def test_ph_calibration_insufficient_points(self):
        """Test pH calibration fails with only 1 point."""
        processor = PHSensorProcessor()

        with pytest.raises(ValueError, match="at least 2 points"):
            processor.calibrate([{"raw": 2150, "reference": 7.0}], method="linear")

    # -------------------------------------------------------------------------
    # EC Sensor Calibration
    # -------------------------------------------------------------------------
    def test_ec_calibration_two_point(self):
        """Test EC two-point calibration (1413 + 12880 µS/cm)."""
        processor = ECSensorProcessor()

        calibration_points = [
            {"raw": 1500, "reference": 1413},
            {"raw": 3000, "reference": 12880},
        ]

        result = processor.calibrate(calibration_points, method="linear")

        assert "slope" in result
        assert "offset" in result
        assert result["method"] == "linear"
        assert result["adc_type"] in ["12bit", "16bit"]

    def test_ec_calibration_16bit_adc(self):
        """Test EC calibration with 16-bit ADC values."""
        processor = ECSensorProcessor()

        calibration_points = [
            {"raw": 10000, "reference": 1413},
            {"raw": 20000, "reference": 12880},
        ]

        result = processor.calibrate(calibration_points, method="linear")

        assert result["adc_type"] == "16bit"

    # -------------------------------------------------------------------------
    # Moisture Sensor Calibration
    # -------------------------------------------------------------------------
    def test_moisture_calibration_dry_wet(self):
        """Test moisture dry/wet calibration."""
        processor = MoistureSensorProcessor()

        calibration_points = [
            {"raw": 3200, "reference": 0.0},  # Dry
            {"raw": 1500, "reference": 100.0},  # Wet
        ]

        result = processor.calibrate(calibration_points, method="linear")

        assert "dry_value" in result
        assert "wet_value" in result
        assert result["dry_value"] == 3200
        assert result["wet_value"] == 1500

    # -------------------------------------------------------------------------
    # Temperature Sensor Calibration (Offset)
    # -------------------------------------------------------------------------
    def test_temperature_calibration_offset(self):
        """Test DS18B20 temperature offset calibration."""
        processor = DS18B20Processor()

        calibration_points = [
            {"raw": 23.5, "reference": 24.0},
        ]

        result = processor.calibrate(calibration_points, method="offset")

        assert "offset" in result
        assert result["offset"] == pytest.approx(0.5, rel=0.01)
        assert result["method"] == "offset"

    def test_temperature_calibration_multi_point_average(self):
        """Test DS18B20 temperature calibration averages multiple points."""
        processor = DS18B20Processor()

        calibration_points = [
            {"raw": 23.0, "reference": 24.0},  # offset +1.0
            {"raw": 19.0, "reference": 20.0},  # offset +1.0
        ]

        result = processor.calibrate(calibration_points, method="offset")

        assert result["offset"] == pytest.approx(1.0, rel=0.01)
        assert result["points"] == 2

    # -------------------------------------------------------------------------
    # Pressure Sensor Calibration (BMP280)
    # -------------------------------------------------------------------------
    def test_pressure_calibration_offset(self):
        """Test BMP280 pressure offset calibration."""
        processor = BMP280PressureProcessor()

        calibration_points = [
            {"raw": 1013.25, "reference": 1015.0},
        ]

        result = processor.calibrate(calibration_points, method="offset")

        assert "offset" in result
        assert result["offset"] == pytest.approx(1.75, rel=0.01)

    def test_bmp280_temperature_calibration(self):
        """Test BMP280 temperature offset calibration."""
        processor = BMP280TemperatureProcessor()

        calibration_points = [
            {"raw": 23.5, "reference": 24.0},
        ]

        result = processor.calibrate(calibration_points, method="offset")

        assert result["offset"] == pytest.approx(0.5, rel=0.01)

    # -------------------------------------------------------------------------
    # Humidity Sensor Calibration (SHT31)
    # -------------------------------------------------------------------------
    def test_humidity_calibration_offset(self):
        """Test SHT31 humidity offset calibration."""
        processor = SHT31HumidityProcessor()

        calibration_points = [
            {"raw": 76.5, "reference": 75.0},  # NaCl salt solution
        ]

        result = processor.calibrate(calibration_points, method="offset")

        assert "offset" in result
        assert result["offset"] == pytest.approx(-1.5, rel=0.01)

    # -------------------------------------------------------------------------
    # Invalid Method Tests
    # -------------------------------------------------------------------------
    def test_invalid_calibration_method(self):
        """Test that invalid calibration method raises error."""
        processor = DS18B20Processor()

        with pytest.raises(ValueError, match="not supported"):
            processor.calibrate(
                [{"raw": 23.5, "reference": 24.0}],
                method="polynomial",
            )


class TestCalibrationIntegration:
    """Integration tests for calibration with process()."""

    def test_ec_calibration_affects_processing(self):
        """Test that EC calibration changes processed values."""
        processor = ECSensorProcessor()

        # Process without calibration
        result_uncalibrated = processor.process(raw_value=2000)

        # Calibrate
        calibration = processor.calibrate(
            [
                {"raw": 1500, "reference": 1413},
                {"raw": 3000, "reference": 12880},
            ],
            method="linear",
        )

        # Process with calibration
        result_calibrated = processor.process(raw_value=2000, calibration=calibration)

        # Values should be different
        assert result_uncalibrated.value != result_calibrated.value
        assert result_calibrated.metadata["calibrated"] is True

    def test_moisture_calibration_affects_processing(self):
        """Test that moisture calibration changes processed values."""
        processor = MoistureSensorProcessor()

        # Calibrate with custom dry/wet points
        calibration = processor.calibrate(
            [
                {"raw": 3500, "reference": 0.0},  # Different dry point
                {"raw": 1200, "reference": 100.0},  # Different wet point
            ],
            method="linear",
        )

        # Test at midpoint: (3500 + 1200) / 2 = 2350 → should be 50%
        result = processor.process(raw_value=2350, calibration=calibration)

        assert result.value == pytest.approx(50.0, rel=0.1)

    def test_temperature_offset_calibration(self):
        """Test that DS18B20 temperature offset calibration is applied."""
        processor = DS18B20Processor()

        # Calibrate with +1.0°C offset
        calibration = processor.calibrate(
            [{"raw": 23.0, "reference": 24.0}],
            method="offset",
        )

        # Process with calibration
        result = processor.process(raw_value=25.0, calibration=calibration)

        # Should be 25.0 + 1.0 = 26.0
        assert result.value == pytest.approx(26.0, rel=0.01)

    def test_pressure_offset_calibration(self):
        """Test that BMP280 pressure offset calibration is applied."""
        processor = BMP280PressureProcessor()

        # Calibrate with +2.0 hPa offset
        calibration = processor.calibrate(
            [{"raw": 1013.0, "reference": 1015.0}],
            method="offset",
        )

        # Process with calibration
        result = processor.process(raw_value=1000.0, calibration=calibration)

        # Should be 1000.0 + 2.0 = 1002.0
        assert result.value == pytest.approx(1002.0, rel=0.01)
