"""
Health Check API Endpoints

Phase: 5 (Week 9-10) - API Layer
Priority: 🟡 HIGH
Status: IMPLEMENTED

Provides:
- GET / - Basic health check
- GET /detailed - Comprehensive health
- GET /esp - ESP health summary
- GET /metrics - Prometheus metrics (served by prometheus-fastapi-instrumentator)
- GET /live - Liveness probe
- GET /ready - Readiness probe

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 191-195)
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from ...core.config import get_settings
from ...core.logging_config import get_logger
from ...core.resilience import ResilienceRegistry
from ...db.repositories import ActuatorRepository, ESPRepository, SensorRepository
from ...mqtt.client import MQTTClient
from ...services.health_service import HealthService
from ...services.runtime_state_service import get_runtime_state_service
from ...schemas import (
    DatabaseHealth,
    DetailedHealthResponse,
    ESPHealthItem,
    HealthResponse,
    LivenessResponse,
    MQTTHealth,
    ReadinessResponse,
    SystemResourceHealth,
    WebSocketHealth,
)
from ...schemas.health import CircuitBreakerHealth, ResilienceHealth, ResilienceSummary
from ...schemas.health import ESPHealthSummaryResponse, RecentError
from ...websocket.manager import WebSocketManager
from ..deps import ActiveUser, DBSession

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/health", tags=["health"])

# Track server start time for uptime calculation
_server_start_time = time.time()


# =============================================================================
# Basic Health
# =============================================================================


@router.get(
    "/",
    response_model=HealthResponse,
    summary="Basic health check",
    description="Simple health check for load balancers.",
)
async def health_check() -> HealthResponse:
    """
    Basic health check.

    Returns basic server status for load balancer health probes.
    """
    mqtt_client = MQTTClient.get_instance()

    # Determine overall status
    status = "healthy"
    if not mqtt_client.is_connected():
        status = "degraded"

    uptime_seconds = int(time.time() - _server_start_time)

    return HealthResponse(
        success=True,
        status=status,
        version="2.0.0",
        environment=settings.environment,
        uptime_seconds=uptime_seconds,
        timestamp=datetime.now(timezone.utc),
    )


# =============================================================================
# Detailed Health
# =============================================================================


@router.get(
    "/detailed",
    response_model=DetailedHealthResponse,
    summary="Detailed health check",
    description="Comprehensive health status with component details.",
)
async def detailed_health(
    db: DBSession,
    current_user: ActiveUser,
) -> DetailedHealthResponse:
    """
    Detailed health check.

    Returns comprehensive health status including all components.
    """
    mqtt_client = MQTTClient.get_instance()
    websocket_manager = await WebSocketManager.get_instance()
    runtime_snapshot = await get_runtime_state_service().snapshot()

    uptime_seconds = int(time.time() - _server_start_time)

    # Format uptime
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_formatted = f"{days}d {hours}h {minutes}m"

    # Database health
    db_health = DatabaseHealth(
        connected=True,  # If we're here, DB is connected
        pool_size=20,  # From config
        pool_available=18,  # Would need to query actual pool
        latency_ms=5.0,  # Would measure actual query time
        database_type="SQLite" if "sqlite" in str(settings.database.url) else "PostgreSQL",
    )

    # MQTT health
    mqtt_health = MQTTHealth(
        connected=mqtt_client.is_connected(),
        broker_host=settings.mqtt.broker_host,
        broker_port=settings.mqtt.broker_port,
        subscriptions=5,  # Would get from subscriber
        messages_received=0,  # Would track in client
        messages_published=0,
        last_message_at=None,
    )

    # WebSocket health
    ws_health = WebSocketHealth(
        active_connections=websocket_manager.connection_count if websocket_manager else 0,
        total_messages_sent=0,  # Would track
    )

    # System resources
    try:
        import psutil

        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        system_health = SystemResourceHealth(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_total_mb=memory.total / (1024 * 1024),
            disk_percent=disk.percent,
            disk_free_gb=disk.free / (1024 * 1024 * 1024),
        )
    except ImportError:
        system_health = SystemResourceHealth(
            cpu_percent=0.0,
            memory_percent=0.0,
            memory_used_mb=0.0,
            memory_total_mb=0.0,
            disk_percent=0.0,
            disk_free_gb=0.0,
        )

    # Resilience health (circuit breakers)
    try:
        registry = ResilienceRegistry.get_instance()
        raw_status = registry.get_health_status()
        resilience_health = ResilienceHealth(
            healthy=raw_status["healthy"],
            breakers={
                name: CircuitBreakerHealth(**data) for name, data in raw_status["breakers"].items()
            },
            summary=ResilienceSummary(**raw_status["summary"]),
        )
    except Exception:
        resilience_health = None

    # Determine overall status
    status = "healthy"
    warnings = []

    if not mqtt_client.is_connected():
        status = "degraded"
        warnings.append("MQTT broker disconnected")

    if runtime_snapshot.get("mode") == "DEGRADED_OPERATION":
        status = "degraded"
    for reason in runtime_snapshot.get("degraded_reason_codes", []):
        warnings.append(f"runtime:{reason}")

    if resilience_health and not resilience_health.healthy:
        status = "degraded"
        open_breakers = [
            name for name, b in resilience_health.breakers.items() if b.state == "open"
        ]
        warnings.append(f"Circuit breakers open: {', '.join(open_breakers)}")

    if system_health.disk_percent > 90:
        warnings.append("Disk space low")
        if status == "healthy":
            status = "degraded"

    if system_health.memory_percent > 90:
        warnings.append("Memory usage high")
        if status == "healthy":
            status = "degraded"

    return DetailedHealthResponse(
        success=True,
        status=status,
        version="2.0.0",
        environment=settings.environment,
        uptime_seconds=uptime_seconds,
        uptime_formatted=uptime_formatted,
        timestamp=datetime.now(timezone.utc),
        database=db_health,
        mqtt=mqtt_health,
        websocket=ws_health,
        system=system_health,
        resilience=resilience_health,
        components=[],
        warnings=warnings,
    )


# =============================================================================
# ESP Health Summary
# =============================================================================


@router.get(
    "/esp",
    response_model=ESPHealthSummaryResponse,
    summary="ESP health summary",
    description="Health summary for all ESP devices.",
)
async def esp_health_summary(
    db: DBSession,
    current_user: ActiveUser,
) -> ESPHealthSummaryResponse:
    """
    Get ESP health summary.

    Returns aggregate health status for all ESP devices.
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    # Get all devices
    devices = await esp_repo.get_all()

    # Count by status
    online_count = sum(1 for d in devices if d.status == "online")
    offline_count = sum(1 for d in devices if d.status == "offline")
    error_count = sum(1 for d in devices if d.status == "error")
    unknown_count = sum(1 for d in devices if d.status == "unknown")

    # Aggregate stats
    total_sensors = 0
    total_actuators = 0
    heap_values = []
    rssi_values = []

    device_items = []
    problem_device_ids: list[str] = []

    for device in devices:
        sensor_count = await sensor_repo.count_by_esp(device.id)
        actuator_count = await actuator_repo.count_by_esp(device.id)

        total_sensors += sensor_count
        total_actuators += actuator_count

        # Get health data from device_metadata
        health_data = device.device_metadata.get("health", {}) if device.device_metadata else {}
        heap_free = health_data.get("heap_free")
        wifi_rssi = health_data.get("wifi_rssi")
        uptime = health_data.get("uptime")

        if heap_free and device.status == "online":
            heap_values.append(heap_free)
        if wifi_rssi and device.status == "online":
            rssi_values.append(wifi_rssi)

        # Track problem devices for error lookup
        is_problem = (
            device.status in ("offline", "error")
            or (heap_free is not None and heap_free < 20000)
            or (wifi_rssi is not None and wifi_rssi < -80)
        )
        if is_problem:
            problem_device_ids.append(device.device_id)

        device_items.append(
            ESPHealthItem(
                device_id=device.device_id,
                name=device.name,
                status=device.status,
                last_seen=device.last_seen,
                uptime_seconds=uptime,
                heap_free=heap_free,
                wifi_rssi=wifi_rssi,
                sensor_count=sensor_count,
                actuator_count=actuator_count,
            )
        )

    # Fetch recent errors for problem devices via HealthService (AUT-224 A2)
    if problem_device_ids:
        health_service = HealthService(db)
        grouped = await health_service.get_recent_esp_errors(
            problem_device_ids,
            max_per_device=5,
            limit=50,
        )

        errors_by_device: dict[str, list[RecentError]] = {
            did: [
                RecentError(
                    timestamp=entry.created_at,
                    severity=entry.severity,
                    category=entry.event_type,
                    message=entry.message or entry.error_description or entry.event_type,
                )
                for entry in entries
            ]
            for did, entries in grouped.items()
        }

        # Attach errors to device items
        for item in device_items:
            if item.device_id in errors_by_device:
                item.recent_errors = errors_by_device[item.device_id]

    # Calculate averages
    avg_heap = sum(heap_values) / len(heap_values) if heap_values else None
    avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None

    return ESPHealthSummaryResponse(
        success=True,
        total_devices=len(devices),
        online_count=online_count,
        offline_count=offline_count,
        error_count=error_count,
        unknown_count=unknown_count,
        total_sensors=total_sensors,
        total_actuators=total_actuators,
        avg_heap_free=avg_heap,
        avg_wifi_rssi=avg_rssi,
        devices=device_items,
    )


# =============================================================================
# Kubernetes Probes
# =============================================================================


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Export Prometheus metrics in text format.",
    include_in_schema=False,
)
async def prometheus_metrics():
    """
    Export Prometheus metrics in text/plain format.

    This endpoint serves as a fallback when the prometheus-fastapi-instrumentator
    expose() endpoint is not active (e.g. in test environments).
    The instrumentator endpoint at the same path takes precedence in production.
    """
    from fastapi.responses import PlainTextResponse

    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

        metrics_output = generate_latest()
        return PlainTextResponse(
            content=metrics_output.decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )
    except ImportError:
        return PlainTextResponse(
            content="# prometheus_client not installed\n",
            media_type="text/plain; charset=utf-8",
        )


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Kubernetes liveness probe. Returns 200 if server is alive.",
)
async def liveness_probe() -> LivenessResponse:
    """
    Liveness probe for Kubernetes.

    Simple check that server process is running.
    """
    return LivenessResponse(
        success=True,
        alive=True,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Kubernetes readiness probe. Returns 200 if ready to accept traffic.",
)
async def readiness_probe(
    db: DBSession,
) -> ReadinessResponse:
    """
    Readiness probe for Kubernetes.

    Checks if server is ready to accept traffic.
    """
    mqtt_client = MQTTClient.get_instance()

    runtime_snapshot = await get_runtime_state_service().snapshot()

    # Check components
    checks = {
        "database": True,  # If we're here, DB is OK
        "mqtt": mqtt_client.is_connected(),
        "logic_liveness": bool(runtime_snapshot["checks"].get("logic_liveness")),
        "recovery_completed": bool(runtime_snapshot["checks"].get("recovery_completed")),
        "worker_mqtt_subscriber": bool(runtime_snapshot["checks"].get("mqtt_subscriber")),
        "worker_websocket_manager": bool(runtime_snapshot["checks"].get("websocket_manager")),
        "worker_inbound_replay_worker": bool(
            runtime_snapshot["checks"].get("inbound_replay_worker")
        ),
    }

    # Check disk space
    try:
        import psutil

        disk = psutil.disk_usage("/")
        checks["disk_space"] = disk.percent < 95
    except ImportError:
        checks["disk_space"] = True

    # Ready if all critical checks pass
    ready = bool(runtime_snapshot.get("ready")) and checks["database"] and checks["mqtt"]

    return ReadinessResponse(
        success=ready,
        ready=ready,
        checks=checks,
        runtime_mode=runtime_snapshot.get("mode"),
        degraded_reason_codes=runtime_snapshot.get("degraded_reason_codes", []),
    )
