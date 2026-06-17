"""
Authentication & Authorization Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- Login/Register request and response models
- JWT token models (access, refresh)
- User profile models
- MQTT authentication configuration models

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 115-123, 462-471)
- core/security.py (JWT utilities)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .common import BaseResponse, IDMixin, TimestampMixin

# =============================================================================
# Initial Setup (First-Run)
# =============================================================================


class SetupRequest(BaseModel):
    """
    Initial admin setup request.

    Used for first-run setup when no users exist in database.
    Creates the first admin user without requiring authentication.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        description="Admin username (alphanumeric, starts with letter)",
        examples=["admin", "system_admin"],
    )
    email: EmailStr = Field(
        ...,
        description="Admin email address",
        examples=["admin@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Admin password (min 8 chars, must include upper, lower, digit, special)",
    )
    full_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Admin's full name",
        examples=["System Administrator"],
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin",
                "email": "admin@example.com",
                "password": "SecureP@ss123!",
                "full_name": "System Administrator",
            }
        }
    )


class SetupResponse(BaseResponse):
    """
    Initial setup response with tokens and user info.

    Returned after successful first admin creation.
    """

    tokens: "TokenResponse" = Field(
        ...,
        description="JWT access and refresh tokens for immediate login",
    )
    user: "UserResponse" = Field(
        ...,
        description="Created admin user information",
    )


class AuthStatusResponse(BaseModel):
    """
    Authentication system status response.

    Used by frontend to determine if initial setup is needed.
    """

    setup_required: bool = Field(
        ...,
        description="True if no users exist and setup is needed",
    )
    users_exist: bool = Field(
        ...,
        description="True if at least one user exists",
    )
    mqtt_auth_enabled: bool = Field(
        ...,
        description="True if MQTT authentication is enabled",
    )
    mqtt_tls_enabled: bool = Field(
        ...,
        description="True if MQTT TLS is enabled",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "setup_required": False,
                "users_exist": True,
                "mqtt_auth_enabled": True,
                "mqtt_tls_enabled": True,
            }
        }
    )


# =============================================================================
# Login
# =============================================================================


class LoginRequest(BaseModel):
    """
    User login request.

    Accepts username or email with password.
    """

    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Username or email address",
        examples=["admin", "user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="User password",
    )
    remember_me: bool = Field(
        False,
        description="Extend token expiration (7 days instead of 24h)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "admin", "password": "SecureP@ss123", "remember_me": False}
        }
    )


class TokenResponse(BaseModel):
    """
    JWT token response.

    Returned after successful login or token refresh.
    """

    access_token: str = Field(
        ...,
        description="JWT access token",
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token for obtaining new access tokens",
    )
    token_type: str = Field(
        "bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Access token expiration time in seconds",
        ge=0,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400,
            }
        }
    )


class LoginResponse(BaseResponse):
    """
    Login response with tokens and user info.
    """

    tokens: TokenResponse = Field(
        ...,
        description="JWT access and refresh tokens",
    )
    user: "UserResponse" = Field(
        ...,
        description="Authenticated user information",
    )


# =============================================================================
# Registration
# =============================================================================


class RegisterRequest(BaseModel):
    """
    User registration request.

    Admin-only endpoint for creating new users.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        description="Username (alphanumeric, starts with letter)",
        examples=["john_doe", "operator1"],
    )
    email: EmailStr = Field(
        ...,
        description="User email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 chars, must include upper, lower, digit, special)",
    )
    full_name: Optional[str] = Field(
        None,
        max_length=100,
        description="User's full name",
        examples=["John Doe"],
    )
    role: str = Field(
        "viewer",
        description="User role (admin, operator, viewer)",
        pattern=r"^(admin|operator|viewer)$",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "SecureP@ss123",
                "full_name": "New User",
                "role": "operator",
            }
        }
    )


class RegisterResponse(BaseResponse):
    """
    Registration response with created user info.
    """

    user: "UserResponse" = Field(
        ...,
        description="Newly created user information",
    )


# =============================================================================
# Token Refresh
# =============================================================================


class RefreshTokenRequest(BaseModel):
    """
    Token refresh request.

    Uses refresh token to obtain new access token.
    """

    refresh_token: str = Field(
        ...,
        description="Valid refresh token",
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}}
    )


class RefreshTokenResponse(BaseResponse):
    """
    Token refresh response with new tokens.
    """

    tokens: TokenResponse = Field(
        ...,
        description="New JWT access and refresh tokens",
    )


# =============================================================================
# User Profile
# =============================================================================


class UserBase(BaseModel):
    """Base user fields."""

    username: str = Field(
        ...,
        description="Username",
    )
    email: EmailStr = Field(
        ...,
        description="Email address",
    )
    full_name: Optional[str] = Field(
        None,
        description="User's full name",
    )
    role: str = Field(
        ...,
        description="User role (admin, operator, viewer)",
    )
    is_active: bool = Field(
        True,
        description="Whether account is active",
    )


class UserResponse(UserBase, IDMixin, TimestampMixin):
    """
    User response model.

    Returned in auth responses and user queries.
    Never includes password hash.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "full_name": "System Administrator",
                "role": "admin",
                "is_active": True,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }
        },
    )


class UserUpdate(BaseModel):
    """
    User update request.

    All fields optional - only provided fields are updated.
    """

    email: Optional[EmailStr] = Field(
        None,
        description="New email address",
    )
    full_name: Optional[str] = Field(
        None,
        max_length=100,
        description="New full name",
    )
    role: Optional[str] = Field(
        None,
        description="New role (admin only)",
        pattern=r"^(admin|operator|viewer)$",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Account active status (admin only)",
    )


class PasswordChangeRequest(BaseModel):
    """
    Password change request.
    """

    current_password: str = Field(
        ...,
        description="Current password for verification",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password",
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# =============================================================================
# Logout / Token Blacklist
# =============================================================================


class LogoutRequest(BaseModel):
    """
    Logout request.

    Optionally blacklist specific token or all user tokens.
    """

    refresh_token: Optional[str] = Field(
        None,
        description="Refresh token to invalidate (optional, invalidates current if not provided)",
    )
    all_devices: bool = Field(
        False,
        description="Invalidate all tokens for user (logout from all devices)",
    )


class LogoutResponse(BaseResponse):
    """
    Logout response.
    """

    tokens_invalidated: int = Field(
        1,
        description="Number of tokens invalidated",
        ge=0,
    )


# =============================================================================
# MQTT Authentication Configuration
# =============================================================================


class MQTTAuthConfigRequest(BaseModel):
    """
    MQTT authentication configuration request.

    Configures MQTT broker credentials for ESP32 devices.
    Updates Mosquitto password file and reloads broker.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="MQTT username for ESP32 devices",
        examples=["esp_user"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="MQTT password (will be hashed)",
    )
    enabled: bool = Field(
        True,
        description="Enable MQTT authentication (disable for testing)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "esp_user", "password": "SecureMqttP@ss", "enabled": True}
        }
    )


class MQTTAuthConfigResponse(BaseResponse):
    """
    MQTT auth configuration response.
    """

    username: str = Field(
        ...,
        description="Configured MQTT username",
    )
    enabled: bool = Field(
        ...,
        description="Whether MQTT auth is enabled",
    )
    broker_reloaded: bool = Field(
        ...,
        description="Whether broker config was reloaded",
    )


class MQTTAuthStatusResponse(BaseResponse):
    """
    MQTT authentication status response.
    """

    enabled: bool = Field(
        ...,
        description="Whether MQTT authentication is enabled",
    )
    username: Optional[str] = Field(
        None,
        description="Configured MQTT username (if enabled)",
    )
    password_file_exists: bool = Field(
        ...,
        description="Whether password file exists",
    )
    broker_connected: bool = Field(
        ...,
        description="Whether server is connected to broker",
    )
    last_configured: Optional[datetime] = Field(
        None,
        description="Last configuration timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "enabled": True,
                "username": "esp_user",
                "password_file_exists": True,
                "broker_connected": True,
                "last_configured": "2025-01-01T12:00:00Z",
            }
        }
    )


# =============================================================================
# API Key Management
# =============================================================================


class APIKeyCreate(BaseModel):
    """
    API key creation request.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="API key name/description",
        examples=["ESP32 Production", "Frontend App"],
    )
    expires_in_days: int = Field(
        365,
        description="Expiration time in days",
        ge=1,
        le=365,
    )


class APIKeyResponse(BaseResponse):
    """
    API key creation response.

    The key is only shown once on creation.
    """

    name: str = Field(
        ...,
        description="API key name",
    )
    key: str = Field(
        ...,
        description="API key (shown only once)",
    )
    expires_at: datetime = Field(
        ...,
        description="Expiration timestamp",
    )


class APIKeyInfo(BaseModel):
    """
    API key information (without the key itself).
    """

    id: int = Field(
        ...,
        description="API key ID",
    )
    name: str = Field(
        ...,
        description="API key name",
    )
    created_at: datetime = Field(
        ...,
        description="Creation timestamp",
    )
    expires_at: datetime = Field(
        ...,
        description="Expiration timestamp",
    )
    last_used: Optional[datetime] = Field(
        None,
        description="Last usage timestamp",
    )
    is_active: bool = Field(
        ...,
        description="Whether key is active",
    )


# Update forward references
LoginResponse.model_rebuild()
RegisterResponse.model_rebuild()
SetupResponse.model_rebuild()
