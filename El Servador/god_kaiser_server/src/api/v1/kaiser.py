"""
Kaiser Management REST API

Phase 1: Kaiser hierarchy implementation.
Status: IMPLEMENTED

Provides REST endpoints for Kaiser relay node management:
- GET /kaiser - List all Kaisers
- GET /kaiser/{kaiser_id} - Kaiser details with zones
- GET /kaiser/{kaiser_id}/hierarchy - Full tree: Kaiser → Zones → Subzones → Devices
- POST /kaiser - Register new Kaiser
- PUT /kaiser/{kaiser_id}/zones - Update managed zones
"""

from typing import Annotated

from fastapi import APIRouter, Path

from ...core.exceptions import (
    KaiserAlreadyExistsError,
    KaiserIdRequiredError,
    KaiserNotFoundException,
)
from ...core.logging_config import get_logger
from ..deps import ActiveUser, DBSession, OperatorUser
from ...services.kaiser_service import KaiserService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v1/kaiser",
    tags=["kaiser"],
)


@router.get(
    "",
    summary="List all Kaisers",
    description="Get all registered Kaiser relay nodes.",
)
async def list_kaisers(
    session: DBSession,
    _user: ActiveUser,
) -> dict:
    """List all Kaiser nodes."""
    service = KaiserService(session)
    kaisers = await service.get_all_kaisers()
    return {
        "success": True,
        "data": [
            {
                "kaiser_id": k.kaiser_id,
                "status": k.status,
                "zone_ids": k.zone_ids or [],
                "capabilities": k.capabilities or {},
                "last_seen": k.last_seen.isoformat() if k.last_seen else None,
            }
            for k in kaisers
        ],
        "total_count": len(kaisers),
    }


@router.get(
    "/{kaiser_id}",
    summary="Get Kaiser details",
    description="Get details of a specific Kaiser with its managed zones.",
)
async def get_kaiser(
    kaiser_id: Annotated[str, Path(description="Kaiser identifier", max_length=50)],
    session: DBSession,
    _user: ActiveUser,
) -> dict:
    """Get Kaiser details."""
    service = KaiserService(session)
    kaiser = await service.get_kaiser(kaiser_id)
    if not kaiser:
        # AUT-228 (E3): Strukturierte Exception statt HTTPException -> numeric_code 5307
        raise KaiserNotFoundException(kaiser_id)

    return {
        "success": True,
        "kaiser_id": kaiser.kaiser_id,
        "status": kaiser.status,
        "zone_ids": kaiser.zone_ids or [],
        "capabilities": kaiser.capabilities or {},
        "last_seen": kaiser.last_seen.isoformat() if kaiser.last_seen else None,
        "kaiser_metadata": kaiser.kaiser_metadata or {},
    }


@router.get(
    "/{kaiser_id}/hierarchy",
    summary="Get full hierarchy",
    description="Full tree: Kaiser → Zones (with context) → Subzones → Devices",
)
async def get_hierarchy(
    kaiser_id: Annotated[str, Path(description="Kaiser identifier", max_length=50)],
    session: DBSession,
    _user: ActiveUser,
) -> dict:
    """Get full Kaiser hierarchy."""
    service = KaiserService(session)
    hierarchy = await service.get_hierarchy(kaiser_id)
    if not hierarchy:
        # AUT-228 (E3): Strukturierte Exception statt HTTPException -> numeric_code 5307
        raise KaiserNotFoundException(kaiser_id)

    return {"success": True, **hierarchy}


@router.post(
    "",
    summary="Register Kaiser",
    description="Register a new Kaiser relay node.",
    status_code=201,
)
async def register_kaiser(
    body: dict,
    session: DBSession,
    user: OperatorUser,
) -> dict:
    """Register a new Kaiser via :class:`KaiserService` (P2 service-pattern)."""
    kaiser_id = body.get("kaiser_id")
    if not kaiser_id:
        # AUT-228 (E3): Strukturierte Exception statt HTTPException -> numeric_code 5205
        raise KaiserIdRequiredError()

    service = KaiserService(session)
    try:
        kaiser = await service.register_kaiser(
            kaiser_id=kaiser_id,
            zone_ids=body.get("zone_ids", []),
            capabilities=body.get("capabilities"),
            ip_address=body.get("ip_address"),
            mac_address=body.get("mac_address"),
        )
    except ValueError as exc:
        # AUT-228 (E3 + AUT-224): Strukturierte Exception statt HTTPException(409)
        raise KaiserAlreadyExistsError(kaiser_id, str(exc)) from exc

    logger.info(f"Kaiser '{kaiser_id}' registered by {user.username}")

    return {
        "success": True,
        "message": f"Kaiser '{kaiser_id}' registered",
        "kaiser_id": kaiser.kaiser_id,
    }


@router.put(
    "/{kaiser_id}/zones",
    summary="Update managed zones",
    description="Set the list of zone IDs managed by this Kaiser.",
)
async def update_zones(
    kaiser_id: Annotated[str, Path(description="Kaiser identifier", max_length=50)],
    body: dict,
    session: DBSession,
    user: OperatorUser,
) -> dict:
    """Update zones managed by a Kaiser."""
    from ...db.repositories.kaiser_repo import KaiserRepository
    from sqlalchemy.orm.attributes import flag_modified

    repo = KaiserRepository(session)
    kaiser = await repo.get_by_kaiser_id(kaiser_id)
    if not kaiser:
        # AUT-228 (E3): Strukturierte Exception statt HTTPException -> numeric_code 5307
        raise KaiserNotFoundException(kaiser_id)

    zone_ids = body.get("zone_ids", [])
    kaiser.zone_ids = zone_ids
    flag_modified(kaiser, "zone_ids")
    await session.commit()

    logger.info(f"Kaiser '{kaiser_id}' zones updated to {zone_ids} by {user.username}")

    return {
        "success": True,
        "kaiser_id": kaiser_id,
        "zone_ids": zone_ids,
    }
