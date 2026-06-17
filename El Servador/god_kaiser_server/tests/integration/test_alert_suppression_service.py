"""
Integration Tests: AlertSuppressionService

Phase 4A Test-Suite (STEP 4, Block 4)
Tests: Sensor/device suppression, expiry, propagation, thresholds
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.services.alert_suppression_service import AlertSuppressionService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def suppressed_sensor(db_session: AsyncSession, sample_esp_device):
    """Create a sensor with alerts_enabled=False (suppressed)."""
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Suppressed Temp Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "maintenance",
        },
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def sensor_with_expired_suppression(db_session: AsyncSession, sample_esp_device):
    """Create a sensor with suppression_until in the past."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=35,
        sensor_type="ph",
        sensor_name="Expired Suppression Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "calibration",
            "suppression_until": past,
        },
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def normal_sensor_with_thresholds(db_session: AsyncSession, sample_esp_device):
    """Create a normal sensor with thresholds configured."""
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=36,
        sensor_type="temperature",
        sensor_name="Threshold Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        thresholds={
            "warning_min": 5.0,
            "warning_max": 35.0,
            "critical_min": 0.0,
            "critical_max": 40.0,
        },
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def suppressed_device(db_session: AsyncSession):
    """Create a device with suppression enabled and propagate_to_children."""
    device = ESPDevice(
        device_id="ESP_SUPPRESS",
        name="Suppressed ESP32",
        ip_address="192.168.1.200",
        mac_address="AA:BB:CC:DD:EE:AA",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
        alert_config={
            "alerts_enabled": False,
            "suppression_reason": "maintenance",
            "propagate_to_children": True,
        },
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest.fixture
async def child_sensor_of_suppressed_device(db_session: AsyncSession, suppressed_device):
    """Create a sensor belonging to suppressed device (alerts_enabled=True on sensor)."""
    sensor = SensorConfig(
        esp_id=suppressed_device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Child Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        alert_config={"alerts_enabled": True},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


# =============================================================================
# Test 1: Sensor Suppressed True
# =============================================================================


@pytest.mark.asyncio
async def test_is_sensor_suppressed_true(db_session, suppressed_sensor):
    """Sensor with alerts_enabled=False is suppressed."""
    service = AlertSuppressionService(db_session)
    is_suppressed, reason = await service.is_sensor_suppressed(suppressed_sensor)

    assert is_suppressed is True
    assert "maintenance" in reason


# =============================================================================
# Test 2: Sensor Suppression Expired
# =============================================================================


@pytest.mark.asyncio
async def test_is_sensor_suppressed_expiry(db_session, sensor_with_expired_suppression):
    """Sensor with suppression_until in the past is NOT suppressed."""
    service = AlertSuppressionService(db_session)
    is_suppressed, reason = await service.is_sensor_suppressed(sensor_with_expired_suppression)

    assert is_suppressed is False
    assert reason is None


# =============================================================================
# Test 3: Device-Level Propagation
# =============================================================================


@pytest.mark.asyncio
async def test_device_level_propagation(
    db_session, suppressed_device, child_sensor_of_suppressed_device
):
    """Device suppressed with propagate_to_children → child sensor also suppressed."""
    service = AlertSuppressionService(db_session)
    is_suppressed, reason = await service.is_sensor_suppressed(child_sensor_of_suppressed_device)

    assert is_suppressed is True
    assert "device:" in reason


# =============================================================================
# Test 4: Actuator Suppressed
# =============================================================================


@pytest.mark.asyncio
async def test_is_actuator_suppressed(db_session, sample_esp_device):
    """Actuator with alerts_enabled=False is suppressed."""
    # Create a mock actuator config
    actuator_config = MagicMock()
    actuator_config.alert_config = {
        "alerts_enabled": False,
        "suppression_reason": "intentionally_offline",
    }
    actuator_config.esp_id = sample_esp_device.id

    service = AlertSuppressionService(db_session)
    is_suppressed, reason = await service.is_actuator_suppressed(actuator_config)

    assert is_suppressed is True
    assert "intentionally_offline" in reason


# =============================================================================
# Test 5: Custom Thresholds Over Global
# =============================================================================


@pytest.mark.asyncio
async def test_get_effective_thresholds_custom_over_global(
    db_session, normal_sensor_with_thresholds
):
    """Custom thresholds from alert_config override global thresholds."""
    # Add custom thresholds to alert_config
    normal_sensor_with_thresholds.alert_config = {
        "alerts_enabled": True,
        "custom_thresholds": {
            "warning_min": 10.0,
            "warning_max": 30.0,
            "critical_min": 5.0,
            "critical_max": 35.0,
        },
    }

    service = AlertSuppressionService(db_session)
    thresholds = service.get_effective_thresholds(normal_sensor_with_thresholds)

    assert thresholds is not None
    assert thresholds["warning_max"] == 30.0  # Custom, not global 35.0
    assert thresholds["critical_max"] == 35.0  # Custom, not global 40.0


# =============================================================================
# Test 6: Check Thresholds — Critical Over Warning
# =============================================================================


def test_check_thresholds_critical_over_warning():
    """Value over critical_max → severity 'critical' (not 'warning')."""
    service = AlertSuppressionService.__new__(AlertSuppressionService)

    thresholds = {
        "warning_min": 5.0,
        "warning_max": 35.0,
        "critical_min": 0.0,
        "critical_max": 40.0,
    }

    # Value over critical_max
    severity = service.check_thresholds(45.0, thresholds)
    assert severity == "critical"

    # Value over warning_max but under critical_max
    severity = service.check_thresholds(37.0, thresholds)
    assert severity == "warning"

    # Value within bounds
    severity = service.check_thresholds(25.0, thresholds)
    assert severity is None
