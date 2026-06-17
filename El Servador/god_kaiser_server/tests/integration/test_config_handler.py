"""
Integration Tests für ConfigHandler.

Location: tests/integration/test_config_handler.py
Benötigt: DB-Session für Failure Processing

Phase 3 Test-Suite: Config ACK Processing, Partial Success, Legacy Format.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.mqtt.handlers.config_handler import ConfigHandler, get_config_handler


@pytest.fixture(autouse=True)
def mock_terminal_authority_repo():
    """Mock terminal authority repository for all ConfigHandler tests."""
    with patch("src.mqtt.handlers.config_handler.CommandContractRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.upsert_terminal_event_authority = AsyncMock(return_value=(MagicMock(), False))
        mock_repo_class.return_value = mock_repo
        yield mock_repo


@pytest.fixture(autouse=True)
def mock_config_status_db_writes(request):
    """
    Keep handler-flow tests isolated from repository internals.

    Dedicated persistence tests in TestFailureProcessing still exercise the real
    _process_config_failures implementation.
    """
    if "TestFailureProcessing" in request.node.nodeid:
        yield
        return

    with (
        patch.object(ConfigHandler, "_mark_config_applied", new=AsyncMock(return_value=True)),
        patch.object(ConfigHandler, "_process_config_failures", new=AsyncMock(return_value=True)),
    ):
        yield


class TestConfigPayloadValidation:
    """Test config response payload validation."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    def test_valid_success_payload(self, handler):
        """Valid success payload passes validation."""
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 3,
            "message": "OK",
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True
        assert result["error"] == ""

    def test_valid_partial_success_payload(self, handler):
        """Valid partial_success payload (Phase 4) passes validation."""
        payload = {
            "status": "partial_success",
            "type": "sensor",
            "count": 2,
            "failed_count": 1,
            "failures": [
                {
                    "type": "sensor",
                    "gpio": 5,
                    "error_code": 1002,
                    "error": "GPIO_CONFLICT",
                    "detail": "Reserved",
                }
            ],
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True

    def test_valid_error_payload(self, handler):
        """Valid error payload passes validation."""
        payload = {
            "status": "error",
            "type": "actuator",
            "count": 0,
            "error_code": "MISSING_FIELD",
            "message": "Configuration failed",
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True

    def test_missing_status_fails(self, handler):
        """Missing status field fails validation."""
        payload = {"type": "sensor", "count": 3}
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "status" in result["error"].lower()

    def test_missing_type_fails(self, handler):
        """Missing type field fails validation."""
        payload = {"status": "success", "count": 3}
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "type" in result["error"].lower()

    def test_config_type_accepted_alternative(self, handler):
        """config_type is accepted as alternative to type."""
        payload = {
            "status": "success",
            "config_type": "actuator",  # Alternative name
            "count": 2,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is True

    def test_invalid_status_fails(self, handler):
        """Invalid status value fails validation."""
        payload = {
            "status": "invalid_status",
            "type": "sensor",
            "count": 3,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "status" in result["error"].lower()

    def test_invalid_type_fails(self, handler):
        """Invalid type value fails validation."""
        payload = {
            "status": "success",
            "type": "invalid_type",
            "count": 3,
        }
        result = handler._validate_payload(payload)
        assert result["valid"] is False
        assert "type" in result["error"].lower()

    def test_valid_types(self, handler):
        """All valid config types are accepted."""
        valid_types = ["sensor", "actuator", "zone", "system"]
        for config_type in valid_types:
            payload = {
                "status": "success",
                "type": config_type,
                "count": 1,
            }
            result = handler._validate_payload(payload)
            assert result["valid"] is True, f"Type '{config_type}' should be valid"

    def test_valid_statuses(self, handler):
        """All valid status values are accepted."""
        valid_statuses = ["success", "partial_success", "error", "failed"]
        for status in valid_statuses:
            payload = {
                "status": status,
                "type": "sensor",
                "count": 1,
            }
            result = handler._validate_payload(payload)
            assert result["valid"] is True, f"Status '{status}' should be valid"


class TestConfigStatusProcessing:
    """Test processing of different config statuses."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    @pytest.mark.asyncio
    async def test_success_status_processed(self, handler):
        """Success status is logged correctly."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 3,
            "message": "Configured 3 sensor(s)",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)
                    assert result is True

    @pytest.mark.asyncio
    async def test_partial_success_processes_failures(self, handler):
        """Partial success processes failure array."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "partial_success",
            "type": "sensor",
            "count": 2,
            "failed_count": 1,
            "message": "2 configured, 1 failed",
            "failures": [
                {
                    "type": "sensor",
                    "gpio": 5,
                    "error_code": 1002,
                    "error": "GPIO_CONFLICT",
                    "detail": "Reserved",
                }
            ],
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch.object(
                    handler, "_process_config_failures", new_callable=AsyncMock
                ) as mock_process:
                    with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                        mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                        result = await handler.handle_config_ack(topic, payload)

                        assert result is True
                        # Failures should be processed
                        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_status_logged(self, handler):
        """Error status is logged as error."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "error",
            "type": "actuator",
            "count": 0,
            "error_code": "MISSING_FIELD",
            "message": "Configuration failed",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)
                    assert result is True

    @pytest.mark.asyncio
    async def test_stale_terminal_event_skips_persistence_side_effects(self, handler):
        """Stale terminal event is acknowledged but not re-applied."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 1,
            "correlation_id": "corr-stale-1",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.mqtt.handlers.config_handler.CommandContractRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.upsert_terminal_event_authority = AsyncMock(
                    return_value=(MagicMock(), True)
                )
                mock_repo_class.return_value = mock_repo

                with patch.object(
                    handler, "_mark_config_applied", new_callable=AsyncMock
                ) as mock_mark_applied:
                    with patch(
                        "src.mqtt.handlers.config_handler.AuditLogRepository"
                    ) as mock_audit_repo_class:
                        mock_audit_repo = MagicMock()
                        mock_audit_repo.log_config_response = AsyncMock()
                        mock_audit_repo_class.return_value = mock_audit_repo

                        result = await handler.handle_config_ack(topic, payload)

                        assert result is True
                        mock_mark_applied.assert_not_called()
                        mock_audit_repo.log_config_response.assert_not_called()


class TestLegacyFormatSupport:
    """Test backward compatibility with legacy format."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    @pytest.mark.asyncio
    async def test_failed_status_accepted(self, handler):
        """'failed' status is accepted (legacy)."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "failed",  # Legacy: "failed" instead of "error"
            "type": "sensor",
            "count": 0,
            "error_code": "JSON_PARSE_ERROR",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)
                    assert result is True

    @pytest.mark.asyncio
    async def test_failed_item_accepted(self, handler):
        """Single failed_item is accepted (legacy)."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "error",
            "type": "sensor",
            "count": 0,
            "error_code": "GPIO_CONFLICT",
            "failed_item": {  # Legacy: single item instead of array
                "gpio": 5,
                "sensor_type": "DS18B20",
                "reason": "GPIO reserved",
            },
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)
                    assert result is True

    @pytest.mark.asyncio
    async def test_config_type_alternative_field(self, handler):
        """config_type field is accepted as alternative to type."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "success",
            "config_type": "sensor",  # Legacy field name
            "count": 2,
            "message": "OK",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo:
                mock_repo.return_value.log_config_response = AsyncMock()

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)
                    assert result is True


class TestTopicParsing:
    """Test config response topic parsing."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    @pytest.mark.asyncio
    async def test_invalid_topic_returns_false(self, handler):
        """Invalid topic format causes handler to return False."""
        topic = "invalid/topic/format"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 1,
        }
        result = await handler.handle_config_ack(topic, payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_topic_returns_false(self, handler):
        """Empty topic returns False."""
        topic = ""
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 1,
        }
        result = await handler.handle_config_ack(topic, payload)
        assert result is False


class TestFailureProcessing:
    """Test Phase 4 failure processing."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    @pytest.mark.asyncio
    async def test_process_sensor_failures(self, handler):
        """Sensor failures are processed and DB is updated."""
        esp_id = "ESP_TEST"
        config_type = "sensor"
        failures = [
            {
                "type": "sensor",
                "gpio": 5,
                "error": "GPIO_CONFLICT",
                "detail": "Reserved by actuator",
            }
        ]

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.ESPRepository") as mock_esp_repo:
                mock_esp = MagicMock()
                mock_esp.id = 1
                mock_esp_repo.return_value.get_by_device_id = AsyncMock(return_value=mock_esp)

                with patch("src.mqtt.handlers.config_handler.SensorRepository") as mock_sensor_repo:
                    mock_sensor = MagicMock()
                    mock_sensor.id = 10
                    mock_sensor_repo.return_value.get_by_esp_and_gpio = AsyncMock(
                        return_value=mock_sensor
                    )
                    mock_sensor_repo.return_value.get_all_by_esp_and_gpio = AsyncMock(
                        return_value=[mock_sensor]
                    )
                    mock_sensor_repo.return_value.update = AsyncMock()

                    with patch("src.mqtt.handlers.config_handler.ActuatorRepository"):
                        await handler._process_config_failures(esp_id, config_type, failures)

                        # Sensor should be updated with failed status
                        mock_sensor_repo.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_actuator_failures(self, handler):
        """Actuator failures are processed and DB is updated."""
        esp_id = "ESP_TEST"
        config_type = "actuator"
        failures = [
            {
                "type": "actuator",
                "gpio": 18,
                "error": "INIT_FAILED",
                "detail": "PWM channel unavailable",
            }
        ]

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.ESPRepository") as mock_esp_repo:
                mock_esp = MagicMock()
                mock_esp.id = 1
                mock_esp_repo.return_value.get_by_device_id = AsyncMock(return_value=mock_esp)

                with patch("src.mqtt.handlers.config_handler.SensorRepository"):
                    with patch(
                        "src.mqtt.handlers.config_handler.ActuatorRepository"
                    ) as mock_actuator_repo:
                        mock_actuator = MagicMock()
                        mock_actuator.id = 20
                        mock_actuator_repo.return_value.get_by_esp_and_gpio = AsyncMock(
                            return_value=mock_actuator
                        )
                        mock_actuator_repo.return_value.update = AsyncMock()

                        await handler._process_config_failures(esp_id, config_type, failures)

                        # Actuator should be updated with failed status
                        mock_actuator_repo.return_value.update.assert_called_once()


class TestCorrelationId:
    """Test correlation ID handling."""

    @pytest.fixture
    def handler(self):
        return ConfigHandler()

    @pytest.mark.asyncio
    async def test_correlation_id_passed_to_audit(self, handler):
        """Correlation ID is passed to audit log."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        correlation_id = "corr-12345-abc"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 2,
            "correlation_id": correlation_id,
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.log_config_response = AsyncMock()
                mock_repo_class.return_value = mock_repo

                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=AsyncMock())

                    result = await handler.handle_config_ack(topic, payload)

                    assert result is True
                    # Verify correlation_id was passed
                    mock_repo.log_config_response.assert_called_once()
                    call_kwargs = mock_repo.log_config_response.call_args
                    assert call_kwargs.kwargs.get("correlation_id") == correlation_id

    @pytest.mark.asyncio
    async def test_request_id_projected_to_websocket_payload(self, handler):
        """Optional request_id is projected into config_response data payload."""
        topic = "kaiser/god/esp/ESP_TEST/config_response"
        payload = {
            "status": "success",
            "type": "sensor",
            "count": 1,
            "correlation_id": "corr-req-test",
            "request_id": "req-42",
        }

        with patch("src.mqtt.handlers.config_handler.resilient_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.mqtt.handlers.config_handler.AuditLogRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.log_config_response = AsyncMock()
                mock_repo_class.return_value = mock_repo

                ws_manager = AsyncMock()
                ws_manager.broadcast = AsyncMock()
                with patch("src.websocket.manager.WebSocketManager") as mock_ws:
                    mock_ws.get_instance = AsyncMock(return_value=ws_manager)

                    result = await handler.handle_config_ack(topic, payload)

                    assert result is True
                    ws_manager.broadcast.assert_awaited_once()
                    event_type, event_payload = ws_manager.broadcast.await_args.args
                    assert event_type == "config_response"
                    assert event_payload["request_id"] == "req-42"
                    assert (
                        ws_manager.broadcast.await_args.kwargs.get("correlation_id")
                        == payload["correlation_id"]
                    )
