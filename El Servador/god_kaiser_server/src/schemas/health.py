"""
Health Check Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🟡 HIGH
Status: IMPLEMENTED

Provides:
- Basic health check response models
- Detailed system health models
- ESP health summary models
- Prometheus metrics models

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 191-195)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import BaseResponse

# =============================================================================
# Component Health Status
# =============================================================================


class ComponentHealth(BaseModel):
    """
    Health status of a single component.
    """

    name: str = Field(..., description="Component name")
    status: str = Field(
        ...,
        pattern=r"^(healthy|degraded|unhealthy|unknown)$",
        description="Health status",
    )
    message: Optional[str] = Field(None, description="Status message or error")
    latency_ms: Optional[float] = Field(
        None,
        description="Response latency (ms)",
        ge=0,
    )
    last_check: Optional[datetime] = Field(None, description="Last check timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional info")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "database",
                "status": "healthy",
                "message": "PostgreSQL connection OK",
                "latency_ms": 5.2,
                "last_check": "2025-01-01T12:00:00Z",
            }
        }
    )


# =============================================================================
# Basic Health Check
# =============================================================================


class HealthResponse(BaseResponse):
    """
    Basic health check response.

    Used by load balancers and monitoring systems.
    """

    status: str = Field(
        ...,
        pattern=r"^(healthy|degraded|unhealthy)$",
        description="Overall system status",
    )
    version: str = Field(
        ...,
        description="Server version",
    )
    environment: str = Field(
        ...,
        description="Environment (development, staging, production)",
    )
    uptime_seconds: int = Field(
        ...,
        description="Server uptime in seconds",
        ge=0,
    )
    timestamp: datetime = Field(
        ...,
        description="Current server timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "status": "healthy",
                "version": "2.0.0",
                "environment": "production",
                "uptime_seconds": 86400,
                "timestamp": "2025-01-01T12:00:00Z",
            }
        }
    )


# =============================================================================
# Detailed Health Check
# =============================================================================


class DatabaseHealth(BaseModel):
    """Database health details."""

    connected: bool = Field(..., description="Connection status")
    pool_size: int = Field(..., description="Connection pool size", ge=0)
    pool_available: int = Field(..., description="Available connections", ge=0)
    latency_ms: Optional[float] = Field(None, description="Query latency (ms)")
    database_type: str = Field(..., description="Database type (PostgreSQL, SQLite)")


class MQTTHealth(BaseModel):
    """MQTT broker health details."""

    connected: bool = Field(..., description="Connection status")
    broker_host: str = Field(..., description="Broker hostname")
    broker_port: int = Field(..., description="Broker port")
    subscriptions: int = Field(..., description="Active subscriptions", ge=0)
    messages_received: int = Field(..., description="Total messages received", ge=0)
    messages_published: int = Field(..., description="Total messages published", ge=0)
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")


class WebSocketHealth(BaseModel):
    """WebSocket health details."""

    active_connections: int = Field(..., description="Active connections", ge=0)
    total_messages_sent: int = Field(..., description="Total messages sent", ge=0)


class SystemResourceHealth(BaseModel):
    """System resource health details."""

    cpu_percent: float = Field(
        ...,
        description="CPU usage percentage",
        ge=0,
        le=100,
    )
    memory_percent: float = Field(
        ...,
        description="Memory usage percentage",
        ge=0,
        le=100,
    )
    memory_used_mb: float = Field(
        ...,
        description="Memory used (MB)",
        ge=0,
    )
    memory_total_mb: float = Field(
        ...,
        description="Total memory (MB)",
        ge=0,
    )
    disk_percent: float = Field(
        ...,
        description="Disk usage percentage",
        ge=0,
        le=100,
    )
    disk_free_gb: float = Field(
        ...,
        description="Free disk space (GB)",
        ge=0,
    )


class CircuitBreakerHealth(BaseModel):
    """Health status of an individual circuit breaker."""

    state: str = Field(..., description="Current state (closed/open/half_open)")
    failures: int = Field(..., description="Current failure count", ge=0)
    failure_threshold: int = Field(..., description="Threshold before opening", ge=1)
    last_failure: Optional[float] = Field(None, description="Timestamp of last failure")
    forced_open: bool = Field(False, description="Whether manually forced open")


class ResilienceSummary(BaseModel):
    """Summary counts of circuit breaker states."""

    total: int = Field(..., description="Total registered breakers", ge=0)
    closed: int = Field(0, description="Breakers in closed (healthy) state", ge=0)
    open: int = Field(0, description="Breakers in open (failing) state", ge=0)
    half_open: int = Field(0, description="Breakers in half-open (recovering) state", ge=0)


class ResilienceHealth(BaseModel):
    """Resilience status with circuit breaker health."""

    healthy: bool = Field(..., description="True if no circuit breakers are OPEN")
    breakers: Dict[str, CircuitBreakerHealth] = Field(
        default_factory=dict,
        description="Individual circuit breaker states",
    )
    summary: ResilienceSummary = Field(..., description="Aggregate breaker state counts")


class DetailedHealthResponse(BaseResponse):
    """
    Detailed health check response.

    Includes component-level health information.
    """

    status: str = Field(
        ...,
        pattern=r"^(healthy|degraded|unhealthy)$",
        description="Overall system status",
    )
    version: str = Field(..., description="Server version")
    environment: str = Field(..., description="Environment")
    uptime_seconds: int = Field(..., description="Server uptime", ge=0)
    uptime_formatted: str = Field(
        ...,
        description="Human-readable uptime (e.g., '1d 2h 30m')",
    )
    timestamp: datetime = Field(..., description="Current timestamp")

    # Component health
    database: DatabaseHealth = Field(..., description="Database health")
    mqtt: MQTTHealth = Field(..., description="MQTT broker health")
    websocket: WebSocketHealth = Field(..., description="WebSocket health")
    system: SystemResourceHealth = Field(..., description="System resources")
    resilience: Optional[ResilienceHealth] = Field(
        None, description="Circuit breaker resilience status"
    )

    # Additional components
    components: List[ComponentHealth] = Field(
        default_factory=list,
        description="Additional component health",
    )

    # Warnings/Issues
    warnings: List[str] = Field(
        default_factory=list,
        description="System warnings",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "status": "healthy",
                "version": "2.0.0",
                "environment": "production",
                "uptime_seconds": 86400,
                "uptime_formatted": "1d 0h 0m",
                "timestamp": "2025-01-01T12:00:00Z",
                "database": {
                    "connected": True,
                    "pool_size": 20,
                    "pool_available": 18,
                    "latency_ms": 5.2,
                    "database_type": "PostgreSQL",
                },
                "mqtt": {
                    "connected": True,
                    "broker_host": "localhost",
                    "broker_port": 8883,
                    "subscriptions": 5,
                    "messages_received": 10000,
                    "messages_published": 500,
                    "last_message_at": "2025-01-01T12:00:00Z",
                },
                "websocket": {"active_connections": 3, "total_messages_sent": 5000},
                "system": {
                    "cpu_percent": 25.5,
                    "memory_percent": 45.0,
                    "memory_used_mb": 1800,
                    "memory_total_mb": 4000,
                    "disk_percent": 60.0,
                    "disk_free_gb": 40.0,
                },
                "components": [],
                "warnings": [],
            }
        }
    )


# =============================================================================
# ESP Health Summary
# =============================================================================


class RecentError(BaseModel):
    """Recent error/event for an ESP device."""

    timestamp: datetime = Field(..., description="Event timestamp")
    severity: str = Field(..., description="Event severity (info, warning, error, critical)")
    category: str = Field(..., description="Event category (heartbeat, mqtt, config, etc.)")
    message: str = Field(..., description="Human-readable error message")


class ESPHealthItem(BaseModel):
    """
    Single ESP health status.
    """

    device_id: str = Field(..., description="ESP device ID")
    name: Optional[str] = Field(None, description="Device name")
    status: str = Field(
        ...,
        pattern=r"^(online|offline|error|unknown|pending_approval|approved|rejected)$",
        description="Device status",
    )
    last_seen: Optional[datetime] = Field(None, description="Last heartbeat")
    uptime_seconds: Optional[int] = Field(None, description="Device uptime", ge=0)
    heap_free: Optional[int] = Field(None, description="Free heap (bytes)", ge=0)
    wifi_rssi: Optional[int] = Field(None, description="WiFi RSSI (dBm)")
    sensor_count: int = Field(0, description="Active sensors", ge=0)
    actuator_count: int = Field(0, description="Active actuators", ge=0)
    recent_errors: List[RecentError] = Field(
        default_factory=list,
        description="Recent error events for this device (max 5)",
    )


class ESPHealthSummaryResponse(BaseResponse):
    """
    Summary of all ESP device health.
    """

    total_devices: int = Field(..., description="Total registered devices", ge=0)
    online_count: int = Field(..., description="Online devices", ge=0)
    offline_count: int = Field(..., description="Offline devices", ge=0)
    error_count: int = Field(..., description="Devices with errors", ge=0)
    unknown_count: int = Field(..., description="Unknown status devices", ge=0)

    # Aggregate stats
    total_sensors: int = Field(..., description="Total active sensors", ge=0)
    total_actuators: int = Field(..., description="Total active actuators", ge=0)
    avg_heap_free: Optional[float] = Field(
        None,
        description="Average free heap across online devices",
    )
    avg_wifi_rssi: Optional[float] = Field(
        None,
        description="Average WiFi RSSI across online devices",
    )

    # Per-device list
    devices: List[ESPHealthItem] = Field(
        default_factory=list,
        description="Per-device health",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "total_devices": 10,
                "online_count": 8,
                "offline_count": 1,
                "error_count": 1,
                "unknown_count": 0,
                "total_sensors": 25,
                "total_actuators": 15,
                "avg_heap_free": 200000,
                "avg_wifi_rssi": -55,
                "devices": [
                    {
                        "device_id": "ESP_12AB34CD",
                        "name": "Greenhouse Node 1",
                        "status": "online",
                        "last_seen": "2025-01-01T12:00:00Z",
                        "uptime_seconds": 86400,
                        "heap_free": 200000,
                        "wifi_rssi": -55,
                        "sensor_count": 3,
                        "actuator_count": 2,
                    }
                ],
            }
        }
    )


# =============================================================================
# Prometheus Metrics
# =============================================================================


class MetricsResponse(BaseModel):
    """
    Prometheus-style metrics response.

    Text format compatible with Prometheus scraper.
    """

    content_type: str = Field(
        "text/plain; version=0.0.4",
        description="Content type for Prometheus",
    )
    metrics: str = Field(
        ...,
        description="Prometheus metrics in text format",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content_type": "text/plain; version=0.0.4",
                "metrics": """# HELP god_kaiser_uptime_seconds Server uptime
# TYPE god_kaiser_uptime_seconds gauge
god_kaiser_uptime_seconds 86400

# HELP god_kaiser_esp_online_total Online ESP devices
# TYPE god_kaiser_esp_online_total gauge
god_kaiser_esp_online_total 8

# HELP god_kaiser_mqtt_messages_total MQTT messages processed
# TYPE god_kaiser_mqtt_messages_total counter
god_kaiser_mqtt_messages_total{direction="received"} 10000
god_kaiser_mqtt_messages_total{direction="published"} 500
""",
            }
        }
    )


# =============================================================================
# Readiness / Liveness Probes
# =============================================================================


class LivenessResponse(BaseResponse):
    """
    Kubernetes liveness probe response.

    Simple check that server is running.
    """

    alive: bool = Field(
        True,
        description="Server is alive",
    )


class ReadinessResponse(BaseResponse):
    """
    Kubernetes readiness probe response.

    Checks if server is ready to accept traffic.
    """

    ready: bool = Field(
        ...,
        description="Server is ready to accept traffic",
    )
    checks: Dict[str, bool] = Field(
        ...,
        description="Individual readiness checks",
    )
    runtime_mode: Optional[str] = Field(
        default=None,
        description="Runtime mode state machine status",
    )
    degraded_reason_codes: List[str] = Field(
        default_factory=list,
        description="Machine-readable degraded reason codes",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "ready": True,
                "checks": {"database": True, "mqtt": True, "disk_space": True},
            }
        }
    )
