"""
Unit tests for EC control-anchor (AUT-1218).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.system_config_repo import SystemConfigRepository
from src.sensors.dose_calculators.active.ec_control_anchor import (
    EC_DRIFT_THRESHOLD_CONFIG_KEY,
    calculate_expected_ec_ms_cm,
    check_ec_control_anchor,
)


def test_calculate_expected_ec_sums_contributions() -> None:
    expected = calculate_expected_ec_ms_cm(
        components=[
            {"kind": "product", "name": "A", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 1.2},
            {"kind": "product", "name": "B", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 0.8},
        ],
        volume_l=10.0,
    )
    assert expected == pytest.approx(2.0)


def test_calculate_expected_ec_skips_without_contribution() -> None:
    assert (
        calculate_expected_ec_ms_cm(
            components=[{"kind": "product", "name": "A", "dose_ml_per_l": 1.0}],
            volume_l=10.0,
        )
        is None
    )


def test_calculate_expected_ec_volume_weighted_mix() -> None:
    expected = calculate_expected_ec_ms_cm(
        components=[
            {"kind": "salt", "name": "KNO3", "conc_g_per_l": 1.0, "ec_contribution_ms_cm": 2.0},
        ],
        volume_l=5.0,
        prior_volume_l=5.0,
        prior_ec_ms_cm=1.0,
    )
    # (5*1.0 + 5*2.0) / 10 = 1.5
    assert expected == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_check_noop_when_threshold_missing(db_session: AsyncSession) -> None:
    warnings = await check_ec_control_anchor(
        session=db_session,
        components=[
            {"kind": "product", "name": "A", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 2.0},
        ],
        volume_l=10.0,
        ec_measured_after=5.0,
        ec_was_measured=True,
    )
    assert warnings == []


@pytest.mark.asyncio
async def test_check_noop_when_threshold_null(db_session: AsyncSession) -> None:
    repo = SystemConfigRepository(db_session)
    await repo.set_config(
        config_key=EC_DRIFT_THRESHOLD_CONFIG_KEY,
        config_value={"value": None},
        config_type="nutrient_batch",
    )
    warnings = await check_ec_control_anchor(
        session=db_session,
        components=[
            {"kind": "product", "name": "A", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 2.0},
        ],
        volume_l=10.0,
        ec_measured_after=5.0,
        ec_was_measured=True,
    )
    assert warnings == []


@pytest.mark.asyncio
async def test_check_warns_when_drift_exceeds_threshold(
    db_session: AsyncSession,
) -> None:
    repo = SystemConfigRepository(db_session)
    await repo.set_config(
        config_key=EC_DRIFT_THRESHOLD_CONFIG_KEY,
        config_value={"value": 10.0},
        config_type="nutrient_batch",
    )
    warnings = await check_ec_control_anchor(
        session=db_session,
        components=[
            {"kind": "product", "name": "A", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 2.0},
        ],
        volume_l=10.0,
        ec_measured_after=3.0,  # 50% drift vs expected 2.0
        ec_was_measured=True,
    )
    assert len(warnings) == 1
    assert "EC-Kontrollanker" in warnings[0]
    assert "50.0%" in warnings[0]


@pytest.mark.asyncio
async def test_check_no_warning_within_threshold(db_session: AsyncSession) -> None:
    repo = SystemConfigRepository(db_session)
    await repo.set_config(
        config_key=EC_DRIFT_THRESHOLD_CONFIG_KEY,
        config_value={"value": 20.0},
        config_type="nutrient_batch",
    )
    warnings = await check_ec_control_anchor(
        session=db_session,
        components=[
            {"kind": "product", "name": "A", "dose_ml_per_l": 1.0, "ec_contribution_ms_cm": 2.0},
        ],
        volume_l=10.0,
        ec_measured_after=2.1,  # 5% drift
        ec_was_measured=True,
    )
    assert warnings == []
