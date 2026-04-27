"""
Pydantic schemas for chat room endpoints.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.models.room import RoomRole


class RoomCreate(BaseModel):
    """Create room request."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_private: bool = False


class RoomResponse(BaseModel):
    """Room data response."""
    id: UUID
    name: str
    description: str | None
    is_private: bool
    created_by: UUID | None
    created_at: datetime
    member_count: int = 0

    class Config:
        from_attributes = True


class RoomDetailResponse(BaseModel):
    """Detailed room response with members."""
    id: UUID
    name: str
    description: str | None
    is_private: bool
    created_by: UUID | None
    created_at: datetime
    members: list["RoomMemberResponse"] = []

    class Config:
        from_attributes = True


class RoomMemberResponse(BaseModel):
    """Room member data."""
    user_id: UUID
    username: str
    display_name: str | None
    role: RoomRole
    joined_at: datetime
    is_online: bool = False

    class Config:
        from_attributes = True


class RoomListResponse(BaseModel):
    """Paginated room list."""
    rooms: list[RoomResponse]
    total: int
