"""Unit tests: ActuatorService.send_command result contract (Epic 1-02)."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from src.db.models.actuator import ActuatorConfig, ActuatorState
from src.db.models.audit_log import AuditLog
from src.db.models.command_contract import CommandIntent, CommandOutcome
from src.db.models.esp import ESPDevice
from src.db.repositories.actuator_repo import ActuatorRepository
from src.db.repositories.audit_log_repo import AuditLogRepository
from src.services.actuator_service import ActuatorService
from src.services.safety_service import SafetyCheckResult, SafetyService


@pytest.fixture(autouse=True)
def clear_emergency_stop_state():
    """Reset SafetyService global E-Stop state before and after each test."""
    SafetyService._global_emergency_stop_active.clear()
    yield
    SafetyService._global_emergency_stop_active.clear()


@pytest.fixture
async def cmd_test_esp_actuator(db_session):
    esp = ESPDevice(
        device_id="ESP_CMDUNIT01",
        name="Cmd Unit",
        ip_address="192.168.1.1",
        mac_address="AA:BB:CC:DD:EE:99",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    ac = ActuatorConfig(
        esp_id=esp.id,
        gpio=5,
        actuator_type="digital",
        actuator_name="Pump",
        enabled=True,
        safety_constraints={},
        actuator_metadata={},
    )
    db_session.add(ac)
    await db_session.commit()
    await db_session.refresh(ac)
    return esp, ac


def _patch_ws():
    mock_manager = MagicMock()
    mock_manager.broadcast = AsyncMock()
    return patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        AsyncMock(return_value=mock_manager),
    )


def _test_session_factory(test_engine):
    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def _factory():
        async with async_session_maker() as session:
            yield session

    return _factory


@pytest.mark.asyncio
async def test_send_command_correlation_id_matches_mqtt_kwarg(
    db_session, test_engine, cmd_test_esp_actuator
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )
    with _patch_ws():
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="OFF",
            value=0.0,
            issued_by="test",
        )
    assert result.success is True
    assert result.command_sent is True
    uuid.UUID(result.correlation_id)
    publisher.publish_actuator_command.assert_called_once()
    kwargs = publisher.publish_actuator_command.call_args.kwargs
    assert kwargs["correlation_id"] == result.correlation_id

    row = (
        await db_session.execute(
            select(CommandIntent).where(CommandIntent.intent_id == result.correlation_id)
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.orchestration_state == "sent"


@pytest.mark.asyncio
async def test_send_command_noop_has_correlation_without_publish(
    db_session, test_engine, cmd_test_esp_actuator
):
    esp, ac = cmd_test_esp_actuator
    db_session.add(
        ActuatorState(
            esp_id=esp.id,
            gpio=ac.gpio,
            actuator_type="digital",
            current_value=0.0,
            state="off",
            runtime_seconds=0,
        )
    )
    await db_session.commit()

    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )
    with _patch_ws():
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="OFF",
            value=0.0,
            issued_by="test",
        )
    assert result.success is True
    assert result.command_sent is False
    uuid.UUID(result.correlation_id)
    publisher.publish_actuator_command.assert_not_called()

    noop_audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.correlation_id == result.correlation_id)
        )
    ).scalar_one_or_none()
    assert noop_audit is not None
    assert noop_audit.event_type == "actuator_command_noop"


@pytest.mark.asyncio
async def test_send_command_propagates_safety_warnings_when_valid(
    db_session, test_engine, cmd_test_esp_actuator
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(
            valid=True,
            warnings=["cooldown_near_limit", "runtime_advisory"],
        )
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )
    with _patch_ws():
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="ON",
            value=1.0,
            issued_by="test",
        )
    assert result.success is True
    assert result.safety_warnings == ["cooldown_near_limit", "runtime_advisory"]


@pytest.mark.asyncio
async def test_send_command_midflow_exception_records_transport_fail(
    db_session,
    test_engine,
    cmd_test_esp_actuator,
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    with (
        _patch_ws(),
        patch.object(
            ActuatorService,
            "_persist_publish_success",
            new_callable=AsyncMock,
            side_effect=RuntimeError("forced mid-flow failure"),
        ),
    ):
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="ON",
            value=1.0,
            issued_by="test",
        )

    assert result.success is False
    assert result.command_sent is False
    transport_intent_id = f"terminal:command_transport_fail:{result.correlation_id.lower()}"
    terminal_row = (
        await db_session.execute(
            select(CommandOutcome).where(CommandOutcome.intent_id == transport_intent_id)
        )
    ).scalar_one_or_none()
    assert terminal_row is not None
    assert terminal_row.outcome == "failed"
    assert terminal_row.is_final is True


@pytest.mark.asyncio
async def test_send_command_parallel_with_stale_injected_session_uses_fresh_context(
    db_session,
    test_engine,
    cmd_test_esp_actuator,
    caplog,
):
    esp, ac = cmd_test_esp_actuator

    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Simulate startup-style stale service wiring: repository holds a closed session.
    stale_session = async_session_maker()
    stale_repo = ActuatorRepository(stale_session)
    await stale_session.close()

    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        stale_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    caplog.set_level("ERROR")
    with (
        _patch_ws(),
        patch.object(
            ActuatorRepository,
            "log_command",
            new_callable=AsyncMock,
        ),
        patch.object(
            AuditLogRepository,
            "log_actuator_command",
            new_callable=AsyncMock,
        ),
    ):
        results = await asyncio.gather(
            *[
                svc.send_command(
                    esp_id=esp.device_id,
                    gpio=ac.gpio,
                    command="ON" if idx % 2 == 0 else "OFF",
                    value=1.0 if idx % 2 == 0 else 0.0,
                    issued_by=f"parallel_{idx}",
                )
                for idx in range(20)
            ]
        )

    assert all(result.success for result in results)
    assert all(result.command_sent for result in results)
    assert "closed transaction" not in caplog.text.lower()


@pytest.mark.asyncio
async def test_send_command_ignores_injected_safetyservice_session_and_uses_fresh_isolation(
    db_session,
    test_engine,
    cmd_test_esp_actuator,
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    esp_repo = MagicMock()
    safety_service = SafetyService(actuator_repo, esp_repo)
    safety_service.validate_actuator_command = AsyncMock(
        side_effect=RuntimeError("must_not_use_injected_safety_service")
    )

    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety_service,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    with _patch_ws():
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="ON",
            value=1.0,
            issued_by="parallel_isolation_test",
        )

    assert result.success is True
    assert result.command_sent is True
    safety_service.validate_actuator_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_command_pre_dispatch_exception_persists_terminal_fail(
    db_session,
    test_engine,
    cmd_test_esp_actuator,
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    with (
        _patch_ws(),
        patch.object(
            ActuatorService,
            "_load_command_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("forced pre-dispatch failure"),
        ),
    ):
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="ON",
            value=1.0,
            issued_by="logic:test_rule",
        )

    assert result.success is False
    assert result.command_sent is False
    terminal_row = (
        await db_session.execute(
            select(CommandOutcome).where(CommandOutcome.intent_id == result.correlation_id)
        )
    ).scalar_one_or_none()
    assert terminal_row is not None
    assert terminal_row.outcome == "failed"
    assert terminal_row.is_final is True
    assert terminal_row.code == "SEND_COMMAND_EXCEPTION_PRE_DISPATCH"


@pytest.mark.asyncio
async def test_send_command_post_dispatch_exception_persists_transport_fail_authority(
    db_session,
    test_engine,
    cmd_test_esp_actuator,
):
    esp, ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publisher.publish_actuator_command.return_value = True
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    with (
        _patch_ws(),
        patch.object(
            ActuatorService,
            "_persist_publish_success",
            new_callable=AsyncMock,
            side_effect=RuntimeError("forced post-dispatch persistence failure"),
        ),
    ):
        result = await svc.send_command(
            esp_id=esp.device_id,
            gpio=ac.gpio,
            command="ON",
            value=1.0,
            issued_by="logic:test_rule",
        )

    assert result.success is False
    assert result.command_sent is False
    transport_intent_id = f"terminal:command_transport_fail:{result.correlation_id.lower()}"
    transport_row = (
        await db_session.execute(
            select(CommandOutcome).where(CommandOutcome.intent_id == transport_intent_id)
        )
    ).scalar_one_or_none()
    assert transport_row is not None
    assert transport_row.outcome == "failed"
    assert transport_row.is_final is True
    assert transport_row.code == "SEND_COMMAND_EXCEPTION_POST_DISPATCH"


@pytest.mark.asyncio
async def test_send_command_serializes_manual_and_logic_on_same_gpio(
    db_session, test_engine, cmd_test_esp_actuator
):
    """Manual REST and logic_engine must not publish MQTT concurrently on one GPIO."""
    esp, _ac = cmd_test_esp_actuator
    actuator_repo = ActuatorRepository(db_session)
    safety = MagicMock()
    safety.validate_actuator_command = AsyncMock(
        return_value=SafetyCheckResult(valid=True, warnings=None)
    )
    publisher = MagicMock()
    publish_trace: list[str] = []
    first_started = asyncio.Event()
    second_may_finish = asyncio.Event()

    async def _serialized_publish(**_kwargs):
        publish_trace.append("enter")
        if len(publish_trace) == 1:
            first_started.set()
            await asyncio.wait_for(second_may_finish.wait(), timeout=2.0)
        publish_trace.append("leave")
        return True

    publisher.publish_actuator_command = AsyncMock(side_effect=_serialized_publish)
    svc = ActuatorService(
        actuator_repo,
        safety,
        publisher,
        session_factory=_test_session_factory(test_engine),
    )

    with _patch_ws():
        task_manual = asyncio.create_task(
            svc.send_command(
                esp.device_id,
                5,
                "ON",
                issued_by="user:robin",
            )
        )
        await asyncio.wait_for(first_started.wait(), timeout=2.0)
        task_logic = asyncio.create_task(
            svc.send_command(
                esp.device_id,
                5,
                "OFF",
                issued_by="logic_engine",
            )
        )
        await asyncio.sleep(0.05)
        assert publish_trace == ["enter"], (
            f"expected single in-flight publish, got trace={publish_trace}"
        )
        second_may_finish.set()
        await asyncio.gather(task_manual, task_logic)

    assert publish_trace == ["enter", "leave", "enter", "leave"]
    assert publisher.publish_actuator_command.await_count == 2
