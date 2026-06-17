"""
ESP32 orchestrated tests via MQTT.

This module contains server-side tests that orchestrate ESP32 devices via MQTT commands.
Tests can run against:
- MockESP32Client: Server-side simulation for fast tests without hardware
- Real ESP32 devices: Integration tests against physical hardware
"""
