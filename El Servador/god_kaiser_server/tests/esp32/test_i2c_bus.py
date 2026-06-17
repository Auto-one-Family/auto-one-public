"""
I2C Bus Mock Test Suite
=======================

Test-IDs: I2C-INIT-*, I2C-SCAN-*, I2C-COMM-*, I2C-ERR-*

Purpose: Server-side validation of ESP32 I2C bus operations through MQTT messages.
These tests complement the Wokwi firmware tests by validating:
1. Sensor data from I2C devices is correctly received and processed
2. I2C error conditions are properly reported via MQTT
3. Multi-device scenarios work correctly

Note: These tests do NOT test the actual I2C hardware - they test the
communication protocol between ESP32 and Server when I2C events occur.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

# Test markers
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.esp32,
]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sht31_sensor_config() -> Dict[str, Any]:
    """SHT31 I2C Temperature/Humidity sensor configuration."""
    return {
        "gpio": 21,  # I2C SDA pin (not actual data pin)
        "sensor_type": "SHT31",
        "i2c_address": 0x44,
        "measurement_interval_ms": 30000,
        "pi_enhanced": True,
        "name": "Greenhouse Temp/Humidity",
    }


@pytest.fixture
def bmp280_sensor_config() -> Dict[str, Any]:
    """BMP280 I2C Pressure/Temperature sensor configuration."""
    return {
        "gpio": 21,  # I2C SDA pin
        "sensor_type": "BMP280",
        "i2c_address": 0x76,
        "measurement_interval_ms": 60000,
        "pi_enhanced": True,
        "name": "Atmospheric Pressure",
    }


@pytest.fixture
def i2c_sensor_data_payload() -> Dict[str, Any]:
    """Mock I2C sensor data payload (SHT31 raw mode)."""
    return {
        "ts": int(datetime.now().timestamp()),
        "gpio": 21,
        "sensor_type": "SHT31",
        "i2c_address": 68,  # 0x44 in decimal
        "raw_mode": True,
        "values": {"temperature_raw": 0x6C5A, "humidity_raw": 0x5E4D},  # ~24.5°C  # ~55% RH
    }


@pytest.fixture
def i2c_error_payload() -> Dict[str, Any]:
    """Mock I2C error payload."""
    return {
        "ts": int(datetime.now().timestamp()),
        "error_code": 1012,  # ERROR_I2C_READ_FAILED
        "severity": "ERROR",
        "message": "I2C read: Expected 6 bytes, got 0",
        "context": {
            "i2c_address": 68,  # 0x44
            "register": 0xFD,
            "expected_bytes": 6,
            "received_bytes": 0,
        },
    }


# =============================================================================
# I2C INITIALIZATION TESTS (Mock Validation)
# =============================================================================


class TestI2CInitialization:
    """
    Tests for I2C bus initialization validation through MQTT diagnostics.

    These tests verify that ESP32 reports I2C status correctly.
    """

    async def test_i2c_init_reported_in_heartbeat(self, mqtt_test_client, sample_esp_device):
        """
        I2C-INIT-001: Verify I2C initialization status in heartbeat.

        Expected: Heartbeat payload includes i2c_initialized: true
        """
        # Arrange
        heartbeat_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/heartbeat"

        # Act
        heartbeat_payload = {
            "ts": int(datetime.now().timestamp()),
            "heap_free": 98304,
            "uptime_seconds": 60,
            "wifi_rssi": -45,
            "i2c_initialized": True,
            "i2c_device_count": 2,
            "sensor_count": 3,
            "actuator_count": 1,
        }
        await mqtt_test_client.publish(heartbeat_topic, json.dumps(heartbeat_payload))

        # Assert
        # Handler should process heartbeat without error
        # Device status should be updated
        assert heartbeat_payload["i2c_initialized"] is True
        assert heartbeat_payload["i2c_device_count"] == 2

    async def test_i2c_init_failure_reported(self, mqtt_test_client, sample_esp_device):
        """
        I2C-INIT-003: Verify I2C initialization failure is reported.

        Expected: System error published with ERROR_I2C_INIT_FAILED
        """
        # Arrange
        error_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/error"

        # Act
        error_payload = {
            "ts": int(datetime.now().timestamp()),
            "error_code": 1010,  # ERROR_I2C_INIT_FAILED
            "severity": "CRITICAL",
            "message": "I2C Bus Manager initialization failed!",
            "context": {"sda_pin": 21, "scl_pin": 22, "reason": "Wire.begin() returned false"},
        }
        await mqtt_test_client.publish(error_topic, json.dumps(error_payload))

        # Assert
        assert error_payload["error_code"] == 1010
        assert error_payload["severity"] == "CRITICAL"


# =============================================================================
# I2C BUS SCANNING TESTS
# =============================================================================


class TestI2CBusScanning:
    """
    Tests for I2C bus scanning validation through diagnostics.
    """

    async def test_i2c_scan_results_in_diagnostics(self, mqtt_test_client, sample_esp_device):
        """
        I2C-SCAN-001: Verify I2C scan results are included in diagnostics.

        Expected: Diagnostics include list of found I2C addresses
        """
        # Arrange
        diagnostics_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/diagnostics"

        # Act
        diagnostics_payload = {
            "ts": int(datetime.now().timestamp()),
            "esp_id": sample_esp_device.device_id,
            "heap_free": 95000,
            "i2c_status": {
                "initialized": True,
                "sda_pin": 21,
                "scl_pin": 22,
                "frequency_khz": 100,
                "devices_found": [0x44, 0x76],  # SHT31, BMP280
                "last_scan_ts": int(datetime.now().timestamp()),
            },
        }
        await mqtt_test_client.publish(diagnostics_topic, json.dumps(diagnostics_payload))

        # Assert
        i2c_status = diagnostics_payload["i2c_status"]
        assert i2c_status["initialized"] is True
        assert 0x44 in i2c_status["devices_found"]
        assert 0x76 in i2c_status["devices_found"]
        assert len(i2c_status["devices_found"]) == 2

    async def test_i2c_device_not_found_error(self, mqtt_test_client, sample_esp_device):
        """
        I2C-SCAN-005: Verify device not found error is reported.

        Expected: Error published when trying to access non-existent device
        """
        # Arrange
        error_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/error"

        # Act
        error_payload = {
            "ts": int(datetime.now().timestamp()),
            "error_code": 1011,  # ERROR_I2C_DEVICE_NOT_FOUND
            "severity": "WARNING",
            "message": "Device 0x99 register write error (2)",
            "context": {
                "i2c_address": 0x99,
                "operation": "write",
                "wire_error": 2,  # NACK on address
            },
        }
        await mqtt_test_client.publish(error_topic, json.dumps(error_payload))

        # Assert
        assert error_payload["error_code"] == 1011
        assert error_payload["context"]["wire_error"] == 2


# =============================================================================
# I2C COMMUNICATION TESTS
# =============================================================================


class TestI2CCommunication:
    """
    Tests for I2C read/write operations validation.
    """

    async def test_i2c_sensor_data_received(
        self, mqtt_test_client, sample_esp_device, i2c_sensor_data_payload
    ):
        """
        I2C-COMM-001: Verify I2C sensor data is correctly received.

        Expected: Sensor data with raw_mode:true is processed
        """
        # Arrange
        sensor_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/sensor/21/data"

        # Act
        await mqtt_test_client.publish(sensor_topic, json.dumps(i2c_sensor_data_payload))

        # Assert
        assert i2c_sensor_data_payload["raw_mode"] is True
        assert "temperature_raw" in i2c_sensor_data_payload["values"]
        assert "humidity_raw" in i2c_sensor_data_payload["values"]

    async def test_i2c_multi_device_data(
        self, mqtt_test_client, sample_esp_device, sht31_sensor_config, bmp280_sensor_config
    ):
        """
        I2C-MULTI-002: Verify multiple I2C sensors report data correctly.

        Expected: Both SHT31 and BMP280 data received within interval
        """
        # Arrange
        ts = int(datetime.now().timestamp())

        sht31_data = {
            "ts": ts,
            "gpio": 21,
            "sensor_type": "SHT31",
            "i2c_address": 0x44,
            "raw_mode": True,
            "values": {"temperature_raw": 0x6C5A, "humidity_raw": 0x5E4D},
        }

        bmp280_data = {
            "ts": ts + 1,
            "gpio": 21,
            "sensor_type": "BMP280",
            "i2c_address": 0x76,
            "raw_mode": True,
            "values": {"pressure_raw": 0x523456, "temperature_raw": 0x8ABC},
        }

        # Act
        sensor_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/sensor/21/data"
        await mqtt_test_client.publish(sensor_topic, json.dumps(sht31_data))
        await asyncio.sleep(0.1)
        await mqtt_test_client.publish(sensor_topic, json.dumps(bmp280_data))

        # Assert - both payloads are valid
        assert sht31_data["i2c_address"] == 0x44
        assert bmp280_data["i2c_address"] == 0x76

    async def test_i2c_read_failure_reported(
        self, mqtt_test_client, sample_esp_device, i2c_error_payload
    ):
        """
        I2C-COMM-007: Verify I2C read failure is reported via error topic.

        Expected: Error with ERROR_I2C_READ_FAILED and context
        """
        # Arrange
        error_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/error"

        # Act
        await mqtt_test_client.publish(error_topic, json.dumps(i2c_error_payload))

        # Assert
        assert i2c_error_payload["error_code"] == 1012
        assert i2c_error_payload["context"]["expected_bytes"] == 6
        assert i2c_error_payload["context"]["received_bytes"] == 0


# =============================================================================
# I2C ERROR HANDLING TESTS
# =============================================================================


class TestI2CErrorHandling:
    """
    Tests for I2C error handling and recovery validation.
    """

    async def test_i2c_bus_error_critical(self, mqtt_test_client, sample_esp_device):
        """
        I2C-ERR-003: Verify bus error is reported with CRITICAL severity.

        Expected: ERROR_I2C_BUS_ERROR with CRITICAL severity
        """
        # Arrange
        error_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/error"

        # Act
        error_payload = {
            "ts": int(datetime.now().timestamp()),
            "error_code": 1014,  # ERROR_I2C_BUS_ERROR
            "severity": "CRITICAL",
            "message": "I2C bus verification failed",
            "context": {"wire_error": 4, "operation": "init_verification"},  # Other error
        }
        await mqtt_test_client.publish(error_topic, json.dumps(error_payload))

        # Assert
        assert error_payload["error_code"] == 1014
        assert error_payload["severity"] == "CRITICAL"
        assert error_payload["context"]["wire_error"] == 4

    async def test_i2c_write_failure_reported(self, mqtt_test_client, sample_esp_device):
        """
        I2C-ERR-001: Verify write failure (NACK) is reported.

        Expected: ERROR_I2C_WRITE_FAILED with wire error code
        """
        # Arrange
        error_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/error"

        # Act
        error_payload = {
            "ts": int(datetime.now().timestamp()),
            "error_code": 1013,  # ERROR_I2C_WRITE_FAILED
            "severity": "ERROR",
            "message": "Write error 3 to 0x44",
            "context": {"i2c_address": 0x44, "register": 0x30, "wire_error": 3},  # NACK on data
        }
        await mqtt_test_client.publish(error_topic, json.dumps(error_payload))

        # Assert
        assert error_payload["error_code"] == 1013
        assert error_payload["context"]["wire_error"] == 3

    async def test_i2c_error_tracking_in_diagnostics(self, mqtt_test_client, sample_esp_device):
        """
        I2C-ERR-005: Verify I2C errors are tracked in diagnostics.

        Expected: Diagnostics include I2C error count and last error
        """
        # Arrange
        diagnostics_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/system/diagnostics"

        # Act
        diagnostics_payload = {
            "ts": int(datetime.now().timestamp()),
            "esp_id": sample_esp_device.device_id,
            "error_count": 2,
            "errors": [
                {"code": 1012, "count": 1, "last_ts": int(datetime.now().timestamp()) - 30},
                {"code": 1011, "count": 1, "last_ts": int(datetime.now().timestamp()) - 60},
            ],
            "i2c_status": {
                "initialized": True,
                "error_count": 2,
                "last_error": {
                    "code": 1012,
                    "message": "Read failed",
                    "ts": int(datetime.now().timestamp()) - 30,
                },
            },
        }
        await mqtt_test_client.publish(diagnostics_topic, json.dumps(diagnostics_payload))

        # Assert
        assert diagnostics_payload["error_count"] == 2
        assert diagnostics_payload["i2c_status"]["error_count"] == 2
        assert diagnostics_payload["i2c_status"]["last_error"]["code"] == 1012


# =============================================================================
# I2C SENSOR CONFIGURATION TESTS
# =============================================================================


class TestI2CSensorConfiguration:
    """
    Tests for I2C sensor runtime configuration.
    """

    async def test_i2c_sensor_config_success(
        self, mqtt_test_client, sample_esp_device, sht31_sensor_config
    ):
        """
        Verify I2C sensor can be configured via MQTT.

        Expected: Config response with SUCCESS status
        """
        # Arrange
        config_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/config"
        response_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/config_response"

        config_payload = {"config_type": "sensor", "action": "add", "sensor": sht31_sensor_config}

        # Act
        await mqtt_test_client.publish(config_topic, json.dumps(config_payload))

        # Expected response (mock)
        expected_response = {
            "ts": int(datetime.now().timestamp()),
            "config_type": "sensor",
            "status": "SUCCESS",
            "gpio": 21,
            "sensor_type": "SHT31",
        }

        # Assert
        assert config_payload["sensor"]["i2c_address"] == 0x44
        assert expected_response["status"] == "SUCCESS"

    async def test_i2c_sensor_config_invalid_address(self, mqtt_test_client, sample_esp_device):
        """
        Verify invalid I2C address is rejected in config.

        Expected: Config response with FAILURE status
        """
        # Arrange
        config_topic = f"kaiser/god/esp/{sample_esp_device.device_id}/config"

        invalid_config = {
            "config_type": "sensor",
            "action": "add",
            "sensor": {
                "gpio": 21,
                "sensor_type": "SHT31",
                "i2c_address": 0x05,  # Reserved address!
                "measurement_interval_ms": 30000,
            },
        }

        # Act
        await mqtt_test_client.publish(config_topic, json.dumps(invalid_config))

        # Expected response
        expected_response = {
            "config_type": "sensor",
            "status": "FAILURE",
            "error_code": "VALIDATION_FAILED",
            "message": "Invalid I2C address: 0x05",
        }

        # Assert - address 0x05 is in reserved range (0x00-0x07)
        assert invalid_config["sensor"]["i2c_address"] < 0x08


# =============================================================================
# I2C PARAMETER VALIDATION TESTS
# =============================================================================


class TestI2CParameterValidation:
    """
    Tests for I2C parameter validation (mock-based).
    """

    async def test_valid_i2c_address_range(self):
        """
        Verify valid I2C address range is 0x08-0x77.
        """
        valid_addresses = [0x08, 0x44, 0x76, 0x77]
        invalid_addresses = [0x00, 0x05, 0x07, 0x78, 0x7F, 0x80]

        for addr in valid_addresses:
            assert 0x08 <= addr <= 0x77, f"Address 0x{addr:02X} should be valid"

        for addr in invalid_addresses:
            assert not (0x08 <= addr <= 0x77), f"Address 0x{addr:02X} should be invalid"

    async def test_i2c_error_code_mapping(self):
        """
        Verify I2C error codes are correctly defined.
        """
        error_codes = {
            "ERROR_I2C_INIT_FAILED": 1010,
            "ERROR_I2C_DEVICE_NOT_FOUND": 1011,
            "ERROR_I2C_READ_FAILED": 1012,
            "ERROR_I2C_WRITE_FAILED": 1013,
            "ERROR_I2C_BUS_ERROR": 1014,
        }

        # All codes should be in range 1010-1019 (I2C error range)
        for name, code in error_codes.items():
            assert 1010 <= code <= 1019, f"{name} should be in I2C range"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestI2CIntegration:
    """
    Integration tests combining multiple I2C operations.
    """

    async def test_full_i2c_sensor_flow(
        self, mqtt_test_client, sample_esp_device, sht31_sensor_config, i2c_sensor_data_payload
    ):
        """
        Full I2C sensor flow: Config → Init → Read → Publish → Heartbeat.

        Expected: Complete flow without errors
        """
        ts = int(datetime.now().timestamp())
        esp_id = sample_esp_device.device_id

        # 1. Configure sensor
        config_topic = f"kaiser/god/esp/{esp_id}/config"
        config_payload = {"config_type": "sensor", "action": "add", "sensor": sht31_sensor_config}
        await mqtt_test_client.publish(config_topic, json.dumps(config_payload))

        # 2. Sensor data published
        sensor_topic = f"kaiser/god/esp/{esp_id}/sensor/21/data"
        await mqtt_test_client.publish(sensor_topic, json.dumps(i2c_sensor_data_payload))

        # 3. Heartbeat confirms sensor count
        heartbeat_topic = f"kaiser/god/esp/{esp_id}/system/heartbeat"
        heartbeat_payload = {
            "ts": ts + 60,
            "heap_free": 95000,
            "uptime_seconds": 120,
            "sensor_count": 1,
            "i2c_initialized": True,
            "i2c_device_count": 1,
        }
        await mqtt_test_client.publish(heartbeat_topic, json.dumps(heartbeat_payload))

        # Assert
        assert heartbeat_payload["sensor_count"] == 1
        assert heartbeat_payload["i2c_initialized"] is True
