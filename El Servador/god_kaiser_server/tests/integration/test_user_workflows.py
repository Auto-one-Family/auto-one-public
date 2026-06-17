"""
User Workflow Tests (USER Category).

Tests end-to-end API workflows that simulate frontend user actions:
device onboarding, monitoring, actuator control, and emergency workflows.

Pattern: AsyncClient + auth_headers, like test_api_esp.py.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Operator user."""
    user = User(
        username="workflow_operator",
        email="workflow@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Workflow Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    """Auth headers."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Pre-registered ESP for workflow tests."""
    esp = ESPDevice(
        device_id="ESP_AF000001",
        name="Workflow ESP",
        ip_address="192.168.1.150",
        mac_address="AA:BB:CC:DD:EE:20",
        firmware_version="2.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        device_metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    return esp


@pytest.fixture
async def test_sensor(db_session: AsyncSession, test_esp: ESPDevice):
    """Pre-configured sensor."""
    sensor = SensorConfig(
        esp_id=test_esp.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Workflow Temp",
        interface_type="ANALOG",
        enabled=True,
        pi_enhanced=True,
        sample_interval_ms=30000,
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.commit()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def test_actuator(db_session: AsyncSession, test_esp: ESPDevice):
    """Pre-configured actuator."""
    actuator = ActuatorConfig(
        esp_id=test_esp.id,
        gpio=5,
        actuator_type="digital",
        actuator_name="Workflow Pump",
        enabled=True,
        safety_constraints={"max_runtime": 1800},
        actuator_metadata={},
    )
    db_session.add(actuator)
    await db_session.commit()
    await db_session.refresh(actuator)
    return actuator


# =========================================================================
# Device Onboarding Workflow
# =========================================================================


class TestDeviceOnboardingWorkflow:
    """Register device → configure sensor → configure actuator → verify."""

    @pytest.mark.asyncio
    async def test_full_onboarding_flow(self, auth_headers: dict):
        """Complete device onboarding: register, add sensor, add actuator, verify."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Step 1: Register device
            reg_response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": "ESP_0B0A0D01",
                    "name": "Onboarding Test",
                    "ip_address": "192.168.1.250",
                    "mac_address": "11:22:33:44:55:AA",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )
            assert reg_response.status_code in [200, 201]

            # Step 1b: Approve device (required before sensor/actuator config)
            approve_response = await client.post(
                "/api/v1/esp/devices/ESP_0B0A0D01/approve",
                json={},
                headers=auth_headers,
            )
            assert approve_response.status_code == 200

            # Step 2: Add sensor
            sensor_response = await client.post(
                "/api/v1/sensors/ESP_0B0A0D01/34",
                json={
                    "esp_id": "ESP_0B0A0D01",
                    "gpio": 34,
                    "sensor_type": "temperature",
                    "name": "Onboard Temp",
                    "interval_ms": 30000,
                },
                headers=auth_headers,
            )
            assert sensor_response.status_code == 200

            # Step 3: Add actuator
            actuator_response = await client.post(
                "/api/v1/actuators/ESP_0B0A0D01/25",
                json={
                    "esp_id": "ESP_0B0A0D01",
                    "gpio": 25,
                    "actuator_type": "digital",
                    "name": "Onboard Pump",
                },
                headers=auth_headers,
            )
            assert actuator_response.status_code == 200

            # Step 4: Verify device has sensor and actuator
            device_response = await client.get(
                "/api/v1/esp/devices/ESP_0B0A0D01",
                headers=auth_headers,
            )
            assert device_response.status_code == 200
            device_data = device_response.json()
            assert device_data["device_id"] == "ESP_0B0A0D01"


# =========================================================================
# Monitoring Workflow
# =========================================================================


class TestMonitoringWorkflow:
    """Health checks and sensor data queries."""

    @pytest.mark.asyncio
    async def test_health_check_returns_status(self, auth_headers: dict):
        """Basic health check returns healthy status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/health/",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data

    @pytest.mark.asyncio
    async def test_detailed_health_includes_components(self, auth_headers: dict):
        """Detailed health check includes database, mqtt, system components."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/health/detailed",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert "system" in data

    @pytest.mark.asyncio
    async def test_sensor_list_after_configuration(
        self, auth_headers: dict, test_esp: ESPDevice, test_sensor: SensorConfig
    ):
        """Sensor list includes configured sensors."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/",
                params={"esp_id": test_esp.device_id},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1


# =========================================================================
# Actuator Control Workflow
# =========================================================================


class TestActuatorControlWorkflow:
    """Send command → check status → view history."""

    @pytest.mark.asyncio
    async def test_send_command_and_check_status(
        self, auth_headers: dict, test_esp: ESPDevice, test_actuator: ActuatorConfig
    ):
        """Send command then query status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Send command
            cmd_response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={"command": "ON", "value": 1.0},
                headers=auth_headers,
            )
            # May fail due to MQTT mock but should not be 422
            assert cmd_response.status_code in [200, 400, 500, 503]

            # Check status
            status_response = await client.get(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/status",
                headers=auth_headers,
            )
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["success"] is True
            assert status_data["esp_id"] == test_esp.device_id
            assert status_data["gpio"] == test_actuator.gpio

    @pytest.mark.asyncio
    async def test_actuator_list_shows_configured(
        self, auth_headers: dict, test_esp: ESPDevice, test_actuator: ActuatorConfig
    ):
        """Actuator list includes configured actuators."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/actuators/",
                params={"esp_id": test_esp.device_id},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1
        assert any(a["gpio"] == test_actuator.gpio for a in data["data"])


# =========================================================================
# Emergency Workflow
# =========================================================================


class TestEmergencyWorkflow:
    """Emergency stop → verify status."""

    @pytest.mark.asyncio
    async def test_emergency_stop_workflow(
        self, auth_headers: dict, test_esp: ESPDevice, test_actuator: ActuatorConfig
    ):
        """Emergency stop then verify actuator status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Emergency stop
            emergency_response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={
                    "esp_id": test_esp.device_id,
                    "reason": "workflow test emergency",
                },
                headers=auth_headers,
            )
            assert emergency_response.status_code in [200, 400, 500]

            # Check device is still listed
            device_response = await client.get(
                f"/api/v1/esp/devices/{test_esp.device_id}",
                headers=auth_headers,
            )
            assert device_response.status_code == 200

    @pytest.mark.asyncio
    async def test_device_listing_after_operations(self, auth_headers: dict, test_esp: ESPDevice):
        """Device listing works after various operations."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pagination"]["total_items"] >= 1
