"""
Unit tests for SheetsClient retry / backoff and error classification
(AUT-449 / S7).

These tests use lightweight fakes — no real gspread dependency is
imported. They verify:
- classify_api_error: HTTP status -> typed exception with correct numeric_code
- execute_with_retry: 429 sequence -> success after backoff
- execute_with_retry: 403/404 -> immediate failure (no retry)
- execute_with_retry: exhausted budget -> RetryableSheetsError
- append_rows: 413 split-and-retry path
- append_rows: split-limit-reached failure
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from src.core.config import SheetsExportSettings
from src.core.error_codes import ConfigErrorCode
from src.services.sheets_export.client import (
    SheetsClient,
    classify_api_error,
)
from src.services.sheets_export.exceptions import (
    NonRetryableSheetsError,
    RetryableSheetsError,
)


# -----------------------------------------------------------------------------
# Fake gspread error
# -----------------------------------------------------------------------------


@dataclass
class _FakeResponse:
    status_code: int
    text: str = ""


class _FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"APIError {status_code}")
        self.response = _FakeResponse(status_code=status_code, text=message)


# -----------------------------------------------------------------------------
# classify_api_error
# -----------------------------------------------------------------------------


class TestClassifyApiError:
    def test_429_is_quota_exceeded(self):
        err = classify_api_error(_FakeAPIError(429))
        assert isinstance(err, RetryableSheetsError)
        assert err.numeric_code == ConfigErrorCode.SHEETS_QUOTA_EXCEEDED

    def test_503_is_transient(self):
        err = classify_api_error(_FakeAPIError(503))
        assert isinstance(err, RetryableSheetsError)
        assert err.numeric_code == ConfigErrorCode.SHEETS_TRANSIENT_API_ERROR

    def test_403_is_permission_denied(self):
        err = classify_api_error(_FakeAPIError(403))
        assert isinstance(err, NonRetryableSheetsError)
        assert err.numeric_code == ConfigErrorCode.SHEETS_PERMISSION_DENIED

    def test_404_is_not_found(self):
        err = classify_api_error(_FakeAPIError(404))
        assert isinstance(err, NonRetryableSheetsError)
        assert err.numeric_code == ConfigErrorCode.SHEETS_NOT_FOUND

    def test_413_is_payload_too_large(self):
        err = classify_api_error(_FakeAPIError(413))
        assert isinstance(err, NonRetryableSheetsError)
        assert err.numeric_code == ConfigErrorCode.SHEETS_PAYLOAD_TOO_LARGE

    def test_unknown_status_is_retryable(self):
        err = classify_api_error(Exception("totally unknown"))
        assert isinstance(err, RetryableSheetsError)


# -----------------------------------------------------------------------------
# execute_with_retry
# -----------------------------------------------------------------------------


def _settings_for_test(**overrides) -> SheetsExportSettings:
    # See note in test_service.py: SheetsExportSettings uses Field aliases,
    # so we pass arguments by alias to bypass env-var binding entirely.
    alias_map = {
        "enabled": "SHEETS_EXPORT_ENABLED",
        "spreadsheet_id": "SHEETS_SPREADSHEET_ID",
        "retry_max_attempts": "SHEETS_RETRY_MAX_ATTEMPTS",
        "retry_max_backoff_seconds": "SHEETS_RETRY_MAX_BACKOFF_SECONDS",
        "batch_min_size_for_split": "SHEETS_BATCH_MIN_SIZE_FOR_SPLIT",
    }
    defaults = {
        alias_map["enabled"]: True,
        alias_map["spreadsheet_id"]: "dummy",
        alias_map["retry_max_attempts"]: 4,
        alias_map["retry_max_backoff_seconds"]: 1.0,
        alias_map["batch_min_size_for_split"]: 2,
    }
    for key, value in overrides.items():
        defaults[alias_map.get(key, key)] = value
    return SheetsExportSettings(**defaults)


@pytest.mark.asyncio
class TestExecuteWithRetry:
    async def test_succeeds_on_first_call(self, monkeypatch):
        client = SheetsClient(_settings_for_test())
        called = {"count": 0}

        async def op():
            called["count"] += 1
            return "ok"

        result = await client.execute_with_retry(op)
        assert result == "ok"
        assert called["count"] == 1

    async def test_retries_on_429_then_succeeds(self, monkeypatch):
        client = SheetsClient(_settings_for_test())
        attempts = {"n": 0}

        async def op():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _FakeAPIError(429)
            return "ok"

        async def _no_sleep(_attempt, _max):  # signature matches _sleep_with_jitter
            return 0.0

        monkeypatch.setattr(
            "src.services.sheets_export.client._sleep_with_jitter", _no_sleep
        )

        result = await client.execute_with_retry(op)
        assert result == "ok"
        assert attempts["n"] == 3

    async def test_fails_fast_on_403(self, monkeypatch):
        client = SheetsClient(_settings_for_test())
        attempts = {"n": 0}

        async def op():
            attempts["n"] += 1
            raise _FakeAPIError(403)

        with pytest.raises(NonRetryableSheetsError) as excinfo:
            await client.execute_with_retry(op)
        assert excinfo.value.numeric_code == ConfigErrorCode.SHEETS_PERMISSION_DENIED
        assert attempts["n"] == 1

    async def test_fails_fast_on_404(self, monkeypatch):
        client = SheetsClient(_settings_for_test())
        attempts = {"n": 0}

        async def op():
            attempts["n"] += 1
            raise _FakeAPIError(404)

        with pytest.raises(NonRetryableSheetsError):
            await client.execute_with_retry(op)
        assert attempts["n"] == 1

    async def test_exhausts_retry_budget(self, monkeypatch):
        client = SheetsClient(_settings_for_test(retry_max_attempts=3))
        attempts = {"n": 0}

        async def op():
            attempts["n"] += 1
            raise _FakeAPIError(500)

        async def _no_sleep(_attempt, _max):
            return 0.0

        monkeypatch.setattr(
            "src.services.sheets_export.client._sleep_with_jitter", _no_sleep
        )

        with pytest.raises(RetryableSheetsError) as excinfo:
            await client.execute_with_retry(op)
        assert "retry budget exhausted" in excinfo.value.message
        assert attempts["n"] == 3


# -----------------------------------------------------------------------------
# append_rows with 413 split
# -----------------------------------------------------------------------------


class _FakeWorksheet:
    """Records every append_rows invocation for assertion."""

    def __init__(self, split_at: int | None = None) -> None:
        self.calls: list[int] = []
        self._split_at = split_at  # raise 413 if batch larger than this

    def append_rows(self, rows, value_input_option):  # signature mirrors gspread
        self.calls.append(len(rows))
        if self._split_at is not None and len(rows) > self._split_at:
            raise _FakeAPIError(413)


class _FakeClientWithWorksheet(SheetsClient):
    """SheetsClient with the worksheet substituted in-place."""

    def __init__(self, settings, worksheet: _FakeWorksheet) -> None:
        super().__init__(settings)
        self._worksheet = worksheet

    async def ensure_worksheet(self, tab_name, header_row, **_):  # type: ignore[override]
        return self._worksheet


@pytest.mark.asyncio
class TestAppendRowsWith413:
    async def test_no_split_when_under_threshold(self):
        ws = _FakeWorksheet(split_at=None)
        client = _FakeClientWithWorksheet(_settings_for_test(), ws)
        rows = [["a", 1] for _ in range(5)]
        result = await client.append_rows("sensoren-2026-05", ["x", "y"], rows)
        assert result.rows_written == 5
        assert ws.calls == [5]

    async def test_split_halves_until_success(self, monkeypatch):
        ws = _FakeWorksheet(split_at=2)
        client = _FakeClientWithWorksheet(
            _settings_for_test(batch_min_size_for_split=1), ws
        )
        rows = [["a", i] for i in range(8)]

        async def _no_sleep(_attempt, _max):
            return 0.0

        monkeypatch.setattr(
            "src.services.sheets_export.client._sleep_with_jitter", _no_sleep
        )
        result = await client.append_rows("sensoren-2026-05", ["x", "y"], rows)
        # All successful sub-batches must be <= split_at.
        successful_batches = [n for n in ws.calls if n <= 2]
        assert sum(successful_batches) == 8
        assert result.rows_written == 8

    async def test_split_limit_reached_raises(self, monkeypatch):
        ws = _FakeWorksheet(split_at=0)  # always 413 even for 1 row
        client = _FakeClientWithWorksheet(
            _settings_for_test(batch_min_size_for_split=5), ws
        )

        async def _no_sleep(_attempt, _max):
            return 0.0

        monkeypatch.setattr(
            "src.services.sheets_export.client._sleep_with_jitter", _no_sleep
        )
        with pytest.raises(NonRetryableSheetsError) as excinfo:
            await client.append_rows(
                "sensoren-2026-05", ["x"], [["a"] for _ in range(3)]
            )
        assert excinfo.value.numeric_code == ConfigErrorCode.SHEETS_BATCH_SPLIT_LIMIT_REACHED
