"""AUT-1410 SR-1: stock_recipe_ref + stock_prepared_at on actuator schemas/model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.db.models.actuator import ActuatorConfig
from src.schemas.actuator import (
    ActuatorConfigCreate,
    ActuatorConfigResponse,
    ActuatorConfigUpdate,
)


def test_actuator_config_response_includes_null_stock_identity_by_default():
    now = datetime.now(timezone.utc)
    response = ActuatorConfigResponse(
        id=uuid.uuid4(),
        esp_id=uuid.uuid4(),
        esp_device_id="ESP_12AB34CD",
        gpio=5,
        actuator_type="digital",
        name="Stock B",
        enabled=True,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    body = response.model_dump()
    assert body["stock_recipe_ref"] is None
    assert body["stock_prepared_at"] is None


def test_actuator_config_response_round_trip_stock_identity():
    now = datetime.now(timezone.utc)
    recipe_id = uuid.uuid4()
    prepared_at = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    response = ActuatorConfigResponse(
        id=uuid.uuid4(),
        esp_id=uuid.uuid4(),
        esp_device_id="ESP_12AB34CD",
        gpio=18,
        actuator_type="digital",
        name="Stock A",
        enabled=True,
        is_active=False,
        created_at=now,
        updated_at=now,
        stock_recipe_ref=recipe_id,
        stock_prepared_at=prepared_at,
    )
    body = response.model_dump()
    assert body["stock_recipe_ref"] == recipe_id
    assert body["stock_prepared_at"] == prepared_at


def test_actuator_config_create_accepts_stock_identity_fields():
    recipe_id = uuid.uuid4()
    prepared_at = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)
    create = ActuatorConfigCreate(
        esp_id="ESP_12AB34CD",
        gpio=18,
        actuator_type="pump",
        name="Stock B",
        stock_recipe_ref=recipe_id,
        stock_prepared_at=prepared_at,
    )
    assert create.stock_recipe_ref == recipe_id
    assert create.stock_prepared_at == prepared_at
    assert "stock_recipe_ref" in create.model_fields_set
    assert "stock_prepared_at" in create.model_fields_set


def test_actuator_config_update_omitted_stock_identity_not_in_fields_set():
    update = ActuatorConfigUpdate(name="renamed")
    assert "stock_recipe_ref" not in update.model_fields_set
    assert "stock_prepared_at" not in update.model_fields_set


def test_actuator_config_model_has_nullable_stock_identity_columns():
    assert "stock_recipe_ref" in ActuatorConfig.__table__.columns
    assert "stock_prepared_at" in ActuatorConfig.__table__.columns
    assert ActuatorConfig.__table__.columns["stock_recipe_ref"].nullable is True
    assert ActuatorConfig.__table__.columns["stock_prepared_at"].nullable is True
    # No hard FK — soft UUID reference only.
    assert ActuatorConfig.__table__.columns["stock_recipe_ref"].foreign_keys == set()
