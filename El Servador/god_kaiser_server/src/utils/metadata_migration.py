"""
Metadata Schema Versioning & Lazy Migration (Phase K4 / L0.1)

Each JSONB/JSON metadata document can carry _schema_version.
Lazy migration runs on read (API layer or service) and updates in-place only when needed.
No batch migrations — avoids DB locks.
"""

from __future__ import annotations

from typing import Any

# Current schema versions per entity type. Bump when adding optional fields.
CURRENT_SCHEMA_VERSIONS: dict[str, int] = {
    "sensor_metadata": 1,
    "actuator_metadata": 1,
    "device_metadata": 1,
    "zone_context": 1,
}


def migrate_metadata(data: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Lazy migration: bring JSONB metadata to current schema version.

    Call on API read. Modifies data in-place only when version < current.
    New fields are added with safe defaults; never rename or remove (deprecate instead).

    Args:
        data: The metadata dict (e.g. sensor_metadata, device_metadata, custom_data).
        entity_type: One of CURRENT_SCHEMA_VERSIONS keys.

    Returns:
        The same dict (possibly updated with _schema_version and new optional fields).
    """
    if not isinstance(data, dict):
        return data

    target = CURRENT_SCHEMA_VERSIONS.get(entity_type, 1)
    version = data.get("_schema_version", 0)

    if version >= target:
        return data

    if entity_type == "sensor_metadata":
        if version < 1:
            data.setdefault("accuracy", {})
            data.setdefault("datasheet_url", None)
            data["_schema_version"] = 1

    elif entity_type == "actuator_metadata":
        if version < 1:
            data.setdefault("datasheet_url", None)
            data["_schema_version"] = 1

    elif entity_type == "device_metadata":
        if version < 1:
            data.setdefault("manufacturer", None)
            data.setdefault("model", None)
            data["_schema_version"] = 1

    elif entity_type == "zone_context":
        if version < 1:
            data.setdefault("custom_data", {})
            data["_schema_version"] = 1

    return data
