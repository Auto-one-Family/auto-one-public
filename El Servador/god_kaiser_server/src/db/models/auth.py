"""
Token Blacklist Model: JWT Token Revocation

Provides token blacklisting for secure logout and session management.
Uses SHA256 hash of tokens for storage (no plain text tokens).
"""

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class TokenBlacklist(Base, TimestampMixin):
    """
    Token Blacklist Model.

    Stores revoked JWT tokens to prevent reuse after logout.
    Tokens are stored as SHA256 hashes for security.

    Attributes:
        id: Primary key (auto-increment)
        token_hash: SHA256 hash of the token (unique, indexed)
        token_type: Token type ("access" or "refresh")
        user_id: User ID the token belongs to (indexed for "logout all")
        expires_at: When the token would naturally expire (for cleanup)
        blacklisted_at: When the token was blacklisted
        reason: Optional reason for blacklisting

    Usage:
        # Blacklist a token
        token_hash = TokenBlacklist.hash_token(raw_token)
        blacklist_entry = TokenBlacklist(
            token_hash=token_hash,
            token_type="access",
            user_id=user_id,
            expires_at=token_expiry,
            blacklisted_at=datetime.now(timezone.utc),
            reason="logout"
        )

        # Check if blacklisted
        is_revoked = await repo.is_blacklisted(raw_token)
    """

    __tablename__ = "token_blacklist"

    # Primary Key
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        doc="Primary key (auto-increment)",
    )

    # Token Identification (SHA256 hash, 64 chars)
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        doc="SHA256 hash of the token",
    )

    # Token Type
    token_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Token type: 'access' or 'refresh'",
    )

    # User Reference (not FK to allow cleanup without cascade issues)
    user_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
        doc="User ID the token belongs to",
    )

    # Expiration (for automatic cleanup of old entries)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
        doc="When the token would naturally expire",
    )

    # Blacklist Timestamp
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="When the token was blacklisted",
    )

    # Reason (optional, for audit trail)
    reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Reason for blacklisting: logout, security, password_change, etc.",
    )

    # Composite Index for cleanup queries
    __table_args__ = (Index("idx_blacklist_expires_at_user", "expires_at", "user_id"),)

    def __repr__(self) -> str:
        return (
            f"<TokenBlacklist(id={self.id}, user_id={self.user_id}, "
            f"type={self.token_type}, hash={self.token_hash[:8]}...)>"
        )

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash a token using SHA256.

        Args:
            token: Raw JWT token string

        Returns:
            64-character hexadecimal hash string
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def create_blacklist_entry(
        token: str,
        token_type: Literal["access", "refresh"],
        user_id: int,
        expires_at: datetime,
        reason: Optional[str] = None,
    ) -> "TokenBlacklist":
        """
        Factory method to create a blacklist entry from a raw token.

        Args:
            token: Raw JWT token string
            token_type: "access" or "refresh"
            user_id: User ID the token belongs to
            expires_at: Token expiration time
            reason: Optional reason for blacklisting

        Returns:
            TokenBlacklist instance (not yet persisted)
        """
        return TokenBlacklist(
            token_hash=TokenBlacklist.hash_token(token),
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at,
            blacklisted_at=datetime.now(timezone.utc),
            reason=reason,
        )
