"""
FastAPI dependency injection — shared dependencies for routes.

Provides:
- Database session
- Redis client
- Authenticated user extraction
- Rate limiter
"""

import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.core.security import decode_access_token
from app.core.exceptions import AuthenticationError
from app.models.user import User
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def get_db(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    """Provide a database session."""
    return session


async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate the current user from the Authorization header.
    
    Expected format: Bearer <access_token>
    
    Returns the User ORM object.
    Raises AuthenticationError if token is invalid or user not found.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)

    if not payload:
        raise AuthenticationError("Invalid or expired access token")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or deactivated")

    return user


async def get_ws_user(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate user from WebSocket query parameter.
    
    WebSocket connections use ?token=<access_token> since
    the WebSocket API doesn't support custom headers.
    """
    payload = decode_access_token(token)
    if not payload:
        raise AuthenticationError("Invalid or expired token")

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or deactivated")

    return user
