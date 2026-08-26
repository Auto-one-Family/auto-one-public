"""AUT-1555: mount fields on existing SensorConfigCreate write mapping."""

from pathlib import Path

from pydantic import ValidationError

from src.api.v1.sensors import (
    _EXPORT_ALLOWED_COLUMNS,
    _EXPORT_DEFAULT_COLUMNS,
    _schema_to_model_fields,
)
from src.db.models.sensor import SensorConfig, SensorData
from src.schemas.sensor import SensorConfigCreate, SensorConfigUpdate

_ALEMBIC_MOUNT = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "add_sensor_mount_geometry_aut1555.py"
)


def _base_create(**overrides: object) -> SensorConfigCreate:
    payload: dict[str, object] = {
        "esp_id": "ESP_12AB34CD",
        "gpio": 34,
        "sensor_type": "temperature",
        "name": "Canopy Temp",
    }
    payload.update(overrides)
    return SensorConfigCreate.model_validate(payload)


def test_schema_to_model_fields_includes_mount_columns():
    req = _base_create(
        mount_height_cm=120.5,
        mount_medium="canopy",
        mount_angle_deg=45.0,
    )
    fields = _schema_to_model_fields(req)

    assert fields["mount_height_cm"] == 120.5
    assert fields["mount_medium"] == "canopy"
    assert fields["mount_angle_deg"] == 45.0
    assert "mount_height_cm" not in fields["sensor_metadata"]
    assert "mount_medium" not in fields["sensor_metadata"]
    assert "mount_angle_deg" not in fields["sensor_metadata"]


def test_schema_to_model_fields_omitted_mount_is_null():
    fields = _schema_to_model_fields(_base_create())

    assert fields["mount_height_cm"] is None
    assert fields["mount_medium"] is None
    assert fields["mount_angle_deg"] is None


def test_invalid_mount_medium_rejected_on_create_and_update():
    try:
        _base_create(mount_medium="soil")
        raise AssertionError("expected ValidationError for create")
    except ValidationError:
        pass

    try:
        SensorConfigUpdate.model_validate({"mount_medium": "water"})
        raise AssertionError("expected ValidationError for update")
    except ValidationError:
        pass


def test_mount_medium_catalog_accepts_all_four_values():
    for medium in ("air", "canopy", "substrate", "solution"):
        req = _base_create(mount_medium=medium)
        assert _schema_to_model_fields(req)["mount_medium"] == medium


def test_explicit_null_on_update_is_same_as_omit():
    """JSON null and omitted both become None — write path then skips (no clobber)."""
    omitted = SensorConfigUpdate.model_validate({})
    explicit_null = SensorConfigUpdate.model_validate({
        "mount_height_cm": None,
        "mount_medium": None,
        "mount_angle_deg": None,
    })
    assert omitted.mount_height_cm is None
    assert omitted.mount_medium is None
    assert omitted.mount_angle_deg is None
    assert explicit_null.mount_height_cm is None
    assert explicit_null.mount_medium is None
    assert explicit_null.mount_angle_deg is None


def test_unique_index_v3_untouched_by_mount_migration():
    source = _ALEMBIC_MOUNT.read_text(encoding="utf-8")
    assert "unique_esp_gpio_sensor_interface_v3" in source
    assert "DROP INDEX" not in source
    assert "CREATE UNIQUE INDEX" not in source
    table_arg_names = {arg.name for arg in SensorConfig.__table_args__ if hasattr(arg, "name")}
    assert "unique_esp_gpio_sensor_interface_v3" not in table_arg_names
    assert "ck_sensor_configs_mount_medium" in table_arg_names


def test_sensor_data_has_no_mount_columns():
    columns = set(SensorData.__table__.c.keys())
    assert "mount_height_cm" not in columns
    assert "mount_medium" not in columns
    assert "mount_angle_deg" not in columns


def test_export_default_columns_include_mount_via_config_join():
    """AUT-1577: mount_* live in the CSV head via config join, not on sensor_data."""
    for col in ("mount_height_cm", "mount_medium", "mount_angle_deg"):
        assert col in _EXPORT_DEFAULT_COLUMNS
        assert col in _EXPORT_ALLOWED_COLUMNS
