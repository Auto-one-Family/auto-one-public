"""
Logic Rules Repository

Stores cross-ESP automation rules + execution history.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.logic import CrossESPLogic, LogicExecutionHistory
from .base_repo import BaseRepository


class LogicRepository(BaseRepository[CrossESPLogic]):
    """
    Logic Rules Repository with CrossESPLogic-specific queries.

    Provides methods for querying automation rules and logging execution history.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(CrossESPLogic, session)

    async def create(self, rule: CrossESPLogic) -> CrossESPLogic:
        """
        Create a new rule from an instance.

        Args:
            rule: CrossESPLogic instance to create

        Returns:
            Created CrossESPLogic instance
        """
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def get_degraded_rules(self, critical_only: bool = False) -> list[CrossESPLogic]:
        """
        Get all rules currently in degraded state (AUT-111).

        Args:
            critical_only: If True, only return rules where is_critical=True.

        Returns:
            List of CrossESPLogic rules whose degraded_since is not null.
        """
        conditions = [CrossESPLogic.degraded_since.isnot(None)]
        if critical_only:
            conditions.append(CrossESPLogic.is_critical == True)
        stmt = (
            select(CrossESPLogic)
            .where(and_(*conditions))
            .order_by(CrossESPLogic.degraded_since.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_enabled_rules(self) -> list[CrossESPLogic]:
        """
        Get all enabled rules, sorted by priority ascending.

        Lower ``priority`` number = higher execution and conflict priority (matches
        ConflictManager and typical evaluation order).

        Returns:
            List of enabled CrossESPLogic rules sorted by priority
        """
        stmt = (
            select(CrossESPLogic)
            .where(CrossESPLogic.enabled == True)
            .order_by(CrossESPLogic.priority.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_rules_by_trigger_sensor(
        self, esp_id: str, gpio: int, sensor_type: str
    ) -> list[CrossESPLogic]:
        """
        Find rules that trigger on a specific sensor.

        Matches rules where trigger_conditions contains:
        - esp_id matching the provided esp_id
        - gpio matching the provided gpio
        - sensor_type matching the provided sensor_type

        Args:
            esp_id: ESP device ID (e.g., "ESP_12AB34CD")
            gpio: GPIO pin number
            sensor_type: Sensor type (e.g., "temperature", "humidity")

        Returns:
            List of matching CrossESPLogic rules
        """
        # Get all enabled rules first
        all_rules = await self.get_enabled_rules()

        # Filter rules that match the trigger sensor
        matching_rules = []
        for rule in all_rules:
            trigger = rule.trigger_conditions

            # Handle single condition or multiple conditions
            conditions = []
            if isinstance(trigger, list):
                # List format (from API): conditions stored as array
                conditions = trigger
            elif isinstance(trigger, dict):
                # Check if it's a single condition or a compound condition
                # Support sensor, sensor_threshold (legacy), AND hysteresis types
                if trigger.get("type") in ("sensor_threshold", "sensor", "hysteresis"):
                    conditions = [trigger]
                elif trigger.get("logic") in ("AND", "OR"):
                    # Compound condition with multiple sub-conditions
                    conditions = trigger.get("conditions", [])
                else:
                    # Single condition without type field (legacy format)
                    conditions = [trigger]

            # Check each condition for sensor match
            # Support sensor_threshold, sensor (shorthand), AND hysteresis condition types
            # All three reference a specific ESP + GPIO + optional sensor_type
            # Use case-insensitive comparison for sensor_type (ESP sends lowercase,
            # rules may store uppercase from UI input)
            SENSOR_CONDITION_TYPES = ("sensor_threshold", "sensor", "hysteresis")
            sensor_type_lower = sensor_type.lower() if sensor_type else ""
            for condition in conditions:
                if condition.get("type") in SENSOR_CONDITION_TYPES:
                    cond_sensor_type = (condition.get("sensor_type") or "").lower()
                    cond_gpio = condition.get("gpio")
                    # GPIO comparison with type coercion (int vs str safety)
                    try:
                        gpio_match = int(cond_gpio) == int(gpio) if cond_gpio is not None else False
                    except (ValueError, TypeError):
                        gpio_match = False
                    if (
                        condition.get("esp_id") == esp_id
                        and gpio_match
                        and (not cond_sensor_type or cond_sensor_type == sensor_type_lower)
                    ):
                        matching_rules.append(rule)
                        break  # Found match, no need to check other conditions for this rule

        return matching_rules

    async def get_rule_gpio_set_for_esp(self, esp_id: str) -> set[int]:
        """
        Return all GPIO pins referenced as trigger-sensors in enabled rules for esp_id.

        Used by QoS-adaptive publish (AUT-555): the server calls this during
        build_combined_config() and annotates each sensor's config payload with
        ``publish_qos = 1`` if its GPIO is in the returned set, else ``0``.
        The ESP32 then uses that value when calling mqtt_client_->publish(), so
        rule-relevant readings use QoS-1 (PUBACK required) while pure telemetry
        sensors keep QoS-0 (fire-and-forget, reduces OUTBOX pressure under WiFi jitter).

        Implementation note: trigger_conditions is stored as raw JSON (not JSONB) and
        can arrive in three distinct shapes from different API paths:
          1. A JSON array of condition objects (standard API write path).
          2. A single condition dict with a "type" key directly at the top level
             (legacy or simplified rule formats).
          3. A compound condition dict with a "logic": "AND"|"OR" key and a nested
             "conditions" array of sub-condition dicts.
        All three shapes are handled below with the same traversal used by
        get_rules_by_trigger_sensor() — keep both methods in sync if the schema evolves.

        Performance: cross_esp_logic is a small table (typically < 100 rows).
        A full table load + Python-side filter is fast enough for the config-push path,
        which runs at most once per ESP reconnect. No DB index change needed.

        Args:
            esp_id: ESP device ID string, e.g. "ESP_12AB34CD".
                    Must match the ``esp_id`` field inside trigger_conditions JSON —
                    NOT the UUID primary key of esp_devices.

        Returns:
            Set of GPIO integers that appear as trigger-sensor GPIOs for this ESP
            in at least one enabled rule. Empty set if the ESP has no active rules.
        """
        all_rules = await self.get_enabled_rules()
        # Only these condition types reference a physical sensor via esp_id+gpio.
        # "time_window" conditions have no sensor GPIO and are intentionally excluded.
        SENSOR_CONDITION_TYPES = ("sensor_threshold", "sensor", "hysteresis")
        result: set[int] = set()

        for rule in all_rules:
            trigger = rule.trigger_conditions

            # Normalise the three possible shapes into a flat list of condition dicts.
            conditions: list = []
            if isinstance(trigger, list):
                # Shape 1: array of condition objects (most common, API write path)
                conditions = trigger
            elif isinstance(trigger, dict):
                if trigger.get("type") in SENSOR_CONDITION_TYPES:
                    # Shape 2: single condition dict stored directly at the top level
                    conditions = [trigger]
                elif trigger.get("logic") in ("AND", "OR"):
                    # Shape 3: compound condition — unwrap the nested "conditions" array
                    conditions = trigger.get("conditions", [])
                else:
                    # Unknown dict shape — try it as a single condition anyway
                    conditions = [trigger]

            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                # Match only conditions that reference a sensor on this specific ESP.
                # esp_id comparison is intentionally exact (no case-fold) because device
                # IDs are always uppercase hex (e.g. "ESP_12AB34CD") from the firmware.
                if cond.get("type") in SENSOR_CONDITION_TYPES and cond.get("esp_id") == esp_id:
                    try:
                        result.add(int(cond["gpio"]))
                    except (KeyError, ValueError, TypeError):
                        # Malformed condition (missing gpio, non-numeric value, etc.)
                        # — skip silently; broken rules are surfaced elsewhere in the
                        # rule validation pipeline.
                        pass

        return result

    async def get_last_execution(self, rule_id: uuid.UUID) -> Optional[LogicExecutionHistory]:
        """
        Get the last execution record for a rule.

        Args:
            rule_id: UUID of the logic rule

        Returns:
            LogicExecutionHistory instance or None if rule has never been executed
        """
        stmt = (
            select(LogicExecutionHistory)
            .where(LogicExecutionHistory.logic_rule_id == rule_id)
            .order_by(LogicExecutionHistory.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_last_execution_timestamp(self, rule_id: uuid.UUID) -> Optional[datetime]:
        """
        Get timestamp of the last execution for a rule (for cooldown check).

        Args:
            rule_id: UUID of the logic rule

        Returns:
            Timestamp of last execution, or None if rule has never been executed
        """
        stmt = select(func.max(LogicExecutionHistory.timestamp)).where(
            LogicExecutionHistory.logic_rule_id == rule_id
        )
        result = await self.session.execute(stmt)
        max_timestamp = result.scalar_one_or_none()
        return max_timestamp

    async def get_execution_count(self, rule_id: uuid.UUID) -> int:
        """
        Get total execution count for a rule.

        Args:
            rule_id: UUID of the logic rule

        Returns:
            Total number of executions
        """
        stmt = (
            select(func.count())
            .select_from(LogicExecutionHistory)
            .where(LogicExecutionHistory.logic_rule_id == rule_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_execution_history(
        self,
        rule_id: Optional[uuid.UUID] = None,
        success: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[LogicExecutionHistory]:
        """
        Get execution history with filters.

        Args:
            rule_id: Optional filter by rule ID
            success: Optional filter by success status
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of records

        Returns:
            List of LogicExecutionHistory records
        """
        conditions = []

        if rule_id is not None:
            conditions.append(LogicExecutionHistory.logic_rule_id == rule_id)
        if success is not None:
            conditions.append(LogicExecutionHistory.success == success)
        if start_time is not None:
            conditions.append(LogicExecutionHistory.timestamp >= start_time)
        if end_time is not None:
            conditions.append(LogicExecutionHistory.timestamp <= end_time)

        stmt = (
            select(LogicExecutionHistory)
            .where(and_(*conditions) if conditions else True)
            .order_by(LogicExecutionHistory.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def log_execution(
        self,
        rule_id: uuid.UUID,
        trigger_data: dict,
        actions: list,
        success: bool,
        execution_ms: int,
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> LogicExecutionHistory:
        """
        Log rule execution to history.

        Args:
            rule_id: UUID of the logic rule that was executed
            trigger_data: Snapshot of sensor data that triggered the rule
            actions: List of actions that were executed
            success: Whether execution succeeded
            execution_ms: Execution duration in milliseconds
            error_message: Optional error message if execution failed
            metadata: Optional additional execution metadata

        Returns:
            Created LogicExecutionHistory instance
        """
        history = LogicExecutionHistory(
            logic_rule_id=rule_id,
            trigger_data=trigger_data,
            actions_executed=actions,
            success=success,
            error_message=error_message,
            execution_time_ms=execution_ms,
            execution_metadata=metadata,
        )
        self.session.add(history)
        await self.session.flush()
        await self.session.refresh(history)
        return history

    async def update_rule_enabled(
        self, rule_id: uuid.UUID, enabled: bool
    ) -> Optional[CrossESPLogic]:
        """
        Enable or disable a rule.

        Args:
            rule_id: UUID of the logic rule
            enabled: True to enable, False to disable

        Returns:
            Updated CrossESPLogic instance, or None if rule not found
        """
        return await self.update(rule_id, enabled=enabled)

    async def get_execution_count_last_hour(self, rule_id: uuid.UUID) -> int:
        """
        Zählt erfolgreiche Executions der letzten Stunde für Rate-Limiting.

        Args:
            rule_id: UUID of the logic rule

        Returns:
            Count of successful executions in the last hour
        """
        from datetime import datetime, timedelta
        from sqlalchemy import func, select
        from ..models.logic import LogicExecutionHistory

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        stmt = select(func.count(LogicExecutionHistory.id)).where(
            LogicExecutionHistory.logic_rule_id == rule_id,
            LogicExecutionHistory.timestamp >= one_hour_ago,
            LogicExecutionHistory.success == True,
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()
