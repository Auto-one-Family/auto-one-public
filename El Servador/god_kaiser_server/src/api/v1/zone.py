"""
Zone Assignment API Endpoint

Phase: 7 - Zone Management
Updated: T13-R1 — Zone Consolidation, subzone_strategy, zones-table-based list

Provides:
- POST /zone/devices/{esp_id}/assign - Assign ESP to zone (with subzone_strategy)
- DELETE /zone/devices/{esp_id}/zone - Remove zone assignment
- GET /zone/zones - List all zones (from zones table, enriched with counts)
- GET /zone/devices/{esp_id} - Get zone info for ESP
- GET /zone/{zone_id}/devices - Get all ESPs in zone
- GET /zone/{zone_id}/monitor-data - Zone monitor data (L2)
- GET /zone/unassigned - Get ESPs without zone assignment
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from ...core.exceptions import ESPNotFoundError
from ...core.logging_config import get_logger
from ...db.repositories import ESPRepository
from ...schemas.monitor import ZoneMonitorData
from ...schemas.zone import (
    ZoneAssignRequest,
    ZoneAssignResponse,
    ZoneInfo,
    ZoneListEntry,
    ZoneListResponse,
    ZoneRemoveResponse,
)
from ...services.monitor_data_service import MonitorDataService
from ...services.zone_service import ZoneService
from ..deps import DBSession, ActiveUser, OperatorUser, get_command_bridge

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/zone", tags=["zone"])


# =============================================================================
# Zone Assignment Endpoints
# =============================================================================


@router.post(
    "/devices/{esp_id}/assign",
    response_model=ZoneAssignResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign ESP to Zone",
    description="""
    Assign an ESP device to a zone via MQTT.

    **T13-R1:** Zone must exist in zones table. Use `subzone_strategy` to control
    how subzones are handled when changing zones:
    - `transfer` (default): Move subzones to new zone
    - `copy`: Clone subzones to new zone, originals stay
    - `reset`: Leave subzones in old zone, start fresh

    **Finalität (HTTP):** DB-Änderung committed; bei echten Geräten wartet der Server optional über
    `MQTTCommandBridge` auf `zone/ack` (Timeout). Felder `mqtt_sent` und `ack_received` im Response-Body
    präzisieren Broker- vs. Gerätebestätigung; Details siehe `docs/finalitaet-http-mqtt-ws.md`.
    Asynchron zusätzlich WebSocket `zone_assignment`.

    **MQTT Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`
    """,
    responses={
        200: {"description": "Zone assignment saved (check mqtt_sent for MQTT status)"},
        400: {"description": "Zone not found or not active"},
        404: {"description": "ESP device not found"},
    },
)
async def assign_zone(
    esp_id: str,
    request: ZoneAssignRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneAssignResponse:
    """Assign ESP device to a zone."""
    esp_repo = ESPRepository(db)
    zone_service = ZoneService(esp_repo, command_bridge=get_command_bridge())

    try:
        result = await zone_service.assign_zone(
            device_id=esp_id,
            zone_id=request.zone_id,
            master_zone_id=request.master_zone_id,
            zone_name=request.zone_name,
            subzone_strategy=request.subzone_strategy,
            changed_by=current_user.username,
        )

        await db.commit()

        logger.info(
            "Zone assignment for %s by %s: zone_id=%s, strategy=%s (%s)",
            esp_id,
            current_user.username,
            request.zone_id,
            request.subzone_strategy,
            "MQTT sent" if result.mqtt_sent else "MQTT offline",
        )

        return result

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg and "ESP" in error_msg:
            raise ESPNotFoundError(esp_id)
        # Zone not found or not active
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )


@router.delete(
    "/devices/{esp_id}/zone",
    response_model=ZoneRemoveResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove Zone Assignment",
    description=(
        "Entfernt die Zonenzuweisung. **Finalität:** wie bei Assign — DB + MQTT, bei echten ESPs "
        "optional Warten auf `zone/ack` über die Bridge; Response-Felder `mqtt_sent` / `ack_received`. "
        "Siehe `docs/finalitaet-http-mqtt-ws.md`."
    ),
    responses={
        200: {"description": "Zone removed (check mqtt_sent for MQTT status)"},
        404: {"description": "ESP device not found"},
    },
)
async def remove_zone(
    esp_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> ZoneRemoveResponse:
    """Remove zone assignment from ESP device."""
    esp_repo = ESPRepository(db)
    zone_service = ZoneService(esp_repo, command_bridge=get_command_bridge())

    try:
        result = await zone_service.remove_zone(
            device_id=esp_id,
            changed_by=current_user.username,
        )
        await db.commit()

        logger.info(
            "Zone removal for %s by %s (%s)",
            esp_id,
            current_user.username,
            "MQTT sent" if result.mqtt_sent else "MQTT offline",
        )

        return result

    except ValueError:
        raise ESPNotFoundError(esp_id)


# =============================================================================
# Zone List Endpoint (T13-R1: zones table as Single Source of Truth)
# =============================================================================


@router.get(
    "/zones",
    response_model=ZoneListResponse,
    summary="[DEPRECATED] List All Zones",
    description="""
    DEPRECATED — Use GET /api/v1/zones/ instead.

    List all zones from the zones table (Single Source of Truth).

    T13-R1: Sourced from zones table, enriched with device/sensor/actuator counts.
    ZoneContext metadata is joined for zone names (if available).

    Use `status` query parameter to filter by zone status.
    Default: shows active and archived zones (excludes deleted).
    """,
    deprecated=True,
    responses={
        200: {"description": "Zone list with device/sensor/actuator counts"},
    },
)
async def list_zones(
    db: DBSession,
    _user: ActiveUser,
    zone_status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by zone status: 'active', 'archived', 'deleted'. Default: all non-deleted.",
    ),
) -> ZoneListResponse:
    """
    List all zones from zones table, enriched with device counts.

    T13-R1: zones table is the Single Source of Truth.
    ZoneContext is joined for additional zone names.
    """
    from ...db.repositories.zone_repo import ZoneRepository

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


# =============================================================================
# Zone Query Endpoints
# =============================================================================


@router.get(
    "/devices/{esp_id}",
    response_model=ZoneInfo,
    summary="Get Zone Info for ESP",
    description="Get current zone assignment information for an ESP device.",
    responses={
        200: {"description": "Zone info retrieved"},
        404: {"description": "ESP device not found"},
    },
)
async def get_zone_info(
    esp_id: str,
    db: DBSession,
    _user: ActiveUser,
) -> ZoneInfo:
    """Get zone information for an ESP device."""
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)

    if not device:
        raise ESPNotFoundError(esp_id)

    return ZoneInfo(
        zone_id=device.zone_id,
        master_zone_id=device.master_zone_id,
        zone_name=device.zone_name,
        is_zone_master=device.is_zone_master,
        kaiser_id=device.kaiser_id,
    )


@router.get(
    "/{zone_id}/devices",
    response_model=List[ZoneInfo],
    summary="Get ESPs in Zone",
    description="Get all ESP devices assigned to a specific zone.",
    responses={
        200: {"description": "List of ESPs in zone"},
    },
)
async def get_zone_devices(
    zone_id: str,
    db: DBSession,
    _user: ActiveUser,
) -> List[ZoneInfo]:
    """Get all ESP devices in a zone."""
    esp_repo = ESPRepository(db)
    devices = await esp_repo.get_by_zone(zone_id)

    return [
        ZoneInfo(
            zone_id=device.zone_id,
            master_zone_id=device.master_zone_id,
            zone_name=device.zone_name,
            is_zone_master=device.is_zone_master,
            kaiser_id=device.kaiser_id,
        )
        for device in devices
    ]


@router.get(
    "/{zone_id}/monitor-data",
    response_model=ZoneMonitorData,
    summary="Get Zone Monitor Data (L2)",
    description="""
    Get sensors and actuators for a zone, grouped by subzone (GPIO-based).

    Used by MonitorView L2 for subzone accordion display.
    Devices without subzone assignment appear in "Keine Subzone".
    """,
    responses={
        200: {"description": "Zone monitor data with subzone groups"},
    },
)
async def get_zone_monitor_data(
    zone_id: str,
    db: DBSession,
    _user: ActiveUser,
) -> ZoneMonitorData:
    """Get monitor data for a zone (sensors/actuators grouped by subzone)."""
    service = MonitorDataService(db)
    return await service.get_zone_monitor_data(zone_id)


@router.get(
    "/unassigned",
    response_model=List[str],
    summary="Get Unassigned ESPs",
    description="Get device IDs of all ESPs without zone assignment.",
    responses={
        200: {"description": "List of unassigned ESP device IDs"},
    },
)
async def get_unassigned_devices(
    db: DBSession,
    _user: ActiveUser,
) -> List[str]:
    """Get all ESPs without zone assignment."""
    esp_repo = ESPRepository(db)
    zone_service = ZoneService(esp_repo)
    devices = await zone_service.get_unassigned_esps()

    return [device.device_id for device in devices]
