"""
Sequence Action Executor

Führt verkettete Aktionen mit Delays aus.

FEATURES:
- Non-blocking via asyncio.create_task()
- Vollständiges Progress-Tracking
- Cancel-Support
- Timeout-Handling pro Step und gesamt
- WebSocket-Broadcasts für Live-Updates
- Retry-Logik für fehlgeschlagene Steps
- Circular-Dependency-Handling via set_action_executors()

LIMITS:
- MAX_CONCURRENT_SEQUENCES = 20
- MAX_STEPS_PER_SEQUENCE = 50
- MAX_SEQUENCE_DURATION_SECONDS = 3600 (1 Stunde)
- PROGRESS_RETENTION_SECONDS = 3600 (1 Stunde nach Completion)

PATTERN: Folgt BaseActionExecutor (siehe actuator_executor.py)

Phase: 3 - Sequence Action Executor
Status: IMPLEMENTED
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ....core.error_codes import SequenceErrorCode
from ....core.logging_config import get_logger
from .base import ActionResult, BaseActionExecutor

logger = get_logger(__name__)


class SequenceStatus(str, Enum):
    """Status einer Sequenz."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class StepResult:
    """Ergebnis eines ausgeführten Steps."""

    step_index: int
    step_name: Optional[str]
    success: bool
    message: str
    error_code: Optional[int] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    retries: int = 0

    def complete(self, success: bool, message: str, error_code: Optional[int] = None):
        """Markiert Step als abgeschlossen."""
        self.completed_at = datetime.now(timezone.utc)
        self.success = success
        self.message = message
        self.error_code = error_code
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)


@dataclass
class SequenceProgress:
    """Vollständiger Fortschritt einer Sequenz."""

    sequence_id: str
    rule_id: str
    rule_name: Optional[str]
    description: Optional[str]
    total_steps: int
    abort_on_failure: bool
    max_duration_seconds: int

    # Runtime State
    status: SequenceStatus = SequenceStatus.PENDING
    current_step: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    step_results: List[StepResult] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[int] = None

    # Metadata
    triggered_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_running(self) -> bool:
        """Prüft ob Sequenz läuft."""
        return self.status == SequenceStatus.RUNNING

    @property
    def is_terminal(self) -> bool:
        """Prüft ob Sequenz beendet ist."""
        return self.status in (
            SequenceStatus.COMPLETED,
            SequenceStatus.FAILED,
            SequenceStatus.CANCELLED,
            SequenceStatus.TIMEOUT,
        )

    @property
    def progress_percent(self) -> float:
        """Berechnet Fortschritt in Prozent."""
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100

    @property
    def current_step_name(self) -> Optional[str]:
        """Gibt Namen des aktuellen Steps zurück."""
        if self.step_results and len(self.step_results) > self.current_step:
            return self.step_results[self.current_step].step_name
        return None

    @property
    def duration_seconds(self) -> float:
        """Berechnet Dauer der Sequenz."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für API/WebSocket."""
        return {
            "sequence_id": self.sequence_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "description": self.description,
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "progress_percent": self.progress_percent,
            "current_step_name": self.current_step_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "duration_seconds": self.duration_seconds,
            "step_results": [
                {
                    "step_index": r.step_index,
                    "step_name": r.step_name,
                    "success": r.success,
                    "message": r.message,
                    "error_code": r.error_code,
                    "duration_ms": r.duration_ms,
                    "retries": r.retries,
                }
                for r in self.step_results
            ],
            "error": self.error,
            "error_code": self.error_code,
        }


class SequenceActionExecutor(BaseActionExecutor):
    """
    Executor für Sequenz-Actions.

    Führt verkettete Aktionen mit Delays, Timeouts und Error-Handling aus.

    WICHTIG:
    - Circular-Dependency: Nutze set_action_executors() NACH Initialisierung
    - Non-blocking: execute() gibt sofort ActionResult zurück
    - Background-Tasks: _run_sequence() läuft als asyncio.Task
    """

    # Limits
    MAX_CONCURRENT_SEQUENCES = 20
    MAX_STEPS_PER_SEQUENCE = 50
    MAX_SEQUENCE_DURATION_SECONDS = 3600
    DEFAULT_STEP_TIMEOUT_SECONDS = 30
    PROGRESS_RETENTION_SECONDS = 3600
    CLEANUP_INTERVAL_SECONDS = 300

    def __init__(
        self,
        websocket_manager=None,
        action_executors: Optional[List[BaseActionExecutor]] = None,
    ):
        """
        Initialisiert Sequence Executor.

        Args:
            websocket_manager: Für Live-Updates ans Frontend
            action_executors: Liste der Sub-Executors (wird später via set_action_executors gesetzt)
        """
        self._action_executors: Dict[str, BaseActionExecutor] = {}
        self._websocket_manager = websocket_manager

        # Runtime State
        self._sequences: Dict[str, SequenceProgress] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # Cleanup Task
        self._cleanup_task: Optional[asyncio.Task] = None

        if action_executors:
            self.set_action_executors(action_executors)

        logger.info("SequenceActionExecutor initialized")

    def supports(self, action_type: str) -> bool:
        """Gibt True für 'sequence' Actions zurück."""
        return action_type == "sequence"

    def set_action_executors(self, executors: List[BaseActionExecutor]) -> None:
        """
        Setzt Action-Executors NACH Initialisierung.

        Löst Circular-Dependency:
        1. SequenceExecutor wird erstellt (ohne action_executors)
        2. Alle Executors werden in Liste gepackt
        3. set_action_executors(executors) wird aufgerufen

        Args:
            executors: Liste aller Action-Executors
        """
        self._action_executors = {}
        for executor in executors:
            if executor is self:
                continue  # Keine Self-Reference (verhindert Rekursion)

            # Ermittle unterstützte Types
            for action_type in self._get_supported_types(executor):
                self._action_executors[action_type] = executor

        logger.info(
            f"SequenceExecutor: Registered {len(self._action_executors)} action types: "
            f"{list(self._action_executors.keys())}"
        )

    def _get_supported_types(self, executor: BaseActionExecutor) -> List[str]:
        """Ermittelt unterstützte Action-Types eines Executors."""
        # Bekannte Types die wir prüfen
        known_types = [
            "actuator_command",
            "actuator",
            "delay",
            "notification",
            "sequence",  # Für verschachtelte Sequenzen (limitiert)
        ]
        return [t for t in known_types if executor.supports(t)]

    async def execute(self, action: dict, context: dict) -> ActionResult:
        """
        Startet eine Sequenz (non-blocking).

        Validiert die Sequenz-Definition, erstellt Progress-Tracking,
        und startet einen Background-Task für die Ausführung.

        Args:
            action: Sequenz-Definition mit steps
            context: Enthält rule_id, rule_name, trigger_data

        Returns:
            ActionResult mit sequence_id (Sequenz läuft im Background)
        """
        # 1. Validierung
        validation_error = self._validate_sequence(action)
        if validation_error:
            return validation_error

        # 2. Concurrent-Limit prüfen
        async with self._lock:
            running_count = sum(1 for s in self._sequences.values() if s.is_running)
            if running_count >= self.MAX_CONCURRENT_SEQUENCES:
                logger.warning(f"Max concurrent sequences reached: {running_count}")
                return ActionResult(
                    success=False,
                    message=f"Maximum concurrent sequences ({self.MAX_CONCURRENT_SEQUENCES}) reached",
                    data={"error_code": SequenceErrorCode.SEQ_ALREADY_RUNNING},
                )

        # 3. Sequence-ID und Progress erstellen
        rule_id = str(context.get("rule_id", "unknown"))
        rule_name = context.get("rule_name")
        steps = action.get("steps", [])

        sequence_id = (
            action.get("sequence_id")
            or f"seq-{rule_id}-{datetime.now(timezone.utc).timestamp():.0f}"
        )

        # Prüfe ob Sequence-ID bereits läuft
        if sequence_id in self._sequences and self._sequences[sequence_id].is_running:
            logger.warning(f"Sequence {sequence_id} already running")
            return ActionResult(
                success=False,
                message=f"Sequence '{sequence_id}' is already running",
                data={"error_code": SequenceErrorCode.SEQ_ALREADY_RUNNING},
            )

        progress = SequenceProgress(
            sequence_id=sequence_id,
            rule_id=rule_id,
            rule_name=rule_name,
            description=action.get("description"),
            total_steps=len(steps),
            abort_on_failure=action.get("abort_on_failure", True),
            max_duration_seconds=min(
                action.get("max_duration_seconds", self.MAX_SEQUENCE_DURATION_SECONDS),
                self.MAX_SEQUENCE_DURATION_SECONDS,
            ),
            triggered_by=context.get("triggered_by", "logic_engine"),
            metadata={
                "trigger_data": context.get("sensor_data", {}),
                "started_by": context.get("issued_by", "system"),
            },
        )

        # 4. Speichern
        async with self._lock:
            self._sequences[sequence_id] = progress

        # 5. Background-Task starten
        try:
            task = asyncio.create_task(self._run_sequence(sequence_id, steps, context))
            self._tasks[sequence_id] = task

            # Cleanup-Task starten falls noch nicht läuft
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            logger.info(
                f"Sequence started: {sequence_id} ({len(steps)} steps) "
                f"for rule {rule_name or rule_id}"
            )

            # WebSocket: Sequence Started
            await self._broadcast_event(
                "sequence_started",
                {
                    "sequence_id": sequence_id,
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "total_steps": len(steps),
                    "description": progress.description,
                },
            )

            return ActionResult(
                success=True,
                message=f"Sequence '{sequence_id}' started with {len(steps)} steps",
                data={
                    "sequence_id": sequence_id,
                    "total_steps": len(steps),
                    "status": "running",
                },
            )

        except Exception as e:
            logger.error(f"Failed to create sequence task: {e}", exc_info=True)
            progress.status = SequenceStatus.FAILED
            progress.error = str(e)
            progress.error_code = SequenceErrorCode.SEQ_TASK_CREATION_FAILED

            return ActionResult(
                success=False,
                message=f"Failed to create sequence task: {str(e)}",
                data={"error_code": SequenceErrorCode.SEQ_TASK_CREATION_FAILED},
            )

    def _validate_sequence(self, action: dict) -> Optional[ActionResult]:
        """
        Validiert Sequenz-Definition.

        Returns:
            ActionResult bei Fehler, None wenn gültig
        """
        steps = action.get("steps", [])

        # Keine Steps
        if not steps:
            return ActionResult(
                success=False,
                message="Sequence must have at least one step",
                data={"error_code": SequenceErrorCode.SEQ_EMPTY_STEPS},
            )

        # Zu viele Steps
        if len(steps) > self.MAX_STEPS_PER_SEQUENCE:
            return ActionResult(
                success=False,
                message=f"Too many steps ({len(steps)}), max is {self.MAX_STEPS_PER_SEQUENCE}",
                data={"error_code": SequenceErrorCode.SEQ_TOO_MANY_STEPS},
            )

        # Jeden Step validieren
        for i, step in enumerate(steps):
            has_action = "action" in step
            has_delay = "delay_seconds" in step

            if not has_action and not has_delay:
                return ActionResult(
                    success=False,
                    message=f"Step {i}: requires either 'action' or 'delay_seconds'",
                    data={
                        "error_code": SequenceErrorCode.SEQ_STEP_MISSING_ACTION,
                        "step": i,
                    },
                )

            # Action-Type prüfen wenn vorhanden
            if has_action:
                action_type = step["action"].get("type")
                if action_type == "sequence":
                    # Verschachtelte Sequenzen haben Tiefenlimit (hier: nicht erlaubt)
                    return ActionResult(
                        success=False,
                        message=f"Step {i}: Nested sequences not allowed",
                        data={
                            "error_code": SequenceErrorCode.SEQ_CIRCULAR_REFERENCE,
                            "step": i,
                        },
                    )

                if action_type and action_type not in self._action_executors:
                    return ActionResult(
                        success=False,
                        message=f"Step {i}: Unknown action type '{action_type}'",
                        data={
                            "error_code": SequenceErrorCode.SEQ_INVALID_ACTION_TYPE,
                            "step": i,
                        },
                    )

            # Delay-Werte validieren
            for delay_key in [
                "delay_seconds",
                "delay_before_seconds",
                "delay_after_seconds",
            ]:
                delay = step.get(delay_key)
                if delay is not None:
                    if not isinstance(delay, (int, float)) or delay < 0 or delay > 3600:
                        return ActionResult(
                            success=False,
                            message=f"Step {i}: {delay_key} must be 0-3600 seconds",
                            data={
                                "error_code": SequenceErrorCode.SEQ_INVALID_DELAY,
                                "step": i,
                            },
                        )

        return None

    async def _run_sequence(self, sequence_id: str, steps: List[dict], context: dict) -> None:
        """
        Führt Sequenz aus (Background-Task).

        Args:
            sequence_id: ID der Sequenz
            steps: Liste der Steps
            context: Execution-Context
        """
        progress = self._sequences.get(sequence_id)
        if not progress:
            logger.error(f"Sequence {sequence_id} not found in progress tracking")
            return

        progress.status = SequenceStatus.RUNNING
        progress.started_at = datetime.now(timezone.utc)

        try:
            # Timeout für gesamte Sequenz
            async with asyncio.timeout(progress.max_duration_seconds):
                for i, step_def in enumerate(steps):
                    # Abbruch prüfen
                    if progress.status == SequenceStatus.CANCELLED:
                        logger.info(f"Sequence {sequence_id} was cancelled at step {i}")
                        break

                    progress.current_step = i
                    step_name = step_def.get("name", f"Step {i+1}")

                    # Step-Result erstellen
                    step_result = StepResult(
                        step_index=i, step_name=step_name, success=False, message="Pending"
                    )
                    progress.step_results.append(step_result)

                    # WebSocket: Step Starting
                    await self._broadcast_event(
                        "sequence_step",
                        {
                            "sequence_id": sequence_id,
                            "step": i,
                            "step_name": step_name,
                            "total_steps": progress.total_steps,
                            "progress_percent": progress.progress_percent,
                            "status": "starting",
                        },
                    )

                    try:
                        # Pre-Delay
                        delay_before = step_def.get("delay_before_seconds", 0)
                        if delay_before > 0:
                            await asyncio.sleep(delay_before)

                        # Step ausführen (Action oder reiner Delay)
                        if "delay_seconds" in step_def and "action" not in step_def:
                            # Reiner Delay-Step
                            await asyncio.sleep(step_def["delay_seconds"])
                            step_result.complete(
                                True, f"Delay {step_def['delay_seconds']}s completed"
                            )
                        else:
                            # Action ausführen mit Timeout und Retry
                            action = step_def.get("action", {})
                            timeout = step_def.get(
                                "timeout_seconds", self.DEFAULT_STEP_TIMEOUT_SECONDS
                            )
                            retry_count = step_def.get("retry_count", 0)
                            retry_delay = step_def.get("retry_delay_seconds", 1.0)

                            success = False
                            last_error = None

                            for attempt in range(retry_count + 1):
                                try:
                                    async with asyncio.timeout(timeout):
                                        result = await self._execute_sub_action(action, context)

                                    if result.success:
                                        success = True
                                        step_result.complete(True, result.message)
                                        step_result.retries = attempt
                                        break
                                    else:
                                        last_error = result.message

                                except asyncio.TimeoutError:
                                    last_error = f"Step timeout after {timeout}s"
                                    logger.warning(f"Step {i} timeout (attempt {attempt+1})")

                                # Retry-Delay (außer beim letzten Versuch)
                                if attempt < retry_count:
                                    step_result.retries = attempt + 1
                                    await asyncio.sleep(retry_delay)

                            if not success:
                                step_result.complete(
                                    False,
                                    last_error or "Unknown error",
                                    SequenceErrorCode.SEQ_STEP_FAILED,
                                )

                        # Post-Delay
                        delay_after = step_def.get("delay_after_seconds", 0)
                        if delay_after > 0:
                            await asyncio.sleep(delay_after)

                        # WebSocket: Step Completed
                        await self._broadcast_event(
                            "sequence_step",
                            {
                                "sequence_id": sequence_id,
                                "step": i,
                                "step_name": step_name,
                                "success": step_result.success,
                                "message": step_result.message,
                                "duration_ms": step_result.duration_ms,
                                "progress_percent": progress.progress_percent,
                                "status": "completed" if step_result.success else "failed",
                            },
                        )

                        # Bei Fehler und abort_on_failure: Abbrechen
                        if not step_result.success:
                            on_failure = step_def.get("on_failure", "abort")
                            if on_failure == "abort" or progress.abort_on_failure:
                                progress.status = SequenceStatus.FAILED
                                progress.error = step_result.message
                                progress.error_code = step_result.error_code
                                logger.warning(
                                    f"Sequence {sequence_id} aborted at step {i}: {step_result.message}"
                                )
                                break

                    except asyncio.CancelledError:
                        step_result.complete(False, "Cancelled", SequenceErrorCode.SEQ_CANCELLED)
                        progress.status = SequenceStatus.CANCELLED
                        raise

                    except Exception as e:
                        logger.error(f"Step {i} error: {e}", exc_info=True)
                        step_result.complete(False, str(e), SequenceErrorCode.SEQ_INTERNAL_ERROR)

                        if progress.abort_on_failure:
                            progress.status = SequenceStatus.FAILED
                            progress.error = str(e)
                            progress.error_code = SequenceErrorCode.SEQ_INTERNAL_ERROR
                            break

                # Sequenz abgeschlossen
                if progress.status == SequenceStatus.RUNNING:
                    progress.status = SequenceStatus.COMPLETED
                    logger.info(
                        f"Sequence {sequence_id} completed successfully "
                        f"({progress.total_steps} steps, {progress.duration_seconds:.1f}s)"
                    )

        except asyncio.TimeoutError:
            progress.status = SequenceStatus.TIMEOUT
            progress.error = f"Sequence exceeded max duration ({progress.max_duration_seconds}s)"
            progress.error_code = SequenceErrorCode.SEQ_MAX_DURATION_EXCEEDED
            logger.warning(f"Sequence {sequence_id} timed out")

            await self._broadcast_event(
                "sequence_error",
                {
                    "sequence_id": sequence_id,
                    "error_code": SequenceErrorCode.SEQ_MAX_DURATION_EXCEEDED,
                    "message": progress.error,
                },
            )

        except asyncio.CancelledError:
            if progress.status != SequenceStatus.CANCELLED:
                progress.status = SequenceStatus.CANCELLED
            progress.error = "Sequence cancelled"
            progress.error_code = SequenceErrorCode.SEQ_CANCELLED
            logger.info(f"Sequence {sequence_id} cancelled")

            await self._broadcast_event(
                "sequence_cancelled",
                {"sequence_id": sequence_id, "reason": "User cancelled"},
            )

        except Exception as e:
            progress.status = SequenceStatus.FAILED
            progress.error = str(e)
            progress.error_code = SequenceErrorCode.SEQ_INTERNAL_ERROR
            logger.error(f"Sequence {sequence_id} failed: {e}", exc_info=True)

            await self._broadcast_event(
                "sequence_error",
                {
                    "sequence_id": sequence_id,
                    "error_code": SequenceErrorCode.SEQ_INTERNAL_ERROR,
                    "message": str(e),
                },
            )

        finally:
            progress.completed_at = datetime.now(timezone.utc)

            # WebSocket: Sequence Completed/Failed
            await self._broadcast_event(
                "sequence_completed",
                {
                    "sequence_id": sequence_id,
                    "status": progress.status.value,
                    "success": progress.status == SequenceStatus.COMPLETED,
                    "duration_seconds": progress.duration_seconds,
                    "steps_completed": len([r for r in progress.step_results if r.success]),
                    "steps_failed": len([r for r in progress.step_results if not r.success]),
                    "error": progress.error,
                    "error_code": progress.error_code,
                },
            )

            # Task-Referenz entfernen
            if sequence_id in self._tasks:
                del self._tasks[sequence_id]

    async def _execute_sub_action(self, action: dict, context: dict) -> ActionResult:
        """
        Führt Sub-Action via registrierten Executor aus.

        Args:
            action: Action-Definition
            context: Execution-Context

        Returns:
            ActionResult vom Sub-Executor
        """
        action_type = action.get("type", "")

        executor = self._action_executors.get(action_type)
        if not executor:
            logger.error(f"No executor for action type: {action_type}")
            return ActionResult(
                success=False,
                message=f"No executor for action type: {action_type}",
                data={"error_code": SequenceErrorCode.SEQ_EXECUTOR_NOT_FOUND},
            )

        try:
            result = await executor.execute(action, context)
            return result
        except Exception as e:
            logger.error(f"Sub-action execution failed: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=str(e),
                data={"error_code": SequenceErrorCode.SEQ_STEP_FAILED},
            )

    async def cancel_sequence(self, sequence_id: str, reason: str = "User cancelled") -> bool:
        """
        Bricht laufende Sequenz ab.

        Args:
            sequence_id: ID der Sequenz
            reason: Abbruchgrund

        Returns:
            True wenn erfolgreich abgebrochen
        """
        progress = self._sequences.get(sequence_id)
        if not progress:
            logger.warning(f"Cannot cancel: Sequence {sequence_id} not found")
            return False

        if not progress.is_running:
            logger.warning(
                f"Cannot cancel: Sequence {sequence_id} not running (status: {progress.status})"
            )
            return False

        # Status setzen
        progress.status = SequenceStatus.CANCELLED
        progress.error = reason
        progress.error_code = SequenceErrorCode.SEQ_CANCELLED

        # Task abbrechen
        task = self._tasks.get(sequence_id)
        if task and not task.done():
            task.cancel()
            logger.info(f"Sequence {sequence_id} cancelled: {reason}")
            return True

        return False

    def get_sequence_status(self, sequence_id: str) -> Optional[Dict[str, Any]]:
        """
        Gibt Status einer Sequenz zurück.

        Args:
            sequence_id: ID der Sequenz

        Returns:
            Status-Dictionary oder None
        """
        progress = self._sequences.get(sequence_id)
        if not progress:
            return None
        return progress.to_dict()

    def get_all_sequences(
        self, running_only: bool = False, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Gibt alle Sequenzen zurück.

        Args:
            running_only: Nur laufende Sequenzen
            limit: Maximale Anzahl

        Returns:
            Liste von Status-Dictionaries
        """
        sequences = list(self._sequences.values())

        if running_only:
            sequences = [s for s in sequences if s.is_running]

        # Nach started_at sortieren (neueste zuerst)
        sequences.sort(
            key=lambda s: s.started_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        return [s.to_dict() for s in sequences[:limit]]

    def get_running_sequences(self) -> List[SequenceProgress]:
        """Gibt laufende Sequenzen zurück (für Monitoring)."""
        return [s for s in self._sequences.values() if s.is_running]

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        all_sequences = list(self._sequences.values())
        running = [s for s in all_sequences if s.is_running]

        # Letzte Stunde
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = [s for s in all_sequences if s.completed_at and s.completed_at >= one_hour_ago]
        completed = [s for s in recent if s.status == SequenceStatus.COMPLETED]
        failed = [s for s in recent if s.status in (SequenceStatus.FAILED, SequenceStatus.TIMEOUT)]

        # Durchschnittliche Dauer
        durations = [s.duration_seconds for s in completed if s.duration_seconds > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_sequences": len(all_sequences),
            "running": len(running),
            "completed_last_hour": len(completed),
            "failed_last_hour": len(failed),
            "average_duration_seconds": round(avg_duration, 2),
        }

    async def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Sendet WebSocket-Event ans Frontend."""
        if not self._websocket_manager:
            return

        try:
            await self._websocket_manager.broadcast(event_type, data)
        except Exception as e:
            logger.warning(f"Failed to broadcast {event_type}: {e}")

    async def _cleanup_loop(self) -> None:
        """Background-Task für Cleanup abgeschlossener Sequenzen."""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_old_sequences()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}", exc_info=True)

    async def _cleanup_old_sequences(self) -> None:
        """Entfernt alte abgeschlossene Sequenzen aus dem Speicher."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.PROGRESS_RETENTION_SECONDS)

        to_remove = []
        async with self._lock:
            for seq_id, progress in self._sequences.items():
                if progress.is_terminal and progress.completed_at:
                    completed_at = progress.completed_at
                    # Make timezone-aware if naive (assume UTC)
                    if completed_at.tzinfo is None:
                        completed_at = completed_at.replace(tzinfo=timezone.utc)
                    if completed_at < cutoff:
                        to_remove.append(seq_id)

            for seq_id in to_remove:
                del self._sequences[seq_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old sequences")

    async def shutdown(self) -> None:
        """
        Graceful shutdown für Cleanup-Task.

        Muss in main.py Shutdown aufgerufen werden.
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("SequenceActionExecutor shutdown complete")
