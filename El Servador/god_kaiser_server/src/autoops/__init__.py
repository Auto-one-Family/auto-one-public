"""
AutoOps - Autonomous Operations Agent Framework

Plugin-based autonomous agent that operates the AutomationOne system
through the God-Kaiser REST API like a real user.

Capabilities:
- Autonomous ESP32 configuration (sensors, actuators, zones)
- Debug & fix (diagnosis, repair, verification)
- Health monitoring and validation
- Automatic documentation of all actions

Architecture:
- Plugin-based: Each capability is a self-contained plugin
- API-driven: All actions go through the God-Kaiser REST API
- Stateful: Agent maintains context across operations
- Self-documenting: Every action is logged and reported
"""

__version__ = "1.0.0"
