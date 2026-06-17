"""
Unit tests for GPIO status validation (Phase 1 + Phase 2).

Tests the Pydantic models GpioStatusItem and GpioStatusList.
These models are the contract between ESP32 and Server.

Phase 2 (2026-01-15): Added tests for Arduino pinMode normalization.
ESP32 sends Arduino values (1, 2, 5), server normalizes to protocol (0, 1, 2).
"""

import pytest
from pydantic import ValidationError
from src.schemas.esp import GpioStatusItem, GpioStatusList


class TestGpioStatusItem:
    """Tests for GpioStatusItem Pydantic model."""

    def test_valid_sensor_gpio(self):
        """Test valid sensor GPIO status."""
        item = GpioStatusItem(
            gpio=4,
            owner="sensor",
            component="DS18B20",
            mode=0,  # INPUT for sensors (protocol value)
            safe=False,
        )
        assert item.gpio == 4
        assert item.owner == "sensor"
        assert item.component == "DS18B20"
        assert item.mode == 0
        assert item.safe is False

    def test_valid_actuator_gpio(self):
        """Test valid actuator GPIO status (using Arduino OUTPUT value)."""
        item = GpioStatusItem(
            gpio=14,
            owner="actuator",
            component="pump_main",
            mode=2,  # Arduino OUTPUT (2) → normalizes to Protocol OUTPUT (1)
            safe=False,
        )
        assert item.owner == "actuator"
        assert item.mode == 1, "Arduino OUTPUT (2) should normalize to Protocol OUTPUT (1)"

    def test_valid_system_gpio(self):
        """Test valid system GPIO status (I2C, using Arduino INPUT value)."""
        item = GpioStatusItem(
            gpio=21,
            owner="system",
            component="I2C_SDA",
            mode=1,  # Arduino INPUT (1) → normalizes to Protocol INPUT (0)
            safe=False,
        )
        assert item.owner == "system"
        assert item.mode == 0, "Arduino INPUT (1) should normalize to Protocol INPUT (0)"

    def test_invalid_owner_rejected(self):
        """Test that invalid owner is rejected by regex pattern."""
        with pytest.raises(ValidationError) as exc:
            GpioStatusItem(
                gpio=4,
                owner="invalid",  # Must be sensor/actuator/system
                component="test",
                mode=1,
                safe=False,
            )
        assert "owner" in str(exc.value).lower()

    def test_gpio_range_validation(self):
        """Test GPIO pin range (0-48)."""
        # Valid - min
        item = GpioStatusItem(gpio=0, owner="sensor", component="test", mode=0, safe=False)
        assert item.gpio == 0

        # Valid - max
        item = GpioStatusItem(gpio=48, owner="sensor", component="test", mode=0, safe=False)
        assert item.gpio == 48

        # Invalid - too high
        with pytest.raises(ValidationError):
            GpioStatusItem(gpio=49, owner="sensor", component="test", mode=0, safe=False)

        # Invalid - negative
        with pytest.raises(ValidationError):
            GpioStatusItem(gpio=-1, owner="sensor", component="test", mode=0, safe=False)

    def test_protocol_mode_zero_passes_through(self):
        """Test protocol mode value 0 passes through unchanged (no Arduino equivalent)."""
        item = GpioStatusItem(gpio=4, owner="sensor", component="test", mode=0, safe=False)
        assert item.mode == 0, "Protocol INPUT (0) should pass through unchanged"

    def test_arduino_mode_one_normalizes_to_zero(self):
        """Arduino INPUT (1) normalizes to Protocol INPUT (0)."""
        item = GpioStatusItem(gpio=4, owner="sensor", component="test", mode=1, safe=False)
        assert item.mode == 0, "Arduino INPUT (1) should normalize to Protocol INPUT (0)"

    def test_arduino_mode_two_normalizes_to_one(self):
        """Arduino OUTPUT (2) normalizes to Protocol OUTPUT (1)."""
        item = GpioStatusItem(gpio=4, owner="actuator", component="test", mode=2, safe=False)
        assert item.mode == 1, "Arduino OUTPUT (2) should normalize to Protocol OUTPUT (1)"

    def test_component_max_length(self):
        """Test component name max length (32 chars)."""
        # Valid - exactly 32 chars
        item = GpioStatusItem(
            gpio=4,
            owner="sensor",
            component="a" * 32,
            mode=0,  # Protocol INPUT (0) - passes through unchanged
            safe=False,
        )
        assert len(item.component) == 32

        # Invalid - too long
        with pytest.raises(ValidationError):
            GpioStatusItem(
                gpio=4, owner="sensor", component="a" * 33, mode=0, safe=False  # Protocol INPUT (0)
            )


class TestGpioModeNormalization:
    """
    Test suite for GPIO mode normalization (Phase 2).

    Arduino pinMode values (1, 2, 5) are normalized to protocol values (0, 1, 2).
    This allows deployed ESPs to send raw Arduino values without breaking.
    """

    def test_arduino_input_normalized_to_zero(self):
        """Arduino INPUT (1) should normalize to protocol INPUT (0)."""
        item = GpioStatusItem(
            gpio=21, owner="sensor", component="DHT22", mode=1, safe=False  # Arduino INPUT (0x01)
        )
        assert item.mode == 0, "Arduino INPUT (1) should normalize to protocol 0"

    def test_arduino_output_normalized_to_one(self):
        """Arduino OUTPUT (2) should normalize to protocol OUTPUT (1)."""
        item = GpioStatusItem(
            gpio=22,
            owner="actuator",
            component="Relay",
            mode=2,  # Arduino OUTPUT (0x02)
            safe=False,
        )
        assert item.mode == 1, "Arduino OUTPUT (2) should normalize to protocol 1"

    def test_arduino_input_pullup_normalized_to_two(self):
        """Arduino INPUT_PULLUP (5) should normalize to protocol INPUT_PULLUP (2)."""
        item = GpioStatusItem(
            gpio=23,
            owner="sensor",
            component="Button",
            mode=5,  # Arduino INPUT_PULLUP (0x05)
            safe=True,
        )
        assert item.mode == 2, "Arduino INPUT_PULLUP (5) should normalize to protocol 2"

    def test_protocol_zero_passes_through(self):
        """
        Protocol INPUT (0) passes through unchanged.

        Value 0 has no Arduino equivalent, so it's always treated as
        already-normalized Protocol INPUT.
        """
        item = GpioStatusItem(gpio=21, owner="system", component="Test", mode=0, safe=False)
        assert item.mode == 0, "Protocol INPUT (0) should pass through unchanged"

    def test_normalization_is_idempotent(self):
        """
        After normalization, re-validating the normalized value should be stable.

        Protocol values 0, 1, 2 (after normalization) should stay stable:
        - 0 → 0 (no Arduino equivalent)
        - 1 → 0 (would be treated as Arduino INPUT, but we document this)
        - 2 → 1 (would be treated as Arduino OUTPUT, but we document this)

        Note: This test documents that values 1 and 2 are ALWAYS treated as
        Arduino values. If a system needs to send already-normalized data,
        it should not re-validate through this model.
        """
        # Value 0 is stable
        item = GpioStatusItem(gpio=21, owner="system", component="Test", mode=0, safe=False)
        assert item.mode == 0

        # Re-validate: 0 → 0 (stable)
        item2 = GpioStatusItem(
            gpio=21, owner="system", component="Test", mode=item.mode, safe=False
        )
        assert item2.mode == 0

    def test_unknown_mode_passes_through_with_warning(self, caplog):
        """Unknown mode values should pass through but log warning."""
        import logging

        caplog.set_level(logging.WARNING)

        item = GpioStatusItem(
            gpio=21,
            owner="system",
            component="Unknown",
            mode=99,  # Unknown mode - not Arduino or protocol
            safe=False,
        )
        assert item.mode == 99, "Unknown mode should pass through unchanged"
        assert "Unknown GPIO mode value: 99" in caplog.text

    def test_mode_out_of_uint8_range_rejected(self):
        """Mode values >255 should be rejected (uint8 overflow)."""
        with pytest.raises(ValidationError) as exc_info:
            GpioStatusItem(
                gpio=21, owner="system", component="Test", mode=256, safe=False  # Exceeds uint8
            )
        error_str = str(exc_info.value)
        assert "mode" in error_str.lower()
        assert "255" in error_str or "less than" in error_str.lower()

    def test_negative_mode_rejected(self):
        """Negative mode values should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GpioStatusItem(gpio=21, owner="system", component="Test", mode=-1, safe=False)
        error_str = str(exc_info.value)
        assert "mode" in error_str.lower()
        assert "0" in error_str or "greater" in error_str.lower()

    def test_real_esp_heartbeat_scenario(self):
        """
        Test realistic ESP32 heartbeat scenario.

        ESP32 sends:
          - mode=5 for INPUT_PULLUP sensors (OneWire, I2C)
          - mode=2 for OUTPUT actuators (relays, pumps)
          - mode=1 for INPUT sensors (ADC, digital)

        Server should normalize all to protocol values.
        """
        # Simulate ESP32 heartbeat gpio_status array
        esp_heartbeat_gpio = [
            # OneWire bus - ESP sends mode=5 (INPUT_PULLUP)
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 5, "safe": True},
            # I2C bus - ESP sends mode=1 (INPUT)
            {"gpio": 21, "owner": "system", "component": "I2C_SDA", "mode": 1, "safe": False},
            {"gpio": 22, "owner": "system", "component": "I2C_SCL", "mode": 1, "safe": False},
            # Relay output - ESP sends mode=2 (OUTPUT)
            {"gpio": 14, "owner": "actuator", "component": "pump_1", "mode": 2, "safe": False},
            # ADC input - ESP sends mode=1 (INPUT)
            {"gpio": 32, "owner": "sensor", "component": "EC_Sensor", "mode": 1, "safe": False},
        ]

        # Expected protocol values after normalization
        expected_modes = {
            4: 2,  # INPUT_PULLUP: 5 → 2
            21: 0,  # INPUT: 1 → 0
            22: 0,  # INPUT: 1 → 0
            14: 1,  # OUTPUT: 2 → 1
            32: 0,  # INPUT: 1 → 0
        }

        for gpio_data in esp_heartbeat_gpio:
            item = GpioStatusItem(**gpio_data)
            gpio_num = gpio_data["gpio"]
            expected = expected_modes[gpio_num]
            assert item.mode == expected, (
                f"GPIO {gpio_num} ({gpio_data['component']}): "
                f"mode {gpio_data['mode']} should normalize to {expected}, got {item.mode}"
            )


class TestGpioStatusList:
    """Tests for GpioStatusList Pydantic model."""

    def test_empty_list_valid(self):
        """Test empty GPIO status list is valid (no sensors/actuators)."""
        gpio_list = GpioStatusList(gpio_status=[], gpio_reserved_count=0)
        assert len(gpio_list.gpio_status) == 0
        assert gpio_list.gpio_reserved_count == 0

    def test_full_list_valid(self):
        """Test full GPIO status list with all owner types."""
        items = [
            GpioStatusItem(gpio=4, owner="sensor", component="DS18B20", mode=0, safe=False),
            GpioStatusItem(gpio=14, owner="actuator", component="pump", mode=1, safe=False),
            GpioStatusItem(gpio=21, owner="system", component="I2C_SDA", mode=1, safe=False),
        ]
        gpio_list = GpioStatusList(gpio_status=items, gpio_reserved_count=3)
        assert len(gpio_list.gpio_status) == 3
        assert gpio_list.gpio_reserved_count == 3

    def test_count_mismatch_handled(self):
        """Test that count mismatch is handled gracefully."""
        gpio_list = GpioStatusList(
            gpio_status=[
                GpioStatusItem(gpio=4, owner="sensor", component="test", mode=0, safe=False)
            ],
            gpio_reserved_count=5,  # Wrong count - should be accepted
        )
        # Should still work - count is just metadata
        assert len(gpio_list.gpio_status) == 1
