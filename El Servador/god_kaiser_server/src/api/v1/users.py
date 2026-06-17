"""
User Management API Router

Provides REST endpoints for user CRUD operations.
Admin-only endpoints for managing user accounts.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import (
    AuthenticationError,
    DuplicateError,
    UserNotFoundException,
    ValidationException,
)
from ...core.logging_config import get_logger
from ...core.security import get_password_hash, verify_password
from ...db.repositories.user_repo import UserRepository
from ...db.session import get_session
from ...schemas.user import (
    MessageResponse,
    PasswordChange,
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from ..deps import ActiveUser, AdminUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/users", tags=["Users"])


async def get_db():
    """Get async database session."""
    async for session in get_session():
        yield session


# =============================================================================
# User CRUD (Admin Only)
# =============================================================================


@router.get(
    "",
    response_model=UserListResponse,
    summary="List Users",
    description="Get list of all users. Admin only.",
)
async def list_users(
    current_user: AdminUser, db: AsyncSession = Depends(get_db)
) -> UserListResponse:
    """List all users (admin only)."""
    user_repo = UserRepository(db)
    users = await user_repo.get_all()

    return UserListResponse(
        success=True, users=[UserResponse.model_validate(u) for u in users], total=len(users)
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    summary="Create User",
    description="Create a new user account. Admin only.",
)
async def create_user(
    user_data: UserCreate, current_user: AdminUser, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Create a new user (admin only)."""
    user_repo = UserRepository(db)

    # Check if username already exists
    existing_user = await user_repo.get_by_username(user_data.username)
    if existing_user:
        raise DuplicateError("User", "username", user_data.username)

    # Check if email already exists
    existing_email = await user_repo.get_by_email(user_data.email)
    if existing_email:
        raise DuplicateError("User", "email", user_data.email)

    # Hash password
    password_hash = get_password_hash(user_data.password)

    # Create user
    new_user = await user_repo.create(
        username=user_data.username,
        email=user_data.email,
        password_hash=password_hash,
        role=user_data.role.value,
        full_name=user_data.full_name,
    )

    await db.commit()
    await db.refresh(new_user)

    logger.info(f"Admin {current_user.username} created user: {user_data.username}")

    return UserResponse.model_validate(new_user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get User",
    description="Get a specific user by ID. Admin only.",
)
async def get_user(
    user_id: int, current_user: AdminUser, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Get user by ID (admin only)."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise UserNotFoundException(user_id)

    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update User",
    description="Update user information. Admin only.",
)
async def update_user(
    user_id: int, user_data: UserUpdate, current_user: AdminUser, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Update user (admin only)."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise UserNotFoundException(user_id)

    # Build update dict
    update_data = user_data.model_dump(exclude_unset=True)

    # Convert role enum to string if present
    if "role" in update_data and update_data["role"] is not None:
        update_data["role"] = update_data["role"].value

    # Check email uniqueness if changing
    if "email" in update_data and update_data["email"]:
        existing = await user_repo.get_by_email(update_data["email"])
        if existing and existing.id != user_id:
            raise DuplicateError("User", "email", update_data["email"])

    # Apply updates
    for field, value in update_data.items():
        if value is not None:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin {current_user.username} updated user {user_id}: {list(update_data.keys())}")

    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Delete User",
    description="Delete a user account. Admin only.",
)
async def delete_user(user_id: int, current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    """Delete user (admin only)."""
    # Prevent self-deletion
    if user_id == current_user.id:
        raise ValidationException("user_id", "Cannot delete your own account")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise UserNotFoundException(user_id)

    # Delete user
    await user_repo.delete(user)
    await db.commit()

    logger.info(f"Admin {current_user.username} deleted user {user_id} ({user.username})")


@router.post(
    "/{user_id}/reset-password",
    response_model=MessageResponse,
    summary="Reset User Password",
    description="Reset a user's password. Admin only.",
)
async def reset_user_password(
    user_id: int,
    password_data: PasswordReset,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Reset user password (admin only)."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise UserNotFoundException(user_id)

    # Hash new password
    user.password_hash = get_password_hash(password_data.new_password)

    # Increment token version to invalidate existing tokens
    user.token_version += 1

    await db.commit()

    logger.info(
        f"Admin {current_user.username} reset password for user {user_id} ({user.username})"
    )

    return MessageResponse(
        success=True, message=f"Password reset successfully for user '{user.username}'"
    )


# =============================================================================
# Self-Service (Authenticated Users)
# =============================================================================


@router.patch(
    "/me/password",
    response_model=MessageResponse,
    summary="Change Own Password",
    description="Change your own password. Requires current password.",
)
async def change_own_password(
    password_data: PasswordChange, current_user: ActiveUser, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Change own password."""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise AuthenticationError("Current password is incorrect")

    # Hash new password
    current_user.password_hash = get_password_hash(password_data.new_password)

    # Increment token version to invalidate other sessions
    current_user.token_version += 1

    await db.commit()

    logger.info(f"User {current_user.username} changed their password")

    return MessageResponse(success=True, message="Password changed successfully")
