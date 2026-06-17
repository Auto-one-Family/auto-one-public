"""
UART CO₂ sensor config (AUT-527): interface inference, GPIO validation, config mapping.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.sensor_interface_inference import infer_interface_type, merge_uart_metadata
from src.core.config_mapping import ConfigMappingEngine, DEFAULT_SENSOR_MAPPINGS
from src.db.models.sensor import SensorConfig
from src.services.gpio_validation_service import GpioValidationService


class TestInferInterfaceTypeUart:
    def test_co2_infers_uart(self):
        assert infer_interface_type("co2") == "UART"

    def test_mhz19_co2_infers_uart(self):
        assert infer_interface_type("mhz19_co2") == "UART"

    def test_ph_regression_analog(self):
        assert infer_interface_type("ph") == "ANALOG"

    def test_sht31_regression_i2c(self):
        assert infer_interface_type("sht31_temp") == "I2C"


class TestInferInterfaceTypeDigital:
    def test_flow_infers_digital(self):
        assert infer_interface_type("flow") == "DIGITAL"

    def test_yfs201_infers_digital(self):
        assert infer_interface_type("yfs201") == "DIGITAL"

    def test_liquid_level_infers_digital(self):
        assert infer_interface_type("liquid_level") == "DIGITAL"

    def test_ph_regression_not_digital(self):
        assert infer_interface_type("ph") != "DIGITAL"

    def test_co2_regression_not_digital(self):
        assert infer_interface_type("co2") != "DIGITAL"


class TestUartMetadataMerge:
    def test_merge_defaults_sen0220_pins(self):
        meta: dict = {}
        merge_uart_metadata(
            meta,
            logical_gpio=18,
            uart_rx_pin=None,
            uart_tx_pin=None,
            uart_baud=None,
        )
        assert meta["uart_rx_pin"] == 18
        assert meta["uart_tx_pin"] == 17
        assert meta["uart_baud"] == 9600


class TestConfigMappingUartFields:
    def test_sensor_payload_includes_uart_keys(self):
        sensor = SensorConfig(
            esp_id=uuid.uuid4(),
            gpio=18,
            sensor_type="co2",
            sensor_name="CO2",
            interface_type="UART",
            sensor_metadata={
                "uart_rx_pin": 18,
                "uart_tx_pin": 17,
                "uart_baud": 9600,
            },
        )
        engine = ConfigMappingEngine(sensor_mappings=DEFAULT_SENSOR_MAPPINGS)
        payload = engine.apply_sensor_mapping(sensor)
        assert payload["uart_rx_pin"] == 18
        assert payload["uart_tx_pin"] == 17
        assert payload["uart_baud"] == 9600


@pytest.fixture
def gpio_service_uart():
    mock_session = AsyncMock()
    mock_sensor_repo = AsyncMock()
    mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
    mock_actuator_repo = AsyncMock()
    mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
    mock_esp_repo = AsyncMock()
    mock_device = MagicMock()
    mock_device.hardware_type = "ESP32_WROOM"
    mock_device.device_metadata = None
    mock_esp_repo.get_by_id = AsyncMock(return_value=mock_device)
    return GpioValidationService(
        session=mock_session,
        sensor_repo=mock_sensor_repo,
        actuator_repo=mock_actuator_repo,
        esp_repo=mock_esp_repo,
    )


class TestGpioValidationUart:
    @pytest.mark.asyncio
    async def test_uart_single_pin_skips_adc2_warning(self, gpio_service_uart):
        esp_id = uuid.uuid4()
        result = await gpio_service_uart.validate_gpio_available(
            esp_db_id=esp_id,
            gpio=18,
            interface_type="UART",
        )
        assert result.available is True
        assert result.warning is None
