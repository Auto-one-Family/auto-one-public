"""
Integration Tests: Alert Suppression Scheduler Tasks

Phase 4A Test-Suite (STEP 4, Block 7a)
Tests: Suppression expiry re-enable, not-expired stays, maintenance overdue notification
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.actuator import ActuatorConfig
from src.db.models.notification import Notification

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sensor_with_expired_suppression(db_session: AsyncSession, sample_esp_device):
    """Create a sensor whose suppression_until is in the past."""
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Expired Suppression Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "calibration",
            "suppression_until": past,
        },
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def sensor_with_future_suppression(db_session: AsyncSession, sample_esp_device):
    """Create a sensor whose suppression_until is in the future."""
    future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=35,
        sensor_type="ph",
        sensor_name="Future Suppression Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "maintenance",
            "suppression_until": future,
        },
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def sensor_with_overdue_maintenance(db_session: AsyncSession, sample_esp_device):
    """Create a sensor with overdue maintenance."""
    past_maintenance = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=36,
        sensor_type="ec",
        sensor_name="Overdue Maintenance Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        sensor_metadata={
            "last_maintenance": past_maintenance,
            "maintenance_interval_days": 30,
        },
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


# =============================================================================
# Test 1: Expiry Re-Enable
# =============================================================================


@pytest.mark.asyncio
async def test_suppression_expiry_re_enables(
    db_session,
    sample_esp_device,
    sensor_with_expired_suppression,
):
    """Sensor with expired suppression_until → alerts_enabled set back to True."""
    from contextlib import asynccontextmanager
    from sqlalchemy import select
    from src.db.models.sensor import SensorConfig
    from src.services.alert_suppression_scheduler import check_suppression_expiry

    sensor_id = sensor_with_expired_suppression.id

    # Mock get_session_maker: returns a factory whose () returns an async ctx manager
    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    def mock_factory():
        return mock_session_ctx()

    with patch(
        "src.services.alert_suppression_scheduler.get_session_maker",
        return_value=mock_factory,
    ):
        await check_suppression_expiry()

    # Expire all cached state so the next query hits the DB
    db_session.expire_all()

    # Re-load the sensor from DB to verify changes
    stmt = select(SensorConfig).where(SensorConfig.id == sensor_id)
    result = await db_session.execute(stmt)
    reloaded = result.scalar_one()

    cfg = reloaded.alert_config or {}
    assert cfg.get("alerts_enabled") is True
    assert "suppression_until" not in cfg
    assert "suppression_reason" not in cfg


# =============================================================================
# Test 2: Not-Expired Stays Suppressed
# =============================================================================


@pytest.mark.asyncio
async def test_suppression_not_expired_stays(
    db_session,
    sample_esp_device,
    sensor_with_future_suppression,
):
    """Sensor with future suppression_until → stays suppressed."""
    from contextlib import asynccontextmanager
    from src.services.alert_suppression_scheduler import check_suppression_expiry

    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    def mock_factory():
        return mock_session_ctx()

    with patch(
        "src.services.alert_suppression_scheduler.get_session_maker",
        return_value=mock_factory,
    ):
        await check_suppression_expiry()

    # Refresh and verify still suppressed
    await db_session.refresh(sensor_with_future_suppression)
    cfg = sensor_with_future_suppression.alert_config or {}
    assert cfg.get("alerts_enabled") is False
    assert "suppression_until" in cfg


# =============================================================================
# Test 3: Maintenance Overdue Notification
# =============================================================================


@pytest.mark.asyncio
async def test_maintenance_overdue_sends_notification(
    db_session,
    sample_esp_device,
    sensor_with_overdue_maintenance,
    sample_user,
):
    """Sensor with overdue maintenance → notification created via router."""
    from contextlib import asynccontextmanager
    from sqlalchemy import select
    from src.services.alert_suppression_scheduler import check_maintenance_overdue

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()

    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    def mock_factory():
        return mock_session_ctx()

    with (
        patch(
            "src.services.alert_suppression_scheduler.get_session_maker",
            return_value=mock_factory,
        ),
        patch(
            "src.websocket.manager.WebSocketManager.get_instance",
            return_value=mock_ws,
        ),
    ):
        await check_maintenance_overdue()

    # Verify maintenance notification was created
    stmt = select(Notification).where(
        Notification.category == "maintenance",
    )
    result = await db_session.execute(stmt)
    notifications = list(result.scalars().all())
    assert len(notifications) >= 1
    assert "Wartung" in notifications[0].title or "maintenance" in notifications[0].title.lower()
