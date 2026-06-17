"""
Token Blacklist Repository: Token Revocation Operations

Provides database operations for token blacklisting and validation.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auth import TokenBlacklist


class TokenBlacklistRepository:
    """
    Token Blacklist Repository.

    Manages token blacklist entries for JWT revocation.
    Provides efficient lookup and cleanup operations.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        self.session = session

    async def add_token(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        user_id: int,
        expires_at: datetime,
        reason: Optional[str] = None,
    ) -> TokenBlacklist:
        """
        Add a token to the blacklist.

        Args:
            token: Raw JWT token string
            token_type: "access" or "refresh"
            user_id: User ID the token belongs to
            expires_at: Token expiration time (for cleanup)
            reason: Optional reason for blacklisting

        Returns:
            Created TokenBlacklist entry
        """
        entry = TokenBlacklist.create_blacklist_entry(
            token=token,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def is_blacklisted(self, token: str) -> bool:
        """
        Check if a token is blacklisted.

        Uses SHA256 hash for lookup (efficient with index).

        Args:
            token: Raw JWT token string

        Returns:
            True if token is blacklisted, False otherwise
        """
        token_hash = TokenBlacklist.hash_token(token)
        stmt = (
            select(func.count())
            .select_from(TokenBlacklist)
            .where(TokenBlacklist.token_hash == token_hash)
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()
        return count > 0

    async def get_by_token(self, token: str) -> Optional[TokenBlacklist]:
        """
        Get blacklist entry by token.

        Args:
            token: Raw JWT token string

        Returns:
            TokenBlacklist entry or None if not blacklisted
        """
        token_hash = TokenBlacklist.hash_token(token)
        stmt = select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def blacklist_user_tokens(
        self,
        user_id: int,
        reason: str = "logout_all_devices",
    ) -> int:
        """
        Mark all tokens for a user as requiring refresh.

        Note: This doesn't actually blacklist existing tokens since we don't
        track active tokens. Instead, you should:
        1. Update user's token_invalidated_at timestamp
        2. Reject tokens issued before that timestamp

        For now, this just returns 0 as a placeholder.
        Full implementation requires token tracking or token versioning.

        Args:
            user_id: User ID to invalidate tokens for
            reason: Reason for invalidation

        Returns:
            Number of tokens invalidated (always 0 for now)
        """
        # TODO: Implement proper "logout all devices" with token versioning
        # This would require either:
        # 1. Tracking all active tokens per user
        # 2. Adding a token_version to users and checking on auth
        return 0

    async def cleanup_expired(self) -> int:
        """
        Remove expired blacklist entries.

        Entries where expires_at < now can be safely removed since
        the tokens are no longer valid anyway.

        Returns:
            Number of entries removed
        """
        now = datetime.now(timezone.utc)
        stmt = delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_user_blacklist_count(self, user_id: int) -> int:
        """
        Get count of blacklisted tokens for a user.

        Args:
            user_id: User ID

        Returns:
            Number of blacklisted tokens
        """
        stmt = (
            select(func.count())
            .select_from(TokenBlacklist)
            .where(TokenBlacklist.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_total_blacklist_count(self) -> int:
        """
        Get total count of blacklisted tokens.

        Returns:
            Total number of blacklisted tokens
        """
        stmt = select(func.count()).select_from(TokenBlacklist)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def remove_entry(self, token: str) -> bool:
        """
        Remove a specific token from the blacklist.

        Use with caution - this re-enables a revoked token.

        Args:
            token: Raw JWT token string

        Returns:
            True if removed, False if not found
        """
        token_hash = TokenBlacklist.hash_token(token)
        stmt = delete(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
