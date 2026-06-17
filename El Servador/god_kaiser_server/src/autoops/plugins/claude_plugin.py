"""
Claude Integration Plugin — Anthropic Claude API configuration and connection test.

Validates the Anthropic API key and tests connectivity by performing
a minimal API call. Used to confirm Claude is available for AI-powered
features like ClaudeDebugAgent (AUT-270).
"""

import os

try:
    from anthropic import AsyncAnthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]
    _ANTHROPIC_AVAILABLE = False

from ..core.api_client import GodKaiserClient
from ..core.base_plugin import (
    ActionSeverity,
    AutoOpsPlugin,
    PluginAction,
    PluginCapability,
    PluginResult,
    plugin_metadata,
)
from ..core.context import AutoOpsContext

# Model used for the lightweight connection test (haiku = cheapest/fastest)
_TEST_MODEL = "claude-haiku-4-5-20251001"


@plugin_metadata(
    display_name="Claude Integration",
    description="Anthropic Claude API — Konfiguration und Verbindungstest",
    category="integration",
    config_schema={
        "api_key": {
            "type": "string",
            "label": "Anthropic API Key",
            "default": "",
            "sensitive": True,
        },
        "model": {
            "type": "string",
            "label": "Modell",
            "default": "claude-opus-4-7",
        },
        "enabled": {
            "type": "boolean",
            "label": "Claude aktivieren",
            "default": False,
        },
    },
)
class ClaudePlugin(AutoOpsPlugin):
    """
    Claude Integration validator.

    Checks whether the Anthropic SDK is installed, an API key is available,
    and connectivity to the Anthropic API can be established.
    """

    @property
    def name(self) -> str:
        return "claude"

    @property
    def description(self) -> str:
        return (
            "Anthropic Claude API integration — validates API key and "
            "tests connectivity with a minimal ping call"
        )

    @property
    def capabilities(self) -> list[PluginCapability]:
        return [PluginCapability.VALIDATE]

    async def execute(self, context: AutoOpsContext, client: GodKaiserClient) -> PluginResult:
        """Run Claude connectivity test."""
        actions: list[PluginAction] = []

        # =============================================
        # Check 1: SDK availability
        # =============================================
        if not _ANTHROPIC_AVAILABLE:
            actions.append(
                PluginAction.create(
                    action="SDK Check",
                    target="anthropic",
                    details={},
                    result="anthropic package not installed",
                    severity=ActionSeverity.ERROR,
                )
            )
            return PluginResult.failure(
                summary="anthropic SDK nicht installiert — `pip install anthropic`",
                actions=actions,
            )

        actions.append(
            PluginAction.create(
                action="SDK Check",
                target="anthropic",
                details={"available": True},
                result="anthropic SDK verfuegbar",
                severity=ActionSeverity.SUCCESS,
            )
        )

        # =============================================
        # Check 2: API Key resolution
        # config_overrides are stored in context.extra by PluginService
        # =============================================
        config_overrides: dict = context.extra.get("config_overrides", {})
        api_key: str | None = config_overrides.get("api_key") or os.environ.get(
            "ANTHROPIC_API_KEY"
        )

        if not api_key:
            actions.append(
                PluginAction.create(
                    action="API Key Check",
                    target="ANTHROPIC_API_KEY",
                    details={"source_checked": ["config_overrides", "env"]},
                    result="Kein API-Key konfiguriert",
                    severity=ActionSeverity.ERROR,
                )
            )
            return PluginResult.failure(
                summary="Kein API-Key konfiguriert — ANTHROPIC_API_KEY setzen oder via Plugin-Config uebergeben",
                actions=actions,
            )

        key_preview = f"{api_key[:8]}..." if len(api_key) > 8 else "***"
        actions.append(
            PluginAction.create(
                action="API Key Check",
                target="ANTHROPIC_API_KEY",
                details={"key_prefix": key_preview},
                result="API-Key gefunden",
                severity=ActionSeverity.SUCCESS,
            )
        )

        # =============================================
        # Check 3: Connectivity test (minimal call)
        # =============================================
        try:
            anthropic_client = AsyncAnthropic(api_key=api_key)
            await anthropic_client.messages.create(
                model=_TEST_MODEL,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            actions.append(
                PluginAction.create(
                    action="Connectivity Test",
                    target=_TEST_MODEL,
                    details={"model": _TEST_MODEL, "max_tokens": 1},
                    result="Verbindung OK",
                    severity=ActionSeverity.SUCCESS,
                )
            )
        except Exception as exc:
            actions.append(
                PluginAction.create(
                    action="Connectivity Test",
                    target=_TEST_MODEL,
                    details={"model": _TEST_MODEL, "error": str(exc)},
                    result=f"FAILED: {exc}",
                    severity=ActionSeverity.ERROR,
                )
            )
            return PluginResult.failure(
                summary=f"Anthropic API nicht erreichbar: {exc}",
                actions=actions,
            )

        return PluginResult(
            success=True,
            summary="Claude Integration OK — SDK installiert, API-Key konfiguriert, Verbindung erfolgreich",
            actions=actions,
        )
