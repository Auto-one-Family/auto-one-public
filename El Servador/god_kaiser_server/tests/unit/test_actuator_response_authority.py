from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.actuator_response_handler import ActuatorResponseHandler


@pytest.mark.asyncio
async def test_stale_terminal_event_skips_history_write():
    handler = ActuatorResponseHandler()
    topic = "kaiser/god/esp/ESP_TEST/actuator/5/response"
    payload = {
        "esp_id": "ESP_TEST",
        "gpio": 5,
        "command": "ON",
        "value": 1.0,
        "success": True,
        "message": "ok",
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "correlation_id": "corr-stale-actuator",
    }

    with patch("src.mqtt.handlers.actuator_response_handler.resilient_session") as mock_session:
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.mqtt.handlers.actuator_response_handler.CommandContractRepository"
        ) as mock_contract_repo_class:
            mock_contract_repo = MagicMock()
            mock_contract_repo.upsert_terminal_event_authority = AsyncMock(
                return_value=(MagicMock(), True)
            )
            mock_contract_repo_class.return_value = mock_contract_repo

            with patch(
                "src.mqtt.handlers.actuator_response_handler.ESPRepository"
            ) as mock_esp_repo_class:
                mock_esp_repo = MagicMock()
                mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="esp-uuid"))
                mock_esp_repo_class.return_value = mock_esp_repo

                with patch(
                    "src.mqtt.handlers.actuator_response_handler.ActuatorRepository"
                ) as mock_actuator_repo_class:
                    mock_actuator_repo = MagicMock()
                    mock_actuator_repo.log_command = AsyncMock()
                    mock_actuator_repo_class.return_value = mock_actuator_repo

                    result = await handler.handle_actuator_response(topic, payload)

                    assert result is True
                    mock_actuator_repo.log_command.assert_not_called()


@pytest.mark.asyncio
async def test_non_stale_terminal_event_writes_history():
    handler = ActuatorResponseHandler()
    topic = "kaiser/god/esp/ESP_TEST/actuator/5/response"
    payload = {
        "esp_id": "ESP_TEST",
        "gpio": 5,
        "command": "ON",
        "value": 1.0,
        "success": True,
        "message": "ok",
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "correlation_id": "corr-fresh-actuator",
    }

    with patch("src.mqtt.handlers.actuator_response_handler.resilient_session") as mock_session:
        mock_db = MagicMock()
        mock_db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.mqtt.handlers.actuator_response_handler.CommandContractRepository"
        ) as mock_contract_repo_class:
            mock_contract_repo = MagicMock()
            mock_contract_repo.upsert_terminal_event_authority = AsyncMock(
                return_value=(MagicMock(), False)
            )
            mock_contract_repo_class.return_value = mock_contract_repo

            with patch(
                "src.mqtt.handlers.actuator_response_handler.ESPRepository"
            ) as mock_esp_repo_class:
                mock_esp_repo = MagicMock()
                mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="esp-uuid"))
                mock_esp_repo_class.return_value = mock_esp_repo

                with patch(
                    "src.mqtt.handlers.actuator_response_handler.ActuatorRepository"
                ) as mock_actuator_repo_class:
                    mock_actuator_repo = MagicMock()
                    mock_actuator_repo.log_command = AsyncMock()
                    mock_actuator_repo_class.return_value = mock_actuator_repo

                    with patch(
                        "src.db.repositories.audit_log_repo.AuditLogRepository"
                    ) as mock_audit_repo_class:
                        mock_audit_repo = MagicMock()
                        mock_audit_repo.log_actuator_command = AsyncMock()
                        mock_audit_repo_class.return_value = mock_audit_repo

                        with patch("src.websocket.manager.WebSocketManager") as mock_ws_class:
                            mock_ws = AsyncMock()
                            mock_ws_class.get_instance = AsyncMock(return_value=mock_ws)

                            result = await handler.handle_actuator_response(topic, payload)

                            assert result is True
                            mock_actuator_repo.log_command.assert_called_once()
                            mock_ws.broadcast.assert_called_once()
                            args, kwargs = mock_ws.broadcast.await_args
                            assert args[0] == "actuator_response"
                            assert isinstance(args[1], dict)
                            assert kwargs.get("correlation_id") == payload["correlation_id"]
