"""
Authentication service — business logic for user registration, login, and token refresh.
"""

import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, TokenResponse
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.exceptions import AuthenticationError, ConflictError

logger = logging.getLogger(__name__)


class AuthService:
    """Handles user authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserRegister) -> User:
        """
        Register a new user.
        
        Raises ConflictError if username or email already exists.
        """
        # Check for existing username
        result = await self.db.execute(
            select(User).where(
                (User.username == data.username) | (User.email == data.email)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.username == data.username:
                raise ConflictError("Username already taken")
            raise ConflictError("Email already registered")

        user = User(
            username=data.username,
            email=data.email,
            hashed_password=hash_password(data.password),
            display_name=data.display_name or data.username,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        logger.info(f"User registered: {user.username} (id={user.id})")
        return user

    async def login(self, data: UserLogin) -> TokenResponse:
        """
        Authenticate a user and return JWT tokens.
        
        Raises AuthenticationError if credentials are invalid.
        """
        result = await self.db.execute(
            select(User).where(User.username == data.username)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise AuthenticationError("Invalid username or password")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        access_token = create_access_token(str(user.id), user.username)
        refresh_token = create_refresh_token(str(user.id))

        logger.info(f"User logged in: {user.username}")
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Issue new tokens using a valid refresh token.
        """
        payload = decode_refresh_token(refresh_token)
        if not payload:
            raise AuthenticationError("Invalid or expired refresh token")

        user_id = payload.get("sub")
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise AuthenticationError("User not found or deactivated")

        new_access = create_access_token(str(user.id), user.username)
        new_refresh = create_refresh_token(str(user.id))

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
        )

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Fetch a user by their ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
