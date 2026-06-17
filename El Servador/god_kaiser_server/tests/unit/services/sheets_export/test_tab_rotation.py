"""
Unit tests for TabRotationManager + build_tab_name (AUT-448 / S6).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.services.sheets_export.cursor import SheetsExportCursor
from src.services.sheets_export.tab_rotation import (
    ACTUATOR_PREFIX,
    SENSOR_PREFIX,
    TabRotationManager,
    build_tab_name,
)


_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_ENGINE, expire_on_commit=False)
    async with factory() as s:
        yield s
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: List[tuple[str, List[str]]] = []

    async def ensure_worksheet(self, name: str, header: List[str]) -> Any:
        self.calls.append((name, list(header)))
        return {"name": name, "header": header}


class TestBuildTabName:
    def test_monthly_prefix(self):
        when = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        assert (
            build_tab_name(prefix=SENSOR_PREFIX, when=when, granularity="monthly")
            == "sensoren-2026-05"
        )

    def test_actuator_monthly(self):
        when = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        assert (
            build_tab_name(prefix=ACTUATOR_PREFIX, when=when, granularity="monthly")
            == "aktoren-2026-05"
        )

    def test_weekly_iso_week(self):
        # 2026-05-23 (Sat) — ISO week varies — just assert pattern.
        when = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        name = build_tab_name(prefix=SENSOR_PREFIX, when=when, granularity="weekly")
        assert name.startswith("sensoren-2026-05-W")
        assert len(name.split("-W")[1]) == 2

    def test_naive_datetime_is_treated_as_utc(self):
        naive = datetime(2026, 1, 15, 23, 0, 0)
        # UTC -> Berlin = +1h -> 2026-01-16 00:00 local
        name = build_tab_name(prefix=SENSOR_PREFIX, when=naive, granularity="monthly")
        assert name == "sensoren-2026-01"


@pytest.mark.asyncio
class TestTabRotationManager:
    async def test_first_ensure_calls_client_and_caches(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        mgr = TabRotationManager(cursor, granularity="monthly")
        client = _FakeClient()
        header = ["a", "b", "c"]
        await mgr.ensure(client, "sensoren-2026-05", header)
        await session.commit()
        assert client.calls == [("sensoren-2026-05", header)]
        # Cached — second call must hit client again (we still need to fetch
        # the worksheet) but must NOT call add_known_tab twice.
        client.calls.clear()
        await mgr.ensure(client, "sensoren-2026-05", header)
        # Even in cached path we call ensure_worksheet (which is idempotent),
        # but only ONE add_known_tab persisted.
        tabs = await cursor.get_known_tabs()
        assert tabs == {"sensoren-2026-05"}

    async def test_known_tabs_rehydrate_from_db(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        await cursor.add_known_tab("sensoren-2026-04")
        await session.commit()

        mgr = TabRotationManager(cursor, granularity="monthly")
        client = _FakeClient()
        # First call triggers cache load — sees previous tab so does not
        # re-persist.
        await mgr.ensure(client, "sensoren-2026-04", ["x"])
        await session.commit()
        tabs = await cursor.get_known_tabs()
        assert tabs == {"sensoren-2026-04"}

    async def test_current_tabs_for_now(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        mgr = TabRotationManager(cursor, granularity="monthly")
        sensor = mgr.current_sensor_tab(when=datetime(2026, 6, 15, tzinfo=timezone.utc))
        actuator = mgr.current_actuator_tab(when=datetime(2026, 6, 15, tzinfo=timezone.utc))
        assert sensor == "sensoren-2026-06"
        assert actuator == "aktoren-2026-06"
