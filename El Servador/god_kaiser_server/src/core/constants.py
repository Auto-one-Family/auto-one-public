"""
System Constants: MQTT Topics, Sensor Types, GPIO Ranges, Timeouts

IMPORTANT: All topics use {kaiser_id} placeholder which must be replaced
with the actual KAISER_ID from config (default: "god").
Use get_topic_with_kaiser_id() helper function for runtime topic building.
"""

# =============================================================================
# MQTT TOPIC PATTERNS (with {kaiser_id} placeholder)
# =============================================================================

# ESP → God-Kaiser (Incoming)
MQTT_TOPIC_ESP_SENSOR_DATA = "kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data"
MQTT_TOPIC_ESP_ACTUATOR_STATUS = "kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status"
MQTT_TOPIC_ESP_HEALTH_STATUS = "kaiser/{kaiser_id}/esp/{esp_id}/health/status"
MQTT_TOPIC_ESP_CONFIG_RESPONSE = "kaiser/{kaiser_id}/esp/{esp_id}/config_response"
MQTT_TOPIC_ESP_RESPONSE = "kaiser/{kaiser_id}/esp/{esp_id}/response"
MQTT_TOPIC_ESP_PI_ENHANCED_REQUEST = "kaiser/{kaiser_id}/esp/{esp_id}/pi_enhanced/request"
MQTT_TOPIC_ESP_HEARTBEAT = "kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat"
MQTT_TOPIC_ESP_HEARTBEAT_METRICS = "kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat_metrics"
MQTT_TOPIC_ESP_SESSION_ANNOUNCE = "kaiser/{kaiser_id}/esp/{esp_id}/session/announce"
MQTT_TOPIC_ESP_LWT = "kaiser/{kaiser_id}/esp/{esp_id}/system/will"

# God-Kaiser → ESP (Outgoing)
MQTT_TOPIC_ESP_ACTUATOR_COMMAND = "kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command"
MQTT_TOPIC_ESP_SENSOR_COMMAND = "kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/command"
MQTT_TOPIC_ESP_SENSOR_RESPONSE = "kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/response"
MQTT_TOPIC_ESP_CONFIG_SENSOR = "kaiser/{kaiser_id}/esp/{esp_id}/config/sensor/{gpio}"
MQTT_TOPIC_ESP_CONFIG_ACTUATOR = "kaiser/{kaiser_id}/esp/{esp_id}/config/actuator/{gpio}"
MQTT_TOPIC_ESP_CONFIG = "kaiser/{kaiser_id}/esp/{esp_id}/config"  # Combined sensor/actuator config
MQTT_TOPIC_ESP_SYSTEM_COMMAND = "kaiser/{kaiser_id}/esp/{esp_id}/system/command"
MQTT_TOPIC_ESP_PI_ENHANCED_RESPONSE = "kaiser/{kaiser_id}/esp/{esp_id}/pi_enhanced/response"
MQTT_TOPIC_ESP_HEARTBEAT_ACK = (
    "kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat/ack"  # Phase 2: Heartbeat-ACK
)

# Zone Assignment (Phase 7 - Hierarchical Zones)
MQTT_TOPIC_ESP_ZONE_ASSIGN = "kaiser/{kaiser_id}/esp/{esp_id}/zone/assign"  # God-Kaiser → ESP
MQTT_TOPIC_ESP_ZONE_ACK = "kaiser/{kaiser_id}/esp/{esp_id}/zone/ack"  # ESP → God-Kaiser

# Zone Assignment Subscription Pattern
MQTT_SUBSCRIBE_ESP_ZONE_ACK = "kaiser/{kaiser_id}/esp/+/zone/ack"

# =============================================================================
# Subzone Management Topics (Phase 9)
# =============================================================================

# Server → ESP (Outgoing)
MQTT_TOPIC_SUBZONE_ASSIGN = "kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign"
MQTT_TOPIC_SUBZONE_REMOVE = "kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove"
MQTT_TOPIC_SUBZONE_SAFE = "kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe"

# ESP → Server (Incoming)
MQTT_TOPIC_SUBZONE_ACK = "kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack"
MQTT_TOPIC_SUBZONE_STATUS = "kaiser/{kaiser_id}/esp/{esp_id}/subzone/status"

# Subzone Subscription Pattern (with wildcard)
MQTT_SUBSCRIBE_SUBZONE_ACK = "kaiser/{kaiser_id}/esp/+/subzone/ack"

# Broadcast Topics
MQTT_TOPIC_BROADCAST_ALL = "kaiser/broadcast/all"
MQTT_TOPIC_BROADCAST_ZONE = "kaiser/broadcast/zone/{zone_id}"

# Kaiser-to-Kaiser Communication
MQTT_TOPIC_KAISER_COMMAND = "kaiser/{kaiser_id}/command"
MQTT_TOPIC_KAISER_STATUS = "kaiser/{kaiser_id}/status"

# Server Status (LWT + online/offline events) — SAFETY-P5
MQTT_TOPIC_SERVER_STATUS = "kaiser/{kaiser_id}/server/status"

# Subscription Patterns (with wildcards) - use {kaiser_id} placeholder
MQTT_SUBSCRIBE_ESP_ALL = "kaiser/{kaiser_id}/esp/+/#"
MQTT_SUBSCRIBE_ESP_SENSORS = "kaiser/{kaiser_id}/esp/+/sensor/+/data"
MQTT_SUBSCRIBE_ESP_ACTUATORS = "kaiser/{kaiser_id}/esp/+/actuator/+/status"
MQTT_SUBSCRIBE_ESP_HEALTH = "kaiser/{kaiser_id}/esp/+/health/status"
MQTT_SUBSCRIBE_ESP_HEARTBEAT_METRICS = "kaiser/{kaiser_id}/esp/+/system/heartbeat_metrics"

# Default Kaiser ID (can be overridden via KAISER_ID env var)
DEFAULT_KAISER_ID = "god"


def get_kaiser_id() -> str:
    """Get KAISER_ID from config or return default."""
    try:
        from .config import get_settings

        return get_settings().hierarchy.kaiser_id
    except Exception:
        return DEFAULT_KAISER_ID


def get_topic_with_kaiser_id(topic_template: str, **kwargs) -> str:
    """
    Replace {kaiser_id} placeholder in topic template with actual value.

    Args:
        topic_template: Topic template with {kaiser_id} and other placeholders
        **kwargs: Additional placeholders to replace (esp_id, gpio, etc.)

    Returns:
        Topic string with all placeholders replaced
    """
    kaiser_id = get_kaiser_id()
    return topic_template.format(kaiser_id=kaiser_id, **kwargs)


# =============================================================================
# GPIO RANGES (Board-Specific)
# =============================================================================

# ESP32 WROOM
# Canonical source: SYSTEM_RESERVED_PINS in services/gpio_validation_service.py
# Only Flash SPI pins (6-11) are hard-reserved and cannot be used at all.
# Boot-Strapping pins (0, 2, 12, 15) and UART pins (1, 3) are usable at runtime
# but require care. Strapping pins are sampled only at boot.
GPIO_RANGE_ESP32_WROOM = range(0, 40)
GPIO_RESERVED_ESP32_WROOM = {6, 7, 8, 9, 10, 11}  # Flash SPI pins only

# XIAO ESP32-C3
GPIO_RANGE_XIAO_ESP32C3 = range(0, 22)
GPIO_RESERVED_XIAO_ESP32C3 = {18, 19}  # USB pins

# ESP32-S3-DevKitC-1 N8R8: Octal Flash+PSRAM (26-37), USB (19-20), RGB (38,48), strap/UART
GPIO_RANGE_ESP32_S3_DEVKITC1 = range(0, 49)
GPIO_RESERVED_ESP32_S3_DEVKITC1 = {
    0,
    3,
    19,
    20,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    43,
    44,
    45,
    46,
    48,
}

# Safe GPIO pins for each board
GPIO_SAFE_ESP32_WROOM = set(GPIO_RANGE_ESP32_WROOM) - GPIO_RESERVED_ESP32_WROOM
GPIO_SAFE_XIAO_ESP32C3 = set(GPIO_RANGE_XIAO_ESP32C3) - GPIO_RESERVED_XIAO_ESP32C3
GPIO_SAFE_ESP32_S3_DEVKITC1 = (
    set(GPIO_RANGE_ESP32_S3_DEVKITC1) - GPIO_RESERVED_ESP32_S3_DEVKITC1
)

# =============================================================================
# SENSOR TYPES
# =============================================================================

SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_HUMIDITY = "humidity"
SENSOR_TYPE_PH = "ph"
SENSOR_TYPE_EC = "ec"
SENSOR_TYPE_MOISTURE = "moisture"
SENSOR_TYPE_PRESSURE = "pressure"
SENSOR_TYPE_CO2 = "co2"
SENSOR_TYPE_LIGHT = "light"
SENSOR_TYPE_FLOW = "flow"
SENSOR_TYPE_GENERIC_ANALOG = "generic_analog"
SENSOR_TYPE_GENERIC_DIGITAL = "generic_digital"

SENSOR_TYPES = [
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_HUMIDITY,
    SENSOR_TYPE_PH,
    SENSOR_TYPE_EC,
    SENSOR_TYPE_MOISTURE,
    SENSOR_TYPE_PRESSURE,
    SENSOR_TYPE_CO2,
    SENSOR_TYPE_LIGHT,
    SENSOR_TYPE_FLOW,
    SENSOR_TYPE_GENERIC_ANALOG,
    SENSOR_TYPE_GENERIC_DIGITAL,
]

# =============================================================================
# ACTUATOR TYPES
# =============================================================================

ACTUATOR_TYPE_DIGITAL = "digital"
ACTUATOR_TYPE_PWM = "pwm"
ACTUATOR_TYPE_SERVO = "servo"
ACTUATOR_TYPE_PUMP = "pump"
ACTUATOR_TYPE_VALVE = "valve"
ACTUATOR_TYPE_RELAY = "relay"

ACTUATOR_TYPES = [
    ACTUATOR_TYPE_DIGITAL,
    ACTUATOR_TYPE_PWM,
    ACTUATOR_TYPE_SERVO,
    ACTUATOR_TYPE_PUMP,
    ACTUATOR_TYPE_VALVE,
    ACTUATOR_TYPE_RELAY,
]

# =============================================================================
# HARDWARE TYPES
# =============================================================================

HARDWARE_TYPE_ESP32_WROOM = "ESP32_WROOM"
HARDWARE_TYPE_XIAO_ESP32C3 = "XIAO_ESP32_C3"
HARDWARE_TYPE_ESP32_S3_DEVKITC1 = "ESP32_S3_DEVKITC1"

HARDWARE_TYPES = [
    HARDWARE_TYPE_ESP32_WROOM,
    HARDWARE_TYPE_XIAO_ESP32C3,
    HARDWARE_TYPE_ESP32_S3_DEVKITC1,
]

# =============================================================================
# TIMEOUTS & INTERVALS (milliseconds)
# =============================================================================

TIMEOUT_SENSOR_PROCESSING = 5000  # 5 seconds
TIMEOUT_ACTUATOR_COMMAND = 10000  # 10 seconds
TIMEOUT_ESP_HEARTBEAT = 120000  # 2 minutes
TIMEOUT_ESP_CONNECTION = 30000  # 30 seconds
TIMEOUT_MQTT_PUBLISH = 5000  # 5 seconds

INTERVAL_ESP_DISCOVERY = 300000  # 5 minutes
INTERVAL_HEALTH_CHECK = 60000  # 1 minute
INTERVAL_SENSOR_POLLING = 5000  # 5 seconds

# =============================================================================
# QOS LEVELS
# =============================================================================

QOS_SENSOR_DATA = 1  # At least once
# AUT-331: Reduced from QoS 2 to QoS 1.
# QoS 2 causes PUBREC + PUBCOMP messages in the ESP-IDF MQTT OUTBOX per command.
# With rapid ON+OFF (<2s), two simultaneous QoS-2 handshakes + lifecycle publishes
# exhaust the 4096-byte OUTBOX, triggering TCP write timeout → disconnect → crash.
# QoS 1 (at-least-once) is sufficient: firmware deduplicates via intent_outcome
# tracking and safety-epoch invalidation. Re-delivery on disconnect is acceptable.
QOS_ACTUATOR_COMMAND = 1  # At least once (was: 2 — see AUT-331)
QOS_SENSOR_COMMAND = 1  # At least once (was: 2 — same reason as AUT-331)
QOS_HEARTBEAT = 0  # At most once
QOS_HEARTBEAT_METRICS = 0  # At most once (same as core heartbeat)
# AUT-331: Reduced from QoS 2 to QoS 1.
# Config pushes on reconnect (sensor_config, actuator_config, full config) used QoS 2,
# generating PUBREC+PUBCOMP OUTBOX slots on the ESP. Combined with actuator command bursts
# these exhausted the 4096-byte OUTBOX → TCP write timeout → crash.
# QoS 1 (at-least-once) is sufficient: ESP firmware deduplicates config via config_response
# contract and safety-epoch invalidation. Re-delivery on reconnect is acceptable.
QOS_CONFIG = 1  # At least once (was: 2 — see AUT-331)

# =============================================================================
# LIMITS & CONSTRAINTS
# =============================================================================

# ESP Limits
MAX_SENSORS_PER_ESP_XIAO = 10
MAX_SENSORS_PER_ESP_WROOM = 20
MAX_ACTUATORS_PER_ESP_XIAO = 6
MAX_ACTUATORS_PER_ESP_WROOM = 12

# Data Retention
DATA_RETENTION_DAYS_SENSOR = 90
DATA_RETENTION_DAYS_ACTUATOR = 30
DATA_RETENTION_DAYS_ERRORS = 7

# PWM Limits
PWM_MIN_VALUE = 0.0
PWM_MAX_VALUE = 1.0
PWM_RESOLUTION = 255  # 8-bit

# =============================================================================
# ERROR CODES (from ESP32 firmware)
# =============================================================================

# Hardware Errors (1000-1999)
ERROR_GPIO_CONFLICT = 1002
ERROR_GPIO_INIT_FAILED = 1003
ERROR_SENSOR_READ_FAILED = 1040
ERROR_ACTUATOR_SET_FAILED = 1050

# Service Errors (2000-2999)
ERROR_CONFIG_INVALID = 2001
ERROR_CONFIG_STORAGE_FULL = 2002
ERROR_SENSOR_NOT_CONFIGURED = 2010
ERROR_ACTUATOR_NOT_CONFIGURED = 2020

# Communication Errors (3000-3999)
ERROR_WIFI_CONNECT_FAILED = 3003
ERROR_MQTT_CONNECT_FAILED = 3011
ERROR_MQTT_PUBLISH_FAILED = 3012
ERROR_MQTT_SUBSCRIBE_FAILED = 3013

# =============================================================================
# HTTP STATUS CODES (Custom Extensions)
# =============================================================================

HTTP_STATUS_ESP32_OFFLINE = 503
HTTP_STATUS_SAFETY_VIOLATION = 422
HTTP_STATUS_GPIO_CONFLICT = 409

# =============================================================================
# PROCESSING MODES
# =============================================================================

PROCESSING_MODE_PI_ENHANCED = "pi_enhanced"
PROCESSING_MODE_LOCAL = "local"
PROCESSING_MODE_RAW = "raw"

PROCESSING_MODES = [
    PROCESSING_MODE_PI_ENHANCED,
    PROCESSING_MODE_LOCAL,
    PROCESSING_MODE_RAW,
]

# =============================================================================
# SYSTEM COMMANDS
# =============================================================================

SYSTEM_COMMAND_RESTART = "restart"
SYSTEM_COMMAND_RESET = "reset"
SYSTEM_COMMAND_EMERGENCY_STOP = "emergency_stop"
SYSTEM_COMMAND_CLEAR_EMERGENCY = "clear_emergency"
SYSTEM_COMMAND_SAFE_MODE_ENABLE = "safe_mode_enable"
SYSTEM_COMMAND_SAFE_MODE_DISABLE = "safe_mode_disable"

SYSTEM_COMMANDS = [
    SYSTEM_COMMAND_RESTART,
    SYSTEM_COMMAND_RESET,
    SYSTEM_COMMAND_EMERGENCY_STOP,
    SYSTEM_COMMAND_CLEAR_EMERGENCY,
    SYSTEM_COMMAND_SAFE_MODE_ENABLE,
    SYSTEM_COMMAND_SAFE_MODE_DISABLE,
]

# =============================================================================
# ACTUATOR COMMANDS
# =============================================================================

ACTUATOR_COMMAND_ON = "on"
ACTUATOR_COMMAND_OFF = "off"
ACTUATOR_COMMAND_SET_PWM = "set_pwm"
ACTUATOR_COMMAND_SET_ANGLE = "set_angle"
ACTUATOR_COMMAND_TOGGLE = "toggle"

ACTUATOR_COMMANDS = [
    ACTUATOR_COMMAND_ON,
    ACTUATOR_COMMAND_OFF,
    ACTUATOR_COMMAND_SET_PWM,
    ACTUATOR_COMMAND_SET_ANGLE,
    ACTUATOR_COMMAND_TOGGLE,
]

# =============================================================================
# DEVICE STATUS
# =============================================================================

DEVICE_STATUS_ONLINE = "online"
DEVICE_STATUS_OFFLINE = "offline"
DEVICE_STATUS_ERROR = "error"
DEVICE_STATUS_UNKNOWN = "unknown"

DEVICE_STATUSES = [
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ERROR,
    DEVICE_STATUS_UNKNOWN,
]

# =============================================================================
# HEALTH STATUS
# =============================================================================

HEALTH_STATUS_HEALTHY = "healthy"
HEALTH_STATUS_DEGRADED = "degraded"
HEALTH_STATUS_UNHEALTHY = "unhealthy"
HEALTH_STATUS_CRITICAL = "critical"

HEALTH_STATUSES = [
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_UNHEALTHY,
    HEALTH_STATUS_CRITICAL,
]
