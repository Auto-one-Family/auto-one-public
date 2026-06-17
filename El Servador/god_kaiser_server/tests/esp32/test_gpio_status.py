"""
Tests for GPIO status generation in Mock ESP32 client.

Heartbeat payloads are slimmed and no longer include gpio_status fields.
GPIO status remains available via the internal builder used by API paths.
"""

import pytest
from tests.esp32.mocks.mock_esp32_client import MockESP32Client, BrokerMode


@pytest.fixture
def mock_esp():
    """Create mock ESP32 with some sensors and actuators."""
    client = MockESP32Client(
        esp_id="MOCK_GPIO_TEST", kaiser_id="god", broker_mode=BrokerMode.DIRECT
    )
    return client


class TestMockHeartbeatGpioStatus:
    """Test GPIO status generation and heartbeat payload contract."""

    def test_heartbeat_omits_gpio_fields(self, mock_esp):
        """Slim heartbeat must not include legacy GPIO status fields."""
        # Add a sensor
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")

        # Trigger heartbeat
        mock_esp.handle_command("heartbeat", {})

        # Get the published heartbeat
        messages = mock_esp.get_messages_by_topic_pattern("heartbeat")
        assert len(messages) > 0

        heartbeat = messages[-1]["payload"]
        assert "gpio_status" not in heartbeat
        assert "gpio_reserved_count" not in heartbeat

    def test_gpio_status_includes_sensors(self, mock_esp):
        """GPIO status builder includes registered sensors."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock_esp.set_sensor_value(gpio=5, raw_value=25.0, sensor_type="analog")
        gpio_status = mock_esp._build_gpio_status()
        gpio_pins = [item["gpio"] for item in gpio_status]
        assert 4 in gpio_pins, "Sensor GPIO 4 not in gpio_status"
        assert 5 in gpio_pins, "Sensor GPIO 5 not in gpio_status"

    def test_gpio_status_includes_actuators(self, mock_esp):
        """GPIO status builder includes registered actuators."""
        mock_esp.configure_zone("test_zone", "main")  # Required for actuator control
        mock_esp.configure_actuator(gpio=14, actuator_type="pump")
        mock_esp.configure_actuator(gpio=15, actuator_type="valve")
        gpio_status = mock_esp._build_gpio_status()
        actuator_items = [item for item in gpio_status if item["owner"] == "actuator"]
        gpio_pins = [item["gpio"] for item in actuator_items]
        assert 14 in gpio_pins, "Actuator GPIO 14 not in gpio_status"
        assert 15 in gpio_pins, "Actuator GPIO 15 not in gpio_status"

    def test_gpio_status_owner_types(self, mock_esp):
        """GPIO status has expected owner types for mixed setup."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="SHT31")  # I2C sensor
        mock_esp.configure_zone("test_zone", "main")
        mock_esp.configure_actuator(gpio=14, actuator_type="pump")
        gpio_status = mock_esp._build_gpio_status()
        owners = set(item["owner"] for item in gpio_status)
        assert "sensor" in owners, "No sensor owner in gpio_status"
        assert "actuator" in owners, "No actuator owner in gpio_status"
        # I2C sensor should trigger system pins
        assert "system" in owners, "No system owner (I2C) in gpio_status"

    def test_gpio_status_list_is_consistent(self, mock_esp):
        """Builder returns a concrete list with stable count semantics."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock_esp.set_sensor_value(gpio=5, raw_value=25.0, sensor_type="analog")
        gpio_status = mock_esp._build_gpio_status()
        assert isinstance(gpio_status, list)
        assert len(gpio_status) >= 2

    def test_emergency_stopped_actuator_marked_safe(self, mock_esp):
        """Emergency-stopped actuators have safe=True in GPIO status builder."""
        mock_esp.configure_zone("test_zone", "main")
        mock_esp.configure_actuator(gpio=14, actuator_type="pump")

        # Emergency stop
        mock_esp.handle_command("emergency_stop", {"reason": "test"})

        gpio_status = mock_esp._build_gpio_status()
        actuator_status = next((item for item in gpio_status if item["gpio"] == 14), None)
        assert actuator_status is not None
        assert actuator_status["safe"] is True, "Emergency-stopped actuator should have safe=True"

    def test_i2c_pins_for_i2c_sensors(self, mock_esp):
        """I2C sensors reserve I2C system pins in GPIO status builder."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="SHT31")  # I2C sensor
        gpio_status = mock_esp._build_gpio_status()
        system_pins = [item for item in gpio_status if item["owner"] == "system"]
        gpio_pins = [item["gpio"] for item in system_pins]

        assert 21 in gpio_pins, "I2C_SDA (GPIO 21) should be in gpio_status"
        assert 22 in gpio_pins, "I2C_SCL (GPIO 22) should be in gpio_status"

    def test_gpio_status_empty_when_no_devices(self, mock_esp):
        """Empty setup returns empty gpio_status list."""
        assert mock_esp._build_gpio_status() == []

    def test_sensor_mode_is_input(self, mock_esp):
        """Sensors have mode=0 (INPUT)."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        gpio_status = mock_esp._build_gpio_status()
        sensor_status = next((item for item in gpio_status if item["gpio"] == 4), None)
        assert sensor_status is not None
        assert sensor_status["mode"] == 0, "Sensor should have mode=0 (INPUT)"

    def test_actuator_mode_is_output(self, mock_esp):
        """Actuators have mode=1 (OUTPUT)."""
        mock_esp.configure_zone("test_zone", "main")
        mock_esp.configure_actuator(gpio=14, actuator_type="pump")
        gpio_status = mock_esp._build_gpio_status()
        actuator_status = next((item for item in gpio_status if item["gpio"] == 14), None)
        assert actuator_status is not None
        assert actuator_status["mode"] == 1, "Actuator should have mode=1 (OUTPUT)"

    def test_non_i2c_sensor_no_system_pins(self, mock_esp):
        """Test that non-I2C sensors don't add I2C system pins."""
        mock_esp.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")  # OneWire, not I2C
        mock_esp.set_sensor_value(gpio=5, raw_value=512, sensor_type="analog")  # Analog, not I2C

        gpio_status = mock_esp._build_gpio_status()
        system_pins = [item for item in gpio_status if item["owner"] == "system"]
        assert len(system_pins) == 0, "Non-I2C sensors should not add system pins"
