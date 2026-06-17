"""
Debug & Fix Plugin - Autonomous diagnosis and repair.

This plugin acts like an expert debugging through the system:

1. DIAGNOSE: Scans all ESPs, sensors, actuators for issues
2. DOCUMENT: Records every finding with full context
3. FIX: Attempts automatic repair where safe
4. VERIFY: Confirms fixes worked

Issue Categories:
- Device Issues: Offline, no heartbeat, wrong state
- Sensor Issues: No data, stale data, out-of-range values, misconfigured
- Actuator Issues: Emergency-stopped, no response, wrong state
- Zone Issues: Unassigned devices, empty zones
- System Issues: MQTT disconnect, high error rate, memory issues
"""

import json
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel

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

_logger = logging.getLogger(__name__)


class DebugFinding(BaseModel):
    root_cause: str
    affected_components: list[str]
    code_references: list[dict]  # {"file": str, "line": int, "symbol": str}
    recommended_actions: list[str]
    auto_fix_applied: bool = False
    fix_description: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "medium"
    evidence: list[str] = []


_DEBUG_TOOLS = [
    {
        "name": "get_esp_error_history",
        "description": "Lese die letzten N Error-Events eines ESPs aus audit_logs",
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["esp_id"],
        },
    },
    {
        "name": "get_logic_rules_for_esp",
        "description": "Alle aktiven Logic Rules die diesen ESP als Condition-Source oder Action-Target haben",
        "input_schema": {
            "type": "object",
            "properties": {"esp_id": {"type": "string"}},
            "required": ["esp_id"],
        },
    },
    {
        "name": "get_offline_mode_state",
        "description": "Aktueller Online/Offline-Status eines ESPs inklusive letzter Heartbeat-Zeit",
        "input_schema": {
            "type": "object",
            "properties": {"esp_id": {"type": "string"}},
            "required": ["esp_id"],
        },
    },
    {
        "name": "get_sensor_last_values",
        "description": "Letzte Messwerte aller Sensoren eines ESPs",
        "input_schema": {
            "type": "object",
            "properties": {
                "esp_id": {"type": "string"},
                "hours": {"type": "integer", "default": 24},
            },
            "required": ["esp_id"],
        },
    },
]


class DiagnosticIssue:
    """A diagnosed issue with severity and suggested fix."""

    def __init__(
        self,
        category: str,
        severity: str,
        target: str,
        description: str,
        suggested_fix: str = "",
        auto_fixable: bool = False,
        fix_action: str = "",
        details: dict[str, Any] | None = None,
    ):
        self.category = category
        self.severity = severity
        self.target = target
        self.description = description
        self.suggested_fix = suggested_fix
        self.auto_fixable = auto_fixable
        self.fix_action = fix_action
        self.details = details or {}


@plugin_metadata(
    display_name="Debug & Auto-Fix",
    description="Diagnostiziert Probleme (Devices, Sensors, Actuators, Zones) und behebt sie automatisch",
    category="diagnostics",
    config_schema={
        "auto_fix": {"type": "boolean", "default": True, "label": "Automatisch beheben"},
        "include_zones": {
            "type": "boolean",
            "default": True,
            "label": "Zonen-Diagnose einschliessen",
        },
    },
)
class DebugFixPlugin(AutoOpsPlugin):
    """
    Autonomous debug and fix agent.

    Scans the entire system, identifies issues, fixes what it can,
    and documents everything with full context.
    """

    @property
    def name(self) -> str:
        return "debug_fix"

    @property
    def description(self) -> str:
        return (
            "Autonomous debug & fix agent - scans system for issues, "
            "diagnoses problems, applies fixes, and verifies repairs"
        )

    @property
    def capabilities(self) -> list[PluginCapability]:
        return [
            PluginCapability.DIAGNOSE,
            PluginCapability.FIX,
            PluginCapability.DOCUMENT,
        ]

    async def execute(self, context: AutoOpsContext, client: GodKaiserClient) -> PluginResult:
        """Run full diagnostic scan, fix issues, verify."""
        actions: list[PluginAction] = []
        all_issues: list[DiagnosticIssue] = []
        fixed_issues: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        # =============================================
        # Phase 1: DIAGNOSE - Scan everything
        # =============================================
        actions.append(
            PluginAction.create(
                action="Start Diagnostic Scan",
                target="system",
                details={},
                result="Scanning...",
                severity=ActionSeverity.INFO,
            )
        )

        # Scan devices
        device_issues = await self._scan_devices(client)
        all_issues.extend(device_issues)

        # Scan sensors
        sensor_issues = await self._scan_sensors(client, context)
        all_issues.extend(sensor_issues)

        # Scan actuators
        actuator_issues = await self._scan_actuators(client, context)
        all_issues.extend(actuator_issues)

        # Scan zones
        zone_issues = await self._scan_zones(client)
        all_issues.extend(zone_issues)

        actions.append(
            PluginAction.create(
                action="Diagnostic Scan Complete",
                target="system",
                details={
                    "total_issues": len(all_issues),
                    "by_category": self._count_by_category(all_issues),
                    "by_severity": self._count_by_severity(all_issues),
                },
                result=f"Found {len(all_issues)} issue(s)",
                severity=ActionSeverity.INFO if not all_issues else ActionSeverity.WARNING,
            )
        )

        # Record all issues
        for issue in all_issues:
            context.diagnosed_issues.append(
                {
                    "category": issue.category,
                    "severity": issue.severity,
                    "target": issue.target,
                    "description": issue.description,
                    "auto_fixable": issue.auto_fixable,
                    "suggested_fix": issue.suggested_fix,
                }
            )

        # =============================================
        # Phase 1.5: LLM Deep Analysis (optional)
        # =============================================
        from ...services.ai_service import ai_service as _ai_svc

        llm_finding: Optional[DebugFinding] = None
        if _ai_svc.is_available() and all_issues:
            try:
                esp_id = getattr(all_issues[0], "device_id", None) or context.data.get(
                    "esp_id", "unknown"
                )
                llm_finding = await self._run_llm_debug(esp_id, all_issues, client)
            except Exception:
                _logger.debug("LLM debug failed (non-critical)", exc_info=True)

        # =============================================
        # Phase 2: FIX - Auto-fix what's safe
        # =============================================
        auto_fixable = [i for i in all_issues if i.auto_fixable]
        if auto_fixable:
            actions.append(
                PluginAction.create(
                    action="Start Auto-Fix",
                    target="system",
                    details={"fixable_count": len(auto_fixable)},
                    result=f"Attempting {len(auto_fixable)} auto-fix(es)",
                    severity=ActionSeverity.INFO,
                )
            )

            for issue in auto_fixable:
                fix_result = await self._apply_fix(issue, client, context)
                if fix_result:
                    fixed_issues.append(
                        f"[{issue.category}] {issue.target}: {issue.description} -> FIXED"
                    )
                    context.fixed_issues.append(
                        {
                            "category": issue.category,
                            "target": issue.target,
                            "description": issue.description,
                            "fix_applied": issue.fix_action,
                        }
                    )
                    actions.append(
                        PluginAction.create(
                            action=f"Fix: {issue.fix_action}",
                            target=issue.target,
                            details=issue.details,
                            result="Fixed",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                else:
                    errors.append(
                        f"Auto-fix failed for [{issue.category}] {issue.target}: "
                        f"{issue.description}"
                    )
                    actions.append(
                        PluginAction.create(
                            action=f"Fix Failed: {issue.fix_action}",
                            target=issue.target,
                            details=issue.details,
                            result="Fix failed",
                            severity=ActionSeverity.ERROR,
                        )
                    )

        # Manual-fix issues become warnings
        manual_fixes = [i for i in all_issues if not i.auto_fixable]
        for issue in manual_fixes:
            warnings.append(
                f"[{issue.severity}] {issue.target}: {issue.description} "
                f"-> Manual fix needed: {issue.suggested_fix}"
            )

        # =============================================
        # Phase 3: Build result
        # =============================================
        total = len(all_issues)
        fixed = len(fixed_issues)
        remaining = total - fixed

        summary_parts = [f"Scanned system: {total} issue(s) found"]
        if fixed:
            summary_parts.append(f"{fixed} auto-fixed")
        if remaining:
            summary_parts.append(f"{remaining} remaining")
        if not all_issues:
            summary_parts = ["System is healthy - no issues found"]

        result_data: dict = {
            "total_issues": total,
            "auto_fixed": fixed,
            "remaining": remaining,
            "issues_by_category": self._count_by_category(all_issues),
            "issues_by_severity": self._count_by_severity(all_issues),
            "fixed_issues": fixed_issues,
        }
        if llm_finding is not None:
            result_data["llm_finding"] = llm_finding.model_dump()

        return PluginResult(
            success=len(errors) == 0,
            summary=", ".join(summary_parts),
            actions=actions,
            errors=errors,
            warnings=warnings,
            data=result_data,
        )

    # =========================================================================
    # Scan Methods
    # =========================================================================

    async def _scan_devices(self, client: GodKaiserClient) -> list[DiagnosticIssue]:
        """Scan all ESP devices for issues."""
        issues: list[DiagnosticIssue] = []

        try:
            response = await client.list_devices()
            devices = self._extract_list(response, "devices")

            for device in devices:
                if not isinstance(device, dict):
                    continue

                # API may return device_id or esp_id (both valid for Mock ESPs)
                device_id = device.get("device_id") or device.get("esp_id") or "unknown"
                status = device.get("status", "unknown")
                system_state = device.get("system_state", "unknown")

                # Check offline devices
                if status == "offline":
                    last_hb = device.get("last_heartbeat", "never")
                    issues.append(
                        DiagnosticIssue(
                            category="device",
                            severity="warning",
                            target=device_id,
                            description=f"Device is offline (last heartbeat: {last_hb})",
                            suggested_fix="Trigger heartbeat or check device connectivity",
                            auto_fixable=self._is_mock_device(device),
                            fix_action="trigger_heartbeat",
                            details={"device_id": device_id, "last_heartbeat": last_hb},
                        )
                    )

                # Check error state
                if system_state == "ERROR":
                    issues.append(
                        DiagnosticIssue(
                            category="device",
                            severity="error",
                            target=device_id,
                            description=f"Device is in ERROR state",
                            suggested_fix="Check device logs, consider restart",
                            auto_fixable=self._is_mock_device(device),
                            fix_action="reset_state_to_operational",
                            details={"device_id": device_id, "system_state": system_state},
                        )
                    )

                # Check no sensors and no actuators
                sensors = device.get("sensors", [])
                actuators = device.get("actuators", [])
                if not sensors and not actuators:
                    issues.append(
                        DiagnosticIssue(
                            category="device",
                            severity="info",
                            target=device_id,
                            description="Device has no sensors or actuators configured",
                            suggested_fix="Add sensors/actuators via ESP config",
                        )
                    )

                # Check memory
                heap_free = device.get("heap_free")
                if heap_free is not None and heap_free < 20000:
                    issues.append(
                        DiagnosticIssue(
                            category="device",
                            severity="warning",
                            target=device_id,
                            description=f"Low memory: {heap_free} bytes free",
                            suggested_fix="Reduce sensor count or increase heap allocation",
                        )
                    )

        except APIError as e:
            issues.append(
                DiagnosticIssue(
                    category="system",
                    severity="error",
                    target="device_scan",
                    description=f"Failed to scan devices: {e.detail}",
                )
            )

        return issues

    async def _scan_sensors(
        self, client: GodKaiserClient, context: AutoOpsContext
    ) -> list[DiagnosticIssue]:
        """Scan all sensors for issues including data freshness."""
        issues: list[DiagnosticIssue] = []

        try:
            response = await client.list_sensors()
            sensors = self._extract_list(response, "sensors")

            for sensor in sensors:
                if not isinstance(sensor, dict):
                    continue

                esp_id = sensor.get("esp_id", "unknown")
                gpio = sensor.get("gpio", -1)
                sensor_type = sensor.get("sensor_type", "unknown")
                target = f"{esp_id}/GPIO:{gpio}"

                # Check if sensor is disabled
                if not sensor.get("enabled", True):
                    issues.append(
                        DiagnosticIssue(
                            category="sensor",
                            severity="info",
                            target=target,
                            description=f"Sensor {sensor_type} is disabled",
                            suggested_fix="Enable sensor if it should be active",
                            auto_fixable=False,
                        )
                    )

                # Check for missing calibration (sensors that need it)
                if sensor_type in ("ph", "ec") and not sensor.get("calibration_data"):
                    issues.append(
                        DiagnosticIssue(
                            category="sensor",
                            severity="info",
                            target=target,
                            description=f"Sensor {sensor_type} has no calibration data",
                            suggested_fix="Calibrate sensor for accurate readings",
                        )
                    )

            # Check sensor data freshness
            try:
                data_response = await client.list_sensor_data(limit=20)
                # API returns SensorDataResponse with "readings" key (not "data"/"items")
                data_items = data_response.get(
                    "readings", data_response.get("data", data_response.get("items", []))
                )
                if isinstance(data_items, list):
                    # Group by esp_id to check which devices have recent data
                    # Note: readings may not include esp_id per item - only when API adds it
                    devices_with_data = set()
                    for item in data_items:
                        if isinstance(item, dict) and item.get("esp_id"):
                            devices_with_data.add(item.get("esp_id", ""))

                    # Only run devices_without_data check when we can determine devices_with_data
                    configured_devices = set()
                    for s in sensors:
                        if isinstance(s, dict) and s.get("enabled", True):
                            configured_devices.add(s.get("esp_id", ""))

                    devices_without_data = configured_devices - devices_with_data
                    if devices_with_data and devices_without_data:
                        issues.append(
                            DiagnosticIssue(
                                category="sensor",
                                severity="warning",
                                target="sensor_data",
                                description=(
                                    f"{len(devices_without_data)} device(s) with sensors "
                                    f"but no recent data: {list(devices_without_data)[:5]}"
                                ),
                                suggested_fix="Check device connectivity and sensor configuration",
                            )
                        )
            except APIError:
                pass  # Data endpoint may not be accessible

        except APIError as e:
            issues.append(
                DiagnosticIssue(
                    category="system",
                    severity="warning",
                    target="sensor_scan",
                    description=f"Failed to scan sensors: {e.detail}",
                )
            )

        return issues

    async def _scan_actuators(
        self, client: GodKaiserClient, context: AutoOpsContext
    ) -> list[DiagnosticIssue]:
        """Scan all actuators for issues."""
        issues: list[DiagnosticIssue] = []

        try:
            response = await client.list_actuators()
            actuators = self._extract_list(response, "actuators")

            for actuator in actuators:
                if not isinstance(actuator, dict):
                    continue

                esp_id = actuator.get("esp_id", "unknown")
                gpio = actuator.get("gpio", -1)
                target = f"{esp_id}/GPIO:{gpio}"

                # Check emergency-stopped actuators
                if actuator.get("emergency_stopped", False):
                    issues.append(
                        DiagnosticIssue(
                            category="actuator",
                            severity="warning",
                            target=target,
                            description="Actuator is emergency-stopped",
                            suggested_fix="Review emergency condition and clear E-stop if safe",
                            auto_fixable=False,  # E-stop clearing requires manual approval
                        )
                    )

        except APIError as e:
            issues.append(
                DiagnosticIssue(
                    category="system",
                    severity="warning",
                    target="actuator_scan",
                    description=f"Failed to scan actuators: {e.detail}",
                )
            )

        return issues

    async def _scan_zones(self, client: GodKaiserClient) -> list[DiagnosticIssue]:
        """Scan zones for issues."""
        issues: list[DiagnosticIssue] = []

        try:
            response = await client.list_devices()
            devices = self._extract_list(response, "devices")

            # Check for unassigned devices
            unassigned = [d for d in devices if isinstance(d, dict) and not d.get("zone_id")]
            if unassigned:
                device_ids = [d.get("device_id", "?") for d in unassigned]
                issues.append(
                    DiagnosticIssue(
                        category="zone",
                        severity="info",
                        target="unassigned_devices",
                        description=f"{len(unassigned)} device(s) without zone: {device_ids}",
                        suggested_fix="Assign devices to zones for better organization",
                    )
                )

        except APIError:
            pass

        return issues

    # =========================================================================
    # Fix Methods
    # =========================================================================

    async def _apply_fix(
        self,
        issue: DiagnosticIssue,
        client: GodKaiserClient,
        context: AutoOpsContext,
    ) -> bool:
        """Apply an automatic fix. Returns True if successful."""
        device_id = issue.details.get("device_id") or issue.details.get("esp_id") or ""

        try:
            if issue.fix_action == "trigger_heartbeat" and device_id:
                await client.trigger_heartbeat(device_id)
                return True

            if issue.fix_action == "reset_state_to_operational" and device_id:
                await client.set_mock_state(device_id, "OPERATIONAL")
                return True

        except APIError:
            return False

        return False

    # =========================================================================
    # LLM Debug Methods
    # =========================================================================

    async def _execute_debug_tool(
        self,
        tool_name: str,
        tool_input: dict,
        client: "GodKaiserClient",
    ) -> str:
        """Execute a debug tool call and return JSON-serialised result."""
        try:
            if tool_name == "get_esp_error_history":
                esp_id = tool_input["esp_id"]
                limit = tool_input.get("limit", 50)
                response = await client.list_audit_logs(limit=limit)
                logs = self._extract_list(response, "logs")
                return json.dumps(logs[:limit])

            if tool_name == "get_logic_rules_for_esp":
                esp_id = tool_input["esp_id"]
                response = await client.list_logic_rules()
                rules = self._extract_list(response, "rules")
                esp_rules = [r for r in rules if esp_id in json.dumps(r)]
                return json.dumps(esp_rules[:10])

            if tool_name == "get_offline_mode_state":
                esp_id = tool_input["esp_id"]
                device = await client.get_device(esp_id)
                payload = device if isinstance(device, dict) else {}
                return json.dumps(
                    {
                        "status": payload.get("status", "unknown"),
                        "last_seen": payload.get("last_seen"),
                    }
                )

            if tool_name == "get_sensor_last_values":
                esp_id = tool_input["esp_id"]
                response = await client.list_sensors(esp_id=esp_id)
                sensors = self._extract_list(response, "sensors")
                return json.dumps(sensors[:20])

        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({"error": f"unknown tool: {tool_name}"})

    async def _run_llm_debug(
        self,
        esp_id: str,
        issues: list,  # list[DiagnosticIssue]
        client: "GodKaiserClient",
    ) -> Optional[DebugFinding]:
        """Run an agentic LLM debug loop via ClaudeDebugAgent (AUT-270)."""
        from ...services.claude_debug_agent import ClaudeDebugAgent

        agent = ClaudeDebugAgent(client=client, db_session=None)
        issue_descriptions = [getattr(i, "description", str(i)) for i in issues]
        message = f"Analysiere ESP {esp_id}. Bekannte Probleme: {issue_descriptions}"
        text = await agent.run_batch(message, session_id=esp_id, esp_id=esp_id)
        if text:
            return DebugFinding(
                root_cause=text[:500],
                affected_components=[f"ESP {esp_id}"],
                code_references=[],
                recommended_actions=["Manuelle Analyse empfohlen"],
                evidence=issue_descriptions,
            )
        return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _is_mock_device(self, device: dict) -> bool:
        """Check if a device is a mock device (safe to auto-fix)."""
        device_id = device.get("device_id", "")
        hardware = device.get("hardware_type", "")
        return (
            device_id.startswith("MOCK_")
            or "MOCK" in hardware.upper()
            or device.get("is_mock", False)
        )

    # _extract_list() inherited from AutoOpsPlugin base class

    def _count_by_category(self, issues: list[DiagnosticIssue]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.category] = counts.get(issue.category, 0) + 1
        return counts

    def _count_by_severity(self, issues: list[DiagnosticIssue]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts
