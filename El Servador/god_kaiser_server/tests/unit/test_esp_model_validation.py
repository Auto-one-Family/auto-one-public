"""
Tests for ESP-Model Awareness (Fix #4).

Tests hardware-specific validation for different ESP32 models:
- ESP32_WROOM: GPIO 0-39, Input-Only 34-39, I2C 21/22
- XIAO_ESP32_C3: GPIO 0-21, No Input-Only, I2C 4/5
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.services.gpio_validation_service import GpioValidationService, GpioConflictType

# ==================== ESP32-C3 Tests ====================


@pytest.mark.asyncio
class TestESP32C3Validation:
    """Tests for ESP32-C3 specific validation."""

    async def test_c3_gpio_out_of_range_34_rejected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_c3: ESPDevice,
    ):
        """Test: ESP32-C3 GPIO 34 rejected (out of range, max is 21)."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_c3.id,
            gpio=34,
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert not result.available, "GPIO 34 should be out of range for C3"
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "out of range" in result.message.lower()
        assert "21" in result.message  # Max GPIO for C3

    async def test_c3_i2c_pin_4_protected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_c3: ESPDevice,
    ):
        """Test: ESP32-C3 GPIO 4 (I2C SDA) protected for ANALOG."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_c3.id,
            gpio=4,  # ← I2C SDA on C3!
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert not result.available, "GPIO 4 should be protected (I2C) on C3"
        assert result.conflict_type == GpioConflictType.SYSTEM
        assert "i2c" in result.message.lower()

    async def test_c3_i2c_pin_5_protected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_c3: ESPDevice,
    ):
        """Test: ESP32-C3 GPIO 5 (I2C SCL) protected for ANALOG."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_c3.id,
            gpio=5,  # ← I2C SCL on C3!
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert not result.available, "GPIO 5 should be protected (I2C) on C3"
        assert "i2c" in result.message.lower()

    async def test_c3_no_input_only_restriction_on_gpio_12(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_c3: ESPDevice,
    ):
        """Test: ESP32-C3 has NO input-only pins (all bidirectional)."""
        # GPIO 12 is valid on C3, and NO input-only restriction
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_c3.id,
            gpio=12,
            purpose="actuator",  # ← Should work! C3 has no input-only pins
            interface_type="DIGITAL",
        )

        assert result.available, "GPIO 12 should be available for actuator on C3"
        assert result.conflict_type is None

    async def test_c3_gpio_21_accepted(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_c3: ESPDevice,
    ):
        """Test: ESP32-C3 GPIO 21 (NOT I2C on C3!) accepted for ANALOG."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_c3.id,
            gpio=21,  # ← NOT I2C on C3 (I2C is 4/5 on C3!)
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert result.available, "GPIO 21 should be available on C3 (not I2C)"
        assert result.conflict_type is None


# ==================== ESP32-WROOM Regression Tests ====================


@pytest.mark.asyncio
class TestESP32WROOMRegression:
    """Ensure WROOM validation still works after C3 changes."""

    async def test_wroom_gpio_21_still_protected_as_i2c(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,  # ← WROOM from conftest
    ):
        """Test: ESP32-WROOM GPIO 21 still protected as I2C."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=21,
            purpose="sensor",
            interface_type="ANALOG",
        )

        assert not result.available, "GPIO 21 should still be protected on WROOM"
        assert "i2c" in result.message.lower()

    async def test_wroom_input_only_pin_34_still_protected(
        self,
        db_session: AsyncSession,
        gpio_service: GpioValidationService,
        sample_esp_device: ESPDevice,
    ):
        """Test: ESP32-WROOM GPIO 34 still protected as input-only."""
        result = await gpio_service.validate_gpio_available(
            esp_db_id=sample_esp_device.id,
            gpio=34,
            purpose="actuator",
            interface_type="DIGITAL",
        )

        assert not result.available, "GPIO 34 should still be input-only on WROOM"
        assert "input-only" in result.message.lower()
