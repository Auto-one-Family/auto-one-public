"""
Exceptions used by the Sheets export pipeline (AUT-449 / S7).

All exceptions carry a numeric error code from
``ConfigErrorCode.SHEETS_*`` (5050-5079) so they can be surfaced in
structured logs, audit entries and API responses.

Two classes of errors:
- ``RetryableSheetsError`` — transient (429, 5xx, transient parse). The
  caller (``SheetsClient.execute_with_retry``) re-attempts with
  exponential backoff up to ``retry_max_attempts``.
- ``NonRetryableSheetsError`` — hard failure (403, 404, invalid config).
  Aborts immediately, cursor stays unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...core.error_codes import ConfigErrorCode


class SheetsExportError(Exception):
    """Base class for all Sheets export runtime errors."""

    def __init__(
        self,
        message: str,
        *,
        numeric_code: int = ConfigErrorCode.SHEETS_WRITE_FAILED,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.numeric_code = int(numeric_code)
        self.details: Dict[str, Any] = dict(details or {})
        self.retryable = retryable

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"{self.__class__.__name__}(numeric_code={self.numeric_code}, "
            f"retryable={self.retryable}, message={self.message!r})"
        )


class RetryableSheetsError(SheetsExportError):
    """Transient errors — retry with exponential backoff."""

    def __init__(
        self,
        message: str,
        *,
        numeric_code: int = ConfigErrorCode.SHEETS_TRANSIENT_API_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            numeric_code=numeric_code,
            details=details,
            retryable=True,
        )


class NonRetryableSheetsError(SheetsExportError):
    """Hard failures — fail-fast, cursor stays unchanged."""

    def __init__(
        self,
        message: str,
        *,
        numeric_code: int = ConfigErrorCode.SHEETS_PERMISSION_DENIED,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            numeric_code=numeric_code,
            details=details,
            retryable=False,
        )
