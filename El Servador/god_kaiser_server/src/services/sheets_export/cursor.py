"""
Idempotency cursor helpers for the Sheets export pipeline (S3 / AUT-446).

We persist three logical cursors plus auxiliary state in ``system_config``
through the existing :class:`SystemConfigRepository`. No new table or
repository is introduced — this keeps S3 lightweight and avoids stepping
on the parallel db-inspector stream.

Cursor keys (FROZEN, see Verify-Plan-Gate runde 2 on AUT-446):
- ``sheets_export_sensor_cursor``     — sensor_data export pointer
- ``sheets_export_history_cursor``    — actuator_history export pointer
- ``sheets_export_logic_cursor``      — optional logic_execution_history pointer

Auxiliary state keys (NOT user-resettable directly via the admin endpoint):
- ``sheets_export_history_open_runs`` — open ON-runs not yet closed (S5)
- ``sheets_export_known_tabs``        — list of tab names already initialised (S6)

Cursor semantics:
- Cursor advances ONLY after a successful Sheets write.
- Cursor structure for sensor / history: ``{"last_row_id": str|None,
  "last_row_timestamp": isoformat|None, "rows_exported": int}``.
- Empty cursor (no entry yet) is normalised to all-None / 0.

Cursor reset is exposed via ``POST /api/v1/admin/sheets-export/reset-cursor``
(AdminUser, audit-logged) — see ``src/api/v1/admin_sheets_export.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.repositories.system_config_repo import SystemConfigRepository

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Frozen cursor keys + capability table
# -----------------------------------------------------------------------------

CURSOR_KEY_SENSOR = "sheets_export_sensor_cursor"
CURSOR_KEY_HISTORY = "sheets_export_history_cursor"
CURSOR_KEY_LOGIC = "sheets_export_logic_cursor"

# Auxiliary keys (not resettable via admin endpoint)
CURSOR_KEY_HISTORY_OPEN_RUNS = "sheets_export_history_open_runs"
CURSOR_KEY_KNOWN_TABS = "sheets_export_known_tabs"

# Public reset whitelist — admin endpoint MUST validate against this set.
KNOWN_CURSOR_KEYS: frozenset[str] = frozenset(
    {CURSOR_KEY_SENSOR, CURSOR_KEY_HISTORY, CURSOR_KEY_LOGIC}
)

CONFIG_TYPE = "sheets_export"


def is_known_cursor_key(name: str) -> bool:
    """Return True when ``name`` is a user-resettable Sheets cursor key."""
    return name in KNOWN_CURSOR_KEYS


# -----------------------------------------------------------------------------
# Normalisation helpers (idempotent, defensive)
# -----------------------------------------------------------------------------

_EMPTY_CURSOR: Dict[str, Any] = {
    "last_row_id": None,
    "last_row_timestamp": None,
    "rows_exported": 0,
}


def _normalise_cursor(raw: Any) -> Dict[str, Any]:
    """Return a well-formed cursor dict from whatever was stored."""
    if not isinstance(raw, dict):
        return dict(_EMPTY_CURSOR)
    return {
        "last_row_id": raw.get("last_row_id"),
        "last_row_timestamp": raw.get("last_row_timestamp"),
        "rows_exported": int(raw.get("rows_exported") or 0),
    }


def _isoformat_ts(value: Any) -> Optional[str]:
    """Convert a datetime / iso-string into a canonical isoformat (UTC, with offset)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        # Trust the caller — already an iso string.
        return value
    raise TypeError(f"Unsupported timestamp type: {type(value).__name__}")


# -----------------------------------------------------------------------------
# Cursor service
# -----------------------------------------------------------------------------


class SheetsExportCursor:
    """
    Async helper around :class:`SystemConfigRepository` for cursor reads
    and atomic writes used by the Sheets export pipeline.

    Designed to be stateless (one instance per session) so it composes
    naturally with the per-tick session pattern used in
    :class:`SheetsExportService`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SystemConfigRepository(session)

    # --- low-level get/set --------------------------------------------------

    async def _get(self, key: str) -> Any:
        entry = await self._repo.get_by_key(key)
        if entry is None:
            return None
        return entry.config_value

    async def _set(
        self,
        key: str,
        value: Any,
        *,
        description: str,
    ) -> None:
        await self._repo.set_config(
            key,
            value,
            config_type=CONFIG_TYPE,
            description=description,
            is_secret=False,
        )

    # --- sensor cursor ------------------------------------------------------

    async def get_sensor_cursor(self) -> Dict[str, Any]:
        return _normalise_cursor(await self._get(CURSOR_KEY_SENSOR))

    async def set_sensor_cursor(
        self,
        *,
        last_row_id: Optional[str],
        last_row_timestamp: Any,
        rows_exported_increment: int,
    ) -> Dict[str, Any]:
        current = await self.get_sensor_cursor()
        new_value: Dict[str, Any] = {
            "last_row_id": last_row_id,
            "last_row_timestamp": _isoformat_ts(last_row_timestamp),
            "rows_exported": int(current.get("rows_exported") or 0)
            + max(0, int(rows_exported_increment)),
        }
        await self._set(
            CURSOR_KEY_SENSOR,
            new_value,
            description="Idempotency cursor for sensor_data -> Sheets export (AUT-445).",
        )
        return new_value

    # --- actuator history cursor -------------------------------------------

    async def get_history_cursor(self) -> Dict[str, Any]:
        return _normalise_cursor(await self._get(CURSOR_KEY_HISTORY))

    async def set_history_cursor(
        self,
        *,
        last_row_id: Optional[str],
        last_row_timestamp: Any,
        rows_exported_increment: int,
    ) -> Dict[str, Any]:
        current = await self.get_history_cursor()
        new_value: Dict[str, Any] = {
            "last_row_id": last_row_id,
            "last_row_timestamp": _isoformat_ts(last_row_timestamp),
            "rows_exported": int(current.get("rows_exported") or 0)
            + max(0, int(rows_exported_increment)),
        }
        await self._set(
            CURSOR_KEY_HISTORY,
            new_value,
            description="Idempotency cursor for actuator_history -> Sheets export (AUT-447).",
        )
        return new_value

    # --- optional logic cursor ---------------------------------------------

    async def get_logic_cursor(self) -> Dict[str, Any]:
        return _normalise_cursor(await self._get(CURSOR_KEY_LOGIC))

    async def set_logic_cursor(
        self,
        *,
        last_row_id: Optional[str],
        last_row_timestamp: Any,
    ) -> Dict[str, Any]:
        new_value: Dict[str, Any] = {
            "last_row_id": last_row_id,
            "last_row_timestamp": _isoformat_ts(last_row_timestamp),
            "rows_exported": 0,
        }
        await self._set(
            CURSOR_KEY_LOGIC,
            new_value,
            description="Optional cursor for logic_execution_history correlation.",
        )
        return new_value

    # --- auxiliary state (S5 open runs, S6 known tabs) ---------------------

    async def get_open_runs(self) -> Dict[str, Dict[str, Any]]:
        raw = await self._get(CURSOR_KEY_HISTORY_OPEN_RUNS)
        if not isinstance(raw, dict):
            return {}
        # Defensive copy — caller may mutate.
        return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}

    async def set_open_runs(self, open_runs: Dict[str, Dict[str, Any]]) -> None:
        await self._set(
            CURSOR_KEY_HISTORY_OPEN_RUNS,
            open_runs,
            description="In-flight ON-runs awaiting OFF event (Sheets export S5 recovery).",
        )

    async def get_known_tabs(self) -> set[str]:
        raw = await self._get(CURSOR_KEY_KNOWN_TABS)
        if isinstance(raw, list):
            return {str(x) for x in raw if isinstance(x, str)}
        return set()

    async def add_known_tab(self, tab_name: str) -> None:
        current = await self.get_known_tabs()
        if tab_name in current:
            return
        current.add(tab_name)
        await self._set(
            CURSOR_KEY_KNOWN_TABS,
            sorted(current),
            description="Sheets tabs already initialised (idempotent rotation guard).",
        )

    # --- admin reset --------------------------------------------------------

    async def reset_cursor(self, cursor_name: str, value: Any) -> Dict[str, Any]:
        """
        Operational reset for one of the FROZEN public cursor keys.

        ``value`` may be:
        - ``None``               -> reset to empty cursor (no rows exported)
        - a dict                 -> stored as-is (normalised to cursor shape)
        - any other type         -> rejected with ``ValueError``

        Raises:
            ValueError: If ``cursor_name`` is not in KNOWN_CURSOR_KEYS.
        """
        if cursor_name not in KNOWN_CURSOR_KEYS:
            raise ValueError(
                f"Unknown cursor name: {cursor_name!r}. "
                f"Allowed values: {sorted(KNOWN_CURSOR_KEYS)}"
            )

        if value is None:
            stored: Dict[str, Any] = dict(_EMPTY_CURSOR)
        elif isinstance(value, dict):
            stored = _normalise_cursor(value)
        else:
            raise ValueError(
                f"Cursor value must be a dict or null, got {type(value).__name__}."
            )

        await self._set(
            cursor_name,
            stored,
            description=f"Manual operator reset of cursor {cursor_name} (AUT-446 / D7).",
        )
        logger.warning(
            "[sheets_export] cursor %s manually reset to %s", cursor_name, stored
        )
        return stored
