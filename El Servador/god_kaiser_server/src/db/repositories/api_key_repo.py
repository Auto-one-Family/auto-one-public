"""
API Key Repository: DB-backed API Key Validation Operations (AUT-290)

Provides database operations for API key creation, lookup by hash,
revocation, and usage tracking.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.api_key import ApiKey


class ApiKeyRepository:
    """
    API Key Repository.

    Manages API key records for secure device authentication.
    All lookups use SHA256 hash — plaintext keys are never stored.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        self.session = session

    async def get_by_hash(self, raw_key: str) -> Optional[ApiKey]:
        """
        Look up an API key by hashing the raw key and querying the DB.

        Args:
            raw_key: Plaintext API key provided by the caller

        Returns:
            ApiKey instance if found, None otherwise
        """
        key_hash = ApiKey.hash_key(raw_key)
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, key_id: uuid.UUID) -> Optional[ApiKey]:
        """
        Retrieve an API key by its primary key.

        Args:
            key_id: UUID primary key of the ApiKey record

        Returns:
            ApiKey instance if found, None otherwise
        """
        stmt = select(ApiKey).where(ApiKey.id == key_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> list[ApiKey]:
        """
        Return all API key records (active and revoked).

        Returns:
            List of ApiKey instances ordered by creation time descending
        """
        stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        raw_key: str,
        key_prefix: str,
        owner_type: str,
        owner_id: Optional[str] = None,
        scopes: Optional[list] = None,
        created_by: Optional[int] = None,
    ) -> ApiKey:
        """
        Persist a new API key record (stores hash, not plaintext).

        Args:
            raw_key: Plaintext API key — will be hashed before storage
            key_prefix: Human-readable prefix (e.g. "esp_")
            owner_type: Owner category ("esp", "god_layer", "service")
            owner_id: Optional owner identifier (e.g. ESP UUID)
            scopes: List of permission scopes; defaults to empty list
            created_by: User ID that triggered the creation

        Returns:
            Persisted ApiKey instance (raw_key is NOT stored on the object)
        """
        api_key = ApiKey(
            key_hash=ApiKey.hash_key(raw_key),
            key_prefix=key_prefix,
            owner_type=owner_type,
            owner_id=owner_id,
            scopes=scopes if scopes is not None else [],
            created_by=created_by,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def revoke(self, key_id: uuid.UUID) -> bool:
        """
        Revoke an API key by setting its revoked_at timestamp.

        Args:
            key_id: UUID of the ApiKey to revoke

        Returns:
            True if a record was updated, False if key_id was not found
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .where(ApiKey.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def touch_last_used(self, key_id: uuid.UUID) -> None:
        """
        Update last_used_at to the current UTC time.

        Called on every successful authentication to track key usage.

        Args:
            key_id: UUID of the ApiKey that was just used
        """
        now = datetime.now(timezone.utc)
        stmt = update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=now)
        await self.session.execute(stmt)
        await self.session.flush()
