"""
Security utilities for God-Kaiser Server
JWT Token generation/verification and password hashing
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from .config import get_settings


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        str: Hashed password
    """
    # Encode password to bytes, hash with bcrypt, return as string
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


# Alias for backwards compatibility
get_password_hash = hash_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database

    Returns:
        bool: True if password matches, False otherwise
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(
    user_id: int,
    additional_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: User ID to encode in token
        additional_claims: Optional additional claims to include
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded JWT token
    """
    settings = get_settings()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.security.jwt_access_token_expire_minutes
        )

    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.security.jwt_secret_key,
        algorithm=settings.security.jwt_algorithm,
    )

    return encoded_jwt


def create_refresh_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT refresh token.

    Args:
        user_id: User ID to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded JWT refresh token
    """
    settings = get_settings()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.security.jwt_refresh_token_expire_days
        )

    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),  # ensure uniqueness to support rotation
        "type": "refresh",
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.security.jwt_secret_key,
        algorithm=settings.security.jwt_algorithm,
    )

    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token to verify
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        dict: Decoded token payload

    Raises:
        JWTError: If token is invalid or expired
        ValueError: If token type doesn't match expected type
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.security.jwt_secret_key,
            algorithms=[settings.security.jwt_algorithm],
        )

        token_type = payload.get("type")
        if token_type != expected_type:
            raise ValueError(f"Invalid token type. Expected '{expected_type}', got '{token_type}'")

        return payload

    except JWTError as e:
        raise JWTError(f"Token verification failed: {str(e)}")


def decode_token_payload(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode token payload without verification (for debugging).

    Args:
        token: JWT token to decode

    Returns:
        dict: Decoded payload or None if invalid
    """
    try:
        # Decode without verification
        payload = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
        return payload
    except Exception:
        return None


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Args:
        password: Password to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    settings = get_settings()

    if len(password) < settings.security.password_min_length:
        return (
            False,
            f"Password must be at least {settings.security.password_min_length} characters long",
        )

    # Check for at least one uppercase letter
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    # Check for at least one lowercase letter
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    # Check for at least one digit
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    # Check for at least one special character
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character"

    return True, None


def create_api_key(user_id: int, name: str) -> str:
    """
    Create an API key for programmatic access.

    Args:
        user_id: User ID
        name: API key name/description

    Returns:
        str: API key token (long-lived access token)
    """
    # API keys are long-lived (1 year expiration)
    expires_delta = timedelta(days=365)

    additional_claims = {
        "name": name,
        "api_key": True,
    }

    return create_access_token(
        user_id=user_id,
        additional_claims=additional_claims,
        expires_delta=expires_delta,
    )


def verify_api_key(api_key: str) -> Dict[str, Any]:
    """
    Verify an API key.

    Args:
        api_key: API key to verify

    Returns:
        dict: Decoded API key payload

    Raises:
        JWTError: If API key is invalid
        ValueError: If token is not an API key
    """
    payload = verify_token(api_key, expected_type="access")

    if not payload.get("api_key"):
        raise ValueError("Token is not an API key")

    return payload
