"""
Debug API Router - Mock ESP32 Management & Database Explorer

Provides REST endpoints for creating, configuring, and controlling
mock ESP32 devices for testing and debugging without real hardware.

Also includes Database Explorer endpoints for inspecting database tables.

ARCHITECTURE (Paket B - Database as Single Source of Truth):
- Database is the Single Source of Truth for Mock-ESP configuration
- SimulationScheduler manages runtime state (heartbeats, sensor jobs)
- MockESPManager is DEPRECATED and only kept for backward compatibility

All endpoints require admin authentication.
"""

import json
import math
import re
import uuid
import zipfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.logging_config import get_logger
from ...db.session import get_session
from ...schemas.debug import (
    ActuatorCommandRequest,
    ActuatorCommandResponse,
    BatchSensorValueRequest,
    CommandResponse,
    HeartbeatResponse,
    MockActuatorConfig,
    MockESPCreate,
    MockESPListResponse,
    MockESPMessagesResponse,
    MockESPResponse,
    MockSensorConfig,
    MockSensorResponse,
    MockActuatorResponse,
    SetActuatorStateRequest,
    SetSensorValueRequest,
    StateTransitionRequest,
)
from ...schemas.debug_db import (
    ALLOWED_TABLES,
    MASKED_FIELDS,
    TIME_SERIES_TABLES,
    DEFAULT_TIME_SERIES_LIMIT_HOURS,
    ColumnSchema,
    ColumnType,
    RecordResponse,
    SortOrder,
    TableDataResponse,
    TableListResponse,
    TableSchema,
)
from ...core.exceptions import (
    ESPNotFoundError,
    SimulationNotRunningError,
)
from ...services.audit_retention_service import AuditRetentionService
from ...db.repositories import (
    ActuatorRepository,
    ESPRepository,
    SensorRepository,
    SubzoneRepository,
)
from ...sensors.sensor_type_registry import (
    expand_multi_value,
    get_device_type_from_sensor_type,
    get_i2c_address,
    get_mock_default_raw_value,
    is_multi_value_sensor,
)
from ..deps import (
    AdminUser,
    DBSession,
    MQTTPublisher,
    SimulationSchedulerDep,
    get_simulation_scheduler,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/debug", tags=["Debug"])


# =========================================================================
# Helper Functions for DB-First Mock ESP Management
# =========================================================================


def _build_mock_esp_response(
    device, simulation_active: bool = False, runtime_status: Optional[Dict[str, Any]] = None
) -> MockESPResponse:
    """
    Build MockESPResponse from ESPDevice model.

    Combines database state with optional runtime status from SimulationScheduler.
    """
    sim_config = (
        device.device_metadata.get("simulation_config", {}) if device.device_metadata else {}
    )
    sensors_config = sim_config.get("sensors", {})
    actuators_config = sim_config.get("actuators", {})

    # Build sensor responses
    # Key format: "cfg_{uuid}" (new, from rebuild_simulation_config)
    # or legacy "{gpio}_{sensor_type}" / "{gpio}"
    sensors = []
    for sensor_key, config in sensors_config.items():
        sensor_value = config.get("raw_value", config.get("base_value", 0.0))

        # Extract GPIO from config dict (reliable) or key (legacy fallback)
        if "gpio" in config:
            gpio = int(config["gpio"])
        elif sensor_key.startswith("cfg_"):
            logger.warning(f"cfg_ key '{sensor_key}' missing 'gpio', skipping")
            continue
        elif "_" in sensor_key and not sensor_key.isdigit():
            gpio = int(sensor_key.split("_")[0])
        else:
            gpio = int(sensor_key)

        sensors.append(
            MockSensorResponse(
                gpio=gpio,
                sensor_type=config.get("sensor_type", "GENERIC"),
                name=config.get("name"),
                subzone_id=config.get("subzone_id"),
                raw_value=sensor_value,
                unit=config.get("unit", ""),
                quality=config.get("quality", "good"),
                raw_mode=config.get("raw_mode", True),
                last_read=None,
                i2c_address=config.get("i2c_address"),
                interface_type=config.get("interface_type"),
                device_scope=config.get("device_scope", "zone_local"),
                assigned_zones=config.get("assigned_zones"),
            )
        )

    # Build actuator responses (merge runtime state if simulation active)
    # Runtime state reflects actual current state (e.g., after toggle commands)
    # DB state may be stale if only runtime was updated
    runtime_actuator_states = {}
    runtime_actuator_pwm = {}
    runtime_last_commands = {}
    runtime_emergency = False
    if simulation_active and runtime_status:
        runtime_actuator_states = runtime_status.get("actuator_states", {})
        runtime_actuator_pwm = runtime_status.get("actuator_pwm_values", {})
        runtime_last_commands = runtime_status.get("last_commands", {})
        runtime_emergency = runtime_status.get("emergency_stopped", False)

    actuators = []
    for gpio_str, config in actuators_config.items():
        gpio_int = int(gpio_str)
        # Prefer runtime state over DB state when simulation is active
        act_state = runtime_actuator_states.get(gpio_int, config.get("state", False))
        act_pwm = runtime_actuator_pwm.get(gpio_int, config.get("pwm_value", 0.0))
        act_last_cmd = runtime_last_commands.get(gpio_int)
        actuators.append(
            MockActuatorResponse(
                gpio=gpio_int,
                actuator_type=config.get("actuator_type", "relay"),
                name=config.get("name"),
                state=act_state,
                pwm_value=act_pwm,
                emergency_stopped=runtime_emergency,
                last_command=act_last_cmd,
                device_scope=config.get("device_scope", "zone_local"),
                assigned_zones=config.get("assigned_zones"),
            )
        )

    # Get uptime from runtime if available
    uptime = 0
    if runtime_status:
        uptime = int(runtime_status.get("uptime_seconds", 0))

    # Get auto_heartbeat from DB config (fallback to simulation_active for backwards compatibility)
    auto_heartbeat_config = sim_config.get("auto_heartbeat", simulation_active)

    return MockESPResponse(
        esp_id=device.device_id,
        name=device.name,  # Human-readable name from DB
        zone_id=device.zone_id,
        zone_name=device.zone_name,
        master_zone_id=device.master_zone_id,
        subzone_id=None,
        system_state="OPERATIONAL" if simulation_active else "OFFLINE",
        sensors=sensors,
        actuators=actuators,
        auto_heartbeat=auto_heartbeat_config,
        heap_free=45000 if simulation_active else 0,
        wifi_rssi=-50 if simulation_active else -100,
        uptime=uptime,
        last_heartbeat=datetime.now(timezone.utc) if simulation_active else None,
        created_at=device.created_at or datetime.now(timezone.utc),
        connected=simulation_active,
        hardware_type="MOCK_ESP32",
        status="online" if simulation_active else "offline",
    )


# DEPRECATED: MockESPManager dependency removed (Paket X)
# Use SimulationScheduler from deps.py instead


# =============================================================================
# Mock ESP CRUD (DB-First Architecture)
# =============================================================================
@router.post(
    "/mock-esp",
    response_model=MockESPResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Mock ESP32",
    description="Create a new mock ESP32 device for testing. Requires admin role.",
)
async def create_mock_esp(
    config: MockESPCreate,
    current_user: AdminUser,
    db: DBSession,
) -> MockESPResponse:
    """
    Create a new mock ESP32 instance.

    DB-FIRST ARCHITECTURE:
    1. Create device in database (Single Source of Truth)
    2. Start simulation via SimulationScheduler if auto_heartbeat=True

    The mock ESP will simulate real ESP32 behavior including:
    - MQTT message publishing (via SimulationScheduler)
    - Sensor readings
    - Actuator control
    """
    esp_repo = ESPRepository(db)

    try:
        # Build initial simulation_config with actuators only.
        # Sensors are populated via rebuild_simulation_config() after
        # SensorConfig DB entries are created (Write-Through Cache pattern).
        simulation_config = {
            "sensors": {},
            "actuators": {
                str(actuator.gpio): {
                    "actuator_type": actuator.actuator_type,
                    "name": actuator.name,
                    "state": actuator.state,
                    "pwm_value": actuator.pwm_value,
                }
                for actuator in config.actuators
            },
            "heartbeat_interval": config.heartbeat_interval_seconds,
            "auto_heartbeat": config.auto_heartbeat,
        }

        # 1. Create device in database (Single Source of Truth)
        device = await esp_repo.create_mock_device(
            device_id=config.esp_id,
            kaiser_id="god",
            zone_id=config.zone_id,
            zone_name=config.zone_name,
            master_zone_id=config.master_zone_id,
            heartbeat_interval=float(config.heartbeat_interval_seconds),
            simulation_config=simulation_config,
            auto_start=config.auto_heartbeat,
        )

        # Update metadata with creator info
        if device.device_metadata:
            device.device_metadata["created_by"] = current_user.username
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(device, "device_metadata")

        await db.commit()
        await db.refresh(device)

        # 1.5 Create SensorConfig entries with multi-value split (Fix A+B+C)
        # MULTI-VALUE SPLIT: expand_multi_value() splits base types (e.g., "sht31")
        # into sub-types (e.g., "sht31_temp" + "sht31_humidity").
        sensor_repo = SensorRepository(db)
        expanded_sensor_configs: list = []
        for sensor in config.sensors:
            if is_multi_value_sensor(sensor.sensor_type):
                sub_types = expand_multi_value(
                    sensor.sensor_type,
                    sensor.name or "",
                    gpio=sensor.gpio,
                )
                for sub in sub_types:
                    expanded_sensor_configs.append((sub["gpio"], sub["sensor_type"], sensor, True))
                logger.info(
                    f"Multi-value sensor '{sensor.sensor_type}' on GPIO {sensor.gpio}: "
                    f"split into {[s['sensor_type'] for s in sub_types]}"
                )
            else:
                expanded_sensor_configs.append((sensor.gpio, sensor.sensor_type, sensor, False))

        for gpio, sensor_type, orig_sensor, is_multi_value in expanded_sensor_configs:
            # Per-subtype default for multi-value sensors (e.g., temp=22, humidity=55)
            raw_for_default = None if is_multi_value else orig_sensor.raw_value
            resolved_raw = get_mock_default_raw_value(sensor_type, raw_for_default)
            # Resolve i2c_address + interface_type from registry (V19-F13)
            device_type = get_device_type_from_sensor_type(sensor_type)
            resolved_i2c = get_i2c_address(device_type) if device_type else None
            resolved_iface = "I2C" if resolved_i2c is not None else "ANALOG"
            try:
                await sensor_repo.create_if_not_exists(
                    esp_id=device.id,
                    gpio=gpio,
                    sensor_type=sensor_type,
                    sensor_name=orig_sensor.name or f"{sensor_type}_{gpio}",
                    enabled=True,
                    pi_enhanced=False,
                    sample_interval_ms=30000,
                    interface_type=resolved_iface,
                    i2c_address=resolved_i2c,
                    sensor_metadata={
                        "source": "mock_esp",
                        "unit": orig_sensor.unit,
                        "subzone_id": orig_sensor.subzone_id,
                        "simulation": {
                            "base_value": resolved_raw,
                            "raw_mode": orig_sensor.raw_mode,
                            "quality": orig_sensor.quality,
                        },
                    },
                )
                logger.debug(
                    f"Created SensorConfig for {config.esp_id} GPIO {gpio} type {sensor_type}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create SensorConfig for GPIO {gpio} type {sensor_type}: {e}"
                )

        # 1.6 Rebuild simulation_config from DB (Write-Through Cache)
        all_sensor_cfgs = await sensor_repo.get_by_esp(device.id)
        await esp_repo.rebuild_simulation_config(device, all_sensor_cfgs)
        await db.commit()

        # 2. Start simulation if auto_heartbeat is True
        simulation_started = False
        if config.auto_heartbeat:
            try:
                sim_scheduler = get_simulation_scheduler()
                simulation_started = await sim_scheduler.start_mock(
                    esp_id=config.esp_id,
                    kaiser_id="god",
                    zone_id=config.zone_id or "",
                    heartbeat_interval=float(config.heartbeat_interval_seconds),
                )

                if simulation_started:
                    # Update status to online
                    device.status = "online"
                    await db.commit()
                    logger.info(f"Simulation started for {config.esp_id}")
            except RuntimeError as e:
                logger.warning(f"SimulationScheduler not available: {e}")

        logger.info(f"Admin {current_user.username} created mock ESP: {config.esp_id}")

        # WebSocket Broadcast: Notify Frontend about new Mock-ESP
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "device_discovered",
                {
                    "esp_id": config.esp_id,
                    "device_id": config.esp_id,
                    "status": device.status,
                    "zone_id": config.zone_id,
                    "zone_name": config.zone_name,
                    "hardware_type": "MOCK_ESP32",
                    "simulation_active": simulation_started,
                    "created_by": current_user.username,
                    "sensor_count": len(config.sensors),
                    "actuator_count": len(config.actuators),
                },
            )
            logger.info(f"📡 WebSocket broadcast: device_discovered for {config.esp_id}")
        except Exception as ws_error:
            logger.warning(f"Failed to broadcast device_discovered: {ws_error}")

        # Build response
        return _build_mock_esp_response(device, simulation_active=simulation_started)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create mock ESP: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create mock ESP: {str(e)}",
        )


@router.get(
    "/mock-esp",
    response_model=MockESPListResponse,
    summary="List Mock ESPs",
    description="Get all mock ESP32 devices from database.",
)
async def list_mock_esps(
    current_user: AdminUser,
    db: DBSession,
) -> MockESPListResponse:
    """
    List all mock ESP32 instances from database.

    DB-FIRST: Loads all Mock-ESPs from database and combines with
    runtime status from SimulationScheduler.
    """
    esp_repo = ESPRepository(db)

    # Load all mocks from database
    devices = await esp_repo.get_all_mock_devices()

    # Get active simulation IDs
    active_ids: List[str] = []
    try:
        sim_scheduler = get_simulation_scheduler()
        active_ids = sim_scheduler.get_active_mocks()
    except RuntimeError:
        pass  # Scheduler not initialized

    # Build responses
    responses = []
    for device in devices:
        is_active = device.device_id in active_ids
        runtime_status = None

        if is_active:
            try:
                sim_scheduler = get_simulation_scheduler()
                runtime_status = sim_scheduler.get_mock_status(device.device_id)
            except RuntimeError:
                pass

        responses.append(_build_mock_esp_response(device, is_active, runtime_status))

    return MockESPListResponse(success=True, data=responses, total=len(responses))


@router.get(
    "/mock-esp/{esp_id}",
    response_model=MockESPResponse,
    summary="Get Mock ESP",
    description="Get details of a specific mock ESP32 device from database.",
)
async def get_mock_esp(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> MockESPResponse:
    """
    Get mock ESP32 details by ID from database.

    DB-FIRST: Loads Mock-ESP configuration from database and combines
    with runtime status from SimulationScheduler.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # Get runtime status
    is_active = False
    runtime_status = None
    try:
        sim_scheduler = get_simulation_scheduler()
        is_active = sim_scheduler.is_mock_active(esp_id)
        if is_active:
            runtime_status = sim_scheduler.get_mock_status(esp_id)
    except RuntimeError:
        pass

    return _build_mock_esp_response(device, is_active, runtime_status)


@router.delete(
    "/mock-esp/{esp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete Mock ESP",
    description="Soft-delete a mock ESP32 device. Sensor data and historical records are preserved.",
)
async def delete_mock_esp(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
):
    """
    Soft-delete a mock ESP32 instance (T02-Fix1).

    DB-FIRST FLOW:
    1. Stop simulation if running
    2. Soft-delete from database (sets deleted_at)
    """
    esp_repo = ESPRepository(db)

    # Check if mock exists in DB
    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        # Debug-logging to diagnose Delete-404 (NB-T09-04)
        any_device = await esp_repo.get_by_device_id(esp_id, include_deleted=True)
        if any_device and any_device.deleted_at is not None:
            logger.warning(
                "DELETE mock %s: device already soft-deleted at %s by %s",
                esp_id,
                any_device.deleted_at,
                any_device.deleted_by,
            )
        elif any_device and any_device.hardware_type != "MOCK_ESP32":
            logger.warning(
                "DELETE mock %s: device exists but hardware_type=%s (not MOCK_ESP32)",
                esp_id,
                any_device.hardware_type,
            )
        else:
            logger.warning("DELETE mock %s: device not found in DB at all", esp_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # 1. Stop simulation if running
    try:
        sim_scheduler = get_simulation_scheduler()
        if sim_scheduler.is_mock_active(esp_id):
            await sim_scheduler.stop_mock(esp_id)
            logger.info(f"Stopped simulation for {esp_id}")
    except RuntimeError:
        pass  # Scheduler not initialized

    # 2. Soft-delete from database (also cleans up sensor_configs + actuator_configs)
    logger.debug(f"Soft-deleting mock ESP {esp_id} (device.id={device.id})")
    deleted = await esp_repo.delete_mock_device(esp_id, deleted_by=current_user.username)
    if deleted:
        await db.commit()
        logger.info(f"Admin {current_user.username} soft-deleted mock ESP: {esp_id}")


# =============================================================================
# Simulation Control (NEW - DB-First)
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/simulation/start",
    response_model=CommandResponse,
    summary="Start Mock Simulation",
    description="Start simulation for an existing mock ESP32 from database.",
)
async def start_mock_simulation(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Start simulation for an existing mock ESP.

    Loads configuration from database and starts heartbeat job.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    try:
        sim_scheduler = get_simulation_scheduler()

        if sim_scheduler.is_mock_active(esp_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Simulation for {esp_id} already running",
            )

        # Get heartbeat interval from metadata
        heartbeat_interval = esp_repo.get_heartbeat_interval(device)

        success = await sim_scheduler.start_mock(
            esp_id=esp_id,
            kaiser_id=device.kaiser_id or "god",
            zone_id=device.zone_id or "",
            heartbeat_interval=heartbeat_interval,
        )

        if success:
            # Update simulation state in DB
            await esp_repo.update_simulation_state(esp_id, "running")
            device.status = "online"
            await db.commit()

        return CommandResponse(
            success=success,
            esp_id=esp_id,
            command="start_simulation",
            result={"started": success, "heartbeat_interval": heartbeat_interval},
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SimulationScheduler not available: {e}",
        )


@router.post(
    "/mock-esp/{esp_id}/simulation/stop",
    response_model=CommandResponse,
    summary="Stop Mock Simulation",
    description="Stop simulation for a mock ESP32.",
)
async def stop_mock_simulation(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Stop simulation for a mock ESP.

    Stops heartbeat job and updates database state.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    try:
        sim_scheduler = get_simulation_scheduler()

        if not sim_scheduler.is_mock_active(esp_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Simulation for {esp_id} not running",
            )

        success = await sim_scheduler.stop_mock(esp_id)

        if success:
            # Update simulation state in DB
            await esp_repo.update_simulation_state(esp_id, "stopped")
            device.status = "offline"
            await db.commit()

        return CommandResponse(
            success=success, esp_id=esp_id, command="stop_simulation", result={"stopped": success}
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SimulationScheduler not available: {e}",
        )


# =============================================================================
# Heartbeat & State
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/heartbeat",
    response_model=HeartbeatResponse,
    summary="Trigger Heartbeat",
    description="Manually trigger a heartbeat from a mock ESP32.",
)
async def trigger_heartbeat(
    esp_id: str,
    current_user: AdminUser,
    scheduler: SimulationSchedulerDep,
    db: DBSession,
) -> HeartbeatResponse:
    """
    Trigger a heartbeat message from the mock ESP.

    Paket X: Uses SimulationScheduler instead of MockESPManager.

    Bug Fix (2025-12-30): If mock exists in DB but simulation is not active
    (e.g., after server restart), automatically start the simulation first.
    """
    # Check if mock is active
    if not scheduler.is_mock_active(esp_id):
        logger.debug(f"[HEARTBEAT] Simulation not active for {esp_id}, checking DB...")

        # Check if mock exists in database
        esp_repo = ESPRepository(db)
        device = await esp_repo.get_mock_device(esp_id)

        if device is None:
            logger.debug(f"[HEARTBEAT] Mock {esp_id} not found in DB")
            raise ESPNotFoundError(esp_id)

        # Mock exists in DB but simulation not running - auto-start it
        logger.info(f"[HEARTBEAT] Auto-starting simulation for {esp_id} (found in DB)")

        # Get config from device metadata
        heartbeat_interval = esp_repo.get_heartbeat_interval(device)

        # Start simulation
        success = await scheduler.start_mock(
            esp_id=esp_id,
            kaiser_id=device.kaiser_id or "god",
            zone_id=device.zone_id or "",
            heartbeat_interval=heartbeat_interval,
        )

        if success:
            # Update simulation_state in DB to 'running'
            await esp_repo.update_simulation_state(esp_id, "running")
            device.status = "online"
            await db.commit()
            logger.info(f"[HEARTBEAT] Simulation auto-started for {esp_id}")
        else:
            logger.error(f"[HEARTBEAT] Failed to auto-start simulation for {esp_id}")
            raise SimulationNotRunningError(esp_id)

    # Trigger heartbeat
    result = await scheduler.trigger_heartbeat(esp_id)
    if result is None:
        raise ESPNotFoundError(esp_id)

    return HeartbeatResponse(
        success=True,
        esp_id=esp_id,
        timestamp=datetime.now(timezone.utc),
        message_published=True,
        payload=result,
    )


@router.post(
    "/mock-esp/{esp_id}/state",
    response_model=CommandResponse,
    summary="Set System State",
    description="Transition mock ESP32 to a specific system state.",
)
async def set_state(
    esp_id: str,
    request: StateTransitionRequest,
    current_user: AdminUser,
    scheduler: SimulationSchedulerDep,
) -> CommandResponse:
    """
    Set the system state of a mock ESP.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    result = await scheduler.set_state(esp_id, request.state, request.reason)
    if result is None:
        raise SimulationNotRunningError(esp_id)

    return CommandResponse(success=True, esp_id=esp_id, command="set_state", result=result)


@router.post(
    "/mock-esp/{esp_id}/auto-heartbeat",
    response_model=CommandResponse,
    summary="Configure Auto-Heartbeat",
    description="Enable or disable automatic heartbeat for a mock ESP32.",
)
async def configure_auto_heartbeat(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
    enabled: bool = Query(True),
    interval_seconds: int = Query(60),
) -> CommandResponse:
    """
    Configure auto-heartbeat for a mock ESP.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    try:
        success = await scheduler.set_auto_heartbeat(
            esp_id=esp_id,
            enabled=enabled,
            interval_seconds=float(interval_seconds),
            session=db,
        )
        await db.commit()

        return CommandResponse(
            success=success,
            esp_id=esp_id,
            command="auto_heartbeat",
            result={"enabled": enabled, "interval_seconds": interval_seconds},
        )
    except ESPNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )


# =============================================================================
# Sensor Operations (DB-First)
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/sensors",
    response_model=CommandResponse,
    summary="Add Sensor",
    description="Add a new sensor to a mock ESP32.",
)
async def add_sensor(
    esp_id: str,
    config: MockSensorConfig,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Add a sensor to a mock ESP.

    DB-FIRST: Updates database configuration.
    If simulation is running, sensor job is started immediately.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # =========================================================================
    # SENSOR CONFIG STORAGE - Dual-Key System for Consistency
    # =========================================================================
    # We store the user-entered value under TWO keys:
    #
    #   "raw_value"  - Used by _build_mock_esp_response() for Frontend display
    #   "base_value" - Used by SimulationScheduler._calculate_sensor_value()
    #
    # IMPORTANT: For Mock ESPs, the user enters human-readable values (e.g., 20°C),
    # NOT hardware ADC values. This differs from real ESP32s where:
    #   - DS18B20/SHT31: Already output Celsius (raw_value = celsius)
    #   - pH/EC sensors: Output ADC 0-4095 (raw_value = adc, server converts)
    #
    # Mock ESPs bypass the ADC layer entirely - the value the user enters
    # is the value that gets displayed and processed.
    # =========================================================================

    # Infer interface_type if not provided
    interface_type = config.interface_type
    if not interface_type:
        sensor_lower = config.sensor_type.lower()
        if "ds18b20" in sensor_lower:
            interface_type = "ONEWIRE"
        elif any(s in sensor_lower for s in ["sht31", "bmp280", "bme280", "bh1750"]):
            interface_type = "I2C"
        else:
            interface_type = "ANALOG"

    # Simulation-specific params stored in sensor_metadata.simulation.
    # Built per sensor_type so each sub-type gets its own plausible default.
    interval_seconds = getattr(config, "interval_seconds", 30.0)
    variation_pattern = getattr(config, "variation_pattern", "constant")
    variation_range = getattr(config, "variation_range", 0.0)

    def _build_sim_params(resolved_raw: float) -> dict:
        return {
            "base_value": resolved_raw,
            "raw_mode": config.raw_mode,
            "quality": config.quality,
            "interval_seconds": interval_seconds,
            "variation_pattern": variation_pattern,
            "variation_range": variation_range,
            "min_value": config.min_value if config.min_value is not None else resolved_raw - 10.0,
            "max_value": config.max_value if config.max_value is not None else resolved_raw + 10.0,
        }

    # 1. Create SensorConfig entries in DB (Fix C: multi-value split)
    sensor_repo = SensorRepository(db)
    created_types: list = []

    if is_multi_value_sensor(config.sensor_type):
        # MULTI-VALUE SPLIT: e.g., "sht31" → "sht31_temp" + "sht31_humidity"
        sub_types = expand_multi_value(
            config.sensor_type,
            config.name or "",
            gpio=config.gpio,
        )
        for sub in sub_types:
            sensor_type = sub["sensor_type"]
            # Per-subtype default: pass None so each sub-type gets its own
            # plausible default from SENSOR_TYPE_MOCK_DEFAULTS (e.g., temp=22, humidity=55)
            resolved_raw = get_mock_default_raw_value(sensor_type, None)
            sim_params = _build_sim_params(resolved_raw)
            # I2C-aware duplicate check: allows same sensor_type at different addresses
            # Resolve from registry if user didn't provide (V19-F13)
            i2c_addr = getattr(config, "i2c_address", None)
            if i2c_addr is None:
                sub_device_type = get_device_type_from_sensor_type(sensor_type)
                if sub_device_type:
                    i2c_addr = get_i2c_address(sub_device_type)
            if i2c_addr is not None:
                existing = await sensor_repo.get_by_esp_gpio_type_and_i2c(
                    device.id, config.gpio, sensor_type, i2c_addr
                )
            else:
                existing = await sensor_repo.get_by_esp_gpio_and_type(
                    device.id, config.gpio, sensor_type
                )
            if existing:
                logger.debug(
                    f"SensorConfig already exists: {esp_id} GPIO {config.gpio} {sensor_type}"
                )
                created_types.append(sensor_type)
                continue
            try:
                await sensor_repo.create(
                    esp_id=device.id,
                    gpio=config.gpio,
                    sensor_type=sensor_type,
                    sensor_name=sub.get("name", f"{sensor_type}_{config.gpio}"),
                    enabled=True,
                    pi_enhanced=False,
                    sample_interval_ms=int(interval_seconds * 1000),
                    interface_type=interface_type,
                    i2c_address=i2c_addr,
                    sensor_metadata={
                        "source": "mock_esp",
                        "unit": sub.get("unit", config.unit),
                        "subzone_id": config.subzone_id,
                        "simulation": sim_params,
                    },
                )
                created_types.append(sensor_type)
                logger.debug(f"Created SensorConfig: {esp_id} GPIO {config.gpio} {sensor_type}")
            except Exception as e:
                await db.rollback()
                logger.warning(f"Failed to create SensorConfig {sensor_type}: {e}")
        logger.info(
            f"Multi-value sensor '{config.sensor_type}' on GPIO {config.gpio}: "
            f"split into {created_types}"
        )
    else:
        # Single-value sensor
        resolved_raw = get_mock_default_raw_value(config.sensor_type, config.raw_value)
        sim_params = _build_sim_params(resolved_raw)
        # I2C-aware duplicate check for single-value sensors
        i2c_addr = getattr(config, "i2c_address", None)
        if i2c_addr is not None:
            existing = await sensor_repo.get_by_esp_gpio_type_and_i2c(
                device.id, config.gpio, config.sensor_type, i2c_addr
            )
        else:
            existing = await sensor_repo.get_by_esp_gpio_and_type(
                device.id, config.gpio, config.sensor_type
            )
        if existing:
            logger.debug(
                f"SensorConfig already exists: {esp_id} GPIO {config.gpio} {config.sensor_type}"
            )
        else:
            try:
                await sensor_repo.create(
                    esp_id=device.id,
                    gpio=config.gpio,
                    sensor_type=config.sensor_type,
                    sensor_name=config.name or f"{config.sensor_type}_{config.gpio}",
                    enabled=True,
                    pi_enhanced=False,
                    sample_interval_ms=int(interval_seconds * 1000),
                    interface_type=interface_type,
                    onewire_address=getattr(config, "onewire_address", None),
                    i2c_address=getattr(config, "i2c_address", None),
                    sensor_metadata={
                        "source": "mock_esp",
                        "unit": config.unit,
                        "subzone_id": config.subzone_id,
                        "simulation": sim_params,
                    },
                )
                logger.debug(
                    f"Created SensorConfig: {esp_id} GPIO {config.gpio} {config.sensor_type}"
                )
            except Exception as e:
                await db.rollback()
                logger.warning(f"Failed to create SensorConfig: {e}")
        created_types.append(config.sensor_type)

    # 2. Rebuild simulation_config from DB (Write-Through Cache — Fix A+B)
    all_sensor_cfgs = await sensor_repo.get_by_esp(device.id)
    await esp_repo.rebuild_simulation_config(device, all_sensor_cfgs)
    await db.commit()
    success = True

    # T13-R1: Sync subzone sensor/actuator counts after sensor create
    try:
        _subzone_repo = SubzoneRepository(db)
        if await _subzone_repo.sync_subzone_counts(esp_id, device.id):
            await db.commit()
    except Exception:
        logger.debug("Subzone count sync skipped for %s", esp_id)

    # 3. If simulation is running: Start sensor job for each created type
    jobs_started = 0
    initial_published_count = 0
    try:
        sim_scheduler = get_simulation_scheduler()
        if sim_scheduler.is_mock_active(esp_id):
            for st in created_types:
                started = sim_scheduler.add_sensor_job(
                    esp_id=esp_id,
                    gpio=config.gpio,
                    interval_seconds=sim_params["interval_seconds"],
                    sensor_type=st,
                )
                if started:
                    jobs_started += 1
                    published = await sim_scheduler.trigger_immediate_sensor_publish(
                        esp_id=esp_id,
                        gpio=config.gpio,
                        sensor_type=st,
                    )
                    if published:
                        initial_published_count += 1
            if jobs_started:
                logger.info(
                    f"Started {jobs_started} sensor job(s) for {esp_id} GPIO {config.gpio} "
                    f"types {created_types}"
                )
    except RuntimeError:
        pass  # Scheduler not initialized

    return CommandResponse(
        success=success,
        esp_id=esp_id,
        command="add_sensor",
        result={
            "gpio": config.gpio,
            "sensor_type": config.sensor_type,
            "created_types": created_types,
            "db_updated": success,
            "jobs_started": jobs_started,
            "initial_published": initial_published_count,
        },
    )


# =============================================================================
# Mock-ESP OneWire Scan (DS18B20 Discovery)
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/onewire/scan",
    response_model=CommandResponse,
    summary="Mock OneWire Bus Scan",
    description="""
    Simulates a OneWire bus scan on a mock ESP.
    
    **Returns fake DS18B20 devices** for testing the Frontend integration.
    
    Use this to test the OneWire scan UI workflow without real hardware.
    """,
    responses={
        200: {"description": "Scan completed (returns fake devices)"},
        404: {"description": "Mock ESP not found"},
    },
)
async def mock_onewire_scan(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
    pin: int = Query(
        4, ge=0, le=48, description="GPIO pin for OneWire bus (ignored, returns fake data)"
    ),
) -> CommandResponse:
    """
    Simulate OneWire bus scan for mock ESP.

    Returns 2 fake DS18B20 devices for testing:
    - Device 1: ROM 28FF641E8D3C0C79
    - Device 2: ROM 28FF123456789ABC

    **Note:** Real ESP scans are handled by `/api/v1/sensors/esp/{esp_id}/onewire/scan`
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # Generate fake OneWire devices for testing
    # Real ROM codes start with family code 0x28 (DS18B20)
    fake_devices = [
        {"rom_code": "28FF641E8D3C0C79", "device_type": "ds18b20", "pin": pin},
        {"rom_code": "28FF123456789ABC", "device_type": "ds18b20", "pin": pin},
    ]

    logger.info(
        f"Mock OneWire scan on {esp_id} GPIO {pin}: returning {len(fake_devices)} fake devices"
    )

    return CommandResponse(
        success=True,
        esp_id=esp_id,
        command="onewire_scan",
        result={
            "devices": fake_devices,
            "found_count": len(fake_devices),
            "pin": pin,
            "message": f"Mock scan: {len(fake_devices)} fake DS18B20 devices (for testing)",
        },
    )


@router.delete(
    "/mock-esp/{esp_id}/sensors/{gpio}",
    response_model=CommandResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove Sensor",
    description="Remove a sensor from a mock ESP32. MULTI-VALUE: Optionally specify sensor_type to remove only that type.",
)
async def remove_sensor(
    esp_id: str,
    gpio: int,
    current_user: AdminUser,
    db: DBSession,
    sensor_type: Optional[str] = Query(
        None,
        description="Optional sensor type to remove (e.g., 'sht31_temp'). If not specified, removes ALL sensors on this GPIO.",
    ),
) -> CommandResponse:
    """
    Remove a sensor from a mock ESP.

    DB-FIRST: Updates database configuration.
    If simulation is running, sensor job is stopped immediately.

    MULTI-VALUE SUPPORT: If sensor_type is provided, removes only that specific
    sensor type on the GPIO. If not provided, removes ALL sensors on that GPIO.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # 1. Stop sensor job if simulation is running
    # MULTI-VALUE: Pass sensor_type for targeted removal
    job_stopped = False
    try:
        sim_scheduler = get_simulation_scheduler()
        if sim_scheduler.is_mock_active(esp_id):
            job_stopped = sim_scheduler.remove_sensor_job(esp_id, gpio, sensor_type)
            if job_stopped:
                logger.info(
                    f"Stopped sensor job for {esp_id} GPIO {gpio} type {sensor_type or 'ALL'}"
                )
    except RuntimeError:
        pass  # Scheduler not initialized

    # 2. Delete SensorConfig from DB (Single Source of Truth — Fix A+B)
    sensor_repo = SensorRepository(db)
    deleted_count = 0
    if sensor_type:
        # Delete specific sensor_type on this GPIO
        cfg = await sensor_repo.get_by_esp_gpio_and_type(device.id, gpio, sensor_type)
        if cfg:
            await sensor_repo.delete(cfg.id)
            deleted_count = 1
    else:
        # Guard: Refuse mass-delete when multiple sensors share a GPIO (e.g. I2C bus on GPIO 0)
        # Use DELETE /sensors/{esp_id}/{config_id} for targeted removal instead.
        all_on_gpio = await sensor_repo.get_all_by_esp_and_gpio(device.id, gpio)
        if len(all_on_gpio) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{len(all_on_gpio)} sensors on GPIO {gpio}. "
                    f"Specify sensor_type query param or use DELETE /sensors/{{esp_id}}/{{config_id}}."
                ),
            )
        for cfg in all_on_gpio:
            await sensor_repo.delete(cfg.id)
            deleted_count += 1

    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sensor GPIO {gpio} (type={sensor_type or 'any'}) not found on {esp_id}",
        )

    # 3. Rebuild simulation_config from DB (Write-Through Cache — Fix A+B)
    all_sensor_cfgs = await sensor_repo.get_by_esp(device.id)
    await esp_repo.rebuild_simulation_config(device, all_sensor_cfgs)
    await db.commit()

    # T13-R1: Sync subzone sensor/actuator counts after sensor delete
    try:
        _subzone_repo = SubzoneRepository(db)
        if await _subzone_repo.sync_subzone_counts(esp_id, device.id):
            await db.commit()
    except Exception:
        logger.debug("Subzone count sync skipped for %s", esp_id)

    return CommandResponse(
        success=True,
        esp_id=esp_id,
        command="remove_sensor",
        result={
            "gpio": gpio,
            "sensor_type": sensor_type,
            "db_updated": True,
            "deleted_count": deleted_count,
            "job_stopped": job_stopped,
        },
    )


@router.post(
    "/mock-esp/{esp_id}/sensors/{gpio}/value",
    response_model=CommandResponse,
    summary="Set Manual Sensor Override",
    description="Set manual override value for a sensor (DB-First). Overrides variation pattern until cleared.",
)
async def set_manual_sensor_override(
    esp_id: str,
    gpio: int,
    request: SetSensorValueRequest,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Set manual override for a sensor value.

    DB-FIRST: Updates simulation_config.manual_overrides in database.
    The sensor will send this constant value until override is cleared.
    """
    esp_repo = ESPRepository(db)

    # Check if sensor exists
    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    sim_config = esp_repo.get_simulation_config(device)
    sensors = sim_config.get("sensors", {})
    # MULTI-VALUE FIX: Keys are "{gpio}_{sensor_type}" (e.g., "0_SHT31"),
    # not just str(gpio). Check for both formats for backward compat.
    sensor_exists = any(k == str(gpio) or k.startswith(f"{gpio}_") for k in sensors)
    if not sensor_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sensor GPIO {gpio} not found on {esp_id}",
        )

    # Set manual override
    success = await esp_repo.set_manual_sensor_override(esp_id, gpio, request.raw_value)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to set manual override"
        )

    await db.commit()

    logger.info(
        f"Admin {current_user.username} set manual override for {esp_id} GPIO {gpio}: {request.raw_value}"
    )

    return CommandResponse(
        success=True,
        esp_id=esp_id,
        command="set_manual_sensor_override",
        result={"gpio": gpio, "override_value": request.raw_value, "db_updated": True},
    )


@router.delete(
    "/mock-esp/{esp_id}/sensors/{gpio}/value",
    response_model=CommandResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear Manual Sensor Override",
    description="Clear manual override value for a sensor (DB-First). Sensor returns to pattern-based simulation.",
)
async def clear_manual_sensor_override(
    esp_id: str,
    gpio: int,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Clear manual override for a sensor value.

    DB-FIRST: Removes from simulation_config.manual_overrides in database.
    The sensor will resume pattern-based value calculation.
    """
    esp_repo = ESPRepository(db)

    # Check if sensor exists
    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # Clear manual override
    success = await esp_repo.clear_manual_sensor_override(esp_id, gpio)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No manual override found for GPIO {gpio} on {esp_id}",
        )

    await db.commit()

    logger.info(f"Admin {current_user.username} cleared manual override for {esp_id} GPIO {gpio}")

    return CommandResponse(
        success=True,
        esp_id=esp_id,
        command="clear_manual_sensor_override",
        result={"gpio": gpio, "override_cleared": True},
    )


@router.post(
    "/mock-esp/{esp_id}/sensors/batch",
    response_model=CommandResponse,
    summary="Set Batch Sensor Values",
    description="Set multiple sensor values at once.",
)
async def set_batch_sensor_values(
    esp_id: str,
    request: BatchSensorValueRequest,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
) -> CommandResponse:
    """
    Set multiple sensor values and optionally publish batch message.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    try:
        result = await scheduler.set_batch_sensor_values(
            esp_id=esp_id, values=request.values, session=db, publish=request.publish
        )
        await db.commit()

        return CommandResponse(
            success=True, esp_id=esp_id, command="set_batch_sensor_values", result=result
        )
    except SimulationNotRunningError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mock ESP {esp_id} not found or simulation not running",
        )


# =============================================================================
# Actuator Operations (DB-First)
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/actuators",
    response_model=CommandResponse,
    summary="Add Actuator",
    description="Add a new actuator to a mock ESP32.",
)
async def add_actuator(
    esp_id: str,
    config: MockActuatorConfig,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Add an actuator to a mock ESP.

    DB-FIRST: Updates database configuration.
    If simulation is running, also registers actuator in runtime.
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_mock_device(esp_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    actuator_config = {
        "actuator_type": config.actuator_type,
        "name": config.name,
        "subzone_id": config.subzone_id,
        "state": config.state,
        "pwm_value": config.pwm_value,
        "min_value": config.min_value,
        "max_value": config.max_value,
    }

    # 1. Update simulation_config in device_metadata (for SimulationScheduler)
    success = await esp_repo.add_actuator_to_mock(esp_id, config.gpio, actuator_config)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add actuator to database"
        )

    # 2. Create ActuatorConfig record (so standard APIs and Logic Engine can find it)
    actuator_repo = ActuatorRepository(db)
    existing = await actuator_repo.get_by_esp_and_gpio(device.id, config.gpio)
    if existing:
        logger.debug(
            f"ActuatorConfig already exists for {esp_id} GPIO {config.gpio}, skipping creation"
        )
    else:
        try:
            await actuator_repo.create(
                esp_id=device.id,
                gpio=config.gpio,
                actuator_type=config.actuator_type,
                actuator_name=config.name or f"{config.actuator_type}_{config.gpio}",
                enabled=True,
                min_value=config.min_value,
                max_value=config.max_value,
                default_value=0.0,
                timeout_seconds=3600,
                safety_constraints={
                    "max_runtime_seconds": 3600,
                    "cooldown_seconds": 60,
                },
                actuator_metadata={
                    "source": "mock_esp",
                    "subzone_id": config.subzone_id,
                },
            )
            logger.debug(f"Created ActuatorConfig for {esp_id} GPIO {config.gpio}")
        except Exception as e:
            await db.rollback()
            await esp_repo.add_actuator_to_mock(esp_id, config.gpio, actuator_config)
            logger.warning(
                f"Failed to create ActuatorConfig for GPIO {config.gpio} (race condition): {e}"
            )

    await db.commit()

    # T13-R1: Sync subzone sensor/actuator counts after actuator create
    try:
        _subzone_repo = SubzoneRepository(db)
        if await _subzone_repo.sync_subzone_counts(esp_id, device.id):
            await db.commit()
    except Exception:
        logger.debug("Subzone count sync skipped for %s", esp_id)

    # Sync with running simulation runtime (if active)
    runtime_synced = False
    try:
        sim_scheduler = get_simulation_scheduler()
        if sim_scheduler.is_mock_active(esp_id):
            runtime = sim_scheduler.get_runtime(esp_id)
            if runtime:
                runtime.actuator_states[config.gpio] = config.state or False
                runtime.actuator_pwm_values[config.gpio] = config.pwm_value or 0
                runtime_synced = True
                logger.info(f"Synced new actuator GPIO {config.gpio} to runtime for {esp_id}")
    except RuntimeError:
        pass  # Scheduler not initialized

    return CommandResponse(
        success=success,
        esp_id=esp_id,
        command="add_actuator",
        result={
            "gpio": config.gpio,
            "actuator_type": config.actuator_type,
            "db_updated": success,
            "runtime_synced": runtime_synced,
        },
    )


@router.post(
    "/mock-esp/{esp_id}/actuators/{gpio}",
    response_model=CommandResponse,
    summary="Set Actuator State",
    description="Set the state of an actuator on a mock ESP32.",
)
async def set_actuator_state(
    esp_id: str,
    gpio: int,
    request: SetActuatorStateRequest,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
) -> CommandResponse:
    """
    Set an actuator's state and optionally publish MQTT status.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    from ...core.exceptions import ActuatorNotFoundError

    try:
        success = await scheduler.set_actuator_state(
            esp_id=esp_id,
            gpio=gpio,
            state=request.state,
            session=db,
            pwm_value=request.pwm_value,
        )

        return CommandResponse(
            success=success,
            esp_id=esp_id,
            command="set_actuator_state",
            result={"gpio": gpio, "state": request.state, "pwm_value": request.pwm_value},
        )
    except SimulationNotRunningError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Simulation for {esp_id} not running"
        )
    except ActuatorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Actuator GPIO {gpio} not found on {esp_id}",
        )


# =============================================================================
# Emergency Stop
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/emergency-stop",
    response_model=CommandResponse,
    summary="Emergency Stop",
    description="Trigger emergency stop on a mock ESP32, stopping all actuators.",
)
async def emergency_stop(
    esp_id: str,
    current_user: AdminUser,
    scheduler: SimulationSchedulerDep,
    reason: str = Query("manual"),
) -> CommandResponse:
    """
    Trigger emergency stop on a mock ESP.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    if not scheduler.is_mock_active(esp_id):
        raise SimulationNotRunningError(esp_id)

    success = await scheduler.emergency_stop(esp_id, reason)

    logger.warning(
        f"Emergency stop triggered on mock ESP {esp_id} by {current_user.username}: {reason}",
        extra={
            "esp_id": esp_id,
            "user": current_user.username,
            "reason": reason,
            "category": "actuator_operation",
        },
    )

    return CommandResponse(
        success=success,
        esp_id=esp_id,
        command="emergency_stop",
        result={"reason": reason, "emergency_stopped": True},
    )


@router.post(
    "/mock-esp/{esp_id}/clear-emergency",
    response_model=CommandResponse,
    summary="Clear Emergency",
    description="Clear emergency stop state on a mock ESP32.",
)
async def clear_emergency(
    esp_id: str,
    current_user: AdminUser,
    scheduler: SimulationSchedulerDep,
) -> CommandResponse:
    """
    Clear emergency stop on a mock ESP.

    Paket X: Uses SimulationScheduler instead of MockESPManager.
    """
    if not scheduler.is_mock_active(esp_id):
        raise SimulationNotRunningError(esp_id)

    success = await scheduler.clear_emergency(esp_id)

    logger.info(
        f"Emergency cleared on mock ESP {esp_id} by {current_user.username}",
        extra={"esp_id": esp_id, "user": current_user.username, "category": "actuator_operation"},
    )

    return CommandResponse(
        success=success,
        esp_id=esp_id,
        command="clear_emergency",
        result={"emergency_stopped": False},
    )


# =============================================================================
# Actuator Command Simulation (Paket G)
# =============================================================================
@router.post(
    "/mock-esp/{esp_id}/actuators/{gpio}/command",
    response_model=ActuatorCommandResponse,
    summary="Simulate Actuator Command",
    description="""
    Simulate an actuator command as if sent by the Logic Engine.
    
    This tests the full MQTT command flow for Mock-ESPs:
    1. Command is processed by MockActuatorHandler
    2. Actuator state is updated in runtime
    3. Response message is published to MQTT
    4. Status message is published to MQTT
    
    Unlike set_actuator_state (which directly sets state), this endpoint
    simulates the complete command flow including emergency stop checks
    and duration-based auto-off scheduling.
    """,
)
async def simulate_actuator_command(
    esp_id: str,
    gpio: int,
    request: ActuatorCommandRequest,
    current_user: AdminUser,
    db: DBSession,
) -> ActuatorCommandResponse:
    """
    Simulate an actuator command via the MQTT flow.

    This endpoint is useful for testing:
    - Logic Engine integration
    - Emergency stop behavior
    - Duration-based auto-off
    - MQTT response/status publishing
    """
    try:
        sim_scheduler = get_simulation_scheduler()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimulationScheduler not available",
        )

    # Check if mock is active
    if not sim_scheduler.is_mock_active(esp_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mock ESP {esp_id} not running. Start it first with auto_heartbeat=true",
        )

    # Get actuator handler
    handler = sim_scheduler.get_actuator_handler()
    if not handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MockActuatorHandler not initialized",
        )

    # Build mock MQTT topic and payload
    from ...mqtt.topics import TopicBuilder
    import json
    import time

    # Use TopicBuilder for consistency (TopicBuilder adds kaiser_id automatically)
    topic = TopicBuilder.build_actuator_command_topic(esp_id, gpio)
    payload = json.dumps(
        {
            "command": request.command,
            "value": request.value,
            "duration": request.duration,
            "timestamp": int(time.time()),
            "command_id": f"api_{int(time.time())}",
        }
    )

    # Execute command via handler
    success = await handler.handle_command(topic, payload)

    # Get updated state
    state_info = sim_scheduler.get_actuator_state(esp_id, gpio)

    if state_info:
        return ActuatorCommandResponse(
            success=success,
            esp_id=esp_id,
            gpio=gpio,
            command=request.command,
            state=state_info["state"],
            pwm_value=state_info["pwm_value"],
            message=f"Command {request.command} {'executed' if success else 'failed'}",
        )
    else:
        # Command may have failed, but return response anyway
        return ActuatorCommandResponse(
            success=success,
            esp_id=esp_id,
            gpio=gpio,
            command=request.command,
            state=False,
            pwm_value=0,
            message="Command processed but actuator state not found",
        )


@router.post(
    "/mock-esp/{esp_id}/actuators/{gpio}/emergency-stop",
    response_model=CommandResponse,
    summary="Emergency Stop Single Actuator",
    description="Trigger emergency stop on a mock ESP32 via SimulationScheduler.",
)
async def emergency_stop_via_scheduler(
    esp_id: str,
    gpio: int,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Trigger emergency stop on a mock ESP using SimulationScheduler.

    This uses the new Paket G infrastructure instead of MockESPManager.
    """
    try:
        sim_scheduler = get_simulation_scheduler()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimulationScheduler not available",
        )

    if not sim_scheduler.is_mock_active(esp_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not running"
        )

    # Get handler and trigger emergency
    handler = sim_scheduler.get_actuator_handler()
    if handler:
        # Simulate emergency message
        import json
        from ...mqtt.topics import TopicBuilder

        topic = TopicBuilder.build_actuator_emergency_topic(esp_id)
        payload = json.dumps(
            {"reason": "manual_api_trigger", "timestamp": int(__import__("time").time())}
        )
        await handler.handle_emergency(topic, payload, esp_id)

    logger.warning(f"Emergency stop triggered on mock ESP {esp_id} by {current_user.username}")

    return CommandResponse(
        success=True,
        esp_id=esp_id,
        command="emergency_stop_scheduler",
        result={"gpio": gpio, "emergency_stopped": True},
    )


@router.post(
    "/mock-esp/{esp_id}/clear-emergency-scheduler",
    response_model=CommandResponse,
    summary="Clear Emergency (Scheduler)",
    description="Clear emergency stop state using SimulationScheduler.",
)
async def clear_emergency_via_scheduler(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> CommandResponse:
    """
    Clear emergency stop on a mock ESP using SimulationScheduler.

    This uses the new Paket G infrastructure instead of MockESPManager.
    """
    try:
        sim_scheduler = get_simulation_scheduler()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimulationScheduler not available",
        )

    if not sim_scheduler.is_mock_active(esp_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not running"
        )

    success = await sim_scheduler.clear_emergency(esp_id)

    return CommandResponse(
        success=success,
        esp_id=esp_id,
        command="clear_emergency_scheduler",
        result={"emergency_cleared": success},
    )


@router.get(
    "/mock-esp/{esp_id}/actuator-states",
    response_model=Dict[str, Any],
    summary="Get All Actuator States",
    description="Get all actuator states for a running mock ESP.",
)
async def get_actuator_states(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> Dict[str, Any]:
    """
    Get all actuator states from SimulationScheduler runtime.

    Returns real-time state information for all actuators.
    """
    try:
        sim_scheduler = get_simulation_scheduler()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimulationScheduler not available",
        )

    if not sim_scheduler.is_mock_active(esp_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not running"
        )

    states = sim_scheduler.get_all_actuator_states(esp_id)
    runtime = sim_scheduler.get_runtime(esp_id)

    return {
        "esp_id": esp_id,
        "emergency_stopped": runtime.emergency_stopped if runtime else False,
        "actuators": states,
    }


# =============================================================================
# Message History
# =============================================================================
@router.get(
    "/mock-esp/{esp_id}/messages",
    response_model=MockESPMessagesResponse,
    summary="Get Published Messages",
    description="DEPRECATED — wird in naechster Version entfernt. Message history is not persisted after migration to SimulationScheduler.",
    deprecated=True,
)
async def get_messages(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
    limit: int = Query(100),
) -> MockESPMessagesResponse:
    """
    Get recently published MQTT messages from a mock ESP.

    Paket X: Message history is no longer stored in-memory.
    Returns empty list - messages should be queried from MQTT broker or database logs.
    """
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_mock_device(esp_id)

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Mock ESP {esp_id} not found"
        )

    # Message history is not stored in SimulationScheduler
    # Return empty list with note about where to find messages
    return MockESPMessagesResponse(success=True, esp_id=esp_id, messages=[], total=0)


@router.delete(
    "/mock-esp/{esp_id}/messages",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear Messages",
    description="DEPRECATED — wird in naechster Version entfernt. Clear message history for a mock ESP32. (no longer applicable)",
    deprecated=True,
)
async def clear_messages(
    esp_id: str,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
):
    """Clear message history for a mock ESP. (Deprecated - no-op)"""
    # Deprecated: SimulationScheduler does not track message history
    return None


# =============================================================================
# Database Explorer
# =============================================================================


def _get_sqlalchemy_type_to_column_type(sqlalchemy_type: str) -> ColumnType:
    """Map SQLAlchemy type string to ColumnType enum."""
    type_lower = sqlalchemy_type.lower()

    if "uuid" in type_lower:
        return ColumnType.UUID
    elif "int" in type_lower:
        return ColumnType.INTEGER
    elif (
        "float" in type_lower
        or "numeric" in type_lower
        or "decimal" in type_lower
        or "real" in type_lower
    ):
        return ColumnType.FLOAT
    elif "bool" in type_lower:
        return ColumnType.BOOLEAN
    elif "datetime" in type_lower or "timestamp" in type_lower:
        return ColumnType.DATETIME
    elif "json" in type_lower:
        return ColumnType.JSON
    else:
        return ColumnType.STRING


def _mask_sensitive_fields(table_name: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive fields in a record."""
    masked = record.copy()
    if table_name in MASKED_FIELDS:
        for field in MASKED_FIELDS[table_name]:
            if field in masked:
                masked[field] = "***MASKED***"
    return masked


def _serialize_value(value: Any) -> Any:
    """Serialize a value for JSON response."""
    if value is None:
        return None
    elif isinstance(value, datetime):
        return value.isoformat()
    elif hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool, list, dict)):
        # UUID and other objects
        return str(value)
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _parse_filters(filters_json: Optional[str], columns: List[str]) -> Dict[str, Any]:
    """Parse filter JSON string into a dict, validating column names."""
    if not filters_json:
        return {}

    try:
        filters = json.loads(filters_json)
        if not isinstance(filters, dict):
            raise ValueError("Filters must be a JSON object")

        # Validate that filter keys reference valid columns
        valid_filters = {}
        for key, value in filters.items():
            # Extract base column name (remove __gte, __lte, __in suffixes)
            base_column = key.split("__")[0]
            if base_column in columns:
                valid_filters[key] = value
            else:
                logger.warning(f"Ignoring filter for unknown column: {base_column}")

        return valid_filters
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid filter JSON: {e}")


async def _get_db_session():
    """Get async database session."""
    async for session in get_session():
        yield session


@router.get(
    "/db/tables",
    response_model=TableListResponse,
    summary="List Database Tables",
    description="Get list of all accessible database tables with metadata.",
)
async def list_database_tables(
    current_user: AdminUser, db: AsyncSession = Depends(_get_db_session)
) -> TableListResponse:
    """
    List all database tables accessible via the explorer.

    Returns table names, column schemas, and row counts.
    Only tables in the whitelist are returned.
    """
    tables = []

    # Get SQLAlchemy inspector
    def get_table_info(connection):
        inspector = inspect(connection)
        return inspector.get_table_names()

    # Run synchronously in the async context
    async with db.begin():
        connection = await db.connection()
        all_tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())

        for table_name in all_tables:
            if table_name not in ALLOWED_TABLES:
                continue

            # Get column info
            columns_info = await connection.run_sync(
                lambda conn, tn=table_name: inspect(conn).get_columns(tn)
            )

            # Get primary key info
            pk_info = await connection.run_sync(
                lambda conn, tn=table_name: inspect(conn).get_pk_constraint(tn)
            )

            # Get foreign key info
            fk_info = await connection.run_sync(
                lambda conn, tn=table_name: inspect(conn).get_foreign_keys(tn)
            )

            # Build foreign key lookup
            fk_lookup = {}
            for fk in fk_info:
                for local_col in fk.get("constrained_columns", []):
                    ref_table = fk.get("referred_table", "")
                    ref_cols = fk.get("referred_columns", [])
                    if ref_cols:
                        fk_lookup[local_col] = f"{ref_table}.{ref_cols[0]}"

            # Get primary key column(s)
            pk_columns = pk_info.get("constrained_columns", []) if pk_info else []
            primary_key = pk_columns[0] if pk_columns else "id"

            # Build column schemas
            columns = []
            for col in columns_info:
                col_name = col["name"]
                col_type = str(col["type"])

                columns.append(
                    ColumnSchema(
                        name=col_name,
                        type=_get_sqlalchemy_type_to_column_type(col_type),
                        nullable=col.get("nullable", True),
                        primary_key=col_name in pk_columns,
                        foreign_key=fk_lookup.get(col_name),
                    )
                )

            # Get row count
            result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = result.scalar() or 0

            tables.append(
                TableSchema(
                    table_name=table_name,
                    columns=columns,
                    row_count=row_count,
                    primary_key=primary_key,
                )
            )

    # Sort tables alphabetically
    tables.sort(key=lambda t: t.table_name)

    logger.info(f"Admin {current_user.username} listed {len(tables)} database tables")
    return TableListResponse(success=True, tables=tables)


@router.get(
    "/db/{table_name}/schema",
    response_model=TableSchema,
    summary="Get Table Schema",
    description="Get detailed schema information for a specific table.",
)
async def get_table_schema(
    table_name: str, current_user: AdminUser, db: AsyncSession = Depends(_get_db_session)
) -> TableSchema:
    """Get detailed schema of a database table."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found or not accessible",
        )

    async with db.begin():
        connection = await db.connection()

        # Check if table exists
        all_tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())

        if table_name not in all_tables:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_name}' not found in database",
            )

        # Get column info
        columns_info = await connection.run_sync(lambda conn: inspect(conn).get_columns(table_name))

        # Get primary key info
        pk_info = await connection.run_sync(
            lambda conn: inspect(conn).get_pk_constraint(table_name)
        )

        # Get foreign key info
        fk_info = await connection.run_sync(lambda conn: inspect(conn).get_foreign_keys(table_name))

        # Build foreign key lookup
        fk_lookup = {}
        for fk in fk_info:
            for local_col in fk.get("constrained_columns", []):
                ref_table = fk.get("referred_table", "")
                ref_cols = fk.get("referred_columns", [])
                if ref_cols:
                    fk_lookup[local_col] = f"{ref_table}.{ref_cols[0]}"

        pk_columns = pk_info.get("constrained_columns", []) if pk_info else []
        primary_key = pk_columns[0] if pk_columns else "id"

        columns = []
        for col in columns_info:
            col_name = col["name"]
            col_type = str(col["type"])

            columns.append(
                ColumnSchema(
                    name=col_name,
                    type=_get_sqlalchemy_type_to_column_type(col_type),
                    nullable=col.get("nullable", True),
                    primary_key=col_name in pk_columns,
                    foreign_key=fk_lookup.get(col_name),
                )
            )

        # Get row count
        result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        row_count = result.scalar() or 0

    return TableSchema(
        table_name=table_name, columns=columns, row_count=row_count, primary_key=primary_key
    )


@router.get(
    "/db/{table_name}",
    response_model=TableDataResponse,
    summary="Query Table Data",
    description="Query data from a database table with pagination, sorting, and filtering.",
)
async def query_table(
    table_name: str,
    current_user: AdminUser,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=50, ge=1, le=500, description="Records per page"),
    sort_by: Optional[str] = Query(default=None, description="Column to sort by"),
    sort_order: SortOrder = Query(default=SortOrder.DESC, description="Sort order"),
    filters: Optional[str] = Query(default=None, description="JSON-encoded filters"),
    db: AsyncSession = Depends(_get_db_session),
) -> TableDataResponse:
    """
    Query data from a database table.

    Supports:
    - Pagination (page, page_size)
    - Sorting (sort_by, sort_order)
    - Filtering (filters as JSON string)

    Filter syntax (Django-style):
    - {"column": "value"} - exact match
    - {"column__gte": 100} - greater than or equal
    - {"column__lte": 200} - less than or equal
    - {"column__in": ["a", "b"]} - in list

    Time-series tables (sensor_data, actuator_history, logic_execution_history)
    default to last 24 hours unless overridden with timestamp filters.
    """
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found or not accessible",
        )

    async with db.begin():
        connection = await db.connection()

        # Get column names for validation
        columns_info = await connection.run_sync(lambda conn: inspect(conn).get_columns(table_name))
        column_names = [col["name"] for col in columns_info]

        # Build type map for automatic coercion (e.g. string → datetime for TIMESTAMPTZ columns)
        column_type_map: Dict[str, type] = {}
        for _col in columns_info:
            _col_type = _col.get("type")
            if _col_type is not None:
                try:
                    column_type_map[_col["name"]] = _col_type.python_type
                except NotImplementedError:
                    pass

        # Parse and validate filters
        try:
            parsed_filters = _parse_filters(filters, column_names)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Build base query
        base_query = f"SELECT * FROM {table_name}"
        count_query = f"SELECT COUNT(*) FROM {table_name}"

        # Build WHERE clause
        where_clauses = []
        params = {}
        param_index = 0

        # For time-series tables, add default time filter if not provided
        if table_name in TIME_SERIES_TABLES:
            timestamp_col = TIME_SERIES_TABLES[table_name]
            has_timestamp_filter = any(
                key.startswith(timestamp_col) for key in parsed_filters.keys()
            )

            if not has_timestamp_filter:
                # Default to last 24 hours — use SQL NOW() to avoid asyncpg
                # datetime serialization issues with text() parameter binding
                where_clauses.append(
                    f"{timestamp_col} >= NOW() - INTERVAL"
                    f" '{DEFAULT_TIME_SERIES_LIMIT_HOURS} hours'"
                )

        # Process filters
        for key, value in parsed_filters.items():
            parts = key.split("__")
            col_name = parts[0]
            operator = parts[1] if len(parts) > 1 else "eq"

            if col_name not in column_names:
                continue

            param_name = f"p{param_index}"

            # Coerce ISO datetime strings to datetime objects for timestamp columns.
            # asyncpg requires a Python datetime for TIMESTAMPTZ — it cannot cast strings.
            if isinstance(value, str) and column_type_map.get(col_name) == datetime:
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            if operator == "eq" or operator == col_name:
                where_clauses.append(f"{col_name} = :{param_name}")
                params[param_name] = value
            elif operator == "gte":
                where_clauses.append(f"{col_name} >= :{param_name}")
                params[param_name] = value
            elif operator == "lte":
                where_clauses.append(f"{col_name} <= :{param_name}")
                params[param_name] = value
            elif operator == "gt":
                where_clauses.append(f"{col_name} > :{param_name}")
                params[param_name] = value
            elif operator == "lt":
                where_clauses.append(f"{col_name} < :{param_name}")
                params[param_name] = value
            elif operator == "in":
                if isinstance(value, list):
                    placeholders = []
                    for i, v in enumerate(value):
                        p_name = f"p{param_index}_{i}"
                        placeholders.append(f":{p_name}")
                        params[p_name] = v
                    where_clauses.append(f"{col_name} IN ({', '.join(placeholders)})")
            elif operator == "contains":
                where_clauses.append(f"{col_name} LIKE :{param_name}")
                params[param_name] = f"%{value}%"

            param_index += 1

        # Add WHERE clause to queries
        if where_clauses:
            where_sql = " AND ".join(where_clauses)
            base_query += f" WHERE {where_sql}"
            count_query += f" WHERE {where_sql}"

        # Get total count
        result = await db.execute(text(count_query), params)
        total_count = result.scalar() or 0

        # Add sorting
        if sort_by and sort_by in column_names:
            order_dir = "ASC" if sort_order == SortOrder.ASC else "DESC"
            base_query += f" ORDER BY {sort_by} {order_dir}"
        elif "created_at" in column_names:
            # Default sort by created_at desc
            base_query += " ORDER BY created_at DESC"
        elif "timestamp" in column_names:
            # For time-series tables
            base_query += " ORDER BY timestamp DESC"
        elif "id" in column_names:
            base_query += " ORDER BY id DESC"

        # Add pagination
        offset = (page - 1) * page_size
        base_query += f" LIMIT {page_size} OFFSET {offset}"

        # Execute query
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        # Serialize and mask data
        data = []
        for row in rows:
            record = {k: _serialize_value(v) for k, v in dict(row).items()}
            record = _mask_sensitive_fields(table_name, record)
            data.append(record)

    # Calculate total pages
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    logger.info(
        f"Admin {current_user.username} queried table {table_name}: "
        f"page={page}, page_size={page_size}, total={total_count}"
    )

    return TableDataResponse(
        success=True,
        table_name=table_name,
        data=data,
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/db/{table_name}/{record_id}",
    response_model=RecordResponse,
    summary="Get Single Record",
    description="Get a single record from a database table by its primary key.",
)
async def get_record(
    table_name: str,
    record_id: str,
    current_user: AdminUser,
    db: AsyncSession = Depends(_get_db_session),
) -> RecordResponse:
    """Get a single record by its primary key."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found or not accessible",
        )

    async with db.begin():
        connection = await db.connection()

        # Get primary key info
        pk_info = await connection.run_sync(
            lambda conn: inspect(conn).get_pk_constraint(table_name)
        )

        pk_columns = pk_info.get("constrained_columns", []) if pk_info else []
        if not pk_columns:
            pk_columns = ["id"]

        primary_key = pk_columns[0]

        # Build and execute query
        query = f"SELECT * FROM {table_name} WHERE {primary_key} = :record_id"
        result = await db.execute(text(query), {"record_id": record_id})
        row = result.mappings().first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record with {primary_key}={record_id} not found in {table_name}",
            )

        # Serialize and mask
        record = {k: _serialize_value(v) for k, v in dict(row).items()}
        record = _mask_sensitive_fields(table_name, record)

    return RecordResponse(success=True, table_name=table_name, record=record)


# =============================================================================
# Log Viewer
# =============================================================================


class LogLevel(str, Enum):
    """Log level filter options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogEntry(BaseModel):
    """A single log entry."""

    timestamp: str
    level: str
    logger: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    exception: Optional[str] = None
    request_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class LogsResponse(BaseModel):
    """Response for log queries."""

    success: bool = True
    logs: List[LogEntry]
    total_count: int
    page: int
    page_size: int
    has_more: bool


class LogFilesResponse(BaseModel):
    """Response for available log files."""

    success: bool = True
    files: List[Dict[str, Any]]
    log_directory: str


class LogFileInfo(BaseModel):
    """Detailed log file information."""

    name: str
    size_mb: float
    size_bytes: int
    modified_at: str
    entry_count: Optional[int] = None
    is_current: bool = False


class LogStatisticsResponse(BaseModel):
    """Response for log statistics."""

    success: bool = True
    total_size_mb: float
    total_size_bytes: int
    file_count: int
    files: List[LogFileInfo]


class LogCleanupResponse(BaseModel):
    """Response for log cleanup operations."""

    success: bool = True
    dry_run: bool
    files_to_delete: List[str]
    total_size_mb: float
    deleted_count: int = 0
    backup_url: Optional[str] = None


class LogDeleteResponse(BaseModel):
    """Response for single log file deletion."""

    success: bool = True
    deleted: bool
    filename: str
    size_mb: float
    backup_url: Optional[str] = None


# In-memory store for temporary backup references
_log_backups: Dict[str, Dict[str, Any]] = {}


def _parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse a single log line (JSON format)."""
    _KNOWN_JSON_KEYS = {
        "timestamp",
        "level",
        "logger",
        "message",
        "module",
        "function",
        "line",
        "exception",
        "request_id",
    }
    try:
        data = json.loads(line.strip())
        return LogEntry(
            timestamp=data.get("timestamp", ""),
            level=data.get("level", "INFO"),
            logger=data.get("logger", "unknown"),
            message=data.get("message", ""),
            module=data.get("module"),
            function=data.get("function"),
            line=data.get("line"),
            exception=data.get("exception"),
            request_id=data.get("request_id"),
            extra={k: v for k, v in data.items() if k not in _KNOWN_JSON_KEYS} or None,
        )
    except json.JSONDecodeError:
        # Try parsing as text format
        # New format: "2025-01-01 12:00:00 - logger - LEVEL - [req-id] - message"
        pattern_with_rid = (
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+?) - (\w+) - \[([^\]]+)\] - (.*)$"
        )
        match = re.match(pattern_with_rid, line.strip())
        if match:
            rid = match.group(4)
            return LogEntry(
                timestamp=match.group(1),
                logger=match.group(2),
                level=match.group(3),
                request_id=rid if rid != "-" else None,
                message=match.group(5),
            )
        # Legacy format: "2025-01-01 12:00:00 - logger - LEVEL - message"
        pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+?) - (\w+) - (.*)$"
        match = re.match(pattern, line.strip())
        if match:
            return LogEntry(
                timestamp=match.group(1),
                logger=match.group(2),
                level=match.group(3),
                message=match.group(4),
            )
        return None
    except Exception:
        return None


def _filter_log_entry(
    entry: LogEntry,
    level: Optional[LogLevel],
    module: Optional[str],
    search: Optional[str],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    request_id: Optional[str] = None,
) -> bool:
    """Check if a log entry matches the filters."""
    # Request-ID filter (exact match)
    if request_id and entry.request_id != request_id:
        return False

    # Level filter
    if level:
        level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level.value in level_order and entry.level in level_order:
            if level_order.index(entry.level) < level_order.index(level.value):
                return False

    # Module filter
    if module and module.lower() not in entry.logger.lower():
        return False

    # Search filter
    if search:
        search_lower = search.lower()
        if search_lower not in entry.message.lower() and search_lower not in entry.logger.lower():
            return False

    # Time filters
    # Log timestamps are in server-local time (naive datetime).
    # Query params from the frontend arrive as UTC-aware datetimes (ISO with Z).
    # We must convert query times to local naive datetimes before comparing.
    if entry.timestamp and (start_time or end_time):
        try:
            # Parse timestamp (handle both formats)
            ts_str = entry.timestamp.replace("T", " ").split(".")[0]
            entry_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")

            # Convert timezone-aware query times to local naive datetimes
            if start_time:
                st = (
                    start_time.astimezone().replace(tzinfo=None)
                    if start_time.tzinfo
                    else start_time
                )
                if entry_time < st.replace(microsecond=0):
                    return False
            if end_time:
                et = end_time.astimezone().replace(tzinfo=None) if end_time.tzinfo else end_time
                if entry_time > et.replace(microsecond=0):
                    return False
        except ValueError:
            pass  # Can't parse timestamp, include entry anyway

    return True


@router.get(
    "/logs/files",
    response_model=LogFilesResponse,
    summary="List Log Files",
    description="Get list of available log files.",
)
async def list_log_files(current_user: AdminUser) -> LogFilesResponse:
    """List all available log files."""
    settings = get_settings()
    log_path = Path(settings.logging.file_path)
    log_dir = log_path.parent

    files = []

    if log_dir.exists():
        for f in sorted(log_dir.glob("*.log*"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = f.stat()
            files.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                    "size_human": (
                        f"{stat.st_size / 1024:.1f} KB"
                        if stat.st_size < 1024 * 1024
                        else f"{stat.st_size / (1024 * 1024):.1f} MB"
                    ),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_current": f.name == log_path.name,
                }
            )

    return LogFilesResponse(success=True, files=files, log_directory=str(log_dir))


@router.get(
    "/logs",
    response_model=LogsResponse,
    summary="Query Logs",
    description="Query server logs with filtering and pagination.",
)
async def query_logs(
    current_user: AdminUser,
    level: Optional[LogLevel] = Query(default=None, description="Minimum log level"),
    module: Optional[str] = Query(default=None, description="Filter by logger/module name"),
    search: Optional[str] = Query(default=None, description="Search in message text"),
    start_time: Optional[datetime] = Query(default=None, description="Start time filter"),
    end_time: Optional[datetime] = Query(default=None, description="End time filter"),
    request_id: Optional[str] = Query(
        default=None, description="Filter by request_id (exact match)"
    ),
    file: Optional[str] = Query(default=None, description="Specific log file to read"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=100, ge=1, le=1000, description="Entries per page"),
) -> LogsResponse:
    """
    Query server logs with filtering.

    Reads logs in reverse order (newest first) for better performance.
    Supports filtering by log level, module name, search text, and time range.

    When start_time/end_time are set and no specific file is selected,
    automatically searches across ALL log files to find entries in the time range.
    """
    settings = get_settings()
    log_dir = Path(settings.logging.file_path).parent

    # Determine which file(s) to read
    if file:
        log_paths = [log_dir / file]
        if not log_paths[0].exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Log file '{file}' not found"
            )
    elif start_time or end_time or request_id:
        # Multi-file search: scan all log files when time range or request_id is specified
        log_paths = (
            sorted(log_dir.glob("god_kaiser.log*"), key=lambda x: x.stat().st_mtime, reverse=True)
            if log_dir.exists()
            else []
        )
    else:
        log_paths = [Path(settings.logging.file_path)]

    if not log_paths or not any(p.exists() for p in log_paths):
        return LogsResponse(
            success=True, logs=[], total_count=0, page=page, page_size=page_size, has_more=False
        )

    # Read and parse logs (reverse order for newest first)
    all_entries: List[LogEntry] = []
    MAX_MATCHED = 10000
    MAX_LINES_SCANNED = 100000  # Stop scanning after 100k lines total

    try:
        lines_scanned = 0
        for log_path in log_paths:
            if not log_path.exists():
                continue

            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Process in reverse (newest first)
            for line in reversed(lines):
                lines_scanned += 1
                if lines_scanned > MAX_LINES_SCANNED:
                    break

                if not line.strip():
                    continue

                entry = _parse_log_line(line)
                if entry and _filter_log_entry(
                    entry, level, module, search, start_time, end_time, request_id
                ):
                    all_entries.append(entry)

                if len(all_entries) >= MAX_MATCHED:
                    break

            if len(all_entries) >= MAX_MATCHED or lines_scanned > MAX_LINES_SCANNED:
                break
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading log file: {str(e)}",
        )

    # Sort by timestamp (newest first) when merging multiple files
    if len(log_paths) > 1 and all_entries:
        all_entries.sort(key=lambda e: e.timestamp if hasattr(e, "timestamp") else "", reverse=True)

    # Pagination
    total_count = len(all_entries)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_entries = all_entries[start_idx:end_idx]

    logger.info(
        f"Admin {current_user.username} queried logs: "
        f"file={log_path.name}, level={level}, page={page}, total={total_count}"
    )

    return LogsResponse(
        success=True,
        logs=page_entries,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=end_idx < total_count,
    )


# =============================================================================
# Log Management (Statistics, Cleanup, Delete, Backup)
# =============================================================================


def _get_log_files_info(log_dir: Path, current_log_name: str) -> List[LogFileInfo]:
    """Get detailed info for all log files in directory."""
    files: List[LogFileInfo] = []
    if not log_dir.exists():
        return files

    for f in sorted(log_dir.glob("*.log*"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        # Count lines for entry estimation (fast: just count newlines)
        try:
            entry_count = sum(
                1 for line in open(f, "r", encoding="utf-8", errors="replace") if line.strip()
            )
        except Exception:
            entry_count = None

        files.append(
            LogFileInfo(
                name=f.name,
                size_mb=round(stat.st_size / (1024 * 1024), 2),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                entry_count=entry_count,
                is_current=f.name == current_log_name,
            )
        )
    return files


def _create_log_backup(log_dir: Path, filenames: List[str]) -> Optional[str]:
    """Create a ZIP backup of specified log files. Returns backup_id."""
    backup_id = str(uuid.uuid4())[:8]
    backup_dir = log_dir / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"logs_backup_{backup_id}.zip"

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in filenames:
                fpath = log_dir / fname
                if fpath.exists():
                    zf.write(fpath, fname)

        _log_backups[backup_id] = {
            "path": str(backup_path),
            "created_at": datetime.now(timezone.utc),
            "files": filenames,
        }
        return backup_id
    except Exception as e:
        logger.error(f"Failed to create log backup: {e}")
        return None


def _cleanup_expired_backups() -> None:
    """Remove backups older than 1 hour."""
    now = datetime.now(timezone.utc)
    expired = [
        bid
        for bid, info in _log_backups.items()
        if (now - info["created_at"]).total_seconds() > 3600
    ]
    for bid in expired:
        try:
            backup_path = Path(_log_backups[bid]["path"])
            if backup_path.exists():
                backup_path.unlink()
        except Exception:
            pass
        del _log_backups[bid]


@router.get(
    "/logs/statistics",
    response_model=LogStatisticsResponse,
    summary="Log Statistics",
    description="Get log file statistics including sizes and entry counts.",
)
async def get_log_statistics(
    current_user: AdminUser,
) -> LogStatisticsResponse:
    """Get statistics about all log files."""
    settings = get_settings()
    log_path = Path(settings.logging.file_path)
    log_dir = log_path.parent

    files = _get_log_files_info(log_dir, log_path.name)
    total_bytes = sum(f.size_bytes for f in files)

    logger.info(f"Admin {current_user.username} requested log statistics")

    return LogStatisticsResponse(
        total_size_mb=round(total_bytes / (1024 * 1024), 2),
        total_size_bytes=total_bytes,
        file_count=len(files),
        files=files,
    )


@router.post(
    "/logs/cleanup",
    response_model=LogCleanupResponse,
    summary="Cleanup Logs",
    description="Delete selected log files with optional dry-run preview and backup.",
)
async def cleanup_logs(
    current_user: AdminUser,
    dry_run: bool = Query(default=True, description="Preview only, don't delete"),
    files: Optional[List[str]] = Query(
        default=None, description="Files to delete (empty = all non-current)"
    ),
    create_backup: bool = Query(default=True, description="Create ZIP backup before deletion"),
) -> LogCleanupResponse:
    """Cleanup log files with dry-run support."""
    _cleanup_expired_backups()

    settings = get_settings()
    log_path = Path(settings.logging.file_path)
    log_dir = log_path.parent
    current_name = log_path.name

    # Determine files to delete
    if files:
        files_to_delete = [f for f in files if f != current_name]
    else:
        # All non-current log files
        if log_dir.exists():
            files_to_delete = [
                f.name for f in log_dir.glob("*.log*") if f.name != current_name and f.is_file()
            ]
        else:
            files_to_delete = []

    # Calculate total size
    total_bytes = 0
    for fname in files_to_delete:
        fpath = log_dir / fname
        if fpath.exists():
            total_bytes += fpath.stat().st_size

    total_mb = round(total_bytes / (1024 * 1024), 2)

    if dry_run:
        logger.info(
            f"Admin {current_user.username} previewed log cleanup: "
            f"{len(files_to_delete)} files, {total_mb} MB"
        )
        return LogCleanupResponse(
            dry_run=True,
            files_to_delete=files_to_delete,
            total_size_mb=total_mb,
        )

    # Create backup if requested
    backup_url = None
    if create_backup and files_to_delete:
        backup_id = _create_log_backup(log_dir, files_to_delete)
        if backup_id:
            backup_url = f"/api/v1/debug/logs/backup/{backup_id}"

    # Delete files
    deleted_count = 0
    for fname in files_to_delete:
        fpath = log_dir / fname
        try:
            if fpath.exists():
                fpath.unlink()
                deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete log file {fname}: {e}")

    logger.info(
        f"Admin {current_user.username} cleaned up logs: "
        f"{deleted_count}/{len(files_to_delete)} files deleted, {total_mb} MB freed"
    )

    return LogCleanupResponse(
        dry_run=False,
        files_to_delete=files_to_delete,
        total_size_mb=total_mb,
        deleted_count=deleted_count,
        backup_url=backup_url,
    )


@router.delete(
    "/logs/{filename}",
    response_model=LogDeleteResponse,
    summary="Delete Log File",
    description="Delete a single log file. The current active log file cannot be deleted.",
)
async def delete_log_file(
    filename: str,
    current_user: AdminUser,
    create_backup: bool = Query(default=False, description="Create backup before deletion"),
) -> LogDeleteResponse:
    """Delete a single log file."""
    settings = get_settings()
    log_path = Path(settings.logging.file_path)
    log_dir = log_path.parent
    current_name = log_path.name

    # Protection: cannot delete current log
    if filename == current_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete the current active log file '{current_name}'",
        )

    target = log_dir / filename
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Log file '{filename}' not found"
        )

    # Security: prevent path traversal
    try:
        target.resolve().relative_to(log_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid filename")

    size_mb = round(target.stat().st_size / (1024 * 1024), 2)

    backup_url = None
    if create_backup:
        backup_id = _create_log_backup(log_dir, [filename])
        if backup_id:
            backup_url = f"/api/v1/debug/logs/backup/{backup_id}"

    try:
        target.unlink()
    except Exception as e:
        logger.error(f"Failed to delete log file {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        )

    logger.info(f"Admin {current_user.username} deleted log file: {filename} ({size_mb} MB)")

    return LogDeleteResponse(
        deleted=True,
        filename=filename,
        size_mb=size_mb,
        backup_url=backup_url,
    )


@router.get(
    "/logs/backup/{backup_id}",
    summary="Download Log Backup",
    description="Download a previously created log backup as ZIP file.",
)
async def download_log_backup(
    backup_id: str,
    current_user: AdminUser,
):
    """Download a log backup ZIP file."""
    from fastapi.responses import FileResponse

    _cleanup_expired_backups()

    if backup_id not in _log_backups:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup '{backup_id}' not found or expired",
        )

    backup_info = _log_backups[backup_id]
    backup_path = Path(backup_info["path"])

    if not backup_path.exists():
        del _log_backups[backup_id]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Backup file no longer exists"
        )

    logger.info(f"Admin {current_user.username} downloaded log backup: {backup_id}")

    return FileResponse(
        path=str(backup_path),
        filename=backup_path.name,
        media_type="application/zip",
    )


# =============================================================================
# System Configuration
# =============================================================================


class ConfigEntry(BaseModel):
    """A single configuration entry."""

    id: str
    config_key: str
    config_value: Any
    config_type: str
    description: Optional[str] = None
    is_secret: bool = False
    created_at: str
    updated_at: str


class ConfigListResponse(BaseModel):
    """Response for config list."""

    success: bool = True
    configs: List[ConfigEntry]
    total: int


class ConfigUpdateRequest(BaseModel):
    """Request to update a config value."""

    config_value: Any = Field(..., description="New configuration value (JSON)")


@router.get(
    "/config",
    response_model=ConfigListResponse,
    summary="List System Configuration",
    description="Get all system configuration entries.",
)
async def list_config(
    current_user: AdminUser,
    config_type: Optional[str] = Query(default=None, description="Filter by config type"),
    db: AsyncSession = Depends(_get_db_session),
) -> ConfigListResponse:
    """List all system configuration."""
    query = "SELECT * FROM system_config"
    params = {}

    if config_type:
        query += " WHERE config_type = :config_type"
        params["config_type"] = config_type

    query += " ORDER BY config_type, config_key"

    result = await db.execute(text(query), params)
    rows = result.mappings().all()

    configs = []
    for row in rows:
        row_dict = dict(row)
        # Mask secret values
        if row_dict.get("is_secret"):
            row_dict["config_value"] = "***MASKED***"

        configs.append(
            ConfigEntry(
                id=str(row_dict["id"]),
                config_key=row_dict["config_key"],
                config_value=row_dict["config_value"],
                config_type=row_dict["config_type"],
                description=row_dict.get("description"),
                is_secret=row_dict.get("is_secret", False),
                created_at=row_dict["created_at"].isoformat() if row_dict.get("created_at") else "",
                updated_at=row_dict["updated_at"].isoformat() if row_dict.get("updated_at") else "",
            )
        )

    return ConfigListResponse(success=True, configs=configs, total=len(configs))


@router.patch(
    "/config/{config_key}",
    response_model=ConfigEntry,
    summary="Update Configuration",
    description="Update a system configuration value.",
)
async def update_config(
    config_key: str,
    update_data: ConfigUpdateRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(_get_db_session),
) -> ConfigEntry:
    """Update a system configuration entry."""
    # Check if config exists
    result = await db.execute(
        text("SELECT * FROM system_config WHERE config_key = :key"), {"key": config_key}
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration '{config_key}' not found"
        )

    # Update the config
    await db.execute(
        text(
            """
            UPDATE system_config
            SET config_value = :value, updated_at = :updated_at
            WHERE config_key = :key
        """
        ),
        {
            "value": update_data.config_value,
            "updated_at": datetime.now(timezone.utc),
            "key": config_key,
        },
    )
    await db.commit()

    # Fetch updated row
    result = await db.execute(
        text("SELECT * FROM system_config WHERE config_key = :key"), {"key": config_key}
    )
    updated_row = result.mappings().first()
    row_dict = dict(updated_row)

    logger.info(f"Admin {current_user.username} updated config: {config_key}")

    return ConfigEntry(
        id=str(row_dict["id"]),
        config_key=row_dict["config_key"],
        config_value=row_dict["config_value"] if not row_dict.get("is_secret") else "***MASKED***",
        config_type=row_dict["config_type"],
        description=row_dict.get("description"),
        is_secret=row_dict.get("is_secret", False),
        created_at=row_dict["created_at"].isoformat() if row_dict.get("created_at") else "",
        updated_at=row_dict["updated_at"].isoformat() if row_dict.get("updated_at") else "",
    )


# =============================================================================
# Load Testing
# =============================================================================


class BulkCreateRequest(BaseModel):
    """Request to bulk-create mock ESPs."""

    count: int = Field(..., ge=1, le=100, description="Number of mock ESPs to create")
    prefix: str = Field(default="LOAD_TEST", description="ESP ID prefix")
    with_sensors: int = Field(default=2, ge=0, le=10, description="Sensors per ESP")
    with_actuators: int = Field(default=1, ge=0, le=10, description="Actuators per ESP")


class BulkCreateResponse(BaseModel):
    """Response for bulk create."""

    success: bool = True
    created_count: int
    esp_ids: List[str]
    message: str


class SimulationRequest(BaseModel):
    """Request to start sensor simulation."""

    esp_ids: Optional[List[str]] = Field(
        default=None, description="ESPs to simulate (all if empty)"
    )
    interval_ms: int = Field(
        default=1000, ge=100, le=60000, description="Simulation interval in ms"
    )
    duration_seconds: int = Field(default=60, ge=10, le=3600, description="Simulation duration")


class SimulationResponse(BaseModel):
    """Response for simulation control."""

    success: bool = True
    message: str
    active_simulations: int = 0


class MetricsResponse(BaseModel):
    """Response for performance metrics."""

    success: bool = True
    mock_esp_count: int
    total_sensors: int
    total_actuators: int
    messages_published: int
    uptime_seconds: float


@router.post(
    "/load-test/bulk-create",
    response_model=BulkCreateResponse,
    summary="Bulk Create Mock ESPs",
    description="Create multiple mock ESPs for load testing using SimulationScheduler.",
)
async def bulk_create_mock_esps(
    request: BulkCreateRequest,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
) -> BulkCreateResponse:
    """
    Create multiple mock ESPs at once for load testing.

    Paket X: Uses SimulationScheduler.create_mock_esp() for DB-first creation.
    """
    created_ids = []

    for i in range(request.count):
        esp_id = f"{request.prefix}_{i+1:04d}"

        try:
            # Build sensor configs
            sensors = []
            for s in range(request.with_sensors):
                sensors.append(
                    {
                        "gpio": 2 + s,
                        "sensor_type": "DHT22" if s % 2 == 0 else "DS18B20",
                        "name": f"Sensor_{s+1}",
                        "unit": "°C" if s % 2 == 0 else "%",
                        "raw_value": 20.0 + s,
                        "interval_seconds": 30.0,
                        "variation_pattern": "random",
                        "variation_range": 5.0,
                    }
                )

            # Build actuator configs
            actuators = []
            for a in range(request.with_actuators):
                actuators.append(
                    {
                        "gpio": 12 + a,
                        "actuator_type": "relay" if a % 2 == 0 else "pwm",
                        "name": f"Actuator_{a+1}",
                    }
                )

            # Create via SimulationScheduler (DB-first)
            await scheduler.create_mock_esp(
                esp_id=esp_id,
                session=db,
                auto_start=True,
                sensors=sensors,
                actuators=actuators,
                heartbeat_interval=60.0,
            )
            created_ids.append(esp_id)

        except Exception as e:
            # ESP already exists or other error, skip
            logger.warning(f"Failed to create mock ESP {esp_id}: {e}")
            continue

    logger.info(
        f"Admin {current_user.username} bulk-created {len(created_ids)} mock ESPs",
        extra={
            "admin_user": current_user.username,
            "created_count": len(created_ids),
            "prefix": request.prefix,
            "category": "esp_lifecycle",
        },
    )

    return BulkCreateResponse(
        success=True,
        created_count=len(created_ids),
        esp_ids=created_ids,
        message=f"Created {len(created_ids)} mock ESPs with prefix '{request.prefix}'",
    )


@router.post(
    "/load-test/simulate",
    response_model=SimulationResponse,
    summary="Start Sensor Simulation",
    description="Start automatic sensor value simulation for load testing using SimulationScheduler.",
)
async def start_simulation(
    request: SimulationRequest,
    current_user: AdminUser,
    db: DBSession,
    scheduler: SimulationSchedulerDep,
) -> SimulationResponse:
    """
    Start sensor simulation on mock ESPs.

    Paket X: Uses SimulationScheduler.set_auto_heartbeat() for simulation control.
    """
    esp_repo = ESPRepository(db)

    # Get ESPs to simulate
    if request.esp_ids:
        esp_ids = request.esp_ids
    else:
        # Get all mock devices from database
        devices = await esp_repo.get_mock_devices()
        esp_ids = [device.device_id for device in devices]

    # Start auto-heartbeat on each ESP (simulating activity)
    interval_seconds = request.interval_ms / 1000

    active_count = 0
    for esp_id in esp_ids:
        try:
            success = await scheduler.set_auto_heartbeat(
                esp_id=esp_id,
                enabled=True,
                interval_seconds=interval_seconds,
                session=db,
            )
            if success:
                active_count += 1
        except Exception as e:
            logger.warning(f"Failed to start simulation for {esp_id}: {e}")
            continue

    logger.info(
        f"Admin {current_user.username} started simulation on {active_count} ESPs "
        f"(interval={request.interval_ms}ms, duration={request.duration_seconds}s)",
        extra={
            "admin_user": current_user.username,
            "active_count": active_count,
            "interval_ms": request.interval_ms,
            "duration_seconds": request.duration_seconds,
            "category": "simulation_control",
        },
    )

    return SimulationResponse(
        success=True,
        message=f"Started simulation on {active_count} mock ESPs",
        active_simulations=active_count,
    )


@router.post(
    "/load-test/stop",
    response_model=SimulationResponse,
    summary="Stop Simulation",
    description="Stop all sensor simulations using SimulationScheduler.",
)
async def stop_simulation(
    current_user: AdminUser,
    scheduler: SimulationSchedulerDep,
) -> SimulationResponse:
    """
    Stop all active simulations.

    Paket X: Uses SimulationScheduler.stop_all_mocks() for efficient batch stop.
    """
    # Stop all active simulations
    stopped_count = await scheduler.stop_all_mocks()

    logger.info(
        f"Admin {current_user.username} stopped simulation on {stopped_count} ESPs",
        extra={
            "admin_user": current_user.username,
            "stopped_count": stopped_count,
            "category": "simulation_control",
        },
    )

    return SimulationResponse(
        success=True,
        message=f"Stopped simulation on {stopped_count} mock ESPs",
        active_simulations=0,
    )


@router.get(
    "/load-test/metrics",
    response_model=MetricsResponse,
    summary="Get Load Test Metrics",
    description="Get performance metrics for load testing from database.",
)
async def get_load_test_metrics(
    current_user: AdminUser,
    db: DBSession,
) -> MetricsResponse:
    """
    Get load test performance metrics.

    Paket X: Uses database queries for metrics (no in-memory message history).
    """
    esp_repo = ESPRepository(db)

    # Get all mock devices
    devices = await esp_repo.get_mock_devices()

    # Count sensors and actuators from device metadata
    total_sensors = 0
    total_actuators = 0
    for device in devices:
        if device.device_metadata:
            sim_config = device.device_metadata.get("simulation_config", {})
            total_sensors += len(sim_config.get("sensors", {}))
            total_actuators += len(sim_config.get("actuators", {}))

    # Count sensor_data entries (as proxy for MQTT messages)
    from ...db.models.sensor import SensorData
    from ...db.models.esp import ESPDevice

    sensor_data_count_result = await db.execute(
        select(func.count(SensorData.id))
        .join(ESPDevice, SensorData.esp_id == ESPDevice.id)
        .where(ESPDevice.hardware_type == "MOCK_ESP32")
    )
    sensor_data_count = sensor_data_count_result.scalar() or 0

    # Count actuator_history entries
    from ...db.models.actuator import ActuatorHistory

    actuator_history_count_result = await db.execute(
        select(func.count(ActuatorHistory.id))
        .join(ESPDevice, ActuatorHistory.esp_id == ESPDevice.id)
        .where(ESPDevice.hardware_type == "MOCK_ESP32")
    )
    actuator_history_count = actuator_history_count_result.scalar() or 0

    total_messages = sensor_data_count + actuator_history_count

    # Calculate uptime (time since first ESP was created)
    uptime_seconds = 0.0
    if devices:
        oldest = min(device.created_at for device in devices if device.created_at)
        if oldest:
            uptime_seconds = (datetime.now(timezone.utc) - oldest).total_seconds()

    return MetricsResponse(
        success=True,
        mock_esp_count=len(devices),
        total_sensors=total_sensors,
        total_actuators=total_actuators,
        messages_published=total_messages,
        uptime_seconds=uptime_seconds,
    )


# =============================================================================
# Cleanup Operations
# =============================================================================


class CleanupResponse(BaseModel):
    """Response for cleanup operations."""

    success: bool = True
    deleted_count: int
    deleted_ids: List[str]
    message: str


@router.delete(
    "/cleanup/orphaned-mocks",
    response_model=CleanupResponse,
    summary="Cleanup Orphaned Mock ESPs",
    description="DEPRECATED: With DB-first architecture, orphaned mocks no longer exist. Use DELETE /mock-esp/{id} instead.",
    deprecated=True,
)
async def cleanup_orphaned_mocks(
    current_user: AdminUser,
    db: DBSession,
) -> CleanupResponse:
    """
    Clean up orphaned mock ESP entries from the database.

    Paket X: DEPRECATED - This endpoint is no longer needed with DB-first architecture.
    With SimulationScheduler, the database is the single source of truth and there are
    no "orphaned" entries. Use DELETE /mock-esp/{id} to remove individual mocks.

    This endpoint now only cleans up legacy entries with NULL required fields
    (from pre-Paket B implementations).
    """
    deleted_ids = []

    # Only delete entries with NULL required fields (legacy cleanup)
    result = await db.execute(
        text(
            """
            SELECT id, device_id
            FROM esp_devices
            WHERE hardware_type = 'MOCK_ESP32'
              AND (ip_address IS NULL OR mac_address IS NULL OR firmware_version IS NULL)
        """
        )
    )
    invalid_esps = result.fetchall()

    for esp in invalid_esps:
        esp_id = esp[1]  # device_id
        await db.execute(text("DELETE FROM esp_devices WHERE id = :id"), {"id": str(esp[0])})
        deleted_ids.append(esp_id)

    if deleted_ids:
        await db.commit()
        logger.info(
            f"Admin {current_user.username} cleaned up {len(deleted_ids)} legacy mock ESPs",
            extra={
                "admin_user": current_user.username,
                "deleted_count": len(deleted_ids),
                "deleted_ids": deleted_ids,
                "category": "esp_lifecycle",
            },
        )

    return CleanupResponse(
        success=True,
        deleted_count=len(deleted_ids),
        deleted_ids=deleted_ids,
        message=f"Cleaned up {len(deleted_ids)} legacy mock ESP entries (use DELETE /mock-esp/{{id}} for individual deletion)",
    )


class TestDataCleanupResponse(BaseModel):
    """Response for test data cleanup operations."""

    success: bool = True
    dry_run: bool
    sensor_data: Dict[str, Any]
    actuator_data: Dict[str, Any]
    total_deleted: int
    message: str


@router.delete(
    "/test-data/cleanup",
    response_model=TestDataCleanupResponse,
    summary="Cleanup Test Data",
    description="Delete test/mock/simulation data from sensor_data and actuator_history tables.",
)
async def cleanup_test_data(
    current_user: AdminUser,
    db: DBSession,
    dry_run: bool = Query(default=True, description="Preview deletions without actually deleting"),
    include_mock: bool = Query(default=True, description="Include MOCK data in cleanup"),
    include_simulation: bool = Query(
        default=True, description="Include SIMULATION data in cleanup"
    ),
) -> TestDataCleanupResponse:
    """
    Clean up test data from the database.

    This deletes sensor_data and actuator_history entries based on their data_source:
    - TEST: Always included, retention = 24 hours
    - MOCK: Optional (include_mock), retention = 7 days
    - SIMULATION: Optional (include_simulation), retention = 30 days
    - PRODUCTION: Never deleted

    Use dry_run=true (default) to preview what would be deleted without actually deleting.
    """
    retention_service = AuditRetentionService(db)

    try:
        result = await retention_service.run_full_test_cleanup(
            dry_run=dry_run, include_mock=include_mock, include_simulation=include_simulation
        )

        # Service returns "total_deleted" in sub-dicts, not "deleted_count"
        total_deleted = result.get("total_deleted", 0)

        action = "Would delete" if dry_run else "Deleted"
        logger.info(
            f"Admin {current_user.username} ran test data cleanup "
            f"(dry_run={dry_run}, mock={include_mock}, sim={include_simulation}): "
            f"{total_deleted} records affected"
        )

        # Map service result keys to API response format
        sensor_result = result.get("sensor_data", {})
        actuator_result = result.get("actuator_history", {})

        return TestDataCleanupResponse(
            success=True,
            dry_run=dry_run,
            sensor_data={
                "deleted_count": sensor_result.get("total_deleted", 0),
                "deleted_by_source": sensor_result.get("deleted", {}),
                "duration_ms": sensor_result.get("duration_ms", 0),
                "errors": sensor_result.get("errors", []),
            },
            actuator_data={
                "deleted_count": actuator_result.get("total_deleted", 0),
                "deleted_by_source": actuator_result.get("deleted", {}),
                "duration_ms": actuator_result.get("duration_ms", 0),
                "errors": actuator_result.get("errors", []),
            },
            total_deleted=total_deleted,
            message=f"{action} {total_deleted} test data records",
        )

    except Exception as e:
        logger.error(f"Error during test data cleanup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup test data: {str(e)}",
        )


# =============================================================================
# Library Management Endpoints
# =============================================================================


class LibraryReloadResponse(BaseModel):
    """Response for library reload operations."""

    success: bool = True
    processors_before: int
    processors_after: int
    available_types: List[str]
    message: str


@router.post(
    "/libraries/reload",
    response_model=LibraryReloadResponse,
    summary="Reload Sensor Libraries",
    description="Hot-reload sensor processing libraries without server restart.",
)
async def reload_sensor_libraries(
    current_user: AdminUser,
) -> LibraryReloadResponse:
    """
    Reload all sensor processing libraries.

    This is useful when:
    - New sensor libraries are added to sensor_libraries/active/
    - Existing libraries are modified
    - Libraries need to be refreshed without server restart

    Returns the count of processors before and after reload.
    """
    from ...sensors.library_loader import LibraryLoader

    loader = LibraryLoader.get_instance()

    # Count before reload
    processors_before = len(loader.processors)

    # Reload libraries
    loader.reload_libraries()

    # Count after reload
    processors_after = len(loader.processors)
    available_types = loader.get_available_sensors()

    logger.info(
        f"Admin {current_user.username} reloaded sensor libraries: "
        f"{processors_before} → {processors_after} processors"
    )

    return LibraryReloadResponse(
        success=True,
        processors_before=processors_before,
        processors_after=processors_after,
        available_types=available_types,
        message=f"Reloaded sensor libraries: {processors_after} processors available",
    )


class LibraryInfoResponse(BaseModel):
    """Response for library info."""

    available_types: List[str]
    count: int
    library_path: str


@router.get(
    "/libraries/info",
    response_model=LibraryInfoResponse,
    summary="Get Library Info",
    description="Get information about loaded sensor processing libraries.",
)
async def get_library_info(
    current_user: AdminUser,
) -> LibraryInfoResponse:
    """
    Get information about loaded sensor processing libraries.

    Returns list of available sensor types and library path.
    """
    from ...sensors.library_loader import LibraryLoader

    loader = LibraryLoader.get_instance()
    available_types = loader.get_available_sensors()

    return LibraryInfoResponse(
        available_types=available_types,
        count=len(available_types),
        library_path=str(loader.library_path),
    )


# =============================================================================
# Mock ESP Sync Status Endpoints
# =============================================================================


class MockESPSyncStatusResponse(BaseModel):
    """Response for Mock ESP sync status."""

    in_memory_count: int
    in_database_count: int
    synced_count: int
    orphaned_count: int
    orphaned_ids: List[str]
    memory_only_ids: List[str]
    is_synced: bool
    message: str


@router.get(
    "/mock-esp/sync-status",
    response_model=MockESPSyncStatusResponse,
    summary="[DEPRECATED] Get Mock ESP Sync Status",
    description="DEPRECATED: This endpoint is no longer needed. Database is now Single Source of Truth. Use GET /mock-esp instead.",
    deprecated=True,
)
async def get_mock_esp_sync_status(
    current_user: AdminUser,
    db: DBSession,
) -> MockESPSyncStatusResponse:
    """
    DEPRECATED: Get synchronization status between in-memory Mock ESPs and database.

    This endpoint exists only for backward compatibility and debugging purposes.
    With DB-First architecture (Paket B), the database is the Single Source of Truth
    and sync issues should not occur.

    Use GET /mock-esp instead to list all Mock ESPs from database.

    Migration:
        OLD: GET /v1/debug/mock-esp/sync-status
        NEW: GET /v1/debug/mock-esp (lists all mocks from DB with runtime status)
    """
    esp_repo = ESPRepository(db)

    # Get all Mock ESPs from database (Single Source of Truth)
    db_mock_esps = await esp_repo.get_all_mock_devices()
    db_mock_ids = [esp.device_id for esp in db_mock_esps]

    # Get active simulations from SimulationScheduler
    active_ids: List[str] = []
    try:
        sim_scheduler = get_simulation_scheduler()
        active_ids = sim_scheduler.get_active_mocks()
    except RuntimeError:
        pass

    # Check for discrepancies (should be rare with DB-first approach)
    # DB has mocks not in runtime -> they need to be recovered or are stopped
    # Runtime has mocks not in DB -> bug (should not happen with DB-first)
    orphaned_ids = [id for id in db_mock_ids if id not in active_ids]
    memory_only_ids = [id for id in active_ids if id not in db_mock_ids]
    synced_count = len([id for id in active_ids if id in db_mock_ids])

    is_synced = len(memory_only_ids) == 0  # DB-first: memory-only is a bug

    if is_synced:
        message = "DEPRECATED: Database is Single Source of Truth. Use GET /mock-esp instead."
    else:
        parts = []
        if len(orphaned_ids) > 0:
            parts.append(f"{len(orphaned_ids)} stopped simulations in DB")
        if len(memory_only_ids) > 0:
            parts.append(f"{len(memory_only_ids)} runtime-only entries (BUG)")
        message = f"Status: {', '.join(parts)}. This endpoint is DEPRECATED."

    return MockESPSyncStatusResponse(
        in_memory_count=len(active_ids),
        in_database_count=len(db_mock_ids),
        synced_count=synced_count,
        orphaned_count=len(orphaned_ids),
        orphaned_ids=orphaned_ids,
        memory_only_ids=memory_only_ids,
        is_synced=is_synced,
        message=message,
    )


class DataSourceDetectionRequest(BaseModel):
    """Request for data source detection test."""

    esp_id: str
    hardware_type: Optional[str] = None
    capabilities_mock: Optional[bool] = None
    payload_test_mode: Optional[bool] = None
    payload_source: Optional[str] = None


class DataSourceDetectionResponse(BaseModel):
    """Response for data source detection test."""

    esp_id: str
    detected_source: str
    detection_reason: str
    checks_performed: List[Dict[str, Any]]


@router.post(
    "/data-source/detect",
    response_model=DataSourceDetectionResponse,
    summary="Test Data Source Detection",
    description="Test data source detection logic with custom parameters.",
)
async def test_data_source_detection(
    request: DataSourceDetectionRequest,
    current_user: AdminUser,
) -> DataSourceDetectionResponse:
    """
    Test the data source detection logic.

    This endpoint simulates the detection logic with custom parameters
    to help debug data source classification issues.

    Returns the detected source and which check triggered the detection.
    """
    from ...db.models.enums import DataSource

    esp_id = request.esp_id
    checks = []
    detected_source = None
    detection_reason = None

    # Build mock payload
    payload = {"esp_id": esp_id}
    if request.payload_test_mode:
        payload["_test_mode"] = True
    if request.payload_source:
        payload["_source"] = request.payload_source

    # Check 1: _test_mode
    checks.append(
        {
            "priority": 1,
            "check": "payload._test_mode",
            "value": payload.get("_test_mode"),
            "matched": bool(payload.get("_test_mode")),
        }
    )
    if payload.get("_test_mode") and detected_source is None:
        detected_source = DataSource.TEST.value
        detection_reason = "payload._test_mode=True"

    # Check 2: _source
    checks.append(
        {
            "priority": 2,
            "check": "payload._source",
            "value": payload.get("_source"),
            "matched": "_source" in payload and detected_source is None,
        }
    )
    if "_source" in payload and detected_source is None:
        try:
            detected_source = DataSource(payload["_source"].lower()).value
            detection_reason = f"payload._source='{payload['_source']}'"
        except ValueError:
            pass

    # Check 3: hardware_type
    checks.append(
        {
            "priority": 3,
            "check": "hardware_type='MOCK_ESP32'",
            "value": request.hardware_type,
            "matched": request.hardware_type == "MOCK_ESP32" and detected_source is None,
        }
    )
    if request.hardware_type == "MOCK_ESP32" and detected_source is None:
        detected_source = DataSource.MOCK.value
        detection_reason = "hardware_type='MOCK_ESP32'"

    # Check 4: capabilities.mock
    checks.append(
        {
            "priority": 4,
            "check": "capabilities.mock=True",
            "value": request.capabilities_mock,
            "matched": request.capabilities_mock is True and detected_source is None,
        }
    )
    if request.capabilities_mock is True and detected_source is None:
        detected_source = DataSource.MOCK.value
        detection_reason = "capabilities.mock=True"

    # Check 5-7: ESP ID prefix
    prefixes = [
        (5, "MOCK_", DataSource.MOCK.value),
        (6, "TEST_", DataSource.TEST.value),
        (7, "SIM_", DataSource.SIMULATION.value),
    ]
    for priority, prefix, source in prefixes:
        matched = esp_id.startswith(prefix) and detected_source is None
        checks.append(
            {
                "priority": priority,
                "check": f"esp_id.startswith('{prefix}')",
                "value": esp_id,
                "matched": matched,
            }
        )
        if matched:
            detected_source = source
            detection_reason = f"esp_id prefix '{prefix}'"

    # Default
    if detected_source is None:
        detected_source = DataSource.PRODUCTION.value
        detection_reason = "default (no matching criteria)"

    checks.append(
        {
            "priority": 8,
            "check": "default",
            "value": None,
            "matched": detection_reason == "default (no matching criteria)",
        }
    )

    return DataSourceDetectionResponse(
        esp_id=esp_id,
        detected_source=detected_source,
        detection_reason=detection_reason,
        checks_performed=checks,
    )


# =============================================================================
# Maintenance Service Endpoints
# =============================================================================


class MaintenanceStatusResponse(BaseModel):
    """Response for maintenance service status."""

    service_running: bool
    jobs: List[Dict[str, Any]]
    stats_cache: Dict[str, Any]


class MaintenanceTriggerResponse(BaseModel):
    """Response for manual job trigger."""

    job_id: str
    triggered: bool
    message: str


class MaintenanceConfigResponse(BaseModel):
    """Response for maintenance configuration (Data-Safe Version)."""

    # Sensor Data Cleanup
    sensor_data_retention_enabled: bool
    sensor_data_retention_days: int
    sensor_data_cleanup_dry_run: bool
    sensor_data_cleanup_batch_size: int
    sensor_data_cleanup_max_batches: int

    # Command History Cleanup
    command_history_retention_enabled: bool
    command_history_retention_days: int
    command_history_cleanup_dry_run: bool
    command_history_cleanup_batch_size: int
    command_history_cleanup_max_batches: int

    # Audit Log Cleanup
    audit_log_retention_enabled: bool
    audit_log_retention_days: int
    audit_log_cleanup_dry_run: bool
    audit_log_cleanup_batch_size: int
    audit_log_cleanup_max_batches: int

    # Orphaned Mocks
    orphaned_mock_cleanup_enabled: bool
    orphaned_mock_auto_delete: bool
    orphaned_mock_age_hours: int

    # Health Checks
    heartbeat_timeout_seconds: int
    mqtt_health_check_interval_seconds: int
    esp_health_check_interval_seconds: int

    # Stats Aggregation
    stats_aggregation_enabled: bool
    stats_aggregation_interval_minutes: int

    # Safety Features
    cleanup_require_confirmation: bool
    cleanup_alert_threshold_percent: float
    cleanup_max_records_per_run: int


@router.get(
    "/maintenance/status",
    response_model=MaintenanceStatusResponse,
    summary="Get Maintenance Service Status",
    description="Get status of all maintenance and monitoring jobs.",
)
async def get_maintenance_status(
    current_user: AdminUser,
) -> MaintenanceStatusResponse:
    """Get status of maintenance service and all registered jobs."""
    try:
        from ...services.maintenance import get_maintenance_service

        maintenance_service = get_maintenance_service()
        status = maintenance_service.get_status()

        return MaintenanceStatusResponse(**status)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MaintenanceService not available: {e}",
        )


@router.post(
    "/maintenance/trigger/{job_name}",
    response_model=MaintenanceTriggerResponse,
    summary="Trigger Maintenance Job Manually",
    description="Manually trigger a maintenance or monitoring job immediately.",
)
async def trigger_maintenance_job(
    job_name: str,
    current_user: AdminUser,
) -> MaintenanceTriggerResponse:
    """
    Manually trigger a maintenance job.

    Available job names:
    - cleanup_sensor_data
    - cleanup_command_history
    - cleanup_orphaned_mocks
    - health_check_esps
    - health_check_mqtt
    - aggregate_stats
    """
    try:
        from ...services.maintenance import get_maintenance_service
        from ...core.scheduler import get_central_scheduler

        maintenance_service = get_maintenance_service()
        get_central_scheduler()  # Verify scheduler is running

        # Map job name to full job ID
        job_id_map = {
            "cleanup_sensor_data": "maintenance_cleanup_sensor_data",
            "cleanup_command_history": "maintenance_cleanup_command_history",
            "cleanup_orphaned_mocks": "maintenance_cleanup_orphaned_mocks",
            "health_check_esps": "monitor_health_check_esps",
            "health_check_mqtt": "monitor_health_check_mqtt",
            "aggregate_stats": "maintenance_aggregate_stats",
        }

        full_job_id = job_id_map.get(job_name)
        if not full_job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown job name: {job_name}. Available: {list(job_id_map.keys())}",
            )

        # Get job function from maintenance service
        job_func_map = {
            "maintenance_cleanup_sensor_data": maintenance_service._cleanup_sensor_data,
            "maintenance_cleanup_command_history": maintenance_service._cleanup_command_history,
            "maintenance_cleanup_orphaned_mocks": maintenance_service._cleanup_orphaned_mocks,
            "monitor_health_check_esps": maintenance_service._health_check_esps,
            "monitor_health_check_mqtt": maintenance_service._health_check_mqtt,
            "maintenance_aggregate_stats": maintenance_service._aggregate_stats,
        }

        job_func = job_func_map.get(full_job_id)
        if not job_func:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Job function not found for {full_job_id}",
            )

        # Trigger job asynchronously
        import asyncio

        asyncio.create_task(job_func())

        logger.info(f"Admin {current_user.username} manually triggered maintenance job: {job_name}")

        return MaintenanceTriggerResponse(
            job_id=full_job_id,
            triggered=True,
            message=f"Job {job_name} triggered manually, will run immediately",
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MaintenanceService not available: {e}",
        )


@router.get(
    "/maintenance/config",
    response_model=MaintenanceConfigResponse,
    summary="Get Maintenance Configuration",
    description="Get current maintenance service configuration.",
)
async def get_maintenance_config(
    current_user: AdminUser,
) -> MaintenanceConfigResponse:
    """Get maintenance service configuration."""
    settings = get_settings()
    maintenance_settings = settings.maintenance

    return MaintenanceConfigResponse(
        # Sensor Data Cleanup
        sensor_data_retention_enabled=maintenance_settings.sensor_data_retention_enabled,
        sensor_data_retention_days=maintenance_settings.sensor_data_retention_days,
        sensor_data_cleanup_dry_run=maintenance_settings.sensor_data_cleanup_dry_run,
        sensor_data_cleanup_batch_size=maintenance_settings.sensor_data_cleanup_batch_size,
        sensor_data_cleanup_max_batches=maintenance_settings.sensor_data_cleanup_max_batches,
        # Command History Cleanup
        command_history_retention_enabled=maintenance_settings.command_history_retention_enabled,
        command_history_retention_days=maintenance_settings.command_history_retention_days,
        command_history_cleanup_dry_run=maintenance_settings.command_history_cleanup_dry_run,
        command_history_cleanup_batch_size=maintenance_settings.command_history_cleanup_batch_size,
        command_history_cleanup_max_batches=maintenance_settings.command_history_cleanup_max_batches,
        # Audit Log Cleanup
        audit_log_retention_enabled=maintenance_settings.audit_log_retention_enabled,
        audit_log_retention_days=maintenance_settings.audit_log_retention_days,
        audit_log_cleanup_dry_run=maintenance_settings.audit_log_cleanup_dry_run,
        audit_log_cleanup_batch_size=maintenance_settings.audit_log_cleanup_batch_size,
        audit_log_cleanup_max_batches=maintenance_settings.audit_log_cleanup_max_batches,
        # Orphaned Mocks
        orphaned_mock_cleanup_enabled=maintenance_settings.orphaned_mock_cleanup_enabled,
        orphaned_mock_auto_delete=maintenance_settings.orphaned_mock_auto_delete,
        orphaned_mock_age_hours=maintenance_settings.orphaned_mock_age_hours,
        # Health Checks
        heartbeat_timeout_seconds=maintenance_settings.heartbeat_timeout_seconds,
        mqtt_health_check_interval_seconds=maintenance_settings.mqtt_health_check_interval_seconds,
        esp_health_check_interval_seconds=maintenance_settings.esp_health_check_interval_seconds,
        # Stats Aggregation
        stats_aggregation_enabled=maintenance_settings.stats_aggregation_enabled,
        stats_aggregation_interval_minutes=maintenance_settings.stats_aggregation_interval_minutes,
        # Safety Features
        cleanup_require_confirmation=maintenance_settings.cleanup_require_confirmation,
        cleanup_alert_threshold_percent=maintenance_settings.cleanup_alert_threshold_percent,
        cleanup_max_records_per_run=maintenance_settings.cleanup_max_records_per_run,
    )


# =============================================================================
# Resilience Debug Endpoints
# =============================================================================


class ResilienceStatusResponse(BaseModel):
    """Response for resilience status."""

    healthy: bool
    circuit_breakers: Dict[str, Any]
    summary: Dict[str, int]
    mqtt_client: Dict[str, Any]


class CircuitBreakerActionResponse(BaseModel):
    """Response for circuit breaker actions."""

    name: str
    previous_state: str
    new_state: str
    message: str


class CircuitBreakerMetricsResponse(BaseModel):
    """Response for circuit breaker metrics."""

    name: str
    state: str
    metrics: Dict[str, Any]


@router.get(
    "/resilience/status",
    response_model=ResilienceStatusResponse,
    summary="Get Resilience Status",
    description="Get status of all circuit breakers and resilience components.",
)
async def get_resilience_status(
    current_user: AdminUser,
) -> ResilienceStatusResponse:
    """
    Get aggregated resilience status.

    Returns:
    - Health status of all circuit breakers
    - Individual breaker states and metrics
    - MQTT client resilience status
    """
    from ...core.resilience import ResilienceRegistry
    from ...mqtt.client import MQTTClient

    registry = ResilienceRegistry.get_instance()
    health_status = registry.get_health_status()

    # Get MQTT client resilience status
    mqtt_client = MQTTClient.get_instance()
    mqtt_status = mqtt_client.get_resilience_status()

    return ResilienceStatusResponse(
        healthy=health_status["healthy"],
        circuit_breakers=health_status["breakers"],
        summary=health_status["summary"],
        mqtt_client=mqtt_status,
    )


@router.get(
    "/resilience/metrics",
    response_model=Dict[str, Any],
    summary="Get Resilience Metrics",
    description="Get detailed metrics from all circuit breakers.",
)
async def get_resilience_metrics(
    current_user: AdminUser,
    publisher: MQTTPublisher,
) -> Dict[str, Any]:
    """
    Get detailed metrics from all circuit breakers.

    Returns metrics including:
    - Total requests
    - Success/failure counts
    - Rejection counts
    - State transition history
    """
    from ...core.resilience import ResilienceRegistry

    registry = ResilienceRegistry.get_instance()
    breaker_metrics = registry.get_metrics()

    # Get publisher metrics (publisher injected via Depends — see api/deps.py)
    publisher_metrics = publisher.get_metrics()

    return {
        "circuit_breakers": breaker_metrics,
        "publisher": publisher_metrics,
    }


@router.get(
    "/resilience/circuit-breaker/{name}",
    response_model=CircuitBreakerMetricsResponse,
    summary="Get Circuit Breaker Details",
    description="Get detailed information about a specific circuit breaker.",
)
async def get_circuit_breaker_details(
    name: str,
    current_user: AdminUser,
) -> CircuitBreakerMetricsResponse:
    """Get details of a specific circuit breaker."""
    from ...core.resilience import ResilienceRegistry

    registry = ResilienceRegistry.get_instance()
    breaker = registry.get_circuit_breaker(name)

    if breaker is None:
        available = registry.get_breaker_names()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found. Available: {available}",
        )

    metrics = breaker.get_metrics()

    return CircuitBreakerMetricsResponse(
        name=name,
        state=breaker.get_state().value,
        metrics=metrics,
    )


@router.post(
    "/resilience/circuit-breaker/{name}/reset",
    response_model=CircuitBreakerActionResponse,
    summary="Reset Circuit Breaker",
    description="Manually reset a circuit breaker to CLOSED state.",
)
async def reset_circuit_breaker(
    name: str,
    current_user: AdminUser,
) -> CircuitBreakerActionResponse:
    """
    Manually reset a circuit breaker to CLOSED state.

    Use this to recover from an OPEN state after resolving
    the underlying issue.
    """
    from ...core.resilience import ResilienceRegistry

    registry = ResilienceRegistry.get_instance()
    breaker = registry.get_circuit_breaker(name)

    if breaker is None:
        available = registry.get_breaker_names()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found. Available: {available}",
        )

    previous_state = breaker.get_state().value
    await breaker.reset_async()
    new_state = breaker.get_state().value

    logger.info(
        f"Admin {current_user.username} reset circuit breaker '{name}': "
        f"{previous_state} → {new_state}"
    )

    return CircuitBreakerActionResponse(
        name=name,
        previous_state=previous_state,
        new_state=new_state,
        message=f"Circuit breaker '{name}' reset successfully",
    )


@router.post(
    "/resilience/circuit-breaker/{name}/force-open",
    response_model=CircuitBreakerActionResponse,
    summary="Force Open Circuit Breaker",
    description="Force a circuit breaker to OPEN state for testing.",
)
async def force_open_circuit_breaker(
    name: str,
    current_user: AdminUser,
) -> CircuitBreakerActionResponse:
    """
    Force a circuit breaker to OPEN state.

    WARNING: This is for testing purposes only.
    The breaker will reject all requests until manually reset.
    """
    from ...core.resilience import ResilienceRegistry

    registry = ResilienceRegistry.get_instance()
    breaker = registry.get_circuit_breaker(name)

    if breaker is None:
        available = registry.get_breaker_names()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Circuit breaker '{name}' not found. Available: {available}",
        )

    previous_state = breaker.get_state().value
    await breaker.force_open_async()
    new_state = "open (forced)"

    logger.warning(
        f"Admin {current_user.username} FORCED OPEN circuit breaker '{name}' "
        f"(previous state: {previous_state})"
    )

    return CircuitBreakerActionResponse(
        name=name,
        previous_state=previous_state,
        new_state=new_state,
        message=f"Circuit breaker '{name}' forced OPEN (testing mode)",
    )


@router.post(
    "/resilience/reset-all",
    response_model=Dict[str, Any],
    summary="Reset All Circuit Breakers",
    description="Reset all circuit breakers to CLOSED state.",
)
async def reset_all_circuit_breakers(
    current_user: AdminUser,
) -> Dict[str, Any]:
    """
    Reset all circuit breakers to CLOSED state.

    Use this for emergency recovery after resolving system-wide issues.
    """
    from ...core.resilience import ResilienceRegistry

    registry = ResilienceRegistry.get_instance()

    # Get states before reset
    before = {
        name: breaker.get_state().value for name, breaker in registry.get_all_breakers().items()
    }

    count = await registry.reset_all_async()

    # Get states after reset
    after = {
        name: breaker.get_state().value for name, breaker in registry.get_all_breakers().items()
    }

    logger.warning(f"Admin {current_user.username} reset ALL {count} circuit breakers")

    return {
        "reset_count": count,
        "before": before,
        "after": after,
        "message": f"Reset {count} circuit breakers successfully",
    }


@router.get(
    "/resilience/offline-buffer",
    response_model=Dict[str, Any],
    summary="Get Offline Buffer Status",
    description="Get MQTT offline buffer status and metrics.",
)
async def get_offline_buffer_status(
    current_user: AdminUser,
) -> Dict[str, Any]:
    """
    Get MQTT offline buffer status.

    Returns:
    - Current buffer size
    - Messages added/flushed/dropped
    - Buffer utilization
    """
    from ...mqtt.client import MQTTClient

    mqtt_client = MQTTClient.get_instance()
    metrics = mqtt_client.get_offline_buffer_metrics()

    return {
        "enabled": metrics.get("enabled", True) if "enabled" in metrics else True,
        "metrics": metrics,
    }


@router.post(
    "/resilience/offline-buffer/flush",
    response_model=Dict[str, Any],
    summary="Flush Offline Buffer",
    description="Manually flush the MQTT offline buffer.",
)
async def flush_offline_buffer(
    current_user: AdminUser,
) -> Dict[str, Any]:
    """
    Manually flush the MQTT offline buffer.

    Attempts to send all buffered messages to the MQTT broker.
    """
    from ...mqtt.client import MQTTClient

    mqtt_client = MQTTClient.get_instance()

    if not mqtt_client._offline_buffer:
        return {
            "success": False,
            "message": "Offline buffer not available",
            "flushed_count": 0,
        }

    flushed_count = await mqtt_client._offline_buffer.flush_all(mqtt_client)

    logger.info(
        f"Admin {current_user.username} manually flushed offline buffer: "
        f"{flushed_count} messages"
    )

    return {
        "success": True,
        "message": f"Flushed {flushed_count} messages from offline buffer",
        "flushed_count": flushed_count,
        "remaining": mqtt_client._offline_buffer.size,
    }


@router.delete(
    "/resilience/offline-buffer",
    response_model=Dict[str, Any],
    summary="Clear Offline Buffer",
    description="Clear all messages from the MQTT offline buffer.",
)
async def clear_offline_buffer(
    current_user: AdminUser,
) -> Dict[str, Any]:
    """
    Clear all messages from the offline buffer.

    WARNING: This will permanently delete all buffered messages.
    """
    from ...mqtt.client import MQTTClient

    mqtt_client = MQTTClient.get_instance()

    if not mqtt_client._offline_buffer:
        return {
            "success": False,
            "message": "Offline buffer not available",
            "cleared_count": 0,
        }

    cleared_count = await mqtt_client._offline_buffer.clear()

    logger.warning(
        f"Admin {current_user.username} CLEARED offline buffer: "
        f"{cleared_count} messages deleted"
    )

    return {
        "success": True,
        "message": f"Cleared {cleared_count} messages from offline buffer",
        "cleared_count": cleared_count,
    }
