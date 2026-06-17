"""
Time Helper Functions: Timezone handling, formatting, parsing
"""

from datetime import datetime
from typing import Union

import time


def unix_timestamp_ms() -> int:
    """
    Get current Unix timestamp in milliseconds.

    Returns:
        Current Unix timestamp in milliseconds (int)
    """
    return int(time.time() * 1000)


def unix_timestamp_s() -> int:
    """
    Get current Unix timestamp in seconds.

    Returns:
        Current Unix timestamp in seconds (int)
    """
    return int(time.time())


def parse_timestamp(timestamp: Union[int, str]) -> datetime:
    """
    Parse timestamp from Unix seconds or ISO string.

    Args:
        timestamp: Unix timestamp (int, seconds) or ISO format string

    Returns:
        datetime object

    Raises:
        ValueError: If timestamp format is invalid
    """
    if isinstance(timestamp, int):
        # Unix timestamp in seconds
        return datetime.fromtimestamp(timestamp)
    elif isinstance(timestamp, str):
        # ISO format string
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            # Try parsing as Unix timestamp string
            try:
                return datetime.fromtimestamp(int(timestamp))
            except ValueError:
                raise ValueError(f"Invalid timestamp format: {timestamp}")
    else:
        raise ValueError(f"Timestamp must be int or str, got {type(timestamp)}")


def format_timestamp(dt: datetime) -> str:
    """
    Format datetime to ISO string.

    Args:
        dt: datetime object to format

    Returns:
        ISO format string (e.g., "2025-01-29T12:34:56.789Z")
    """
    return dt.isoformat() + "Z"
