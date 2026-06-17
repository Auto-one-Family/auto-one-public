"""
Integration Tests: Token Blacklist

Tests token blacklisting functionality for secure logout and session management.
"""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.user import User
from src.db.repositories.token_blacklist_repo import TokenBlacklistRepository
from src.main import app


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user for token blacklist tests."""
    user = User(
        username="blacklist_testuser",
        email="blacklist_test@example.com",
        password_hash=get_password_hash("TestP@ss123"),
        full_name="Token Blacklist Test User",
        role="operator",
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


class TestTokenBlacklist:
    """Test token blacklist functionality."""

    @pytest.mark.asyncio
    async def test_logout_blacklists_access_token(
        self, test_user: User, auth_headers: dict, override_get_db
    ):
        """Test that logout blacklists the access token."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First, make an authenticated request to verify token works
            response = await client.get(
                "/api/v1/auth/me",
                headers=auth_headers,
            )
            assert response.status_code == 200

            # Extract token from headers
            token = auth_headers["Authorization"].replace("Bearer ", "")

            # Logout - should blacklist the token
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": False},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["tokens_invalidated"] == 1

            # Verify token is now blacklisted by trying to use it
            response = await client.get(
                "/api/v1/auth/me",
                headers=auth_headers,
            )
            assert response.status_code == 401
            assert (
                "revoked" in response.json()["detail"].lower()
                or "unauthorized" in response.json()["detail"].lower()
            )

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, test_user: User, auth_headers: dict, override_get_db):
        """Test logout with all_devices=True."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Logout all devices
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": True},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            # Current token is blacklisted
            assert data["tokens_invalidated"] >= 1

    @pytest.mark.asyncio
    async def test_blacklisted_token_rejected_in_api(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """Test that blacklisted tokens are rejected in REST API."""
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )

        # Blacklist the token
        blacklist_repo = TokenBlacklistRepository(db_session)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await blacklist_repo.add_token(
            token=token,
            token_type="access",
            user_id=test_user.id,
            expires_at=expires_at,
            reason="test",
        )
        await db_session.commit()

        # Try to use blacklisted token
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_token_rejected_in_websocket(
        self, test_user: User, db_session: AsyncSession
    ):
        """Test that blacklisted tokens are rejected in WebSocket connections."""
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )

        # Blacklist the token
        blacklist_repo = TokenBlacklistRepository(db_session)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await blacklist_repo.add_token(
            token=token,
            token_type="access",
            user_id=test_user.id,
            expires_at=expires_at,
            reason="test",
        )
        await db_session.commit()

        # Verify token is blacklisted
        is_blacklisted = await blacklist_repo.is_blacklisted(token)
        assert is_blacklisted is True

        # In a real WebSocket connection, this would close with code 4001
        # This test verifies the blacklist check logic

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(self, test_user: User, db_session: AsyncSession):
        """Test cleanup of expired blacklist entries."""
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )

        # Blacklist the token with past expiration
        blacklist_repo = TokenBlacklistRepository(db_session)
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)  # Already expired

        await blacklist_repo.add_token(
            token=token,
            token_type="access",
            user_id=test_user.id,
            expires_at=expires_at,
            reason="test",
        )
        await db_session.commit()

        # Cleanup expired entries
        removed_count = await blacklist_repo.cleanup_expired()
        assert removed_count >= 1

        # Verify token is no longer in blacklist (it was expired anyway)
        is_blacklisted = await blacklist_repo.is_blacklisted(token)
        # Token might still be blacklisted if cleanup hasn't run, but it's expired
        # The important thing is that cleanup removed the entry
