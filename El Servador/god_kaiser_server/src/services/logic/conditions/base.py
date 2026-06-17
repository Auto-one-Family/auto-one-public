"""
Base Condition Evaluator

Abstract base class for condition evaluators.
"""

from abc import ABC, abstractmethod
from typing import Dict


class BaseConditionEvaluator(ABC):
    """
    Abstract base class for condition evaluators.

    Each condition type (sensor, time, etc.) has its own evaluator
    that implements this interface.
    """

    @abstractmethod
    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate a condition.

        Args:
            condition: Condition dictionary
            context: Evaluation context (sensor data, current time, etc.)

        Returns:
            True if condition is met, False otherwise
        """
        pass

    @abstractmethod
    def supports(self, condition_type: str) -> bool:
        """
        Check if this evaluator supports the given condition type.

        Args:
            condition_type: Condition type string (e.g., "sensor_threshold", "time_window")

        Returns:
            True if this evaluator supports the type, False otherwise
        """
        pass
