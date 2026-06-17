"""
Logic Scheduler

Periodically evaluates timer-triggered rules (time_window conditions) and
broadcasts aggregated rule.health snapshots for is_critical rules every
``interval_seconds`` (AUT-115).
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from ..core.logging_config import get_logger
from ..db.session import get_session_maker
from .logic_engine import LogicEngine
from .rule_health_service import RuleHealthService

if TYPE_CHECKING:
    from ..websocket.manager import WebSocketManager

logger = get_logger(__name__)


class LogicScheduler:
    """
    Logic Scheduler for timer-based rule evaluation.

    Periodically checks and evaluates rules with time_window conditions
    and (when configured) broadcasts ``rule.health`` snapshots for all
    safety-critical rules via WebSocket (AUT-115).
    """

    def __init__(
        self,
        logic_engine: LogicEngine,
        interval_seconds: int = 60,
        websocket_manager: Optional["WebSocketManager"] = None,
    ):
        """
        Initialize Logic Scheduler.

        Args:
            logic_engine: LogicEngine instance
            interval_seconds: Evaluation interval in seconds (default: 60)
            websocket_manager: Optional WebSocket manager for rule.health
                broadcasts. If None, broadcasting is disabled (AUT-115).
        """
        self.logic_engine = logic_engine
        self.interval_seconds = interval_seconds
        self._websocket_manager = websocket_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """
        Start scheduler background task.

        Should be called on application startup.
        """
        if self._running:
            logger.warning("Logic Scheduler is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            "Logic Scheduler started (interval: %ss, rule.health broadcast: %s)",
            self.interval_seconds,
            "enabled" if self._websocket_manager else "disabled",
        )

    async def stop(self) -> None:
        """
        Stop scheduler background task.

        Should be called on application shutdown.
        """
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Logic Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """
        Main scheduler loop.

        Runs periodically to evaluate timer-triggered rules and broadcast
        rule.health snapshots (AUT-115).
        """
        logger.info("Logic Scheduler loop started")

        while self._running:
            try:
                # Wait for interval
                await asyncio.sleep(self.interval_seconds)

                # Evaluate timer-triggered rules
                await self._evaluate_timer_rules()

                # AUT-115: Broadcast aggregated rule.health snapshots
                # for all safety-critical rules (best effort).
                if self._websocket_manager is not None:
                    await self._broadcast_rule_health()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                # Wait a bit before retrying to avoid tight error loop
                await asyncio.sleep(5.0)

        logger.info("Logic Scheduler loop stopped")

    async def _evaluate_timer_rules(self) -> None:
        """
        Evaluate all timer-triggered rules.

        Delegates to LogicEngine.evaluate_timer_triggered_rules().
        """
        try:
            await self.logic_engine.evaluate_timer_triggered_rules()
        except Exception as e:
            logger.error(
                f"Error evaluating timer-triggered rules: {e}",
                exc_info=True,
            )

    async def _broadcast_rule_health(self) -> None:
        """
        Build and broadcast rule.health payloads for all is_critical rules.

        Best-effort: any error is logged at WARNING and never aborts the
        scheduler loop (AUT-115).
        """
        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                service = RuleHealthService(session)
                payloads = await service.get_all_critical_rules_health()

            for payload in payloads:
                try:
                    await self._websocket_manager.broadcast(
                        "rule.health",
                        payload.model_dump(mode="json"),
                    )
                except Exception as exc:
                    logger.warning("rule.health broadcast failed: %s", exc)
        except Exception as exc:
            logger.warning("rule.health snapshot build failed: %s", exc)
