"""
User model for authentication and profile management.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    """User account model."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    display_name: Mapped[str] = mapped_column(
        String(100), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    rooms_created = relationship("Room", back_populates="creator", lazy="selectin")
    room_memberships = relationship("RoomMember", back_populates="user", lazy="selectin")
    messages = relationship("Message", back_populates="sender", lazy="selectin")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
