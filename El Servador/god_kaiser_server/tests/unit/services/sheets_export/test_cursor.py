"""
Unit tests for SheetsExportCursor (AUT-446 wrap that S4/S5 use).

Covers the dict-shaped cursor persistence in ``system_config`` and
verifies behaviour when the parallel db-inspector stream deletes the
config row (simulating their ``reset_sheets_export_cursor`` admin path).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.services.sheets_export.cursor import (
    CURSOR_KEY_HISTORY,
    CURSOR_KEY_SENSOR,
    KNOWN_CURSOR_KEYS,
    SheetsExportCursor,
    is_known_cursor_key,
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


class TestKnownCursorKeys:
    def test_known_keys_contain_three_frozen_names(self):
        assert KNOWN_CURSOR_KEYS == frozenset(
            {
                "sheets_export_sensor_cursor",
                "sheets_export_history_cursor",
                "sheets_export_logic_cursor",
            }
        )

    def test_is_known_cursor_key_accepts_sensor(self):
        assert is_known_cursor_key("sheets_export_sensor_cursor") is True

    def test_is_known_cursor_key_rejects_random(self):
        assert is_known_cursor_key("sheets_export_unknown") is False
        assert is_known_cursor_key("sheets_export_known_tabs") is False


@pytest.mark.asyncio
class TestSensorCursor:
    async def test_get_sensor_cursor_returns_empty_when_missing(
        self,
        session: AsyncSession,
    ):
        cursor = SheetsExportCursor(session)
        result = await cursor.get_sensor_cursor()
        assert result == {
            "last_row_id": None,
            "last_row_timestamp": None,
            "rows_exported": 0,
        }

    async def test_set_then_get_round_trip(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        row_id = uuid.uuid4()
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await cursor.set_sensor_cursor(
            last_row_id=str(row_id),
            last_row_timestamp=ts,
            rows_exported_increment=5,
        )
        await session.commit()

        stored = await cursor.get_sensor_cursor()
        assert stored["last_row_id"] == str(row_id)
        assert stored["last_row_timestamp"] == ts.isoformat()
        assert stored["rows_exported"] == 5

    async def test_rows_exported_accumulates_across_calls(
        self,
        session: AsyncSession,
    ):
        cursor = SheetsExportCursor(session)
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await cursor.set_sensor_cursor(
            last_row_id=str(uuid.uuid4()),
            last_row_timestamp=ts,
            rows_exported_increment=3,
        )
        await cursor.set_sensor_cursor(
            last_row_id=str(uuid.uuid4()),
            last_row_timestamp=ts,
            rows_exported_increment=4,
        )
        await session.commit()
        stored = await cursor.get_sensor_cursor()
        assert stored["rows_exported"] == 7

    async def test_get_after_repo_delete_returns_empty(
        self,
        session: AsyncSession,
    ):
        # Seed via service.
        cursor = SheetsExportCursor(session)
        await cursor.set_sensor_cursor(
            last_row_id=str(uuid.uuid4()),
            last_row_timestamp=datetime.now(timezone.utc),
            rows_exported_increment=1,
        )
        await session.commit()
        # Simulate the parallel admin reset (SheetsCursorService.reset()).
        repo = SystemConfigRepository(session)
        await repo.reset_sheets_export_cursor(CURSOR_KEY_SENSOR)
        await session.commit()

        empty = await cursor.get_sensor_cursor()
        assert empty["last_row_id"] is None
        assert empty["rows_exported"] == 0


@pytest.mark.asyncio
class TestHistoryCursorAndOpenRuns:
    async def test_history_cursor_set_and_get(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        ts = datetime(2026, 5, 23, 14, 0, 0, tzinfo=timezone.utc)
        await cursor.set_history_cursor(
            last_row_id=str(uuid.uuid4()),
            last_row_timestamp=ts,
            rows_exported_increment=2,
        )
        await session.commit()
        stored = await cursor.get_history_cursor()
        assert stored["rows_exported"] == 2
        assert stored["last_row_timestamp"] == ts.isoformat()

    async def test_open_runs_round_trip(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        sample = {
            f"{uuid.uuid4()}:5": {
                "start_id": str(uuid.uuid4()),
                "start_ts": datetime.now(timezone.utc).isoformat(),
                "issued_by": "logic:11111111-1111-1111-1111-111111111111",
                "value": 1.0,
                "ausloeser": "rule:11111111-1111-1111-1111-111111111111:test",
                "notes": "",
            }
        }
        await cursor.set_open_runs(sample)
        await session.commit()
        loaded = await cursor.get_open_runs()
        assert loaded == sample

    async def test_open_runs_default_empty(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        assert await cursor.get_open_runs() == {}


@pytest.mark.asyncio
class TestKnownTabs:
    async def test_add_known_tab_persists_and_dedupes(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        await cursor.add_known_tab("sensoren-2026-05")
        await cursor.add_known_tab("aktoren-2026-05")
        await cursor.add_known_tab("sensoren-2026-05")  # duplicate
        await session.commit()
        tabs = await cursor.get_known_tabs()
        assert tabs == {"sensoren-2026-05", "aktoren-2026-05"}


@pytest.mark.asyncio
class TestResetCursor:
    async def test_reset_unknown_name_raises(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        with pytest.raises(ValueError, match="Unknown cursor name"):
            await cursor.reset_cursor("not_a_cursor", None)

    async def test_reset_to_empty(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        await cursor.set_history_cursor(
            last_row_id=str(uuid.uuid4()),
            last_row_timestamp=datetime.now(timezone.utc),
            rows_exported_increment=7,
        )
        await session.commit()
        new_value = await cursor.reset_cursor(CURSOR_KEY_HISTORY, None)
        assert new_value["last_row_id"] is None
        assert new_value["rows_exported"] == 0

    async def test_reset_with_explicit_value_dict(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        target = {
            "last_row_id": str(uuid.uuid4()),
            "last_row_timestamp": datetime.now(timezone.utc).isoformat(),
            "rows_exported": 42,
        }
        new_value = await cursor.reset_cursor(CURSOR_KEY_SENSOR, target)
        assert new_value == target

    async def test_reset_with_invalid_value_type(self, session: AsyncSession):
        cursor = SheetsExportCursor(session)
        with pytest.raises(ValueError, match="Cursor value must be a dict"):
            await cursor.reset_cursor(CURSOR_KEY_SENSOR, "not-a-dict")
