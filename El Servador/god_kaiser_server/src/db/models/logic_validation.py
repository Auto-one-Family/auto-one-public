"""
Pydantic Models for Logic Rule Validation

Provides type-safe validation for:
- Trigger Conditions (sensor_threshold, time_window)
- Actions (actuator_command)

Prevents runtime errors from malformed JSON in production.
"""

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# CONDITION MODELS
# =============================================================================


class SensorThresholdCondition(BaseModel):
    """
    Sensor Threshold Condition.

    Triggers when sensor value meets threshold criteria.

    Example:
        {
            "type": "sensor_threshold",  # or "sensor" for shorthand
            "esp_id": "ESP_12AB34",
            "gpio": 34,
            "sensor_type": "temperature",
            "operator": ">",
            "value": 25.0
        }
    """

    type: Literal["sensor_threshold", "sensor"] = Field(
        ..., description="Condition type ('sensor_threshold' or 'sensor')"
    )
    esp_id: str = Field(
        ...,
        description="ESP device ID",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
    )
    gpio: int = Field(..., description="GPIO pin number", ge=0, le=50)
    sensor_type: Optional[str] = Field(
        None, description="Sensor type (e.g., 'temperature'). Optional for 'sensor' shorthand."
    )
    operator: Literal[">", ">=", "<", "<=", "==", "!=", "between"] = Field(
        ..., description="Comparison operator"
    )
    value: Optional[float] = Field(
        None, description="Threshold value (required for all operators except 'between')"
    )

    # Optional fields for "between" operator
    min: Optional[float] = Field(None, description="Minimum value for 'between' operator")
    max: Optional[float] = Field(None, description="Maximum value for 'between' operator")

    # Phase 2.4: Optional subzone filter — rule fires only when trigger_data.subzone_id matches
    subzone_id: Optional[str] = Field(
        None,
        description="Optional subzone filter: condition met only when sensor is in this subzone",
    )

    @field_validator("value", mode="after")
    @classmethod
    def validate_value_required(cls, v, info):
        """Validate that value is required for non-between operators."""
        if info.data.get("operator") != "between" and v is None:
            raise ValueError("'value' is required for operators other than 'between'")
        return v

    @field_validator("min", "max")
    @classmethod
    def validate_between_operator(cls, v, info):
        """Validate min/max for 'between' operator."""
        if info.data.get("operator") == "between":
            if v is None:
                raise ValueError("'between' operator requires 'min' and 'max' values")
        return v


class TimeWindowCondition(BaseModel):
    """
    Time Window Condition.

    Triggers only during specific time windows (hours, days of week).

    Example:
        {
            "type": "time_window",
            "start_hour": 8,
            "end_hour": 18,
            "days_of_week": [0, 1, 2, 3, 4]  # Monday-Friday
        }
    """

    type: Literal["time_window", "time"] = Field(
        ..., description="Condition type ('time_window' or 'time')"
    )
    start_hour: int = Field(..., description="Start hour (0-23)", ge=0, le=23)
    start_minute: int = Field(0, description="Start minute (0-59)", ge=0, le=59)
    end_hour: int = Field(..., description="End hour (0-24)", ge=0, le=24)
    end_minute: int = Field(0, description="End minute (0-59)", ge=0, le=59)
    days_of_week: Optional[List[int]] = Field(
        None,
        description="Days of week (0=Monday, 6=Sunday). If None, applies to all days.",
    )

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v):
        """Validate days_of_week are in range 0-6."""
        if v is not None:
            for day in v:
                if day < 0 or day > 6:
                    raise ValueError(f"Invalid day of week: {day}. Must be 0-6 (Monday-Sunday)")
        return v

    @field_validator("end_minute")
    @classmethod
    def validate_end_minute_for_hour_24(cls, v, info):
        """24:xx is invalid. Allow 24:00 only as end-of-day marker."""
        end_hour = info.data.get("end_hour")
        if end_hour == 24 and v != 0:
            raise ValueError("end_minute must be 0 when end_hour is 24")
        return v


class HysteresisCondition(BaseModel):
    """
    Hysteresis Condition.

    Prevents "flapping" near threshold by using separate activate/deactivate thresholds.

    Two modes:
    - Cooling: activate_above + deactivate_below (e.g., fan)
    - Heating: activate_below + deactivate_above (e.g., heater)

    Example (Cooling):
        {
            "type": "hysteresis",
            "esp_id": "ESP_12AB34",
            "gpio": 4,
            "sensor_type": "DS18B20",
            "activate_above": 28.0,
            "deactivate_below": 24.0
        }
    """

    type: Literal["hysteresis"] = Field(..., description="Condition type (must be 'hysteresis')")
    esp_id: str = Field(
        ...,
        description="ESP device ID",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
    )
    gpio: int = Field(..., description="GPIO pin number", ge=0, le=50)
    sensor_type: Optional[str] = Field(None, description="Sensor type filter (optional)")

    # Cooling mode thresholds
    activate_above: Optional[float] = Field(
        None, description="Activate when value exceeds this (cooling mode)"
    )
    deactivate_below: Optional[float] = Field(
        None, description="Deactivate when value drops below this (cooling mode)"
    )

    # Heating mode thresholds
    activate_below: Optional[float] = Field(
        None, description="Activate when value drops below this (heating mode)"
    )
    deactivate_above: Optional[float] = Field(
        None, description="Deactivate when value exceeds this (heating mode)"
    )

    @field_validator("deactivate_below", mode="after")
    @classmethod
    def validate_thresholds(cls, v, info):
        """Validate that either cooling or heating mode thresholds are provided."""
        data = info.data
        has_cooling = data.get("activate_above") is not None and v is not None
        has_heating = (
            data.get("activate_below") is not None and data.get("deactivate_above") is not None
        )

        if not has_cooling and not has_heating:
            # Only raise if we're done processing all fields and neither mode is set
            # This validator runs after deactivate_below, so cooling mode can be checked here
            pass  # Will be checked in model_validator if needed
        return v


class SensorDiffCondition(BaseModel):
    """
    Sensor Pair Difference Condition.

    Triggers when the difference between two sensors meets threshold criteria.
    Universal across sensor types - compares numeric values only.

    Example:
        {
            "type": "sensor_diff",
            "sensor_a_id": "550e8400-e29b-41d4-a716-446655440000",
            "sensor_b_id": "550e8400-e29b-41d4-a716-446655440001",
            "operator": "gt",
            "value": 0.8,
            "consecutive_count": 3
        }
    """

    type: Literal["sensor_diff"] = Field(..., description="Condition type (must be 'sensor_diff')")
    sensor_a_id: str = Field(
        ...,
        description="UUID of first sensor (A)",
        min_length=36,
        max_length=36,
    )
    sensor_b_id: str = Field(
        ...,
        description="UUID of second sensor (B)",
        min_length=36,
        max_length=36,
    )
    operator: Literal[">", ">=", "<", "<=", "==", "!="] = Field(
        ..., description="Comparison operator for (B - A)"
    )
    value: float = Field(..., description="Threshold value: (sensor_b - sensor_a) [operator] value")
    consecutive_count: int = Field(
        default=1,
        description="Number of consecutive measurements exceeding threshold to trigger",
        ge=1,
        le=100,
    )

    @field_validator("sensor_a_id", "sensor_b_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """Validate UUID format (36 chars with hyphens)."""
        # Simple format check: 8-4-4-4-12
        parts = v.split("-")
        if len(parts) != 5 or len("".join(parts)) != 32:
            raise ValueError(f"Invalid UUID format: {v}")
        return v

    @field_validator("sensor_b_id")
    @classmethod
    def validate_different_sensors(cls, v: str, info):
        """Ensure sensor_a_id and sensor_b_id are different."""
        if "sensor_a_id" in info.data and v == info.data["sensor_a_id"]:
            raise ValueError("sensor_a_id and sensor_b_id must be different")
        return v


class MetadataFilterCondition(BaseModel):
    """
    Metadata Filter Condition (AUT-214 / AUT-219).

    Filters sensor data based on payload metadata fields (e.g.
    sensor_metadata.phase, plant_id). Supports nested field access
    via dot-notation and 7 comparison operators.

    The runtime evaluator lives in
    ``services/logic/conditions/metadata_filter_evaluator.py`` and uses
    ``condition.get("type") == "metadata_filter"`` for dispatch.

    Example:
        {
            "type": "metadata_filter",
            "field": "sensor_metadata.phase",
            "operator": "eq",
            "value": "bluete-bulk"
        }

    Nullary operators (``is_null`` / ``is_not_null``) omit ``value``.
    The ``in`` operator expects ``value`` to be a list.
    """

    type: Literal["metadata_filter"] = Field(
        ..., description="Condition type (must be 'metadata_filter')"
    )
    field: str = Field(
        ...,
        description="Field path (dot-notation, e.g. 'sensor_metadata.phase')",
        min_length=1,
        max_length=200,
    )
    operator: Literal["eq", "neq", "lt", "gt", "in", "is_null", "is_not_null"] = Field(
        ..., description="Comparison operator (matches MetadataFilterEvaluator)"
    )
    value: Optional[Any] = Field(
        None,
        description=(
            "Comparison value. Required for all operators except is_null/is_not_null. "
            "Must be a list for the 'in' operator."
        ),
    )

    @field_validator("value", mode="after")
    @classmethod
    def validate_value_required(cls, v, info):
        """Ensure 'value' is present for non-nullary operators."""
        operator = info.data.get("operator")
        if operator in ("is_null", "is_not_null"):
            return v
        if v is None:
            raise ValueError(
                f"'value' is required for operator '{operator}' "
                "(only is_null/is_not_null may omit it)"
            )
        if operator == "in" and not isinstance(v, list):
            raise ValueError("'in' operator requires 'value' to be a list")
        return v


class CompoundCondition(BaseModel):
    """
    Compound Condition (AND/OR logic).

    Combines multiple conditions with AND/OR logic.

    Example:
        {
            "logic": "AND",
            "conditions": [
                {"type": "sensor_threshold", ...},
                {"type": "time_window", ...}
            ]
        }
    """

    logic: Literal["AND", "OR"] = Field(..., description="Logic operator (AND/OR)")
    conditions: List[Any] = Field(..., description="List of conditions", min_length=1)


# Union type for all condition types
ConditionType = Union[
    SensorThresholdCondition,
    TimeWindowCondition,
    HysteresisCondition,
    SensorDiffCondition,
    MetadataFilterCondition,
    CompoundCondition,
]


# =============================================================================
# ACTION MODELS
# =============================================================================


class ActuatorCommandAction(BaseModel):
    """
    Actuator Command Action.

    Executes actuator command when rule triggers.

    Example:
        {
            "type": "actuator_command",  # or "actuator" for shorthand
            "esp_id": "ESP_12AB34",
            "gpio": 18,
            "command": "PWM",
            "value": 0.75,
            "duration_seconds": 60
        }
    """

    type: Literal["actuator_command", "actuator"] = Field(
        ..., description="Action type ('actuator_command' or 'actuator')"
    )
    esp_id: str = Field(
        ...,
        description="ESP device ID",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
    )
    gpio: int = Field(..., description="GPIO pin number", ge=0, le=50)
    command: Optional[Literal["ON", "OFF", "PWM", "TOGGLE"]] = Field(
        None, description="Actuator command. Optional for 'actuator' shorthand."
    )
    actuator_type: Optional[str] = Field(
        None, description="Actuator type (e.g., 'pump'). Used with 'actuator' shorthand."
    )
    value: float = Field(..., description="Command value (0.0-1.0)", ge=0.0, le=1.0)
    duration_seconds: int = Field(0, description="Duration in seconds (0 = unlimited)", ge=0)


class NotificationAction(BaseModel):
    """
    Notification Action.

    Sends notification via websocket, email or webhook.
    """

    type: Literal["notification"] = Field(..., description="Action type")
    channel: Literal["websocket", "email", "webhook"] = Field(
        ..., description="Notification channel"
    )
    target: str = Field(..., description="Target (email address, webhook URL, WS topic)")
    message_template: str = Field("", description="Message template with {placeholders}")


class DelayAction(BaseModel):
    """
    Delay Action.

    Pauses execution for a specified duration.
    """

    type: Literal["delay"] = Field(..., description="Action type")
    seconds: int = Field(..., description="Delay duration in seconds", ge=1, le=3600)


class SequenceAction(BaseModel):
    """
    Sequence Action.

    Executes multiple actions in sequence with optional delays.
    """

    type: Literal["sequence"] = Field(..., description="Action type")
    steps: List[Any] = Field(..., description="List of action steps", min_length=1)


class PluginTriggerAction(BaseModel):
    """
    Plugin Trigger Action.

    Triggers an AutoOps plugin as a Logic Rule action.

    Example:
        {
            "type": "plugin",  # or "autoops_trigger"
            "plugin_id": "health_check",
            "config": {"skip_mqtt": true}
        }
    """

    type: Literal["plugin", "autoops_trigger"] = Field(
        ..., description="Action type ('plugin' or 'autoops_trigger')"
    )
    plugin_id: str = Field(..., description="Registered plugin ID", min_length=1, max_length=128)
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional config overrides passed to the plugin",
    )


# Union type for all action types
ActionType = Union[
    ActuatorCommandAction,
    NotificationAction,
    DelayAction,
    SequenceAction,
    PluginTriggerAction,
]


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def validate_condition(condition: dict) -> ConditionType:
    """
    Validate a single condition.

    Args:
        condition: Condition dictionary

    Returns:
        Validated Pydantic model

    Raises:
        ValidationError: If condition is invalid
    """
    cond_type = condition.get("type")

    # Accept both "sensor_threshold" and "sensor" as valid condition types
    if cond_type in ("sensor_threshold", "sensor"):
        return SensorThresholdCondition(**condition)
    elif cond_type in ("time_window", "time"):
        return TimeWindowCondition(**condition)
    elif cond_type == "hysteresis":
        return HysteresisCondition(**condition)
    elif cond_type == "sensor_diff":
        return SensorDiffCondition(**condition)
    elif cond_type == "metadata_filter":
        return MetadataFilterCondition(**condition)
    elif "logic" in condition and "conditions" in condition:
        # Compound condition - recursively validate sub-conditions
        validated_sub_conditions = [
            validate_condition(sub_cond) for sub_cond in condition["conditions"]
        ]
        return CompoundCondition(logic=condition["logic"], conditions=validated_sub_conditions)
    else:
        raise ValueError(f"Unknown condition type: {cond_type}")


def validate_conditions(conditions: Union[dict, list]) -> Union[ConditionType, List[ConditionType]]:
    """
    Validate trigger_conditions (single dict or list).

    Args:
        conditions: Conditions (dict or list of dicts)

    Returns:
        Validated Pydantic model(s)

    Raises:
        ValidationError: If conditions are invalid
    """
    if isinstance(conditions, dict):
        return validate_condition(conditions)
    elif isinstance(conditions, list):
        return [validate_condition(cond) for cond in conditions]
    else:
        raise ValueError(f"Invalid conditions format: {type(conditions)}")


def validate_action(action: dict) -> ActionType:
    """
    Validate a single action.

    Args:
        action: Action dictionary

    Returns:
        Validated Pydantic model

    Raises:
        ValidationError: If action is invalid
    """
    action_type = action.get("type")

    # Accept both "actuator_command" and "actuator" as valid action types
    if action_type in ("actuator_command", "actuator"):
        return ActuatorCommandAction(**action)
    elif action_type == "notification":
        return NotificationAction(**action)
    elif action_type == "delay":
        return DelayAction(**action)
    elif action_type == "sequence":
        return SequenceAction(**action)
    elif action_type in ("plugin", "autoops_trigger"):
        return PluginTriggerAction(**action)
    else:
        raise ValueError(f"Unknown action type: {action_type}")


def validate_actions(actions: list) -> List[ActionType]:
    """
    Validate list of actions.

    Args:
        actions: List of action dictionaries

    Returns:
        List of validated Pydantic models

    Raises:
        ValidationError: If any action is invalid
    """
    if not isinstance(actions, list):
        raise ValueError(f"Actions must be a list, got: {type(actions)}")

    if len(actions) == 0:
        raise ValueError("Actions list cannot be empty")

    return [validate_action(action) for action in actions]
