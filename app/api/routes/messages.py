"""
Message API routes — chat history with cursor-based pagination.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.message import MessageListResponse
from app.services.message_service import MessageService
from app.services.room_service import RoomService
from app.core.exceptions import AuthorizationError
from app.models.user import User

router = APIRouter(prefix="/rooms/{room_id}/messages", tags=["Messages"])


@router.get("", response_model=MessageListResponse)
async def get_messages(
    room_id: UUID,
    limit: int = Query(50, ge=1, le=100, description="Number of messages to return"),
    before: str | None = Query(None, description="Cursor: ISO datetime string"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get paginated chat history for a room.
    
    Uses cursor-based pagination for consistent results:
    - First request: omit `before` to get the latest messages
    - Subsequent requests: pass `next_cursor` from the response as `before`
    
    Messages are returned in chronological order (oldest first).
    """
    # Verify user is a member of the room
    room_service = RoomService(db)
    is_member = await room_service.is_member(room_id, current_user.id)
    if not is_member:
        raise AuthorizationError("You must be a member of this room to view messages")

    message_service = MessageService(db)
    return await message_service.get_room_messages(room_id, limit, before)
