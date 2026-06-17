"""
Integration Tests: Runtime Stats API Endpoints

Phase 4A Test-Suite (STEP 4, Block 7d)
Tests: Sensor/actuator runtime GET/PATCH
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def runtime_operator(db_session: AsyncSession):
    """Create an operator user with JWT token."""
    user = User(
        username="runtime_operator",
        email="runtime_op@example.com",
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
async def runtime_sensor(db_session: AsyncSession, sample_esp_device):
    """Create a sensor with runtime stats for testing."""
    past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    sensor = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Runtime Test Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        runtime_stats={
            "expected_lifetime_hours": 8760,
            "last_restart": "2026-02-01T00:00:00Z",
        },
        sensor_metadata={
            "installation_date": past,
        },
    )
    db_session.add(sensor)
    await db_session.flush()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def runtime_actuator(db_session: AsyncSession, sample_esp_device):
    """Create an actuator with runtime stats for testing."""
    actuator = ActuatorConfig(
        esp_id=sample_esp_device.id,
        gpio=25,
        actuator_type="relay",
        actuator_name="Runtime Test Relay",
        enabled=True,
        min_value=0.0,
        max_value=1.0,
        default_value=0.0,
        timeout_seconds=3600,
        runtime_stats={
            "total_cycles": 150,
            "last_restart": "2026-02-01T08:00:00Z",
        },
    )
    db_session.add(actuator)
    await db_session.flush()
    await db_session.refresh(actuator)
    return actuator


# =============================================================================
# Test 1: GET Sensor Runtime Stats
# =============================================================================


@pytest.mark.asyncio
async def test_get_sensor_runtime_stats(
    runtime_operator,
    sample_esp_device,
    runtime_sensor,
):
    """GET /v1/sensors/{id}/runtime returns runtime_stats + computed fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/sensors/{runtime_sensor.id}/runtime",
            headers={"Authorization": f"Bearer {runtime_operator.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "runtime_stats" in data
    assert data["runtime_stats"]["expected_lifetime_hours"] == 8760
    # computed_uptime_hours should be ~30 days in hours
    assert data["computed_uptime_hours"] is not None
    assert data["computed_uptime_hours"] > 0


# =============================================================================
# Test 2: PATCH Sensor Runtime Stats
# =============================================================================


@pytest.mark.asyncio
async def test_patch_sensor_runtime_stats(
    runtime_operator,
    sample_esp_device,
    runtime_sensor,
):
    """PATCH /v1/sensors/{id}/runtime updates runtime_stats via JSONB merge."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/sensors/{runtime_sensor.id}/runtime",
            json={
                "expected_lifetime_hours": 10000,
                "maintenance_log": [
                    {"date": "2026-03-01", "action": "Calibration", "notes": "pH probe"},
                ],
            },
            headers={"Authorization": f"Bearer {runtime_operator.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    stats = data["runtime_stats"]
    assert stats["expected_lifetime_hours"] == 10000
    # Original field should still be there (JSONB merge)
    assert stats["last_restart"] == "2026-02-01T00:00:00Z"


# =============================================================================
# Test 3: GET Actuator Runtime Stats
# =============================================================================


@pytest.mark.asyncio
async def test_get_actuator_runtime_stats(
    runtime_operator,
    sample_esp_device,
    runtime_actuator,
):
    """GET /v1/actuators/{id}/runtime returns runtime_stats + computed uptime."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/actuators/{runtime_actuator.id}/runtime",
            headers={"Authorization": f"Bearer {runtime_operator.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "runtime_stats" in data
    assert data["runtime_stats"]["total_cycles"] == 150


# =============================================================================
# Test 4: PATCH Actuator Runtime Stats
# =============================================================================


@pytest.mark.asyncio
async def test_patch_actuator_runtime_stats(
    runtime_operator,
    sample_esp_device,
    runtime_actuator,
):
    """PATCH /v1/actuators/{id}/runtime updates runtime_stats."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/actuators/{runtime_actuator.id}/runtime",
            json={
                "expected_lifetime_hours": 5000,
            },
            headers={"Authorization": f"Bearer {runtime_operator.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    stats = data["runtime_stats"]
    assert stats["expected_lifetime_hours"] == 5000
    # Original field should still be there (merge)
    assert stats["total_cycles"] == 150
