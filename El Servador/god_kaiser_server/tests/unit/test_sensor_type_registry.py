"""
Unit tests for sensor type registry.

Tests sensor type normalization, multi-value sensor definitions,
and I2C address lookups.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.sensors.sensor_type_registry import (
    MULTI_VALUE_SENSORS,
    SENSOR_TYPE_MAPPING,
    VIRTUAL_SENSOR_TYPES,
    normalize_sensor_type,
    get_multi_value_sensor_def,
    is_multi_value_sensor,
    get_device_type_from_sensor_type,
    get_all_value_types_for_device,
    get_i2c_address,
)


class TestSensorTypeNormalization:
    """Test sensor type normalization (ESP32 -> Server Processor)."""

    def test_normalize_sht31_temperature(self):
        """Test normalization of SHT31 temperature sensor type."""
        assert normalize_sensor_type("temperature_sht31") == "sht31_temp"

    def test_normalize_sht31_humidity(self):
        """Test normalization of SHT31 humidity sensor type."""
        assert normalize_sensor_type("humidity_sht31") == "sht31_humidity"

    def test_normalize_ds18b20(self):
        """Test normalization of DS18B20 sensor type."""
        assert normalize_sensor_type("temperature_ds18b20") == "ds18b20"

    def test_normalize_already_normalized(self):
        """Test that already normalized types remain unchanged."""
        assert normalize_sensor_type("sht31_temp") == "sht31_temp"
        assert normalize_sensor_type("ph") == "ph"

    def test_normalize_case_insensitive(self):
        """Test that normalization is case-insensitive."""
        assert normalize_sensor_type("TEMPERATURE_SHT31") == "sht31_temp"
        assert normalize_sensor_type("Temperature_Sht31") == "sht31_temp"

    def test_normalize_unknown_type(self):
        """Test that unknown types return lowercase version."""
        assert normalize_sensor_type("unknown_sensor") == "unknown_sensor"
        assert normalize_sensor_type("") == ""


class TestMultiValueSensorDefinitions:
    """Test multi-value sensor definitions."""

    def test_get_sht31_definition(self):
        """Test getting SHT31 multi-value sensor definition."""
        def_ = get_multi_value_sensor_def("sht31")
        assert def_ is not None
        assert def_["device_type"] == "i2c"
        assert def_["device_address"] == 0x44
        assert len(def_["values"]) == 2

    def test_get_bmp280_definition(self):
        """Test getting BMP280 multi-value sensor definition."""
        def_ = get_multi_value_sensor_def("bmp280")
        assert def_ is not None
        assert def_["device_type"] == "i2c"
        assert def_["device_address"] == 0x76
        assert len(def_["values"]) == 2

    def test_get_nonexistent_sensor(self):
        """Test getting definition for non-existent sensor."""
        assert get_multi_value_sensor_def("nonexistent") is None

    def test_is_multi_value_sht31(self):
        """Test that SHT31 is identified as multi-value sensor."""
        assert is_multi_value_sensor("sht31") is True

    def test_is_multi_value_bmp280(self):
        """Test that BMP280 is identified as multi-value sensor."""
        assert is_multi_value_sensor("bmp280") is True

    def test_is_multi_value_single_value(self):
        """Test that single-value sensors return False."""
        assert is_multi_value_sensor("ds18b20") is False
        assert is_multi_value_sensor("ph") is False

    def test_sht31_value_types(self):
        """Test SHT31 value type definitions."""
        def_ = get_multi_value_sensor_def("sht31")
        value_types = [v["sensor_type"] for v in def_["values"]]
        assert "sht31_temp" in value_types
        assert "sht31_humidity" in value_types

    def test_sht31_value_names(self):
        """Test SHT31 value names."""
        def_ = get_multi_value_sensor_def("sht31")
        value_names = [v["name"] for v in def_["values"]]
        assert "Temperature" in value_names
        assert "Humidity" in value_names

    def test_sht31_value_units(self):
        """Test SHT31 value units."""
        def_ = get_multi_value_sensor_def("sht31")
        value_units = [v["unit"] for v in def_["values"]]
        assert "°C" in value_units
        assert "%RH" in value_units


class TestDeviceTypeExtraction:
    """Test device type extraction from sensor types."""

    def test_get_device_type_from_sht31_temp(self):
        device_type = get_device_type_from_sensor_type("sht31_temp")
        assert device_type == "sht31"

    def test_get_device_type_from_sht31_humidity(self):
        device_type = get_device_type_from_sensor_type("sht31_humidity")
        assert device_type == "sht31"

    def test_get_device_type_from_single_value(self):
        assert get_device_type_from_sensor_type("ds18b20") is None
        assert get_device_type_from_sensor_type("ph") is None

    def test_get_device_type_from_normalized_type(self):
        device_type = get_device_type_from_sensor_type("temperature_sht31")
        assert device_type == "sht31"


class TestValueTypeLists:
    """Test getting all value types for a device."""

    def test_get_all_value_types_sht31(self):
        value_types = get_all_value_types_for_device("sht31")
        assert len(value_types) == 2
        assert "sht31_temp" in value_types
        assert "sht31_humidity" in value_types

    def test_get_all_value_types_bmp280(self):
        value_types = get_all_value_types_for_device("bmp280")
        assert len(value_types) == 2
        assert "bmp280_pressure" in value_types
        assert "bmp280_temp" in value_types

    def test_get_all_value_types_single_value(self):
        assert get_all_value_types_for_device("ds18b20") == []
        assert get_all_value_types_for_device("ph") == []


class TestI2CAddressLookup:
    """Test I2C address lookups."""

    def test_get_i2c_address_sht31(self):
        address = get_i2c_address("sht31")
        assert address == 0x44

    def test_get_i2c_address_bmp280(self):
        address = get_i2c_address("bmp280")
        assert address == 0x76

    def test_get_i2c_address_non_i2c(self):
        address = get_i2c_address("ds18b20", default_address=0x00)
        assert address == 0x00

    def test_get_i2c_address_unknown(self):
        address = get_i2c_address("unknown", default_address=0x48)
        assert address == 0x48


# ==================== Hardware Validation: I2C Address Range (Fix #1) ====================


@pytest.mark.asyncio
class TestI2CAddressRangeValidation:
    """Tests for I2C address range validation (Fix #1)."""

    async def test_i2c_negative_address_rejected(
        self,
        db_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Test: Negative I2C address rejected."""
        from src.api.v1.sensors import _validate_i2c_config
        from src.db.repositories.sensor_repo import SensorRepository
        from src.core.exceptions import ValidationException

        sensor_repo = SensorRepository(db_session)

        with pytest.raises(ValidationException) as exc_info:
            await _validate_i2c_config(
                sensor_repo=sensor_repo,
                esp_id=sample_esp_device.id,
                i2c_address=-1,
                exclude_sensor_id=None,
            )

        assert exc_info.value.status_code == 400
        assert "positive" in exc_info.value.message.lower()

    async def test_i2c_out_of_7bit_range_rejected(
        self,
        db_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Test: I2C address > 0x7F rejected (out of 7-bit range)."""
        from src.api.v1.sensors import _validate_i2c_config
        from src.db.repositories.sensor_repo import SensorRepository
        from src.core.exceptions import ValidationException

        sensor_repo = SensorRepository(db_session)

        with pytest.raises(ValidationException) as exc_info:
            await _validate_i2c_config(
                sensor_repo=sensor_repo,
                esp_id=sample_esp_device.id,
                i2c_address=255,
                exclude_sensor_id=None,
            )

        assert exc_info.value.status_code == 400
        assert "0x08-0x77" in exc_info.value.message or "7-bit range" in exc_info.value.message

    async def test_i2c_reserved_low_address_rejected(
        self,
        db_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Test: Reserved I2C address 0x00-0x07 rejected."""
        from src.api.v1.sensors import _validate_i2c_config
        from src.db.repositories.sensor_repo import SensorRepository
        from src.core.exceptions import ValidationException

        sensor_repo = SensorRepository(db_session)

        reserved_addresses = [0x00, 0x01, 0x05, 0x07]

        for addr in reserved_addresses:
            with pytest.raises(ValidationException) as exc_info:
                await _validate_i2c_config(
                    sensor_repo=sensor_repo,
                    esp_id=sample_esp_device.id,
                    i2c_address=addr,
                    exclude_sensor_id=None,
                )

            assert exc_info.value.status_code == 400
            message = exc_info.value.message.lower()
            if addr == 0x00:
                assert "required" in message
            else:
                assert "reserved" in message

    async def test_i2c_reserved_high_address_rejected(
        self,
        db_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Test: Reserved I2C address 0x78-0x7F rejected."""
        from src.api.v1.sensors import _validate_i2c_config
        from src.db.repositories.sensor_repo import SensorRepository
        from src.core.exceptions import ValidationException

        sensor_repo = SensorRepository(db_session)

        reserved_addresses = [0x78, 0x7A, 0x7D, 0x7F]

        for addr in reserved_addresses:
            with pytest.raises(ValidationException) as exc_info:
                await _validate_i2c_config(
                    sensor_repo=sensor_repo,
                    esp_id=sample_esp_device.id,
                    i2c_address=addr,
                    exclude_sensor_id=None,
                )

            assert exc_info.value.status_code == 400
            assert "reserved" in exc_info.value.message.lower()

    async def test_i2c_valid_address_accepted(
        self,
        db_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Test: Valid I2C address 0x08-0x77 accepted."""
        from src.api.v1.sensors import _validate_i2c_config
        from src.db.repositories.sensor_repo import SensorRepository

        sensor_repo = SensorRepository(db_session)

        valid_addresses = [0x08, 0x44, 0x76, 0x77]

        for addr in valid_addresses:
            await _validate_i2c_config(
                sensor_repo=sensor_repo,
                esp_id=sample_esp_device.id,
                i2c_address=addr,
                exclude_sensor_id=None,
            )


# ==================== AUT-229 F2: Registry-Updates ====================
#
# Tests for registry changes added in AUT-226:
# - vpd in SENSOR_TYPE_MAPPING (registry hit, not passthrough)
# - BME280 multi-value sensor + 3 sub-types (bme280_temp, bme280_pressure,
#   bme280_humidity) -- needed because LibraryLoader looks up processors
#   via normalize_sensor_type() and we want a hit, not raw passthrough.
# - VIRTUAL_SENSOR_TYPES membership for "vpd" (AUT-227 retained it).


class TestVPDRegistryEntry:
    """AUT-229 F2: VPD virtual sensor must be a registry hit (not passthrough)."""

    def test_normalize_vpd_is_registry_hit(self):
        """normalize_sensor_type('vpd') returns 'vpd' from SENSOR_TYPE_MAPPING.

        This guards against accidental passthrough behaviour: vpd MUST be
        listed explicitly in SENSOR_TYPE_MAPPING so downstream consumers
        (LibraryLoader, sensor_handler.py) treat it as a known type.
        """
        assert "vpd" in SENSOR_TYPE_MAPPING
        assert SENSOR_TYPE_MAPPING["vpd"] == "vpd"
        assert normalize_sensor_type("vpd") == "vpd"

    def test_normalize_vpd_case_insensitive(self):
        """normalize_sensor_type is case-insensitive for vpd."""
        assert normalize_sensor_type("VPD") == "vpd"
        assert normalize_sensor_type("Vpd") == "vpd"

    def test_vpd_in_virtual_sensor_types(self):
        """VPD must be flagged as virtual (event-driven, not scheduled)."""
        assert "vpd" in VIRTUAL_SENSOR_TYPES

    def test_vpd_is_not_multi_value_sensor(self):
        """VPD is computed (single value), not a multi-value device."""
        assert is_multi_value_sensor("vpd") is False
        assert get_multi_value_sensor_def("vpd") is None


class TestBME280Registry:
    """AUT-229 F2: BME280 (3 processor types from AUT-226 commit 7a5a3eb)."""

    def test_bme280_in_multi_value_sensors(self):
        """BME280 is registered as a multi-value sensor."""
        assert "bme280" in MULTI_VALUE_SENSORS

    def test_bme280_definition_structure(self):
        """BME280 multi-value definition has the expected i2c structure."""
        def_ = get_multi_value_sensor_def("bme280")
        assert def_ is not None
        assert def_["device_type"] == "i2c"
        assert def_["device_address"] == 0x76
        assert len(def_["values"]) == 3

    def test_bme280_value_types(self):
        """All three BME280 sub-types must be present (matches new processors
        in src/sensors/sensor_libraries/active/bme280.py)."""
        types = [v["sensor_type"] for v in get_multi_value_sensor_def("bme280")["values"]]
        assert "bme280_temp" in types
        assert "bme280_pressure" in types
        assert "bme280_humidity" in types

    def test_bme280_get_all_value_types_for_device(self):
        types = set(get_all_value_types_for_device("bme280"))
        assert types == {"bme280_temp", "bme280_pressure", "bme280_humidity"}

    @pytest.mark.parametrize(
        "esp_type,normalized",
        [
            ("temperature_bme280", "bme280_temp"),
            ("pressure_bme280", "bme280_pressure"),
            ("humidity_bme280", "bme280_humidity"),
            ("bme280_temp", "bme280_temp"),
            ("bme280_pressure", "bme280_pressure"),
            ("bme280_humidity", "bme280_humidity"),
        ],
    )
    def test_bme280_normalize_mapping(self, esp_type, normalized):
        """SENSOR_TYPE_MAPPING covers all ESP32 -> normalized BME280 variants."""
        assert normalize_sensor_type(esp_type) == normalized

    def test_bme280_get_device_type_from_sub_type(self):
        """get_device_type_from_sensor_type identifies bme280 as parent."""
        assert get_device_type_from_sensor_type("bme280_temp") == "bme280"
        assert get_device_type_from_sensor_type("bme280_pressure") == "bme280"
        assert get_device_type_from_sensor_type("bme280_humidity") == "bme280"

    def test_bme280_i2c_address(self):
        assert get_i2c_address("bme280") == 0x76


class TestRegistryConsistency:
    """AUT-229 F2: Registry-wide invariants after AUT-226 cleanup."""

    def test_all_multi_value_sub_types_in_mapping(self):
        """Every value.sensor_type from MULTI_VALUE_SENSORS must be in
        SENSOR_TYPE_MAPPING (so normalize_sensor_type() always hits)."""
        for device_type, definition in MULTI_VALUE_SENSORS.items():
            for value_def in definition["values"]:
                sub_type = value_def["sensor_type"]
                assert sub_type in SENSOR_TYPE_MAPPING, (
                    f"{device_type} sub-type '{sub_type}' missing from "
                    f"SENSOR_TYPE_MAPPING"
                )

    def test_virtual_sensor_types_is_set(self):
        """VIRTUAL_SENSOR_TYPES is a set (membership-test friendly)."""
        assert isinstance(VIRTUAL_SENSOR_TYPES, set)
