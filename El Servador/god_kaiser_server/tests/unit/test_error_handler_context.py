"""Unit tests for AUT-456 context extraction in ErrorEventHandler."""

from src.mqtt.handlers.error_handler import ErrorEventHandler


def test_extract_context_fields_returns_expected_keys():
    payload_context = {
        "topic": "kaiser/god/esp/ESP_698EB4/sensor/34/data",
        "gpio": 34,
        "sensor_type": "moisture",
        "reason_class": "queue_shed",
        "extra": "ignored",
    }

    result = ErrorEventHandler._extract_context_fields(payload_context)

    assert result == {
        "topic": "kaiser/god/esp/ESP_698EB4/sensor/34/data",
        "gpio": 34,
        "sensor_type": "moisture",
        "reason_class": "queue_shed",
    }


def test_extract_context_fields_handles_legacy_non_dict():
    assert ErrorEventHandler._extract_context_fields(None) == {}
    assert ErrorEventHandler._extract_context_fields("legacy-string") == {}
"""Unit tests for AUT-456 context extraction in ErrorEventHandler."""

from src.mqtt.handlers.error_handler import ErrorEventHandler


def test_extract_context_fields_returns_expected_keys():
    payload_context = {
        "topic": "kaiser/god/esp/ESP_698EB4/sensor/34/data",
        "gpio": 34,
        "sensor_type": "moisture",
        "reason_class": "queue_shed",
        "extra": "ignored",
    }

    result = ErrorEventHandler._extract_context_fields(payload_context)

    assert result == {
        "topic": "kaiser/god/esp/ESP_698EB4/sensor/34/data",
        "gpio": 34,
        "sensor_type": "moisture",
        "reason_class": "queue_shed",
    }


def test_extract_context_fields_handles_legacy_non_dict():
    assert ErrorEventHandler._extract_context_fields(None) == {}
    assert ErrorEventHandler._extract_context_fields("legacy-string") == {}
