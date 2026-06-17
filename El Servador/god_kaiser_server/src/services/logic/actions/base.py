"""
Base Action Executor

Abstract base class for action executors.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ActionResult:
    """Result of action execution."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.message = message
        self.data = data or {}


class BaseActionExecutor(ABC):
    """
    Abstract base class for action executors.

    Each action type (actuator, notification, delay, etc.) has its own executor
    that implements this interface.
    """

    @abstractmethod
    async def execute(self, action: Dict, context: Dict) -> ActionResult:
        """
        Execute an action.

        Args:
            action: Action dictionary
            context: Execution context (rule info, trigger data, etc.)

        Returns:
            ActionResult with execution status
        """
        pass

    @abstractmethod
    def supports(self, action_type: str) -> bool:
        """
        Check if this executor supports the given action type.

        Args:
            action_type: Action type string (e.g., "actuator_command", "notification")

        Returns:
            True if this executor supports the type, False otherwise
        """
        pass
