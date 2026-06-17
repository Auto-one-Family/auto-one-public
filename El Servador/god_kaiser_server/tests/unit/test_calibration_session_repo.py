"""Unit tests for calibration session repository JSONB updates."""

import pytest
from sqlalchemy import select

from src.db.models.calibration_session import CalibrationSession
from src.db.repositories.calibration_session_repo import CalibrationSessionRepository


@pytest.mark.asyncio
async def test_add_calibration_point_persists_multiple_points(db_session):
    repo = CalibrationSessionRepository(db_session)

    session = CalibrationSession(
        esp_id="ESP_TEST_001",
        gpio=32,
        sensor_type="moisture",
        expected_points=2,
        method="linear_2point",
    )
    db_session.add(session)
    await db_session.flush()

    updated = await repo.add_calibration_point(
        session.id,
        {
            "raw": 900.0,
            "reference": 0.0,
            "quality": "good",
            "timestamp": "2026-04-06T10:05:03Z",
        },
    )
    assert updated is not None
    assert updated.points_collected == 1

    updated = await repo.add_calibration_point(
        session.id,
        {
            "raw": 1137.0,
            "reference": 100.0,
            "quality": "good",
            "timestamp": "2026-04-06T10:05:04Z",
        },
    )
    assert updated is not None
    assert updated.points_collected == 2

    await db_session.commit()

    reloaded = (
        await db_session.execute(
            select(CalibrationSession).where(CalibrationSession.id == session.id)
        )
    ).scalar_one()
    points = (reloaded.calibration_points or {}).get("points", [])
    assert len(points) == 2
