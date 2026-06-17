import pytest

from src.services.runtime_state_service import RuntimeMode, RuntimeStateService


@pytest.mark.asyncio
async def test_runtime_state_readiness_requires_all_guards():
    service = RuntimeStateService()
    await service.transition(RuntimeMode.WARMING_UP, "test setup")
    await service.transition(RuntimeMode.RECOVERY_SYNC, "test setup")
    await service.set_logic_liveness(True)
    await service.set_worker_health("mqtt_subscriber", True)
    await service.set_worker_health("websocket_manager", True)
    await service.set_worker_health("inbound_replay_worker", True)
    await service.set_recovery_completed(True)
    await service.transition(RuntimeMode.NORMAL_OPERATION, "test ready")

    snapshot = await service.snapshot()
    assert snapshot["mode"] == RuntimeMode.NORMAL_OPERATION.value
    assert snapshot["ready"] is True


@pytest.mark.asyncio
async def test_runtime_state_blocks_invalid_transition():
    service = RuntimeStateService()
    await service.transition(RuntimeMode.SHUTDOWN_DRAIN, "shutdown")
    await service.transition(RuntimeMode.NORMAL_OPERATION, "must be blocked")
    snapshot = await service.snapshot()
    assert snapshot["mode"] == RuntimeMode.SHUTDOWN_DRAIN.value


@pytest.mark.asyncio
async def test_runtime_state_not_ready_with_active_degraded_reason():
    service = RuntimeStateService()
    await service.transition(RuntimeMode.WARMING_UP, "test setup")
    await service.transition(RuntimeMode.RECOVERY_SYNC, "test setup")
    await service.set_logic_liveness(True)
    await service.set_worker_health("mqtt_subscriber", True)
    await service.set_worker_health("websocket_manager", True)
    await service.set_worker_health("inbound_replay_worker", True)
    await service.set_recovery_completed(True)
    await service.set_degraded_reason("persist_guard_block", True)
    await service.transition(RuntimeMode.NORMAL_OPERATION, "test blocked")

    snapshot = await service.snapshot()
    assert snapshot["mode"] == RuntimeMode.NORMAL_OPERATION.value
    assert snapshot["ready"] is False
    assert "persist_guard_block" in snapshot["degraded_reason_codes"]
