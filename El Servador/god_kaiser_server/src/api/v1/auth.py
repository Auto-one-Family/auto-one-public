"""
Authentication & Authorization API Endpoints

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- POST /login - User login with JWT tokens
- POST /register - User registration (admin only)
- POST /refresh - Refresh access token
- POST /logout - Invalidate tokens
- POST /mqtt/configure - Configure MQTT auth
- GET /mqtt/status - Get MQTT auth status

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 115-123)
- core/security.py (JWT utilities)
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from ...core.config import get_settings
from ...core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationException,
    DuplicateError,
    InvalidCredentialsException,
    InvalidTokenException,
    ServiceUnavailableError,
    TokenExpiredException,
)
from ...core.logging_config import get_logger
from ...core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from ...db.repositories.api_key_repo import ApiKeyRepository
from ...db.repositories.esp_repo import ESPRepository
from ...db.repositories.system_config_repo import SystemConfigRepository
from ...db.repositories.token_blacklist_repo import TokenBlacklistRepository
from ...db.repositories.user_repo import UserRepository
from ...services.mqtt_auth_service import MQTTAuthService
from ...schemas import (
    AuthStatusResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    MQTTAuthConfigRequest,
    MQTTAuthConfigResponse,
    MQTTAuthStatusResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    SetupRequest,
    SetupResponse,
    TokenResponse,
    UserResponse,
)
from ..deps import (
    AdminUser,
    ActiveUser,
    DBSession,
    check_auth_rate_limit,
    oauth2_scheme,
)

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# =============================================================================
# Initial Setup (First-Run)
# =============================================================================


@router.get(
    "/status",
    response_model=AuthStatusResponse,
    summary="Get auth system status",
    description="Get authentication system status. Used by frontend to check if setup is needed.",
)
async def get_auth_status(
    db: DBSession,
) -> AuthStatusResponse:
    """
    Get authentication system status.

    This endpoint is always public (no auth required).
    Used by frontend to determine if initial setup is needed.

    Returns:
        AuthStatusResponse with setup status
    """
    user_repo = UserRepository(db)
    user_count = await user_repo.count()

    # Get MQTT status from system config
    system_config_repo = SystemConfigRepository(db)
    mqtt_config = await system_config_repo.get_mqtt_auth_config()
    mqtt_auth_enabled = mqtt_config.get("enabled", False)

    return AuthStatusResponse(
        setup_required=(user_count == 0),
        users_exist=(user_count > 0),
        mqtt_auth_enabled=mqtt_auth_enabled,
        mqtt_tls_enabled=settings.mqtt.use_tls,
    )


@router.post(
    "/setup",
    response_model=SetupResponse,
    responses={
        200: {"description": "Setup successful"},
        403: {"description": "Setup already completed"},
        400: {"description": "Invalid request"},
    },
    summary="Initial admin setup",
    description="Create first admin user. ONLY available when no users exist.",
)
async def initial_setup(
    request: SetupRequest,
    db: DBSession,
) -> SetupResponse:
    """
    Initial admin setup endpoint.

    ONLY available when no users exist in database!
    Creates the first admin user without authentication.

    Args:
        request: Setup request with admin credentials
        db: Database session

    Returns:
        SetupResponse with tokens and user info
    """
    user_repo = UserRepository(db)

    # Check if users already exist
    user_count = await user_repo.count()
    if user_count > 0:
        logger.warning("Setup attempted but users already exist")
        raise AuthorizationError("Setup already completed. Use /register endpoint instead.")

    # Check if username or email already exists (safety check)
    existing_user = await user_repo.get_by_username(request.username)
    if existing_user:
        raise DuplicateError("User", "username", request.username)

    existing_email = await user_repo.get_by_email(request.email)
    if existing_email:
        raise DuplicateError("User", "email", request.email)

    # Create first admin user
    admin = await user_repo.create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        role="admin",
        full_name=request.full_name,
    )
    await db.commit()

    # Generate tokens for immediate login
    access_token = create_access_token(
        user_id=admin.id,
        additional_claims={
            "role": admin.role,
            "token_version": admin.token_version,
        },
    )
    refresh_token = create_refresh_token(user_id=admin.id)

    logger.info(f"Initial setup completed: Admin '{admin.username}' created")

    return SetupResponse(
        success=True,
        message="Admin account created successfully",
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.security.jwt_access_token_expire_minutes * 60,
        ),
        user=UserResponse(
            id=admin.id,
            username=admin.username,
            email=admin.email,
            full_name=admin.full_name,
            role=admin.role,
            is_active=admin.is_active,
            created_at=admin.created_at,
            updated_at=admin.updated_at,
        ),
    )


# =============================================================================
# Login
# =============================================================================


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many attempts"},
    },
    summary="User login",
    description="Authenticate user and return JWT tokens.",
)
async def login(
    credentials: LoginRequest,
    db: DBSession,
    _rate_limit: Annotated[None, Depends(check_auth_rate_limit)] = None,
) -> LoginResponse:
    """
    User login endpoint.

    Authenticates user by username/email and password.
    Returns access and refresh JWT tokens.

    Args:
        credentials: Login credentials (username, password)
        db: Database session

    Returns:
        LoginResponse with tokens and user info
    """
    user_repo = UserRepository(db)

    # Try to authenticate
    user = await user_repo.authenticate(
        username=credentials.username,
        password=credentials.password,
    )

    if not user:
        # Also try by email if username lookup failed
        user = await user_repo.get_by_email(credentials.username)
        if user and verify_password(credentials.password, user.password_hash):
            pass  # Email login successful
        else:
            logger.warning(f"Failed login attempt for: {credentials.username}")
            raise InvalidCredentialsException()

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user.username}")
        raise AuthenticationError("User account is disabled")

    # Generate tokens (include token_version for logout-all functionality)
    expires_delta = timedelta(days=7) if credentials.remember_me else None
    access_token = create_access_token(
        user_id=user.id,
        additional_claims={
            "role": user.role,
            "token_version": user.token_version,
        },
        expires_delta=expires_delta,
    )
    refresh_token = create_refresh_token(user_id=user.id)

    # Calculate expiration time
    expires_in = (
        7 * 24 * 60 * 60
        if credentials.remember_me
        else settings.security.jwt_access_token_expire_minutes * 60
    )

    logger.info(f"User logged in: {user.username}")

    return LoginResponse(
        success=True,
        message="Login successful",
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        ),
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.post(
    "/login/form",
    response_model=TokenResponse,
    include_in_schema=False,  # OAuth2 form login for Swagger UI
)
async def login_form(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
) -> TokenResponse:
    """
    OAuth2 form login endpoint (for Swagger UI).
    """
    user_repo = UserRepository(db)

    user = await user_repo.authenticate(
        username=form_data.username,
        password=form_data.password,
    )

    if not user or not user.is_active:
        raise InvalidCredentialsException()

    # FIX: Include token_version for logout-all functionality (same as /login)
    access_token = create_access_token(
        user_id=user.id,
        additional_claims={
            "role": user.role,
            "token_version": user.token_version,
        },
    )
    refresh_token = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.security.jwt_access_token_expire_minutes * 60,
    )


# =============================================================================
# Registration
# =============================================================================


@router.post(
    "/register",
    response_model=RegisterResponse,
    responses={
        200: {"description": "Registration successful"},
        400: {"description": "Username or email already exists"},
        403: {"description": "Admin privileges required"},
    },
    summary="Register new user",
    description="Create new user account. Admin only.",
)
async def register(
    request: RegisterRequest,
    db: DBSession,
    current_user: AdminUser,
) -> RegisterResponse:
    """
    User registration endpoint.

    Creates a new user account. Requires admin privileges.

    Args:
        request: Registration data
        db: Database session
        current_user: Current admin user

    Returns:
        RegisterResponse with created user info
    """
    user_repo = UserRepository(db)

    # Check if username already exists
    existing_user = await user_repo.get_by_username(request.username)
    if existing_user:
        raise DuplicateError("User", "username", request.username)

    # Check if email already exists
    existing_email = await user_repo.get_by_email(request.email)
    if existing_email:
        raise DuplicateError("User", "email", request.email)

    # Create user
    new_user = await user_repo.create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        role=request.role,
        full_name=request.full_name,
    )
    await db.commit()

    logger.info(
        f"User created by {current_user.username}: {new_user.username} (role={new_user.role})"
    )

    return RegisterResponse(
        success=True,
        message=f"User '{new_user.username}' created successfully",
        user=UserResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
            updated_at=new_user.updated_at,
        ),
    )


# =============================================================================
# Token Refresh
# =============================================================================


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    responses={
        200: {"description": "Token refreshed"},
        401: {"description": "Invalid refresh token"},
    },
    summary="Refresh access token",
    description="Get new access token using refresh token.",
)
async def refresh_token(
    request: RefreshTokenRequest,
    db: DBSession,
) -> RefreshTokenResponse:
    """
    Token refresh endpoint.

    Uses valid refresh token to get new access and refresh tokens.
    Implements token rotation: old refresh token is blacklisted before issuing new ones.

    Args:
        request: Refresh token
        db: Database session

    Returns:
        RefreshTokenResponse with new tokens
    """
    old_refresh_token = request.refresh_token

    # Check if token is blacklisted BEFORE verification
    blacklist_repo = TokenBlacklistRepository(db)
    if await blacklist_repo.is_blacklisted(old_refresh_token):
        logger.warning("Refresh token is blacklisted")
        raise InvalidTokenException("Refresh token has been revoked")

    try:
        # Verify refresh token
        payload = verify_token(old_refresh_token, expected_type="refresh")
        user_id = int(payload.get("sub"))
        expires_at = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)

    except InvalidTokenException:
        raise
    except Exception as e:
        logger.warning(f"Refresh token verification failed: {e}")
        raise TokenExpiredException()

    # Verify user still exists and is active
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    # TOKEN ROTATION: Blacklist old refresh token BEFORE creating new ones
    # Cache user data before any DB operations that might fail
    user_id = user.id
    user_role = user.role
    user_token_version = user.token_version
    user_username = user.username

    try:
        await blacklist_repo.add_token(
            token=old_refresh_token,
            token_type="refresh",
            user_id=user_id,
            expires_at=expires_at,
            reason="token_rotation",
        )
        await db.commit()
        logger.debug(f"Old refresh token blacklisted for user: {user_username}")
    except Exception as e:
        # Rollback the failed transaction to allow further DB operations
        await db.rollback()
        logger.warning(f"Failed to blacklist old refresh token (might be already blacklisted): {e}")
        # Continue anyway - token rotation is best effort
        # Token might already be blacklisted by concurrent request (race condition)

    # Generate new tokens (include token_version)
    # Use cached values to avoid accessing expired/rolled-back session objects
    new_access_token = create_access_token(
        user_id=user_id,
        additional_claims={
            "role": user_role,
            "token_version": user_token_version,
        },
    )
    new_refresh_token = create_refresh_token(user_id=user_id)

    logger.info(f"Token rotated for user: {user_username}")

    return RefreshTokenResponse(
        success=True,
        message="Token refreshed successfully",
        tokens=TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.security.jwt_access_token_expire_minutes * 60,
        ),
    )


# =============================================================================
# Logout
# =============================================================================


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={
        200: {"description": "Logout successful"},
    },
    summary="Logout user",
    description="Invalidate user tokens.",
)
async def logout(
    request: LogoutRequest,
    current_user: ActiveUser,
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: DBSession,
) -> LogoutResponse:
    """
    User logout endpoint.

    Invalidates user tokens by adding them to the token blacklist.

    Args:
        request: Logout request
        current_user: Current user
        token: JWT access token from Authorization header
        db: Database session

    Returns:
        LogoutResponse with number of tokens invalidated
    """
    tokens_invalidated = 0

    # Blacklist the current access token
    if token:
        try:
            # Verify token to extract expiration
            payload = verify_token(token, expected_type="access")
            expires_at = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)

            # Add token to blacklist
            blacklist_repo = TokenBlacklistRepository(db)
            await blacklist_repo.add_token(
                token=token,
                token_type="access",
                user_id=current_user.id,
                expires_at=expires_at,
                reason="logout",
            )
            tokens_invalidated = 1
            await db.commit()
            logger.info(f"Access token blacklisted for user: {current_user.username}")
        except Exception as e:
            logger.warning(f"Failed to blacklist access token: {e}")

    # Handle "logout all devices" request (TOKEN VERSIONING)
    if request.all_devices:
        # Increment token_version to invalidate all existing tokens
        _user_repo = UserRepository(db)
        current_user.token_version += 1
        await db.commit()

        logger.info(
            f"All devices logged out for user: {current_user.username} "
            f"(token_version incremented to {current_user.token_version})"
        )
        tokens_invalidated = -1  # -1 indicates "all tokens" (not countable)

    if request.all_devices:
        logger.info(f"User logged out from all devices: {current_user.username}")
        return LogoutResponse(
            success=True,
            message="Logged out from all devices successfully",
            tokens_invalidated=max(tokens_invalidated, 1),
        )
    else:
        logger.info(
            f"User logged out: {current_user.username} (tokens_invalidated={tokens_invalidated})"
        )
        return LogoutResponse(
            success=True,
            message="Logged out successfully",
            tokens_invalidated=tokens_invalidated,
        )


# =============================================================================
# Current User
# =============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get currently authenticated user info.",
)
async def get_current_user_info(
    current_user: ActiveUser,
) -> UserResponse:
    """
    Get current user info.

    Args:
        current_user: Current authenticated user

    Returns:
        UserResponse with user info
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


# =============================================================================
# MQTT Authentication Configuration
# =============================================================================


@router.post(
    "/mqtt/configure",
    response_model=MQTTAuthConfigResponse,
    responses={
        200: {"description": "MQTT auth configured"},
        403: {"description": "Admin privileges required"},
        500: {"description": "Configuration failed"},
    },
    summary="Configure MQTT authentication",
    description="Configure MQTT broker credentials for ESP32 devices. Admin only.",
)
async def configure_mqtt_auth(
    request: MQTTAuthConfigRequest,
    current_user: AdminUser,
    db: DBSession,
) -> MQTTAuthConfigResponse:
    """
    Configure MQTT authentication.

    Updates Mosquitto password file and reloads broker configuration.

    Args:
        request: MQTT auth configuration
        current_user: Admin user
        db: Database session

    Returns:
        MQTTAuthConfigResponse
    """
    try:
        # Initialize repositories and service
        system_config_repo = SystemConfigRepository(db)
        esp_repo = ESPRepository(db)
        mqtt_auth_service = MQTTAuthService(system_config_repo, esp_repo)

        # Configure credentials
        if request.enabled:
            broker_reloaded = await mqtt_auth_service.configure_credentials(
                username=request.username,
                password=request.password,
                enabled=True,
            )

            # Broadcast auth_update to all ESPs (only if TLS enabled)
            try:
                broadcast_count = await mqtt_auth_service.broadcast_auth_update(
                    username=request.username,
                    password=request.password,
                    esp_ids=None,  # Broadcast to all
                    action="update",
                )
                logger.info(f"Auth update broadcasted to {broadcast_count} ESP devices")
            except RuntimeError as e:
                # TLS not enabled - log warning but don't fail
                logger.warning(f"Cannot broadcast auth_update: {e}")
        else:
            # Disable authentication
            await mqtt_auth_service.disable_authentication()
            broker_reloaded = True

        # Commit database changes
        await db.commit()

        logger.info(
            f"MQTT auth configured by {current_user.username}: "
            f"username={request.username}, enabled={request.enabled}"
        )

        return MQTTAuthConfigResponse(
            success=True,
            message="MQTT authentication configured successfully",
            username=request.username if request.enabled else None,
            enabled=request.enabled,
            broker_reloaded=broker_reloaded,
        )

    except ValueError as e:
        logger.error(f"MQTT auth configuration failed (validation): {e}", exc_info=True)
        raise ConfigurationException("mqtt_auth", str(e))
    except Exception as e:
        logger.error(f"MQTT auth configuration failed: {e}", exc_info=True)
        await db.rollback()
        raise ServiceUnavailableError(
            "MQTT Authentication",
            "MQTT authentication configuration failed. Check server logs for details.",
        )


@router.get(
    "/mqtt/status",
    response_model=MQTTAuthStatusResponse,
    summary="Get MQTT auth status",
    description="Get current MQTT authentication configuration status.",
)
async def get_mqtt_auth_status(
    current_user: ActiveUser,
    db: DBSession,
) -> MQTTAuthStatusResponse:
    """
    Get MQTT authentication status.

    Returns current MQTT auth configuration.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        MQTTAuthStatusResponse
    """
    from ...mqtt.client import MQTTClient
    import os

    # Get configuration from database
    system_config_repo = SystemConfigRepository(db)
    config = await system_config_repo.get_mqtt_auth_config()

    # Check password file existence
    passwd_file_path = settings.mqtt.passwd_file_path
    password_file_exists = os.path.exists(passwd_file_path)

    # Check MQTT client connection
    mqtt_client = MQTTClient.get_instance()
    broker_connected = mqtt_client.is_connected()

    return MQTTAuthStatusResponse(
        success=True,
        enabled=config.get("enabled", False),
        username=config.get("username"),
        password_file_exists=password_file_exists,
        broker_connected=broker_connected,
        last_configured=config.get("last_configured"),
    )


# =============================================================================
# API Key Management (Admin only) — AUT-290
# =============================================================================

# Token length in bytes for secrets.token_urlsafe (results in ~43 chars base64)
_API_KEY_TOKEN_BYTES: int = 32

# Supported key prefixes and their owner_type mapping
_PREFIX_TO_OWNER_TYPE: dict[str, str] = {
    "esp_": "esp",
    "god_": "god_layer",
    "svc_": "service",
}


class ApiKeyCreateRequest(BaseModel):
    """Request body for creating a new API key."""

    owner_type: str
    """Owner category: 'esp', 'god_layer', or 'service'."""

    owner_id: Optional[str] = None
    """Optional owner identifier (e.g. ESP device UUID or service name)."""

    scopes: list[str] = []
    """Permission scopes granted to this key."""

    note: Optional[str] = None
    """Human-readable note used to derive the key prefix (e.g. 'esp' → 'esp_')."""


class ApiKeyCreateResponse(BaseModel):
    """Response body when a new API key is created.

    The raw_key field is shown ONLY at creation time and cannot be retrieved again.
    """

    id: uuid.UUID
    raw_key: str
    key_prefix: str
    owner_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyResponse(BaseModel):
    """Public representation of a stored API key (no raw key exposed)."""

    id: uuid.UUID
    key_prefix: str
    owner_type: str
    owner_id: Optional[str]
    scopes: list
    created_at: datetime
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


def _resolve_prefix(owner_type: str) -> str:
    """
    Derive the key prefix from owner_type.

    Args:
        owner_type: One of "esp", "god_layer", "service"

    Returns:
        Key prefix string (e.g. "esp_")

    Raises:
        ValueError: If owner_type is not recognised
    """
    for prefix, otype in _PREFIX_TO_OWNER_TYPE.items():
        if otype == owner_type:
            return prefix
    raise ValueError(
        f"Unknown owner_type {owner_type!r}. "
        f"Valid values: {list(_PREFIX_TO_OWNER_TYPE.values())}"
    )


@router.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=201,
    summary="Create API key",
    description=(
        "Generate and store a new API key. "
        "The raw key is returned ONCE — it cannot be retrieved afterwards. "
        "Admin only."
    ),
)
async def create_api_key_endpoint(
    body: ApiKeyCreateRequest,
    db: DBSession,
    current_user: AdminUser,
) -> ApiKeyCreateResponse:
    """
    Create a new API key (admin only).

    Generates a cryptographically random key, stores its SHA256 hash,
    and returns the plaintext key exactly once.

    Args:
        body: Creation parameters
        db: Database session
        current_user: Authenticated admin user

    Returns:
        ApiKeyCreateResponse including the one-time raw key
    """
    try:
        prefix = _resolve_prefix(body.owner_type)
    except ValueError as exc:
        from fastapi import HTTPException as _HTTPException

        raise _HTTPException(status_code=422, detail=str(exc)) from exc

    raw_token = secrets.token_urlsafe(_API_KEY_TOKEN_BYTES)
    raw_key = f"{prefix}{raw_token}"

    api_key_repo = ApiKeyRepository(db)
    api_key_record = await api_key_repo.create(
        raw_key=raw_key,
        key_prefix=prefix,
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        scopes=body.scopes,
        created_by=current_user.id,
    )
    await db.commit()
    await db.refresh(api_key_record)

    logger.info(
        "API key created by %s: owner_type=%r prefix=%r id=%s",
        current_user.username,
        body.owner_type,
        prefix,
        api_key_record.id,
    )

    return ApiKeyCreateResponse(
        id=api_key_record.id,
        raw_key=raw_key,
        key_prefix=prefix,
        owner_type=body.owner_type,
        created_at=api_key_record.created_at,
    )


@router.post(
    "/api-keys/{key_id}/revoke",
    response_model=dict,
    summary="Revoke API key",
    description="Revoke an API key by ID. Returns 404 if not found. Admin only.",
)
async def revoke_api_key_endpoint(
    key_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> dict:
    """
    Revoke an API key (admin only).

    Sets the revoked_at timestamp so subsequent validation requests fail.

    Args:
        key_id: UUID of the ApiKey record to revoke
        db: Database session
        current_user: Authenticated admin user

    Returns:
        Confirmation dict with revoked key ID

    Raises:
        HTTPException: 404 if the key does not exist
        HTTPException: 409 if the key is already revoked
    """
    from fastapi import HTTPException as _HTTPException

    api_key_repo = ApiKeyRepository(db)
    api_key_record = await api_key_repo.get_by_id(key_id)

    if api_key_record is None:
        raise _HTTPException(status_code=404, detail="API key not found")

    if not api_key_record.is_valid:
        raise _HTTPException(status_code=409, detail="API key is already revoked")

    revoked = await api_key_repo.revoke(key_id)
    if not revoked:
        raise _HTTPException(status_code=404, detail="API key not found or already revoked")

    await db.commit()

    logger.info(
        "API key revoked by %s: id=%s owner_type=%r",
        current_user.username,
        key_id,
        api_key_record.owner_type,
    )

    return {"status": "revoked", "id": str(key_id)}


@router.get(
    "/api-keys",
    response_model=list[ApiKeyResponse],
    summary="List API keys",
    description="Return all API keys (active and revoked). Admin only.",
)
async def list_api_keys_endpoint(
    db: DBSession,
    _current_user: AdminUser,
) -> list[ApiKeyResponse]:
    """
    List all API keys (admin only).

    Returns both active and revoked keys for audit purposes.

    Args:
        db: Database session
        _current_user: Authenticated admin user (auth check only)

    Returns:
        List of ApiKeyResponse objects (no raw keys exposed)
    """
    api_key_repo = ApiKeyRepository(db)
    records = await api_key_repo.get_all()
    return [
        ApiKeyResponse(
            id=rec.id,
            key_prefix=rec.key_prefix,
            owner_type=rec.owner_type,
            owner_id=rec.owner_id,
            scopes=rec.scopes,
            created_at=rec.created_at,
            last_used_at=rec.last_used_at,
            revoked_at=rec.revoked_at,
        )
        for rec in records
    ]
