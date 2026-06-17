"""
Zone Entity CRUD API Endpoints

Phase: 0.3 - Zone as DB Entity
Updated: T13-R1 — Archive/Reactivate, Soft-Delete, Status filter

Provides:
- POST   /zones                        - Create a new zone
- GET    /zones                        - List all zones (with status filter)
- GET    /zones/{zone_id}              - Get zone by zone_id
- PUT    /zones/{zone_id}              - Update zone (full)
- PATCH  /zones/{zone_id}              - Partial update zone (+ zone_name sync)
- POST   /zones/{zone_id}/archive      - Archive zone
- POST   /zones/{zone_id}/reactivate   - Reactivate archived zone
- DELETE /zones/{zone_id}              - Soft-delete zone

These endpoints manage zones as independent DB entities.
The existing zone.py router handles zone <-> ESP assignment via MQTT.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ...core.logging_config import get_logger
from ...db.repositories import ESPRepository
from ...db.repositories.subzone_repo import SubzoneRepository
from ...db.repositories.zone_repo import ZoneRepository
from ...schemas.zone import (
    ZoneListEntry,
    ZoneListResponse,
)
from ...schemas.zone_entity import (
    ZoneCreate,
    ZoneDeleteResponse,
    ZoneResponse,
    ZoneUpdate,
)
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/zones", tags=["zones"])


@router.post(
    "",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Zone",
    description="Create a new zone as an independent entity.",
    responses={
        201: {"description": "Zone created successfully"},
        409: {"description": "Zone with this zone_id already exists"},
    },
)
async def create_zone(
    request: ZoneCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneResponse:
    zone_repo = ZoneRepository(db)

    if await zone_repo.exists_by_zone_id(request.zone_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zone with zone_id '{request.zone_id}' already exists",
        )

    zone = await zone_repo.create(
        zone_id=request.zone_id,
        name=request.name,
        description=request.description,
    )
    await db.commit()
    await db.refresh(zone)

    logger.info(
        "Zone created by %s: zone_id=%s, name=%s",
        current_user.username,
        zone.zone_id,
        zone.name,
    )
    return ZoneResponse.model_validate(zone)


@router.get(
    "",
    response_model=ZoneListResponse,
    summary="List Zones",
    description="List all zones enriched with device/sensor/actuator counts. Use `status` to filter by lifecycle status.",
    responses={200: {"description": "List of all zones with device counts"}},
)
async def list_zones(
    db: DBSession,
    _user: ActiveUser,
    zone_status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status: 'active', 'archived', 'deleted'. Default: all non-deleted.",
    ),
) -> ZoneListResponse:
    zone_repo = ZoneRepository(db)
    zone_rows = await zone_repo.list_with_device_counts(status_filter=zone_status)

    zones = [
        ZoneListEntry(
            zone_id=row["zone_id"],
            zone_name=row["zone_name"],
            status=row["status"],
            device_count=row["device_count"],
            sensor_count=row["sensor_count"],
            actuator_count=row["actuator_count"],
        )
        for row in zone_rows
    ]
    return ZoneListResponse(zones=zones, total=len(zones))


@router.get(
    "/{zone_id}",
    response_model=ZoneResponse,
    summary="Get Zone",
    description="Get a single zone by its zone_id.",
    responses={
        200: {"description": "Zone found"},
        404: {"description": "Zone not found"},
    },
)
async def get_zone(
    zone_id: str,
    db: DBSession,
    _user: ActiveUser,
) -> ZoneResponse:
    zone_repo = ZoneRepository(db)
    zone = await zone_repo.get_by_zone_id(zone_id)

    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    return ZoneResponse.model_validate(zone)


@router.put(
    "/{zone_id}",
    response_model=ZoneResponse,
    summary="Update Zone",
    description="Update zone name and/or description.",
    responses={
        200: {"description": "Zone updated"},
        404: {"description": "Zone not found"},
    },
)
async def update_zone(
    zone_id: str,
    request: ZoneUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneResponse:
    zone_repo = ZoneRepository(db)
    zone = await zone_repo.get_by_zone_id(zone_id)

    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    updated = await zone_repo.update(
        id=zone.id,
        name=request.name,
        description=request.description,
    )

    # BUG-10: Sync denormalized zone_name in esp_devices on rename
    if request.name is not None and request.name != zone.name:
        synced = await zone_repo.sync_zone_name_to_devices(zone_id, request.name)
        if synced > 0:
            logger.info("Synced zone_name to %d device(s) for zone %s", synced, zone_id)

    await db.commit()
    await db.refresh(updated)

    logger.info("Zone updated by %s: zone_id=%s", current_user.username, zone_id)
    return ZoneResponse.model_validate(updated)


@router.patch(
    "/{zone_id}",
    response_model=ZoneResponse,
    summary="Partial Update Zone",
    description="Partially update zone. Only provided fields are changed.",
    responses={
        200: {"description": "Zone updated"},
        400: {"description": "No fields to update"},
        404: {"description": "Zone not found"},
    },
)
async def patch_zone(
    zone_id: str,
    request: ZoneUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneResponse:
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    zone_repo = ZoneRepository(db)
    zone = await zone_repo.get_by_zone_id(zone_id)

    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    updated = await zone_repo.update(
        id=zone.id,
        **update_data,
    )

    # BUG-10: Sync denormalized zone_name in esp_devices on rename
    if "name" in update_data:
        synced = await zone_repo.sync_zone_name_to_devices(zone_id, update_data["name"])
        if synced > 0:
            logger.info("Synced zone_name to %d device(s) for zone %s", synced, zone_id)

    await db.commit()
    await db.refresh(updated)

    logger.info(
        "Zone patched by %s: zone_id=%s, fields=%s",
        current_user.username,
        zone_id,
        list(update_data.keys()),
    )
    return ZoneResponse.model_validate(updated)


# =============================================================================
# Zone Lifecycle Endpoints (T13-R1)
# =============================================================================


@router.post(
    "/{zone_id}/archive",
    response_model=ZoneResponse,
    summary="Archive Zone",
    description="""
    Archive a zone. Archived zones are read-only.

    **Rules:**
    - All devices must be unassigned or moved to another zone BEFORE archiving.
    - Subzones are deactivated (is_active=False) on archive.
    - Archived zones still show historical data in Monitor (read-only).
    """,
    responses={
        200: {"description": "Zone archived"},
        400: {"description": "Zone still has assigned devices"},
        404: {"description": "Zone not found"},
    },
)
async def archive_zone(
    zone_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneResponse:
    zone_repo = ZoneRepository(db)
    esp_repo = ESPRepository(db)

    zone = await zone_repo.get_by_zone_id(zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    if zone.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only active zones can be archived. Current status: {zone.status}",
        )

    # Check for assigned devices (blocking for archive)
    devices = await esp_repo.get_by_zone(zone_id)
    if devices:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot archive zone with {len(devices)} device(s) assigned. "
                "Move or unassign all devices first."
            ),
        )

    # Archive the zone
    archived = await zone_repo.archive(zone_id)
    if not archived:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    # Deactivate all subzones in this zone
    subzone_repo = SubzoneRepository(db)
    deactivated = await subzone_repo.deactivate_by_zone(zone_id)

    await db.commit()
    await db.refresh(archived)

    logger.info(
        "Zone archived by %s: zone_id=%s (%d subzones deactivated)",
        current_user.username,
        zone_id,
        deactivated,
    )
    return ZoneResponse.model_validate(archived)


@router.post(
    "/{zone_id}/reactivate",
    response_model=ZoneResponse,
    summary="Reactivate Zone",
    description="""
    Reactivate an archived zone.

    **Note:** Subzones remain deactivated after reactivation.
    User must manually reactivate subzones.
    """,
    responses={
        200: {"description": "Zone reactivated"},
        400: {"description": "Zone is not archived"},
        404: {"description": "Zone not found"},
    },
)
async def reactivate_zone(
    zone_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneResponse:
    zone_repo = ZoneRepository(db)

    zone = await zone_repo.get_by_zone_id(zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    if zone.status != "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only archived zones can be reactivated. Current status: {zone.status}",
        )

    reactivated = await zone_repo.reactivate(zone_id)
    if not reactivated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    await db.commit()
    await db.refresh(reactivated)

    logger.info("Zone reactivated by %s: zone_id=%s", current_user.username, zone_id)
    return ZoneResponse.model_validate(reactivated)


@router.delete(
    "/{zone_id}",
    response_model=ZoneDeleteResponse,
    summary="Delete Zone (Soft-Delete)",
    description="""
    Soft-delete a zone. Sets status='deleted' and deleted_at timestamp.

    T13-R1: Uses soft-delete instead of hard-delete.
    Zone data remains in DB. Deleted zones are only visible to admins.

    If devices are still assigned, deletion is blocked (unlike before).
    """,
    responses={
        200: {"description": "Zone soft-deleted"},
        400: {"description": "Zone still has assigned devices"},
        404: {"description": "Zone not found"},
    },
)
async def delete_zone(
    zone_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneDeleteResponse:
    zone_repo = ZoneRepository(db)
    esp_repo = ESPRepository(db)

    zone = await zone_repo.get_by_zone_id(zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    # Block deletion if devices are still assigned (T13-R1: FK constraint)
    devices = await esp_repo.get_by_zone(zone_id)
    device_count = len(devices)
    if device_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete zone with {device_count} device(s) assigned. "
                "Move or unassign all devices first."
            ),
        )

    # Soft-delete
    deleted = await zone_repo.soft_delete(zone_id, deleted_by=current_user.username)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found",
        )

    await db.commit()

    logger.info("Zone soft-deleted by %s: zone_id=%s", current_user.username, zone_id)

    return ZoneDeleteResponse(
        success=True,
        message="Zone deleted (soft-delete)",
        zone_id=zone_id,
        had_devices=False,
        device_count=0,
    )
