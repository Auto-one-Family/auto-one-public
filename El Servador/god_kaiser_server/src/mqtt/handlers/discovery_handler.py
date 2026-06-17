"""
MQTT Handler: ESP32 Discovery Messages — REMOVED (AUT-225, 2026-05).

This module previously handled the legacy ``kaiser/{kaiser_id}/discovery/esp32_nodes``
topic. ESP32 firmware (v4.0+) auto-discovers via heartbeat and no longer publishes
to that topic. The server-side subscription has been removed in AUT-225.

This stub is kept ONLY because the underlying filesystem (FUSE bridge) refused
the unlink operation during the AUT-225 refactor. The module:

- exports nothing
- registers nothing
- is no longer imported from ``src/mqtt/handlers/__init__.py``
- is no longer referenced from ``src/main.py``
- references no longer-existing constant ``MQTT_TOPIC_ESP_DISCOVERY``

Safe to delete in a follow-up commit when the working tree allows.
"""

# Intentionally empty. See module docstring for context.
