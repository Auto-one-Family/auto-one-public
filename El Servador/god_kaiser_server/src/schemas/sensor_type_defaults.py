"""
Pydantic schemas for SensorTypeDefaults API.

Provides request/response models for sensor type default configuration endpoints.

Phase: 2A - Sensor Operating Modes
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse

# =============================================================================
# OPERATING MODE VALIDATION
# =============================================================================

VALID_OPERATING_MODES = {"continuous", "on_demand", "scheduled", "paused"}


def validate_operating_mode(value: str) -> str:
    """Validate operating mode value."""
    value = value.lower().strip()
    if value not in VALID_OPERATING_MODES:
        raise ValueError(
            f"Invalid operating_mode '{value}'. "
            f"Must be one of: {', '.join(sorted(VALID_OPERATING_MODES))}"
        )
    return value


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class SensorTypeDefaultsCreate(BaseModel):
    """Request schema for creating sensor type defaults."""

    sensor_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique sensor type identifier (e.g., 'ph', 'temperature')",
        examples=["ph", "temperature", "humidity"],
    )

    operating_mode: str = Field(
        "continuous",
        description="Default operating mode",
        examples=["continuous", "on_demand"],
    )

    measurement_interval_seconds: int = Field(
        30,
        ge=1,
        le=86400,
        description="Default measurement interval in seconds (1-86400)",
    )

    timeout_seconds: int = Field(
        180,
        ge=0,
        le=86400,
        description="Timeout for stale detection (0 = no timeout)",
    )

    timeout_warning_enabled: bool = Field(
        True,
        description="Whether to show warnings when timeout is exceeded",
    )

    supports_on_demand: bool = Field(
        False,
        description="Whether this sensor type supports manual measurements",
    )

    description: Optional[str] = Field(
        None,
        max_length=500,
        description="User-facing description of recommended usage",
    )

    schedule_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Default schedule configuration for scheduled mode",
    )

    measurement_freshness_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,
        description="Hours after which on-demand/scheduled measurement is considered stale (NULL = no limit)",
    )

    calibration_interval_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Days between recommended recalibrations (NULL = no reminder)",
    )

    @field_validator("operating_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        return validate_operating_mode(v)

    @field_validator("sensor_type")
    @classmethod
    def normalize_sensor_type(cls, v: str) -> str:
        return v.lower().strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sensor_type": "ph",
                "operating_mode": "on_demand",
                "measurement_interval_seconds": 0,
                "timeout_seconds": 0,
                "timeout_warning_enabled": False,
                "supports_on_demand": True,
                "description": "PH-Sensoren werden manuell bei Bedarf ausgelöst",
                "measurement_freshness_hours": 24,
                "calibration_interval_days": 30,
            }
        }
    )


class SensorTypeDefaultsUpdate(BaseModel):
    """Request schema for updating sensor type defaults."""

    operating_mode: Optional[str] = Field(
        None,
        description="Default operating mode",
    )

    measurement_interval_seconds: Optional[int] = Field(
        None,
        ge=1,
        le=86400,
        description="Default measurement interval in seconds",
    )

    timeout_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Timeout for stale detection (0 = no timeout)",
    )

    timeout_warning_enabled: Optional[bool] = Field(
        None,
        description="Whether to show warnings when timeout is exceeded",
    )

    supports_on_demand: Optional[bool] = Field(
        None,
        description="Whether this sensor type supports manual measurements",
    )

    description: Optional[str] = Field(
        None,
        max_length=500,
        description="User-facing description",
    )

    schedule_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Default schedule configuration",
    )

    measurement_freshness_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,
        description="Hours after which measurement is stale (NULL = no limit)",
    )

    calibration_interval_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Days between recalibrations (NULL = no reminder)",
    )

    @field_validator("operating_mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_operating_mode(v)
        return v


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================


class SensorTypeDefaultsResponse(BaseModel):
    """Response schema for sensor type defaults."""

    id: UUID = Field(..., description="Unique identifier")
    sensor_type: str = Field(..., description="Sensor type identifier")
    operating_mode: str = Field(..., description="Default operating mode")
    measurement_interval_seconds: int = Field(..., description="Default measurement interval")
    timeout_seconds: int = Field(..., description="Timeout for stale detection")
    timeout_warning_enabled: bool = Field(..., description="Timeout warning enabled")
    supports_on_demand: bool = Field(..., description="Supports manual measurements")
    description: Optional[str] = Field(None, description="Usage description")
    schedule_config: Optional[Dict[str, Any]] = Field(None, description="Schedule configuration")
    measurement_freshness_hours: Optional[int] = Field(None, description="Freshness limit in hours")
    calibration_interval_days: Optional[int] = Field(
        None, description="Calibration interval in days"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class SensorTypeDefaultsListResponse(BaseResponse):
    """Response schema for list of sensor type defaults."""

    items: List[SensorTypeDefaultsResponse] = Field(
        default_factory=list,
        description="List of sensor type defaults",
    )
    total: int = Field(..., description="Total count")


class EffectiveConfigResponse(BaseModel):
    """Response schema for effective sensor configuration."""

    sensor_type: str = Field(..., description="Sensor type")
    operating_mode: str = Field(..., description="Effective operating mode")
    measurement_interval_seconds: int = Field(..., description="Effective interval")
    timeout_seconds: int = Field(..., description="Effective timeout")
    timeout_warning_enabled: bool = Field(..., description="Effective warning setting")
    supports_on_demand: bool = Field(..., description="Supports on-demand")
    measurement_freshness_hours: Optional[int] = Field(
        None, description="Effective freshness limit"
    )
    calibration_interval_days: Optional[int] = Field(
        None, description="Effective calibration interval"
    )
    source: str = Field(
        ...,
        description="Configuration source: 'instance', 'type_default', or 'system_default'",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sensor_type": "ph",
                "operating_mode": "on_demand",
                "measurement_interval_seconds": 0,
                "timeout_seconds": 0,
                "timeout_warning_enabled": False,
                "supports_on_demand": True,
                "measurement_freshness_hours": 24,
                "calibration_interval_days": 30,
                "source": "type_default",
            }
        }
    )
