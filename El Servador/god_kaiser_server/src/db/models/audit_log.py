"""
Audit Log Model: System Events and Configuration Tracking

Records all significant system events including:
- Config responses from ESP32 devices
- Security events (login attempts, permission changes)
- Operational events (emergency stops, service restarts)
- Error conditions and recovery

Phase: Runtime Config Flow Implementation
Priority: MEDIUM
Status: IMPLEMENTED
"""

import uuid
from typing import Optional

from sqlalchemy import Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """
    Audit Log Model.

    Records system events for traceability, debugging, and compliance.
    Immutable by design - entries should never be modified or deleted
    (except via automated retention policy).

    Performance Indexes:
    - event_type: Fast filtering by event type
    - severity: Fast filtering by severity level
    - source_type, source_id: Fast lookup by source
    - status: Fast filtering by status
    - error_code: Fast error code analysis
    - correlation_id: Fast correlation tracking
    - created_at: Fast time-range queries and retention cleanup

    Attributes:
        id: Primary key (UUID)
        event_type: Type of event (config_response, login, emergency_stop, etc.)
        severity: Event severity (info, warning, error, critical)
        source_type: Source of event (esp32, user, system, api)
        source_id: Identifier of source (esp_id, user_id, etc.)
        status: Event status (success, failed, pending)
        message: Human-readable event description
        details: JSON field with event-specific details
        error_code: Error code if applicable
        error_description: Human-readable error description
        ip_address: Client IP address if applicable
        user_agent: Client user agent if applicable
        correlation_id: ID for correlating related events
    """

    __tablename__ = "audit_logs"

    # Table-level index for time-based queries (retention, reporting)
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_severity_created_at", "severity", "created_at"),
        Index("ix_audit_logs_source_created_at", "source_type", "source_id", "created_at"),
    )

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Event Classification
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Type of event (config_response, login, emergency_stop, error, etc.)",
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        default="info",
        nullable=False,
        index=True,
        doc="Event severity (info, warning, error, critical)",
    )

    # Source Identification
    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        doc="Source type (esp32, user, system, api, mqtt)",
    )

    source_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Identifier of source (esp_id, user_id, etc.)",
    )

    # Event Details
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Event status (success, failed, pending, or lifecycle event_type up to 50 chars)",
    )

    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable event description",
    )

    details: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="JSON field with event-specific details",
    )

    # Error Information
    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        doc="Error code if applicable",
    )

    error_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable error description",
    )

    # Request Context (for API/web events)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        doc="Client IP address if applicable",
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Client user agent if applicable",
    )

    # Correlation (for tracing related events)
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Correlation ID for tracing related events",
    )

    # Request-ID (for server-log correlation)
    # VARCHAR(255) to support MQTT-generated IDs like "unknown:heartbeat:no-seq:{timestamp}"
    request_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        doc="HTTP or MQTT request ID for server-log correlation",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(event_type='{self.event_type}', "
            f"source='{self.source_type}:{self.source_id}', "
            f"status='{self.status}')>"
        )

    @property
    def is_error(self) -> bool:
        """Check if this is an error event."""
        return self.severity in ("error", "critical") or self.status == "failed"

    @property
    def is_critical(self) -> bool:
        """Check if this is a critical event."""
        return self.severity == "critical"


# Event Type Constants (for consistent usage across codebase)
class AuditEventType:
    """Audit event type constants."""

    # Config Events
    CONFIG_RESPONSE = "config_response"
    CONFIG_PUBLISHED = "config_published"
    CONFIG_FAILED = "config_failed"

    # Auth Events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REVOKED = "token_revoked"

    # Security Events
    PERMISSION_DENIED = "permission_denied"
    API_KEY_INVALID = "api_key_invalid"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # Operational Events
    EMERGENCY_STOP = "emergency_stop"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"
    DEVICE_REGISTERED = "device_registered"
    DEVICE_OFFLINE = "device_offline"

    # ESP Lifecycle Events
    DEVICE_DISCOVERED = "device_discovered"
    DEVICE_APPROVED = "device_approved"
    DEVICE_REJECTED = "device_rejected"
    DEVICE_ONLINE = "device_online"
    DEVICE_REDISCOVERED = "device_rediscovered"
    LWT_RECEIVED = "lwt_received"

    # Actuator Command Events
    ACTUATOR_COMMAND = "actuator_command"
    ACTUATOR_COMMAND_FAILED = "actuator_command_failed"

    # Config Validation Events
    CONFIG_OFFLINE_RULES_STRIPPED = "config_offline_rules_stripped"

    # Error Events
    MQTT_ERROR = "mqtt_error"
    DATABASE_ERROR = "database_error"
    VALIDATION_ERROR = "validation_error"
    API_ERROR = "api_error"


class AuditSeverity:
    """Audit severity level constants."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditSourceType:
    """Audit source type constants."""

    ESP32 = "esp32"
    USER = "user"
    SYSTEM = "system"
    API = "api"
    MQTT = "mqtt"
    SCHEDULER = "scheduler"
