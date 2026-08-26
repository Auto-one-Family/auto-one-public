"""MultispeQ / PhotosynQ measurement parser.

Provides three pure functions used by the MultispeQ HTTP import endpoint:

* :func:`parse_photosynq_measurement` — map raw PhotosynQ JSON keys to internal
  sensor type names and coerce values to ``float``.
* :func:`validate_calibration` — emit human-readable warnings for values outside
  plausible physical ranges.
* :func:`expand_to_sensor_rows` — turn a parsed measurement into ``SensorData``-
  compatible row dicts (one per value), assigning a deterministic GPIO offset
  starting at ``gpio_base`` (typically 200 for the virtual MultispeQ range).

The functions are intentionally side-effect free so they can be called from
HTTP handlers, batch importers, and unit tests alike.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

# Mapping: PhotosynQ JSON key -> internal sensor_type (matches
# SENSOR_TYPE_MAPPING and VIRTUAL_SENSOR_TYPES in sensor_type_registry).
MULTISPEQ_FIELD_MAP: dict[str, str] = {
    "Phi2": "phi2",
    "FvFm": "fv_fm",
    "NPQt": "npqt",
    "LEF": "lef",
    "PAR_Ambient": "par_internal",
    "PPFD": "ppfd",
    "Chl_SPAD": "chlorophyll_spad",
    "Leaf_Temp": "leaf_temp",
    "Anthocyanin_Index": "anthocyanin_index",
}

# Canonical units per internal sensor_type. Kept local to the parser to avoid a
# circular dependency with sensor_type_registry while staying consistent with
# SENSOR_TYPE_MOCK_DEFAULTS / MULTI_VALUE_SENSORS["multispeq"].
MULTISPEQ_UNITS: dict[str, str] = {
    "phi2": "Φ",
    "fv_fm": "Fv/Fm",
    "npqt": "NPQt",
    "lef": "μmol e⁻/m²/s",
    "par_internal": "μmol/m²/s",
    "ppfd": "μmol/m²/s",
    "chlorophyll_spad": "SPAD",
    "leaf_temp": "°C",
    "anthocyanin_index": "ARI",
}

# Plausible physical ranges per internal sensor_type. Values outside the range
# generate a warning in :func:`validate_calibration` but are not rejected.
_CALIBRATION_RANGES: dict[str, tuple[float, float]] = {
    "phi2": (0.0, 1.0),
    "fv_fm": (0.0, 1.0),
    "npqt": (0.0, 10.0),
    "lef": (0.0, 500.0),
    "par_internal": (0.0, 2500.0),
    "leaf_temp": (-10.0, 60.0),
    "chlorophyll_spad": (0.0, 100.0),
}


def parse_photosynq_measurement(raw: dict) -> dict[str, float]:
    """Map a raw PhotosynQ measurement to internal sensor_type → float.

    Only keys present in :data:`MULTISPEQ_FIELD_MAP` are considered. Values
    that cannot be coerced to ``float`` (or that are ``None``) are skipped.

    Args:
        raw: Raw PhotosynQ JSON dict (arbitrary keys allowed).

    Returns:
        Dict mapping internal sensor_type to its float value. Missing or
        invalid fields are simply omitted.
    """
    parsed: dict[str, float] = {}
    if not raw:
        return parsed

    for source_key, internal_key in MULTISPEQ_FIELD_MAP.items():
        if source_key not in raw:
            continue
        value = raw[source_key]
        if value is None:
            continue
        try:
            parsed[internal_key] = float(value)
        except (TypeError, ValueError):
            # Silently skip non-numeric payloads — the import endpoint can log
            # at a higher level if required.
            continue
    return parsed


def validate_calibration(parsed: dict[str, float]) -> list[str]:
    """Return human-readable warnings for values outside plausible ranges.

    Args:
        parsed: Output of :func:`parse_photosynq_measurement`.

    Returns:
        List of warning strings. Empty list means everything is within range.
        Missing fields never generate a warning (all values are optional).
    """
    warnings: list[str] = []
    for sensor_type, (lower, upper) in _CALIBRATION_RANGES.items():
        if sensor_type not in parsed:
            continue
        value = parsed[sensor_type]
        if value < lower or value > upper:
            warnings.append(
                f"{sensor_type}={value} outside plausible range [{lower}, {upper}]"
            )
    return warnings


def expand_to_sensor_rows(
    parsed: dict[str, float],
    esp_id: str,
    gpio_base: int,
    timestamp: datetime,
    plant_id: Optional[uuid.UUID] = None,
) -> list[dict]:
    """Expand a parsed measurement into ``SensorData``-compatible row dicts.

    Each row corresponds to exactly one MultispeQ value and gets a stable GPIO
    offset derived from its position in :data:`MULTISPEQ_FIELD_MAP`. With
    ``gpio_base=200`` the assignments are::

        phi2              -> 200
        fv_fm             -> 201
        npqt              -> 202
        lef               -> 203
        par_internal      -> 204
        ppfd              -> 205
        chlorophyll_spad  -> 206
        leaf_temp         -> 207
        anthocyanin_index -> 208

    Args:
        parsed: Output of :func:`parse_photosynq_measurement`.
        esp_id: Owning ESP / virtual device identifier.
        gpio_base: First GPIO in the virtual MultispeQ range (typically 200).
        timestamp: Measurement timestamp (should be timezone-aware UTC).
        plant_id: Optional plant association.

    Returns:
        List of dicts ready for ``SensorData`` insert. Rows are emitted only
        for keys that are present in ``parsed``.
    """
    # Stable offset = index of internal sensor_type in MULTISPEQ_FIELD_MAP.values().
    ordered_internal_types = list(MULTISPEQ_FIELD_MAP.values())
    offset_by_type = {name: idx for idx, name in enumerate(ordered_internal_types)}

    rows: list[dict] = []
    for sensor_type in ordered_internal_types:
        if sensor_type not in parsed:
            continue
        value = parsed[sensor_type]
        rows.append(
            {
                "esp_id": esp_id,
                "gpio": gpio_base + offset_by_type[sensor_type],
                "sensor_type": sensor_type,
                "raw_value": value,
                "processed_value": value,
                "unit": MULTISPEQ_UNITS.get(sensor_type, ""),
                "processing_mode": "snapshot",
                "quality": "good",
                "timestamp": timestamp,
                "data_source": "production",
                "plant_id": plant_id,
            }
        )
    return rows
