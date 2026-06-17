"""
Zone-Aware Thresholds — Dynamic alarm thresholds based on growth phase.

Phase 5: The Circle — ZoneContext (growth_phase) influences alert thresholds.
Status: IMPLEMENTED

Static thresholds (warning_high=30°C) ignore growth context.
In week 1 vegetative, 30°C is tolerable. In week 8 flower, 28°C is too high.

Used by:
- sensor_handler.py → _evaluate_thresholds_and_notify()
"""

from typing import Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.zone_context_repo import ZoneContextRepository

logger = get_logger(__name__)

PHASE_THRESHOLDS: Dict[str, Dict[str, Dict[str, float]]] = {
    "seedling": {
        "temperature": {"warning_low": 18, "warning_high": 28, "critical_high": 32},
        "humidity": {"warning_low": 50, "warning_high": 80, "critical_high": 90},
    },
    "clone": {
        "temperature": {"warning_low": 20, "warning_high": 28, "critical_high": 32},
        "humidity": {"warning_low": 60, "warning_high": 85, "critical_high": 95},
    },
    "vegetative": {
        "temperature": {"warning_low": 18, "warning_high": 30, "critical_high": 35},
        "humidity": {"warning_low": 40, "warning_high": 75, "critical_high": 85},
    },
    "pre_flower": {
        "temperature": {"warning_low": 18, "warning_high": 28, "critical_high": 32},
        "humidity": {"warning_low": 40, "warning_high": 65, "critical_high": 75},
    },
    "flower_early": {
        "temperature": {"warning_low": 18, "warning_high": 28, "critical_high": 32},
        "humidity": {"warning_low": 35, "warning_high": 65, "critical_high": 75},
    },
    "flower_late": {
        "temperature": {"warning_low": 16, "warning_high": 26, "critical_high": 30},
        "humidity": {"warning_low": 30, "warning_high": 55, "critical_high": 65},
    },
    "drying": {
        "temperature": {"warning_low": 16, "warning_high": 22, "critical_high": 26},
        "humidity": {"warning_low": 45, "warning_high": 65, "critical_high": 75},
    },
}

SENSOR_TYPE_TO_CATEGORY = {
    "sht31_temp": "temperature",
    "bmp280_temp": "temperature",
    "ds18b20": "temperature",
    "sht31_humidity": "humidity",
    "bmp280_humidity": "humidity",
}


def _normalize_phase(phase: str) -> str:
    """Normalize growth phase to a known key. flower_week_X → flower_early/flower_late."""
    if not phase:
        return "vegetative"
    p = phase.lower().strip()
    if p.startswith("flower_week_"):
        try:
            week = int(p.replace("flower_week_", ""))
            return "flower_late" if week >= 5 else "flower_early"
        except ValueError:
            return "flower_early"
    if p in PHASE_THRESHOLDS:
        return p
    if "flower" in p:
        return "flower_early"
    return "vegetative"


class ZoneAwareThresholdService:
    """Provides dynamic thresholds based on zone growth phase."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ctx_repo = ZoneContextRepository(session)
        self._cache: Dict[str, Tuple[str, Dict]] = {}

    async def get_thresholds(
        self, zone_id: Optional[str], sensor_type: str
    ) -> Optional[Dict[str, float]]:
        """Get phase-adjusted thresholds for a sensor type in a zone.

        Returns None if no zone context or no mapping exists.
        """
        if not zone_id:
            return None

        category = SENSOR_TYPE_TO_CATEGORY.get(sensor_type)
        if not category:
            return None

        ctx = await self.ctx_repo.get_by_zone_id(zone_id)
        if not ctx or not ctx.growth_phase:
            return None

        phase_key = _normalize_phase(ctx.growth_phase)
        phase_data = PHASE_THRESHOLDS.get(phase_key, {})
        return phase_data.get(category)

    async def evaluate_with_context(
        self,
        zone_id: Optional[str],
        sensor_type: str,
        value: float,
        static_thresholds: Optional[dict] = None,
    ) -> Optional[str]:
        """Evaluate a sensor value against phase-aware thresholds.

        Returns severity: 'critical', 'warning', or None (normal).
        Falls back to static_thresholds if no zone context available.
        """
        thresholds = await self.get_thresholds(zone_id, sensor_type)
        if not thresholds:
            thresholds = static_thresholds
        if not thresholds:
            return None

        critical_high = thresholds.get("critical_high")
        critical_low = thresholds.get("critical_low")
        warning_high = thresholds.get("warning_high")
        warning_low = thresholds.get("warning_low")

        if critical_high is not None and value >= critical_high:
            return "critical"
        if critical_low is not None and value <= critical_low:
            return "critical"
        if warning_high is not None and value >= warning_high:
            return "warning"
        if warning_low is not None and value <= warning_low:
            return "warning"

        return None
