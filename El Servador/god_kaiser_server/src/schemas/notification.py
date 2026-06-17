"""
Notification Pydantic Schemas

Phase 4A.1: Notification-Stack Backend
Priority: HIGH
Status: IMPLEMENTED

Provides:
- NotificationCreate: Input schema for creating notifications
- NotificationResponse: Output schema for single notification
- NotificationListResponse: Paginated notification list
- NotificationPreferencesUpdate: Input for updating preferences
- NotificationPreferencesResponse: Output for preferences
- NotificationUnreadCountResponse: Badge counter
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse, PaginationMeta

# =============================================================================
# Severity / Source / Category Constants
# =============================================================================

NOTIFICATION_SEVERITIES = ["critical", "warning", "info"]
ALERT_STATUSES = ["active", "acknowledged", "resolved"]

# Query-string filters (FastAPI + Pydantic): invalid values → 422 instead of empty/ignored results.
NotificationListStatusFilter = Literal["active", "acknowledged", "resolved"]
NotificationSourceBucketQuery = Literal["system"]
EmailLogStatusFilter = Literal["pending", "sent", "failed", "permanently_failed"]

NOTIFICATION_SOURCES = [
    "logic_engine",
    "mqtt_handler",
    "grafana",
    "sensor_threshold",
    "device_event",
    "autoops",
    "manual",
    "system",
    "ai_anomaly_service",  # Phase K4 / L2.2 — KI-Anomalie → Notification-Pipeline
    "freshness_reminder",  # Sensor-Lifecycle: Messwert-Alter überschritten
    "calibration_reminder",  # Sensor-Lifecycle: Kalibrierung fällig
]
NOTIFICATION_CATEGORIES = [
    "connectivity",
    "data_quality",
    "infrastructure",
    "lifecycle",
    "maintenance",
    "security",
    "system",
    "ai_anomaly",  # Phase K4 / L2.2 — Kategorie für KI-Anomalie-Alerts
]


# =============================================================================
# Notification Schemas
# =============================================================================


class NotificationCreate(BaseModel):
    """Schema for creating a new notification (internal + API)."""

    user_id: Optional[int] = Field(
        None,
        description="Target user ID. If None, broadcasts to all users.",
    )
    channel: str = Field(
        default="websocket",
        description="Delivery channel (websocket, email, webhook)",
    )
    severity: str = Field(
        default="info",
        description="Severity level (critical, warning, info)",
    )
    category: str = Field(
        default="system",
        description="Alert category",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Short notification title",
    )
    body: Optional[str] = Field(
        None,
        description="Full notification body text",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (esp_id, sensor_type, rule_id, etc.)",
    )
    source: str = Field(
        default="system",
        description="Notification origin",
    )
    parent_notification_id: Optional[uuid.UUID] = Field(
        None,
        description="Parent notification ID for cascade suppression",
    )
    fingerprint: Optional[str] = Field(
        None,
        max_length=64,
        description="Unique fingerprint for alert deduplication (e.g., Grafana alert fingerprint)",
    )
    correlation_id: Optional[str] = Field(
        None,
        max_length=128,
        description="Correlation ID for grouping related alerts (e.g., grafana_{fingerprint})",
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in NOTIFICATION_SEVERITIES:
            raise ValueError(f"severity must be one of {NOTIFICATION_SEVERITIES}")
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in NOTIFICATION_SOURCES:
            raise ValueError(f"source must be one of {NOTIFICATION_SOURCES}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in NOTIFICATION_CATEGORIES:
            raise ValueError(f"category must be one of {NOTIFICATION_CATEGORIES}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "severity": "warning",
                "category": "data_quality",
                "title": "Sensor data stale",
                "body": "SHT31 temperature sensor has not reported for 5 minutes",
                "source": "sensor_threshold",
                "metadata": {"esp_id": "ESP_12AB34CD", "sensor_type": "sht31_temp"},
            }
        }
    )


class NotificationResponse(BaseModel):
    """Schema for a single notification response."""

    id: uuid.UUID
    user_id: int
    channel: str
    severity: str
    category: str
    title: str
    body: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="extra_data")
    source: str
    is_read: bool
    is_archived: bool
    digest_sent: bool
    parent_notification_id: Optional[uuid.UUID] = None
    fingerprint: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    # Alert Lifecycle (Phase 4B)
    status: str = Field(default="active", description="Alert lifecycle status")
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    correlation_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class NotificationListResponse(BaseResponse):
    """Paginated list of notifications."""

    data: List[NotificationResponse] = Field(default_factory=list)
    pagination: PaginationMeta


class NotificationUnreadCountResponse(BaseResponse):
    """Unread notification count for badge."""

    unread_count: int = Field(
        ...,
        ge=0,
        description="Number of unread notifications",
    )
    highest_severity: Optional[str] = Field(
        None,
        description="Highest severity among unread notifications",
    )


class NotificationSendRequest(BaseModel):
    """Admin request to manually send a notification."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Notification title",
    )
    body: Optional[str] = Field(None, description="Notification body")
    severity: str = Field(default="info")
    category: str = Field(default="system")
    source: str = Field(default="manual")
    channel: str = Field(default="websocket")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in NOTIFICATION_SEVERITIES:
            raise ValueError(f"severity must be one of {NOTIFICATION_SEVERITIES}")
        return v


# =============================================================================
# Alert Lifecycle Schemas (Phase 4B)
# =============================================================================


class AlertStatsResponse(BaseResponse):
    """Alert statistics for dashboard display."""

    active_count: int = Field(0, ge=0, description="Number of active alerts")
    acknowledged_count: int = Field(0, ge=0, description="Number of acknowledged alerts")
    resolved_today_count: int = Field(0, ge=0, description="Alerts resolved today")
    critical_active: int = Field(0, ge=0, description="Active critical alerts")
    warning_active: int = Field(0, ge=0, description="Active warning alerts")
    mean_time_to_acknowledge_s: Optional[float] = Field(
        None, description="Average time to acknowledge (seconds)"
    )
    mean_time_to_resolve_s: Optional[float] = Field(
        None, description="Average time to resolve (seconds)"
    )


class AlertActiveListResponse(BaseResponse):
    """List of active alerts with pagination."""

    data: List[NotificationResponse] = Field(default_factory=list)
    pagination: PaginationMeta


class AlertBulkResolveResponse(BaseResponse):
    """Bulk resolve response for unresolved alerts."""

    resolved_count: int = Field(0, ge=0, description="Number of resolved alerts")


# =============================================================================
# Notification Preferences Schemas
# =============================================================================


class NotificationPreferencesUpdate(BaseModel):
    """Schema for updating user notification preferences."""

    websocket_enabled: Optional[bool] = Field(None, description="Enable WebSocket notifications")
    email_enabled: Optional[bool] = Field(None, description="Enable email notifications")
    email_address: Optional[str] = Field(None, description="Override email address")
    email_severities: Optional[List[str]] = Field(None, description="Severities that trigger email")
    quiet_hours_enabled: Optional[bool] = Field(None, description="Enable quiet hours")
    quiet_hours_start: Optional[str] = Field(
        None,
        description="Quiet hours start (HH:MM)",
        pattern=r"^\d{2}:\d{2}$",
    )
    quiet_hours_end: Optional[str] = Field(
        None,
        description="Quiet hours end (HH:MM)",
        pattern=r"^\d{2}:\d{2}$",
    )
    digest_interval_minutes: Optional[int] = Field(
        None,
        ge=0,
        le=1440,
        description="Digest interval in minutes (0 = disabled)",
    )
    browser_notifications: Optional[bool] = Field(None, description="Enable browser notifications")

    @field_validator("email_severities")
    @classmethod
    def validate_email_severities(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            for s in v:
                if s not in NOTIFICATION_SEVERITIES:
                    raise ValueError(
                        f"Invalid severity '{s}', must be one of {NOTIFICATION_SEVERITIES}"
                    )
        return v


class NotificationPreferencesResponse(BaseModel):
    """Schema for notification preferences response."""

    user_id: int
    websocket_enabled: bool = True
    email_enabled: bool = False
    email_address: Optional[str] = None
    email_severities: List[str] = Field(default_factory=lambda: ["critical", "warning"])
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = "22:00"
    quiet_hours_end: Optional[str] = "07:00"
    digest_interval_minutes: int = 60
    browser_notifications: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Test Email Schema
# =============================================================================


class TestEmailRequest(BaseModel):
    """Request to send a test email."""

    email: Optional[str] = Field(
        None,
        description="Recipient email address. If None, uses user's email from preferences or account.",
    )


class TestEmailResponse(BaseResponse):
    """Response for test email request."""

    provider: Optional[str] = Field(None, description="Email provider used (Resend or SMTP)")
    recipient: Optional[str] = Field(None, description="Recipient email address")


# =============================================================================
# Email Log Schemas (Phase C V1.1)
# =============================================================================


class EmailLogResponse(BaseModel):
    """Schema for a single email log entry."""

    id: uuid.UUID
    notification_id: Optional[uuid.UUID] = None
    to_address: str
    subject: str
    template: Optional[str] = None
    provider: str
    status: str
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EmailLogBrief(BaseModel):
    """Brief email log for embedding in notification responses."""

    status: str
    provider: str
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EmailLogListResponse(BaseResponse):
    """Paginated list of email logs."""

    data: List[EmailLogResponse] = Field(default_factory=list)
    pagination: PaginationMeta


class EmailLogStatsResponse(BaseResponse):
    """Email sending statistics."""

    total: int = 0
    sent: int = 0
    failed: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_provider: Dict[str, int] = Field(default_factory=dict)
