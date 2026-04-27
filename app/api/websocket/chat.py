"""
WebSocket chat endpoint — handles real-time bidirectional communication.

Event flow:
1. Client connects with JWT token: ws://host/ws/chat?token=<jwt>
2. Server authenticates and registers the connection
3. Client sends events: message, join_room, leave_room, typing_start, typing_stop, ping
4. Server broadcasts via Redis Pub/Sub to all instances
5. Each instance delivers to local WebSocket connections

Supports:
- JWT authentication via query parameter
- Room-based message routing
- Typing indicators
- Presence tracking
- Heartbeat/ping-pong for dead connection detection
- Backpressure handling via bounded send queues
"""

import json
import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from app.core.security import decode_access_token
from app.db.session import async_session_factory
from app.models.user import User
from app.models.message import MessageType
from app.services.message_service import MessageService
from app.services.room_service import RoomService
from app.schemas.ws import WSOutboundMessage
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(None)):
    """
    Main WebSocket endpoint for real-time chat.
    
    Authentication: Pass JWT access token as query parameter: ?token=<jwt>
    
    Inbound events (JSON):
    - {"event": "join_room", "data": {"room_id": "<uuid>"}}
    - {"event": "leave_room", "data": {"room_id": "<uuid>"}}
    - {"event": "message", "data": {"room_id": "<uuid>", "content": "...", "idempotency_key": "..."}}
    - {"event": "typing_start", "data": {"room_id": "<uuid>"}}
    - {"event": "typing_stop", "data": {"room_id": "<uuid>"}}
    - {"event": "ping", "data": {}}
    
    Outbound events:
    - {"event": "message", "data": {...}}
    - {"event": "presence", "data": {...}}
    - {"event": "typing", "data": {...}}
    - {"event": "system", "data": {...}}
    - {"event": "pong", "data": {}}
    - {"event": "error", "data": {...}}
    """
    # Access global app state
    app = websocket.app
    connection_manager = app.state.connection_manager
    redis_broker = app.state.redis_broker
    redis_client = app.state.redis_client
    presence_service = app.state.presence_service
    typing_service = app.state.typing_service
    rate_limiter = app.state.rate_limiter

    # === Authentication ===
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.get("sub")
    username = payload.get("username", "Unknown")

    # Verify user exists
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.close(code=4001, reason="User not found")
            return

    # === Connection Setup ===
    conn = await connection_manager.connect(websocket, user_id, username)
    logger.info(f"WS connected: {username} ({user_id})")

    # Send welcome message
    welcome = WSOutboundMessage.system_message(
        room_id="system",
        content=f"Welcome, {username}! You are connected."
    )
    await connection_manager.send_to_user(user_id, welcome)

    # === Heartbeat Task ===
    async def heartbeat():
        """Send periodic pings to detect dead connections."""
        try:
            while True:
                await asyncio.sleep(30)
                if websocket.client_state == WebSocketState.CONNECTED:
                    try:
                        await websocket.send_json({"event": "ping", "data": {}})
                    except Exception:
                        break
                else:
                    break
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(heartbeat())

    # === Main Message Loop ===
    try:
        while True:
            raw = await websocket.receive_text()
            conn.update_activity()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await connection_manager.send_to_user(
                    user_id,
                    WSOutboundMessage.error_message("Invalid JSON format"),
                )
                continue

            event = data.get("event", "")
            event_data = data.get("data", {})

            # --- Rate Limiting ---
            try:
                await rate_limiter.check_ws_rate_limit(
                    user_id,
                    limit=app.state.settings.WS_RATE_LIMIT_PER_MINUTE,
                )
            except Exception:
                await connection_manager.send_to_user(
                    user_id,
                    WSOutboundMessage.error_message(
                        "Rate limit exceeded. Please slow down.", "rate_limited"
                    ),
                )
                continue

            # --- Event Handling ---
            if event == "join_room":
                await _handle_join_room(
                    user_id, username, event_data,
                    connection_manager, redis_broker, presence_service, db_factory=async_session_factory
                )

            elif event == "leave_room":
                await _handle_leave_room(
                    user_id, username, event_data,
                    connection_manager, redis_broker, presence_service
                )

            elif event == "message":
                await _handle_message(
                    user_id, username, event_data,
                    connection_manager, redis_broker, db_factory=async_session_factory
                )

            elif event == "typing_start":
                room_id = event_data.get("room_id", "")
                if room_id:
                    await typing_service.set_typing(room_id, user_id, username)
                    typing_msg = WSOutboundMessage.typing_indicator(
                        room_id, user_id, username, True
                    )
                    await redis_broker.publish(
                        f"room:{room_id}",
                        {"type": "typing", "payload": typing_msg.model_dump()},
                    )

            elif event == "typing_stop":
                room_id = event_data.get("room_id", "")
                if room_id:
                    await typing_service.clear_typing(room_id, user_id)
                    typing_msg = WSOutboundMessage.typing_indicator(
                        room_id, user_id, username, False
                    )
                    await redis_broker.publish(
                        f"room:{room_id}",
                        {"type": "typing", "payload": typing_msg.model_dump()},
                    )

            elif event == "ping" or event == "pong":
                await connection_manager.send_to_user(
                    user_id, WSOutboundMessage.pong()
                )

            else:
                await connection_manager.send_to_user(
                    user_id,
                    WSOutboundMessage.error_message(f"Unknown event: {event}"),
                )

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {username} ({user_id})")
    except Exception as e:
        logger.error(f"WS error for {username}: {e}")
    finally:
        # === Cleanup ===
        heartbeat_task.cancel()

        # Notify rooms about user leaving
        for room_id in list(conn.rooms):
            await presence_service.set_offline(room_id, user_id)
            leave_msg = WSOutboundMessage.presence_update(
                room_id, user_id, username, "offline"
            )
            try:
                await redis_broker.publish(
                    f"room:{room_id}",
                    {"type": "presence", "payload": leave_msg.model_dump()},
                )
            except Exception:
                pass

        await connection_manager.disconnect(user_id)


# === Event Handlers ===

async def _handle_join_room(
    user_id, username, event_data,
    connection_manager, redis_broker, presence_service, db_factory
):
    """Handle a user joining a chat room."""
    room_id = event_data.get("room_id", "")
    if not room_id:
        await connection_manager.send_to_user(
            user_id, WSOutboundMessage.error_message("room_id is required")
        )
        return

    # Verify membership
    async with db_factory() as db:
        room_service = RoomService(db)
        is_member = await room_service.is_member(UUID(room_id), UUID(user_id))
        if not is_member:
            await connection_manager.send_to_user(
                user_id,
                WSOutboundMessage.error_message("You are not a member of this room"),
            )
            return

    # Subscribe to Redis channel for this room
    channel = f"room:{room_id}"

    async def room_message_handler(ch, message):
        """Callback for Redis Pub/Sub messages on this room's channel."""
        msg_type = message.get("type", "")
        payload = message.get("payload", {})

        if msg_type == "chat":
            # Deliver to all local connections in this room
            sender_id = payload.get("data", {}).get("sender_id", "")
            outbound = WSOutboundMessage(**payload)
            await connection_manager.broadcast_to_room(room_id, outbound)

        elif msg_type == "presence":
            outbound = WSOutboundMessage(**payload)
            await connection_manager.broadcast_to_room(room_id, outbound)

        elif msg_type == "typing":
            outbound = WSOutboundMessage(**payload)
            # Don't send typing indicator back to the typer
            typer_id = payload.get("data", {}).get("user_id", "")
            await connection_manager.broadcast_to_room(
                room_id, outbound, exclude_user=typer_id
            )

        elif msg_type == "system":
            outbound = WSOutboundMessage(**payload)
            await connection_manager.broadcast_to_room(room_id, outbound)

    await redis_broker.subscribe(channel, room_message_handler)
    await connection_manager.join_room(user_id, room_id)
    await presence_service.set_online(room_id, user_id, username)

    # Notify room about new user
    join_msg = WSOutboundMessage.presence_update(room_id, user_id, username, "online")
    await redis_broker.publish(
        channel, {"type": "presence", "payload": join_msg.model_dump()}
    )

    # Send online users list
    online = await presence_service.get_online_users(room_id)
    await connection_manager.send_to_user(
        user_id,
        WSOutboundMessage(event="online_users", data={"room_id": room_id, "users": online}),
    )

    logger.info(f"User {username} joined room {room_id}")


async def _handle_leave_room(
    user_id, username, event_data,
    connection_manager, redis_broker, presence_service
):
    """Handle a user leaving a chat room."""
    room_id = event_data.get("room_id", "")
    if not room_id:
        return

    await connection_manager.leave_room(user_id, room_id)
    await presence_service.set_offline(room_id, user_id)

    leave_msg = WSOutboundMessage.presence_update(room_id, user_id, username, "offline")
    await redis_broker.publish(
        f"room:{room_id}",
        {"type": "presence", "payload": leave_msg.model_dump()},
    )

    logger.info(f"User {username} left room {room_id}")


async def _handle_message(
    user_id, username, event_data,
    connection_manager, redis_broker, db_factory
):
    """Handle a new chat message — persist and broadcast."""
    room_id = event_data.get("room_id", "")
    content = event_data.get("content", "").strip()
    idempotency_key = event_data.get("idempotency_key")

    if not room_id or not content:
        await connection_manager.send_to_user(
            user_id,
            WSOutboundMessage.error_message("room_id and content are required"),
        )
        return

    if len(content) > 5000:
        await connection_manager.send_to_user(
            user_id,
            WSOutboundMessage.error_message("Message too long (max 5000 chars)"),
        )
        return

    # Persist to database
    async with db_factory() as db:
        msg_service = MessageService(db)
        message = await msg_service.save_message(
            room_id=UUID(room_id),
            sender_id=UUID(user_id),
            content=content,
            message_type=MessageType.TEXT,
            idempotency_key=idempotency_key,
        )
        await db.commit()

        # Build outbound message
        chat_msg = WSOutboundMessage.chat_message(
            message_id=str(message.id),
            room_id=room_id,
            sender_id=user_id,
            sender_username=username,
            content=content,
            message_type="text",
            created_at=message.created_at.isoformat(),
        )

    # Publish to Redis for cross-instance delivery
    await redis_broker.publish(
        f"room:{room_id}",
        {"type": "chat", "payload": chat_msg.model_dump()},
    )
