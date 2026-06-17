from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.actuator_response_handler import ActuatorResponseHandler
from src.mqtt.handlers.config_handler import ConfigHandler
from src.mqtt.handlers.diagnostics_handler import DiagnosticsHandler
from src.mqtt.handlers.error_handler import ErrorEventHandler
from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler
from src.mqtt.handlers.lwt_handler import LWTHandler
from src.services.device_response_contract import CONTRACT_UNKNOWN_CODE as DEVICE_UNKNOWN
from src.services.system_event_contract import CONTRACT_UNKNOWN_CODE as SYSTEM_UNKNOWN


def _session_cm(session: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_t1_config_response_unknown_contract_visible_and_stable():
    handler = ConfigHandler()
    topic = "kaiser/god/esp/ESP_T1/config_response"
    payload = {
        "status": "mystery_state",
        "type": "mystery_type",
        "message": "raw-unknown",
    }

    authority_session = MagicMock()
    authority_session.commit = AsyncMock()
    audit_session = MagicMock()
    audit_session.commit = AsyncMock()

    ws = AsyncMock()
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), False)
    )
    audit_repo = MagicMock()
    audit_repo.log_config_response = AsyncMock()

    with (
        patch(
            "src.mqtt.handlers.config_handler.resilient_session",
            side_effect=[_session_cm(authority_session), _session_cm(audit_session)],
        ),
        patch(
            "src.mqtt.handlers.config_handler.CommandContractRepository", return_value=contract_repo
        ),
        patch("src.mqtt.handlers.config_handler.AuditLogRepository", return_value=audit_repo),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_config_ack(topic, payload)

    assert result is True
    kwargs = contract_repo.upsert_terminal_event_authority.await_args.kwargs
    assert kwargs["code"] == DEVICE_UNKNOWN
    assert kwargs["reason"] == "raw-unknown"
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "config_response"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["raw_status"] == "mystery_state"


@pytest.mark.asyncio
async def test_t2_actuator_response_unknown_contract_visible_and_stable():
    handler = ActuatorResponseHandler()
    topic = "kaiser/god/esp/ESP_T2/actuator/12/response"
    payload = {
        "esp_id": "ESP_OTHER",
        "gpio": 99,
        "command": "on",
        "value": 1,
        "success": "unknown",
        "ts": int(datetime.now(timezone.utc).timestamp()),
    }

    session = MagicMock()
    session.commit = AsyncMock()
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), False)
    )
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(
        return_value=SimpleNamespace(id="esp-uuid", name="ESP_T2")
    )
    actuator_repo = MagicMock()
    actuator_repo.log_command = AsyncMock()
    audit_repo = MagicMock()
    audit_repo.log_actuator_command = AsyncMock()
    ws = AsyncMock()

    with (
        patch(
            "src.mqtt.handlers.actuator_response_handler.resilient_session",
            return_value=_session_cm(session),
        ),
        patch(
            "src.mqtt.handlers.actuator_response_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch("src.mqtt.handlers.actuator_response_handler.ESPRepository", return_value=esp_repo),
        patch(
            "src.mqtt.handlers.actuator_response_handler.ActuatorRepository",
            return_value=actuator_repo,
        ),
        patch("src.db.repositories.audit_log_repo.AuditLogRepository", return_value=audit_repo),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_actuator_response(topic, payload)

    assert result is True
    kwargs = contract_repo.upsert_terminal_event_authority.await_args.kwargs
    assert kwargs["code"] == DEVICE_UNKNOWN
    assert kwargs["outcome"] == "failed"
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "actuator_response"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["code"] == DEVICE_UNKNOWN


@pytest.mark.asyncio
async def test_t3_heartbeat_unknown_system_state_visible_without_drop():
    handler = HeartbeatHandler()
    topic = "kaiser/god/esp/ESP_T3/system/heartbeat"
    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "ts": now_ts,
        "uptime": 123,
        "heap_free": 40000,
        "wifi_rssi": -55,
        "system_state": "alien_state",
    }

    session = MagicMock()
    session.commit = AsyncMock()
    nested = MagicMock()
    nested.commit = AsyncMock()
    session.begin_nested = AsyncMock(return_value=nested)

    esp_device = SimpleNamespace(
        id="esp-uuid",
        device_id="ESP_T3",
        status="online",
        zone_id=None,
        last_seen=datetime.now(timezone.utc),
        device_metadata={},
        hardware_type="ESP32_WROOM",
        capabilities={},
    )
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
    esp_repo.update_status = AsyncMock()
    heartbeat_repo = MagicMock()
    heartbeat_repo.log_heartbeat = AsyncMock()
    ws = AsyncMock()
    mqtt_client = MagicMock()
    mqtt_client.publish = MagicMock(return_value=True)

    with (
        patch(
            "src.mqtt.handlers.heartbeat_handler.resilient_session",
            return_value=_session_cm(session),
        ),
        patch("src.mqtt.handlers.heartbeat_handler.ESPRepository", return_value=esp_repo),
        patch(
            "src.mqtt.handlers.heartbeat_handler.ESPHeartbeatRepository",
            return_value=heartbeat_repo,
        ),
        patch.object(handler, "_send_heartbeat_ack", AsyncMock(return_value=True)),
        patch.object(handler, "_has_pending_config", AsyncMock(return_value=False)),
        patch.object(handler, "_update_esp_metadata", AsyncMock(return_value=None)),
        patch.object(handler, "_log_health_metrics", MagicMock()),
        patch("src.mqtt.client.MQTTClient.get_instance", MagicMock(return_value=mqtt_client)),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_heartbeat(topic, payload)

    assert result is True
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "esp_health"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["contract_code"] == SYSTEM_UNKNOWN
    assert ws_payload["raw_system_state"] == "alien_state"


@pytest.mark.asyncio
async def test_t4_lwt_unknown_reason_visible_and_terminal_authority_kept():
    handler = LWTHandler()
    topic = "kaiser/god/esp/ESP_T4/system/will"
    payload = {
        "status": "offline",
        "reason": "alien_disconnect",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }

    session = MagicMock()
    session.commit = AsyncMock()
    esp_device = SimpleNamespace(
        id="esp-uuid",
        device_id="ESP_T4",
        status="online",
        device_metadata={},
        last_seen=datetime.now(timezone.utc),
    )
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
    esp_repo.update_status = AsyncMock()
    contract_repo = MagicMock()
    contract_repo.upsert_terminal_event_authority = AsyncMock(
        return_value=(SimpleNamespace(), False)
    )
    actuator_repo = MagicMock()
    actuator_repo.get_active_actuators_for_device = AsyncMock(return_value=[])
    actuator_repo.reset_states_for_device = AsyncMock(return_value=0)
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()
    ws = AsyncMock()

    with (
        patch("src.mqtt.handlers.lwt_handler.resilient_session", return_value=_session_cm(session)),
        patch("src.mqtt.handlers.lwt_handler.ESPRepository", return_value=esp_repo),
        patch(
            "src.mqtt.handlers.lwt_handler.CommandContractRepository", return_value=contract_repo
        ),
        patch("src.mqtt.handlers.lwt_handler.ActuatorRepository", return_value=actuator_repo),
        patch("src.mqtt.handlers.lwt_handler.AuditLogRepository", return_value=audit_repo),
        patch(
            "src.mqtt.handlers.lwt_handler.get_state_adoption_service",
            return_value=SimpleNamespace(clear_cycle=AsyncMock()),
        ),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_lwt(topic, payload)

    assert result is True
    kwargs = contract_repo.upsert_terminal_event_authority.await_args.kwargs
    assert kwargs["event_class"] == "lwt"
    assert kwargs["is_final"] is True
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "esp_health"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["contract_code"] == SYSTEM_UNKNOWN
    assert ws_payload["raw_reason"] == "alien_disconnect"


@pytest.mark.asyncio
async def test_t5_diagnostics_unknown_state_visible_and_persisted():
    handler = DiagnosticsHandler()
    topic = "kaiser/god/esp/ESP_T5/system/diagnostics"
    payload = {
        "heap_free": 120000,
        "wifi_rssi": -62,
        "system_state": "mystery_mode",
        "ts": int(datetime.now(timezone.utc).timestamp()),
    }

    session = MagicMock()
    session.commit = AsyncMock()
    esp_device = SimpleNamespace(device_metadata={})
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)
    ws = AsyncMock()

    with (
        patch(
            "src.mqtt.handlers.diagnostics_handler.resilient_session",
            return_value=_session_cm(session),
        ),
        patch("src.mqtt.handlers.diagnostics_handler.ESPRepository", return_value=esp_repo),
        patch("src.mqtt.handlers.diagnostics_handler.flag_modified", MagicMock()),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_diagnostics(topic, payload)

    assert result is True
    assert esp_device.device_metadata["diagnostics"]["contract_violation"] is True
    assert esp_device.device_metadata["diagnostics"]["contract_code"] == SYSTEM_UNKNOWN
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "esp_diagnostics"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["raw_system_state"] == "mystery_mode"


@pytest.mark.asyncio
async def test_t6_error_event_unknown_fields_visible_without_pipeline_break():
    handler = ErrorEventHandler()
    topic = "kaiser/god/esp/ESP_T6/system/error"
    payload = {
        "error_code": 1023,
        "severity": "fatal-plus",
        "category": "invalid-category",
        "message": "raw firmware message",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }

    session = MagicMock()
    session.commit = AsyncMock()
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(return_value=SimpleNamespace(name="ESP_T6"))
    audit_repo = MagicMock()
    audit_repo.log_mqtt_error = AsyncMock(return_value=SimpleNamespace(id="audit-1"))
    ws = AsyncMock()

    with (
        patch(
            "src.mqtt.handlers.error_handler.resilient_session", return_value=_session_cm(session)
        ),
        patch("src.mqtt.handlers.error_handler.ESPRepository", return_value=esp_repo),
        patch("src.mqtt.handlers.error_handler.AuditLogRepository", return_value=audit_repo),
        patch("src.mqtt.handlers.error_handler.get_error_info", MagicMock(return_value=None)),
        patch("src.websocket.manager.WebSocketManager.get_instance", AsyncMock(return_value=ws)),
    ):
        result = await handler.handle_error_event(topic, payload)

    assert result is True
    log_kwargs = audit_repo.log_mqtt_error.await_args.kwargs
    assert log_kwargs["error_code"] == SYSTEM_UNKNOWN
    details = log_kwargs["details"]
    assert details["contract_violation"] is True
    assert details["raw_severity"] == "fatal-plus"
    event_name, ws_payload = ws.broadcast.await_args.args
    assert event_name == "error_event"
    assert ws_payload["contract_violation"] is True
    assert ws_payload["contract_code"] == SYSTEM_UNKNOWN
