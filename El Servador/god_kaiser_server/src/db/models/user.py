"""
User Model: Authentication, Roles, Permissions
"""

from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    User Account Model.

    Stores user authentication and authorization information.

    Attributes:
        id: Primary key (auto-increment)
        username: Unique username
        email: Unique email address
        password_hash: Bcrypt hashed password
        role: User role (admin, operator, viewer)
        is_active: Whether account is active
        full_name: User's full name
        metadata: Additional user metadata
    """

    __tablename__ = "user_accounts"

    # Primary Key
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        doc="Primary key (auto-increment)",
    )

    # Identity
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique username",
    )

    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique email address",
    )

    # Authentication
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Bcrypt hashed password",
    )

    # Authorization
    role: Mapped[str] = mapped_column(
        String(20),
        default="viewer",
        nullable=False,
        doc="User role (admin, operator, viewer)",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether account is active",
    )

    # Profile
    full_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="User's full name",
    )

    # Token Versioning (for logout all devices)
    token_version: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Token version (incremented on logout all devices)",
    )

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', role='{self.role}')>"

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role == "admin"

    @property
    def is_operator(self) -> bool:
        """Check if user has operator role"""
        return self.role == "operator"
