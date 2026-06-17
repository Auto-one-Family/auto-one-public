"""
Schema Registry API — Device-type JSON Schemas for metadata validation (Phase K4 L0.2)

Provides:
- GET /v1/schema-registry/         — List available device types
- GET /v1/schema-registry/{type}   — Schema for a device type (sensor or actuator)
- POST /v1/schema-registry/{type}/validate — Validate metadata against schema

Schemas are in-code minimal defaults; optional: sync from El Frontend src/config/device-schemas.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..deps import ActiveUser

router = APIRouter(prefix="/v1/schema-registry", tags=["schema-registry"])

# Minimal base properties (matches Frontend base.schema.json)
_BASE_PROPERTIES: dict[str, Any] = {
    "manufacturer": {"type": "string", "title": "Hersteller"},
    "model": {"type": "string", "title": "Modell"},
    "serial_number": {"type": "string", "title": "Seriennummer"},
    "datasheet_url": {"type": "string", "format": "uri", "title": "Datenblatt-Link"},
    "notes": {"type": "string", "title": "Notizen"},
}

# Device types known to the registry (align with Frontend device-schemas)
SENSOR_TYPES = ["sht31", "bmp280", "ds18b20", "moisture", "ph", "ec", "light"]
ACTUATOR_TYPES = ["relay", "pwm"]
ALL_DEVICE_TYPES = SENSOR_TYPES + ACTUATOR_TYPES


def _get_schema_for_type(device_type: str) -> dict[str, Any]:
    """Return merged (base + device) JSON Schema for the given type."""
    base: dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": dict(_BASE_PROPERTIES),
    }
    if device_type in SENSOR_TYPES:
        if device_type == "sht31":
            base["properties"].update(
                {
                    "i2c_address": {"type": "string", "enum": ["0x44", "0x45"], "default": "0x44"},
                    "accuracy_temperature": {"type": "string", "default": "±0.3°C"},
                    "accuracy_humidity": {"type": "string", "default": "±2% RH"},
                }
            )
        elif device_type == "ds18b20":
            base["properties"].update(
                {
                    "onewire_address": {"type": "string", "title": "OneWire ROM"},
                }
            )
    elif device_type in ACTUATOR_TYPES:
        base["properties"].update(
            {
                "inverted": {"type": "boolean", "default": False},
            }
        )
    return base


@router.get("", summary="List device types")
async def list_schemas(
    _user: ActiveUser,
) -> dict[str, list[str]]:
    """Return all device types that have a schema (sensors and actuators)."""
    return {
        "sensors": SENSOR_TYPES,
        "actuators": ACTUATOR_TYPES,
    }


@router.get("/{device_type}", summary="Get schema for device type")
async def get_schema(
    device_type: str,
    _user: ActiveUser,
) -> dict[str, Any]:
    """Return JSON Schema for the given device type (for metadata validation)."""
    if device_type not in ALL_DEVICE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown device type: {device_type}")
    return _get_schema_for_type(device_type)


@router.post("/{device_type}/validate", summary="Validate metadata")
async def validate_metadata(
    device_type: str,
    body: dict[str, Any],
    _user: ActiveUser,
) -> dict[str, Any]:
    """Validate a metadata object against the device type schema. Returns valid + optional errors."""
    if device_type not in ALL_DEVICE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown device type: {device_type}")
    schema = _get_schema_for_type(device_type)
    # Lazy import: jsonschema only needed when validate endpoint is called
    import jsonschema

    try:
        jsonschema.validate(instance=body, schema=schema)
        return {"valid": True}
    except jsonschema.ValidationError as e:
        return {
            "valid": False,
            "errors": [{"path": list(e.absolute_path), "message": e.message}],
        }
    except jsonschema.SchemaError as e:
        return {"valid": False, "errors": [{"message": str(e)}]}
