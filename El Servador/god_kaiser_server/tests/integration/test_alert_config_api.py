"""
Integration Tests: Alert Config API Endpoints

Phase 4A Test-Suite (STEP 4, Block 7c)
Tests: Sensor/device alert-config PATCH/GET, JSONB merge, suppression_until
"""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user with JWT token."""
    user = User(
        username="alertconfig_operator",
        email="alertconfig_op@example.com",
        password_hash="hashed_pw",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    user.token = create_access_token(user_id=user.id, additional_claims={"role": user.role})
    return user


@pytest.fixture
async def alert_config_sensor(db_session: AsyncSession, sample_esp_device):
    """Create a sensor for alert config testing."""
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Alert Config Test Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        thresholds={
            "warning_min": 5.0,
            "warning_max": 35.0,
            "critical_min": 0.0,
            "critical_max": 40.0,
        },
        alert_config={"alerts_enabled": True},
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


# =============================================================================
# Test 1: PATCH Sensor Alert Config
# =============================================================================


@pytest.mark.asyncio
async def test_patch_sensor_alert_config(
    operator_user,
    sample_esp_device,
    alert_config_sensor,
):
    """PATCH /v1/sensors/{id}/alert-config updates suppression fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/sensors/{alert_config_sensor.id}/alert-config",
            json={
                "alerts_enabled": False,
                "suppression_reason": "calibration",
            },
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["alert_config"]["alerts_enabled"] is False
    assert data["alert_config"]["suppression_reason"] == "calibration"


# =============================================================================
# Test 2: GET Sensor Alert Config
# =============================================================================


@pytest.mark.asyncio
async def test_get_sensor_alert_config(
    operator_user,
    sample_esp_device,
    alert_config_sensor,
):
    """GET /v1/sensors/{id}/alert-config returns alert_config + thresholds."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/sensors/{alert_config_sensor.id}/alert-config",
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "alert_config" in data
    assert "thresholds" in data
    assert data["thresholds"]["warning_max"] == 35.0


# =============================================================================
# Test 3: PATCH Device Alert Config with propagate_to_children
# =============================================================================


@pytest.mark.asyncio
async def test_patch_device_alert_config_propagate(
    operator_user,
    sample_esp_device,
):
    """PATCH /v1/esp/devices/{esp_id}/alert-config with propagate_to_children."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/esp/devices/{sample_esp_device.device_id}/alert-config",
            json={
                "alerts_enabled": False,
                "suppression_reason": "maintenance",
                "propagate_to_children": True,
            },
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["alert_config"]["propagate_to_children"] is True
    assert data["alert_config"]["alerts_enabled"] is False


# =============================================================================
# Test 4: JSONB Merge — Partial Update
# =============================================================================


@pytest.mark.asyncio
async def test_alert_config_jsonb_merge(
    operator_user,
    sample_esp_device,
    alert_config_sensor,
):
    """Two successive PATCHes merge fields — second does not overwrite first."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First PATCH: set suppression_reason
        await client.patch(
            f"/api/v1/sensors/{alert_config_sensor.id}/alert-config",
            json={"suppression_reason": "maintenance"},
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

        # Second PATCH: set severity_override (should NOT remove suppression_reason)
        response = await client.patch(
            f"/api/v1/sensors/{alert_config_sensor.id}/alert-config",
            json={"severity_override": "warning"},
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    cfg = data["alert_config"]
    assert cfg["suppression_reason"] == "maintenance"  # From first PATCH
    assert cfg["severity_override"] == "warning"  # From second PATCH


# =============================================================================
# Test 5: Suppression with suppression_until
# =============================================================================


@pytest.mark.asyncio
async def test_alert_config_suppression_with_until(
    operator_user,
    sample_esp_device,
    alert_config_sensor,
):
    """PATCH with suppression_until stores ISO datetime for scheduler."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/sensors/{alert_config_sensor.id}/alert-config",
            json={
                "alerts_enabled": False,
                "suppression_reason": "calibration",
                "suppression_until": "2026-03-03T12:00:00Z",
            },
            headers={"Authorization": f"Bearer {operator_user.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    cfg = data["alert_config"]
    assert cfg["alerts_enabled"] is False
    assert cfg["suppression_until"] == "2026-03-03T12:00:00Z"
