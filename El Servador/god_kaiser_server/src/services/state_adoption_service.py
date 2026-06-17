"""
State adoption lifecycle for reconnect-safe actuator handover.

This service tracks per-ESP reconnect cycles:
1) start adoption (ADOPTING),
2) collect adopted actuator states from status events,
3) mark adoption completed (ADOPTED),
4) allow delta-only enforce afterwards.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..core.logging_config import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AdoptedActuatorState:
    gpio: int
    state: str
    value: float
    observed_at: datetime


@dataclass
class AdoptionCycle:
    esp_id: str
    phase: str = "adopting"  # adopting | adopted
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    last_offline_seconds: Optional[float] = None
    adopted_actuator_states: dict[int, AdoptedActuatorState] = field(default_factory=dict)


class StateAdoptionService:
    """Process-wide adoption coordinator for reconnect handover."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cycles: dict[str, AdoptionCycle] = {}

    async def start_reconnect_cycle(
        self, esp_id: str, last_offline_seconds: Optional[float] = None
    ) -> None:
        async with self._lock:
            self._cycles[esp_id] = AdoptionCycle(
                esp_id=esp_id,
                phase="adopting",
                last_offline_seconds=last_offline_seconds,
            )
            logger.info(
                "State adoption started for %s (offline_seconds=%s)",
                esp_id,
                (
                    f"{last_offline_seconds:.1f}"
                    if isinstance(last_offline_seconds, (int, float))
                    else "n/a"
                ),
            )

    async def record_adopted_state(self, esp_id: str, gpio: int, state: str, value: float) -> None:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            if not cycle or cycle.phase != "adopting":
                return
            cycle.adopted_actuator_states[int(gpio)] = AdoptedActuatorState(
                gpio=int(gpio),
                state=str(state).lower(),
                value=float(value),
                observed_at=_utc_now(),
            )

    async def mark_adoption_completed(self, esp_id: str) -> bool:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            if not cycle:
                return False
            if cycle.phase != "adopted":
                cycle.phase = "adopted"
                cycle.completed_at = _utc_now()
                logger.info(
                    "State adoption completed for %s (adopted_states=%d)",
                    esp_id,
                    len(cycle.adopted_actuator_states),
                )
            return True

    async def is_adoption_completed(self, esp_id: str) -> bool:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            if cycle is None:
                return True
            return cycle.phase == "adopted"

    async def is_adopting(self, esp_id: str) -> bool:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            return bool(cycle and cycle.phase == "adopting")

    async def get_adopted_state(self, esp_id: str, gpio: int) -> Optional[AdoptedActuatorState]:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            if not cycle:
                return None
            return cycle.adopted_actuator_states.get(int(gpio))

    async def clear_cycle(self, esp_id: str) -> None:
        async with self._lock:
            self._cycles.pop(esp_id, None)

    async def snapshot(self, esp_id: str) -> Optional[dict]:
        async with self._lock:
            cycle = self._cycles.get(esp_id)
            if cycle is None:
                return None
            return {
                "esp_id": cycle.esp_id,
                "phase": cycle.phase,
                "started_at": cycle.started_at.isoformat(),
                "completed_at": cycle.completed_at.isoformat() if cycle.completed_at else None,
                "last_offline_seconds": cycle.last_offline_seconds,
                "adopted_count": len(cycle.adopted_actuator_states),
            }


_state_adoption: Optional[StateAdoptionService] = None


def get_state_adoption_service() -> StateAdoptionService:
    global _state_adoption
    if _state_adoption is None:
        _state_adoption = StateAdoptionService()
    return _state_adoption
