"""
Config Payload Builder Service

Builds ESP32-compatible configuration payloads from database models.

Features:
- Configurable field name mapping via ConfigMappingEngine
- Metadata extraction (subzone_id from sensor_metadata/actuator_metadata)
- Default value handling
- Zone information extraction for logging
- Runtime-configurable mapping overrides via SystemConfig
- Offline rules extraction for local hysteresis control during network loss

Converts Server DB models to ESP32 payload format using flexible mappings
that can be customized without code changes.

Phase: Runtime Config Flow Implementation
Priority: CRITICAL
Status: IMPLEMENTED
"""

import base64
import json
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config_mapping import ConfigMappingEngine, get_mapping_engine
from ..core.logging_config import get_logger
from ..db.models.actuator import ActuatorConfig
from ..db.models.logic import LogicHysteresisState
from ..db.models.sensor import SensorConfig
from ..db.repositories import ESPRepository, SensorRepository, ActuatorRepository, LogicRepository
from ..sensors.sensor_type_registry import normalize_sensor_type

logger = get_logger(__name__)

# AUT-134 PKG-01: Pre-flight Config-Budget für serverseitigen Auto-Push.
#
# El Trabajante: ``CONFIG_PAYLOAD_MAX_LEN`` (config_update_queue.h) liegt bei
# 4352 Bytes inkl. MQTT-/Header-Overhead. Für reines JSON ist das effektive
# Budget ~4096 Bytes — wir nutzen diese konservative Schwelle als Pre-flight
# Gate VOR dem Auto-Push, damit der Server gar nicht erst Frames produziert,
# die der ESP32-Ingress beim Empfang verwirft. Die finale Wire-Schwelle in
# ``ESPService.send_config`` (4352) bleibt als Defense-in-Depth bestehen.
CONFIG_AUTOPUSH_BUDGET_BYTES = 4096

# AUT-1029 / AUT-1027 Grenzen-Inventar: Firmware-Ingress CONFIG_PAYLOAD_MAX_LEN ist
# für ESP32_WROOM, ESP32_S3_DEVKITC1 und XIAO_ESP32_C3 identisch 4352 B
# (config_update_queue.h:31, kein Board-#ifdef). Server-Pre-flight bleibt konservativ
# darunter (~4096 B reines JSON unterhalb 4352 inkl. MQTT-/Header-Overhead).
_AUTOPUSH_BUDGET_BY_HARDWARE: Dict[str, int] = {
    "ESP32_WROOM": CONFIG_AUTOPUSH_BUDGET_BYTES,
    "ESP32_S3_DEVKITC1": CONFIG_AUTOPUSH_BUDGET_BYTES,
    "XIAO_ESP32_C3": CONFIG_AUTOPUSH_BUDGET_BYTES,
}


def resolve_autopush_budget_bytes(hardware_type: Optional[str]) -> int:
    """Return board-aware Auto-Push preflight budget (AUT-1029 / TM E1).

    Values are keyed by ``esp_devices.hardware_type`` (AUT-1027: identisches
    Firmware-Ingress 4352 B auf allen Boards → einheitlich 4096 B Pre-flight).
    """
    if hardware_type:
        return _AUTOPUSH_BUDGET_BY_HARDWARE.get(hardware_type, CONFIG_AUTOPUSH_BUDGET_BYTES)
    return CONFIG_AUTOPUSH_BUDGET_BYTES


# AUT-1143: Board-differentiated offline_rules capacity.
#
# S3 boards have substantially more DRAM headroom (~161 KB free) vs. WROOM
# (~232 B — AUT-1139 S0/D6), so S3 can safely hold 16 offline rules while WROOM
# and XIAO stay at the conservative 8. ``MOCK_ESP32`` devices have no real DRAM
# constraints and always receive the S3-equivalent capacity (16).
_MAX_OFFLINE_RULES_BY_HARDWARE: Dict[str, int] = {
    "ESP32_WROOM": 8,
    "ESP32_S3_DEVKITC1": 16,
    "XIAO_ESP32_C3": 8,
}


def resolve_max_offline_rules(hardware_type: Optional[str]) -> int:
    """Return the board-specific offline_rules capacity (AUT-1143).

    ``MOCK_ESP32`` is treated as always capable of 16 rules (no real DRAM
    limit). Real boards are keyed by ``esp_devices.hardware_type``; unknown or
    non-string values fall back to ``ConfigPayloadBuilder.MAX_OFFLINE_RULES``
    (8 — the conservative class-level constant kept for backwards compatibility).
    Pattern mirrors ``resolve_offline_rules_encoding`` (MOCK_ESP32 explicit
    check before dict lookup, defensive ``isinstance`` guard).
    """
    if isinstance(hardware_type, str) and hardware_type == "MOCK_ESP32":
        return 16
    if isinstance(hardware_type, str):
        return _MAX_OFFLINE_RULES_BY_HARDWARE.get(
            hardware_type, ConfigPayloadBuilder.MAX_OFFLINE_RULES
        )
    return ConfigPayloadBuilder.MAX_OFFLINE_RULES


# AUT-1141 L1: packed-struct wire encoding for the offline_rules scope.
#
# Byte-exact mirror of the firmware OfflineRule struct (56 B, v5,
# El Trabajante/src/models/offline_rule.h:22-49) — the same layout the
# firmware already persists in the NVS ``ofr_blob`` (offline_mode_manager.cpp
# saveOfflineRulesToNVS/loadOfflineRulesFromNVS ver>=5). Field order/padding
# verified against the struct declaration (S0 AUT-1140):
#   0 enabled(B) 1 actuator_gpio(B) 2 sensor_gpio(B) 3-23 sensor_value_type(21s)
#   24-39 activate_below/deactivate_above/activate_above/deactivate_below (ffff)
#   40-48 is_active/server_override/time_filter_enabled/start_hour/start_minute/
#         end_hour/end_minute/days_of_week_mask/timezone_mode (BBBBBBBBB)
#   49 padding(x) 50-51 max_on_seconds(H) 52-53 cooldown_seconds(H) 54-55 padding(xx)
OFFLINE_RULE_PACK_FORMAT_V5 = "<BBB21sffffBBBBBBBBBxHHxx"
_OFFLINE_RULE_SVT_MAX_LEN = 20  # NUL-terminated within the 21-byte field

# Minimum firmware_version that can decode "packed" (AUT-1141). Devices below
# this (or with an unparsable version) get the JSON-array fallback.
_PACKED_CAPABLE_MIN_VERSION: Tuple[int, int, int] = (4, 1, 0)


def _crc8_smbus(data: bytes) -> int:
    """CRC-8/SMBUS (poly 0x07, init 0, no reflect/xor-out) — mirrors the
    firmware's table-free implementation (offline_mode_manager.cpp:67-77)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _timezone_mode_from_name(timezone_name: Optional[str]) -> int:
    """Python mirror of parseTimezoneMode() (offline_mode_manager.cpp:138-147)."""
    if not timezone_name or timezone_name == "UTC":
        return 0
    if timezone_name in ("Europe/Berlin", "CET", "CEST"):
        return 1
    return 0


def _parse_firmware_version_tuple(
    firmware_version: Optional[str],
) -> Optional[Tuple[int, int, int]]:
    if not isinstance(firmware_version, str):
        return None
    parts = firmware_version.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def resolve_offline_rules_encoding(
    hardware_type: Optional[str], firmware_version: Optional[str]
) -> str:
    """Return the offline_rules wire encoding for a device: "packed" or "json".

    Per-device dispatch (AUT-1141 DP-Pflicht) — NOT a global switch — so a
    later additive encoding (e.g. CBOR for flash-rich S3 boards) only needs a
    new branch here, never a change to the decode side. ``MOCK_ESP32`` devices
    are always packed-capable (dev-local, no real firmware to be incompatible
    with). Real boards require firmware_version >= _PACKED_CAPABLE_MIN_VERSION
    so the server never sends a shape the deployed firmware cannot parse
    (safety net for the window between server merge and firmware reflash).
    """
    if isinstance(hardware_type, str) and hardware_type == "MOCK_ESP32":
        return "packed"
    version_tuple = _parse_firmware_version_tuple(firmware_version)
    if version_tuple is not None and version_tuple >= _PACKED_CAPABLE_MIN_VERSION:
        return "packed"
    return "json"


def _pack_offline_rule(rule: Dict[str, Any]) -> bytes:
    """Serialize one offline_rules dict into the 56 B OfflineRule wire layout.

    Replicates the defaults ``OfflineModeManager::parseOfflineRules()``
    (offline_mode_manager.cpp:948-1078) applies on the JSON-array path so the
    packed and JSON encodings drive the firmware to identical struct state.
    """
    sensor_value_type = str(rule.get("sensor_value_type", ""))
    enabled = 1
    if len(sensor_value_type) > _OFFLINE_RULE_SVT_MAX_LEN:
        # Mirrors parseOfflineRules' defensive fallback: an oversized field
        # disables the rule instead of failing the whole config push.
        logger.warning(
            "[CONFIG] packed offline_rule: sensor_value_type truncated: '%s'",
            sensor_value_type,
        )
        enabled = 0
        sensor_value_type = sensor_value_type[:_OFFLINE_RULE_SVT_MAX_LEN]

    time_filter = rule.get("time_filter") or {}

    return struct.pack(
        OFFLINE_RULE_PACK_FORMAT_V5,
        enabled,
        int(rule.get("actuator_gpio", 255) or 255) & 0xFF,
        int(rule.get("sensor_gpio", 255) or 255) & 0xFF,
        sensor_value_type.encode("ascii", errors="replace"),
        float(rule.get("activate_below", 0.0) or 0.0),
        float(rule.get("deactivate_above", 0.0) or 0.0),
        float(rule.get("activate_above", 0.0) or 0.0),
        float(rule.get("deactivate_below", 0.0) or 0.0),
        1 if rule.get("current_state_active") else 0,
        0,  # server_override — parseOfflineRules always forces false on config push
        1 if time_filter.get("enabled") else 0,
        int(time_filter.get("start_hour", 0) or 0) & 0xFF,
        int(time_filter.get("start_minute", 0) or 0) & 0xFF,
        int(time_filter.get("end_hour", 0) or 0) & 0xFF,
        int(time_filter.get("end_minute", 0) or 0) & 0xFF,
        int(time_filter.get("days_of_week_mask", 0x7F) or 0x7F) & 0xFF,
        _timezone_mode_from_name(time_filter.get("timezone")),
        min(int(rule.get("max_on_seconds", 0) or 0), 65535),
        min(int(rule.get("cooldown_seconds", 0) or 0), 65535),
    )


def _encode_offline_rules_packed(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pack ``offline_rules`` into the wire-compatible OfflineRule blob (AUT-1141 L1).

    Produces the exact byte layout the firmware already persists in the NVS
    ``ofr_blob`` (N x 56 B + 1 CRC8 trailer byte) so the firmware can reuse its
    existing blob-decode path — no second/parallel parser.
    """
    body = b"".join(_pack_offline_rule(rule) for rule in rules)
    blob = body + bytes([_crc8_smbus(body)])
    return {
        "encoding": "packed",
        "count": len(rules),
        "blob": base64.b64encode(blob).decode("ascii"),
    }


def estimate_config_wire_size(config: Dict[str, Any]) -> int:
    """
    Schätzt die finale JSON-Wire-Größe der Config wie ``ESPService.send_config``.

    Spiegelt die Felder, die der Publisher zusätzlich injiziert
    (``correlation_id``/``request_id``/``intent_id``/``generation``/
    ``config_fingerprint``/``reason_code``/``timestamp``), um eine realistische
    Vorab-Schätzung zu erhalten. Genaue Werte sind nicht kritisch — wir nutzen
    Platzhalter mit identischer Länge.

    Args:
        config: Config-Frame, der an ``send_config`` übergeben würde.

    Returns:
        Anzahl Bytes der serialisierten Wire-Form (UTF-8).
    """
    sentinel_correlation = "00000000-0000-0000-0000-000000000000"
    wire_for_size = {
        **config,
        "correlation_id": sentinel_correlation,
        "request_id": sentinel_correlation,
        "intent_id": sentinel_correlation,
        "generation": int(time.time() * 1000),
        "config_fingerprint": "0" * 64,
        "reason_code": str(config.get("reason_code", "auto_push")),
        "timestamp": int(time.time()),
    }
    try:
        return len(json.dumps(wire_for_size, default=str).encode("utf-8"))
    except (TypeError, ValueError) as exc:  # noqa: BLE001 — defensive
        logger.error("Config wire size estimation failed: %s", exc)
        # Konservative Annahme: bei Serialisierungsfehlern als oversize behandeln,
        # damit der Caller den sauberen Abbruchpfad wählt.
        return CONFIG_AUTOPUSH_BUDGET_BYTES + 1


def _get_default_deadband(sensor_type: str) -> float:
    """Return a type-specific deadband for auto-converting a simple threshold to hysteresis.

    Called only for digital sensors that deliver calibrated physical values directly
    on the ESP32 (temperature, humidity, pressure, CO2, light, flow). Analog sensors
    that require server-side calibration (ph, ec, moisture, soil_moisture) are
    filtered out by the P4-GUARD before this function is ever reached.
    """
    DEADBAND_MAP = {
        "sht31_temp": 2.0,  # °C — typical HVAC hysteresis band
        "ds18b20": 2.0,  # °C
        "bmp280_temp": 2.0,  # °C
        "bme280_temp": 2.0,  # °C
        "sht31_humidity": 5.0,  # %RH — higher variance for humidity
        "bme280_humidity": 5.0,
        "bmp280_pressure": 5.0,  # hPa
        "bme280_pressure": 5.0,
        "co2": 50.0,  # ppm — large natural fluctuations
        "light": 100.0,  # lux
        "flow": 0.5,  # l/min — conservative
        "liquid_level": 0.5,  # binary 0/1 — default 2.0 would never trigger
    }
    for prefix, deadband in DEADBAND_MAP.items():
        if sensor_type.startswith(prefix):
            return deadband
    return 2.0  # Safe fallback for unmapped types


def _days_of_week_db_to_tm_mask(raw_days: Any) -> int:
    """
    Convert DB weekday list (0=Mon..6=Sun) to tm_wday bitmask (bit0=Sun..bit6=Sat).

    Defaults:
    - Field missing (None): all days (0x7F)
    - Empty list: no day active (0x00)
    - Invalid/non-list or all invalid values: all days (0x7F)
    """
    if raw_days is None:
        return 0x7F
    if isinstance(raw_days, list) and len(raw_days) == 0:
        return 0x00
    if not isinstance(raw_days, list):
        return 0x7F

    db_to_tm_wday = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}
    days_mask = 0
    for day in raw_days:
        try:
            tm_wday = db_to_tm_wday.get(int(day))
        except (TypeError, ValueError):
            tm_wday = None
        if tm_wday is not None:
            days_mask |= 1 << tm_wday

    if days_mask == 0:
        logger.warning(
            "[CONFIG] Invalid days_of_week values (%s), fallback to all days (0x7F)",
            raw_days,
        )
        return 0x7F
    return days_mask


class ConfigConflictError(Exception):
    """
    Raised when config contains GPIO conflicts.

    This error indicates that multiple sensors/actuators are configured
    for the same GPIO pin, which would cause hardware conflicts on the ESP32.

    Phase: 2 (GPIO Validation)
    """

    pass


class ConfigPayloadBuilder:
    """
    Baut Config-Payloads für ESP32-Geräte.

    VERWENDUNG:
        Wird automatisch von Sensor/Actuator APIs aufgerufen nach CRUD-Operationen.

    ARCHITEKTUR:
        1. Sensor/Actuator CRUD API führt DB-Operation durch
        2. build_combined_config() lädt alle Sensoren/Aktoren eines ESP aus DB
        3. Für jeden Sensor/Actuator wird apply_sensor/actuator_mapping() aufgerufen
        4. Mappings kommen aus core/config_mapping.py (DEFAULT_SENSOR_MAPPINGS)
        5. Ergebnis wird an esp_service.send_config() übergeben
        6. MQTT Publisher sendet an: kaiser/{kaiser_id}/esp/{esp_id}/config

    FELD-KONFIGURATION:
        Welche Felder zum ESP32 gesendet werden, wird in
        core/config_mapping.py definiert (DEFAULT_SENSOR_MAPPINGS).

    HINWEIS:
        Ein manueller Config-Push-Endpoint existiert NICHT.
        Configs werden automatisch nach CRUD-Operationen gesendet.

    Converts database models to ESP32 payload format with configurable field mapping
    and zone information extraction.

    Field mappings can be customized via:
    1. Constructor parameter (custom_mapping_engine)
    2. SystemConfig entries (config_mapping.sensor, config_mapping.actuator)
    3. Default mappings in config_mapping.py

    Usage:
        # Default mappings
        builder = ConfigPayloadBuilder()
        config = await builder.build_combined_config(esp_id, db)

        # Custom mappings
        engine = ConfigMappingEngine(sensor_mappings=[...])
        builder = ConfigPayloadBuilder(mapping_engine=engine)
    """

    # Conservative fallback for the maximum number of offline rules per ESP32
    # when the board type is unknown (AUT-1143). Board-aware capacity is
    # determined at runtime by ``resolve_max_offline_rules()`` — S3=16,
    # WROOM=8, XIAO=8, MOCK=16. Do NOT remove this constant; it is used as the
    # default fallback value inside ``resolve_max_offline_rules``.
    MAX_OFFLINE_RULES = 8

    # Sensor types that require calibration parameters to convert ADC raw values
    # to physical units. The ESP32 firmware's applyLocalConversion() has no
    # calibration data for these sensors and returns only the ADC raw value
    # (0-4095). Offline rule thresholds expressed in physical units (e.g. pH 7.5,
    # EC 1.8 mS/cm) would be compared against raw ADC counts — meaningless and
    # potentially dangerous (e.g. ADC 2048 > pH 7.5 → dosing pump fires).
    CALIBRATION_REQUIRED_SENSOR_TYPES = {"ph", "ec", "moisture", "soil_moisture"}
    TIME_WINDOW_ONLY_SENSOR_GPIO = 255
    TIME_WINDOW_ONLY_SENSOR_TYPE_ON = "__twindow_on"
    TIME_WINDOW_ONLY_SENSOR_TYPE_OFF = "__twindow_off"

    # =========================================================================
    # AUT-132: Offline-rules diagnostics — Reason-Code SSOT
    # =========================================================================
    # Stable strings shared with frontend / firmware diagnostics. Do NOT change
    # these literals without coordinating with consumers. The ESP32 firmware
    # treats these as opaque, but human operators read them in logs and UI.
    REASON_CALIBRATION_REQUIRED = "CALIBRATION_REQUIRED"
    REASON_GPIO_NOT_IN_FRAME = "GPIO_NOT_IN_FRAME"
    REASON_MAX_RULE_LIMIT = "MAX_RULE_LIMIT"
    REASON_UNSUPPORTED_CONDITION = "UNSUPPORTED_CONDITION"
    REASON_CONSISTENCY_CHECK_FAILED = "CONSISTENCY_CHECK_FAILED"

    def __init__(
        self,
        sensor_repo: Optional[SensorRepository] = None,
        actuator_repo: Optional[ActuatorRepository] = None,
        esp_repo: Optional[ESPRepository] = None,
        logic_repo: Optional[LogicRepository] = None,
        mapping_engine: Optional[ConfigMappingEngine] = None,
    ):
        """
        Initialize ConfigPayloadBuilder.

        Args:
            sensor_repo: Sensor repository (optional, created if not provided)
            actuator_repo: Actuator repository (optional, created if not provided)
            esp_repo: ESP repository (optional, created if not provided)
            logic_repo: Logic repository (optional, created if not provided)
            mapping_engine: Custom field mapping engine (optional, uses global default)
        """
        self.sensor_repo = sensor_repo
        self.actuator_repo = actuator_repo
        self.esp_repo = esp_repo
        self.logic_repo = logic_repo
        self.mapping_engine = mapping_engine or get_mapping_engine()

    @classmethod
    def _is_time_window_only_sensor_type(cls, sensor_value_type: str) -> bool:
        return sensor_value_type in (
            cls.TIME_WINDOW_ONLY_SENSOR_TYPE_ON,
            cls.TIME_WINDOW_ONLY_SENSOR_TYPE_OFF,
        )

    # UART pin pairs used as fallback when sensor_metadata lacks explicit uart pins.
    # Convention: sensor.gpio = uart_rx_pin; value = uart_tx_pin.
    # ESP32-S3 DevKitC-1 UART1:  GPIO 18 (RX) ↔ GPIO 17 (TX)
    # Standard ESP32 WROOM UART2: GPIO 16 (RX) → GPIO 17 (TX)
    _UART1_COMPLEMENT: Dict[int, int] = {16: 17, 17: 18, 18: 17}

    def build_sensor_payload(self, sensor: SensorConfig) -> Dict[str, Any]:
        """
        Convert SensorConfig model to ESP32 payload format.

        Uses configurable field mappings from ConfigMappingEngine.
        Default mappings:
        - sensor_name → sensor_name (direct)
        - sensor_type → sensor_type (direct)
        - gpio → gpio (direct)
        - enabled → active (boolean mapping)
        - sample_interval_ms → sample_interval_ms (direct)
        - sensor_metadata.subzone_id → subzone_id (extracted from metadata)
        - raw_mode → always true (ESP32 expects this field)

        Args:
            sensor: SensorConfig model instance

        Returns:
            Dictionary with ESP32-compatible sensor payload
        """
        payload = self.mapping_engine.apply_sensor_mapping(sensor)

        # UART pin fallback (AUT-576): sensor_metadata may be empty for sensors
        # created before uart_rx_pin/uart_tx_pin were stored on the write path.
        # Derive pins from sensor.gpio so both old and new records work without
        # requiring a DB migration or UI changes.
        # Convention: sensor.gpio = uart_rx_pin (where sensor TX connects to ESP).
        is_uart = (
            getattr(sensor, "interface_type", None) == "UART"
            or (getattr(sensor, "sensor_type", "") or "").lower() == "co2"
        )
        if is_uart and payload.get("uart_rx_pin", 255) in (255, 0):
            rx = sensor.gpio
            tx = self._UART1_COMPLEMENT.get(rx, rx)
            payload["uart_rx_pin"] = rx
            payload["uart_tx_pin"] = tx

        return payload

    def build_actuator_payload(self, actuator: ActuatorConfig) -> Dict[str, Any]:
        """
        Convert ActuatorConfig model to ESP32 payload format.

        Uses configurable field mappings from ConfigMappingEngine.
        Default mappings:
        - actuator_name → actuator_name (direct)
        - actuator_type → actuator_type (direct)
        - gpio → gpio (direct)
        - enabled → active (boolean mapping)
        - actuator_metadata.subzone_id → subzone_id (extracted from metadata)
        - actuator_metadata.aux_gpio → aux_gpio (default: 255)
        - actuator_metadata.critical → critical (default: false)
        - actuator_metadata.inverted_logic → inverted_logic (default: false)
        - actuator_metadata.default_state → default_state (default: false)
        - actuator_metadata.default_pwm → default_pwm (default: 0)

        AUT-120 / AUT-482 — fail_safe_on_disconnect:
            Included in the payload when set on the DB row (``is not None``).
            Product default on create: ``True`` (manual actuator without offline
            rule must turn OFF on MQTT disconnect). ``False`` = explicit hold.
            ``None`` = omit field (legacy rows only; ESP NVS default applies).

        Args:
            actuator: ActuatorConfig model instance

        Returns:
            Dictionary with ESP32-compatible actuator payload
        """
        payload = self.mapping_engine.apply_actuator_mapping(actuator)

        # Preserve ESP-side hardware driver tokens when available.
        # API normalization stores actuator_type as server mode (e.g. "digital"),
        # while ESP firmware expects hardware tokens such as "relay"/"pump"/"valve".
        #
        # AUT-997/AUT-998: compare against the ORIGINAL DB value actuator.actuator_type
        # (nullable=False, always present) — NOT payload["actuator_type"]. By this point
        # apply_actuator_mapping() (above) has already run the actuator_type_to_esp32
        # transform, which maps "digital" → "relay". Comparing the already-transformed
        # payload value made this restore branch dead code, so every binary actuator was
        # pushed as "relay" regardless of its real hardware_type (e.g. a pump).
        hardware_type = str(getattr(actuator, "hardware_type", "") or "").strip().lower()
        original_type = str(getattr(actuator, "actuator_type", "") or "").strip().lower()
        if original_type == "digital" and hardware_type in {"relay", "pump", "valve", "pwm"}:
            payload["actuator_type"] = hardware_type

        # AUT-120: Add fail_safe_on_disconnect only when the server has an
        # explicit opinion. None → field omitted → ESP32 default applies.
        fail_safe = getattr(actuator, "fail_safe_on_disconnect", None)
        if fail_safe is not None:
            payload["fail_safe_on_disconnect"] = bool(fail_safe)

        return payload

    async def build_combined_config(
        self,
        esp_device_id: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Build combined sensor/actuator configuration payload for ESP32.

        Loads all active sensors and actuators for the ESP device and builds
        a combined payload in ESP32-compatible format.

        Args:
            esp_device_id: ESP device ID (e.g., "ESP_12AB34CD")
            db: Database session

        Returns:
            Dictionary with "sensors" and "actuators" arrays in ESP32 format

        Raises:
            ValueError: If ESP device not found
        """
        # Initialize repositories if not provided
        if not self.esp_repo:
            self.esp_repo = ESPRepository(db)
        if not self.sensor_repo:
            self.sensor_repo = SensorRepository(db)
        if not self.actuator_repo:
            self.actuator_repo = ActuatorRepository(db)
        if not self.logic_repo:
            self.logic_repo = LogicRepository(db)

        # Get ESP device
        esp_device = await self.esp_repo.get_by_device_id(esp_device_id)
        if not esp_device:
            raise ValueError(f"ESP device '{esp_device_id}' not found")

        # Load all sensors and actuators for this ESP
        sensors = await self.sensor_repo.get_by_esp(esp_device.id)
        actuators = await self.actuator_repo.get_by_esp(esp_device.id)

        # Filter only enabled sensors/actuators (ESP32 only processes active ones)
        active_sensors = [s for s in sensors if s.enabled]
        active_actuators = [a for a in actuators if a.enabled]

        # Filter out VIRTUAL sensors — computed server-side (e.g. VPD), never sent to ESP32
        active_sensors = [
            s
            for s in active_sensors
            if not (getattr(s, "interface_type", None) or "").upper() == "VIRTUAL"
        ]

        # =====================================================================
        # GPIO-Konflikt-Check (Phase 2)
        # Prüft ob mehrere Sensoren/Aktoren auf dem gleichen GPIO konfiguriert sind.
        # I2C and OneWire sensors are EXCLUDED — they share a bus and GPIO is valid
        # to be reused (e.g., two SHT31 configs on GPIO 0 for I2C SDA/SCL).
        # =====================================================================
        used_gpios: dict[int, str] = {}

        for sensor in active_sensors:
            # I2C/OneWire sensors share bus pins — no GPIO conflict possible
            iface = getattr(sensor, "interface_type", None)
            if iface and iface.upper() in ("I2C", "ONEWIRE"):
                continue
            # ADS1115 sensors use virtual GPIO 0 over I2C — no real ESP32 pin conflict
            adc_src = getattr(sensor, "adc_source", None)
            if adc_src and adc_src.lower() == "ads1115":
                continue
            if sensor.gpio in used_gpios:
                sensor_name = sensor.sensor_name or sensor.sensor_type
                raise ConfigConflictError(
                    f"GPIO {sensor.gpio} Konflikt: Sensor '{sensor_name}' "
                    f"kollidiert mit {used_gpios[sensor.gpio]}"
                )
            sensor_name = sensor.sensor_name or sensor.sensor_type
            used_gpios[sensor.gpio] = f"sensor:{sensor_name}"

        for actuator in active_actuators:
            if actuator.gpio in used_gpios:
                actuator_name = actuator.actuator_name or actuator.actuator_type
                raise ConfigConflictError(
                    f"GPIO {actuator.gpio} Konflikt: Actuator '{actuator_name}' "
                    f"kollidiert mit {used_gpios[actuator.gpio]}"
                )
            actuator_name = actuator.actuator_name or actuator.actuator_type
            used_gpios[actuator.gpio] = f"actuator:{actuator_name}"

        logger.debug(f"Config GPIO validation passed: {len(used_gpios)} unique GPIOs")
        # =====================================================================

        # Build payload arrays
        sensor_payloads = [self.build_sensor_payload(s) for s in active_sensors]
        actuator_payloads = [self.build_actuator_payload(a) for a in active_actuators]

        # AUT-555: QoS-adaptive publish.
        #
        # Problem context:
        #   AUT-54 switched all sensor publishes to QoS-0 because simultaneous QoS-1
        #   sensor + actuator traffic filled the IDF OUTBOX under WiFi jitter, causing
        #   1500 ms write-timeouts and MQTT disconnects (root-cause on ESP_EA5484).
        #   But sensors referenced in a cross_esp_logic rule MUST have their reading
        #   delivered — a lost QoS-0 packet means the rule engine sees a stale value
        #   and may miss or delay a trigger (e.g. humidity threshold not crossed).
        #
        # Solution:
        #   Let the server decide per-sensor. It knows which GPIOs are rule trigger-
        #   sensors (via cross_esp_logic.trigger_conditions). All others are pure
        #   monitoring sensors whose loss is acceptable (next reading in ≤30 s).
        #
        # Data flow (end-to-end):
        #   1. LogicRepository.get_rule_gpio_set_for_esp(esp_device_id)
        #      → queries all enabled cross_esp_logic rules, extracts GPIOs that appear
        #        as trigger-sensor GPIOs for this device.
        #   2. Here: each sensor payload dict gets "publish_qos": 1 or 0 injected.
        #   3. ESP32 main.cpp parseAndConfigureSensorWithTracking()
        #      → reads "publish_qos" from the JSON payload into SensorConfig.publish_qos.
        #   4. SensorManager::publishSensorReading() (sensor_manager.cpp)
        #      → calls findSensorConfig(gpio, sensor_type) and uses publish_qos as the
        #        QoS argument in mqtt_client_->publish(topic, payload, qos).
        #
        # Note: logic_repo is guaranteed initialised above (line ~357) before this point.
        rule_gpios: set[int] = await self.logic_repo.get_rule_gpio_set_for_esp(esp_device_id)
        for sp in sensor_payloads:
            # QoS-1 only for sensors that are trigger-inputs for at least one active rule.
            # All others stay QoS-0 to keep the OUTBOX lean under WiFi jitter.
            sp["publish_qos"] = 1 if sp.get("gpio") in rule_gpios else 0

        # AUT-132: Collect per-rule skip diagnostics so the ESP32 (and operators
        # reading the config push) see *why* offline rules were stripped.
        stripped_rules: List[Dict[str, Any]] = []
        candidate_counter: Dict[str, int] = {"total_candidate_rules": 0}

        # Build offline rules for local hysteresis control during network loss
        offline_rules = await self._build_offline_rules(
            db,
            esp_device,
            skip_collector=stripped_rules,
            candidate_counter=candidate_counter,
        )

        # AUT-59: Validate offline_rules consistency against config frame.
        # Rules referencing actuator/sensor GPIOs not present in this config
        # frame would cause a pending-exit blockade on the ESP32 firmware.
        offline_rules = self._validate_offline_rules_consistency(
            offline_rules,
            sensor_payloads,
            actuator_payloads,
            esp_device_id,
            skip_collector=stripped_rules,
        )

        # AUT-132: assemble the diagnostics block in a backward-compatible way.
        # The legacy ``offline_rules`` field is unchanged; ``offline_rules_diagnostics``
        # is additive metadata for operators and firmware diagnostics.
        accepted_count = len(offline_rules)
        stripped_count = len(stripped_rules)
        total_candidate_rules = candidate_counter.get("total_candidate_rules", 0)
        offline_rules_diagnostics: Dict[str, Any] = {
            "total_candidate_rules": total_candidate_rules,
            "accepted_count": accepted_count,
            "stripped_count": stripped_count,
            "stripped_rules": stripped_rules,
        }

        # AUT-727: propagate offline-rule max_on_seconds into actuator max_runtime_ms.
        # When safety_constraints.max_runtime is None on the ActuatorConfig DB row (i.e.
        # max_on_seconds was configured only on the Logic Rule), config_mapping defaults
        # max_runtime_ms to 3600000 (1h). Pull the validated offline_rules as the source
        # of truth for a tighter per-actuator cap so the ESP NVS can persist it and the
        # universal RuntimeProtection watchdog survives reboots and connection changes.
        max_on_by_gpio: Dict[int, int] = {}
        for rule_dict in offline_rules:
            gpio = rule_dict.get("actuator_gpio")
            max_on = rule_dict.get("max_on_seconds", 0)
            if gpio is not None and isinstance(max_on, int) and max_on > 0:
                if gpio not in max_on_by_gpio or max_on < max_on_by_gpio[gpio]:
                    max_on_by_gpio[gpio] = max_on
        for ap in actuator_payloads:
            rule_cap_ms = max_on_by_gpio.get(ap.get("gpio", -1), 0) * 1000
            if rule_cap_ms > 0:
                current_ms = ap.get("max_runtime_ms") or 3600000
                if rule_cap_ms < current_ms:
                    ap["max_runtime_ms"] = rule_cap_ms

        # Build combined config
        config = {
            "sensors": sensor_payloads,
            "actuators": actuator_payloads,
            "offline_rules": offline_rules,
            "offline_rules_diagnostics": offline_rules_diagnostics,
        }

        # AUT-1141 L1: per-device encoding dispatch for the offline_rules scope.
        # Packed-capable devices get the compact 56 B/rule blob (< the JSON array's
        # ~214 B/rule); everything else keeps the existing JSON array untouched —
        # required during the merge-to-reflash window so old firmware never
        # receives a shape it cannot parse.
        offline_rules_encoding = resolve_offline_rules_encoding(
            getattr(esp_device, "hardware_type", None),
            getattr(esp_device, "firmware_version", None),
        )
        if offline_rules_encoding == "packed":
            config["offline_rules"] = _encode_offline_rules_packed(offline_rules)

        # Log zone information for better traceability
        zone_info = f"zone={esp_device.zone_id or 'none'}"
        if esp_device.zone_name:
            zone_info += f" ({esp_device.zone_name})"

        logger.info(
            f"Built config payload for {esp_device_id}: "
            f"{len(sensor_payloads)} sensors, {len(actuator_payloads)} actuators, "
            f"{len(offline_rules)} offline_rules "
            f"(candidates={total_candidate_rules}, stripped={stripped_count}), "
            f"{zone_info}"
        )

        return config

    async def _build_offline_rules(
        self,
        db: AsyncSession,
        esp_device: Any,
        skip_collector: Optional[List[Dict[str, Any]]] = None,
        candidate_counter: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build offline hysteresis rules for local ESP32 execution during network loss.

        Extracts enabled hysteresis rules where both the trigger sensor and the
        actuator action belong to the same ESP device. These rules are sent to the
        ESP32 so it can maintain basic hysteresis control without server connectivity.

        Only local rules are included — cross-ESP rules (sensor and actuator on
        different ESPs) cannot be executed locally and are excluded.

        ## Inclusion criteria (all must be met)
        A rule is included in offline_rules when:
        1. At least one actuator action targets this ESP (``action.esp_id == esp_id``).
        2. The rule has exactly one of: a hysteresis condition, a simple threshold
           condition (``sensor_threshold``/``sensor``), or a time-window-only condition
           (``time_window``/``time``) — all scoped to this ESP.
        3. For sensor-based conditions: ``sensor_gpio >= 0`` and a valid threshold pair
           (cooling: activate_above + deactivate_below; heating: activate_below +
           deactivate_above).
        4. Sensor type is NOT calibration-required (ph, ec, moisture, soil_moisture —
           these lack calibration data on the ESP32 so thresholds would fire against
           raw ADC counts, not physical units).
        5. ``sensor_value_type`` fits in 23 chars (ESP OfflineRule struct limit).
        6. For OR-compound rules: each branch is flattened into a separate single-condition
           offline rule (DNF, AUT-739). AND-compound rules are not supported and are
           excluded with REASON_UNSUPPORTED_CONDITION.

        ## Why offline_rules count may differ from UI logic-rule count

        The UI displays all *CrossESPLogic* rules regardless of locality. The
        ``offline_rules`` array in the config payload only carries rules that the
        ESP32 can execute autonomously. The delta is expected and breaks down as:

        - **Cross-ESP rules** — actuator or sensor belongs to a different ESP.
        - **Calibration-required sensors** — ph / ec / moisture / soil_moisture excluded.
        - **OR-compound rules** — cannot be represented as a single hysteresis struct.
        - **No convertible condition** — unsupported operator or missing threshold value.
        - **Time-window-only rules** — *are* included but use ``sensor_gpio=255`` and
          ``sensor_value_type=__twindow_on`` or ``__twindow_off`` as a firmware
          display-semantic marker; these entries do NOT correspond to a physical sensor
          and may not be visible as "sensor rules" in the UI logic rule list.
        - **AUT-59 consistency strip** — rules referencing GPIOs absent in the current
          config frame are removed by ``_validate_offline_rules_consistency``.
        - **MAX_OFFLINE_RULES cap** — board-budgeted limit (see ``resolve_max_offline_rules()``);
          excess entries are truncated.

        Per-rule skip details are logged at WARNING/INFO level inside
        ``_extract_offline_rule``. A structured audit summary is emitted at INFO level
        after the build loop (search for "[CONFIG] offline_rules audit").

        Args:
            db: Database session
            esp_device: ESPDevice model instance (must have device_id attribute)

        Returns:
            List of offline rule dicts with fields:
                - actuator_gpio: int
                - sensor_gpio: int  (255 for time-window-only rules)
                - sensor_value_type: str  (e.g. "sht31_humidity", "__twindow_on")
                - activate_below: float   (heating mode; 0.0 if cooling mode)
                - deactivate_above: float (heating mode; 0.0 if cooling mode)
                - activate_above: float   (cooling mode; 0.0 if heating mode)
                - deactivate_below: float (cooling mode; 0.0 if heating mode)
                - current_state_active: bool
                - time_filter: dict  (optional, present when a time_window condition exists)
            Board-budgeted number of entries (see ``resolve_max_offline_rules()``);
            excess entries are truncated with a warning.
        """
        if not self.logic_repo:
            self.logic_repo = LogicRepository(db)
        if not self.sensor_repo:
            self.sensor_repo = SensorRepository(db)

        esp_id = esp_device.device_id
        max_offline_rules = resolve_max_offline_rules(esp_device.hardware_type)

        try:
            enabled_rules = await self.logic_repo.get_enabled_rules()
        except Exception as exc:
            logger.error(
                "[CONFIG] Failed to load logic rules for offline_rules build (ESP %s): %s",
                esp_id,
                exc,
                exc_info=True,
            )
            return []

        # Preload all persisted hysteresis states in one query.
        # Key format matches HysteresisConditionEvaluator: "{rule_id}:{condition_index}"
        # This allows _extract_offline_rule to include current_state_active in the payload
        # without N+1 DB queries.
        hysteresis_states: Dict[str, bool] = {}
        try:
            result = await db.execute(select(LogicHysteresisState))
            for row in result.scalars().all():
                key = f"{row.rule_id}:{row.condition_index}"
                hysteresis_states[key] = row.is_active
            logger.debug(
                "[CONFIG] Preloaded %d hysteresis states for ESP %s", len(hysteresis_states), esp_id
            )
        except Exception as exc:
            logger.warning(
                "[CONFIG] Could not preload hysteresis states for ESP %s: %s", esp_id, exc
            )

        # Preload calibrated sensors for this ESP in one query.
        # Key format: "{gpio}:{sensor_type}" — avoids N+1 queries inside the synchronous
        # _extract_offline_rule / _flatten_or_conditions_to_rules helpers.
        # A sensor is considered calibrated when calibration_data is present and non-empty.
        calibrated_sensors: set = set()
        try:
            esp_sensors = await self.sensor_repo.get_by_esp(esp_device.id)
            for s in esp_sensors:
                if s.calibration_data:
                    calibrated_sensors.add(f"{s.gpio}:{normalize_sensor_type(s.sensor_type)}")
            logger.debug(
                "[CONFIG] Preloaded %d calibrated sensors for ESP %s",
                len(calibrated_sensors),
                esp_id,
            )
        except Exception as exc:
            logger.warning(
                "[CONFIG] Could not preload calibrated sensors for ESP %s: %s", esp_id, exc
            )

        offline_rules: List[Dict[str, Any]] = []
        pre_filtered_cross_esp = 0  # Rules silently skipped — no local actuator action

        if candidate_counter is not None:
            candidate_counter["total_candidate_rules"] = len(enabled_rules)

        def _has_local_actuator_action(rule_actions: list) -> bool:
            """Return True if at least one action targets this ESP."""
            return any(
                isinstance(a, dict)
                and a.get("type") in ("actuator_command", "actuator")
                and a.get("esp_id") == esp_id
                for a in rule_actions
            )

        for rule in enabled_rules:
            # Pre-filter: pure cross-ESP rules have no local actuator action.
            # They are silently skipped — no WARNING, no skip_collector entry.
            # (Rules with mixed local+cross-ESP actions still pass through.)
            actions = rule.actions if isinstance(rule.actions, list) else []
            if not _has_local_actuator_action(actions):
                pre_filtered_cross_esp += 1
                logger.debug(
                    "[CONFIG] Rule '%s' for ESP %s — no local actuator action, skip (cross-ESP only)",
                    getattr(rule, "rule_name", "<unknown>"),
                    esp_id,
                )
                continue

            try:
                rule_entries = self._extract_offline_rule(
                    rule,
                    esp_id,
                    hysteresis_states,
                    skip_collector=skip_collector,
                    calibrated_sensors=calibrated_sensors,
                )
                offline_rules.extend(rule_entries)
            except Exception as exc:
                logger.warning(
                    "[CONFIG] Skipping rule '%s' for offline_rules due to extraction error: %s",
                    getattr(rule, "rule_name", "<unknown>"),
                    exc,
                )
                if skip_collector is not None:
                    skip_collector.append(
                        {
                            "rule_id": str(getattr(rule, "id", "") or ""),
                            "rule_name": getattr(rule, "rule_name", "<unknown>") or "<unknown>",
                            "actuator_gpio": None,
                            "reason_code": self.REASON_UNSUPPORTED_CONDITION,
                            "reason_detail": f"extraction error: {exc}",
                        }
                    )
                continue

        rules_before_cap = len(offline_rules)
        if rules_before_cap > max_offline_rules:
            logger.warning(
                "[CONFIG] ESP %s: %d offline rules exceed limit of %d, truncating",
                esp_id,
                rules_before_cap,
                max_offline_rules,
            )
            if skip_collector is not None:
                # AUT-132: Record each truncated rule so the diagnostics payload
                # tells operators *why* a rule did not reach the ESP.
                for dropped in offline_rules[max_offline_rules:]:
                    skip_collector.append(
                        {
                            "rule_id": "",
                            "rule_name": "<truncated>",
                            "actuator_gpio": dropped.get("actuator_gpio"),
                            "reason_code": self.REASON_MAX_RULE_LIMIT,
                            "reason_detail": (
                                f"rule exceeded firmware limit of {max_offline_rules} "
                                f"offline rules (had {rules_before_cap})"
                            ),
                        }
                    )
            offline_rules = offline_rules[:max_offline_rules]

        twindow_count = sum(
            1
            for r in offline_rules
            if self._is_time_window_only_sensor_type(str(r.get("sensor_value_type", "")))
        )
        # skipped_count excludes pre_filtered_cross_esp (those never entered _extract_offline_rule)
        skipped_count = len(enabled_rules) - pre_filtered_cross_esp - rules_before_cap
        capped_count = rules_before_cap - len(offline_rules)

        logger.info(
            "[CONFIG] offline_rules audit ESP %s: "
            "enabled_rules_checked=%d | pre_filtered_cross_esp=%d | "
            "included=%d (sensor_hysteresis=%d, time_window_only=%d) | "
            "skipped=%d | capped=%d. "
            "Skip reasons per rule logged above as [CONFIG] Rule/Offline-rule skip. "
            "Typical causes: calibration_required (ph/ec/moisture), "
            "or_compound, no_convertible_condition, invalid_gpio. "
            "time_window_only rules use sensor_gpio=255 and sensor_value_type=__twindow_on/off — "
            "these count in offline_rules but are not listed as sensor-based logic rules in the UI.",
            esp_id,
            len(enabled_rules),
            pre_filtered_cross_esp,
            len(offline_rules),
            len(offline_rules) - twindow_count,
            twindow_count,
            skipped_count,
            capped_count,
        )

        return offline_rules

    def _validate_offline_rules_consistency(
        self,
        offline_rules: List[Dict[str, Any]],
        sensor_payloads: List[Dict[str, Any]],
        actuator_payloads: List[Dict[str, Any]],
        esp_id: str,
        skip_collector: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Filter offline_rules that reference GPIOs absent from the config frame.

        AUT-59: An offline_rule whose actuator_gpio or sensor_gpio has no
        matching entry in the actuator/sensor payload arrays would cause the
        ESP32 firmware to enter a pending-exit blockade.  This guard removes
        such rules before the config is published.

        Args:
            offline_rules: Offline rule dicts from _build_offline_rules
            sensor_payloads: Sensor payloads that will be sent in this config
            actuator_payloads: Actuator payloads that will be sent in this config
            esp_id: Device ID for logging context

        Returns:
            Filtered list containing only consistent offline rules
        """
        if not offline_rules:
            return offline_rules

        actuator_gpios = {int(a["gpio"]) for a in actuator_payloads if "gpio" in a}
        sensor_gpios = {int(s["gpio"]) for s in sensor_payloads if "gpio" in s}

        consistent: List[Dict[str, Any]] = []
        stripped_details: List[Dict[str, Any]] = []

        for rule in offline_rules:
            a_gpio = rule.get("actuator_gpio")
            s_gpio = rule.get("sensor_gpio")
            sensor_value_type = str(rule.get("sensor_value_type", ""))
            is_time_window_only = self._is_time_window_only_sensor_type(sensor_value_type)
            reasons: List[str] = []

            if a_gpio is not None and int(a_gpio) not in actuator_gpios:
                reasons.append(f"actuator_gpio={a_gpio} not in config actuators")
            if not is_time_window_only and s_gpio is not None and int(s_gpio) not in sensor_gpios:
                reasons.append(f"sensor_gpio={s_gpio} not in config sensors")

            if reasons:
                stripped_details.append(
                    {
                        "actuator_gpio": a_gpio,
                        "sensor_gpio": s_gpio,
                        "sensor_value_type": rule.get("sensor_value_type", ""),
                        "reasons": reasons,
                    }
                )
                if skip_collector is not None:
                    # AUT-132: forward consistency-strip reasons into the
                    # diagnostics payload using the canonical reason code.
                    skip_collector.append(
                        {
                            "rule_id": "",
                            "rule_name": "<consistency-strip>",
                            "actuator_gpio": a_gpio,
                            "reason_code": self.REASON_GPIO_NOT_IN_FRAME,
                            "reason_detail": "; ".join(reasons),
                        }
                    )
            else:
                consistent.append(rule)

        if stripped_details:
            logger.warning(
                "[CONFIG] AUT-59: ESP %s — stripped %d/%d offline_rules "
                "(referenced GPIOs absent in config frame): %s",
                esp_id,
                len(stripped_details),
                len(offline_rules),
                stripped_details,
            )

        return consistent

    def _flatten_or_conditions_to_rules(
        self,
        conditions_list: List[Dict[str, Any]],
        actuator_entries: List[Dict[str, Any]],
        rule: Any,
        esp_id: str,
        hysteresis_states: Optional[Dict[str, bool]],
        skip_collector: Optional[List[Dict[str, Any]]],
        actuator_gpio: Optional[int],
        calibrated_sensors: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """
        DNF-flatten an OR-compound rule into individual single-condition offline rules.

        Each convertible branch in the OR list yields one offline rule per local actuator
        action.  Non-convertible branches (calibration-required, unsupported operator,
        invalid GPIO) are skipped individually with an INFO log; the conversion is
        considered successful as long as at least one branch produces a rule.

        Slot overflow (total rules > MAX_OFFLINE_RULES across all rules) is handled by
        the global cap in _build_offline_rules — no additional truncation here.

        Args:
            conditions_list: OR branch conditions from trigger_conditions.
            actuator_entries: Local actuator actions already collected by the caller.
            rule: CrossESPLogic rule instance (for rule_id / rule_name / hysteresis state).
            esp_id: Device ID of the target ESP.
            hysteresis_states: Preloaded hysteresis state map {rule_id:idx → bool}.
            skip_collector: Optional diagnostics list (receives entry on total failure).
            actuator_gpio: Representative actuator GPIO for diagnostics.

        Returns:
            List of offline rule dicts (may be empty if no branch converts).
        """
        rule_id_str = str(getattr(rule, "id", "") or "")
        rule_name = getattr(rule, "rule_name", "<unknown>") or "<unknown>"
        _MAX_SVT_LEN = 23  # ESP OfflineRule.sensor_value_type[24]

        result_rules: List[Dict[str, Any]] = []

        for branch_idx, cond in enumerate(conditions_list):
            if not isinstance(cond, dict):
                continue

            cond_type = cond.get("type", "")
            hysteresis_cond: Optional[Dict[str, Any]] = None
            hysteresis_cond_index: int = branch_idx

            if cond_type == "hysteresis" and cond.get("esp_id") == esp_id:
                hysteresis_cond = cond

            elif cond_type in ("sensor_threshold", "sensor") and cond.get("esp_id") == esp_id:
                raw_sensor_type: str = cond.get("sensor_type") or ""
                normalized_type: str = normalize_sensor_type(raw_sensor_type)

                _cal_key = f"{cond.get('gpio', -1)}:{normalized_type}"
                if normalized_type in self.CALIBRATION_REQUIRED_SENSOR_TYPES and _cal_key not in (
                    calibrated_sensors or set()
                ):
                    logger.info(
                        "[CONFIG] Rule '%s' OR-branch[%d]: sensor_type '%s' requires calibration (not calibrated), branch skipped",
                        rule_name,
                        branch_idx,
                        normalized_type,
                    )
                    continue

                op: str = cond.get("operator", "")
                raw_value = cond.get("value")
                if raw_value is None:
                    logger.info(
                        "[CONFIG] Rule '%s' OR-branch[%d]: threshold missing 'value', branch skipped",
                        rule_name,
                        branch_idx,
                    )
                    continue
                try:
                    threshold_value = float(raw_value)
                except (ValueError, TypeError):
                    logger.info(
                        "[CONFIG] Rule '%s' OR-branch[%d]: threshold value not numeric (%r), branch skipped",
                        rule_name,
                        branch_idx,
                        raw_value,
                    )
                    continue

                deadband = _get_default_deadband(normalized_type)

                if op in (">", ">="):
                    hysteresis_cond = {
                        "type": "hysteresis",
                        "esp_id": esp_id,
                        "gpio": cond.get("gpio", -1),
                        "sensor_type": normalized_type,
                        "activate_above": threshold_value,
                        "deactivate_below": threshold_value - deadband,
                        "activate_below": None,
                        "deactivate_above": None,
                    }
                    hysteresis_cond_index = -1
                elif op in ("<", "<="):
                    hysteresis_cond = {
                        "type": "hysteresis",
                        "esp_id": esp_id,
                        "gpio": cond.get("gpio", -1),
                        "sensor_type": normalized_type,
                        "activate_above": None,
                        "deactivate_below": None,
                        "activate_below": threshold_value,
                        "deactivate_above": threshold_value + deadband,
                    }
                    hysteresis_cond_index = -1
                else:
                    logger.info(
                        "[CONFIG] Rule '%s' OR-branch[%d]: operator '%s' not convertible, branch skipped",
                        rule_name,
                        branch_idx,
                        op,
                    )
                    continue

            else:
                logger.info(
                    "[CONFIG] Rule '%s' OR-branch[%d]: condition type '%s' not convertible to offline rule",
                    rule_name,
                    branch_idx,
                    cond_type,
                )
                continue

            if hysteresis_cond is None:
                continue

            activate_above: Optional[float] = hysteresis_cond.get("activate_above")
            deactivate_below: Optional[float] = hysteresis_cond.get("deactivate_below")
            activate_below: Optional[float] = hysteresis_cond.get("activate_below")
            deactivate_above: Optional[float] = hysteresis_cond.get("deactivate_above")

            is_cooling = activate_above is not None and deactivate_below is not None
            is_heating = activate_below is not None and deactivate_above is not None
            if not is_cooling and not is_heating:
                continue

            sensor_gpio: int = int(hysteresis_cond.get("gpio", -1))
            if sensor_gpio < 0:
                continue

            raw_svt: str = str(hysteresis_cond.get("sensor_type") or "")
            if self._is_time_window_only_sensor_type(raw_svt):
                sensor_value_type: str = raw_svt
            else:
                sensor_value_type = normalize_sensor_type(raw_svt)

            if len(sensor_value_type) > _MAX_SVT_LEN:
                continue

            _svt_cal_key = f"{sensor_gpio}:{sensor_value_type}"
            if (
                not self._is_time_window_only_sensor_type(sensor_value_type)
                and sensor_value_type in self.CALIBRATION_REQUIRED_SENSOR_TYPES
                and _svt_cal_key not in (calibrated_sensors or set())
            ):
                continue

            current_state_active = False
            if hysteresis_states is not None:
                state_key = f"{rule.id}:{hysteresis_cond_index}"
                current_state_active = hysteresis_states.get(state_key, False)

            for _entry in actuator_entries:
                rule_dict: Dict[str, Any] = {
                    "actuator_gpio": _entry["gpio"],
                    "sensor_gpio": sensor_gpio,
                    "sensor_value_type": sensor_value_type,
                    "activate_below": float(activate_below) if activate_below is not None else 0.0,
                    "deactivate_above": (
                        float(deactivate_above) if deactivate_above is not None else 0.0
                    ),
                    "activate_above": float(activate_above) if activate_above is not None else 0.0,
                    "deactivate_below": (
                        float(deactivate_below) if deactivate_below is not None else 0.0
                    ),
                    "current_state_active": current_state_active,
                    "max_on_seconds": _entry["duration"],
                }
                result_rules.append(rule_dict)

        if result_rules:
            logger.info(
                "[CONFIG] Rule '%s': OR compound DNF-flattened into %d offline rule(s) (AUT-739)",
                rule_name,
                len(result_rules),
            )
        else:
            logger.warning(
                "[CONFIG] Rule '%s': OR compound — no branch convertible to offline rule",
                rule_name,
            )
            if skip_collector is not None:
                skip_collector.append(
                    {
                        "rule_id": rule_id_str,
                        "rule_name": rule_name,
                        "actuator_gpio": actuator_gpio,
                        "reason_code": self.REASON_UNSUPPORTED_CONDITION,
                        "reason_detail": "OR compound: no branch could be converted to an offline rule",
                    }
                )

        return result_rules

    def _extract_offline_rule(
        self,
        rule: Any,
        esp_id: str,
        hysteresis_states: Optional[Dict[str, bool]] = None,
        skip_collector: Optional[List[Dict[str, Any]]] = None,
        calibrated_sensors: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract offline rule entries from a CrossESPLogic rule.

        Returns an empty list when the rule does not qualify as a local
        hysteresis rule for the given ESP device.  Returns one entry per
        local actuator action so that a multi-actuator rule (e.g. GPIO 25 ON
        + GPIO 14 ON) is decomposed into N single-actuator offline_rules as
        required by the firmware OfflineRule struct (AUT-664).

        Qualification criteria:
        1. trigger_conditions must be a hysteresis condition (type == "hysteresis")
           — single-condition rules only (compound conditions are excluded)
        2. The hysteresis condition's esp_id must equal esp_id
        3. At least one actuator_command action whose esp_id equals esp_id
        4. Either cooling mode (activate_above + deactivate_below) or
           heating mode (activate_below + deactivate_above) must be present

        AUT-132: When a ``skip_collector`` list is provided, every rejection
        appends a structured diagnostic record::

            {
                "rule_id": str,
                "rule_name": str,
                "actuator_gpio": int | None,
                "reason_code": str,   # one of REASON_* constants
                "reason_detail": str,
            }

        Args:
            rule: CrossESPLogic model instance
            esp_id: Device ID of the target ESP (e.g. "ESP_12AB34CD")
            hysteresis_states: Preloaded hysteresis state map (rule_id:idx)
            skip_collector: Optional list that receives skip diagnostics

        Returns:
            List of offline rule dicts (one per local actuator action), or [].
        """
        rule_id_str = str(getattr(rule, "id", "") or "")
        rule_name = getattr(rule, "rule_name", "<unknown>") or "<unknown>"

        def _skip(
            reason_code: str,
            reason_detail: str,
            actuator_gpio: Optional[int] = None,
            resolution_hint: Optional[str] = None,
        ) -> None:
            if skip_collector is not None:
                entry: Dict[str, Any] = {
                    "rule_id": rule_id_str,
                    "rule_name": rule_name,
                    "actuator_gpio": actuator_gpio,
                    "reason_code": reason_code,
                    "reason_detail": reason_detail,
                }
                if resolution_hint is not None:
                    entry["resolution_hint"] = resolution_hint
                skip_collector.append(entry)

        tc = rule.trigger_conditions

        # Normalise to a list of conditions for uniform processing
        if isinstance(tc, dict):
            conditions_list = [tc]
        elif isinstance(tc, list):
            conditions_list = tc
        else:
            logger.warning(
                "[CONFIG] Offline-rule skip: rule '%s' — malformed conditions_list (type: %s)",
                rule.rule_name,
                type(tc).__name__,
            )
            _skip(
                self.REASON_UNSUPPORTED_CONDITION,
                f"trigger_conditions has unsupported type {type(tc).__name__}",
            )
            return []

        # Determine compound operator; used for 3b DNF-flatten (OR) and 3c time_filter (AND).
        compound_op: str = getattr(rule, "logic_operator", None) or "AND"

        # Locate ALL actuator actions on the SAME ESP.
        # Firmware OfflineRule struct is single-actuator — each action becomes one entry.
        actions = rule.actions
        if not isinstance(actions, list):
            logger.warning(
                "[CONFIG] Offline-rule skip: rule '%s' — actions is not a list (type: %s)",
                rule.rule_name,
                type(actions).__name__,
            )
            _skip(
                self.REASON_UNSUPPORTED_CONDITION,
                f"actions has unsupported type {type(actions).__name__}",
            )
            return []

        # Collect ALL local actuator actions. One entry per action:
        # {"gpio": int, "duration": int, "target_state": bool | None}
        actuator_entries: List[Dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("type") not in ("actuator_command", "actuator"):
                continue
            if action.get("esp_id") != esp_id:
                continue
            raw_gpio = action.get("gpio")
            if raw_gpio is None:
                continue
            try:
                _gpio = int(raw_gpio)
            except (ValueError, TypeError):
                continue
            raw_duration = (
                action.get("duration_seconds")
                if "duration_seconds" in action
                else action.get("duration", 0)
            )
            try:
                _duration = max(0, int(raw_duration or 0))
            except (TypeError, ValueError):
                _duration = 0
            _command = str(action.get("command", "")).strip().upper()
            if _command == "ON":
                _target_state: Optional[bool] = True
            else:
                _raw_value = action.get("value")
                if isinstance(_raw_value, (int, float)) and float(_raw_value) > 0.0:
                    _target_state = True
                else:
                    _target_state = None
            actuator_entries.append(
                {"gpio": _gpio, "duration": _duration, "target_state": _target_state}
            )

        if not actuator_entries:
            seen_esp_ids = [
                str(a.get("esp_id", ""))
                for a in actions
                if isinstance(a, dict) and a.get("type") in ("actuator_command", "actuator")
            ]
            detail = (
                f"no actuator action targets ESP '{esp_id}'" f"; seen_esp_ids={seen_esp_ids}"
                if seen_esp_ids
                else f"no actuator action targets ESP '{esp_id}' (no matching action type or empty)"
            )
            logger.warning(
                "[CONFIG] Offline-rule skip: rule '%s' — %s",
                rule.rule_name,
                detail,
            )
            _skip(self.REASON_GPIO_NOT_IN_FRAME, detail)
            return []

        # Representative GPIO for rule-level skip diagnostics (condition validation).
        actuator_gpio: Optional[int] = actuator_entries[0]["gpio"]
        # True if any local action has an explicit ON command (time_window-only fallback).
        time_window_target_state: Optional[bool] = next(
            (e["target_state"] for e in actuator_entries if e["target_state"] is True), None
        )

        # 3b: OR-compound → DNF-flattening (AUT-739).
        # Each condition in the OR list becomes a separate single-sensor offline rule.
        # The firmware's sequential last-wins evaluation is semantically equivalent to OR:
        # both rules can independently activate the same actuator.
        # AND-compounds are not supported here — they continue on the path below.
        if compound_op == "OR" and len(conditions_list) > 1:
            return self._flatten_or_conditions_to_rules(
                conditions_list=conditions_list,
                actuator_entries=actuator_entries,
                rule=rule,
                esp_id=esp_id,
                hysteresis_states=hysteresis_states,
                skip_collector=skip_collector,
                actuator_gpio=actuator_gpio,
                calibrated_sensors=calibrated_sensors,
            )

        # Locate the first hysteresis condition that belongs to our ESP.
        # Track condition_index to match HysteresisConditionEvaluator's state key format.
        hysteresis_cond: Optional[Dict[str, Any]] = None
        hysteresis_cond_index: int = 0
        for idx, cond in enumerate(conditions_list):
            if not isinstance(cond, dict):
                continue
            if cond.get("type") == "hysteresis" and cond.get("esp_id") == esp_id:
                hysteresis_cond = cond
                hysteresis_cond_index = idx
                break

        if hysteresis_cond is None:
            # 3a: sensor_threshold / sensor condition fallback.
            # Simple threshold operators are converted to hysteresis by adding a
            # type-specific deadband so the ESP firmware can use its existing
            # hysteresis logic without a new condition type.
            threshold_cond: Optional[Dict[str, Any]] = None
            for cond in conditions_list:
                if not isinstance(cond, dict):
                    continue
                if (
                    cond.get("type") in ("sensor_threshold", "sensor")
                    and cond.get("esp_id") == esp_id
                ):
                    threshold_cond = cond
                    break

            if threshold_cond is None:
                # 3d: time_window-only fallback for local binary actuator schedules.
                # Uses existing offline rule/time_filter mechanics without changing
                # payload contracts or firmware struct layout.
                time_cond = next(
                    (
                        c
                        for c in conditions_list
                        if isinstance(c, dict) and c.get("type") in ("time_window", "time")
                    ),
                    None,
                )
                if time_cond is None:
                    condition_types = [
                        c.get("type", "MISSING") if isinstance(c, dict) else type(c).__name__
                        for c in conditions_list
                    ]
                    logger.warning(
                        "[CONFIG] Offline-rule skip: rule '%s' — no hysteresis or threshold "
                        "condition found (types: %s)",
                        rule.rule_name,
                        condition_types,
                    )
                    _skip(
                        self.REASON_UNSUPPORTED_CONDITION,
                        f"no hysteresis/threshold/time_window condition found "
                        f"(types: {condition_types})",
                        actuator_gpio=actuator_gpio,
                    )
                    return []

                if time_window_target_state is None:
                    logger.warning(
                        "[CONFIG] Offline-rule skip: rule '%s' — time_window-only rule "
                        "has no binary ON action for ESP %s",
                        rule.rule_name,
                        esp_id,
                    )
                    _skip(
                        self.REASON_UNSUPPORTED_CONDITION,
                        "time_window-only rule has no binary ON action",
                        actuator_gpio=actuator_gpio,
                    )
                    return []

                sensor_type_marker = (
                    self.TIME_WINDOW_ONLY_SENSOR_TYPE_ON
                    if time_window_target_state
                    else self.TIME_WINDOW_ONLY_SENSOR_TYPE_OFF
                )
                hysteresis_cond = {
                    "type": "hysteresis",
                    "esp_id": esp_id,
                    "gpio": self.TIME_WINDOW_ONLY_SENSOR_GPIO,
                    "sensor_type": sensor_type_marker,
                    # Keep a valid pair to satisfy existing mode checks; firmware
                    # special-cases these marker sensor types and ignores thresholds.
                    "activate_above": 1.0,
                    "deactivate_below": 0.0,
                    "activate_below": None,
                    "deactivate_above": None,
                }
                hysteresis_cond_index = -1
            else:
                # threshold fallback
                raw_sensor_type: str = threshold_cond.get("sensor_type") or ""
                normalized_type: str = normalize_sensor_type(raw_sensor_type)
                _cal_key = f"{threshold_cond.get('gpio', -1)}:{normalized_type}"
                if normalized_type in self.CALIBRATION_REQUIRED_SENSOR_TYPES and _cal_key not in (
                    calibrated_sensors or set()
                ):
                    logger.info(
                        "[CONFIG] Rule '%s': sensor_type '%s' (normalized: '%s') requires "
                        "calibration (not calibrated) — offline threshold rule skipped.",
                        rule.rule_name,
                        raw_sensor_type,
                        normalized_type,
                    )
                    _skip(
                        self.REASON_CALIBRATION_REQUIRED,
                        f"sensor type '{normalized_type}' requires calibration data",
                        actuator_gpio=actuator_gpio,
                    )
                    return []

                op: str = threshold_cond.get("operator", "")
                raw_value = threshold_cond.get("value")
                if raw_value is None:
                    logger.info(
                        "[CONFIG] Rule '%s': threshold condition missing 'value', skipping",
                        rule.rule_name,
                    )
                    _skip(
                        self.REASON_UNSUPPORTED_CONDITION,
                        "threshold condition missing 'value'",
                        actuator_gpio=actuator_gpio,
                    )
                    return []
                try:
                    threshold_value = float(raw_value)
                except (ValueError, TypeError):
                    logger.info(
                        "[CONFIG] Rule '%s': threshold 'value' is not numeric, skipping",
                        rule.rule_name,
                    )
                    _skip(
                        self.REASON_UNSUPPORTED_CONDITION,
                        f"threshold 'value' is not numeric ({raw_value!r})",
                        actuator_gpio=actuator_gpio,
                    )
                    return []

                deadband = _get_default_deadband(normalized_type)

                if op in (">", ">="):
                    synth_activate_above: Optional[float] = threshold_value
                    synth_deactivate_below: Optional[float] = threshold_value - deadband
                    synth_activate_below: Optional[float] = None
                    synth_deactivate_above: Optional[float] = None
                elif op in ("<", "<="):
                    synth_activate_above = None
                    synth_deactivate_below = None
                    synth_activate_below = threshold_value
                    synth_deactivate_above = threshold_value + deadband
                else:
                    logger.info(
                        "[CONFIG] Rule '%s': operator '%s' not convertible to offline hysteresis",
                        rule.rule_name,
                        op,
                    )
                    _skip(
                        self.REASON_UNSUPPORTED_CONDITION,
                        f"operator '{op}' not convertible to offline hysteresis",
                        actuator_gpio=actuator_gpio,
                    )
                    return []

                # Build a synthetic hysteresis_cond so the remaining validation and
                # output-building code can operate on a single unified path.
                hysteresis_cond = {
                    "type": "hysteresis",
                    "esp_id": esp_id,
                    "gpio": threshold_cond.get("gpio", -1),
                    "sensor_type": normalized_type,
                    "activate_above": synth_activate_above,
                    "deactivate_below": synth_deactivate_below,
                    "activate_below": synth_activate_below,
                    "deactivate_above": synth_deactivate_above,
                }
                hysteresis_cond_index = (
                    -1
                )  # no DB hysteresis state entry for threshold-converted rules

        # Validate that threshold fields form a valid mode
        activate_above: Optional[float] = hysteresis_cond.get("activate_above")
        deactivate_below: Optional[float] = hysteresis_cond.get("deactivate_below")
        activate_below: Optional[float] = hysteresis_cond.get("activate_below")
        deactivate_above: Optional[float] = hysteresis_cond.get("deactivate_above")

        is_cooling = activate_above is not None and deactivate_below is not None
        is_heating = activate_below is not None and deactivate_above is not None

        if not is_cooling and not is_heating:
            logger.debug(
                "[CONFIG] Rule '%s': hysteresis condition missing valid threshold pair, skipping",
                rule.rule_name,
            )
            _skip(
                self.REASON_UNSUPPORTED_CONDITION,
                "hysteresis condition missing valid threshold pair "
                "(needs activate_above+deactivate_below or activate_below+deactivate_above)",
                actuator_gpio=actuator_gpio,
            )
            return []

        sensor_gpio: int = int(hysteresis_cond.get("gpio", -1))
        if sensor_gpio < 0:
            logger.debug(
                "[CONFIG] Rule '%s': hysteresis condition has invalid gpio, skipping",
                rule.rule_name,
            )
            _skip(
                self.REASON_GPIO_NOT_IN_FRAME,
                f"hysteresis sensor_gpio={sensor_gpio} is invalid (<0)",
                actuator_gpio=actuator_gpio,
            )
            return []

        # sensor_value_type — prefer explicit sensor_type on the condition;
        # this is the same value_type string used in SensorReading.sensor_type.
        # Normalize aliases to canonical types (e.g. "soil_moisture" → "moisture",
        # "ph_sensor" → "ph") so the calibration guard and the firmware ValueCache
        # key both operate on the same canonical string.
        raw_sensor_type = str(hysteresis_cond.get("sensor_type") or "")
        if self._is_time_window_only_sensor_type(raw_sensor_type):
            sensor_value_type = raw_sensor_type
        else:
            sensor_value_type = normalize_sensor_type(raw_sensor_type)

        _MAX_SENSOR_VALUE_TYPE_LEN = 23  # ESP OfflineRule.sensor_value_type[24]
        if len(sensor_value_type) > _MAX_SENSOR_VALUE_TYPE_LEN:
            logger.warning(
                "[CONFIG] Offline-rule fuer Regel '%s' uebersprungen: sensor_value_type '%s' "
                "ist %d Zeichen lang (max %d fuer ESP OfflineRule struct)",
                rule.rule_name,
                sensor_value_type,
                len(sensor_value_type),
                _MAX_SENSOR_VALUE_TYPE_LEN,
            )
            _skip(
                self.REASON_UNSUPPORTED_CONDITION,
                f"sensor_value_type '{sensor_value_type}' exceeds firmware limit "
                f"({_MAX_SENSOR_VALUE_TYPE_LEN} chars)",
                actuator_gpio=actuator_gpio,
            )
            return []

        # Guard: analog sensors have no calibration parameters on the ESP32.
        # applyLocalConversion() delivers only the ADC raw value (0-4095) for
        # these types — comparing it against a physical-unit threshold would
        # produce wrong and potentially dangerous trigger decisions.
        # sensor_value_type is already normalized above, so direct set-membership
        # check is sufficient (no alias splitting needed).
        # AUT-739 calibration gate: allow through if calibration_data is present in DB.
        _hyst_cal_key = f"{sensor_gpio}:{sensor_value_type}"
        if (
            not self._is_time_window_only_sensor_type(sensor_value_type)
            and sensor_value_type in self.CALIBRATION_REQUIRED_SENSOR_TYPES
            and _hyst_cal_key not in (calibrated_sensors or set())
        ):
            logger.warning(
                "[CONFIG] Rule '%s': sensor_type '%s' requires calibration "
                "(actuator_gpio=%d) — ESP has no calibration parameters, "
                "applyLocalConversion delivers ADC raw value only. "
                "Offline rule skipped.",
                rule.rule_name,
                sensor_value_type,
                actuator_gpio,
            )
            _skip(
                self.REASON_CALIBRATION_REQUIRED,
                f"sensor type '{sensor_value_type}' requires calibration data",
                actuator_gpio=actuator_gpio,
            )
            return []

        # Look up the persisted hysteresis state for this rule+condition.
        # The ESP uses current_state_active to initialise is_active on config push,
        # preventing a cold-start reset when the server reconnects after a reboot.
        # Fallback is False (safe: actuator stays OFF until first sensor evaluation).
        current_state_active = False
        if hysteresis_states is not None:
            state_key = f"{rule.id}:{hysteresis_cond_index}"
            current_state_active = hysteresis_states.get(state_key, False)
            logger.debug(
                "[CONFIG] Rule '%s' hysteresis state key=%s -> current_state_active=%s",
                rule.rule_name,
                state_key,
                current_state_active,
            )

        # 3c: Extract time_filter from any time_window / time condition.
        # Only applies to AND-compounds or single-condition rules; OR-compounds are handled
        # in 3b via _flatten_or_conditions_to_rules() and return early.
        time_filter: Optional[Dict[str, Any]] = None
        if compound_op == "AND" or len(conditions_list) == 1:
            for cond in conditions_list:
                if not isinstance(cond, dict):
                    continue
                if cond.get("type") in ("time_window", "time"):
                    tz = str(cond.get("timezone", "UTC") or "UTC")
                    start_h = cond.get("start_hour")
                    start_m = cond.get("start_minute")
                    end_h = cond.get("end_hour")
                    end_m = cond.get("end_minute")

                    # Backward-compatible fallback for old payloads using HH:MM strings.
                    start_time = cond.get("start_time")
                    end_time = cond.get("end_time")
                    if (start_h is None or start_m is None) and isinstance(start_time, str):
                        parts = start_time.split(":")
                        if len(parts) == 2:
                            start_h = int(parts[0])
                            start_m = int(parts[1])
                    if (end_h is None or end_m is None) and isinstance(end_time, str):
                        parts = end_time.split(":")
                        if len(parts) == 2:
                            end_h = int(parts[0])
                            end_m = int(parts[1])

                    start_h = int(start_h or 0)
                    start_m = int(start_m or 0)
                    end_h = int(end_h or 0)
                    end_m = int(end_m or 0)
                    raw_days = cond.get("days_of_week", None)
                    time_filter = {
                        "enabled": True,
                        "start_hour": start_h % 24,
                        "start_minute": start_m % 60,
                        "end_hour": end_h % 24,
                        "end_minute": end_m % 60,
                        "days_of_week_mask": _days_of_week_db_to_tm_mask(raw_days),
                        "timezone": tz,
                    }
                    break

        # Build one offline_rule dict per local actuator action.
        result_rules: List[Dict[str, Any]] = []
        for _entry in actuator_entries:
            rule_dict: Dict[str, Any] = {
                "actuator_gpio": _entry["gpio"],
                "sensor_gpio": sensor_gpio,
                "sensor_value_type": sensor_value_type,
                "activate_below": float(activate_below) if activate_below is not None else 0.0,
                "deactivate_above": (
                    float(deactivate_above) if deactivate_above is not None else 0.0
                ),
                "activate_above": float(activate_above) if activate_above is not None else 0.0,
                "deactivate_below": (
                    float(deactivate_below) if deactivate_below is not None else 0.0
                ),
                "current_state_active": current_state_active,
                # Carry per-action runtime cap so firmware enforces "ON for N seconds"
                # during MQTT disconnect / OFFLINE_ACTIVE.
                "max_on_seconds": _entry["duration"],
            }
            if time_filter is not None:
                rule_dict["time_filter"] = time_filter
            result_rules.append(rule_dict)
        return result_rules
