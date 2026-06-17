"""
Logic Models: CrossESPLogic, LogicExecutionHistory, LogicHysteresisState
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import (
    Boolean,
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

    max_executions_per_hour: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum executions per hour (rate limit)",
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

    # Indices
    __table_args__ = (
        Index("idx_rule_enabled_priority", "enabled", "priority"),
        Index(
            "idx_rule_degraded_critical",
            "is_critical",
            "degraded_since",
            postgresql_where=text("degraded_since IS NOT NULL"),
        ),
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
