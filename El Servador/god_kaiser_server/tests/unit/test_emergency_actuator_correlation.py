"""Emergency stop: per-GPIO MQTT correlation_id (Epic 1-03)."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.request_context import build_emergency_actuator_correlation_id
from src.mqtt.publisher import Publisher


def test_build_emergency_actuator_correlation_id_format():
    incident = "11111111-1111-1111-1111-111111111111"
    assert build_emergency_actuator_correlation_id(incident, "ESP_TEST01", 5) == (
        f"{incident}:ESP_TEST01:5"
    )


def test_build_emergency_actuator_correlation_id_unique_per_gpio():
    incident = "22222222-2222-2222-2222-222222222222"
    a = build_emergency_actuator_correlation_id(incident, "ESP_X", 4)
    b = build_emergency_actuator_correlation_id(incident, "ESP_X", 5)
    assert a != b


@pytest.mark.parametrize("correlation_id", [None, ""])
def test_publish_actuator_command_omits_correlation_when_missing(correlation_id):
    mock_client = MagicMock()
    pub = Publisher(mqtt_client=mock_client)

    captured = {}

    def fake_publish(topic, payload, qos, retry):
        captured["payload"] = payload
        return True

    with patch.object(pub, "_publish_with_retry", side_effect=fake_publish):
        pub.publish_actuator_command(
            "ESP_1", 3, "OFF", 0.0, duration=0, retry=True, correlation_id=correlation_id
        )

    assert "correlation_id" not in captured["payload"]


def test_publish_actuator_command_includes_correlation_in_payload():
    mock_client = MagicMock()
    pub = Publisher(mqtt_client=mock_client)

    captured = {}

    def fake_publish(topic, payload, qos, retry):
        captured["payload"] = payload
        return True

    incident = "33333333-3333-3333-3333-333333333333"
    cid = build_emergency_actuator_correlation_id(incident, "ESP_ABC", 12)

    with patch.object(pub, "_publish_with_retry", side_effect=fake_publish):
        pub.publish_actuator_command(
            "ESP_ABC",
            12,
            "OFF",
            0.0,
            duration=0,
            retry=True,
            correlation_id=cid,
        )

    assert captured["payload"]["correlation_id"] == cid
    assert captured["payload"]["command"] == "OFF"
