"""
Input Validation: GPIO, IP, MQTT Topics, Sensor Data
"""

import re
from ipaddress import IPv4Address, AddressValueError
from typing import Optional

from . import constants


def validate_gpio(gpio: int, board_type: str) -> tuple[bool, Optional[str]]:
    """
    Validate GPIO pin for specific board type.

    Args:
        gpio: GPIO pin number
        board_type: Board type (ESP32_WROOM or XIAO_ESP32_C3)

    Returns:
        tuple: (is_valid, error_message)
    """
    if board_type == constants.HARDWARE_TYPE_ESP32_WROOM:
        if gpio not in constants.GPIO_RANGE_ESP32_WROOM:
            return False, f"GPIO {gpio} is out of range for ESP32 WROOM (0-39)"
        if gpio in constants.GPIO_RESERVED_ESP32_WROOM:
            return False, f"GPIO {gpio} is reserved (Flash pins) on ESP32 WROOM"
    elif board_type == constants.HARDWARE_TYPE_XIAO_ESP32C3:
        if gpio not in constants.GPIO_RANGE_XIAO_ESP32C3:
            return False, f"GPIO {gpio} is out of range for XIAO ESP32-C3 (0-21)"
        if gpio in constants.GPIO_RESERVED_XIAO_ESP32C3:
            return False, f"GPIO {gpio} is reserved (USB pins) on XIAO ESP32-C3"
    elif board_type == constants.HARDWARE_TYPE_ESP32_S3_DEVKITC1:
        if gpio not in constants.GPIO_RANGE_ESP32_S3_DEVKITC1:
            return False, f"GPIO {gpio} is out of range for ESP32-S3 DevKitC-1 (0-48)"
        if gpio in constants.GPIO_RESERVED_ESP32_S3_DEVKITC1:
            return False, f"GPIO {gpio} is reserved on ESP32-S3 DevKitC-1"
    else:
        return False, f"Unknown board type: {board_type}"

    return True, None


def validate_mqtt_topic(topic: str) -> tuple[bool, Optional[str]]:
    """
    Validate MQTT topic format.

    Args:
        topic: MQTT topic string

    Returns:
        tuple: (is_valid, error_message)
    """
    if not topic:
        return False, "Topic cannot be empty"

    if len(topic) > 65535:
        return False, "Topic exceeds maximum length (65535 bytes)"

    # Check for invalid characters
    invalid_chars = ["\x00", "\x01", "\x02", "\x03", "\x04", "\x05"]
    if any(char in topic for char in invalid_chars):
        return False, "Topic contains invalid control characters"

    # Check for wildcards in wrong positions
    if "#" in topic and not topic.endswith("#"):
        return False, "Multi-level wildcard (#) must be at the end"

    if "#" in topic and topic.count("#") > 1:
        return False, "Only one multi-level wildcard (#) allowed"

    return True, None


def validate_esp_id(esp_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate ESP device ID format.

    Args:
        esp_id: ESP device ID

    Returns:
        tuple: (is_valid, error_message)
    """
    if not esp_id:
        return False, "ESP ID cannot be empty"

    # ESP ID format: ESP_{6-8 hex chars} or MOCK_{alphanumeric}
    pattern = r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$"
    if not re.match(pattern, esp_id):
        return False, "ESP ID must match format 'ESP_XXXXXX' (6-8 hex characters) or 'MOCK_XXX'"

    if len(esp_id) > 64:
        return False, "ESP ID exceeds maximum length (64 characters)"

    return True, None


def validate_sensor_type(sensor_type: str) -> tuple[bool, Optional[str]]:
    """
    Validate sensor type.

    Args:
        sensor_type: Sensor type string

    Returns:
        tuple: (is_valid, error_message)
    """
    if sensor_type not in constants.SENSOR_TYPES:
        return False, f"Invalid sensor type. Must be one of: {', '.join(constants.SENSOR_TYPES)}"

    return True, None


def validate_actuator_type(actuator_type: str) -> tuple[bool, Optional[str]]:
    """
    Validate actuator type.

    Args:
        actuator_type: Actuator type string

    Returns:
        tuple: (is_valid, error_message)
    """
    if actuator_type not in constants.ACTUATOR_TYPES:
        return (
            False,
            f"Invalid actuator type. Must be one of: {', '.join(constants.ACTUATOR_TYPES)}",
        )

    return True, None


def validate_pwm_value(value: float) -> tuple[bool, Optional[str]]:
    """
    Validate PWM value (0.0 - 1.0).

    Args:
        value: PWM value

    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(value, (int, float)):
        return False, "PWM value must be a number"

    if value < constants.PWM_MIN_VALUE or value > constants.PWM_MAX_VALUE:
        return (
            False,
            f"PWM value must be between {constants.PWM_MIN_VALUE} and {constants.PWM_MAX_VALUE}",
        )

    return True, None


def validate_ip_address(ip: str) -> tuple[bool, Optional[str]]:
    """
    Validate IPv4 address format.

    Args:
        ip: IP address string

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        IPv4Address(ip)
        return True, None
    except AddressValueError:
        return False, f"Invalid IPv4 address format: {ip}"


def validate_zone_id(zone_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate zone ID format.

    Args:
        zone_id: Zone ID string

    Returns:
        tuple: (is_valid, error_message)
    """
    if not zone_id:
        return False, "Zone ID cannot be empty"

    # Zone ID format: alphanumeric + underscore + hyphen
    pattern = r"^[A-Za-z0-9_-]+$"
    if not re.match(pattern, zone_id):
        return False, "Zone ID must be alphanumeric (with _ and - allowed)"

    if len(zone_id) > 64:
        return False, "Zone ID exceeds maximum length (64 characters)"

    return True, None


def validate_processing_mode(mode: str) -> tuple[bool, Optional[str]]:
    """
    Validate sensor processing mode.

    Args:
        mode: Processing mode string

    Returns:
        tuple: (is_valid, error_message)
    """
    if mode not in constants.PROCESSING_MODES:
        return (
            False,
            f"Invalid processing mode. Must be one of: {', '.join(constants.PROCESSING_MODES)}",
        )

    return True, None


def validate_device_status(status: str) -> tuple[bool, Optional[str]]:
    """
    Validate device status.

    Args:
        status: Device status string

    Returns:
        tuple: (is_valid, error_message)
    """
    if status not in constants.DEVICE_STATUSES:
        return (
            False,
            f"Invalid device status. Must be one of: {', '.join(constants.DEVICE_STATUSES)}",
        )

    return True, None


def validate_system_command(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate system command.

    Args:
        command: System command string

    Returns:
        tuple: (is_valid, error_message)
    """
    if command not in constants.SYSTEM_COMMANDS:
        return (
            False,
            f"Invalid system command. Must be one of: {', '.join(constants.SYSTEM_COMMANDS)}",
        )

    return True, None


def validate_actuator_command(command: str) -> tuple[bool, Optional[str]]:
    """
    Validate actuator command.

    Args:
        command: Actuator command string

    Returns:
        tuple: (is_valid, error_message)
    """
    if command not in constants.ACTUATOR_COMMANDS:
        return (
            False,
            f"Invalid actuator command. Must be one of: {', '.join(constants.ACTUATOR_COMMANDS)}",
        )

    return True, None


def validate_hardware_type(hardware_type: str) -> tuple[bool, Optional[str]]:
    """
    Validate hardware type.

    Args:
        hardware_type: Hardware type string

    Returns:
        tuple: (is_valid, error_message)
    """
    if hardware_type not in constants.HARDWARE_TYPES:
        return (
            False,
            f"Invalid hardware type. Must be one of: {', '.join(constants.HARDWARE_TYPES)}",
        )

    return True, None
