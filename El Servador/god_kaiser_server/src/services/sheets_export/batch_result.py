"""
Shared dataclasses for the Sheets export pipeline.

``ExportBatchResult`` is the public contract returned by the two stable
service entry-points ``SheetsExportService.export_sensors`` and
``SheetsExportService.export_actor_history`` (see Verify-Plan-Gate from
2026-05-23 on AUT-444).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ExportStatus(str, enum.Enum):
    """Final status of an export batch run."""

    SUCCESS = "success"           # Cursor advanced, all rows written.
    NOTHING_TO_DO = "nothing_to_do"  # No new rows since last cursor.
    DRY_RUN = "dry_run"           # No writes performed (cursor unchanged).
    FAILED_RETRYABLE = "failed_retryable"    # Aborted after max retries.
    FAILED_NON_RETRYABLE = "failed_non_retryable"  # 403/404/config error.
    SKIPPED_DISABLED = "skipped_disabled"    # SHEETS_EXPORT_ENABLED=false.


@dataclass
class ExportBatchResult:
    """
    Result of a single export tick (sensor or actuator pipeline).

    Attributes:
        path: ``"sensor"`` or ``"actuator"``.
        status: Final status (see :class:`ExportStatus`).
        rows_read: Rows fetched from DB.
        rows_written: Rows actually appended to the spreadsheet.
        retries: Number of retry attempts performed.
        duration_ms: Wall-clock duration of the tick.
        cursor_before: Cursor JSON dict before the run (for diagnostics).
        cursor_after: Cursor JSON dict after the run (for diagnostics).
        error_code: Optional numeric ``ConfigErrorCode.SHEETS_*`` on failure.
        error_message: Optional structured error message on failure.
        tabs_touched: Names of spreadsheet tabs that received writes.
        notes: Free-form per-row notes accumulator (e.g. open_run counts).
    """

    path: str
    status: ExportStatus
    rows_read: int = 0
    rows_written: int = 0
    retries: int = 0
    duration_ms: float = 0.0
    cursor_before: Dict[str, Any] = field(default_factory=dict)
    cursor_after: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    tabs_touched: list[str] = field(default_factory=list)
    notes: Dict[str, int] = field(default_factory=dict)

    def to_log_extra(self) -> Dict[str, Any]:
        """Serialize to a flat dict suitable for ``logger.info(..., extra=...)``."""
        return {
            "sheets_export_path": self.path,
            "sheets_export_status": self.status.value,
            "sheets_export_rows_read": self.rows_read,
            "sheets_export_rows_written": self.rows_written,
            "sheets_export_retries": self.retries,
            "sheets_export_duration_ms": round(self.duration_ms, 2),
            "sheets_export_error_code": self.error_code,
            "sheets_export_error_message": self.error_message,
            "sheets_export_tabs_touched": self.tabs_touched,
            "sheets_export_notes": self.notes,
        }
