"""
Zentrale Scheduler-Infrastruktur für AutomationOne.

Diese Komponente verwaltet ALLE zeitgesteuerten Jobs im System:
- Mock-ESP Simulationen (Heartbeats, Sensor-Daten)
- Maintenance Jobs (Cleanup, Reports)
- Monitoring Jobs (Timeout-Checks, Health-Checks)

NICHT für Logic Engine! Die Logic Engine ist event-driven und nutzt
MQTT-basierte Reaktionen, nicht zeitgesteuerte Jobs.

Architektur:
- Ein APScheduler für das gesamte System
- Jobs werden über Job-IDs identifiziert
- Job-Kategorien durch Prefix: "mock_", "maintenance_", "monitor_"
- Graceful Shutdown mit DB-Status-Update
"""

from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

from .logging_config import get_logger

logger = get_logger(__name__)


def parse_cron_string(cron: str) -> dict[str, str]:
    """Parse 5-field cron string to APScheduler dict.

    Args:
        cron: "minute hour day month day_of_week" (e.g., "0 3 * * *")

    Returns:
        Dict with minute, hour, day, month, day_of_week keys (only non-wildcard fields).

    Raises:
        ValueError: If cron string does not have exactly 5 fields.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: '{cron}' (expected 5 fields, got {len(parts)})")

    keys = ["minute", "hour", "day", "month", "day_of_week"]
    result: dict[str, str] = {}
    for key, value in zip(keys, parts):
        if value != "*":
            result[key] = value  # APScheduler accepts strings like "0", "3", "*/5"
    return result


class JobCategory(str, Enum):
    """Kategorien für Jobs - bestimmt Prefix der Job-ID."""

    MOCK_ESP = "mock"  # Mock-ESP Simulationen
    MAINTENANCE = "maintenance"  # Cleanup, Reports
    MONITOR = "monitor"  # Timeout-Checks, Health
    CUSTOM = "custom"  # User-definierte Jobs
    SENSOR_SCHEDULE = "sensor_schedule"  # Scheduled sensor measurements (Phase 2H)
    DAILY_ANALYSIS = "daily_analysis"  # AUT-194: 2x/day Claude stack analysis


@dataclass
class JobStats:
    """Statistiken für einen Job."""

    job_id: str
    category: JobCategory
    executions: int = 0
    errors: int = 0
    last_run: Optional[datetime] = None
    last_error: Optional[str] = None
    avg_duration_ms: float = 0.0


class CentralScheduler:
    """
    Zentraler Scheduler für alle zeitgesteuerten Operationen.

    VERWENDUNG:

    1. Initialisierung (einmal in main.py):
        scheduler = init_central_scheduler()

    2. Job hinzufügen:
        scheduler.add_interval_job(
            job_id="mock_ESP001_heartbeat",
            func=heartbeat_func,
            seconds=60,
            args=["ESP001"],
            category=JobCategory.MOCK_ESP
        )

    3. Job entfernen:
        scheduler.remove_job("mock_ESP001_heartbeat")

    4. Alle Jobs einer Kategorie entfernen:
        scheduler.remove_jobs_by_category(JobCategory.MOCK_ESP)

    5. Shutdown:
        await scheduler.shutdown()
    """

    def __init__(self):
        """Initialisiert den Scheduler (noch nicht gestartet)."""
        self._job_stats: Dict[str, JobStats] = {}
        self._is_running: bool = False

        # APScheduler Konfiguration
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {
            "coalesce": True,  # Verpasste Jobs zusammenfassen
            "max_instances": 1,  # Max 1 Instanz pro Job gleichzeitig
            "misfire_grace_time": 120,  # 120s Toleranz (Event-Loop-Blockierung bei vielen Jobs)
        }

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )

        # Event Listener für Statistiken
        self._scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)

        logger.debug("CentralScheduler initialized")

    # ================================================================
    # LIFECYCLE
    # ================================================================

    def start(self) -> None:
        """Startet den Scheduler."""
        if not self._is_running:
            self._scheduler.start()
            self._is_running = True
            logger.info("CentralScheduler started")

    async def shutdown(self, wait: bool = True, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Graceful Shutdown des Schedulers.

        Args:
            wait: Warten bis laufende Jobs fertig sind
            timeout: Maximale Wartezeit in Sekunden

        Returns:
            Shutdown-Statistiken
        """
        if not self._is_running:
            return {"status": "not_running", "jobs_removed": 0}

        logger.info("CentralScheduler shutdown initiated...")

        # Zähle Jobs vor Shutdown
        jobs_before = len(self._scheduler.get_jobs())

        # Scheduler stoppen
        self._scheduler.shutdown(wait=wait)
        self._is_running = False

        # Stats sammeln
        stats = {
            "status": "shutdown_complete",
            "jobs_removed": jobs_before,
            "job_stats": {
                job_id: {
                    "executions": stat.executions,
                    "errors": stat.errors,
                    "last_run": stat.last_run.isoformat() if stat.last_run else None,
                }
                for job_id, stat in self._job_stats.items()
            },
        }

        logger.info(f"CentralScheduler shutdown complete: {jobs_before} jobs removed")
        return stats

    @property
    def is_running(self) -> bool:
        """Gibt zurück ob Scheduler läuft."""
        return self._is_running

    # ================================================================
    # JOB MANAGEMENT
    # ================================================================

    def add_interval_job(
        self,
        job_id: str,
        func: Callable,
        seconds: float,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        category: JobCategory = JobCategory.CUSTOM,
        start_immediately: bool = True,
    ) -> bool:
        """
        Fügt einen Interval-Job hinzu.

        Args:
            job_id: Eindeutige Job-ID (wird mit Kategorie-Prefix versehen)
            func: Async oder Sync Funktion die ausgeführt wird
            seconds: Intervall in Sekunden
            args: Positionale Argumente für func
            kwargs: Keyword-Argumente für func
            category: Job-Kategorie
            start_immediately: Sofort ersten Lauf ausführen

        Returns:
            True wenn erfolgreich hinzugefügt
        """
        full_job_id = f"{category.value}_{job_id}"

        # Prüfe ob Job bereits existiert
        if self._scheduler.get_job(full_job_id):
            logger.warning(f"Job {full_job_id} already exists, skipping")
            return False

        # Job hinzufügen
        # WICHTIG: next_run_time=None paust den Job in APScheduler.
        # Für reguläre Intervall-Jobs darf das Feld daher nur gesetzt werden,
        # wenn ein Sofort-Start explizit gewünscht ist.
        add_job_kwargs: Dict[str, Any] = {
            "trigger": IntervalTrigger(seconds=seconds),
            "id": full_job_id,
            "args": args or [],
            "kwargs": kwargs or {},
            "replace_existing": True,
        }
        if start_immediately:
            add_job_kwargs["next_run_time"] = datetime.now(timezone.utc)

        self._scheduler.add_job(func, **add_job_kwargs)

        # Stats initialisieren
        self._job_stats[full_job_id] = JobStats(job_id=full_job_id, category=category)

        logger.debug(f"Added interval job: {full_job_id} (every {seconds}s)")
        return True

    def add_cron_job(
        self,
        job_id: str,
        func: Callable,
        cron_expression: Dict[str, Any],
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        category: JobCategory = JobCategory.MAINTENANCE,
    ) -> bool:
        """
        Fügt einen Cron-Job hinzu.

        Args:
            job_id: Eindeutige Job-ID
            func: Funktion die ausgeführt wird
            cron_expression: Dict mit Cron-Parametern (hour, minute, day_of_week, etc.)
            args: Positionale Argumente
            kwargs: Keyword-Argumente
            category: Job-Kategorie

        Returns:
            True wenn erfolgreich

        Beispiel:
            scheduler.add_cron_job(
                "daily_cleanup",
                cleanup_func,
                {"hour": 3, "minute": 0},  # Täglich um 3:00
                category=JobCategory.MAINTENANCE
            )
        """
        full_job_id = f"{category.value}_{job_id}"

        if self._scheduler.get_job(full_job_id):
            logger.warning(f"Job {full_job_id} already exists")
            return False

        self._scheduler.add_job(
            func,
            trigger=CronTrigger(**cron_expression),
            id=full_job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=True,
        )

        self._job_stats[full_job_id] = JobStats(job_id=full_job_id, category=category)

        logger.debug(f"Added cron job: {full_job_id}")
        return True

    def add_onetime_job(
        self,
        job_id: str,
        func: Callable,
        run_at: datetime,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        category: JobCategory = JobCategory.CUSTOM,
    ) -> bool:
        """
        Fügt einen einmaligen Job hinzu.

        Args:
            job_id: Eindeutige Job-ID
            func: Funktion die ausgeführt wird
            run_at: Zeitpunkt der Ausführung
            args: Positionale Argumente
            kwargs: Keyword-Argumente
            category: Job-Kategorie

        Returns:
            True wenn erfolgreich
        """
        full_job_id = f"{category.value}_{job_id}"

        self._scheduler.add_job(
            func,
            trigger=DateTrigger(run_date=run_at),
            id=full_job_id,
            args=args or [],
            kwargs=kwargs or {},
        )

        self._job_stats[full_job_id] = JobStats(job_id=full_job_id, category=category)

        logger.debug(f"Added onetime job: {full_job_id} at {run_at}")
        return True

    def remove_job(self, job_id: str, category: Optional[JobCategory] = None) -> bool:
        """
        Entfernt einen Job.

        Args:
            job_id: Job-ID (mit oder ohne Kategorie-Prefix)
            category: Kategorie (falls job_id ohne Prefix)

        Returns:
            True wenn erfolgreich entfernt
        """
        # Bestimme full_job_id
        if category:
            full_job_id = f"{category.value}_{job_id}"
        else:
            # Prüfe ob job_id bereits Prefix hat
            full_job_id = job_id

        job = self._scheduler.get_job(full_job_id)
        if not job:
            logger.warning(f"Job {full_job_id} not found")
            return False

        self._scheduler.remove_job(full_job_id)
        self._job_stats.pop(full_job_id, None)

        logger.debug(f"Removed job: {full_job_id}")
        return True

    def remove_jobs_by_prefix(self, prefix: str) -> int:
        """
        Entfernt alle Jobs die mit einem Prefix beginnen.

        Args:
            prefix: Job-ID Prefix (z.B. "mock_ESP001")

        Returns:
            Anzahl entfernter Jobs
        """
        removed = 0
        for job in self._scheduler.get_jobs():
            if job.id.startswith(prefix):
                self._scheduler.remove_job(job.id)
                self._job_stats.pop(job.id, None)
                removed += 1

        if removed > 0:
            logger.debug(f"Removed {removed} jobs with prefix '{prefix}'")
        return removed

    def remove_jobs_by_category(self, category: JobCategory) -> int:
        """
        Entfernt alle Jobs einer Kategorie.

        Args:
            category: Job-Kategorie

        Returns:
            Anzahl entfernter Jobs
        """
        return self.remove_jobs_by_prefix(f"{category.value}_")

    def pause_job(self, job_id: str) -> bool:
        """Pausiert einen Job."""
        job = self._scheduler.get_job(job_id)
        if job:
            self._scheduler.pause_job(job_id)
            logger.debug(f"Paused job: {job_id}")
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """Setzt einen pausierten Job fort."""
        job = self._scheduler.get_job(job_id)
        if job:
            self._scheduler.resume_job(job_id)
            logger.debug(f"Resumed job: {job_id}")
            return True
        return False

    def reschedule_job(self, job_id: str, seconds: float) -> bool:
        """
        Ändert das Intervall eines Jobs.

        Args:
            job_id: Job-ID
            seconds: Neues Intervall in Sekunden

        Returns:
            True wenn erfolgreich
        """
        job = self._scheduler.get_job(job_id)
        if not job:
            return False

        self._scheduler.reschedule_job(job_id, trigger=IntervalTrigger(seconds=seconds))
        logger.debug(f"Rescheduled job {job_id} to {seconds}s")
        return True

    # ================================================================
    # STATUS & MONITORING
    # ================================================================

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """
        Gibt alle geplanten Jobs zurück.

        Returns:
            Liste von Job-Informationen
        """
        return [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
                "pending": job.pending,
            }
            for job in self._scheduler.get_jobs()
        ]

    def get_jobs_by_category(self, category: JobCategory) -> List[Dict[str, Any]]:
        """Gibt alle Jobs einer Kategorie zurück."""
        prefix = f"{category.value}_"
        return [job for job in self.get_all_jobs() if job["id"].startswith(prefix)]

    def get_job_stats(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Gibt Statistiken für einen Job zurück."""
        stats = self._job_stats.get(job_id)
        if not stats:
            return None

        return {
            "job_id": stats.job_id,
            "category": stats.category.value,
            "executions": stats.executions,
            "errors": stats.errors,
            "last_run": stats.last_run.isoformat() if stats.last_run else None,
            "last_error": stats.last_error,
            "avg_duration_ms": stats.avg_duration_ms,
        }

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Gibt Gesamtstatus des Schedulers zurück.

        Returns:
            Status-Dictionary
        """
        jobs = self._scheduler.get_jobs()

        # Jobs nach Kategorie zählen
        category_counts = {}
        for cat in JobCategory:
            prefix = f"{cat.value}_"
            category_counts[cat.value] = len([j for j in jobs if j.id.startswith(prefix)])

        return {
            "running": self._is_running,
            "total_jobs": len(jobs),
            "jobs_by_category": category_counts,
            "total_executions": sum(s.executions for s in self._job_stats.values()),
            "total_errors": sum(s.errors for s in self._job_stats.values()),
        }

    # ================================================================
    # EVENT HANDLERS (intern)
    # ================================================================

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handler für erfolgreiche Job-Ausführung."""
        job_id = event.job_id
        if job_id in self._job_stats:
            self._job_stats[job_id].executions += 1
            self._job_stats[job_id].last_run = datetime.now(timezone.utc)

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handler für Job-Fehler."""
        job_id = event.job_id
        if job_id in self._job_stats:
            self._job_stats[job_id].errors += 1
            self._job_stats[job_id].last_error = str(event.exception)
        logger.error(f"Job {job_id} failed: {event.exception}")

    def _on_job_missed(self, event: JobExecutionEvent) -> None:
        """Handler für verpasste Jobs."""
        logger.warning(f"Job {event.job_id} missed scheduled run")


# ================================================================
# DEPENDENCY INJECTION
# ================================================================

_scheduler_instance: Optional[CentralScheduler] = None


def get_central_scheduler() -> CentralScheduler:
    """
    FastAPI Dependency für CentralScheduler.

    Verwendung:
        @router.get("/scheduler/status")
        async def get_status(
            scheduler: CentralScheduler = Depends(get_central_scheduler)
        ):
            return scheduler.get_scheduler_status()
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        raise RuntimeError("CentralScheduler not initialized. Call init_central_scheduler() first.")
    return _scheduler_instance


def init_central_scheduler() -> CentralScheduler:
    """
    Initialisiert und startet den zentralen Scheduler.

    MUSS in main.py während Startup aufgerufen werden.

    Returns:
        Initialisierte CentralScheduler-Instanz
    """
    global _scheduler_instance

    if _scheduler_instance is not None:
        logger.warning("CentralScheduler already initialized")
        return _scheduler_instance

    _scheduler_instance = CentralScheduler()
    _scheduler_instance.start()

    return _scheduler_instance


async def shutdown_central_scheduler() -> Dict[str, Any]:
    """
    Fährt den zentralen Scheduler herunter.

    MUSS in main.py während Shutdown aufgerufen werden.

    Returns:
        Shutdown-Statistiken
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        return {"status": "not_initialized"}

    result = await _scheduler_instance.shutdown()
    _scheduler_instance = None

    return result
