"""
Integration Tests: Threshold → Notification Pipeline

Phase 4A Test-Suite (STEP 4, Block 6)
Tests: Sensor value → threshold check → NotificationRouter pipeline
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.notification import Notification
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.mqtt.handlers.sensor_handler import SensorDataHandler

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def pipeline_user(db_session: AsyncSession):
    """Create a user for notification routing."""
    user = User(
        username="pipeline_user",
        email="pipeline@example.com",
        password_hash="hashed_pw",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def pipeline_esp(db_session: AsyncSession):
    """Create an ESP device for pipeline testing."""
    device = ESPDevice(
        device_id="ESP_PIPELINE",
        name="Pipeline Test ESP",
        ip_address="192.168.1.250",
        mac_address="AA:BB:CC:DD:EE:PP",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest.fixture
async def pipeline_sensor(db_session: AsyncSession, pipeline_esp):
    """Create a sensor with thresholds for pipeline testing."""
    sensor = SensorConfig(
        esp_id=pipeline_esp.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Pipeline Temp Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        thresholds={
            "warning_min": 5.0,
            "warning_max": 35.0,
            "critical_min": 0.0,
            "critical_max": 40.0,
        },
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def suppressed_pipeline_sensor(db_session: AsyncSession, pipeline_esp):
    """Create a sensor that is suppressed (for audit trail test)."""
    sensor = SensorConfig(
        esp_id=pipeline_esp.id,
        gpio=35,
        sensor_type="ph",
        sensor_name="Suppressed pH Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        thresholds={
            "warning_min": 5.5,
            "warning_max": 7.5,
            "critical_min": 4.0,
            "critical_max": 9.0,
        },
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "calibration",
        },
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def sensor_no_thresholds(db_session: AsyncSession, pipeline_esp):
    """Create a sensor WITHOUT thresholds."""
    sensor = SensorConfig(
        esp_id=pipeline_esp.id,
        gpio=36,
        sensor_type="moisture",
        sensor_name="No Threshold Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


# =============================================================================
# Test 1: Threshold Exceeded → Notification Created
# =============================================================================


@pytest.mark.asyncio
async def test_threshold_exceeded_creates_notification(
    db_session,
    pipeline_esp,
    pipeline_sensor,
    pipeline_user,
):
    """Value over critical_max → router.route() called with severity='critical'."""
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()

    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        handler = SensorDataHandler.__new__(SensorDataHandler)
        await handler._evaluate_thresholds_and_notify(
            session=db_session,
            sensor_config=pipeline_sensor,
            esp_id_str="ESP_PIPELINE",
            gpio=34,
            sensor_type="temperature",
            value=45.0,  # Above critical_max (40.0)
        )
        await db_session.commit()

    # Verify notification was created
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.source == "sensor_threshold",
        Notification.severity == "critical",
    )
    result = await db_session.execute(stmt)
    notifications = list(result.scalars().all())
    assert len(notifications) >= 1


# =============================================================================
# Test 2: Suppressed Sensor → persist_suppressed
# =============================================================================


@pytest.mark.asyncio
async def test_suppressed_sensor_persists_suppressed(
    db_session,
    pipeline_esp,
    suppressed_pipeline_sensor,
    pipeline_user,
):
    """Suppressed sensor → persist_suppressed() instead of route()."""
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()

    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        handler = SensorDataHandler.__new__(SensorDataHandler)
        await handler._evaluate_thresholds_and_notify(
            session=db_session,
            sensor_config=suppressed_pipeline_sensor,
            esp_id_str="ESP_PIPELINE",
            gpio=35,
            sensor_type="ph",
            value=10.0,  # Above critical_max (9.0)
        )
        await db_session.commit()

    # Verify suppressed notification was persisted
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.channel == "suppressed",
    )
    result = await db_session.execute(stmt)
    suppressed = list(result.scalars().all())
    assert len(suppressed) >= 1
    assert "[Suppressed]" in suppressed[0].title


# =============================================================================
# Test 3: Severity Override from alert_config
# =============================================================================


@pytest.mark.asyncio
async def test_severity_override_from_alert_config(
    db_session,
    pipeline_esp,
    pipeline_sensor,
    pipeline_user,
):
    """severity_override in alert_config overrides calculated severity."""
    # Set severity override
    pipeline_sensor.alert_config = {
        "alerts_enabled": True,
        "severity_override": "warning",
    }

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()

    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        handler = SensorDataHandler.__new__(SensorDataHandler)
        await handler._evaluate_thresholds_and_notify(
            session=db_session,
            sensor_config=pipeline_sensor,
            esp_id_str="ESP_PIPELINE",
            gpio=34,
            sensor_type="temperature",
            value=45.0,  # Would normally be critical
        )
        await db_session.commit()

    # Verify notification used overridden severity
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.source == "sensor_threshold",
        Notification.severity == "warning",  # Overridden from critical
    )
    result = await db_session.execute(stmt)
    notifications = list(result.scalars().all())
    assert len(notifications) >= 1


# =============================================================================
# Test 4: No Threshold → No Notification
# =============================================================================


@pytest.mark.asyncio
async def test_no_threshold_no_notification(
    db_session,
    pipeline_esp,
    sensor_no_thresholds,
    pipeline_user,
):
    """No thresholds configured → no notification created."""
    handler = SensorDataHandler.__new__(SensorDataHandler)
    await handler._evaluate_thresholds_and_notify(
        session=db_session,
        sensor_config=sensor_no_thresholds,
        esp_id_str="ESP_PIPELINE",
        gpio=36,
        sensor_type="moisture",
        value=50.0,
    )

    # No notifications should have been created
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.source == "sensor_threshold",
    )
    result = await db_session.execute(stmt)
    notifications = list(result.scalars().all())
    # Filter to only notifications for this specific test
    for n in notifications:
        meta = n.extra_data or {}
        assert meta.get("gpio") != 36 or meta.get("sensor_type") != "moisture"


# =============================================================================
# Test 5: Pipeline Error Non-Blocking
# =============================================================================


@pytest.mark.asyncio
async def test_pipeline_error_non_blocking(
    db_session,
    pipeline_esp,
    pipeline_sensor,
    pipeline_user,
):
    """Error in notification pipeline does NOT block sensor data commit."""
    # Mock NotificationRouter.route to raise an exception
    # NotificationRouter is imported inside _evaluate_thresholds_and_notify,
    # so we patch at its source module
    with patch("src.services.notification_router.NotificationRouter") as MockRouter:
        mock_router_instance = AsyncMock()
        mock_router_instance.route = AsyncMock(side_effect=Exception("DB connection lost"))
        mock_router_instance.persist_suppressed = AsyncMock(
            side_effect=Exception("DB connection lost")
        )
        MockRouter.return_value = mock_router_instance

        handler = SensorDataHandler.__new__(SensorDataHandler)

        # This should NOT raise — the exception is caught internally
        try:
            await handler._evaluate_thresholds_and_notify(
                session=db_session,
                sensor_config=pipeline_sensor,
                esp_id_str="ESP_PIPELINE",
                gpio=34,
                sensor_type="temperature",
                value=45.0,
            )
        except Exception:
            pytest.fail("Pipeline error should not propagate — must be non-blocking")
