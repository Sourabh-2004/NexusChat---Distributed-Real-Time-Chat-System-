"""
WebSocket Connection Manager — centralized management of WebSocket connections.

Handles:
- Connection tracking per room
- Backpressure for slow clients
- Heartbeat/ping-pong for dead connection detection
- Efficient broadcast to room members
- Graceful disconnect and cleanup
"""

import asyncio
import json
import time
import logging
from typing import Dict, Set, Optional
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.schemas.ws import WSOutboundMessage

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class WebSocketConnection:
    """
    Wrapper around a FastAPI WebSocket with metadata and send queue.
    
    Tracks:
    - User identity (user_id, username)
    - Rooms the connection is subscribed to
    - Send queue for backpressure handling
    - Last activity timestamp for heartbeat
    """

    websocket: WebSocket
    user_id: str
    username: str
    rooms: Set[str] = field(default_factory=set)
    send_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=settings.MAX_SEND_QUEUE_SIZE))
    last_activity: float = field(default_factory=time.time)
    _send_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = time.time()


class ConnectionManager:
    """
    Central manager for all WebSocket connections across the application instance.
    
    Data structures:
    - _connections: user_id → WebSocketConnection (1 connection per user)
    - _room_connections: room_id → Set[user_id] (fast room-level broadcast)
    
    Memory efficiency:
    - Uses sets for O(1) add/remove/membership-check
    - Bounded send queues prevent memory leaks from slow clients
    """

    def __init__(self):
        self._connections: Dict[str, WebSocketConnection] = {}
        self._room_connections: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    @property
    def active_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return len(self._connections)

    async def connect(
        self, websocket: WebSocket, user_id: str, username: str
    ) -> WebSocketConnection:
        """
        Accept a WebSocket connection and register it.
        
        If the user already has an active connection, the old one is
        disconnected first (prevents ghost connections).
        """
        await websocket.accept()

        async with self._lock:
            # Disconnect existing connection for this user
            if user_id in self._connections:
                old_conn = self._connections[user_id]
                await self._force_disconnect(old_conn, reason="New connection opened")

            conn = WebSocketConnection(
                websocket=websocket,
                user_id=user_id,
                username=username,
            )
            # Start the send queue processor
            conn._send_task = asyncio.create_task(self._process_send_queue(conn))
            self._connections[user_id] = conn

        logger.info(
            f"WebSocket connected: user={username} ({user_id}), "
            f"total_connections={self.active_connections}"
        )
        return conn

    async def disconnect(self, user_id: str) -> None:
        """
        Remove a connection and clean up room subscriptions.
        """
        async with self._lock:
            conn = self._connections.pop(user_id, None)
            if conn:
                # Remove from all rooms
                for room_id in list(conn.rooms):
                    room_set = self._room_connections.get(room_id)
                    if room_set:
                        room_set.discard(user_id)
                        if not room_set:
                            del self._room_connections[room_id]

                # Cancel the send queue processor
                if conn._send_task:
                    conn._send_task.cancel()

                # Close the WebSocket if still open
                try:
                    if conn.websocket.client_state == WebSocketState.CONNECTED:
                        await conn.websocket.close()
                except Exception:
                    pass

        logger.info(f"WebSocket disconnected: user_id={user_id}")

    async def join_room(self, user_id: str, room_id: str) -> None:
        """Subscribe a user's connection to a room."""
        async with self._lock:
            conn = self._connections.get(user_id)
            if conn:
                conn.rooms.add(room_id)
                if room_id not in self._room_connections:
                    self._room_connections[room_id] = set()
                self._room_connections[room_id].add(user_id)
                logger.debug(f"User {user_id} joined room {room_id}")

    async def leave_room(self, user_id: str, room_id: str) -> None:
        """Unsubscribe a user's connection from a room."""
        async with self._lock:
            conn = self._connections.get(user_id)
            if conn:
                conn.rooms.discard(room_id)
                room_set = self._room_connections.get(room_id)
                if room_set:
                    room_set.discard(user_id)
                    if not room_set:
                        del self._room_connections[room_id]

    async def broadcast_to_room(
        self, room_id: str, message: WSOutboundMessage, exclude_user: str | None = None
    ) -> None:
        """
        Send a message to all connections in a room.
        
        Uses the send queue for backpressure control. If a client's
        queue is full, the message is dropped and a warning is logged.
        """
        user_ids = self._room_connections.get(room_id, set()).copy()
        payload = message.model_dump_json()

        for user_id in user_ids:
            if user_id == exclude_user:
                continue

            conn = self._connections.get(user_id)
            if conn:
                try:
                    conn.send_queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Backpressure: client is too slow
                    logger.warning(
                        f"Send queue full for user {user_id}, disconnecting slow client"
                    )
                    asyncio.create_task(self._force_disconnect(
                        conn, reason="Send queue overflow (slow client)"
                    ))

    async def send_to_user(self, user_id: str, message: WSOutboundMessage) -> None:
        """Send a message directly to a specific user."""
        conn = self._connections.get(user_id)
        if conn:
            payload = message.model_dump_json()
            try:
                conn.send_queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(f"Send queue full for user {user_id}")

    async def _process_send_queue(self, conn: WebSocketConnection) -> None:
        """
        Background task that drains the send queue and writes to the WebSocket.
        
        Runs for the lifetime of the connection. Handles send errors
        by disconnecting the client cleanly.
        """
        try:
            while True:
                payload = await conn.send_queue.get()
                try:
                    if conn.websocket.client_state == WebSocketState.CONNECTED:
                        await conn.websocket.send_text(payload)
                    else:
                        break
                except Exception as e:
                    logger.error(f"Send failed for user {conn.user_id}: {e}")
                    break
        except asyncio.CancelledError:
            pass

    async def _force_disconnect(
        self, conn: WebSocketConnection, reason: str = "Forced disconnect"
    ) -> None:
        """Force-disconnect a connection with a reason message."""
        try:
            error_msg = WSOutboundMessage.error_message(reason, "disconnected")
            if conn.websocket.client_state == WebSocketState.CONNECTED:
                await conn.websocket.send_text(error_msg.model_dump_json())
                await conn.websocket.close(code=1000, reason=reason)
        except Exception:
            pass
        finally:
            # Clean up from tracking structures
            self._connections.pop(conn.user_id, None)
            for room_id in list(conn.rooms):
                room_set = self._room_connections.get(room_id)
                if room_set:
                    room_set.discard(conn.user_id)
            if conn._send_task:
                conn._send_task.cancel()

    def get_room_user_ids(self, room_id: str) -> Set[str]:
        """Get all user IDs connected to a room on this instance."""
        return self._room_connections.get(room_id, set()).copy()

    def get_connection(self, user_id: str) -> Optional[WebSocketConnection]:
        """Get a user's connection if it exists."""
        return self._connections.get(user_id)

    def get_user_rooms(self, user_id: str) -> Set[str]:
        """Get all rooms a user is subscribed to."""
        conn = self._connections.get(user_id)
        return conn.rooms.copy() if conn else set()
