"""
Integration Tests: Authentication Security Features

Tests for newly implemented security features:
- Token Rotation (Refresh Token)
- Logout All Devices (Token Versioning)
- MQTT Authentication Configuration
- MQTT Auth Update Broadcasting

These tests are realistic and test actual system behavior, not just mocks.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, create_refresh_token, get_password_hash
from src.db.models.user import User
from src.db.repositories.esp_repo import ESPRepository
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.db.repositories.token_blacklist_repo import TokenBlacklistRepository
from src.db.repositories.user_repo import UserRepository
from src.main import app
from src.services.mqtt_auth_service import MQTTAuthService


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user with token_version."""
    user = User(
        username="security_testuser",
        email="security_test@example.com",
        password_hash=get_password_hash("TestP@ss123"),
        full_name="Security Test User",
        role="operator",
        is_active=True,
        token_version=0,  # Start with version 0
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user."""
    user = User(
        username="security_admin",
        email="security_admin@example.com",
        password_hash=get_password_hash("AdminP@ss123"),
        full_name="Security Admin",
        role="admin",
        is_active=True,
        token_version=0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User):
    """Create admin access token with token_version."""
    return create_access_token(
        user_id=admin_user.id,
        additional_claims={
            "role": admin_user.role,
            "token_version": admin_user.token_version,
        },
    )


@pytest.fixture
def admin_headers(admin_token: str):
    """Get admin authorization headers."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestTokenRotation:
    """Test refresh token rotation functionality."""

    @pytest.mark.asyncio
    async def test_refresh_rotates_old_token(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """
        Test that refreshing a token blacklists the old refresh token.

        This is a critical security feature - old refresh tokens must be invalidated
        to prevent token reuse attacks.
        """
        # Create initial refresh token
        old_refresh_token = create_refresh_token(user_id=test_user.id)

        # Verify old token is valid
        from src.core.security import verify_token

        payload = verify_token(old_refresh_token, expected_type="refresh")
        assert payload.get("sub") == str(test_user.id)

        # Refresh token - should blacklist old one
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": old_refresh_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "tokens" in data
        new_access_token = data["tokens"]["access_token"]
        new_refresh_token = data["tokens"]["refresh_token"]

        # Verify old refresh token is blacklisted
        # Note: We need to use the same db session that the endpoint uses
        # The endpoint uses override_get_db, so we check via the endpoint's session
        # by trying to use the old token again (which should fail)

        # Verify old refresh token cannot be used again
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": old_refresh_token},
            )
        assert response.status_code == 401, "Old refresh token should be rejected"

        # Verify new refresh token works
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": new_refresh_token},
            )
        assert response.status_code == 200, "New refresh token should work"

    @pytest.mark.asyncio
    async def test_refresh_includes_token_version(self, test_user: User, override_get_db):
        """
        Test that refreshed tokens include token_version claim.

        This ensures token versioning works correctly after refresh.
        """
        refresh_token = create_refresh_token(user_id=test_user.id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )

        assert response.status_code == 200
        data = response.json()
        new_access_token = data["tokens"]["access_token"]

        # Verify new token includes token_version
        from src.core.security import verify_token

        payload = verify_token(new_access_token, expected_type="access")
        assert "token_version" in payload, "New token should include token_version"
        assert payload["token_version"] == test_user.token_version


class TestLogoutAllDevices:
    """Test logout all devices (token versioning) functionality."""

    @pytest.mark.asyncio
    async def test_logout_all_increments_token_version(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """
        Test that logout all devices increments token_version.

        This invalidates all existing tokens across all devices.
        """
        initial_version = test_user.token_version

        # Create a token with current version
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Verify token works
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200

        # Logout all devices
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": True},
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify token_version was incremented
        await db_session.refresh(test_user)
        assert test_user.token_version == initial_version + 1, "Token version should be incremented"

        # Verify old token is now invalid (version mismatch)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401, "Old token should be rejected due to version mismatch"
        detail_lower = response.json()["detail"].lower()
        assert any(
            keyword in detail_lower
            for keyword in ["invalidated", "unauthorized", "revoked", "invalid"]
        ), f"Error message should indicate token invalidation, got: {response.json()['detail']}"

    @pytest.mark.asyncio
    async def test_logout_all_prevents_token_reuse(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """
        Test that after logout all, old tokens cannot be used even if not blacklisted.

        This tests the token versioning mechanism - tokens with old versions
        are rejected even if they're not in the blacklist.
        """
        # Create multiple tokens (simulating multiple devices)
        token1 = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )
        token2 = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )

        # Verify both tokens work
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers=headers1)
            assert response.status_code == 200
            response = await client.get("/api/v1/auth/me", headers=headers2)
            assert response.status_code == 200

        # Logout all devices (using token1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": True},
                headers=headers1,
            )
        assert response.status_code == 200

        # Verify both tokens are now invalid
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers=headers1)
            assert response.status_code == 401, "Token1 should be invalid"

            response = await client.get("/api/v1/auth/me", headers=headers2)
            assert response.status_code == 401, "Token2 should be invalid (version mismatch)"

    @pytest.mark.asyncio
    async def test_logout_single_device_does_not_increment_version(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """
        Test that logout single device does NOT increment token_version.

        Only logout all devices should increment version.
        """
        initial_version = test_user.token_version
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Logout single device
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": False},
                headers=headers,
            )

        assert response.status_code == 200

        # Verify token_version was NOT incremented
        await db_session.refresh(test_user)
        assert (
            test_user.token_version == initial_version
        ), "Token version should NOT be incremented for single logout"


class TestMQTTAuthService:
    """Test MQTT Authentication Service functionality."""

    @pytest.mark.asyncio
    async def test_hash_mosquitto_password_format(self):
        """
        Test that password hashing produces correct Mosquitto format.

        Format: $6$salt$hash (6 = SHA-512)
        """
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        password = "TestPassword123"
        hashed = service.hash_mosquitto_password(password)

        # Verify format
        assert hashed.startswith("$6$"), "Hash should start with $6$ (SHA-512)"
        parts = hashed.split("$")
        assert len(parts) == 4, "Hash should have format $6$salt$hash"
        assert len(parts[2]) == 32, "Salt should be 16 bytes = 32 hex chars"
        assert len(parts[3]) == 128, "SHA-512 hash should be 64 bytes = 128 hex chars"

    @pytest.mark.asyncio
    async def test_configure_credentials_persists_to_db(self, db_session: AsyncSession):
        """
        Test that MQTT credentials are persisted to database.

        This ensures configuration survives server restarts.
        """
        system_config_repo = SystemConfigRepository(db_session)
        service = MQTTAuthService(system_config_repo, None)

        # Mock file operations
        with (
            patch("src.services.mqtt_auth_service.MQTTAuthService._update_passwd_file"),
            patch(
                "src.services.mqtt_auth_service.MQTTAuthService.reload_mosquitto", return_value=True
            ),
        ):

            await service.configure_credentials(
                username="test_mqtt_user",
                password="TestMqttP@ss123",
                enabled=True,
            )
            await db_session.commit()

        # Verify config in database
        config = await system_config_repo.get_mqtt_auth_config()
        assert config["enabled"] is True
        assert config["username"] == "test_mqtt_user"
        assert config["password_hash"] is not None
        assert config["last_configured"] is not None

    @pytest.mark.asyncio
    async def test_broadcast_auth_update_requires_tls(self, db_session: AsyncSession):
        """
        Test that auth_update broadcast is refused without TLS.

        This is a critical security check - credentials must not be sent in plain text.
        """
        system_config_repo = SystemConfigRepository(db_session)
        esp_repo = ESPRepository(db_session)
        service = MQTTAuthService(system_config_repo, esp_repo)

        # Mock settings to disable TLS
        with patch("src.services.mqtt_auth_service.settings") as mock_settings:
            mock_settings.mqtt.use_tls = False

            # Attempt to broadcast - should raise RuntimeError
            with pytest.raises(RuntimeError) as exc_info:
                await service.broadcast_auth_update(
                    username="test_user",
                    password="test_password",
                )

            assert "TLS" in str(exc_info.value), "Error should mention TLS requirement"

    @pytest.mark.asyncio
    async def test_broadcast_auth_update_with_tls(self, db_session: AsyncSession):
        """
        Test that auth_update broadcast works when TLS is enabled.

        This tests the happy path for credential distribution.
        """
        system_config_repo = SystemConfigRepository(db_session)
        esp_repo = ESPRepository(db_session)
        service = MQTTAuthService(system_config_repo, esp_repo)

        # Create test ESP device
        from src.db.models.esp import ESPDevice

        esp_device = ESPDevice(
            device_id="ESP_TEST_001",
            name="Test ESP",
            ip_address="192.168.1.100",
            status="online",
            hardware_type="ESP32_WROOM",  # Required field
        )
        db_session.add(esp_device)
        await db_session.commit()

        # Mock settings to enable TLS
        with (
            patch("src.services.mqtt_auth_service.settings") as mock_settings,
            patch("src.services.mqtt_auth_service.Publisher") as mock_publisher_class,
        ):

            mock_settings.mqtt.use_tls = True
            mock_publisher = MagicMock()
            # _publish_with_retry is sync in Publisher, not async
            mock_publisher._publish_with_retry = MagicMock(return_value=True)
            mock_publisher_class.return_value = mock_publisher
            service.publisher = mock_publisher

            # Broadcast should succeed
            count = await service.broadcast_auth_update(
                username="test_user",
                password="test_password",
            )

            assert count == 1, "Should broadcast to 1 ESP device"
            # Verify the async method was called
            mock_publisher._publish_with_retry.assert_called()


class TestMQTTConfigureEndpoint:
    """Test MQTT configuration API endpoints."""

    @pytest.mark.asyncio
    async def test_configure_mqtt_auth_requires_admin(self, test_user: User, override_get_db):
        """
        Test that MQTT auth configuration requires admin privileges.

        This is a security check - only admins should configure MQTT authentication.
        """
        # Create token for non-admin user
        token = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,  # operator, not admin
                "token_version": test_user.token_version,
            },
        )
        headers = {"Authorization": f"Bearer {token}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/mqtt/configure",
                json={
                    "username": "mqtt_user",
                    "password": "MqttP@ss123",
                    "enabled": True,
                },
                headers=headers,
            )

        assert response.status_code == 403, "Non-admin should be forbidden"
        assert "admin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_configure_mqtt_auth_success(
        self, admin_user: User, admin_headers: dict, db_session: AsyncSession, override_get_db
    ):
        """
        Test successful MQTT auth configuration.

        This tests the full flow: password hashing, file update, broker reload, DB persistence.
        """
        # Mock file and broker operations
        with (
            patch("src.services.mqtt_auth_service.MQTTAuthService._update_passwd_file"),
            patch(
                "src.services.mqtt_auth_service.MQTTAuthService.reload_mosquitto", return_value=True
            ),
            patch(
                "src.services.mqtt_auth_service.MQTTAuthService.broadcast_auth_update",
                new_callable=AsyncMock,
            ) as mock_broadcast,
        ):

            mock_broadcast.side_effect = RuntimeError("TLS not enabled")  # Simulate TLS disabled

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/auth/mqtt/configure",
                    json={
                        "username": "mqtt_user",
                        "password": "MqttP@ss123",
                        "enabled": True,
                    },
                    headers=admin_headers,
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["username"] == "mqtt_user"
            assert data["enabled"] is True
            assert data["broker_reloaded"] is True

        # Verify config persisted to database
        system_config_repo = SystemConfigRepository(db_session)
        config = await system_config_repo.get_mqtt_auth_config()
        assert config["enabled"] is True
        assert config["username"] == "mqtt_user"

    @pytest.mark.asyncio
    async def test_get_mqtt_auth_status(
        self, admin_user: User, admin_headers: dict, db_session: AsyncSession, override_get_db
    ):
        """
        Test getting MQTT auth status.

        This tests the status endpoint returns correct configuration state.
        """
        # Configure MQTT auth first
        system_config_repo = SystemConfigRepository(db_session)
        await system_config_repo.set_mqtt_auth_config(
            enabled=True,
            username="status_test_user",
            password_hash="$6$salt$hash",
        )
        await db_session.commit()

        # Mock MQTT client
        with patch("src.mqtt.client.MQTTClient") as mock_mqtt_client_class:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = True
            mock_mqtt_client_class.get_instance.return_value = mock_client

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/auth/mqtt/status",
                    headers=admin_headers,
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["enabled"] is True
            assert data["username"] == "status_test_user"
            assert data["broker_connected"] is True


class TestTokenVersioningEdgeCases:
    """Test edge cases for token versioning."""

    @pytest.mark.asyncio
    async def test_old_token_without_version_still_works(self, test_user: User, override_get_db):
        """
        Test that tokens without token_version claim still work (backward compatibility).

        This ensures old tokens (created before versioning) continue to work.
        """
        # Create token without token_version (old format)
        old_token = create_access_token(
            user_id=test_user.id,
            additional_claims={"role": test_user.role},
            # No token_version claim
        )
        headers = {"Authorization": f"Bearer {old_token}"}

        # Token should still work (backward compatibility)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers=headers)

        # Should work if user.token_version is 0, or fail gracefully if > 0
        # The implementation allows old tokens if user.token_version is 0
        if test_user.token_version == 0:
            assert response.status_code == 200
        else:
            # If version was incremented, old token should fail
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_version_incremented_after_logout_all(
        self, test_user: User, db_session: AsyncSession, override_get_db
    ):
        """
        Test that token_version increments correctly after multiple logout_all calls.

        This tests that versioning works correctly across multiple operations.
        """
        initial_version = test_user.token_version

        # First logout all
        token1 = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )
        headers1 = {"Authorization": f"Bearer {token1}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": True},
                headers=headers1,
            )
        assert response.status_code == 200

        await db_session.refresh(test_user)
        assert test_user.token_version == initial_version + 1

        # Second logout all
        token2 = create_access_token(
            user_id=test_user.id,
            additional_claims={
                "role": test_user.role,
                "token_version": test_user.token_version,
            },
        )
        headers2 = {"Authorization": f"Bearer {token2}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/logout",
                json={"all_devices": True},
                headers=headers2,
            )
        assert response.status_code == 200

        await db_session.refresh(test_user)
        assert test_user.token_version == initial_version + 2, "Version should increment again"
