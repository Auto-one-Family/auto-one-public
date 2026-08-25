"""
Logic Models: CrossESPLogic, LogicExecutionHistory, LogicHysteresisState
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from ..base import Base, TimestampMixin
from .logic_validation import validate_actions, validate_conditions

# AUT-1173 (TAX-5): fixed rule_group catalog — single source of truth shared by the
# DB CheckConstraint (below) and the Pydantic schemas (schemas/logic.py). A
# user-benennbarer Katalog ist bewusst NICHT Teil dieser Welle.
#
# Variante C (AUT-1163 Entscheidung): Messgröße als Primärachse, "sicherheit" als
# einzige feste Ausnahme (Risikoeinstufung schlägt Messgröße). Die 9 Messgrößen-Werte
# sind 1:1 gespiegelt von AggCategory (El Frontend/src/utils/sensorDefaults.ts:1610-1654)
# — deutschsprachig benannt, siehe LogicService._sensor_type_to_messgroesse(). "alarm"
# und "dosierung" entfallen als eigene Gruppen (Regelausführung wird ein Kennzeichen
# innerhalb der Messgrößen-Gruppe, AUT-1176/TAX-8 — nicht hier).
RULE_GROUP_CATALOG: tuple[str, ...] = (
    "ph",
    "ec",
    "bodenfeuchte",
    "luftfeuchte",
    "temperatur",
    "co2",
    "luftdruck",
    "licht",
    "durchfluss",
    "zeitplan",
    "sicherheit",
    "sonstiges",
)
_RULE_GROUP_CHECK = f"rule_group IN ({', '.join(repr(g) for g in RULE_GROUP_CATALOG)})"


class CrossESPLogic(Base, TimestampMixin):
    """
    Cross-ESP Logic Model (Automation Rules).

    Stores automation rules that trigger actions based on sensor data
    across multiple ESPs. Enables complex multi-device automation.

    Attributes:
        id: Primary key (UUID)
        rule_name: Unique rule name (also accessible as 'name' property)
        description: Human-readable rule description
        enabled: Whether rule is active
        trigger_conditions: JSON conditions (also accessible as 'conditions' property)
        logic_operator: Logic operator for multiple conditions (AND/OR)
        actions: JSON actions to execute (actuator commands, notifications, etc.)
        priority: Execution priority (lower = higher priority)
        cooldown_seconds: Minimum time between executions (prevents spam)
        max_executions_per_hour: Maximum executions per hour (rate limit)
        last_triggered: Timestamp of last execution
        metadata: Additional rule metadata
    """

    __tablename__ = "cross_esp_logic"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Rule Identity
    rule_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique rule name",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable rule description",
    )

    # Rule Status
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        doc="Whether rule is active",
    )

    # Trigger Conditions (CRITICAL!)
    trigger_conditions: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc=(
            "Trigger conditions (sensor thresholds, time windows, etc.). "
            "Example: {'type': 'sensor_threshold', 'esp_id': 'ESP_12AB34', 'gpio': 34, "
            "'sensor_type': 'temperature', 'operator': '>', 'value': 25.0}"
        ),
    )

    # Logic Operator for Multiple Conditions
    logic_operator: Mapped[str] = mapped_column(
        String(3),
        default="AND",
        nullable=False,
        doc="Logic operator for multiple conditions (AND/OR)",
    )

    # Actions (CRITICAL!)
    actions: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        doc=(
            "Actions to execute when triggered. "
            "Example: [{'type': 'actuator_command', 'esp_id': 'ESP_12AB34', 'gpio': 18, "
            "'actuator_type': 'pump', 'value': 0.75, 'duration_seconds': 60}]"
        ),
    )

    # Execution Control
    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        doc="Execution priority (lower = higher priority)",
    )

    cooldown_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Minimum time between executions (prevents spam)",
    )

    settle_after_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc=(
            "AUT-1115: Wait for settle_seconds after the last execution of THIS "
            "other rule before evaluating. NULL = no settle dependency."
        ),
    )

    settle_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc=(
            "AUT-1115: Settle window in seconds, evaluated against "
            "settle_after_rule_id's last execution. NULL = no settle wait."
        ),
    )

    max_executions_per_hour: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum executions per hour (rate limit)",
    )
    max_executions_per_day: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum executions per day (rolling 24h window)",
    )
    max_dose_ml_per_day: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Maximum total dose ml per day (rolling 24h window, requires AO-5 dose_ml audit field)",
    )

    last_triggered: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last execution",
    )

    # Metadata
    rule_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional rule metadata (tags, category, owner, etc.)",
    )

    # AUT-111: Critical-Rule Degraded-Handling
    is_critical: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this rule is safety-critical (enables degraded-state tracking)",
    )

    escalation_policy: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc=(
            "Escalation policy for critical rules when degraded. "
            "Shape: {'notify': ['email','websocket'], 'retry_interval_s': 60, "
            "'max_retries': 5, 'failover_actions': [...]}"
        ),
    )

    degraded_since: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when rule entered degraded state (target ESP offline)",
    )

    degraded_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Reason for degraded state (e.g. 'target_esp_offline:ESP_AABB')",
    )

    # AUT-1145 (S0): explicit display-group override (see RULE_GROUP_CATALOG).
    # NULL = no override, group is derived from the rule's mechanic
    # (LogicService.derive_rule_group() — the only place this may happen,
    # never re-implemented in the frontend). No backfill for existing rows.
    rule_group: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Explicit rule_group override (see RULE_GROUP_CATALOG). NULL = auto-derived.",
    )

    # AUT-1232 (Welle 5 T2): Opt-in plan subscription. Default False — existing
    # rules stay non-subscribing after migration. Engine wiring is T3.
    follows_plan: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="AUT-1232: When True, rule may read plan_segment@now (T3); default False",
    )

    plan_zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="SET NULL"),
        nullable=True,
        doc="AUT-1232: Zone reference for plan subscription (nullable)",
    )

    plan_subzone_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="AUT-1232: Optional subzone_config scope for plan subscription",
    )

    plan_domain: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="AUT-1232: Plan domain (see PLAN_DOMAINS); NULL when not subscribed",
    )

    plan_measure: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="AUT-1232: Plan measure (see PLAN_MEASURES); NULL when not subscribed",
    )

    # Indices
    __table_args__ = (
        Index("idx_rule_enabled_priority", "enabled", "priority"),
        Index(
            "idx_rule_degraded_critical",
            "is_critical",
            "degraded_since",
            postgresql_where=text("degraded_since IS NOT NULL"),
        ),
        CheckConstraint(_RULE_GROUP_CHECK, name="ck_cross_esp_logic_rule_group"),
    )

    # Alias properties for API compatibility
    @property
    def name(self) -> str:
        """Alias for rule_name (API compatibility)."""
        return self.rule_name

    @name.setter
    def name(self, value: str) -> None:
        """Setter for name alias."""
        self.rule_name = value

    @property
    def conditions(self) -> list:
        """Return trigger_conditions as list format (API compatibility)."""
        if isinstance(self.trigger_conditions, list):
            return self.trigger_conditions
        # Single condition dict -> wrap in list
        return [self.trigger_conditions]

    @conditions.setter
    def conditions(self, value: list) -> None:
        """Setter for conditions - stores as trigger_conditions."""
        self.trigger_conditions = value

    # =========================================================================
    # VALIDATORS (Pydantic Validation for Production Safety)
    # =========================================================================

    @validates("trigger_conditions")
    def validate_trigger_conditions(self, key, value):
        """
        Validate trigger_conditions using Pydantic models.

        Ensures conditions are well-formed before saving to database.
        Prevents runtime errors from malformed JSON.

        Args:
            key: Column name
            value: Conditions (dict or list)

        Returns:
            Validated conditions (original format)

        Raises:
            ValidationError: If conditions are invalid
        """
        if value is None:
            raise ValueError("trigger_conditions cannot be None")

        try:
            # Validate using Pydantic models
            validate_conditions(value)
            # Return original value (Pydantic validation doesn't modify)
            return value
        except ValidationError as e:
            raise ValueError(f"Invalid trigger_conditions: {e}")

    @validates("actions")
    def validate_actions_field(self, key, value):
        """
        Validate actions using Pydantic models.

        Ensures actions are well-formed before saving to database.
        Prevents runtime errors from malformed JSON.

        Args:
            key: Column name
            value: Actions list

        Returns:
            Validated actions (original format)

        Raises:
            ValidationError: If actions are invalid
        """
        if value is None:
            raise ValueError("actions cannot be None")

        try:
            # Validate using Pydantic models
            validate_actions(value)
            # Return original value (Pydantic validation doesn't modify)
            return value
        except ValidationError as e:
            raise ValueError(f"Invalid actions: {e}")

    # =========================================================================

    def __repr__(self) -> str:
        return f"<CrossESPLogic(rule_name='{self.rule_name}', enabled={self.enabled})>"


class LogicExecutionHistory(Base):
    """
    Logic Execution History (Time-Series).

    Stores history of logic rule executions for auditing and analytics.
    Optimized for high-volume inserts with time-based indices.

    Attributes:
        id: Primary key (UUID)
        logic_rule_id: Foreign key to logic rule
        trigger_data: JSON snapshot of sensor data that triggered rule
        actions_executed: JSON snapshot of actions that were executed
        success: Whether execution succeeded
        is_skip: True for self-generated cooldown/settle/rate-limit skip markers
        error_message: Error message if failed
        execution_time_ms: Execution duration in milliseconds
        timestamp: Execution timestamp
        metadata: Additional execution metadata
    """

    __tablename__ = "logic_execution_history"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    logic_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_esp_logic.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to logic rule",
    )

    # Execution Data
    trigger_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc="Snapshot of sensor data that triggered rule (for auditing)",
    )

    actions_executed: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        doc="Snapshot of actions that were executed",
    )

    # Result
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        doc="Whether execution succeeded",
    )

    # AUT-1020 skip markers (cooldown/settle/rate-limit) vs. real execution attempts
    is_skip: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc=(
            "True for self-generated cooldown/settle/rate-limit skip markers "
            "(AUT-1020) — excluded from get_last_execution()"
        ),
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Error message if execution failed",
    )

    # Performance Metrics
    execution_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Execution duration in milliseconds",
    )

    # Timestamp (CRITICAL for Time-Series!)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
        doc="Execution timestamp",
    )

    # Metadata
    execution_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Additional execution metadata (retry_count, etc.)",
    )

    # AO-5: Dosier-Audit Felder
    dose_ml: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Dispensed volume in ml. NULL for time-only dispatch or non-pump actions.",
    )

    flow_rate_ml_s_snapshot: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc=(
            "Flow rate snapshot in ml/s at execution time. Immutable audit "
            "record — independent from actuator_configs.flow_rate_ml_s which "
            "may change later."
        ),
    )

    # Time-Series Optimized Indices
    __table_args__ = (
        Index("idx_logic_rule_timestamp", "logic_rule_id", "timestamp"),
        Index("idx_success_timestamp_logic", "success", "timestamp"),
        Index("idx_timestamp_desc_logic", "timestamp", postgresql_ops={"timestamp": "DESC"}),
    )

    def __repr__(self) -> str:
        return (
            f"<LogicExecutionHistory(logic_rule_id='{self.logic_rule_id}', "
            f"success={self.success}, timestamp='{self.timestamp.isoformat()}')>"
        )


class LogicHysteresisState(Base):
    """
    Persistent hysteresis state for Logic Engine rules.

    Survives server restarts. Without persistence, active hysteresis states
    reset to inactive on restart, leaving actuators running uncontrolled
    until the next threshold crossing.

    State-Key: (rule_id, condition_index) — one state per hysteresis condition.
    CASCADE delete: removing a rule auto-removes its hysteresis state.
    """

    __tablename__ = "logic_hysteresis_states"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Primary key",
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_esp_logic.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to logic rule",
    )

    condition_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Index of the hysteresis condition within the rule",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Current activation state (True = actuator ON)",
    )

    last_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Last processed sensor value",
    )

    last_activation: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last activation",
    )

    last_deactivation: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last deactivation",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="Timestamp of last state update",
    )

    __table_args__ = (
        UniqueConstraint("rule_id", "condition_index", name="uq_hysteresis_state_rule_cond"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogicHysteresisState(rule_id='{self.rule_id}', "
            f"condition_index={self.condition_index}, is_active={self.is_active})>"
        )
