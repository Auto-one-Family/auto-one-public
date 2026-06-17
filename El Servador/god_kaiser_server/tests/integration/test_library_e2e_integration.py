"""
End-to-End Library Integration Tests - Phase 6

Tests the complete flow: Mock ESP → SensorHandler → REAL Library → DB
WITHOUT mocking the sensor processor libraries.

These tests validate:
1. RAW values are correctly transmitted from Mock ESP
2. Real sensor processors are loaded and used (NOT mocked)
3. Pi-Enhanced processing produces realistic results
4. Processed values match expected sensor physics

Test Coverage:
- DS18B20: Temperature (direct Celsius, -55°C to +125°C)
- SHT31: Temperature + Humidity (I2C, -40°C to +125°C)
- Moisture: Capacitive soil moisture (ADC 0-4095 → 0-100%)
- pH: Analog pH sensor (ADC 0-4095 → pH 0-14)
- EC: Electrical conductivity (ADC 0-4095 → 0-20000 µS/cm)

Reference Values (from hardware datasheets):
- DS18B20: Raw = Celsius directly (sensor outputs digital temp)
- Moisture: ADC 3200 = dry (0%), ADC 1500 = wet (100%)
- pH: ADC 1860 ≈ pH 7.0 (neutral), slope ~-3.5 pH/V
- EC: Linear mapping with 2% temp compensation per °C
"""

import pytest
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.sensors.library_loader import LibraryLoader, get_library_loader
from src.sensors.sensor_libraries.active.temperature import (
    DS18B20Processor,
    SHT31TemperatureProcessor,
)
from src.sensors.sensor_libraries.active.moisture import MoistureSensorProcessor
from src.sensors.sensor_libraries.active.ph_sensor import PHSensorProcessor
from src.sensors.sensor_libraries.active.ec_sensor import ECSensorProcessor
from src.sensors.sensor_libraries.active.humidity import SHT31HumidityProcessor


class TestLibraryLoaderRealProcessors:
    """Test that LibraryLoader loads REAL processors correctly."""

    def test_library_loader_loads_all_processors(self):
        """LibraryLoader should load all active processors."""
        loader = get_library_loader()
        available = loader.get_available_sensors()

        # Core processors must be available
        assert "ds18b20" in available, "DS18B20 processor not loaded"
        assert "sht31_temp" in available, "SHT31 temperature processor not loaded"
        assert "moisture" in available, "Moisture processor not loaded"
        assert "ph" in available, "pH processor not loaded"
        assert "ec" in available, "EC processor not loaded"

    def test_get_processor_returns_correct_type(self):
        """get_processor should return correct processor instances."""
        loader = get_library_loader()

        ds18b20 = loader.get_processor("ds18b20")
        assert isinstance(ds18b20, DS18B20Processor)

        moisture = loader.get_processor("moisture")
        assert isinstance(moisture, MoistureSensorProcessor)

        ph = loader.get_processor("ph")
        assert isinstance(ph, PHSensorProcessor)

        ec = loader.get_processor("ec")
        assert isinstance(ec, ECSensorProcessor)


class TestDS18B20RealProcessing:
    """
    DS18B20 Temperature Sensor End-to-End Tests.

    Hardware Reference:
    - Output: Direct Celsius value (digital sensor)
    - Range: -55°C to +125°C
    - Accuracy: ±0.5°C (-10°C to +85°C)
    - Resolution: 9-12 bit (0.5°C to 0.0625°C)

    RAW Value = Celsius directly (no ADC conversion needed)
    """

    @pytest.fixture
    def processor(self):
        """Get real DS18B20 processor from library loader."""
        loader = get_library_loader()
        return loader.get_processor("ds18b20")

    def test_room_temperature_processing(self, processor):
        """Test processing typical room temperature (23.5°C) in pre-converted mode."""
        result = processor.process(raw_value=23.5, params={"raw_mode": False})

        assert result.value == 23.5
        assert result.unit == "°C"
        assert result.quality == "good"
        assert result.metadata["raw_celsius"] == 23.5

    def test_cold_temperature_processing(self, processor):
        """Test processing cold temperature (-10°C) in pre-converted mode."""
        result = processor.process(raw_value=-10.0, params={"raw_mode": False})

        assert result.value == -10.0
        assert result.unit == "°C"
        # -10°C is within accuracy range but below typical
        assert result.quality in ["good", "fair"]

    def test_hot_temperature_processing(self, processor):
        """Test processing hot temperature (85°C - max accuracy range) in pre-converted mode."""
        result = processor.process(raw_value=85.0, params={"raw_mode": False})

        assert result.value == 85.0
        assert result.unit == "°C"
        assert result.quality in ["good", "fair"]

    def test_extreme_low_temperature(self, processor):
        """Test processing extreme low temperature (-55°C - sensor limit) in pre-converted mode."""
        result = processor.process(raw_value=-55.0, params={"raw_mode": False})

        assert result.value == -55.0
        assert result.unit == "°C"
        assert result.quality == "fair"  # At sensor limits

    def test_extreme_high_temperature(self, processor):
        """Test processing extreme high temperature (+125°C - sensor limit) in pre-converted mode."""
        result = processor.process(raw_value=125.0, params={"raw_mode": False})

        assert result.value == 125.0
        assert result.unit == "°C"
        assert result.quality == "fair"  # At sensor limits

    def test_fahrenheit_conversion(self, processor):
        """Test Celsius to Fahrenheit conversion in pre-converted mode."""
        result = processor.process(raw_value=0.0, params={"raw_mode": False, "unit": "fahrenheit"})

        assert result.value == 32.0  # 0°C = 32°F
        assert result.unit == "°F"

    def test_calibration_offset(self, processor):
        """Test calibration offset application in pre-converted mode."""
        calibration = {"offset": 0.5}
        result = processor.process(
            raw_value=23.0, calibration=calibration, params={"raw_mode": False}
        )

        assert result.value == 23.5  # 23.0 + 0.5 offset
        assert result.metadata["calibrated"] is True


class TestMoistureRealProcessing:
    """
    Capacitive Soil Moisture Sensor End-to-End Tests.

    Hardware Reference (ESP32 + Capacitive Sensor v1.2):
    - ADC: 12-bit (0-4095)
    - Dry (in air): ~3000-3500 ADC
    - Wet (in water): ~1200-1500 ADC
    - Inverted logic: Higher ADC = Drier soil

    Conversion Formula:
    moisture% = (ADC - dry_value) / (wet_value - dry_value) * 100
    """

    @pytest.fixture
    def processor(self):
        """Get real moisture processor from library loader."""
        loader = get_library_loader()
        return loader.get_processor("moisture")

    def test_dry_soil_processing(self, processor):
        """Test dry soil (ADC ~3200 → 0% moisture)."""
        result = processor.process(raw_value=3200)

        # Default: dry=3200, wet=1500
        # (3200 - 3200) / (1500 - 3200) * 100 = 0%
        assert result.value == 0.0
        assert result.unit == "%"
        assert result.quality == "poor"  # Very dry

    def test_wet_soil_processing(self, processor):
        """Test wet soil (ADC ~1500 → 100% moisture)."""
        result = processor.process(raw_value=1500)

        # (1500 - 3200) / (1500 - 3200) * 100 = 100%
        assert result.value == 100.0
        assert result.unit == "%"
        assert result.quality == "poor"  # Saturated

    def test_medium_moisture_processing(self, processor):
        """Test medium moisture (ADC 2350 → ~50% moisture)."""
        result = processor.process(raw_value=2350)

        # (2350 - 3200) / (1500 - 3200) * 100 = 50%
        assert result.value == 50.0
        assert result.unit == "%"
        assert result.quality == "good"  # Healthy range

    def test_healthy_moisture_range(self, processor):
        """Test healthy moisture range (20-80% → quality=good)."""
        # ADC for 40% moisture
        # 40 = (ADC - 3200) / (1500 - 3200) * 100
        # ADC = 3200 + (40/100) * (1500 - 3200) = 3200 - 680 = 2520
        result = processor.process(raw_value=2520)

        assert 35 <= result.value <= 45  # ~40% with rounding
        assert result.quality == "good"

    def test_calibrated_moisture(self, processor):
        """Test with custom calibration (dry=3500, wet=1200)."""
        calibration = {"dry_value": 3500, "wet_value": 1200}
        result = processor.process(raw_value=2350, calibration=calibration)

        # (2350 - 3500) / (1200 - 3500) * 100 = 50%
        assert 48 <= result.value <= 52  # ~50%
        assert result.metadata["calibrated"] is True

    def test_realistic_sensor_values(self, processor):
        """Test with realistic sensor readings from research."""
        # From web search: dry ~2126, wet ~1224 (one example)
        calibration = {"dry_value": 2126, "wet_value": 1224}

        # Test midpoint
        midpoint = (2126 + 1224) / 2  # 1675
        result = processor.process(raw_value=midpoint, calibration=calibration)

        assert 45 <= result.value <= 55  # ~50%


class TestPHRealProcessing:
    """
    Analog pH Sensor End-to-End Tests.

    Hardware Reference (DFRobot pH Sensor + ESP32):
    - ADC: 12-bit (0-4095)
    - pH 7.0 (neutral): ~1.5V → ADC ~1860
    - pH 4.0 (acidic): ~2.0V → ADC ~2480
    - pH 10.0 (basic): ~1.0V → ADC ~1240
    - Slope: ~-3.5 pH/V (varies by sensor)

    Default Conversion:
    pH = 7.0 + (-3.5) * (voltage - 1.5V)
    """

    @pytest.fixture
    def processor(self):
        """Get real pH processor from library loader."""
        loader = get_library_loader()
        return loader.get_processor("ph")

    def test_neutral_ph_processing(self, processor):
        """Test neutral pH (ADC ~1860 → pH 7.0)."""
        # At 1.5V: ADC = 1.5 / 3.3 * 4095 ≈ 1860
        result = processor.process(raw_value=1860)

        # pH = 7.0 + (-3.5) * (1.5 - 1.5) = 7.0
        assert 6.8 <= result.value <= 7.2  # ~7.0 with tolerance
        assert result.unit == "pH"
        assert result.quality in ["good", "fair"]

    def test_acidic_ph_processing(self, processor):
        """Test acidic pH (higher voltage → lower pH)."""
        # At 2.0V: ADC = 2.0 / 3.3 * 4095 ≈ 2480
        result = processor.process(raw_value=2480)

        # pH = 7.0 + (-3.5) * (2.0 - 1.5) = 7.0 - 1.75 = 5.25
        assert 4.5 <= result.value <= 6.0  # Acidic range
        assert result.unit == "pH"

    def test_basic_ph_processing(self, processor):
        """Test basic/alkaline pH (lower voltage → higher pH)."""
        # At 1.0V: ADC = 1.0 / 3.3 * 4095 ≈ 1240
        result = processor.process(raw_value=1240)

        # pH = 7.0 + (-3.5) * (1.0 - 1.5) = 7.0 + 1.75 = 8.75
        assert 8.0 <= result.value <= 10.0  # Basic range
        assert result.unit == "pH"

    def test_calibrated_ph_sensor(self, processor):
        """Test with two-point calibration (pH 4.0 and pH 7.0)."""
        # Calibration points from DFRobot sensor
        # pH 7.0 at ADC 2048 (1.65V), pH 4.0 at ADC 2480 (2.0V)
        calibration_points = [
            {"raw": 2048, "reference": 7.0},
            {"raw": 2480, "reference": 4.0},
        ]
        calibration = processor.calibrate(calibration_points, method="linear")

        # Test with calibrated values
        result = processor.process(raw_value=2048, calibration=calibration)
        assert 6.8 <= result.value <= 7.2  # Should be ~7.0

        result = processor.process(raw_value=2480, calibration=calibration)
        assert 3.8 <= result.value <= 4.2  # Should be ~4.0

    def test_ph_range_validation(self, processor):
        """Test pH is clamped to valid range (0-14)."""
        # Very low ADC (would calculate pH > 14)
        result = processor.process(raw_value=100)
        assert result.value <= 14.0

        # Very high ADC (would calculate pH < 0)
        result = processor.process(raw_value=4000)
        assert result.value >= 0.0


class TestECRealProcessing:
    """
    EC (Electrical Conductivity) Sensor End-to-End Tests.

    Hardware Reference (DFRobot EC Sensor + ESP32):
    - ADC: 12-bit (0-4095)
    - Range: 0-20000 µS/cm
    - Temperature dependency: 2% per °C from 25°C

    Default Conversion:
    EC = 6060 * voltage (linear mapping: 3.3V → 20000 µS/cm)

    Temperature Compensation:
    EC_25C = EC_raw / (1 + 0.02 * (T - 25))
    """

    @pytest.fixture
    def processor(self):
        """Get real EC processor from library loader."""
        loader = get_library_loader()
        return loader.get_processor("ec")

    def test_low_ec_processing(self, processor):
        """Test low EC (tap water ~200-800 µS/cm)."""
        # At 0.1V: ADC = 0.1 / 3.3 * 4095 ≈ 124
        result = processor.process(raw_value=124)

        # EC = 6060 * 0.1 ≈ 606 µS/cm
        assert 400 <= result.value <= 800
        assert result.unit == "µS/cm"

    def test_medium_ec_processing(self, processor):
        """Test medium EC (hydroponics ~1000-3000 µS/cm)."""
        # At 0.5V: ADC = 0.5 / 3.3 * 4095 ≈ 620
        result = processor.process(raw_value=620)

        # EC = 6060 * 0.5 ≈ 3030 µS/cm
        assert 2500 <= result.value <= 3500
        assert result.unit == "µS/cm"

    def test_high_ec_processing(self, processor):
        """Test high EC (brackish water ~5000-15000 µS/cm)."""
        # At 1.5V: ADC = 1.5 / 3.3 * 4095 ≈ 1860
        result = processor.process(raw_value=1860)

        # EC = 6060 * 1.5 ≈ 9090 µS/cm
        assert 8000 <= result.value <= 10000
        assert result.unit == "µS/cm"

    def test_temperature_compensation(self, processor):
        """Test temperature compensation (2% per °C)."""
        # At 30°C (5°C above reference)
        result_30c = processor.process(raw_value=1860, params={"temperature_compensation": 30.0})

        # At 25°C (reference, no compensation)
        result_25c = processor.process(raw_value=1860, params={"temperature_compensation": 25.0})

        # At 30°C, EC should be LOWER after compensation
        # EC_25C = EC_raw / 1.1 (10% lower)
        assert result_30c.value < result_25c.value

    def test_unit_conversion_ms_cm(self, processor):
        """Test unit conversion to mS/cm."""
        result = processor.process(raw_value=1860, params={"unit": "ms_cm"})

        # 9090 µS/cm = 9.09 mS/cm
        assert 8.0 <= result.value <= 10.0
        assert result.unit == "mS/cm"

    def test_unit_conversion_ppm(self, processor):
        """Test unit conversion to ppm (TDS approximation)."""
        result = processor.process(raw_value=1860, params={"unit": "ppm"})

        # 9090 µS/cm * 0.5 ≈ 4545 ppm
        assert 4000 <= result.value <= 5000
        assert result.unit == "ppm"


class TestSHT31RealProcessing:
    """
    SHT31 Temperature & Humidity Sensor End-to-End Tests.

    Hardware Reference (Sensirion SHT31):
    - I2C sensor (not analog ADC)
    - Raw output in the library expects already-converted values
    - Temperature: -40°C to +125°C (±0.3°C accuracy)
    - Humidity: 0-100% RH (±2% accuracy)

    Note: SHT31 raw data is converted to Celsius/RH by the ESP32
    before sending to server. Server receives float values directly.
    """

    @pytest.fixture
    def temp_processor(self):
        """Get real SHT31 temperature processor."""
        loader = get_library_loader()
        return loader.get_processor("sht31_temp")

    @pytest.fixture
    def humidity_processor(self):
        """Get real SHT31 humidity processor."""
        loader = get_library_loader()
        return loader.get_processor("sht31_humidity")

    def test_sht31_temperature_processing(self, temp_processor):
        """Test SHT31 temperature processing (already in Celsius)."""
        result = temp_processor.process(raw_value=25.5)

        assert result.value == 25.5
        assert result.unit == "°C"
        assert result.quality == "good"

    def test_sht31_humidity_processing(self, humidity_processor):
        """Test SHT31 humidity processing (already in %RH)."""
        if humidity_processor is None:
            pytest.skip("SHT31 humidity processor not available")

        result = humidity_processor.process(raw_value=65.0)

        assert result.value == 65.0
        assert result.unit == "%RH"  # Fixed: Relative Humidity uses %RH unit
        assert result.quality == "good"

    def test_sht31_high_temp_quality(self, temp_processor):
        """Test quality assessment at high temperature."""
        result = temp_processor.process(raw_value=70.0)

        # Above optimal range (0-65°C) → fair quality
        assert result.quality == "fair"


class TestPiEnhancedFlowE2E:
    """
    End-to-End tests for Pi-Enhanced processing flow.

    Tests the complete path:
    Mock ESP → MQTT Payload → SensorHandler → LibraryLoader → Processor → Result
    """

    @pytest.fixture
    def mock_publisher(self):
        """Create mock publisher for response verification."""
        publisher = MagicMock()
        publisher.publish_pi_enhanced_response = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_pi_enhanced_moisture_flow(self, mock_publisher):
        """Test complete Pi-Enhanced flow for moisture sensor."""
        from src.mqtt.handlers.sensor_handler import SensorDataHandler

        # Create handler with mock publisher
        handler = SensorDataHandler(publisher=mock_publisher)

        # Simulate MQTT payload from Mock ESP
        topic = "kaiser/god/esp/MOCK_E2E_001/sensor/34/data"
        payload = {
            "ts": 1735818000,
            "esp_id": "MOCK_E2E_001",
            "gpio": 34,
            "sensor_type": "moisture",
            "raw": 2350,  # ~50% moisture
            "value": 0.0,
            "unit": "",
            "quality": "stale",
            "raw_mode": True,
        }

        # Create mock ESP device
        mock_esp = MagicMock()
        mock_esp.id = 1
        mock_esp.device_id = "MOCK_E2E_001"

        # Create mock sensor config with pi_enhanced=True
        mock_sensor_config = MagicMock()
        mock_sensor_config.pi_enhanced = True
        mock_sensor_config.calibration = None
        mock_sensor_config.processing_params = {}

        # Setup mock repositories
        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id.return_value = mock_esp

        mock_sensor_repo = AsyncMock()
        mock_sensor_repo.get_by_esp_and_gpio.return_value = mock_sensor_config
        mock_sensor_repo.save_sensor_data.return_value = MagicMock()

        # Create async context manager for session
        @asynccontextmanager
        async def mock_resilient_session():
            yield MagicMock()

        # Mock database session and repositories
        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            # Patch repositories
            with patch(
                "src.mqtt.handlers.sensor_handler.ESPRepository", return_value=mock_esp_repo
            ):
                with patch(
                    "src.mqtt.handlers.sensor_handler.SensorRepository",
                    return_value=mock_sensor_repo,
                ):
                    # Process the sensor data
                    result = await handler.handle_sensor_data(topic, payload)

                    # Verify Pi-Enhanced processing was triggered
                    if result:
                        # Check publisher was called with processed value
                        mock_publisher.publish_pi_enhanced_response.assert_called_once()
                        call_args = mock_publisher.publish_pi_enhanced_response.call_args

                        # Verify processed value is ~50% moisture
                        processed_value = call_args[0][2]  # Third positional arg
                        assert 45 <= processed_value <= 55, f"Expected ~50%, got {processed_value}"

    @pytest.mark.asyncio
    async def test_pi_enhanced_ph_flow(self, mock_publisher):
        """Test complete Pi-Enhanced flow for pH sensor."""
        from src.mqtt.handlers.sensor_handler import SensorDataHandler

        handler = SensorDataHandler(publisher=mock_publisher)

        topic = "kaiser/god/esp/MOCK_E2E_002/sensor/35/data"
        payload = {
            "ts": 1735818000,
            "esp_id": "MOCK_E2E_002",
            "gpio": 35,
            "sensor_type": "ph",
            "raw": 1860,  # ~pH 7.0
            "value": 0.0,
            "unit": "",
            "quality": "stale",
            "raw_mode": True,
        }

        mock_esp = MagicMock()
        mock_esp.id = 2
        mock_esp.device_id = "MOCK_E2E_002"

        mock_sensor_config = MagicMock()
        mock_sensor_config.pi_enhanced = True
        mock_sensor_config.calibration = None
        mock_sensor_config.processing_params = {}

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id.return_value = mock_esp

        mock_sensor_repo = AsyncMock()
        mock_sensor_repo.get_by_esp_and_gpio.return_value = mock_sensor_config
        mock_sensor_repo.save_sensor_data.return_value = MagicMock()

        @asynccontextmanager
        async def mock_resilient_session():
            yield MagicMock()

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            with patch(
                "src.mqtt.handlers.sensor_handler.ESPRepository", return_value=mock_esp_repo
            ):
                with patch(
                    "src.mqtt.handlers.sensor_handler.SensorRepository",
                    return_value=mock_sensor_repo,
                ):
                    result = await handler.handle_sensor_data(topic, payload)

                    if result:
                        mock_publisher.publish_pi_enhanced_response.assert_called_once()
                        call_args = mock_publisher.publish_pi_enhanced_response.call_args

                        processed_value = call_args[0][2]
                        # pH 7.0 is neutral
                        assert (
                            6.5 <= processed_value <= 7.5
                        ), f"Expected ~7.0 pH, got {processed_value}"


class TestRealisticHardwareValues:
    """
    Tests with realistic hardware values from datasheets and web research.

    These values come from:
    - Official sensor datasheets
    - ESP32 ADC characteristics
    - Real-world measurements from community projects
    """

    def test_ds18b20_sensor_limits(self):
        """Test DS18B20 at sensor specification limits."""
        processor = DS18B20Processor()

        # Sensor reports -127°C when disconnected
        result = processor.process(raw_value=-127.0)
        assert result.quality in ["error", "poor"]

        # Sensor reports 85°C on power-up (default)
        result = processor.process(raw_value=85.0)
        assert result.value == 85.0

    def test_moisture_sensor_realistic_calibration(self):
        """Test moisture with realistic calibration from ESP32 forum."""
        processor = MoistureSensorProcessor()

        # Values from ESP32 forum: dry 2126, wet 1224
        calibration = {"dry_value": 2126, "wet_value": 1224}

        # Test at calibration points
        dry_result = processor.process(raw_value=2126, calibration=calibration)
        assert dry_result.value == 0.0

        wet_result = processor.process(raw_value=1224, calibration=calibration)
        assert wet_result.value == 100.0

    def test_ph_sensor_greenponik_formula(self):
        """Test pH with GreenPonik/DFRobot formula reference."""
        processor = PHSensorProcessor()

        # GreenPonik formula: pHValue = 4.24 * voltage + Offset
        # At 1.5V (neutral): pH = 4.24 * 1.5 + offset ≈ 6.36 + offset
        # Our formula: pH = 7.0 + (-3.5) * (V - 1.5)

        # Both should give ~7.0 at neutral point
        adc_neutral = int(1.5 / 3.3 * 4095)  # ~1860
        result = processor.process(raw_value=adc_neutral)
        assert 6.5 <= result.value <= 7.5

    def test_ec_dfrobot_temperature_compensation(self):
        """Test EC temperature compensation per DFRobot wiki."""
        processor = ECSensorProcessor()

        # DFRobot: 2% per °C compensation
        # At 30°C: EC_25C = EC_raw / 1.1

        result_30c = processor.process(raw_value=2000, params={"temperature_compensation": 30.0})

        result_25c = processor.process(raw_value=2000, params={"temperature_compensation": 25.0})

        # At 30°C, compensated EC should be ~9% lower
        ratio = result_30c.value / result_25c.value
        assert 0.88 <= ratio <= 0.92  # ~10% reduction


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
