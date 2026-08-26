"""
Unit Tests for GPIO Validation Service

Phase: 2 (GPIO Validation)
Author: KI-Agent (Claude)
Created: 2026-01-08

Tests:
- System pin rejection
- Sensor conflict detection
- Actuator conflict detection
- Cross-component conflict detection
- Update exclusion (own GPIO allowed)
- Available GPIO passes
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.services.gpio_validation_service import (
    GpioValidationService,
    GpioValidationResult,
    GpioConflictType,
    SYSTEM_RESERVED_PINS,
    ADC1_SAFE_PINS,
    ADC2_WIFI_CONFLICT_PINS,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_sensor_repo():
    """Create a mock sensor repository."""
    repo = AsyncMock()
    repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
    repo.get_by_esp = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_actuator_repo():
    """Create a mock actuator repository."""
    repo = AsyncMock()
    repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
    repo.get_by_esp = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_esp_repo():
    """Create a mock ESP repository."""
    repo = AsyncMock()
    mock_device = MagicMock()
    mock_device.device_metadata = None
    repo.get_by_id = AsyncMock(return_value=mock_device)
    return repo


@pytest.fixture
def gpio_service(mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo):
    """Create a GpioValidationService with mock dependencies."""
    return GpioValidationService(
        session=mock_session,
        sensor_repo=mock_sensor_repo,
        actuator_repo=mock_actuator_repo,
        esp_repo=mock_esp_repo,
    )


# =============================================================================
# System Pin Tests
# =============================================================================


class TestSystemPinRejection:
    """Tests for system-reserved GPIO pins."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("gpio", list(SYSTEM_RESERVED_PINS))
    async def test_system_pins_rejected(self, gpio_service, gpio):
        """System-Pins (0,1,2,3,6-11) müssen abgelehnt werden."""
        esp_id = uuid.uuid4()

        result = await gpio_service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert result.conflict_component is not None
        assert "System-Pin" in result.message

    @pytest.mark.asyncio
    async def test_non_system_pins_not_rejected_by_default(self, gpio_service):
        """Non-system GPIOs sollten verfügbar sein (ohne andere Konflikte).

        Note: GPIO 21/22 sind jetzt durch Fix #3 (I2C Pin Protection) für I2C reserviert
        und werden für ANALOG-Sensoren abgelehnt. Daher sind sie hier nicht mehr in der Liste.
        """
        esp_id = uuid.uuid4()
        # GPIO 21/22 entfernt (I2C Pin Protection), GPIO 12 entfernt (MTDI Strapping)
        non_system_gpios = [4, 5, 13, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27, 32, 33]

        for gpio in non_system_gpios:
            result = await gpio_service.validate_gpio_available(esp_id, gpio)
            assert result.available, f"GPIO {gpio} should be available"


# =============================================================================
# Sensor Conflict Tests
# =============================================================================


class TestSensorConflictDetection:
    """Tests for sensor GPIO conflict detection."""

    @pytest.mark.asyncio
    async def test_sensor_conflict_detected(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Sensor auf belegtem GPIO wird erkannt."""
        esp_id = uuid.uuid4()
        gpio = 4

        # Mock: Sensor existiert auf GPIO 4
        mock_sensor = MagicMock()
        mock_sensor.id = uuid.uuid4()
        mock_sensor.sensor_type = "DS18B20"
        mock_sensor.sensor_name = "Temperature Sensor"
        mock_sensor_repo.get_by_esp_and_gpio.return_value = mock_sensor

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        result = await service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.SENSOR
        assert result.conflict_component == "DS18B20"
        assert result.conflict_id == mock_sensor.id
        assert "Sensor" in result.message

    @pytest.mark.asyncio
    async def test_sensor_update_own_gpio_allowed(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Update auf eigenem GPIO erlaubt (exclude_sensor_id)."""
        esp_id = uuid.uuid4()
        gpio = 4
        sensor_id = uuid.uuid4()

        # Mock: Sensor existiert auf GPIO 4 mit der gleichen ID
        mock_sensor = MagicMock()
        mock_sensor.id = sensor_id
        mock_sensor.sensor_type = "DS18B20"
        mock_sensor.sensor_name = "Temperature Sensor"
        mock_sensor_repo.get_by_esp_and_gpio.return_value = mock_sensor

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # Mit exclude_sensor_id sollte der eigene Sensor ignoriert werden
        result = await service.validate_gpio_available(esp_id, gpio, exclude_sensor_id=sensor_id)

        assert result.available, "Own sensor GPIO should be available for update"


# =============================================================================
# Actuator Conflict Tests
# =============================================================================


class TestActuatorConflictDetection:
    """Tests for actuator GPIO conflict detection."""

    @pytest.mark.asyncio
    async def test_actuator_conflict_detected(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Actuator auf belegtem GPIO wird erkannt."""
        esp_id = uuid.uuid4()
        gpio = 5

        # Mock: Actuator existiert auf GPIO 5
        mock_actuator = MagicMock()
        mock_actuator.id = uuid.uuid4()
        mock_actuator.actuator_type = "pump"
        mock_actuator.actuator_name = "Water Pump"
        mock_actuator_repo.get_by_esp_and_gpio.return_value = mock_actuator

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        result = await service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.ACTUATOR
        assert result.conflict_component == "pump"
        assert result.conflict_id == mock_actuator.id
        assert "Actuator" in result.message

    @pytest.mark.asyncio
    async def test_actuator_update_own_gpio_allowed(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Update auf eigenem GPIO erlaubt (exclude_actuator_id)."""
        esp_id = uuid.uuid4()
        gpio = 5
        actuator_id = uuid.uuid4()

        # Mock: Actuator existiert auf GPIO 5 mit der gleichen ID
        mock_actuator = MagicMock()
        mock_actuator.id = actuator_id
        mock_actuator.actuator_type = "pump"
        mock_actuator.actuator_name = "Water Pump"
        mock_actuator_repo.get_by_esp_and_gpio.return_value = mock_actuator

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # Mit exclude_actuator_id sollte der eigene Actuator ignoriert werden
        result = await service.validate_gpio_available(
            esp_id, gpio, exclude_actuator_id=actuator_id
        )

        assert result.available, "Own actuator GPIO should be available for update"


# =============================================================================
# Cross-Component Conflict Tests
# =============================================================================


class TestCrossComponentConflict:
    """Tests for cross-component (sensor/actuator) GPIO conflict detection."""

    @pytest.mark.asyncio
    async def test_sensor_on_actuator_gpio_rejected(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Sensor auf Actuator-GPIO wird erkannt."""
        esp_id = uuid.uuid4()
        gpio = 5

        # Mock: Kein Sensor, aber Actuator auf GPIO 5
        mock_sensor_repo.get_by_esp_and_gpio.return_value = None

        mock_actuator = MagicMock()
        mock_actuator.id = uuid.uuid4()
        mock_actuator.actuator_type = "pump"
        mock_actuator.actuator_name = "Water Pump"
        mock_actuator_repo.get_by_esp_and_gpio.return_value = mock_actuator

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        result = await service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.ACTUATOR
        assert "Actuator" in result.message

    @pytest.mark.asyncio
    async def test_actuator_on_sensor_gpio_rejected(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Actuator auf Sensor-GPIO wird erkannt."""
        esp_id = uuid.uuid4()
        gpio = 4

        # Mock: Sensor auf GPIO 4, kein Actuator
        mock_sensor = MagicMock()
        mock_sensor.id = uuid.uuid4()
        mock_sensor.sensor_type = "DS18B20"
        mock_sensor.sensor_name = "Temperature Sensor"
        mock_sensor_repo.get_by_esp_and_gpio.return_value = mock_sensor

        mock_actuator_repo.get_by_esp_and_gpio.return_value = None

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        result = await service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.SENSOR
        assert "Sensor" in result.message


# =============================================================================
# Available GPIO Tests
# =============================================================================


class TestAvailableGpio:
    """Tests for available GPIO detection."""

    @pytest.mark.asyncio
    async def test_available_gpio_passes(self, gpio_service):
        """Freier GPIO ist verfügbar."""
        esp_id = uuid.uuid4()
        gpio = 33  # Ein freier GPIO

        result = await gpio_service.validate_gpio_available(esp_id, gpio)

        assert result.available
        assert result.conflict_type is None
        assert result.message is None


# =============================================================================
# ESP-Reported Status Tests
# =============================================================================


class TestEspReportedStatus:
    """Tests for ESP-reported GPIO status (Phase 1 integration)."""

    @pytest.mark.asyncio
    async def test_esp_reported_system_pin_rejected(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """ESP-gemeldeter System-Pin wird erkannt.

        Note: Verwende GPIO 15 (nicht 21), da GPIO 21 jetzt durch Fix #3 (I2C Pin Protection)
        bereits VOR der ESP-Status-Prüfung abgelehnt wird.

        Dieser Test simuliert: ESP meldet GPIO 15 als "system" (z.B. weil der ESP
        diesen Pin intern für etwas verwendet). Der Server sollte diese Meldung
        respektieren und den GPIO ablehnen.
        """
        esp_id = uuid.uuid4()
        gpio = 15  # Ein normaler GPIO, der vom ESP als "system" gemeldet wird

        # Mock: ESP meldet GPIO 15 als system (z.B. für externe Peripherie)
        mock_device = MagicMock()
        mock_device.hardware_type = "ESP32_WROOM"  # Wichtig für Board-Constraints!
        mock_device.device_metadata = {
            "gpio_status": [
                {
                    "gpio": 15,
                    "owner": "system",
                    "component": "EXTERNAL_PERIPHERAL",
                    "mode": 1,
                    "safe": False,
                }
            ]
        }
        mock_esp_repo.get_by_id.return_value = mock_device

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        result = await service.validate_gpio_available(esp_id, gpio)

        assert not result.available
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert result.esp_reported_owner == "system"
        assert "ESP" in result.message or "System-Pin" in result.message


# =============================================================================
# get_all_used_gpios Tests
# =============================================================================


class TestGetAllUsedGpios:
    """Tests for get_all_used_gpios method."""

    @pytest.mark.asyncio
    async def test_combines_sensors_actuators_and_system(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Kombiniert Sensoren, Aktoren und System-Pins."""
        esp_id = uuid.uuid4()

        # Mock: 1 Sensor, 1 Actuator
        mock_sensor = MagicMock()
        mock_sensor.gpio = 4
        mock_sensor.sensor_type = "DS18B20"
        mock_sensor.sensor_name = "Temp1"
        mock_sensor.id = uuid.uuid4()
        mock_sensor_repo.get_by_esp.return_value = [mock_sensor]

        mock_actuator = MagicMock()
        mock_actuator.gpio = 5
        mock_actuator.actuator_type = "pump"
        mock_actuator.actuator_name = "Pump1"
        mock_actuator.id = uuid.uuid4()
        mock_actuator_repo.get_by_esp.return_value = [mock_actuator]

        # Mock: ESP device without GPIO status
        mock_device = MagicMock()
        mock_device.device_metadata = None
        mock_esp_repo.get_by_id.return_value = mock_device

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        used_gpios = await service.get_all_used_gpios(esp_id)

        # Should have: 1 sensor + 1 actuator + 10 system pins = 12 entries
        gpio_numbers = [g["gpio"] for g in used_gpios]

        # Sensor and actuator should be present
        assert 4 in gpio_numbers, "Sensor GPIO should be in list"
        assert 5 in gpio_numbers, "Actuator GPIO should be in list"

        # System pins should be present
        for system_pin in SYSTEM_RESERVED_PINS:
            assert system_pin in gpio_numbers, f"System pin {system_pin} should be in list"

    @pytest.mark.asyncio
    async def test_sorted_by_gpio_number(
        self, mock_session, mock_sensor_repo, mock_actuator_repo, mock_esp_repo
    ):
        """Ergebnis ist nach GPIO-Nummer sortiert."""
        esp_id = uuid.uuid4()

        # Mock: 2 Sensors on non-sequential GPIOs
        mock_sensor1 = MagicMock()
        mock_sensor1.gpio = 33
        mock_sensor1.sensor_type = "DS18B20"
        mock_sensor1.sensor_name = "Temp1"
        mock_sensor1.id = uuid.uuid4()

        mock_sensor2 = MagicMock()
        mock_sensor2.gpio = 15
        mock_sensor2.sensor_type = "SHT31"
        mock_sensor2.sensor_name = "Humidity"
        mock_sensor2.id = uuid.uuid4()

        mock_sensor_repo.get_by_esp.return_value = [mock_sensor1, mock_sensor2]
        mock_actuator_repo.get_by_esp.return_value = []

        # Mock: ESP device without GPIO status
        mock_device = MagicMock()
        mock_device.device_metadata = None
        mock_esp_repo.get_by_id.return_value = mock_device

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        used_gpios = await service.get_all_used_gpios(esp_id)

        gpio_numbers = [g["gpio"] for g in used_gpios]
        assert gpio_numbers == sorted(gpio_numbers), "GPIOs should be sorted"


# ==================== Hardware Validation: Input-Only Pin Protection (Fix #2) ====================


@pytest.mark.asyncio
class TestInputOnlyPinProtection:
    """Tests for input-only pin protection (GPIO 34-39 on ESP32-WROOM).

    ESP32-WROOM has pins 34-39 that are input-only (no OUTPUT mode).
    Actuators require OUTPUT → must be rejected on these pins.
    Sensors only need INPUT → are allowed on these pins.
    """

    async def test_actuator_on_input_only_pin_34_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: Actuator on GPIO 34 (input-only) rejected."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=34,
            purpose="actuator",  # ← CRITICAL: Actuators need OUTPUT!
            interface_type="DIGITAL",
        )

        assert not result.available, "GPIO 34 should be rejected for actuator"
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "input-only" in result.message.lower()
        assert "34" in result.message

    async def test_actuator_on_all_input_only_pins_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: Actuators on all input-only pins (34-39) rejected."""
        input_only_pins = [34, 35, 36, 39]  # ESP32-WROOM input-only pins

        for gpio in input_only_pins:
            result = await gpio_service.validate_gpio_available(
                esp_db_id=sample_esp_device.id,
                gpio=gpio,
                purpose="actuator",
                interface_type="DIGITAL",
            )

            assert not result.available, f"GPIO {gpio} should be rejected for actuator"
            assert result.conflict_type == GpioConflictType.SYSTEM
            assert "input-only" in result.message.lower()

    async def test_sensor_on_input_only_pin_34_accepted(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: Sensor on GPIO 34 (input-only) accepted."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=34,
            purpose="sensor",  # ← Sensors only need INPUT, OK!
            interface_type="ANALOG",
        )

        assert result.available, "GPIO 34 should be accepted for sensor"
        assert result.conflict_type is None
        if result.message is not None:
            assert "available" in result.message.lower()

    async def test_actuator_on_normal_pin_32_accepted(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: Actuator on GPIO 32 (normal pin) accepted."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=32,
            purpose="actuator",
            interface_type="DIGITAL",
        )

        assert result.available, "GPIO 32 should be accepted for actuator"
        assert result.conflict_type is None


# ==================== Hardware Validation: I2C Pin Protection (Fix #3) ====================


@pytest.mark.asyncio
class TestI2CPinProtection:
    """Tests for I2C bus pin protection (GPIO 21/22 on ESP32-WROOM).

    ESP32-WROOM uses GPIO 21 (SDA) and 22 (SCL) for I2C communication.
    These pins are auto-reserved by system and should NOT be used for
    ANALOG/DIGITAL sensors or actuators.
    """

    async def test_analog_sensor_on_i2c_sda_pin_21_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: ANALOG sensor on GPIO 21 (I2C SDA) rejected."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=21,
            purpose="sensor",
            interface_type="ANALOG",  # ← NOT I2C!
        )

        assert not result.available, "GPIO 21 should be rejected for ANALOG"
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "i2c" in result.message.lower()
        assert "21" in result.message

    async def test_analog_sensor_on_i2c_scl_pin_22_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: ANALOG sensor on GPIO 22 (I2C SCL) rejected."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=22,
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert not result.available, "GPIO 22 should be rejected for ANALOG"
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "i2c" in result.message.lower()
        assert "22" in result.message

    async def test_digital_actuator_on_i2c_pin_21_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: DIGITAL actuator on GPIO 21 (I2C SDA) rejected."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=21,
            purpose="actuator",
            interface_type="DIGITAL",
        )

        assert not result.available, "GPIO 21 should be rejected for DIGITAL"
        assert "i2c" in result.message.lower()

    async def test_analog_sensor_on_normal_pin_32_accepted(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: ANALOG sensor on GPIO 32 (normal pin) accepted."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=32,
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert result.available, "GPIO 32 should be accepted for ANALOG"
        assert result.conflict_type is None


# ==================== MTDI Strapping Pin Protection (GPIO 12) ====================


class TestGpio12StrappingPin:
    """Tests for GPIO 12 (MTDI strapping pin) rejection.

    GPIO 12 controls flash voltage on ESP32-WROOM. If pulled HIGH during boot,
    the board may fail to boot or corrupt flash. Must be blocked.
    """

    @pytest.mark.asyncio
    async def test_gpio_12_rejected_as_system_pin(self, gpio_service):
        """GPIO 12 must be rejected — MTDI strapping pin."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 12)

        assert not result.available
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "12" in result.message

    @pytest.mark.asyncio
    async def test_gpio_12_in_system_reserved_set(self):
        """GPIO 12 must be in SYSTEM_RESERVED_PINS."""
        assert 12 in SYSTEM_RESERVED_PINS


# ==================== ADC2 WiFi Conflict Warning ====================


class TestADC2WiFiWarning:
    """Tests for ADC2 pin warning when used for ANALOG sensors.

    ADC2 pins (0,2,4,12,13,14,15,25,26,27) do not work with analogRead()
    when WiFi is active. ADC1 pins (32,33,34,35,36,39) are safe.
    """

    @pytest.mark.asyncio
    async def test_adc2_pin_4_warns_for_analog_sensor(self, gpio_service):
        """ADC2 pin 4 should produce warning for ANALOG sensor."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 4, interface_type="ANALOG")

        assert result.available, "ADC2 pins are usable, just with warning"
        assert result.warning is not None
        assert "ADC2" in result.warning
        assert "WiFi" in result.warning

    @pytest.mark.asyncio
    async def test_adc2_pin_25_warns_for_analog_sensor(self, gpio_service):
        """ADC2 pin 25 should produce warning for ANALOG sensor."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 25, interface_type="ANALOG")

        assert result.available
        assert result.warning is not None
        assert "ADC2" in result.warning

    @pytest.mark.asyncio
    async def test_adc1_pin_32_no_warning_for_analog_sensor(self, gpio_service):
        """ADC1 pin 32 should NOT produce warning for ANALOG sensor."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 32, interface_type="ANALOG")

        assert result.available
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_adc1_pin_34_no_warning_for_analog_sensor(self, gpio_service):
        """ADC1 pin 34 — safe for analog sensors, no warning."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 34, interface_type="ANALOG")

        assert result.available
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_no_warning_for_digital_sensor_on_adc2(self, gpio_service):
        """DIGITAL sensor on ADC2 pin should NOT produce ADC warning."""
        esp_id = uuid.uuid4()
        result = await gpio_service.validate_gpio_available(esp_id, 4, interface_type="DIGITAL")

        assert result.available
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_adc_constants_disjoint(self):
        """ADC1 and ADC2 pin sets must not overlap."""
        assert ADC1_SAFE_PINS.isdisjoint(ADC2_WIFI_CONFLICT_PINS)
