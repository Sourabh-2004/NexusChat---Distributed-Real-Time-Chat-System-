"""
Room and RoomMember models for chat room management.
"""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, ForeignKey, Enum, Index, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class RoomRole(str, enum.Enum):
    """Role of a user within a chat room."""
    ADMIN = "admin"
    MEMBER = "member"


class Room(Base, UUIDMixin, TimestampMixin):
    """Chat room model."""

    __tablename__ = "rooms"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=True
    )
    is_private: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    creator = relationship("User", back_populates="rooms_created")
    members = relationship(
        "RoomMember", back_populates="room", cascade="all, delete-orphan", lazy="selectin"
    )
    messages = relationship(
        "Message", back_populates="room", cascade="all, delete-orphan", lazy="noload"
    )

    def __repr__(self):
        return f"<Room(id={self.id}, name={self.name})>"


class RoomMember(Base, UUIDMixin):
    """Association table for room membership with roles."""

    __tablename__ = "room_members"

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[RoomRole] = mapped_column(
        Enum(RoomRole), default=RoomRole.MEMBER, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_memberships")

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_member"),
        Index("ix_room_members_room_user", "room_id", "user_id"),
    )

    def __repr__(self):
        return f"<RoomMember(room={self.room_id}, user={self.user_id}, role={self.role})>"
