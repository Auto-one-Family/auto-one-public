"""
Alert Configuration Pydantic Schemas

Phase 4A.7: Per-Sensor/Device Alert Configuration
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .common import BaseResponse

# =============================================================================
# Sensor/Actuator Alert Config
# =============================================================================


class CustomThresholds(BaseModel):
    """Custom threshold overrides for a sensor."""

    warning_min: Optional[float] = None
    warning_max: Optional[float] = None
    critical_min: Optional[float] = None
    critical_max: Optional[float] = None


class SensorAlertConfigUpdate(BaseModel):
    """Schema for updating per-sensor alert configuration."""

    alerts_enabled: Optional[bool] = Field(
        None, description="Master toggle for this sensor's alerts"
    )
    suppression_reason: Optional[str] = Field(
        None,
        description="Reason for suppression: maintenance, intentionally_offline, calibration, custom",
    )
    suppression_note: Optional[str] = Field(
        None, max_length=500, description="Free-text note for suppression"
    )
    suppression_until: Optional[str] = Field(
        None, description="ISO datetime — auto re-enable after this time"
    )
    custom_thresholds: Optional[CustomThresholds] = Field(
        None, description="Override global thresholds for this sensor"
    )
    severity_override: Optional[str] = Field(
        None, description="Override default severity: critical, warning, info"
    )
    notification_channels: Optional[List[str]] = Field(
        None, description="Override channels for this sensor (null = global)"
    )

    @field_validator("suppression_reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["maintenance", "intentionally_offline", "calibration", "custom"]
            if v not in valid:
                raise ValueError(f"suppression_reason must be one of {valid}")
        return v

    @field_validator("severity_override")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["critical", "warning", "info"]
            if v not in valid:
                raise ValueError(f"severity_override must be one of {valid}")
        return v


class SensorAlertConfigResponse(BaseResponse):
    """Response for sensor alert config."""

    esp_id: str
    gpio: int
    sensor_type: str
    sensor_name: str
    alert_config: Dict[str, Any] = Field(default_factory=dict)


class SensorAlertConfigViewResponse(BaseModel):
    """Lightweight response for GET/PATCH per-sensor alert config endpoints.

    Matches the legacy ``{status, alert_config, thresholds}`` payload shape used by
    ``/v1/sensors/{sensor_id}/alert-config`` so consumers don't break.
    """

    status: str = Field("ok", description="Operation status marker")
    alert_config: Dict[str, Any] = Field(default_factory=dict)
    thresholds: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Default thresholds (only present on GET).",
    )


# =============================================================================
# Actuator Alert Config
# =============================================================================


class ActuatorAlertConfigUpdate(BaseModel):
    """Schema for updating per-actuator alert configuration.

    Separate from SensorAlertConfigUpdate for independent evolution.
    Actuators may gain actuator-specific fields (e.g., command_suppression,
    safety_override) without affecting sensor alert config.
    """

    alerts_enabled: Optional[bool] = Field(
        None, description="Master toggle for this actuator's alerts"
    )
    suppression_reason: Optional[str] = Field(
        None,
        description="Reason for suppression: maintenance, intentionally_offline, calibration, custom",
    )
    suppression_note: Optional[str] = Field(
        None, max_length=500, description="Free-text note for suppression"
    )
    suppression_until: Optional[str] = Field(
        None, description="ISO datetime — auto re-enable after this time"
    )
    custom_thresholds: Optional[CustomThresholds] = Field(
        None, description="Override global thresholds for this actuator"
    )
    severity_override: Optional[str] = Field(
        None, description="Override default severity: critical, warning, info"
    )
    notification_channels: Optional[List[str]] = Field(
        None, description="Override channels for this actuator (null = global)"
    )

    @field_validator("suppression_reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["maintenance", "intentionally_offline", "calibration", "custom"]
            if v not in valid:
                raise ValueError(f"suppression_reason must be one of {valid}")
        return v

    @field_validator("severity_override")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["critical", "warning", "info"]
            if v not in valid:
                raise ValueError(f"severity_override must be one of {valid}")
        return v


class ActuatorAlertConfigResponse(BaseResponse):
    """Response for actuator alert config."""

    actuator_id: str
    actuator_type: str
    actuator_name: str
    alert_config: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Device Alert Config
# =============================================================================


class DeviceAlertConfigUpdate(BaseModel):
    """Schema for updating device-level alert configuration."""

    alerts_enabled: Optional[bool] = Field(None, description="Master toggle for device alerts")
    suppression_reason: Optional[str] = Field(None)
    suppression_note: Optional[str] = Field(None, max_length=500)
    suppression_until: Optional[str] = Field(None)
    propagate_to_children: Optional[bool] = Field(
        None, description="Propagate suppression to all child sensors/actuators"
    )

    @field_validator("suppression_reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["maintenance", "intentionally_offline", "calibration", "custom"]
            if v not in valid:
                raise ValueError(f"suppression_reason must be one of {valid}")
        return v


class DeviceAlertConfigResponse(BaseResponse):
    """Response for device alert config."""

    device_id: str
    alert_config: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Runtime Stats
# =============================================================================


class MaintenanceLogEntry(BaseModel):
    """Single maintenance log entry."""

    date: str = Field(..., description="ISO date of maintenance")
    action: str = Field(..., max_length=500, description="Maintenance action performed")
    notes: Optional[str] = Field(None, max_length=500, description="Additional notes")


class RuntimeStatsUpdate(BaseModel):
    """Schema for updating runtime stats."""

    expected_lifetime_hours: Optional[float] = Field(None, ge=0)
    maintenance_log: Optional[List[MaintenanceLogEntry]] = Field(
        None, description="Full maintenance log (replaces existing)"
    )


class RuntimeStatsResponse(BaseResponse):
    """Response for runtime stats."""

    runtime_stats: Dict[str, Any] = Field(default_factory=dict)
    # Computed fields from device metadata
    computed_uptime_hours: Optional[float] = None
    last_restart: Optional[str] = None
    next_maintenance: Optional[str] = None
    maintenance_overdue: bool = False


class SensorRuntimeViewResponse(BaseModel):
    """Response for ``GET /v1/sensors/{sensor_id}/runtime``.

    Mirrors the historic dict payload (status, runtime_stats, computed fields)
    so frontend consumers continue to work without changes.
    """

    status: str = Field("ok", description="Operation status marker")
    runtime_stats: Dict[str, Any] = Field(default_factory=dict)
    computed_uptime_hours: Optional[float] = None
    last_restart: Optional[str] = None
    expected_lifetime_hours: Optional[float] = None
    maintenance_log: List[Dict[str, Any]] = Field(default_factory=list)
    next_maintenance: Optional[str] = None
    maintenance_overdue: bool = False


class SensorRuntimeUpdateResponse(BaseModel):
    """Response for ``PATCH /v1/sensors/{sensor_id}/runtime``.

    Matches the legacy ``{status, runtime_stats}`` payload.
    """

    status: str = Field("ok", description="Operation status marker")
    runtime_stats: Dict[str, Any] = Field(default_factory=dict)
