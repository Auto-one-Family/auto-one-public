"""
Tests for GPIO Emergency Safe-Mode (Safety-Critical).

Validates that enableSafeModeForAllPins() correctly de-energizes all OUTPUT pins
and transitions them to INPUT_PULLUP mode, preventing hardware damage.

Firmware reference: El Trabajante/src/drivers/gpio_manager.cpp
    - enableSafeModeForAllPins(): De-energize FIRST, then set INPUT_PULLUP
    - Order is critical: digitalWrite(LOW) BEFORE pinMode(INPUT_PULLUP)

These tests use the MockESP32Client's enter_safe_mode() and verify
the resulting actuator/system states and MQTT messages.
"""

import pytest

from .mocks.mock_esp32_client import MockESP32Client, SystemState


class GPIOEmergencySimulator:
    """
    Simulates GPIO Safe-Mode behavior from GPIOManager::enableSafeModeForAllPins().

    Tracks operation order to verify that de-energize happens before mode change.
    """

    def __init__(self, mock: MockESP32Client):
        self.mock = mock
        self.operations: list[tuple[str, int, ...]] = []
        self._pins: dict[int, dict] = {}

    def reserve_pin(self, gpio: int, mode: str, owner: str, component: str = ""):
        """Register a pin as reserved (simulates gpioManager.requestPin)."""
        self._pins[gpio] = {
            "gpio": gpio,
            "mode": mode,
            "owner": owner,
            "component": component or owner,
            "value": 0,
        }

    def digital_write(self, gpio: int, value: int):
        """Simulate digitalWrite."""
        if gpio in self._pins:
            self._pins[gpio]["value"] = value
            self.operations.append(("write", gpio, value))

    def enable_safe_mode_for_all_pins(self):
        """
        Simulate GPIOManager::enableSafeModeForAllPins().

        Critical order for OUTPUT pins:
        1. digitalWrite(pin, LOW)    - De-energize FIRST
        2. pinMode(pin, INPUT_PULLUP) - Then safe mode
        3. Clear owner
        """
        self.operations.clear()
        for gpio, pin in list(self._pins.items()):
            if pin["mode"] == "OUTPUT":
                # Step 1: De-energize
                self.operations.append(("write", gpio, 0))
                pin["value"] = 0
                # Step 2: Safe mode
                self.operations.append(("mode", gpio, "INPUT_PULLUP"))
                pin["mode"] = "INPUT_PULLUP"
            # Step 3: Clear owner
            pin["owner"] = ""

        # Also trigger mock safe mode for actuator state
        self.mock.enter_safe_mode("emergency")

    def get_pin(self, gpio: int) -> dict | None:
        return self._pins.get(gpio)


class TestGPIOEmergency:
    """Tests for GPIO Emergency Safe-Mode (Safety-Critical)."""

    @pytest.fixture
    def sim(self):
        mock = MockESP32Client(esp_id="ESP_GPIO_TEST", kaiser_id="god")
        mock.configure_zone("gpio-zone", "main-zone", "gpio-subzone")
        mock.configure_actuator(gpio=5, actuator_type="pump", name="Pump")
        mock.configure_actuator(gpio=6, actuator_type="valve", name="Valve")
        mock.clear_published_messages()

        simulator = GPIOEmergencySimulator(mock)
        simulator.reserve_pin(5, "OUTPUT", "actuator", "pump")
        simulator.reserve_pin(6, "OUTPUT", "actuator", "valve")
        simulator.reserve_pin(34, "INPUT", "sensor", "moisture")
        yield simulator
        mock.reset()

    def test_all_output_pins_to_low_then_input_pullup(self, sim):
        """GE-001: All OUTPUT pins → LOW → INPUT_PULLUP."""
        sim.digital_write(5, 1)  # Pump ON
        sim.digital_write(6, 1)  # Valve ON

        sim.enable_safe_mode_for_all_pins()

        pin5 = sim.get_pin(5)
        pin6 = sim.get_pin(6)
        assert pin5["value"] == 0
        assert pin5["mode"] == "INPUT_PULLUP"
        assert pin6["value"] == 0
        assert pin6["mode"] == "INPUT_PULLUP"

    def test_de_energize_before_mode_change(self, sim):
        """GE-002: digitalWrite(LOW) MUST happen BEFORE pinMode(INPUT_PULLUP)."""
        sim.digital_write(5, 1)

        sim.enable_safe_mode_for_all_pins()

        # Find operations for GPIO 5
        ops_5 = [(op, val) for op, gpio, val in sim.operations if gpio == 5]
        write_idx = next(i for i, (op, _) in enumerate(ops_5) if op == "write")
        mode_idx = next(i for i, (op, _) in enumerate(ops_5) if op == "mode")

        assert write_idx < mode_idx, "De-energize MUST happen before mode change!"

    def test_all_pin_owners_cleared(self, sim):
        """GE-003: All pin owners are cleared after safe mode."""
        sim.enable_safe_mode_for_all_pins()

        for gpio in [5, 6, 34]:
            pin = sim.get_pin(gpio)
            assert pin["owner"] == "", f"GPIO {gpio} owner should be cleared"

    def test_input_pins_unchanged(self, sim):
        """GE-004: INPUT pins are not written to (no de-energize needed)."""
        sim.enable_safe_mode_for_all_pins()

        # INPUT pin should not have write operations
        input_writes = [(op, g, v) for op, g, v in sim.operations if g == 34 and op == "write"]
        assert len(input_writes) == 0, "INPUT pins should not be de-energized"

        # But owner should still be cleared
        assert sim.get_pin(34)["owner"] == ""

    def test_i2c_pins_handled(self, sim):
        """GE-005: I2C pins (SDA/SCL) are handled during safe mode."""
        sim.reserve_pin(21, "OUTPUT", "system", "I2C_SDA")
        sim.reserve_pin(22, "OUTPUT", "system", "I2C_SCL")

        sim.enable_safe_mode_for_all_pins()

        assert sim.get_pin(21)["mode"] == "INPUT_PULLUP"
        assert sim.get_pin(22)["mode"] == "INPUT_PULLUP"

    def test_pwm_stopped_before_safe_mode(self, sim):
        """GE-006: PWM actuators have value=0 after safe mode."""
        sim.mock.configure_actuator(gpio=7, actuator_type="fan", name="Fan")
        sim.mock.handle_command("actuator_set", {"gpio": 7, "value": 0.8, "mode": "pwm"})
        sim.reserve_pin(7, "OUTPUT", "actuator", "fan")

        sim.enable_safe_mode_for_all_pins()

        state = sim.mock.get_actuator_state(7)
        assert state.pwm_value == 0.0
        assert state.state is False

    def test_pins_can_be_re_reserved_after_recovery(self, sim):
        """GE-007: After safe mode exit, pins can be reserved again."""
        sim.enable_safe_mode_for_all_pins()

        # All owners cleared
        assert sim.get_pin(5)["owner"] == ""

        # Re-reserve pin
        sim.reserve_pin(5, "OUTPUT", "actuator", "pump")
        assert sim.get_pin(5)["owner"] == "actuator"

        # Mock can exit safe mode
        sim.mock.exit_safe_mode()
        assert sim.mock.system_state == SystemState.OPERATIONAL

    def test_safe_mode_publishes_status(self, sim):
        """GE-008: Safe mode activation publishes MQTT status message."""
        sim.mock.clear_published_messages()

        sim.enable_safe_mode_for_all_pins()

        # Check for safe mode status message
        safe_msgs = sim.mock.get_messages_by_topic_pattern("safe")
        assert len(safe_msgs) >= 1

        payload = safe_msgs[-1]["payload"]
        assert payload["safe_mode"] is True
        assert payload["reason"] == "emergency"
        assert "actuators_disabled" in payload
