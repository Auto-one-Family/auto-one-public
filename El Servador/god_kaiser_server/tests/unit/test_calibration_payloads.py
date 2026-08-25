"""Unit tests for canonical calibration payload adapters."""

from src.services.calibration_payloads import (
    build_canonical_calibration_result,
    canonicalize_calibration_data,
    read_calibrated_at,
)


def test_canonicalize_calibration_data_accepts_none_for_legacy_nulls():
    assert canonicalize_calibration_data(None) is None


def test_canonicalize_calibration_data_preserves_canonical_shape():
    payload = {
        "method": "linear_2point",
        "points": [{"point_role": "dry", "raw": 900.0, "reference": 0.0}],
        "derived": {"slope": 0.5, "offset": -10.0},
        "metadata": {"schema_version": 1, "source": "test"},
    }
    normalized = canonicalize_calibration_data(payload)
    assert normalized is not None
    assert normalized["method"] == "linear_2point"
    assert normalized["points"][0]["point_role"] == "dry"
    assert normalized["derived"]["slope"] == 0.5
    assert normalized["metadata"]["schema_version"] == 1


def test_canonicalize_calibration_data_maps_legacy_object_to_derived():
    legacy = {"type": "linear_2point", "slope": 0.2, "offset": 1.0}
    normalized = canonicalize_calibration_data(legacy, source="legacy_db_row")
    assert normalized is not None
    assert normalized["method"] == "linear_2point"
    assert normalized["points"] == []
    assert normalized["derived"]["slope"] == 0.2
    assert normalized["metadata"]["source"] == "legacy_db_row"


def test_build_canonical_calibration_result_produces_strict_write_shape():
    payload = build_canonical_calibration_result(
        method="linear_2point",
        points=[{"point_role": "dry", "raw": 800.0, "reference": 0.0}],
        derived={"slope": 0.6, "offset": -5.0},
        source="unit-test",
    )
    assert set(payload.keys()) == {"method", "points", "derived", "metadata"}
    assert payload["metadata"]["schema_version"] == 1
    assert payload["metadata"]["source"] == "unit-test"


def test_read_calibrated_at_uses_derived_when_top_level_empty():
    payload = {
        "method": "ph_2point",
        "points": [],
        "derived": {"slope": -3.5, "calibrated_at": "2026-08-01T12:00:00+00:00"},
        "metadata": {"schema_version": 1, "source": "calibration_session_apply"},
    }
    assert read_calibrated_at(payload) == "2026-08-01T12:00:00+00:00"


def test_read_calibrated_at_falls_back_to_legacy_top_level():
    payload = {"type": "linear_2point", "slope": 0.2, "calibrated_at": "2025-01-01T00:00:00+00:00"}
    assert read_calibrated_at(payload) == "2025-01-01T00:00:00+00:00"


def test_read_calibrated_at_prefers_derived_when_both_exist():
    payload = {
        "method": "ec_1point",
        "points": [],
        "derived": {"cell_factor": 1.1, "calibrated_at": "2026-08-22T00:00:00+00:00"},
        "metadata": {},
        "calibrated_at": "2020-01-01T00:00:00+00:00",
    }
    assert read_calibrated_at(payload) == "2026-08-22T00:00:00+00:00"


def test_read_calibrated_at_returns_none_for_empty_payload():
    assert read_calibrated_at(None) is None
    assert read_calibrated_at({}) is None
    assert read_calibrated_at({"method": "ph_2point", "points": [], "derived": {}, "metadata": {}}) is None
