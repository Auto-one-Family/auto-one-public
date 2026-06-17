from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.actuator_response_handler import ActuatorResponseHandler
from src.mqtt.handlers.config_handler import ConfigHandler
from src.mqtt.handlers.lwt_handler import LWTHandler


def _session_cm(session: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_config_stale_terminalization_increments_blocked_metric():
    handler = ConfigHandler()
    topic = "kaiser/god/esp/ESP_CFG/config_response"
    payload = {"status": "success", "type": "sensor", "message": "ok", "correlation_id": "corr-1"}

    authority_session = MagicMock()
    authority_session.commit = AsyncMock()
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), True)
    )

    with (
        patch(
            "src.mqtt.handlers.config_handler.resilient_session",
            side_effect=[_session_cm(authority_session)],
        ),
        patch(
            "src.mqtt.handlers.config_handler.CommandContractRepository", return_value=contract_repo
        ),
        patch(
            "src.mqtt.handlers.config_handler.increment_contract_terminalization_blocked"
        ) as blocked_metric,
    ):
        result = await handler.handle_config_ack(topic, payload)

    assert result is True
    blocked_metric.assert_called_once_with(
        event_class="config_response",
        reason="terminal_authority_guard",
    )


@pytest.mark.asyncio
async def test_actuator_stale_terminalization_increments_blocked_metric():
    handler = ActuatorResponseHandler()
    topic = "kaiser/god/esp/ESP_ACT/actuator/12/response"
    payload = {
        "esp_id": "ESP_ACT",
        "gpio": 12,
        "command": "ON",
        "value": 1,
        "success": True,
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "correlation_id": "corr-2",
    }

    session = MagicMock()
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), True)
    )

    with (
        patch(
            "src.mqtt.handlers.actuator_response_handler.resilient_session",
            return_value=_session_cm(session),
        ),
        patch(
            "src.mqtt.handlers.actuator_response_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.actuator_response_handler.increment_contract_terminalization_blocked"
        ) as blocked_metric,
    ):
        result = await handler.handle_actuator_response(topic, payload)

    assert result is True
    blocked_metric.assert_called_once_with(
        event_class="actuator_response",
        reason="terminal_authority_guard",
    )


@pytest.mark.asyncio
async def test_lwt_stale_terminalization_increments_blocked_metric():
    handler = LWTHandler()
    topic = "kaiser/god/esp/ESP_LWT/system/will"
    payload = {
        "status": "offline",
        "reason": "unexpected_disconnect",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "correlation_id": "corr-3",
    }

    session = MagicMock()
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(
        return_value=SimpleNamespace(
            id="esp-uuid",
            device_id="ESP_LWT",
            status="online",
            device_metadata={},
            last_seen=datetime.now(timezone.utc),
        )
    )
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), True)
    )

    with (
        patch("src.mqtt.handlers.lwt_handler.resilient_session", return_value=_session_cm(session)),
        patch("src.mqtt.handlers.lwt_handler.ESPRepository", return_value=esp_repo),
        patch(
            "src.mqtt.handlers.lwt_handler.CommandContractRepository", return_value=contract_repo
        ),
        patch(
            "src.mqtt.handlers.lwt_handler.increment_contract_terminalization_blocked"
        ) as blocked_metric,
    ):
        result = await handler.handle_lwt(topic, payload)

    assert result is True
    blocked_metric.assert_called_once_with(
        event_class="lwt",
        reason="terminal_authority_guard",
    )
