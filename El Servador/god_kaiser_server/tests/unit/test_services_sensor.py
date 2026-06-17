"""
Unit Tests: Sensor Service

Tests the SensorService business logic layer including:
- Configuration CRUD operations
- Reading processing with calibration
- Data queries and statistics
- Error handling for missing devices/configs
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.sensor_service import SensorService


class TestSensorServiceConfigManagement:
    """Tests for sensor configuration CRUD operations."""

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_missing_esp(self):
        """get_config returns None when ESP device doesn't exist."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=None)

        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.get_config("ESP_UNKNOWN", gpio=4)

        # ASSERT
        assert result is None, "get_config should return None when ESP device not found"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_missing_sensor(self):
        """get_config returns None when sensor config doesn't exist."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[])

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.get_config("ESP_TEST001", gpio=4)

        # ASSERT
        assert result is None, "get_config should return None when sensor config not found"
        mock_sensor_repo.get_all_by_esp_and_gpio.assert_called_once_with(1, 4)

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_get_config_success(self):
        """get_config returns SensorConfig when it exists."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_config = MagicMock(
            id=100,
            esp_id=1,
            gpio=4,
            sensor_type="ds18b20",
            name="Temperature Sensor",
        )
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[mock_config])

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.get_config("ESP_TEST001", gpio=4)

        # ASSERT
        assert result is not None, "get_config should return SensorConfig when found"
        assert (
            result.sensor_type == "ds18b20"
        ), f"Expected sensor_type='ds18b20', got '{result.sensor_type}'"
        assert result.gpio == 4, f"Expected gpio=4, got {result.gpio}"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_create_config_raises_for_unknown_esp(self):
        """create_or_update_config raises ValueError for unknown ESP."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=None)

        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT & ASSERT
        with pytest.raises(ValueError, match="not found"):
            await service.create_or_update_config(
                esp_id="ESP_UNKNOWN",
                gpio=4,
                sensor_type="ds18b20",
            )

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_create_config_success(self):
        """create_or_update_config creates new config when none exists."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_gpio_and_type = AsyncMock(return_value=None)  # No existing
        mock_sensor_repo.create = AsyncMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # Patch SensorConfig to avoid actual SQLAlchemy model instantiation
        with patch("src.services.sensor_service.SensorConfig") as MockSensorConfig:
            mock_config = MagicMock(
                sensor_type="ds18b20",
                gpio=4,
                sensor_name="Soil Temperature",
            )
            MockSensorConfig.return_value = mock_config

            # ACT
            result = await service.create_or_update_config(
                esp_id="ESP_TEST001",
                gpio=4,
                sensor_type="ds18b20",
                name="Soil Temperature",
                interval_ms=30000,
            )

            # ASSERT
            assert result is not None, "Should return created SensorConfig"
            mock_sensor_repo.create.assert_called_once()

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_update_existing_config(self):
        """create_or_update_config updates existing config when found."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_existing = MagicMock(
            id=100,
            esp_id=1,
            gpio=4,
            sensor_type="ds18b20",
            name="Old Name",
            calibration={"offset": 0.5},
            metadata={},
        )
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_gpio_and_type = AsyncMock(return_value=mock_existing)
        mock_sensor_repo.create = AsyncMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.create_or_update_config(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="sht31",  # Changed type
            name="New Name",
        )

        # ASSERT
        assert (
            result.sensor_type == "sht31"
        ), f"sensor_type should be updated to 'sht31', got '{result.sensor_type}'"
        assert (
            result.name == "New Name"
        ), f"name should be updated to 'New Name', got '{result.name}'"
        mock_sensor_repo.create.assert_not_called()  # Should NOT create new


class TestSensorServiceProcessing:
    """Tests for sensor reading processing."""

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_process_reading_success(self):
        """process_reading returns processed value and quality."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[])
        mock_sensor_repo.store_reading = AsyncMock()

        # Mock processor that returns dict (as service expects)
        # Note: Real processors return ProcessingResult dataclass, but service uses .get()
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(
            return_value={
                "value": 25.0,
                "unit": "°C",
                "quality": "good",
                "metadata": {"raw_mode": True, "original_raw_value": 400},
            }
        )

        mock_loader = MagicMock()
        mock_loader.get_processor = MagicMock(return_value=mock_processor)

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            library_loader=mock_loader,
        )

        # ACT
        result = await service.process_reading(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            raw_value=400,  # RAW 400 = 25.0°C
            params={"raw_mode": True},
        )

        # ASSERT
        assert (
            result["success"] is True
        ), f"Processing should succeed, got error: {result.get('error')}"
        assert (
            result["processed_value"] == 25.0
        ), f"RAW 400 should process to 25.0°C, got {result['processed_value']}"
        assert result["quality"] == "good", f"Expected quality='good', got '{result['quality']}'"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_process_reading_with_calibration(self):
        """process_reading applies calibration offset."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
        mock_sensor_repo.store_reading = AsyncMock()

        # Mock processor that simulates calibration applied
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(
            return_value={
                "value": 25.5,  # 25.0°C + 0.5 offset
                "unit": "°C",
                "quality": "good",
                "metadata": {"raw_mode": True, "original_raw_value": 400, "offset_applied": 0.5},
            }
        )

        mock_loader = MagicMock()
        mock_loader.get_processor = MagicMock(return_value=mock_processor)

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            library_loader=mock_loader,
        )

        # ACT
        result = await service.process_reading(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            raw_value=400,  # RAW 400 = 25.0°C
            calibration={"offset": 0.5},  # +0.5°C offset
            params={"raw_mode": True},
        )

        # ASSERT
        assert (
            result["success"] is True
        ), f"Processing should succeed, got error: {result.get('error')}"
        assert (
            result["processed_value"] == 25.5
        ), f"25.0°C + 0.5 offset should be 25.5°C, got {result['processed_value']}"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_process_reading_unknown_sensor_type(self):
        """process_reading returns error for unknown sensor type."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[])

        mock_loader = MagicMock()
        mock_loader.get_processor = MagicMock(return_value=None)  # No processor

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            library_loader=mock_loader,
        )

        # ACT
        result = await service.process_reading(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="unknown_sensor_xyz",
            raw_value=100,
        )

        # ASSERT
        assert result["success"] is False, "Processing should fail for unknown sensor type"
        assert "No processor" in result.get(
            "error", ""
        ), f"Error should mention missing processor, got: {result.get('error')}"


class TestSensorServiceDelete:
    """Tests for sensor config deletion."""

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_delete_config_returns_false_for_unknown_esp(self):
        """delete_config returns False when ESP not found."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=None)

        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.delete_config("ESP_UNKNOWN", gpio=4)

        # ASSERT
        assert result is False, "delete_config should return False when ESP not found"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_delete_config_returns_false_for_unknown_sensor(self):
        """delete_config returns False when sensor not found."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.delete_config("ESP_TEST001", gpio=4)

        # ASSERT
        assert result is False, "delete_config should return False when sensor not found"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_delete_config_success(self):
        """delete_config returns True and calls delete when sensor exists."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor = MagicMock(id=100)
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_sensor)
        mock_sensor_repo.delete = AsyncMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.delete_config("ESP_TEST001", gpio=4)

        # ASSERT
        assert result is True, "delete_config should return True when sensor deleted"
        mock_sensor_repo.delete.assert_called_once_with(100)


class TestSensorServiceCalibration:
    """Tests for sensor calibration."""

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_calibrate_offset_method(self):
        """calibrate with offset method calculates correct offset."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # Mock get_config to return None (don't save)
        service.get_config = AsyncMock(return_value=None)

        # ACT
        result = await service.calibrate(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            calibration_points=[{"raw": 25.0, "reference": 25.5}],  # Actual 25°C, reference 25.5°C
            method="offset",
            save_to_config=False,
        )

        # ASSERT
        assert result["success"] is True, f"Calibration should succeed, got: {result}"
        assert (
            result["calibration"]["offset"] == 0.5
        ), f"Offset should be 0.5 (25.5 - 25.0), got {result['calibration']['offset']}"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_calibrate_linear_method(self):
        """calibrate with linear method calculates slope and offset."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        service.get_config = AsyncMock(return_value=None)

        # ACT
        result = await service.calibrate(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            calibration_points=[
                {"raw": 0.0, "reference": 0.0},  # 0°C → 0°C
                {"raw": 100.0, "reference": 100.0},  # 100°C → 100°C
            ],
            method="linear",
            save_to_config=False,
        )

        # ASSERT
        assert result["success"] is True, f"Calibration should succeed, got: {result}"
        assert (
            result["calibration"]["slope"] == 1.0
        ), f"Slope should be 1.0, got {result['calibration']['slope']}"
        assert (
            result["calibration"]["offset"] == 0.0
        ), f"Offset should be 0.0, got {result['calibration']['offset']}"

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_calibrate_insufficient_points(self):
        """calibrate fails with no calibration points."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.calibrate(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            calibration_points=[],  # Empty!
            method="offset",
        )

        # ASSERT
        assert result["success"] is False, "Calibration should fail with no points"
        assert (
            "at least 1" in result.get("error", "").lower()
        ), f"Error should mention minimum points, got: {result.get('error')}"


class TestSensorServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.sensor
    @pytest.mark.edge_case
    @pytest.mark.asyncio
    async def test_process_ds18b20_sensor_fault(self):
        """process_reading handles DS18B20 -127°C sensor fault."""
        # ARRANGE
        mock_esp = MagicMock(id=1)
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[])
        mock_sensor_repo.store_reading = AsyncMock()

        # Mock processor that simulates sensor fault detection
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(
            return_value={
                "value": 0.0,  # Fault returns 0.0 value
                "unit": "°C",
                "quality": "error",  # Sensor fault = error quality
                "metadata": {
                    "raw_mode": True,
                    "original_raw_value": -2032,
                    "error_code": 1060,
                    "error": "DS18B20 sensor fault: -127°C indicates disconnected sensor",
                },
            }
        )

        mock_loader = MagicMock()
        mock_loader.get_processor = MagicMock(return_value=mock_processor)

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            library_loader=mock_loader,
        )

        # ACT
        result = await service.process_reading(
            esp_id="ESP_TEST001",
            gpio=4,
            sensor_type="ds18b20",
            raw_value=-2032,  # RAW -2032 = -127°C (sensor fault)
            params={"raw_mode": True},
        )

        # ASSERT
        assert (
            result["success"] is True
        ), f"Processing should succeed even for error, got: {result.get('error')}"
        assert (
            result["quality"] == "error"
        ), f"DS18B20 -127°C should return quality='error', got '{result['quality']}'"

    @pytest.mark.sensor
    @pytest.mark.edge_case
    @pytest.mark.asyncio
    async def test_get_latest_reading_unknown_esp(self):
        """get_latest_reading returns None for unknown ESP."""
        # ARRANGE
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=None)

        mock_sensor_repo = MagicMock()

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.get_latest_reading("ESP_UNKNOWN", gpio=4)

        # ASSERT
        assert result is None, "get_latest_reading should return None for unknown ESP"


class TestSensorServiceTriggerMeasurementContract:
    """Contract persistence tests for manual measurement trigger flow."""

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_trigger_measurement_persists_sent_intent(self):
        mock_esp = MagicMock(id=1, status="online")
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor = MagicMock(enabled=True, sensor_type="moisture")
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[mock_sensor])
        mock_sensor_repo.session = MagicMock()

        mock_publisher = MagicMock()
        mock_publisher.publish_sensor_command = MagicMock(return_value=(True, "rid-1"))

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            publisher=mock_publisher,
        )

        with patch("src.services.sensor_service.CommandContractRepository") as repo_cls:
            repo_instance = repo_cls.return_value
            repo_instance.record_intent_publish_sent = AsyncMock()

            result = await service.trigger_measurement(esp_id="ESP_TEST001", gpio=4)

        assert result["success"] is True
        assert result["request_id"] == "rid-1"
        repo_instance.record_intent_publish_sent.assert_awaited_once_with(
            intent_id="rid-1",
            correlation_id="rid-1",
            esp_id="ESP_TEST001",
            flow="command",
        )

    @pytest.mark.sensor
    @pytest.mark.asyncio
    async def test_trigger_measurement_ignores_contract_persist_failure(self):
        mock_esp = MagicMock(id=1, status="online")
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp)

        mock_sensor = MagicMock(enabled=True, sensor_type="moisture")
        mock_sensor_repo = MagicMock()
        mock_sensor_repo.get_all_by_esp_and_gpio = AsyncMock(return_value=[mock_sensor])
        mock_sensor_repo.session = MagicMock()

        mock_publisher = MagicMock()
        mock_publisher.publish_sensor_command = MagicMock(return_value=(True, "rid-2"))

        service = SensorService(
            sensor_repo=mock_sensor_repo,
            esp_repo=mock_esp_repo,
            publisher=mock_publisher,
        )

        with patch("src.services.sensor_service.CommandContractRepository") as repo_cls:
            repo_instance = repo_cls.return_value
            repo_instance.record_intent_publish_sent = AsyncMock(
                side_effect=RuntimeError("db down")
            )

            result = await service.trigger_measurement(esp_id="ESP_TEST002", gpio=5)

        assert result["success"] is True
        assert result["request_id"] == "rid-2"
