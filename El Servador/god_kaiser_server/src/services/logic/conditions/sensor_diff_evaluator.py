"""
Sensor Pair Difference Evaluator

Evaluates sensor_diff conditions: triggers when the difference between
two sensor values meets threshold criteria.

Pattern: (sensor_b_value - sensor_a_value) [operator] threshold
"""

from typing import Dict
from datetime import datetime, timezone

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)

# State tracking for consecutive_count
# Key: f"{condition_hash}", Value: {"count": int, "last_exceeded": datetime}
_diff_state_cache: dict[str, dict] = {}


def _get_condition_hash(condition: Dict) -> str:
    """Generate unique hash for condition state tracking."""
    a_id = condition["sensor_a_id"]
    b_id = condition["sensor_b_id"]
    op = condition.get("operator")
    val = condition.get("value")
    return f"{a_id}:{b_id}:{op}:{val}"


class SensorDiffConditionEvaluator(BaseConditionEvaluator):
    """
    Evaluates sensor pair difference conditions.

    Supports:
    - Comparison operators: >, <, >=, <=, ==, !=
    - Consecutive count threshold (count number of measurements exceeding threshold)
    - Cross-ESP sensor references via context["sensor_values"]
    """

    def supports(self, condition_type: str) -> bool:
        """Check if this evaluator supports sensor_diff conditions."""
        return condition_type == "sensor_diff"

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate sensor pair difference condition.

        Difference = sensor_b_value - sensor_a_value
        Triggers when difference [operator] threshold for consecutive_count measurements.

        Args:
            condition: Condition dictionary with:
                - type: "sensor_diff"
                - sensor_a_id: UUID of first sensor
                - sensor_b_id: UUID of second sensor
                - operator: Comparison operator (>, <, >=, <=, ==, !=)
                - value: Threshold value
                - consecutive_count: Number of consecutive measurements (default 1)
            context: Evaluation context with:
                - sensor_values: Dict of pre-loaded sensor values
                  Key format: "sensor_uuid", Value: {"value": float, ...}

        Returns:
            True if condition is met (difference meets threshold for consecutive_count measurements)
        """
        sensor_a_id = condition.get("sensor_a_id")
        sensor_b_id = condition.get("sensor_b_id")
        operator = condition.get("operator")
        threshold = condition.get("value")
        consecutive_count = condition.get("consecutive_count", 1)

        # Validate inputs
        if not all([sensor_a_id, sensor_b_id, operator, threshold is not None]):
            logger.warning(
                f"Incomplete sensor_diff condition: "
                f"sensor_a={sensor_a_id}, sensor_b={sensor_b_id}, "
                f"op={operator}, threshold={threshold}"
            )
            return False

        # Get sensor values from context
        sensor_values = context.get("sensor_values", {})

        # Lookup sensor values
        sensor_a_data = sensor_values.get(sensor_a_id)
        sensor_b_data = sensor_values.get(sensor_b_id)

        if sensor_a_data is None or sensor_b_data is None:
            logger.debug(
                f"Missing sensor data for diff condition: "
                f"A={sensor_a_id} ({sensor_a_data is not None}), "
                f"B={sensor_b_id} ({sensor_b_data is not None})"
            )
            return False

        # Extract values
        try:
            value_a = float(sensor_a_data.get("value"))
            value_b = float(sensor_b_data.get("value"))
        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Invalid numeric values for sensor_diff: {e}")
            return False

        # Calculate difference
        diff = value_b - value_a

        # Evaluate comparison
        if not self._compare(operator, diff, threshold):
            # Reset count if threshold not met
            cond_hash = _get_condition_hash(condition)
            if cond_hash in _diff_state_cache:
                del _diff_state_cache[cond_hash]
            return False

        # Threshold met - track consecutive count
        cond_hash = _get_condition_hash(condition)
        current_state = _diff_state_cache.get(cond_hash, {"count": 0, "last_exceeded": None})
        current_state["count"] += 1
        current_state["last_exceeded"] = datetime.now(timezone.utc)
        _diff_state_cache[cond_hash] = current_state

        # Check if consecutive_count reached
        if current_state["count"] >= consecutive_count:
            logger.info(
                f"Sensor diff condition triggered: "
                f"({sensor_b_id} - {sensor_a_id}) = {diff:.3f} {operator} {threshold} "
                f"(count: {current_state['count']}/{consecutive_count})"
            )
            return True

        logger.debug(
            f"Sensor diff threshold met but awaiting consecutive count: "
            f"{current_state['count']}/{consecutive_count}"
        )
        return False

    def _compare(self, operator: str, actual_diff: float, threshold: float) -> bool:
        """Compare difference against threshold using the operator."""
        try:
            actual_diff = float(actual_diff)
            threshold = float(threshold)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid numeric values for comparison: {e}")
            return False

        if operator == ">":
            return actual_diff > threshold
        elif operator == ">=":
            return actual_diff >= threshold
        elif operator == "<":
            return actual_diff < threshold
        elif operator == "<=":
            return actual_diff <= threshold
        elif operator == "==":
            return actual_diff == threshold
        elif operator == "!=":
            return actual_diff != threshold
        else:
            logger.warning(f"Unknown operator in sensor_diff: {operator}")
            return False

    def reset_state(self, sensor_a_id: str, sensor_b_id: str) -> None:
        """Reset consecutive count for a specific sensor pair."""
        # Create a dummy condition to get the hash
        dummy = {
            "sensor_a_id": sensor_a_id,
            "sensor_b_id": sensor_b_id,
            "operator": ">",
            "value": 0,
        }
        cond_hash = _get_condition_hash(dummy)
        if cond_hash in _diff_state_cache:
            del _diff_state_cache[cond_hash]
