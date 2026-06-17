"""
Component Export API — AI-Ready JSON Export

Phase: K4 (Komponenten-Tab Wissensinfrastruktur)
Status: IMPLEMENTED

Provides WoT-TD-inspired JSON export of all system components,
zones, and system descriptions for MCP server consumption.

Endpoints:
- GET /v1/export/components          — All components as AI-Ready JSON
- GET /v1/export/components/{id}     — Single component
- GET /v1/export/zones               — All zones with context
- GET /v1/export/zones/{zone_id}     — Single zone with all components + context
- GET /v1/export/system-description  — Full system as WoT System Description
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ActiveUser, DBSession
from ...core.logging_config import get_logger
from ...db.models.actuator import ActuatorConfig
from ...db.models.esp import ESPDevice
from ...db.models.sensor import SensorConfig
from ...db.models.zone_context import ZoneContext
from ...db.repositories import (
    ActuatorRepository,
    ESPRepository,
    SensorRepository,
    ZoneContextRepository,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/export", tags=["export"])


# =============================================================================
# Serializer Helpers
# =============================================================================

SENSOR_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "sht31_temp": {
        "measures": ["temperature"],
        "units": {"temperature": "°C"},
        "ranges": {"temperature": [-40, 125]},
        "accuracy": {"temperature": "±0.3°C"},
    },
    "sht31_humidity": {
        "measures": ["humidity"],
        "units": {"humidity": "%RH"},
        "ranges": {"humidity": [0, 100]},
        "accuracy": {"humidity": "±2%RH"},
    },
    "bmp280_temp": {
        "measures": ["temperature"],
        "units": {"temperature": "°C"},
        "ranges": {"temperature": [-40, 85]},
        "accuracy": {"temperature": "±1.0°C"},
    },
    "bmp280_pressure": {
        "measures": ["pressure"],
        "units": {"pressure": "hPa"},
        "ranges": {"pressure": [300, 1100]},
        "accuracy": {"pressure": "±1.0hPa"},
    },
    "ds18b20": {
        "measures": ["temperature"],
        "units": {"temperature": "°C"},
        "ranges": {"temperature": [-55, 125]},
        "accuracy": {"temperature": "±0.5°C"},
    },
    "moisture": {
        "measures": ["soil_moisture"],
        "units": {"soil_moisture": "%"},
        "ranges": {"soil_moisture": [0, 100]},
    },
    "ph": {
        "measures": ["ph"],
        "units": {"ph": "pH"},
        "ranges": {"ph": [0, 14]},
        "accuracy": {"ph": "±0.1pH"},
    },
    "ec": {
        "measures": ["electrical_conductivity"],
        "units": {"electrical_conductivity": "µS/cm"},
        "ranges": {"electrical_conductivity": [0, 20000]},
    },
    "light": {
        "measures": ["illuminance"],
        "units": {"illuminance": "lux"},
        "ranges": {"illuminance": [0, 120000]},
    },
}

ACTUATOR_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "relay": {
        "actions": ["on", "off", "toggle"],
        "type": "binary",
    },
    "pwm": {
        "actions": ["set_duty", "on", "off"],
        "type": "continuous",
        "range": [0.0, 1.0],
    },
    "pump": {
        "actions": ["on", "off", "set_flow"],
        "type": "binary",
    },
    "valve": {
        "actions": ["open", "close"],
        "type": "binary",
    },
    "fan": {
        "actions": ["on", "off", "set_speed"],
        "type": "continuous",
        "range": [0.0, 1.0],
    },
}


def _serialize_component(
    esp: ESPDevice,
    sensor: Optional[SensorConfig] = None,
    actuator: Optional[ActuatorConfig] = None,
    latest_value: Optional[dict] = None,
    actuator_state: Optional[dict] = None,
) -> dict[str, Any]:
    """Serialize a single component to AI-Ready JSON format."""
    is_sensor = sensor is not None
    config = sensor if is_sensor else actuator
    if config is None:
        raise ValueError("Either sensor or actuator must be provided")

    device_type = (
        sensor.sensor_type if is_sensor else actuator.actuator_type  # type: ignore[union-attr]
    )

    component_id = (
        f"sensor_{device_type}_{str(config.id)[:8]}"
        if is_sensor
        else f"actuator_{device_type}_{str(config.id)[:8]}"
    )

    # Build hardware section
    metadata = (
        sensor.sensor_metadata if is_sensor else actuator.actuator_metadata  # type: ignore[union-attr]
    )
    hardware: dict[str, Any] = {
        "interface": sensor.interface_type if is_sensor else "GPIO",  # type: ignore[union-attr]
        "firmware": esp.firmware_version,
    }
    if metadata:
        for key in ("manufacturer", "model", "serial_number", "installation_date"):
            if key in metadata:
                hardware[key] = metadata[key]
    if is_sensor and sensor.i2c_address:  # type: ignore[union-attr]
        hardware["i2c_address"] = hex(sensor.i2c_address)  # type: ignore[union-attr]
    if is_sensor and sensor.onewire_address:  # type: ignore[union-attr]
        hardware["onewire_address"] = sensor.onewire_address  # type: ignore[union-attr]

    # Build capabilities
    if is_sensor:
        capabilities = SENSOR_CAPABILITY_MAP.get(
            device_type,
            {
                "measures": [device_type],
                "units": {device_type: ""},
            },
        )
    else:
        capabilities = ACTUATOR_CAPABILITY_MAP.get(
            device_type,
            {
                "actions": ["on", "off"],
                "type": "binary",
            },
        )

    # Build current_state
    current_state: dict[str, Any] = {
        "status": esp.status,
        "last_seen": esp.last_seen.isoformat() if esp.last_seen else None,
    }
    if is_sensor and latest_value:
        current_state["values"] = latest_value
    if not is_sensor and actuator_state:
        current_state["state"] = actuator_state

    # Build runtime
    runtime_stats = config.runtime_stats or {}
    runtime: dict[str, Any] = {}
    if runtime_stats:
        for key in (
            "uptime_hours",
            "last_restart",
            "next_maintenance",
            "error_rate_24h",
        ):
            if key in runtime_stats:
                runtime[key] = runtime_stats[key]

    # Build alerts
    alert_config = config.alert_config or {}
    alerts: dict[str, Any] = {
        "suppressed": not alert_config.get("alerts_enabled", True),
    }
    if is_sensor:
        thresholds = sensor.thresholds or {}  # type: ignore[union-attr]
        custom_thresholds = alert_config.get("custom_thresholds", {})
        if custom_thresholds:
            alerts["thresholds"] = custom_thresholds
        elif thresholds:
            alerts["thresholds"] = thresholds

    result: dict[str, Any] = {
        "@context": "automationone://schemas/component/v1",
        "id": component_id,
        "type": "sensor" if is_sensor else "actuator",
        "deviceType": device_type,
        "name": sensor.sensor_name if is_sensor else actuator.actuator_name,  # type: ignore[union-attr]
        "hardware": hardware,
        "location": {
            "zone_id": esp.zone_id,
            "zone_name": esp.zone_name,
            "esp_id": esp.device_id,
            "gpio": config.gpio,
        },
        "capabilities": capabilities,
        "current_state": current_state,
    }

    if runtime:
        result["runtime"] = runtime
    if alerts.get("thresholds") or alerts.get("suppressed"):
        result["alerts"] = alerts
    if metadata:
        # Include remaining metadata fields not already in hardware
        extra_meta = {
            k: v
            for k, v in metadata.items()
            if k not in ("manufacturer", "model", "serial_number", "installation_date")
        }
        if extra_meta:
            result["metadata"] = extra_meta

    return result


def _serialize_zone(
    zone_id: str,
    zone_name: Optional[str],
    zone_context: Optional[ZoneContext],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    """Serialize a zone with context and components to AI-Ready JSON."""
    result: dict[str, Any] = {
        "@context": "automationone://schemas/zone/v1",
        "zone_id": zone_id,
        "zone_name": zone_name or zone_id,
    }

    if zone_context:
        ctx: dict[str, Any] = {}
        for field in (
            "plant_count",
            "variety",
            "substrate",
            "growth_phase",
            "planted_date",
            "expected_harvest",
            "responsible_person",
            "work_hours_weekly",
            "notes",
        ):
            val = getattr(zone_context, field, None)
            if val is not None:
                if hasattr(val, "isoformat"):
                    ctx[field] = val.isoformat()
                else:
                    ctx[field] = val
        # Computed properties
        if zone_context.plant_age_days is not None:
            ctx["plant_age_days"] = zone_context.plant_age_days
        if zone_context.days_to_harvest is not None:
            ctx["days_to_harvest"] = zone_context.days_to_harvest
        if zone_context.custom_data:
            ctx["custom_data"] = zone_context.custom_data
        result["context"] = ctx

    result["components"] = components

    # Build environment summary from sensor components
    env_summary: dict[str, Any] = {}
    for comp in components:
        if comp.get("type") == "sensor" and comp.get("current_state", {}).get("values"):
            values = comp["current_state"]["values"]
            caps = comp.get("capabilities", {})
            measures = caps.get("measures", [])
            for measure in measures:
                if measure in values:
                    env_summary[measure] = {"current": values[measure]}

    if env_summary:
        result["environment_summary"] = env_summary

    return result


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/components")
async def export_components(
    _user: ActiveUser,
    db: DBSession,
    type: Optional[str] = Query(None, description="Filter by type: sensor or actuator"),
    zone: Optional[str] = Query(None, description="Filter by zone_id"),
    device_type: Optional[str] = Query(
        None, description="Filter by device type (e.g., sht31_temp, relay)"
    ),
) -> dict[str, Any]:
    """
    Export all components as AI-Ready JSON.

    Returns a list of all sensors and actuators in WoT-TD-inspired format.
    Supports filtering by type, zone, and device type.
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    # Get all ESP devices (optionally filtered by zone)
    if zone:
        devices = await esp_repo.get_by_zone(zone)
    else:
        devices = await esp_repo.get_all()

    components: list[dict[str, Any]] = []

    for device in devices:
        # Sensors
        if type is None or type == "sensor":
            sensors = await sensor_repo.get_by_esp(device.id)
            for sensor in sensors:
                if device_type and sensor.sensor_type != device_type:
                    continue
                components.append(_serialize_component(esp=device, sensor=sensor))

        # Actuators
        if type is None or type == "actuator":
            actuators = await actuator_repo.get_by_esp(device.id)
            for actuator in actuators:
                if device_type and actuator.actuator_type != device_type:
                    continue
                state_obj = await actuator_repo.get_state(device.id, actuator.gpio)
                actuator_state = None
                if state_obj:
                    actuator_state = {
                        "current_value": state_obj.current_value,
                        "state": state_obj.state,
                        "last_changed": (
                            state_obj.last_changed.isoformat()
                            if hasattr(state_obj, "last_changed") and state_obj.last_changed
                            else None
                        ),
                    }
                components.append(
                    _serialize_component(
                        esp=device,
                        actuator=actuator,
                        actuator_state=actuator_state,
                    )
                )

    return {
        "@context": "automationone://schemas/export/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(components),
        "components": components,
    }


@router.get("/components/{component_id}")
async def export_component_by_id(
    component_id: str,
    _user: ActiveUser,
    db: DBSession,
) -> dict[str, Any]:
    """
    Export a single component by its composite ID.

    Component ID format: sensor_{type}_{uuid_prefix} or actuator_{type}_{uuid_prefix}
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    # Parse component_id: sensor_sht31_temp_abcd1234 or actuator_relay_abcd1234
    parts = component_id.split("_", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid component ID format",
        )

    comp_type = parts[0]  # "sensor" or "actuator"
    uuid_prefix = component_id.rsplit("_", 1)[-1]  # last 8 chars = UUID prefix

    # Search across all devices
    devices = await esp_repo.get_all()

    for device in devices:
        if comp_type == "sensor":
            sensors = await sensor_repo.get_by_esp(device.id)
            for sensor in sensors:
                if str(sensor.id)[:8] == uuid_prefix:
                    return _serialize_component(esp=device, sensor=sensor)
        elif comp_type == "actuator":
            actuators = await actuator_repo.get_by_esp(device.id)
            for actuator in actuators:
                if str(actuator.id)[:8] == uuid_prefix:
                    state_obj = await actuator_repo.get_state(device.id, actuator.gpio)
                    actuator_state = None
                    if state_obj:
                        actuator_state = {
                            "current_value": state_obj.current_value,
                            "state": state_obj.state,
                        }
                    return _serialize_component(
                        esp=device,
                        actuator=actuator,
                        actuator_state=actuator_state,
                    )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Component '{component_id}' not found",
    )


@router.get("/zones")
async def export_zones(
    _user: ActiveUser,
    db: DBSession,
) -> dict[str, Any]:
    """
    Export all zones with context and component counts.

    Returns zone-level summary without full component details.
    Use /zones/{zone_id} for full component export per zone.
    """
    # Get all devices to discover zones via repo helper (eager-load — AUT-224 A2)
    esp_repo = ESPRepository(db)
    all_devices = await esp_repo.get_all_with_components()

    # Group devices by zone
    zone_map: dict[str, dict[str, Any]] = {}
    for device in all_devices:
        zid = device.zone_id or "__unassigned__"
        if zid not in zone_map:
            zone_map[zid] = {
                "zone_id": device.zone_id,
                "zone_name": device.zone_name,
                "device_count": 0,
                "sensor_count": 0,
                "actuator_count": 0,
                "online_count": 0,
            }
        zone_map[zid]["device_count"] += 1
        zone_map[zid]["sensor_count"] += (
            len(device.sensors) if hasattr(device, "sensors") and device.sensors else 0
        )
        zone_map[zid]["actuator_count"] += (
            len(device.actuators) if hasattr(device, "actuators") and device.actuators else 0
        )
        if device.status == "online":
            zone_map[zid]["online_count"] += 1

    # Load zone contexts
    zone_ctx_repo = ZoneContextRepository(db)
    all_contexts = await zone_ctx_repo.list_all()
    context_map = {ctx.zone_id: ctx for ctx in all_contexts}

    zones: list[dict[str, Any]] = []
    for zid, info in zone_map.items():
        zone_data: dict[str, Any] = {
            "zone_id": info["zone_id"],
            "zone_name": info["zone_name"],
            "device_count": info["device_count"],
            "sensor_count": info["sensor_count"],
            "actuator_count": info["actuator_count"],
            "online_count": info["online_count"],
        }
        ctx = context_map.get(zid)
        if ctx:
            zone_data["context"] = {
                "growth_phase": ctx.growth_phase,
                "variety": ctx.variety,
                "plant_count": ctx.plant_count,
                "plant_age_days": ctx.plant_age_days,
                "days_to_harvest": ctx.days_to_harvest,
            }
        zones.append(zone_data)

    return {
        "@context": "automationone://schemas/export/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_zones": len(zones),
        "zones": zones,
    }


@router.get("/zones/{zone_id}")
async def export_zone_detail(
    zone_id: str,
    _user: ActiveUser,
    db: DBSession,
) -> dict[str, Any]:
    """
    Export a single zone with full context and all components.

    Returns the complete zone export including all sensors, actuators,
    zone context data, and environment summary.
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)
    zone_ctx_repo = ZoneContextRepository(db)

    # Get all devices in zone
    devices = await esp_repo.get_by_zone(zone_id)
    if not devices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No devices found in zone '{zone_id}'",
        )

    # Get zone context
    zone_context = await zone_ctx_repo.get_by_zone_id(zone_id)

    # Build component list
    components: list[dict[str, Any]] = []
    zone_name = devices[0].zone_name if devices else zone_id

    for device in devices:
        # Sensors
        sensors = await sensor_repo.get_by_esp(device.id)
        for sensor in sensors:
            components.append(_serialize_component(esp=device, sensor=sensor))

        # Actuators
        actuators = await actuator_repo.get_by_esp(device.id)
        for actuator in actuators:
            state_obj = await actuator_repo.get_state(device.id, actuator.gpio)
            actuator_state = None
            if state_obj:
                actuator_state = {
                    "current_value": state_obj.current_value,
                    "state": state_obj.state,
                }
            components.append(
                _serialize_component(
                    esp=device,
                    actuator=actuator,
                    actuator_state=actuator_state,
                )
            )

    return _serialize_zone(zone_id, zone_name, zone_context, components)


@router.get("/system-description")
async def export_system_description(
    _user: ActiveUser,
    db: DBSession,
) -> dict[str, Any]:
    """
    Export complete system description as WoT-inspired System Description.

    Provides a high-level overview of the entire AutomationOne system
    with all zones, devices, component counts, and operational status.
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)
    zone_ctx_repo = ZoneContextRepository(db)

    # Get all devices
    all_devices = await esp_repo.get_all()

    # Count statistics
    total_sensors = 0
    total_actuators = 0
    online_devices = 0
    offline_devices = 0

    zone_ids: set[str] = set()

    for device in all_devices:
        if device.zone_id:
            zone_ids.add(device.zone_id)
        if device.status == "online":
            online_devices += 1
        else:
            offline_devices += 1

        # Count sensors/actuators via repository methods
        total_sensors += len(await sensor_repo.get_by_esp(device.id))
        total_actuators += len(await actuator_repo.get_by_esp(device.id))

    # Load zone contexts
    all_contexts = await zone_ctx_repo.list_all()

    zones_with_context = len(all_contexts)
    active_growth_phases = set()
    for ctx in all_contexts:
        if ctx.growth_phase:
            active_growth_phases.add(ctx.growth_phase)

    return {
        "@context": "automationone://schemas/system/v1",
        "system": "AutomationOne",
        "description": "IoT Greenhouse Automation Framework",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "overview": {
            "total_devices": len(all_devices),
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "total_sensors": total_sensors,
            "total_actuators": total_actuators,
            "total_zones": len(zone_ids),
            "zones_with_context": zones_with_context,
        },
        "growth_phases_active": sorted(active_growth_phases),
        "api_endpoints": {
            "components": "/api/v1/export/components",
            "components_filtered": "/api/v1/export/components?type=sensor&zone={zone_id}",
            "zones": "/api/v1/export/zones",
            "zone_detail": "/api/v1/export/zones/{zone_id}",
        },
        "mcp_tool_mapping": {
            "get_all_components": "GET /api/v1/export/components",
            "get_component": "GET /api/v1/export/components/{id}",
            "get_zone_info": "GET /api/v1/export/zones/{zone_id}",
            "get_system_overview": "GET /api/v1/export/system-description",
            "query_components": "GET /api/v1/export/components?type={type}&zone={zone_id}&device_type={device_type}",
        },
    }
