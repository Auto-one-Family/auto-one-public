"""
AUT-1395 [M-4]: Live read path — fail-closed, reuse existing freshness.

Given/When/Then:
- Fresh reading → success with value (any sensor_type)
- Missing reading → Failure(reason=missing), not silent 0
- Stale (existing measurement_freshness_hours) → Failure(reason=stale)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic.measure_live_reader import (
    MeasureReadFailure,
    MeasureReadSuccess,
    read_live_sensor_for_measure,
)


def _reading(*, value: float, age_hours: float, sensor_type: str = "ec"):
    reading = MagicMock()
    reading.processed_value = value
    reading.raw_value = value
    reading.sensor_type = sensor_type
    reading.timestamp = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return reading


def _config(*, operating_mode: str, freshness_hours):
    cfg = MagicMock()
    cfg.operating_mode = operating_mode
    cfg.measurement_freshness_hours = freshness_hours
    return cfg


@pytest.mark.asyncio
async def test_read_live_sensor_fresh_ec_succeeds():
    session = MagicMock()
    esp = MagicMock()
    esp.id = "uuid-esp"
    esp.is_online = True

    with (
        patch("src.services.logic.measure_live_reader.ESPRepository") as EspRepo,
        patch("src.services.logic.measure_live_reader.SensorRepository") as SensorRepo,
    ):
        EspRepo.return_value.get_by_device_id = AsyncMock(return_value=esp)
        SensorRepo.return_value.get_latest_reading = AsyncMock(
            return_value=_reading(value=1.42, age_hours=0.01, sensor_type="ec")
        )
        SensorRepo.return_value.get_by_esp_gpio_and_type = AsyncMock(
            return_value=_config(operating_mode="continuous", freshness_hours=None)
        )

        result = await read_live_sensor_for_measure(
            session, esp_id="ESP_12AB34CD", gpio=34, sensor_type="ec"
        )

    assert isinstance(result, MeasureReadSuccess)
    assert result.ok is True
    assert result.value == 1.42


@pytest.mark.asyncio
async def test_read_live_sensor_fresh_ph_succeeds():
    """Generic path — not EC-only."""
    session = MagicMock()
    esp = MagicMock()
    esp.id = "uuid-esp"
    esp.is_online = True

    with (
        patch("src.services.logic.measure_live_reader.ESPRepository") as EspRepo,
        patch("src.services.logic.measure_live_reader.SensorRepository") as SensorRepo,
    ):
        EspRepo.return_value.get_by_device_id = AsyncMock(return_value=esp)
        SensorRepo.return_value.get_latest_reading = AsyncMock(
            return_value=_reading(value=6.2, age_hours=0.01, sensor_type="ph")
        )
        SensorRepo.return_value.get_by_esp_gpio_and_type = AsyncMock(
            return_value=_config(operating_mode="continuous", freshness_hours=None)
        )

        result = await read_live_sensor_for_measure(
            session, esp_id="ESP_12AB34CD", gpio=35, sensor_type="ph"
        )

    assert isinstance(result, MeasureReadSuccess)
    assert result.value == 6.2
    assert result.sensor_type == "ph"


@pytest.mark.asyncio
async def test_read_live_sensor_missing_fails_closed():
    session = MagicMock()
    esp = MagicMock()
    esp.id = "uuid-esp"
    esp.is_online = True

    with (
        patch("src.services.logic.measure_live_reader.ESPRepository") as EspRepo,
        patch("src.services.logic.measure_live_reader.SensorRepository") as SensorRepo,
    ):
        EspRepo.return_value.get_by_device_id = AsyncMock(return_value=esp)
        SensorRepo.return_value.get_latest_reading = AsyncMock(return_value=None)

        result = await read_live_sensor_for_measure(
            session, esp_id="ESP_12AB34CD", gpio=34, sensor_type="ec"
        )

    assert isinstance(result, MeasureReadFailure)
    assert result.ok is False
    assert result.reason == "missing"
    # Fail-closed: no silent zero
    assert not hasattr(result, "value") or getattr(result, "value", None) is None


@pytest.mark.asyncio
async def test_read_live_sensor_stale_fails_closed():
    """
    Uses existing measurement_freshness_hours + operating_mode (AUT-41),
    not an invented max_age_seconds.
    """
    session = MagicMock()
    esp = MagicMock()
    esp.id = "uuid-esp"
    esp.is_online = True

    with (
        patch("src.services.logic.measure_live_reader.ESPRepository") as EspRepo,
        patch("src.services.logic.measure_live_reader.SensorRepository") as SensorRepo,
    ):
        EspRepo.return_value.get_by_device_id = AsyncMock(return_value=esp)
        SensorRepo.return_value.get_latest_reading = AsyncMock(
            return_value=_reading(value=1.9, age_hours=3.0, sensor_type="ec")
        )
        SensorRepo.return_value.get_by_esp_gpio_and_type = AsyncMock(
            return_value=_config(operating_mode="on_demand", freshness_hours=1.0)
        )

        result = await read_live_sensor_for_measure(
            session, esp_id="ESP_12AB34CD", gpio=34, sensor_type="ec"
        )

    assert isinstance(result, MeasureReadFailure)
    assert result.ok is False
    assert result.reason == "stale"
    assert result.age_seconds is not None
    assert result.age_seconds > 3600
