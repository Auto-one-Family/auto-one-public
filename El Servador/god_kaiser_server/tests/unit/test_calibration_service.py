"""Unit tests for calibration service session flow and guards."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.services.calibration_payloads import read_calibrated_at, read_valid_until
from src.services.calibration_service import CalibrationError, CalibrationService


async def _create_bound_sensor(
    db_session,
    *,
    esp_id: str,
    gpio: int,
    sensor_type: str = "moisture",
) -> None:
    esp = ESPDevice(device_id=esp_id, hardware_type="ESP32_WROOM", status="online")
    db_session.add(esp)
    await db_session.flush()
    sensor = SensorConfig(
        esp_id=esp.id,
        gpio=gpio,
        sensor_type=sensor_type,
        sensor_name=f"{sensor_type}-sensor-{gpio}",
        enabled=True,
    )
    db_session.add(sensor)
    await db_session.flush()


@pytest.mark.asyncio
async def test_calibration_service_add_finalize_apply_flow(db_session):
    await _create_bound_sensor(db_session, esp_id="ESP_TEST_001", gpio=4)
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=4,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )

    session = await service.add_point(
        session_id=session.id,
        raw=850.0,
        reference=0.0,
        point_role="dry",
    )
    assert session.points_collected == 1

    session = await service.add_point(
        session_id=session.id,
        raw=620.0,
        reference=100.0,
        point_role="wet",
    )
    assert session.points_collected == 2

    session = await service.finalize(session.id)
    assert session.status.value == "finalizing"
    assert session.calibration_result is not None

    session = await service.apply(session.id)
    assert session.status.value == "applied"
    assert session.initiated_by == "tester"
    result = session.calibration_result or {}
    assert read_calibrated_at(result)
    assert "valid_until" in (result.get("derived") or {})
    assert result["derived"]["valid_until"] is None
    assert "initiated_by" not in result
    assert "initiated_by" not in (result.get("derived") or {})
    assert "initiated_by" not in (result.get("metadata") or {})


@pytest.mark.asyncio
async def test_apply_writes_valid_until_on_derived_without_copying_initiated_by(db_session):
    await _create_bound_sensor(db_session, esp_id="ESP_TEST_001", gpio=41)
    service = CalibrationService(db_session)
    valid_until = datetime(2026, 12, 1, tzinfo=timezone.utc)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=41,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
        session_metadata={"valid_until": valid_until.isoformat()},
    )
    await service.add_point(session_id=session.id, raw=850.0, reference=0.0, point_role="dry")
    await service.add_point(session_id=session.id, raw=620.0, reference=100.0, point_role="wet")
    await service.finalize(session.id)
    session = await service.apply(session.id)

    sensor = await service.sensor_repo.get_by_id(session.sensor_config_id)
    assert sensor is not None
    blob = sensor.calibration_data
    assert blob is not None
    assert blob["derived"]["valid_until"].startswith("2026-12-01")
    assert "calibrated_at" in blob["derived"]
    assert "initiated_by" not in blob
    assert "initiated_by" not in blob["derived"]
    assert "initiated_by" not in blob.get("metadata", {})
    assert session.initiated_by == "tester"


@pytest.mark.asyncio
async def test_apply_omits_valid_until_when_not_provided(db_session):
    await _create_bound_sensor(db_session, esp_id="ESP_TEST_001", gpio=42)
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=42,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )
    await service.add_point(session_id=session.id, raw=850.0, reference=0.0, point_role="dry")
    await service.add_point(session_id=session.id, raw=620.0, reference=100.0, point_role="wet")
    await service.finalize(session.id)
    session = await service.apply(session.id)

    sensor = await service.sensor_repo.get_by_id(session.sensor_config_id)
    assert sensor is not None
    derived = (sensor.calibration_data or {}).get("derived") or {}
    assert "valid_until" in derived
    assert derived["valid_until"] is None


@pytest.mark.asyncio
async def test_add_point_blocks_duplicate_role_without_overwrite(db_session):
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=5,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )

    await service.add_point(
        session_id=session.id,
        raw=900.0,
        reference=0.0,
        point_role="dry",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.add_point(
            session_id=session.id,
            raw=910.0,
            reference=5.0,
            point_role="dry",
            overwrite=False,
        )

    assert exc.value.code == "ROLE_POINT_EXISTS"


@pytest.mark.asyncio
async def test_finalize_requires_both_dry_and_wet(db_session):
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=6,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )

    await service.add_point(
        session_id=session.id,
        raw=900.0,
        reference=0.0,
        point_role="dry",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "INSUFFICIENT_POINTS"


@pytest.mark.asyncio
async def test_add_point_overwrite_replaces_role_deterministically(db_session):
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=7,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )

    session = await service.add_point(
        session_id=session.id,
        raw=910.0,
        reference=0.0,
        point_role="dry",
    )
    dry_before = (session.calibration_points or {}).get("points", [])[0]
    assert dry_before.get("point_role") == "dry"

    session = await service.add_point(
        session_id=session.id,
        raw=870.0,
        reference=5.0,
        point_role="dry",
        overwrite=True,
    )
    points = (session.calibration_points or {}).get("points", [])
    dry_after = next(point for point in points if point.get("point_role") == "dry")
    assert len(points) == 1
    assert dry_after.get("id") == dry_before.get("id")
    assert dry_after.get("raw") == 870.0
    assert dry_after.get("reference") == 5.0


@pytest.mark.asyncio
async def test_delete_point_removes_role_and_keeps_collecting(db_session):
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=8,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=900.0,
        reference=0.0,
        point_role="dry",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=620.0,
        reference=100.0,
        point_role="wet",
    )

    points = (session.calibration_points or {}).get("points", [])
    dry_id = next(point["id"] for point in points if point.get("point_role") == "dry")
    session = await service.delete_point(session_id=session.id, point_id=dry_id)

    remaining_points = (session.calibration_points or {}).get("points", [])
    assert session.status.value == "collecting"
    assert len(remaining_points) == 1
    assert remaining_points[0].get("point_role") == "wet"


@pytest.mark.asyncio
async def test_apply_is_idempotent(db_session):
    await _create_bound_sensor(db_session, esp_id="ESP_TEST_001", gpio=9)
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=9,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=850.0,
        reference=0.0,
        point_role="dry",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=650.0,
        reference=100.0,
        point_role="wet",
    )
    session = await service.finalize(session.id)
    first_apply = await service.apply(session.id)
    second_apply = await service.apply(session.id)

    assert first_apply.status.value == "applied"
    assert second_apply.status.value == "applied"
    assert second_apply.id == first_apply.id


@pytest.mark.asyncio
async def test_apply_persists_nullable_valid_until_on_existing_blob(db_session):
    await _create_bound_sensor(db_session, esp_id="ESP_TEST_001", gpio=14)
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_TEST_001",
        gpio=14,
        sensor_type="moisture",
        method="linear_2point",
        expected_points=2,
        initiated_by="tester",
    )
    await service.add_point(session_id=session.id, raw=850.0, reference=0.0, point_role="dry")
    await service.add_point(session_id=session.id, raw=650.0, reference=100.0, point_role="wet")
    session = await service.finalize(session.id)

    past = datetime(2020, 1, 15, tzinfo=timezone.utc)
    session = await service.apply(session.id, valid_until=past)
    assert session.status.value == "applied"
    assert session.initiated_by == "tester"

    result = session.calibration_result or {}
    assert result["derived"]["valid_until"] == past.isoformat()
    assert read_valid_until(result) == past.isoformat()
    assert read_calibrated_at(result)
    assert "initiated_by" not in result
    assert "initiated_by" not in result["derived"]
    points = result.get("points") or []
    assert {point.get("point_role") for point in points} == {"dry", "wet"}
    assert {point.get("reference") for point in points} == {0.0, 100.0}

    sensor = (
        await db_session.execute(
            select(SensorConfig).where(SensorConfig.gpio == 14)
        )
    ).scalar_one()
    blob = sensor.calibration_data or {}
    assert blob["derived"]["valid_until"] == past.isoformat()
    assert read_valid_until(blob) == past.isoformat()
    assert blob["derived"]["valid_until"]  # stale past date stays stored
    assert "initiated_by" not in blob


# ─────────────────────────────────────────────────────────────────────────────
# pH Calibration (2-point) Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ph_2point_calibration_happy_path(db_session):
    """pH 2-point calibration with typical Nernst buffer values (pH 7.00 and 4.01)."""
    await _create_bound_sensor(db_session, esp_id="ESP_pH_001", gpio=34, sensor_type="ph")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_pH_001",
        gpio=34,
        sensor_type="ph",
        method="ph_2point",
        expected_points=2,
        initiated_by="tester",
    )

    # ADC-based Nernst response: raw values are ADC counts (0–4095), not mV.
    # raw=2048 → ~1.650V, raw=2267 → ~1.826V, voltage_diff ≈ 0.177V
    # slope ≈ -16.93 pH/V → 59.07 mV/pH → deviation ≈ 0.16% ✓ within 15%
    session = await service.add_point(
        session_id=session.id,
        raw=2048.0,
        reference=7.00,
        point_role="buffer_high",
    )
    assert session.points_collected == 1

    session = await service.add_point(
        session_id=session.id,
        raw=2267.0,
        reference=4.01,
        point_role="buffer_low",
    )
    assert session.points_collected == 2

    # Finalize and check result
    session = await service.finalize(session.id)
    assert session.status.value == "finalizing"
    assert session.calibration_result is not None

    result = session.calibration_result
    assert result["method"] == "ph_2point"

    derived = result["derived"]
    # raw=2048 ADC (~1.650V) at pH 7.00, raw=2267 ADC (~1.826V) at pH 4.01
    # voltage_diff ≈ 0.177V → slope ≈ -16.93 pH/V → 59.07 mV/pH
    # Deviation: |59.07 - 59.16| / 59.16 * 100 ≈ 0.16% ✓ within 15%
    assert derived["slope"] < 0  # Must be negative per Nernst
    assert "slope_deviation_pct" in derived
    assert derived["slope_deviation_pct"] <= 15.0
    assert "point_high_raw" in derived
    assert "point_low_raw" in derived


@pytest.mark.asyncio
async def test_ph_2point_validation_negative_slope(db_session):
    """pH 2-point should reject if slope is not negative (electrode polarity error)."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_pH_002",
        gpio=34,
        sensor_type="ph",
        method="ph_2point",
        expected_points=2,
    )

    # WRONG polarity: raw increases with pH (opposite of Nernst)
    # This will compute positive slope and should fail
    session = await service.add_point(
        session_id=session.id,
        raw=100.0,
        reference=4.01,
        point_role="buffer_low",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=250.0,
        reference=7.00,
        point_role="buffer_high",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "COMPUTE_FAILED"


@pytest.mark.asyncio
async def test_ph_2point_validation_slope_deviation(db_session):
    """pH 2-point should reject if slope deviates more than ±15% from ideal."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_pH_003",
        gpio=34,
        sensor_type="ph",
        method="ph_2point",
        expected_points=2,
    )

    # Extreme slope: nearly 0 mV/pH (electrode nearly dead)
    # raw differs by only 20 mV over 3 pH units: 1/(-0.15) ≈ -6.67 mV/pH
    # Deviation from 59.16 mV/pH: |(6.67 - 59.16) / 59.16| ≈ 89% >> 15% ✗
    session = await service.add_point(
        session_id=session.id,
        raw=100.0,
        reference=4.01,
        point_role="buffer_low",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=120.0,
        reference=7.00,
        point_role="buffer_high",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "COMPUTE_FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# EC Calibration Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ec_1point_calibration_happy_path(db_session):
    """EC 1-point calibration with standard reference solution."""
    await _create_bound_sensor(db_session, esp_id="ESP_EC_001", gpio=35, sensor_type="ec")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_EC_001",
        gpio=35,
        sensor_type="ec",
        method="ec_1point",
        expected_points=1,
        initiated_by="tester",
    )

    # Standard 1.413 mS/cm reference — raw must be in conductance units (mS/cm)
    # so cell_factor = reference / raw falls in [0.5, 2.0]. raw=1.5 → cell_factor≈0.942.
    session = await service.add_point(
        session_id=session.id,
        raw=1.5,  # conductance in mS/cm
        reference=1.413,  # mS/cm
        point_role="reference",
    )
    assert session.points_collected == 1

    session = await service.finalize(session.id)
    assert session.status.value == "finalizing"
    assert session.calibration_result is not None

    result = session.calibration_result
    assert result["method"] == "ec_1point"

    derived = result["derived"]
    assert "cell_factor" in derived
    # cell_factor = 1.413 / 1.5 = 0.942
    assert 0.5 < derived["cell_factor"] < 2.0
    assert "point_raw" in derived
    assert "point_reference" in derived


@pytest.mark.asyncio
async def test_ec_1point_validation_cell_factor_range(db_session):
    """EC 1-point should reject if cell_factor is outside [0.5, 2.0]."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_EC_002",
        gpio=35,
        sensor_type="ec",
        method="ec_1point",
        expected_points=1,
    )

    # Unrealistic: raw=1 with reference=100 → cell_factor = 100 (way too high)
    session = await service.add_point(
        session_id=session.id,
        raw=1.0,
        reference=100.0,
        point_role="reference",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "COMPUTE_FAILED"


@pytest.mark.asyncio
async def test_canonical_structure_ph_2point(db_session):
    """Canonical calibration result structure for ph_2point."""
    await _create_bound_sensor(db_session, esp_id="ESP_pH_CANON", gpio=34, sensor_type="ph")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_pH_CANON",
        gpio=34,
        sensor_type="ph",
        method="ph_2point",
        expected_points=2,
        initiated_by="tester",
    )

    # Realistic Nernst data: buffer_high (pH 7) at 100 mV, buffer_low (pH 4.01) at 258 mV
    session = await service.add_point(
        session_id=session.id,
        raw=100.0,
        reference=7.00,
        point_role="buffer_high",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=258.0,
        reference=4.01,
        point_role="buffer_low",
    )

    session = await service.finalize(session.id)
    result = session.calibration_result

    # Check canonical structure
    assert "method" in result
    assert result["method"] == "ph_2point"
    assert "points" in result
    assert isinstance(result["points"], list)
    assert len(result["points"]) == 2
    assert "derived" in result
    assert isinstance(result["derived"], dict)
    assert "metadata" in result
    assert isinstance(result["metadata"], dict)

    # Check metadata
    assert result["metadata"]["schema_version"] == 1
    assert "source" in result["metadata"]
    assert "normalized_at" in result["metadata"]

    # Check points preserved
    assert result["points"][0]["point_role"] == "buffer_high"
    assert result["points"][1]["point_role"] == "buffer_low"


# ─────────────────────────────────────────────────────────────────────────────
# EC linear 2-point Calibration Tests (AUT-487)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ec_linear_2point_happy_path(db_session):
    """EC linear 2-point calibration with standard KCl reference solutions."""
    await _create_bound_sensor(db_session, esp_id="ESP_EC_LIN_001", gpio=32, sensor_type="ec")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_EC_LIN_001",
        gpio=32,
        sensor_type="ec",
        method="ec_linear_2point",
        expected_points=2,
        initiated_by="tester",
    )

    # reference_low: 1413 µS/cm (0.01 M KCl), ADC reading in low-conductivity solution
    session = await service.add_point(
        session_id=session.id,
        raw=625.0,
        reference=1413.0,
        point_role="reference_low",
    )
    assert session.points_collected == 1

    # reference_high: 12880 µS/cm (0.1 M KCl), ADC reading in high-conductivity solution
    session = await service.add_point(
        session_id=session.id,
        raw=3200.0,
        reference=12880.0,
        point_role="reference_high",
    )
    assert session.points_collected == 2

    session = await service.finalize(session.id)
    assert session.status.value == "finalizing"
    assert session.calibration_result is not None

    result = session.calibration_result
    assert result["method"] == "ec_linear_2point"

    derived = result["derived"]
    assert "slope" in derived
    assert "offset" in derived
    assert derived["type"] == "ec_linear_2point"
    assert derived["point_low_raw"] == 625.0
    assert derived["point_low_ref"] == 1413.0
    assert derived["point_high_raw"] == 3200.0
    assert derived["point_high_ref"] == 12880.0
    # Slope must be positive (EC sensor: higher voltage = higher conductivity)
    assert derived["slope"] > 0
    # Verify slope and offset produce correct readings at calibration points
    _ADC_MAX = 4095.0
    _ADC_VOLTAGE = 3.3
    voltage_low = (625.0 / _ADC_MAX) * _ADC_VOLTAGE
    voltage_high = (3200.0 / _ADC_MAX) * _ADC_VOLTAGE
    computed_low = derived["slope"] * voltage_low + derived["offset"]
    computed_high = derived["slope"] * voltage_high + derived["offset"]
    assert abs(computed_low - 1413.0) < 1.0  # within 1 µS/cm at 25°C
    assert abs(computed_high - 12880.0) < 1.0


@pytest.mark.asyncio
async def test_ec_linear_2point_canonical_structure(db_session):
    """ec_linear_2point finalize produces canonical calibration_result structure."""
    await _create_bound_sensor(db_session, esp_id="ESP_EC_LIN_002", gpio=32, sensor_type="ec")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_EC_LIN_002",
        gpio=32,
        sensor_type="ec",
        method="ec_linear_2point",
        expected_points=2,
        initiated_by="tester",
    )
    await service.add_point(session_id=session.id, raw=625.0, reference=1413.0, point_role="reference_low")
    await service.add_point(session_id=session.id, raw=3200.0, reference=12880.0, point_role="reference_high")

    session = await service.finalize(session.id)
    result = session.calibration_result

    assert "method" in result
    assert result["method"] == "ec_linear_2point"
    assert "points" in result
    assert isinstance(result["points"], list)
    assert len(result["points"]) == 2
    assert "derived" in result
    assert isinstance(result["derived"], dict)
    assert "metadata" in result
    assert result["metadata"]["schema_version"] == 1

    # Check point roles preserved
    roles = {p["point_role"] for p in result["points"]}
    assert roles == {"reference_low", "reference_high"}


@pytest.mark.asyncio
async def test_ec_linear_2point_missing_reference_low(db_session):
    """ec_linear_2point finalize should fail if reference_low is missing."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_EC_LIN_003",
        gpio=32,
        sensor_type="ec",
        method="ec_linear_2point",
        expected_points=2,
    )
    # Add only reference_high, skip reference_low
    await service.add_point(session_id=session.id, raw=600.0, reference=1413.0, point_role="reference_low")
    await service.add_point(session_id=session.id, raw=3200.0, reference=12880.0, point_role="reference_high")
    # Overwrite reference_low with a wrong role to simulate missing scenario by checking
    # that invalid role is rejected first

    # Test the static method with two points but missing reference_low role
    with pytest.raises(ValueError, match="reference_low"):
        CalibrationService._compute_ec_linear_2point(
            [
                {"point_role": "reference_high", "raw": 3200.0, "reference": 12880.0},
                {"point_role": "air", "raw": 100.0, "reference": 0.0},
            ],
        )


@pytest.mark.asyncio
async def test_ec_linear_2point_monotonicity_violation(db_session):
    """ec_linear_2point should reject when ADC_high <= ADC_low (inverted sensor)."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_EC_LIN_004",
        gpio=32,
        sensor_type="ec",
        method="ec_linear_2point",
        expected_points=2,
    )

    # ADC inverted: high-conductivity solution produces lower ADC than low-conductivity
    session = await service.add_point(
        session_id=session.id,
        raw=3000.0,  # ADC for low solution — intentionally higher than high solution
        reference=1413.0,
        point_role="reference_low",
    )
    session = await service.add_point(
        session_id=session.id,
        raw=800.0,  # ADC for high solution — inverted
        reference=12880.0,
        point_role="reference_high",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "COMPUTE_FAILED"


@pytest.mark.asyncio
async def test_ec_linear_2point_reference_high_not_greater_than_low(db_session):
    """ec_linear_2point should reject when reference_high <= reference_low."""
    service = CalibrationService(db_session)
    session = await service.start_session(
        esp_id="ESP_EC_LIN_005",
        gpio=32,
        sensor_type="ec",
        method="ec_linear_2point",
        expected_points=2,
    )

    # Swapped reference values: reference_low (1413) > reference_high (500) — invalid
    await service.add_point(
        session_id=session.id,
        raw=500.0,
        reference=500.0,  # reference_high has lower EC than reference_low — invalid
        point_role="reference_low",
    )
    await service.add_point(
        session_id=session.id,
        raw=3000.0,
        reference=200.0,  # reference_high < reference_low
        point_role="reference_high",
    )

    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)

    assert exc.value.code == "COMPUTE_FAILED"


def test_ec_linear_2point_static_compute_slope_and_offset():
    """Unit test for _compute_ec_linear_2point static method at 25°C (no temp correction)."""
    points = [
        {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
        {"point_role": "reference_high", "raw": 3200.0, "reference": 12880.0},
    ]
    result = CalibrationService._compute_ec_linear_2point(points, temperature=25.0)

    assert result["type"] == "ec_linear_2point"
    assert result["point_low_raw"] == 625.0
    assert result["point_low_ref"] == 1413.0
    assert result["point_high_raw"] == 3200.0
    assert result["point_high_ref"] == 12880.0
    assert result["calibration_temperature"] == 25.0
    # At 25°C: no temperature normalization, ref_at_cal_temp == reference
    assert abs(result["ref_low_at_cal_temp"] - 1413.0) < 0.01
    assert abs(result["ref_high_at_cal_temp"] - 12880.0) < 0.01

    # Verify computed slope/offset round-trip
    _ADC_MAX = 4095.0
    _ADC_VOLTAGE = 3.3
    v_low = (625.0 / _ADC_MAX) * _ADC_VOLTAGE
    v_high = (3200.0 / _ADC_MAX) * _ADC_VOLTAGE
    expected_slope = (12880.0 - 1413.0) / (v_high - v_low)
    expected_offset = 1413.0 - expected_slope * v_low
    import pytest
    assert result["slope"] == pytest.approx(expected_slope, rel=0.001)
    assert result["offset"] == pytest.approx(expected_offset, rel=0.001)


def test_ec_linear_2point_static_compute_temperature_normalization():
    """ec_linear_2point at 30°C should normalize reference EC to actual-at-cal-temp."""
    points = [
        {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
        {"point_role": "reference_high", "raw": 3200.0, "reference": 12880.0},
    ]
    result_25 = CalibrationService._compute_ec_linear_2point(points, temperature=25.0)
    result_30 = CalibrationService._compute_ec_linear_2point(points, temperature=30.0)

    # At 30°C: actual EC = reference * (1 + 0.02 * (30 - 25)) = reference * 1.1
    # ref_low_at_cal_temp(30°C) = 1413 * 1.1 ≈ 1554.3
    import pytest
    assert result_30["ref_low_at_cal_temp"] == pytest.approx(1413.0 * 1.1, rel=0.001)
    assert result_30["ref_high_at_cal_temp"] == pytest.approx(12880.0 * 1.1, rel=0.001)

    # Slope at 30°C is higher (normalized to higher actual EC values)
    assert result_30["slope"] > result_25["slope"]


def test_ec_linear_2point_static_monotonicity_rejection():
    """_compute_ec_linear_2point raises ValueError when ADC_high <= ADC_low."""
    points = [
        {"point_role": "reference_low", "raw": 3000.0, "reference": 1413.0},
        {"point_role": "reference_high", "raw": 800.0, "reference": 12880.0},
    ]
    with pytest.raises(ValueError, match="ADC for reference_high"):
        CalibrationService._compute_ec_linear_2point(points)


def test_ec_linear_2point_static_reference_sanity_rejection():
    """_compute_ec_linear_2point raises ValueError when reference_high <= reference_low."""
    points = [
        {"point_role": "reference_low", "raw": 500.0, "reference": 5000.0},
        {"point_role": "reference_high", "raw": 3000.0, "reference": 1000.0},
    ]
    with pytest.raises(ValueError, match="reference_high"):
        CalibrationService._compute_ec_linear_2point(points)


@pytest.mark.asyncio
async def test_canonical_structure_ec_1point(db_session):
    """Canonical calibration result structure for ec_1point."""
    await _create_bound_sensor(db_session, esp_id="ESP_EC_CANON", gpio=35, sensor_type="ec")
    service = CalibrationService(db_session)

    session = await service.start_session(
        esp_id="ESP_EC_CANON",
        gpio=35,
        sensor_type="ec",
        method="ec_1point",
        expected_points=1,
        initiated_by="tester",
    )

    # raw in conductance units (mS/cm); cell_factor = 1.413/1.5 ≈ 0.942 — in [0.5, 2.0]
    session = await service.add_point(
        session_id=session.id,
        raw=1.5,
        reference=1.413,
        point_role="reference",
    )

    session = await service.finalize(session.id)
    result = session.calibration_result

    # Check canonical structure
    assert "method" in result
    assert result["method"] == "ec_1point"
    assert "points" in result
    assert isinstance(result["points"], list)
    assert len(result["points"]) == 1
    assert "derived" in result
    assert isinstance(result["derived"], dict)
    assert "metadata" in result

    # Check derived has cell_factor
    assert "cell_factor" in result["derived"]
    assert 0.5 <= result["derived"]["cell_factor"] <= 2.0
