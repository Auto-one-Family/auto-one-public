"""
Subzone API helpers.

Shared utilities for sensors and actuators API routes.
"""

from typing import Optional


def normalize_subzone_id(value: Optional[str]) -> Optional[str]:
    """
    Normalize subzone_id for API: "__none__" and empty string mean "remove from all subzones".
    Frontend may send "__none__" as sentinel for "Keine Subzone"; backend treats it as None.

    Used by sensors.py and actuators.py for consistent subzone assignment semantics.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v in ("", "__none__"):
        return None
    return v
