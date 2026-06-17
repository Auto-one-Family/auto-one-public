"""
Timing Behavior Tests (TIME Category).

Tests timestamp consistency, heartbeat payload structure, actuator safety timeout
tracking, and batch sensor ordering.

Pattern: MockESP32Client (synchron).
"""

import time

import pytest

from tests.esp32.mocks.mock_esp32_client import MockESP32Client

# =========================================================================
# Timestamp Consistency
# =========================================================================


class TestTimestampConsistency:
    """Sensor data timestamps are Unix seconds, monotonically increasing."""

    @pytest.fixture
    def sensor_esp(self):
        esp = MockESP32Client(esp_id="ESP_TIME001")
        esp.configure_zone("time_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=22.5, sensor_type="DS18B20")
        esp.set_sensor_value(gpio=35, raw_value=65.0, sensor_type="analog")
        esp.clear_published_messages()
        yield esp
        esp.reset()

    def test_sensor_data_has_unix_timestamp(self, sensor_esp):
        """Sensor data payload contains 'ts' in Unix seconds."""
        sensor_esp.handle_command("sensor_read", {"gpio": 34})

        messages = sensor_esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1

        payload = sensor_msgs[0]["payload"]
        assert "ts" in payload
        # Unix timestamp should be a reasonable value (after 2020)
        assert payload["ts"] > 1577836800  # 2020-01-01

    def test_timestamps_monotonic_across_reads(self, sensor_esp):
        """Sequential sensor reads produce non-decreasing timestamps."""
        sensor_esp.handle_command("sensor_read", {"gpio": 34})
        sensor_esp.handle_command("sensor_read", {"gpio": 34})

        messages = sensor_esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 2

        ts1 = sensor_msgs[0]["payload"]["ts"]
        ts2 = sensor_msgs[1]["payload"]["ts"]
        assert ts2 >= ts1, f"Timestamps should be monotonic: {ts1} <= {ts2}"

    def test_timestamp_in_seconds_not_milliseconds(self, sensor_esp):
        """Timestamps are in seconds (not milliseconds)."""
        sensor_esp.handle_command("sensor_read", {"gpio": 34})

        messages = sensor_esp.get_published_messages()
        payload = messages[0]["payload"]

        # Milliseconds would be > 1e12, seconds are ~1.7e9
        assert payload["ts"] < 1e12, "Timestamp appears to be in milliseconds, should be seconds"


# =========================================================================
# Heartbeat Payload Structure
# =========================================================================


class TestHeartbeatPayload:
    """Heartbeat contains required fields."""

    def test_heartbeat_has_required_fields(self):
        """Heartbeat payload includes uptime, heap_free, ts."""
        esp = MockESP32Client(esp_id="ESP_HB001")
        esp.configure_zone("hb_zone", "main_zone")
        esp.clear_published_messages()

        result = esp.handle_command("heartbeat", {})
        assert result["status"] == "ok"

        messages = esp.get_published_messages()
        hb_msgs = [m for m in messages if "heartbeat" in m["topic"]]
        assert len(hb_msgs) >= 1

        payload = hb_msgs[0]["payload"]
        # Required fields per MQTT protocol
        assert "ts" in payload or "timestamp" in payload
        assert "heap_free" in payload or "free_heap" in payload

    def test_heartbeat_contains_esp_id(self):
        """Heartbeat payload identifies the ESP."""
        esp = MockESP32Client(esp_id="ESP_HB002")
        esp.configure_zone("hb_zone", "main_zone")
        esp.clear_published_messages()

        esp.handle_command("heartbeat", {})

        messages = esp.get_published_messages()
        hb_msgs = [m for m in messages if "heartbeat" in m["topic"]]
        assert len(hb_msgs) >= 1

        payload = hb_msgs[0]["payload"]
        assert payload.get("esp_id") == "ESP_HB002"

    def test_heartbeat_topic_format(self):
        """Heartbeat topic follows kaiser/god/esp/{id}/system/heartbeat."""
        esp = MockESP32Client(esp_id="ESP_HB003")
        esp.configure_zone("hb_zone", "main_zone")
        esp.clear_published_messages()

        esp.handle_command("heartbeat", {})

        messages = esp.get_published_messages()
        hb_msgs = [m for m in messages if "heartbeat" in m["topic"]]
        assert len(hb_msgs) >= 1

        topic = hb_msgs[0]["topic"]
        assert "kaiser/god/esp/ESP_HB003/system/heartbeat" in topic


# =========================================================================
# Actuator Safety Timeout
# =========================================================================


class TestActuatorSafetyTimeout:
    """Actuator safety_timeout_ms configuration and tracking."""

    def test_actuator_timeout_configured(self):
        """Actuator with safety_timeout_ms tracks the value."""
        esp = MockESP32Client(esp_id="ESP_TO001")
        esp.configure_zone("timeout_zone", "main_zone")
        esp.configure_actuator(
            gpio=25,
            actuator_type="pump",
            name="Timed Pump",
            safety_timeout_ms=300000,  # 5 minutes
        )

        actuator = esp.get_actuator_state(25)
        assert actuator.safety_timeout_ms == 300000

    def test_actuator_activation_records_timestamp(self):
        """Activating an actuator updates its timestamp."""
        esp = MockESP32Client(esp_id="ESP_TO002")
        esp.configure_zone("timeout_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pump")

        before = time.time()
        esp.handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})
        after = time.time()

        actuator = esp.get_actuator_state(25)
        assert before <= actuator.timestamp <= after


# =========================================================================
# Batch Sensor Ordering
# =========================================================================


class TestBatchSensorOrdering:
    """Multiple sensor reads maintain correct ordering."""

    def test_multiple_sensors_all_publish(self):
        """Reading 3 sensors produces 3 published messages."""
        esp = MockESP32Client(esp_id="ESP_BATCH001")
        esp.configure_zone("batch_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=22.0, sensor_type="DS18B20")
        esp.set_sensor_value(gpio=35, raw_value=65.0, sensor_type="analog")
        esp.set_sensor_value(gpio=36, raw_value=1.0, sensor_type="digital")
        esp.clear_published_messages()

        for gpio in [34, 35, 36]:
            esp.handle_command("sensor_read", {"gpio": gpio})

        messages = esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/" in m["topic"] and "/data" in m["topic"]]
        assert len(sensor_msgs) >= 3

    def test_sensor_messages_maintain_gpio_order(self):
        """Sensor messages appear in the order they were read."""
        esp = MockESP32Client(esp_id="ESP_BATCH002")
        esp.configure_zone("batch_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=22.0, sensor_type="DS18B20")
        esp.set_sensor_value(gpio=35, raw_value=65.0, sensor_type="analog")
        esp.set_sensor_value(gpio=36, raw_value=1.0, sensor_type="digital")
        esp.clear_published_messages()

        for gpio in [34, 35, 36]:
            esp.handle_command("sensor_read", {"gpio": gpio})

        messages = esp.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/" in m["topic"] and "/data" in m["topic"]]

        # Extract GPIOs in order
        gpios = [m["payload"]["gpio"] for m in sensor_msgs]
        assert gpios == [34, 35, 36], f"GPIO order should be [34, 35, 36], got {gpios}"

    def test_sensor_values_match_configured(self):
        """Each sensor's published value matches its configured value."""
        esp = MockESP32Client(esp_id="ESP_BATCH003")
        esp.configure_zone("batch_zone", "main_zone")
        esp.set_sensor_value(gpio=34, raw_value=22.0, sensor_type="DS18B20")
        esp.set_sensor_value(gpio=35, raw_value=65.0, sensor_type="analog")
        esp.clear_published_messages()

        esp.handle_command("sensor_read", {"gpio": 34})
        esp.handle_command("sensor_read", {"gpio": 35})

        messages = esp.get_published_messages()
        sensor_msgs = {
            m["payload"]["gpio"]: m["payload"] for m in messages if "/sensor/" in m["topic"]
        }

        assert sensor_msgs[34]["value"] == 22.0
        assert sensor_msgs[35]["value"] == 65.0
