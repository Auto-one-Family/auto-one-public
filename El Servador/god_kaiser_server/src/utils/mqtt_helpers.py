"""
MQTT Helper Functions: Topic parsing, validation, formatting

Note: Topic building is already implemented in mqtt/topics.py.
This module provides additional helper functions for MQTT message formatting.
"""

from typing import Any, Dict, Optional


def format_mqtt_payload(data: Dict[str, Any], include_timestamp: bool = True) -> Dict[str, Any]:
    """
    Format data as MQTT payload with optional timestamp.

    Args:
        data: Data dictionary to format
        include_timestamp: Whether to include timestamp field

    Returns:
        Formatted payload dictionary
    """
    payload = data.copy()

    if include_timestamp:
        from .time_helpers import unix_timestamp_s

        payload["timestamp"] = unix_timestamp_s()

    return payload


def validate_mqtt_payload(
    payload: Dict[str, Any], required_fields: list[str]
) -> tuple[bool, Optional[str]]:
    """
    Validate MQTT payload has required fields.

    Args:
        payload: Payload dictionary to validate
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, error_message)
    """
    missing_fields = [field for field in required_fields if field not in payload]

    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"

    return True, None


def get_qos_level(message_type: str) -> int:
    """
    Get appropriate QoS level for message type.

    Args:
        message_type: Message type (e.g., "sensor_data", "actuator_command")

    Returns:
        QoS level (0, 1, or 2)
    """
    # High-priority messages use QoS 2 (exactly once)
    high_priority = ["actuator_command", "config", "system_command"]

    # Medium-priority messages use QoS 1 (at least once)
    medium_priority = ["sensor_data", "actuator_status", "heartbeat"]

    if message_type in high_priority:
        return 2
    elif message_type in medium_priority:
        return 1
    else:
        return 0  # Default: at most once
