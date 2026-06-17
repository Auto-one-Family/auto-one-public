"""
API Key Model: DB-backed API Key Validation (AUT-290)

Provides secure API key storage with SHA256 hashing, revocation support,
and scope-based authorization. Replaces prefix-only validation in deps.py.
"""

import hashlib
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin

# Prefix length used for key generation (e.g. "esp_", "god_")
KEY_PREFIX_MAX_LENGTH: int = 8

# SHA256 hex digest length (constant)
KEY_HASH_LENGTH: int = 64

# Owner type values
OWNER_TYPE_ESP: str = "esp"
OWNER_TYPE_GOD_LAYER: str = "god_layer"
OWNER_TYPE_SERVICE: str = "service"


class ApiKey(Base, TimestampMixin):
    """
    API Key Model.

    Stores API keys as SHA256 hashes for secure validation.
    Supports revocation, scopes, and usage tracking.

    Attributes:
        id: Primary key (UUID)
        key_hash: SHA256 hash of the raw key (unique, indexed)
        key_prefix: Human-readable prefix of the key (e.g. "esp_", "god_")
        owner_type: Category of the key owner ("esp", "god_layer", "service")
        owner_id: Optional identifier for the specific owner (e.g. ESP UUID)
        scopes: List of permission scopes granted to this key
        created_by: User ID that created the key (nullable for system keys)
        last_used_at: Timestamp of the last successful authentication
        revoked_at: Timestamp when the key was revoked (None = active)

    Usage:
        # Create and store a new key
        raw_key = "esp_" + secrets.token_urlsafe(32)
        key_hash = ApiKey.hash_key(raw_key)
        api_key = ApiKey(
            key_hash=key_hash,
            key_prefix="esp_",
            owner_type=OWNER_TYPE_ESP,
            owner_id="some-esp-uuid",
        )

        # Validate a key
        stored = await repo.get_by_hash(raw_key)
        if stored and stored.is_valid:
            ...
    """

    __tablename__ = "api_keys"

    # Primary Key (UUID for distributed safety)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID v4)",
    )

    # Key Hash (SHA256, 64 hex chars) — uniqueness enforced via ix_api_keys_key_hash index
    key_hash: Mapped[str] = mapped_column(
        String(KEY_HASH_LENGTH),
        nullable=False,
        doc="SHA256 hash of the raw API key",
    )

    # Prefix for identification (e.g. "esp_", "god_")
    key_prefix: Mapped[str] = mapped_column(
        String(KEY_PREFIX_MAX_LENGTH),
        nullable=False,
        doc="Short prefix identifying the key type (e.g. 'esp_', 'god_')",
    )

    # Owner classification
    owner_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="Owner category: 'esp', 'god_layer', or 'service'",
    )

    # Optional owner reference (e.g. ESP device UUID)
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Optional owner identifier (e.g. ESP UUID or service name)",
    )

    # Scopes as JSON array (e.g. ["sensor:write", "actuator:read"])
    scopes: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="List of permission scopes granted to this key",
    )

    # Creator reference (not FK to avoid cascade complications)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="User ID that created this key (None for system-generated keys)",
    )

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last successful authentication with this key",
    )

    # Revocation timestamp (None = key is active)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when the key was revoked (None means active)",
    )

    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
        Index("ix_api_keys_owner_type", "owner_type"),
    )

    def __repr__(self) -> str:
        status = "revoked" if self.revoked_at else "active"
        return (
            f"<ApiKey(id={self.id}, prefix={self.key_prefix!r}, "
            f"owner_type={self.owner_type!r}, status={status})>"
        )

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """
        Hash a raw API key using SHA256.

        Args:
            raw_key: The plaintext API key string

        Returns:
            64-character hexadecimal SHA256 digest
        """
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @property
    def is_valid(self) -> bool:
        """
        Check whether the key is currently active (not revoked).

        Returns:
            True if revoked_at is None, False otherwise
        """
        return self.revoked_at is None

    @staticmethod
    def build_key(prefix: str, token: str) -> str:
        """
        Construct a raw key string from prefix and token.

        Args:
            prefix: Key prefix (e.g. "esp_")
            token: Random token portion

        Returns:
            Full raw key string (e.g. "esp_<token>")
        """
        return f"{prefix}{token}"
