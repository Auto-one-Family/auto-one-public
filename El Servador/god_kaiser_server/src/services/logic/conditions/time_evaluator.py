"""
Time Condition Evaluator

Evaluates time window conditions.
"""

from datetime import datetime, timezone
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)


class TimeConditionEvaluator(BaseConditionEvaluator):
    """
    Evaluates time window conditions.

    Supports:
    - Time windows (start_hour to end_hour)
    - Days of week filtering
    """

    def supports(self, condition_type: str) -> bool:
        """Check if this evaluator supports time conditions."""
        return condition_type in ("time_window", "time")

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate time window condition.

        Args:
            condition: Condition dictionary with:
                - type: "time_window" or "time"
                - start_hour: Start hour (0-23) or start_time (HH:MM format)
                - end_hour: End hour (0-23) or end_time (HH:MM format)
                - days_of_week: Optional list of days (0=Monday, 6=Sunday)
            context: Evaluation context with:
                - current_time: Optional datetime object (defaults to now)

        Returns:
            True if current time is within the time window, False otherwise
        """
        # Get current time from context or use now
        current_time = context.get("current_time")
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif isinstance(current_time, str):
            # Try to parse if string
            try:
                current_time = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Could not parse current_time: {current_time}")
                current_time = datetime.now(timezone.utc)

        # B2-fix: convert to condition timezone so start_hour/end_hour are interpreted
        # in the user's local time rather than UTC.  Existing rules without a "timezone"
        # field keep their UTC behaviour (backward-compatible).
        tz_name = condition.get("timezone")
        if tz_name:
            try:
                current_time = current_time.astimezone(ZoneInfo(tz_name))
            except (ZoneInfoNotFoundError, ValueError):
                logger.warning(
                    f"TimeConditionEvaluator: invalid timezone '{tz_name}', falling back to UTC"
                )

        rule_name = str(context.get("rule_name") or context.get("rule_id") or "unknown_rule")

        # Check day of week if specified
        days_of_week = condition.get("days_of_week")
        if days_of_week is not None:
            if not isinstance(days_of_week, list):
                logger.warning("days_of_week must be a list")
                return False

            # Python weekday(): 0=Monday, 6=Sunday
            current_weekday = current_time.weekday()
            if current_weekday not in days_of_week:
                logger.info(
                    "Rule '%s' inactive due to TimeWindow: weekday=%s not in allowed=%s",
                    rule_name,
                    current_weekday,
                    days_of_week,
                )
                return False

        # Get time window
        # Support both hour-based (0-23) and time-based (HH:MM) formats
        start_hour = condition.get("start_hour")
        end_hour = condition.get("end_hour")
        start_minute = condition.get("start_minute")
        end_minute = condition.get("end_minute")
        start_time_str = condition.get("start_time")
        end_time_str = condition.get("end_time")

        # Parse explicit minute fields first (preferred path).
        try:
            start_minute = int(start_minute) if start_minute is not None else 0
            end_minute = int(end_minute) if end_minute is not None else 0
        except (TypeError, ValueError):
            logger.warning("Invalid start_minute/end_minute values")
            return False

        # Backward-compatible fallback: parse HH:MM only when hour field is absent.
        if start_hour is None and start_time_str:
            try:
                parts = start_time_str.split(":")
                start_hour = int(parts[0])
                start_minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Invalid start_time format: {start_time_str}")
                return False

        if end_hour is None and end_time_str:
            try:
                parts = end_time_str.split(":")
                end_hour = int(parts[0])
                end_minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Invalid end_time format: {end_time_str}")
                return False

        # Default to full day if not specified
        if start_hour is None:
            start_hour = 0
        if end_hour is None:
            end_hour = 24

        # Validate hour ranges
        if not (0 <= start_hour <= 23):
            logger.warning(f"Invalid start_hour: {start_hour}. Must be 0-23")
            return False
        if not (0 <= end_hour <= 24):
            logger.warning(f"Invalid end_hour: {end_hour}. Must be 0-24")
            return False
        if not (0 <= start_minute <= 59):
            logger.warning(f"Invalid start_minute: {start_minute}. Must be 0-59")
            return False
        if not (0 <= end_minute <= 59):
            logger.warning(f"Invalid end_minute: {end_minute}. Must be 0-59")
            return False
        if end_hour == 24 and end_minute != 0:
            logger.warning("Invalid end time: 24:%02d is not allowed", end_minute)
            return False

        # Compare using total minutes for proper HH:MM granularity
        current_minutes = current_time.hour * 60 + current_time.minute
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute

        # Handle wrapping (e.g., 22:00 to 06:00)
        if start_minutes <= end_minutes:
            # Normal case (e.g., 8:00 to 18:00)
            in_window = start_minutes <= current_minutes < end_minutes
        else:
            # Wrapping case (e.g., 22:30 to 06:15)
            in_window = current_minutes >= start_minutes or current_minutes < end_minutes

        if not in_window:
            logger.info(
                "Rule '%s' inactive due to TimeWindow: now=%02d:%02d, window=%02d:%02d-%02d:%02d, timezone=%s",
                rule_name,
                current_time.hour,
                current_time.minute,
                start_hour,
                start_minute,
                end_hour,
                end_minute,
                tz_name or "UTC",
            )

        return in_window
