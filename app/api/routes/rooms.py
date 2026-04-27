"""
Chat room API routes — CRUD, join/leave, member listing.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.room import RoomCreate, RoomResponse, RoomListResponse
from app.services.room_service import RoomService
from app.models.user import User

router = APIRouter(prefix="/rooms", tags=["Chat Rooms"])


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    data: RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat room. The creator is automatically added as admin."""
    service = RoomService(db)
    room = await service.create_room(data, current_user.id)
    return RoomResponse(
        id=room.id,
        name=room.name,
        description=room.description,
        is_private=room.is_private,
        created_by=room.created_by,
        created_at=room.created_at,
        member_count=1,
    )


@router.get("", response_model=RoomListResponse)
async def list_rooms(
    my_rooms: bool = Query(False, description="Only show rooms I'm a member of"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List chat rooms.
    
    - `my_rooms=true`: Show only rooms the user has joined
    - `my_rooms=false`: Show all public rooms
    """
    service = RoomService(db)
    if my_rooms:
        rooms = await service.list_user_rooms(current_user.id)
    else:
        rooms = await service.list_public_rooms()
    return RoomListResponse(rooms=rooms, total=len(rooms))


@router.get("/{room_id}")
async def get_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get room details including member list."""
    service = RoomService(db)
    room = await service.get_room(room_id)
    members = await service.get_room_members(room_id)
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "is_private": room.is_private,
        "created_by": str(room.created_by) if room.created_by else None,
        "created_at": room.created_at.isoformat(),
        "members": members,
    }


@router.post("/{room_id}/join", status_code=200)
async def join_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Join a chat room."""
    service = RoomService(db)
    await service.join_room(room_id, current_user.id)
    return {"detail": "Successfully joined the room"}


@router.delete("/{room_id}/leave", status_code=200)
async def leave_room(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leave a chat room."""
    service = RoomService(db)
    await service.leave_room(room_id, current_user.id)
    return {"detail": "Successfully left the room"}


@router.get("/{room_id}/members")
async def get_room_members(
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List members of a room with their details."""
    service = RoomService(db)
    members = await service.get_room_members(room_id)
    return {"members": members}
