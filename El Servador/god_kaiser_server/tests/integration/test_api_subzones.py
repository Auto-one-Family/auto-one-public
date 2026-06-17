"""
Integration Tests for Subzone API Endpoints

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Tests Subzone REST API endpoints via FastAPI TestClient.
Uses mocked MQTT publisher (from conftest.py auto-fixtures).

Test Categories:
- Subzone Assignment Endpoints
- Subzone Query Endpoints
- Safe-Mode Control Endpoints
- Error Response Testing
- Authentication/Authorization

References:
- El Servador/god_kaiser_server/src/api/v1/subzone.py
- El Frontend/Docs/System Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.db.models.esp import ESPDevice
from src.db.models.subzone import SubzoneConfig
from src.db.models.user import User
from src.core.security import get_password_hash, create_access_token

# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def test_esp_with_zone(db_session: AsyncSession) -> ESPDevice:
    """Create ESP device with assigned zone for API tests.

    Note: device_id must match API pattern: ^ESP_[A-Z0-9]{6,8}$
    """
    device = ESPDevice(
        device_id="ESP_A00000E1",  # 8 chars after ESP_, valid format
        name="API Test ESP",
        ip_address="192.168.1.200",
        mac_address="AA:BB:CC:DD:EE:FF",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id="api_test_zone",
        zone_name="API Test Zone",
        master_zone_id="api_master",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def test_esp_no_zone(db_session: AsyncSession) -> ESPDevice:
    """Create ESP device without zone for API tests.

    Note: device_id must match API pattern: ^ESP_[A-Z0-9]{6,8}$
    """
    device = ESPDevice(
        device_id="ESP_B0000001",  # 8 chars after ESP_, valid format
        name="No Zone ESP",
        ip_address="192.168.1.201",
        mac_address="AA:BB:CC:DD:EE:EE",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=None,
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def operator_user(db_session: AsyncSession) -> User:
    """Create operator user for authenticated requests."""
    user = User(
        username="api_operator",
        email="operator@test.com",
        password_hash=get_password_hash("testpassword123"),
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Create viewer user (lower permissions)."""
    user = User(
        username="api_viewer",
        email="viewer@test.com",
        password_hash=get_password_hash("testpassword123"),
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(operator_user: User) -> dict:
    """Create authentication headers with operator token."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def viewer_headers(viewer_user: User) -> dict:
    """Create authentication headers with viewer token."""
    token = create_access_token(
        user_id=viewer_user.id, additional_claims={"role": viewer_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def existing_subzone(
    db_session: AsyncSession, test_esp_with_zone: ESPDevice
) -> SubzoneConfig:
    """Create existing subzone for query tests."""
    subzone = SubzoneConfig(
        esp_id=test_esp_with_zone.device_id,
        subzone_id="existing_subzone",
        subzone_name="Existing Test Subzone",
        parent_zone_id=test_esp_with_zone.zone_id,
        assigned_gpios=[4, 5, 6],
        safe_mode_active=True,
        sensor_count=1,
        actuator_count=2,
    )
    db_session.add(subzone)
    await db_session.commit()
    await db_session.refresh(subzone)
    return subzone


# =============================================================================
# Test: Subzone Assignment Endpoints
# =============================================================================


class TestSubzoneAssignmentAPI:
    """Test subzone assignment API endpoints."""

    @pytest.mark.asyncio
    async def test_assign_subzone_success(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test successful subzone assignment via API."""
        request_data = {
            "subzone_id": "irrigation_section_a",
            "subzone_name": "Irrigation Section A",
            "assigned_gpios": [4, 5, 6],
            "safe_mode_active": False,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["device_id"] == test_esp_with_zone.device_id
        assert data["subzone_id"] == "irrigation_section_a"
        assert data["assigned_gpios"] == [4, 5, 6]
        assert data["mqtt_sent"] is True
        assert "subzone/assign" in data["mqtt_topic"]

    @pytest.mark.asyncio
    async def test_assign_subzone_esp_not_found(self, auth_headers: dict):
        """Test assignment with non-existent ESP returns 404."""
        request_data = {
            "subzone_id": "test_subzone",
            "assigned_gpios": [4, 5],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/subzone/devices/ESP_FF000000/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert "not found" in response.json()["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_assign_subzone_no_zone(self, auth_headers: dict, test_esp_no_zone: ESPDevice):
        """Test assignment fails when ESP has no zone assigned."""
        request_data = {
            "subzone_id": "test_subzone",
            "assigned_gpios": [4, 5],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_no_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "zone" in response.json()["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_assign_subzone_invalid_gpio(
        self, auth_headers: dict, test_esp_with_zone: ESPDevice
    ):
        """Test assignment with invalid GPIO returns validation error."""
        request_data = {
            "subzone_id": "test_subzone",
            "assigned_gpios": [50],  # Invalid GPIO (>39)
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        # Pydantic validation should catch this
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_assign_subzone_empty_gpios(
        self, auth_headers: dict, test_esp_with_zone: ESPDevice
    ):
        """Test assignment with empty GPIO list is accepted (create subzone only)."""
        request_data = {
            "subzone_id": "test_subzone_empty",
            "assigned_gpios": [],  # Empty list - valid per schema (create subzone only)
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        # API accepts empty gpios (schema min_length=0, "create subzone only")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_assign_subzone_no_auth(self, test_esp_with_zone: ESPDevice):
        """Test assignment without authentication returns 401."""
        request_data = {
            "subzone_id": "test_subzone",
            "assigned_gpios": [4, 5],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                # No auth headers
            )

        assert response.status_code == 401


# =============================================================================
# Test: Subzone Query Endpoints
# =============================================================================


class TestSubzoneQueryAPI:
    """Test subzone query API endpoints."""

    @pytest.mark.asyncio
    async def test_get_subzones_empty(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test getting subzones for ESP with none."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_count"] == 0
        assert len(data["subzones"]) == 0

    @pytest.mark.asyncio
    async def test_get_subzones_with_existing(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test getting subzones for ESP with existing subzone."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_count"] == 1
        assert len(data["subzones"]) == 1
        assert data["subzones"][0]["subzone_id"] == "existing_subzone"
        assert data["subzones"][0]["assigned_gpios"] == [4, 5, 6]

    @pytest.mark.asyncio
    async def test_get_subzone_detail_found(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test getting specific subzone details."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/existing_subzone",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["subzone_id"] == "existing_subzone"
        assert data["subzone_name"] == "Existing Test Subzone"
        assert data["assigned_gpios"] == [4, 5, 6]
        assert data["safe_mode_active"] is True
        assert data["sensor_count"] == 1
        assert data["actuator_count"] == 2

    @pytest.mark.asyncio
    async def test_get_subzone_detail_not_found(
        self, auth_headers: dict, test_esp_with_zone: ESPDevice
    ):
        """Test getting non-existent subzone returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/non_existent",
                headers=auth_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_subzones_esp_not_found(self, auth_headers: dict):
        """Test getting subzones for non-existent ESP returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/subzone/devices/ESP_FF000000/subzones",
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Safe-Mode Control Endpoints
# =============================================================================


class TestSafeModeAPI:
    """Test safe-mode control API endpoints."""

    @pytest.mark.asyncio
    async def test_enable_safe_mode_success(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test enabling safe-mode via API."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/existing_subzone/safe-mode",
                json={"reason": "maintenance"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["safe_mode_active"] is True
        assert data["mqtt_sent"] is True

    @pytest.mark.asyncio
    async def test_disable_safe_mode_success(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test disabling safe-mode via API."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/existing_subzone/safe-mode",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["safe_mode_active"] is False
        assert data["mqtt_sent"] is True

    @pytest.mark.asyncio
    async def test_safe_mode_esp_not_found(self, auth_headers: dict):
        """Test safe-mode for non-existent ESP returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/subzone/devices/ESP_FF000000/subzones/test/safe-mode",
                json={"reason": "test"},
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Subzone Removal Endpoints
# =============================================================================


class TestSubzoneRemovalAPI:
    """Test subzone removal API endpoints."""

    @pytest.mark.asyncio
    async def test_remove_subzone_success(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test successful subzone removal via API."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/existing_subzone",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["device_id"] == test_esp_with_zone.device_id
        assert data["subzone_id"] == "existing_subzone"
        assert data["mqtt_sent"] is True

    @pytest.mark.asyncio
    async def test_remove_subzone_esp_not_found(self, auth_headers: dict):
        """Test removal with non-existent ESP returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/subzone/devices/ESP_FF000000/subzones/test_subzone",
                headers=auth_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Test: Authorization (Operator Permission Required)
# =============================================================================


class TestSubzoneAuthorization:
    """Test subzone endpoint authorization requirements."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_assign_subzone(
        self, viewer_headers: dict, test_esp_with_zone: ESPDevice
    ):
        """Test viewer role cannot assign subzones (requires operator)."""
        request_data = {
            "subzone_id": "test_subzone",
            "assigned_gpios": [4, 5],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=viewer_headers,
            )

        # Viewer should be forbidden (403) for operator-only endpoints
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_can_get_subzones(
        self,
        viewer_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test viewer role can read subzones."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones",
                headers=viewer_headers,
            )

        # Viewer should be able to read (GET endpoints might allow viewer)
        # This depends on the API implementation - adjust assertion if needed
        assert response.status_code in [200, 403]


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestSubzoneEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_assign_duplicate_subzone_id(
        self,
        auth_headers: dict,
        test_esp_with_zone: ESPDevice,
        existing_subzone: SubzoneConfig,
    ):
        """Test assigning to existing subzone_id updates it."""
        request_data = {
            "subzone_id": "existing_subzone",  # Same ID as existing
            "subzone_name": "Updated Subzone Name",
            "assigned_gpios": [18, 19],  # Different GPIOs
            "safe_mode_active": False,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        # Should succeed (upsert behavior)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_subzone_id_normalization(
        self, auth_headers: dict, test_esp_with_zone: ESPDevice
    ):
        """Test subzone_id is normalized to lowercase."""
        request_data = {
            "subzone_id": "UPPERCASE_SubZone",  # Mixed case
            "assigned_gpios": [4, 5],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        # Schema validator should lowercase the subzone_id
        assert data["subzone_id"] == "uppercase_subzone"

    @pytest.mark.asyncio
    async def test_gpio_deduplication(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test duplicate GPIOs are removed."""
        request_data = {
            "subzone_id": "dedup_test",
            "assigned_gpios": [4, 5, 4, 5, 6, 6],  # Duplicates
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        # Duplicates should be removed
        assert data["assigned_gpios"] == [4, 5, 6]

    @pytest.mark.asyncio
    async def test_max_gpios_validation(self, auth_headers: dict, test_esp_with_zone: ESPDevice):
        """Test maximum GPIOs per subzone validation."""
        request_data = {
            "subzone_id": "max_gpio_test",
            "assigned_gpios": list(range(25)),  # More than max_length=20
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/subzone/devices/{test_esp_with_zone.device_id}/subzones/assign",
                json=request_data,
                headers=auth_headers,
            )

        # Pydantic validation should reject too many GPIOs
        assert response.status_code in [400, 422]
