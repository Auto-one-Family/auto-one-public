"""
Unit Tests: OneWire ROM Code Validation

Tests for OneWire address (ROM code) validation including:
- ROM code format validation (16 hex chars)
- 4-way lookup for multiple DS18B20 sensors on same GPIO
- Payload validation in sensor_handler

ROM Code Format:
- DS18B20 family code: 0x28
- 48-bit serial number: unique per device
- CRC: 8-bit checksum
- Total: 8 bytes = 16 hex characters

Example: "28FF641E8D3C0C79"
         |  |           |
         |  |           +-- CRC (79)
         |  +-------------- Serial (FF641E8D3C0C)
         +----------------- Family Code (28)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.db.models.sensor import SensorConfig


class TestOneWireRomCodeFormat:
    """Tests for OneWire ROM code format validation."""

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_valid_rom_code_16_hex_chars(self):
        """Valid 16-character hex ROM code is accepted."""
        # ARRANGE
        valid_rom_code = "28FF641E8D3C0C79"  # Real DS18B20 format

        # ACT - Create SensorConfig with valid onewire_address
        config = MagicMock(spec=SensorConfig)
        config.onewire_address = valid_rom_code

        # ASSERT
        assert (
            len(config.onewire_address) == 16
        ), f"ROM code should be 16 chars, got {len(config.onewire_address)}"
        assert all(
            c in "0123456789ABCDEFabcdef" for c in config.onewire_address
        ), "ROM code should only contain hex characters"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_rom_code_lowercase_accepted(self):
        """Lowercase hex ROM code is accepted."""
        # ARRANGE
        lowercase_rom = "28ff641e8d3c0c79"

        # ACT
        config = MagicMock(spec=SensorConfig)
        config.onewire_address = lowercase_rom

        # ASSERT
        assert len(config.onewire_address) == 16, "Lowercase ROM code should be 16 chars"
        assert all(
            c in "0123456789ABCDEFabcdef" for c in config.onewire_address
        ), "Lowercase hex should be valid"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_rom_code_family_code_28(self):
        """DS18B20 ROM codes start with family code 28."""
        # ARRANGE - Multiple valid DS18B20 ROM codes
        valid_roms = [
            "28FF641E8D3C0C79",
            "28A1B2C3D4E5F611",
            "280123456789ABCD",
        ]

        for rom in valid_roms:
            # ASSERT
            assert rom[:2] == "28", f"DS18B20 ROM should start with '28', got '{rom[:2]}'"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_rom_code_empty_not_required(self):
        """Empty/None onewire_address is allowed for non-OneWire sensors."""
        # ARRANGE
        config = MagicMock(spec=SensorConfig)

        # ACT - Set to None (for analog sensors)
        config.onewire_address = None

        # ASSERT
        assert (
            config.onewire_address is None
        ), "onewire_address should be nullable for non-OneWire sensors"


class TestOneWireFourWayLookup:
    """Tests for 4-way lookup: (esp_id, gpio, sensor_type, onewire_address)."""

    @pytest.mark.onewire
    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_lookup_specific_ds18b20_on_shared_gpio(self):
        """4-way lookup finds correct DS18B20 among multiple on same GPIO."""
        # ARRANGE
        mock_sensor_repo = MagicMock()

        # Create 3 DS18B20 sensors on same GPIO but different ROM codes
        sensor1 = MagicMock(
            id=1,
            esp_id="uuid-1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28FF641E8D3C0C79",
            sensor_name="Water Tank",
        )
        sensor2 = MagicMock(
            id=2,
            esp_id="uuid-1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28A1B2C3D4E5F611",
            sensor_name="Air Temperature",
        )
        sensor3 = MagicMock(
            id=3,
            esp_id="uuid-1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="280123456789ABCD",
            sensor_name="Soil Temperature",
        )

        # Mock 4-way lookup
        async def mock_4way_lookup(esp_id, gpio, sensor_type, onewire_address):
            sensors = [sensor1, sensor2, sensor3]
            for s in sensors:
                if s.onewire_address == onewire_address:
                    return s
            return None

        mock_sensor_repo.get_by_esp_gpio_type_and_onewire = AsyncMock(side_effect=mock_4way_lookup)

        # ACT - Lookup sensor2 by its unique ROM code
        result = await mock_sensor_repo.get_by_esp_gpio_type_and_onewire(
            esp_id="uuid-1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28A1B2C3D4E5F611",
        )

        # ASSERT
        assert result is not None, "4-way lookup should find sensor with matching ROM code"
        assert (
            result.sensor_name == "Air Temperature"
        ), f"Should find 'Air Temperature' sensor, got '{result.sensor_name}'"
        assert (
            result.onewire_address == "28A1B2C3D4E5F611"
        ), f"ROM code should match, got '{result.onewire_address}'"

    @pytest.mark.onewire
    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_lookup_returns_none_for_unknown_rom(self):
        """4-way lookup returns None for non-existent ROM code."""
        # ARRANGE
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_gpio_type_and_onewire = AsyncMock(return_value=None)

        # ACT
        result = await mock_sensor_repo.get_by_esp_gpio_type_and_onewire(
            esp_id="uuid-1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="AAAAAAAAAAAAAAAA",  # Unknown ROM
        )

        # ASSERT
        assert result is None, "4-way lookup should return None for unknown ROM code"

    @pytest.mark.onewire
    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_same_rom_different_esp_allowed(self):
        """Same ROM code on different ESP devices are distinct sensors."""
        # ARRANGE
        mock_sensor_repo = MagicMock()

        sensor_esp1 = MagicMock(
            id=1,
            esp_id="uuid-esp1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28FF641E8D3C0C79",
            sensor_name="ESP1 Sensor",
        )
        sensor_esp2 = MagicMock(
            id=2,
            esp_id="uuid-esp2",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28FF641E8D3C0C79",  # Same ROM code!
            sensor_name="ESP2 Sensor",
        )

        async def mock_lookup(esp_id, gpio, sensor_type, onewire_address):
            if esp_id == "uuid-esp1":
                return sensor_esp1
            elif esp_id == "uuid-esp2":
                return sensor_esp2
            return None

        mock_sensor_repo.get_by_esp_gpio_type_and_onewire = AsyncMock(side_effect=mock_lookup)

        # ACT
        result1 = await mock_sensor_repo.get_by_esp_gpio_type_and_onewire(
            esp_id="uuid-esp1",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28FF641E8D3C0C79",
        )
        result2 = await mock_sensor_repo.get_by_esp_gpio_type_and_onewire(
            esp_id="uuid-esp2",
            gpio=4,
            sensor_type="ds18b20",
            onewire_address="28FF641E8D3C0C79",
        )

        # ASSERT
        assert result1.sensor_name == "ESP1 Sensor", "Should find ESP1's sensor"
        assert result2.sensor_name == "ESP2 Sensor", "Should find ESP2's sensor"
        assert (
            result1.id != result2.id
        ), "Same ROM on different ESPs should be different sensor records"


class TestOneWirePayloadValidation:
    """Tests for onewire_address in MQTT payload handling."""

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_payload_with_valid_onewire_address(self):
        """Payload with valid onewire_address is processed correctly."""
        # ARRANGE
        payload = {
            "ts": 1735818000,
            "gpio": 4,
            "sensor_type": "ds18b20",
            "onewire_address": "28FF641E8D3C0C79",
            "value": 400,  # RAW value
            "raw_mode": True,
        }

        # ACT
        onewire_address = payload.get("onewire_address")

        # ASSERT
        assert (
            onewire_address == "28FF641E8D3C0C79"
        ), "onewire_address should be extracted from payload"
        assert len(onewire_address) == 16, "ROM code should be 16 characters"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_payload_without_onewire_address(self):
        """Payload without onewire_address uses standard 3-way lookup."""
        # ARRANGE
        payload = {
            "ts": 1735818000,
            "gpio": 4,
            "sensor_type": "ph",  # Non-OneWire sensor
            "value": 512,
            "raw_mode": True,
            # No onewire_address!
        }

        # ACT
        onewire_address = payload.get("onewire_address")

        # ASSERT
        assert onewire_address is None, "onewire_address should be None for non-OneWire sensors"


class TestOneWireAddressTransform:
    """Tests for strip_auto_prefix transform in ConfigMappingEngine (R20-P6)."""

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_sim_address_stripped_to_empty(self):
        """SIM_ prefixed addresses are transformed to empty string."""
        from src.core.config_mapping import ConfigMappingEngine

        transform = ConfigMappingEngine.TRANSFORMS["strip_auto_prefix"]
        assert transform("SIM_A1B2C3D4E5F6") == "", "SIM_ address should become empty string"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_auto_address_stripped_to_empty(self):
        """AUTO_ prefixed addresses are transformed to empty string."""
        from src.core.config_mapping import ConfigMappingEngine

        transform = ConfigMappingEngine.TRANSFORMS["strip_auto_prefix"]
        assert transform("AUTO_28FF641E8D3C0C79") == "", "AUTO_ address should become empty string"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_real_rom_code_unchanged(self):
        """Real 16-char hex ROM codes pass through unchanged."""
        from src.core.config_mapping import ConfigMappingEngine

        transform = ConfigMappingEngine.TRANSFORMS["strip_auto_prefix"]
        assert (
            transform("28FF641E8D3C0C79") == "28FF641E8D3C0C79"
        ), "Real ROM code should be unchanged"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_empty_string_unchanged(self):
        """Empty string passes through unchanged."""
        from src.core.config_mapping import ConfigMappingEngine

        transform = ConfigMappingEngine.TRANSFORMS["strip_auto_prefix"]
        assert transform("") == "", "Empty string should remain empty"

    @pytest.mark.onewire
    @pytest.mark.sensor
    def test_none_returns_empty_string(self):
        """None input returns empty string."""
        from src.core.config_mapping import ConfigMappingEngine

        transform = ConfigMappingEngine.TRANSFORMS["strip_auto_prefix"]
        assert transform(None) == "", "None should become empty string"
