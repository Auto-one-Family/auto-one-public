"""
Tank / Nutrient Ledger Write API (AUT-1217, AUT-1223, AUT-1225, AUT-1343)

Endpoints:
- GET    /v1/tanks                                      — list tanks (AUT-1223 Q3)
- GET    /v1/tanks/{tank_id}                             — get tank (AUT-1223 Q3)
- GET    /v1/tanks/{tank_id}/targets                     — Soll targets from plan_segment@now (AUT-1225 Q4)
- GET    /v1/tanks/{tank_id}/volume                      — running volume Anker±Flow (AUT-1377 A3)
- GET    /v1/tanks/{tank_id}/devices                     — devices assigned to tank (AUT-1223 Q2)
- PUT    /v1/tanks/{tank_id}/devices/{esp_id}            — assign device to tank (AUT-1223 Q2)
- DELETE /v1/tanks/{tank_id}/devices/{esp_id}            — clear device assignment (AUT-1223 Q2)
- POST   /v1/tanks                                      — create tank
- PATCH  /v1/tanks/{tank_id}                             — update tank (AUT-1381 fresh water)
- POST   /v1/tanks/{tank_id}/subzones                   — assign subzone
- DELETE /v1/tanks/{tank_id}/subzones/{subzone_config_id} — remove assignment
- POST   /v1/tanks/{tank_id}/assist/dose-expectation    — Salt calculator assist (AUT-1343, read-only)
- POST   /v1/tanks/{tank_id}/batches                    — append ledger entry (AUT-1346 prior_*)

Pattern: SensorSubzoneAssignment routes in subzone.py (AUT-1155).
No dosing-pump / automation-rule dependency.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from ...core.logging_config import get_logger
from ...schemas.tank import (
    NutrientBatchCreate,
    NutrientBatchResponse,
    TankCreate,
    TankDeviceAssignResponse,
    TankDevicesResponse,
    TankDeviceSummary,
    TankDeviceUnassignResponse,
    TankResponse,
    TankSubzoneAssignRequest,
    TankSubzoneAssignmentInfo,
    TankSubzoneRemoveResponse,
    TankTargetsResponse,
    TankUpdate,
    TankVolumeResponse,
    SaltCalculatorAssistRequest,
    SaltCalculatorAssistResponse,
)
from ...services.tank_service import TankService
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/tanks", tags=["tanks"])


# =============================================================================
# Read: List / Get (AUT-1223 Q3)
# =============================================================================


@router.get(
    "",
    response_model=List[TankResponse],
    summary="List Tanks",
    description="List all tanks. Needed for device↔tank assignment UI (AUT-1223).",
)
async def list_tanks(
    db: DBSession,
    current_user: ActiveUser,
) -> List[TankResponse]:
    """List all tanks."""
    service = TankService(db)
    return await service.list_tanks()


@router.get(
    "/{tank_id}",
    response_model=TankResponse,
    responses={404: {"description": "Tank not found"}},
    summary="Get Tank",
    description="Get a single tank by id.",
)
async def get_tank(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    db: DBSession,
    current_user: ActiveUser,
) -> TankResponse:
    """Get a tank by id."""
    service = TankService(db)
    result = await service.get_tank(tank_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Tank '{tank_id}' not found"
        )
    return result


@router.get(
    "/{tank_id}/targets",
    response_model=TankTargetsResponse,
    responses={404: {"description": "Tank not found"}},
    summary="Get Tank Targets (Soll)",
    description=(
        "Resolve the current target_ec / target_ph Soll for a tank from "
        "plan_segment@now via Tank.zone_id (+ optional subzone assignment). "
        "Read-only projection — does not touch rule setpoints or sensor "
        "thresholds (AUT-1225 Q4)."
    ),
)
async def get_tank_targets(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    db: DBSession,
    current_user: ActiveUser,
) -> TankTargetsResponse:
    """Resolve tank Soll targets at 'now' from plan_segment (AUT-1225 Q4)."""
    service = TankService(db)
    try:
        return await service.get_targets_at_now(tank_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{tank_id}/volume",
    response_model=TankVolumeResponse,
    responses={404: {"description": "Tank not found"}},
    summary="Get Tank Running Volume (Ist)",
    description=(
        "Running volume from persisted dose_config.volume_l (same resolve_v_real "
        "as K2 / AUT-1563). Read-only display facade — does not parse sensor "
        "names and does not treat GPIO14 as volume truth. "
        "nominal_volume_l is returned separately and is NOT the Ist (AUT-1377)."
    ),
)
async def get_tank_volume(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    db: DBSession,
    current_user: ActiveUser,
) -> TankVolumeResponse:
    """Resolve running tank volume for display (AUT-1377 A3)."""
    service = TankService(db)
    try:
        return await service.get_volume_truth(tank_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# =============================================================================
# Tank ↔ ESP Device Assignment (n:1, AUT-1223 Q2)
# =============================================================================
# Cardinality n:1 via nullable esp_devices.tank_id FK — analogous to
# ESPDevice.zone_id. NOT the n:m tank_subzone_assignments junction below.


@router.get(
    "/{tank_id}/devices",
    response_model=TankDevicesResponse,
    responses={404: {"description": "Tank not found"}},
    summary="List Devices Assigned to Tank",
    description="List all ESP devices currently assigned to a tank (n:1, AUT-1223).",
)
async def list_tank_devices(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    db: DBSession,
    current_user: ActiveUser,
) -> TankDevicesResponse:
    """List ESP devices assigned to a tank."""
    service = TankService(db)
    try:
        devices = await service.get_devices_for_tank(tank_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    summaries = [TankDeviceSummary.model_validate(d) for d in devices]
    return TankDevicesResponse(
        tank_id=str(tank_id),
        devices=summaries,
        count=len(summaries),
    )


@router.put(
    "/{tank_id}/devices/{esp_id}",
    response_model=TankDeviceAssignResponse,
    responses={
        400: {"description": "Device domain is not wasser (AUT-1328)"},
        404: {"description": "Tank or device not found"},
    },
    summary="Assign Device to Tank",
    description=(
        "Alias: assign an ESP device to a tank (n:1) by writing "
        "esp_devices.tank_id (AUT-1223 / AUT-1358). UI-SSOT is "
        "PATCH /esp/devices/{esp_id} {tank_id}; this route keeps the "
        "same column for API/scripts. AUT-1328: domain must be wasser."
    ),
)
async def assign_device_to_tank(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    esp_id: Annotated[str, Path(description="ESP device_id (e.g. ESP_12AB34CD)")],
    db: DBSession,
    current_user: OperatorUser,
) -> TankDeviceAssignResponse:
    """Assign device→tank (n:1)."""
    service = TankService(db)
    try:
        result = await service.assign_device(tank_id=tank_id, esp_device_id=esp_id)
        await db.commit()
        logger.info(
            "ESP device %s assigned to tank %s by %s",
            esp_id,
            tank_id,
            current_user.username,
        )
        return result
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete(
    "/{tank_id}/devices/{esp_id}",
    response_model=TankDeviceUnassignResponse,
    responses={404: {"description": "Tank not found or device not assigned to this tank"}},
    summary="Clear Device Assignment",
    description=(
        "Alias: clear esp_devices.tank_id when the device is assigned to "
        "this tank (AUT-1223 / AUT-1358). UI-SSOT clears via "
        "PATCH /esp/devices/{esp_id} {tank_id: null}."
    ),
)
async def remove_device_from_tank(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    esp_id: Annotated[str, Path(description="ESP device_id (e.g. ESP_12AB34CD)")],
    db: DBSession,
    current_user: OperatorUser,
) -> TankDeviceUnassignResponse:
    """Clear device→tank assignment, only if currently assigned to this tank."""
    service = TankService(db)

    tank = await service.get_tank(tank_id)
    if tank is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Tank '{tank_id}' not found"
        )

    current_tank = await service.get_tank_for_device(esp_id)
    if current_tank is None or str(current_tank.id) != str(tank_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ESP device '{esp_id}' is not assigned to tank '{tank_id}'",
        )

    try:
        await service.clear_device_assignment(esp_id)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    logger.info(
        "Tank assignment cleared for ESP device %s (tank %s) by %s",
        esp_id,
        tank_id,
        current_user.username,
    )
    return TankDeviceUnassignResponse(
        success=True,
        message="Tank device assignment cleared",
        tank_id=str(tank_id),
        device_id=esp_id,
    )


@router.post(
    "",
    response_model=TankResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Tank",
    description="Create a nutrient-solution tank in an existing zone.",
)
async def create_tank(
    request: TankCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> TankResponse:
    """Create a tank (zone-scoped reservoir)."""
    service = TankService(db)
    try:
        result = await service.create_tank(request)
        await db.commit()
        logger.info(
            "Tank created by %s: id=%s zone_id=%s",
            current_user.username,
            result.id,
            result.zone_id,
        )
        return result
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.patch(
    "/{tank_id}",
    response_model=TankResponse,
    responses={404: {"description": "Tank not found"}},
    summary="Update Tank",
    description=(
        "Partial update for tank attributes (AUT-1381): name, nominal_volume_l, "
        "operation_mode, fresh_water_ec_us_cm, fresh_water_ph. "
        "Frischwasser-EC lives on the tank — one place, no silent hardcode."
    ),
)
async def update_tank(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    request: TankUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> TankResponse:
    """Update tank fields (incl. fresh-water quality)."""
    service = TankService(db)
    try:
        result = await service.update_tank(tank_id, request)
        await db.commit()
        logger.info(
            "Tank %s updated by %s fields=%s",
            tank_id,
            current_user.username,
            list(request.model_dump(exclude_unset=True).keys()),
        )
        return result
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/{tank_id}/subzones",
    response_model=TankSubzoneAssignmentInfo,
    status_code=status.HTTP_200_OK,
    summary="Assign Tank to Subzone",
    description=(
        "Assign a tank to a subzone_config via the n:m junction table "
        "`tank_subzone_assignments` (AUT-1217, pattern AUT-1155)."
    ),
)
async def assign_tank_to_subzone(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    request: TankSubzoneAssignRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> TankSubzoneAssignmentInfo:
    """Assign tank→subzone (n:m)."""
    service = TankService(db)
    try:
        result = await service.assign_subzone(
            tank_id=tank_id,
            subzone_config_id=request.subzone_config_id,
            assigned_by=current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete(
    "/{tank_id}/subzones/{subzone_config_id}",
    response_model=TankSubzoneRemoveResponse,
    summary="Remove Tank from Subzone",
    description="Remove a tank↔subzone assignment. The tank itself is not deleted.",
)
async def remove_tank_from_subzone(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    subzone_config_id: Annotated[UUID, Path(description="subzone_configs.id UUID")],
    db: DBSession,
    current_user: OperatorUser,
) -> TankSubzoneRemoveResponse:
    """Remove tank→subzone assignment (n:m)."""
    service = TankService(db)
    try:
        deleted = await service.remove_subzone(
            tank_id=tank_id,
            subzone_config_id=subzone_config_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Assignment tank '{tank_id}' ↔ "
                    f"subzone_config '{subzone_config_id}' not found"
                ),
            )
        await db.commit()
        logger.info(
            "Tank assignment removed by %s: tank=%s subzone=%s",
            current_user.username,
            tank_id,
            subzone_config_id,
        )
        return TankSubzoneRemoveResponse(
            success=True,
            message="Tank assignment removed",
            tank_id=str(tank_id),
            subzone_config_id=str(subzone_config_id),
        )
    except HTTPException:
        raise
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/{tank_id}/assist/dose-expectation",
    response_model=SaltCalculatorAssistResponse,
    summary="Salt Calculator Dose Expectation (Assist, read-only)",
    description=(
        "AUT-1343: Compute feedforward A/B dose expectation from System-EC, "
        "ledger V_alt (or override), EC_wasser dilution, and empiric "
        "concentration via calculate_dose_ml (A:B 1:1). "
        "Read-only — does not persist and does not dose actuators."
    ),
)
async def compute_tank_dose_assist(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    request: SaltCalculatorAssistRequest,
    db: DBSession,
    current_user: ActiveUser,
) -> SaltCalculatorAssistResponse:
    """Read-only Salt calculator assist expectation (no dosing)."""
    service = TankService(db)
    try:
        return await service.compute_dose_assist(tank_id=tank_id, data=request)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/{tank_id}/batches",
    response_model=NutrientBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Nutrient Ledger Entry",
    description=(
        "Append a nutrient-solution batch ledger entry for a tank. "
        "Supports all entry_types including system_incident. "
        "No dosing pump or automation rule is required."
    ),
)
async def create_tank_batch(
    tank_id: Annotated[UUID, Path(description="Tank UUID")],
    request: NutrientBatchCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> NutrientBatchResponse:
    """Append a ledger entry (manual bookkeeping path)."""
    service = TankService(db)
    try:
        result = await service.create_batch(tank_id=tank_id, data=request)
        await db.commit()
        logger.info(
            "Ledger entry created by %s: id=%s tank=%s type=%s",
            current_user.username,
            result.id,
            tank_id,
            result.entry_type,
        )
        return result
    except ValueError as e:
        await db.rollback()
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
