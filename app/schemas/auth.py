"""
Pydantic schemas for authentication endpoints.
"""

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


class UserRegister(BaseModel):
    """Registration request schema."""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=100)


class UserLogin(BaseModel):
    """Login request schema."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Token refresh request."""
    refresh_token: str


class UserResponse(BaseModel):
    """User data response."""
    id: UUID
    username: str
    email: str
    display_name: str | None
    is_active: bool

    class Config:
        from_attributes = True
