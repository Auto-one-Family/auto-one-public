"""
Delay Action Executor

Executes delay actions for sequencing.
"""

import asyncio
from typing import Dict

from ....core.logging_config import get_logger
from .base import ActionResult, BaseActionExecutor

logger = get_logger(__name__)


class DelayActionExecutor(BaseActionExecutor):
    """
    Executes delay actions.

    Supports:
    - Delays between 1 and 3600 seconds
    """

    def supports(self, action_type: str) -> bool:
        """Check if this executor supports delay actions."""
        return action_type == "delay"

    async def execute(self, action: Dict, context: Dict) -> ActionResult:
        """
        Execute delay action.

        Args:
            action: Action dictionary with:
                - type: "delay"
                - seconds: Delay duration in seconds (1-3600)
            context: Execution context (not used for delays)

        Returns:
            ActionResult with execution status
        """
        # Extract delay duration
        seconds = action.get("seconds")

        if seconds is None:
            return ActionResult(
                success=False,
                message="Missing 'seconds' field in delay action",
            )

        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            return ActionResult(
                success=False,
                message=f"Invalid 'seconds' value: {seconds}. Must be an integer",
            )

        # Validate range
        if seconds < 1 or seconds > 3600:
            return ActionResult(
                success=False,
                message=f"Invalid delay duration: {seconds}s. Must be between 1 and 3600 seconds",
            )

        try:
            # NOTE: asyncio.sleep() blocks this rule's action chain intentionally.
            # Other rules (separate asyncio tasks) are unaffected.
            # For non-blocking delay (fire-and-forget next actions), use SequenceActionExecutor.
            logger.debug(f"Delay action: sleeping for {seconds} seconds")
            await asyncio.sleep(seconds)

            return ActionResult(
                success=True,
                message=f"Delay completed: {seconds} seconds",
                data={"seconds": seconds},
            )

        except Exception as e:
            logger.error(
                f"Error executing delay action: {e}",
                exc_info=True,
            )
            return ActionResult(
                success=False,
                message=f"Error executing delay action: {str(e)}",
            )
