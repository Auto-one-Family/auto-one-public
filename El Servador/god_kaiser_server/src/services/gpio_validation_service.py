"""
GPIO Validation Service

Zentrale Validierungslogik für GPIO-Verfügbarkeit.
Prüft gegen: System-Pins, DB-Sensoren, DB-Aktoren, ESP-gemeldeten Status (Phase 1).

Phase: 2 (Foundation Layer)
Author: KI-Agent (Claude)
Created: 2026-01-08

Usage:
    service = GpioValidationService(session, sensor_repo, actuator_repo, esp_repo)
    result = await service.validate_gpio_available(esp_db_id, gpio)
    if not result.available:
        raise HTTPException(409, detail=result.message)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..core.constants import (
    HARDWARE_TYPE_ESP32_WROOM,
    HARDWARE_TYPE_ESP32_S3_DEVKITC1,
    GPIO_RESERVED_ESP32_S3_DEVKITC1,
)
from ..db.repositories.sensor_repo import SensorRepository
from ..db.repositories.actuator_repo import ActuatorRepository
from ..db.repositories.esp_repo import ESPRepository

logger = get_logger(__name__)


class GpioConflictType(str, Enum):
    """Art des GPIO-Konflikts"""

    NONE = "none"
    SYSTEM = "system"  # I2C, SPI, Flash, Boot-Pins
    SENSOR = "sensor"  # Bereits von Sensor belegt
    ACTUATOR = "actuator"  # Bereits von Actuator belegt
    ESP_RESERVED = "esp_reserved"  # ESP meldet als belegt (unbekannter Owner)


@dataclass
class GpioValidationResult:
    """Ergebnis der GPIO-Validierung"""

    available: bool
    conflict_type: Optional[GpioConflictType] = None
    conflict_component: Optional[str] = None  # z.B. "DS18B20", "pump_1", "I2C_SDA"
    conflict_id: Optional[int] = None  # DB-ID der konfliktierenden Komponente
    esp_reported_owner: Optional[str] = None  # Was der ESP für diesen GPIO meldet
    message: Optional[str] = None  # Menschenlesbare Fehlermeldung
    warning: Optional[str] = None  # Soft-Warnung (Pin nutzbar, aber suboptimal)


@dataclass
class BoardConstraints:
    """Board-spezifische GPIO-Constraints"""

    input_only_pins: Set[int]
    i2c_bus_pins: Set[int]
    system_reserved_pins: Set[int]
    gpio_max: int


# =============================================================================
# System-reservierte Pins (board-spezifisch)
# Diese Pins dürfen NIEMALS für Sensoren/Aktoren verwendet werden
# =============================================================================

# ESP32-WROOM: Flash SPI pins + Boot-Strapping/UART pins hard-reserved.
# Note: Boot-Strapping pins (0, 2, 12, 15) are sampled only at boot but
# must not be driven high/low during normal operation to avoid boot issues.
# UART pins (1, 3) are used by the debug console.
SYSTEM_RESERVED_PINS_WROOM: Set[int] = {
    0,  # Boot-Strapping (HIGH = boot from UART, LOW = boot from flash)
    1,  # UART TX0 (USB-to-serial debug console)
    2,  # Boot-Strapping (must be LOW for flash boot)
    3,  # UART RX0 (USB-to-serial debug console)
    6,  # Flash SPI CLK
    7,  # Flash SPI D0
    8,  # Flash SPI D1
    9,  # Flash SPI D2
    10,  # Flash SPI D3
    11,  # Flash SPI CMD
    12,  # MTDI Strapping (controls flash voltage; HIGH = 1.8V, destroys 3.3V boards)
}

# XIAO ESP32-C3: USB D+/D- pins are hard-reserved
# GPIO 12 is a normal bidirectional pin on C3 (NOT a strapping pin)
SYSTEM_RESERVED_PINS_C3: Set[int] = {
    18,  # USB D-
    19,  # USB D+
}

# ESP32-S3-DevKitC-1 N8R8: Octal Flash+PSRAM, USB, RGB, strap/UART (mirrors esp32_s3_devkit.h)
SYSTEM_RESERVED_PINS_S3: Set[int] = GPIO_RESERVED_ESP32_S3_DEVKITC1

# Legacy alias — kept for backward compat, points to WROOM set
SYSTEM_RESERVED_PINS: Set[int] = SYSTEM_RESERVED_PINS_WROOM

# =============================================================================
# Hardware-spezifische Pin-Constraints (Legacy - wird durch Fix #4 ersetzt)
# Diese werden jetzt board-aware über _get_board_constraints() geladen
# =============================================================================
# Input-Only Pins: Können nur als Input verwendet werden (kein OUTPUT möglich)
# ESP32-WROOM: {34, 35, 36, 39}
# XIAO ESP32-C3: {} (keine input-only pins)
INPUT_ONLY_PINS_LEGACY: Set[int] = {34, 35, 36, 39}  # ESP32-WROOM (Fallback)

# I2C Bus Pins: Standard I2C Bus (können nur für I2C/ONEWIRE verwendet werden)
# ESP32-WROOM: {21, 22} (SDA=21, SCL=22)
# XIAO ESP32-C3: {4, 5} (SDA=4, SCL=5)
I2C_BUS_PINS_LEGACY: Set[int] = {21, 22}  # ESP32-WROOM (Fallback)

# =============================================================================
# ADC Pin Constraints (ESP32-WROOM)
# ADC2 pins do NOT work when WiFi is active — only ADC1 is reliable
# =============================================================================
ADC1_SAFE_PINS: Set[int] = {32, 33, 34, 35, 36, 39}
ADC2_WIFI_CONFLICT_PINS: Set[int] = {0, 2, 4, 12, 13, 14, 15, 25, 26, 27}

# Menschenlesbare Namen für System-Pins (WROOM)
SYSTEM_PIN_NAMES_WROOM: Dict[int, str] = {
    0: "Boot-Strapping",
    1: "UART TX0",
    2: "Boot-Strapping",
    3: "UART RX0",
    6: "Flash CLK",
    7: "Flash D0",
    8: "Flash D1",
    9: "Flash D2",
    10: "Flash D3",
    11: "Flash CMD",
    12: "MTDI Strapping (Flash-Spannung)",
}

# Menschenlesbare Namen für System-Pins (ESP32-C3)
SYSTEM_PIN_NAMES_C3: Dict[int, str] = {
    18: "USB D-",
    19: "USB D+",
}

# Menschenlesbare Namen für System-Pins (ESP32-S3-DevKitC-1)
SYSTEM_PIN_NAMES_S3: Dict[int, str] = {
    0: "Boot-Strapping",
    3: "JTAG Strapping",
    19: "USB D-",
    20: "USB D+",
    26: "Octal Flash/PSRAM",
    27: "Octal Flash/PSRAM",
    28: "Octal Flash/PSRAM",
    29: "Octal Flash/PSRAM",
    30: "Octal Flash/PSRAM",
    31: "Octal Flash/PSRAM",
    32: "Octal Flash/PSRAM",
    33: "Octal Flash/PSRAM",
    34: "Octal Flash/PSRAM",
    35: "Octal Flash/PSRAM",
    36: "Octal Flash/PSRAM",
    37: "Octal Flash/PSRAM",
    38: "RGB LED (v1.1)",
    43: "UART0 TX",
    44: "UART0 RX",
    45: "Strapping",
    46: "VDD_SPI Strapping",
    48: "RGB LED (v1.0)",
}

# Legacy alias — kept for backward compat
SYSTEM_PIN_NAMES: Dict[int, str] = SYSTEM_PIN_NAMES_WROOM


class GpioValidationService:
    """
    Service für GPIO-Verfügbarkeitsprüfung.

    Prüft in dieser Reihenfolge:
    1. GPIO Range Check (board-specific)
    2. System-Pins (statisch, ohne DB-Query)
    3. Hardware Constraints (input-only, I2C pins - board-specific)
    4. DB: Sensoren
    5. DB: Aktoren
    6. ESP-gemeldeten Status (Phase 1 Daten)

    Usage:
        service = GpioValidationService(session, sensor_repo, actuator_repo, esp_repo)
        result = await service.validate_gpio_available(esp_db_id, gpio)
        if not result.available:
            raise HTTPException(409, detail=result.message)
    """

    def __init__(
        self,
        session: AsyncSession,
        sensor_repo: SensorRepository,
        actuator_repo: ActuatorRepository,
        esp_repo: ESPRepository,
    ):
        self.session = session
        self.sensor_repo = sensor_repo
        self.actuator_repo = actuator_repo
        self.esp_repo = esp_repo

    def _get_system_reserved_pins(
        self, board_model: Optional[str]
    ) -> tuple[Set[int], Dict[int, str]]:
        """
        Returns the board-specific set of hard-reserved system pins and their names.

        ESP32-WROOM: Flash SPI pins (6-11), Boot-Strapping pins (0, 2, 12) and
        UART pins (1, 3) are permanently reserved (see SYSTEM_RESERVED_PINS_WROOM).
        XIAO ESP32-C3: USB pins (18, 19) are permanently reserved.

        Note: GPIO 12 (MTDI) is reserved on WROOM because driving it HIGH at any
        time can latch the flash voltage to 1.8 V and permanently destroy 3.3 V boards.
        It is NOT freely usable at runtime despite being a boot-strapping pin.

        Args:
            board_model: Hardware type string (ESP32_WROOM, XIAO_ESP32_C3, etc.)

        Returns:
            Tuple of (reserved_pins_set, pin_names_dict)
        """
        if not board_model:
            return SYSTEM_RESERVED_PINS_WROOM, SYSTEM_PIN_NAMES_WROOM

        board_model_upper = board_model.upper()
        if board_model_upper in ("XIAO_ESP32_C3", "XIAO_ESP32C3", "ESP32_C3"):
            return SYSTEM_RESERVED_PINS_C3, SYSTEM_PIN_NAMES_C3

        if board_model_upper in (
            HARDWARE_TYPE_ESP32_S3_DEVKITC1,
            "ESP32_S3_DEVKIT",
            "ESP32_S3",
        ):
            return SYSTEM_RESERVED_PINS_S3, SYSTEM_PIN_NAMES_S3

        # Default: WROOM-style Flash SPI pins
        return SYSTEM_RESERVED_PINS_WROOM, SYSTEM_PIN_NAMES_WROOM

    def _get_board_constraints(self, board_model: Optional[str]) -> BoardConstraints:
        """
        Gibt board-spezifische GPIO-Constraints zurück.

        Args:
            board_model: Hardware type (ESP32_WROOM, XIAO_ESP32_C3, etc.)

        Returns:
            BoardConstraints mit input_only_pins, i2c_bus_pins, gpio_max
        """
        # Normalize board_model (handle variations)
        if not board_model:
            logger.warning("Unknown board_model (None), defaulting to ESP32_WROOM")
            board_model = HARDWARE_TYPE_ESP32_WROOM

        board_model_upper = board_model.upper()

        # ESP32-WROOM variants
        if board_model_upper in ("ESP32_WROOM", "ESP32_WROOM_32", "ESP32_WROOM32"):
            return BoardConstraints(
                input_only_pins={34, 35, 36, 39},
                i2c_bus_pins={21, 22},
                system_reserved_pins=SYSTEM_RESERVED_PINS_WROOM,
                gpio_max=39,
            )

        # XIAO ESP32-C3 variants
        if board_model_upper in ("XIAO_ESP32_C3", "XIAO_ESP32C3", "ESP32_C3"):
            return BoardConstraints(
                input_only_pins=set(),  # XIAO has no input-only pins
                i2c_bus_pins={4, 5},
                system_reserved_pins=SYSTEM_RESERVED_PINS_C3,
                gpio_max=21,
            )

        # ESP32-S3-DevKitC-1 N8R8 (mirrors esp32_s3_devkit.h)
        if board_model_upper in (
            HARDWARE_TYPE_ESP32_S3_DEVKITC1,
            "ESP32_S3_DEVKIT",
            "ESP32_S3",
        ):
            return BoardConstraints(
                input_only_pins=set(),
                i2c_bus_pins={8, 9},
                system_reserved_pins=SYSTEM_RESERVED_PINS_S3,
                gpio_max=48,
            )

        # Default to WROOM if unknown
        logger.warning(
            f"Unknown board_model '{board_model}', defaulting to ESP32_WROOM constraints"
        )
        return BoardConstraints(
            input_only_pins={34, 35, 36, 39},
            i2c_bus_pins={21, 22},
            system_reserved_pins=SYSTEM_RESERVED_PINS_WROOM,
            gpio_max=39,
        )

    async def validate_gpio_available(
        self,
        esp_db_id: uuid.UUID,
        gpio: int,
        exclude_sensor_id: Optional[uuid.UUID] = None,
        exclude_actuator_id: Optional[uuid.UUID] = None,
        purpose: str = "sensor",
        interface_type: str = "ANALOG",
    ) -> GpioValidationResult:
        """
        Prüft ob ein GPIO-Pin für eine neue Sensor/Actuator-Konfiguration verfügbar ist.

        Args:
            esp_db_id: Datenbank-ID des ESP-Devices (UUID)
            gpio: GPIO-Pin-Nummer
            exclude_sensor_id: Sensor-ID ausschließen (für Update-Operationen)
            exclude_actuator_id: Actuator-ID ausschließen (für Update-Operationen)
            purpose: "sensor" oder "actuator" (Standard: "sensor")
            interface_type: "I2C", "ONEWIRE", "ANALOG", "DIGITAL" (Standard: "ANALOG")

        Returns:
            GpioValidationResult mit Verfügbarkeit und ggf. Konflikt-Details
        """

        # =====================================================================
        # 0. Fetch ESP device and get board-specific constraints (Fix #4)
        # =====================================================================
        esp_device = await self.esp_repo.get_by_id(esp_db_id)
        if not esp_device:
            rejection_reason = f"ESP device {esp_db_id} not found"
            logger.error(f"Rejected GPIO config: ESP {esp_db_id} not found, GPIO {gpio}")
            return GpioValidationResult(
                available=False, conflict_type=GpioConflictType.SYSTEM, message=rejection_reason
            )

        hardware_type = esp_device.hardware_type
        board_constraints = self._get_board_constraints(hardware_type)
        system_reserved, system_pin_names = self._get_system_reserved_pins(hardware_type)

        # =====================================================================
        # 0.5. GPIO Range Check (board-specific, Fix #4)
        # =====================================================================
        if gpio < 0 or gpio > board_constraints.gpio_max:
            rejection_reason = (
                f"GPIO {gpio} is out of range for {hardware_type}. "
                f"Valid range: 0-{board_constraints.gpio_max}"
            )
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.SYSTEM,
                conflict_component="GPIO_RANGE",
                message=rejection_reason,
            )

        # =====================================================================
        # 1. System-Pin Check (board-specific, sofort, ohne DB-Query)
        # =====================================================================
        if gpio in system_reserved:
            pin_name = system_pin_names.get(gpio, f"GPIO_{gpio}")
            rejection_reason = (
                f"GPIO {gpio} ist ein System-Pin ({pin_name}) und kann nicht verwendet werden"
            )
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.SYSTEM,
                conflict_component=pin_name,
                message=rejection_reason,
            )

        # =====================================================================
        # 1.5. Hardware Constraints Check (Fix #2 & #3 - board-aware via Fix #4)
        # =====================================================================
        # Input-Only Check: Actuators cannot use input-only pins
        if gpio in board_constraints.input_only_pins and purpose == "actuator":
            rejection_reason = (
                f"GPIO {gpio} is input-only on {hardware_type} and cannot be used for actuators. "
                f"These pins support INPUT mode only."
            )
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.SYSTEM,
                conflict_component="INPUT_ONLY_PIN",
                message=rejection_reason,
            )

        # I2C Pin Check: ANALOG/DIGITAL sensors cannot use I2C bus pins
        if gpio in board_constraints.i2c_bus_pins and interface_type not in ("I2C", "ONEWIRE"):
            rejection_reason = (
                f"GPIO {gpio} is reserved for I2C bus on {hardware_type}. "
                f"Only I2C or ONEWIRE sensors can use this pin. "
                f"Interface type '{interface_type}' is not allowed."
            )
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.SYSTEM,
                conflict_component="I2C_BUS_PIN",
                message=rejection_reason,
            )

        # =====================================================================
        # 2. Sensor-Check in DB
        # =====================================================================
        existing_sensor = await self.sensor_repo.get_by_esp_and_gpio(esp_db_id, gpio)
        if existing_sensor and existing_sensor.id != exclude_sensor_id:
            sensor_name = existing_sensor.sensor_name or existing_sensor.sensor_type
            rejection_reason = f"GPIO {gpio} ist bereits von Sensor '{sensor_name}' belegt"
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.SENSOR,
                conflict_component=existing_sensor.sensor_type,
                conflict_id=existing_sensor.id,
                message=rejection_reason,
            )

        # =====================================================================
        # 3. Actuator-Check in DB
        # =====================================================================
        existing_actuator = await self.actuator_repo.get_by_esp_and_gpio(esp_db_id, gpio)
        if existing_actuator and existing_actuator.id != exclude_actuator_id:
            actuator_name = existing_actuator.actuator_name or existing_actuator.actuator_type
            rejection_reason = f"GPIO {gpio} ist bereits von Actuator '{actuator_name}' belegt"
            logger.info(
                f"Rejected GPIO config: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"purpose={purpose}, interface={interface_type} (reason: {rejection_reason})"
            )
            return GpioValidationResult(
                available=False,
                conflict_type=GpioConflictType.ACTUATOR,
                conflict_component=existing_actuator.actuator_type,
                conflict_id=existing_actuator.id,
                message=rejection_reason,
            )

        # =====================================================================
        # 4. ESP-gemeldeten Status prüfen (aus Phase 1)
        # =====================================================================
        esp_gpio_status = await self._get_esp_gpio_status(esp_db_id, gpio)
        if esp_gpio_status:
            owner = esp_gpio_status.get("owner")
            component = esp_gpio_status.get("component", "unknown")

            # ESP meldet diesen GPIO als System-Pin
            if owner == "system":
                return GpioValidationResult(
                    available=False,
                    conflict_type=GpioConflictType.SYSTEM,
                    conflict_component=component,
                    esp_reported_owner=owner,
                    message=f"GPIO {gpio} wird vom ESP als System-Pin gemeldet ({component})",
                )

            # ESP meldet belegt, aber nicht in DB
            # → Warnung loggen, aber erlauben (Sync-Problem)
            if owner in ("sensor", "actuator"):
                # Nur warnen wenn wir keinen DB-Eintrag haben
                if not existing_sensor and not existing_actuator:
                    logger.warning(
                        f"GPIO {gpio} vom ESP als '{owner}' gemeldet ({component}), "
                        f"aber nicht in DB gefunden. Mögliches Sync-Problem."
                    )

        # =====================================================================
        # 5. ADC2 Warning für ANALOG-Sensoren (WiFi-Konflikt)
        # =====================================================================
        adc_warning: Optional[str] = None
        if interface_type == "ANALOG" and gpio in ADC2_WIFI_CONFLICT_PINS:
            adc_warning = (
                f"GPIO {gpio} nutzt ADC2, der bei aktivem WiFi nicht funktioniert. "
                f"Empfohlen: ADC1-Pins (32, 33, 34, 35, 36, 39) für zuverlässige Messungen."
            )
            logger.info(
                f"ADC2 warning: ESP {esp_db_id} ({hardware_type}), GPIO {gpio}, "
                f"interface={interface_type} — ADC2+WiFi conflict"
            )

        # =====================================================================
        # Alles OK - GPIO ist verfügbar
        # =====================================================================
        return GpioValidationResult(
            available=True,
            esp_reported_owner=esp_gpio_status.get("owner") if esp_gpio_status else None,
            warning=adc_warning,
        )

    async def get_all_used_gpios(self, esp_db_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Gibt alle belegten GPIOs für einen ESP zurück.
        Kombiniert DB-Daten mit ESP-gemeldetem Status.

        Uses board-specific reserved pins via _get_system_reserved_pins() so that
        XIAO ESP32-C3 does not report WROOM-only pins (e.g. 6-12) as reserved.

        Args:
            esp_db_id: Datenbank-ID des ESP-Devices (UUID)

        Returns:
            Liste von Dictionaries mit gpio, owner, component, name, id, source
        """
        used_gpios: List[Dict[str, Any]] = []

        # Fetch board type for board-aware system pin selection
        esp_device = await self.esp_repo.get_by_id(esp_db_id)
        hardware_type: Optional[str] = esp_device.hardware_type if esp_device else None
        board_reserved_pins, board_pin_names = self._get_system_reserved_pins(hardware_type)

        # Sensoren aus DB
        sensors = await self.sensor_repo.get_by_esp(esp_db_id)
        for sensor in sensors:
            used_gpios.append(
                {
                    "gpio": sensor.gpio,
                    "owner": "sensor",
                    "component": sensor.sensor_type,
                    "name": sensor.sensor_name,
                    "id": str(sensor.id),
                    "source": "database",
                }
            )

        # Aktoren aus DB
        actuators = await self.actuator_repo.get_by_esp(esp_db_id)
        for actuator in actuators:
            used_gpios.append(
                {
                    "gpio": actuator.gpio,
                    "owner": "actuator",
                    "component": actuator.actuator_type,
                    "name": actuator.actuator_name,
                    "id": str(actuator.id),
                    "source": "database",
                }
            )

        # System-Pins aus ESP-Status (Phase 1 Daten)
        esp_status = await self._get_all_esp_gpio_status(esp_db_id)
        for status in esp_status:
            if status.get("owner") == "system":
                gpio_num = status.get("gpio")
                # System-Pins nur aus ESP-Status, nicht aus DB
                if not any(g["gpio"] == gpio_num for g in used_gpios):
                    used_gpios.append(
                        {
                            "gpio": gpio_num,
                            "owner": "system",
                            "component": status.get("component", "unknown"),
                            "name": None,
                            "id": None,
                            "source": "esp_reported",
                        }
                    )

        # Statische System-Pins hinzufügen — board-aware (nicht Legacy WROOM-only)
        for gpio_num in board_reserved_pins:
            if not any(g["gpio"] == gpio_num for g in used_gpios):
                pin_name = board_pin_names.get(gpio_num, f"System GPIO {gpio_num}")
                used_gpios.append(
                    {
                        "gpio": gpio_num,
                        "owner": "system",
                        "component": pin_name,
                        "name": None,
                        "id": None,
                        "source": "static",
                    }
                )

        return sorted(used_gpios, key=lambda x: x["gpio"])

    async def _get_esp_gpio_status(
        self, esp_db_id: uuid.UUID, gpio: int
    ) -> Optional[Dict[str, Any]]:
        """
        Holt GPIO-Status für einen spezifischen Pin aus ESP device_metadata.

        Args:
            esp_db_id: Datenbank-ID des ESP-Devices
            gpio: GPIO-Pin-Nummer

        Returns:
            Dictionary mit gpio, owner, component, mode, safe oder None
        """
        esp = await self.esp_repo.get_by_id(esp_db_id)
        if not esp or not esp.device_metadata:
            return None

        gpio_status_list = esp.device_metadata.get("gpio_status", [])
        for status in gpio_status_list:
            if status.get("gpio") == gpio:
                return status

        return None

    async def _get_all_esp_gpio_status(self, esp_db_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Holt alle GPIO-Status aus ESP device_metadata.

        Args:
            esp_db_id: Datenbank-ID des ESP-Devices

        Returns:
            Liste von GPIO-Status-Dictionaries
        """
        esp = await self.esp_repo.get_by_id(esp_db_id)
        if not esp or not esp.device_metadata:
            return []

        return esp.device_metadata.get("gpio_status", [])

    def _get_system_pin_name(self, gpio: int) -> str:
        """
        Gibt menschenlesbaren Namen für System-Pins zurück.

        Args:
            gpio: GPIO-Pin-Nummer

        Returns:
            Menschenlesbarer Name oder Fallback
        """
        return SYSTEM_PIN_NAMES.get(gpio, f"System GPIO {gpio}")
