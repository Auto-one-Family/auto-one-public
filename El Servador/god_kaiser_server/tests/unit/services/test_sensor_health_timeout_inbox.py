"""AUT-1562: Timeout-stale enters the existing freshness inbox chain."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import MaintenanceSettings
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig, SensorData
from src.schemas.notification import NOTIFICATION_SOURCES
from src.services.maintenance.jobs.sensor_health import check_sensor_timeouts


def _settings() -> MaintenanceSettings:
    return MaintenanceSettings()


async def _online_continuous_sensor(
    db_session: AsyncSession,
    *,
    last_reading_at: datetime | None,
) -> ESPDevice:
    device = ESPDevice(
        device_id="ESP_TIMEOUT_01",
        name="Timeout ESP",
        ip_address="192.168.1.90",
        mac_address="AA:BB:CC:DD:EE:90",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    sensor = SensorConfig(
        esp_id=device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Luft temp",
        enabled=True,
        operating_mode="continuous",
        timeout_seconds=60,
        timeout_warning_enabled=True,
    )
    db_session.add(sensor)
    await db_session.flush()
    if last_reading_at is not None:
        db_session.add(
            SensorData(
                esp_id=device.id,
                gpio=34,
                sensor_type="temperature",
                raw_value=21.0,
                processed_value=21.0,
                unit="C",
                processing_mode="raw",
                quality="good",
                timestamp=last_reading_at,
                data_source="test",
            )
        )
        await db_session.flush()
    return device


@pytest.mark.asyncio
async def test_timeout_stale_routes_existing_freshness_reminder(
    db_session: AsyncSession,
) -> None:
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=180)
    await _online_continuous_sensor(db_session, last_reading_at=stale_at)
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()
    routed: list = []

    async def _capture(notification):
        routed.append(notification)
        return MagicMock()

    with patch(
        "src.services.notification_router.NotificationRouter"
    ) as mock_router_cls:
        mock_router_cls.return_value.route = AsyncMock(side_effect=_capture)
        result = await check_sensor_timeouts(db_session, _settings(), ws_manager)

    assert result["sensors_stale"] == 1
    ws_manager.broadcast.assert_awaited()
    assert routed, "timeout must enter NotificationRouter"
    notification = routed[0]
    assert notification.source == "freshness_reminder"
    assert notification.category == "data_quality"
    assert notification.severity == "warning"
    assert notification.fingerprint == "freshness_ESP_TIMEOUT_01_34_temperature"
    assert "timeout_stale" not in NOTIFICATION_SOURCES
    assert "sensor_timeout" not in NOTIFICATION_SOURCES


@pytest.mark.asyncio
async def test_timeout_healthy_does_not_route_inbox(
    db_session: AsyncSession,
) -> None:
    fresh_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await _online_continuous_sensor(db_session, last_reading_at=fresh_at)
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()

    with patch(
        "src.services.notification_router.NotificationRouter"
    ) as mock_router_cls:
        mock_router_cls.return_value.route = AsyncMock()
        result = await check_sensor_timeouts(db_session, _settings(), ws_manager)

    assert result["sensors_stale"] == 0
    mock_router_cls.return_value.route.assert_not_awaited()
    ws_manager.broadcast.assert_not_awaited()


def test_no_new_notification_source_for_timeout() -> None:
    assert "freshness_reminder" in NOTIFICATION_SOURCES
    assert "timeout" not in NOTIFICATION_SOURCES
    assert "timeout_exceeded" not in NOTIFICATION_SOURCES
    assert "sensor_health" not in NOTIFICATION_SOURCES
