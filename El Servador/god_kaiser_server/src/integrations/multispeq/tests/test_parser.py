"""Unit tests for the MultispeQ / PhotosynQ parser (AUT-212)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.integrations.multispeq.parser import (
    MULTISPEQ_FIELD_MAP,
    MULTISPEQ_UNITS,
    expand_to_sensor_rows,
    parse_photosynq_measurement,
    validate_calibration,
)


# ---------------------------------------------------------------------------
# parse_photosynq_measurement
# ---------------------------------------------------------------------------


def test_parse_photosynq_measurement_maps_known_fields() -> None:
    raw = {
        "Phi2": 0.72,
        "FvFm": 0.82,
        "NPQt": 1.5,
        "LEF": 120.0,
        "PAR_Ambient": 800.0,
        "PPFD": 850.0,
        "Chl_SPAD": 42.0,
        "Leaf_Temp": 23.5,
        "Anthocyanin_Index": 0.18,
    }

    parsed = parse_photosynq_measurement(raw)

    assert parsed == {
        "phi2": 0.72,
        "fv_fm": 0.82,
        "npqt": 1.5,
        "lef": 120.0,
        "par_internal": 800.0,
        "ppfd": 850.0,
        "chlorophyll_spad": 42.0,
        "leaf_temp": 23.5,
        "anthocyanin_index": 0.18,
    }
    # Sanity: all values must be ``float`` after parsing.
    for value in parsed.values():
        assert isinstance(value, float)


def test_parse_photosynq_measurement_ignores_unknown_fields() -> None:
    raw = {
        "Phi2": 0.7,
        "UnknownField": 99.9,
        "device_id": "abc123",
        "metadata": {"foo": "bar"},
    }

    parsed = parse_photosynq_measurement(raw)

    assert "phi2" in parsed
    assert parsed["phi2"] == 0.7
    assert "UnknownField" not in parsed
    assert "device_id" not in parsed
    assert len(parsed) == 1


def test_parse_photosynq_measurement_skips_invalid_values() -> None:
    raw = {
        "Phi2": "not_a_number",
        "FvFm": None,
        "NPQt": 2.5,
        "LEF": [1, 2, 3],
        "PPFD": "850.5",  # string-coerceable to float -> kept
    }

    parsed = parse_photosynq_measurement(raw)

    # Invalid / None / list values are skipped, valid ones (incl. coerceable
    # strings) are kept.
    assert parsed == {"npqt": 2.5, "ppfd": 850.5}


def test_parse_photosynq_measurement_handles_empty_input() -> None:
    assert parse_photosynq_measurement({}) == {}
    assert parse_photosynq_measurement(None) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_calibration
# ---------------------------------------------------------------------------


def test_validate_calibration_phi2_out_of_range() -> None:
    parsed = {"phi2": 1.5}

    warnings = validate_calibration(parsed)

    assert len(warnings) == 1
    assert "phi2" in warnings[0]
    assert "1.5" in warnings[0]


def test_validate_calibration_ok_no_warnings() -> None:
    parsed = {
        "phi2": 0.72,
        "fv_fm": 0.82,
        "npqt": 1.5,
        "lef": 120.0,
        "par_internal": 800.0,
        "leaf_temp": 23.5,
        "chlorophyll_spad": 42.0,
    }

    assert validate_calibration(parsed) == []


def test_validate_calibration_missing_fields_no_warnings() -> None:
    # Empty parsed dict -> no warnings (all fields are optional).
    assert validate_calibration({}) == []


def test_validate_calibration_multiple_violations() -> None:
    parsed = {
        "phi2": -0.1,
        "fv_fm": 1.2,
        "leaf_temp": 200.0,
    }

    warnings = validate_calibration(parsed)

    assert len(warnings) == 3
    joined = " ".join(warnings)
    assert "phi2" in joined
    assert "fv_fm" in joined
    assert "leaf_temp" in joined


# ---------------------------------------------------------------------------
# expand_to_sensor_rows
# ---------------------------------------------------------------------------


def test_expand_to_sensor_rows_correct_gpio_offset() -> None:
    parsed = {"phi2": 0.72}
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)

    rows = expand_to_sensor_rows(
        parsed=parsed,
        esp_id="ESP_MULTISPEQ_01",
        gpio_base=200,
        timestamp=ts,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["esp_id"] == "ESP_MULTISPEQ_01"
    assert row["gpio"] == 200  # phi2 is the first entry -> offset 0
    assert row["sensor_type"] == "phi2"
    assert row["raw_value"] == 0.72
    assert row["processed_value"] == 0.72
    assert row["unit"] == MULTISPEQ_UNITS["phi2"]
    assert row["processing_mode"] == "snapshot"
    assert row["quality"] == "good"
    assert row["timestamp"] == ts
    assert row["data_source"] == "production"
    assert row["plant_id"] is None


def test_expand_to_sensor_rows_only_present_fields() -> None:
    parsed = {"phi2": 0.7, "ppfd": 850.0}
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)

    rows = expand_to_sensor_rows(
        parsed=parsed,
        esp_id="ESP_X",
        gpio_base=200,
        timestamp=ts,
    )

    assert len(rows) == 2
    sensor_types = {row["sensor_type"] for row in rows}
    assert sensor_types == {"phi2", "ppfd"}

    # Validate stable GPIO offsets derived from MULTISPEQ_FIELD_MAP order.
    expected = {name: 200 + idx for idx, name in enumerate(MULTISPEQ_FIELD_MAP.values())}
    for row in rows:
        assert row["gpio"] == expected[row["sensor_type"]]


def test_expand_to_sensor_rows_full_payload_offsets() -> None:
    parsed = {internal: 1.0 for internal in MULTISPEQ_FIELD_MAP.values()}
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)

    rows = expand_to_sensor_rows(
        parsed=parsed,
        esp_id="ESP_FULL",
        gpio_base=200,
        timestamp=ts,
    )

    assert len(rows) == 9
    # Rows must be emitted in MULTISPEQ_FIELD_MAP order with consecutive GPIOs.
    expected_order = list(MULTISPEQ_FIELD_MAP.values())
    actual_order = [row["sensor_type"] for row in rows]
    assert actual_order == expected_order
    actual_gpios = [row["gpio"] for row in rows]
    assert actual_gpios == [200 + i for i in range(9)]


def test_expand_to_sensor_rows_with_plant_id() -> None:
    plant_id = uuid.uuid4()
    parsed = {"fv_fm": 0.8}
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)

    rows = expand_to_sensor_rows(
        parsed=parsed,
        esp_id="ESP_X",
        gpio_base=200,
        timestamp=ts,
        plant_id=plant_id,
    )

    assert len(rows) == 1
    assert rows[0]["plant_id"] == plant_id
    assert rows[0]["gpio"] == 201  # fv_fm is second -> offset 1


def test_expand_to_sensor_rows_empty_parsed_returns_empty_list() -> None:
    rows = expand_to_sensor_rows(
        parsed={},
        esp_id="ESP_X",
        gpio_base=200,
        timestamp=datetime.now(timezone.utc),
    )
    assert rows == []
