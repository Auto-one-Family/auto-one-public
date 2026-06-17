from src.services.device_response_contract import (
    CONTRACT_UNKNOWN_CODE,
    canonicalize_actuator_response,
    canonicalize_config_response,
)


def test_canonicalize_config_response_legacy_aliases():
    canonical = canonicalize_config_response(
        {
            "status": "failed",
            "config_type": "cfg",
            "count": 0,
            "error_code": "gpio_conflict",
            "correlation_id": "corr-1",
        },
        esp_id="ESP_01",
    )

    assert canonical.status == "error"
    assert canonical.config_type == "system"
    assert canonical.error_code == "GPIO_CONFLICT"
    assert canonical.is_contract_violation is False
    assert canonical.is_final is True


def test_canonicalize_config_response_unknown_values_to_contract_violation():
    canonical = canonicalize_config_response(
        {
            "status": "mystery",
            "type": "mystery_type",
            "error_code": "mystery_code",
        },
        esp_id="ESP_02",
    )

    assert canonical.status == "error"
    assert canonical.error_code == CONTRACT_UNKNOWN_CODE
    assert canonical.is_contract_violation is True
    assert canonical.correlation_id.startswith("missing-corr:cfg:ESP_02:")
    assert canonical.severity == "error"


def test_canonicalize_config_response_uses_request_id_when_correlation_missing():
    canonical = canonicalize_config_response(
        {
            "status": "success",
            "type": "sensor",
            "count": 1,
            "request_id": "req-123",
        },
        esp_id="ESP_77",
    )

    assert canonical.correlation_id == "req-123"
    assert canonical.is_contract_violation is True
    assert canonical.status == "success"


def test_canonicalize_actuator_response_uses_topic_authority():
    canonical = canonicalize_actuator_response(
        {
            "esp_id": "ESP_WRONG",
            "gpio": 99,
            "command": "on",
            "success": True,
            "ts": 1733000000,
            "correlation_id": "corr-2",
        },
        topic_esp_id="ESP_RIGHT",
        topic_gpio=12,
    )

    assert canonical.esp_id == "ESP_RIGHT"
    assert canonical.gpio == 12
    assert canonical.command == "ON"
    assert canonical.code == CONTRACT_UNKNOWN_CODE
    assert canonical.is_contract_violation is True


def test_canonicalize_actuator_response_missing_fields_stays_robust():
    canonical = canonicalize_actuator_response(
        {
            "value": "x",
            "success": "unknown",
        },
        topic_esp_id="ESP_03",
        topic_gpio=5,
    )

    assert canonical.esp_id == "ESP_03"
    assert canonical.gpio == 5
    assert canonical.success is False
    assert canonical.correlation_id.startswith("missing-corr:act:ESP_03:")
    assert canonical.is_contract_violation is True
