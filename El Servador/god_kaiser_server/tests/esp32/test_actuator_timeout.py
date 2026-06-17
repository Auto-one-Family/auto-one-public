"""
Tests for Actuator Timeout-Protection (Safety-Critical).

Validates that actuators automatically stop after their configured max runtime,
preventing scenarios like pumps running endlessly which could cause flooding.

Firmware reference: El Trabajante/src/services/actuator/actuator_manager.cpp
    - processActuatorLoops() checks runtime vs max_runtime for each actuator
    - Timeout triggers automatic stop + MQTT alert

These tests simulate the timeout behavior using the MockESP32Client's
safety_timeout_ms field and a lightweight time simulation helper.
"""

import time

import pytest

from .mocks.mock_esp32_client import ActuatorState, MockESP32Client


class ActuatorTimeoutSimulator:
    """
    Simulates actuator timeout-protection logic from ActuatorManager::processActuatorLoops().

    The real firmware tracks start_time per actuator and compares against max_runtime.
    This simulator replicates that logic for test purposes.
    """

    def __init__(self, mock: MockESP32Client):
        self.mock = mock
        self._simulated_millis: int = 0
        self._actuator_start_times: dict[int, int] = {}

    def set_millis(self, ms: int):
        """Set the simulated millis() value."""
        self._simulated_millis = ms

    def advance_time(self, ms: int):
        """Advance simulated time by ms milliseconds."""
        self._simulated_millis += ms

    def activate_actuator(self, gpio: int, value: float = 1.0, mode: str = "digital"):
        """Activate an actuator and record its start time."""
        response = self.mock.handle_command(
            "actuator_set", {"gpio": gpio, "value": value, "mode": mode}
        )
        if response.get("status") == "ok":
            self._actuator_start_times[gpio] = self._simulated_millis
        return response

    def process_actuator_loops(self):
        """
        Simulate ActuatorManager::processActuatorLoops().

        Checks each running actuator against its safety_timeout_ms.
        If exceeded, stops the actuator and publishes a timeout alert.
        """
        stopped = []
        for gpio, actuator in self.mock.actuators.items():
            if not actuator.state:
                continue
            if actuator.safety_timeout_ms <= 0:
                continue

            start_time = self._actuator_start_times.get(gpio)
            if start_time is None:
                continue

            # Handle millis() overflow (unsigned 32-bit wraps at ~49 days)
            if self._simulated_millis >= start_time:
                runtime = self._simulated_millis - start_time
            else:
                # Overflow: 2^32 - start + current
                runtime = (0xFFFFFFFF - start_time) + self._simulated_millis + 1

            if runtime > actuator.safety_timeout_ms:
                # Stop actuator (mirrors firmware behavior)
                actuator.state = False
                actuator.pwm_value = 0.0
                actuator.target_value = 0.0
                actuator.last_command = "timeout_protection"
                actuator.timestamp = time.time()

                # Publish alert (mirrors publishTimeoutAlert)
                self.mock._publish_actuator_alert(
                    gpio,
                    "runtime_protection",
                    f"Actuator on GPIO {gpio} stopped after {runtime}ms (max: {actuator.safety_timeout_ms}ms)",
                )
                stopped.append(gpio)

                # Remove start time
                del self._actuator_start_times[gpio]

        return stopped


class TestActuatorTimeout:
    """Tests for Actuator Timeout-Protection (Safety-Critical)."""

    @pytest.fixture
    def sim(self):
        """Provide a MockESP32Client with timeout simulator."""
        mock = MockESP32Client(esp_id="ESP_TIMEOUT_TEST", kaiser_id="god")
        mock.configure_zone("timeout-zone", "main-zone", "test-subzone")
        simulator = ActuatorTimeoutSimulator(mock)
        yield simulator
        mock.reset()

    def test_actuator_stops_after_max_runtime(self, sim):
        """AT-001: Actuator with max_runtime_ms=5000 stops after 5s."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=5000)
        sim.activate_actuator(gpio=5, value=1.0)

        assert sim.mock.get_actuator_state(5).state is True

        sim.advance_time(5001)
        sim.process_actuator_loops()

        state = sim.mock.get_actuator_state(5)
        assert state.state is False
        assert state.last_command == "timeout_protection"

    def test_process_actuator_loops_checks_all(self, sim):
        """AT-002: processActuatorLoops() checks every actuator."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=1000)
        sim.mock.configure_actuator(gpio=6, actuator_type="valve", safety_timeout_ms=2000)
        sim.activate_actuator(gpio=5, value=1.0)
        sim.activate_actuator(gpio=6, value=1.0)

        sim.advance_time(1001)
        stopped = sim.process_actuator_loops()
        assert 5 in stopped
        assert 6 not in stopped  # 2000ms timeout not reached

        assert sim.mock.get_actuator_state(5).state is False
        assert sim.mock.get_actuator_state(6).state is True

    def test_timeout_publishes_mqtt_alert(self, sim):
        """AT-003: Timeout triggers MQTT alert on actuator/{gpio}/alert topic."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=1000)
        sim.activate_actuator(gpio=5, value=1.0)
        sim.mock.clear_published_messages()

        sim.advance_time(1001)
        sim.process_actuator_loops()

        alert_msgs = sim.mock.get_messages_by_topic_pattern("actuator/5/alert")
        assert len(alert_msgs) >= 1
        payload = alert_msgs[-1]["payload"]
        assert payload["alert_type"] == "runtime_protection"
        assert payload["gpio"] == 5

    def test_new_command_resets_timer(self, sim):
        """AT-004: New command resets the timeout timer."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=5000)
        sim.activate_actuator(gpio=5, value=1.0)

        sim.advance_time(3000)
        # Re-activate (refresh timer)
        sim.activate_actuator(gpio=5, value=1.0)

        sim.advance_time(3000)  # 6s total, but 3s since last command
        sim.process_actuator_loops()

        assert sim.mock.get_actuator_state(5).state is True

    def test_zero_timeout_runs_indefinitely(self, sim):
        """AT-005: safety_timeout_ms=0 means no timeout."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=0)
        sim.activate_actuator(gpio=5, value=1.0)

        sim.advance_time(3600000)  # 1 hour
        sim.process_actuator_loops()

        assert sim.mock.get_actuator_state(5).state is True

    def test_multiple_actuators_independent_timers(self, sim):
        """AT-006: Each actuator has its own independent timer."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=3000)
        sim.mock.configure_actuator(gpio=6, actuator_type="valve", safety_timeout_ms=6000)

        sim.activate_actuator(gpio=5, value=1.0)
        sim.advance_time(1000)
        sim.activate_actuator(gpio=6, value=1.0)

        sim.advance_time(2001)  # gpio5: 3001ms, gpio6: 2001ms
        sim.process_actuator_loops()

        assert sim.mock.get_actuator_state(5).state is False  # Timed out
        assert sim.mock.get_actuator_state(6).state is True  # Still running

    def test_pwm_actuator_zero_after_timeout(self, sim):
        """AT-007: PWM actuator PWM value goes to 0 after timeout."""
        sim.mock.configure_actuator(gpio=7, actuator_type="fan", safety_timeout_ms=2000)
        sim.activate_actuator(gpio=7, value=0.75, mode="pwm")

        assert sim.mock.get_actuator_state(7).pwm_value == 0.75

        sim.advance_time(2001)
        sim.process_actuator_loops()

        state = sim.mock.get_actuator_state(7)
        assert state.pwm_value == 0.0
        assert state.state is False

    def test_binary_actuator_low_after_timeout(self, sim):
        """AT-008: Binary actuator goes LOW after timeout."""
        sim.mock.configure_actuator(gpio=5, actuator_type="relay", safety_timeout_ms=1000)
        sim.activate_actuator(gpio=5, value=1.0, mode="digital")

        sim.advance_time(1001)
        sim.process_actuator_loops()

        state = sim.mock.get_actuator_state(5)
        assert state.state is False
        assert state.pwm_value == 0.0

    def test_timeout_during_emergency_stop_no_double_stop(self, sim):
        """AT-009: Timeout doesn't trigger for already emergency-stopped actuators."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=1000)
        sim.activate_actuator(gpio=5, value=1.0)

        # Emergency stop first
        sim.mock.handle_command("emergency_stop", {})
        sim.mock.clear_published_messages()

        sim.advance_time(1001)
        stopped = sim.process_actuator_loops()

        # No additional stops - actuator was already stopped
        assert len(stopped) == 0
        assert len(sim.mock.get_messages_by_topic_pattern("runtime_protection")) == 0

    def test_millis_overflow_handled(self, sim):
        """AT-010: millis() overflow after ~49 days is handled correctly."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=5000)

        # Start near overflow (2^32 - 1 = 4294967295)
        sim.set_millis(4294967290)
        sim.activate_actuator(gpio=5, value=1.0)

        # After overflow: millis wrapped to ~4996
        sim.set_millis(4996)
        sim.process_actuator_loops()
        # Runtime = (4294967295 - 4294967290) + 4996 + 1 = 5002 > 5000
        assert sim.mock.get_actuator_state(5).state is False

    def test_re_enable_after_timeout(self, sim):
        """AT-011: Actuator can be re-activated after timeout."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=1000)
        sim.activate_actuator(gpio=5, value=1.0)

        sim.advance_time(1001)
        sim.process_actuator_loops()
        assert sim.mock.get_actuator_state(5).state is False

        # Re-activate
        sim.activate_actuator(gpio=5, value=1.0)
        assert sim.mock.get_actuator_state(5).state is True

    def test_alert_payload_format(self, sim):
        """AT-012: Alert payload contains gpio, alert_type, and message with runtime info."""
        sim.mock.configure_actuator(gpio=5, actuator_type="pump", safety_timeout_ms=1000)
        sim.activate_actuator(gpio=5, value=1.0)
        sim.mock.clear_published_messages()

        sim.advance_time(1500)
        sim.process_actuator_loops()

        alert_msgs = sim.mock.get_messages_by_topic_pattern("actuator/5/alert")
        assert len(alert_msgs) == 1

        payload = alert_msgs[0]["payload"]
        assert payload["gpio"] == 5
        assert payload["alert_type"] == "runtime_protection"
        assert "1500" in payload["message"] or "1000" in payload["message"]
        assert "esp_id" in payload
        assert "ts" in payload
