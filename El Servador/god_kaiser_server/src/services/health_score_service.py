"""
Component Health Score — 0–100 score per device (Phase K4 L2.4)

Weighted factors: online status, error rate (24h), data quality, maintenance, uptime.
Used by: GET /v1/esp/devices/{esp_id}/health/score, Inventar table (K1) Health badge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorData

logger = get_logger(__name__)

# Weights (sum = 100)
W_ONLINE = 30
W_ERROR_RATE = 25
W_DATA_QUALITY = 20
W_MAINTENANCE = 15
W_UPTIME = 10


class HealthScoreService:
    """Compute health score (0–100) for an ESP device."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_score(self, device_id: str) -> Optional[dict[str, Any]]:
        """
        Return { "score": 0–100, "factors": { ... } } for the device.
        Returns None if device not found.
        """
        from ..db.repositories import ESPRepository

        esp_repo = ESPRepository(self.session)
        device = await esp_repo.get_by_device_id(device_id)
        if not device:
            return None

        factors: dict[str, Any] = {}
        total = 0.0

        # Online (30%)
        online_score = self._score_online(device)
        factors["online"] = {"score": online_score, "weight": W_ONLINE}
        total += online_score * (W_ONLINE / 100.0)

        # Error rate 24h (25%) — placeholder: no error log table yet
        error_score = 100.0
        factors["error_rate_24h"] = {"score": error_score, "weight": W_ERROR_RATE}
        total += error_score * (W_ERROR_RATE / 100.0)

        # Data quality (20%) — from latest sensor data quality
        quality_score = await self._score_data_quality(device.id)
        factors["data_quality"] = {"score": quality_score, "weight": W_DATA_QUALITY}
        total += quality_score * (W_DATA_QUALITY / 100.0)

        # Maintenance (15%) — from device_metadata or sensor runtime
        maint_score = self._score_maintenance(device)
        factors["maintenance"] = {"score": maint_score, "weight": W_MAINTENANCE}
        total += maint_score * (W_MAINTENANCE / 100.0)

        # Uptime (10%)
        uptime_score = self._score_uptime(device)
        factors["uptime"] = {"score": uptime_score, "weight": W_UPTIME}
        total += uptime_score * (W_UPTIME / 100.0)

        return {
            "device_id": device_id,
            "score": round(min(100.0, max(0.0, total)), 1),
            "factors": factors,
        }

    def _score_online(self, device: ESPDevice) -> float:
        if device.status == "online":
            return 100.0
        if device.status == "error":
            return 40.0
        if not device.last_seen:
            return 0.0
        last = device.last_seen
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - last).total_seconds()
        if delta < 300:
            return 80.0  # offline < 5 min
        if delta < 3600:
            return 50.0
        return 0.0

    async def _score_data_quality(self, esp_uuid: Any) -> float:
        """Average quality of latest sensor readings (excellent=100, good=80, …)."""
        quality_map = {
            "excellent": 100,
            "good": 80,
            "fair": 60,
            "poor": 40,
            "bad": 20,
            "stale": 30,
            "error": 0,
        }
        stmt = (
            select(SensorData.quality)
            .where(SensorData.esp_id == esp_uuid)
            .order_by(SensorData.timestamp.desc())
            .limit(50)
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return 80.0  # no data yet
        total = sum(quality_map.get(str(q), 50) for q in rows if q)
        return total / len(rows) if rows else 80.0

    def _score_maintenance(self, device: ESPDevice) -> float:
        _ = device.device_metadata or {}
        # Placeholder: no maintenance_until in device_metadata yet
        return 100.0

    def _score_uptime(self, device: ESPDevice) -> float:
        health = (device.device_metadata or {}).get("health", {})
        uptime_sec = health.get("uptime", 0)
        hours = uptime_sec / 3600.0
        if hours < 1000:
            return 100.0
        if hours < 5000:
            return 60.0
        if hours < 10000:
            return 30.0
        return 20.0
