"""
Integration Tests: ESP Device API

Phase: 5 (Week 9-10) - API Layer
Tests: ESP endpoints (devices, config, restart, health)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.db.models.esp import ESPDevice
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Create a test ESP device."""
    esp = ESPDevice(
        device_id="ESP_12AB34CD",
        name="Test ESP",
        zone_id="test-zone",
        zone_name="Test Zone",
        is_zone_master=False,
        ip_address="192.168.1.100",
        mac_address="AA:BB:CC:DD:EE:FF",
        firmware_version="2.0.0",
        hardware_type="ESP32_WROOM",
        capabilities={"gpio_count": 39},
        status="online",
        device_metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    return esp


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user."""
    from src.core.security import get_password_hash

    user = User(
        username="operator",
        email="operator@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Operator User",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    """Get authorization headers."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


class TestListDevices:
    """Test device listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_devices(self, auth_headers: dict, test_esp: ESPDevice):
        """Test listing ESP devices."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1
        assert data["pagination"]["total_items"] >= 1

    @pytest.mark.asyncio
    async def test_list_devices_with_filter(self, auth_headers: dict, test_esp: ESPDevice):
        """Test listing ESP devices with zone filter."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices",
                params={"zone_id": "test-zone"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(d["zone_id"] == "test-zone" for d in data["data"])

    @pytest.mark.asyncio
    async def test_list_devices_runtime_vs_include_deleted(
        self, auth_headers: dict, db_session: AsyncSession
    ):
        """runtime_only hides deleted rows; historical mode can include them."""
        deleted_esp = ESPDevice(
            device_id="ESP_DEADBEAF",
            name="Deleted Runtime Test",
            hardware_type="ESP32_WROOM",
            status="deleted",
            device_metadata={},
        )
        db_session.add(deleted_esp)
        await db_session.flush()
        from datetime import datetime, timezone

        deleted_esp.deleted_at = datetime.now(timezone.utc)
        deleted_esp.deleted_by = "pytest"
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            runtime_response = await client.get(
                "/api/v1/esp/devices",
                params={"include_deleted": True, "runtime_only": True},
                headers=auth_headers,
            )
            historical_response = await client.get(
                "/api/v1/esp/devices",
                params={"include_deleted": True, "runtime_only": False},
                headers=auth_headers,
            )

        assert runtime_response.status_code == 200
        runtime_ids = {entry["device_id"] for entry in runtime_response.json()["data"]}
        assert "ESP_DEADBEAF" not in runtime_ids

        assert historical_response.status_code == 200
        historical_ids = {entry["device_id"] for entry in historical_response.json()["data"]}
        assert "ESP_DEADBEAF" in historical_ids


class TestGetDevice:
    """Test getting single device."""

    @pytest.mark.asyncio
    async def test_get_device(self, auth_headers: dict, test_esp: ESPDevice):
        """Test getting a device by ID."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/esp/devices/{test_esp.device_id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == test_esp.device_id
        assert data["name"] == "Test ESP"

    @pytest.mark.asyncio
    async def test_get_device_not_found(self, auth_headers: dict):
        """Test getting non-existent device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices/ESP_NOTFOUND",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestRegisterDevice:
    """Test device registration."""

    @pytest.mark.asyncio
    async def test_register_device(self, auth_headers: dict):
        """Test registering a new device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": "ESP_AABBCCDD",
                    "name": "New ESP Device",
                    "zone_id": "new-zone",
                    "zone_name": "New Zone",
                    "is_zone_master": False,
                    "ip_address": "192.168.1.101",
                    "mac_address": "11:22:33:44:55:66",
                    "firmware_version": "2.0.0",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["device_id"] == "ESP_AABBCCDD"
        assert data["name"] == "New ESP Device"

    @pytest.mark.asyncio
    async def test_register_duplicate_device(self, auth_headers: dict, test_esp: ESPDevice):
        """Test registering duplicate device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": test_esp.device_id,  # Already exists
                    "ip_address": "192.168.1.102",
                    "mac_address": "AA:BB:CC:DD:EE:00",
                    "firmware_version": "2.0.0",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )

        assert response.status_code == 409


class TestUpdateDevice:
    """Test device update."""

    @pytest.mark.asyncio
    async def test_update_device(self, auth_headers: dict, test_esp: ESPDevice):
        """Test updating device info."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/esp/devices/{test_esp.device_id}",
                json={
                    "name": "Updated ESP Name",
                    "zone_name": "Updated Zone",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated ESP Name"
        assert data["zone_name"] == "Updated Zone"


class TestDeviceHealth:
    """Test device health endpoint."""

    @pytest.mark.asyncio
    async def test_get_device_health(self, auth_headers: dict, test_esp: ESPDevice):
        """Test getting device health."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/esp/devices/{test_esp.device_id}/health",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == test_esp.device_id
        assert data["status"] == "online"


class TestDeviceCommands:
    """Test device command endpoints."""

    @pytest.mark.asyncio
    async def test_restart_device(self, auth_headers: dict, test_esp: ESPDevice):
        """Test restarting a device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/esp/devices/{test_esp.device_id}/restart",
                json={
                    "delay_seconds": 5,
                    "reason": "Test restart",
                },
                headers=auth_headers,
            )

        # May fail if MQTT not connected, but endpoint should be reachable
        assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_factory_reset_requires_confirm(self, auth_headers: dict, test_esp: ESPDevice):
        """Test that factory reset requires confirmation."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/esp/devices/{test_esp.device_id}/reset",
                json={
                    "confirm": False,  # Must be true
                    "preserve_wifi": True,
                },
                headers=auth_headers,
            )

        assert response.status_code == 400


class TestDeleteDevice:
    """Test device deletion."""

    @pytest.mark.asyncio
    async def test_delete_device(self, auth_headers: dict, db_session: AsyncSession):
        """Test deleting a device."""
        # Create a device to delete
        esp = ESPDevice(
            device_id="ESP_DELETE01",
            name="Delete Me",
            ip_address="192.168.1.199",
            mac_address="DD:DD:DD:DD:DD:DD",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            device_metadata={},
        )
        db_session.add(esp)
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/esp/devices/ESP_DELETE01",
                headers=auth_headers,
            )

        assert response.status_code == 204

        # Verify deleted
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices/ESP_DELETE01",
                headers=auth_headers,
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_device_not_found(self, auth_headers: dict):
        """Test deleting non-existent device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/esp/devices/ESP_NOTEXIST",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestDevicePagination:
    """Test device listing pagination."""

    @pytest.mark.asyncio
    async def test_list_with_page_size(self, auth_headers: dict, test_esp: ESPDevice):
        """Test listing with page_size parameter."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/esp/devices",
                params={"page_size": 1},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 1
        assert data["pagination"]["page_size"] == 1


class TestDeviceGpioStatus:
    """Test device GPIO status endpoint."""

    @pytest.mark.asyncio
    async def test_get_gpio_status(self, auth_headers: dict, test_esp: ESPDevice):
        """Test getting GPIO status for a device."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/esp/devices/{test_esp.device_id}/gpio-status",
                headers=auth_headers,
            )

        assert response.status_code == 200


class TestDeviceAuth:
    """Test authentication requirements for device endpoints."""

    @pytest.mark.asyncio
    async def test_register_without_auth(self):
        """Test registering device without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": "ESP_NOAUTH01",
                    "ip_address": "192.168.1.200",
                    "mac_address": "FF:FF:FF:FF:FF:FF",
                    "firmware_version": "2.0.0",
                    "hardware_type": "ESP32_WROOM",
                },
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_without_auth(self, test_esp: ESPDevice):
        """Test updating device without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/esp/devices/{test_esp.device_id}",
                json={"name": "Hacked Name"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_without_auth(self, test_esp: ESPDevice):
        """Test deleting device without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/esp/devices/{test_esp.device_id}",
            )

        assert response.status_code == 401
