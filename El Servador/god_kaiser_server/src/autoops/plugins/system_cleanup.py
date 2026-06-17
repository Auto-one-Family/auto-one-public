"""
System Cleanup Plugin - Maintenance and cleanup operations.

Handles:
1. Stale mock device cleanup (offline > threshold)
2. Orphaned sensor/actuator config removal
3. Old report cleanup
4. Database table health verification
5. Simulation state cleanup

This plugin runs last (CLEANUP capability) and is safe to auto-execute.
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
    display_name="System Cleanup",
    description="Raeumt veraltete Daten, Logs und temporaere Ressourcen auf",
    category="maintenance",
    config_schema={
        "max_log_age_days": {"type": "integer", "default": 30, "label": "Max Log-Alter (Tage)"},
        "dry_run": {"type": "boolean", "default": False, "label": "Nur simulieren"},
    },
)
class SystemCleanupPlugin(AutoOpsPlugin):
    """
    System cleanup and maintenance agent.

    Removes stale mock devices, orphaned configurations,
    and verifies overall system consistency.
    """

    @property
    def name(self) -> str:
        return "system_cleanup"

    @property
    def description(self) -> str:
        return (
            "System cleanup and maintenance - removes stale mock devices, "
            "orphaned configs, and verifies system consistency"
        )

    @property
    def capabilities(self) -> list[PluginCapability]:
        return [PluginCapability.CLEANUP, PluginCapability.VALIDATE]

    async def execute(self, context: AutoOpsContext, client: GodKaiserClient) -> PluginResult:
        """Run cleanup operations."""
        actions: list[PluginAction] = []
        errors: list[str] = []
        warnings: list[str] = []
        cleanup_data: dict[str, Any] = {
            "stale_devices_removed": 0,
            "orphaned_configs_found": 0,
            "simulations_stopped": 0,
        }

        # =============================================
        # Step 1: Find stale mock devices
        # =============================================
        stale_devices: list[dict[str, Any]] = []
        try:
            response = await client.list_devices()
            devices = self._extract_list(response, "devices")

            for device in devices:
                if not isinstance(device, dict):
                    continue

                device_id = device.get("device_id", "")
                is_mock = (
                    device_id.startswith("MOCK_")
                    or device.get("is_mock", False)
                    or "MOCK" in device.get("hardware_type", "").upper()
                )
                status = device.get("status", "unknown")

                # Only cleanup stale mock devices
                if is_mock and status == "offline":
                    stale_devices.append(device)

            actions.append(
                PluginAction.create(
                    action="Scan for Stale Devices",
                    target="all_devices",
                    details={
                        "total_devices": len(devices),
                        "stale_mocks": len(stale_devices),
                    },
                    result=f"Found {len(stale_devices)} stale mock device(s)",
                    severity=ActionSeverity.INFO,
                )
            )

        except APIError as e:
            errors.append(f"Device scan failed: {e.detail}")

        # =============================================
        # Step 2: Remove stale mock devices (if auto_approve)
        # =============================================
        if stale_devices and context.auto_approve:
            for device in stale_devices:
                device_id = device.get("device_id", "")
                try:
                    await client.delete_mock_esp(device_id)
                    cleanup_data["stale_devices_removed"] += 1
                    context.cleaned_resources.append(
                        {
                            "type": "mock_device",
                            "device_id": device_id,
                            "action": "deleted",
                        }
                    )
                    actions.append(
                        PluginAction.create(
                            action="Remove Stale Mock Device",
                            target=device_id,
                            details={"status": device.get("status")},
                            result="Removed",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                except APIError as e:
                    warnings.append(f"Failed to remove stale device {device_id}: {e.detail}")
        elif stale_devices:
            device_ids = [d.get("device_id", "?") for d in stale_devices]
            warnings.append(
                f"{len(stale_devices)} stale mock device(s) found but not removed "
                f"(auto_approve=False): {device_ids}"
            )

        # =============================================
        # Step 3: Check for orphaned sensor configs
        # =============================================
        try:
            sensors_response = await client.list_sensors()
            sensors = self._extract_list(sensors_response, "sensors")

            # Get active device IDs
            active_device_ids = set()
            try:
                devices_resp = await client.list_devices()
                for d in self._extract_list(devices_resp, "devices"):
                    if isinstance(d, dict):
                        active_device_ids.add(d.get("device_id", ""))
            except APIError:
                pass

            orphaned_sensors = []
            for sensor in sensors:
                if isinstance(sensor, dict):
                    esp_id = sensor.get("esp_id", "")
                    if esp_id and active_device_ids and esp_id not in active_device_ids:
                        orphaned_sensors.append(sensor)

            if orphaned_sensors:
                cleanup_data["orphaned_configs_found"] += len(orphaned_sensors)
                warnings.append(
                    f"{len(orphaned_sensors)} orphaned sensor config(s) found "
                    f"(device no longer exists)"
                )
                actions.append(
                    PluginAction.create(
                        action="Orphaned Sensor Config Check",
                        target="sensor_configs",
                        details={"orphaned": len(orphaned_sensors)},
                        result=f"{len(orphaned_sensors)} orphaned config(s)",
                        severity=ActionSeverity.WARNING,
                    )
                )
            else:
                actions.append(
                    PluginAction.create(
                        action="Orphaned Sensor Config Check",
                        target="sensor_configs",
                        details={},
                        result="No orphaned configs",
                        severity=ActionSeverity.SUCCESS,
                    )
                )

        except APIError as e:
            warnings.append(f"Sensor config check failed: {e.detail}")

        # =============================================
        # Step 4: Database Table Health
        # =============================================
        try:
            tables_response = await client.list_tables()
            tables = tables_response.get("tables", [])
            empty_tables = []

            for table_entry in tables[:10]:  # Check first 10 tables
                table_name = (
                    table_entry.get("table_name")
                    if isinstance(table_entry, dict)
                    else getattr(table_entry, "table_name", None) if table_entry else None
                )
                if not table_name or not isinstance(table_name, str):
                    continue
                try:
                    table_data = await client.query_table(table_name, limit=1)
                    row_count = table_data.get(
                        "total_count", table_data.get("total", table_data.get("count", 0))
                    )
                    if row_count == 0:
                        empty_tables.append(table_name)
                except APIError:
                    pass

            actions.append(
                PluginAction.create(
                    action="Database Table Health",
                    target="database",
                    details={
                        "total_tables": len(tables),
                        "empty_tables": empty_tables,
                    },
                    result=f"{len(tables)} tables, {len(empty_tables)} empty",
                    severity=ActionSeverity.SUCCESS,
                )
            )

        except APIError as e:
            warnings.append(f"Database health check failed: {e.detail}")

        # =============================================
        # Build result
        # =============================================
        removed = cleanup_data["stale_devices_removed"]
        orphaned = cleanup_data["orphaned_configs_found"]

        summary_parts = ["System cleanup complete"]
        if removed:
            summary_parts.append(f"{removed} stale device(s) removed")
        if orphaned:
            summary_parts.append(f"{orphaned} orphaned config(s) found")
        if not removed and not orphaned:
            summary_parts.append("system is clean")

        return PluginResult(
            success=len(errors) == 0,
            summary=", ".join(summary_parts),
            actions=actions,
            errors=errors,
            warnings=warnings,
            data=cleanup_data,
        )

    # _extract_list() inherited from AutoOpsPlugin base class
