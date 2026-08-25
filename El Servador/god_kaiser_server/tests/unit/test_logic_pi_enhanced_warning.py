"""
Unit Tests: AUT-1117 (S7, DP7) — non-blocking pi_enhanced warning for EC/pH trigger sensors

_collect_ec_ph_trigger_sensors() / _check_pi_enhanced_warning() reuse the S6/DP4
warnings mechanism: an EC-/pH-dosing rule whose trigger sensor has pi_enhanced=False
gets a warning (ATC compensation skipped, sensor_handler.py:332), never a raise.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic_service import LogicService


def _hysteresis_condition(esp_id="ESP_001", gpio=4, sensor_type="ec"):
    return {
        "type": "hysteresis",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "activate_below": 1.6,
        "deactivate_above": 1.7,
    }


class TestCollectEcPhTriggerSensors:
    """Pure helper: collects hysteresis/sensor conditions with sensor_type ec/ph."""

    def test_hysteresis_ec_condition_collected(self):
        result = LogicService._collect_ec_ph_trigger_sensors([_hysteresis_condition()])
        assert len(result) == 1
        assert result[0]["sensor_type"] == "ec"

    def test_case_insensitive_sensor_type(self):
        result = LogicService._collect_ec_ph_trigger_sensors(
            [_hysteresis_condition(sensor_type="PH")]
        )
        assert len(result) == 1

    def test_non_ec_ph_sensor_type_ignored(self):
        conditions = [_hysteresis_condition(sensor_type="temperature")]
        assert LogicService._collect_ec_ph_trigger_sensors(conditions) == []

    def test_compound_and_condition_descends(self):
        conditions = {
            "logic": "AND",
            "conditions": [
                {"type": "time_window", "start_hour": 0, "end_hour": 23},
                _hysteresis_condition(gpio=34, sensor_type="ph"),
            ],
        }
        result = LogicService._collect_ec_ph_trigger_sensors(conditions)
        assert len(result) == 1
        assert result[0]["gpio"] == 34


class TestCheckPiEnhancedWarning:
    def _service(self):
        service = LogicService(logic_repo=AsyncMock())
        service.logic_repo.session = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_pi_enhanced_false_produces_warning(self):
        service = self._service()
        esp_device = MagicMock(id=uuid.uuid4())
        sensor_config = MagicMock(pi_enhanced=False)

        with (
            patch("src.services.logic_service.ESPRepository") as MockESPRepo,
            patch("src.services.logic_service.SensorRepository") as MockSensorRepo,
        ):
            MockESPRepo.return_value.get_by_device_id = AsyncMock(return_value=esp_device)
            MockSensorRepo.return_value.get_by_esp_and_gpio = AsyncMock(return_value=sensor_config)

            warnings = await service._check_pi_enhanced_warning([_hysteresis_condition()])

        assert len(warnings) == 1
        assert "pi_enhanced" in warnings[0]

    @pytest.mark.asyncio
    async def test_pi_enhanced_true_no_warning(self):
        """Control test: pi_enhanced=True produces an empty warnings array."""
        service = self._service()
        esp_device = MagicMock(id=uuid.uuid4())
        sensor_config = MagicMock(pi_enhanced=True)

        with (
            patch("src.services.logic_service.ESPRepository") as MockESPRepo,
            patch("src.services.logic_service.SensorRepository") as MockSensorRepo,
        ):
            MockESPRepo.return_value.get_by_device_id = AsyncMock(return_value=esp_device)
            MockSensorRepo.return_value.get_by_esp_and_gpio = AsyncMock(return_value=sensor_config)

            warnings = await service._check_pi_enhanced_warning([_hysteresis_condition()])

        assert warnings == []

    @pytest.mark.asyncio
    async def test_non_ec_ph_sensor_not_checked(self):
        service = self._service()
        conditions = [_hysteresis_condition(sensor_type="temperature")]

        with patch("src.services.logic_service.ESPRepository") as MockESPRepo:
            warnings = await service._check_pi_enhanced_warning(conditions)

        assert warnings == []
        MockESPRepo.assert_not_called()

    @pytest.mark.asyncio
    async def test_esp_not_found_fails_open(self):
        service = self._service()

        with patch("src.services.logic_service.ESPRepository") as MockESPRepo:
            MockESPRepo.return_value.get_by_device_id = AsyncMock(return_value=None)
            warnings = await service._check_pi_enhanced_warning([_hysteresis_condition()])

        assert warnings == []

    @pytest.mark.asyncio
    async def test_sensor_not_found_fails_open(self):
        service = self._service()
        esp_device = MagicMock(id=uuid.uuid4())

        with (
            patch("src.services.logic_service.ESPRepository") as MockESPRepo,
            patch("src.services.logic_service.SensorRepository") as MockSensorRepo,
        ):
            MockESPRepo.return_value.get_by_device_id = AsyncMock(return_value=esp_device)
            MockSensorRepo.return_value.get_by_esp_and_gpio = AsyncMock(return_value=None)

            warnings = await service._check_pi_enhanced_warning([_hysteresis_condition()])

        assert warnings == []

    @pytest.mark.asyncio
    async def test_lookup_exception_fails_open(self):
        """Any exception during sensor lookup must never propagate — fail-open."""
        service = self._service()

        with patch("src.services.logic_service.ESPRepository") as MockESPRepo:
            MockESPRepo.return_value.get_by_device_id = AsyncMock(
                side_effect=RuntimeError("db unavailable")
            )
            warnings = await service._check_pi_enhanced_warning([_hysteresis_condition()])

        assert warnings == []
