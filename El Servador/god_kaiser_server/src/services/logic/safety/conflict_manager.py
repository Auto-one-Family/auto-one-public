"""
Conflict Manager für Logic Engine

Erkennt und löst Konflikte wenn mehrere Rules den gleichen Actuator steuern wollen.

INTEGRATION: Via Dependency Injection in LogicEngine
PATTERN: Kein Singleton - wird als Dependency injiziert
"""

import asyncio
import logging
import logging.handlers
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ....core.config import get_settings
from ....core.logging_config import JSONFormatter, get_logger

logger = get_logger(__name__)


def _build_arbitration_logger() -> logging.Logger:
    """Build dedicated structured logger for conflict arbitration decisions."""
    logger_name = "conflict_manager.arbitration"
    arbitration_logger = logging.getLogger(logger_name)
    if getattr(arbitration_logger, "_aut_one_initialized", False):
        return arbitration_logger

    settings = get_settings()
    root_log_path = Path(settings.logging.file_path)
    conflict_log_path = root_log_path.with_name("conflict_manager.log")
    conflict_log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        filename=conflict_log_path,
        maxBytes=settings.logging.file_max_bytes,
        backupCount=settings.logging.file_backup_count,
        encoding="utf-8",
    )
    if settings.logging.format == "json":
        formatter = JSONFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, settings.logging.level))

    arbitration_logger.handlers.clear()
    arbitration_logger.addHandler(handler)
    arbitration_logger.setLevel(getattr(logging, settings.logging.level))
    arbitration_logger.propagate = False
    setattr(arbitration_logger, "_aut_one_initialized", True)
    return arbitration_logger


arbitration_logger = _build_arbitration_logger()


class ConflictResolution(Enum):
    """Wie ein Konflikt aufgelöst wird.

    HIGHER_PRIORITY_WINS bedeutet: die gewinnende Regel hat die höhere Konfliktpriorität,
    also die niedrigere numerische ``priority`` (kleinere Zahl im Datenmodell), nicht die
    größere Zahl im Feld.
    """

    HIGHER_PRIORITY_WINS = "higher_priority_wins"
    FIRST_WINS = "first_wins"
    SAFETY_WINS = "safety_wins"  # Sicherheits-relevante Commands haben Vorrang
    BLOCKED = "blocked"  # Actuator ist temporär blockiert


@dataclass
class ConflictInfo:
    """Information über einen erkannten Konflikt."""

    actuator_key: str  # "esp_id:gpio"
    competing_rules: List[str]  # Rule-IDs die konkurrieren
    winner_rule_id: str
    resolution: ConflictResolution
    blocked_until: Optional[datetime] = None
    message: str = ""
    trace_id: str = ""


@dataclass
class ActuatorLock:
    """Lock für einen Actuator."""

    rule_id: str
    priority: int
    command: str
    acquired_at: datetime
    expires_at: Optional[datetime] = None
    is_safety_critical: bool = False
    active_zone_id: Optional[str] = None  # T13-R2: Zone this lock serves


class ConflictManager:
    """
    Verwaltet Konflikte zwischen Rules die den gleichen Actuator steuern.

    Strategie:
        1. Höhere Priorität gewinnt (niedrigerer priority-Wert = höher)
        2. Bei gleicher Priorität: Erste Rule gewinnt (FIFO)
        3. Safety-kritische Commands haben IMMER Vorrang
        4. Locks haben TTL (default: 60 Sekunden)

    Thread-Safety:
        - asyncio.Lock für jeden Actuator
        - Alle Operationen sind async

    USAGE:
        conflict_manager = ConflictManager()
        can_execute, conflict = await conflict_manager.acquire_actuator(
            esp_id="ESP_001",
            gpio=12,
            rule_id="rule-123",
            priority=1,
            command="ON"
        )
    """

    DEFAULT_LOCK_TTL_SECONDS = 60
    SAFETY_PRIORITY = -1000  # Safety-Commands haben immer höchste Priorität

    def __init__(self, websocket_manager=None):
        self._locks: Dict[str, ActuatorLock] = {}  # "esp_id:gpio" → Lock
        self._mutexes: Dict[str, asyncio.Lock] = {}  # "esp_id:gpio" → asyncio.Lock
        self._conflict_history: List[ConflictInfo] = []
        self._websocket_manager = websocket_manager  # P0-Fix T9: user notification

    @staticmethod
    def _decision_mode_for_resolution(resolution: ConflictResolution) -> str:
        """Map internal resolution enum to operator-facing arbitration mode."""
        if resolution in (
            ConflictResolution.HIGHER_PRIORITY_WINS,
            ConflictResolution.SAFETY_WINS,
        ):
            return "priority"
        return "first_wins"

    def _get_actuator_key(self, esp_id: str, gpio: int, zone_id: Optional[str] = None) -> str:
        """
        Generiert eindeutigen Key für Actuator.

        T13-R2: For zone-aware locking, zone_id is included in the key.
        This allows the same physical actuator to be locked per-zone
        for sequential multi-zone operation.
        """
        if zone_id:
            return f"{esp_id}:{gpio}:{zone_id}"
        return f"{esp_id}:{gpio}"

    def _get_mutex(self, actuator_key: str) -> asyncio.Lock:
        """Holt oder erstellt Mutex für Actuator."""
        if actuator_key not in self._mutexes:
            self._mutexes[actuator_key] = asyncio.Lock()
        return self._mutexes[actuator_key]

    async def acquire_actuator(
        self,
        esp_id: str,
        gpio: int,
        rule_id: str,
        priority: int,
        command: str,
        is_safety_critical: bool = False,
        lock_ttl_seconds: Optional[int] = None,
        zone_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[ConflictInfo]]:
        """
        Versucht einen Actuator für eine Rule zu reservieren.

        Args:
            esp_id: ESP-ID
            gpio: GPIO des Actuators
            rule_id: ID der aufrufenden Rule
            priority: Priorität (niedriger = höher)
            command: Das gewünschte Command (ON, OFF, PWM, etc.)
            is_safety_critical: True für Emergency-Stop etc.
            lock_ttl_seconds: Wie lange der Lock gehalten wird
            zone_id: T13-R2 — Zone context for multi-zone actuators

        Returns:
            Tuple of (success, conflict_info)
            - success=True: Rule darf Actuator steuern
            - success=False: Konflikt, conflict_info enthält Details
        """
        actuator_key = self._get_actuator_key(esp_id, gpio, zone_id)
        mutex = self._get_mutex(actuator_key)

        async with mutex:
            now = datetime.now(timezone.utc)
            existing_lock = self._locks.get(actuator_key)
            effective_priority = self.SAFETY_PRIORITY if is_safety_critical else priority

            # Cleanup: Abgelaufene Locks entfernen
            if existing_lock and existing_lock.expires_at and existing_lock.expires_at < now:
                del self._locks[actuator_key]
                existing_lock = None

            # Kein existierender Lock → einfach erwerben
            if existing_lock is None:
                ttl = lock_ttl_seconds or self.DEFAULT_LOCK_TTL_SECONDS
                self._locks[actuator_key] = ActuatorLock(
                    rule_id=rule_id,
                    priority=self.SAFETY_PRIORITY if is_safety_critical else priority,
                    command=command,
                    acquired_at=now,
                    expires_at=now + timedelta(seconds=ttl),
                    is_safety_critical=is_safety_critical,
                    active_zone_id=zone_id,
                )
                logger.debug(f"Actuator {actuator_key} acquired by rule {rule_id}")
                return True, None

            # Gleiche Rule → erlauben (Update)
            if existing_lock.rule_id == rule_id:
                existing_lock.command = command
                existing_lock.acquired_at = now
                existing_lock.priority = effective_priority
                existing_lock.is_safety_critical = is_safety_critical
                logger.debug(f"Actuator {actuator_key} renewed by rule {rule_id}")
                return True, None

            # Konflikt! Resolution bestimmen
            # Safety-kritische Commands gewinnen immer
            if is_safety_critical and not existing_lock.is_safety_critical:
                resolution = ConflictResolution.SAFETY_WINS
                winner = rule_id
                self._locks[actuator_key] = ActuatorLock(
                    rule_id=rule_id,
                    priority=effective_priority,
                    command=command,
                    acquired_at=now,
                    expires_at=now
                    + timedelta(seconds=lock_ttl_seconds or self.DEFAULT_LOCK_TTL_SECONDS),
                    is_safety_critical=True,
                    active_zone_id=zone_id,
                )
                logger.warning(
                    f"Safety override on {actuator_key}: {rule_id} > {existing_lock.rule_id}"
                )

            # Höhere Priorität gewinnt
            elif effective_priority < existing_lock.priority:
                resolution = ConflictResolution.HIGHER_PRIORITY_WINS
                winner = rule_id
                self._locks[actuator_key] = ActuatorLock(
                    rule_id=rule_id,
                    priority=effective_priority,
                    command=command,
                    acquired_at=now,
                    expires_at=now
                    + timedelta(seconds=lock_ttl_seconds or self.DEFAULT_LOCK_TTL_SECONDS),
                    is_safety_critical=is_safety_critical,
                    active_zone_id=zone_id,
                )
                logger.warning(
                    f"Priority override on {actuator_key}: {rule_id} (prio {priority}) > "
                    f"{existing_lock.rule_id} (prio {existing_lock.priority})"
                )

            # Gleiche oder niedrigere Priorität
            # P1-Fix T9: Deterministic tie-breaker — when priorities are equal,
            # use lexicographic rule_id comparison instead of arrival order (FIFO).
            # This ensures the same rule always wins regardless of evaluation order
            # or server restart timing.
            elif effective_priority == existing_lock.priority:
                # Tie: deterministic winner by rule_id (smaller UUID string wins)
                if rule_id < existing_lock.rule_id:
                    resolution = ConflictResolution.HIGHER_PRIORITY_WINS
                    winner = rule_id
                    self._locks[actuator_key] = ActuatorLock(
                        rule_id=rule_id,
                        priority=effective_priority,
                        command=command,
                        acquired_at=now,
                        expires_at=now
                        + timedelta(seconds=lock_ttl_seconds or self.DEFAULT_LOCK_TTL_SECONDS),
                        is_safety_critical=is_safety_critical,
                        active_zone_id=zone_id,
                    )
                    logger.warning(
                        f"Tie-break on {actuator_key}: {rule_id} wins over "
                        f"{existing_lock.rule_id} (equal priority {effective_priority}, "
                        f"deterministic rule_id comparison)"
                    )
                else:
                    resolution = ConflictResolution.FIRST_WINS
                    winner = existing_lock.rule_id
                    logger.warning(
                        f"Tie-break on {actuator_key}: {rule_id} blocked by "
                        f"{existing_lock.rule_id} (equal priority {effective_priority}, "
                        f"deterministic rule_id comparison)"
                    )
            else:
                resolution = ConflictResolution.FIRST_WINS
                winner = existing_lock.rule_id
                logger.warning(
                    "Conflict on %s: %s blocked by %s (lower priority %d vs %d)",
                    actuator_key,
                    rule_id,
                    existing_lock.rule_id,
                    effective_priority,
                    existing_lock.priority,
                    extra={
                        "event_class": "RULE_ARBITRATION",
                        "result": "blocked",
                        "classification": "expected",
                        "policy": "first_wins",
                        "actuator_key": actuator_key,
                        "winner_rule_id": existing_lock.rule_id,
                        "loser_rule_id": rule_id,
                        "winner_priority": existing_lock.priority,
                        "loser_priority": effective_priority,
                    },
                )

            conflict = ConflictInfo(
                actuator_key=actuator_key,
                competing_rules=[existing_lock.rule_id, rule_id],
                winner_rule_id=winner,
                resolution=resolution,
                blocked_until=existing_lock.expires_at if winner != rule_id else None,
                message=f"Conflict on {actuator_key}: {resolution.value}",
                trace_id=str(uuid.uuid4()),
            )

            self._conflict_history.append(conflict)

            loser_rule_id = existing_lock.rule_id if winner == rule_id else rule_id
            winner_priority = effective_priority if winner == rule_id else existing_lock.priority
            loser_priority = existing_lock.priority if winner == rule_id else effective_priority
            arbitration_payload = {
                "trace_id": conflict.trace_id,
                "actuator_key": actuator_key,
                "winner_rule_id": winner,
                "loser_rule_id": loser_rule_id,
                "competing_rules": conflict.competing_rules,
                "arbitration_mode": self._decision_mode_for_resolution(resolution),
                "resolution": conflict.resolution.value,
                "winner_priority": winner_priority,
                "loser_priority": loser_priority,
                "command": command,
                "message": conflict.message,
                "timestamp": now.isoformat(),
            }

            arbitration_logger.info(
                "Conflict arbitration decision",
                extra={"extra": arbitration_payload},
            )

            # AUT-114: Structured rule_conflict_resolved log + WS telemetry event.
            # Distinct from AUT-131 _emit_conflict_alert (alert-center lifecycle):
            # this is a pure telemetry signal for system-monitor and dashboards.
            policy_name = self._decision_mode_for_resolution(resolution)
            losers_payload = [
                {
                    "id": loser_rule_id,
                    "name": loser_rule_id,  # Conflict-Manager only knows rule_id
                    "priority": loser_priority,
                    "reason": "lower_priority",
                }
            ]
            winning_payload = {
                "id": winner,
                "name": winner,  # Conflict-Manager only knows rule_id
                "priority": winner_priority,
            }
            correlation_id = (
                f"conflict_{esp_id}_{gpio}_{int(time.time() * 1000)}"
            )

            logger.info(
                "rule_conflict_resolved",
                extra={
                    "correlation_id": correlation_id,
                    "category": "rule_arbitration",
                    "target_esp_id": esp_id,
                    "target_gpio": gpio,
                    "winning_rule": winning_payload,
                    "losing_rules": losers_payload,
                    "resolution_policy": policy_name,
                },
            )

            if self._websocket_manager:
                try:
                    await self._websocket_manager.broadcast(
                        "conflict.arbitration",
                        arbitration_payload,
                    )
                except Exception as ws_err:
                    logger.debug("Conflict arbitration broadcast failed: %s", ws_err)

                # AUT-114: dedicated telemetry event (separate from AUT-131
                # _emit_conflict_alert which drives the alert-center lifecycle).
                try:
                    await self._websocket_manager.broadcast(
                        "rule_conflict_resolved",
                        {
                            "category": "rule_arbitration",
                            "correlation_id": correlation_id,
                            "target_esp_id": esp_id,
                            "target_gpio": gpio,
                            "winning_rule_id": winner,
                            "winning_rule_name": winner,
                            "losing_rule_ids": [loser_rule_id],
                            "resolution_policy": policy_name,
                        },
                    )
                except Exception as ws_err:
                    logger.warning(
                        "rule_conflict_resolved WS broadcast failed: %s", ws_err
                    )

            return winner == rule_id, conflict

    async def release_actuator(
        self, esp_id: str, gpio: int, rule_id: str, zone_id: Optional[str] = None
    ) -> bool:
        """
        Gibt einen Actuator-Lock frei.

        Args:
            esp_id, gpio: Actuator-Identifikation
            rule_id: Rule die den Lock freigeben will
            zone_id: T13-R2 — Zone context for multi-zone actuators

        Returns:
            True wenn erfolgreich, False wenn Lock einer anderen Rule gehört
        """
        actuator_key = self._get_actuator_key(esp_id, gpio, zone_id)
        mutex = self._get_mutex(actuator_key)

        async with mutex:
            existing_lock = self._locks.get(actuator_key)
            if existing_lock and existing_lock.rule_id == rule_id:
                del self._locks[actuator_key]
                logger.debug(f"Actuator {actuator_key} released by rule {rule_id}")
                return True
            return False

    def has_active_lock_for_rule(
        self,
        esp_id: str,
        gpio: int,
        rule_id: str,
        command: str,
    ) -> bool:
        """
        Check if a non-expired lock exists for the given rule + actuator + command.

        Used by the LogicEngine to detect re-execution of the same command
        while the actuator is still running (e.g. duration-based ON that has not
        yet expired).  This avoids resetting the ESP32 duration timer with
        redundant MQTT publishes.

        Returns:
            True if an active lock exists for this rule+actuator with the same command.
        """
        actuator_key = self._get_actuator_key(esp_id, gpio)
        lock = self._locks.get(actuator_key)
        if lock is None:
            return False
        now = datetime.now(timezone.utc)
        if lock.expires_at and lock.expires_at < now:
            return False
        return lock.rule_id == rule_id and lock.command == command

    def get_active_conflicts(self) -> List[ConflictInfo]:
        """Returns die letzten 100 Konflikte für Debugging."""
        return self._conflict_history[-100:]

    def get_locked_actuators(self) -> Dict[str, ActuatorLock]:
        """Returns alle aktuell gelockten Actuatoren."""
        now = datetime.now(timezone.utc)
        return {
            key: lock
            for key, lock in self._locks.items()
            if lock.expires_at is None or lock.expires_at > now
        }

    def get_stats(self) -> dict:
        """Returns Statistiken für Monitoring."""
        now = datetime.now(timezone.utc)
        active_locks = sum(
            1 for lock in self._locks.values() if lock.expires_at is None or lock.expires_at > now
        )

        return {
            "active_locks": active_locks,
            "total_locks": len(self._locks),
            "total_conflicts": len(self._conflict_history),
            "recent_conflicts": len(self._conflict_history[-10:]),
        }
