"""
API Schemas - Pydantic Models for Request/Response Validation

Provides type-safe, validated models for:
- Sensor processing requests
- Processing responses
- Error responses
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SensorProcessRequest(BaseModel):
    """
    Request model for sensor processing endpoint.

    ESP32 sends raw sensor data for server-side processing.
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID (format: ESP_XXXXXX to ESP_XXXXXXXX or MOCK_XXX)",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        examples=["ESP_D0B19C", "ESP_12AB34CD", "MOCK_TEST01"],
    )

    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number (0-39 for ESP32)",
    )

    sensor_type: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Sensor type identifier (e.g., 'ph', 'temperature', 'ec')",
        examples=["ph", "temperature", "humidity", "ec"],
    )

    raw_value: float = Field(
        ...,
        description="Raw sensor value (ADC reading 0-4095 for ESP32)",
        ge=0,
        le=4095,
    )

    calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="Calibration data (sensor-specific format)",
    )

    params: Optional[Dict[str, Any]] = Field(
        None,
        description="Processing parameters (sensor-specific)",
    )

    timestamp: Optional[int] = Field(
        None,
        description="Unix timestamp (seconds)",
    )

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        """Validate sensor type format."""
        v = v.lower().strip()

        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Sensor type must be alphanumeric (with - or _)")

        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "raw_value": 2150,
                "calibration": {"slope": -3.5, "offset": 21.34},
                "params": {"temperature_compensation": 25.0},
                "timestamp": 1735818000,
            }
        }
    )


class SensorProcessResponse(BaseModel):
    """
    Response model for sensor processing endpoint.

    Server returns processed sensor data.
    """

    success: bool = Field(
        ...,
        description="Whether processing succeeded",
    )

    processed_value: Optional[float] = Field(
        None,
        description="Processed sensor value (e.g., 7.2 for pH)",
    )

    unit: Optional[str] = Field(
        None,
        description="Measurement unit (e.g., 'pH', '°C', 'ppm')",
    )

    quality: Optional[str] = Field(
        None,
        description="Data quality indicator (excellent, good, fair, poor, bad, error)",
    )

    processing_time_ms: Optional[float] = Field(
        None,
        description="Server processing time in milliseconds",
    )

    error: Optional[str] = Field(
        None,
        description="Error message if processing failed",
    )

    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional processing metadata",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "processed_value": 7.2,
                "unit": "pH",
                "quality": "good",
                "processing_time_ms": 15.3,
                "metadata": {"voltage": 1.75, "calibrated": True},
            }
        }
    )


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(
        ...,
        description="Error type or code",
    )

    detail: str = Field(
        ...,
        description="Human-readable error description",
    )

    timestamp: Optional[int] = Field(
        None,
        description="Error timestamp (Unix seconds)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "SENSOR_NOT_FOUND",
                "detail": "No processor found for sensor type 'invalid_sensor'",
                "timestamp": 1735818000,
            }
        }
    )


# =============================================================================
# Calibration Schemas
# =============================================================================


class CalibrationPoint(BaseModel):
    """Single calibration point: measured raw value + known reference value."""

    raw: float = Field(
        ...,
        description="Raw sensor value (ADC or processed value from sensor)",
        examples=[1500, 3000, 2048],
    )

    reference: float = Field(
        ...,
        description="Known reference value (e.g., buffer pH, EC standard)",
        examples=[7.0, 1413, 100.0],
    )


class SensorCalibrateRequest(BaseModel):
    """
    Request model for sensor calibration endpoint.

    Calibration methods by sensor type:
    - pH: 2-point linear (buffers pH 4.0 + pH 7.0)
    - EC: 2-point linear (buffers 1413 µS/cm + 12880 µS/cm)
    - Moisture: 2-point linear (dry=0%, wet=100%)
    - Temperature/Pressure/Humidity: 1-point offset
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID (format: ESP_XXXXXX to ESP_XXXXXXXX or MOCK_XXX)",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        examples=["ESP_D0B19C", "ESP_12AB34CD", "MOCK_TEST01"],
    )

    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number (0-39 for ESP32)",
    )

    sensor_type: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Sensor type (determines calibration method)",
        examples=["ph", "ec", "moisture", "temperature"],
    )

    calibration_points: list[CalibrationPoint] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Calibration points (1 for offset, 2+ for linear)",
    )

    method: Optional[str] = Field(
        None,
        description="Calibration method (auto-detected if not specified)",
        examples=["linear", "offset"],
    )

    save_to_config: bool = Field(
        True,
        description="Save calibration to sensor config in database",
    )

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        """Normalize sensor type."""
        return v.lower().strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ec",
                "calibration_points": [
                    {"raw": 1500, "reference": 1413},
                    {"raw": 3000, "reference": 12880},
                ],
                "method": "linear",
                "save_to_config": True,
            }
        }
    )


class SensorCalibrateResponse(BaseModel):
    """Response model for sensor calibration endpoint."""

    success: bool = Field(
        ...,
        description="Whether calibration succeeded",
    )

    calibration: Dict[str, Any] = Field(
        ...,
        description="Calculated calibration data (slope/offset, dry/wet, etc.)",
    )

    sensor_type: str = Field(
        ...,
        description="Sensor type that was calibrated",
    )

    method: str = Field(
        ...,
        description="Calibration method used",
    )

    saved: bool = Field(
        ...,
        description="Whether calibration was saved to database",
    )

    message: Optional[str] = Field(
        None,
        description="Additional information or warnings",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "calibration": {
                    "slope": 15210.9,
                    "offset": -4876.2,
                    "method": "linear",
                    "points": 2,
                },
                "sensor_type": "ec",
                "method": "linear",
                "saved": True,
                "message": "Calibration saved. Apply temperature compensation for best accuracy.",
            }
        }
    )
