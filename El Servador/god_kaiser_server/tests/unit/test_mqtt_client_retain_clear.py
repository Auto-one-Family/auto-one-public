"""Unit tests for MQTT retained-message deletion helper."""

from unittest.mock import MagicMock, patch

from src.mqtt.client import MQTTClient


def test_clear_retained_message_publishes_empty_with_retain():
    client = MQTTClient.__new__(MQTTClient)
    client.client = MagicMock()
    client.connected = True
    client._circuit_breaker = None
    client._offline_buffer = None
    client._event_loop = None

    publish_result = MagicMock()
    publish_result.rc = 0
    client.client.publish.return_value = publish_result

    with patch("src.core.metrics.increment_mqtt_published"):
        ok = client.clear_retained_message("kaiser/broadcast/emergency")

    assert ok is True
    client.client.publish.assert_called_once_with(
        "kaiser/broadcast/emergency",
        "",
        0,
        True,
    )


def test_clear_retained_message_rejects_empty_topic():
    client = MQTTClient.__new__(MQTTClient)
    client.client = MagicMock()
    client.connected = True
    client._circuit_breaker = None
    client._offline_buffer = None
    client._event_loop = None

    assert client.clear_retained_message("") is False
    client.client.publish.assert_not_called()
