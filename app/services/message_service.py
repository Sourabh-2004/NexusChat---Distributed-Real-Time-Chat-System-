"""
Message service — business logic for message persistence and retrieval.
"""

import logging
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import Message, MessageType
from app.models.user import User
from app.schemas.message import MessageResponse, MessageListResponse

logger = logging.getLogger(__name__)


class MessageService:
    """Handles chat message persistence and retrieval."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_message(
        self,
        room_id: UUID,
        sender_id: UUID,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        idempotency_key: str | None = None,
    ) -> Message:
        """
        Persist a chat message to the database.
        
        If an idempotency_key is provided and a message with that key
        already exists, returns the existing message (prevents duplicates).
        """
        # Check idempotency
        if idempotency_key:
            result = await self.db.execute(
                select(Message).where(Message.idempotency_key == idempotency_key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.debug(f"Duplicate message detected: idempotency_key={idempotency_key}")
                return existing

        message = Message(
            room_id=room_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            idempotency_key=idempotency_key,
        )
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        logger.debug(f"Message saved: id={message.id}, room={room_id}")
        return message

    async def save_system_message(
        self,
        room_id: UUID,
        content: str,
    ) -> Message:
        """Save a system message (join/leave notification)."""
        message = Message(
            room_id=room_id,
            sender_id=None,
            content=content,
            message_type=MessageType.SYSTEM,
        )
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def get_room_messages(
        self,
        room_id: UUID,
        limit: int = 50,
        before: str | None = None,
    ) -> MessageListResponse:
        """
        Get paginated chat messages for a room using cursor-based pagination.
        
        Args:
            room_id: Room UUID
            limit: Max messages to return (default 50, max 100)
            before: Cursor (ISO datetime string) — return messages before this time
        
        Returns:
            MessageListResponse with messages, has_more flag, and next cursor
        """
        limit = min(limit, 100)

        query = (
            select(Message, User)
            .outerjoin(User, Message.sender_id == User.id)
            .where(Message.room_id == room_id)
        )

        if before:
            try:
                cursor_dt = datetime.fromisoformat(before)
                query = query.where(Message.created_at < cursor_dt)
            except ValueError:
                pass  # Invalid cursor, ignore

        query = query.order_by(Message.created_at.desc()).limit(limit + 1)

        result = await self.db.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        messages = []
        for msg, user in rows:
            messages.append(
                MessageResponse(
                    id=msg.id,
                    room_id=msg.room_id,
                    sender_id=msg.sender_id,
                    sender_username=user.username if user else None,
                    content=msg.content,
                    message_type=msg.message_type,
                    created_at=msg.created_at,
                )
            )

        # Reverse so messages are in chronological order
        messages.reverse()

        next_cursor = None
        if has_more and messages:
            next_cursor = messages[0].created_at.isoformat()

        return MessageListResponse(
            messages=messages,
            has_more=has_more,
            next_cursor=next_cursor,
        )
