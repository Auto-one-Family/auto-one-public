"""
Communication Tests - Server-orchestrated ESP32 MQTT testing.

These tests verify MQTT communication between God-Kaiser server and ESP32 devices.
They are the FOUNDATION for all other server-orchestrated tests.

NOTE: These tests use the REAL MQTT topic structure (not separate test topics).
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Pre-production validation with authentic message routing
- Cross-ESP orchestration scenarios
- Seamless CI/CD → Staging → Production flow

Topic structure: kaiser/god/esp/{esp_id}/...
(Identical to production - see El Trabajante/docs/Mqtt_Protocoll.md)

Test Categories:
1. Basic Connectivity (ping/pong)
2. Response Time
3. Command-Response Cycle
4. Error Handling

Migration from ESP32 Tests:
- comm_mqtt_client.cpp → test_mqtt_ping, test_mqtt_response_time, test_mqtt_command_response
- comm_wifi_manager.cpp → (Hardware-only, not applicable for Mock)
- comm_http_client.cpp → (Pi-Enhanced, tested in sensor tests)
"""

import pytest
import time
from typing import Dict, Any


class TestMQTTConnectivity:
    """Test basic MQTT connectivity via ping/pong commands."""

    def test_mqtt_ping(self, mock_esp32):
        """Test basic MQTT connectivity with ping command."""
        # Send ping command
        response = mock_esp32.handle_command("ping", {})

        # Verify response
        assert response is not None, "No response received"
        assert response["status"] == "ok", f"Ping failed: {response.get('error')}"
        assert response["command"] == "pong", "Expected pong response"
        assert "esp_id" in response, "Missing esp_id in response"
        assert response["esp_id"] == mock_esp32.esp_id, "ESP ID mismatch"

    def test_mqtt_response_time(self, mock_esp32):
        """Test MQTT response time is acceptable (< 500ms)."""
        # Measure response time
        start_time = time.time()
        response = mock_esp32.handle_command("ping", {})
        end_time = time.time()

        response_time = (end_time - start_time) * 1000  # ms

        # Verify response time (Mock should be instant, real hardware < 500ms)
        assert response_time < 500, f"Response time too slow: {response_time:.2f}ms"
        assert response["status"] == "ok"

    def test_mqtt_uptime_in_response(self, mock_esp32):
        """Test that ping response includes uptime."""
        response = mock_esp32.handle_command("ping", {})

        assert "uptime" in response, "Missing uptime in ping response"
        assert response["uptime"] >= 0, "Uptime should be non-negative"

    def test_mqtt_multiple_pings(self, mock_esp32):
        """Test multiple consecutive ping commands."""
        for i in range(5):
            response = mock_esp32.handle_command("ping", {})
            assert response["status"] == "ok", f"Ping {i+1} failed"
            assert response["command"] == "pong"


class TestCommandResponseCycle:
    """Test full command-response cycle for various commands."""

    def test_actuator_command_response(self, mock_esp32):
        """Test actuator command generates correct response."""
        # Send actuator_set command
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Verify response
        assert response["status"] == "ok"
        assert response["command"] == "actuator_set"
        assert response["gpio"] == 5
        assert response["state"] is True

    def test_sensor_read_command_response(self, mock_esp32_with_sensors):
        """Test sensor read command generates correct response."""
        # Send sensor_read command
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Verify response
        assert response["status"] == "ok"
        assert response["command"] == "sensor_read"
        assert response["gpio"] == 34
        assert "raw_value" in response["data"]

    def test_config_get_command_response(self, mock_esp32):
        """Test config get command generates correct response."""
        # Configure zone first (production ESP32s have zone configured)
        mock_esp32.configure_zone("test-zone", "test-master", "test-subzone")

        # Send config_get command (no key = get all)
        response = mock_esp32.handle_command("config_get", {})

        # Verify response
        assert response["status"] == "ok"
        assert response["command"] == "config_get"
        assert "config" in response["data"]
        assert "wifi" in response["data"]["config"]
        assert "zone" in response["data"]["config"]

    def test_config_get_specific_key(self, mock_esp32):
        """Test config get with specific key."""
        # Send config_get command with key
        response = mock_esp32.handle_command("config_get", {"key": "wifi"})

        # Verify response
        assert response["status"] == "ok"
        assert response["command"] == "config_get"
        assert response["data"]["key"] == "wifi"
        assert response["data"]["value"] is not None


class TestErrorHandling:
    """Test error handling in MQTT communication."""

    def test_unknown_command_error(self, mock_esp32):
        """Test that unknown commands return error."""
        response = mock_esp32.handle_command("invalid_command", {})

        assert response["status"] == "error"
        assert "Unknown command" in response["error"]

    def test_missing_required_parameter(self, mock_esp32):
        """Test error when required parameter is missing."""
        # actuator_set requires gpio and value
        response = mock_esp32.handle_command(
            "actuator_set",
            {
                "gpio": 5
                # Missing "value"
            },
        )

        assert response["status"] == "error"
        assert "Missing" in response["error"] or "required" in response["error"].lower()

    def test_invalid_gpio(self, mock_esp32):
        """Test actuator_get on non-existent GPIO."""
        response = mock_esp32.handle_command("actuator_get", {"gpio": 99})  # Non-existent actuator

        assert response["status"] == "error"
        assert "not found" in response["error"].lower()


class TestMQTTPublishing:
    """Test MQTT message publishing (side effects of commands)."""

    def test_actuator_status_published(self, mock_esp32):
        """Test that actuator_set publishes status message."""
        # Clear previous messages
        mock_esp32.clear_published_messages()

        # Send actuator_set command
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Verify status message was published (now includes status + response)
        messages = mock_esp32.get_published_messages()
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        assert len(status_msgs) >= 1, "Expected at least one status message"

        message = status_msgs[0]
        assert message["topic"] == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status"
        assert message["payload"]["gpio"] == 5
        assert message["payload"]["state"] is True

    def test_sensor_data_published(self, mock_esp32_with_sensors):
        """Test that sensor_read publishes sensor data."""
        # Clear previous messages
        mock_esp32_with_sensors.clear_published_messages()

        # Send sensor_read command
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Verify sensor data was published (may have zone topic too)
        messages = mock_esp32_with_sensors.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1, "Expected at least one published message"

        message = sensor_msgs[0]
        assert f"kaiser/god/esp/{mock_esp32_with_sensors.esp_id}/sensor/34/data" in message["topic"]
        assert message["payload"]["gpio"] == 34
        # Production uses "raw" field per Mqtt_Protocoll.md
        assert (
            "raw" in message["payload"]
        ), "Payload should have 'raw' field (per Mqtt_Protocoll.md)"

    def test_emergency_stop_publishes_multiple_statuses(self, mock_esp32_with_actuators):
        """Test that emergency_stop publishes status for all actuators."""
        # Clear previous messages
        mock_esp32_with_actuators.clear_published_messages()

        # Send emergency_stop command
        response = mock_esp32_with_actuators.handle_command("emergency_stop", {})

        # Verify messages were published (includes actuator statuses + emergency broadcasts)
        messages = mock_esp32_with_actuators.get_published_messages()

        # Filter only actuator status messages (not emergency broadcasts)
        status_messages = [m for m in messages if "status" in m["topic"]]
        assert len(status_messages) == 3, "Expected status for all 3 actuators"

        # Verify all status messages are actuator status messages
        for message in status_messages:
            assert "actuator" in message["topic"]
            assert "status" in message["topic"]
            assert message["payload"]["state"] is False, "Actuator should be stopped"


class TestResponseFormat:
    """Test that responses follow the correct format."""

    def test_response_has_timestamp(self, mock_esp32):
        """Test that all responses include timestamp."""
        commands_to_test = [
            ("ping", {}),
            ("actuator_get", {}),
            ("config_get", {}),
        ]

        for command, params in commands_to_test:
            response = mock_esp32.handle_command(command, params)
            assert "timestamp" in response, f"Missing timestamp in {command} response"
            assert isinstance(response["timestamp"], float), "Timestamp should be float"
            assert response["timestamp"] > 0, "Timestamp should be positive"

    def test_error_response_format(self, mock_esp32):
        """Test that error responses follow correct format."""
        response = mock_esp32.handle_command("invalid_command", {})

        # Verify error response format
        assert "status" in response
        assert response["status"] == "error"
        assert "error" in response
        assert isinstance(response["error"], str)
        assert "timestamp" in response

    def test_success_response_format(self, mock_esp32):
        """Test that success responses follow correct format."""
        response = mock_esp32.handle_command("ping", {})

        # Verify success response format
        assert "status" in response
        assert response["status"] == "ok"
        assert "command" in response
        assert "timestamp" in response
        assert "error" not in response or response.get("error") is None


class TestConcurrentCommands:
    """Test handling of multiple concurrent commands."""

    def test_sequential_commands(self, mock_esp32):
        """Test multiple sequential commands work correctly."""
        commands = [
            ("ping", {}),
            ("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}),
            ("actuator_get", {"gpio": 5}),
            ("config_get", {"key": "wifi"}),
        ]

        for command, params in commands:
            response = mock_esp32.handle_command(command, params)
            assert response["status"] == "ok", f"Command {command} failed: {response.get('error')}"

    def test_command_state_persistence(self, mock_esp32):
        """Test that command effects persist across multiple commands."""
        # Set actuator ON
        response1 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert response1["status"] == "ok"

        # Verify actuator is still ON
        response2 = mock_esp32.handle_command("actuator_get", {"gpio": 5})
        assert response2["status"] == "ok"
        assert response2["data"]["state"] is True

        # Set actuator OFF
        response3 = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
        )
        assert response3["status"] == "ok"

        # Verify actuator is now OFF
        response4 = mock_esp32.handle_command("actuator_get", {"gpio": 5})
        assert response4["status"] == "ok"
        assert response4["data"]["state"] is False


class TestInMemoryMQTTClient:
    """Test in-memory MQTT test client for brokerless workflows.

    NOTE: These tests validate the InMemoryMQTTTestClient mock infrastructure,
    not the real MQTT system. The mock is used by other tests (e.g., test_i2c_bus.py)
    to simulate MQTT communication without a real broker.

    The mock's publish() is async to be compatible with async test code,
    even though the real MQTTClient.publish() is synchronous.
    """

    async def test_publish_and_wait_for_message(self, mqtt_test_client):
        """Test that published messages can be retrieved with wait_for_message()."""
        await mqtt_test_client.publish("kaiser/god/esp/test/command", {"cmd": "ping"})
        message = mqtt_test_client.wait_for_message("kaiser/god/esp/test/command", timeout=1)

        assert message["topic"] == "kaiser/god/esp/test/command"
        assert message["payload"]["cmd"] == "ping"

    async def test_subscribe_callback_invoked(self, mqtt_test_client):
        """Test that subscribe callbacks are invoked when messages are published."""
        calls = []

        def on_message(msg):
            calls.append(msg)

        mqtt_test_client.subscribe("kaiser/god/esp/test/response", callback=on_message)
        await mqtt_test_client.publish("kaiser/god/esp/test/response", {"ok": True})

        assert len(calls) == 1
        assert calls[0]["payload"]["ok"] is True


# Skip real hardware tests for now (MQTT client not yet implemented)
@pytest.mark.skip(reason="Real ESP32 MQTT client not yet implemented")
class TestClientLifecycle:
    """Test client connection lifecycle (connect/disconnect)."""

    def test_mock_client_disconnect(self, mock_esp32):
        """Test MockESP32Client disconnect() method."""
        # Client should be connected initially
        assert mock_esp32.connected is True

        # Disconnect
        mock_esp32.disconnect()

        # Client should be disconnected
        assert mock_esp32.connected is False

    def test_mock_client_api_compatibility(self, mock_esp32):
        """Test MockESP32Client has same API as RealESP32Client."""
        # Verify essential methods exist
        assert hasattr(mock_esp32, "handle_command")
        assert hasattr(mock_esp32, "get_actuator_state")
        assert hasattr(mock_esp32, "set_sensor_value")
        assert hasattr(mock_esp32, "get_published_messages")
        assert hasattr(mock_esp32, "clear_published_messages")
        assert hasattr(mock_esp32, "reset")
        assert hasattr(mock_esp32, "disconnect")  # NEW: API compatibility with RealESP32Client

        # Verify methods are callable
        assert callable(mock_esp32.handle_command)
        assert callable(mock_esp32.disconnect)


class TestRealHardware:
    """Tests against real ESP32 hardware (TODO: implement when MQTT client ready)."""

    def test_real_esp32_ping(self, real_esp32):
        """Test ping against real ESP32 device."""
        if real_esp32 is None:
            pytest.skip("No real ESP32 available")

        response = real_esp32.send_command("ping", {})
        assert response["status"] == "ok"
        assert response["command"] == "pong"

    def test_real_esp32_response_time(self, real_esp32):
        """Test response time against real hardware."""
        if real_esp32 is None:
            pytest.skip("No real ESP32 available")

        start_time = time.time()
        response = real_esp32.send_command("ping", {})
        end_time = time.time()

        response_time = (end_time - start_time) * 1000
        assert response_time < 500, f"Response time too slow: {response_time:.2f}ms"
