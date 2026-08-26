"""AUT-1577: honest schema CSV head on the existing sensor export serializer."""

from datetime import datetime, timezone
from types import SimpleNamespace

from src.api.v1.sensors import (
    _EXPORT_ALLOWED_COLUMNS,
    _EXPORT_DEFAULT_COLUMNS,
    _ensure_schema_columns,
    _export_column_value,
    _format_export_timestamp,
)
from src.db.models.sensor import SensorConfig, SensorData


EXPECTED_DEFAULT_HEADER = [
    "timestamp",
    "processed_value",
    "unit",
    "quality",
    "sensor_type",
    "timezone",
    "esp_id",
    "zone_id",
    "subzone_id",
    "sample_interval_ms",
    "mount_height_cm",
    "mount_medium",
    "mount_angle_deg",
    "calibrated_at",
    "site_id",
]


def test_default_header_contains_required_schema_names():
    assert list(_EXPORT_DEFAULT_COLUMNS) == EXPECTED_DEFAULT_HEADER
    for name in ("unit", "timezone", "zone_id", "mount_medium", "esp_id", "calibrated_at", "quality"):
        assert name in _EXPORT_DEFAULT_COLUMNS
        assert name in _EXPORT_ALLOWED_COLUMNS


def test_missing_calibrated_at_keeps_named_empty_cell():
    config = SimpleNamespace(
        sample_interval_ms=30000,
        mount_height_cm=None,
        mount_medium=None,
        mount_angle_deg=None,
        calibration_data={},
    )
    row = SimpleNamespace(
        timestamp=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
        processed_value=24.0,
        unit="°C",
        quality="good",
        sensor_type="temperature",
        zone_id="haus_a",
        subzone_id=None,
    )

    values = [
        _export_column_value(row, col, False, config=config, device_id="ESP_12AB34CD")
        for col in _EXPORT_DEFAULT_COLUMNS
    ]
    mapped = dict(zip(_EXPORT_DEFAULT_COLUMNS, values, strict=True))

    assert mapped["calibrated_at"] == ""
    assert mapped["mount_medium"] == ""
    assert mapped["mount_height_cm"] == ""
    assert mapped["mount_angle_deg"] == ""
    assert mapped["site_id"] == ""
    assert mapped["timezone"] == "UTC"
    assert mapped["unit"] == "°C"
    assert mapped["esp_id"] == "ESP_12AB34CD"
    assert mapped["zone_id"] == "haus_a"
    assert mapped["subzone_id"] == ""
    assert mapped["sample_interval_ms"] == "30000"
    assert mapped["quality"] == "good"
    assert "MIAPPE" not in "".join(values)


def test_canopy_medium_and_calibrated_at_from_config_join():
    config = SimpleNamespace(
        sample_interval_ms=15000,
        mount_height_cm=120.5,
        mount_medium="canopy",
        mount_angle_deg=45.0,
        calibration_data={"derived": {"calibrated_at": "2026-08-01T12:00:00+00:00"}},
    )
    row = SimpleNamespace(
        timestamp=datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc),
        processed_value=26.1,
        unit="°C",
        quality="good",
        sensor_type="temperature",
        zone_id="haus_b",
        subzone_id="canopy_1",
    )

    values = [
        _export_column_value(row, col, False, config=config, device_id="ESP_AABBCCDD")
        for col in _EXPORT_DEFAULT_COLUMNS
    ]
    mapped = dict(zip(_EXPORT_DEFAULT_COLUMNS, values, strict=True))

    assert mapped["mount_medium"] == "canopy"
    assert mapped["mount_height_cm"] == "120.5"
    assert mapped["mount_angle_deg"] == "45.0"
    assert mapped["calibrated_at"] == "2026-08-01T12:00:00+00:00"
    assert mapped["sample_interval_ms"] == "15000"
    assert mapped["timezone"] == "UTC"
    assert mapped["site_id"] == ""


def test_timestamp_is_forced_utc():
    naive = datetime(2026, 8, 26, 12, 0, 0)
    assert _format_export_timestamp(naive) == "2026-08-26T12:00:00+00:00"


def test_sensor_data_still_has_no_mount_or_site_columns():
    columns = set(SensorData.__table__.c.keys())
    assert "mount_height_cm" not in columns
    assert "mount_medium" not in columns
    assert "mount_angle_deg" not in columns
    assert "site_id" not in columns
    assert "calibrated_at" not in columns
    assert "sample_interval_ms" not in columns
    assert "sample_interval_ms" in SensorConfig.__table__.c.keys()


def test_old_five_column_request_still_appends_schema_head():
    """AUT-1577 briefing: columns= old five must still carry Pflicht-Spalten."""
    requested = ["timestamp", "processed_value", "unit", "quality", "sensor_type"]
    merged = _ensure_schema_columns(requested)
    assert merged[:5] == requested
    assert merged == EXPECTED_DEFAULT_HEADER
    assert "timezone" in merged
    assert "esp_id" in merged
    assert "mount_medium" in merged
    assert "calibrated_at" in merged
    assert "site_id" in merged


def test_aggregated_config_cells_stay_empty():
    row = SimpleNamespace(
        bucket=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
        avg_processed=24.0,
        unit="°C",
        sensor_type="temperature",
    )
    assert _export_column_value(row, "mount_medium", True, config=None, device_id="") == ""
    assert _export_column_value(row, "calibrated_at", True, config=None, device_id="") == ""
    assert _export_column_value(row, "esp_id", True, config=None, device_id="ESP_X") == ""
    assert _export_column_value(row, "timezone", True) == "UTC"
    assert _export_column_value(row, "site_id", True) == ""
