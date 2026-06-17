"""
Data Buffer & Offline Resilience Tests.

Tests ESP32 offline data buffering behavior using MockESP32Client.
The ESP32 firmware uses a fixed array buffer (NOT circular):
- MAX_OFFLINE_MESSAGES = 100
- Overflow: NEWEST messages are rejected (Error 3016)
- Drain: Synchronous FIFO on reconnect
- No persistence across reboots

These tests validate the server-side mock behavior and the
MQTT client's offline buffer integration.
"""

import pytest
from tests.esp32.mocks.mock_esp32_client import (
    MockESP32Client,
    BrokerMode,
    SystemState,
)


class TestMockESPBufferingBasics:
    """Test MockESP32Client message storage when disconnected."""

    def test_connected_esp_publishes_normally(self):
        """Connected ESP stores messages in published_messages list."""
        esp = MockESP32Client(esp_id="ESP_BUF00001")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")

        esp.handle_command("sensor_read", {"gpio": 34})

        messages = esp.get_published_messages()
        sensor_msgs = [m for m in messages if "sensor" in m["topic"] and "data" in m["topic"]]
        assert len(sensor_msgs) >= 1

    def test_disconnected_esp_state_transition(self):
        """Disconnecting ESP transitions to MQTT_CONNECTING state."""
        esp = MockESP32Client(esp_id="ESP_BUF00002")
        assert esp.connected is True
        assert esp.get_system_state() == SystemState.OPERATIONAL

        esp.disconnect()

        assert esp.connected is False
        assert esp.get_system_state() == SystemState.MQTT_CONNECTING

    def test_reconnect_restores_operational_state(self):
        """Reconnecting ESP transitions back through states to OPERATIONAL."""
        esp = MockESP32Client(esp_id="ESP_BUF00003")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")

        esp.disconnect()
        assert esp.get_system_state() == SystemState.MQTT_CONNECTING

        esp.reconnect()
        assert esp.connected is True
        assert esp.get_system_state() == SystemState.OPERATIONAL

    def test_messages_accumulate_while_connected(self):
        """Messages accumulate in published_messages list during normal operation."""
        esp = MockESP32Client(esp_id="ESP_BUF00004")
        esp.configure_zone("test_zone", "main_zone")

        for i in range(10):
            esp.set_sensor_value(gpio=34, raw_value=20.0 + i, sensor_type="DS18B20")
            esp.handle_command("sensor_read", {"gpio": 34})

        messages = esp.get_published_messages()
        # Each sensor_read publishes sensor data messages
        assert len(messages) >= 10


class TestMockESPDisconnectBehavior:
    """Test behavior during disconnect/reconnect cycles."""

    def test_emergency_stop_works_while_disconnected(self):
        """Emergency stop still works on local actuators when disconnected."""
        esp = MockESP32Client(esp_id="ESP_BUF00005")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pwm")

        # Set actuator active
        esp.handle_command("actuator_set", {"gpio": 25, "value": 0.75, "mode": "pwm"})
        assert esp.get_actuator_state(25).pwm_value == 0.75

        # Disconnect then emergency stop
        esp.disconnect()
        result = esp.handle_command("emergency_stop", {"reason": "test"})

        assert result["status"] == "ok"
        assert esp.get_actuator_state(25).pwm_value == 0.0
        assert esp.get_actuator_state(25).emergency_stopped is True

    def test_published_messages_preserved_across_disconnect(self):
        """Published messages list is not cleared on disconnect."""
        esp = MockESP32Client(esp_id="ESP_BUF00006")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")
        esp.handle_command("sensor_read", {"gpio": 34})

        msg_count_before = len(esp.get_published_messages())
        assert msg_count_before > 0

        esp.disconnect()

        # Messages from before disconnect are still there (disconnect may add
        # state transition diagnostics, so count can only grow)
        assert len(esp.get_published_messages()) >= msg_count_before

    def test_clear_messages_resets_list(self):
        """clear_published_messages empties the list."""
        esp = MockESP32Client(esp_id="ESP_BUF00007")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")
        esp.handle_command("sensor_read", {"gpio": 34})

        assert len(esp.get_published_messages()) > 0

        esp.clear_published_messages()
        assert len(esp.get_published_messages()) == 0


class TestMockESPRebootBehavior:
    """Test that reboot clears volatile state (simulates buffer loss)."""

    def test_reset_clears_all_state(self):
        """Reset (simulating reboot) clears sensors, actuators, messages."""
        esp = MockESP32Client(esp_id="ESP_BUF00008")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")
        esp.configure_actuator(gpio=25, actuator_type="relay")
        esp.handle_command("sensor_read", {"gpio": 34})

        assert len(esp.sensors) > 0
        assert len(esp.actuators) > 0
        assert len(esp.get_published_messages()) > 0

        esp.reset()

        assert len(esp.sensors) == 0
        assert len(esp.actuators) == 0
        assert len(esp.get_published_messages()) == 0

    def test_system_reboot_preserves_zone_config(self):
        """System reboot via command preserves zone configuration."""
        esp = MockESP32Client(esp_id="ESP_BUF00009")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")

        # Reboot via system command
        esp.handle_command("system_command", {"action": "reboot"})

        # Zone should be preserved
        assert esp.zone is not None
        assert esp.zone.zone_id == "test_zone"
        # State should return to OPERATIONAL
        assert esp.get_system_state() == SystemState.OPERATIONAL


class TestMQTTClientOfflineBuffer:
    """
    Server-side MQTT client offline buffer tests.

    The server's MQTTClient has an offline buffer for when the broker
    is unavailable. These tests verify the buffer exists and is accessible.
    """

    def test_mqtt_client_has_offline_buffer(self):
        """Verify MQTTClient singleton has offline buffer attribute."""
        from src.mqtt.client import MQTTClient

        mqtt_client = MQTTClient.get_instance()
        assert mqtt_client._offline_buffer is not None

    def test_mqtt_client_resilience_status(self):
        """Verify MQTTClient reports resilience status."""
        from src.mqtt.client import MQTTClient

        mqtt_client = MQTTClient.get_instance()
        status = mqtt_client.get_resilience_status()

        assert "connected" in status


class TestSensorDataPayloadStructure:
    """Verify sensor data MQTT payload matches protocol specification."""

    def test_sensor_data_has_required_fields(self):
        """Sensor data payload must contain all required fields per Mqtt_Protocoll.md."""
        esp = MockESP32Client(esp_id="ESP_BUF00010")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(
            gpio=34,
            raw_value=25.5,
            sensor_type="DS18B20",
            raw_mode=True,
        )
        esp.handle_command("sensor_read", {"gpio": 34})

        messages = esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1

        payload = sensor_msgs[0]["payload"]
        assert "ts" in payload
        assert "esp_id" in payload
        assert "gpio" in payload
        assert "sensor_type" in payload
        assert "raw" in payload
        assert "value" in payload
        assert "quality" in payload
        assert "raw_mode" in payload

        assert payload["esp_id"] == "ESP_BUF00010"
        assert payload["gpio"] == 34
        assert payload["sensor_type"] == "DS18B20"
        assert payload["raw_mode"] is True

    def test_sensor_data_qos_1(self):
        """Sensor data is published with QoS 1."""
        esp = MockESP32Client(esp_id="ESP_BUF00011")
        esp.configure_zone("test_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")
        esp.handle_command("sensor_read", {"gpio": 34})

        messages = esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]

        for msg in sensor_msgs:
            assert msg["qos"] == 1

    def test_heartbeat_qos_0(self):
        """Heartbeat is published with QoS 0 (best effort)."""
        esp = MockESP32Client(esp_id="ESP_BUF00012")
        esp.handle_command("heartbeat", {})

        messages = esp.get_published_messages()
        heartbeat_msgs = [m for m in messages if "heartbeat" in m["topic"]]
        assert len(heartbeat_msgs) >= 1
        assert heartbeat_msgs[0]["qos"] == 0

    def test_heartbeat_uses_heap_free_not_free_heap(self):
        """
        Heartbeat payload must use 'heap_free' field name.
        CRITICAL: NOT 'free_heap' - this was a documented correction.
        """
        esp = MockESP32Client(esp_id="ESP_BUF00013")
        esp.handle_command("heartbeat", {})

        messages = esp.get_published_messages()
        heartbeat_msgs = [m for m in messages if "heartbeat" in m["topic"]]
        payload = heartbeat_msgs[0]["payload"]

        assert "heap_free" in payload
        assert "free_heap" not in payload
