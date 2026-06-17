"""
Monitor L2 — Zone Monitor Data Schemas

Phase: Monitor L2 Optimized Design
Status: IMPLEMENTED

Provides Pydantic schemas for GET /zone/{zone_id}/monitor-data endpoint.
Used by MonitorView L2 to display sensors/actuators grouped by subzone (GPIO-based).
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SubzoneSensorEntry(BaseModel):
    """Sensor entry for monitor display (from sensor_configs + sensor_data)."""

    model_config = ConfigDict(from_attributes=True)

    esp_id: str
    gpio: int
    sensor_type: str
    name: Optional[str] = None
    raw_value: Optional[float] = None
    unit: str = ""
    quality: str = "unknown"
    last_read: Optional[str] = None
    operating_mode: Optional[str] = None


class SubzoneActuatorEntry(BaseModel):
    """Actuator entry for monitor display (from actuator_configs + actuator_state).

    pwm_value is a normalized 0.0–1.0 float. The frontend is responsible for
    converting to percentage (val * 100). Storing as raw normalized value avoids
    double-multiplication when the service layer passes current_value directly.
    """

    model_config = ConfigDict(from_attributes=True)

    esp_id: str
    gpio: int
    actuator_type: str
    name: Optional[str] = None
    state: bool = False
    pwm_value: float = 0.0
    emergency_stopped: bool = False


class SubzoneGroup(BaseModel):
    """Subzone group with sensors and actuators. subzone_id=None = "Keine Subzone"."""

    model_config = ConfigDict(from_attributes=True)

    subzone_id: Optional[str] = None
    subzone_name: str
    sensors: List[SubzoneSensorEntry] = []
    actuators: List[SubzoneActuatorEntry] = []


class ZoneMonitorData(BaseModel):
    """Full zone monitor data for L2 display."""

    model_config = ConfigDict(from_attributes=True)

    zone_id: str
    zone_name: str
    subzones: List[SubzoneGroup] = []
    sensor_count: int = 0
    actuator_count: int = 0
    alarm_count: int = 0
