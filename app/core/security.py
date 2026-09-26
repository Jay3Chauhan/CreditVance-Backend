"""
Security Module for Password Hashing and JWT Token Management.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import bcrypt
import jwt
from app.core.config import settings
from app.core.exceptions import AuthenticationError


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Generates a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Authentication token has expired.")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid authentication token.")


def create_refresh_token(
    subject: str | int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a long-lived JWT refresh token (default: 30 days)."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=30))
    to_encode = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "refresh",
    }
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("token_type") != "refresh":
            raise AuthenticationError("Invalid token type. Expected refresh token.")
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Refresh token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid refresh token.")


def create_password_reset_token(
    email: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a short-lived JWT password reset token (default: 15 minutes)."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))
    to_encode = {
        "sub": email.lower(),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "password_reset",
    }
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_password_reset_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT password reset token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("token_type") != "password_reset":
            raise AuthenticationError("Invalid token type. Expected password reset token.")
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Password reset token has expired.")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid password reset token.")

