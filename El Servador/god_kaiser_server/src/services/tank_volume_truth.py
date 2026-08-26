"""
Tank volume truth from persisted ``volume_l`` (AUT-1563).

Reads existing ``rule_metadata.dose_config.volume_l`` on enabled rules whose
dosing ESPs (actions) all belong to the tank. Observe-only refs such as
``measure_bindings`` do not attribute volume. No name-parse ("20 Liter"),
no GPIO14 as volume truth, no new column.

Fail-closed: returns None when no typed volume_l is set.
Does NOT use ``tanks.nominal_volume_l``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.logic_repo import LogicRepository


logger = get_logger(__name__)

VOLUME_SOURCE_DOSE_CONFIG = "dose_config.volume_l"


@dataclass(frozen=True)
class TankVolumeTruth:
    """Resolved running volume for concentration attribution."""

    volume_l: float
    source: str
    anchor_liters: float
    level_gpio: Optional[int]
    level_device_id: Optional[str]
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
    1. Existing ``dose_config.volume_l`` on an enabled rule whose dosing
       ESPs all belong to this tank (same field LogicEngine uses for
       chemistry dose).
    2. None (fail-closed — no name magic, no GPIO guess).

    ``as_of`` is accepted for caller compatibility and unused: the typed
    volume is a configured value, not a time-series reconstruction.
    """
    esp_repo = ESPRepository(session)
    devices = await esp_repo.get_by_tank_id(tank_id)
    if not devices:
        logger.info("AUT-1563 V_real: no ESPs for tank_id=%s", tank_id)
        return None

    device_ids = {d.device_id for d in devices if d.device_id}
    volume = await _dose_config_volume_l(session, device_ids)
    if volume is None or volume <= 0:
        logger.info(
            "AUT-1563 V_real: no dose_config.volume_l for tank %s (devices=%s)",
            tank_id,
            sorted(device_ids),
        )
        return None

    return TankVolumeTruth(
        volume_l=round(float(volume), 4),
        source=VOLUME_SOURCE_DOSE_CONFIG,
        anchor_liters=round(float(volume), 4),
        level_gpio=None,
        level_device_id=None,
        flow_delta_l=0.0,
        anchor_at=None,
    )


async def _dose_config_volume_l(
    session: AsyncSession,
    device_ids: set[str],
) -> Optional[float]:
    """Return the first positive dose_config.volume_l owned by this tank."""
    if not device_ids:
        return None

    logic_repo = LogicRepository(session)
    rules = await logic_repo.get_enabled_rules()
    for rule in rules:
        meta = rule.rule_metadata or {}
        dose_config = meta.get("dose_config") if isinstance(meta, dict) else None
        if not isinstance(dose_config, dict):
            continue
        raw = dose_config.get("volume_l")
        try:
            volume = float(raw)
        except (TypeError, ValueError):
            continue
        if volume <= 0:
            continue
        if not _rule_touches_devices(rule, device_ids):
            continue
        return volume
    return None


def _rule_touches_devices(rule: Any, device_ids: set[str]) -> bool:
    """True when the rule's dosing ESPs all belong to the tank.

    Ownership is the action set only. Trigger conditions and
    ``rule_metadata`` (including observe-only ``measure_bindings``) must
    not attribute ``dose_config.volume_l`` to another tank.
    """
    dosing = _collect_esp_ids(getattr(rule, "actions", None))
    return bool(dosing) and dosing.issubset(device_ids)


def _collect_esp_ids(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        esp = obj.get("esp_id")
        if isinstance(esp, str) and esp:
            found.add(esp)
        for value in obj.values():
            found.update(_collect_esp_ids(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_collect_esp_ids(item))
    return found
