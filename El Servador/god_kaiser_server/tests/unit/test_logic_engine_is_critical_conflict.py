"""AUT-1336 Option A: rule.is_critical feeds existing ConflictManager safety path."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic.safety.conflict_manager import ConflictManager
from src.services.logic_engine import LogicEngine


def _make_engine() -> LogicEngine:
    engine = LogicEngine(
        logic_repo=MagicMock(),
        actuator_service=MagicMock(),
        websocket_manager=AsyncMock(),
        conflict_manager=ConflictManager(websocket_manager=AsyncMock()),
        condition_evaluators=[],
        action_executors=[],
    )
    mock_executor = MagicMock()
    mock_executor.supports = MagicMock(return_value=True)
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.message = "OK"
    mock_result.data = {"noop": False}
    mock_executor.execute = AsyncMock(return_value=mock_result)
    engine.action_executors = [mock_executor]
    return engine


def _actuator(esp_id: str, gpio: int, command: str = "ON", **extra: object) -> dict:
    return {
        "type": "actuator_command",
        "esp_id": esp_id,
        "gpio": gpio,
        "command": command,
        "duration_seconds": 5,
        **extra,
    }


def _esp_online(esp_id: str) -> tuple[MagicMock, AsyncMock, AsyncMock]:
    mock_esp = MagicMock()
    mock_esp.is_online = True
    mock_esp.config_pending = False
    mock_esp.device_id = esp_id
    mock_repo = AsyncMock()
    mock_repo.get_by_device_id = AsyncMock(return_value=mock_esp)
    mock_adoption = AsyncMock()
    mock_adoption.is_adoption_completed = AsyncMock(return_value=True)
    return mock_repo, mock_adoption, AsyncMock()


@pytest.mark.asyncio
async def test_execute_actions_passes_rule_is_critical_into_acquire():
    """Wiring point: rule_is_critical ORs into acquire_actuator is_safety_critical."""
    engine = _make_engine()
    rule_id = uuid.uuid4()
    acquire = AsyncMock(return_value=(True, None))
    engine.conflict_manager.acquire_actuator = acquire
    mock_repo, mock_adoption, mock_session = _esp_online("ESP_W")

    with (
        patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
        patch("src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption),
    ):
        await engine._execute_actions(
            [_actuator("ESP_W", 10)],
            {"type": "test"},
            rule_id,
            "critical-rule",
            rule_priority=40,
            rule_is_critical=True,
            session=mock_session,
            batch_locks=[],
        )

    assert acquire.await_count == 1
    kwargs = acquire.await_args.kwargs
    assert kwargs["is_safety_critical"] is True
    assert kwargs["priority"] == 40
    assert kwargs["rule_id"] == str(rule_id)


@pytest.mark.asyncio
async def test_execute_actions_default_rule_is_critical_false_unchanged():
    """Backward-compatible default: no rule flag → action flag only."""
    engine = _make_engine()
    acquire = AsyncMock(return_value=(True, None))
    engine.conflict_manager.acquire_actuator = acquire
    mock_repo, mock_adoption, mock_session = _esp_online("ESP_W")

    with (
        patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
        patch("src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption),
    ):
        await engine._execute_actions(
            [_actuator("ESP_W", 11)],
            {"type": "test"},
            uuid.uuid4(),
            "normal-rule",
            rule_priority=10,
            session=mock_session,
            batch_locks=[],
        )

    assert acquire.await_args.kwargs["is_safety_critical"] is False


@pytest.mark.asyncio
async def test_critical_rule_wins_over_non_critical_same_actuator():
    """Live-shape: same esp:gpio — critical challenger overrides non-critical holder."""
    engine = _make_engine()
    esp_id = "ESP_CRIT_001"
    gpio = 16
    holder_id = uuid.uuid4()
    critical_id = uuid.uuid4()

    await engine.conflict_manager.acquire_actuator(
        esp_id=esp_id,
        gpio=gpio,
        rule_id=str(holder_id),
        priority=1,
        command="ON",
        is_safety_critical=False,
    )
    # Same OR as _execute_actions: action flag False, rule_is_critical True.
    ok, _conflict = await engine.conflict_manager.acquire_actuator(
        esp_id=esp_id,
        gpio=gpio,
        rule_id=str(critical_id),
        priority=50,
        command="OFF",
        is_safety_critical=True,
    )
    assert ok is True
    lock = engine.conflict_manager._locks[f"{esp_id}:{gpio}"]
    assert lock.rule_id == str(critical_id)
    assert lock.is_safety_critical is True


@pytest.mark.asyncio
async def test_action_is_safety_critical_or_preserved():
    """Action-level is_safety_critical still wins when rule_is_critical is False."""
    engine = _make_engine()
    acquire = AsyncMock(return_value=(True, None))
    engine.conflict_manager.acquire_actuator = acquire
    mock_repo, mock_adoption, mock_session = _esp_online("ESP_W")

    with (
        patch("src.services.logic_engine.ESPRepository", return_value=mock_repo),
        patch("src.services.logic_engine.get_state_adoption_service", return_value=mock_adoption),
    ):
        await engine._execute_actions(
            [_actuator("ESP_W", 12, is_safety_critical=True)],
            {"type": "test"},
            uuid.uuid4(),
            "action-safety",
            rule_priority=99,
            rule_is_critical=False,
            session=mock_session,
            batch_locks=[],
        )

    assert acquire.await_args.kwargs["is_safety_critical"] is True
