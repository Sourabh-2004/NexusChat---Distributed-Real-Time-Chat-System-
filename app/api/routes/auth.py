"""
Authentication API routes — register, login, and token refresh.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    TokenRefresh,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register a new user account.
    
    - **username**: 3-50 alphanumeric characters and underscores
    - **email**: Valid email address
    - **password**: 6-128 characters
    """
    service = AuthService(db)
    user = await service.register(data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate and receive JWT tokens.
    
    Returns access_token (30 min TTL) and refresh_token (7 day TTL).
    Use the access_token in the Authorization header: `Bearer <token>`
    """
    service = AuthService(db)
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for new access and refresh tokens.
    """
    service = AuthService(db)
    return await service.refresh_token(data.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the currently authenticated user's profile.
    """
    return current_user
