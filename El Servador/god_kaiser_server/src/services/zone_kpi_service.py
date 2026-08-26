"""
Zone KPI Service — Computes zone-level KPIs from sensor data + context.

Phase 5: The Circle — Sensor data flows into zone KPIs.
Status: IMPLEMENTED

Provides:
- VPD from latest zone temperature + SHT31 humidity (BMP280 has no RH)
- Growth progress from planted_date/expected_harvest
- Zone health score aggregated from device health

DLI is not computed: light/lux is not PPFD, and no reader exists (AUT-1530).
Live VPD persist remains on SHT31 ingest in sensor_handler.

Used by:
- REST API (GET /v1/zone/context/{zone_id}/kpis) — no WebSocket publisher
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorConfig, SensorData
from ..db.repositories.zone_context_repo import ZoneContextRepository
from .vpd_calculator import calculate_vpd as _calc_vpd

logger = get_logger(__name__)


def _calculate_vpd(temp_c: float, humidity_pct: float) -> float:
    """Calculate Vapor Pressure Deficit (kPa) from temperature and humidity.

    Delegates to the shared vpd_calculator module (single source of truth).
    """
    result = _calc_vpd(temp_c, humidity_pct)
    # Preserve original behavior: return 0.0 for out-of-range inputs
    return round(max(result or 0.0, 0.0), 3)


class VPDResult:
    def __init__(self, vpd: float, temp: float, humidity: float, quality: str = "good"):
        self.vpd = vpd
        self.temp = temp
        self.humidity = humidity
        self.quality = quality

    def to_dict(self) -> dict:
        return {
            "vpd_kpa": self.vpd,
            "temperature_c": self.temp,
            "humidity_pct": self.humidity,
            "quality": self.quality,
        }


class ZoneKPIService:
    """Computes zone-level KPIs from live sensor data + zone context."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ctx_repo = ZoneContextRepository(session)

    async def calculate_vpd(self, zone_id: str, domain: Optional[str] = None) -> Optional[dict]:
        """VPD from latest temperature + humidity sensors in the zone.

        Args:
            zone_id: Zone identifier.
            domain: Optional report domain pre-filter (AUT-1087).  When set,
                only devices with ``ESPDevice.domain == domain`` contribute.
                ``None`` (default) preserves the existing zone-wide behaviour.
        """
        temp_val = await self._get_latest_sensor_value(
            zone_id, ["sht31_temp", "bmp280_temp", "ds18b20"], domain=domain
        )
        hum_val = await self._get_latest_sensor_value(
            zone_id, ["sht31_humidity"], domain=domain
        )

        if temp_val is None or hum_val is None:
            return None

        vpd = _calculate_vpd(temp_val, hum_val)
        return VPDResult(vpd, temp_val, hum_val).to_dict()

    async def calculate_growth_progress(self, zone_id: str) -> Optional[dict]:
        """Growth progress from planted_date / expected_harvest."""
        ctx = await self.ctx_repo.get_by_zone_id(zone_id)
        if not ctx or not ctx.planted_date:
            return None

        age_days = ctx.plant_age_days or 0
        days_left = ctx.days_to_harvest

        total_days = None
        progress_pct = None
        if ctx.expected_harvest and ctx.planted_date:
            total_days = (ctx.expected_harvest - ctx.planted_date).days
            if total_days > 0:
                progress_pct = round(min(age_days / total_days * 100, 100), 1)

        return {
            "growth_phase": ctx.growth_phase,
            "plant_age_days": age_days,
            "days_to_harvest": days_left,
            "total_cycle_days": total_days,
            "progress_pct": progress_pct,
            "variety": ctx.variety,
        }

    async def get_zone_health_score(self, zone_id: str) -> Optional[dict]:
        """Aggregated health score (0-100) from all devices in the zone."""
        stmt = select(ESPDevice).where(
            ESPDevice.zone_id == zone_id,
            ESPDevice.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        devices = list(result.scalars().all())

        if not devices:
            return None

        scores: List[float] = []
        for device in devices:
            score = self._device_health_score(device)
            scores.append(score)

        avg_score = sum(scores) / len(scores) if scores else 0
        return {
            "zone_health_score": round(avg_score, 1),
            "device_count": len(devices),
            "online_count": sum(1 for d in devices if d.status == "online"),
            "lowest_score": round(min(scores), 1) if scores else 0,
        }

    async def get_all_kpis(self, zone_id: str, domain: Optional[str] = None) -> dict:
        """All KPIs in one call.

        Args:
            zone_id: Zone identifier.
            domain: Optional report domain pre-filter (AUT-1087).  Forwarded to
                ``calculate_vpd`` only.  Zone health and growth progress are
                always zone-wide (by design).  ``dli`` is always ``None``
                (AUT-1530: lux is not PPFD, no reader).
        """
        vpd = await self.calculate_vpd(zone_id, domain=domain)
        growth = await self.calculate_growth_progress(zone_id)
        health = await self.get_zone_health_score(zone_id)

        return {
            "zone_id": zone_id,
            "vpd": vpd,
            "dli": None,
            "growth": growth,
            "health": health,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─── Internal helpers ─────────────────────────────────────────────

    async def _get_latest_sensor_value(
        self,
        zone_id: str,
        sensor_types: List[str],
        domain: Optional[str] = None,
    ) -> Optional[float]:
        """Get latest processed_value from any sensor of given types in the zone.

        Args:
            zone_id: Zone identifier.
            sensor_types: Accepted sensor type names (OR condition).
            domain: Optional report domain pre-filter (AUT-1087).  When set,
                restricts to devices whose ``ESPDevice.domain`` matches.
        """
        conditions = [
            ESPDevice.zone_id == zone_id,
            ESPDevice.deleted_at.is_(None),
            SensorData.sensor_type.in_(sensor_types),
            SensorData.processed_value.isnot(None),
        ]
        if domain is not None:
            conditions.append(ESPDevice.domain == domain)

        stmt = (
            select(SensorData.processed_value)
            .join(
                SensorConfig,
                and_(
                    SensorData.esp_id == SensorConfig.esp_id,
                    SensorData.gpio == SensorConfig.gpio,
                ),
            )
            .join(ESPDevice, SensorConfig.esp_id == ESPDevice.id)
            .where(*conditions)
            .order_by(SensorData.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return float(row) if row is not None else None

    def _device_health_score(self, device: ESPDevice) -> float:
        """Calculate health score for a single device (0-100)."""
        score = 100.0

        if device.status != "online":
            score -= 40
        if device.status == "error":
            score -= 20

        meta = device.device_metadata or {}
        health = meta.get("health", {})

        heap_free = health.get("heap_free")
        if heap_free is not None and heap_free < 20000:
            score -= 15

        rssi = health.get("wifi_rssi")
        if rssi is not None and rssi < -80:
            score -= 10

        return max(score, 0.0)
