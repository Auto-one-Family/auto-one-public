"""
Integration tests for GPIO status in heartbeat flow.

Tests the complete flow from MQTT heartbeat to database storage.

Phase 2 (2026-01-15): Added tests for Arduino pinMode normalization.
ESP32 sends raw Arduino values (1, 2, 5), server normalizes to protocol (0, 1, 2).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.mqtt.handlers.heartbeat_handler import get_heartbeat_handler


@pytest.fixture
def heartbeat_handler():
    """Get the singleton heartbeat handler."""
    return get_heartbeat_handler()


@pytest.fixture
def sample_heartbeat_with_gpio():
    """Sample heartbeat payload with GPIO status (protocol values - legacy format)."""
    return {
        "esp_id": "ESP_TEST123",
        "zone_id": "test_zone",
        "master_zone_id": "main",
        "zone_assigned": True,
        "ts": 1704722400,
        "uptime": 3600,
        "heap_free": 200000,
        "wifi_rssi": -65,
        "sensor_count": 2,
        "actuator_count": 1,
        "gpio_status": [
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 0, "safe": False},
            {"gpio": 5, "owner": "sensor", "component": "SHT31", "mode": 0, "safe": False},
            {"gpio": 14, "owner": "actuator", "component": "pump_1", "mode": 1, "safe": False},
            {"gpio": 21, "owner": "system", "component": "I2C_SDA", "mode": 1, "safe": False},
            {"gpio": 22, "owner": "system", "component": "I2C_SCL", "mode": 1, "safe": False},
        ],
        "gpio_reserved_count": 5,
    }


@pytest.fixture
def sample_heartbeat_with_arduino_modes():
    """
    Sample heartbeat payload with Arduino pinMode values (real ESP32 format).

    Arduino Core definitions:
        INPUT           = 0x01 (1)
        OUTPUT          = 0x02 (2)
        INPUT_PULLUP    = 0x05 (5)
    """
    return {
        "esp_id": "ESP_00000001",
        "zone_id": "wokwi_zone",
        "master_zone_id": "",
        "zone_assigned": True,
        "ts": 1768443787,
        "uptime": 1000,
        "heap_free": 200000,
        "wifi_rssi": -75,
        "sensor_count": 2,
        "actuator_count": 1,
        "gpio_status": [
            # OneWire bus - INPUT_PULLUP (Arduino: 5)
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 5, "safe": True},
            # I2C bus - INPUT (Arduino: 1)
            {"gpio": 21, "owner": "system", "component": "I2C_SDA", "mode": 1, "safe": False},
            {"gpio": 22, "owner": "system", "component": "I2C_SCL", "mode": 1, "safe": False},
            # Relay - OUTPUT (Arduino: 2)
            {"gpio": 14, "owner": "actuator", "component": "pump_main", "mode": 2, "safe": False},
            # ADC sensor - INPUT (Arduino: 1)
            {"gpio": 32, "owner": "sensor", "component": "EC_Probe", "mode": 1, "safe": False},
        ],
        "gpio_reserved_count": 5,
    }


@pytest.fixture
def sample_heartbeat_without_gpio():
    """Sample heartbeat without GPIO status (backward compatibility)."""
    return {
        "esp_id": "ESP_OLD_FW",
        "zone_id": "legacy_zone",
        "zone_assigned": True,
        "ts": 1704722400,
        "uptime": 3600,
        "heap_free": 200000,
        "wifi_rssi": -65,
        "sensor_count": 1,
        "actuator_count": 0,
    }


class TestHeartbeatGpioValidation:
    """Test GPIO validation in heartbeat handler."""

    def test_validate_gpio_status_valid(self, heartbeat_handler, sample_heartbeat_with_gpio):
        """Test validation of valid GPIO status."""
        result = heartbeat_handler._validate_gpio_status(
            sample_heartbeat_with_gpio["gpio_status"],
            sample_heartbeat_with_gpio["gpio_reserved_count"],
            "ESP_TEST123",
        )

        assert result is not None
        assert len(result["gpio_status"]) == 5
        assert result["gpio_reserved_count"] == 5

    def test_validate_gpio_status_invalid_item_skipped(self, heartbeat_handler):
        """Test that invalid GPIO items are skipped, not rejected."""
        gpio_status = [
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 0, "safe": False},
            {
                "gpio": 99,
                "owner": "invalid",
                "component": "bad",
                "mode": 99,
                "safe": "wrong",
            },  # Invalid
            {"gpio": 5, "owner": "actuator", "component": "pump", "mode": 1, "safe": False},
        ]

        result = heartbeat_handler._validate_gpio_status(gpio_status, 3, "ESP_TEST123")

        assert result is not None
        assert len(result["gpio_status"]) == 2  # Invalid item skipped
        assert result["gpio_reserved_count"] == 2  # Actual count, not reported count

    def test_validate_gpio_status_empty_list(self, heartbeat_handler):
        """Test validation of empty GPIO status list (no sensors)."""
        result = heartbeat_handler._validate_gpio_status([], 0, "ESP_TEST123")

        assert result is not None
        assert result["gpio_status"] == []
        assert result["gpio_reserved_count"] == 0

    def test_bus_gpio_mismatch_demoted_to_debug(self, heartbeat_handler, caplog):
        """Bus-GPIO validation failures should produce DEBUG, not WARNING (F9 fix)."""
        import logging

        caplog.set_level(logging.DEBUG)

        # 2 bus-GPIOs with invalid owner format (missing bus/ prefix in one)
        # that will fail validation, plus 2 valid items
        gpio_status = [
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 0, "safe": False},
            {"gpio": 14, "owner": "actuator", "component": "pump", "mode": 1, "safe": False},
            # Bus-GPIO that will fail validation (owner pattern doesn't match)
            {
                "gpio": 21,
                "owner": "bus/i2c/sda",
                "component": "I2C_SDA",
                "mode": 1,
                "safe": False,
                "extra_field_that_breaks": True,
            },
        ]

        # Report count includes all 3, but if bus-GPIO fails validation → mismatch = 1
        # With bus_gpio_count = 1, mismatch (1) <= bus_gpio_count (1) → DEBUG not WARNING
        result = heartbeat_handler._validate_gpio_status(gpio_status, 3, "ESP_BUS_TEST")

        # Regardless of bus-GPIO validation outcome, no WARNING for bus-GPIO-sized mismatches
        warning_messages = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "GPIO count mismatch" in r.message
        ]
        # If all items validated (bus/i2c/sda is valid per F5), mismatch = 0 → no log at all
        # If bus-GPIO failed, mismatch = 1 <= bus_gpio_count = 1 → DEBUG only
        for msg in warning_messages:
            assert (
                "GPIO count mismatch" not in msg.message
            ), "Bus-GPIO mismatch should be DEBUG, not WARNING"

    def test_genuine_mismatch_still_warns(self, heartbeat_handler, caplog):
        """Non-bus-GPIO mismatches should still produce WARNING."""
        import logging

        caplog.set_level(logging.WARNING)

        gpio_status = [
            {"gpio": 4, "owner": "sensor", "component": "DS18B20", "mode": 0, "safe": False},
        ]

        # Report says 3 reserved, but only 1 valid item, no bus-GPIOs → genuine mismatch
        result = heartbeat_handler._validate_gpio_status(gpio_status, 3, "ESP_GENUINE")

        assert result is not None
        warning_messages = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "GPIO count mismatch" in r.message
        ]
        assert len(warning_messages) == 1, "Genuine mismatch should produce WARNING"


class TestHeartbeatGpioIntegration:
    """Test GPIO status in complete heartbeat flow."""

    @pytest.mark.asyncio
    async def test_heartbeat_with_gpio_format(self, sample_heartbeat_with_gpio):
        """Test that heartbeat with GPIO format is valid."""
        # Verify GPIO status structure
        assert "gpio_status" in sample_heartbeat_with_gpio
        assert "gpio_reserved_count" in sample_heartbeat_with_gpio
        assert len(sample_heartbeat_with_gpio["gpio_status"]) == 5
        assert sample_heartbeat_with_gpio["gpio_reserved_count"] == 5

        # Verify each GPIO item has required fields
        for item in sample_heartbeat_with_gpio["gpio_status"]:
            assert "gpio" in item
            assert "owner" in item
            assert "component" in item
            assert "mode" in item
            assert "safe" in item

    @pytest.mark.asyncio
    async def test_backward_compatible_heartbeat(self, sample_heartbeat_without_gpio):
        """Test that old heartbeats without GPIO still work."""
        handler = get_heartbeat_handler()

        # Old heartbeat format (no gpio_status) should not cause errors
        assert "gpio_status" not in sample_heartbeat_without_gpio

        # Handler should handle missing gpio_status gracefully
        result = handler._validate_gpio_status(None, 0, "ESP_OLD_FW")
        assert result is None or result["gpio_status"] == []

    @pytest.mark.asyncio
    async def test_gpio_owner_types_valid(self, sample_heartbeat_with_gpio):
        """Test that all GPIO owner types are represented."""
        owners = set(item["owner"] for item in sample_heartbeat_with_gpio["gpio_status"])

        assert "sensor" in owners
        assert "actuator" in owners
        assert "system" in owners

    @pytest.mark.asyncio
    async def test_gpio_modes_correct(self, sample_heartbeat_with_gpio):
        """Test that GPIO modes are correct for each owner type."""
        for item in sample_heartbeat_with_gpio["gpio_status"]:
            if item["owner"] == "sensor":
                assert item["mode"] == 0, f"Sensor GPIO {item['gpio']} should have mode=0"
            elif item["owner"] in ("actuator", "system"):
                assert item["mode"] == 1, f"{item['owner']} GPIO {item['gpio']} should have mode=1"


class TestHeartbeatArduinoModeNormalization:
    """
    Integration tests for Arduino pinMode normalization (Phase 2).

    ESP32 sends raw Arduino Core pinMode values:
        INPUT           = 0x01 (1)
        OUTPUT          = 0x02 (2)
        INPUT_PULLUP    = 0x05 (5)

    Server normalizes to protocol values:
        0 = INPUT
        1 = OUTPUT
        2 = INPUT_PULLUP
    """

    def test_validate_arduino_modes_accepted(
        self, heartbeat_handler, sample_heartbeat_with_arduino_modes
    ):
        """Heartbeat with Arduino pinMode values should be accepted (not rejected)."""
        result = heartbeat_handler._validate_gpio_status(
            sample_heartbeat_with_arduino_modes["gpio_status"],
            sample_heartbeat_with_arduino_modes["gpio_reserved_count"],
            "ESP_00000001",
        )

        assert result is not None, "Arduino mode values should not cause validation failure"
        assert len(result["gpio_status"]) == 5, "All 5 GPIO items should be validated"

    def test_arduino_modes_normalized_in_validation(
        self, heartbeat_handler, sample_heartbeat_with_arduino_modes
    ):
        """Arduino modes should be normalized to protocol values during validation."""
        result = heartbeat_handler._validate_gpio_status(
            sample_heartbeat_with_arduino_modes["gpio_status"],
            sample_heartbeat_with_arduino_modes["gpio_reserved_count"],
            "ESP_00000001",
        )

        assert result is not None

        # Build a map of gpio -> normalized mode
        gpio_modes = {item["gpio"]: item["mode"] for item in result["gpio_status"]}

        # Verify normalization:
        # GPIO 4: Arduino INPUT_PULLUP (5) → Protocol 2
        assert gpio_modes[4] == 2, "INPUT_PULLUP (5) should normalize to 2"

        # GPIO 21, 22: Arduino INPUT (1) → Protocol 0
        assert gpio_modes[21] == 0, "INPUT (1) should normalize to 0"
        assert gpio_modes[22] == 0, "INPUT (1) should normalize to 0"

        # GPIO 14: Arduino OUTPUT (2) → Protocol 1
        assert gpio_modes[14] == 1, "OUTPUT (2) should normalize to 1"

        # GPIO 32: Arduino INPUT (1) → Protocol 0
        assert gpio_modes[32] == 0, "INPUT (1) should normalize to 0"

    def test_all_values_normalized_as_arduino(self, heartbeat_handler):
        """
        Test that all values 1, 2, 5 are treated as Arduino values.

        IMPORTANT: Values 1 and 2 are ALWAYS treated as Arduino values
        because we cannot distinguish between "already normalized" and
        "Arduino raw". ESP32 always sends Arduino values, so this is
        the correct behavior.

        If a system needs to send already-normalized data, it should
        not re-validate through this model.
        """
        gpio_status = [
            # Protocol INPUT (0) - passes through unchanged (no Arduino equivalent)
            {"gpio": 4, "owner": "sensor", "component": "protocol_input", "mode": 0, "safe": False},
            # Arduino INPUT (1) → Protocol INPUT (0)
            {"gpio": 5, "owner": "sensor", "component": "arduino_input", "mode": 1, "safe": False},
            # Arduino OUTPUT (2) → Protocol OUTPUT (1)
            {
                "gpio": 14,
                "owner": "actuator",
                "component": "arduino_output",
                "mode": 2,
                "safe": False,
            },
            # Arduino INPUT_PULLUP (5) → Protocol INPUT_PULLUP (2)
            {"gpio": 15, "owner": "sensor", "component": "arduino_pullup", "mode": 5, "safe": True},
        ]

        result = heartbeat_handler._validate_gpio_status(gpio_status, 4, "ESP_ALL_ARDUINO")

        assert result is not None
        gpio_modes = {item["gpio"]: item["mode"] for item in result["gpio_status"]}

        # Protocol INPUT (0) → stays 0
        assert gpio_modes[4] == 0, "Protocol INPUT (0) should stay 0"
        # Arduino INPUT (1) → Protocol INPUT (0)
        assert gpio_modes[5] == 0, "Arduino INPUT (1) should become 0"
        # Arduino OUTPUT (2) → Protocol OUTPUT (1)
        assert gpio_modes[14] == 1, "Arduino OUTPUT (2) should become 1"
        # Arduino INPUT_PULLUP (5) → Protocol INPUT_PULLUP (2)
        assert gpio_modes[15] == 2, "Arduino INPUT_PULLUP (5) should become 2"

    def test_wokwi_simulation_heartbeat_format(self, heartbeat_handler):
        """
        Test exact Wokwi simulation heartbeat format.

        This matches the actual payload from El Trabajante/src/services/communication/mqtt_client.cpp
        where pin.mode is the raw Arduino Core value.
        """
        wokwi_heartbeat = {
            "gpio_status": [
                {"gpio": 21, "owner": "system", "component": "I2C_SDA", "mode": 1, "safe": False},
                {"gpio": 22, "owner": "system", "component": "I2C_SCL", "mode": 1, "safe": False},
                {"gpio": 4, "owner": "system", "component": "OneWireBus", "mode": 5, "safe": True},
            ],
            "gpio_reserved_count": 3,
        }

        result = heartbeat_handler._validate_gpio_status(
            wokwi_heartbeat["gpio_status"], wokwi_heartbeat["gpio_reserved_count"], "ESP_00000001"
        )

        assert result is not None
        assert len(result["gpio_status"]) == 3

        gpio_modes = {item["gpio"]: item["mode"] for item in result["gpio_status"]}

        # I2C pins: Arduino INPUT (1) → Protocol INPUT (0)
        assert gpio_modes[21] == 0
        assert gpio_modes[22] == 0

        # OneWire: Arduino INPUT_PULLUP (5) → Protocol INPUT_PULLUP (2)
        assert gpio_modes[4] == 2

    def test_unknown_arduino_mode_passes_through(self, heartbeat_handler, caplog):
        """Unknown Arduino mode values should pass through with warning."""
        import logging

        caplog.set_level(logging.WARNING)

        gpio_status = [
            {"gpio": 4, "owner": "sensor", "component": "unknown", "mode": 99, "safe": False}
        ]

        result = heartbeat_handler._validate_gpio_status(gpio_status, 1, "ESP_UNKNOWN")

        assert result is not None
        assert result["gpio_status"][0]["mode"] == 99
        assert "Unknown GPIO mode value: 99" in caplog.text
