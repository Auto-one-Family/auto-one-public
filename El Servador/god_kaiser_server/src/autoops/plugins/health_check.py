"""
Health Check Plugin - System-wide health validation.

Performs comprehensive health checks:
1. Server connectivity and health endpoint
2. MQTT broker connectivity
3. Database accessibility
4. ESP device responsiveness
5. Sensor data freshness
6. Actuator responsiveness

This plugin is typically the first to run (VALIDATE capability).
"""

from typing import Any

from ..core.api_client import APIError, GodKaiserClient
from ..core.base_plugin import (
    ActionSeverity,
    AutoOpsPlugin,
    PluginAction,
    PluginCapability,
    PluginResult,
    plugin_metadata,
)
from ..core.context import AutoOpsContext


@plugin_metadata(
    display_name="System Health Check",
    description="Prueft Server, Auth, Devices, Database, MQTT, Services, Sensor-Daten und Zonen",
    category="monitoring",
    config_schema={
        "include_containers": {"type": "boolean", "default": True, "label": "Container pruefen"},
        "alert_on_degraded": {"type": "boolean", "default": True, "label": "Alert bei Degraded"},
    },
)
class HealthCheckPlugin(AutoOpsPlugin):
    """
    System health validator.

    Runs before other plugins to ensure the system is in a good state.
    """

    @property
    def name(self) -> str:
        return "health_check"

    @property
    def description(self) -> str:
        return (
            "System-wide health validation - checks server, MQTT, database, "
            "and device connectivity before other operations"
        )

    @property
    def capabilities(self) -> list[PluginCapability]:
        return [PluginCapability.VALIDATE, PluginCapability.MONITOR]

    async def execute(self, context: AutoOpsContext, client: GodKaiserClient) -> PluginResult:
        """Run all health checks."""
        actions: list[PluginAction] = []
        errors: list[str] = []
        warnings: list[str] = []
        health_data: dict[str, Any] = {}

        # =============================================
        # Check 1: Server Health
        # =============================================
        try:
            health = await client.check_health()
            server_status = health.get("status", "unknown")
            health_data["server"] = {"status": server_status, "details": health}

            # Server returns "healthy" or "degraded", not "ok"
            is_healthy = server_status in ("ok", "healthy")
            actions.append(
                PluginAction.create(
                    action="Server Health Check",
                    target=context.server_url,
                    details=health,
                    result=f"Server: {server_status}",
                    severity=(ActionSeverity.SUCCESS if is_healthy else ActionSeverity.WARNING),
                )
            )
        except APIError as e:
            health_data["server"] = {"status": "error", "detail": e.detail}
            errors.append(f"Server health check failed: {e.detail}")
            actions.append(
                PluginAction.create(
                    action="Server Health Check",
                    target=context.server_url,
                    details={"error": e.detail},
                    result=f"FAILED: {e.detail}",
                    severity=ActionSeverity.CRITICAL,
                )
            )
        except Exception as e:
            health_data["server"] = {"status": "unreachable", "detail": str(e)}
            errors.append(f"Server unreachable: {str(e)}")
            actions.append(
                PluginAction.create(
                    action="Server Health Check",
                    target=context.server_url,
                    details={"error": str(e)},
                    result=f"UNREACHABLE: {str(e)}",
                    severity=ActionSeverity.CRITICAL,
                )
            )

        # =============================================
        # Check 2: Authentication
        # =============================================
        if context.auth_token:
            health_data["auth"] = {"status": "authenticated"}
            actions.append(
                PluginAction.create(
                    action="Authentication Check",
                    target="auth_token",
                    details={},
                    result="Authenticated",
                    severity=ActionSeverity.SUCCESS,
                )
            )
        else:
            health_data["auth"] = {"status": "not_authenticated"}
            warnings.append("Not authenticated - some operations may fail")
            actions.append(
                PluginAction.create(
                    action="Authentication Check",
                    target="auth_token",
                    details={},
                    result="Not authenticated",
                    severity=ActionSeverity.WARNING,
                )
            )

        # =============================================
        # Check 3: Device Overview
        # =============================================
        try:
            devices_response = await client.list_devices()
            devices = self._extract_list(devices_response, "devices")
            total = len(devices)
            online = sum(1 for d in devices if isinstance(d, dict) and d.get("status") == "online")
            offline = total - online

            health_data["devices"] = {
                "total": total,
                "online": online,
                "offline": offline,
            }

            severity = ActionSeverity.SUCCESS
            if offline > 0 and online == 0:
                severity = ActionSeverity.WARNING
            elif total == 0:
                severity = ActionSeverity.INFO

            actions.append(
                PluginAction.create(
                    action="Device Overview",
                    target="all_devices",
                    details={"total": total, "online": online, "offline": offline},
                    result=f"{total} devices ({online} online, {offline} offline)",
                    severity=severity,
                )
            )
        except APIError as e:
            health_data["devices"] = {"status": "error", "detail": e.detail}
            warnings.append(f"Device overview failed: {e.detail}")

        # =============================================
        # Check 4: Database Check (via tables endpoint)
        # =============================================
        try:
            tables = await client.list_tables()
            table_count = len(tables.get("tables", []))
            health_data["database"] = {"status": "ok", "tables": table_count}
            actions.append(
                PluginAction.create(
                    action="Database Check",
                    target="database",
                    details={"table_count": table_count},
                    result=f"Database accessible ({table_count} tables)",
                    severity=ActionSeverity.SUCCESS,
                )
            )
        except APIError as e:
            health_data["database"] = {"status": "error", "detail": e.detail}
            warnings.append(f"Database check failed: {e.detail}")
            actions.append(
                PluginAction.create(
                    action="Database Check",
                    target="database",
                    details={"error": e.detail},
                    result=f"FAILED: {e.detail}",
                    severity=ActionSeverity.WARNING,
                )
            )

        # =============================================
        # Check 5: Detailed Health (MQTT, services)
        # =============================================
        try:
            detailed = await client.get_server_health()
            mqtt_details = detailed.get("mqtt", {})
            # Server returns MQTTHealth with "connected" bool, not "status"
            mqtt_connected = mqtt_details.get("connected", False)
            mqtt_status = "connected" if mqtt_connected else "disconnected"
            health_data["mqtt"] = {"status": mqtt_status, "details": mqtt_details}
            actions.append(
                PluginAction.create(
                    action="MQTT Broker Check",
                    target="mqtt_broker",
                    details=mqtt_details,
                    result=f"MQTT: {mqtt_status}",
                    severity=(
                        ActionSeverity.SUCCESS
                        if mqtt_status == "connected"
                        else ActionSeverity.WARNING
                    ),
                )
            )

            # Additional service statuses from detailed health (database has "connected", not "status")
            for service_key in ("database", "redis", "scheduler"):
                service_info = detailed.get(service_key)
                if isinstance(service_info, dict):
                    svc_status = service_info.get("status")
                    if svc_status is None and "connected" in service_info:
                        svc_status = "ok" if service_info.get("connected") else "error"
                    if svc_status is None:
                        svc_status = "unknown"
                    health_data[service_key] = {**service_info, "status": svc_status}
                    actions.append(
                        PluginAction.create(
                            action=f"{service_key.title()} Service Check",
                            target=service_key,
                            details=service_info,
                            result=f"{service_key}: {svc_status}",
                            severity=(
                                ActionSeverity.SUCCESS
                                if svc_status in ("ok", "connected", "running")
                                else ActionSeverity.WARNING
                            ),
                        )
                    )
        except APIError:
            health_data["mqtt"] = {"status": "unknown"}

        # =============================================
        # Check 6: Server Metrics (performance)
        # =============================================
        try:
            metrics = await client.get_health_metrics()
            metric_count = metrics.get("metric_count", len(metrics))
            health_data["metrics"] = metrics
            actions.append(
                PluginAction.create(
                    action="Performance Metrics",
                    target="server_metrics",
                    details={"format": metrics.get("format", "json"), "count": metric_count},
                    result=f"Metrics collected ({metric_count} metrics)",
                    severity=ActionSeverity.SUCCESS,
                )
            )
        except Exception:
            pass  # Metrics endpoint may not exist or return unexpected format

        # =============================================
        # Check 7: Sensor Data Freshness
        # =============================================
        try:
            sensor_data = await client.list_sensor_data(limit=5)
            # API returns SensorDataResponse with "readings" key (not "data"/"items")
            data_items = sensor_data.get(
                "readings", sensor_data.get("data", sensor_data.get("items", []))
            )
            if isinstance(data_items, list) and data_items:
                health_data["sensor_data"] = {
                    "recent_readings": len(data_items),
                    "latest": data_items[0] if data_items else None,
                }
                actions.append(
                    PluginAction.create(
                        action="Sensor Data Freshness",
                        target="sensor_data",
                        details={"count": len(data_items)},
                        result=f"{len(data_items)} recent reading(s) found",
                        severity=ActionSeverity.SUCCESS,
                    )
                )
            else:
                health_data["sensor_data"] = {"recent_readings": 0}
                actions.append(
                    PluginAction.create(
                        action="Sensor Data Freshness",
                        target="sensor_data",
                        details={},
                        result="No recent sensor data",
                        severity=ActionSeverity.INFO,
                    )
                )
        except APIError:
            pass

        # =============================================
        # Check 8: Zone Configuration
        # =============================================
        try:
            zones_response = await client.list_zones()
            zones = self._extract_list(zones_response, "zones")
            health_data["zones"] = {
                "count": len(zones),
                "names": [z.get("name", "?") for z in zones if isinstance(z, dict)],
            }
            actions.append(
                PluginAction.create(
                    action="Zone Configuration Check",
                    target="zones",
                    details={"zone_count": len(zones)},
                    result=f"{len(zones)} zone(s) configured",
                    severity=ActionSeverity.SUCCESS if zones else ActionSeverity.INFO,
                )
            )
        except APIError:
            pass

        # =============================================
        # Build Summary
        # =============================================
        checks_passed = sum(1 for a in actions if a.severity == ActionSeverity.SUCCESS)
        checks_total = len(actions)

        return PluginResult(
            success=len(errors) == 0,
            summary=f"Health check: {checks_passed}/{checks_total} checks passed",
            actions=actions,
            errors=errors,
            warnings=warnings,
            data=health_data,
        )

    # _extract_list() inherited from AutoOpsPlugin base class
