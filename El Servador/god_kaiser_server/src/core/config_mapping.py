"""
Configuration Field Mapping System

Defines field mappings between Server DB models and ESP32 payload format.
Designed for industrial systems with full configurability.

=============================================================================
ESP32 Config-Mapping System
=============================================================================

Dieses Modul definiert wie Sensor/Actuator-Daten aus der Datenbank
in ESP32-kompatible Config-Payloads transformiert werden.

ARCHITEKTUR:

  DB Model (SensorConfig/ActuatorConfig)
      ↓
  ConfigPayloadBuilder.build_combined_config() [services/config_builder.py]
      ↓
  ConfigMappingEngine.apply_sensor_mapping() / apply_actuator_mapping()
      ↓
  DEFAULT_SENSOR_MAPPINGS / DEFAULT_ACTUATOR_MAPPINGS (dieses Modul)
      ↓
  ESP32-Payload Dict
      ↓
  MQTT Topic: kaiser/{kaiser_id}/esp/{esp_id}/config

MAPPING-STRUKTUR:

  Jedes Mapping hat folgende Felder:
  - source: Pfad zum Feld im DB-Model (z.B. "gpio" oder "sensor_metadata.subzone_id")
  - target: Feldname im ESP32-Payload
  - field_type: "string", "int", "bool", "float"
  - required: True/False (ob Feld Pflicht ist)
  - default: Default-Wert wenn source leer
  - transform: Optional - Name einer Transform-Funktion aus TRANSFORMS Dict

ERWEITERUNG:

  Um neue Felder zum ESP32 zu senden, hier ein Mapping hinzufügen.
  Für neue Transform-Funktionen das TRANSFORMS Dict erweitern.

HINWEIS:

  Ein manueller Config-Push-Endpoint existiert NICHT.
  Configs werden automatisch nach Sensor/Actuator CRUD-Operationen gesendet.
  Siehe: api/v1/sensors.py und api/v1/actuators.py

=============================================================================

Features:
- Default mappings for sensors and actuators
- Dynamic mapping override via SystemConfig
- Validation of mappings
- Support for nested field extraction (metadata.subzone_id)
- Type conversion support

Configuration Key (SystemConfig):
- config_mapping.sensor: Custom sensor field mappings
- config_mapping.actuator: Custom actuator field mappings

Phase: Runtime Config Flow Implementation
Priority: MEDIUM
Status: IMPLEMENTED
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# ACTUATOR TYPE MAPPING: Server DB → ESP32
# =============================================================================
# The Server stores normalized types (e.g. "digital" for all binary actuators).
# The ESP32 expects specific types ("relay", "pump", "valve", "pwm").
#
# This mapping converts Server types back to ESP32-compatible types.

# ESP32-compatible Actuator Types (from El Trabajante/src/models/actuator_types.h)
ESP32_ACTUATOR_TYPES = frozenset({"pump", "valve", "pwm", "relay"})

# Reverse-Mapping: Server-Type → ESP32-Type
SERVER_TO_ESP32_ACTUATOR_TYPE = {
    "digital": "relay",  # Server "digital" → ESP32 "relay"
    "binary": "relay",  # Alternative name for binary actuators
    "switch": "relay",  # Alternative name for switch actuators
    # Types that remain unchanged:
    "relay": "relay",
    "pump": "pump",
    "valve": "valve",
    "pwm": "pwm",
}


def map_actuator_type_for_esp32(server_type: str) -> str:
    """
    Convert a Server actuator type to an ESP32-compatible type.

    Args:
        server_type: Actuator type from Server database (e.g. "digital")

    Returns:
        ESP32-compatible type (e.g. "relay")

    Raises:
        ValueError: If the type cannot be mapped

    Example:
        >>> map_actuator_type_for_esp32("digital")
        "relay"
        >>> map_actuator_type_for_esp32("pwm")
        "pwm"
    """
    if not server_type:
        raise ValueError("actuator_type must not be empty")

    server_type_lower = server_type.lower().strip()

    # Check after strip for whitespace-only input
    if not server_type_lower:
        raise ValueError("actuator_type must not be empty")

    # Directly ESP32-compatible?
    if server_type_lower in ESP32_ACTUATOR_TYPES:
        return server_type_lower

    # Apply mapping
    esp32_type = SERVER_TO_ESP32_ACTUATOR_TYPE.get(server_type_lower)

    if esp32_type is None:
        raise ValueError(
            f"Unknown actuator_type '{server_type}'. "
            f"Allowed: {', '.join(sorted(SERVER_TO_ESP32_ACTUATOR_TYPE.keys()))}"
        )

    return esp32_type


class FieldType(str, Enum):
    """Supported field types for mapping."""

    STRING = "string"
    INTEGER = "int"
    FLOAT = "float"
    BOOLEAN = "bool"
    JSON = "json"


@dataclass
class FieldMapping:
    """
    Single field mapping definition.

    Attributes:
        source: Source field path (supports dots for nested: "metadata.subzone_id")
        target: Target field name in ESP32 payload
        field_type: Expected field type
        default: Default value if source is None
        required: Whether field must have a value
        transform: Optional transformation function name
    """

    source: str
    target: str
    field_type: FieldType = FieldType.STRING
    default: Any = None
    required: bool = False
    transform: Optional[str] = None


# =============================================================================
# Default Field Mappings
# =============================================================================


# Sensor field mappings (Server → ESP32)
DEFAULT_SENSOR_MAPPINGS: List[Dict[str, Any]] = [
    {
        "source": "gpio",
        "target": "gpio",
        "field_type": "int",
        "required": True,
    },
    {
        "source": "sensor_type",
        "target": "sensor_type",
        "field_type": "string",
        "required": True,
    },
    {
        "source": "sensor_name",
        "target": "sensor_name",
        "field_type": "string",
        "default": "",
    },
    {
        "source": "sensor_metadata.subzone_id",
        "target": "subzone_id",
        "field_type": "string",
        "default": "",
    },
    {
        "source": "enabled",
        "target": "active",
        "field_type": "bool",
        "default": True,
    },
    {
        "source": "sample_interval_ms",
        "target": "sample_interval_ms",
        "field_type": "int",
        "default": 1000,
    },
    # ESP32 expects raw_mode field (always true for server-processed sensors)
    {
        "source": "_constant",
        "target": "raw_mode",
        "field_type": "bool",
        "default": True,
    },
    # Phase 2C: Operating Mode for ESP32 measurement behavior
    # Modes: continuous (auto-measure), on_demand (command only), paused (no measure), scheduled (server-triggered)
    {
        "source": "operating_mode",
        "target": "operating_mode",
        "field_type": "string",
        "required": False,
        "default": "continuous",
    },
    # Phase 2C: Per-sensor measurement interval in seconds (converted from ms)
    {
        "source": "sample_interval_ms",
        "target": "measurement_interval_seconds",
        "field_type": "int",
        "required": False,
        "default": 30,
        "transform": "ms_to_seconds",
    },
    # =============================================================
    # Interface-specific fields (OneWire, I2C, SPI)
    #
    # Diese Felder werden für Bus-basierte Sensoren benötigt:
    # - interface_type: ANALOG, DIGITAL, I2C, ONEWIRE, SPI
    # - onewire_address: 16-char hex ROM-Code für DS18B20 etc.
    # - i2c_address: 7-bit I2C Adresse (0x00-0x7F)
    #
    # Hinzugefügt: 2026-02-03 (BUG-ONEWIRE-CONFIG-001)
    # =============================================================
    {
        "source": "interface_type",
        "target": "interface_type",
        "field_type": "string",
        "required": False,
        "default": "ANALOG",
    },
    {
        "source": "onewire_address",
        "target": "onewire_address",
        "field_type": "string",
        "required": False,
        "default": "",
        "transform": "strip_auto_prefix",
    },
    {
        "source": "i2c_address",
        "target": "i2c_address",
        "field_type": "int",
        "required": False,
        "default": 0,
    },
    # =============================================================
    # External ADC (ADS1115) acquisition fields — per-sensor.
    #
    # pH/EC can OPTIONALLY be read via an external 16-bit I2C ADC instead of the
    # internal ESP32 ADC. Only the acquisition source changes; the RAW value
    # still flows through the identical conversion/calibration path.
    #
    # adc_source = "internal" (default) | "ads1115"
    # adc_channel = ADS1115 single-ended channel 0-3 (255 = not set, internal ADC)
    # pga_gain    = ADS1115 PGA full-scale range in volts, e.g. "4.096"
    # =============================================================
    {
        "source": "adc_source",
        "target": "adc_source",
        "field_type": "string",
        "required": False,
        "default": "internal",
    },
    {
        "source": "adc_channel",
        "target": "adc_channel",
        "field_type": "int",
        "required": False,
        "default": 255,
    },
    {
        "source": "pga_gain",
        "target": "pga_gain",
        "field_type": "string",
        "required": False,
        "default": "4.096",
    },
    # =============================================================
    # Digital sensor polarity — liquid_level (and future digital types).
    # active_low  = NPN / signal LOW when triggered (default, backwards-compatible)
    # active_high = PNP / signal HIGH when triggered (XKC-Y26S-PNP)
    # =============================================================
    {
        "source": "polarity",
        "target": "polarity",
        "field_type": "string",
        "required": False,
        "default": "active_low",
    },
    # =============================================================
    # UART sensor fields (AUT-576: SEN0220 / MH-Z16 CO2 via UART)
    #
    # UART pins are stored in sensor_metadata by the API layer when
    # the operator creates a CO2 sensor with interface_type=UART.
    # The ESP32 firmware reads uart_rx_pin / uart_tx_pin / uart_baud
    # from the config payload top-level to initialise Serial2.
    #
    # Default 255 = "not set" (same sentinel the firmware uses in NVS).
    # =============================================================
    {
        "source": "sensor_metadata.uart_rx_pin",
        "target": "uart_rx_pin",
        "field_type": "int",
        "required": False,
        "default": 255,
    },
    {
        "source": "sensor_metadata.uart_tx_pin",
        "target": "uart_tx_pin",
        "field_type": "int",
        "required": False,
        "default": 255,
    },
    {
        "source": "sensor_metadata.uart_baud",
        "target": "uart_baud",
        "field_type": "int",
        "required": False,
        "default": 9600,
    },
]


# Actuator field mappings (Server → ESP32)
DEFAULT_ACTUATOR_MAPPINGS: List[Dict[str, Any]] = [
    {
        "source": "gpio",
        "target": "gpio",
        "field_type": "int",
        "required": True,
    },
    {
        "source": "actuator_type",
        "target": "actuator_type",
        "field_type": "string",
        "required": True,
        # BUG-FIX: Transform "digital" → "relay" for ESP32 compatibility
        # Server normalizes relay/pump/valve to "digital" but ESP32 needs "relay"
        "transform": "actuator_type_to_esp32",
    },
    {
        "source": "actuator_name",
        "target": "actuator_name",
        "field_type": "string",
        "default": "",
    },
    {
        "source": "actuator_metadata.subzone_id",
        "target": "subzone_id",
        "field_type": "string",
        "default": "",
    },
    {
        "source": "enabled",
        "target": "active",
        "field_type": "bool",
        "default": True,
    },
    {
        "source": "actuator_metadata.aux_gpio",
        "target": "aux_gpio",
        "field_type": "int",
        "default": 255,  # 255 = unused
    },
    {
        "source": "actuator_metadata.critical",
        "target": "critical",
        "field_type": "bool",
        "default": False,
    },
    {
        "source": "actuator_metadata.inverted_logic",
        "target": "inverted_logic",
        "field_type": "bool",
        "default": False,
    },
    {
        "source": "actuator_metadata.default_state",
        "target": "default_state",
        "field_type": "bool",
        "default": False,
    },
    {
        "source": "actuator_metadata.default_pwm",
        "target": "default_pwm",
        "field_type": "int",
        "default": 0,
    },
    {
        # SAFETY-P1 Mechanism C: max_runtime_ms — from safety_constraints.max_runtime (seconds) → ms
        # Default: 3600000ms (1h). Server can set lower values per actuator type (e.g. 120000ms for pumps).
        "source": "safety_constraints.max_runtime",
        "target": "max_runtime_ms",
        "field_type": "int",
        "transform": "seconds_to_ms",
        "default": None,  # None → seconds_to_ms(None) → 3600000 (1h fallback)
    },
    {
        # Cooldown — from safety_constraints.cooldown_period (seconds) → cooldown_ms
        # Default: 30000ms (30s), matches ESP32 firmware's compiled PumpActuator default.
        "source": "safety_constraints.cooldown_period",
        "target": "cooldown_ms",
        "field_type": "int",
        "transform": "cooldown_seconds_to_ms",
        "default": None,  # None → cooldown_seconds_to_ms(None) → 30000 (30s fallback)
    },
]


# =============================================================================
# Mapping Engine
# =============================================================================


class ConfigMappingEngine:
    """
    Engine for applying field mappings to model objects.

    Supports:
    - Nested field extraction (metadata.field)
    - Type conversion
    - Default values
    - Custom transformations
    - Runtime configuration override

    Usage:
        engine = ConfigMappingEngine()

        # Use default mappings
        payload = engine.apply_sensor_mapping(sensor_model)

        # Or with custom mappings
        custom_mappings = [{"source": "name", "target": "custom_name"}]
        payload = engine.apply_mapping(model, custom_mappings)
    """

    # Available transform functions
    TRANSFORMS: Dict[str, Callable[[Any], Any]] = {
        "uppercase": lambda x: str(x).upper() if x else "",
        "lowercase": lambda x: str(x).lower() if x else "",
        "to_int": lambda x: int(x) if x is not None else 0,
        "to_float": lambda x: float(x) if x is not None else 0.0,
        "to_bool": lambda x: bool(x) if x is not None else False,
        "invert_bool": lambda x: not bool(x) if x is not None else True,
        # Phase 2C: Convert milliseconds to seconds for ESP32 measurement interval
        "ms_to_seconds": lambda x: (int(x) // 1000) if x else 30,
        # SAFETY-P1: Convert seconds to milliseconds for max_runtime_ms Config-Push
        "seconds_to_ms": lambda x: (int(x) * 1000) if x is not None else 3600000,
        # Cooldown: Convert seconds to milliseconds for cooldown_ms Config-Push
        # 0 = no cooldown (explicit contract: is not None check, not truthy check)
        "cooldown_seconds_to_ms": lambda x: (int(x) * 1000) if x is not None else 30000,
        # BUG-FIX: Convert Server actuator types to ESP32-compatible types
        # Server stores "digital" but ESP32 expects "relay"
        # See: El Trabajante/src/models/actuator_types.h (ActuatorTypeTokens)
        "actuator_type_to_esp32": map_actuator_type_for_esp32,
        # BUG-ONEWIRE-CONFIG-001 + R20-P6: Strip placeholder prefixes from OneWire addresses
        # ESP32 expects pure 16 hex char ROM-Code (e.g., "28FF641E8D3C0C79")
        # DB may store "AUTO_..." (auto-discovered) or "SIM_..." (simulated) addresses
        # Both are placeholders — real ESPs cannot use them, so return ""
        "strip_auto_prefix": lambda x: (
            ""
            if x and isinstance(x, str) and (x.startswith("AUTO_") or x.startswith("SIM_"))
            else (x or "")
        ),
    }

    def __init__(
        self,
        sensor_mappings: Optional[List[Dict[str, Any]]] = None,
        actuator_mappings: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize ConfigMappingEngine.

        Args:
            sensor_mappings: Custom sensor mappings (uses defaults if None)
            actuator_mappings: Custom actuator mappings (uses defaults if None)
        """
        self.sensor_mappings = sensor_mappings or DEFAULT_SENSOR_MAPPINGS
        self.actuator_mappings = actuator_mappings or DEFAULT_ACTUATOR_MAPPINGS

    def apply_sensor_mapping(self, model: Any) -> Dict[str, Any]:
        """
        Apply sensor field mappings to a model.

        Args:
            model: SensorConfig model instance

        Returns:
            ESP32-compatible payload dict
        """
        return self.apply_mapping(model, self.sensor_mappings)

    def apply_actuator_mapping(self, model: Any) -> Dict[str, Any]:
        """
        Apply actuator field mappings to a model.

        Args:
            model: ActuatorConfig model instance

        Returns:
            ESP32-compatible payload dict
        """
        return self.apply_mapping(model, self.actuator_mappings)

    def apply_mapping(
        self,
        model: Any,
        mappings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Apply field mappings to a model object.

        Args:
            model: Model instance with attributes
            mappings: List of field mapping definitions

        Returns:
            Transformed payload dict
        """
        payload: Dict[str, Any] = {}

        for mapping_def in mappings:
            source = mapping_def.get("source", "")
            target = mapping_def.get("target", "")
            field_type = mapping_def.get("field_type", "string")
            default = mapping_def.get("default")
            required = mapping_def.get("required", False)
            transform = mapping_def.get("transform")

            if not target:
                continue

            # Handle constant values (source="_constant")
            if source == "_constant":
                payload[target] = self._convert_type(default, field_type)
                continue

            # Extract value from model
            value = self._extract_value(model, source)

            # Apply default if value is None
            if value is None:
                if required:
                    logger.warning(f"Required field {source} is missing")
                value = default

            # Apply transformation if specified
            if transform and transform in self.TRANSFORMS:
                value = self.TRANSFORMS[transform](value)

            # Convert to target type
            value = self._convert_type(value, field_type)

            payload[target] = value

        return payload

    def _extract_value(self, model: Any, path: str) -> Any:
        """
        Extract value from model using dot-notation path.

        Supports:
        - Simple: "field_name"
        - Nested: "metadata.subzone_id"
        - Dict access: "sensor_metadata.custom_field"

        Args:
            model: Model instance
            path: Dot-separated field path

        Returns:
            Extracted value or None
        """
        parts = path.split(".")
        value = model

        for part in parts:
            if value is None:
                return None

            # Try attribute access first
            if hasattr(value, part):
                value = getattr(value, part)
            # Then try dict access
            elif isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        return value

    def _convert_type(self, value: Any, field_type: str) -> Any:
        """
        Convert value to specified type.

        Args:
            value: Value to convert
            field_type: Target type (string, int, float, bool, json)

        Returns:
            Converted value
        """
        if value is None:
            # Return type-appropriate None value
            type_defaults = {
                "string": "",
                "int": 0,
                "float": 0.0,
                "bool": False,
                "json": {},
            }
            return type_defaults.get(field_type, None)

        try:
            if field_type == "string":
                return str(value)
            elif field_type == "int":
                return int(value) if value is not None else 0
            elif field_type == "float":
                return float(value) if value is not None else 0.0
            elif field_type == "bool":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)
            elif field_type == "json":
                return value if isinstance(value, (dict, list)) else {}
            else:
                return value
        except (ValueError, TypeError) as e:
            logger.warning(f"Type conversion failed for {value} to {field_type}: {e}")
            return value

    def validate_mappings(self, mappings: List[Dict[str, Any]]) -> List[str]:
        """
        Validate mapping definitions.

        Args:
            mappings: List of mapping definitions

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        targets_seen = set()

        for i, mapping in enumerate(mappings):
            # Check required fields
            if not mapping.get("source"):
                errors.append(f"Mapping {i}: missing 'source' field")
            if not mapping.get("target"):
                errors.append(f"Mapping {i}: missing 'target' field")

            # Check for duplicate targets
            target = mapping.get("target", "")
            if target in targets_seen:
                errors.append(f"Mapping {i}: duplicate target '{target}'")
            targets_seen.add(target)

            # Validate field_type
            field_type = mapping.get("field_type", "string")
            valid_types = ["string", "int", "float", "bool", "json"]
            if field_type not in valid_types:
                errors.append(
                    f"Mapping {i}: invalid field_type '{field_type}', "
                    f"must be one of {valid_types}"
                )

            # Validate transform
            transform = mapping.get("transform")
            if transform and transform not in self.TRANSFORMS:
                errors.append(
                    f"Mapping {i}: unknown transform '{transform}', "
                    f"must be one of {list(self.TRANSFORMS.keys())}"
                )

        return errors

    def get_mapping_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for mapping validation.

        Returns:
            JSON schema dict for frontend validation
        """
        return {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "target"],
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source field path (dot notation for nested)",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target field name in ESP32 payload",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": ["string", "int", "float", "bool", "json"],
                        "default": "string",
                    },
                    "default": {
                        "description": "Default value if source is None",
                    },
                    "required": {
                        "type": "boolean",
                        "default": False,
                    },
                    "transform": {
                        "type": "string",
                        "enum": list(self.TRANSFORMS.keys()),
                    },
                },
            },
        }


# =============================================================================
# Global Instance
# =============================================================================

# Default engine instance (can be replaced with configured version)
_default_engine: Optional[ConfigMappingEngine] = None


def get_mapping_engine() -> ConfigMappingEngine:
    """Get or create the default mapping engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = ConfigMappingEngine()
    return _default_engine


def set_mapping_engine(engine: ConfigMappingEngine) -> None:
    """Set a custom mapping engine (for testing or runtime config)."""
    global _default_engine
    _default_engine = engine
