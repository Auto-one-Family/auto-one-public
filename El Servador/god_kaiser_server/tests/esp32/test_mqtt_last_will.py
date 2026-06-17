"""
Tests for MQTT Last-Will Testament (Safety-Critical).

Validates that the ESP32 configures a Last-Will message so the server
is notified when the device disconnects ungracefully.

Firmware reference: El Trabajante/src/services/communication/mqtt_client.cpp
    - mqtt.setWill(topic, payload, retain=true, qos=1)
    - Topic: kaiser/{id}/esp/{esp_id}/system/will
    - Payload: {"status":"offline","reason":"disconnect"}

These tests verify the Last-Will configuration and payload format.
"""

import json
import time

import pytest

from .mocks.mock_esp32_client import MockESP32Client


class LastWillSimulator:
    """
    Simulates MQTT Last-Will Testament configuration from MQTTClient::connectToBroker().
    """

    def __init__(self, esp_id: str, kaiser_id: str = "god"):
        self.esp_id = esp_id
        self.kaiser_id = kaiser_id
        self.will_config: dict | None = None

    def configure_last_will(self):
        """Simulate setWill() call during connectToBroker()."""
        topic = f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/system/will"
        payload = {
            "status": "offline",
            "reason": "disconnect",
            "esp_id": self.esp_id,
            "timestamp": int(time.time()),
        }
        self.will_config = {
            "topic": topic,
            "payload": payload,
            "retain": True,
            "qos": 1,
        }

    def simulate_ungraceful_disconnect(self) -> dict | None:
        """
        Simulate what the broker sends when the client disconnects ungracefully.

        Returns the Last-Will message that would be published by the broker.
        """
        if self.will_config:
            return {
                "topic": self.will_config["topic"],
                "payload": self.will_config["payload"],
                "qos": self.will_config["qos"],
                "retain": self.will_config["retain"],
            }
        return None


class TestMQTTLastWill:
    """Tests for MQTT Last-Will Testament."""

    @pytest.fixture
    def sim(self):
        simulator = LastWillSimulator(esp_id="ESP_WILL_TEST", kaiser_id="god")
        simulator.configure_last_will()
        return simulator

    def test_topic_format_correct(self, sim):
        """LW-001: Last-Will topic matches expected format."""
        assert sim.will_config is not None
        expected = f"kaiser/god/esp/{sim.esp_id}/system/will"
        assert sim.will_config["topic"] == expected

    def test_payload_contains_required_fields(self, sim):
        """LW-002: Payload contains status, reason, esp_id, and timestamp."""
        payload = sim.will_config["payload"]

        assert payload["status"] == "offline"
        assert payload["reason"] == "disconnect"
        assert payload["esp_id"] == sim.esp_id
        assert "timestamp" in payload
        assert isinstance(payload["timestamp"], int)

    def test_qos_is_one(self, sim):
        """LW-003: QoS level is 1 (at-least-once delivery)."""
        assert sim.will_config["qos"] == 1

    def test_broker_sends_will_on_ungraceful_disconnect(self, sim):
        """LW-004: Broker publishes Last-Will on ungraceful disconnect."""
        message = sim.simulate_ungraceful_disconnect()

        assert message is not None
        assert "system/will" in message["topic"]
        assert message["payload"]["status"] == "offline"
        assert message["retain"] is True
        assert message["qos"] == 1
