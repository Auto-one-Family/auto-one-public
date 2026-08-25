"""AUT-1412 SR-2: atomic stock reset via existing explicit-null upsert path."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from src.api.v1.actuators import _schema_to_model_fields
from src.schemas.actuator import ActuatorConfigCreate


def _base_create(**overrides: object) -> ActuatorConfigCreate:
    payload: dict[str, object] = {
        "esp_id": "ESP_12AB34CD",
        "gpio": 18,
        "actuator_type": "pump",
        "name": "Stock B",
        "enabled": True,
        "flow_rate_ml_s": 2.5,
        "concentration": 42.0,
        "dose_role": "part_b",
    }
    payload.update(overrides)
    return ActuatorConfigCreate.model_validate(payload)


def test_reset_sets_concentration_null_and_identity_without_clobbering():
    recipe_id = uuid.uuid4()
    prepared_at = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        safety_constraints={"max_runtime": 1800, "cooldown_period": 60},
        actuator_metadata={"keep": True},
        fail_safe_on_disconnect=True,
    )
    req = _base_create(
        concentration=None,
        stock_recipe_ref=recipe_id,
        stock_prepared_at=prepared_at,
        max_runtime_seconds=1800,
        cooldown_seconds=60,
    )
    fields = _schema_to_model_fields(req, existing=existing)

    assert "concentration" in fields
    assert fields["concentration"] is None
    assert fields["stock_recipe_ref"] == recipe_id
    assert fields["stock_prepared_at"] == prepared_at
    assert fields["flow_rate_ml_s"] == 2.5
    assert fields["dose_role"] == "part_b"
    assert fields["actuator_name"] == "Stock B"


def test_omit_concentration_and_identity_leaves_them_out_of_fields():
    req = ActuatorConfigCreate.model_validate(
        {
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "name": "Stock B",
            "flow_rate_ml_s": 3.0,
        }
    )
    fields = _schema_to_model_fields(req)

    assert "concentration" not in fields
    assert "stock_recipe_ref" not in fields
    assert "stock_prepared_at" not in fields
    assert fields["flow_rate_ml_s"] == 3.0


def test_partial_flow_rate_update_does_not_clear_identity_when_omitted():
    """Weglassen darf Identity/c nicht auf null setzen (kein Clobber)."""
    req = ActuatorConfigCreate.model_validate(
        {
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "name": "Stock A",
            "flow_rate_ml_s": 1.25,
            "dose_role": "part_a",
        }
    )
    fields = _schema_to_model_fields(req)
    assert fields["flow_rate_ml_s"] == 1.25
    assert fields["dose_role"] == "part_a"
    assert "concentration" not in fields
    assert "stock_recipe_ref" not in fields
    assert "stock_prepared_at" not in fields
