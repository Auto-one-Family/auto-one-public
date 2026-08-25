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
- GET    /v1/plants/{plant_id}/phase-sections    - Explicit WHEN intervals + attached actions
- GET    /v1/plants/zone-summary/{zone_id}       - Plant histogram + avg phi2 per zone (AUT-221)
"""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from ...core.logging_config import get_logger
from ...db.models.audit_log import (
    AuditSeverity,
    AuditSourceType,
)
from ...db.models.plant import NUTRIENT_PHASES, PLANT_PHASES, Plant, PlantLifecycleEvent
from ...db.models.subzone import SubzoneConfig
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.repositories.plant_repo import PlantRepository
from ...schemas.plant import (
    LifecycleEventCreate,
    LifecycleEventListResponse,
    LifecycleEventResponse,
    LifecycleEventStatusUpdate,
    PhaseSectionActionResponse,
    PhaseSectionListResponse,
    PhaseSectionResponse,
    PlantCreate,
    PlantDeleteResponse,
    PlantListResponse,
    PlantMeasurementEntry,
    PlantMeasurementsResponse,
    PlantResponse,
    PlantUpdate,
    TankIncidentEventResponse,
    ZonePlantSummaryResponse,
)
from ...services.phase_section_service import (
    build_phase_sections,
    is_measure_event_type,
    section_covering,
    section_overlapping_window,
    validate_action_window,
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
_EVENT_PLANT_LIFECYCLE_STATUS_CHANGED = "plant_lifecycle_event_status_changed"
_EVENT_PLANT_LIFECYCLE_EVENT_CORRECTED = "plant_lifecycle_event_corrected"

# Sensor type used for plant photosynthetic efficiency aggregation.
_PHI2_SENSOR_TYPE = "phi2"
_PHI2_WINDOW_DAYS = 30

# AUT-1209: axis-correct new_phase validation needs event_type in context,
# so it lives here (not as a schema-level field validator — see
# schemas/plant.py's _ANY_PHASE_SET comment for why).
_PHASE_SET = set(PLANT_PHASES)
_NUTRIENT_PHASE_SET = set(NUTRIENT_PHASES)


def _to_plant_response(
    plant: Plant,
    zone_name_by_id: dict[str, str],
) -> PlantResponse:
    """Serialize a plant with Ortseinheit name + effective zone (AUT-1073)."""
    data = PlantResponse.model_validate(plant).model_dump()
    subzone = plant.subzone
    if subzone is not None:
        data["subzone_name"] = subzone.subzone_name
    # Display/grouping: effective zone. Edit forms: stored zone_id (from ORM).
    effective_zone_id = PlantRepository.resolve_effective_zone_id(plant)
    data["parent_zone_id"] = effective_zone_id
    if effective_zone_id is not None:
        data["zone_name"] = zone_name_by_id.get(effective_zone_id)
    return PlantResponse(**data)


async def _to_plant_responses(
    plant_repo: PlantRepository,
    plants: list[Plant],
) -> list[PlantResponse]:
    """Serialize eagerly loaded plants with one batched parent-zone lookup."""
    parent_zone_ids = {
        effective
        for plant in plants
        if (effective := PlantRepository.resolve_effective_zone_id(plant)) is not None
    }
    zone_name_by_id = await plant_repo.get_zone_names_by_id(parent_zone_ids)
    return [_to_plant_response(plant, zone_name_by_id) for plant in plants]


async def _assert_zone_subzone_consistent(
    db,
    *,
    zone_id: Optional[str],
    subzone_id: Optional[uuid.UUID],
) -> None:
    """
    Single write-path gate for create/patch (AUT-1073 + AUT-1266).

    - Unknown Ortseinheit → 422
    - Ortseinheit parent P and direct zone_id Z with P != Z → 422
    - Ortseinheit without parent may carry a direct zone_id (fallback)
    """
    if subzone_id is None:
        return

    result = await db.execute(select(SubzoneConfig).where(SubzoneConfig.id == subzone_id))
    subzone = result.scalar_one_or_none()
    if subzone is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Ortseinheit '{subzone_id}' nicht gefunden",
        )
    if zone_id is None:
        return
    if subzone.parent_zone_id is not None and subzone.parent_zone_id != zone_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"zone_id '{zone_id}' widerspricht der Elternzone "
                f"'{subzone.parent_zone_id}' der Ortseinheit. "
                "Bei einer Ortseinheit mit Elternzone darf die direkte "
                "Zone nicht abweichend gesetzt werden "
                "(Ortseinheit-Elternzone hat Vorrang; weglassen oder angleichen)."
            ),
        )


def _validate_new_phase_for_axis(event_type: str, new_phase: Optional[str]) -> None:
    """Raise 422 when new_phase does not belong to event_type's axis (AUT-1209)."""
    if new_phase is None:
        return
    if event_type == "phase_changed" and new_phase not in _PHASE_SET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid new_phase '{new_phase}' for phase_changed (light/growth axis). "
            f"Must be one of: {sorted(_PHASE_SET)}",
        )
    if event_type == "nutrient_phase_changed" and new_phase not in _NUTRIENT_PHASE_SET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid new_phase '{new_phase}' for nutrient_phase_changed "
            f"(nutrient/fertilizer axis). Must be one of: {sorted(_NUTRIENT_PHASE_SET)}",
        )


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

    await _assert_zone_subzone_consistent(
        db, zone_id=request.zone_id, subzone_id=request.subzone_id
    )

    # Generate QR code once and use as default external_plant_id.
    from ...db.models.plant import _generate_qr_code  # local import to keep API surface clean

    qr_code = _generate_qr_code()

    create_kwargs: dict = {
        "genotype_label": request.genotype_label,
        "planting_date": request.planting_date,
        # AUT-1183: optional nutrient/fertilizer phase axis.
        "nutrient_phase": request.nutrient_phase,
        "kaiser_id": request.kaiser_id,
        "cultivar_or_variety": request.cultivar_or_variety,
        "batch_label": request.batch_label,
        "zone_id": request.zone_id,
        "subzone_id": request.subzone_id,
        "notes": request.notes,
        "qr_code": qr_code,
        "external_plant_id": qr_code,
    }
    # Omit phase when unset so ORM/DB server_default ('clone') applies (AUT-1073).
    if request.phase is not None:
        create_kwargs["phase"] = request.phase

    plant = await plant_repo.create(**create_kwargs)
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

    refreshed_plant = await plant_repo.get_by_plant_id(plant.plant_id)
    if refreshed_plant is None:  # pragma: no cover - created above in this transaction
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Created plant could not be reloaded",
        )
    return (await _to_plant_responses(plant_repo, [refreshed_plant]))[0]


@router.get(
    "",
    response_model=PlantListResponse,
    summary="List Plants",
    description=(
        "List active (non-soft-deleted) plants. Supports filtering by "
        "kaiser_id, phase, nutrient_phase, and effective zone_id (AUT-1073)."
    ),
)
async def list_plants(
    db: DBSession,
    _user: ActiveUser,
    kaiser_id: Optional[str] = Query(None, description="Filter by tenant (kaiser_id)"),
    phase: Optional[str] = Query(None, description="Filter by light/growth lifecycle phase"),
    # AUT-1183: filter by nutrient/fertilizer phase axis.
    nutrient_phase: Optional[str] = Query(
        None, description="Filter by nutrient/fertilizer phase (AUT-1183)"
    ),
    zone_id: Optional[str] = Query(
        None,
        description=(
            "Filter by effective zone (AUT-1073): "
            "COALESCE(Ortseinheit.parent_zone_id, plants.zone_id)"
        ),
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of rows"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
) -> PlantListResponse:
    plant_repo = PlantRepository(db)
    plants = await plant_repo.get_active(
        kaiser_id=kaiser_id,
        phase=phase,
        nutrient_phase=nutrient_phase,
        zone_id=zone_id,
        skip=skip,
        limit=limit,
    )

    return PlantListResponse(
        plants=await _to_plant_responses(plant_repo, plants),
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

    return (await _to_plant_responses(plant_repo, [plant]))[0]


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

    # Conflict / existence check against the post-update state (AUT-1073).
    final_zone_id = update_data.get("zone_id", plant.zone_id)
    final_subzone_id = update_data.get("subzone_id", plant.subzone_id)
    await _assert_zone_subzone_consistent(db, zone_id=final_zone_id, subzone_id=final_subzone_id)

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
    refreshed_plant = await plant_repo.get_by_plant_id(plant.plant_id)
    if refreshed_plant is None:  # pragma: no cover - checked before mutation
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Updated plant could not be reloaded",
        )
    return (await _to_plant_responses(plant_repo, [refreshed_plant]))[0]


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


@router.get(
    "/{plant_id}/lifecycle-events",
    response_model=LifecycleEventListResponse,
    summary="List Plant Lifecycle Events",
    description=(
        "Return all lifecycle events for a plant ordered chronologically "
        "(oldest first). The audit trail is accessible even for soft-deleted "
        "plants. Supports pagination via ``skip`` / ``limit``."
    ),
    responses={
        200: {"description": "Events returned (possibly empty)"},
        404: {"description": "Plant not found"},
    },
)
async def list_lifecycle_events(
    plant_id: uuid.UUID,
    db: DBSession,
    _user: ActiveUser,
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of rows"),
) -> LifecycleEventListResponse:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=True)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    events = await plant_repo.get_lifecycle_events(plant_id, skip=skip, limit=limit)
    tank_incidents = await plant_repo.get_tank_incident_events_for_plant(plant)

    return LifecycleEventListResponse(
        plant_id=plant_id,
        total=len(events),
        events=[LifecycleEventResponse.model_validate(e) for e in events],
        tank_incidents=[TankIncidentEventResponse.model_validate(i) for i in tank_incidents],
    )


@router.get(
    "/{plant_id}/phase-sections",
    response_model=PhaseSectionListResponse,
    summary="List Plant Phase Sections",
    description=(
        "Explicit WHEN intervals for a plant, derived from occurred "
        "phase_changed events (or the current plants.phase when no "
        "transition exists yet). Actions that overlap a section are "
        "attached. Space (zone/subzone) is the plant's current assignment."
    ),
    responses={
        200: {"description": "Phase sections returned"},
        404: {"description": "Plant not found"},
    },
)
async def list_phase_sections(
    plant_id: uuid.UUID,
    db: DBSession,
    _user: ActiveUser,
    axis: str = Query("light", description="Phase axis: light or nutrient"),
) -> PhaseSectionListResponse:
    if axis not in ("light", "nutrient"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="axis must be 'light' or 'nutrient'",
        )
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=False)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found or already deleted",
        )
    events = await plant_repo.get_lifecycle_events(plant_id, limit=1000)
    sections = build_phase_sections(plant, events, axis=axis)
    actions = [
        ev
        for ev in events
        if is_measure_event_type(ev.event_type) and ev.event_status != "test_data"
    ]
    payload: list[PhaseSectionResponse] = []
    for section in sections:
        belonging: list[PhaseSectionActionResponse] = []
        for ev in actions:
            if ev.linked_sensor_window_start and ev.linked_sensor_window_end:
                if section.overlaps(ev.linked_sensor_window_start, ev.linked_sensor_window_end):
                    belonging.append(PhaseSectionActionResponse.model_validate(ev))
            elif section.covers(ev.event_timestamp):
                belonging.append(PhaseSectionActionResponse.model_validate(ev))
        payload.append(
            PhaseSectionResponse(
                plant_id=section.plant_id,
                phase=section.phase,
                axis=section.axis,
                start=section.start,
                end=section.end,
                source_event_id=section.source_event_id,
                zone_id=section.zone_id,
                subzone_id=section.subzone_id,
                actions=belonging,
            )
        )
    current = plant.phase if axis == "light" else plant.nutrient_phase
    return PhaseSectionListResponse(
        plant_id=plant.plant_id,
        zone_id=PlantRepository.resolve_effective_zone_id(plant),
        subzone_id=plant.subzone_id,
        current_phase=current,
        axis=axis,
        sections=payload,
    )


@router.post(
    "/{plant_id}/lifecycle-event",
    response_model=LifecycleEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append Plant Lifecycle Event",
    description=(
        "Append an immutable lifecycle event to a plant. "
        "When ``event_type == 'phase_changed'`` and ``new_phase`` is provided, "
        "the plant's light/growth ``phase`` is updated atomically. "
        "When ``event_type == 'nutrient_phase_changed'`` (AUT-1183) and "
        "``new_phase`` is provided, the plant's ``nutrient_phase`` "
        "(nutrient/fertilizer axis) is updated atomically instead. "
        "Both event types record ``previous_phase`` on the event row. "
        "After successful insert a ``plant_lifecycle_update`` WebSocket event "
        "is broadcast."
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
    current_user: ActiveUser,
) -> LifecycleEventResponse:
    # Viewers (non-operator, non-admin) may only submit 'note_added' events.
    # All other event types (phase transitions, structural changes) require
    # operator or admin role — consistent with require_operator() in deps.py.
    if current_user.role not in ("admin", "operator") and body.event_type != "note_added":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"event_type '{body.event_type}' requires operator or admin role. "
                "Active users may only submit 'note_added' events."
            ),
        )

    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=False)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found or already deleted",
        )

    # Phase-Change semantics: ``new_phase`` is mandatory for both
    # ``phase_changed`` (light/growth axis) and ``nutrient_phase_changed``
    # (nutrient/fertilizer axis, AUT-1183).  The ``event_type`` value
    # distinguishes which column is updated; two events on the same day —
    # one per axis — land in their respective column independently.
    # AUT-1205: previous_phase/new_phase below are event metadata only (what
    # THIS event asserts) — they no longer write plant.phase/nutrient_phase
    # directly. The plant's current state is set further down, after the
    # event is flushed, by re-deriving it chronologically (see there).
    previous_phase: Optional[str] = None
    new_phase: Optional[str] = None
    if body.event_type == "phase_changed":
        if body.new_phase is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="phase_changed requires 'new_phase'",
            )
        _validate_new_phase_for_axis(body.event_type, body.new_phase)  # AUT-1209
        previous_phase = plant.phase
        new_phase = body.new_phase
    elif body.event_type == "nutrient_phase_changed":
        # AUT-1183: second independent phase axis — updates plants.nutrient_phase.
        if body.new_phase is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="nutrient_phase_changed requires 'new_phase'",
            )
        _validate_new_phase_for_axis(body.event_type, body.new_phase)  # AUT-1209
        previous_phase = plant.nutrient_phase
        new_phase = body.new_phase

    # Persist the optional structured ``metadata`` blob inside ``notes``
    # because the underlying model has no JSON metadata column. ``note``
    # always wins over ``metadata`` when both are present.
    notes_value: Optional[str] = body.note
    if notes_value is None and body.metadata is not None:
        notes_value = json.dumps(body.metadata, sort_keys=True, default=str)

    now_utc = datetime.now(timezone.utc)
    event_timestamp = body.event_timestamp if body.event_timestamp is not None else now_utc

    window_start = None
    window_end = None
    if is_measure_event_type(body.event_type):
        try:
            window_start, window_end = validate_action_window(
                body.linked_sensor_window_start,
                body.linked_sensor_window_end,
                required=False,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        existing_events = await plant_repo.get_lifecycle_events(plant.plant_id, limit=1000)
        sections = build_phase_sections(plant, existing_events, axis="light", now=now_utc)
        covering = None
        if window_start is not None and window_end is not None:
            covering = section_overlapping_window(sections, window_start, window_end)
            if covering is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "Action window must overlap a plant-phase section " "(WHEN) for this plant."
                    ),
                )
        else:
            covering = section_covering(sections, event_timestamp)
        if covering is not None and new_phase is None:
            new_phase = covering.phase
    elif body.linked_sensor_window_start is not None or body.linked_sensor_window_end is not None:
        try:
            window_start, window_end = validate_action_window(
                body.linked_sensor_window_start,
                body.linked_sensor_window_end,
                required=False,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    event = PlantLifecycleEvent(
        plant_id=plant.plant_id,
        kaiser_id=plant.kaiser_id,
        event_type=body.event_type,
        event_timestamp=event_timestamp,
        previous_phase=previous_phase,
        new_phase=new_phase,
        notes=notes_value,
        created_by_user=current_user.id,
        created_at=now_utc,
        event_status=body.event_status,  # AUT-1207, defaults to 'occurred'
        linked_sensor_window_start=window_start,
        linked_sensor_window_end=window_end,
        zone_id=PlantRepository.resolve_effective_zone_id(plant),
        subzone_id=plant.subzone_id,
    )
    db.add(event)
    await db.flush()

    # AUT-1205: chronology-aware current-state update. A backdated event
    # must be stored in full (above) but must not silently overwrite a
    # chronologically newer transition on the same axis — re-derive the
    # current value from the complete event log (now visible within this
    # transaction after the flush above) instead of unconditionally
    # applying this event. Reuses the existing AUT-981 late-binding
    # helpers, previously unused by any caller.
    if body.event_type == "phase_changed":
        derived_phase = await plant_repo.get_plant_phase_at(plant.plant_id, now_utc)
        if derived_phase is not None:
            if derived_phase != new_phase:
                # AUT-1205: warning (not info) — this deployment runs with
                # LOG_LEVEL=WARNING (production), so info-level
                # would be silently dropped and defeat the point of this
                # hint (matches existing WARNING-level telemetry convention
                # elsewhere in this module, e.g. latency_stage logs).
                logger.warning(
                    "Backdated phase_changed event %s for plant %s did not move current "
                    "phase (event sets %r, chronologically current remains %r)",
                    event.event_id,
                    plant.plant_id,
                    new_phase,
                    derived_phase,
                )
            plant.phase = derived_phase
    elif body.event_type == "nutrient_phase_changed":
        derived_nutrient_phase = await plant_repo.get_plant_nutrient_phase_at(
            plant.plant_id, now_utc
        )
        if derived_nutrient_phase is not None:
            if derived_nutrient_phase != new_phase:
                logger.warning(
                    "Backdated nutrient_phase_changed event %s for plant %s did not move "
                    "current nutrient phase (event sets %r, chronologically current "
                    "remains %r)",
                    event.event_id,
                    plant.plant_id,
                    new_phase,
                    derived_nutrient_phase,
                )
            plant.nutrient_phase = derived_nutrient_phase

    if body.event_type == "phase_changed":
        zone_id = PlantRepository.resolve_effective_zone_id(plant)
        if zone_id:
            from ...services.zone_context_service import ZoneContextService

            await ZoneContextService(db).sync_growth_phase_from_plants(zone_id)

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


@router.patch(
    "/{plant_id}/lifecycle-event/{event_id}/status",
    response_model=LifecycleEventResponse,
    summary="Update Lifecycle Event Truth Status / Correct Event Fields",
    description=(
        "Change the truth status of an existing lifecycle event (AUT-1207): "
        "'occurred', 'planned', 'reverted', or 'test_data' — 'reverted' "
        "requires a non-empty 'reason'. Also accepts field-level corrections "
        "(AUT-1208): event_timestamp, notes, event_type, new_phase — each "
        "requires a non-empty 'reason' and is recorded in the audit log with "
        "old/new values. A content correction is rejected (400) once the "
        "event is 'reverted' — a settled event is not corrected further, "
        "only its status can still change. Correcting event_type (e.g. "
        "fixing an event recorded on the wrong axis) re-derives both the old "
        "and new axis's current plant state; other corrections re-derive "
        "only the event's own axis, matching AUT-1205. A reverted/planned/"
        "test_data event is kept in the log and remains visible in the "
        "timeline, but never sets the plant's current phase/nutrient_phase "
        "state."
    ),
    responses={
        200: {"description": "Status and/or fields updated"},
        400: {"description": "Content correction attempted on an already-reverted event"},
        404: {"description": "Plant or event not found"},
        422: {
            "description": (
                "Request body failed validation: missing reason for 'reverted' "
                "or for a correction, no field supplied at all, or an invalid "
                "enum value — raised by the Pydantic schema, not this handler"
            )
        },
    },
)
async def update_lifecycle_event_status(
    plant_id: uuid.UUID,
    event_id: uuid.UUID,
    body: LifecycleEventStatusUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> LifecycleEventResponse:
    plant_repo = PlantRepository(db)
    plant = await plant_repo.get_by_plant_id(plant_id, include_deleted=True)
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plant '{plant_id}' not found",
        )

    event = await plant_repo.get_lifecycle_event_by_id(plant_id, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lifecycle event '{event_id}' not found on plant '{plant_id}'",
        )

    has_correction = any(
        f is not None for f in (body.event_timestamp, body.notes, body.event_type, body.new_phase)
    )
    # AUT-1208: a settled (reverted) event is not corrected further — only
    # its status may still change (e.g. un-reverting it back to 'occurred').
    if event.event_status == "reverted" and has_correction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot correct a reverted event's content — it is settled",
        )

    old_status = event.event_status
    old_event_type = event.event_type
    now_utc = datetime.now(timezone.utc)

    # AUT-1209: validate new_phase against the EFFECTIVE axis (the corrected
    # event_type if one is supplied in this same request, otherwise the
    # event's current type) before any mutation — a correction touching only
    # new_phase must still land on the right axis's value list.
    if body.new_phase is not None:
        effective_event_type = body.event_type if body.event_type is not None else old_event_type
        _validate_new_phase_for_axis(effective_event_type, body.new_phase)

    # AUT-1208: collect the field-level change trail before mutating, so
    # "old" always reflects the pre-correction row (see Hypothesis 3 —
    # AuditLog.details is the existing feature-level fine-grained pattern,
    # not a dedicated old/new column pair).
    corrections: list[dict] = []
    if body.event_timestamp is not None and body.event_timestamp != event.event_timestamp:
        corrections.append(
            {
                "field": "event_timestamp",
                "old": event.event_timestamp.isoformat(),
                "new": body.event_timestamp.isoformat(),
            }
        )
        event.event_timestamp = body.event_timestamp
    if body.notes is not None and body.notes != event.notes:
        corrections.append({"field": "notes", "old": event.notes, "new": body.notes})
        event.notes = body.notes
    if body.event_type is not None and body.event_type != event.event_type:
        corrections.append({"field": "event_type", "old": event.event_type, "new": body.event_type})
        event.event_type = body.event_type
    if body.new_phase is not None and body.new_phase != event.new_phase:
        corrections.append({"field": "new_phase", "old": event.new_phase, "new": body.new_phase})
        event.new_phase = body.new_phase

    if body.event_status is not None:
        event.event_status = body.event_status
        event.status_reason = body.reason

    if corrections or body.event_status is not None:
        event.status_changed_at = now_utc

    # Session is autoflush=False (see db/session.py) — the changes above are
    # only visible to the derivation queries below after an explicit flush,
    # same reasoning as in add_lifecycle_event().
    await db.flush()

    # AUT-1207 + AUT-1205 + AUT-1208: any change that can move an event in or
    # out of consideration for the derived current state — a status change,
    # or a correction of event_timestamp/event_type — must re-derive every
    # axis the event touched, before AND after the correction (an axis
    # change moves the event OUT of its old axis and INTO its new one; both
    # must be re-derived, not just the current one).
    axes_to_rederive: set[str] = set()
    for event_type_value in (old_event_type, event.event_type):
        if event_type_value == "phase_changed":
            axes_to_rederive.add("phase")
        elif event_type_value == "nutrient_phase_changed":
            axes_to_rederive.add("nutrient_phase")

    if "phase" in axes_to_rederive:
        derived_phase = await plant_repo.get_plant_phase_at(plant.plant_id, now_utc)
        if derived_phase is not None:
            plant.phase = derived_phase
    if "nutrient_phase" in axes_to_rederive:
        derived_nutrient_phase = await plant_repo.get_plant_nutrient_phase_at(
            plant.plant_id, now_utc
        )
        if derived_nutrient_phase is not None:
            plant.nutrient_phase = derived_nutrient_phase

    await db.commit()
    await db.refresh(event)

    if corrections:
        await _audit_safe(
            db,
            event_type=_EVENT_PLANT_LIFECYCLE_EVENT_CORRECTED,
            severity=AuditSeverity.INFO,
            source_id=str(current_user.id),
            message=f"Lifecycle event corrected by {current_user.username}",
            details={
                "plant_id": str(plant.plant_id),
                "event_id": str(event.event_id),
                "corrections": corrections,
                "reason": body.reason,
            },
        )
    if body.event_status is not None:
        await _audit_safe(
            db,
            event_type=_EVENT_PLANT_LIFECYCLE_STATUS_CHANGED,
            severity=AuditSeverity.INFO,
            source_id=str(current_user.id),
            message=(
                f"Lifecycle event status changed from '{old_status}' to "
                f"'{event.event_status}' by {current_user.username}"
            ),
            details={
                "plant_id": str(plant.plant_id),
                "event_id": str(event.event_id),
                "old_status": old_status,
                "new_status": event.event_status,
                "reason": event.status_reason,
            },
        )
    await db.commit()

    logger.info(
        "Lifecycle event updated by %s: event_id=%s, status %s -> %s, corrections=%s",
        current_user.username,
        event.event_id,
        old_status,
        event.event_status,
        [c["field"] for c in corrections],
    )

    return LifecycleEventResponse.model_validate(event)


@router.get(
    "/zone-summary/{zone_id}",
    response_model=ZonePlantSummaryResponse,
    summary="Zone Plant Summary",
    description=(
        "Aggregate plant statistics for a single zone: total active plant "
        "count, phase histogram, and the average ``phi2`` measurement over "
        f"the last {_PHI2_WINDOW_DAYS} days. Plants are matched via "
        "effective zone ``COALESCE(Ortseinheit.parent_zone_id, plants.zone_id)`` "
        "(AUT-1073) — direct zone plants without Ortseinheit are included. "
        "Returns zero counts when the zone is unknown — it does not validate "
        "against the zones table to avoid coupling the Phyta surface to zone "
        "lifecycle."
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

    # AUT-1194: get_zone_phase_histogram now returns ZonePhaseHistograms
    # with both axes so neither axis is silently absent from the response.
    histograms = await plant_repo.get_zone_phase_histogram(zone_id)
    # plant_count is derived from the light/growth axis (non-nullable,
    # every active plant contributes exactly one entry there).
    plant_count = sum(histograms.light_growth.values())

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
        # ``phases`` = light/growth axis (backward-compatible field name).
        phases=histograms.light_growth,
        # ``nutrient_phase_histogram`` = nutrient/fertilizer axis (AUT-1194,
        # AUT-1183).  Empty dict when no plant has a nutrient_phase set.
        nutrient_phase_histogram=histograms.nutrient,
        avg_phi2=avg_phi2,
    )
