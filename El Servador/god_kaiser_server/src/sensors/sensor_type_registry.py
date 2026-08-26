"""
Sensor Type Registry - Centralized sensor type normalization and multi-value sensor definitions

Provides:
- Sensor type mapping (ESP32 → Server Processor)
- Multi-value sensor definitions (e.g., SHT31 with temp + humidity)
- I2C device address mappings
- Device type information

Usage:
    from .sensor_type_registry import normalize_sensor_type, get_multi_value_sensor_def

    normalized = normalize_sensor_type("temperature_sht31")  # Returns "sht31_temp"
    sht31_def = get_multi_value_sensor_def("sht31")  # Returns multi-value definition
"""

from typing import Any, Dict, List, Optional, TypedDict

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class ValueDefinition(TypedDict):
    """Definition for a single value provided by a multi-value sensor."""

    sensor_type: str  # Server processor type (e.g., "sht31_temp")
    name: str  # Human-readable name (e.g., "Temperature")
    unit: str  # Unit (e.g., "°C")


class MultiValueSensorDefinition(TypedDict):
    """Definition for a multi-value sensor (e.g., SHT31, BMP280)."""

    device_type: str  # Communication type: "i2c", "uart", etc.
    device_address: int  # I2C address (e.g., 0x44 for SHT31)
    values: List[ValueDefinition]  # List of values this sensor provides
    i2c_pins: Optional[Dict[str, int]]  # I2C pin configuration (SDA, SCL)


# Sensor Type Mapping: ESP32 → Server Processor
# Maps sensor types sent by ESP32 to the processor types expected by the server
SENSOR_TYPE_MAPPING: Dict[str, str] = {
    # SHT31 variants
    "temperature_sht31": "sht31_temp",
    "humidity_sht31": "sht31_humidity",
    "sht31_temp": "sht31_temp",  # Already normalized
    "sht31_humidity": "sht31_humidity",  # Already normalized
    # DS18B20 variants
    "temperature_ds18b20": "ds18b20",
    "ds18b20": "ds18b20",  # Already normalized
    # BMP280 variants (Phase 2)
    "pressure_bmp280": "bmp280_pressure",
    "temperature_bmp280": "bmp280_temp",
    "bmp280_pressure": "bmp280_pressure",  # Already normalized
    "bmp280_temp": "bmp280_temp",  # Already normalized
    # pH sensor
    "ph_sensor": "ph",
    "ph": "ph",  # Already normalized
    # EC sensor (Phase 2)
    "ec_sensor": "ec",
    "ec": "ec",  # Already normalized
    # Moisture sensor (Phase 2)
    "moisture": "moisture",
    "soil_moisture": "moisture",  # Alias — normalize_sensor_type() returns "moisture"
    # BME280 variants (Phase 2)
    # BME280 has own processors (BME280TemperatureProcessor, BME280PressureProcessor).
    # Do NOT alias bme280_temp/bme280_pressure to bmp280_* types.
    "pressure_bme280": "bme280_pressure",
    "temperature_bme280": "bme280_temp",
    "humidity_bme280": "bme280_humidity",
    "bme280_pressure": "bme280_pressure",
    "bme280_temp": "bme280_temp",
    "bme280_humidity": "bme280_humidity",  # BME280HumidityProcessor
    # CO2 sensors (Phase 3)
    "mhz19_co2": "mhz19_co2",
    "scd30_co2": "scd30_co2",
    # Light sensor (Phase 3)
    "light": "light",
    "tsl2561": "light",
    "bh1750": "light",
    # Flow sensor (Phase 3)
    "flow": "flow",
    "yfs201": "flow",
    # Digital sensors
    "liquid_level": "liquid_level",
    # VPD: computed from temperature + humidity (VIRTUAL — no processor, raw passthrough)
    "vpd": "vpd",
    # MultispeQ snapshot sensors (VIRTUAL, via HTTP import, GPIO 200-249)
    "phi2": "phi2",
    "fv_fm": "fv_fm",
    "npqt": "npqt",
    "lef": "lef",
    "par_internal": "par_internal",
    "ppfd": "ppfd",
    "chlorophyll_spad": "chlorophyll_spad",
    "leaf_temp": "leaf_temp",
    "anthocyanin_index": "anthocyanin_index",
}


# Virtual Sensor Types: computed/event-driven, never scheduled by the simulation scheduler.
# These sensors must not appear in simulation_config.sensors and must not receive
# scheduled MQTT publishes. They are calculated on-the-fly from other sensor readings.
VIRTUAL_SENSOR_TYPES: set[str] = {
    "vpd",
    "phi2", "fv_fm", "npqt", "lef",
    "par_internal", "ppfd",
    "chlorophyll_spad", "leaf_temp", "anthocyanin_index",
}


# Multi-Value Sensor Definitions
# Defines sensors that provide multiple values (e.g., SHT31: temp + humidity)
MULTI_VALUE_SENSORS: Dict[str, MultiValueSensorDefinition] = {
    "sht31": {
        "device_type": "i2c",
        "device_address": 0x44,  # Default SHT31 address (0x45 if ADR pin to VIN)
        "values": [
            {
                "sensor_type": "sht31_temp",
                "name": "Temperature",
                "unit": "°C",
            },
            {
                "sensor_type": "sht31_humidity",
                "name": "Humidity",
                "unit": "%RH",
            },
        ],
        "i2c_pins": {"sda": 21, "scl": 22},  # ESP32 default I2C pins
    },
    "bmp280": {
        "device_type": "i2c",
        "device_address": 0x76,  # Default BMP280 address (0x77 if SDO to VCC)
        "values": [
            {
                "sensor_type": "bmp280_pressure",
                "name": "Pressure",
                "unit": "hPa",
            },
            {
                "sensor_type": "bmp280_temp",
                "name": "Temperature",
                "unit": "°C",
            },
        ],
        "i2c_pins": {"sda": 21, "scl": 22},  # ESP32 default I2C pins
    },
    "bme280": {
        "device_type": "i2c",
        "device_address": 0x76,  # Default BME280 address (0x77 if SDO to VCC)
        "values": [
            {
                "sensor_type": "bme280_temp",
                "name": "Temperature",
                "unit": "°C",
            },
            {
                "sensor_type": "bme280_pressure",
                "name": "Pressure",
                "unit": "hPa",
            },
            {
                "sensor_type": "bme280_humidity",
                "name": "Humidity",
                "unit": "%RH",
            },
        ],
        "i2c_pins": {"sda": 21, "scl": 22},  # ESP32 default I2C pins
    },
    # Future multi-value sensors can be added here:
    # "scd30": { ... },  # CO2 + Temp + Humidity
}


# MultispeQ virtual multi-value "device" (HTTP import, GPIO 200+).
# This entry uses an extended schema (`value_type`, `unit`, `gpio_offset`) that
# differs from the hardware MultiValueSensorDefinition above because MultispeQ
# values are imported as snapshots (no I2C address, no SDA/SCL pins). The list
# is consumed by the MultispeQ parser/import pipeline (AUT-212).
_MULTISPEQ_VALUE_DEFS: List[Dict[str, Any]] = [
    {"value_type": "phi2", "sensor_type": "phi2", "unit": "Φ", "gpio_offset": 0},
    {"value_type": "fv_fm", "sensor_type": "fv_fm", "unit": "Fv/Fm", "gpio_offset": 1},
    {"value_type": "npqt", "sensor_type": "npqt", "unit": "NPQt", "gpio_offset": 2},
    {"value_type": "lef", "sensor_type": "lef", "unit": "μmol e⁻/m²/s", "gpio_offset": 3},
    {"value_type": "par_internal", "sensor_type": "par_internal", "unit": "μmol/m²/s", "gpio_offset": 4},
    {"value_type": "ppfd", "sensor_type": "ppfd", "unit": "μmol/m²/s", "gpio_offset": 5},
    {"value_type": "chlorophyll_spad", "sensor_type": "chlorophyll_spad", "unit": "SPAD", "gpio_offset": 6},
    {"value_type": "leaf_temp", "sensor_type": "leaf_temp", "unit": "°C", "gpio_offset": 7},
    {"value_type": "anthocyanin_index", "sensor_type": "anthocyanin_index", "unit": "ARI", "gpio_offset": 8},
]

# Register MultispeQ in MULTI_VALUE_SENSORS without breaking the hardware
# schema consumers (expand_multi_value, get_all_value_types_for_device, ...).
# The entry is added only if not already present so re-imports stay idempotent.
if "multispeq" not in MULTI_VALUE_SENSORS:
    MULTI_VALUE_SENSORS["multispeq"] = {  # type: ignore[typeddict-item]
        "device_type": "virtual_http",
        "device_address": 0,
        "values": _MULTISPEQ_VALUE_DEFS,  # type: ignore[typeddict-item]
        "i2c_pins": None,
    }


# SSOT for canonical unit (+ optional mock defaults / plausible threshold ranges)
# per sensor_type. Read via get_unit_for_sensor_type() / get_plausible_range_for_sensor_type().
# Logic-rule thresholds and processed sensor values must use the same unit (AUT-1269).
#
# Plausible physical default start values for mock sensors.
# Applied when the user does NOT provide a raw_value (None).
# Keyed by the SPLIT sensor_type (e.g., "sht31_temp"), not the base type ("sht31").
# Optional plausible_min/plausible_max: typical operating range in the canonical unit
# for non-blocking rule-threshold warnings (AUT-1274) — tighter than absolute sensor clamps.
SENSOR_TYPE_MOCK_DEFAULTS: Dict[str, Dict[str, object]] = {
    # Temperature: typical room temperature
    "sht31_temp": {"raw_value": 22.0, "unit": "°C"},
    "ds18b20": {
        "raw_value": 20.0,
        "unit": "°C",
        "plausible_min": -55.0,
        "plausible_max": 125.0,
    },
    "bmp280_temp": {"raw_value": 22.0, "unit": "°C"},
    "bme280_temp": {"raw_value": 22.0, "unit": "°C"},
    "temperature": {"raw_value": 22.0, "unit": "°C"},
    # Humidity: moderate relative humidity
    "sht31_humidity": {"raw_value": 55.0, "unit": "%RH"},
    "bme280_humidity": {"raw_value": 55.0, "unit": "%RH"},
    "humidity": {"raw_value": 55.0, "unit": "%RH"},
    # Soil moisture: moderate substrate moisture
    "moisture": {"raw_value": 45.0, "unit": "%"},
    "soil_moisture": {"raw_value": 45.0, "unit": "%"},
    # Atmospheric pressure: sea-level standard
    "bmp280_pressure": {"raw_value": 1013.25, "unit": "hPa"},
    "bme280_pressure": {"raw_value": 1013.25, "unit": "hPa"},
    "pressure": {"raw_value": 1013.25, "unit": "hPa"},
    # Nutrient solution (canonical EC unit = µS/cm — E1 AUT-1268)
    "ph": {
        "raw_value": 6.2,
        "unit": "pH",
        "plausible_min": 0.0,
        "plausible_max": 14.0,
    },
    "ec": {
        "raw_value": 1500.0,
        "unit": "µS/cm",
        "plausible_min": 100.0,
        "plausible_max": 10000.0,
    },
    # Environment
    "co2": {"raw_value": 800.0, "unit": "ppm"},
    "mhz19_co2": {"raw_value": 800.0, "unit": "ppm"},
    "scd30_co2": {"raw_value": 800.0, "unit": "ppm"},
    "light": {"raw_value": 25000.0, "unit": "lux"},
    # Flow: pump off = 0 is correct; FS300A Messbereich 1–60 L/min (AUT-849)
    "flow": {
        "raw_value": 0.0,
        "unit": "L/min",
        "plausible_min": 0.0,
        "plausible_max": 60.0,
    },
    # Liquid level: binary 0=empty / 1=full
    "liquid_level": {"raw_value": 0.0, "unit": ""},
    # VPD: computed from temperature + humidity (optimal range ~0.8-1.2 kPa)
    "vpd": {"raw_value": 1.0, "unit": "kPa"},
    # MultispeQ photosynthesis snapshot sensors
    "phi2": {"raw_value": 0.75, "unit": "Φ"},
    "fv_fm": {"raw_value": 0.80, "unit": "Fv/Fm"},
    "npqt": {"raw_value": 0.30, "unit": "NPQt"},
    "lef": {"raw_value": 120.0, "unit": "µmol/(m²·s)"},
    "par_internal": {"raw_value": 800.0, "unit": "µmol/(m²·s)"},
    "ppfd": {"raw_value": 800.0, "unit": "µmol/(m²·s)"},
    "chlorophyll_spad": {"raw_value": 40.0, "unit": "SPAD"},
    "leaf_temp": {"raw_value": 22.0, "unit": "°C"},
    "anthocyanin_index": {"raw_value": 0.15, "unit": "ACI"},
}


def get_mock_default_raw_value(sensor_type: str, user_provided_raw: Optional[float]) -> float:
    """Return the user value if provided, otherwise a plausible physical default.

    User values always take precedence.  ``None`` means "no value given"
    (triggers default lookup), while ``0.0`` means "user explicitly set 0".
    """
    if user_provided_raw is not None:
        return user_provided_raw
    defaults = SENSOR_TYPE_MOCK_DEFAULTS.get(sensor_type.lower())
    if defaults:
        return float(defaults["raw_value"])
    return 0.0


def normalize_sensor_type(sensor_type: str) -> str:
    """
    Normalize sensor type from ESP32 format to server processor format.

    Args:
        sensor_type: Sensor type from ESP32 (e.g., "temperature_sht31")

    Returns:
        Normalized sensor type for server processor lookup (e.g., "sht31_temp")

    Example:
        >>> normalize_sensor_type("temperature_sht31")
        'sht31_temp'
        >>> normalize_sensor_type("sht31_temp")  # Already normalized
        'sht31_temp'
        >>> normalize_sensor_type("unknown_type")  # Unknown type
        'unknown_type'
    """
    if not sensor_type:
        return sensor_type

    normalized = SENSOR_TYPE_MAPPING.get(sensor_type.lower(), sensor_type.lower())

    if normalized != sensor_type.lower():
        logger.debug(f"Normalized sensor type: '{sensor_type}' → '{normalized}'")

    return normalized


def get_unit_for_sensor_type(sensor_type: str) -> Optional[str]:
    """
    SSOT accessor: canonical unit for a sensor type (AUT-1269).

    Looks up SENSOR_TYPE_MOCK_DEFAULTS for the unit. Logic-rule thresholds and
    processed sensor values must be expressed in this unit (EC → µS/cm).

    Args:
        sensor_type: Normalized sensor type (e.g., "ds18b20", "sht31_temp", "ec")

    Returns:
        Unit string (e.g., "°C", "%RH", "µS/cm") or None if unknown
    """
    key = sensor_type.lower()
    defaults = SENSOR_TYPE_MOCK_DEFAULTS.get(key)
    if defaults and "unit" in defaults:
        return str(defaults["unit"])
    return None


def get_plausible_range_for_sensor_type(
    sensor_type: str,
) -> Optional[Dict[str, float]]:
    """
    SSOT accessor: typical operating range in the canonical unit (AUT-1269/F5).

    Used for non-blocking rule-threshold plausibility warnings. Not the absolute
    sensor clamp (e.g. EC library 0–20000) — tighter so mS-magnitude mistakes
    like ``1.6`` in a µS/cm field are flagged.

    Args:
        sensor_type: Normalized sensor type (e.g., "ec", "ph", "ds18b20")

    Returns:
        ``{"min": float, "max": float}`` or None if no range is defined
    """
    key = sensor_type.lower()
    defaults = SENSOR_TYPE_MOCK_DEFAULTS.get(key)
    if not defaults:
        return None
    if "plausible_min" not in defaults or "plausible_max" not in defaults:
        return None
    return {
        "min": float(defaults["plausible_min"]),
        "max": float(defaults["plausible_max"]),
    }


def sanitize_unit_encoding(unit: str) -> str:
    """
    Fix Latin-1 → UTF-8 double-encoding in unit strings.

    ESP32 firmware sends degree sign as Latin-1 byte 0xB0. When interpreted
    as UTF-8, this produces Mojibake (e.g., "Â°C" instead of "°C").

    Args:
        unit: Unit string potentially with encoding issues

    Returns:
        Correctly encoded UTF-8 unit string
    """
    if not unit:
        return unit
    try:
        # Try to detect double-encoding: if re-encoding as Latin-1 then
        # decoding as UTF-8 produces a valid shorter string, it was double-encoded
        fixed = unit.encode("latin-1").decode("utf-8")
        if len(fixed) < len(unit):
            return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass  # Already correct UTF-8 or non-Latin content
    return unit


def get_multi_value_sensor_def(device_type: str) -> Optional[MultiValueSensorDefinition]:
    """
    Get multi-value sensor definition by device type.

    Args:
        device_type: Device type identifier (e.g., "sht31", "bmp280")

    Returns:
        MultiValueSensorDefinition if found, None otherwise

    Example:
        >>> def_ = get_multi_value_sensor_def("sht31")
        >>> def_["device_address"]
        0x44
        >>> len(def_["values"])
        2
    """
    return MULTI_VALUE_SENSORS.get(device_type.lower())


def is_multi_value_sensor(device_type: str) -> bool:
    """
    Check if a device type is a multi-value sensor.

    Args:
        device_type: Device type identifier (e.g., "sht31")

    Returns:
        True if device type provides multiple values, False otherwise

    Example:
        >>> is_multi_value_sensor("sht31")
        True
        >>> is_multi_value_sensor("ds18b20")
        False
    """
    return device_type.lower() in MULTI_VALUE_SENSORS


def get_device_type_from_sensor_type(sensor_type: str) -> Optional[str]:
    """
    Extract device type from sensor type.

    For multi-value sensors, extracts the base device type.
    For single-value sensors, returns None.

    Args:
        sensor_type: Normalized sensor type (e.g., "sht31_temp")

    Returns:
        Device type (e.g., "sht31") if multi-value sensor, None otherwise

    Example:
        >>> get_device_type_from_sensor_type("sht31_temp")
        'sht31'
        >>> get_device_type_from_sensor_type("ds18b20")
        None
    """
    normalized = normalize_sensor_type(sensor_type)

    # Check if this sensor type belongs to a multi-value sensor.
    # Hardware sensors expose ``sensor_type`` per value; the MultispeQ entry
    # uses ``value_type`` (extended schema), so we accept both.
    for device_type, definition in MULTI_VALUE_SENSORS.items():
        for value_def in definition["values"]:
            value_type_key = value_def.get("sensor_type") or value_def.get("value_type")
            if value_type_key == normalized:
                return device_type

    return None


def expand_multi_value(
    base_type: str,
    user_name: str = "",
    **common_fields: object,
) -> List[dict]:
    """
    Expand a base multi-value sensor type into N logical sensor config dicts.

    Shared by BOTH batch-create (create_mock_device) and single-add (add_sensor)
    to guarantee identical splitting behavior.

    Args:
        base_type: Base device type (e.g., "sht31", "bme280")
        user_name: User-given name for the sensor
        **common_fields: Fields shared across all sub-types (gpio, i2c_address, etc.)

    Returns:
        List of dicts, each representing one sub-type with keys:
        sensor_type, name, unit, plus all common_fields.
        Empty list if base_type is not a multi-value sensor.

    Example:
        >>> expand_multi_value("sht31", "Klima Boden", gpio=0, i2c_address=68)
        [{"sensor_type": "sht31_temp", "name": "Klima Boden Temperature", "unit": "°C", "gpio": 0, ...},
         {"sensor_type": "sht31_humidity", "name": "Klima Boden Humidity", "unit": "%RH", "gpio": 0, ...}]
    """
    definition = MULTI_VALUE_SENSORS.get(base_type.lower())
    if not definition:
        return []

    configs: List[dict] = []
    for value_def in definition["values"]:
        # Hardware schema uses ``sensor_type`` + ``name``; the MultispeQ entry
        # uses ``value_type`` and has no friendly name. Fall back gracefully so
        # both schemas are supported by the same expansion helper.
        sensor_type = value_def.get("sensor_type") or value_def.get("value_type", "")
        name_suffix = value_def.get("name") or sensor_type
        sensor_name = f"{user_name} {name_suffix}" if user_name else sensor_type
        configs.append(
            {
                "sensor_type": sensor_type,
                "name": sensor_name,
                "unit": value_def.get("unit", ""),
                **common_fields,
            }
        )
    return configs


def get_all_value_types_for_device(device_type: str) -> List[str]:
    """
    Get all sensor types (processor types) for a multi-value sensor device.

    Args:
        device_type: Device type identifier (e.g., "sht31")

    Returns:
        List of sensor types (e.g., ["sht31_temp", "sht31_humidity"])

    Example:
        >>> get_all_value_types_for_device("sht31")
        ['sht31_temp', 'sht31_humidity']
    """
    definition = get_multi_value_sensor_def(device_type)
    if not definition:
        return []

    return [
        value_def.get("sensor_type") or value_def.get("value_type", "")
        for value_def in definition["values"]
    ]


def get_i2c_address(device_type: str, default_address: Optional[int] = None) -> Optional[int]:
    """
    Get I2C address for a device type.

    Args:
        device_type: Device type identifier (e.g., "sht31")
        default_address: Default address to return if device not found

    Returns:
        I2C address (e.g., 0x44) if found, default_address otherwise

    Example:
        >>> get_i2c_address("sht31")
        68
        >>> get_i2c_address("unknown", default_address=0x48)
        72
    """
    definition = get_multi_value_sensor_def(device_type)
    if definition and definition["device_type"] == "i2c":
        return definition["device_address"]

    return default_address
