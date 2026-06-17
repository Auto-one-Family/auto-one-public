"""
Rule Health Service (AUT-115)

Aggregates runtime health information for logic rules to power the
Climate-Cockpit tile (frontend). Combines:

- Rule definition (CrossESPLogic) — setpoint, target ESP, time-window
- Latest sensor reading (SensorData) — current_value, deviation
- Target ESP state (ESPDevice) — online/offline, last_seen
- Last execution (LogicExecutionHistory) — last_dispatch / last_skip

Used by:
- REST: GET /v1/logic/{rule_id}/health
- WebSocket: 'rule.health' broadcast every 60s for is_critical rules
  (driven by LogicScheduler).
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.esp import ESPDevice
from ..db.models.logic import CrossESPLogic, LogicExecutionHistory
from ..db.models.sensor import SensorData
from ..schemas.logic import (
    RuleHealthDispatchInfo,
    RuleHealthPayload,
    RuleHealthSkipInfo,
)


class RuleHealthService:
    """
    Aggregates IST/Soll/ESP-State/last-dispatch info for a logic rule.

    All ORM accesses are defensive: missing relations or values yield
    ``None``/``False`` rather than raising — the payload is intended for
    a UI tile, not for control flow.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = get_logger(__name__)

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_rule_health(self, rule_id: uuid.UUID) -> Optional[RuleHealthPayload]:
        """
        Aggregate health payload for a single rule.

        Args:
            rule_id: UUID of the logic rule.

        Returns:
            RuleHealthPayload if the rule exists, otherwise None.
        """
        rule = await self._get_rule(rule_id)
        if rule is None:
            return None
        return await self._build_payload(rule)

    async def get_all_critical_rules_health(self) -> list[RuleHealthPayload]:
        """
        Aggregate health payloads for all is_critical=True rules.

        Used by LogicScheduler for the 60s WebSocket broadcast loop.

        Returns:
            List of RuleHealthPayload (may be empty).
        """
        stmt = select(CrossESPLogic).where(CrossESPLogic.is_critical == True)  # noqa: E712
        result = await self.session.execute(stmt)
        rules = list(result.scalars().all())

        payloads: list[RuleHealthPayload] = []
        for rule in rules:
            try:
                payload = await self._build_payload(rule)
                payloads.append(payload)
            except Exception as exc:  # defensive: never break the broadcast loop
                self.logger.warning(
                    "Failed to build rule.health payload for rule %s: %s",
                    rule.id,
                    exc,
                )
        return payloads

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _get_rule(self, rule_id: uuid.UUID) -> Optional[CrossESPLogic]:
        stmt = select(CrossESPLogic).where(CrossESPLogic.id == rule_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _build_payload(self, rule: CrossESPLogic) -> RuleHealthPayload:
        """Compose the full RuleHealthPayload for a rule."""
        conditions = self._normalize_conditions(rule.trigger_conditions)
        actions = rule.actions if isinstance(rule.actions, list) else []

        # Trigger sensor (first sensor-condition wins)
        trigger = self._extract_trigger_sensor(conditions)
        setpoint = self._extract_setpoint(conditions)
        current_value = await self._fetch_current_value(trigger)
        deviation = self._compute_deviation(current_value, setpoint)

        # Target ESP (first actuator-action wins)
        target_esp_id = self._extract_target_esp_id(actions)
        target_esp_online, target_esp_offline_since = await self._fetch_target_esp_state(
            target_esp_id
        )

        # Last dispatch / skip
        last_dispatch, last_skip = await self._fetch_last_execution(rule.id)

        # Active time window (best effort)
        time_window_active = self._extract_time_window_label(conditions)

        return RuleHealthPayload(
            rule_id=rule.id,
            rule_name=rule.rule_name,
            is_critical=rule.is_critical,
            setpoint=setpoint,
            current_value=current_value,
            deviation=deviation,
            target_esp_id=target_esp_id,
            target_esp_online=target_esp_online,
            target_esp_offline_since=target_esp_offline_since,
            last_dispatch=last_dispatch,
            last_skip=last_skip,
            degraded_since=rule.degraded_since,
            time_window_active=time_window_active,
        )

    @staticmethod
    def _normalize_conditions(raw: Any) -> list[dict]:
        """trigger_conditions may be a single dict or a list — normalize to list."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
        if isinstance(raw, dict):
            return [raw]
        return []

    @staticmethod
    def _extract_trigger_sensor(conditions: list[dict]) -> Optional[dict]:
        """Return the first sensor-typed condition (esp_id + gpio)."""
        for cond in conditions:
            ctype = cond.get("type")
            if ctype in ("sensor", "sensor_threshold", "hysteresis") and cond.get("esp_id"):
                return cond
        # Fallback: first condition with esp_id+gpio fields, irrespective of type
        for cond in conditions:
            if cond.get("esp_id") and cond.get("gpio") is not None:
                return cond
        return None

    @staticmethod
    def _extract_setpoint(conditions: list[dict]) -> Optional[float]:
        """
        Extract setpoint from conditions.

        Priority:
        1. activate_below / activate_above (hysteresis)
        2. value (sensor_threshold / sensor)
        """
        for cond in conditions:
            for key in ("activate_below", "activate_above"):
                if key in cond and cond[key] is not None:
                    try:
                        return float(cond[key])
                    except (TypeError, ValueError):
                        continue
        for cond in conditions:
            if cond.get("type") in ("sensor", "sensor_threshold") and cond.get("value") is not None:
                try:
                    return float(cond["value"])
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _extract_target_esp_id(actions: list) -> Optional[str]:
        """Return the first actuator action's esp_id, if any."""
        for action in actions:
            if not isinstance(action, dict):
                continue
            esp_id = action.get("esp_id")
            if esp_id:
                return str(esp_id)
        return None

    @staticmethod
    def _extract_time_window_label(conditions: list[dict]) -> Optional[str]:
        """
        If a time/time_window condition is present, return a short label.

        Currently returns the condition's ``name`` or a 'HH:MM-HH:MM' fallback.
        Activation logic (current time within window) is intentionally NOT
        evaluated here — the frontend renders the label and decides display.
        """
        for cond in conditions:
            if cond.get("type") in ("time", "time_window"):
                name = cond.get("name")
                if isinstance(name, str) and name:
                    return name
                start = cond.get("start_time")
                end = cond.get("end_time")
                if start and end:
                    return f"{start}-{end}"
                return cond.get("type")
        return None

    @staticmethod
    def _compute_deviation(
        current_value: Optional[float], setpoint: Optional[float]
    ) -> Optional[float]:
        if current_value is None or setpoint is None:
            return None
        return current_value - setpoint

    async def _fetch_current_value(self, trigger: Optional[dict]) -> Optional[float]:
        """
        Fetch the latest processed_value (fallback: raw_value) for the trigger sensor.

        SensorData.esp_id is a UUID FK to esp_devices.id, so we resolve the
        device_id (string, e.g. 'ESP_AABB') to the UUID first.
        """
        if not trigger:
            return None
        esp_id_str = trigger.get("esp_id")
        gpio = trigger.get("gpio")
        sensor_type = trigger.get("sensor_type")
        if not esp_id_str or gpio is None:
            return None

        # Resolve device_id (string) -> ESPDevice.id (UUID)
        esp_uuid = await self._resolve_esp_uuid(str(esp_id_str))
        if esp_uuid is None:
            return None

        try:
            gpio_int = int(gpio)
        except (TypeError, ValueError):
            return None

        stmt = (
            select(SensorData)
            .where(SensorData.esp_id == esp_uuid, SensorData.gpio == gpio_int)
            .order_by(SensorData.timestamp.desc())
            .limit(1)
        )
        if isinstance(sensor_type, str) and sensor_type:
            stmt = stmt.where(SensorData.sensor_type == sensor_type)

        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        if latest is None:
            return None
        if latest.processed_value is not None:
            return float(latest.processed_value)
        return float(latest.raw_value) if latest.raw_value is not None else None

    async def _resolve_esp_uuid(self, device_id: str) -> Optional[uuid.UUID]:
        """Resolve ESPDevice.device_id (string) to ESPDevice.id (UUID)."""
        stmt = select(ESPDevice.id).where(ESPDevice.device_id == device_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_target_esp_state(
        self, device_id: Optional[str]
    ) -> tuple[bool, Optional[datetime]]:
        """
        Look up the target ESP's online state and (when offline) last_seen.

        Returns:
            (online, offline_since)
        """
        if not device_id:
            return False, None
        stmt = select(ESPDevice).where(ESPDevice.device_id == device_id)
        result = await self.session.execute(stmt)
        esp = result.scalar_one_or_none()
        if esp is None:
            return False, None
        online = esp.status == "online"
        offline_since = None if online else esp.last_seen
        return online, offline_since

    async def _fetch_last_execution(
        self, rule_id: uuid.UUID
    ) -> tuple[Optional[RuleHealthDispatchInfo], Optional[RuleHealthSkipInfo]]:
        """
        Fetch the most recent LogicExecutionHistory entry and map it to
        either a dispatch (success=True) or a skip (success=False).
        """
        stmt = (
            select(LogicExecutionHistory)
            .where(LogicExecutionHistory.logic_rule_id == rule_id)
            .order_by(LogicExecutionHistory.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        last = result.scalar_one_or_none()
        if last is None:
            return None, None

        if last.success:
            dispatch = self._build_dispatch_info(last)
            return dispatch, None

        skip = self._build_skip_info(last)
        return None, skip

    @staticmethod
    def _build_dispatch_info(
        entry: LogicExecutionHistory,
    ) -> Optional[RuleHealthDispatchInfo]:
        """Map a successful LogicExecutionHistory entry to a dispatch info."""
        actions = entry.actions_executed if isinstance(entry.actions_executed, list) else []
        first_action: dict = {}
        for action in actions:
            if isinstance(action, dict):
                first_action = action
                break

        command = str(first_action.get("command") or first_action.get("type") or "unknown")
        # Derive a coarse state from command (frontend may refine).
        cmd_upper = command.upper()
        if cmd_upper in ("ON", "TOGGLE"):
            state = "on"
        elif cmd_upper == "OFF":
            state = "off"
        elif cmd_upper == "PWM":
            state = "pwm"
        else:
            state = command.lower()

        source = "rule"
        meta = entry.execution_metadata if isinstance(entry.execution_metadata, dict) else None
        if meta and isinstance(meta.get("source"), str):
            source = meta["source"]

        return RuleHealthDispatchInfo(
            ts=entry.timestamp,
            command=command,
            state=state,
            source=source,
        )

    @staticmethod
    def _build_skip_info(entry: LogicExecutionHistory) -> RuleHealthSkipInfo:
        """Map a failed LogicExecutionHistory entry to a skip info."""
        reason = entry.error_message or "unknown"
        # Truncate to a short reason label (frontend has its own translator).
        if len(reason) > 64:
            reason = reason[:61] + "..."

        consecutive = 0
        meta = entry.execution_metadata if isinstance(entry.execution_metadata, dict) else None
        if meta:
            raw = meta.get("consecutive_skip_count") or meta.get("consecutive_count")
            try:
                consecutive = max(0, int(raw)) if raw is not None else 0
            except (TypeError, ValueError):
                consecutive = 0

        return RuleHealthSkipInfo(
            ts=entry.timestamp,
            reason=reason,
            consecutive_count=consecutive,
        )
