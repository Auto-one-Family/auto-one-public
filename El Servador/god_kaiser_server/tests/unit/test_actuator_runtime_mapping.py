"""Regression tests for actuator runtime mapping (0 = unlimited)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.api.v1.actuators import _model_to_schema_response
from src.core.config_mapping import ConfigMappingEngine


def test_seconds_to_ms_transform_preserves_unlimited_zero() -> None:
    """max_runtime transform uses 1h fallback, explicit 0 stays 0ms."""
    engine = ConfigMappingEngine()
    transform = engine.TRANSFORMS["seconds_to_ms"]

    assert transform(None) == 3_600_000
    assert transform(0) == 0
    assert transform(3600) == 3_600_000


def test_cooldown_seconds_to_ms_transform_preserves_no_cooldown_zero() -> None:
    """cooldown_seconds_to_ms uses 30s fallback for None; explicit 0 stays 0ms."""
    engine = ConfigMappingEngine()
    transform = engine.TRANSFORMS["cooldown_seconds_to_ms"]

    assert transform(None) == 30_000
    assert transform(0) == 0
    assert transform(300) == 300_000


def test_model_to_schema_response_preserves_zero_runtime_and_cooldown() -> None:
    """API response must not collapse explicit 0 values to null."""
    actuator = SimpleNamespace(
        id=uuid4(),
        esp_id=uuid4(),
        gpio=14,
        actuator_type="digital",
        actuator_name="Grow Light",
        enabled=True,
        safety_constraints={"max_runtime": 0, "cooldown_period": 0},
        actuator_metadata={},
        config_status="applied",
        config_error=None,
        config_error_detail=None,
        device_scope="zone_local",
        assigned_zones=[],
        assigned_subzones=[],
        fail_safe_on_disconnect=True,
        flow_rate_ml_s=None,
        concentration=None,
        dose_role=None,
        stock_recipe_ref=None,
        stock_prepared_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    response = _model_to_schema_response(actuator=actuator, esp_device_id="ESP_TEST_01", state=None)

    assert response.max_runtime_seconds == 0
    assert response.cooldown_seconds == 0
