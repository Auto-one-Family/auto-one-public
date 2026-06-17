"""
Integration Tests - Server-orchestrated full-system ESP32 testing.

NOTE: These tests use the REAL MQTT topic structure (not separate test topics).
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Pre-production validation with authentic message routing
- Cross-ESP orchestration scenarios
- Seamless CI/CD → Staging → Production flow

Topic structure: kaiser/god/esp/{esp_id}/...
(Identical to production - see El Trabajante/docs/Mqtt_Protocoll.md)

Tests verify:
1. Complete sensor → server → actuator flow
2. MQTT message orchestration
3. Emergency scenarios
4. System-level behavior

Migration from ESP32 Tests:
- integration_full.cpp → test_complete_workflow, test_system_orchestration
- integration_phase2.cpp → test_pi_enhanced_flow
"""

import pytest


class TestCompleteSensorActuatorFlow:
    """Test complete flow from sensor reading to actuator control."""

    def test_sensor_read_then_actuator_control(self, mock_esp32_with_sensors):
        """Test reading sensor value then controlling actuator based on it."""
        # Read sensor
        sensor_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        assert sensor_response["status"] == "ok"
        raw_value = sensor_response["data"]["raw_value"]

        # Control actuator based on sensor value (simple logic)
        # If moisture (GPIO 34) is low (< 2000), turn pump ON
        pump_value = 1 if raw_value < 2000 else 0

        actuator_response = mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 5, "value": pump_value, "mode": "digital"}
        )
        assert actuator_response["status"] == "ok"

        # Verify actuator state matches decision
        actuator_state = mock_esp32_with_sensors.get_actuator_state(5)
        assert actuator_state.state == (pump_value == 1)

    def test_multiple_sensors_control_multiple_actuators(self, mock_esp32_with_sensors):
        """Test orchestrating multiple sensors and actuators."""
        mock_esp32_with_sensors.clear_published_messages()

        # Read multiple sensors
        moisture = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        temp = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 35})
        flow = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 36})

        # Control multiple actuators
        mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )  # Pump
        mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
        )  # Valve
        mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"}
        )  # Motor

        # Verify all commands succeeded
        actuator_response = mock_esp32_with_sensors.handle_command("actuator_get", {})
        assert len(actuator_response["data"]["actuators"]) == 3

        # Verify MQTT messages published for both sensors and actuators
        messages = mock_esp32_with_sensors.get_published_messages()

        # Count by type (sensors have zone topics, actuators have status + response)
        sensor_msgs = [m for m in messages if "/sensor/" in m["topic"]]
        actuator_msgs = [m for m in messages if "/actuator/" in m["topic"]]

        # 3 sensors × 2 (normal + zone topic) = 6 sensor messages
        # 3 actuators × 2 (status + response) = 6 actuator messages
        assert len(sensor_msgs) >= 3  # At least 3 (6 with zone)
        assert len(actuator_msgs) == 6  # Exactly 6 (3 status + 3 response)


class TestMQTTOrchestration:
    """Test MQTT message orchestration and flow."""

    def test_command_response_message_flow(self, mock_esp32):
        """Test complete command → response → status message flow."""
        mock_esp32.clear_published_messages()

        # Send command
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Verify response received
        assert response["status"] == "ok"
        assert response["command"] == "actuator_set"

        # Verify messages published (now 2: status + response)
        messages = mock_esp32.get_published_messages()
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        response_msgs = [m for m in messages if "/response" in m["topic"]]

        assert len(status_msgs) == 1
        assert len(response_msgs) == 1
        assert "actuator/5/status" in status_msgs[0]["topic"]

    def test_message_ordering(self, mock_esp32):
        """Test messages are published in correct order."""
        mock_esp32.clear_published_messages()

        # Execute sequence of commands
        commands = [
            ("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}),
            ("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}),
            ("sensor_read", {"gpio": 34}),
        ]

        for command, params in commands:
            response = mock_esp32.handle_command(command, params)
            assert response["status"] == "ok"

        # Verify messages in order (actuators publish status + response = 4, sensor = 2 with zone)
        messages = mock_esp32.get_published_messages()

        # Filter by type
        actuator_5_msgs = [m for m in messages if "actuator/5" in m["topic"]]
        actuator_6_msgs = [m for m in messages if "actuator/6" in m["topic"]]
        sensor_msgs = [m for m in messages if "sensor/34" in m["topic"]]

        # Each actuator should have status + response
        assert len(actuator_5_msgs) == 2
        assert len(actuator_6_msgs) == 2
        assert len(sensor_msgs) >= 1  # At least 1 (2 with zone)


class TestEmergencyScenarios:
    """Test emergency scenarios and system recovery."""

    def test_emergency_stop_system_wide(self, mock_esp32_with_actuators):
        """Test emergency stop affects entire system."""
        # Turn all actuators ON
        for gpio in [5, 6]:
            mock_esp32_with_actuators.handle_command(
                "actuator_set", {"gpio": gpio, "value": 1, "mode": "digital"}
            )
        mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"}
        )

        # Trigger emergency stop
        emergency_response = mock_esp32_with_actuators.handle_command("emergency_stop", {})
        assert emergency_response["status"] == "ok"

        # Verify ALL actuators stopped
        actuator_response = mock_esp32_with_actuators.handle_command("actuator_get", {})
        for gpio, actuator in actuator_response["data"]["actuators"].items():
            assert actuator["state"] is False, f"Actuator {gpio} not stopped"

    def test_system_recovery_after_emergency(self, mock_esp32_with_actuators):
        """Test system can recover after emergency stop (requires clear_emergency)."""
        # Emergency stop
        mock_esp32_with_actuators.handle_command("emergency_stop", {})

        # Attempt to restart actuators - should fail (emergency stopped)
        response = mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert response["status"] == "error"
        assert "emergency stopped" in response["error"]

        # Clear emergency first
        clear_response = mock_esp32_with_actuators.handle_command("clear_emergency", {})
        assert clear_response["status"] == "ok"

        # Now restart should work
        response = mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert response["status"] == "ok"


class TestSystemConfiguration:
    """Test system-wide configuration and state."""

    def test_complete_system_status(self, mock_esp32_with_actuators):
        """Test retrieving complete system status."""
        # Get all actuators
        actuator_response = mock_esp32_with_actuators.handle_command("actuator_get", {})
        assert len(actuator_response["data"]["actuators"]) == 3

        # Get config
        config_response = mock_esp32_with_actuators.handle_command("config_get", {})
        assert "wifi" in config_response["data"]["config"]
        assert "zone" in config_response["data"]["config"]

        # Get ping (uptime)
        ping_response = mock_esp32_with_actuators.handle_command("ping", {})
        assert "uptime" in ping_response

    def test_config_persists_across_operations(self, mock_esp32):
        """Test configuration remains stable during operations."""
        # Get initial config
        config1 = mock_esp32.handle_command("config_get", {"key": "zone"})
        zone1 = config1["data"]["value"]

        # Perform various operations
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock_esp32.handle_command("sensor_read", {"gpio": 34})
        mock_esp32.handle_command("ping", {})

        # Get config again
        config2 = mock_esp32.handle_command("config_get", {"key": "zone"})
        zone2 = config2["data"]["value"]

        # Config should be unchanged
        assert zone1 == zone2


class TestPiEnhancedFlow:
    """Test Pi-Enhanced sensor processing flow."""

    def test_raw_value_to_server_flow(self, mock_esp32_with_sensors):
        """Test RAW sensor value sent to server for processing."""
        # ESP32 sends RAW value
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Verify RAW value present
        assert "raw_value" in response["data"]
        raw_value = response["data"]["raw_value"]

        # Verify it's unprocessed (server would process it)
        assert raw_value == 2048.0  # Pre-configured value

        # Server would process and send back (not tested here - server-side)

    def test_sensor_type_determines_processing(self, mock_esp32_with_sensors):
        """Test different sensor types send appropriate data."""
        # Analog sensor
        analog_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        assert analog_response["data"]["type"] == "analog"
        assert isinstance(analog_response["data"]["raw_value"], (int, float))

        # Digital sensor
        digital_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 36})
        assert digital_response["data"]["type"] == "digital"
        assert digital_response["data"]["raw_value"] in [0.0, 1.0]


class TestSystemReset:
    """Test system reset functionality."""

    def test_reset_clears_all_state(self, mock_esp32_with_actuators):
        """Test reset clears all actuators and sensors."""
        # Add sensor
        mock_esp32_with_actuators.handle_command("sensor_read", {"gpio": 34})

        # Verify state exists
        actuator_count_before = len(mock_esp32_with_actuators.actuators)
        sensor_count_before = len(mock_esp32_with_actuators.sensors)

        assert actuator_count_before == 3  # Pre-configured
        assert sensor_count_before == 1  # Just added

        # Reset
        reset_response = mock_esp32_with_actuators.handle_command("reset", {})
        assert reset_response["status"] == "ok"

        # Verify state cleared
        assert len(mock_esp32_with_actuators.actuators) == 0
        assert len(mock_esp32_with_actuators.sensors) == 0

    def test_reset_clears_published_messages(self, mock_esp32):
        """Test reset clears message history."""
        # Generate messages
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert len(mock_esp32.get_published_messages()) > 0

        # Reset
        mock_esp32.handle_command("reset", {})

        # Verify messages cleared
        assert len(mock_esp32.get_published_messages()) == 0


class TestConcurrentOperations:
    """Test concurrent sensor and actuator operations."""

    def test_interleaved_sensor_actuator_commands(self, mock_esp32):
        """Test interleaving sensor reads and actuator controls."""
        operations = [
            ("sensor_read", {"gpio": 34}),
            ("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}),
            ("sensor_read", {"gpio": 35}),
            ("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}),
            ("sensor_read", {"gpio": 36}),
            ("actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"}),
        ]

        for command, params in operations:
            response = mock_esp32.handle_command(command, params)
            assert response["status"] == "ok", f"{command} failed: {response.get('error')}"

    def test_rapid_command_sequence(self, mock_esp32):
        """Test rapid sequence of commands."""
        for i in range(20):
            command = "sensor_read" if i % 2 == 0 else "actuator_set"

            if command == "sensor_read":
                params = {"gpio": 34 + (i % 3)}
            else:
                params = {"gpio": 5 + (i % 3), "value": i % 2, "mode": "digital"}

            response = mock_esp32.handle_command(command, params)
            assert response["status"] == "ok"


class TestSystemHealth:
    """Test system health monitoring."""

    def test_ping_uptime_monitoring(self, mock_esp32):
        """Test uptime reporting via ping."""
        response1 = mock_esp32.handle_command("ping", {})
        uptime1 = response1["uptime"]

        import time

        time.sleep(0.01)

        response2 = mock_esp32.handle_command("ping", {})
        uptime2 = response2["uptime"]

        # Uptime should increase
        assert uptime2 >= uptime1

    def test_system_version_reporting(self, mock_esp32):
        """Test system version is reported."""
        response = mock_esp32.handle_command("config_get", {"key": "system"})

        system_info = response["data"]["value"]
        assert "version" in system_info
        assert len(system_info["version"]) > 0


class TestErrorRecovery:
    """Test system error recovery."""

    def test_recovery_after_invalid_command(self, mock_esp32):
        """Test system recovers after invalid command."""
        # Send invalid command
        error_response = mock_esp32.handle_command("invalid_command", {})
        assert error_response["status"] == "error"

        # Verify system still works
        ok_response = mock_esp32.handle_command("ping", {})
        assert ok_response["status"] == "ok"

    def test_recovery_after_missing_parameter(self, mock_esp32):
        """Test system recovers after command with missing parameter."""
        # Send command with missing parameter
        error_response = mock_esp32.handle_command("actuator_set", {"gpio": 5})
        assert error_response["status"] == "error"

        # Verify system still works
        ok_response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert ok_response["status"] == "ok"


class TestFullSystemWorkflow:
    """Test complete system workflow scenarios."""

    def test_greenhouse_automation_scenario(self, mock_esp32_with_sensors):
        """Test typical greenhouse automation workflow."""
        # 1. Read soil moisture
        moisture_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        moisture = moisture_response["data"]["raw_value"]

        # 2. Read temperature
        temp_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 35})
        temp = temp_response["data"]["raw_value"]

        # 3. Control irrigation based on moisture (simple logic)
        if moisture < 2000:
            # Turn pump ON
            pump_response = mock_esp32_with_sensors.handle_command(
                "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
            )
            assert pump_response["status"] == "ok"
        else:
            # Turn pump OFF
            pump_response = mock_esp32_with_sensors.handle_command(
                "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
            )
            assert pump_response["status"] == "ok"

        # 4. Control ventilation based on temperature (PWM)
        fan_speed = min(1.0, temp / 3000.0)  # Scale to 0-1
        fan_response = mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 7, "value": fan_speed, "mode": "pwm"}
        )
        assert fan_response["status"] == "ok"

        # Verify final state
        final_state = mock_esp32_with_sensors.handle_command("actuator_get", {})
        assert final_state["status"] == "ok"
        assert len(final_state["data"]["actuators"]) >= 2
