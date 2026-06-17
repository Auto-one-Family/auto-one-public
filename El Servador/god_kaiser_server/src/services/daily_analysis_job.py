"""
Daily Analysis Job (AUT-194).

Orchestrates the 2x/day server-stack diagnostic:
  06:00 UTC (slot='morning')
  18:00 UTC (slot='evening')

Pipeline::

    DailySnapshotService.collect()
        -> AiService.analyze_daily_snapshot() (Claude API + prompt-cache)
        -> AutoOpsReporter.generate_daily_report() (TASK-PACKAGES + SPECIALIST-PROMPTS)
        -> optional EmailService.send_email() (gated by EMAIL_DAILY_REPORT_ENABLED)

Critical invariants
-------------------
- Idempotenz: prueft (run_date, run_slot) ueber ``plugin_executions`` und
  bricht bei bereits ``status='completed'`` ohne erneuten Claude-Call ab.
- Self-Exclusion: schreibt sich selbst als ``plugin_id='daily_analysis_<slot>'``
  in ``plugin_executions`` — der DailySnapshotService filtert diese Eintraege
  konsequent heraus, damit der Snapshot nicht rekursiv wird.
- ContextVar: ``asyncio.create_task()`` verliert den ContextVar-Scope. Der Job
  wird vom Scheduler aufgerufen und reicht ``correlation_id`` daher manuell durch
  (``logger.bind`` falls strukturierte Felder noetig).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..autoops.core.reporter import AutoOpsReporter
from ..core.config import get_settings
from ..core.logging_config import get_logger
from ..db.models.plugin import PluginExecution
from .ai_service import AiService
from .daily_snapshot_service import DailySnapshotService
from .email_service import EmailService

logger = get_logger(__name__)

# Plugin-IDs used for self-exclusion and idempotency. Must match the values
# filtered out by DailySnapshotService._fetch_plugin_executions.
_PLUGIN_ID_PREFIX = "daily_analysis"

# Default analysis window: 12h covers the gap between morning + evening slots.
_DEFAULT_PERIOD_HOURS = 12


class DailyAnalysisJob:
    """
    Encapsulates a single execution of the daily-analysis pipeline.

    Designed to be wired into ``CentralScheduler.add_cron_job`` once on startup;
    each invocation creates a fresh DB session via the injected ``session_factory``
    so that the job is safe to run concurrently with the rest of the server
    (no shared state, no leaked sessions on error).
    """

    def __init__(
        self,
        snapshot_service: DailySnapshotService,
        ai_service: AiService,
        reporter: AutoOpsReporter,
        email_service: EmailService,
        session_factory: Callable,
        period_hours: int = _DEFAULT_PERIOD_HOURS,
    ) -> None:
        """
        Args:
            snapshot_service: aggregates DB telemetry into SystemAnalysisRequest
            ai_service: Claude wrapper (uses prompt caching from analyze_error)
            reporter: writes the TASK-PACKAGES + SPECIALIST-PROMPTS markdown
            email_service: optional mail delivery (feature-flag gated)
            session_factory: zero-arg async generator yielding AsyncSession
                             (typically ``db.session.get_session``)
            period_hours: aggregation window (default 12h)
        """
        self._snapshot_service = snapshot_service
        self._ai_service = ai_service
        self._reporter = reporter
        self._email_service = email_service
        self._session_factory = session_factory
        self._period_hours = period_hours

    # ------------------------------------------------------------------
    # Scheduler entry point
    # ------------------------------------------------------------------

    async def run(self, slot: str = "morning") -> None:
        """
        Execute the full pipeline for the given slot.

        Args:
            slot: 'morning' or 'evening'
        """
        if slot not in ("morning", "evening"):
            raise ValueError(f"slot must be 'morning' or 'evening', got: {slot!r}")

        run_date = datetime.now(timezone.utc)
        plugin_id = f"{_PLUGIN_ID_PREFIX}_{slot}"
        execution_id = uuid.uuid4()

        logger.info(
            "DailyAnalysisJob.run starting (slot=%s, run_date=%s, execution_id=%s)",
            slot,
            run_date.isoformat(),
            execution_id,
        )

        # Step 1: Idempotenz-Guard — skip if completed run exists for this slot today
        async for session in self._session_factory():
            try:
                already_done = await DailySnapshotService.has_completed_run(
                    session=session,
                    run_date=run_date,
                    run_slot=slot,
                )
                if already_done:
                    logger.info(
                        "DailyAnalysisJob: idempotency guard hit, skipping (slot=%s, date=%s)",
                        slot,
                        run_date.date().isoformat(),
                    )
                    return
            finally:
                pass
            break

        # Step 2: Pipeline — own session for the heavy lifting
        async for session in self._session_factory():
            execution_row: Optional[PluginExecution] = None
            try:
                # Record running execution (for idempotency + audit trail).
                execution_row = PluginExecution(
                    id=execution_id,
                    plugin_id=plugin_id,
                    started_at=run_date,
                    status="running",
                    triggered_by="scheduler",
                )
                session.add(execution_row)
                await session.commit()

                # 2a) collect snapshot
                request = await self._snapshot_service.collect(
                    db_session=session,
                    period_hours=self._period_hours,
                )

                # 2b) Claude analysis (reuses cached system prompt)
                if not self._ai_service.is_available():
                    logger.warning(
                        "DailyAnalysisJob: AiService unavailable (no ANTHROPIC_API_KEY) — "
                        "writing empty findings report"
                    )
                    findings = []
                else:
                    findings = await self._ai_service.analyze_daily_snapshot(request)

                # 2c) report
                report_path = self._reporter.generate_daily_report(
                    run_date=run_date,
                    run_slot=slot,
                    findings=findings,
                    period_hours=self._period_hours,
                )

                # 2d) optional email (feature-flag gated)
                await self._maybe_send_email(
                    slot=slot,
                    run_date=run_date,
                    findings_count=len(findings),
                    report_path=report_path,
                )

                # 2e) finalize execution row
                finished_at = datetime.now(timezone.utc)
                duration_seconds = (finished_at - run_date).total_seconds()
                execution_row.finished_at = finished_at
                execution_row.duration_seconds = duration_seconds
                execution_row.status = "completed"
                execution_row.result = {
                    "slot": slot,
                    "findings_count": len(findings),
                    "report_path": report_path,
                    "period_hours": self._period_hours,
                }
                await session.commit()

                logger.info(
                    "DailyAnalysisJob.run completed (slot=%s, findings=%d, report=%s)",
                    slot,
                    len(findings),
                    report_path,
                )
            except Exception as exc:
                logger.error(
                    "DailyAnalysisJob.run FAILED (slot=%s): %s",
                    slot,
                    exc,
                    exc_info=True,
                )
                if execution_row is not None:
                    try:
                        execution_row.finished_at = datetime.now(timezone.utc)
                        execution_row.status = "failed"
                        execution_row.error_message = str(exc)
                        await session.commit()
                    except Exception:
                        await session.rollback()
            break  # exit the async-generator after first session

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _maybe_send_email(
        self,
        slot: str,
        run_date: datetime,
        findings_count: int,
        report_path: str,
    ) -> None:
        """Send the report via email if the feature flag is on AND a recipient is set."""
        settings = get_settings()
        notif = settings.notification
        if not notif.email_daily_report_enabled:
            logger.debug(
                "DailyAnalysisJob: email delivery disabled (EMAIL_DAILY_REPORT_ENABLED=False)"
            )
            return
        if not notif.email_daily_report_recipient:
            logger.warning(
                "DailyAnalysisJob: EMAIL_DAILY_REPORT_ENABLED=True but no recipient configured — "
                "set EMAIL_DAILY_REPORT_RECIPIENT to enable delivery"
            )
            return

        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            logger.warning("DailyAnalysisJob: cannot read report file %s: %s", report_path, exc)
            return

        date_str = run_date.strftime("%Y-%m-%d")
        subject = f"[AutomationOne] Daily Stack Report {date_str} ({slot}, {findings_count} findings)"
        await self._email_service.send_email(
            to=notif.email_daily_report_recipient,
            subject=subject,
            text_body=body,
        )
