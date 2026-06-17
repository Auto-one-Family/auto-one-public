"""
User Management API Schemas

Pydantic schemas for user CRUD operations.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRole(str, Enum):
    """User role enumeration."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class UserBase(BaseModel):
    """Base user schema with common fields."""

    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(default=None, max_length=100, description="User's full name")


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=8, description="User password (minimum 8 characters)")
    role: UserRole = Field(default=UserRole.VIEWER, description="User role")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "newuser",
                "email": "user@example.com",
                "password": "SecurePass123",
                "full_name": "New User",
                "role": "viewer",
            }
        }
    )


class UserUpdate(BaseModel):
    """Schema for updating a user (partial update)."""

    email: Optional[EmailStr] = Field(default=None, description="New email address")
    full_name: Optional[str] = Field(default=None, max_length=100, description="New full name")
    role: Optional[UserRole] = Field(default=None, description="New role")
    is_active: Optional[bool] = Field(default=None, description="Account active status")

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "newemail@example.com", "role": "operator"}}
    )


class UserResponse(BaseModel):
    """Schema for user response (public data only)."""

    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "full_name": "Administrator",
                "role": "admin",
                "is_active": True,
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        },
    )


class UserListResponse(BaseModel):
    """Response for listing users."""

    success: bool = True
    users: List[UserResponse]
    total: int


class PasswordReset(BaseModel):
    """Schema for admin password reset."""

    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class PasswordChange(BaseModel):
    """Schema for changing own password."""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate password complexity."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"current_password": "OldPassword123", "new_password": "NewSecure456"}
        }
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    success: bool = True
    message: str
