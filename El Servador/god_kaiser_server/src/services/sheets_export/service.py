"""
SheetsExportService — orchestrator for the Sheets export pipeline.

This is the S2 (AUT-444) skeleton service plus the integration glue for
S4 (sensor batcher), S5 (actuator batcher), S6 (tab rotation), and S7
(retry/backoff).

Public surface (matches the verbindlicher Vertrag from the
Verify-Plan-Gate on AUT-444):

- ``export_sensors(*, limit=None, dry_run=False) -> ExportBatchResult``
- ``export_actor_history(*, limit=None, dry_run=False,
    correlation_window_seconds=120) -> ExportBatchResult``

Both methods are idempotent relative to their cursors; the cursor only
moves after a successful Sheets write. A failure in one path does not
advance the other's cursor.

The service registers ONE interval job with the CentralScheduler that
calls both methods in sequence. The job is only registered when
``SHEETS_EXPORT_ENABLED=true`` AND ``SHEETS_SPREADSHEET_ID`` is set —
keeping the default deployment a no-op.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ...core.config import SheetsExportSettings, get_settings
from ...core.error_codes import ConfigErrorCode
from ...core.logging_config import get_logger
from ...core.scheduler import CentralScheduler, JobCategory
from .actuator_batcher import (
    ACTUATOR_HEADER,
    ActuatorBatch,
    ActuatorRunRow,
    ActuatorExportBatcher,
)
from .batch_result import ExportBatchResult, ExportStatus
from .client import SheetsClient
from .cursor import SheetsExportCursor
from .exceptions import NonRetryableSheetsError, RetryableSheetsError
from .sensor_batcher import (
    SENSOR_HEADER,
    SensorBatch,
    SensorRow,
    SensorExportBatcher,
)
from .tab_rotation import TabRotationManager

logger = get_logger(__name__)


SessionFactory = Callable[..., Any]


JOB_ID = "sheets_export_tick"


class SheetsExportService:
    """
    Standalone service (per E2 fix on AUT-442) that periodically
    publishes new sensor and actuator data to a shared Google Sheet.
    """

    def __init__(
        self,
        scheduler: CentralScheduler,
        session_factory: SessionFactory,
        *,
        settings: Optional[SheetsExportSettings] = None,
        client: Optional[SheetsClient] = None,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._settings: SheetsExportSettings = (
            settings or get_settings().sheets_export
        )
        self._client = client or SheetsClient(self._settings)
        self._job_results: Dict[str, Any] = {
            "last_sensor_run": None,
            "last_history_run": None,
        }
        self._lock = asyncio.Lock()

    # --- lifecycle ----------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.enabled and self._settings.spreadsheet_id)

    def start(self) -> bool:
        """Register the interval job. Returns True on actual registration."""
        if not self.is_enabled:
            logger.info(
                "[sheets_export] Service start skipped — feature disabled "
                "(SHEETS_EXPORT_ENABLED=%s, spreadsheet_configured=%s)",
                self._settings.enabled,
                bool(self._settings.spreadsheet_id),
            )
            return False

        ok = self._scheduler.add_interval_job(
            job_id=JOB_ID,
            func=self._run_tick,
            seconds=max(60, self._settings.export_interval_minutes * 60),
            category=JobCategory.MAINTENANCE,
            start_immediately=True,
        )
        if ok:
            logger.info(
                "[sheets_export] Interval job registered (every %d min)",
                self._settings.export_interval_minutes,
            )
        return ok

    def stop(self) -> int:
        """Remove the interval job. Returns 1 if removed, 0 otherwise."""
        removed = self._scheduler.remove_jobs_by_prefix(
            f"{JobCategory.MAINTENANCE.value}_{JOB_ID}"
        )
        if removed:
            logger.info("[sheets_export] Interval job removed (%d jobs)", removed)
        return removed

    def get_status(self) -> Dict[str, Any]:
        """Return a JSON-serialisable status snapshot for admin endpoints."""
        return {
            "enabled": self.is_enabled,
            "interval_minutes": self._settings.export_interval_minutes,
            "spreadsheet_id_configured": bool(self._settings.spreadsheet_id),
            "tab_granularity": self._settings.tab_granularity,
            "last_runs": self._job_results,
        }

    # --- scheduler entry-point ---------------------------------------------

    async def _run_tick(self) -> None:
        """Periodic tick — runs sensor + actuator export back-to-back."""
        if not self.is_enabled:
            return
        async with self._lock:
            sensor_result = await self.export_sensors()
            self._job_results["last_sensor_run"] = sensor_result.to_log_extra()

            actuator_result = await self.export_actor_history(
                correlation_window_seconds=self._settings.correlation_window_seconds,
            )
            self._job_results["last_history_run"] = actuator_result.to_log_extra()

    # --- public contract ----------------------------------------------------

    async def export_sensors(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> ExportBatchResult:
        """
        Export the next batch of sensor measurements.

        Returns:
            ``ExportBatchResult`` (see :mod:`.batch_result`).
        """
        if not self.is_enabled:
            return ExportBatchResult(
                path="sensor",
                status=ExportStatus.SKIPPED_DISABLED,
            )
        batch_limit = limit or self._settings.sensor_batch_size
        return await self._run_path(
            path="sensor",
            batch_limit=batch_limit,
            dry_run=dry_run,
            runner=self._run_sensor_path,
        )

    async def export_actor_history(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = False,
        correlation_window_seconds: Optional[int] = None,
    ) -> ExportBatchResult:
        """
        Export the next batch of actuator history (paired ON/OFF runs).
        """
        if not self.is_enabled:
            return ExportBatchResult(
                path="actuator",
                status=ExportStatus.SKIPPED_DISABLED,
            )
        batch_limit = limit or self._settings.history_batch_size
        window = correlation_window_seconds or self._settings.correlation_window_seconds
        return await self._run_path(
            path="actuator",
            batch_limit=batch_limit,
            dry_run=dry_run,
            runner=lambda session, cursor, tab_mgr: self._run_actuator_path(
                session, cursor, tab_mgr, window_seconds=window
            ),
        )

    # --- private path orchestration ----------------------------------------

    async def _run_path(
        self,
        *,
        path: str,
        batch_limit: int,
        dry_run: bool,
        runner: Callable[
            [Any, SheetsExportCursor, TabRotationManager],
            Awaitable[ExportBatchResult],
        ],
    ) -> ExportBatchResult:
        start = time.monotonic()
        result: ExportBatchResult
        try:
            async for session in self._session_factory():
                cursor = SheetsExportCursor(session)
                tab_mgr = self._get_tab_manager(cursor)
                result = await runner(session, cursor, tab_mgr)
                if dry_run:
                    result.status = ExportStatus.DRY_RUN
                    # Roll back any incidental writes — cursor stays.
                    await session.rollback()
                else:
                    await session.commit()
                break
            else:  # pragma: no cover - session_factory always yields
                result = ExportBatchResult(
                    path=path,
                    status=ExportStatus.FAILED_NON_RETRYABLE,
                    error_code=ConfigErrorCode.SHEETS_CURSOR_READ_FAILED,
                    error_message="No DB session available",
                )
        except RetryableSheetsError as exc:
            result = ExportBatchResult(
                path=path,
                status=ExportStatus.FAILED_RETRYABLE,
                error_code=exc.numeric_code,
                error_message=exc.message,
            )
        except NonRetryableSheetsError as exc:
            result = ExportBatchResult(
                path=path,
                status=ExportStatus.FAILED_NON_RETRYABLE,
                error_code=exc.numeric_code,
                error_message=exc.message,
            )
        except Exception as exc:  # last-resort safety net
            logger.error(
                "[sheets_export] Unexpected error on %s path: %s",
                path,
                exc,
                exc_info=True,
            )
            result = ExportBatchResult(
                path=path,
                status=ExportStatus.FAILED_NON_RETRYABLE,
                error_code=ConfigErrorCode.SHEETS_WRITE_FAILED,
                error_message=str(exc),
            )

        result.duration_ms = (time.monotonic() - start) * 1000.0
        logger.info(
            "[sheets_export] %s tick done (status=%s, rows=%d, retries=%d, %.1fms)",
            path,
            result.status.value,
            result.rows_written,
            result.retries,
            result.duration_ms,
            extra=result.to_log_extra(),
        )
        return result

    async def _run_sensor_path(
        self,
        session: Any,
        cursor: SheetsExportCursor,
        tab_mgr: TabRotationManager,
    ) -> ExportBatchResult:
        cursor_before = await cursor.get_sensor_cursor()
        result = ExportBatchResult(
            path="sensor",
            status=ExportStatus.NOTHING_TO_DO,
            cursor_before=cursor_before,
        )

        batcher = SensorExportBatcher(session)
        batch: SensorBatch = await batcher.fetch_batch(
            last_timestamp_iso=cursor_before.get("last_row_timestamp"),
            last_id=cursor_before.get("last_row_id"),
            limit=self._settings.sensor_batch_size,
        )
        result.rows_read = len(batch.rows)
        if batch.is_empty():
            result.cursor_after = cursor_before
            return result

        tabs_touched: List[str] = []
        for tab_name, rows in self._chunk_sensor_rows_by_tab(batch, tab_mgr):
            await self._client.append_rows(
                tab_name=tab_name,
                header_row=SENSOR_HEADER,
                rows=rows,
            )
            tabs_touched.append(tab_name)
        result.rows_written = len(batch.rows)
        result.tabs_touched.extend(tabs_touched)

        new_cursor = await cursor.set_sensor_cursor(
            last_row_id=str(batch.last_row_id) if batch.last_row_id else None,
            last_row_timestamp=batch.last_row_timestamp,
            rows_exported_increment=result.rows_written,
        )
        result.cursor_after = new_cursor
        result.status = ExportStatus.SUCCESS
        return result

    async def _run_actuator_path(
        self,
        session: Any,
        cursor: SheetsExportCursor,
        tab_mgr: TabRotationManager,
        *,
        window_seconds: int,
    ) -> ExportBatchResult:
        cursor_before = await cursor.get_history_cursor()
        open_runs_before = await cursor.get_open_runs()
        result = ExportBatchResult(
            path="actuator",
            status=ExportStatus.NOTHING_TO_DO,
            cursor_before={
                **cursor_before,
                "open_runs": len(open_runs_before),
            },
        )

        batcher = ActuatorExportBatcher(
            session, correlation_window_seconds=window_seconds
        )
        batch: ActuatorBatch = await batcher.fetch_batch(
            last_timestamp_iso=cursor_before.get("last_row_timestamp"),
            last_id=cursor_before.get("last_row_id"),
            limit=self._settings.history_batch_size,
            open_runs=open_runs_before,
        )
        result.rows_read = len(batch.rows)
        result.notes = dict(batch.notes_counter)

        if batch.is_empty():
            # Even with no completed runs we still persist open_runs after
            # the call (in case the batcher consumed events that did not
            # close a run yet).
            await cursor.set_open_runs(batch.open_runs_after)
            result.cursor_after = {
                **cursor_before,
                "open_runs": len(batch.open_runs_after),
            }
            return result

        tabs_touched: List[str] = []
        for tab_name, rows in self._chunk_actuator_rows_by_tab(batch, tab_mgr):
            await self._client.append_rows(
                tab_name=tab_name,
                header_row=ACTUATOR_HEADER,
                rows=rows,
            )
            tabs_touched.append(tab_name)
        result.rows_written = len(batch.rows)
        result.tabs_touched.extend(tabs_touched)

        new_cursor = await cursor.set_history_cursor(
            last_row_id=str(batch.last_row_id) if batch.last_row_id else None,
            last_row_timestamp=batch.last_row_timestamp,
            rows_exported_increment=result.rows_written,
        )
        await cursor.set_open_runs(batch.open_runs_after)
        result.cursor_after = {
            **new_cursor,
            "open_runs": len(batch.open_runs_after),
        }
        result.status = ExportStatus.SUCCESS
        return result

    # --- helpers ------------------------------------------------------------
    def _group_sensor_rows_by_tab(
        self,
        rows: List[SensorRow],
        tab_mgr: TabRotationManager,
    ) -> List[Tuple[str, List[List[Any]]]]:
        buckets: "OrderedDict[str, List[List[Any]]]" = OrderedDict()
        for row in rows:
            tab_name = tab_mgr.current_sensor_tab(when=row.timestamp_utc)
            buckets.setdefault(tab_name, []).append(row.to_sheet_row())
        return list(buckets.items())

    def _group_actuator_rows_by_tab(
        self,
        rows: List[ActuatorRunRow],
        tab_mgr: TabRotationManager,
    ) -> List[Tuple[str, List[List[Any]]]]:
        buckets: "OrderedDict[str, List[List[Any]]]" = OrderedDict()
        for row in rows:
            tab_when = row.run_end_utc or row.run_start_utc
            tab_name = tab_mgr.current_actuator_tab(when=tab_when)
            buckets.setdefault(tab_name, []).append(row.to_sheet_row())
        return list(buckets.items())

    def _get_tab_manager(self, cursor: SheetsExportCursor) -> TabRotationManager:
        granularity = (
            self._settings.tab_granularity
            if self._settings.tab_granularity in ("monthly", "weekly")
            else "monthly"
        )
        return TabRotationManager(cursor, granularity=granularity)

    def _chunk_sensor_rows_by_tab(
        self,
        batch: SensorBatch,
        tab_mgr: TabRotationManager,
    ) -> List[Tuple[str, List[List[Any]]]]:
        chunks: List[Tuple[str, List[List[Any]]]] = []
        for row in batch.rows:
            tab_name = tab_mgr.current_sensor_tab(when=row.timestamp_utc)
            sheet_row = row.to_sheet_row()
            if chunks and chunks[-1][0] == tab_name:
                chunks[-1][1].append(sheet_row)
            else:
                chunks.append((tab_name, [sheet_row]))
        return chunks

    def _chunk_actuator_rows_by_tab(
        self,
        batch: ActuatorBatch,
        tab_mgr: TabRotationManager,
    ) -> List[Tuple[str, List[List[Any]]]]:
        chunks: List[Tuple[str, List[List[Any]]]] = []
        for row in batch.rows:
            anchor = row.run_end_utc or row.run_start_utc
            tab_name = tab_mgr.current_actuator_tab(when=anchor)
            sheet_row = row.to_sheet_row()
            if chunks and chunks[-1][0] == tab_name:
                chunks[-1][1].append(sheet_row)
            else:
                chunks.append((tab_name, [sheet_row]))
        return chunks


# -----------------------------------------------------------------------------
# Dependency injection singletons
# -----------------------------------------------------------------------------


_service_instance: Optional[SheetsExportService] = None


def get_sheets_export_service() -> SheetsExportService:
    """FastAPI dependency for ``SheetsExportService``."""
    if _service_instance is None:
        raise RuntimeError(
            "SheetsExportService not initialised. "
            "Call init_sheets_export_service() during startup."
        )
    return _service_instance


def init_sheets_export_service(
    scheduler: CentralScheduler,
    session_factory: SessionFactory,
    *,
    settings: Optional[SheetsExportSettings] = None,
) -> SheetsExportService:
    """
    Initialise the singleton service. Safe to call multiple times — the
    second call returns the existing instance.
    """
    global _service_instance
    if _service_instance is not None:
        logger.warning("[sheets_export] Service already initialised — reusing instance")
        return _service_instance
    _service_instance = SheetsExportService(
        scheduler=scheduler,
        session_factory=session_factory,
        settings=settings,
    )
    return _service_instance


# Surface frozen headers for tests / docs --------------------------------------
__all_headers__: List[List[str]] = [SENSOR_HEADER, ACTUATOR_HEADER]
