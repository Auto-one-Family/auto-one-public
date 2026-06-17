"""
Error Event Pydantic Schemas

Provides schemas for:
- Error log responses (single and paginated)
- Error summary statistics
- Error code information

Pattern: Follows sensor.py schema structure
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import BaseResponse, PaginationMeta

# =============================================================================
# Error Log Response Models
# =============================================================================


class ErrorLogResponse(BaseModel):
    """
    Error log entry response.

    Maps AuditLog entries for ESP32 error events to a frontend-friendly format.
    """

    id: UUID = Field(
        ...,
        description="Unique error log identifier",
    )
    esp_id: str = Field(
        ...,
        description="ESP device ID that reported the error",
    )
    esp_name: Optional[str] = Field(
        None,
        description="Human-readable ESP device name",
    )
    error_code: int = Field(
        ...,
        description="ESP32 error code (e.g., 1023-1029 for DS18B20)",
    )
    severity: str = Field(
        ...,
        description="Error severity (info, warning, error, critical)",
    )
    category: Optional[str] = Field(
        None,
        description="Error category (HARDWARE, CONFIG, etc.)",
    )
    message: str = Field(
        ...,
        description="User-friendly error message",
    )
    troubleshooting: List[str] = Field(
        default_factory=list,
        description="List of troubleshooting steps",
    )
    docs_link: Optional[str] = Field(
        None,
        description="Link to documentation",
    )
    user_action_required: bool = Field(
        False,
        description="Whether user needs to take action",
    )
    recoverable: bool = Field(
        True,
        description="Whether the error is potentially recoverable",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (gpio, sensor_type, etc.)",
    )
    esp_raw_message: Optional[str] = Field(
        None,
        description="Original error message from ESP32",
    )
    timestamp: datetime = Field(
        ...,
        description="When the error occurred",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "esp_id": "ESP_12AB34CD",
                "esp_name": "Growroom Controller 1",
                "error_code": 1026,
                "severity": "error",
                "category": "HARDWARE",
                "message": "Hardware-Fehler: Sensor antwortet nicht am OneWire-Bus",
                "troubleshooting": [
                    "1. Physische Kabelverbindung prüfen",
                    "2. Sensor-Stromversorgung prüfen",
                    "3. Pull-up Widerstand (4.7k Ohm) am Bus prüfen",
                ],
                "docs_link": "/docs/sensors/ds18b20#troubleshooting",
                "user_action_required": True,
                "recoverable": True,
                "context": {"gpio": 4, "sensor_type": "ds18b20"},
                "esp_raw_message": "OneWire device not found on bus",
                "timestamp": "2024-01-15T14:30:00Z",
            }
        },
    )


class ErrorLogListResponse(BaseResponse):
    """
    Paginated error log list response.
    """

    errors: List[ErrorLogResponse] = Field(
        default_factory=list,
        description="List of error log entries",
    )
    total_count: int = Field(
        0,
        description="Total number of error entries",
        ge=0,
    )
    unacknowledged_count: int = Field(
        0,
        description="Number of errors requiring user action",
        ge=0,
    )
    pagination: PaginationMeta = Field(
        ...,
        description="Pagination metadata",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": None,
                "errors": [],
                "total_count": 42,
                "unacknowledged_count": 5,
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total_items": 42,
                    "total_pages": 3,
                    "has_next": True,
                    "has_prev": False,
                },
            }
        }
    )


# =============================================================================
# Error Summary Models
# =============================================================================


class ErrorCodeCount(BaseModel):
    """Count of errors by error code."""

    error_code: int = Field(
        ...,
        description="Error code",
    )
    count: int = Field(
        ...,
        description="Number of occurrences",
        ge=0,
    )
    message: str = Field(
        ...,
        description="Error message description",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": 1026,
                "count": 15,
                "message": "OneWire Device nicht am Bus gefunden",
            }
        }
    )


class ErrorSummaryResponse(BaseResponse):
    """
    Error summary statistics.

    Provides aggregated error statistics for monitoring dashboards.
    """

    period_hours: int = Field(
        24,
        description="Time period in hours for the statistics",
        ge=1,
    )
    total_errors: int = Field(
        0,
        description="Total number of errors in the period",
        ge=0,
    )
    errors_by_severity: Dict[str, int] = Field(
        default_factory=dict,
        description="Error counts grouped by severity",
    )
    errors_by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Error counts grouped by category",
    )
    errors_by_esp: Dict[str, int] = Field(
        default_factory=dict,
        description="Error counts grouped by ESP device",
    )
    top_error_codes: List[ErrorCodeCount] = Field(
        default_factory=list,
        description="Most frequent error codes",
    )
    action_required_count: int = Field(
        0,
        description="Errors requiring user action",
        ge=0,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": None,
                "period_hours": 24,
                "total_errors": 42,
                "errors_by_severity": {"error": 25, "warning": 15, "critical": 2},
                "errors_by_category": {"HARDWARE": 30, "CONFIG": 12},
                "errors_by_esp": {"ESP_12AB34CD": 20, "ESP_56EF78GH": 22},
                "top_error_codes": [
                    {
                        "error_code": 1026,
                        "count": 15,
                        "message": "OneWire Device nicht am Bus gefunden",
                    },
                    {"error_code": 1028, "count": 10, "message": "DS18B20 Lese-Timeout"},
                ],
                "action_required_count": 30,
            }
        }
    )


# =============================================================================
# Error Code Information Models
# =============================================================================


class ErrorCodeInfoResponse(BaseModel):
    """
    Information about a specific error code.

    Used for error code lookup/reference endpoints.
    """

    error_code: int = Field(
        ...,
        description="Error code",
    )
    title: Optional[str] = Field(
        None,
        description="Short German error title (e.g. 'MQTT-Publish fehlgeschlagen')",
    )
    category: str = Field(
        ...,
        description="Error category",
    )
    severity: str = Field(
        ...,
        description="Default severity level",
    )
    message: str = Field(
        ...,
        description="User-friendly error description (detailed)",
    )
    troubleshooting: List[str] = Field(
        default_factory=list,
        description="Troubleshooting steps",
    )
    docs_link: Optional[str] = Field(
        None,
        description="Documentation link",
    )
    recoverable: bool = Field(
        True,
        description="Whether error is recoverable",
    )
    user_action_required: bool = Field(
        False,
        description="Whether user action is required",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": 1026,
                "category": "HARDWARE",
                "severity": "ERROR",
                "message": "Hardware-Fehler: Sensor antwortet nicht am OneWire-Bus",
                "troubleshooting": [
                    "1. Physische Kabelverbindung prüfen",
                    "2. Sensor-Stromversorgung prüfen",
                ],
                "docs_link": "/docs/sensors/ds18b20#troubleshooting",
                "recoverable": True,
                "user_action_required": True,
            }
        }
    )


class ErrorCodeListResponse(BaseResponse):
    """
    List of all known error codes.
    """

    error_codes: List[ErrorCodeInfoResponse] = Field(
        default_factory=list,
        description="List of error code information",
    )
    total_count: int = Field(
        0,
        description="Total number of error codes",
        ge=0,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"success": True, "message": None, "error_codes": [], "total_count": 7}
        }
    )
