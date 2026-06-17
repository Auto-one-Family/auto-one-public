"""
Calibration Session REST Endpoints (S-P3)

Session-based calibration lifecycle:
    POST   /v1/calibration/sessions           → Start session
    GET    /v1/calibration/sessions/{id}       → Get session
    POST   /v1/calibration/sessions/{id}/points → Add calibration point
    POST   /v1/calibration/sessions/{id}/finalize → Compute result
    POST   /v1/calibration/sessions/{id}/apply    → Apply to sensor config
    POST   /v1/calibration/sessions/{id}/reject   → Reject/abort session
    GET    /v1/calibration/sessions/sensor/{esp_id}/{gpio} → History
"""

import uuid
from math import isfinite
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.logging_config import get_logger
from ...services.calibration_service import CalibrationError, CalibrationService
from ..deps import DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v1/calibration/sessions",
    tags=["Calibration Sessions"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────


class StartSessionRequest(BaseModel):
    esp_id: str = Field(..., min_length=1, max_length=24)
    gpio: int = Field(..., ge=0, le=48)
    sensor_type: str = Field(..., min_length=1, max_length=50)
    method: str = Field(default="linear_2point", max_length=30)
    expected_points: int = Field(default=2, ge=1, le=10)
    correlation_id: Optional[str] = Field(default=None, max_length=64)
    # AUT-299: Solution temperature at calibration time for temperature-compensated
    # coefficient calculation.  Default 25.0°C = NIST reference temperature.
    calibration_temperature: Optional[float] = Field(
        None,
        ge=-10.0,
        le=50.0,
        description="Solution temperature at calibration time (°C). If omitted, server tries linked DS18B20/temperature sensor and falls back to 25.0°C.",
    )
    calibration_temperature_source: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional provenance marker for temperature value (e.g. manual, config:<uuid>).",
    )


class AddPointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: float = Field(..., description="Raw ADC/sensor value")
    reference_value: float = Field(..., description="Known reference value")
    point_role: str = Field(
        ...,
        description=(
            "Calibration point role: "
            "dry|wet|buffer_high|buffer_low|reference|air|reference_low|reference_high"
        ),
    )
    overwrite: bool = Field(default=False, description="Overwrite point with same role if true")
    quality: str = Field(default="good", max_length=20)
    intent_id: Optional[str] = Field(default=None, max_length=64)
    measured_at: Optional[str] = Field(default=None, max_length=64)
    correlation_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("raw_value", "reference_value")
    @classmethod
    def _validate_finite_number(cls, value: float) -> float:
        if not isfinite(float(value)):
            raise ValueError("must be a finite number")
        return float(value)

    @field_validator("point_role")
    @classmethod
    def _validate_point_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {
            "dry",
            "wet",
            "buffer_high",
            "buffer_low",
            "reference",
            "air",
            "reference_low",
            "reference_high",
        }:
            raise ValueError(
                "must be one of: dry, wet, buffer_high, buffer_low, "
                "reference, air, reference_low, reference_high"
            )
        return normalized


class UpdatePointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: float = Field(..., description="Raw ADC/sensor value")
    reference_value: float = Field(..., description="Known reference value")
    point_role: str = Field(
        ...,
        description=(
            "Calibration point role: "
            "dry|wet|buffer_high|buffer_low|reference|air|reference_low|reference_high"
        ),
    )
    quality: str = Field(default="good", max_length=20)
    intent_id: Optional[str] = Field(default=None, max_length=64)
    measured_at: Optional[str] = Field(default=None, max_length=64)
    correlation_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("raw_value", "reference_value")
    @classmethod
    def _validate_finite_number(cls, value: float) -> float:
        if not isfinite(float(value)):
            raise ValueError("must be a finite number")
        return float(value)

    @field_validator("point_role")
    @classmethod
    def _validate_point_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {
            "dry",
            "wet",
            "buffer_high",
            "buffer_low",
            "reference",
            "air",
            "reference_low",
            "reference_high",
        }:
            raise ValueError(
                "must be one of: dry, wet, buffer_high, buffer_low, "
                "reference, air, reference_low, reference_high"
            )
        return normalized


class RejectRequest(BaseModel):
    reason: str = Field(default="User rejected", max_length=500)


class CalibrationPointOut(BaseModel):
    raw: float
    reference: float
    quality: str = "good"
    timestamp: Optional[str] = None
    intent_id: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    esp_id: str
    gpio: int
    sensor_type: str
    status: str
    method: str
    expected_points: int
    points_collected: int
    calibration_points: Optional[dict] = None
    calibration_result: Optional[dict] = None
    correlation_id: Optional[str] = None
    initiated_by: Optional[str] = None
    completed_at: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: str
    updated_at: str


def _session_to_response(session) -> SessionResponse:  # type: ignore[no-untyped-def]
    """Map CalibrationSession model to response schema."""
    return SessionResponse(
        id=str(session.id),
        esp_id=session.esp_id,
        gpio=session.gpio,
        sensor_type=session.sensor_type,
        status=session.status.value if hasattr(session.status, "value") else str(session.status),
        method=session.method,
        expected_points=session.expected_points,
        points_collected=session.points_collected,
        calibration_points=session.calibration_points,
        calibration_result=session.calibration_result,
        correlation_id=session.correlation_id,
        initiated_by=session.initiated_by,
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        failure_reason=session.failure_reason,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new calibration session",
)
async def start_session(
    request: StartSessionRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """
    Start a new calibration session for a sensor.

    Existing active sessions for the same sensor are automatically expired.
    """
    service = CalibrationService(db)
    try:
        # AUT-299: Session metadata is resolved by CalibrationService:
        # explicit frontend value > linked temp sensor > 25.0°C fallback.
        session_metadata: dict[str, object] = {}
        if request.calibration_temperature is not None:
            session_metadata["calibration_temperature"] = request.calibration_temperature
        if request.calibration_temperature_source:
            session_metadata["calibration_temperature_source"] = request.calibration_temperature_source
        session = await service.start_session(
            esp_id=request.esp_id,
            gpio=request.gpio,
            sensor_type=request.sensor_type,
            method=request.method,
            expected_points=request.expected_points,
            initiated_by=current_user.username if current_user else None,
            correlation_id=request.correlation_id,
            session_metadata=session_metadata,
        )
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get calibration session details",
)
async def get_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """Get current state of a calibration session."""
    service = CalibrationService(db)
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calibration session {session_id} not found",
        )
    return _session_to_response(session)


@router.post(
    "/{session_id}/points",
    response_model=SessionResponse,
    summary="Add a calibration point",
)
async def add_point(
    session_id: uuid.UUID,
    request: AddPointRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """
    Add a measurement point to the calibration session.

    Point includes raw sensor value and known reference value.
    """
    service = CalibrationService(db)
    try:
        session = await service.add_point(
            session_id=session_id,
            raw=request.raw_value,
            reference=request.reference_value,
            point_role=request.point_role,
            overwrite=request.overwrite,
            quality=request.quality,
            intent_id=request.intent_id,
            measured_at=request.measured_at,
            correlation_id=request.correlation_id,
        )
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.put(
    "/{session_id}/points/{point_id}",
    response_model=SessionResponse,
    summary="Update a calibration point",
)
async def update_point(
    session_id: uuid.UUID,
    point_id: str,
    request: UpdatePointRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """Update a point by point ID inside a mutable session."""
    service = CalibrationService(db)
    try:
        session = await service.update_point(
            session_id=session_id,
            point_id=point_id,
            raw=request.raw_value,
            reference=request.reference_value,
            point_role=request.point_role,
            quality=request.quality,
            intent_id=request.intent_id,
            measured_at=request.measured_at,
            correlation_id=request.correlation_id,
        )
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.delete(
    "/{session_id}/points/{point_id}",
    response_model=SessionResponse,
    summary="Delete a calibration point",
)
async def delete_point(
    session_id: uuid.UUID,
    point_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """Delete a point by point ID inside a mutable session."""
    service = CalibrationService(db)
    try:
        session = await service.delete_point(session_id=session_id, point_id=point_id)
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.post(
    "/{session_id}/finalize",
    response_model=SessionResponse,
    summary="Compute calibration from collected points",
)
async def finalize_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """
    Finalize the calibration session.

    Computes slope/offset from the collected points.
    Session transitions to FINALIZING state.
    """
    service = CalibrationService(db)
    try:
        session = await service.finalize(session_id)
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.post(
    "/{session_id}/apply",
    response_model=SessionResponse,
    summary="Apply calibration to sensor config",
)
async def apply_calibration(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """
    Apply the computed calibration result to the sensor configuration.

    Only works when session is in FINALIZING state.
    """
    service = CalibrationService(db)
    try:
        session = await service.apply(session_id)
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        # Persist fail-closed apply transitions (e.g. APPLY_PERSISTENCE_REQUIRED)
        # before surfacing contract error to the API caller.
        if e.code == "APPLY_PERSISTENCE_REQUIRED":
            await db.commit()
        raise _calibration_http_exception(e)


@router.post(
    "/{session_id}/reject",
    response_model=SessionResponse,
    summary="Reject/abort calibration session",
)
async def reject_calibration(
    session_id: uuid.UUID,
    request: RejectRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> SessionResponse:
    """Reject a calibration session. Terminal — cannot be undone."""
    service = CalibrationService(db)
    try:
        session = await service.reject(session_id, reason=request.reason)
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.delete(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Discard calibration session",
)
async def delete_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
    reason: str = Query(default="User discarded session", max_length=500),
) -> SessionResponse:
    """Discard (reject) a mutable session via explicit delete."""
    service = CalibrationService(db)
    try:
        session = await service.delete_session(session_id=session_id, reason=reason)
        await db.commit()
        return _session_to_response(session)
    except CalibrationError as e:
        raise _calibration_http_exception(e)


@router.get(
    "/sensor/{esp_id}/{gpio}",
    response_model=list[SessionResponse],
    summary="Get calibration history for a sensor",
)
async def get_sensor_history(
    esp_id: str,
    gpio: int,
    db: DBSession,
    current_user: OperatorUser,
    sensor_type: Optional[str] = Query(default=None, description="Filter by sensor type"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SessionResponse]:
    """Get calibration session history for a specific sensor."""
    service = CalibrationService(db)
    sessions = await service.get_session_history(
        esp_id=esp_id,
        gpio=gpio,
        sensor_type=sensor_type,
        limit=limit,
    )
    return [_session_to_response(s) for s in sessions]


def _status_from_calibration_error(error_code: str) -> int:
    """Map calibration domain error codes to stable HTTP semantics."""
    if error_code in {"SESSION_NOT_FOUND", "POINT_NOT_FOUND"}:
        return status.HTTP_404_NOT_FOUND
    if error_code == "FORBIDDEN":
        return status.HTTP_403_FORBIDDEN
    if error_code in {
        "SESSION_TERMINAL",
        "INVALID_STATE",
        "STATE_ERROR",
        "INSUFFICIENT_POINTS",
        "DUPLICATE_POINT_ROLE",
        "ROLE_POINT_EXISTS",
        "POINTS_COMPLETE",
        "SESSION_EXPIRED",
        "NO_RESULT",
        "APPLY_PERSISTENCE_REQUIRED",
    }:
        return status.HTTP_409_CONFLICT
    if error_code in {
        "SET_RESULT_FAILED",
        "STATUS_UPDATE_FAILED",
        "ADD_POINT_FAILED",
        "POINT_UPDATE_FAILED",
        "POINT_DELETE_FAILED",
    }:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    if error_code in {"COMPUTE_FAILED", "VALIDATION_ERROR"}:
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return status.HTTP_400_BAD_REQUEST


def _contract_error_code(error_code: str) -> str:
    if error_code in {"DUPLICATE_POINT_ROLE", "ROLE_POINT_EXISTS"}:
        return "ROLE_POINT_EXISTS"
    return error_code


def _calibration_http_exception(error: CalibrationError) -> HTTPException:
    status_code = _status_from_calibration_error(error.code)
    return HTTPException(
        status_code=status_code,
        detail={
            "code": _contract_error_code(error.code),
            "message": error.message,
        },
    )
