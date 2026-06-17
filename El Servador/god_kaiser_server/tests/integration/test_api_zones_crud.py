"""
Integration Tests: Zone Entity CRUD API

Phase: 0.3 - Zone as DB Entity
Tests: POST/GET/PUT/DELETE /zones endpoints,
       empty zone persistence, backward compatibility with assign
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.esp import ESPDevice
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user for auth."""
    user = User(
        username="zones_operator",
        email="zones_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Zones Operator",
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


@pytest.fixture
async def sample_zone(db_session: AsyncSession):
    """Create a sample zone in the DB."""
    zone = Zone(
        zone_id="greenhouse_1",
        name="Greenhouse Section 1",
        description="Primary growing area",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


@pytest.fixture
async def sample_esp_in_zone(db_session: AsyncSession, sample_zone: Zone):
    """Create an ESP device assigned to the sample zone."""
    esp = ESPDevice(
        device_id="ESP_IN_ZONE_001",
        name="ESP in Zone",
        zone_id=sample_zone.zone_id,
        zone_name=sample_zone.name,
        ip_address="192.168.1.200",
        mac_address="AA:BB:CC:DD:EE:A1",
        firmware_version="2.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        device_metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    return esp


# =============================================================================
# Test: Create Zone
# =============================================================================


class TestCreateZone:
    """Test POST /zones"""

    @pytest.mark.asyncio
    async def test_create_zone_success(self, auth_headers: dict):
        """Test successful zone creation."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zones",
                json={
                    "zone_id": "balcony_west",
                    "name": "West Balcony",
                    "description": "Outdoor growing area",
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["zone_id"] == "balcony_west"
        assert data["name"] == "West Balcony"
        assert data["description"] == "Outdoor growing area"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_zone_minimal(self, auth_headers: dict):
        """Test zone creation with only required fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zones",
                json={"zone_id": "minimal_zone", "name": "Minimal"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["zone_id"] == "minimal_zone"
        assert data["description"] is None

    @pytest.mark.asyncio
    async def test_create_zone_duplicate(self, auth_headers: dict, sample_zone: Zone):
        """Test creating a zone with an existing zone_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zones",
                json={"zone_id": sample_zone.zone_id, "name": "Duplicate"},
                headers=auth_headers,
            )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_zone_no_auth(self):
        """Test zone creation without auth."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zones",
                json={"zone_id": "no_auth", "name": "No Auth"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_zone_invalid_zone_id(self, auth_headers: dict):
        """Test zone creation with invalid zone_id format."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/zones",
                json={"zone_id": "invalid zone!", "name": "Bad ID"},
                headers=auth_headers,
            )

        assert response.status_code == 422


# =============================================================================
# Test: List Zones
# =============================================================================


class TestListZones:
    """Test GET /zones"""

    @pytest.mark.asyncio
    async def test_list_zones_empty(self, auth_headers: dict):
        """Test listing zones when none exist."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/zones", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["zones"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_zones_with_data(self, auth_headers: dict, sample_zone: Zone):
        """Test listing zones with data."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/zones", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        zone_ids = [z["zone_id"] for z in data["zones"]]
        assert sample_zone.zone_id in zone_ids

    @pytest.mark.asyncio
    async def test_list_zones_includes_empty_zones(self, auth_headers: dict, sample_zone: Zone):
        """Test that zones without devices are still listed (KEY REQUIREMENT)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/zones", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # sample_zone has no devices assigned but should still appear
        zone_ids = [z["zone_id"] for z in data["zones"]]
        assert sample_zone.zone_id in zone_ids


# =============================================================================
# Test: Get Zone
# =============================================================================


class TestGetZone:
    """Test GET /zones/{zone_id}"""

    @pytest.mark.asyncio
    async def test_get_zone_success(self, auth_headers: dict, sample_zone: Zone):
        """Test getting a zone by zone_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/zones/{sample_zone.zone_id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == sample_zone.zone_id
        assert data["name"] == sample_zone.name
        assert data["description"] == sample_zone.description

    @pytest.mark.asyncio
    async def test_get_zone_not_found(self, auth_headers: dict):
        """Test getting a non-existent zone."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/zones/nonexistent_zone",
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Update Zone
# =============================================================================


class TestUpdateZone:
    """Test PUT /zones/{zone_id}"""

    @pytest.mark.asyncio
    async def test_update_zone_name(self, auth_headers: dict, sample_zone: Zone):
        """Test updating zone name."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/zones/{sample_zone.zone_id}",
                json={"name": "Updated Greenhouse"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Greenhouse"
        assert data["zone_id"] == sample_zone.zone_id  # Unchanged

    @pytest.mark.asyncio
    async def test_update_zone_description(self, auth_headers: dict, sample_zone: Zone):
        """Test updating zone description."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/zones/{sample_zone.zone_id}",
                json={"description": "New description"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New description"

    @pytest.mark.asyncio
    async def test_update_zone_not_found(self, auth_headers: dict):
        """Test updating a non-existent zone."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                "/api/v1/zones/nonexistent",
                json={"name": "Nope"},
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Delete Zone
# =============================================================================


class TestDeleteZone:
    """Test DELETE /zones/{zone_id}"""

    @pytest.mark.asyncio
    async def test_delete_zone_success(self, auth_headers: dict, sample_zone: Zone):
        """Test successful zone deletion."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/zones/{sample_zone.zone_id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["zone_id"] == sample_zone.zone_id
        assert data["had_devices"] is False
        assert data["device_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_zone_with_devices_blocked(
        self, auth_headers: dict, sample_zone: Zone, sample_esp_in_zone: ESPDevice
    ):
        """Test deleting a zone with assigned devices is blocked (T13-R1: soft-delete, must unassign first)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/zones/{sample_zone.zone_id}",
                headers=auth_headers,
            )

        assert response.status_code == 400
        data = response.json()
        assert "device" in data["detail"].lower() or "assigned" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_zone_not_found(self, auth_headers: dict):
        """Test deleting a non-existent zone."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/zones/nonexistent",
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Zone Persistence (Empty Zone Survives Device Removal)
# =============================================================================


class TestZonePersistence:
    """Test that zones survive when all devices are removed."""

    @pytest.mark.asyncio
    async def test_zone_exists_after_all_devices_removed(
        self, auth_headers: dict, db_session: AsyncSession
    ):
        """
        KEY TEST: Create zone -> assign device -> remove all devices -> zone still exists.
        """
        # 1. Create zone via API
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/zones",
                json={"zone_id": "persist_zone", "name": "Persistent Zone"},
                headers=auth_headers,
            )
        assert create_resp.status_code == 201

        # 2. Create an ESP and assign it to the zone
        esp = ESPDevice(
            device_id="ESP_PERSIST_001",
            name="Persist ESP",
            zone_id="persist_zone",
            ip_address="192.168.1.210",
            mac_address="AA:BB:CC:DD:EE:B1",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            device_metadata={},
        )
        db_session.add(esp)
        await db_session.commit()

        # 3. Remove zone assignment from ESP (simulating unassign)
        await db_session.refresh(esp)
        esp.zone_id = None
        esp.zone_name = None
        await db_session.commit()

        # 4. Verify zone still exists
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            get_resp = await client.get(
                "/api/v1/zones/persist_zone",
                headers=auth_headers,
            )

        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["zone_id"] == "persist_zone"
        assert data["name"] == "Persistent Zone"


# =============================================================================
# Test: Zone Existence Required (T13-R1: no auto-create)
# =============================================================================


class TestZoneExistenceRequired:
    """Test that zone must exist before assignment (T13-R1: no auto-create)."""

    @pytest.mark.asyncio
    async def test_assign_nonexistent_zone_rejected(
        self, auth_headers: dict, db_session: AsyncSession
    ):
        """
        T13-R1: Assigning a zone that doesn't exist in the zones table
        must be rejected (no auto-create).
        """
        # Create an ESP device
        esp = ESPDevice(
            device_id="ESP_COMPAT_001",
            name="Compat ESP",
            ip_address="192.168.1.220",
            mac_address="AA:BB:CC:DD:EE:C1",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            device_metadata={},
        )
        db_session.add(esp)
        await db_session.commit()

        # Assign zone that doesn't exist — must be rejected
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assign_resp = await client.post(
                "/api/v1/zone/devices/ESP_COMPAT_001/assign",
                json={
                    "zone_id": "nonexistent_zone",
                    "zone_name": "Does Not Exist",
                },
                headers=auth_headers,
            )

        assert assign_resp.status_code == 400
        data = assign_resp.json()
        assert "zone" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_assign_existing_zone_succeeds(
        self, auth_headers: dict, db_session: AsyncSession
    ):
        """
        T13-R1: Assigning a zone that exists in the zones table succeeds.
        """
        # Create zone entity first
        zone = Zone(zone_id="pre_created_zone", name="Pre-Created Zone")
        db_session.add(zone)
        await db_session.commit()

        # Create an ESP device
        esp = ESPDevice(
            device_id="ESP_COMPAT_002",
            name="Compat ESP 2",
            ip_address="192.168.1.221",
            mac_address="AA:BB:CC:DD:EE:C2",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            device_metadata={},
        )
        db_session.add(esp)
        await db_session.commit()

        # Assign zone that exists — must succeed
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assign_resp = await client.post(
                "/api/v1/zone/devices/ESP_COMPAT_002/assign",
                json={
                    "zone_id": "pre_created_zone",
                    "zone_name": "Pre-Created Zone",
                },
                headers=auth_headers,
            )

        assert assign_resp.status_code == 200
        data = assign_resp.json()
        assert data["zone_id"] == "pre_created_zone"
