"""
Database Models Package

This module imports all models to ensure they are registered with SQLAlchemy's Base.metadata.
All models should be imported here so that Base.metadata.create_all() includes all tables.
"""

# Import all model modules to ensure SQLAlchemy registers them
from . import (  # noqa: F401
    actuator,
    ai,
    api_key,  # ApiKey model for DB-backed API key validation (AUT-290)
    audit_log,  # AuditLog model for event tracking
    auth,  # TokenBlacklist model
    calibration_session,  # Calibration session tracking (S-P2)
    command_contract,  # Intent/outcome contract persistence (P0.1/P0.2)
    dashboard,  # Dashboard layout persistence
    dashboard_assignment,  # Dashboard n:m user assignments (AUT-1095)
    device_context,  # Device active context for multi-zone routing (T13-R2)
    device_domain_change,  # Device domain change audit (AUT-1085)
    device_zone_change,  # Device zone change audit (T13-R1)
    diagnostic,  # Diagnostic reports (Phase 4D)
    email_log,  # Email delivery tracking (Phase C V1.1)
    enums,  # Shared enums (DataSource, SensorOperatingMode, etc.)
    esp,
    esp_heartbeat,  # ESP Heartbeat History (Time-Series)
    kaiser,
    library,
    logic,
    notification,  # Notification + Preferences (Phase 4A.1)
    nutrient_solution_batch,  # Nutrient solution batch ledger (AUT-1211 follow-up)
    plant,  # Plants + Cannabis extension + Lifecycle events (AUT-222)
    plan_segment,  # Interval setpoints + subzone junction (AUT-1232)
    stock_mix_recipe,  # Stammlösungs-Rezeptur identity (AUT-1361 / P9)
    salt_composition,  # Salz-Referenzbibliothek Elementgehalt (AUT-1418 / B1)
    applied_setpoint_log,  # Applied setpoint history with origin (AUT-1232)
    plugin,  # Plugin configs + execution history (Phase 4C)
    sensor,
    actuator_subzone_assignment,  # Actuator-Subzone n:m junction (Verortung)
    sensor_subzone_assignment,  # Sensor-Subzone n:m junction table (AUT-1155)
    sensor_type_defaults,  # Sensor type default configuration (Phase 2A)
    subzone,  # Subzone configuration model (Phase 9)
    system,
    tank,  # Tank entity (AUT-1211)
    tank_subzone_assignment,  # Tank-Subzone n:m junction table (AUT-1211)
    user,
    zone,  # Zone entity (Phase 0.3)
    zone_context,  # Zone business context (Phase K3)
)

# Explicitly export models for convenience (optional, but helpful)
from .actuator import ActuatorConfig, ActuatorState, ActuatorHistory  # noqa: F401
from .ai import AIPredictions  # noqa: F401
from .audit_log import AuditLog, AuditEventType, AuditSeverity, AuditSourceType  # noqa: F401
from .api_key import ApiKey  # noqa: F401
from .auth import TokenBlacklist  # noqa: F401
from .calibration_session import CalibrationSession, CalibrationStatus  # noqa: F401
from .command_contract import CommandIntent, CommandOutcome  # noqa: F401
from .dashboard import Dashboard  # noqa: F401
from .dashboard_assignment import DashboardUserAssignment  # noqa: F401
from .device_context import DeviceActiveContext  # noqa: F401
from .device_domain_change import DeviceDomainChange  # noqa: F401
from .device_zone_change import DeviceZoneChange  # noqa: F401
from .diagnostic import DiagnosticReport  # noqa: F401
from .email_log import EmailLog  # noqa: F401
from .enums import DataSource, SensorOperatingMode  # noqa: F401
from .esp import ESPDevice  # noqa: F401
from .esp_heartbeat import (
    ESPHeartbeatLog,
    HeartbeatHealthStatus,
    determine_health_status,
)  # noqa: F401
from .kaiser import KaiserRegistry, ESPOwnership  # noqa: F401
from .library import LibraryMetadata  # noqa: F401
from .logic import CrossESPLogic, LogicExecutionHistory, LogicHysteresisState  # noqa: F401
from .notification import (
    Notification,
    NotificationCategory,
    NotificationPreferences,
    NotificationSeverity,
    NotificationSource,
)  # noqa: F401
from .nutrient_solution_batch import NutrientSolutionBatch  # noqa: F401
from .plant import (
    Plant,
    PlantCannabisExtension,
    PlantLifecycleEvent,
)  # noqa: F401
from .plan_segment import (  # noqa: F401
    PlanSegment,
    PlanSegmentSubzoneAssignment,
    PLAN_DOMAINS,
    PLAN_MEASURES,
    PLAN_INTERPS,
    PLAN_SEGMENT_STATUSES,
)
from .stock_mix_recipe import (  # noqa: F401
    StockMixRecipe,
    STOCK_MIX_COVERAGES,
)
from .salt_composition import (  # noqa: F401
    SaltComposition,
    SALT_SOURCE_TYPES,
)
from .applied_setpoint_log import (  # noqa: F401
    AppliedSetpointLog,
    APPLIED_SETPOINT_ORIGINS,
)
from .sensor import SensorConfig, SensorData  # noqa: F401
from .actuator_subzone_assignment import ActuatorSubzoneAssignment  # noqa: F401
from .sensor_subzone_assignment import SensorSubzoneAssignment  # noqa: F401
from .sensor_type_defaults import SensorTypeDefaults  # noqa: F401
from .plugin import PluginConfig, PluginExecution  # noqa: F401
from .subzone import SubzoneConfig  # noqa: F401
from .system import SystemConfig  # noqa: F401
from .tank import Tank  # noqa: F401
from .tank_subzone_assignment import TankSubzoneAssignment  # noqa: F401
from .user import User  # noqa: F401
from .zone import Zone  # noqa: F401
from .zone_context import ZoneContext  # noqa: F401

__all__ = [
    # Modules
    "actuator",
    "ai",
    "api_key",
    "audit_log",
    "auth",
    "calibration_session",
    "CalibrationSession",
    "CalibrationStatus",
    "command_contract",
    "dashboard",
    "dashboard_assignment",
    "device_domain_change",
    "device_zone_change",
    "diagnostic",
    "email_log",
    "enums",
    "esp",
    "esp_heartbeat",
    "kaiser",
    "library",
    "logic",
    "notification",
    "nutrient_solution_batch",
    "plant",
    "plan_segment",
    "stock_mix_recipe",
    "salt_composition",
    "applied_setpoint_log",
    "plugin",
    "sensor",
    "actuator_subzone_assignment",
    "sensor_subzone_assignment",
    "sensor_type_defaults",
    "subzone",
    "system",
    "tank",
    "tank_subzone_assignment",
    "user",
    # Enums
    "DataSource",
    "SensorOperatingMode",
    "PLAN_DOMAINS",
    "PLAN_MEASURES",
    "PLAN_INTERPS",
    "PLAN_SEGMENT_STATUSES",
    "APPLIED_SETPOINT_ORIGINS",
    # Models
    "ActuatorConfig",
    "ActuatorState",
    "ActuatorHistory",
    "AIPredictions",
    "AuditLog",
    "AuditEventType",
    "AuditSeverity",
    "AuditSourceType",
    "ApiKey",
    "TokenBlacklist",
    "CommandIntent",
    "CommandOutcome",
    "Dashboard",
    "DashboardUserAssignment",
    "DeviceActiveContext",
    "DeviceDomainChange",
    "DeviceZoneChange",
    "DiagnosticReport",
    "EmailLog",
    "ESPDevice",
    "ESPHeartbeatLog",
    "HeartbeatHealthStatus",
    "determine_health_status",
    "KaiserRegistry",
    "ESPOwnership",
    "LibraryMetadata",
    "CrossESPLogic",
    "LogicExecutionHistory",
    "LogicHysteresisState",
    "Notification",
    "NotificationCategory",
    "NotificationPreferences",
    "NotificationSeverity",
    "NotificationSource",
    "NutrientSolutionBatch",
    "Plant",
    "PlantCannabisExtension",
    "PlantLifecycleEvent",
    "PlanSegment",
    "PlanSegmentSubzoneAssignment",
    "StockMixRecipe",
    "STOCK_MIX_COVERAGES",
    "SaltComposition",
    "SALT_SOURCE_TYPES",
    "AppliedSetpointLog",
    "SensorConfig",
    "SensorData",
    "ActuatorSubzoneAssignment",
    "SensorSubzoneAssignment",
    "SensorTypeDefaults",
    "PluginConfig",
    "PluginExecution",
    "SubzoneConfig",
    "SystemConfig",
    "Tank",
    "TankSubzoneAssignment",
    "User",
    "Zone",
    "ZoneContext",
]
