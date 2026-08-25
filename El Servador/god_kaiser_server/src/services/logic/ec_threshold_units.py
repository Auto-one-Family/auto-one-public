"""
EC hysteresis threshold unit helpers (AUT-1268 / AUT-1270).

Canonical EC unit is µS/cm (E1). Legacy rules stored mS-magnitude numbers
(e.g. 1.6 / 1.7) in those fields — migrate by ×1000 when the value looks like mS.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, List, Tuple

# Thresholds below this for EC are treated as legacy mS/cm magnitudes.
_MS_MAGNITUDE_MAX = 50.0
_US_PER_MS = 1000.0

_THRESHOLD_KEYS = (
    "activate_below",
    "activate_above",
    "deactivate_below",
    "deactivate_above",
)


def _is_ec_sensor_type(sensor_type: Any) -> bool:
    return str(sensor_type or "").lower() == "ec"


def _needs_us_migration(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 < numeric < _MS_MAGNITUDE_MAX


def migrate_ec_hysteresis_conditions(
    conditions: Any,
) -> Tuple[Any, List[str]]:
    """
    Multiply EC hysteresis thresholds that look like mS-magnitude by 1000.

    Idempotent for already-migrated µS/cm values (>= 50). Does not touch pH
    or non-hysteresis conditions.

    Returns:
        (migrated_conditions, change_descriptions)
    """
    changes: List[str] = []
    migrated = deepcopy(conditions)

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("logic") in ("AND", "OR"):
            _walk(node.get("conditions", []))
            return
        if node.get("type") != "hysteresis" or not _is_ec_sensor_type(node.get("sensor_type")):
            return
        for key in _THRESHOLD_KEYS:
            if key not in node or node[key] is None:
                continue
            if not _needs_us_migration(node[key]):
                continue
            old = float(node[key])
            new = old * _US_PER_MS
            node[key] = new
            changes.append(f"{key}: {old} → {new}")

    _walk(migrated)
    return migrated, changes
