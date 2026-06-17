"""AutoOps core framework - agent, plugins, context, API client."""

from .base_plugin import AutoOpsPlugin, PluginCapability, PluginResult
from .plugin_registry import PluginRegistry
from .context import (
    AutoOpsContext,
    DeviceMode,
    SimulationPattern,
    ESPSpec,
    SensorSpec,
    ActuatorSpec,
)
from .api_client import GodKaiserClient, APIError
from .agent import AutoOpsAgent
from .reporter import AutoOpsReporter

__all__ = [
    "AutoOpsPlugin",
    "PluginCapability",
    "PluginResult",
    "PluginRegistry",
    "AutoOpsContext",
    "DeviceMode",
    "SimulationPattern",
    "ESPSpec",
    "SensorSpec",
    "ActuatorSpec",
    "GodKaiserClient",
    "APIError",
    "AutoOpsAgent",
    "AutoOpsReporter",
]
