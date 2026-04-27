"""
Room service — business logic for chat room CRUD and membership.
"""

import logging
from uuid import UUID
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.room import Room, RoomMember, RoomRole
from app.models.user import User
from app.schemas.room import RoomCreate, RoomResponse, RoomDetailResponse, RoomMemberResponse
from app.core.exceptions import NotFoundError, ConflictError, AuthorizationError

logger = logging.getLogger(__name__)


class RoomService:
    """Handles chat room operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_room(self, data: RoomCreate, user_id: UUID) -> Room:
        """Create a new chat room and add creator as admin."""
        room = Room(
            name=data.name,
            description=data.description,
            is_private=data.is_private,
            created_by=user_id,
        )
        self.db.add(room)
        await self.db.flush()

        # Add creator as admin member
        member = RoomMember(
            room_id=room.id,
            user_id=user_id,
            role=RoomRole.ADMIN,
        )
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(room)
        logger.info(f"Room created: {room.name} (id={room.id}) by user {user_id}")
        return room

    async def get_room(self, room_id: UUID) -> Room:
        """Get a room by ID, raising NotFoundError if missing."""
        result = await self.db.execute(
            select(Room)
            .options(selectinload(Room.members).selectinload(RoomMember.user))
            .where(Room.id == room_id)
        )
        room = result.scalar_one_or_none()
        if not room:
            raise NotFoundError("Room")
        return room

    async def list_user_rooms(self, user_id: UUID) -> list[RoomResponse]:
        """List all rooms a user is a member of."""
        result = await self.db.execute(
            select(Room)
            .join(RoomMember, Room.id == RoomMember.room_id)
            .where(RoomMember.user_id == user_id)
            .order_by(Room.created_at.desc())
        )
        rooms = result.scalars().all()

        room_responses = []
        for room in rooms:
            # Get member count
            count_result = await self.db.execute(
                select(func.count(RoomMember.id)).where(RoomMember.room_id == room.id)
            )
            member_count = count_result.scalar()

            room_responses.append(
                RoomResponse(
                    id=room.id,
                    name=room.name,
                    description=room.description,
                    is_private=room.is_private,
                    created_by=room.created_by,
                    created_at=room.created_at,
                    member_count=member_count or 0,
                )
            )
        return room_responses

    async def list_public_rooms(self) -> list[RoomResponse]:
        """List all public rooms."""
        result = await self.db.execute(
            select(Room).where(Room.is_private == False).order_by(Room.created_at.desc())
        )
        rooms = result.scalars().all()

        room_responses = []
        for room in rooms:
            count_result = await self.db.execute(
                select(func.count(RoomMember.id)).where(RoomMember.room_id == room.id)
            )
            member_count = count_result.scalar()
            room_responses.append(
                RoomResponse(
                    id=room.id,
                    name=room.name,
                    description=room.description,
                    is_private=room.is_private,
                    created_by=room.created_by,
                    created_at=room.created_at,
                    member_count=member_count or 0,
                )
            )
        return room_responses

    async def join_room(self, room_id: UUID, user_id: UUID) -> RoomMember:
        """Add a user to a room."""
        # Check room exists
        room = await self.get_room(room_id)

        # Check if already a member
        result = await self.db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ConflictError("Already a member of this room")

        member = RoomMember(
            room_id=room_id,
            user_id=user_id,
            role=RoomRole.MEMBER,
        )
        self.db.add(member)
        await self.db.flush()
        logger.info(f"User {user_id} joined room {room_id}")
        return member

    async def leave_room(self, room_id: UUID, user_id: UUID) -> None:
        """Remove a user from a room."""
        result = await self.db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise NotFoundError("Room membership")

        await self.db.delete(member)
        await self.db.flush()
        logger.info(f"User {user_id} left room {room_id}")

    async def is_member(self, room_id: UUID, user_id: UUID) -> bool:
        """Check if a user is a member of a room."""
        result = await self.db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_room_members(self, room_id: UUID) -> list[dict]:
        """Get all members of a room with user details."""
        result = await self.db.execute(
            select(RoomMember, User)
            .join(User, RoomMember.user_id == User.id)
            .where(RoomMember.room_id == room_id)
            .order_by(RoomMember.joined_at)
        )
        rows = result.all()
        members = []
        for member, user in rows:
            members.append({
                "user_id": str(user.id),
                "username": user.username,
                "display_name": user.display_name,
                "role": member.role.value,
                "joined_at": member.joined_at.isoformat(),
            })
        return members
