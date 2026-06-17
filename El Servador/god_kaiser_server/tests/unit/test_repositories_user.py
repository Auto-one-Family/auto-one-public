"""
Unit Tests: UserRepository
Tests for user authentication and management operations
"""

import pytest
import pytest_asyncio

from src.core.security import verify_password
from src.db.repositories.user_repo import UserRepository


@pytest.mark.asyncio
class TestUserRepositoryGetByUsername:
    """Test UserRepository.get_by_username()"""

    async def test_get_by_username_success(self, user_repo: UserRepository):
        """Test successful retrieval by username."""
        user = await user_repo.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            role="operator",
        )

        retrieved = await user_repo.get_by_username("testuser")

        assert retrieved is not None
        assert retrieved.username == "testuser"
        assert retrieved.id == user.id

    async def test_get_by_username_not_found(self, user_repo: UserRepository):
        """Test retrieval with non-existent username."""
        result = await user_repo.get_by_username("nonexistent")
        assert result is None


@pytest.mark.asyncio
class TestUserRepositoryGetByEmail:
    """Test UserRepository.get_by_email()"""

    async def test_get_by_email_success(self, user_repo: UserRepository):
        """Test successful retrieval by email."""
        user = await user_repo.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        retrieved = await user_repo.get_by_email("test@example.com")

        assert retrieved is not None
        assert retrieved.email == "test@example.com"
        assert retrieved.id == user.id

    async def test_get_by_email_not_found(self, user_repo: UserRepository):
        """Test retrieval with non-existent email."""
        result = await user_repo.get_by_email("nonexistent@example.com")
        assert result is None


@pytest.mark.asyncio
class TestUserRepositoryCreateUser:
    """Test UserRepository.create_user()"""

    async def test_create_user_success(self, user_repo: UserRepository):
        """Test successful user creation."""
        user = await user_repo.create_user(
            username="newuser",
            email="newuser@example.com",
            password="securepass123",
            role="admin",
            full_name="New User",
        )

        assert user is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.role == "admin"
        assert user.full_name == "New User"
        assert user.is_active is True  # Default
        # Password should be hashed
        assert user.password_hash != "securepass123"
        assert verify_password("securepass123", user.password_hash)

    async def test_create_user_default_role(self, user_repo: UserRepository):
        """Test user creation with default role."""
        user = await user_repo.create_user(
            username="viewer",
            email="viewer@example.com",
            password="pass123",
        )

        assert user.role == "viewer"  # Default role


@pytest.mark.asyncio
class TestUserRepositoryAuthenticate:
    """Test UserRepository.authenticate()"""

    async def test_authenticate_success(self, user_repo: UserRepository):
        """Test successful authentication."""
        await user_repo.create_user(
            username="authuser",
            email="auth@example.com",
            password="correctpass",
        )

        user = await user_repo.authenticate("authuser", "correctpass")

        assert user is not None
        assert user.username == "authuser"

    async def test_authenticate_wrong_password(self, user_repo: UserRepository):
        """Test authentication with wrong password."""
        await user_repo.create_user(
            username="authuser",
            email="auth@example.com",
            password="correctpass",
        )

        user = await user_repo.authenticate("authuser", "wrongpass")

        assert user is None

    async def test_authenticate_nonexistent_user(self, user_repo: UserRepository):
        """Test authentication with non-existent user."""
        user = await user_repo.authenticate("nonexistent", "anypass")

        assert user is None


@pytest.mark.asyncio
class TestUserRepositoryUpdatePassword:
    """Test UserRepository.update_password()"""

    async def test_update_password_success(self, user_repo: UserRepository):
        """Test successful password update."""
        user = await user_repo.create_user(
            username="passuser",
            email="pass@example.com",
            password="oldpass",
        )

        updated = await user_repo.update_password(user.id, "newpass")

        assert updated is not None
        assert verify_password("newpass", updated.password_hash)
        assert not verify_password("oldpass", updated.password_hash)

    async def test_update_password_not_found(self, user_repo: UserRepository):
        """Test password update with non-existent user."""
        result = await user_repo.update_password(99999, "newpass")
        assert result is None


@pytest.mark.asyncio
class TestUserRepositoryGetActiveUsers:
    """Test UserRepository.get_active_users()"""

    async def test_get_active_users_success(self, user_repo: UserRepository):
        """Test retrieval of active users."""
        await user_repo.create_user(
            username="active1",
            email="active1@example.com",
            password="pass",
        )

        await user_repo.create_user(
            username="active2",
            email="active2@example.com",
            password="pass",
        )

        # Create inactive user
        inactive_user = await user_repo.create(
            username="inactive",
            email="inactive@example.com",
            password_hash="hash",
            is_active=False,
        )

        active_users = await user_repo.get_active_users()

        assert len(active_users) == 2
        usernames = {u.username for u in active_users}
        assert usernames == {"active1", "active2"}


@pytest.mark.asyncio
class TestUserRepositoryGetByRole:
    """Test UserRepository.get_by_role()"""

    async def test_get_by_role_success(self, user_repo: UserRepository):
        """Test retrieval by role."""
        await user_repo.create_user(
            username="admin1",
            email="admin1@example.com",
            password="pass",
            role="admin",
        )

        await user_repo.create_user(
            username="admin2",
            email="admin2@example.com",
            password="pass",
            role="admin",
        )

        await user_repo.create_user(
            username="operator1",
            email="operator1@example.com",
            password="pass",
            role="operator",
        )

        admins = await user_repo.get_by_role("admin")

        assert len(admins) == 2
        usernames = {u.username for u in admins}
        assert usernames == {"admin1", "admin2"}
