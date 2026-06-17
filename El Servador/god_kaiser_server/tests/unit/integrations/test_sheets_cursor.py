"""
Unit tests for src.integrations.sheets.cursor and the underlying
SystemConfigRepository cursor methods (AUT-446 / S3).

Strategy: use an in-memory SQLite session to avoid depending on a
running PostgreSQL instance — mirrors the pattern used throughout the
unit-test layer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.repositories.system_config_repo import (
    ALLOWED_SHEETS_CURSOR_NAMES,
    SHEETS_CURSOR_HISTORY,
    SHEETS_CURSOR_LOGIC,
    SHEETS_CURSOR_SENSOR,
    SystemConfigRepository,
)
from src.integrations.sheets.cursor import SheetsCursorService

# ---------------------------------------------------------------------------
# In-memory DB fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SystemConfigRepository — cursor methods
# ---------------------------------------------------------------------------


class TestSystemConfigRepoCursorMethods:
    async def test_get_cursor_returns_none_when_not_set(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        result = await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        assert result is None

    async def test_set_and_get_cursor_round_trip(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        ts = "2026-05-23T10:00:00+00:00"
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, ts)
        await session.commit()
        result = await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        assert result == ts

    async def test_set_cursor_is_idempotent_on_update(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, "2026-05-23T10:00:00+00:00")
        await session.commit()
        new_ts = "2026-05-23T11:00:00+00:00"
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, new_ts)
        await session.commit()
        result = await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        assert result == new_ts

    async def test_reset_cursor_deletes_entry(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, "2026-05-23T10:00:00+00:00")
        await session.commit()
        deleted = await repo.reset_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        await session.commit()
        assert deleted is True
        result = await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        assert result is None

    async def test_reset_cursor_returns_false_when_not_found(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        deleted = await repo.reset_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        assert deleted is False

    async def test_all_three_cursors_are_independent(self, session: AsyncSession):
        repo = SystemConfigRepository(session)
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, "ts_sensor")
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_HISTORY, "ts_history")
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_LOGIC, "ts_logic")
        await session.commit()

        assert await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR) == "ts_sensor"
        assert await repo.get_sheets_export_cursor(SHEETS_CURSOR_HISTORY) == "ts_history"
        assert await repo.get_sheets_export_cursor(SHEETS_CURSOR_LOGIC) == "ts_logic"

        await repo.reset_sheets_export_cursor(SHEETS_CURSOR_SENSOR)
        await session.commit()
        assert await repo.get_sheets_export_cursor(SHEETS_CURSOR_SENSOR) is None
        assert await repo.get_sheets_export_cursor(SHEETS_CURSOR_HISTORY) == "ts_history"


# ---------------------------------------------------------------------------
# SheetsCursorService
# ---------------------------------------------------------------------------


class TestSheetsCursorService:
    async def test_get_returns_none_initially(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        assert await svc.get(SHEETS_CURSOR_SENSOR) is None

    async def test_set_persists_value(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        ts = "2026-05-23T12:00:00+00:00"
        await svc.set(SHEETS_CURSOR_SENSOR, ts)
        await session.commit()
        assert await svc.get(SHEETS_CURSOR_SENSOR) == ts

    async def test_reset_deletes_value(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        await svc.set(SHEETS_CURSOR_HISTORY, "ts_h")
        await session.commit()
        deleted = await svc.reset(SHEETS_CURSOR_HISTORY)
        await session.commit()
        assert deleted is True
        assert await svc.get(SHEETS_CURSOR_HISTORY) is None

    async def test_reset_returns_false_when_cursor_not_set(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        assert await svc.reset(SHEETS_CURSOR_LOGIC) is False

    def test_set_raises_on_unknown_cursor_name(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        with pytest.raises(ValueError, match="Unknown Sheets-Export cursor"):
            svc._validate("non_existent_cursor")

    async def test_set_raises_on_empty_value(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        with pytest.raises(ValueError, match="cursor value must not be empty"):
            await svc.set(SHEETS_CURSOR_SENSOR, "")

    async def test_set_raises_on_whitespace_only_value(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        with pytest.raises(ValueError, match="cursor value must not be empty"):
            await svc.set(SHEETS_CURSOR_SENSOR, "   ")

    async def test_get_raises_on_unknown_cursor_name(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        with pytest.raises(ValueError, match="Unknown Sheets-Export cursor"):
            await svc.get("bad_cursor")

    async def test_reset_raises_on_unknown_cursor_name(self, session: AsyncSession):
        svc = SheetsCursorService(session)
        with pytest.raises(ValueError, match="Unknown Sheets-Export cursor"):
            await svc.reset("bad_cursor")


# ---------------------------------------------------------------------------
# ALLOWED_SHEETS_CURSOR_NAMES constant
# ---------------------------------------------------------------------------


class TestAllowedCursorNames:
    def test_contains_all_three_cursors(self):
        assert SHEETS_CURSOR_SENSOR in ALLOWED_SHEETS_CURSOR_NAMES
        assert SHEETS_CURSOR_HISTORY in ALLOWED_SHEETS_CURSOR_NAMES
        assert SHEETS_CURSOR_LOGIC in ALLOWED_SHEETS_CURSOR_NAMES

    def test_is_frozenset(self):
        assert isinstance(ALLOWED_SHEETS_CURSOR_NAMES, frozenset)
