"""
Unit Tests: Phase 2.4 — Subzone-Matching in Logic Engine

Tests SensorConditionEvaluator subzone filter and ActuatorActionExecutor subzone skip.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.actuator_service import ActuatorSendCommandResult
from src.services.logic.conditions.sensor_evaluator import SensorConditionEvaluator
from src.services.logic.actions.actuator_executor import ActuatorActionExecutor

_MOCK_SEND_OK = ActuatorSendCommandResult(
    success=True,
    correlation_id="00000000-0000-4000-8000-000000000001",
    command_sent=True,
    safety_warnings=[],
)


class TestSensorConditionEvaluatorSubzone:
    """Test SensorConditionEvaluator subzone_id filter (Phase 2.4)."""

    @pytest.fixture
    def evaluator(self):
        return SensorConditionEvaluator()

    @pytest.mark.asyncio
    async def test_condition_without_subzone_id_fires_as_before(self, evaluator):
        """SensorCondition without subzone_id behaves like before (backward compatible)."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
            }
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_condition_with_subzone_id_matching_fires(self, evaluator):
        """Condition with subzone_id fires when trigger_data.subzone_id matches."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "subzone_id": "subzone_vorne",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "subzone_id": "subzone_vorne",
            }
        }
        result = await evaluator.evaluate(condition, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_condition_with_subzone_id_mismatch_does_not_fire(self, evaluator):
        """Condition with subzone_id does not fire when trigger_data.subzone_id differs."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "subzone_id": "subzone_vorne",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                "subzone_id": "subzone_hinten",
            }
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_condition_with_subzone_id_trigger_missing_subzone_does_not_fire(self, evaluator):
        """When condition requires subzone_id but trigger_data has none: do not fire."""
        condition = {
            "type": "sensor",
            "esp_id": "ESP_01",
            "gpio": 5,
            "operator": ">",
            "value": 25.0,
            "subzone_id": "subzone_vorne",
        }
        context = {
            "sensor_data": {
                "esp_id": "ESP_01",
                "gpio": 5,
                "value": 30.0,
                # subzone_id missing or None
            }
        }
        result = await evaluator.evaluate(condition, context)
        assert result is False


class TestActuatorActionExecutorSubzone:
    """Test ActuatorActionExecutor subzone skip (Phase 2.4)."""

    @pytest.fixture
    async def mock_actuator_service(self):
        service = AsyncMock()
        service.send_command = AsyncMock(return_value=_MOCK_SEND_OK)
        return service

    @pytest.mark.asyncio
    async def test_actuator_executes_when_no_trigger_subzone(self, mock_actuator_service):
        """Actuator executes when trigger_data has no subzone_id (backward compatible)."""
        executor = ActuatorActionExecutor(mock_actuator_service)
        action = {
            "type": "actuator",
            "esp_id": "ESP_01",
            "gpio": 5,
            "command": "ON",
        }
        context = {
            "trigger_data": {"timestamp": 123},
            "rule_id": str(uuid.uuid4()),
            "rule_name": "test",
        }
        result = await executor.execute(action, context)
        assert result.success is True
        assert result.data.get("skipped") is not True
        mock_actuator_service.send_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_actuator_skipped_when_subzone_mismatch(self, mock_actuator_service):
        """Actuator is skipped when it serves different subzone than trigger."""
        mock_subzone_repo = AsyncMock()
        mock_subzone = MagicMock()
        mock_subzone.subzone_id = "subzone_hinten"
        mock_subzone_repo.get_subzone_by_gpio = AsyncMock(return_value=mock_subzone)

        executor = ActuatorActionExecutor(mock_actuator_service)
        action = {
            "type": "actuator",
            "esp_id": "ESP_01",
            "gpio": 5,
            "command": "ON",
        }
        mock_session = MagicMock()

        # We need to patch SubzoneRepository to return our mock
        with patch(
            "src.services.logic.actions.actuator_executor.SubzoneRepository"
        ) as mock_repo_class:
            mock_repo_class.return_value = mock_subzone_repo

            context = {
                "trigger_data": {"subzone_id": "subzone_vorne", "timestamp": 123},
                "rule_id": str(uuid.uuid4()),
                "rule_name": "test",
                "session": mock_session,
            }
            result = await executor.execute(action, context)

        assert result.success is True
        assert result.data.get("skipped") is True
        assert result.data.get("reason") == "subzone_mismatch"
        mock_actuator_service.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_actuator_executes_when_subzone_match(self, mock_actuator_service):
        """Actuator executes when it serves same subzone as trigger."""
        mock_subzone_repo = AsyncMock()
        mock_subzone = MagicMock()
        mock_subzone.subzone_id = "subzone_vorne"
        mock_subzone_repo.get_subzone_by_gpio = AsyncMock(return_value=mock_subzone)

        with patch(
            "src.services.logic.actions.actuator_executor.SubzoneRepository"
        ) as mock_repo_class:
            mock_repo_class.return_value = mock_subzone_repo

            executor = ActuatorActionExecutor(mock_actuator_service)
            action = {
                "type": "actuator",
                "esp_id": "ESP_01",
                "gpio": 5,
                "command": "ON",
            }
            context = {
                "trigger_data": {"subzone_id": "subzone_vorne", "timestamp": 123},
                "rule_id": str(uuid.uuid4()),
                "rule_name": "test",
                "session": MagicMock(),
            }
            result = await executor.execute(action, context)

        assert result.success is True
        assert result.data.get("skipped") is not True
        mock_actuator_service.send_command.assert_called_once()
