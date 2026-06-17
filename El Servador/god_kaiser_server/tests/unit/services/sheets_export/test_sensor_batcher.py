"""
Unit tests for SensorExportBatcher (AUT-445 / S4).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig, SensorData
from src.services.sheets_export.sensor_batcher import (
    SENSOR_HEADER,
    SensorExportBatcher,
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


async def _make_esp(session: AsyncSession, device_id: str = "ESP_S4_TEST") -> ESPDevice:
    esp = ESPDevice(
        device_id=device_id,
        name="S4 test ESP",
        ip_address="192.168.1.10",
        mac_address="AA:BB:CC:DD:EE:99",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 4, "max_actuators": 2},
    )
    session.add(esp)
    await session.flush()
    await session.refresh(esp)
    return esp


async def _make_sensor_config(
    session: AsyncSession,
    esp: ESPDevice,
    gpio: int,
    sensor_type: str,
    name: str,
    onewire: str | None = None,
    i2c: int | None = None,
) -> SensorConfig:
    cfg = SensorConfig(
        esp_id=esp.id,
        gpio=gpio,
        sensor_type=sensor_type,
        sensor_name=name,
        interface_type="ANALOG",
        onewire_address=onewire,
        i2c_address=i2c,
    )
    session.add(cfg)
    await session.flush()
    await session.refresh(cfg)
    return cfg


async def _make_sensor_data(
    session: AsyncSession,
    esp: ESPDevice,
    gpio: int,
    sensor_type: str,
    *,
    value: float,
    timestamp: datetime,
    unit: str = "C",
    zone_id: str | None = None,
    subzone_id: str | None = None,
) -> SensorData:
    data = SensorData(
        esp_id=esp.id,
        gpio=gpio,
        sensor_type=sensor_type,
        raw_value=value,
        processed_value=value,
        unit=unit,
        processing_mode="raw",
        quality="good",
        timestamp=timestamp,
        zone_id=zone_id,
        subzone_id=subzone_id,
        data_source="test",
    )
    session.add(data)
    await session.flush()
    await session.refresh(data)
    return data


@pytest.mark.asyncio
class TestSensorBatcherFetch:
    async def test_empty_table_returns_empty_batch(self, session: AsyncSession):
        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100
        )
        assert batch.is_empty() is True
        assert batch.rows == []

    async def test_fetch_returns_rows_with_enriched_columns(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        await _make_sensor_config(
            session, esp, gpio=4, sensor_type="ds18b20", name="Wurzel-Temp",
            onewire="28FF82F110C78897",
        )
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _make_sensor_data(
            session, esp, gpio=4, sensor_type="ds18b20",
            value=22.5, timestamp=ts, unit="C", zone_id="zone-a",
        )
        await session.commit()

        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.sensor_type == "ds18b20"
        assert row.sensor_label == "Wurzel-Temp"
        assert row.onewire_address == "28FF82F110C78897"
        assert row.i2c_address == ""
        assert row.value == 22.5
        assert row.unit == "C"
        assert row.zone_id == "zone-a"
        assert row.esp_device_id == "ESP_S4_TEST"

    async def test_cursor_anchor_skips_already_exported(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        await _make_sensor_config(
            session, esp, gpio=5, sensor_type="ph_v2", name="pH"
        )
        ts1 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 5, 23, 10, 0, 30, tzinfo=timezone.utc)
        row1 = await _make_sensor_data(
            session, esp, gpio=5, sensor_type="ph_v2", value=6.5, timestamp=ts1
        )
        await _make_sensor_data(
            session, esp, gpio=5, sensor_type="ph_v2", value=6.6, timestamp=ts2
        )
        await session.commit()

        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=ts1.isoformat(),
            last_id=str(row1.id),
            limit=10,
        )
        assert len(batch.rows) == 1
        assert batch.rows[0].value == 6.6

    async def test_i2c_address_is_hex_formatted(self, session: AsyncSession):
        esp = await _make_esp(session)
        await _make_sensor_config(
            session, esp, gpio=21, sensor_type="sht31_temp", name="SHT31-T",
            i2c=0x44,
        )
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _make_sensor_data(
            session, esp, gpio=21, sensor_type="sht31_temp",
            value=21.3, timestamp=ts, unit="C",
        )
        await session.commit()

        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=10
        )
        assert batch.rows[0].i2c_address == "0x44"

    async def test_multi_value_sensor_produces_separate_rows(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        # SHT31 multi-value: same gpio, different sensor_type, same i2c
        await _make_sensor_config(
            session, esp, gpio=21, sensor_type="sht31_temp", name="SHT31-T",
            i2c=0x44,
        )
        await _make_sensor_config(
            session, esp, gpio=21, sensor_type="sht31_humidity", name="SHT31-H",
            i2c=0x44,
        )
        ts = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _make_sensor_data(
            session, esp, gpio=21, sensor_type="sht31_temp",
            value=22.0, timestamp=ts, unit="C",
        )
        await _make_sensor_data(
            session, esp, gpio=21, sensor_type="sht31_humidity",
            value=55.0, timestamp=ts, unit="%",
        )
        await session.commit()

        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=10
        )
        types = {row.sensor_type for row in batch.rows}
        assert types == {"sht31_temp", "sht31_humidity"}
        assert all(row.i2c_address == "0x44" for row in batch.rows)


@pytest.mark.asyncio
class TestSensorBatchSerialization:
    async def test_to_sheet_values_uses_header_order(self, session: AsyncSession):
        esp = await _make_esp(session)
        await _make_sensor_config(
            session, esp, gpio=4, sensor_type="ds18b20", name="Test"
        )
        ts = datetime(2026, 5, 23, 8, 0, 0, tzinfo=timezone.utc)
        await _make_sensor_data(
            session, esp, gpio=4, sensor_type="ds18b20",
            value=20.0, timestamp=ts, unit="C",
        )
        await session.commit()

        batcher = SensorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=10
        )
        rows = batch.to_sheet_values()
        assert len(rows) == 1
        sheet_row = rows[0]
        assert len(sheet_row) == len(SENSOR_HEADER)
        # timestamp_utc first
        assert sheet_row[0] == ts.isoformat()
        # esp_id third
        assert sheet_row[2] == "ESP_S4_TEST"
        # gpio fourth
        assert sheet_row[3] == 4
        # value (index 8)
        assert sheet_row[8] == 20.0
