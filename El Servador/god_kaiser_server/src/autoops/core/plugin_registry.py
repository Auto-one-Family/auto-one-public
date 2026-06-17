"""
AutoOps Plugin Registry

Singleton registry that discovers, loads, and manages plugins.
Plugins register themselves or are discovered from the plugins/ directory.

Usage:
    registry = PluginRegistry()
    registry.discover_plugins()

    # Get plugins by capability
    config_plugins = registry.get_by_capability(PluginCapability.CONFIGURE)

    # Get a specific plugin
    esp_config = registry.get("esp_configurator")
"""

import importlib
import logging
import pkgutil
from typing import Optional

from .base_plugin import AutoOpsPlugin, PluginCapability

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Singleton plugin registry for AutoOps.

    Discovers and manages plugin lifecycle.
    """

    _instance: Optional["PluginRegistry"] = None
    _plugins: dict[str, AutoOpsPlugin]

    def __new__(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
        return cls._instance

    def register(self, plugin: AutoOpsPlugin) -> None:
        """Register a plugin instance."""
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name."""
        self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[AutoOpsPlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def get_all(self) -> list[AutoOpsPlugin]:
        """Get all registered plugins."""
        return list(self._plugins.values())

    def get_by_capability(self, capability: PluginCapability) -> list[AutoOpsPlugin]:
        """Get all plugins that have a specific capability."""
        return [p for p in self._plugins.values() if capability in p.capabilities]

    def discover_plugins(self) -> int:
        """
        Auto-discover plugins from the autoops.plugins package.

        Scans the plugins directory for modules containing AutoOpsPlugin subclasses.
        Returns the number of newly discovered plugins.
        """
        from .. import plugins as plugins_package

        discovered = 0
        plugins_pkg_name = plugins_package.__name__
        for importer, modname, ispkg in pkgutil.iter_modules(plugins_package.__path__):
            if modname.startswith("_"):
                continue
            try:
                module = importlib.import_module(f".{modname}", package=plugins_pkg_name)
                # Look for plugin classes in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, AutoOpsPlugin)
                        and attr is not AutoOpsPlugin
                        and not getattr(attr, "__abstractmethods__", None)
                    ):
                        if attr_name not in [p.__class__.__name__ for p in self._plugins.values()]:
                            plugin = attr()
                            self.register(plugin)
                            discovered += 1
            except Exception as e:
                logger.warning("Failed to load plugin module '%s': %s", modname, e)

        return discovered

    def list_plugins(self) -> list[dict]:
        """List all plugins with their metadata."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "version": p.version,
                "capabilities": [c.value for c in p.capabilities],
                "requires_auth": p.requires_auth,
            }
            for p in self._plugins.values()
        ]

    def reset(self) -> None:
        """Clear all registered plugins (for testing)."""
        self._plugins.clear()

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None
