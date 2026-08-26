"""
Unit tests: NotRunningConditionEvaluator (AUT-1245)

Covers the three Given/When/Then cases from AUT-1244:
1. Feed actuator running → Angleich not_running(actuator) is False
2. Angleich sequence running → Feed not_running(sequence) is False
3. Neither running → both not_running conditions are True
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic.conditions.running_state_evaluator import (
    NotRunningConditionEvaluator,
)


class _FakeSequenceExecutor:
    def __init__(self, running_rule_ids: Optional[List[str]] = None):
        self._running = [
            SimpleNamespace(rule_id=rid) for rid in (running_rule_ids or [])
        ]

    def get_running_sequences(self) -> list[Any]:
        return list(self._running)


def _session_factory_returning(state_row: Any):
    """Build an async session-factory that yields one session (unused by mock repo)."""

    async def _factory():
        session = MagicMock()
        yield session

    return _factory


class TestNotRunningConditionEvaluatorSupports:
    def test_supports_not_running(self):
        evaluator = NotRunningConditionEvaluator()
        assert evaluator.supports("not_running") is True
        assert evaluator.supports("sensor_threshold") is False


class TestNotRunningSequenceTarget:
    """GWT 2 + 3 (sequence half): Angleich running blocks Feed; idle allows."""

    @pytest.mark.asyncio
    async def test_sequence_running_returns_false(self):
        """Given Angleich sequence running, When Feed evaluates not_running(sequence), Then False."""
        angleich_rule_id = str(uuid.uuid4())
        evaluator = NotRunningConditionEvaluator(
            sequence_executor=_FakeSequenceExecutor([angleich_rule_id]),
        )
        condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": angleich_rule_id,
        }
        assert await evaluator.evaluate(condition, {}) is False

    @pytest.mark.asyncio
    async def test_sequence_idle_returns_true(self):
        """Given neither running, When Feed evaluates not_running(sequence), Then True."""
        angleich_rule_id = str(uuid.uuid4())
        evaluator = NotRunningConditionEvaluator(
            sequence_executor=_FakeSequenceExecutor([]),
        )
        condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": angleich_rule_id,
        }
        assert await evaluator.evaluate(condition, {}) is True

    @pytest.mark.asyncio
    async def test_sequence_other_rule_running_returns_true(self):
        """A different running sequence does not block the configured rule_id."""
        evaluator = NotRunningConditionEvaluator(
            sequence_executor=_FakeSequenceExecutor([str(uuid.uuid4())]),
        )
        condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": str(uuid.uuid4()),
        }
        assert await evaluator.evaluate(condition, {}) is True

    @pytest.mark.asyncio
    async def test_sequence_missing_rule_id_returns_false(self):
        evaluator = NotRunningConditionEvaluator(
            sequence_executor=_FakeSequenceExecutor([]),
        )
        assert (
            await evaluator.evaluate({"type": "not_running", "target": "sequence"}, {})
            is False
        )

    @pytest.mark.asyncio
    async def test_sequence_missing_executor_returns_false(self):
        evaluator = NotRunningConditionEvaluator(sequence_executor=None)
        condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": str(uuid.uuid4()),
        }
        assert await evaluator.evaluate(condition, {}) is False


class TestNotRunningActuatorTarget:
    """GWT 1 + 3 (actuator half): Feed on blocks Angleich; idle allows."""

    @pytest.mark.asyncio
    async def test_actuator_on_returns_false(self):
        """Given Feed pump running (state=on), When Angleich evaluates not_running(actuator), Then False."""
        esp_id = uuid.uuid4()
        state_row = SimpleNamespace(state="on")
        evaluator = NotRunningConditionEvaluator(
            session_factory=_session_factory_returning(state_row),
        )

        with patch(
            "src.db.repositories.actuator_repo.ActuatorRepository.get_state",
            new=AsyncMock(return_value=state_row),
        ):
            result = await evaluator.evaluate(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": str(esp_id),
                    "gpio": 5,
                },
                {},
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_actuator_pwm_returns_false(self):
        esp_id = uuid.uuid4()
        state_row = SimpleNamespace(state="pwm")
        evaluator = NotRunningConditionEvaluator(
            session_factory=_session_factory_returning(state_row),
        )

        with patch(
            "src.db.repositories.actuator_repo.ActuatorRepository.get_state",
            new=AsyncMock(return_value=state_row),
        ):
            result = await evaluator.evaluate(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": esp_id,
                    "gpio": 5,
                },
                {},
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_actuator_off_returns_true(self):
        """Given neither running (Feed off), When Angleich evaluates not_running(actuator), Then True."""
        esp_id = uuid.uuid4()
        state_row = SimpleNamespace(state="off")
        evaluator = NotRunningConditionEvaluator(
            session_factory=_session_factory_returning(state_row),
        )

        with patch(
            "src.db.repositories.actuator_repo.ActuatorRepository.get_state",
            new=AsyncMock(return_value=state_row),
        ):
            result = await evaluator.evaluate(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": str(esp_id),
                    "gpio": 5,
                },
                {},
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_actuator_no_state_row_returns_true(self):
        esp_id = uuid.uuid4()
        evaluator = NotRunningConditionEvaluator(
            session_factory=_session_factory_returning(None),
        )

        with patch(
            "src.db.repositories.actuator_repo.ActuatorRepository.get_state",
            new=AsyncMock(return_value=None),
        ):
            result = await evaluator.evaluate(
                {
                    "type": "not_running",
                    "target": "actuator",
                    "esp_id": str(esp_id),
                    "gpio": 5,
                },
                {},
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_actuator_missing_session_factory_returns_false(self):
        evaluator = NotRunningConditionEvaluator(session_factory=None)
        result = await evaluator.evaluate(
            {
                "type": "not_running",
                "target": "actuator",
                "esp_id": str(uuid.uuid4()),
                "gpio": 5,
            },
            {},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_actuator_missing_gpio_returns_false(self):
        evaluator = NotRunningConditionEvaluator(
            session_factory=_session_factory_returning(None),
        )
        result = await evaluator.evaluate(
            {
                "type": "not_running",
                "target": "actuator",
                "esp_id": str(uuid.uuid4()),
            },
            {},
        )
        assert result is False


class TestNotRunningGwtBothSides:
    """GWT 3 end-to-end: both conditions True when neither side is active."""

    @pytest.mark.asyncio
    async def test_neither_running_both_conditions_true(self):
        angleich_rule_id = str(uuid.uuid4())
        feed_esp_id = uuid.uuid4()
        state_row = SimpleNamespace(state="off")

        evaluator = NotRunningConditionEvaluator(
            sequence_executor=_FakeSequenceExecutor([]),
            session_factory=_session_factory_returning(state_row),
        )

        sequence_condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": angleich_rule_id,
        }
        actuator_condition = {
            "type": "not_running",
            "target": "actuator",
            "esp_id": str(feed_esp_id),
            "gpio": 12,
        }

        assert await evaluator.evaluate(sequence_condition, {}) is True

        with patch(
            "src.db.repositories.actuator_repo.ActuatorRepository.get_state",
            new=AsyncMock(return_value=state_row),
        ):
            assert await evaluator.evaluate(actuator_condition, {}) is True


class TestNotRunningRegistration:
    """Smoke: default LogicEngine wiring includes not_running evaluator."""

    def test_logic_engine_registers_not_running_in_both_lists(self):
        from src.services.logic.conditions.compound_evaluator import (
            CompoundConditionEvaluator,
        )
        from src.services.logic_engine import LogicEngine

        logic_repo = MagicMock()
        actuator_service = MagicMock()
        websocket_manager = MagicMock()

        engine = LogicEngine(
            logic_repo=logic_repo,
            actuator_service=actuator_service,
            websocket_manager=websocket_manager,
            session_factory=None,
        )

        not_running = [
            e
            for e in engine.condition_evaluators
            if isinstance(e, NotRunningConditionEvaluator)
        ]
        assert len(not_running) == 1

        compounds = [
            e
            for e in engine.condition_evaluators
            if isinstance(e, CompoundConditionEvaluator)
        ]
        assert len(compounds) == 1
        compound_has = any(
            isinstance(e, NotRunningConditionEvaluator)
            for e in compounds[0].evaluators
        )
        assert compound_has is True

        # Shared SequenceActionExecutor instance between condition eval and actions
        from src.services.logic.actions import SequenceActionExecutor

        seq_executors = [
            e for e in engine.action_executors if isinstance(e, SequenceActionExecutor)
        ]
        assert len(seq_executors) == 1
        assert not_running[0]._sequence_executor is seq_executors[0]
