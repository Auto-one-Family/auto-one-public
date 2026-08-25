"""AUT-1029: Oversize auto-push notify damping + board-aware budget."""

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.heartbeat_handler import (
    CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS,
    HeartbeatHandler,
)
from src.services.config_builder import (
    CONFIG_AUTOPUSH_BUDGET_BYTES,
    resolve_autopush_budget_bytes,
)


def test_resolve_autopush_budget_bytes_board_aware_uniform_4096() -> None:
    """AUT-1027: all boards share firmware ingress 4352 B → preflight 4096 B."""
    assert resolve_autopush_budget_bytes("ESP32_WROOM") == 4096
    assert resolve_autopush_budget_bytes("ESP32_S3_DEVKITC1") == 4096
    assert resolve_autopush_budget_bytes("XIAO_ESP32_C3") == 4096
    assert resolve_autopush_budget_bytes(None) == CONFIG_AUTOPUSH_BUDGET_BYTES
    assert resolve_autopush_budget_bytes("UNKNOWN_BOARD") == CONFIG_AUTOPUSH_BUDGET_BYTES


@pytest.mark.asyncio
async def test_oversize_auto_push_notifies_on_first_block() -> None:
    handler = HeartbeatHandler()
    session = AsyncMock()
    session.commit = AsyncMock()

    mock_dev = MagicMock()
    mock_dev.device_metadata = {}
    mock_repo = MagicMock()
    mock_repo.get_by_device_id = AsyncMock(return_value=mock_dev)

    mock_audit_repo = MagicMock()
    mock_audit_repo.create = AsyncMock()
    mock_ws = MagicMock()
    mock_ws.broadcast = AsyncMock()

    with (
        patch("src.mqtt.handlers.heartbeat_handler.ESPRepository", return_value=mock_repo),
        patch("src.mqtt.handlers.heartbeat_handler.AuditLogRepository", return_value=mock_audit_repo),
        patch(
            "src.websocket.manager.WebSocketManager.get_instance",
            new_callable=AsyncMock,
            return_value=mock_ws,
        ),
        patch("src.mqtt.handlers.heartbeat_handler.logger") as mock_logger,
    ):
        await handler._handle_oversize_auto_push(
            session=session,
            esp_device_id="ESP_TEST",
            reason_code="heartbeat_count_mismatch",
            estimated_wire_len=4308,
            budget_bytes=4096,
            sensor_count=3,
            actuator_count=5,
            offline_rules_count=4,
        )

    mock_logger.error.assert_called_once()
    mock_audit_repo.create.assert_awaited_once()
    mock_ws.broadcast.assert_awaited_once()
    assert "config_push_oversize_blocked_at" in mock_dev.device_metadata
    assert "config_push_sent_at" not in mock_dev.device_metadata or mock_dev.device_metadata.get(
        "config_push_sent_at"
    ) is None


@pytest.mark.asyncio
async def test_oversize_auto_push_damps_notify_within_cooldown() -> None:
    handler = HeartbeatHandler()
    session = AsyncMock()
    session.commit = AsyncMock()

    recent_blocked_at = int(time.time()) - 30
    mock_dev = MagicMock()
    mock_dev.device_metadata = {"config_push_oversize_blocked_at": recent_blocked_at}

    mock_repo = MagicMock()
    mock_repo.get_by_device_id = AsyncMock(return_value=mock_dev)

    with (
        patch("src.mqtt.handlers.heartbeat_handler.ESPRepository", return_value=mock_repo),
        patch("src.mqtt.handlers.heartbeat_handler.AuditLogRepository") as mock_audit_cls,
        patch("src.mqtt.handlers.heartbeat_handler.logger") as mock_logger,
    ):
        await handler._handle_oversize_auto_push(
            session=session,
            esp_device_id="ESP_TEST",
            reason_code="heartbeat_count_mismatch",
            estimated_wire_len=4308,
            budget_bytes=4096,
            sensor_count=3,
            actuator_count=5,
            offline_rules_count=4,
        )

    mock_logger.error.assert_not_called()
    mock_audit_cls.assert_not_called()
    mock_logger.debug.assert_called()
    assert mock_dev.device_metadata["config_push_oversize_blocked_at"] == recent_blocked_at


@pytest.mark.asyncio
async def test_oversize_auto_push_renotifies_after_cooldown_expired() -> None:
    handler = HeartbeatHandler()
    session = AsyncMock()
    session.commit = AsyncMock()

    stale_blocked_at = int(time.time()) - CONFIG_OVERSIZE_NOTIFY_COOLDOWN_SECONDS - 1
    mock_dev = MagicMock()
    mock_dev.device_metadata = {"config_push_oversize_blocked_at": stale_blocked_at}

    mock_repo = MagicMock()
    mock_repo.get_by_device_id = AsyncMock(return_value=mock_dev)

    mock_audit_repo = MagicMock()
    mock_audit_repo.create = AsyncMock()

    with (
        patch("src.mqtt.handlers.heartbeat_handler.ESPRepository", return_value=mock_repo),
        patch("src.mqtt.handlers.heartbeat_handler.AuditLogRepository", return_value=mock_audit_repo),
        patch("src.mqtt.handlers.heartbeat_handler.logger") as mock_logger,
        patch(
            "src.websocket.manager.WebSocketManager.get_instance",
            new_callable=AsyncMock,
            return_value=MagicMock(broadcast=AsyncMock()),
        ),
    ):
        await handler._handle_oversize_auto_push(
            session=session,
            esp_device_id="ESP_TEST",
            reason_code="heartbeat_count_mismatch",
            estimated_wire_len=4308,
            budget_bytes=4096,
            sensor_count=3,
            actuator_count=5,
            offline_rules_count=4,
        )

    mock_logger.error.assert_called_once()
    mock_audit_repo.create.assert_awaited_once()
    assert mock_dev.device_metadata["config_push_oversize_blocked_at"] > stale_blocked_at


@pytest.mark.asyncio
async def test_auto_push_config_clears_oversize_metadata_on_recovery() -> None:
    handler = HeartbeatHandler()
    session = AsyncMock()
    session.commit = AsyncMock()

    mock_dev = MagicMock()
    mock_dev.hardware_type = "ESP32_S3_DEVKITC1"
    mock_dev.device_metadata = {
        "config_push_oversize_blocked_at": int(time.time()) - 600,
        "config_push_oversize_reason_code": "heartbeat_count_mismatch",
        "config_push_oversize_snapshot": {"estimated_wire_len": 4308},
    }

    mock_repo = MagicMock()
    mock_repo.get_by_device_id = AsyncMock(return_value=mock_dev)

    mock_builder = MagicMock()
    mock_builder.build_combined_config = AsyncMock(return_value={"sensors": [], "actuators": []})

    mock_esp_service = MagicMock()
    mock_esp_service.send_config = AsyncMock(return_value={"success": True})

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.heartbeat_handler.resilient_session",
            fake_resilient_session,
        ),
        patch("src.mqtt.handlers.heartbeat_handler.ESPRepository", return_value=mock_repo),
        patch(
            "src.services.config_builder.ConfigPayloadBuilder",
            return_value=mock_builder,
        ),
        patch(
            "src.services.config_builder.estimate_config_wire_size",
            return_value=3000,
        ),
        patch("src.services.esp_service.ESPService", return_value=mock_esp_service),
    ):
        await handler._auto_push_config("ESP_TEST", reason_code="heartbeat_count_mismatch")

    assert "config_push_oversize_blocked_at" not in mock_dev.device_metadata
    mock_esp_service.send_config.assert_awaited_once()
