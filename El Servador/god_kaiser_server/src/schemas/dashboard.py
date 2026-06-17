"""
Dashboard Pydantic Schemas

Request/response models for dashboard CRUD operations.
"""

import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import BaseResponse, PaginationMeta

# =============================================================================
# Widget Schema (embedded in Dashboard)
# =============================================================================


class DashboardWidgetConfig(BaseModel):
    """Widget-specific configuration."""

    sensor_id: Optional[str] = Field(None, alias="sensorId")
    actuator_id: Optional[str] = Field(None, alias="actuatorId")
    esp_id: Optional[str] = Field(None, alias="espId")
    gpio: Optional[int] = None
    sensor_type: Optional[str] = Field(None, alias="sensorType")
    zone_id: Optional[str] = Field(None, alias="zoneId")
    time_range: Optional[str] = Field(None, alias="timeRange")
    show_thresholds: Optional[bool] = Field(None, alias="showThresholds")
    title: Optional[str] = None
    color: Optional[str] = None
    sync_time_axis: Optional[bool] = Field(None, alias="syncTimeAxis")
    data_sources: Optional[str] = Field(None, alias="dataSources")
    y_min: Optional[float] = Field(None, alias="yMin")
    y_max: Optional[float] = Field(None, alias="yMax")
    warn_low: Optional[float] = Field(None, alias="warnLow")
    warn_high: Optional[float] = Field(None, alias="warnHigh")
    alarm_low: Optional[float] = Field(None, alias="alarmLow")
    alarm_high: Optional[float] = Field(None, alias="alarmHigh")

    model_config = ConfigDict(populate_by_name=True)


class DashboardWidget(BaseModel):
    """Single widget in a dashboard layout."""

    id: str = Field(..., description="Widget unique identifier")
    type: str = Field(..., description="Widget type (line-chart, gauge, sensor-card, etc.)")
    x: int = Field(..., description="Grid X position", ge=0)
    y: int = Field(..., description="Grid Y position", ge=0)
    w: int = Field(..., description="Grid width", ge=1)
    h: int = Field(..., description="Grid height", ge=1)
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Widget-specific configuration",
    )

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Request Schemas
# =============================================================================


class DashboardCreate(BaseModel):
    """Create a new dashboard."""

    name: str = Field(
        ...,
        description="Dashboard display name",
        min_length=1,
        max_length=200,
    )
    description: Optional[str] = Field(
        None,
        description="Optional description",
        max_length=500,
    )
    widgets: List[DashboardWidget] = Field(
        default_factory=list,
        description="Initial widget configurations",
    )
    is_shared: bool = Field(
        False,
        description="Whether dashboard is visible to all users",
    )
    scope: Optional[Literal["zone", "zone-tile", "cross-zone", "sensor-detail"]] = Field(
        None,
        description="Dashboard scope",
    )
    zone_id: Optional[str] = Field(
        None,
        description="Associated zone ID",
        max_length=100,
    )
    auto_generated: bool = Field(
        False,
        description="Whether auto-generated from zone devices",
    )
    sensor_id: Optional[str] = Field(
        None,
        description="Associated sensor ID",
        max_length=100,
    )
    target: Optional[dict[str, Any]] = Field(
        None,
        description="Display target: { view, placement, anchor?, panelPosition?, panelWidth?, order? }",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Mein Dashboard",
                "description": "Temperatur-Übersicht",
                "widgets": [
                    {
                        "id": "widget-1",
                        "type": "gauge",
                        "x": 0,
                        "y": 0,
                        "w": 3,
                        "h": 3,
                        "config": {"title": "Temperatur", "sensorType": "temperature"},
                    }
                ],
                "is_shared": False,
            }
        }
    )


class DashboardUpdate(BaseModel):
    """Update an existing dashboard."""

    name: Optional[str] = Field(
        None,
        description="Dashboard display name",
        min_length=1,
        max_length=200,
    )
    description: Optional[str] = Field(
        None,
        description="Optional description",
        max_length=500,
    )
    widgets: Optional[List[DashboardWidget]] = Field(
        None,
        description="Updated widget configurations",
    )
    is_shared: Optional[bool] = Field(
        None,
        description="Whether dashboard is visible to all users",
    )
    scope: Optional[Literal["zone", "zone-tile", "cross-zone", "sensor-detail"]] = Field(
        None,
        description="Dashboard scope",
    )
    zone_id: Optional[str] = Field(
        None,
        description="Associated zone ID",
        max_length=100,
    )
    auto_generated: Optional[bool] = Field(
        None,
        description="Whether auto-generated",
    )
    sensor_id: Optional[str] = Field(
        None,
        description="Associated sensor ID",
        max_length=100,
    )
    target: Optional[dict[str, Any]] = Field(
        None,
        description="Display target: { view, placement, anchor?, panelPosition?, panelWidth?, order? }",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class DashboardResponse(BaseModel):
    """Single dashboard in API response."""

    id: uuid.UUID = Field(..., description="Dashboard UUID")
    name: str = Field(..., description="Dashboard display name")
    description: Optional[str] = Field(None, description="Optional description")
    owner_id: int = Field(..., description="Owner user ID")
    is_shared: bool = Field(..., description="Whether shared")
    widgets: List[DashboardWidget] = Field(
        default_factory=list,
        description="Widget configurations",
    )
    scope: Optional[str] = Field(None, description="Dashboard scope")
    zone_id: Optional[str] = Field(None, description="Associated zone ID")
    auto_generated: bool = Field(False, description="Whether auto-generated")
    sensor_id: Optional[str] = Field(None, description="Associated sensor ID")
    target: Optional[dict[str, Any]] = Field(None, description="Display target config")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class DashboardListResponse(BaseResponse):
    """Response for listing dashboards."""

    data: List[DashboardResponse] = Field(
        default_factory=list,
        description="List of dashboards",
    )
    pagination: Optional[PaginationMeta] = Field(
        None,
        description="Pagination metadata",
    )


class DashboardDataResponse(BaseResponse):
    """Response for single dashboard operations."""

    data: Optional[DashboardResponse] = Field(
        None,
        description="Dashboard data",
    )
