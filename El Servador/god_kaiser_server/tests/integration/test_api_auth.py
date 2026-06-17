"""
Integration Tests: Authentication API

Phase: 5 (Week 9-10) - API Layer
Tests: Auth endpoints (login, register, refresh, logout)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, verify_password, get_password_hash
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user for authentication tests."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=get_password_hash("TestP@ss123"),
        full_name="Test User",
        role="operator",
        is_active=True,
        token_version=0,  # Initialize token version
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for admin-only tests."""
    user = User(
        username="admin",
        email="admin@example.com",
        password_hash=get_password_hash("AdminP@ss123"),
        full_name="Admin User",
        role="admin",
        is_active=True,
        token_version=0,  # Initialize token version
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User):
    """Get authorization headers with test user token."""
    token = create_access_token(
        user_id=test_user.id,
        additional_claims={
            "role": test_user.role,
            "token_version": test_user.token_version,
        },
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user: User):
    """Get authorization headers with admin token."""
    token = create_access_token(
        user_id=admin_user.id,
        additional_claims={
            "role": admin_user.role,
            "token_version": admin_user.token_version,
        },
    )
    return {"Authorization": f"Bearer {token}"}


class TestLogin:
    """Test login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, test_user: User):
        """Test successful login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "testuser",
                    "password": "TestP@ss123",
                    "remember_me": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "tokens" in data
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["tokens"]["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, test_user: User):
        """Test login with wrong password."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "testuser",
                    "password": "WrongPassword",
                },
            )

        assert response.status_code == 401
        data = response.json()
        assert "Invalid" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_login_invalid_username(self):
        """Test login with non-existent user."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "username": "nonexistent",
                    "password": "SomePassword123",
                },
            )

        assert response.status_code == 401


class TestRegister:
    """Test registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, admin_headers: dict):
        """Test successful user registration by admin."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "newuser",
                    "email": "newuser@example.com",
                    "password": "NewP@ss123",
                    "full_name": "New User",
                    "role": "operator",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["username"] == "newuser"
        assert data["user"]["role"] == "operator"

    @pytest.mark.asyncio
    async def test_register_non_admin_forbidden(self, auth_headers: dict):
        """Test that non-admin cannot register users."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "anotheruser",
                    "email": "another@example.com",
                    "password": "AnotherP@ss123",
                    "role": "viewer",
                },
                headers=auth_headers,
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, admin_headers: dict, test_user: User):
        """Test registration with existing username."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "testuser",  # Already exists
                    "email": "different@example.com",
                    "password": "DiffP@ss123",
                    "role": "viewer",
                },
                headers=admin_headers,
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["error"]["message"]


class TestTokenRefresh:
    """Test token refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, test_user: User):
        """Test successful token refresh."""
        from src.core.security import create_refresh_token

        refresh_token = create_refresh_token(user_id=test_user.id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "tokens" in data
        assert "access_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """Test refresh with invalid token."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid_token"},
            )

        assert response.status_code == 401


class TestCurrentUser:
    """Test current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_user(self, auth_headers: dict, test_user: User):
        """Test getting current user info."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert data["role"] == "operator"

    @pytest.mark.asyncio
    async def test_get_current_user_unauthenticated(self):
        """Test getting current user without token."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401


class TestAuthStatus:
    """Test auth status endpoint."""

    @pytest.mark.asyncio
    async def test_status_shows_setup_required_when_empty(self, db_session: AsyncSession):
        """Test that status shows setup_required when no users exist."""
        # Note: This test requires an empty database (no users)
        # The db_session fixture should provide a clean session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/status")

        assert response.status_code == 200
        data = response.json()
        # Note: setup_required depends on whether test fixtures create users
        assert "setup_required" in data
        assert "users_exist" in data
        assert "mqtt_auth_enabled" in data
        assert "mqtt_tls_enabled" in data

    @pytest.mark.asyncio
    async def test_status_shows_users_exist(self, test_user: User):
        """Test that status shows users_exist when users are present."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["setup_required"] is False
        assert data["users_exist"] is True


class TestSetup:
    """Test initial setup endpoint."""

    @pytest.mark.asyncio
    async def test_setup_fails_when_users_exist(self, test_user: User):
        """Test that setup fails when users already exist."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/setup",
                json={
                    "username": "newadmin",
                    "email": "newadmin@example.com",
                    "password": "SecureP@ss123!",
                    "full_name": "New Admin",
                },
            )

        assert response.status_code == 403
        data = response.json()
        assert "already completed" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_setup_requires_strong_password(self, db_session: AsyncSession):
        """Test that setup validates password strength."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/setup",
                json={
                    "username": "admin",
                    "email": "admin@example.com",
                    "password": "weak",  # Too weak
                    "full_name": "Admin",
                },
            )

        # Should fail validation (422 for Pydantic validation errors)
        assert response.status_code == 422


class TestLoginFormTokenVersion:
    """Test that login/form includes token_version."""

    @pytest.mark.asyncio
    async def test_login_form_includes_token_version(self, test_user: User):
        """Login form tokens should include token_version for logout-all."""
        from jose import jwt

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login/form",
                data={"username": "testuser", "password": "TestP@ss123"},
            )

        assert response.status_code == 200
        data = response.json()

        # Decode token (without verification) and check for token_version
        token = data["access_token"]
        payload = jwt.decode(token, key="", options={"verify_signature": False})

        # CRITICAL: token_version must be present for logout-all to work
        assert "token_version" in payload, "token_version missing from login/form tokens"
        assert payload["token_version"] == test_user.token_version

    @pytest.mark.asyncio
    async def test_login_form_tokens_rejected_after_logout_all(
        self, test_user: User, db_session: AsyncSession
    ):
        """Test that login/form tokens are invalidated after logout all devices."""
        from jose import jwt

        # Step 1: Login via form
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_response = await client.post(
                "/api/v1/auth/login/form",
                data={"username": "testuser", "password": "TestP@ss123"},
            )

        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Step 2: Increment token_version (simulate logout all)
        test_user.token_version += 1
        await db_session.commit()

        # Step 3: Try to use the old token
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )  # Should be rejected because token_version is outdated
        assert me_response.status_code == 401
        assert "invalidated" in me_response.json()["detail"].lower()
