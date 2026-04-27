"""
JWT authentication, password hashing, and security utilities.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
import bcrypt
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if len(password) > 72:
        password = password[:72]  # bcrypt limits passwords to 72 bytes
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if len(plain_password) > 72:
        plain_password = plain_password[:72]
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(
    user_id: str,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: UUID of the user (as string)
        username: Username for token payload
        expires_delta: Optional custom expiry duration
    
    Returns:
        Encoded JWT string
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token with longer expiry."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.
    
    Returns:
        Decoded payload dict, or None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None


def decode_access_token(token: str) -> Optional[dict]:
    """Decode an access token and verify its type."""
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        return payload
    return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode a refresh token and verify its type."""
    payload = decode_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None
