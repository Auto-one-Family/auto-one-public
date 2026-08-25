"""AUT-723 E3: no fake 0.0 chart Y from missing avg_raw or warming_up."""

from datetime import datetime, timezone
from types import SimpleNamespace

from src.api.v1.sensors import _aggregated_row_to_reading, _raw_row_to_reading
from src.schemas.sensor import SensorReading


def test_aggregated_bucket_without_raw_has_null_not_zero() -> None:
    """Agg bucket with processed but no raw → raw_value is None, never 0.0."""
    row = SimpleNamespace(
        bucket=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        avg_raw=None,
        avg_processed=6.8,
        unit="pH",
        sensor_type="ph",
        min_val=6.7,
        max_val=6.9,
        sample_count=4,
    )

    reading = _aggregated_row_to_reading(row)

    assert reading is not None
    assert reading.raw_value is None
    assert reading.processed_value == 6.8
    dumped = reading.model_dump()
    assert dumped["raw_value"] is None
    assert dumped["raw_value"] != 0.0


def test_aggregated_bucket_without_any_y_is_omitted() -> None:
    """Agg bucket with neither raw nor processed → no fake chart point."""
    row = SimpleNamespace(
        bucket=datetime(2026, 8, 23, 13, 0, tzinfo=timezone.utc),
        avg_raw=None,
        avg_processed=None,
        unit="pH",
        sensor_type="ph",
        min_val=None,
        max_val=None,
        sample_count=1,
    )

    assert _aggregated_row_to_reading(row) is None


def test_aggregated_normal_sample_unchanged() -> None:
    """Normal aggregated sample keeps numeric raw and processed."""
    row = SimpleNamespace(
        bucket=datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc),
        avg_raw=2150.0,
        avg_processed=6.8,
        unit="pH",
        sensor_type="ph",
        min_val=6.5,
        max_val=7.1,
        sample_count=12,
    )

    reading = _aggregated_row_to_reading(row)

    assert reading is not None
    assert reading.raw_value == 2150.0
    assert reading.processed_value == 6.8
    assert reading.sample_count == 12


def test_raw_warming_up_is_not_a_chart_y() -> None:
    """warming_up rows are quality-only — omitted from /sensors/data series."""
    row = SimpleNamespace(
        timestamp=datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc),
        raw_value=0.0,
        processed_value=None,
        unit="pH",
        quality="warming_up",
        sensor_type="ph",
        zone_id=None,
        subzone_id=None,
    )

    assert _raw_row_to_reading(row) is None


def test_raw_normal_sample_unchanged() -> None:
    """Normal raw sample stays a chart point."""
    row = SimpleNamespace(
        timestamp=datetime(2026, 8, 23, 16, 0, tzinfo=timezone.utc),
        raw_value=2150.0,
        processed_value=6.8,
        unit="pH",
        quality="good",
        sensor_type="ph",
        zone_id="greenhouse",
        subzone_id="bed_a",
    )

    reading = _raw_row_to_reading(row)

    assert reading is not None
    assert reading.raw_value == 2150.0
    assert reading.processed_value == 6.8
    assert reading.quality == "good"


def test_sensor_reading_allows_null_raw() -> None:
    """Schema accepts raw_value=None so JSON can carry null instead of 0.0."""
    reading = SensorReading(
        timestamp=datetime(2026, 8, 23, 17, 0, tzinfo=timezone.utc),
        raw_value=None,
        processed_value=6.8,
        unit="pH",
        quality="aggregated",
        sensor_type="ph",
    )
    assert reading.raw_value is None
    assert reading.model_dump()["raw_value"] is None
