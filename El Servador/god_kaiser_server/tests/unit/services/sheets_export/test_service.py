"""
Service-level tests for SheetsExportService (AUT-444 vertrag + S4/S5 wiring).

We stub the SheetsClient (no gspread) and verify:
- export_sensors / export_actor_history return ExportBatchResult contract.
- Cursor advances ONLY after a successful write.
- Cursor stays unchanged on retryable/non-retryable failure.
- skipped_disabled status when feature flag is off.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, List

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import SheetsExportSettings
from src.core.error_codes import ConfigErrorCode
from src.core.scheduler import CentralScheduler
from src.db.base import Base
from src.db.models.actuator import ActuatorHistory
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig, SensorData
from src.services.sheets_export.batch_result import ExportStatus
from src.services.sheets_export.client import SheetsAppendResult
from src.services.sheets_export.cursor import SheetsExportCursor
from src.services.sheets_export.exceptions import (
    NonRetryableSheetsError,
    RetryableSheetsError,
)
from src.services.sheets_export.service import SheetsExportService


_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture()
async def session_factory_pair():
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_ENGINE, expire_on_commit=False)

    async def session_factory() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    async with factory() as s:
        yield s, session_factory
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# -----------------------------------------------------------------------------
# Stub client
# -----------------------------------------------------------------------------


class _StubClient:
    """Pretend SheetsClient that records appends and can raise on demand."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.appended: List[tuple[str, int]] = []
        self.raises = raises

    async def append_rows(self, tab_name, header_row, rows, value_input_option="RAW"):
        if self.raises is not None:
            raise self.raises
        self.appended.append((tab_name, len(rows)))
        return SheetsAppendResult(rows_written=len(rows), tab_name=tab_name)

    async def ensure_worksheet(self, tab_name, header_row, **_):  # used by tab manager
        return {"name": tab_name, "header": header_row}


def _enabled_settings(**overrides) -> SheetsExportSettings:
    # SheetsExportSettings uses Field aliases (SHEETS_EXPORT_ENABLED, etc.)
    # for env-var binding. Passing kwargs by alias guarantees a value
    # override even when those env vars are not set in the test environment.
    defaults = dict(
        SHEETS_EXPORT_ENABLED=True,
        SHEETS_SPREADSHEET_ID="dummy",
        SHEETS_EXPORT_SENSOR_BATCH_SIZE=100,
        SHEETS_EXPORT_HISTORY_BATCH_SIZE=100,
        SHEETS_EXPORT_INTERVAL_MINUTES=5,
    )
    if "enabled" in overrides:
        defaults["SHEETS_EXPORT_ENABLED"] = overrides.pop("enabled")
    defaults.update(overrides)
    return SheetsExportSettings(**defaults)


# -----------------------------------------------------------------------------
# Helpers to seed data
# -----------------------------------------------------------------------------


async def _seed_sensor_row(
    session: AsyncSession,
    ts: datetime,
    *,
    device_id: str | None = None,
) -> tuple[ESPDevice, SensorData]:
    device_id = device_id or f"ESP_SVC_{uuid.uuid4().hex[:8]}"
    suffix = uuid.uuid4().hex[:8]
    mac = ":".join(suffix[i : i + 2] for i in range(0, 8, 2))
    esp = ESPDevice(
        device_id=device_id,
        name="svc test",
        ip_address=f"10.0.{int(suffix[0:2], 16) % 255}.{int(suffix[2:4], 16) % 255}",
        mac_address=f"02:00:{mac}",
        firmware_version="1.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 4, "max_actuators": 2},
    )
    session.add(esp)
    await session.flush()
    cfg = SensorConfig(
        esp_id=esp.id,
        gpio=4,
        sensor_type="ds18b20",
        sensor_name="Test",
        interface_type="ONEWIRE",
    )
    session.add(cfg)
    data = SensorData(
        esp_id=esp.id,
        gpio=4,
        sensor_type="ds18b20",
        raw_value=22.0,
        processed_value=22.0,
        unit="C",
        processing_mode="raw",
        quality="good",
        timestamp=ts,
        data_source="test",
    )
    session.add(data)
    await session.flush()
    await session.refresh(esp)
    await session.refresh(data)
    return esp, data


async def _seed_actuator_pair(session: AsyncSession, esp: ESPDevice, t0: datetime, t1: datetime):
    on = ActuatorHistory(
        esp_id=esp.id,
        gpio=18,
        actuator_type="pump",
        command_type="set",
        value=1.0,
        issued_by="user:robin",
        success=True,
        timestamp=t0,
        data_source="test",
    )
    off = ActuatorHistory(
        esp_id=esp.id,
        gpio=18,
        actuator_type="pump",
        command_type="stop",
        value=0.0,
        issued_by="user:robin",
        success=True,
        timestamp=t1,
        data_source="test",
    )
    session.add_all([on, off])
    await session.flush()


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
class TestServiceDisabled:
    async def test_export_sensors_returns_skipped(self, session_factory_pair):
        session, factory = session_factory_pair
        settings = _enabled_settings(enabled=False)
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=settings,
            client=_StubClient(),
        )
        result = await svc.export_sensors()
        assert result.status == ExportStatus.SKIPPED_DISABLED
        assert result.rows_written == 0

    async def test_start_does_not_register_job_when_disabled(self, session_factory_pair):
        _, factory = session_factory_pair
        settings = _enabled_settings(enabled=False)
        scheduler = CentralScheduler()
        scheduler.start()
        try:
            svc = SheetsExportService(
                scheduler=scheduler,
                session_factory=factory,
                settings=settings,
                client=_StubClient(),
            )
            assert svc.start() is False
        finally:
            await scheduler.shutdown(wait=False)


@pytest.mark.asyncio
class TestServiceSensorPath:
    async def test_export_sensors_success_advances_cursor(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        esp, data = await _seed_sensor_row(session, ts)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors()
        assert result.status == ExportStatus.SUCCESS
        assert result.rows_written == 1
        assert len(client.appended) == 1
        assert client.appended[0][0] == "sensoren-2026-05"

        # Verify cursor advanced.
        async for s in factory():
            cursor = SheetsExportCursor(s)
            stored = await cursor.get_sensor_cursor()
            assert stored["last_row_id"] == str(data.id)
            assert stored["rows_exported"] == 1
            break

    async def test_export_sensors_failure_keeps_cursor(self, session_factory_pair):
        session, factory = session_factory_pair
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _seed_sensor_row(session, ts)
        await session.commit()

        client = _StubClient(
            raises=NonRetryableSheetsError(
                "403",
                numeric_code=ConfigErrorCode.SHEETS_PERMISSION_DENIED,
            )
        )
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors()
        assert result.status == ExportStatus.FAILED_NON_RETRYABLE
        assert result.error_code == ConfigErrorCode.SHEETS_PERMISSION_DENIED

        # Cursor MUST stay empty.
        async for s in factory():
            cursor = SheetsExportCursor(s)
            stored = await cursor.get_sensor_cursor()
            assert stored["last_row_id"] is None
            break

    async def test_export_sensors_retryable_failure_keeps_cursor(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _seed_sensor_row(session, ts)
        await session.commit()

        client = _StubClient(
            raises=RetryableSheetsError(
                "429",
                numeric_code=ConfigErrorCode.SHEETS_QUOTA_EXCEEDED,
            )
        )
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors()
        assert result.status == ExportStatus.FAILED_RETRYABLE
        assert result.error_code == ConfigErrorCode.SHEETS_QUOTA_EXCEEDED

        async for s in factory():
            cursor = SheetsExportCursor(s)
            stored = await cursor.get_sensor_cursor()
            assert stored["rows_exported"] == 0
            break

    async def test_export_sensors_splits_mixed_month_batch(self, session_factory_pair):
        session, factory = session_factory_pair
        # Europe/Berlin month boundary at 2026-05-31 22:00:00 UTC.
        ts_may = datetime(2026, 5, 31, 21, 59, 0, tzinfo=timezone.utc)
        ts_june = datetime(2026, 5, 31, 22, 1, 0, tzinfo=timezone.utc)
        await _seed_sensor_row(session, ts_may, device_id="ESP_SVC_MIX_1")
        _, june_data = await _seed_sensor_row(session, ts_june, device_id="ESP_SVC_MIX_2")
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors()
        assert result.status == ExportStatus.SUCCESS
        assert result.rows_written == 2
        assert client.appended == [
            ("sensoren-2026-05", 1),
            ("sensoren-2026-06", 1),
        ]

        async for s in factory():
            cursor = SheetsExportCursor(s)
            stored = await cursor.get_sensor_cursor()
            assert stored["last_row_id"] == str(june_data.id)
            assert stored["rows_exported"] == 2
            break

    async def test_dry_run_does_not_commit_cursor(self, session_factory_pair):
        session, factory = session_factory_pair
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _seed_sensor_row(session, ts)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors(dry_run=True)
        assert result.status == ExportStatus.DRY_RUN
        # No persisted cursor change.
        async for s in factory():
            cursor = SheetsExportCursor(s)
            stored = await cursor.get_sensor_cursor()
            assert stored["rows_exported"] == 0
            break

    async def test_export_sensors_splits_batch_by_monthly_tab(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        may_ts = datetime(2026, 5, 31, 23, 59, 30, tzinfo=timezone.utc)
        june_ts = datetime(2026, 6, 1, 0, 0, 30, tzinfo=timezone.utc)
        esp, _ = await _seed_sensor_row(session, may_ts)
        row_june = SensorData(
            esp_id=esp.id,
            gpio=4,
            sensor_type="ds18b20",
            raw_value=23.0,
            processed_value=23.0,
            unit="C",
            processing_mode="raw",
            quality="good",
            timestamp=june_ts,
            data_source="test",
        )
        session.add(row_june)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_sensors()

        assert result.status == ExportStatus.SUCCESS
        assert result.rows_written == 2
        assert client.appended == [("sensoren-2026-05", 1), ("sensoren-2026-06", 1)]
        assert result.tabs_touched == ["sensoren-2026-05", "sensoren-2026-06"]


@pytest.mark.asyncio
class TestServiceActuatorPath:
    async def test_export_actor_history_advances_cursor(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        ts0 = datetime(2026, 5, 23, 11, 0, 0, tzinfo=timezone.utc)
        ts1 = datetime(2026, 5, 23, 11, 0, 30, tzinfo=timezone.utc)
        esp, _ = await _seed_sensor_row(session, ts0)
        await _seed_actuator_pair(session, esp, ts0, ts1)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_actor_history()
        assert result.status == ExportStatus.SUCCESS
        assert result.rows_written == 1
        assert client.appended[0][0] == "aktoren-2026-05"

        async for s in factory():
            cursor = SheetsExportCursor(s)
            history = await cursor.get_history_cursor()
            assert history["rows_exported"] == 1
            open_runs = await cursor.get_open_runs()
            assert open_runs == {}
            break

    async def test_export_actor_history_persists_open_runs_on_open_only(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        ts0 = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
        esp, _ = await _seed_sensor_row(session, ts0)
        # Only ON, no OFF.
        on = ActuatorHistory(
            esp_id=esp.id,
            gpio=18,
            actuator_type="pump",
            command_type="set",
            value=1.0,
            issued_by="user:robin",
            success=True,
            timestamp=ts0,
            data_source="test",
        )
        session.add(on)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_actor_history()
        # No completed run -> nothing written, but open_runs persisted.
        assert result.status == ExportStatus.NOTHING_TO_DO
        assert result.rows_written == 0
        async for s in factory():
            cursor = SheetsExportCursor(s)
            open_runs = await cursor.get_open_runs()
            assert len(open_runs) == 1
            break

    async def test_export_actor_history_splits_batch_by_monthly_tab(
        self,
        session_factory_pair,
    ):
        session, factory = session_factory_pair
        may_on = datetime(2026, 5, 31, 23, 59, 0, tzinfo=timezone.utc)
        may_off = datetime(2026, 5, 31, 23, 59, 30, tzinfo=timezone.utc)
        june_on = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        june_off = datetime(2026, 6, 1, 0, 0, 30, tzinfo=timezone.utc)

        esp, _ = await _seed_sensor_row(session, may_on)
        await _seed_actuator_pair(session, esp, may_on, may_off)
        await _seed_actuator_pair(session, esp, june_on, june_off)
        await session.commit()

        client = _StubClient()
        svc = SheetsExportService(
            scheduler=CentralScheduler(),
            session_factory=factory,
            settings=_enabled_settings(),
            client=client,
        )
        result = await svc.export_actor_history()

        assert result.status == ExportStatus.SUCCESS
        assert result.rows_written == 2
        assert client.appended == [("aktoren-2026-05", 1), ("aktoren-2026-06", 1)]
        assert result.tabs_touched == ["aktoren-2026-05", "aktoren-2026-06"]
