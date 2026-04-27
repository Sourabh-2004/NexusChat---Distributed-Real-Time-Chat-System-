"""
Pydantic schemas for WebSocket event payloads.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Any


class WSEvent(BaseModel):
    """Base WebSocket event structure."""
    event: str
    data: dict = {}


class WSMessageData(BaseModel):
    """Data payload for a chat message event."""
    room_id: str
    content: str = Field(..., min_length=1, max_length=5000)
    idempotency_key: str | None = None


class WSJoinRoomData(BaseModel):
    """Data payload for joining a room."""
    room_id: str


class WSLeaveRoomData(BaseModel):
    """Data payload for leaving a room."""
    room_id: str


class WSTypingData(BaseModel):
    """Data payload for typing indicator."""
    room_id: str


class WSOutboundMessage(BaseModel):
    """Outbound message sent to clients."""
    event: str
    data: dict

    @classmethod
    def chat_message(
        cls,
        message_id: str,
        room_id: str,
        sender_id: str,
        sender_username: str,
        content: str,
        message_type: str,
        created_at: str,
    ) -> "WSOutboundMessage":
        return cls(
            event="message",
            data={
                "id": message_id,
                "room_id": room_id,
                "sender_id": sender_id,
                "sender_username": sender_username,
                "content": content,
                "message_type": message_type,
                "created_at": created_at,
            },
        )

    @classmethod
    def presence_update(
        cls, room_id: str, user_id: str, username: str, status: str
    ) -> "WSOutboundMessage":
        return cls(
            event="presence",
            data={
                "room_id": room_id,
                "user_id": user_id,
                "username": username,
                "status": status,
            },
        )

    @classmethod
    def typing_indicator(
        cls, room_id: str, user_id: str, username: str, is_typing: bool
    ) -> "WSOutboundMessage":
        return cls(
            event="typing",
            data={
                "room_id": room_id,
                "user_id": user_id,
                "username": username,
                "is_typing": is_typing,
            },
        )

    @classmethod
    def system_message(cls, room_id: str, content: str) -> "WSOutboundMessage":
        return cls(
            event="system",
            data={
                "room_id": room_id,
                "content": content,
            },
        )

    @classmethod
    def error_message(cls, detail: str, code: str = "error") -> "WSOutboundMessage":
        return cls(
            event="error",
            data={"detail": detail, "code": code},
        )

    @classmethod
    def pong(cls) -> "WSOutboundMessage":
        return cls(event="pong", data={})
