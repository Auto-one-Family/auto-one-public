"""
Maintenance Service Package

Provides automated maintenance jobs:
- Cleanup of old sensor data and command history
- Health checks for ESPs and MQTT broker
- Statistics aggregation
"""

from .service import (
    MaintenanceService,
    get_maintenance_service,
    init_maintenance_service,
)

__all__ = [
    "MaintenanceService",
    "get_maintenance_service",
    "init_maintenance_service",
]
