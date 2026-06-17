"""
Data Helper Functions: Validation, transformation, aggregation
"""

import zlib


def normalize_sensor_data(raw_value: float, min_val: float, max_val: float) -> float:
    """
    Normalize sensor value to 0.0-1.0 range.

    Args:
        raw_value: Raw sensor value
        min_val: Minimum expected value
        max_val: Maximum expected value

    Returns:
        Normalized value in range [0.0, 1.0]

    Raises:
        ValueError: If min_val >= max_val
    """
    if min_val >= max_val:
        raise ValueError(f"min_val ({min_val}) must be less than max_val ({max_val})")

    # Clamp value to range
    clamped_value = max(min_val, min(raw_value, max_val))

    # Normalize to 0.0-1.0
    if max_val == min_val:
        return 0.0

    normalized = (clamped_value - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, normalized))  # Ensure result is in [0.0, 1.0]


def calculate_crc32(data: bytes) -> int:
    """
    Calculate CRC32 checksum for data.

    Args:
        data: Bytes to calculate checksum for

    Returns:
        CRC32 checksum as unsigned 32-bit integer
    """
    return zlib.crc32(data) & 0xFFFFFFFF


def validate_sensor_range(value: float, min_val: float, max_val: float) -> bool:
    """
    Validate sensor value is within valid range.

    Args:
        value: Sensor value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        True if value is within range [min_val, max_val], False otherwise
    """
    return min_val <= value <= max_val
