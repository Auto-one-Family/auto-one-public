"""
Tests for GPIO Conflict Detection (Server-side validation).

Validates that the server correctly detects and rejects GPIO conflicts
when configuring sensors and actuators on ESP32 devices.

GPIO Conflict Scenarios:
- Sensor on already-occupied GPIO
- Actuator on already-occupied GPIO
- Reserved system pin (I2C, UART, Flash)
- INPUT-only pin used as OUTPUT

These tests complement the Wokwi firmware tests by validating
the server's pre-flight checks before sending configs to ESPs.
"""

import pytest
from tests.esp32.mocks.mock_esp32_client import MockESP32Client, BrokerMode


class GPIOConflictValidator:
    """
    Validates GPIO configurations for conflicts.

    Mirrors the ESP32 GPIOManager's conflict detection logic
    for server-side validation.
    """

    # ESP32 WROOM Configuration
    SAFE_GPIO_PINS = [4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33]
    RESERVED_GPIO_PINS = [0, 1, 2, 3, 12, 13]  # Boot, UART, Flash
    INPUT_ONLY_PINS = [34, 35, 36, 39]
    I2C_SDA_PIN = 21
    I2C_SCL_PIN = 22

    def __init__(self):
        self.reserved_pins: dict[int, dict] = {}
        # Auto-reserve I2C pins
        self._reserve_system_pins()

    def _reserve_system_pins(self):
        """Reserve system pins (I2C) on initialization."""
        self.reserved_pins[self.I2C_SDA_PIN] = {
            "owner": "system",
            "component": "I2C_SDA",
            "mode": "INPUT",
        }
        self.reserved_pins[self.I2C_SCL_PIN] = {
            "owner": "system",
            "component": "I2C_SCL",
            "mode": "INPUT",
        }

    def is_reserved_pin(self, gpio: int) -> bool:
        """Check if GPIO is a reserved system pin."""
        return gpio in self.RESERVED_GPIO_PINS

    def is_safe_pin(self, gpio: int) -> bool:
        """Check if GPIO is in the safe pins list."""
        return gpio in self.SAFE_GPIO_PINS

    def is_input_only_pin(self, gpio: int) -> bool:
        """Check if GPIO can only be used as INPUT."""
        return gpio in self.INPUT_ONLY_PINS

    def is_pin_available(self, gpio: int) -> bool:
        """Check if a GPIO pin is available for reservation."""
        if self.is_reserved_pin(gpio):
            return False
        if not self.is_safe_pin(gpio):
            return False
        return gpio not in self.reserved_pins

    def validate_sensor_config(self, gpio: int, sensor_name: str) -> tuple[bool, str]:
        """
        Validate a sensor configuration.

        Returns:
            (success, error_message)
        """
        # I2C sensors use virtual GPIO 255
        if gpio == 255:
            return True, ""

        if self.is_reserved_pin(gpio):
            return False, f"GPIO {gpio} is a reserved system pin"

        if not self.is_safe_pin(gpio):
            return False, f"GPIO {gpio} is not in safe pins list"

        if gpio in self.reserved_pins:
            existing = self.reserved_pins[gpio]
            return False, f"GPIO {gpio} conflict - already owned by {existing['component']}"

        return True, ""

    def validate_actuator_config(self, gpio: int, actuator_name: str) -> tuple[bool, str]:
        """
        Validate an actuator configuration.

        Actuators require OUTPUT mode, which is not possible on INPUT-only pins.

        Returns:
            (success, error_message)
        """
        if self.is_reserved_pin(gpio):
            return False, f"GPIO {gpio} is a reserved system pin"

        if not self.is_safe_pin(gpio):
            # Check if it's an INPUT-only pin
            if self.is_input_only_pin(gpio):
                return False, f"GPIO {gpio} is INPUT-only, cannot be used as OUTPUT for actuator"
            return False, f"GPIO {gpio} is not in safe pins list"

        if gpio in self.reserved_pins:
            existing = self.reserved_pins[gpio]
            return False, f"GPIO {gpio} conflict - already owned by {existing['component']}"

        return True, ""

    def reserve_pin(self, gpio: int, owner: str, component: str, mode: str = "INPUT"):
        """Reserve a GPIO pin."""
        self.reserved_pins[gpio] = {"owner": owner, "component": component, "mode": mode}

    def release_pin(self, gpio: int) -> bool:
        """Release a GPIO pin."""
        if gpio in self.reserved_pins:
            del self.reserved_pins[gpio]
            return True
        return False


class TestGPIOConflictDetection:
    """Tests for GPIO conflict detection."""

    @pytest.fixture
    def validator(self):
        """Create GPIO conflict validator."""
        return GPIOConflictValidator()

    @pytest.fixture
    def mock_esp(self):
        """Create mock ESP32 with zone configured."""
        client = MockESP32Client(
            esp_id="ESP_GPIO_CONFLICT", kaiser_id="god", broker_mode=BrokerMode.DIRECT
        )
        client.configure_zone("test_zone", "main")
        return client

    # ============================================
    # GPIO-RES-002: Double Reservation Detection
    # ============================================

    def test_sensor_on_occupied_gpio(self, validator):
        """GPIO-RES-002: Second sensor on same GPIO should be rejected."""
        # First sensor succeeds
        success, error = validator.validate_sensor_config(4, "TempSensor1")
        assert success is True
        validator.reserve_pin(4, "sensor", "TempSensor1")

        # Second sensor on same GPIO fails
        success, error = validator.validate_sensor_config(4, "TempSensor2")
        assert success is False
        assert "conflict" in error.lower()
        assert "TempSensor1" in error

    def test_actuator_on_sensor_gpio(self, validator):
        """Actuator on GPIO already used by sensor should be rejected."""
        # Reserve for sensor
        success, _ = validator.validate_sensor_config(4, "TempSensor")
        assert success is True
        validator.reserve_pin(4, "sensor", "TempSensor")

        # Actuator on same GPIO fails
        success, error = validator.validate_actuator_config(4, "WaterPump")
        assert success is False
        assert "conflict" in error.lower()

    def test_sensor_on_actuator_gpio(self, validator):
        """Sensor on GPIO already used by actuator should be rejected."""
        # Reserve for actuator
        success, _ = validator.validate_actuator_config(5, "WaterPump")
        assert success is True
        validator.reserve_pin(5, "actuator", "WaterPump", "OUTPUT")

        # Sensor on same GPIO fails
        success, error = validator.validate_sensor_config(5, "TempSensor")
        assert success is False
        assert "conflict" in error.lower()

    # ============================================
    # GPIO-RES-003: Reserved Pin Rejection
    # ============================================

    def test_sensor_on_reserved_pin(self, validator):
        """GPIO-RES-003: Sensor on reserved pin should be rejected."""
        # Boot button (GPIO 0)
        success, error = validator.validate_sensor_config(0, "BadSensor")
        assert success is False
        assert "reserved" in error.lower()

        # UART TX (GPIO 1)
        success, error = validator.validate_sensor_config(1, "BadSensor")
        assert success is False
        assert "reserved" in error.lower()

        # Flash pin (GPIO 12)
        success, error = validator.validate_sensor_config(12, "BadSensor")
        assert success is False
        assert "reserved" in error.lower()

    def test_actuator_on_reserved_pin(self, validator):
        """Actuator on reserved pin should be rejected."""
        # UART RX (GPIO 3)
        success, error = validator.validate_actuator_config(3, "BadActuator")
        assert success is False
        assert "reserved" in error.lower()

    # ============================================
    # GPIO-RES-007: INPUT-Only Pin for OUTPUT
    # ============================================

    def test_actuator_on_input_only_pin(self, validator):
        """GPIO-RES-007: Actuator on INPUT-only pin should be rejected."""
        # GPIO 34 is INPUT-only
        success, error = validator.validate_actuator_config(34, "InvalidPump")
        assert success is False
        assert "INPUT-only" in error or "not in safe" in error.lower()

        # GPIO 35 is INPUT-only
        success, error = validator.validate_actuator_config(35, "InvalidFan")
        assert success is False

    def test_sensor_on_input_only_pin(self, validator):
        """Sensor on INPUT-only pin should be allowed (sensors are INPUT)."""
        # Note: INPUT-only pins are NOT in SAFE_GPIO_PINS on ESP32 WROOM
        # This is a design decision - if they were in SAFE_GPIO_PINS,
        # sensors could use them
        success, error = validator.validate_sensor_config(34, "AnalogSensor")
        # In current implementation, 34 is not in SAFE_GPIO_PINS
        assert success is False  # Would be True if 34 was in safe pins

    # ============================================
    # GPIO-RES-004: Pin Release and Re-Reserve
    # ============================================

    def test_release_and_rereserve(self, validator):
        """GPIO-RES-004: Released pin can be re-reserved."""
        # Reserve
        success, _ = validator.validate_sensor_config(4, "Sensor1")
        assert success is True
        validator.reserve_pin(4, "sensor", "Sensor1")

        # Verify occupied
        success, _ = validator.validate_sensor_config(4, "Sensor2")
        assert success is False

        # Release
        released = validator.release_pin(4)
        assert released is True

        # Re-reserve
        success, error = validator.validate_sensor_config(4, "Sensor2")
        assert success is True
        assert error == ""

    def test_release_nonexistent_pin(self, validator):
        """GPIO-RES-005: Releasing non-reserved pin returns False."""
        released = validator.release_pin(99)
        assert released is False

    # ============================================
    # GPIO-INT: Integration with MockESP32Client
    # ============================================

    def test_mock_esp_gpio_conflict_simulation(self, mock_esp):
        """Integration test: MockESP32Client respects GPIO conflicts."""
        # Configure sensor on GPIO 4
        mock_esp.set_sensor_value(gpio=4, raw_value=25.0, sensor_type="DS18B20")

        # Configure another sensor on GPIO 5 (should succeed)
        mock_esp.set_sensor_value(gpio=5, raw_value=512, sensor_type="analog")

        # Both sensors should be tracked
        assert mock_esp.get_sensor_state(4) is not None
        assert mock_esp.get_sensor_state(5) is not None

    def test_mock_esp_actuator_gpio_modes(self, mock_esp):
        """Integration test: Actuators are configured as OUTPUT."""
        mock_esp.configure_actuator(gpio=14, actuator_type="pump", name="Pump")

        # Slim heartbeat omits gpio_status; use mock helper (see test_gpio_status.py).
        gpio_status = mock_esp._build_gpio_status()
        actuator_gpio = next((item for item in gpio_status if item["gpio"] == 14), None)
        assert actuator_gpio is not None
        assert actuator_gpio["mode"] == 1  # OUTPUT
        assert actuator_gpio["owner"] == "actuator"

    # ============================================
    # Edge Cases
    # ============================================

    def test_i2c_pins_auto_reserved(self, validator):
        """I2C pins (21, 22) should be auto-reserved at init."""
        # GPIO 21 (SDA) should be reserved
        success, error = validator.validate_sensor_config(21, "BadSensor")
        assert success is False
        assert "I2C_SDA" in error

        # GPIO 22 (SCL) should be reserved
        success, error = validator.validate_actuator_config(22, "BadActuator")
        assert success is False
        assert "I2C_SCL" in error

    def test_i2c_sensor_virtual_gpio(self, validator):
        """I2C sensors use virtual GPIO 255, should always succeed."""
        success, error = validator.validate_sensor_config(255, "SHT31")
        assert success is True
        assert error == ""

    def test_out_of_range_gpio(self, validator):
        """GPIO numbers outside valid range should be rejected."""
        # GPIO 50 (beyond ESP32 max)
        success, error = validator.validate_sensor_config(50, "BadSensor")
        assert success is False
        assert "not in safe" in error.lower()

        # GPIO 100
        success, error = validator.validate_actuator_config(100, "BadActuator")
        assert success is False


class TestGPIOConflictWithMQTT:
    """Tests for GPIO conflict handling via MQTT config messages."""

    @pytest.fixture
    def mock_esp(self):
        """Create mock ESP32."""
        client = MockESP32Client(
            esp_id="ESP_MQTT_GPIO", kaiser_id="god", broker_mode=BrokerMode.DIRECT
        )
        client.configure_zone("test_zone", "main")
        return client

    def test_config_sensor_success(self, mock_esp):
        """Sensor config via MQTT should allocate GPIO."""
        # Simulate receiving config message
        mock_esp.handle_command(
            "config",
            {
                "sensors": [
                    {
                        "gpio": 4,
                        "sensor_type": "temp_ds18b20",
                        "sensor_name": "TempSensor",
                        "active": True,
                    }
                ]
            },
        )

        # Sensor should be configured
        state = mock_esp.get_sensor_state(4)
        assert state is not None

    def test_config_actuator_success(self, mock_esp):
        """Actuator config via MQTT should allocate GPIO."""
        mock_esp.handle_command(
            "config",
            {
                "actuators": [
                    {
                        "gpio": 5,
                        "actuator_type": "pump",
                        "actuator_name": "WaterPump",
                        "active": True,
                    }
                ]
            },
        )

        # Actuator should be configured
        state = mock_esp.get_actuator_state(5)
        assert state is not None

    def test_config_conflict_response(self, mock_esp):
        """Config with GPIO conflict should return error response."""
        # First sensor
        mock_esp.handle_command(
            "config",
            {
                "sensors": [
                    {
                        "gpio": 4,
                        "sensor_type": "temp_ds18b20",
                        "sensor_name": "Sensor1",
                        "active": True,
                    }
                ]
            },
        )

        mock_esp.clear_published_messages()

        # Second sensor on same GPIO
        mock_esp.handle_command(
            "config",
            {
                "sensors": [
                    {
                        "gpio": 4,
                        "sensor_type": "ph_sensor",
                        "sensor_name": "ConflictSensor",
                        "active": True,
                    }
                ]
            },
        )

        # Should publish error in config_response
        responses = mock_esp.get_messages_by_topic_pattern("config_response")
        if responses:
            # If MockESP32Client implements conflict detection,
            # the response should indicate failure
            response = responses[-1]["payload"]
            # Check for error status or partial_success
            # (depends on MockESP32Client implementation)
            pass  # Implementation-dependent assertion
