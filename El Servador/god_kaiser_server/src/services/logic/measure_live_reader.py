"""
Live sensor read for measure bindings (AUT-1395 / M-4).

Reuses the Logic-Engine cross-sensor load path:
  ESP device_id → get_latest_reading → age_seconds + measurement_freshness_hours

Freshness policy: same rules as ``SensorConditionEvaluator._check_freshness``
(existing sensor config fields only — no invented max_age knobs).

Fail-closed: missing or stale → explicit Failure; never a silent 0 / None value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from ...db.repositories.esp_repo import ESPRepository
from ...db.repositories.sensor_repo import SensorRepository
from .conditions.sensor_evaluator import SensorConditionEvaluator

MeasureFailReason = Literal[
    "esp_not_found",
    "esp_offline",
    "missing",
    "stale",
]


@dataclass(frozen=True)
class MeasureReadSuccess:
    ok: Literal[True]
    value: float
    age_seconds: float
    sensor_type: Optional[str]
    operating_mode: str
    measurement_freshness_hours: Optional[float]


@dataclass(frozen=True)
class MeasureReadFailure:
    ok: Literal[False]
    reason: MeasureFailReason
    esp_id: str
    gpio: int
    sensor_type: Optional[str]
    age_seconds: Optional[float] = None
    detail: Optional[dict] = None


MeasureReadResult = Union[MeasureReadSuccess, MeasureReadFailure]


async def read_live_sensor_for_measure(
    session: AsyncSession,
    *,
    esp_id: str,
    gpio: int,
    sensor_type: Optional[str] = None,
) -> MeasureReadResult:
    """
    Read one live sensor value for a measure-binding hook.

    Args:
        session: Async DB session.
        esp_id: Device id (Live-Form, e.g. ESP_12AB34CD).
        gpio: GPIO pin.
        sensor_type: Optional type for multi-value sensors.

    Returns:
        MeasureReadSuccess with value, or MeasureReadFailure with reason.
        Never returns a bare None/0 as a stand-in for missing/stale data.
    """
    esp_repo = ESPRepository(session)
    sensor_repo = SensorRepository(session)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        return MeasureReadFailure(
            ok=False,
            reason="esp_not_found",
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=sensor_type,
        )
    if not esp_device.is_online:
        return MeasureReadFailure(
            ok=False,
            reason="esp_offline",
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=sensor_type,
        )

    reading = await sensor_repo.get_latest_reading(
        esp_id=esp_device.id, gpio=gpio, sensor_type=sensor_type
    )
    if reading is None:
        return MeasureReadFailure(
            ok=False,
            reason="missing",
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=sensor_type,
        )

    display_value = (
        reading.processed_value
        if reading.processed_value is not None
        else reading.raw_value
    )
    if display_value is None:
        return MeasureReadFailure(
            ok=False,
            reason="missing",
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=sensor_type or reading.sensor_type,
        )

    age_seconds = (datetime.now(timezone.utc) - reading.timestamp).total_seconds()
    sensor_config = await sensor_repo.get_by_esp_gpio_and_type(
        esp_id=esp_device.id, gpio=gpio, sensor_type=sensor_type or reading.sensor_type
    )
    operating_mode = "continuous"
    freshness_hours = None
    if sensor_config:
        operating_mode = sensor_config.operating_mode or "continuous"
        freshness_hours = getattr(sensor_config, "measurement_freshness_hours", None)

    resolved_type = sensor_type or reading.sensor_type
    sensor_key = (
        f"{esp_id}:{gpio}:{resolved_type}" if resolved_type else f"{esp_id}:{gpio}"
    )
    entry = {
        "value": display_value,
        "sensor_type": resolved_type,
        "age_seconds": age_seconds,
        "operating_mode": operating_mode,
        "measurement_freshness_hours": freshness_hours,
    }

    # Reuse existing AUT-41 freshness rules (no duplicated threshold invention).
    evaluator = SensorConditionEvaluator()
    stale_reason = evaluator._check_freshness(
        condition={
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": resolved_type,
        },
        context={"sensor_values": {sensor_key: entry}},
        trigger_matches=False,
    )
    if stale_reason is not None:
        return MeasureReadFailure(
            ok=False,
            reason="stale",
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=resolved_type,
            age_seconds=age_seconds,
            detail=stale_reason,
        )

    return MeasureReadSuccess(
        ok=True,
        value=float(display_value),
        age_seconds=age_seconds,
        sensor_type=resolved_type,
        operating_mode=operating_mode,
        measurement_freshness_hours=freshness_hours,
    )
