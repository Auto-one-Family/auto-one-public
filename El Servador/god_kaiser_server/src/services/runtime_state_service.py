"""
Runtime state machine for server operational lifecycle (P1.2/P1.3).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from ..core.metrics import increment_ready_blocked, increment_ready_transition
from ..core.logging_config import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeMode(str, Enum):
    COLD_START = "COLD_START"
    WARMING_UP = "WARMING_UP"
    NORMAL_OPERATION = "NORMAL_OPERATION"
    DEGRADED_OPERATION = "DEGRADED_OPERATION"
    RECOVERY_SYNC = "RECOVERY_SYNC"
    SHUTDOWN_DRAIN = "SHUTDOWN_DRAIN"


@dataclass
class RuntimeTransition:
    from_state: RuntimeMode
    to_state: RuntimeMode
    reason: str
    at: datetime = field(default_factory=_utc_now)


class RuntimeStateService:
    """Process-wide runtime-mode state machine with readiness guards."""

    _ALLOWED: dict[RuntimeMode, set[RuntimeMode]] = {
        RuntimeMode.COLD_START: {RuntimeMode.WARMING_UP, RuntimeMode.SHUTDOWN_DRAIN},
        RuntimeMode.WARMING_UP: {
            RuntimeMode.RECOVERY_SYNC,
            RuntimeMode.NORMAL_OPERATION,
            RuntimeMode.DEGRADED_OPERATION,
            RuntimeMode.SHUTDOWN_DRAIN,
        },
        RuntimeMode.RECOVERY_SYNC: {
            RuntimeMode.NORMAL_OPERATION,
            RuntimeMode.DEGRADED_OPERATION,
            RuntimeMode.SHUTDOWN_DRAIN,
        },
        RuntimeMode.NORMAL_OPERATION: {
            RuntimeMode.DEGRADED_OPERATION,
            RuntimeMode.RECOVERY_SYNC,
            RuntimeMode.SHUTDOWN_DRAIN,
        },
        RuntimeMode.DEGRADED_OPERATION: {
            RuntimeMode.NORMAL_OPERATION,
            RuntimeMode.RECOVERY_SYNC,
            RuntimeMode.SHUTDOWN_DRAIN,
        },
        RuntimeMode.SHUTDOWN_DRAIN: set(),
    }

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: RuntimeMode = RuntimeMode.COLD_START
        self._transitions: list[RuntimeTransition] = []
        self._logic_liveness = False
        self._recovery_completed = False
        self._worker_health: dict[str, bool] = {
            "mqtt_subscriber": False,
            "websocket_manager": False,
            "inbound_replay_worker": False,
        }
        self._degraded_reasons: set[str] = set()
        self._last_ready: Optional[bool] = None
        self._last_blocked: bool = False

    async def transition(self, target: RuntimeMode, reason: str) -> None:
        async with self._lock:
            if target == self._state:
                return
            if target not in self._ALLOWED.get(self._state, set()):
                logger.warning(
                    "Runtime transition blocked: %s -> %s (%s)",
                    self._state.value,
                    target.value,
                    reason,
                )
                return
            old = self._state
            self._state = target
            self._transitions.append(
                RuntimeTransition(from_state=old, to_state=target, reason=reason)
            )
            logger.info(
                "Runtime transition: %s -> %s (%s)",
                old.value,
                target.value,
                reason,
            )

    async def set_logic_liveness(self, alive: bool) -> None:
        async with self._lock:
            self._logic_liveness = bool(alive)

    async def set_recovery_completed(self, completed: bool) -> None:
        async with self._lock:
            self._recovery_completed = bool(completed)

    async def set_worker_health(self, worker_name: str, healthy: bool) -> None:
        async with self._lock:
            self._worker_health[worker_name] = bool(healthy)

    async def set_degraded_reason(self, reason_code: str, active: bool) -> None:
        async with self._lock:
            if active:
                self._degraded_reasons.add(reason_code)
            else:
                self._degraded_reasons.discard(reason_code)

    async def snapshot(self) -> dict:
        async with self._lock:
            checks = {
                "logic_liveness": self._logic_liveness,
                "recovery_completed": self._recovery_completed,
                **self._worker_health,
            }
            ready = (
                self._state == RuntimeMode.NORMAL_OPERATION
                and all(checks.values())
                and not self._degraded_reasons
            )

            blocked = self._state == RuntimeMode.NORMAL_OPERATION and not ready
            if ready and self._last_ready is not True:
                increment_ready_transition()
            if blocked and not self._last_blocked:
                increment_ready_blocked()
            self._last_ready = ready
            self._last_blocked = blocked

            return {
                "mode": self._state.value,
                "ready": ready,
                "checks": checks,
                "degraded_reason_codes": sorted(self._degraded_reasons),
                "recent_transitions": [
                    {
                        "from": t.from_state.value,
                        "to": t.to_state.value,
                        "reason": t.reason,
                        "at": t.at.isoformat(),
                    }
                    for t in self._transitions[-20:]
                ],
            }


_runtime_state: Optional[RuntimeStateService] = None


def get_runtime_state_service() -> RuntimeStateService:
    global _runtime_state
    if _runtime_state is None:
        _runtime_state = RuntimeStateService()
    return _runtime_state
