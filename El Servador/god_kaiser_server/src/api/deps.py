"""
FastAPI Dependency Injection: DB Sessions, Auth, Rate Limiting

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- get_db() - Database session injection
- get_current_user() - JWT authentication
- get_current_active_user() - Active user check
- require_admin() - Admin role guard
- require_operator() - Operator/Admin role guard
- verify_api_key() - API key authentication (ESP32)
- check_rate_limit() - Rate limiting

References:
- .claude/PI_SERVER_REFACTORING.md (Phase 5)
- core/security.py (JWT utilities)
- db/session.py (Database session)
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Any, AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.logging_config import get_logger
from ..core.security import verify_token
from ..db.models.user import User
from ..db.repositories.api_key_repo import ApiKeyRepository
from ..db.repositories.token_blacklist_repo import TokenBlacklistRepository
from ..db.repositories.user_repo import UserRepository
from ..db.session import get_session

logger = get_logger(__name__)
settings = get_settings()

# OAuth2 scheme for JWT tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)

# HTTP Bearer scheme (alternative)
http_bearer = HTTPBearer(auto_error=False)


# =============================================================================
# Database Session Dependency
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency.

    Provides an async database session for request handlers.
    Session is automatically closed after request completes.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async for session in get_session():
        try:
            yield session
        finally:
            pass  # Session cleanup handled by get_session()


# Type alias for dependency injection
DBSession = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# JWT Authentication Dependencies
# =============================================================================


async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: DBSession,
) -> User:
    """
    Get current authenticated user from JWT token.

    Extracts user ID from token, validates, and returns User model.

    Args:
        token: JWT token from Authorization header
        db: Database session

    Returns:
        User model instance

    Raises:
        HTTPException: 401 if token invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Development mode bypass (SECURITY: Never in production!)
    if settings.development.debug_mode and settings.development.allow_auth_bypass and not token:
        # CRITICAL: Prevent auth bypass in production environment
        if settings.environment == "production":
            logger.error(
                "SECURITY: Auth bypass attempted in production mode! "
                "DEBUG_AUTH_BYPASS_ENABLED should NEVER be enabled in production."
            )
            raise credentials_exception

        # In debug mode (non-production only), allow requests without token
        logger.warning(
            "Auth bypass in debug mode - returning mock admin user. "
            "This is only allowed in non-production environments when explicitly enabled."
        )
        user_repo = UserRepository(db)
        admin_user = await user_repo.get_by_username("admin")
        if admin_user:
            return admin_user
        # No admin user exists, fail
        raise credentials_exception

    if not token:
        logger.warning("No authentication token provided")
        raise credentials_exception

    try:
        # Verify and decode token
        payload = verify_token(token, expected_type="access")
        user_id_str = payload.get("sub")

        if user_id_str is None:
            logger.warning("Token missing 'sub' claim")
            raise credentials_exception

        try:
            user_id = int(user_id_str)
        except ValueError:
            logger.warning(f"Invalid user_id in token: {user_id_str}")
            raise credentials_exception

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise credentials_exception
    except ValueError as e:
        logger.warning(f"Token validation error: {e}")
        raise credentials_exception

    # Check if token is blacklisted (revoked)
    blacklist_repo = TokenBlacklistRepository(db)
    if await blacklist_repo.is_blacklisted(token):
        logger.warning(f"Blacklisted token used for user_id={user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if user is None:
        logger.warning(f"User {user_id} not found in database")
        raise credentials_exception

    # TOKEN VERSIONING: Check if token version matches user's current version
    token_version = payload.get("token_version")
    if token_version is not None:
        # Token has version claim - validate it
        if token_version < user.token_version:
            logger.warning(
                f"Token version mismatch for user {user.username}: "
                f"token_version={token_version}, user.token_version={user.token_version}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated (logout all devices)",
                headers={"WWW-Authenticate": "Bearer"},
            )
    # If token doesn't have version claim, it's an old token - allow it for backward compatibility
    # but log a warning
    elif user.token_version > 0:
        logger.debug(
            f"Token without version claim for user {user.username} "
            f"(user.token_version={user.token_version})"
        )

    return user


# Type alias for current user dependency
CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_user(
    current_user: CurrentUser,
) -> User:
    """
    Get current authenticated and active user.

    Ensures user account is active (not disabled).

    Args:
        current_user: Current user from get_current_user

    Returns:
        User model instance

    Raises:
        HTTPException: 403 if user is inactive
    """
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return current_user


# Type alias for active user dependency
ActiveUser = Annotated[User, Depends(get_current_active_user)]


# =============================================================================
# Role-Based Access Control
# =============================================================================


async def require_admin(
    current_user: ActiveUser,
) -> User:
    """
    Require admin role.

    Ensures current user has admin role.

    Args:
        current_user: Current active user

    Returns:
        User model instance

    Raises:
        HTTPException: 403 if user is not admin
    """
    if current_user.role != "admin":
        logger.warning(
            f"Non-admin user attempted admin action: {current_user.username} (role={current_user.role})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def require_operator(
    current_user: ActiveUser,
) -> User:
    """
    Require operator or admin role.

    Ensures current user has operator or admin role.
    Viewers are denied access.

    Args:
        current_user: Current active user

    Returns:
        User model instance

    Raises:
        HTTPException: 403 if user is viewer
    """
    if current_user.role not in ("admin", "operator"):
        logger.warning(f"Viewer attempted operator action: {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or admin privileges required",
        )
    return current_user


# Type aliases for role guards
AdminUser = Annotated[User, Depends(require_admin)]
OperatorUser = Annotated[User, Depends(require_operator)]


# =============================================================================
# API Key Authentication (for ESP32 devices)
# =============================================================================


async def verify_api_key(
    db: DBSession,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> str:
    """
    Verify API key from request header against the api_keys DB table (AUT-290).

    Authentication flow:
    1. Debug-mode bypass (non-production only)
    2. Missing-key guard
    3. Configured-key fallback (settings.security.api_key)
    4. DB lookup via SHA256 hash (ApiKeyRepository)
       - Found + active   → update last_used_at, return key
       - Found + revoked  → 401
       - Not found        → 401 (no prefix fallback)

    Args:
        x_api_key: API key from X-API-Key header
        db: Database session (injected by FastAPI)

    Returns:
        Raw API key string if authentication succeeded

    Raises:
        HTTPException: 401 if the key is missing, revoked, or unknown
    """
    # Development mode: Allow without API key (SECURITY: Never in production!)
    if settings.development.debug_mode:
        # CRITICAL: Prevent API key bypass in production environment
        if settings.environment == "production":
            logger.error(
                "SECURITY: API key bypass attempted in production mode! "
                "DEBUG_MODE should NEVER be enabled in production."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        logger.debug("API key verification DISABLED (debug mode - non-production only)")
        return "debug-mode"

    if not x_api_key:
        logger.warning("API request without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Fallback: configured master key in settings (backwards-compatible)
    configured_key = getattr(settings.security, "api_key", None)
    if configured_key and x_api_key == configured_key:
        return x_api_key

    # DB-backed validation (AUT-290)
    api_key_repo = ApiKeyRepository(db)
    api_key_record = await api_key_repo.get_by_hash(x_api_key)

    if api_key_record is not None:
        if not api_key_record.is_valid:
            logger.warning(
                "Revoked API key used: prefix=%r owner_type=%r",
                api_key_record.key_prefix,
                api_key_record.owner_type,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        # Key is active — record usage and return
        await api_key_repo.touch_last_used(api_key_record.id)
        return x_api_key

    logger.warning("Unknown API key attempted: prefix=%r", x_api_key[:8])
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


# Type alias for API key dependency
APIKey = Annotated[str, Depends(verify_api_key)]


# =============================================================================
# Rate Limiting
# =============================================================================


# Simple in-memory rate limiter
# For production: Use Redis-based implementation
try:
    import redis.asyncio as redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    redis = None


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_seconds: int


class InMemoryRateLimiter:
    """
    In-memory rate limiter with TTL cleanup.

    Used as fallback when Redis is unavailable/disabled.
    """

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        max_keys: int = 10_000,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str) -> RateLimitResult:
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old timestamps
        entries = [req_time for req_time in self.requests[key] if req_time > window_start]
        self.requests[key] = entries

        allowed = len(entries) < self.max_requests
        if allowed:
            entries.append(now)
            self.requests[key] = entries

        # Compact dict if too many keys (drop oldest)
        if len(self.requests) > self.max_keys:
            # Drop keys with oldest activity first
            ranked = []
            for k, vals in self.requests.items():
                last_ts = max(vals) if vals else 0
                ranked.append((last_ts, k))
            ranked.sort(key=lambda x: x[0])
            for _, k in ranked[: len(self.requests) - self.max_keys]:
                self.requests.pop(k, None)

        remaining = max(0, self.max_requests - len(self.requests[key]))
        reset_seconds = 0
        if self.requests[key]:
            oldest = min(self.requests[key])
            reset_at = oldest + self.window_seconds
            reset_seconds = max(0, int(reset_at - now))

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )


class RedisRateLimiter:
    """
    Redis-backed sliding window rate limiter (shared across processes).
    """

    def __init__(
        self,
        client,
        max_requests: int = 100,
        window_seconds: int = 60,
        prefix: str = "rate_limit",
    ):
        self.client = client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix

    async def check(self, key: str) -> RateLimitResult:
        now = int(time.time())
        window_start = now - self.window_seconds
        redis_key = f"{self.prefix}:{key}"

        pipe = self.client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zadd(redis_key, {str(now): now})
        pipe.zcard(redis_key)
        pipe.zrange(redis_key, 0, 0, withscores=True)
        pipe.expire(redis_key, self.window_seconds)
        try:
            _, _, count, oldest_entry, _ = await pipe.execute()
        except Exception as exc:  # pragma: no cover - operational fallback
            logger.warning(f"Redis rate limit failed, falling back to allow: {exc}")
            return RateLimitResult(True, self.max_requests, 0)

        remaining = max(0, self.max_requests - count)
        reset_seconds = 0
        if oldest_entry:
            # oldest_entry is list of (member, score)
            _, oldest_score = oldest_entry[0]
            reset_seconds = max(0, int(self.window_seconds - (now - int(oldest_score))))

        allowed = count <= self.max_requests
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )


def _build_rate_limiter(max_requests: int, window_seconds: int, prefix: str):
    if settings.redis.enabled and redis:
        try:
            client = redis.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=settings.redis.password,
                decode_responses=False,
            )
            return RedisRateLimiter(
                client=client,
                max_requests=max_requests,
                window_seconds=window_seconds,
                prefix=prefix,
            )
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning(f"Redis init failed, using in-memory rate limiter: {exc}")

    return InMemoryRateLimiter(max_requests=max_requests, window_seconds=window_seconds)


# Global rate limiter instances (shared for reuse)
_rate_limiter = _build_rate_limiter(max_requests=100, window_seconds=60, prefix="rl")
_auth_rate_limiter = _build_rate_limiter(max_requests=10, window_seconds=60, prefix="rl_auth")


async def check_rate_limit(
    request: Request,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    x_forwarded_for: Annotated[Optional[str], Header(alias="X-Forwarded-For")] = None,
) -> None:
    """
    Check rate limit for API requests.

    Uses API key or IP as rate limit key.

    Args:
        x_api_key: API key from header (or use IP)

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    # Use API key as rate limit key, or "anonymous" if none
    key = x_api_key[:20] if x_api_key else None
    if not key:
        if x_forwarded_for:
            key = x_forwarded_for.split(",")[0].strip()
        elif request.client and request.client.host:
            key = request.client.host
        else:
            key = "anonymous"

    result = await _rate_limiter.check(key)

    if not result.allowed:
        logger.warning(f"Rate limit exceeded for key: {key}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {_rate_limiter.max_requests} requests per {_rate_limiter.window_seconds}s.",
            headers={
                "Retry-After": str(result.reset_seconds),
                "X-RateLimit-Limit": str(_rate_limiter.max_requests),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(result.reset_seconds),
            },
        )


async def check_auth_rate_limit(
    request: Request,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    x_forwarded_for: Annotated[Optional[str], Header(alias="X-Forwarded-For")] = None,
) -> None:
    """
    Stricter rate limit for authentication endpoints.

    Limits to 10 requests per minute to prevent brute force.
    """
    key = x_api_key[:20] if x_api_key else None
    if not key:
        if x_forwarded_for:
            key = x_forwarded_for.split(",")[0].strip()
        elif request.client and request.client.host:
            key = request.client.host
        else:
            key = "anonymous"

    result = await _auth_rate_limiter.check(key)

    if not result.allowed:
        logger.warning(f"Auth rate limit exceeded for key: {key}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please wait before trying again.",
            headers={
                "Retry-After": str(result.reset_seconds),
            },
        )


# =============================================================================
# Optional Authentication (for public + authenticated endpoints)
# =============================================================================


async def get_optional_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: DBSession,
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise None.

    For endpoints that work both authenticated and anonymously,
    but provide additional features when authenticated.

    Args:
        token: JWT token (optional)
        db: Database session

    Returns:
        User if authenticated, None otherwise
    """
    if not token:
        return None

    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


OptionalUser = Annotated[Optional[User], Depends(get_optional_user)]


# =============================================================================
# Service Dependencies
# =============================================================================


def get_command_bridge():
    """Get the MQTTCommandBridge instance. Returns None if not initialized."""
    from ..main import _mqtt_command_bridge

    return _mqtt_command_bridge


def get_mqtt_publisher():
    """Get MQTT Publisher instance."""
    from ..mqtt.publisher import Publisher

    global _publisher_singleton
    try:
        return _publisher_singleton
    except NameError:
        _publisher_singleton = None  # type: ignore

    if _publisher_singleton is None:
        _publisher_singleton = Publisher()
    return _publisher_singleton


def get_safety_service(db: DBSession):
    """Get SafetyService instance."""
    from ..db.repositories import ActuatorRepository, ESPRepository
    from ..services.safety_service import SafetyService

    actuator_repo = ActuatorRepository(db)
    esp_repo = ESPRepository(db)
    return SafetyService(actuator_repo, esp_repo)


def get_actuator_service(db: DBSession):
    """Get ActuatorService instance."""
    from ..db.repositories import ActuatorRepository, ESPRepository
    from ..services.actuator_service import ActuatorService
    from ..services.safety_service import SafetyService

    actuator_repo = ActuatorRepository(db)
    esp_repo = ESPRepository(db)
    safety_service = SafetyService(actuator_repo, esp_repo)
    publisher = get_mqtt_publisher()

    return ActuatorService(actuator_repo, safety_service, publisher)


def get_sensor_service(db: DBSession):
    """
    Get SensorService instance.

    Provides SensorService with all required dependencies:
    - SensorRepository
    - ESPRepository
    - Publisher (for MQTT commands)
    """
    from ..db.repositories import ESPRepository, SensorRepository
    from ..services.sensor_service import SensorService

    sensor_repo = SensorRepository(db)
    esp_repo = ESPRepository(db)
    publisher = get_mqtt_publisher()

    return SensorService(
        sensor_repo=sensor_repo,
        esp_repo=esp_repo,
        publisher=publisher,
    )


def get_config_builder(db: DBSession):
    """Get ConfigPayloadBuilder instance."""
    from ..db.repositories import ActuatorRepository, ESPRepository, SensorRepository
    from ..services.config_builder import ConfigPayloadBuilder

    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)
    esp_repo = ESPRepository(db)

    return ConfigPayloadBuilder(
        sensor_repo=sensor_repo,
        actuator_repo=actuator_repo,
        esp_repo=esp_repo,
    )


def get_esp_service(db: DBSession):
    """Get ESPService instance."""
    from ..db.repositories import ESPRepository
    from ..services.esp_service import ESPService

    esp_repo = ESPRepository(db)
    publisher = get_mqtt_publisher()

    return ESPService(esp_repo, publisher)


def get_audit_log_repo(db: DBSession):
    """Get AuditLogRepository instance."""
    from ..db.repositories import AuditLogRepository

    return AuditLogRepository(db)


# Type aliases for service dependencies (for consistent usage)
MQTTPublisher = Annotated[Any, Depends(get_mqtt_publisher)]


async def get_config_builder_dep(db: DBSession):
    """Async dependency for ConfigPayloadBuilder."""
    return get_config_builder(db)


async def get_esp_service_dep(db: DBSession):
    """Async dependency for ESPService."""
    return get_esp_service(db)


async def get_audit_log_repo_dep(db: DBSession):
    """Async dependency for AuditLogRepository."""
    return get_audit_log_repo(db)


# =============================================================================
# Simulation Scheduler Dependency (Paket X)
# =============================================================================


def get_simulation_scheduler():
    """
    Get SimulationScheduler singleton instance.

    Paket X: Code Consolidation - Unified dependency for mock ESP simulation.

    Returns:
        SimulationScheduler instance

    Raises:
        HTTPException: 503 if scheduler not initialized
    """
    from ..services.simulation import get_simulation_scheduler as _get_scheduler

    try:
        scheduler = _get_scheduler()
        return scheduler
    except RuntimeError as e:
        logger.error(f"SimulationScheduler not initialized: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Simulation service not initialized",
        )


# Type alias for simulation scheduler dependency
# IMPORTANT: Named 'SimulationSchedulerDep' to avoid shadowing the actual class name
SimulationSchedulerDep = Annotated[Any, Depends(get_simulation_scheduler)]


# =============================================================================
# Sensor Scheduler Service Dependency (Phase 2H)
# =============================================================================


def get_sensor_scheduler_service(db: DBSession):
    """
    Get SensorSchedulerService instance.

    Phase 2H: Provides dependency for scheduled sensor measurement jobs.

    Args:
        db: Database session

    Returns:
        SensorSchedulerService instance with all dependencies
    """
    from ..db.repositories.esp_repo import ESPRepository
    from ..db.repositories.sensor_repo import SensorRepository
    from ..services.sensor_scheduler_service import SensorSchedulerService

    sensor_repo = SensorRepository(db)
    esp_repo = ESPRepository(db)
    publisher = get_mqtt_publisher()

    return SensorSchedulerService(
        sensor_repo=sensor_repo,
        esp_repo=esp_repo,
        publisher=publisher,
    )


# Type alias for sensor scheduler service dependency
SensorSchedulerServiceDep = Annotated[Any, Depends(get_sensor_scheduler_service)]
