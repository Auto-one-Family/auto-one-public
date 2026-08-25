"""
API v1 Router Package

Combines all v1 API routers into a single router for inclusion in main app.

Phase: 5 (Week 9-10) - API Layer
Status: IMPLEMENTED
"""

from fastapi import APIRouter

from .actuators import router as actuators_router
from .audit import router as audit_router
from .auth import router as auth_router
from .debug import router as debug_router
from .errors import router as errors_router
from .esp import router as esp_router
from .health import router as health_router
from .logic import router as logic_router
from .logs import router as logs_router
from .notifications import router as notifications_router
from .intent_outcomes import router as intent_outcomes_router
from .plants import router as plants_router
from .plan_segments import router as plan_segments_router
from .stock_mix_recipes import router as stock_mix_recipes_router
from .salt_compositions import router as salt_compositions_router
from .applied_setpoint_logs import router as applied_setpoint_logs_router
from .tanks import router as tanks_router
from .sensors import router as sensors_router
from .sensor_type_defaults import router as sensor_type_defaults_router
from .sequences import router as sequences_router
from .subzone import router as subzone_router
from .users import router as users_router
from .zone import router as zone_router
from .zones import router as zones_router
from .dashboards import router as dashboards_router
from .device_context import router as device_context_router
from .webhooks import router as webhooks_router
from .plugins import router as plugins_router
from .backups import router as backups_router
from .diagnostics import router as diagnostics_router
from .zone_context import router as zone_context_router
from .calibration_sessions import router as calibration_sessions_router
from .component_export import router as component_export_router
from .admin_sheets_export import router as admin_sheets_export_router
from .multispeq import router as multispeq_router
from .scheduler import router as scheduler_router
from .schema_registry import router as schema_registry_router
from .flash import router as flash_router  # AUT-765 — USB Device Detection
from .camera import router as camera_router  # AUT-572 — Camera Snapshot Service

# PLANNED routers - stubs with no endpoints yet, included for discoverability.
# Add endpoints directly to the router files; they will be available immediately.
from .ai import router as ai_router
from .kaiser import router as kaiser_router

# Create main v1 router
api_v1_router = APIRouter()

# Include all sub-routers
api_v1_router.include_router(auth_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(errors_router)  # DS18B20 Error Handling Integration
api_v1_router.include_router(esp_router)
api_v1_router.include_router(sensors_router)
api_v1_router.include_router(sensor_type_defaults_router)  # Phase 2A - Sensor Operating Modes
api_v1_router.include_router(actuators_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(logic_router)
api_v1_router.include_router(debug_router)
api_v1_router.include_router(logs_router)  # Frontend error log ingestion
api_v1_router.include_router(notifications_router)  # Phase 4A.1 - Notification Stack
api_v1_router.include_router(intent_outcomes_router)  # P0.2 - Canonical intent outcome visibility
api_v1_router.include_router(plants_router)  # AUT-222 - Phyta Plants Schema
api_v1_router.include_router(plan_segments_router)  # AUT-1232 - Plan Segment CRUD (T5 precondition)
api_v1_router.include_router(stock_mix_recipes_router)  # AUT-1361 - Stock mix recipe identity (P9)
api_v1_router.include_router(salt_compositions_router)  # AUT-1418 - Salt composition library (B1)
api_v1_router.include_router(applied_setpoint_logs_router)  # AUT-1236 - Applied setpoint log read (T6)
api_v1_router.include_router(tanks_router)  # AUT-1217 - Tank / Ledger write API
api_v1_router.include_router(users_router)
api_v1_router.include_router(zone_router)
api_v1_router.include_router(zones_router)  # Phase 0.3 - Zone Entity CRUD
api_v1_router.include_router(subzone_router)  # Phase 9 - Subzone Management
api_v1_router.include_router(sequences_router)  # Phase 3 - Sequence Actions
api_v1_router.include_router(ai_router)  # PLANNED - God Layer AI integration
api_v1_router.include_router(kaiser_router)  # PLANNED - Kaiser relay node management
api_v1_router.include_router(device_context_router)  # T13-R2 - Multi-Zone Device Context
api_v1_router.include_router(dashboards_router)  # Dashboard Layout Persistence
api_v1_router.include_router(webhooks_router)  # Phase 4A.3 - Grafana Webhook
api_v1_router.include_router(plugins_router)  # Phase 4C - Plugin Management
api_v1_router.include_router(backups_router)  # Phase A V5.1 - Database Backup
api_v1_router.include_router(diagnostics_router)  # Phase 4D - Diagnostics Hub
api_v1_router.include_router(zone_context_router)  # Phase K3 - Zone Context Data
api_v1_router.include_router(component_export_router)  # Phase K4 - AI-Ready Export
api_v1_router.include_router(schema_registry_router)  # Phase K4 L0.2 - Schema Registry
api_v1_router.include_router(calibration_sessions_router)  # S-P3 - Calibration Sessions
api_v1_router.include_router(multispeq_router)  # AUT-217 - MultispeQ Ingress
api_v1_router.include_router(scheduler_router)  # AUT-194 - Scheduler Health Endpoint
api_v1_router.include_router(admin_sheets_export_router)  # AUT-446 - Sheets-Export Cursor Admin
api_v1_router.include_router(flash_router)  # AUT-765 - USB Device Detection for Flash Workflow
api_v1_router.include_router(camera_router)  # AUT-572 - Camera Snapshot Service

# Export individual routers for direct access if needed
__all__ = [
    "api_v1_router",
    "ai_router",
    "audit_router",
    "auth_router",
    "debug_router",
    "errors_router",
    "esp_router",
    "sensors_router",
    "sensor_type_defaults_router",
    "actuators_router",
    "health_router",
    "kaiser_router",
    "logic_router",
    "logs_router",
    "multispeq_router",
    "scheduler_router",
    "notifications_router",
    "intent_outcomes_router",
    "plants_router",
    "plan_segments_router",
    "stock_mix_recipes_router",
    "salt_compositions_router",
    "applied_setpoint_logs_router",
    "sequences_router",
    "subzone_router",
    "users_router",
    "zone_router",
    "zones_router",
    "dashboards_router",
    "device_context_router",
    "webhooks_router",
    "plugins_router",
    "backups_router",
    "diagnostics_router",
    "zone_context_router",
    "admin_sheets_export_router",
    "component_export_router",
    "schema_registry_router",
]
