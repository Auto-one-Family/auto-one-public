"""
User Repository: User Authentication and Management
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.security import get_password_hash, verify_password
from ..models.user import User
from .base_repo import BaseRepository


class UserRepository(BaseRepository[User]):
    """User Repository with authentication-specific queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: str = "viewer",
        full_name: Optional[str] = None,
    ) -> User:
        """Create new user with hashed password."""
        password_hash = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user by username and password."""
        user = await self.get_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def update_password(self, user_id: int, new_password: str) -> Optional[User]:
        """Update user password."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        user.password_hash = get_password_hash(new_password)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_active_users(self) -> list[User]:
        """Get all active users."""
        stmt = select(User).where(User.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_role(self, role: str) -> list[User]:
        """Get users by role."""
        stmt = select(User).where(User.role == role)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
