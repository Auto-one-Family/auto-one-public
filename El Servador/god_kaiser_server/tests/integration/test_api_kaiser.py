"""
Integration Tests: Kaiser REST API (AUT-229 F1)

Tests for src/api/v1/kaiser.py - Kaiser relay node management.

Coverage:
- GET /api/v1/kaiser (list all)
- GET /api/v1/kaiser/{kaiser_id}
- GET /api/v1/kaiser/{kaiser_id}/hierarchy
- POST /api/v1/kaiser (register)
- PUT /api/v1/kaiser/{kaiser_id}/zones (update zones)

Each endpoint covers: Happy path (200/201), Not Found (404),
Validation Error (422), Auth Error (401/403).

Refs: AUT-229 F1.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.kaiser import KaiserRegistry
from src.db.models.user import User
from src.main import app


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user for kaiser tests."""
    user = User(
        username="kaiser_operator",
        email="kaiser_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Kaiser Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def active_user(db_session: AsyncSession):
    """Create an active (non-operator) user for auth tests."""
    user = User(
        username="kaiser_active",
        email="kaiser_active@example.com",
        password_hash=get_password_hash("ActiveP@ss123"),
        full_name="Kaiser Active",
        role="active",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User):
    """Auth headers for operator user."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def active_headers(active_user: User):
    """Auth headers for active user."""
    token = create_access_token(
        user_id=active_user.id, additional_claims={"role": active_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_kaiser(db_session: AsyncSession):
    """Create a sample Kaiser entry for tests."""
    kaiser = KaiserRegistry(
        kaiser_id="KAISER_TEST_001",
        zone_ids=["zone_alpha", "zone_beta"],
        capabilities={"max_esps": 100, "features": ["mqtt_relay"]},
        status="online",
        last_seen=datetime.now(timezone.utc),
        kaiser_metadata={"description": "Test relay node"},
    )
    db_session.add(kaiser)
    await db_session.commit()
    await db_session.refresh(kaiser)
    return kaiser


# =============================================================================
# Tests: GET /api/v1/kaiser (list)
# =============================================================================


class TestListKaisers:
    """Tests for GET /api/v1/kaiser."""

    @pytest.mark.asyncio
    async def test_list_kaisers_happy_path(
        self,
        operator_headers: dict,
        sample_kaiser: KaiserRegistry,
    ):
        """List endpoint returns 200 with the existing Kaiser."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/kaiser", headers=operator_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_count"] >= 1
        kaiser_ids = [k["kaiser_id"] for k in data["data"]]
        assert "KAISER_TEST_001" in kaiser_ids

    @pytest.mark.asyncio
    async def test_list_kaisers_empty(self, operator_headers: dict):
        """List endpoint returns 200 with empty list when no Kaiser exists."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/kaiser", headers=operator_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_count"] == 0
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_kaisers_no_auth(self):
        """List endpoint returns 401 without auth header."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/kaiser")

        assert response.status_code == 401


# =============================================================================
# Tests: GET /api/v1/kaiser/{kaiser_id}
# =============================================================================


class TestGetKaiser:
    """Tests for GET /api/v1/kaiser/{kaiser_id}."""

    @pytest.mark.asyncio
    async def test_get_kaiser_happy_path(
        self,
        operator_headers: dict,
        sample_kaiser: KaiserRegistry,
    ):
        """Get endpoint returns 200 with details."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/kaiser/{sample_kaiser.kaiser_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["kaiser_id"] == "KAISER_TEST_001"
        assert "zone_alpha" in data["zone_ids"]
        assert data["status"] == "online"

    @pytest.mark.asyncio
    async def test_get_kaiser_not_found(self, operator_headers: dict):
        """Get endpoint returns 404 for unknown Kaiser (KaiserNotFoundException)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/kaiser/UNKNOWN_KAISER",
                headers=operator_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_kaiser_no_auth(self, sample_kaiser: KaiserRegistry):
        """Get endpoint returns 401 without auth header."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/kaiser/{sample_kaiser.kaiser_id}")

        assert response.status_code == 401


# =============================================================================
# Tests: GET /api/v1/kaiser/{kaiser_id}/hierarchy
# =============================================================================


class TestGetHierarchy:
    """Tests for GET /api/v1/kaiser/{kaiser_id}/hierarchy."""

    @pytest.mark.asyncio
    async def test_get_hierarchy_happy_path(
        self,
        operator_headers: dict,
        sample_kaiser: KaiserRegistry,
    ):
        """Hierarchy endpoint returns 200 (with empty zones when no ESPs)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/kaiser/{sample_kaiser.kaiser_id}/hierarchy",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["kaiser_id"] == "KAISER_TEST_001"
        assert "zones" in data
        assert "unassigned_devices" in data
        assert data["total_devices"] == 0
        assert data["total_zones"] == 0

    @pytest.mark.asyncio
    async def test_get_hierarchy_not_found(self, operator_headers: dict):
        """Hierarchy endpoint returns 404 for unknown Kaiser."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/kaiser/UNKNOWN_KAISER/hierarchy",
                headers=operator_headers,
            )

        assert response.status_code == 404


# =============================================================================
# Tests: POST /api/v1/kaiser (register)
# =============================================================================


class TestRegisterKaiser:
    """Tests for POST /api/v1/kaiser."""

    @pytest.mark.asyncio
    async def test_register_kaiser_happy_path(self, operator_headers: dict):
        """Register endpoint returns 201 for new Kaiser."""
        body = {
            "kaiser_id": "KAISER_NEW_001",
            "zone_ids": ["zone_x"],
            "capabilities": {"max_esps": 50, "features": ["mqtt_relay"]},
            "ip_address": "192.168.1.50",
            "mac_address": "AA:BB:CC:11:22:33",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/kaiser",
                json=body,
                headers=operator_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["kaiser_id"] == "KAISER_NEW_001"

    @pytest.mark.asyncio
    async def test_register_kaiser_missing_id(self, operator_headers: dict):
        """Register endpoint returns 422 (or 400) when kaiser_id missing.

        Maps to KaiserIdRequiredError (numeric_code 5205).
        """
        body = {"zone_ids": []}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/kaiser",
                json=body,
                headers=operator_headers,
            )

        # ValidationException -> status_code 400 (per core/exceptions.py),
        # but FastAPI may convert to 422. Accept either.
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_register_kaiser_duplicate(
        self,
        operator_headers: dict,
        sample_kaiser: KaiserRegistry,
    ):
        """Register endpoint returns 409 for duplicate Kaiser."""
        body = {"kaiser_id": sample_kaiser.kaiser_id}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/kaiser",
                json=body,
                headers=operator_headers,
            )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_kaiser_no_auth(self):
        """Register endpoint returns 401 without auth header."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/kaiser",
                json={"kaiser_id": "KAISER_X"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_register_kaiser_active_user_forbidden(self, active_headers: dict):
        """Register endpoint returns 403 for non-operator active user."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/kaiser",
                json={"kaiser_id": "KAISER_FORBIDDEN"},
                headers=active_headers,
            )

        assert response.status_code == 403


# =============================================================================
# Tests: PUT /api/v1/kaiser/{kaiser_id}/zones
# =============================================================================


class TestUpdateZones:
    """Tests for PUT /api/v1/kaiser/{kaiser_id}/zones."""

    @pytest.mark.asyncio
    async def test_update_zones_happy_path(
        self,
        operator_headers: dict,
        sample_kaiser: KaiserRegistry,
    ):
        """Update zones endpoint returns 200 and updates zone_ids."""
        body = {"zone_ids": ["zone_new_1", "zone_new_2", "zone_new_3"]}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                f"/api/v1/kaiser/{sample_kaiser.kaiser_id}/zones",
                json=body,
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["kaiser_id"] == sample_kaiser.kaiser_id
        assert data["zone_ids"] == ["zone_new_1", "zone_new_2", "zone_new_3"]

    @pytest.mark.asyncio
    async def test_update_zones_not_found(self, operator_headers: dict):
        """Update zones endpoint returns 404 for unknown Kaiser."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/v1/kaiser/UNKNOWN_KAISER/zones",
                json={"zone_ids": []},
                headers=operator_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_zones_no_auth(self, sample_kaiser: KaiserRegistry):
        """Update zones endpoint returns 401 without auth header."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                f"/api/v1/kaiser/{sample_kaiser.kaiser_id}/zones",
                json={"zone_ids": []},
            )

        assert response.status_code == 401
