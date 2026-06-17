"""Unit tests for canonical calibration payload adapters."""

from src.services.calibration_payloads import (
    build_canonical_calibration_result,
    canonicalize_calibration_data,
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
