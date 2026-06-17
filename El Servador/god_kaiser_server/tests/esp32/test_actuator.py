"""
Actuator Tests - Server-orchestrated ESP32 actuator control testing.

NOTE: These tests use the REAL MQTT topic structure (not separate test topics).
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Pre-production validation with authentic message routing
- Cross-ESP orchestration scenarios
- Seamless CI/CD → Staging → Production flow

Topic structure: kaiser/god/esp/{esp_id}/actuator/{gpio}/...
(Identical to production - see El Trabajante/docs/Mqtt_Protocoll.md)

Tests verify:
1. Digital actuator control (ON/OFF)
2. PWM actuator control (0.0-1.0)
3. Safety constraints and emergency stop
4. Actuator state persistence
5. MQTT status publishing

Migration from ESP32 Tests:
- actuator_manager.cpp → test_digital_control, test_pwm_control, test_mqtt_command
- actuator_safety_controller.cpp → test_emergency_stop, test_safety_constraints
- actuator_pwm_controller.cpp → test_pwm_percentage_control
- actuator_integration.cpp → test_mqtt_integration, test_status_publishing
"""

import pytest
import time


class TestDigitalActuatorControl:
    """Test digital (ON/OFF) actuator control."""

    def test_actuator_set_on(self, mock_esp32):
        """Test turning actuator ON."""
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        assert response["status"] == "ok"
        assert response["state"] is True
        assert response["gpio"] == 5

        # Verify internal state
        actuator = mock_esp32.get_actuator_state(5)
        assert actuator is not None
        assert actuator.state is True
        # actuator_type is set from mode parameter (defaults to "relay" for digital)
        assert actuator.actuator_type in ["digital", "relay"]

    def test_actuator_set_off(self, mock_esp32):
        """Test turning actuator OFF."""
        # First turn ON
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Then turn OFF
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
        )

        assert response["status"] == "ok"
        assert response["state"] is False
        assert response["gpio"] == 5

        # Verify internal state
        actuator = mock_esp32.get_actuator_state(5)
        assert actuator.state is False

    def test_actuator_toggle(self, mock_esp32):
        """Test toggling actuator state."""
        # Set initial state
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # Toggle ON
        response1 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert response1["state"] is True

        # Toggle OFF
        response2 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
        )
        assert response2["state"] is False

    def test_actuator_get_state(self, mock_esp32_with_actuators):
        """Test retrieving actuator state."""
        # Query specific actuator
        response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 5})

        assert response["status"] == "ok"
        assert response["data"]["gpio"] == 5
        assert "state" in response["data"]
        assert "type" in response["data"]

    def test_actuator_get_all(self, mock_esp32_with_actuators):
        """Test retrieving all actuator states."""
        response = mock_esp32_with_actuators.handle_command("actuator_get", {})

        assert response["status"] == "ok"
        assert "actuators" in response["data"]

        actuators = response["data"]["actuators"]
        assert len(actuators) == 3  # Pre-configured with 3 actuators
        # Keys are strings in the implementation (GPIO pins as string keys)
        assert "5" in actuators or 5 in actuators  # Pump on GPIO 5
        assert "6" in actuators or 6 in actuators  # Valve on GPIO 6
        assert "7" in actuators or 7 in actuators  # PWM Motor on GPIO 7


class TestPWMActuatorControl:
    """Test PWM actuator control (0.0-1.0 range)."""

    def test_pwm_set_percentage(self, mock_esp32):
        """Test setting PWM percentage."""
        test_values = [0.0, 0.25, 0.5, 0.75, 1.0]

        for value in test_values:
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 7, "value": value, "mode": "pwm"}
            )

            assert response["status"] == "ok"
            assert response["pwm_value"] == value
            assert response["state"] == (value > 0)

    def test_pwm_range_clamping(self, mock_esp32):
        """Test PWM values are clamped to 0.0-1.0."""
        # Test over max (should clamp to 1.0)
        response1 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 7, "value": 1.5, "mode": "pwm"}
        )
        assert response1["pwm_value"] == 1.0  # Clamped to max
        assert response1["state"] is True

        # Test under min (should clamp to 0.0)
        response2 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 7, "value": -0.5, "mode": "pwm"}
        )
        assert response2["pwm_value"] == 0.0
        assert response2["state"] is False

    def test_pwm_state_consistency(self, mock_esp32):
        """Test PWM state is consistent with value."""
        # PWM = 0.0 → state = False
        response1 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.0, "mode": "pwm"}
        )
        assert response1["state"] is False

        # PWM > 0.0 → state = True
        response2 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.1, "mode": "pwm"}
        )
        assert response2["state"] is True

    def test_pwm_respects_configured_limits(self, mock_esp32):
        """Test PWM limits from actuator configuration are enforced."""
        mock_esp32.configure_actuator(gpio=8, actuator_type="fan", min_value=0.2, max_value=0.8)
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 8, "value": 1.0, "mode": "pwm"}
        )

        assert response["pwm_value"] == 0.8
        assert response["state"] is True

    def test_pwm_get_value(self, mock_esp32_with_actuators):
        """Test retrieving PWM actuator value."""
        # GPIO 7 is pre-configured as PWM (Ventilation Fan)
        response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 7})

        assert response["status"] == "ok"
        # Type reflects the configured actuator_type (can be pwm, pwm_motor, fan, etc.)
        assert response["data"]["type"] in ["pwm", "pwm_motor", "fan", "motor"]
        assert "pwm_value" in response["data"]
        assert 0.0 <= response["data"]["pwm_value"] <= 1.0


class TestEmergencyStop:
    """Test emergency stop functionality (SAFETY-CRITICAL!)."""

    def test_emergency_stop_all_actuators(self, mock_esp32_with_actuators):
        """Test emergency stop turns OFF all actuators."""
        # Turn all actuators ON
        mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
        )
        mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"}
        )

        # Trigger emergency stop
        response = mock_esp32_with_actuators.handle_command("emergency_stop", {})

        assert response["status"] == "ok"
        assert response["command"] == "emergency_stop"
        assert len(response["stopped_actuators"]) == 3

        # Verify all actuators are OFF
        for gpio in [5, 6, 7]:
            actuator = mock_esp32_with_actuators.get_actuator_state(gpio)
            assert actuator.state is False, f"Actuator {gpio} not stopped"
            assert actuator.pwm_value == 0.0, f"Actuator {gpio} PWM not zero"

    def test_emergency_stop_publishes_status(self, mock_esp32_with_actuators):
        """Test emergency stop publishes status for all actuators."""
        mock_esp32_with_actuators.clear_published_messages()

        # Trigger emergency stop
        mock_esp32_with_actuators.handle_command("emergency_stop", {})

        # Verify messages published:
        # Now includes:
        # - 3 actuator status messages (GPIO 5, 6, 7)
        # - 3 actuator alert messages (GPIO 5, 6, 7)
        # - 1 device-specific emergency message
        # - 1 broadcast emergency message
        # Total: 8 messages
        messages = mock_esp32_with_actuators.get_published_messages()
        assert len(messages) >= 5, f"Expected at least 5 messages, got {len(messages)}"

        # Verify actuator status messages
        status_messages = [m for m in messages if "/status" in m["topic"]]
        assert (
            len(status_messages) == 3
        ), f"Should have 3 actuator status messages, got {len(status_messages)}"

        for message in status_messages:
            assert "actuator" in message["topic"]
            assert "status" in message["topic"]
            assert message["payload"]["state"] is False

    def test_emergency_stop_publishes_emergency_topics(self, mock_esp32_with_actuators):
        """Test emergency stop publishes to device-specific AND broadcast emergency topics."""
        mock_esp32_with_actuators.clear_published_messages()

        # Trigger emergency stop
        response = mock_esp32_with_actuators.handle_command("emergency_stop", {})
        assert response["status"] == "ok"

        # Get published messages
        messages = mock_esp32_with_actuators.get_published_messages()

        # Find device-specific emergency topic
        device_emergency = [m for m in messages if "actuator/emergency" in m["topic"]]
        assert len(device_emergency) == 1, "Should have 1 device-specific emergency message"
        assert (
            device_emergency[0]["topic"]
            == f"kaiser/god/esp/{mock_esp32_with_actuators.esp_id}/actuator/emergency"
        )
        assert device_emergency[0]["payload"]["esp_id"] == mock_esp32_with_actuators.esp_id

        # Find broadcast emergency topic
        broadcast_emergency = [m for m in messages if m["topic"] == "kaiser/broadcast/emergency"]
        assert len(broadcast_emergency) == 1, "Should have 1 broadcast emergency message"
        assert broadcast_emergency[0]["payload"]["esp_id"] == mock_esp32_with_actuators.esp_id

    def test_emergency_stop_timestamp(self, mock_esp32_with_actuators):
        """Test emergency stop updates actuator timestamps."""
        # Get initial timestamps
        initial_times = {}
        for gpio in [5, 6, 7]:
            actuator = mock_esp32_with_actuators.get_actuator_state(gpio)
            initial_times[gpio] = actuator.timestamp

        time.sleep(0.01)  # Small delay

        # Trigger emergency stop
        mock_esp32_with_actuators.handle_command("emergency_stop", {})

        # Verify timestamps updated
        for gpio in [5, 6, 7]:
            actuator = mock_esp32_with_actuators.get_actuator_state(gpio)
            assert (
                actuator.timestamp > initial_times[gpio]
            ), f"Timestamp not updated for GPIO {gpio}"


class TestActuatorStatePersistence:
    """Test actuator state persistence across commands."""

    def test_state_persists_across_get_commands(self, mock_esp32):
        """Test actuator state doesn't change on get commands."""
        # Set actuator ON
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Query state multiple times
        for _ in range(3):
            response = mock_esp32.handle_command("actuator_get", {"gpio": 5})
            assert response["data"]["state"] is True

        # State should still be ON
        actuator = mock_esp32.get_actuator_state(5)
        assert actuator.state is True

    def test_state_persists_across_other_commands(self, mock_esp32):
        """Test actuator state persists when other commands are executed."""
        # Set actuator ON
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Execute other commands
        mock_esp32.handle_command("ping", {})
        mock_esp32.handle_command("config_get", {})

        # Verify actuator still ON
        response = mock_esp32.handle_command("actuator_get", {"gpio": 5})
        assert response["data"]["state"] is True

    def test_last_command_tracked(self, mock_esp32):
        """Test last command is tracked for actuators."""
        # Set digital
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        actuator = mock_esp32.get_actuator_state(5)
        assert actuator.last_command == "set_digital"

        # Set PWM
        mock_esp32.handle_command("actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"})
        actuator = mock_esp32.get_actuator_state(7)
        assert actuator.last_command == "set_pwm"


class TestMQTTStatusPublishing:
    """Test MQTT status publishing for actuator commands."""

    def test_actuator_set_publishes_status(self, mock_esp32):
        """Test actuator_set publishes status message."""
        mock_esp32.clear_published_messages()

        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        messages = mock_esp32.get_published_messages()
        # Now publishes both status and response (2 messages)
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        response_msgs = [m for m in messages if "/response" in m["topic"]]
        assert len(status_msgs) == 1, f"Expected 1 status message, got {len(status_msgs)}"
        assert len(response_msgs) == 1, f"Expected 1 response message, got {len(response_msgs)}"

        message = status_msgs[0]
        assert message["topic"] == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status"
        assert message["payload"]["gpio"] == 5
        assert message["payload"]["state"] is True

    def test_pwm_set_publishes_pwm_value(self, mock_esp32):
        """Test PWM actuator_set includes PWM value in status."""
        mock_esp32.clear_published_messages()

        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"}
        )

        messages = mock_esp32.get_published_messages()
        message = messages[0]
        assert message["payload"]["pwm_value"] == 0.75

    def test_multiple_actuators_publish_separately(self, mock_esp32):
        """Test multiple actuator commands publish separate status messages."""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock_esp32.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        messages = mock_esp32.get_published_messages()
        # Now publishes status + response for each actuator (4 total: 2 status + 2 response)
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        assert len(status_msgs) == 2, f"Expected 2 status messages, got {len(status_msgs)}"

        topics = [msg["topic"] for msg in status_msgs]
        assert f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status" in topics
        assert f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/6/status" in topics


class TestActuatorTypes:
    """Test different actuator types (pump, valve, pwm)."""

    def test_pump_actuator(self, mock_esp32_with_actuators):
        """Test pump actuator (GPIO 5 - digital)."""
        # GPIO 5 is pre-configured as pump
        response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 5})

        # Type reflects the specific actuator type (configured as "pump")
        assert response["data"]["type"] == "pump"

        # Test control
        set_response = mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert set_response["state"] is True

    def test_valve_actuator(self, mock_esp32_with_actuators):
        """Test valve actuator (GPIO 6 - digital)."""
        response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 6})

        # Type reflects the specific actuator type (configured as "valve")
        assert response["data"]["type"] == "valve"

    def test_pwm_motor_actuator(self, mock_esp32_with_actuators):
        """Test PWM motor actuator (GPIO 7 - pwm)."""
        response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 7})

        # Type reflects the specific actuator type (configured as "pwm_motor")
        assert response["data"]["type"] in ["pwm", "pwm_motor", "fan", "motor"]

        # Test PWM control
        set_response = mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"}
        )
        assert set_response["pwm_value"] == 0.5


class TestActuatorErrors:
    """Test actuator error handling."""

    def test_actuator_get_nonexistent_gpio(self, mock_esp32):
        """Test getting state of non-existent actuator."""
        response = mock_esp32.handle_command("actuator_get", {"gpio": 99})

        assert response["status"] == "error"
        assert "not found" in response["error"].lower()

    def test_actuator_set_missing_value(self, mock_esp32):
        """Test actuator_set without value parameter."""
        response = mock_esp32.handle_command("actuator_set", {"gpio": 5})

        assert response["status"] == "error"
        assert "missing" in response["error"].lower() or "value" in response["error"].lower()

    def test_actuator_set_missing_gpio(self, mock_esp32):
        """Test actuator_set without gpio parameter."""
        response = mock_esp32.handle_command("actuator_set", {"value": 1})

        assert response["status"] == "error"
        assert "missing" in response["error"].lower() or "gpio" in response["error"].lower()


class TestActuatorProvisioningSafety:
    """Test safety behavior before an ESP is provisioned with a zone."""

    def test_actuator_rejected_without_zone(self, mock_esp32_unconfigured):
        """Actuator commands should be rejected when no zone is configured."""
        response = mock_esp32_unconfigured.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        assert response["status"] == "error"
        assert "zone not configured" in response["error"].lower()


class TestActuatorConcurrency:
    """Test concurrent actuator operations."""

    def test_multiple_actuators_independent(self, mock_esp32):
        """Test multiple actuators operate independently."""
        # Set actuator 5 ON
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Set actuator 6 OFF
        mock_esp32.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})

        # Verify states are independent
        response5 = mock_esp32.handle_command("actuator_get", {"gpio": 5})
        response6 = mock_esp32.handle_command("actuator_get", {"gpio": 6})

        assert response5["data"]["state"] is True
        assert response6["data"]["state"] is False

    def test_rapid_state_changes(self, mock_esp32):
        """Test rapid actuator state changes."""
        for i in range(10):
            value = i % 2  # Alternate 0 and 1
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 5, "value": value, "mode": "digital"}
            )
            assert response["status"] == "ok"

        # Final state should be 1 (last iteration i=9, value=1)
        actuator = mock_esp32.get_actuator_state(5)
        assert actuator.state is True
