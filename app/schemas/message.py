"""
Pydantic schemas for message endpoints.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from app.models.message import MessageType


class MessageResponse(BaseModel):
    """Message data response."""
    id: UUID
    room_id: UUID
    sender_id: UUID | None
    sender_username: str | None = None
    content: str
    message_type: MessageType
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated message list with cursor."""
    messages: list[MessageResponse]
    has_more: bool
    next_cursor: str | None = None
