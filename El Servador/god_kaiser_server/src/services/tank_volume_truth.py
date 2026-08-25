"""
Tank volume truth from Level-Anker + Flow-Delta (AUT-1371 K2).

Composes existing pieces — no new sensor type, no new integrator:
- liquid_level sensor named ``20 Liter`` (anchor = 20.0 L when active)
- ``FlowVolumeService.accumulate_flow_volume_l`` for delta since last anchor

Fail-closed: returns None when no usable absolute volume can be derived.
Does NOT use ``tanks.nominal_volume_l``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorConfig, SensorData
from ..db.repositories.esp_repo import ESPRepository
from .flow_volume_service import (
    REFILL_FLOW_DEVICE_ID,
    REFILL_FLOW_GPIO,
    REFILL_FLOW_SENSOR_TYPE,
    FlowVolumeService,
)


logger = get_logger(__name__)

LEVEL_ANCHOR_LITERS = 20.0
LEVEL_ANCHOR_SENSOR_NAME = "20 Liter"
LEVEL_SENSOR_TYPE = "liquid_level"


@dataclass(frozen=True)
class TankVolumeTruth:
    """Resolved running volume for concentration attribution."""

    volume_l: float
    source: str
    anchor_liters: float
    level_gpio: int
    level_device_id: str
    flow_delta_l: float
    anchor_at: Optional[datetime]


async def resolve_v_real(
    session: AsyncSession,
    tank_id: UUID,
    *,
    as_of: Optional[datetime] = None,
) -> Optional[TankVolumeTruth]:
    """
    Resolve ``V_real`` for ``tank_id``.

    Priority:
    1. Live level anchor active (processed/raw == 1) → exactly ``LEVEL_ANCHOR_LITERS``
    2. Last time anchor was high + flow delta since then (Flow-first Minimal-Start)
    3. None (fail-closed)
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    esp_repo = ESPRepository(session)
    devices = await esp_repo.get_by_tank_id(tank_id)
    if not devices:
        logger.info("AUT-1371 V_real: no ESPs for tank_id=%s", tank_id)
        return None

    level_cfg, level_device = await _find_level_anchor(session, devices)
    if level_cfg is None or level_device is None:
        logger.info(
            "AUT-1371 V_real: no '%s' liquid_level sensor on tank %s",
            LEVEL_ANCHOR_SENSOR_NAME,
            tank_id,
        )
        return None

    latest = await _latest_level_reading(session, level_cfg.esp_id, int(level_cfg.gpio))
    if latest is not None and _level_is_active(latest):
        return TankVolumeTruth(
            volume_l=LEVEL_ANCHOR_LITERS,
            source="level_anchor_live",
            anchor_liters=LEVEL_ANCHOR_LITERS,
            level_gpio=int(level_cfg.gpio),
            level_device_id=level_device.device_id,
            flow_delta_l=0.0,
            anchor_at=(
                latest.timestamp
                if latest.timestamp.tzinfo
                else latest.timestamp.replace(tzinfo=timezone.utc)
            ),
        )

    anchor_at = await _last_anchor_high_at(session, level_cfg.esp_id, int(level_cfg.gpio))
    if anchor_at is None:
        logger.info(
            "AUT-1371 V_real: no historical '%s' high for tank %s (gpio=%s)",
            LEVEL_ANCHOR_SENSOR_NAME,
            tank_id,
            level_cfg.gpio,
        )
        return None

    flow_esp = await _resolve_flow_esp(session, devices)
    if flow_esp is None:
        logger.info("AUT-1371 V_real: no flow ESP for tank %s", tank_id)
        return None

    flow_svc = FlowVolumeService(session)
    flow_result = await flow_svc.accumulate_flow_volume_l(
        flow_esp.id,
        REFILL_FLOW_GPIO,
        anchor_at,
        now,
        sensor_type=REFILL_FLOW_SENSOR_TYPE,
    )
    volume = LEVEL_ANCHOR_LITERS + float(flow_result.volume_l)
    if volume <= 0:
        return None

    return TankVolumeTruth(
        volume_l=round(volume, 4),
        source="anchor_plus_flow_delta",
        anchor_liters=LEVEL_ANCHOR_LITERS,
        level_gpio=int(level_cfg.gpio),
        level_device_id=level_device.device_id,
        flow_delta_l=float(flow_result.volume_l),
        anchor_at=anchor_at,
    )


async def _find_level_anchor(
    session: AsyncSession,
    devices: list[ESPDevice],
) -> tuple[Optional[SensorConfig], Optional[ESPDevice]]:
    esp_ids = [d.id for d in devices]
    stmt = select(SensorConfig).where(
        and_(
            SensorConfig.esp_id.in_(esp_ids),
            SensorConfig.sensor_type == LEVEL_SENSOR_TYPE,
            SensorConfig.sensor_name == LEVEL_ANCHOR_SENSOR_NAME,
            SensorConfig.enabled.is_(True),
        )
    )
    result = await session.execute(stmt)
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return None, None
    device = next((d for d in devices if d.id == cfg.esp_id), None)
    return cfg, device


async def _latest_level_reading(
    session: AsyncSession, esp_id: UUID, gpio: int
) -> Optional[SensorData]:
    stmt = (
        select(SensorData)
        .where(
            SensorData.esp_id == esp_id,
            SensorData.gpio == gpio,
            SensorData.sensor_type == LEVEL_SENSOR_TYPE,
        )
        .order_by(desc(SensorData.timestamp))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _last_anchor_high_at(
    session: AsyncSession, esp_id: UUID, gpio: int
) -> Optional[datetime]:
    stmt = (
        select(SensorData.timestamp)
        .where(
            SensorData.esp_id == esp_id,
            SensorData.gpio == gpio,
            SensorData.sensor_type == LEVEL_SENSOR_TYPE,
            ((SensorData.processed_value == 1.0) | (SensorData.raw_value == 1.0)),
        )
        .order_by(desc(SensorData.timestamp))
        .limit(1)
    )
    result = await session.execute(stmt)
    ts = result.scalar_one_or_none()
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _level_is_active(row: SensorData) -> bool:
    value = row.processed_value if row.processed_value is not None else row.raw_value
    if value is None:
        return False
    try:
        return float(value) >= 0.5
    except (TypeError, ValueError):
        return False


async def _resolve_flow_esp(session: AsyncSession, devices: list[ESPDevice]) -> Optional[ESPDevice]:
    by_id = {d.device_id: d for d in devices}
    if REFILL_FLOW_DEVICE_ID in by_id:
        return by_id[REFILL_FLOW_DEVICE_ID]
    # Fallback: any tank ESP that has a flow sensor on the canonical GPIO
    esp_ids = [d.id for d in devices]
    stmt = (
        select(SensorConfig.esp_id)
        .where(
            and_(
                SensorConfig.esp_id.in_(esp_ids),
                SensorConfig.gpio == REFILL_FLOW_GPIO,
                SensorConfig.sensor_type == REFILL_FLOW_SENSOR_TYPE,
                SensorConfig.enabled.is_(True),
            )
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    esp_uuid = result.scalar_one_or_none()
    if esp_uuid is None:
        return None
    return next((d for d in devices if d.id == esp_uuid), None)
