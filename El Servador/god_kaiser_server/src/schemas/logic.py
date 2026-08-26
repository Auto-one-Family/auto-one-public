"""
Logic Rules & Automation Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🟡 HIGH
Status: IMPLEMENTED

Provides:
- Logic rule CRUD models
- Rule testing/simulation models
- Execution history models

Cross-ESP Automation:
- Rules can trigger actions across different ESPs
- Conditions: sensor value comparisons, time constraints
- Actions: actuator commands, notifications

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 164-172)
- db/models/logic.py (LogicRule model)
- services/logic_engine.py (Rule execution)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..db.models.logic import RULE_GROUP_CATALOG
from .common import BaseResponse, PaginatedResponse, TimestampMixin

_RULE_GROUP_SET = set(RULE_GROUP_CATALOG)

# =============================================================================
# Escalation Policy Validation (AUT-111)
# =============================================================================

_VALID_NOTIFY_CHANNELS = {"email", "websocket", "webhook"}


def _validate_escalation_policy(v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Validate escalation_policy shape: structure + types."""
    if v is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("escalation_policy must be a JSON object")
    allowed_keys = {"notify", "retry_interval_s", "max_retries", "failover_actions"}
    unknown = set(v.keys()) - allowed_keys
    if unknown:
        raise ValueError(f"Unknown escalation_policy keys: {unknown}")
    if "notify" in v:
        if not isinstance(v["notify"], list):
            raise ValueError("escalation_policy.notify must be a list")
        for ch in v["notify"]:
            if ch not in _VALID_NOTIFY_CHANNELS:
                raise ValueError(
                    f"Invalid notify channel '{ch}', allowed: {_VALID_NOTIFY_CHANNELS}"
                )
    if "retry_interval_s" in v:
        ri = v["retry_interval_s"]
        if not isinstance(ri, (int, float)) or ri < 1 or ri > 3600:
            raise ValueError("retry_interval_s must be 1..3600")
    if "max_retries" in v:
        mr = v["max_retries"]
        if not isinstance(mr, int) or mr < 0 or mr > 100:
            raise ValueError("max_retries must be 0..100")
    if "failover_actions" in v:
        fa = v["failover_actions"]
        if not isinstance(fa, list):
            raise ValueError("failover_actions must be a list")
    return v


def _validate_rule_group(v: Optional[str]) -> Optional[str]:
    """AUT-1145: None = no override (auto-derived). Otherwise must be in RULE_GROUP_CATALOG."""
    if v is not None and v not in _RULE_GROUP_SET:
        raise ValueError(f"Invalid rule_group '{v}'. Must be one of: {sorted(_RULE_GROUP_SET)}")
    return v


# =============================================================================
# Measure Bindings (AUT-1393 / M-1) — additive rule_metadata key
# =============================================================================

MEASURE_BINDING_HOOKS = (
    "on_start",
    "after_action",
    "after_settle",
    "on_complete",
)
MEASURE_BINDING_FORMULA_IDS = (
    "difference",
    "delta_over_event",
)
MEASURE_BINDING_OUTPUT_TARGETS = (
    "execution_metadata",
    "ledger",
)


class MeasureBindingSensorRef(BaseModel):
    """Live sensor reference (M-0 SSOT): esp_id + gpio + sensor_type."""

    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device_id (Live-Form, not config UUID)",
    )
    gpio: int = Field(..., ge=0, le=39)
    sensor_type: str = Field(..., min_length=1, max_length=50)


class MeasureBinding(BaseModel):
    """
    AUT-1393: Optional measure binding under rule_metadata.measure_bindings[].

    Never part of trigger_conditions — observe-only after a rule already fired.
    """

    sensor_refs: List[MeasureBindingSensorRef] = Field(..., min_length=1)
    hooks: List[Literal["on_start", "after_action", "after_settle", "on_complete"]] = Field(
        ...,
        min_length=1,
        description="Closed hook list — no free-text strings",
    )
    formula_id: Literal["difference", "delta_over_event"] = Field(
        ...,
        description="Formula registry id (wave-1: difference/delta_over_event)",
    )
    formula_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Formula-specific params (caller-defined; no invented knobs here)",
    )
    output_target: Literal["execution_metadata", "ledger"] = Field(
        ...,
        description="Where derived output is written (wired in M-3)",
    )


def _validate_rule_metadata_measure_bindings(
    v: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    If rule_metadata contains measure_bindings, validate shape.
    Other keys remain free-form (dose_config etc.). Absent key = no-op.
    """
    if v is None:
        return v
    if not isinstance(v, dict):
        raise ValueError("rule_metadata must be a JSON object")
    if "measure_bindings" not in v:
        return v
    bindings = v["measure_bindings"]
    if bindings is None:
        return v
    if not isinstance(bindings, list):
        raise ValueError("rule_metadata.measure_bindings must be a list")
    validated: List[Dict[str, Any]] = []
    for i, item in enumerate(bindings):
        try:
            validated.append(MeasureBinding.model_validate(item).model_dump())
        except Exception as exc:
            raise ValueError(f"rule_metadata.measure_bindings[{i}]: {exc}") from exc
    out = dict(v)
    out["measure_bindings"] = validated
    return out


# Kanonisch mit Laufzeit: logic_repo.get_enabled_rules (priority.asc), ConflictManager
LOGIC_RULE_PRIORITY_FIELD_DESCRIPTION = (
    "Priorität für Konfliktauflösung und typische Ausführungsreihenfolge: "
    "niedrigere Zahl = höhere Priorität (wichtigere Regel). Typischer Bereich 1–100. "
    "Beispiel: Bei konkurrierenden Regeln gewinnt priority=20 vor priority=80."
)

# =============================================================================
# Condition Types
# =============================================================================


class SensorCondition(BaseModel):
    """
    Sensor-based trigger condition.

    Example: IF ESP_12AB34CD.GPIO34 (pH) > 7.5
    """

    type: str = Field(
        "sensor",
        description="Condition type (always 'sensor' for this model)",
    )
    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID",
    )
    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin with sensor",
    )
    operator: str = Field(
        ...,
        pattern=r"^(>|<|>=|<=|==|!=)$",
        description="Comparison operator",
    )
    value: float = Field(
        ...,
        description="Threshold value",
    )
    sensor_type: Optional[str] = Field(
        None,
        description="Expected sensor type (for validation)",
    )
    subzone_id: Optional[str] = Field(
        None,
        description="Optional subzone filter (Phase 2.4): rule fires only when trigger_data.subzone_id matches",
    )
    require_fresh_data: Optional[bool] = Field(
        False,
        description=(
            "AUT-41: When True, condition evaluates False if the sensor value is stale "
            "(on_demand/scheduled sensors only; age > measurement_freshness_hours). "
            "Continuous sensors and sensors without freshness config are unaffected."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "sensor",
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "operator": ">",
                "value": 7.5,
                "sensor_type": "ph",
                "require_fresh_data": False,
            }
        }
    )


class TimeCondition(BaseModel):
    """
    Time-based condition.

    Example: Only between 08:00 and 18:00
    """

    type: str = Field(
        "time",
        description="Condition type (always 'time' for this model)",
    )
    start_time: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Start time (HH:MM)",
        examples=["08:00", "18:30"],
    )
    end_time: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="End time (HH:MM)",
        examples=["18:00", "06:00"],
    )
    days_of_week: Optional[List[int]] = Field(
        None,
        description="Days of week (0=Monday, 6=Sunday), None=all days",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "time",
                "start_time": "08:00",
                "end_time": "18:00",
                "days_of_week": [0, 1, 2, 3, 4],
            }
        }
    )


class CooldownCondition(BaseModel):
    """
    Cooldown condition to prevent rapid triggering.
    """

    type: str = Field(
        "cooldown",
        description="Condition type",
    )
    min_interval_seconds: int = Field(
        ...,
        ge=1,
        le=86400,
        description="Minimum seconds between triggers",
    )


# =============================================================================
# Action Types
# =============================================================================


class ActuatorAction(BaseModel):
    """
    Actuator control action.

    Example: THEN ESP_AABBCCDD.GPIO5 (pump) = ON
    """

    type: str = Field(
        "actuator",
        description="Action type (always 'actuator' for this model)",
    )
    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Target ESP device ID",
    )
    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin with actuator",
    )
    command: str = Field(
        ...,
        pattern=r"^(ON|OFF|PWM|TOGGLE)$",
        description="Actuator command",
    )
    value: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Command value (0.0-1.0 for PWM)",
    )
    duration: int = Field(
        0,
        ge=0,
        le=86400,
        description="Duration in seconds (0=until explicitly stopped)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "actuator",
                "esp_id": "ESP_AABBCCDD",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration": 300,
            }
        }
    )


class NotificationAction(BaseModel):
    """
    Notification action (email, webhook, etc.).
    """

    type: str = Field(
        "notification",
        description="Action type",
    )
    channel: str = Field(
        ...,
        pattern=r"^(email|webhook|websocket)$",
        description="Notification channel",
    )
    target: str = Field(
        ...,
        description="Target (email address, webhook URL, etc.)",
    )
    message_template: str = Field(
        ...,
        max_length=1000,
        description="Message template (supports {sensor_value}, {esp_id}, etc.)",
    )


class DelayAction(BaseModel):
    """
    Delay action for sequencing.
    """

    type: str = Field(
        "delay",
        description="Action type",
    )
    seconds: int = Field(
        ...,
        ge=1,
        le=3600,
        description="Delay in seconds",
    )


# =============================================================================
# Logic Rule
# =============================================================================


class LogicRuleBase(BaseModel):
    """Base logic rule fields."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Rule name",
        examples=["pH Too High - Stop Dosing"],
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Rule description",
    )


class LogicRuleCreate(LogicRuleBase):
    """
    Logic rule creation request.
    """

    conditions: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Trigger conditions (all must be true)",
    )
    actions: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=10,
        description=(
            "Actions to execute when triggered. "
            "AUT-1317 (opt-in): each action may include "
            "condition_refs (list[int]|null) and condition_op ('AND'|'OR'|null); "
            "absent/null/[] refs keep the legacy global rule gate. "
            "Actuator OFF may set is_safety_critical for action-level cooldown bypass."
        ),
    )
    logic_operator: str = Field(
        "AND",
        pattern=r"^(AND|OR)$",
        description="Logic operator for multiple conditions",
    )
    enabled: bool = Field(
        True,
        description="Whether rule is active",
    )
    priority: int = Field(
        50,
        ge=1,
        le=100,
        description=LOGIC_RULE_PRIORITY_FIELD_DESCRIPTION,
    )
    cooldown_seconds: int = Field(
        60,
        ge=0,
        le=86400,
        description="Minimum seconds between executions",
    )
    settle_after_rule_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            "AUT-1115: Wait for settle_seconds after the last execution of THIS "
            "other rule before evaluating. None = no settle dependency."
        ),
    )
    settle_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="AUT-1115: Settle window in seconds, evaluated against settle_after_rule_id's last execution",
    )
    max_executions_per_hour: Optional[int] = Field(
        None,
        ge=1,
        le=60,
        description="Maximum executions per hour (None=unlimited)",
    )
    max_executions_per_day: Optional[int] = Field(
        None,
        ge=0,
        description="Maximum executions per day / rolling 24h window (None or 0=unlimited)",
    )
    max_dose_ml_per_day: Optional[float] = Field(
        None,
        ge=0,
        description="Maximum total dose ml per day / rolling 24h window (None=unlimited, requires AO-5 dose_ml audit)",
    )
    is_critical: bool = Field(
        False,
        description=(
            "AUT-111/AUT-1336: Safety-critical flag — degraded-state/Health-Tracking "
            "and ConflictManager precedence (OR with action.is_safety_critical)"
        ),
    )
    escalation_policy: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "AUT-111: Escalation policy for critical rules when degraded. "
            "Shape: {notify: ['email','websocket'], retry_interval_s: 60, "
            "max_retries: 5, failover_actions: [...]}"
        ),
    )
    rule_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "AUT-1113: Free-form rule metadata (e.g. chemistry dose_config for "
            "AUT-1112 — target_value, volume_l, components, safety_factor, "
            "dilution_value). AUT-1366: components[i] may carry optional "
            "volume_share (intended volume fraction; Σ≈1; missing → equal "
            "shares via resolve_volume_shares). AUT-1393: optional "
            "measure_bindings[] (observe-only; never trigger_conditions) is "
            "shape-validated when present; other keys stay caller-defined."
        ),
    )
    rule_group: Optional[str] = Field(
        None,
        description=(
            "AUT-1145: Explicit display-group override "
            f"(one of {sorted(_RULE_GROUP_SET)}). None = auto-derived from the "
            "rule's mechanic (see LogicService.derive_rule_group)."
        ),
    )
    # AUT-1232: Opt-in plan subscription (default off — additive, no behavior change)
    follows_plan: bool = Field(
        False,
        description=(
            "AUT-1232: When True, rule may follow plan_segment@now (wired in T3). "
            "Default False — existing rules stay on their static setpoints."
        ),
    )
    plan_zone_id: Optional[str] = Field(
        None, max_length=50, description="AUT-1232: Zone for plan subscription"
    )
    plan_subzone_config_id: Optional[uuid.UUID] = Field(
        None, description="AUT-1232: Optional subzone_config for plan subscription"
    )
    plan_domain: Optional[str] = Field(
        None, max_length=32, description="AUT-1232: Plan domain (e.g. nutrient_solution)"
    )
    plan_measure: Optional[str] = Field(
        None, max_length=32, description="AUT-1232: Plan measure (e.g. target_ec)"
    )

    @field_validator("escalation_policy")
    @classmethod
    def validate_escalation(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return _validate_escalation_policy(v)

    @field_validator("rule_group")
    @classmethod
    def validate_rule_group(cls, v: Optional[str]) -> Optional[str]:
        return _validate_rule_group(v)

    @field_validator("rule_metadata")
    @classmethod
    def validate_rule_metadata_measure_bindings(
        cls, v: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = _validate_rule_metadata_measure_bindings(v)
        return result if result is not None else {}

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "High pH Alert",
                "description": "Stop dosing pump when pH exceeds 7.5",
                "conditions": [
                    {
                        "type": "sensor",
                        "esp_id": "ESP_12AB34CD",
                        "gpio": 34,
                        "operator": ">",
                        "value": 7.5,
                    },
                    {"type": "time", "start_time": "06:00", "end_time": "22:00"},
                ],
                "actions": [
                    {
                        "type": "actuator",
                        "esp_id": "ESP_AABBCCDD",
                        "gpio": 5,
                        "command": "OFF",
                        "value": 0.0,
                    }
                ],
                "logic_operator": "AND",
                "enabled": True,
                "priority": 80,
                "cooldown_seconds": 300,
                "is_critical": False,
            }
        }
    )


class LogicRuleUpdate(BaseModel):
    """
    Logic rule update request.

    All fields optional - only provided fields are updated.
    """

    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    conditions: Optional[List[Dict[str, Any]]] = Field(None, min_length=1, max_length=10)
    actions: Optional[List[Dict[str, Any]]] = Field(None, min_length=1, max_length=10)
    logic_operator: Optional[str] = Field(None, pattern=r"^(AND|OR)$")
    enabled: Optional[bool] = Field(None)
    priority: Optional[int] = Field(
        None,
        ge=1,
        le=100,
        description=LOGIC_RULE_PRIORITY_FIELD_DESCRIPTION,
    )
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=86400)
    settle_after_rule_id: Optional[uuid.UUID] = Field(
        None, description="AUT-1115: Settle-after rule reference. None = leave unchanged."
    )
    settle_seconds: Optional[int] = Field(None, ge=0, le=86400)
    max_executions_per_hour: Optional[int] = Field(None, ge=1, le=60)
    max_executions_per_day: Optional[int] = Field(None, ge=0)
    max_dose_ml_per_day: Optional[float] = Field(None, ge=0)
    is_critical: Optional[bool] = Field(None, description="AUT-111: Safety-critical flag")
    escalation_policy: Optional[Dict[str, Any]] = Field(
        None, description="AUT-111: Escalation policy"
    )
    rule_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "AUT-1113: Free-form rule metadata. None = leave unchanged. "
            "AUT-1393: optional measure_bindings[] shape-validated when present."
        ),
    )
    rule_group: Optional[str] = Field(
        None,
        description=(
            "AUT-1145: Explicit display-group override. Omit the field to leave "
            "unchanged; send null explicitly to clear the override and revert to "
            f"auto-derivation. One of {sorted(_RULE_GROUP_SET)} when set."
        ),
    )
    follows_plan: Optional[bool] = Field(
        None, description="AUT-1232: Opt-in plan subscription flag"
    )
    plan_zone_id: Optional[str] = Field(
        None, max_length=50, description="AUT-1232: Zone for plan subscription"
    )
    plan_subzone_config_id: Optional[uuid.UUID] = Field(
        None, description="AUT-1232: Optional subzone_config for plan subscription"
    )
    plan_domain: Optional[str] = Field(
        None, max_length=32, description="AUT-1232: Plan domain"
    )
    plan_measure: Optional[str] = Field(
        None, max_length=32, description="AUT-1232: Plan measure"
    )

    @field_validator("escalation_policy")
    @classmethod
    def validate_escalation(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return _validate_escalation_policy(v)

    @field_validator("rule_group")
    @classmethod
    def validate_rule_group(cls, v: Optional[str]) -> Optional[str]:
        return _validate_rule_group(v)

    @field_validator("rule_metadata")
    @classmethod
    def validate_rule_metadata_measure_bindings(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return _validate_rule_metadata_measure_bindings(v)


class LogicRuleResponse(LogicRuleBase, TimestampMixin):
    """
    Logic rule response.
    """

    id: Any = Field(..., description="Rule ID (UUID)")
    conditions: List[Dict[str, Any]] = Field(
        ...,
        description="Trigger conditions",
    )
    actions: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "Actions to execute. May include optional AUT-1317 fields "
            "condition_refs / condition_op (and is_safety_critical on actuators)."
        ),
    )
    logic_operator: str = Field(
        ...,
        description="Logic operator (AND/OR)",
    )
    enabled: bool = Field(
        ...,
        description="Whether rule is active",
    )
    priority: int = Field(
        ...,
        description=LOGIC_RULE_PRIORITY_FIELD_DESCRIPTION,
    )
    cooldown_seconds: int = Field(
        ...,
        description="Cooldown between executions",
    )
    settle_after_rule_id: Optional[uuid.UUID] = Field(
        None, description="AUT-1115: Settle-after rule reference"
    )
    settle_seconds: Optional[int] = Field(
        None, description="AUT-1115: Settle window in seconds"
    )
    max_executions_per_hour: Optional[int] = Field(None)
    max_executions_per_day: Optional[int] = Field(None)
    max_dose_ml_per_day: Optional[float] = Field(None)
    # Runtime info
    last_triggered: Optional[datetime] = Field(
        None,
        description="Last trigger timestamp",
    )
    execution_count: int = Field(
        0,
        description="Total execution count",
        ge=0,
    )
    last_execution_success: Optional[bool] = Field(
        None,
        description="Whether last execution succeeded",
    )
    # AUT-111: Critical-Rule Degraded-Handling
    is_critical: bool = Field(
        False,
        description="Whether this rule is safety-critical",
    )
    escalation_policy: Optional[Dict[str, Any]] = Field(
        None,
        description="Escalation policy for critical rules",
    )
    rule_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="AUT-1113: Free-form rule metadata (e.g. chemistry dose_config).",
    )
    rule_group: str = Field(
        ...,
        description=(
            "AUT-1145: Effective display group — the explicit override if set, "
            "otherwise derived from the rule's mechanic (LogicService."
            f"derive_rule_group, single source of truth). One of {sorted(_RULE_GROUP_SET)}."
        ),
    )
    follows_plan: bool = Field(
        False,
        description="AUT-1232: Opt-in plan subscription (default False)",
    )
    plan_zone_id: Optional[str] = Field(
        None, description="AUT-1232: Zone for plan subscription"
    )
    plan_subzone_config_id: Optional[uuid.UUID] = Field(
        None, description="AUT-1232: Optional subzone_config for plan subscription"
    )
    plan_domain: Optional[str] = Field(
        None, description="AUT-1232: Plan domain"
    )
    plan_measure: Optional[str] = Field(
        None, description="AUT-1232: Plan measure"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description=(
            "AUT-1116: Non-blocking hints (e.g. paired-rule deadband overlap, "
            "AUT-1117 pi_enhanced). HTTP 2xx is returned regardless — never a reject."
        ),
    )
    degraded_since: Optional[datetime] = Field(
        None,
        description="Timestamp when rule entered degraded state",
    )
    degraded_reason: Optional[str] = Field(
        None,
        description="Reason for degraded state",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "High pH Alert",
                "description": "Stop dosing pump when pH exceeds 7.5",
                "conditions": [
                    {
                        "type": "sensor",
                        "esp_id": "ESP_12AB34CD",
                        "gpio": 34,
                        "operator": ">",
                        "value": 7.5,
                    }
                ],
                "actions": [
                    {"type": "actuator", "esp_id": "ESP_AABBCCDD", "gpio": 5, "command": "OFF"}
                ],
                "logic_operator": "AND",
                "enabled": True,
                "priority": 80,
                "cooldown_seconds": 300,
                "is_critical": False,
                "last_triggered": "2025-01-01T12:00:00Z",
                "execution_count": 15,
                "last_execution_success": True,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        },
    )


# =============================================================================
# Rule Toggle
# =============================================================================


class RuleToggleRequest(BaseModel):
    """
    Rule enable/disable request.
    """

    enabled: bool = Field(
        ...,
        description="New enabled state",
    )
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Reason for toggle (for audit log)",
    )


class RuleToggleResponse(BaseResponse):
    """
    Rule toggle response.
    """

    rule_id: Any = Field(..., description="Rule ID (UUID)")
    rule_name: str = Field(..., description="Rule name")
    enabled: bool = Field(..., description="New enabled state")
    previous_state: bool = Field(..., description="Previous enabled state")


# =============================================================================
# Bulk Quick-Update (AUT-1145, S0 — Gruppenkarten-Schnellfeld)
# =============================================================================


class RuleBulkQuickUpdateRequest(BaseModel):
    """
    Bulk quick-field update for a set of marked rules (Gruppenkarten-Schnellfeld).

    Exactly the three field groups from the group-card quick-field (AUT-1145):
    active (An/Aus), threshold_value / hysteresis_on_value+hysteresis_off_value
    (Schwellwert/Zielwert), and the time-window fields (Zeiten). priority and
    cooldown_seconds are DELIBERATELY absent — those stay editor-only.

    Every provided field is applied per rule_id via the existing single-rule
    LogicService.update_rule() path (see bulk_quick_update_rules) — this is a
    thin loop, not a second write path.
    """

    ids: List[uuid.UUID] = Field(..., min_length=1, max_length=200)
    active: Optional[bool] = Field(None, description="An/Aus")
    threshold_value: Optional[float] = Field(
        None, description="Neuer Zahlenwert fuer eine normale Schwellwert-Bedingung"
    )
    hysteresis_on_value: Optional[float] = Field(
        None, description="Hysterese Ein-Wert (activate_above/activate_below je nach Modus)"
    )
    hysteresis_off_value: Optional[float] = Field(
        None, description="Hysterese Aus-Wert (deactivate_below/deactivate_above je nach Modus)"
    )
    start_hour: Optional[int] = Field(None, ge=0, le=23)
    start_minute: Optional[int] = Field(None, ge=0, le=59)
    end_hour: Optional[int] = Field(None, ge=0, le=24)
    end_minute: Optional[int] = Field(None, ge=0, le=59)
    days_of_week: Optional[List[int]] = Field(
        None, description="0=Monday..6=Sunday, None=leave unchanged"
    )


class RuleBulkQuickUpdateResult(BaseModel):
    """Per-rule outcome of a bulk quick-update call."""

    rule_id: uuid.UUID = Field(..., description="Rule ID")
    success: bool = Field(..., description="Whether this rule was updated without error")
    error: Optional[str] = Field(None, description="Error message if success=False")


class RuleBulkQuickUpdateResponse(BaseResponse):
    """Bulk quick-update response — one result per requested rule_id."""

    results: List[RuleBulkQuickUpdateResult] = Field(...)


# =============================================================================
# Rule Testing
# =============================================================================


class RuleTestRequest(BaseModel):
    """
    Rule test/simulation request.

    Simulates rule execution without actually triggering actions.
    """

    mock_sensor_values: Optional[Dict[str, float]] = Field(
        None,
        description="Mock sensor values for testing (key: 'ESP_ID:GPIO')",
        examples=[{"ESP_12AB34CD:34": 7.8}],
    )
    mock_time: Optional[str] = Field(
        None,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Mock time (HH:MM) for time-based conditions",
    )
    dry_run: bool = Field(
        True,
        description="If False, actually execute actions (use with caution)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mock_sensor_values": {"ESP_12AB34CD:34": 7.8},
                "mock_time": "14:30",
                "dry_run": True,
            }
        }
    )


class ConditionResult(BaseModel):
    """
    Individual condition evaluation result.
    """

    condition_index: int = Field(..., description="Condition index in array")
    condition_type: str = Field(..., description="Condition type")
    result: bool = Field(..., description="Evaluation result")
    details: str = Field(..., description="Human-readable evaluation details")
    actual_value: Optional[float] = Field(None, description="Actual sensor value (if applicable)")


class ActionResult(BaseModel):
    """
    Individual action execution result.
    """

    action_index: int = Field(..., description="Action index in array")
    action_type: str = Field(..., description="Action type")
    would_execute: bool = Field(..., description="Whether action would execute")
    details: str = Field(..., description="Action details")
    dry_run: bool = Field(..., description="Whether this was dry run")


class RuleTestResponse(BaseResponse):
    """
    Rule test response.
    """

    rule_id: Any = Field(..., description="Rule ID (UUID)")
    rule_name: str = Field(..., description="Rule name")
    would_trigger: bool = Field(..., description="Whether rule would trigger")
    condition_results: List[ConditionResult] = Field(
        default_factory=list,
        description="Individual condition results",
    )
    action_results: List[ActionResult] = Field(
        default_factory=list,
        description="Individual action results (if would_trigger)",
    )
    dry_run: bool = Field(..., description="Whether this was a dry run")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "rule_id": 1,
                "rule_name": "High pH Alert",
                "would_trigger": True,
                "condition_results": [
                    {
                        "condition_index": 0,
                        "condition_type": "sensor",
                        "result": True,
                        "details": "ESP_12AB34CD:34 (7.8) > 7.5",
                        "actual_value": 7.8,
                    }
                ],
                "action_results": [
                    {
                        "action_index": 0,
                        "action_type": "actuator",
                        "would_execute": True,
                        "details": "ESP_AABBCCDD:5 OFF",
                        "dry_run": True,
                    }
                ],
                "dry_run": True,
            }
        }
    )


# =============================================================================
# Execution History
# =============================================================================


class ExecutionHistoryEntry(BaseModel):
    """
    Rule execution history entry.
    """

    id: Any = Field(..., description="Entry ID (UUID)")
    rule_id: Any = Field(..., description="Rule ID (UUID)")
    rule_name: str = Field(..., description="Rule name at execution time")
    triggered_at: datetime = Field(..., description="Trigger timestamp")
    trigger_reason: str = Field(..., description="Condition that triggered")
    actions_executed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Actions that were executed",
    )
    success: bool = Field(..., description="Overall execution success")
    error_message: Optional[str] = Field(None, description="Error if failed")
    execution_time_ms: float = Field(..., description="Execution time (ms)")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 100,
                "rule_id": 1,
                "rule_name": "High pH Alert",
                "triggered_at": "2025-01-01T12:00:00Z",
                "trigger_reason": "ESP_12AB34CD:34 (7.8) > 7.5",
                "actions_executed": [
                    {"type": "actuator", "esp_id": "ESP_AABBCCDD", "gpio": 5, "command": "OFF"}
                ],
                "success": True,
                "error_message": None,
                "execution_time_ms": 45.2,
            }
        },
    )


class ExecutionHistoryQuery(BaseModel):
    """
    Execution history query parameters.
    """

    rule_id: Optional[Any] = Field(None, description="Filter by rule ID (UUID)")
    success: Optional[bool] = Field(None, description="Filter by success status")
    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")


class ExecutionHistoryResponse(BaseResponse):
    """
    Execution history response.
    """

    entries: List[ExecutionHistoryEntry] = Field(
        default_factory=list,
        description="History entries",
    )
    total_count: int = Field(..., description="Total entries matching filter", ge=0)
    success_rate: Optional[float] = Field(
        None,
        description="Success rate (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )


# =============================================================================
# Paginated Responses
# =============================================================================


class LogicRuleListResponse(PaginatedResponse[LogicRuleResponse]):
    """
    Paginated list of logic rules.
    """

    pass


class ExecutionHistoryPaginatedResponse(PaginatedResponse[ExecutionHistoryEntry]):
    """
    Paginated execution history.
    """

    pass


# =============================================================================
# Rule Health (AUT-115) - Climate Cockpit Tile
# =============================================================================


class RuleHealthDispatchInfo(BaseModel):
    """Last successful actuator dispatch for a rule."""

    ts: datetime = Field(..., description="Dispatch timestamp (UTC)")
    command: str = Field(..., description="Dispatched command (e.g. 'ON', 'OFF', 'PWM')")
    state: str = Field(..., description="Resulting actuator state ('on', 'off', 'pwm')")
    source: str = Field(
        ...,
        description="Dispatch source ('rule', 'manual', 'sequence')",
    )

    model_config = ConfigDict(from_attributes=True)


class RuleHealthSkipInfo(BaseModel):
    """Last suppressed dispatch (cooldown, rate-limit, target offline, ...)."""

    ts: datetime = Field(..., description="Skip timestamp (UTC)")
    reason: str = Field(..., description="Skip reason")
    consecutive_count: int = Field(
        0,
        ge=0,
        description="Number of consecutive skips for the same reason",
    )

    model_config = ConfigDict(from_attributes=True)


class RuleHealthPayload(BaseModel):
    """
    Aggregated runtime health snapshot for a single logic rule.

    AUT-115: Powers the Climate-Cockpit tile (frontend) and is broadcast
    every 60s via WebSocket as 'rule.health' for all is_critical rules.
    """

    rule_id: uuid.UUID = Field(..., description="Rule ID (UUID)")
    rule_name: str = Field(..., description="Rule name")
    is_critical: bool = Field(False, description="Whether this rule is safety-critical")
    setpoint: Optional[float] = Field(
        None,
        description="Configured threshold (from conditions.activate_below/above/value)",
    )
    current_value: Optional[float] = Field(
        None,
        description="Latest processed sensor value for the trigger sensor",
    )
    deviation: Optional[float] = Field(
        None,
        description="current_value - setpoint (None if either is None)",
    )
    target_esp_id: Optional[str] = Field(
        None,
        description="Target ESP for the first action",
    )
    target_esp_online: bool = Field(
        False,
        description="Whether the target ESP is currently online",
    )
    target_esp_offline_since: Optional[datetime] = Field(
        None,
        description="last_seen timestamp when target ESP is offline",
    )
    last_dispatch: Optional[RuleHealthDispatchInfo] = Field(
        None,
        description="Last successful action dispatch",
    )
    last_skip: Optional[RuleHealthSkipInfo] = Field(
        None,
        description="Last suppressed dispatch",
    )
    degraded_since: Optional[datetime] = Field(
        None,
        description="When the rule entered degraded state (target offline)",
    )
    time_window_active: Optional[str] = Field(
        None,
        description="Label of the active time-window condition (if any)",
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Rule Templates (AUT-224 A1: typed responses)
# =============================================================================


class TemplateListResponse(BaseModel):
    """Response for ``GET /v1/logic/templates``.

    Wraps the dynamic template-info payloads returned by the template loader.
    """

    success: bool = True
    templates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Loaded template metadata dicts (shape determined by loader).",
    )
    total_count: int = 0


class TemplateDetailResponse(BaseModel):
    """Response for ``GET /v1/logic/templates/{template_id}``."""

    success: bool = True
    template: Dict[str, Any] = Field(
        default_factory=dict,
        description="Template metadata and parameter schema (shape from loader).",
    )
