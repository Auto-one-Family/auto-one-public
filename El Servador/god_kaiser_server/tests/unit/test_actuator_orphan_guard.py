from src.services.actuator_orphan_guard import (
    is_orphan_external_actuator_failure,
    parse_gpio_from_actuator_error_message,
    should_suppress_actuator_not_found_error_broadcast,
)


def test_orphan_external_actuator_failure_missing_corr_unconfigured_gpio():
    assert is_orphan_external_actuator_failure(
        success=False,
        correlation_id="missing-corr:act:ESP_70705C:1780019956",
        command="UNKNOWN_COMMAND",
        has_actuator_config=False,
    )


def test_orphan_external_actuator_failure_not_orphan_when_configured():
    assert not is_orphan_external_actuator_failure(
        success=False,
        correlation_id="missing-corr:act:ESP_70705C:1780019956",
        command="UNKNOWN_COMMAND",
        has_actuator_config=True,
    )


def test_parse_gpio_from_actuator_error_message():
    assert parse_gpio_from_actuator_error_message(
        "Actuator not configured on GPIO 0. Configure via API first."
    ) == 0


def test_suppress_actuator_not_found_error_broadcast():
    assert should_suppress_actuator_not_found_error_broadcast(
        error_code=1052,
        message="Actuator not configured on GPIO 0. Configure via API first.",
        context_gpio=None,
        has_actuator_config=False,
    )
