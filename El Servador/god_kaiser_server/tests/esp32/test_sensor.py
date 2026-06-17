"""
Sensor Tests - Server-orchestrated ESP32 sensor reading testing.

NOTE: These tests use the REAL MQTT topic structure (not separate test topics).
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Pre-production validation with authentic message routing
- Cross-ESP orchestration scenarios
- Seamless CI/CD → Staging → Production flow

Topic structure: kaiser/god/esp/{esp_id}/sensor/{gpio}/...
(Identical to production - see El Trabajante/docs/Mqtt_Protocoll.md)

Tests verify:
1. Sensor reading (RAW values)
2. Pi-Enhanced processing (server-side)
3. Sensor data publishing via MQTT
4. Sensor value simulation

Migration from ESP32 Tests:
- sensor_manager.cpp → test_sensor_read, test_sensor_data_publishing
- sensor_integration.cpp → test_sensor_mqtt_integration
- sensor_i2c_bus.cpp → (Hardware-specific, not applicable for Mock)
- sensor_onewire_bus.cpp → (Hardware-specific, not applicable for Mock)
"""

import pytest


class TestSensorReading:
    """Test sensor reading via MQTT commands."""

    def test_sensor_read_analog(self, mock_esp32_with_sensors):
        """Test reading analog sensor value."""
        # GPIO 34 is pre-configured as analog sensor (moisture)
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        assert response["status"] == "ok"
        assert response["command"] == "sensor_read"
        assert response["data"]["gpio"] == 34
        assert response["data"]["type"] == "analog"
        assert "raw_value" in response["data"]

    def test_sensor_read_digital(self, mock_esp32_with_sensors):
        """Test reading digital sensor value."""
        # GPIO 36 is pre-configured as digital sensor (flow)
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 36})

        assert response["status"] == "ok"
        assert response["data"]["gpio"] == 36
        assert response["data"]["type"] == "digital"
        assert response["data"]["raw_value"] == 1.0  # Pre-configured value

    def test_sensor_read_raw_value_range(self, mock_esp32_with_sensors):
        """Test sensor raw values are in expected range."""
        # GPIO 34 is analog (ADC range: 0-4095 for ESP32)
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        raw_value = response["data"]["raw_value"]
        # Mock uses float, real ESP32 would use 0-4095 integer range
        assert isinstance(raw_value, (int, float))
        assert raw_value >= 0  # Non-negative

    def test_sensor_read_nonexistent_gpio(self, mock_esp32):
        """Test reading from non-existent sensor creates it with default value."""
        # Reading non-existent sensor should auto-create it
        response = mock_esp32.handle_command("sensor_read", {"gpio": 38})

        assert response["status"] == "ok"
        assert response["data"]["gpio"] == 38
        assert response["data"]["raw_value"] == 0.0  # Default value

    def test_sensor_read_missing_gpio(self, mock_esp32):
        """Test sensor_read without gpio parameter."""
        response = mock_esp32.handle_command("sensor_read", {})

        assert response["status"] == "error"
        assert "missing" in response["error"].lower() or "gpio" in response["error"].lower()


class TestSensorDataPublishing:
    """Test sensor data publishing via MQTT."""

    def test_sensor_read_publishes_data(self, mock_esp32_with_sensors):
        """Test sensor_read publishes data to MQTT topic."""
        mock_esp32_with_sensors.clear_published_messages()

        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        messages = mock_esp32_with_sensors.get_published_messages()
        # With zone configured, publishes to both normal and zone topic
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1

        message = sensor_msgs[0]
        assert f"kaiser/god/esp/{mock_esp32_with_sensors.esp_id}/sensor/34/data" in message["topic"]
        assert message["payload"]["gpio"] == 34
        # Production uses "raw" field per Mqtt_Protocoll.md
        assert "raw" in message["payload"]

    def test_sensor_data_topic_format(self, mock_esp32_with_sensors):
        """Test sensor data topic follows correct format."""
        mock_esp32_with_sensors.clear_published_messages()

        mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 35})

        messages = mock_esp32_with_sensors.get_published_messages()
        topic = messages[0]["topic"]

        # Format: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
        assert "kaiser/god/esp/" in topic
        assert "/sensor/35/data" in topic
        assert mock_esp32_with_sensors.esp_id in topic

    def test_sensor_data_payload_structure(self, mock_esp32_with_sensors):
        """Test sensor data payload has correct structure per Mqtt_Protocoll.md."""
        mock_esp32_with_sensors.clear_published_messages()

        mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        messages = mock_esp32_with_sensors.get_published_messages()
        payload = messages[0]["payload"]

        assert "gpio" in payload
        # Production uses "raw" field per Mqtt_Protocoll.md
        assert "raw" in payload
        assert "ts" in payload  # Timestamp is "ts" per protocol


class TestPiEnhancedProcessing:
    """Test Pi-Enhanced sensor processing (server-side)."""

    def test_raw_value_sent_to_server(self, mock_esp32_with_sensors):
        """Test RAW sensor value is sent to server."""
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Response includes RAW value
        assert "raw_value" in response["data"]
        raw_value = response["data"]["raw_value"]

        # RAW value should be unprocessed (2048.0 as configured)
        assert raw_value == 2048.0

    def test_processed_value_optional(self, mock_esp32_with_sensors):
        """Test processed value is optional (server-side processing)."""
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Processed value may be None if not processed yet
        processed = response["data"].get("processed_value")
        # Mock doesn't process, so should be None
        assert processed is None or isinstance(processed, (int, float))

    def test_sensor_value_simulation(self, mock_esp32):
        """Test setting sensor value for simulation."""
        # Set sensor value programmatically
        mock_esp32.set_sensor_value(gpio=40, raw_value=3000.0, sensor_type="analog")

        # Read sensor value
        response = mock_esp32.handle_command("sensor_read", {"gpio": 40})

        assert response["data"]["raw_value"] == 3000.0
        assert response["data"]["type"] == "analog"


class TestMultipleSensors:
    """Test reading multiple sensors."""

    def test_three_preconfigured_sensors(self, mock_esp32_with_sensors):
        """Test fixture provides 3 pre-configured sensors."""
        # GPIO 34: Moisture (analog)
        # GPIO 35: Temperature (analog)
        # GPIO 36: Flow (digital)

        sensors = [34, 35, 36]
        for gpio in sensors:
            response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": gpio})
            assert response["status"] == "ok"
            assert response["data"]["gpio"] == gpio

    def test_sensors_independent(self, mock_esp32_with_sensors):
        """Test sensors operate independently."""
        # Read sensor 34
        response1 = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        # Read sensor 35
        response2 = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 35})

        # Values should be different (different pre-configured values)
        assert response1["data"]["raw_value"] != response2["data"]["raw_value"]

    def test_multiple_sensor_reads_publish_separately(self, mock_esp32_with_sensors):
        """Test multiple sensor reads publish separate messages."""
        mock_esp32_with_sensors.clear_published_messages()

        mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 35})

        messages = mock_esp32_with_sensors.get_published_messages()
        # With zone configured, each sensor publishes to both normal and zone topic
        assert len(messages) >= 2

        topics = [msg["topic"] for msg in messages]
        assert any("/sensor/34/data" in topic for topic in topics)
        assert any("/sensor/35/data" in topic for topic in topics)


class TestSensorTimestamps:
    """Test sensor reading timestamps."""

    def test_sensor_read_includes_timestamp(self, mock_esp32_with_sensors):
        """Test sensor read response includes timestamp."""
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        assert "timestamp" in response["data"]
        assert isinstance(response["data"]["timestamp"], (int, float))
        assert response["data"]["timestamp"] > 0

    def test_sensor_timestamp_updates_on_read(self, mock_esp32_with_sensors):
        """Test sensor timestamp updates on each read."""
        # First read
        response1 = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        timestamp1 = response1["data"]["timestamp"]

        import time

        time.sleep(0.01)  # Small delay

        # Second read
        response2 = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        timestamp2 = response2["data"]["timestamp"]

        # Timestamp should be updated
        assert timestamp2 > timestamp1


class TestSensorTypes:
    """Test different sensor types."""

    def test_analog_sensor_type(self, mock_esp32_with_sensors):
        """Test analog sensor (GPIO 34 - Moisture)."""
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        assert response["data"]["type"] == "analog"
        # Analog sensors typically have raw values in ADC range
        assert isinstance(response["data"]["raw_value"], (int, float))

    def test_digital_sensor_type(self, mock_esp32_with_sensors):
        """Test digital sensor (GPIO 36 - Flow)."""
        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 36})

        assert response["data"]["type"] == "digital"
        # Digital sensors typically have 0 or 1 values
        assert response["data"]["raw_value"] in [0.0, 1.0]

    def test_sensor_type_consistency(self, mock_esp32):
        """Test sensor type remains consistent across reads."""
        # Create sensor with specific type
        mock_esp32.set_sensor_value(gpio=42, raw_value=100.0, sensor_type="analog")

        # Read multiple times
        for _ in range(3):
            response = mock_esp32.handle_command("sensor_read", {"gpio": 42})
            assert response["data"]["type"] == "analog"


class TestSensorValueChanges:
    """Test sensor value changes over time."""

    def test_sensor_value_can_change(self, mock_esp32):
        """Test sensor value can be updated."""
        # Set initial value
        mock_esp32.set_sensor_value(gpio=45, raw_value=100.0)

        # Read initial value
        response1 = mock_esp32.handle_command("sensor_read", {"gpio": 45})
        assert response1["data"]["raw_value"] == 100.0

        # Update value
        mock_esp32.set_sensor_value(gpio=45, raw_value=200.0)

        # Read updated value
        response2 = mock_esp32.handle_command("sensor_read", {"gpio": 45})
        assert response2["data"]["raw_value"] == 200.0

    def test_sensor_value_simulation_sequence(self, mock_esp32):
        """Test simulating a sequence of sensor values."""
        gpio = 50
        values = [100.0, 150.0, 200.0, 250.0, 300.0]

        for expected_value in values:
            mock_esp32.set_sensor_value(gpio=gpio, raw_value=expected_value)
            response = mock_esp32.handle_command("sensor_read", {"gpio": gpio})
            assert response["data"]["raw_value"] == expected_value


class TestSensorIntegration:
    """Test sensor integration with other systems."""

    def test_sensor_read_doesnt_affect_actuators(self, mock_esp32_with_actuators):
        """Test sensor reads don't affect actuator states."""
        # Set actuator state
        mock_esp32_with_actuators.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Read sensor (non-existent, will create)
        mock_esp32_with_actuators.handle_command("sensor_read", {"gpio": 34})

        # Verify actuator state unchanged
        actuator_response = mock_esp32_with_actuators.handle_command("actuator_get", {"gpio": 5})
        assert actuator_response["data"]["state"] is True

    def test_sensor_and_actuator_on_different_gpios(self, mock_esp32_with_sensors):
        """Test sensors and actuators can coexist on different GPIOs."""
        # Add actuator
        mock_esp32_with_sensors.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Read sensor (different GPIO)
        sensor_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
        actuator_response = mock_esp32_with_sensors.handle_command("actuator_get", {"gpio": 5})

        # Both should work independently
        assert sensor_response["status"] == "ok"
        assert actuator_response["status"] == "ok"


class TestSensorErrorCases:
    """Test sensor error handling."""

    def test_sensor_read_recovers_gracefully(self, mock_esp32):
        """Test sensor read handles non-existent sensors gracefully."""
        # Reading non-existent sensor should create it with default value (not error)
        response = mock_esp32.handle_command("sensor_read", {"gpio": 99})

        assert response["status"] == "ok"
        assert response["data"]["raw_value"] == 0.0  # Default value
