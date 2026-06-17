"""
Debug Database API Schemas - Database Explorer

Pydantic schemas for the database explorer API that allows
admin users to inspect and query database tables.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SortOrder(str, Enum):
    """Sort order for table queries."""

    ASC = "asc"
    DESC = "desc"


class ColumnType(str, Enum):
    """Supported column types for schema display."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    JSON = "json"
    UUID = "uuid"


class ColumnSchema(BaseModel):
    """Schema of a single database column."""

    name: str = Field(..., description="Column name")
    type: ColumnType = Field(..., description="Column data type")
    nullable: bool = Field(..., description="Whether column allows NULL")
    primary_key: bool = Field(default=False, description="Whether column is primary key")
    foreign_key: Optional[str] = Field(
        default=None, description="Foreign key reference (table_name.column_name)"
    )

    model_config = ConfigDict(use_enum_values=True)


class TableSchema(BaseModel):
    """Schema of a database table."""

    table_name: str = Field(..., description="Name of the table")
    columns: List[ColumnSchema] = Field(..., description="List of column schemas")
    row_count: int = Field(..., ge=0, description="Total number of rows in table")
    primary_key: str = Field(..., description="Primary key column name")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "table_name": "user_accounts",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False, "primary_key": True},
                    {"name": "username", "type": "string", "nullable": False, "primary_key": False},
                ],
                "row_count": 5,
                "primary_key": "id",
            }
        }
    )


class TableListResponse(BaseModel):
    """Response for GET /debug/db/tables."""

    success: bool = True
    tables: List[TableSchema] = Field(..., description="List of available tables")


class TableDataResponse(BaseModel):
    """Response for GET /debug/db/{table_name}."""

    success: bool = True
    table_name: str = Field(..., description="Name of the queried table")
    data: List[Dict[str, Any]] = Field(..., description="List of records")
    total_count: int = Field(..., ge=0, description="Total number of records (before pagination)")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Records per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "table_name": "esp_devices",
                "data": [
                    {"id": "550e8400-e29b-41d4-a716-446655440000", "device_id": "ESP_12AB34CD"}
                ],
                "total_count": 100,
                "page": 1,
                "page_size": 50,
                "total_pages": 2,
            }
        }
    )


class RecordResponse(BaseModel):
    """Response for GET /debug/db/{table_name}/{record_id}."""

    success: bool = True
    table_name: str = Field(..., description="Name of the table")
    record: Dict[str, Any] = Field(..., description="The record data")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "table_name": "user_accounts",
                "record": {
                    "id": 1,
                    "username": "admin",
                    "email": "admin@example.com",
                    "role": "admin",
                },
            }
        }
    )


# =============================================================================
# Constants for Database Explorer
# =============================================================================

# Whitelist of tables accessible via the Database Explorer
ALLOWED_TABLES = {
    "user_accounts",  # Auth - User accounts
    "token_blacklist",  # Auth - Revoked tokens
    "esp_devices",  # Devices - ESP32 devices
    "kaiser_registry",  # Devices - Kaiser hierarchy
    "esp_ownership",  # Devices - Device ownership
    "sensor_configs",  # Sensors - Configuration
    "sensor_data",  # Sensors - Time-Series data
    "sensor_type_defaults",  # Sensors - Type defaults configuration
    "actuator_configs",  # Actuators - Configuration
    "actuator_states",  # Actuators - Current state
    "actuator_history",  # Actuators - Time-Series history
    "cross_esp_logic",  # Automation - Logic rules
    "logic_execution_history",  # Automation - Execution history
    "subzone_configs",  # Zones - Subzone management (Phase 9)
    "library_metadata",  # System - Sensor libraries
    "system_config",  # System - Configuration
    "audit_logs",  # System - Audit trail
    "ai_predictions",  # KI/Analytics - AI predictions
}

# Time-series tables with their timestamp column names
# Maps table_name -> timestamp_column for default time filtering
TIME_SERIES_TABLES = {
    "sensor_data": "timestamp",
    "actuator_history": "timestamp",
    "logic_execution_history": "timestamp",
    "audit_logs": "created_at",
}

# Fields that should be masked (not returned) for security
MASKED_FIELDS = {
    "user_accounts": ["password_hash"],
    "token_blacklist": ["token_hash"],
    "audit_logs": ["ip_address"],  # Mask client IP addresses for privacy
}

# Default time limit for time-series tables (24 hours in seconds)
DEFAULT_TIME_SERIES_LIMIT_HOURS = 24
