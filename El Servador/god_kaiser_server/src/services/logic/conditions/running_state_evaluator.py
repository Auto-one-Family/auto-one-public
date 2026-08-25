"""
Not-Running Condition Evaluator (AUT-1245)

Evaluates whether a sequence or actuator is currently idle.
Used as a lightweight feed-interlock via existing trigger_conditions JSON
(AND-chained by CompoundConditionEvaluator) — no new subsystem.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Protocol

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)

_ACTUATOR_RUNNING_STATES = frozenset({"on", "pwm"})


class _SequenceExecutorProto(Protocol):
    def get_running_sequences(self) -> list[Any]: ...


class NotRunningConditionEvaluator(BaseConditionEvaluator):
    """
    Condition is True when the named target is NOT running.

    Condition formats:
        {
            "type": "not_running",
            "target": "sequence",
            "rule_id": "<logic-rule-uuid>"
        }
        {
            "type": "not_running",
            "target": "actuator",
            "esp_id": "<esp-uuid>",
            "gpio": 5
        }

    Dependencies (constructor DI, same pattern as DiagnosticsConditionEvaluator):
        - sequence_executor: SequenceActionExecutor (in-memory running state)
        - session_factory: async session factory for ActuatorRepository.get_state()
    """

    def __init__(
        self,
        sequence_executor: Optional[_SequenceExecutorProto] = None,
        session_factory=None,
    ):
        self._sequence_executor = sequence_executor
        self._session_factory = session_factory

    def supports(self, condition_type: str) -> bool:
        return condition_type == "not_running"

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Returns True when the target is idle (not running).

        Fail-closed: missing config / missing dependencies / read errors → False
        so the interlock does not silently allow concurrent starts.
        """
        target = condition.get("target")
        if target == "sequence":
            return await self._evaluate_sequence(condition)
        if target == "actuator":
            return await self._evaluate_actuator(condition)
        logger.warning("NotRunningConditionEvaluator: unsupported or missing target=%r", target)
        return False

    async def _evaluate_sequence(self, condition: Dict) -> bool:
        rule_id = condition.get("rule_id")
        if not rule_id:
            logger.warning("NotRunningConditionEvaluator: sequence target missing rule_id")
            return False

        if self._sequence_executor is None:
            logger.warning("NotRunningConditionEvaluator: no sequence_executor configured")
            return False

        try:
            running = self._sequence_executor.get_running_sequences()
        except Exception as exc:
            logger.error(
                "NotRunningConditionEvaluator: get_running_sequences failed: %s",
                exc,
                exc_info=True,
            )
            return False

        target_id = str(rule_id)
        for progress in running:
            if str(getattr(progress, "rule_id", "")) == target_id:
                return False
        return True

    async def _evaluate_actuator(self, condition: Dict) -> bool:
        esp_id_raw = condition.get("esp_id")
        gpio_raw = condition.get("gpio")
        if esp_id_raw is None or gpio_raw is None:
            logger.warning("NotRunningConditionEvaluator: actuator target missing esp_id or gpio")
            return False

        if not self._session_factory:
            logger.warning("NotRunningConditionEvaluator: no session factory configured")
            return False

        try:
            esp_id = esp_id_raw if isinstance(esp_id_raw, uuid.UUID) else uuid.UUID(str(esp_id_raw))
            gpio = int(gpio_raw)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "NotRunningConditionEvaluator: invalid esp_id/gpio (%r, %r): %s",
                esp_id_raw,
                gpio_raw,
                exc,
            )
            return False

        try:
            state = await self._get_actuator_state(esp_id, gpio)
        except Exception as exc:
            logger.error(
                "NotRunningConditionEvaluator: failed to read actuator state: %s",
                exc,
                exc_info=True,
            )
            return False

        if state is None:
            # No state row → treat as idle (not on/pwm)
            return True

        return state not in _ACTUATOR_RUNNING_STATES

    async def _get_actuator_state(self, esp_id: uuid.UUID, gpio: int) -> Optional[str]:
        """Read ActuatorState.state via ActuatorRepository.get_state()."""
        from ....db.repositories.actuator_repo import ActuatorRepository

        async for session in self._session_factory():
            repo = ActuatorRepository(session)
            row = await repo.get_state(esp_id, gpio)
            if row is None:
                return None
            return row.state
        return None
