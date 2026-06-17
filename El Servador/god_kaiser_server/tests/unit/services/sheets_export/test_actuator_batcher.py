"""
Unit tests for ActuatorExportBatcher (AUT-447 / S5).

Covers all six edge cases mandated by the parent triage:
- ON without OFF -> open_run
- OFF without ON -> off_without_on
- Normal ON/OFF pair
- Emergency-Stop
- LWT-Auto-OFF
- Server restart (open_runs rehydration)
- Double-ON (overlapping_on)

Also verifies the D3 ``ausloeser`` vocabulary mapping and the D8 Option A
correlation with logic_execution_history.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models.actuator import ActuatorHistory
from src.db.models.esp import ESPDevice
from src.db.models.logic import CrossESPLogic, LogicExecutionHistory
from src.services.sheets_export.actuator_batcher import (
    ACTUATOR_HEADER,
    AUSLOESER_EMERGENCY,
    AUSLOESER_LWT,
    ActuatorExportBatcher,
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


async def _make_esp(session: AsyncSession, device_id: str = "ESP_S5_TEST") -> ESPDevice:
    esp = ESPDevice(
        device_id=device_id,
        name="S5 ESP",
        ip_address="192.168.1.20",
        mac_address="AA:BB:CC:DD:EE:55",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 4, "max_actuators": 2},
    )
    session.add(esp)
    await session.flush()
    await session.refresh(esp)
    return esp


async def _add_history(
    session: AsyncSession,
    esp: ESPDevice,
    *,
    gpio: int,
    command_type: str,
    value: float,
    timestamp: datetime,
    issued_by: str = "user:robin",
    success: bool = True,
    metadata: dict | None = None,
    actuator_type: str = "pump",
    error_message: str | None = None,
) -> ActuatorHistory:
    row = ActuatorHistory(
        esp_id=esp.id,
        gpio=gpio,
        actuator_type=actuator_type,
        command_type=command_type,
        value=value,
        issued_by=issued_by,
        success=success,
        error_message=error_message,
        timestamp=timestamp,
        command_metadata=metadata,
        data_source="test",
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


# Build a valid CrossESPLogic rule that survives the model-level Pydantic
# validators (sensor_threshold + actuator_command both require ESP IDs of the
# form ``ESP_<6-8 hex>`` or ``MOCK_<…>`` — strict regex enforced server-side).
_VALID_ESP_ID = "ESP_ABCDEF"


def _make_logic_rule(rule_id: uuid.UUID, rule_name: str) -> CrossESPLogic:
    return CrossESPLogic(
        id=rule_id,
        rule_name=rule_name,
        trigger_conditions={
            "type": "sensor_threshold",
            "esp_id": _VALID_ESP_ID,
            "gpio": 4,
            "sensor_type": "temperature",
            "operator": ">",
            "value": 25.0,
        },
        logic_operator="AND",
        actions=[
            {
                "type": "actuator_command",
                "esp_id": _VALID_ESP_ID,
                "gpio": 18,
                "actuator_type": "pwm",
                "value": 0.5,
            }
        ],
    )


# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPairingEdgeCases:
    async def test_normal_on_off_pair(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 30, tzinfo=timezone.utc)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0)
        await _add_history(session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1)
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.run_start_utc == t0
        assert row.run_end_utc == t1
        assert row.duration_seconds == 30
        assert row.ausloeser == "manual:user:robin"
        assert row.notes == ""
        assert batch.open_runs_after == {}

    async def test_on_without_off_keeps_run_open(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by="logic:11111111-1111-1111-1111-111111111111",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        # No completed runs emitted, but open_runs should track this.
        assert batch.is_empty()
        key = f"{esp.id}:18"
        assert key in batch.open_runs_after

    async def test_off_without_on_emits_isolated_row(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t0,
            issued_by="system:lwt_disconnect",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.run_start_utc is None
        assert row.run_end_utc == t0
        assert row.duration_seconds is None
        assert row.notes == "off_without_on"
        assert row.ausloeser == AUSLOESER_LWT

    async def test_emergency_stop_overrides_ausloeser(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 5, tzinfo=timezone.utc)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0)
        await _add_history(
            session, esp, gpio=18, command_type="emergency_stop", value=0.0, timestamp=t1,
            issued_by="emergency:robin",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.ausloeser == AUSLOESER_EMERGENCY
        assert "emergency_stop" in row.notes

    async def test_lwt_auto_off_closes_run(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 10, tzinfo=timezone.utc)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0)
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1,
            issued_by="system:lwt_disconnect",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.ausloeser == AUSLOESER_LWT
        assert "lwt_offline" in row.notes

    async def test_overlapping_on_closes_previous(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 5, tzinfo=timezone.utc)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t1)
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.run_start_utc == t0
        assert row.run_end_utc == t1
        assert row.notes == "overlapping_on"

    async def test_restart_recovery_via_open_runs(self, session: AsyncSession):
        esp = await _make_esp(session)
        prior_start = datetime(2026, 5, 23, 9, 0, 0, tzinfo=timezone.utc)
        key = f"{esp.id}:18"
        open_runs = {
            key: {
                "start_id": str(uuid.uuid4()),
                "start_ts": prior_start.isoformat(),
                "issued_by": "user:robin",
                "value": 1.0,
                "ausloeser": "manual:user:robin",
                "notes": "",
            }
        }
        t_off = datetime(2026, 5, 23, 9, 0, 45, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t_off
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None,
            last_id=None,
            limit=100,
            open_runs=open_runs,
        )
        assert len(batch.rows) == 1
        row = batch.rows[0]
        assert row.run_start_utc == prior_start
        assert row.duration_seconds == 45
        assert key not in batch.open_runs_after


# -----------------------------------------------------------------------------
# ausloeser vocabulary (D3 freeze)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAusloeserVocabulary:
    async def test_logic_rule_with_known_name(self, session: AsyncSession):
        esp = await _make_esp(session)
        rule_id = uuid.uuid4()
        rule = _make_logic_rule(rule_id, "Pumpe-Bewaesserung")
        session.add(rule)
        await session.flush()

        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 30, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by=f"logic:{rule_id}",
        )
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1,
            issued_by=f"logic:{rule_id}",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert len(batch.rows) == 1
        assert batch.rows[0].ausloeser == f"rule:{rule_id}:Pumpe-Bewaesserung"

    async def test_offline_marker_maps_to_offline_gpio(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 5, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by="system:offline_safe",
        )
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1,
            issued_by="system:offline_safe",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert batch.rows[0].ausloeser == "offline:18"

    async def test_api_user_maps_to_manual(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 5, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by="api:dashboard",
        )
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1,
            issued_by="api:dashboard",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert batch.rows[0].ausloeser == "manual:api:dashboard"

    async def test_empty_issued_by_falls_back_to_manual_unknown(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t0,
            issued_by="",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert batch.rows[0].ausloeser == "manual:unknown"


# -----------------------------------------------------------------------------
# D8 correlation (Option A)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
class TestD8Correlation:
    async def test_correlation_id_match_preserves_rule_label(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        rule_id = uuid.uuid4()
        rule = _make_logic_rule(rule_id, "Wasser-Pumpe")
        session.add(rule)
        await session.flush()

        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 30, tzinfo=timezone.utc)
        corr = str(uuid.uuid4())
        execution = LogicExecutionHistory(
            logic_rule_id=rule_id,
            trigger_data={"sensor": "soil"},
            actions_executed=[{"actuator": 18}],
            success=True,
            execution_time_ms=10,
            timestamp=t0,
            execution_metadata={"correlation_id": corr},
        )
        session.add(execution)
        await session.flush()

        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by=f"logic:{rule_id}",
            metadata={"correlation_id": corr},
        )
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1,
            issued_by=f"logic:{rule_id}",
            metadata={"correlation_id": corr},
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session, correlation_window_seconds=60)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert batch.rows[0].ausloeser == f"rule:{rule_id}:Wasser-Pumpe"

    async def test_window_match_without_correlation_id_still_resolves_name(
        self,
        session: AsyncSession,
    ):
        esp = await _make_esp(session)
        rule_id = uuid.uuid4()
        rule = _make_logic_rule(rule_id, "Fan")
        session.add(rule)
        await session.flush()

        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        execution = LogicExecutionHistory(
            logic_rule_id=rule_id,
            trigger_data={"sensor": "temperature"},
            actions_executed=[{"actuator": 18}],
            success=True,
            execution_time_ms=10,
            timestamp=t0,
            execution_metadata={},
        )
        session.add(execution)
        await session.flush()

        await _add_history(
            session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0,
            issued_by=f"logic:{rule_id}",
        )
        await _add_history(
            session, esp, gpio=18, command_type="stop", value=0.0,
            timestamp=t0.replace(second=20),
            issued_by=f"logic:{rule_id}",
        )
        await session.commit()

        batcher = ActuatorExportBatcher(session, correlation_window_seconds=120)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        assert batch.rows[0].ausloeser == f"rule:{rule_id}:Fan"


@pytest.mark.asyncio
class TestActuatorBatchSerialization:
    async def test_to_sheet_values_matches_header(self, session: AsyncSession):
        esp = await _make_esp(session)
        t0 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 5, 23, 10, 0, 12, tzinfo=timezone.utc)
        await _add_history(session, esp, gpio=18, command_type="set", value=1.0, timestamp=t0)
        await _add_history(session, esp, gpio=18, command_type="stop", value=0.0, timestamp=t1)
        await session.commit()

        batcher = ActuatorExportBatcher(session)
        batch = await batcher.fetch_batch(
            last_timestamp_iso=None, last_id=None, limit=100, open_runs={}
        )
        rows = batch.to_sheet_values()
        assert len(rows) == 1
        sheet_row = rows[0]
        assert len(sheet_row) == len(ACTUATOR_HEADER)
        assert sheet_row[0] == t0.isoformat()
        assert sheet_row[1] == t1.isoformat()
        assert sheet_row[2] == 12
        assert sheet_row[3] == "ESP_S5_TEST"
        assert sheet_row[4] == 18
        assert sheet_row[5] == "pump"
        assert sheet_row[7] == "success"
