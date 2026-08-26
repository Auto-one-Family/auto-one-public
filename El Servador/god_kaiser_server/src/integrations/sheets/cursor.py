"""
Google Sheets Export — Cursor Management (AUT-446 / S3).

Provides an atomic get/set/reset abstraction over SystemConfigRepository
for the three Sheets-Export progress cursors:

  sheets_export_sensor_cursor   — last exported sensor_data timestamp
  sheets_export_history_cursor  — last exported actuator_history timestamp
  sheets_export_logic_cursor    — last exported logic_execution_history timestamp (optional)

Cursors are plain strings (ISO-8601 or integer ID) stored in the
``system_config`` table under config_type = "sheets_export".

The service layer (S4+) calls these helpers instead of touching the
repository directly, so cursor semantics are defined in one place.

Reference: docs/plans/BELEG-sheets-export-baseline-2026-05-23.md
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.repositories.system_config_repo import (
    ALLOWED_SHEETS_CURSOR_NAMES,
    SHEETS_CURSOR_HISTORY,
    SHEETS_CURSOR_LOGIC,
    SHEETS_CURSOR_SENSOR,
    SystemConfigRepository,
)

logger = get_logger(__name__)

__all__ = [
    "ALLOWED_SHEETS_CURSOR_NAMES",
    "SHEETS_CURSOR_HISTORY",
    "SHEETS_CURSOR_LOGIC",
    "SHEETS_CURSOR_SENSOR",
    "SheetsCursorService",
]


class SheetsCursorService:
    """
    Atomic get/set/reset for all Sheets-Export cursors.

    One instance per request/session (pass the AsyncSession from the
    dependency-injection layer).

    Usage::

        async with get_session() as session:
            svc = SheetsCursorService(session)
            last_ts = await svc.get(SHEETS_CURSOR_SENSOR)
            await svc.set(SHEETS_CURSOR_SENSOR, "2026-05-23T12:00:00+00:00")
            deleted = await svc.reset(SHEETS_CURSOR_SENSOR)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SystemConfigRepository(session)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, cursor_name: str) -> Optional[str]:
        """
        Return the stored cursor value, or None when not yet initialised.

        Args:
            cursor_name: Must be in ALLOWED_SHEETS_CURSOR_NAMES.

        Raises:
            ValueError: If cursor_name is not allowed.
        """
        self._validate(cursor_name)
        return await self._repo.get_sheets_export_cursor(cursor_name)

    async def set(self, cursor_name: str, value: str) -> None:
        """
        Persist a new cursor value.

        Args:
            cursor_name: Must be in ALLOWED_SHEETS_CURSOR_NAMES.
            value: Non-empty string (ISO-8601 timestamp or integer ID).

        Raises:
            ValueError: If cursor_name is not allowed or value is empty.
        """
        self._validate(cursor_name)
        if not value or not value.strip():
            raise ValueError(f"cursor value must not be empty (cursor_name={cursor_name!r})")
        await self._repo.set_sheets_export_cursor(cursor_name, value)
        logger.debug("Sheets cursor updated: %s = %r", cursor_name, value)

    async def reset(self, cursor_name: str) -> bool:
        """
        Delete the cursor so the next export run starts from the beginning.

        Args:
            cursor_name: Must be in ALLOWED_SHEETS_CURSOR_NAMES.

        Returns:
            True if an entry existed and was deleted, False otherwise.

        Raises:
            ValueError: If cursor_name is not allowed.
        """
        self._validate(cursor_name)
        deleted = await self._repo.reset_sheets_export_cursor(cursor_name)
        if deleted:
            logger.info("Sheets cursor reset: %s", cursor_name)
        else:
            logger.debug("Sheets cursor reset requested but not found: %s", cursor_name)
        return deleted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(cursor_name: str) -> None:
        if cursor_name not in ALLOWED_SHEETS_CURSOR_NAMES:
            allowed = ", ".join(sorted(ALLOWED_SHEETS_CURSOR_NAMES))
            raise ValueError(
                f"Unknown Sheets-Export cursor {cursor_name!r}. "
                f"Allowed values: {allowed}"
            )
