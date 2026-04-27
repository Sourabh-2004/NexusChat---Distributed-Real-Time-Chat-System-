"""
Message model for persistent chat message storage.
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class MessageType(str, enum.Enum):
    """Type of chat message."""
    TEXT = "text"
    SYSTEM = "system"  # Join/leave notifications
    IMAGE = "image"


class Message(Base, UUIDMixin, TimestampMixin):
    """Chat message model with idempotency support."""

    __tablename__ = "messages"

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType), default=MessageType.TEXT, nullable=False
    )
    # Client-generated UUID to prevent duplicate messages on retry
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=True
    )

    # Relationships
    room = relationship("Room", back_populates="messages")
    sender = relationship("User", back_populates="messages")

    __table_args__ = (
        # Optimized index for paginated message retrieval per room
        Index("ix_messages_room_created", "room_id", "created_at"),
        Index("ix_messages_idempotency", "idempotency_key"),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, room={self.room_id}, type={self.message_type})>"
