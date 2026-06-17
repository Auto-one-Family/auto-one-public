"""
Unified Error Code System (Server + ESP32)

Provides a synchronized error code system that works across both
the God-Kaiser server and ESP32 firmware. Designed for industrial
systems with comprehensive error tracking and human-readable descriptions.

Error Code Ranges:
ESP32 Firmware (1000-4999):
- HARDWARE: 1000-1999 (GPIO, I2C, Sensors, Actuators)
- SERVICE: 2000-2999 (NVS, Config, Storage)
- COMMUNICATION: 3000-3999 (WiFi, MQTT, HTTP)
- APPLICATION: 4000-4999 (State, Operations, Commands)

Server (5000-5999):
- CONFIG_ERROR: 5000-5099
- MQTT_ERROR: 5100-5199
- VALIDATION_ERROR: 5200-5299
- DATABASE_ERROR: 5300-5399
- SERVICE_ERROR: 5400-5499
- AUDIT_ERROR: 5500-5599
- SEQUENCE_ERROR: 5600-5699
- LOGIC_ERROR: 5700-5749
- DASHBOARD_ERROR: 5750-5779
- SUBZONE_ERROR: 5780-5799
- AUTOOPS_ERROR: 5800-5849
- NOTIFICATION_ERROR: 5850-5899
- PLUGIN_ERROR: 5900-5949
- RESERVED: 5950-5999

Test Infrastructure (6000-6099):
- TEST_ERROR: 6000-6099

Phase: Cross-Layer Error Consistency
Priority: HIGH
Status: IMPLEMENTED
"""

from enum import IntEnum
from typing import Dict, List

# =============================================================================
# ESP32 Error Codes (Mirror of error_codes.h)
# =============================================================================


class ESP32HardwareError(IntEnum):
    """ESP32 Hardware error codes (1000-1999)."""

    GPIO_RESERVED = 1001
    GPIO_CONFLICT = 1002
    GPIO_INIT_FAILED = 1003
    GPIO_INVALID_MODE = 1004
    GPIO_READ_FAILED = 1005
    GPIO_WRITE_FAILED = 1006

    # I2C Extended Error Codes (Phase 4 - Protocol Abstraction)
    I2C_TIMEOUT = 1007
    I2C_CRC_FAILED = 1009

    I2C_INIT_FAILED = 1010
    I2C_DEVICE_NOT_FOUND = 1011
    I2C_READ_FAILED = 1012
    I2C_WRITE_FAILED = 1013
    I2C_BUS_ERROR = 1014
    I2C_BUS_STUCK = 1015
    I2C_BUS_RECOVERY_STARTED = 1016
    I2C_BUS_RECOVERY_FAILED = 1017
    I2C_BUS_RECOVERED = 1018
    I2C_PROTOCOL_UNSUPPORTED = 1019

    ONEWIRE_INIT_FAILED = 1020
    ONEWIRE_NO_DEVICES = 1021
    ONEWIRE_READ_FAILED = 1022
    ONEWIRE_INVALID_ROM_LENGTH = 1023
    ONEWIRE_INVALID_ROM_FORMAT = 1024
    ONEWIRE_INVALID_ROM_CRC = 1025
    ONEWIRE_DEVICE_NOT_FOUND = 1026
    ONEWIRE_BUS_NOT_INITIALIZED = 1027
    ONEWIRE_READ_TIMEOUT = 1028
    ONEWIRE_DUPLICATE_ROM = 1029

    PWM_INIT_FAILED = 1030
    PWM_CHANNEL_FULL = 1031
    PWM_SET_FAILED = 1032

    SENSOR_READ_FAILED = 1040
    SENSOR_INIT_FAILED = 1041
    SENSOR_NOT_FOUND = 1042
    SENSOR_TIMEOUT = 1043

    ACTUATOR_SET_FAILED = 1050
    ACTUATOR_INIT_FAILED = 1051
    ACTUATOR_NOT_FOUND = 1052
    ACTUATOR_CONFLICT = 1053

    # DS18B20-specific Temperature Errors (1060-1069)
    DS18B20_SENSOR_FAULT = 1060
    DS18B20_POWER_ON_RESET = 1061
    DS18B20_OUT_OF_RANGE = 1062
    DS18B20_DISCONNECTED_RUNTIME = 1063


class ESP32ServiceError(IntEnum):
    """ESP32 Service error codes (2000-2999)."""

    NVS_INIT_FAILED = 2001
    NVS_READ_FAILED = 2002
    NVS_WRITE_FAILED = 2003
    NVS_NAMESPACE_FAILED = 2004
    NVS_CLEAR_FAILED = 2005

    CONFIG_INVALID = 2010
    CONFIG_MISSING = 2011
    CONFIG_LOAD_FAILED = 2012
    CONFIG_SAVE_FAILED = 2013
    CONFIG_VALIDATION = 2014

    LOGGER_INIT_FAILED = 2020
    LOGGER_BUFFER_FULL = 2021

    STORAGE_INIT_FAILED = 2030
    STORAGE_READ_FAILED = 2031
    STORAGE_WRITE_FAILED = 2032

    # Subzone Management Errors (2500-2599)
    SUBZONE_INVALID_ID = 2500
    SUBZONE_GPIO_CONFLICT = 2501
    SUBZONE_PARENT_MISMATCH = 2502
    SUBZONE_NOT_FOUND = 2503
    SUBZONE_GPIO_INVALID = 2504
    SUBZONE_SAFE_MODE_FAILED = 2505
    SUBZONE_CONFIG_SAVE_FAILED = 2506


class ESP32CommunicationError(IntEnum):
    """ESP32 Communication error codes (3000-3999)."""

    WIFI_INIT_FAILED = 3001
    WIFI_CONNECT_TIMEOUT = 3002
    WIFI_CONNECT_FAILED = 3003
    WIFI_DISCONNECT = 3004
    WIFI_NO_SSID = 3005

    MQTT_INIT_FAILED = 3010
    MQTT_CONNECT_FAILED = 3011
    MQTT_PUBLISH_FAILED = 3012
    MQTT_SUBSCRIBE_FAILED = 3013
    MQTT_DISCONNECT = 3014
    MQTT_BUFFER_FULL = 3015
    MQTT_PAYLOAD_INVALID = 3016

    HTTP_INIT_FAILED = 3020
    HTTP_REQUEST_FAILED = 3021
    HTTP_RESPONSE_INVALID = 3022
    HTTP_TIMEOUT = 3023

    NETWORK_UNREACHABLE = 3030
    DNS_FAILED = 3031
    CONNECTION_LOST = 3032


class FlashDeviceError(IntEnum):
    """Flash device USB scanning and secrets workflow error codes (3100-3199)."""

    DEVICE_SCAN_FAILED = 3100
    PLATFORM_USB_UNAVAILABLE = 3101
    SECRETS_NOT_FOUND = 3102
    BUILD_FAILED = 3103
    INVALID_ENV = 3104
    FLASH_EXECUTE_FAILED = 3105
    FIRMWARE_NOT_FOUND = 3106
    PORT_HOLDER_KILL_FAILED = 3107
    POST_FLASH_TIMEOUT = 3108
    ERASE_CONFIRM_REQUIRED = 3109


class ESP32ApplicationError(IntEnum):
    """ESP32 Application error codes (4000-4999)."""

    STATE_INVALID = 4001
    STATE_TRANSITION = 4002
    STATE_MACHINE_STUCK = 4003

    OPERATION_TIMEOUT = 4010
    OPERATION_FAILED = 4011
    OPERATION_CANCELLED = 4012

    COMMAND_INVALID = 4020
    COMMAND_PARSE_FAILED = 4021
    COMMAND_EXEC_FAILED = 4022

    PAYLOAD_INVALID = 4030
    PAYLOAD_TOO_LARGE = 4031
    PAYLOAD_PARSE_FAILED = 4032

    MEMORY_FULL = 4040
    MEMORY_ALLOCATION = 4041
    MEMORY_LEAK = 4042

    SYSTEM_INIT_FAILED = 4050
    SYSTEM_RESTART = 4051
    SYSTEM_SAFE_MODE = 4052

    TASK_FAILED = 4060
    TASK_TIMEOUT = 4061
    TASK_QUEUE_FULL = 4062

    # Watchdog Errors (4070-4079)
    WATCHDOG_TIMEOUT = 4070
    WATCHDOG_FEED_BLOCKED = 4071
    WATCHDOG_FEED_BLOCKED_CRITICAL = 4072

    # Device Discovery & Approval (4200-4209)
    DEVICE_REJECTED = 4200
    APPROVAL_TIMEOUT = 4201
    APPROVAL_REVOKED = 4202


# ESP32 ConfigErrorCode (string-based, mirrors enum in error_codes.h)
class ESP32ConfigErrorCode:
    """ESP32 configuration response error codes (string-based)."""

    NONE = "NONE"
    JSON_PARSE_ERROR = "JSON_PARSE_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    GPIO_CONFLICT = "GPIO_CONFLICT"
    NVS_WRITE_FAILED = "NVS_WRITE_FAILED"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    MISSING_FIELD = "MISSING_FIELD"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


# =============================================================================
# Server Error Codes (5000-5999)
# =============================================================================


class ConfigErrorCode(IntEnum):
    """Server configuration error codes (5000-5099)."""

    NONE = 0
    ESP_DEVICE_NOT_FOUND = 5001
    CONFIG_BUILD_FAILED = 5002
    CONFIG_PAYLOAD_INVALID = 5003
    CONFIG_PUBLISH_FAILED = 5004
    FIELD_MAPPING_FAILED = 5005
    CONFIG_TIMEOUT = 5006
    ESP_OFFLINE = 5007
    ESP_COMMAND_FAILED = 5008
    CONFIG_OFFLINE_RULES_INCONSISTENT = 5009

    SHEETS_AUTH_NOT_CONFIGURED = 5050
    SHEETS_CREDENTIALS_FILE_NOT_FOUND = 5051
    SHEETS_CREDENTIALS_FILE_INVALID = 5052
    SHEETS_CREDENTIALS_FILE_PERMISSIONS_UNSAFE = 5053
    SHEETS_DEPENDENCY_MISSING = 5054
    # Sheets Export Pipeline Runtime Errors (5055-5079) — AUT-449 / S7
    SHEETS_QUOTA_EXCEEDED = 5055
    SHEETS_TRANSIENT_API_ERROR = 5056
    SHEETS_PERMISSION_DENIED = 5057
    SHEETS_NOT_FOUND = 5058
    SHEETS_PAYLOAD_TOO_LARGE = 5059
    SHEETS_WRITE_FAILED = 5060
    SHEETS_TAB_CREATE_FAILED = 5061
    SHEETS_CURSOR_READ_FAILED = 5062
    SHEETS_CURSOR_WRITE_FAILED = 5063
    SHEETS_INVALID_RESPONSE = 5064
    SHEETS_RATE_LIMIT_PER_USER = 5065
    SHEETS_BATCH_SPLIT_LIMIT_REACHED = 5070


class MQTTErrorCode(IntEnum):
    """Server MQTT error codes (5100-5199)."""

    NONE = 0
    PUBLISH_FAILED = 5101
    TOPIC_BUILD_FAILED = 5102
    PAYLOAD_SERIALIZATION_FAILED = 5103
    CONNECTION_LOST = 5104
    RETRY_EXHAUSTED = 5105
    BROKER_UNAVAILABLE = 5106
    AUTHENTICATION_FAILED = 5107
    SUBSCRIBE_FAILED = 5108


class ValidationErrorCode(IntEnum):
    """Server validation error codes (5200-5299)."""

    NONE = 0
    INVALID_ESP_ID = 5201
    INVALID_GPIO = 5202
    INVALID_SENSOR_TYPE = 5203
    INVALID_ACTUATOR_TYPE = 5204
    MISSING_REQUIRED_FIELD = 5205
    FIELD_TYPE_MISMATCH = 5206
    VALUE_OUT_OF_RANGE = 5207
    DUPLICATE_ENTRY = 5208
    INVALID_PAYLOAD_FORMAT = 5209
    SENSOR_NOT_FOUND = 5210
    ACTUATOR_NOT_FOUND = 5211


class DatabaseErrorCode(IntEnum):
    """Server database error codes (5300-5399)."""

    NONE = 0
    TRANSACTION_OPEN_FAILED = 5301
    QUERY_FAILED = 5301
    COMMIT_FAILED = 5302
    ROLLBACK_FAILED = 5303
    NAMESPACE_CONFLICT = 5304
    CONNECTION_FAILED = 5304
    WRITE_WITHOUT_TRANSACTION = 5305
    INTEGRITY_ERROR = 5305
    WRITE_TIMEOUT = 5306
    MIGRATION_FAILED = 5306
    RECORD_NOT_FOUND = 5307
    RECORD_DUPLICATE = 5308


class ServiceErrorCode(IntEnum):
    """Server service error codes (5400-5499)."""

    NONE = 0
    SERVICE_INITIALIZATION_FAILED = 5401
    DEPENDENCY_MISSING = 5402
    OPERATION_TIMEOUT = 5403
    RATE_LIMIT_EXCEEDED = 5404
    PERMISSION_DENIED = 5405
    AUTHENTICATION_FAILED = 5406
    TOKEN_EXPIRED = 5407
    TOKEN_INVALID = 5408
    AUTHORIZATION_FAILED = 5409
    EXTERNAL_SERVICE_FAILED = 5410
    SENSOR_PROCESSING_FAILED = 5411
    ACTUATOR_COMMAND_FAILED = 5412
    SAFETY_CONSTRAINT_VIOLATED = 5413
    USER_NOT_FOUND = 5414


class AuditErrorCode(IntEnum):
    """Server audit error codes (5500-5599)."""

    NONE = 0
    AUDIT_LOG_FAILED = 5501
    RETENTION_CLEANUP_FAILED = 5502
    STATISTICS_FAILED = 5503


class SequenceErrorCode(IntEnum):
    """Server sequence error codes (5600-5699)."""

    # Validation Errors (5600-5609)
    SEQ_INVALID_DEFINITION = 5600
    SEQ_EMPTY_STEPS = 5601
    SEQ_INVALID_STEP = 5602
    SEQ_INVALID_ACTION_TYPE = 5603
    SEQ_STEP_MISSING_ACTION = 5604
    SEQ_INVALID_DELAY = 5605
    SEQ_TOO_MANY_STEPS = 5606
    SEQ_DURATION_EXCEEDED = 5607

    # Runtime Errors (5610-5629)
    SEQ_ALREADY_RUNNING = 5610
    SEQ_NOT_FOUND = 5611
    SEQ_CANCELLED = 5612
    SEQ_TIMEOUT = 5613
    SEQ_STEP_FAILED = 5614
    SEQ_STEP_TIMEOUT = 5615
    SEQ_MAX_DURATION_EXCEEDED = 5616
    SEQ_EXECUTOR_NOT_FOUND = 5617
    SEQ_CIRCULAR_REFERENCE = 5618

    # System Errors (5630-5639)
    SEQ_TASK_CREATION_FAILED = 5630
    SEQ_INTERNAL_ERROR = 5631
    SEQ_CLEANUP_FAILED = 5632
    SEQ_STATE_CORRUPTION = 5633

    # Conflict Errors (5640-5649)
    SEQ_ACTUATOR_LOCKED = 5640
    SEQ_RATE_LIMITED = 5641
    SEQ_SAFETY_BLOCKED = 5642


class LogicErrorCode(IntEnum):
    """Logic Engine error codes (5700-5749)."""

    RULE_NOT_FOUND = 5700
    RULE_VALIDATION_FAILED = 5701
    RULE_EXECUTION_FAILED = 5702
    RULE_LOOP_DETECTED = 5703
    RULE_CONDITION_INVALID = 5704
    RULE_ACTION_FAILED = 5705


class DashboardErrorCode(IntEnum):
    """Dashboard error codes (5750-5779)."""

    DASHBOARD_NOT_FOUND = 5750
    DASHBOARD_LAYOUT_INVALID = 5751
    WIDGET_TYPE_UNKNOWN = 5752
    WIDGET_CONFIG_INVALID = 5753


class SubzoneErrorCode(IntEnum):
    """Server-side Subzone error codes (5780-5799)."""

    SUBZONE_NOT_FOUND = 5780
    SUBZONE_PARENT_INVALID = 5781
    SUBZONE_GPIO_CONFLICT = 5782


class AutoOpsErrorCode(IntEnum):
    """AutoOps error codes (5800-5849)."""

    AUTOOPS_JOB_FAILED = 5800
    AUTOOPS_SCHEDULE_INVALID = 5801


class NotificationErrorCode(IntEnum):
    """Phase 4A Notification-System error codes (5850-5899)."""

    NOTIFICATION_NOT_FOUND = 5850
    NOTIFICATION_SEND_FAILED = 5851
    EMAIL_PROVIDER_UNAVAILABLE = 5852
    EMAIL_TEMPLATE_MISSING = 5853
    DIGEST_SCHEDULE_INVALID = 5854
    SUPPRESSION_CONFIG_INVALID = 5855
    SUPPRESSION_WINDOW_CONFLICT = 5856
    WEBHOOK_INVALID_PAYLOAD = 5857
    WEBHOOK_SIGNATURE_INVALID = 5858
    ALERT_PREFERENCE_NOT_FOUND = 5859


class PluginErrorCode(IntEnum):
    """Plugin system error codes (5900-5949)."""

    PLUGIN_NOT_FOUND = 5900
    PLUGIN_DISABLED = 5901
    PLUGIN_EXECUTE_FAILED = 5902
    PLUGIN_CONFIG_INVALID = 5903
    PLUGIN_ROLLBACK_FAILED = 5904
    PLUGIN_AUTH_FAILED = 5905
    PLUGIN_SCHEDULE_INVALID = 5906
    PLUGIN_REGISTRY_SYNC_FAILED = 5907


class TestErrorCodes(IntEnum):
    """Test infrastructure error codes (6000-6099). Only used in test reports, NOT in production."""

    WOKWI_TIMEOUT = 6000
    WOKWI_BOOT_INCOMPLETE = 6001
    MOCK_ESP_CONFIG_INVALID = 6002
    SCENARIO_ASSERTION_FAILED = 6010
    SCENARIO_NOT_FOUND = 6011
    MQTT_INJECTION_FAILED = 6020
    MQTT_BROKER_UNAVAILABLE = 6021
    DOCKER_SERVICE_UNHEALTHY = 6030
    DB_SEED_FAILED = 6031
    PLAYWRIGHT_TIMEOUT = 6040
    PLAYWRIGHT_ELEMENT_NOT_FOUND = 6041
    SERIAL_LOG_MISSING = 6050


# =============================================================================
# Error Code Descriptions (All Systems)
# =============================================================================

# ESP32 error descriptions (synchronized with error_codes.h)
ESP32_ERROR_DESCRIPTIONS: Dict[int, str] = {
    # Hardware (1000-1999)
    1001: "GPIO pin is reserved by system",
    1002: "GPIO pin already in use by another component",
    1003: "Failed to initialize GPIO pin",
    1004: "Invalid GPIO pin mode specified",
    1005: "Failed to read GPIO pin value",
    1006: "Failed to write GPIO pin value",
    # I2C Extended Error Codes (Phase 4 - Protocol Abstraction)
    1007: "I2C operation timed out - sensor not responding",
    1009: "I2C sensor data CRC validation failed - data corrupted",
    1010: "Failed to initialize I2C bus",
    1011: "I2C device not found on bus",
    1012: "Failed to read from I2C device",
    1013: "Failed to write to I2C device",
    1014: "I2C bus error (SDA/SCL stuck or timeout)",
    1015: "I2C bus stuck (SDA or SCL held low by slave device)",
    1016: "I2C bus recovery initiated",
    1017: "I2C bus recovery failed after max attempts",
    1018: "I2C bus recovered successfully",
    1019: "I2C sensor type has no registered communication protocol",
    1020: "Failed to initialize OneWire bus",
    1021: "No OneWire devices found on bus",
    1022: "Failed to read from OneWire device",
    1023: "OneWire ROM-Code must be 16 hex characters",
    1024: "OneWire ROM-Code contains invalid characters (expected 0-9, A-F)",
    1025: "OneWire ROM-Code CRC validation failed (corrupted or fake ROM)",
    1026: "OneWire device not present on bus (check wiring)",
    1027: "OneWire bus not initialized (call begin() first)",
    1028: "OneWire device read timeout (device not responding)",
    1029: "OneWire ROM-Code already registered for another sensor",
    1030: "Failed to initialize PWM controller",
    1031: "All PWM channels already in use",
    1032: "Failed to set PWM duty cycle",
    1040: "Failed to read sensor data",
    1041: "Failed to initialize sensor",
    1042: "Sensor not configured or not found",
    1043: "Sensor read timeout (device not responding)",
    1050: "Failed to set actuator state",
    1051: "Failed to initialize actuator",
    1052: "Actuator not configured or not found",
    1053: "Actuator GPIO conflict with sensor",
    # DS18B20-specific Temperature Errors (1060-1069)
    1060: "DS18B20 sensor fault: -127°C indicates disconnected sensor or CRC failure",
    1061: "DS18B20 power-on reset: 85°C indicates no conversion was performed",
    1062: "DS18B20 temperature outside valid range (-55°C to +125°C)",
    1063: "DS18B20 device was present but is now disconnected",
    # Service (2000-2999)
    2001: "Failed to initialize NVS (Non-Volatile Storage)",
    2002: "Failed to read from NVS",
    2003: "Failed to write to NVS (storage full or corrupted)",
    2004: "Failed to open NVS namespace",
    2005: "Failed to clear NVS namespace",
    2010: "Configuration data is invalid",
    2011: "Required configuration is missing",
    2012: "Failed to load configuration from NVS",
    2013: "Failed to save configuration to NVS",
    2014: "Configuration validation failed",
    2020: "Failed to initialize logger system",
    2021: "Logger buffer is full (messages dropped)",
    2030: "Failed to initialize storage manager",
    2031: "Failed to read from storage",
    2032: "Failed to write to storage",
    # Subzone Management Errors (2500-2599)
    2500: "Invalid subzone_id format (must be 1-32 chars, alphanumeric + underscore)",
    2501: "GPIO already assigned to different subzone",
    2502: "parent_zone_id doesn't match ESP zone assignment",
    2503: "Subzone doesn't exist",
    2504: "GPIO not in safe pins list",
    2505: "Safe-mode activation failed for subzone",
    2506: "Failed to save subzone configuration to NVS",
    # Communication (3000-3999)
    3001: "Failed to initialize WiFi module",
    3002: "WiFi connection timeout",
    3003: "WiFi connection failed (wrong password or SSID not found)",
    3004: "WiFi disconnected unexpectedly",
    3005: "WiFi SSID not configured",
    3010: "Failed to initialize MQTT client",
    3011: "MQTT broker connection failed",
    3012: "Failed to publish MQTT message",
    3013: "Failed to subscribe to MQTT topic",
    3014: "MQTT disconnected from broker",
    3015: "MQTT offline buffer is full (messages dropped)",
    3016: "MQTT payload is invalid or malformed",
    3020: "Failed to initialize HTTP client",
    3021: "HTTP request failed (server unreachable)",
    3022: "HTTP response is invalid or malformed",
    3023: "HTTP request timeout",
    3030: "Network is unreachable",
    3031: "DNS lookup failed (hostname not resolved)",
    3032: "Network connection lost",
    # Flash Device (3100-3199)
    3100: "USB device scan failed",
    3101: "USB scanning not available on this platform (Docker on Windows without passthrough)",
    3102: "NVS secrets CSV not found for environment — run PUT /flash/secrets/{env} first",
    3103: "NVS partition binary generation failed (nvs_partition_gen error)",
    3104: "Invalid flash environment — must be dev-local, pi-home, or pi-elbherb",
    3105: "Flash execution failed (esptool error — check port and NVS binary)",
    # Application (4000-4999)
    4001: "Invalid system state",
    4002: "Invalid state transition",
    4003: "State machine is stuck (no valid transitions)",
    4010: "Operation timeout",
    4011: "Operation failed",
    4012: "Operation cancelled by user or system",
    4020: "Command is invalid or unknown",
    4021: "Failed to parse command",
    4022: "Command execution failed",
    4030: "Payload is invalid or malformed",
    4031: "Payload size exceeds maximum allowed",
    4032: "Failed to parse payload (JSON syntax error)",
    4040: "Memory is full (heap exhausted)",
    4041: "Failed to allocate memory",
    4042: "Memory leak detected",
    4050: "System initialization failed",
    4051: "System restart requested",
    4052: "System entered safe mode (errors detected)",
    4060: "FreeRTOS task failed",
    4061: "FreeRTOS task timeout",
    4062: "FreeRTOS task queue is full",
    # Watchdog Errors (4070-4079)
    4070: "Watchdog timeout detected (system hang)",
    4071: "Watchdog feed blocked: Circuit breakers open",
    4072: "Watchdog feed blocked: Critical errors active",
    # Device Discovery & Approval (4200-4209)
    4200: "Device rejected by server administrator",
    4201: "Timeout waiting for server approval",
    4202: "Previously approved device was revoked",
}

# ESP32 ConfigErrorCode descriptions
ESP32_CONFIG_ERROR_DESCRIPTIONS: Dict[str, str] = {
    "NONE": "No error",
    "JSON_PARSE_ERROR": "Failed to parse JSON configuration",
    "VALIDATION_FAILED": "Configuration validation failed",
    "GPIO_CONFLICT": "GPIO pin conflict detected",
    "NVS_WRITE_FAILED": "Failed to save configuration to NVS",
    "TYPE_MISMATCH": "Field type mismatch in configuration",
    "MISSING_FIELD": "Required field missing in configuration",
    "OUT_OF_RANGE": "Value out of allowed range",
    "UNKNOWN_ERROR": "Unknown configuration error",
}

# Server error descriptions
SERVER_ERROR_DESCRIPTIONS: Dict[int, str] = {
    # Config errors (5000-5099)
    5001: "ESP device not found in database",
    5002: "Failed to build configuration payload",
    5003: "Configuration payload is invalid",
    5004: "Failed to publish configuration via MQTT",
    5005: "Failed to map fields between server and ESP32 format",
    5006: "Configuration response timeout",
    5007: "ESP device is offline",
    5008: "ESP32 command execution failed",
    # MQTT errors (5100-5199)
    5101: "MQTT publish operation failed",
    5102: "Failed to build MQTT topic",
    5103: "Failed to serialize MQTT payload",
    5104: "MQTT connection lost",
    5105: "MQTT retry attempts exhausted",
    5106: "MQTT broker is unavailable",
    5107: "MQTT authentication failed",
    5108: "MQTT subscribe operation failed",
    # Validation errors (5200-5299)
    5201: "Invalid ESP device ID format",
    5202: "Invalid GPIO pin number",
    5203: "Invalid sensor type",
    5204: "Invalid actuator type",
    5205: "Missing required field in request",
    5206: "Field type mismatch",
    5207: "Value out of allowed range",
    5208: "Duplicate entry (already exists)",
    5209: "Invalid payload format",
    5210: "Sensor not found in server database",
    5211: "Actuator not found in server database",
    # Database errors (5300-5399)
    5301: "Database transaction open/query failed",
    5302: "Database commit failed",
    5303: "Database rollback failed",
    5304: "Persistence namespace conflict or database connection conflict",
    5305: "Write without transaction or integrity constraint violated",
    5306: "Persistence write timeout or database migration failed",
    5307: "Database record not found",
    5308: "Duplicate database record (integrity constraint)",
    # Service errors (5400-5499)
    5401: "Service initialization failed",
    5402: "Required dependency missing",
    5403: "Service operation timed out",
    5404: "Rate limit exceeded",
    5405: "Permission denied",
    5406: "Authentication failed (invalid credentials)",
    5407: "Authentication token expired",
    5408: "Authentication token invalid or malformed",
    5409: "Authorization failed (insufficient permissions)",
    5410: "External service unavailable or failed",
    5411: "Sensor data processing failed",
    5412: "Actuator command execution failed",
    5413: "Safety constraint violated",
    5414: "User not found",
    # Audit errors (5500-5599)
    5501: "Failed to write audit log",
    5502: "Retention cleanup failed",
    5503: "Failed to compute audit statistics",
    # Sequence errors (5600-5699)
    5600: "Invalid sequence definition",
    5601: "Sequence must have at least one step",
    5602: "Invalid step configuration",
    5603: "Unknown action type in step",
    5604: "Step requires either 'action' or 'delay_seconds'",
    5605: "Invalid delay value (must be 0-3600 seconds)",
    5606: "Too many steps (max 50)",
    5607: "Sequence duration exceeds maximum allowed",
    5610: "Sequence with this ID is already running",
    5611: "Sequence not found",
    5612: "Sequence was cancelled",
    5613: "Sequence timed out",
    5614: "Step execution failed",
    5615: "Step timed out",
    5616: "Maximum sequence duration exceeded",
    5617: "No executor found for action type",
    5618: "Circular sequence reference detected",
    5630: "Failed to create sequence task",
    5631: "Internal sequence error",
    5632: "Failed to cleanup completed sequence",
    5633: "Sequence state corruption detected",
    5640: "Actuator locked by another sequence/rule",
    5641: "Rate limit exceeded",
    5642: "Action blocked by safety system",
    # Logic Engine errors (5700-5749)
    5700: "Logic rule not found",
    5701: "Logic rule validation failed",
    5702: "Logic rule execution failed",
    5703: "Logic rule loop detected (circular dependency)",
    5704: "Logic rule condition invalid",
    5705: "Logic rule action execution failed",
    # Dashboard errors (5750-5779)
    5750: "Dashboard not found",
    5751: "Dashboard layout invalid",
    5752: "Unknown widget type",
    5753: "Widget configuration invalid",
    # Subzone errors (5780-5799)
    5780: "Subzone not found",
    5781: "Subzone parent zone invalid",
    5782: "Subzone GPIO conflict with existing assignment",
    # AutoOps errors (5800-5849)
    5800: "AutoOps job execution failed",
    5801: "AutoOps schedule configuration invalid",
    # Notification errors (5850-5899)
    5850: "Notification with given ID not found",
    5851: "Failed to send notification via configured provider",
    5852: "Email provider unavailable or misconfigured",
    5853: "Email template missing or invalid",
    5854: "Digest schedule configuration invalid",
    5855: "Alert suppression configuration invalid",
    5856: "Alert suppression window conflicts with existing window",
    5857: "Webhook payload invalid or malformed",
    5858: "Webhook signature validation failed",
    5859: "Alert preference for device not found",
    # Plugin system errors (5900-5949)
    5900: "Plugin not found in registry",
    5901: "Plugin is disabled and cannot be executed",
    5902: "Plugin execution failed",
    5903: "Plugin configuration invalid or schema mismatch",
    5904: "Plugin rollback failed after execution error",
    5905: "Plugin authentication to internal API failed",
    5906: "Plugin schedule (cron expression) invalid",
    5907: "Plugin registry sync to database failed",
}

# Test infrastructure error descriptions
TEST_ERROR_DESCRIPTIONS: Dict[int, str] = {
    6000: "Wokwi simulation timeout exceeded",
    6001: "ESP32 boot in simulation incomplete",
    6002: "Mock-ESP configuration invalid",
    6010: "Wokwi scenario assertion failed",
    6011: "Referenced scenario does not exist",
    6020: "MQTT inject in test failed",
    6021: "Test MQTT broker not reachable",
    6030: "Docker service unhealthy during test",
    6031: "Test data seeding failed",
    6040: "Frontend E2E test (Playwright) timeout",
    6041: "UI element not found in E2E test",
    6050: "Expected serial log pattern not found",
}


def get_error_code_description(code: int) -> str:
    """
    Get human-readable description for any error code (ESP32 or Server).

    Supports all error code ranges:
    - ESP32 Hardware (1000-1999)
    - ESP32 Service (2000-2999)
    - ESP32 Communication (3000-3999)
    - ESP32 Application (4000-4999)
    - Server Config (5000-5099)
    - Server MQTT (5100-5199)
    - Server Validation (5200-5299)
    - Server Database (5300-5399)
    - Server Service (5400-5499)
    - Server Audit (5500-5599)

    Args:
        code: Error code integer

    Returns:
        Human-readable error description
    """
    # ESP32 errors (1000-4999)
    if 1000 <= code < 5000:
        return ESP32_ERROR_DESCRIPTIONS.get(code, f"Unknown ESP32 error: {code}")

    # Server errors (5000-5999)
    if 5000 <= code < 6000:
        return SERVER_ERROR_DESCRIPTIONS.get(code, f"Unknown server error: {code}")

    # Test infrastructure errors (6000-6099)
    if 6000 <= code < 6100:
        return TEST_ERROR_DESCRIPTIONS.get(code, f"Unknown test error: {code}")

    return f"Unknown error code: {code}"


def get_esp32_config_error_description(code: str) -> str:
    """
    Get description for ESP32 ConfigErrorCode (string-based).

    Args:
        code: ConfigErrorCode string (e.g., "GPIO_CONFLICT")

    Returns:
        Human-readable description
    """
    return ESP32_CONFIG_ERROR_DESCRIPTIONS.get(code, f"Unknown config error: {code}")


def get_error_code_range(code: int) -> str:
    """
    Get the error code category/range name.

    Args:
        code: Error code integer

    Returns:
        Category name (e.g., "HARDWARE", "SERVER_CONFIG")
    """
    if 1000 <= code < 2000:
        return "HARDWARE"
    elif 2000 <= code < 3000:
        return "SERVICE"
    elif 3000 <= code < 4000:
        return "COMMUNICATION"
    elif 4000 <= code < 5000:
        return "APPLICATION"
    elif 5000 <= code < 5100:
        return "SERVER_CONFIG"
    elif 5100 <= code < 5200:
        return "SERVER_MQTT"
    elif 5200 <= code < 5300:
        return "SERVER_VALIDATION"
    elif 5300 <= code < 5400:
        return "SERVER_DATABASE"
    elif 5400 <= code < 5500:
        return "SERVER_SERVICE"
    elif 5500 <= code < 5600:
        return "SERVER_AUDIT"
    elif 5600 <= code < 5700:
        return "SERVER_SEQUENCE"
    elif 5700 <= code < 5750:
        return "SERVER_LOGIC"
    elif 5750 <= code < 5780:
        return "SERVER_DASHBOARD"
    elif 5780 <= code < 5800:
        return "SERVER_SUBZONE"
    elif 5800 <= code < 5850:
        return "SERVER_AUTOOPS"
    elif 5850 <= code < 5900:
        return "SERVER_NOTIFICATION"
    elif 5900 <= code < 5950:
        return "SERVER_PLUGIN"
    elif 6000 <= code < 6100:
        return "TEST"
    return "UNKNOWN"


def get_error_code_source(code: int) -> str:
    """
    Get the source system for an error code.

    Args:
        code: Error code integer

    Returns:
        Source system ("esp32" or "server")
    """
    if 1000 <= code < 5000:
        return "esp32"
    elif 5000 <= code < 6000:
        return "server"
    elif 6000 <= code < 6100:
        return "test"
    return "unknown"


def get_all_error_codes() -> List[Dict]:
    """
    Get all error codes with descriptions for API/frontend use.

    Returns:
        List of dicts with code, description, range, source
    """
    all_codes = []

    # ESP32 errors
    for code, desc in ESP32_ERROR_DESCRIPTIONS.items():
        all_codes.append(
            {
                "code": code,
                "description": desc,
                "range": get_error_code_range(code),
                "source": "esp32",
            }
        )

    # Server errors
    for code, desc in SERVER_ERROR_DESCRIPTIONS.items():
        all_codes.append(
            {
                "code": code,
                "description": desc,
                "range": get_error_code_range(code),
                "source": "server",
            }
        )

    # Test infrastructure errors
    for code, desc in TEST_ERROR_DESCRIPTIONS.items():
        all_codes.append(
            {
                "code": code,
                "description": desc,
                "range": get_error_code_range(code),
                "source": "test",
            }
        )

    return sorted(all_codes, key=lambda x: x["code"])


def get_esp32_config_error_codes() -> List[Dict]:
    """
    Get all ESP32 config error codes (string-based).

    Returns:
        List of dicts with code and description
    """
    return [
        {"code": code, "description": desc}
        for code, desc in ESP32_CONFIG_ERROR_DESCRIPTIONS.items()
    ]
