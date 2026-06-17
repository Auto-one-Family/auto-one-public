"""
Integration Tests: Zone API

Phase: 5 - API Layer
Updated: T13-R1 — Zone must exist before assignment, FK constraint
Tests: Zone assignment, removal, and query endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.esp import ESPDevice
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app


@pytest.fixture
async def test_zone(db_session: AsyncSession):
    """Create a test zone entity (T13-R1: zones must exist before assignment)."""
    zone = Zone(
        zone_id="greenhouse_zone_1",
        name="Greenhouse Zone 1",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


@pytest.fixture
async def test_zone_gh1(db_session: AsyncSession):
    """Create greenhouse_1 zone entity for ESP with zone fixtures."""
    zone = Zone(
        zone_id="greenhouse_1",
        name="Greenhouse 1",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Create a test ESP device."""
    esp = ESPDevice(
        device_id="ESP_ZN000001",
        name="Zone Test ESP",
        ip_address="192.168.1.130",
        mac_address="AA:BB:CC:DD:EE:03",
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
async def test_esp_with_zone(db_session: AsyncSession, test_zone_gh1: Zone):
    """Create a test ESP device with zone assigned (T13-R1: zone entity must exist first)."""
    esp = ESPDevice(
        device_id="ESP_ZN000002",
        name="Zoned ESP",
        zone_id="greenhouse_1",
        zone_name="Greenhouse 1",
        master_zone_id="greenhouse_master",
        is_zone_master=False,
        ip_address="192.168.1.131",
        mac_address="AA:BB:CC:DD:EE:04",
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
async def test_esp_no_zone(db_session: AsyncSession):
    """Create a test ESP device without zone."""
    esp = ESPDevice(
        device_id="ESP_ZN000003",
        name="Unzoned ESP",
        ip_address="192.168.1.132",
        mac_address="AA:BB:CC:DD:EE:05",
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
async def operator_user(db_session: AsyncSession):
    """Create an operator user."""
    user = User(
        username="zone_operator",
        email="zone_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Zone Operator",
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


class TestZoneAssign:
    """Test zone assignment endpoint."""

    @pytest.mark.asyncio
    async def test_assign_zone_success(
        self, auth_headers: dict, test_esp: ESPDevice, test_zone: Zone
    ):
        """Test successful zone assignment (T13-R1: zone must exist before assignment)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/zone/devices/{test_esp.device_id}/assign",
                json={
                    "zone_id": "greenhouse_zone_1",
                    "master_zone_id": "greenhouse_master",
                    "zone_name": "Greenhouse Zone 1",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == test_esp.device_id
        assert data["zone_id"] == "greenhouse_zone_1"
        assert data["zone_name"] == "Greenhouse Zone 1"

    @pytest.mark.asyncio
    async def test_assign_zone_esp_not_found(self, auth_headers: dict):
        """Test zone assignment for non-existent ESP."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zone/devices/ESP_NOTFOUND/assign",
                json={
                    "zone_id": "test_zone",
                },
                headers=auth_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_zone_invalid_zone_id(self, auth_headers: dict, test_esp: ESPDevice):
        """Test zone assignment with invalid zone_id format."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/zone/devices/{test_esp.device_id}/assign",
                json={
                    "zone_id": "invalid zone id!",
                },
                headers=auth_headers,
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_assign_zone_no_auth(self, test_esp: ESPDevice):
        """Test zone assignment without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/zone/devices/{test_esp.device_id}/assign",
                json={
                    "zone_id": "test_zone",
                },
            )

        assert response.status_code == 401


class TestZoneRemove:
    """Test zone removal endpoint."""

    @pytest.mark.asyncio
    async def test_remove_zone_success(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test successful zone removal."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/zone/devices/{test_esp_with_zone.device_id}/zone",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == test_esp_with_zone.device_id

    @pytest.mark.asyncio
    async def test_remove_zone_esp_not_found(self, auth_headers: dict):
        """Test zone removal for non-existent ESP."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/zone/devices/ESP_NOTFOUND/zone",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestZoneQuery:
    """Test zone query endpoints."""

    @pytest.mark.asyncio
    async def test_get_zone_info(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test getting zone info for an ESP."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/zone/devices/{test_esp_with_zone.device_id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == "greenhouse_1"
        assert data["zone_name"] == "Greenhouse 1"

    @pytest.mark.asyncio
    async def test_get_zone_info_not_found(self, auth_headers: dict):
        """Test getting zone info for non-existent ESP."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/zone/devices/ESP_NOTFOUND",
                headers=auth_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_zone_devices(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test listing devices in a zone."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/zone/{test_esp_with_zone.zone_id}/devices",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_unassigned_devices(self, auth_headers: dict, test_esp_no_zone: ESPDevice):
        """Test listing unassigned ESPs."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/zone/unassigned",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert test_esp_no_zone.device_id in data
