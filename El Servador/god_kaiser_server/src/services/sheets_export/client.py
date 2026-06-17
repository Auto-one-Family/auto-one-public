"""
Google Sheets client wrapper with retry/backoff and error catalog
(AUT-449 / S7).

Two responsibilities:
1. Lazy-load and authorise a ``gspread`` client from the existing
   Service-Account credentials (S1 / AUT-443).
2. Translate raw gspread / google-api errors into our typed Sheets
   exceptions (``RetryableSheetsError`` / ``NonRetryableSheetsError``)
   so the rest of the pipeline can stay pure-Python.

The wrapper is intentionally narrow — only the operations we need:
- ``open_spreadsheet`` (once at startup)
- ``ensure_worksheet`` (idempotent get-or-create + header)
- ``append_rows`` (the batch write)

It exposes a single ``execute_with_retry`` helper that all callers go
through; this keeps the retry semantics in one place.
"""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

from ...core.config import SheetsExportSettings, get_settings
from ...core.error_codes import ConfigErrorCode
from ...core.logging_config import get_logger
from .exceptions import (
    NonRetryableSheetsError,
    RetryableSheetsError,
    SheetsExportError,
)

logger = get_logger(__name__)

T = TypeVar("T")


# -----------------------------------------------------------------------------
# Status-code parsing
# -----------------------------------------------------------------------------

_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_NON_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({400, 401, 403, 404, 409})


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Best-effort status code extraction from gspread / requests exceptions."""
    # gspread.exceptions.APIError carries a ``response`` attribute.
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    # Fallback: scrape the message ("APIError: 429 ...").
    match = re.search(r"\b([1-5]\d{2})\b", str(exc))
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return None


def classify_api_error(exc: Exception) -> SheetsExportError:
    """
    Convert a raw gspread / Google API exception into our typed pipeline
    exception. Unknown exceptions are wrapped as ``RetryableSheetsError``
    with a generic transient code so they get one bounded retry pass
    before bubbling up.
    """
    code = _extract_status_code(exc)
    msg = str(exc) or exc.__class__.__name__

    if code == 429:
        return RetryableSheetsError(
            f"Sheets API quota exceeded (429): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_QUOTA_EXCEEDED,
            details={"http_status": code},
        )
    if code in (500, 502, 503, 504):
        return RetryableSheetsError(
            f"Sheets API transient error ({code}): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_TRANSIENT_API_ERROR,
            details={"http_status": code},
        )
    if code == 403:
        return NonRetryableSheetsError(
            f"Sheets API permission denied (403): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_PERMISSION_DENIED,
            details={"http_status": code},
        )
    if code == 404:
        return NonRetryableSheetsError(
            f"Sheets resource not found (404): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_NOT_FOUND,
            details={"http_status": code},
        )
    if code == 413:
        return NonRetryableSheetsError(
            f"Sheets payload too large (413): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_PAYLOAD_TOO_LARGE,
            details={"http_status": code},
        )
    if code in _RETRYABLE_HTTP_CODES:
        return RetryableSheetsError(
            f"Sheets API retryable error ({code}): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_TRANSIENT_API_ERROR,
            details={"http_status": code},
        )
    if code in _NON_RETRYABLE_HTTP_CODES:
        return NonRetryableSheetsError(
            f"Sheets API non-retryable error ({code}): {msg}",
            numeric_code=ConfigErrorCode.SHEETS_WRITE_FAILED,
            details={"http_status": code},
        )
    # Unknown status — treat as retryable, but with conservative backoff cap.
    return RetryableSheetsError(
        f"Unclassified Sheets API error: {msg}",
        numeric_code=ConfigErrorCode.SHEETS_INVALID_RESPONSE,
        details={"http_status": code},
    )


# -----------------------------------------------------------------------------
# Backoff (S7)
# -----------------------------------------------------------------------------


@dataclass
class _BackoffState:
    attempts: int = 0
    total_sleep_s: float = 0.0


async def _sleep_with_jitter(attempt: int, max_backoff: float) -> float:
    """Sleep ``min((2**attempt) + jitter, max_backoff)`` seconds and return it."""
    base = min(2.0**attempt, max_backoff)
    jitter = random.uniform(0.0, min(1.0, max_backoff - base + 1.0))
    sleep_s = min(base + jitter, max_backoff)
    await asyncio.sleep(sleep_s)
    return sleep_s


# -----------------------------------------------------------------------------
# Client wrapper
# -----------------------------------------------------------------------------


@dataclass
class SheetsAppendResult:
    """Outcome of one ``append_rows`` call."""

    rows_written: int
    tab_name: str


class SheetsClient:
    """
    Narrow async wrapper around ``gspread``.

    The wrapper deliberately holds no domain logic — it knows how to
    open a spreadsheet, get-or-create a worksheet, append rows, and how
    to retry on quota / transient errors. The Sheets dependency is
    lazy-imported so the package keeps loading even when
    ``SHEETS_EXPORT_ENABLED=false`` and the user never installed
    ``gspread``.
    """

    def __init__(
        self,
        settings: Optional[SheetsExportSettings] = None,
        *,
        gspread_client: Optional[Any] = None,
        spreadsheet: Optional[Any] = None,
    ) -> None:
        self._settings: SheetsExportSettings = settings or get_settings().sheets_export
        self._client: Optional[Any] = gspread_client
        self._spreadsheet: Optional[Any] = spreadsheet
        self._lock = asyncio.Lock()

    # --- introspection ------------------------------------------------------

    @property
    def spreadsheet_id(self) -> Optional[str]:
        return self._settings.spreadsheet_id

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.enabled and self._settings.spreadsheet_id)

    # --- bootstrap ---------------------------------------------------------

    async def open_spreadsheet(self) -> Any:
        """
        Lazy authorise + open the configured spreadsheet.

        Raises:
            NonRetryableSheetsError: When credentials or spreadsheet id
                are missing or invalid.
        """
        if self._spreadsheet is not None:
            return self._spreadsheet

        async with self._lock:
            if self._spreadsheet is not None:
                return self._spreadsheet

            if not self._settings.enabled:
                raise NonRetryableSheetsError(
                    "SHEETS_EXPORT_ENABLED=false — cannot open spreadsheet.",
                    numeric_code=ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED,
                )
            if not self._settings.spreadsheet_id:
                raise NonRetryableSheetsError(
                    "SHEETS_SPREADSHEET_ID is not configured.",
                    numeric_code=ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED,
                )

            if self._client is None:
                try:
                    import gspread
                    from ...integrations.sheets import load_service_account_credentials
                except ImportError as exc:
                    raise NonRetryableSheetsError(
                        "gspread is not installed. Run `poetry install` to "
                        "enable the Sheets export pipeline.",
                        numeric_code=ConfigErrorCode.SHEETS_DEPENDENCY_MISSING,
                        details={"missing_package": "gspread"},
                    ) from exc

                creds = load_service_account_credentials(self._settings)
                self._client = gspread.authorize(creds)

            spreadsheet = await asyncio.to_thread(
                self._client.open_by_key, self._settings.spreadsheet_id
            )
            self._spreadsheet = spreadsheet
            logger.info(
                "[sheets_export] Opened spreadsheet id=%s",
                self._settings.spreadsheet_id,
            )
            return spreadsheet

    # --- worksheet management (S6) -----------------------------------------

    async def ensure_worksheet(
        self,
        tab_name: str,
        header_row: List[str],
        *,
        default_cols: int = 20,
        default_rows: int = 1000,
    ) -> Any:
        """
        Idempotent get-or-create with header initialisation.

        Returns the gspread Worksheet on success.

        Raises:
            NonRetryableSheetsError: On 403/404 / tab create failure.
            RetryableSheetsError: On transient errors.
        """
        spreadsheet = await self.open_spreadsheet()

        def _get_or_create() -> Any:
            try:
                ws = spreadsheet.worksheet(tab_name)
                return ws
            except Exception as exc:  # gspread.exceptions.WorksheetNotFound
                exc_name = exc.__class__.__name__
                if exc_name != "WorksheetNotFound":
                    raise
                cols = max(default_cols, len(header_row))
                ws = spreadsheet.add_worksheet(
                    title=tab_name, rows=default_rows, cols=cols
                )
                ws.append_row(header_row, value_input_option="RAW")
                logger.info(
                    "[sheets_export] Created new tab %s with %d header columns",
                    tab_name,
                    len(header_row),
                )
                return ws

        try:
            return await asyncio.to_thread(_get_or_create)
        except SheetsExportError:
            raise
        except Exception as exc:
            err = classify_api_error(exc)
            # Override numeric code for clarity when it's a tab creation issue.
            if not err.retryable and err.numeric_code in (
                ConfigErrorCode.SHEETS_WRITE_FAILED,
            ):
                err = NonRetryableSheetsError(
                    f"Failed to create worksheet {tab_name!r}: {exc}",
                    numeric_code=ConfigErrorCode.SHEETS_TAB_CREATE_FAILED,
                    details={"tab_name": tab_name},
                )
            raise err

    # --- append (with retry + 413 split) -----------------------------------

    async def append_rows(
        self,
        tab_name: str,
        header_row: List[str],
        rows: List[List[Any]],
        *,
        value_input_option: str = "RAW",
    ) -> SheetsAppendResult:
        """
        Append ``rows`` to ``tab_name``. Handles 429/5xx with exponential
        backoff and 413 by recursively halving the batch.

        Returns:
            ``SheetsAppendResult`` with rows actually written.
        """
        if not rows:
            return SheetsAppendResult(rows_written=0, tab_name=tab_name)

        worksheet = await self.ensure_worksheet(tab_name, header_row)
        await self._append_rows_with_split(worksheet, rows)
        return SheetsAppendResult(rows_written=len(rows), tab_name=tab_name)

    async def _append_rows_with_split(
        self,
        worksheet: Any,
        rows: List[List[Any]],
    ) -> None:
        min_size = self._settings.batch_min_size_for_split

        async def _do_append(chunk: List[List[Any]]) -> None:
            await asyncio.to_thread(
                worksheet.append_rows, chunk, value_input_option="RAW"
            )

        try:
            await self.execute_with_retry(lambda: _do_append(rows))
            return
        except NonRetryableSheetsError as exc:
            if (
                exc.numeric_code == ConfigErrorCode.SHEETS_PAYLOAD_TOO_LARGE
                and len(rows) > 1
            ):
                # 413 — split and retry both halves.
                if len(rows) < min_size:
                    raise NonRetryableSheetsError(
                        "Batch is below min split size; aborting.",
                        numeric_code=ConfigErrorCode.SHEETS_BATCH_SPLIT_LIMIT_REACHED,
                        details={
                            "batch_size": len(rows),
                            "min_size_for_split": min_size,
                        },
                    ) from exc
                mid = len(rows) // 2
                logger.warning(
                    "[sheets_export] 413 received — splitting batch (size=%d -> %d + %d)",
                    len(rows),
                    mid,
                    len(rows) - mid,
                )
                await self._append_rows_with_split(worksheet, rows[:mid])
                await self._append_rows_with_split(worksheet, rows[mid:])
                return
            raise

    # --- retry primitive (used by append + ensure) -------------------------

    async def execute_with_retry(
        self,
        op: Callable[[], Awaitable[T]],
        *,
        max_attempts: Optional[int] = None,
        max_backoff: Optional[float] = None,
    ) -> T:
        """
        Execute ``op`` with exponential-backoff retry on
        ``RetryableSheetsError`` and raw gspread exceptions.

        Args:
            op: async callable returning some value.
            max_attempts: override of ``settings.retry_max_attempts``.
            max_backoff: override of ``settings.retry_max_backoff_seconds``.
        """
        attempts = max_attempts or self._settings.retry_max_attempts
        cap = max_backoff or self._settings.retry_max_backoff_seconds
        state = _BackoffState()
        last_exc: Optional[SheetsExportError] = None

        for attempt in range(attempts):
            try:
                return await op()
            except SheetsExportError as exc:
                last_exc = exc
                if not exc.retryable:
                    raise
                state.attempts += 1
                slept = await _sleep_with_jitter(attempt, cap)
                state.total_sleep_s += slept
                logger.warning(
                    "[sheets_export] retryable error (code=%s, attempt=%d/%d, slept=%.2fs): %s",
                    exc.numeric_code,
                    attempt + 1,
                    attempts,
                    slept,
                    exc.message,
                )
            except Exception as exc:
                last_exc = classify_api_error(exc)
                if not last_exc.retryable:
                    raise last_exc
                state.attempts += 1
                slept = await _sleep_with_jitter(attempt, cap)
                state.total_sleep_s += slept
                logger.warning(
                    "[sheets_export] retryable raw exception (code=%s, attempt=%d/%d, slept=%.2fs): %s",
                    last_exc.numeric_code,
                    attempt + 1,
                    attempts,
                    slept,
                    last_exc.message,
                )

        assert last_exc is not None  # noqa: S101 - loop guarantees this
        raise RetryableSheetsError(
            f"Sheets retry budget exhausted after {attempts} attempts: {last_exc.message}",
            numeric_code=last_exc.numeric_code,
            details={
                **last_exc.details,
                "retries_attempted": state.attempts,
                "total_sleep_s": round(state.total_sleep_s, 3),
            },
        )
