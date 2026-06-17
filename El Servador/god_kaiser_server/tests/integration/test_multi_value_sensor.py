"""
Integration tests for multi-value sensor handling.

Tests the complete flow from ESP32 sensor reading to server processing
for multi-value sensors like SHT31.
"""

import pytest
from src.sensors.library_loader import get_library_loader
from src.sensors.sensor_type_registry import (
    normalize_sensor_type,
    get_multi_value_sensor_def,
    get_all_value_types_for_device,
)


class TestMultiValueSensorProcessing:
    """Test processing of multi-value sensor data."""

    def test_sht31_temperature_processing(self):
        """Test processing SHT31 temperature reading."""
        loader = get_library_loader()

        # Normalize sensor type
        normalized = normalize_sensor_type("temperature_sht31")
        assert normalized == "sht31_temp"

        # Get processor
        processor = loader.get_processor("temperature_sht31")
        assert processor is not None
        assert processor.get_sensor_type() == "sht31_temp"

        # Process a temperature reading (23.5°C as raw value)
        result = processor.process(raw_value=23.5)
        assert result.value == pytest.approx(23.5, rel=0.01)
        assert result.unit == "°C"
        assert result.quality in ["good", "fair", "poor"]

    def test_sht31_humidity_processing(self):
        """Test processing SHT31 humidity reading."""
        loader = get_library_loader()

        # Normalize sensor type
        normalized = normalize_sensor_type("humidity_sht31")
        assert normalized == "sht31_humidity"

        # Get processor
        processor = loader.get_processor("humidity_sht31")
        assert processor is not None
        assert processor.get_sensor_type() == "sht31_humidity"

        # Process a humidity reading (65.5% RH as raw value)
        result = processor.process(raw_value=65.5)
        assert result.value == pytest.approx(65.5, rel=0.01)
        assert result.unit == "%RH"
        assert result.quality in ["good", "fair", "poor"]

    def test_multi_value_sensor_definition(self):
        """Test that SHT31 definition includes both values."""
        def_ = get_multi_value_sensor_def("sht31")
        assert def_ is not None

        value_types = [v["sensor_type"] for v in def_["values"]]
        assert "sht31_temp" in value_types
        assert "sht31_humidity" in value_types

    def test_all_value_types_available(self):
        """Test that all SHT31 value types have processors."""
        loader = get_library_loader()
        value_types = get_all_value_types_for_device("sht31")

        assert len(value_types) == 2

        for value_type in value_types:
            processor = loader.get_processor(value_type)
            assert processor is not None, f"Processor not found for {value_type}"

    def test_sensor_type_mapping_consistency(self):
        """Test that ESP32 sensor types map correctly to server processors."""
        loader = get_library_loader()

        # Test SHT31 mappings
        esp32_types = ["temperature_sht31", "humidity_sht31"]
        server_types = ["sht31_temp", "sht31_humidity"]

        for esp32_type, expected_server_type in zip(esp32_types, server_types):
            normalized = normalize_sensor_type(esp32_type)
            assert normalized == expected_server_type

            processor = loader.get_processor(esp32_type)
            assert processor is not None
            assert processor.get_sensor_type() == expected_server_type

    def test_bmp280_multi_value_support(self):
        """Test BMP280 multi-value sensor support (Phase 2)."""
        def_ = get_multi_value_sensor_def("bmp280")
        assert def_ is not None

        value_types = [v["sensor_type"] for v in def_["values"]]
        assert "bmp280_pressure" in value_types
        assert "bmp280_temp" in value_types

    def test_single_value_sensor_still_works(self):
        """Test that single-value sensors still work correctly."""
        loader = get_library_loader()

        # DS18B20 should still work
        processor = loader.get_processor("temperature_ds18b20")
        assert processor is not None
        assert processor.get_sensor_type() == "ds18b20"

        result = processor.process(raw_value=20.5)
        assert result.value == pytest.approx(20.5, rel=0.01)
        assert result.unit == "°C"
