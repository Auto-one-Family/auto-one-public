"""
Monthly / weekly tab rotation for the Sheets export pipeline (AUT-448 / S6).

Tab names follow the operator-friendly schema:

- ``sensoren-YYYY-MM``       (monthly default)
- ``aktoren-YYYY-MM``
- ``sensoren-YYYY-MM-W##``   (weekly, ISO 8601 week, opt-in via ENV)
- ``aktoren-YYYY-MM-W##``

Naming uses Europe/Berlin so the operator sees ``-2026-05`` while still
in the local month boundary. The cell content keeps both UTC and local
timestamps (D6).

Granularity is configurable via ``SheetsExportSettings.tab_granularity``
(``monthly`` / ``weekly``). Threshold-based rotation (Option C from the
parent triage) is intentionally NOT implemented — the operator would not
be able to predict the tab name.

Header-row initialisation is delegated to :class:`SheetsClient` via
``ensure_worksheet`` which is idempotent. Known tabs are persisted in
``system_config`` (key ``sheets_export_known_tabs``) so a restart does
not re-fetch every worksheet from the API.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional
from zoneinfo import ZoneInfo

from ...core.logging_config import get_logger
from .cursor import SheetsExportCursor

logger = get_logger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")

SENSOR_PREFIX = "sensoren"
ACTUATOR_PREFIX = "aktoren"

Granularity = Literal["monthly", "weekly"]


def build_tab_name(
    *,
    prefix: str,
    when: Optional[datetime] = None,
    granularity: Granularity = "monthly",
) -> str:
    """
    Compose a tab name for the given date.

    Args:
        prefix: ``SENSOR_PREFIX`` or ``ACTUATOR_PREFIX``.
        when: Reference datetime (default: now, UTC).
        granularity: ``"monthly"`` or ``"weekly"``.

    Returns:
        ``"sensoren-2026-05"`` or ``"sensoren-2026-05-W21"``.
    """
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(BERLIN)

    base = f"{prefix}-{local.year:04d}-{local.month:02d}"
    if granularity == "weekly":
        iso_year, iso_week, _ = local.isocalendar()
        # Use ISO year/week to handle the year-boundary edge case.
        base = f"{prefix}-{iso_year:04d}-{local.month:02d}-W{iso_week:02d}"
    return base


class TabRotationManager:
    """
    Stateful guard against double-initialisation of monthly/weekly tabs.

    The in-memory cache is rehydrated from ``system_config`` on first
    use so a server restart does not trigger spurious worksheet probes.
    """

    def __init__(
        self,
        cursor: SheetsExportCursor,
        *,
        granularity: Granularity = "monthly",
    ) -> None:
        self._cursor = cursor
        self._granularity: Granularity = granularity
        self._known_tabs: Optional[set[str]] = None
        self._lock = asyncio.Lock()

    @property
    def granularity(self) -> Granularity:
        return self._granularity

    async def _ensure_cache_loaded(self) -> set[str]:
        if self._known_tabs is None:
            self._known_tabs = await self._cursor.get_known_tabs()
        return self._known_tabs

    def current_sensor_tab(self, when: Optional[datetime] = None) -> str:
        return build_tab_name(
            prefix=SENSOR_PREFIX, when=when, granularity=self._granularity
        )

    def current_actuator_tab(self, when: Optional[datetime] = None) -> str:
        return build_tab_name(
            prefix=ACTUATOR_PREFIX, when=when, granularity=self._granularity
        )

    async def ensure(
        self,
        client: Any,
        tab_name: str,
        header_row: List[str],
    ) -> Any:
        """
        Ensure the tab exists with the given header and remember it.

        ``client`` is duck-typed (only needs ``ensure_worksheet``) so we
        can drop in a fake during unit tests without importing gspread.
        """
        cache = await self._ensure_cache_loaded()
        if tab_name in cache:
            return await client.ensure_worksheet(tab_name, header_row)

        async with self._lock:
            cache = await self._ensure_cache_loaded()
            if tab_name in cache:
                return await client.ensure_worksheet(tab_name, header_row)
            worksheet = await client.ensure_worksheet(tab_name, header_row)
            cache.add(tab_name)
            await self._cursor.add_known_tab(tab_name)
            logger.info(
                "[sheets_export] tab initialised: %s (granularity=%s)",
                tab_name,
                self._granularity,
            )
            return worksheet

    async def reset_cache(self) -> None:
        """Drop the in-memory cache (next ``ensure`` rehydrates from DB)."""
        async with self._lock:
            self._known_tabs = None
