"""
Plant Entity CRUD API Endpoints (AUT-222 — Phyta Plants Schema).

Provides:
- POST   /v1/plants                              - Create a new plant (auto QR code)
- GET    /v1/plants                              - List active plants (filter by kaiser_id, phase)
- GET    /v1/plants/{plant_id}                   - Get plant by plant_id
- PATCH  /v1/plants/{plant_id}                   - Partial update
- DELETE /v1/plants/{plant_id}                   - Soft-delete (AUT-221)
- GET    /v1/plants/{plant_id}/qr-code.png       - PNG QR-code label
- GET    /v1/plants/{plant_id}/measurements      - Recent sensor_data window (AUT-221)
- POST   /v1/plants/{plant_id}/lifecycle-event   - Append lifecycle event + WS broadcast (AUT-221)
- GET    /v1/plants/zone-summary/{zone_id}       - Plant histogram + avg phi2 per zone (AUT-221)
"""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from ...core.logging_config import get_logger
from ...db.models.audit_log import (
    AuditSeverity,
    AuditSourceType,
)
from ...db.models.plant import PlantLifecycleEvent
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.repositories.plant_repo import PlantRepository
from ...schemas.plant import (
    LifecycleEventCreate,
    LifecycleEventResponse,
    PlantCreate,
    PlantDeleteResponse,
    PlantListResponse,
    PlantMeasurementEntry,
    PlantMeasurementsResponse,
    PlantResponse,
    PlantUpdate,
    ZonePlantSummaryResponse,
)
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/plants", tags=["plants"])


# Audit event type constants — kept local to avoid bloating the global
# AuditEventType class for a single feature area.
_EVENT_PLANT_CREATED = "plant_created"
_EVENT_PLANT_UPDATED = "plant_updated"
_EVENT_PLANT_DELETED = "plant_deleted"
_EVENT_PLANT_LIFECYCLE = "plant_lifecycle_event_added"

# Sensor type used for plant photosynthetic efficiency aggregation.
_PHI2_SENSOR_TYPE = "phi2"
_PHI2_WINDOW_DAYS = 30


async def _audit_safe(
    db,
    *,
    event_type: str,
    severity: str,
    source_id: str,
    message: str,
    details: dict,
) -> None:
    """Best-effort audit logging — never blocks the request on failure."""
    try:
        audit_repo = AuditLogRepository(db)
        await audit_repo.create(
            event_type=event_type,
            severity=severity,
            source_type=AuditSourceType.API,
            source_id=source_id,
            status="success",
            message=message,
            details=details,
        )
    except Exception as exc:  # pragma: no cover - audit must never fail caller
        logger.warning("Failed to write audit log for %s: %s", event_type, exc)


@router.post(
    "",
    response_model=PlantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Plant",
    description=(
        "Create a new plant. A QR code (``PL-XXXXXXXX``) is generated server-side "
        "and ``external_plant_id`` is initialised to the same value. Both can be "
        "overridden later via PATCH."
    ),
    responses={
        201: {"description": "Plant created successfully"},
    },
)
async def create_plant(
    request: PlantCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> PlantResponse:
    plant_repo = PlantRepository(db)

    # Generate QR code once and use as default external_plant_id.
    from ...db.models.plant import _generate_qr_code  # local import to keep API surface clean

    qr_code = _generate_qr_code()

    plant = await plant_repo.create(
        genotype_label=request.genotype_label,
        planting_date=request.planting_date,
        phase=request.phase,
        kaiser_id=request.kaiser_id,
        cultivar_or_variety=request.cultivar_or_variety,
        batch_label=request.batch_label,
        subzone_id=request.subzone_id,
        notes=request.notes,
        qr_code=qr_code,
        external_plant_id=qr_code,
    )
    await db.commit()
    await db.refresh(plant)

    await _audit_safe(
        db,
        event_type=_EVENT_PLANT_CREATED,
        severity=AuditSeverity.INFO,
        source_id=str(current_user.id),
        message=f"Plant created by {current_user.username}",
        details={
            "plant_id": str(plant.plant_id),
            "qr_code": plant.qr_code,
            "kaiser_id": plant.kaiser_id,
            "phase": plant.phase,
            "genotype_label": plant.genotype_label,
        },
    )
    await db.commit()

    logger.info(
        "Plant created by %s: plant_id=%s, qr_code=%s",
        current_user.username,
        plant.plant_id,
        plant.qr_code,
    )

    return PlantResponse.model_validate(plant)


@router.get(
    "",
    response_model=PlantListResponse,
    summary="List Plants",
    description="List active (non-soft-deleted) plants. Supports filtering by kaiser_id and phase.",
)
async def list_plants(
    db: DBSession,
    _user: ActiveUser,
    kaiser_id: Optional[str] = Query(
        None, description="Filter by tenant (kaiser_id)"
    ),
    phase: Optional[str] = Query(
        None, description="Filter by lifecycle phase"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of rows"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
) -> PlantListResponse:
    plant_repo = PlantRepository(db)
    plants = await plant_repo.get_active(
        kaiser_id=kaiser_id,
        phase=phase,
        skip=skip,
        limit=limit,
    )

    return PlantListResponse(
        plants=[PlantResponse.model_validate(p) for p in plants],
        total=len(plants),
    )


@router.get(
    "/{plant_id}",
    response_model=PlantResponse,
    summary="Get Plant",
    responses={
        200: {"description": "Plant found"},
        404: {"description": "Plant not found"},
    },
)
async def get_plant(
    plant_id: uuid.UUID,
    db: DBSession,
    _user: ActiveUser,
) -> PlantResponse:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id)

    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    return PlantResponse.model_validate(plant)


@router.patch(
    "/{plant_id}",
    response_model=PlantResponse,
    summary="Partial Update Plant",
    description="Partially update a plant. Only provided fields are changed.",
    responses={
        200: {"description": "Plant updated"},
        400: {"description": "No fields to update"},
        404: {"description": "Plant not found"},
    },
)
async def patch_plant(
    plant_id: uuid.UUID,
    request: PlantUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> PlantResponse:
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    # Note: BaseRepository.update keys on ``id`` but Plant's PK is ``plant_id``.
    # We update fields directly on the instance for clarity and correctness.
    for key, value in update_data.items():
        setattr(plant, key, value)

    await db.flush()
    await db.commit()
    await db.refresh(plant)

    await _audit_safe(
        db,
        event_type=_EVENT_PLANT_UPDATED,
        severity=AuditSeverity.INFO,
        source_id=str(current_user.id),
        message=f"Plant patched by {current_user.username}",
        details={
            "plant_id": str(plant.plant_id),
            "fields": sorted(update_data.keys()),
        },
    )
    await db.commit()

    logger.info(
        "Plant patched by %s: plant_id=%s, fields=%s",
        current_user.username,
        plant.plant_id,
        sorted(update_data.keys()),
    )
    return PlantResponse.model_validate(plant)


@router.get(
    "/{plant_id}/qr-code.png",
    summary="Plant QR-Code PNG",
    description=(
        "Render the plant QR code as a PNG label. The encoded payload is the "
        "plant's ``qr_code`` value (e.g. ``PL-A1B2C3D4``)."
    ),
    responses={
        200: {
            "description": "PNG image",
            "content": {"image/png": {}},
        },
        404: {"description": "Plant not found"},
        500: {"description": "QR rendering failed (qrcode library missing)"},
    },
)
async def get_plant_qr_code_png(
    plant_id: uuid.UUID,
    db: DBSession,
    _user: ActiveUser,
) -> Response:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    try:
        import qrcode  # type: ignore
    except ImportError as exc:
        logger.error("qrcode library not available: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="QR code rendering is not available (qrcode library not installed)",
        )

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(plant.qr_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="{plant.qr_code}.png"',
        },
    )


# =============================================================================
# AUT-221 Wave 2 — DELETE, Measurements, Lifecycle-Event, Zone-Summary
# =============================================================================


@router.delete(
    "/{plant_id}",
    response_model=PlantDeleteResponse,
    summary="Soft-Delete Plant",
    description=(
        "Soft-delete a plant. Sets ``deleted_at`` and ``deleted_by``; the "
        "row remains in the database for audit / history. Returns 404 when "
        "the plant does not exist or is already deleted."
    ),
    responses={
        200: {"description": "Plant soft-deleted"},
        404: {"description": "Plant not found or already deleted"},
    },
)
async def delete_plant(
    plant_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> PlantDeleteResponse:
    plant_repo = PlantRepository(db)

    # ``soft_delete`` itself returns None when the plant is already deleted
    # (because ``get_by_plant_id(include_deleted=False)`` filters it out),
    # so a single call covers both 404 cases.
    deleted = await plant_repo.soft_delete(plant_id, deleted_by=current_user.id)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found or already deleted",
        )

    await db.commit()

    await _audit_safe(
        db,
        event_type=_EVENT_PLANT_DELETED,
        severity=AuditSeverity.INFO,
        source_id=str(current_user.id),
        message=f"Plant soft-deleted by {current_user.username}",
        details={
            "plant_id": str(deleted.plant_id),
            "qr_code": deleted.qr_code,
            "kaiser_id": deleted.kaiser_id,
        },
    )
    await db.commit()

    logger.info(
        "Plant soft-deleted by %s: plant_id=%s, qr_code=%s",
        current_user.username,
        deleted.plant_id,
        deleted.qr_code,
    )

    return PlantDeleteResponse(
        success=True,
        message="Plant soft-deleted",
        plant_id=deleted.plant_id,
    )


@router.get(
    "/{plant_id}/measurements",
    response_model=PlantMeasurementsResponse,
    summary="Plant Measurements (Time-Series)",
    description=(
        "Return ``sensor_data`` rows associated with this plant via "
        "``sensor_data.plant_id`` over the last ``days`` days, ordered by "
        "timestamp DESC. Used by the Phyta UI to render per-plant trends."
    ),
    responses={
        200: {"description": "Measurements returned (possibly empty)"},
        404: {"description": "Plant not found"},
    },
)
async def get_plant_measurements(
    plant_id: uuid.UUID,
    db: DBSession,
    _user: ActiveUser,
    days: int = Query(
        30,
        ge=1,
        le=365,
        description="Sliding window size in days (default 30, max 365)",
    ),
    limit: int = Query(
        1000,
        ge=1,
        le=10_000,
        description="Hard upper bound on returned rows",
    ),
) -> PlantMeasurementsResponse:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=True)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await plant_repo.get_sensor_data_for_plant(
        plant_id=plant_id,
        cutoff=cutoff,
        limit=limit,
    )

    measurements = [
        PlantMeasurementEntry(
            sensor_type=row.sensor_type,
            processed_value=row.processed_value,
            raw_value=row.raw_value,
            unit=row.unit,
            timestamp=row.timestamp,
            gpio=row.gpio,
        )
        for row in rows
    ]

    return PlantMeasurementsResponse(
        plant_id=plant_id,
        days=days,
        total=len(measurements),
        measurements=measurements,
    )


@router.post(
    "/{plant_id}/lifecycle-event",
    response_model=LifecycleEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append Plant Lifecycle Event",
    description=(
        "Append an immutable lifecycle event to a plant. When "
        "``event_type == 'phase_changed'`` and ``new_phase`` is provided, "
        "the plant's ``phase`` is updated atomically and ``previous_phase`` "
        "is recorded on the event row. After successful insert a "
        "``plant_lifecycle_update`` WebSocket event is broadcast."
    ),
    responses={
        201: {"description": "Lifecycle event recorded"},
        400: {"description": "Invalid payload (e.g. phase_changed without new_phase)"},
        404: {"description": "Plant not found or already deleted"},
    },
)
async def add_lifecycle_event(
    plant_id: uuid.UUID,
    body: LifecycleEventCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> LifecycleEventResponse:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=False)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found or already deleted",
        )

    # Phase-Change semantics: ``new_phase`` is mandatory and must differ
    # from the current phase to avoid no-op event spam.
    previous_phase: Optional[str] = None
    new_phase: Optional[str] = None
    if body.event_type == "phase_changed":
        if body.new_phase is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="phase_changed requires 'new_phase'",
            )
        previous_phase = plant.phase
        new_phase = body.new_phase
        plant.phase = new_phase

    # Persist the optional structured ``metadata`` blob inside ``notes``
    # because the underlying model has no JSON metadata column. ``note``
    # always wins over ``metadata`` when both are present.
    notes_value: Optional[str] = body.note
    if notes_value is None and body.metadata is not None:
        notes_value = json.dumps(body.metadata, sort_keys=True, default=str)

    event_timestamp = datetime.now(timezone.utc)
    event = PlantLifecycleEvent(
        plant_id=plant.plant_id,
        kaiser_id=plant.kaiser_id,
        event_type=body.event_type,
        event_timestamp=event_timestamp,
        previous_phase=previous_phase,
        new_phase=new_phase,
        notes=notes_value,
        created_by_user=current_user.id,
        created_at=event_timestamp,
    )
    db.add(event)
    await db.flush()
    await db.commit()
    await db.refresh(event)

    await _audit_safe(
        db,
        event_type=_EVENT_PLANT_LIFECYCLE,
        severity=AuditSeverity.INFO,
        source_id=str(current_user.id),
        message=f"Plant lifecycle event '{body.event_type}' by {current_user.username}",
        details={
            "plant_id": str(plant.plant_id),
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "previous_phase": previous_phase,
            "new_phase": new_phase,
        },
    )
    await db.commit()

    # ==========================================================================
    # WS BROADCAST plant_lifecycle_update
    # Best-effort: failures must not break the request — the event row is
    # already committed and the audit log captures the change.
    # ==========================================================================
    try:
        from ...websocket.manager import WebSocketManager

        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "plant_lifecycle_update",
            {
                "plant_id": str(plant.plant_id),
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "previous_phase": previous_phase,
                "new_phase": new_phase,
                "event_timestamp": event_timestamp.isoformat(),
            },
        )
    except Exception as exc:  # pragma: no cover - WS broadcast is best-effort
        logger.warning(
            "Failed to broadcast plant_lifecycle_update for plant %s: %s",
            plant.plant_id,
            exc,
        )

    logger.info(
        "Plant lifecycle event recorded by %s: plant_id=%s, type=%s",
        current_user.username,
        plant.plant_id,
        event.event_type,
    )

    return LifecycleEventResponse.model_validate(event)


@router.get(
    "/zone-summary/{zone_id}",
    response_model=ZonePlantSummaryResponse,
    summary="Zone Plant Summary",
    description=(
        "Aggregate plant statistics for a single zone: total active plant "
        "count, phase histogram, and the average ``phi2`` measurement over "
        f"the last {_PHI2_WINDOW_DAYS} days. The endpoint resolves the "
        "zone via ``subzone_configs.parent_zone_id`` joined through "
        "``plants.subzone_id``. Returns zero counts when the zone is "
        "unknown — it does not validate against the zones table to avoid "
        "coupling the Phyta surface to zone lifecycle."
    ),
    responses={
        200: {"description": "Summary returned (possibly empty)"},
    },
)
async def get_zone_plant_summary(
    zone_id: str,
    db: DBSession,
    _user: ActiveUser,
) -> ZonePlantSummaryResponse:
    plant_repo = PlantRepository(db)

    phases = await plant_repo.get_zone_phase_histogram(zone_id)
    plant_count = sum(phases.values())

    avg_phi2: Optional[float] = None
    if plant_count > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_PHI2_WINDOW_DAYS)
        avg_phi2 = await plant_repo.get_zone_avg_phi2(
            zone_id=zone_id,
            phi2_sensor_type=_PHI2_SENSOR_TYPE,
            cutoff=cutoff,
        )

    return ZonePlantSummaryResponse(
        zone_id=zone_id,
        plant_count=plant_count,
        phases=phases,
        avg_phi2=avg_phi2,
    )
