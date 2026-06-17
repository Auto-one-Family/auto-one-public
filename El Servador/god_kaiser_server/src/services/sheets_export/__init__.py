"""
Google Sheets Export Pipeline (AUT-442).

This package implements the pull-from-DB sheets export pipeline that
periodically writes sensor measurements and actuator runs to a Google
Spreadsheet shared with the operator (Christoph).

Sub-Issues:
- S2 (AUT-444): SheetsExportService skeleton + scheduler hook
- S3 (AUT-446): Idempotency cursor in system_config + admin reset
- S4 (AUT-445): Sensor batcher (D5/D6 columns)
- S5 (AUT-447): Actuator batcher (ON/OFF pairing, ausloeser vocab, D8 correlation)
- S6 (AUT-448): Monthly/weekly tab rotation + header initialization
- S7 (AUT-449): Retry/backoff/error catalog

Design contract (locked by TM Verify-Plan-Gate, 2026-05-23):
- Two stable entry points on the service:
    - ``export_sensors(*, limit, dry_run) -> ExportBatchResult``
    - ``export_actor_history(*, limit, dry_run, correlation_window_seconds) -> ExportBatchResult``
- Both are idempotent relative to their cursors.
- Cursor only advances after a successful Sheets write.
- Errors in one path MUST NOT silently mark the other as successful.

The feature is OFF by default (``SHEETS_EXPORT_ENABLED=false``); the
scheduler hook in main.py is the only place that may start the service.
"""

from .batch_result import ExportBatchResult, ExportStatus
from .cursor import (
    CURSOR_KEY_HISTORY,
    CURSOR_KEY_HISTORY_OPEN_RUNS,
    CURSOR_KEY_KNOWN_TABS,
    CURSOR_KEY_LOGIC,
    CURSOR_KEY_SENSOR,
    KNOWN_CURSOR_KEYS,
    SheetsExportCursor,
    is_known_cursor_key,
)
from .exceptions import (
    NonRetryableSheetsError,
    RetryableSheetsError,
    SheetsExportError,
)
from .service import (
    SheetsExportService,
    get_sheets_export_service,
    init_sheets_export_service,
)

__all__ = [
    "CURSOR_KEY_HISTORY",
    "CURSOR_KEY_HISTORY_OPEN_RUNS",
    "CURSOR_KEY_KNOWN_TABS",
    "CURSOR_KEY_LOGIC",
    "CURSOR_KEY_SENSOR",
    "ExportBatchResult",
    "ExportStatus",
    "KNOWN_CURSOR_KEYS",
    "NonRetryableSheetsError",
    "RetryableSheetsError",
    "SheetsExportCursor",
    "SheetsExportError",
    "SheetsExportService",
    "get_sheets_export_service",
    "init_sheets_export_service",
    "is_known_cursor_key",
]
