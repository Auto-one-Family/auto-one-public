"""
AutoOps Plugin Base Classes

Every AutoOps capability is implemented as a plugin that:
1. Declares its capabilities (what it can do)
2. Validates preconditions before executing
3. Executes autonomously through the API
4. Reports results with full documentation
5. Can ask questions when uncertain (fallback)

Usage:
    class MyPlugin(AutoOpsPlugin):
        @property
        def name(self) -> str:
            return "my_plugin"

        @property
        def capabilities(self) -> list[PluginCapability]:
            return [PluginCapability.CONFIGURE, PluginCapability.DIAGNOSE]

        async def execute(self, context, client) -> PluginResult:
            # ... do work ...
            return PluginResult.success("Done", actions=[...])
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class PluginCapability(str, Enum):
    """What a plugin can do."""

    CONFIGURE = "configure"  # Can configure ESP devices
    DIAGNOSE = "diagnose"  # Can diagnose problems
    FIX = "fix"  # Can fix problems
    VALIDATE = "validate"  # Can validate system state
    MONITOR = "monitor"  # Can monitor system health
    DOCUMENT = "document"  # Can generate documentation
    TEST = "test"  # Can run tests
    CLEANUP = "cleanup"  # Can clean up resources


class ActionSeverity(str, Enum):
    """Severity of an action taken."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    SUCCESS = "success"


@dataclass
class PluginAction:
    """A single action taken by a plugin, fully documented."""

    timestamp: str
    action: str
    target: str
    details: dict[str, Any]
    result: str
    severity: ActionSeverity = ActionSeverity.INFO
    api_endpoint: Optional[str] = None
    api_method: Optional[str] = None
    api_response_code: Optional[int] = None

    @classmethod
    def create(
        cls,
        action: str,
        target: str,
        details: dict[str, Any] | None = None,
        result: str = "",
        severity: ActionSeverity = ActionSeverity.INFO,
        api_endpoint: str | None = None,
        api_method: str | None = None,
        api_response_code: int | None = None,
    ) -> "PluginAction":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            target=target,
            details=details or {},
            result=result,
            severity=severity,
            api_endpoint=api_endpoint,
            api_method=api_method,
            api_response_code=api_response_code,
        )


@dataclass
class PluginQuestion:
    """A question the plugin needs to ask the user."""

    question: str
    options: list[str] | None = None
    default: str | None = None
    required: bool = True
    context: str = ""


@dataclass
class PluginResult:
    """Result of a plugin execution."""

    success: bool
    summary: str
    actions: list[PluginAction] = field(default_factory=list)
    questions: list[PluginQuestion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    needs_user_input: bool = False

    @classmethod
    def success_result(
        cls,
        summary: str,
        actions: list[PluginAction] | None = None,
        data: dict[str, Any] | None = None,
    ) -> "PluginResult":
        return cls(
            success=True,
            summary=summary,
            actions=actions or [],
            data=data or {},
        )

    @classmethod
    def failure(
        cls,
        summary: str,
        errors: list[str] | None = None,
        actions: list[PluginAction] | None = None,
    ) -> "PluginResult":
        return cls(
            success=False,
            summary=summary,
            errors=errors or [],
            actions=actions or [],
        )

    @classmethod
    def needs_input(
        cls,
        summary: str,
        questions: list[PluginQuestion] | None = None,
    ) -> "PluginResult":
        return cls(
            success=True,
            summary=summary,
            questions=questions or [],
            needs_user_input=True,
        )


class AutoOpsPlugin(ABC):
    """
    Abstract base class for all AutoOps plugins.

    Lifecycle:
    1. validate_preconditions() - Check if plugin can run
    2. plan() - Generate execution plan (optional, for complex tasks)
    3. execute() - Run the plugin's main logic
    4. report() - Generate documentation of what was done
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this plugin does."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[PluginCapability]:
        """List of capabilities this plugin provides."""
        ...

    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"

    @property
    def requires_auth(self) -> bool:
        """Whether this plugin requires authentication."""
        return True

    async def validate_preconditions(
        self,
        context: "AutoOpsContext",
        client: "GodKaiserClient",
    ) -> PluginResult:
        """
        Check if all preconditions are met before executing.

        Override to add custom validation.
        Returns PluginResult.needs_input() if user input is needed.
        Returns PluginResult.failure() if preconditions aren't met.
        Returns PluginResult.success_result() if ready to execute.
        """
        return PluginResult.success_result(f"Plugin {self.name} preconditions met")

    async def plan(
        self,
        context: "AutoOpsContext",
        client: "GodKaiserClient",
    ) -> list[str]:
        """
        Generate a human-readable execution plan.

        Override for complex plugins that benefit from showing the plan first.
        Returns list of planned steps.
        """
        return [f"Execute {self.name}"]

    @abstractmethod
    async def execute(
        self,
        context: "AutoOpsContext",
        client: "GodKaiserClient",
    ) -> PluginResult:
        """
        Execute the plugin's main logic.

        This is where the actual work happens.
        Must return a PluginResult with full documentation of actions taken.
        """
        ...

    async def rollback(
        self,
        context: "AutoOpsContext",
        client: "GodKaiserClient",
        actions: list[PluginAction],
    ) -> PluginResult:
        """
        Rollback actions on failure.

        Override to implement rollback logic for destructive operations.
        """
        return PluginResult.success_result(f"No rollback needed for {self.name}")

    def _extract_list(self, response: dict, key: str) -> list:
        """Extract a list from various API response formats.

        Handles different response structures:
        - Direct list response
        - Dict with expected key (e.g., "devices", "sensors")
        - Dict with fallback keys ("data", "items", "results")
        """
        if isinstance(response, list):
            return response
        for k in (key, "data", "items", "results"):
            val = response.get(k)
            if isinstance(val, list):
                return val
        return []

    def format_report(self, result: PluginResult) -> str:
        """Generate a markdown report from the plugin result."""
        lines = [
            f"## AutoOps Plugin Report: {self.name}",
            f"**Version:** {self.version}",
            f"**Status:** {'SUCCESS' if result.success else 'FAILED'}",
            f"**Summary:** {result.summary}",
            "",
        ]

        if result.actions:
            lines.append("### Actions Taken")
            lines.append("")
            lines.append("| # | Time | Action | Target | Result | Severity |")
            lines.append("|---|------|--------|--------|--------|----------|")
            for i, action in enumerate(result.actions, 1):
                lines.append(
                    f"| {i} | {action.timestamp} | {action.action} | "
                    f"{action.target} | {action.result} | {action.severity.value} |"
                )
            lines.append("")

        if result.errors:
            lines.append("### Errors")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")

        if result.warnings:
            lines.append("### Warnings")
            for warning in result.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        if result.data:
            lines.append("### Data")
            lines.append("```json")
            import json

            lines.append(json.dumps(result.data, indent=2, default=str))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Phase 4C.1.3 — Plugin Metadata Decorator
# =============================================================================


def plugin_metadata(
    *,
    display_name: str,
    description: str,
    category: str,
    config_schema: dict[str, Any] | None = None,
):
    """
    Decorator that attaches metadata to a plugin class for Registry and API.

    Usage:
        @plugin_metadata(
            display_name="System Health Check",
            description="Checks server health",
            category="monitoring",
            config_schema={"alert_on_degraded": {"type": "boolean", "default": True, "label": "Alert bei Degraded"}},
        )
        class HealthCheckPlugin(AutoOpsPlugin):
            ...
    """

    def decorator(cls):
        cls._display_name = display_name
        cls._description = description
        cls._category = category
        cls._config_schema = config_schema or {}
        return cls

    return decorator


# =============================================================================
# Phase 4C.1.4 — PluginContext (Web/API context, separate from AutoOpsContext)
# =============================================================================


@dataclass
class PluginContext:
    """
    Context passed to plugins when triggered via REST-API or Logic Engine.

    This is NOT AutoOpsContext (which is for CLI/Agent execution).
    PluginService translates PluginContext into AutoOpsContext + GodKaiserClient
    before calling plugin.execute().
    """

    user_id: int | None = None
    user_preferences: dict[str, Any] = field(default_factory=dict)
    system_config: dict[str, Any] = field(default_factory=dict)
    trigger_source: str = "manual"  # 'manual', 'schedule', 'logic_rule'
    trigger_rule_id: str | None = None
    trigger_value: float | None = None
    config_overrides: dict[str, Any] = field(default_factory=dict)
    esp_devices: list[dict[str, Any]] = field(default_factory=list)
    active_alerts: list[dict[str, Any]] = field(default_factory=list)
