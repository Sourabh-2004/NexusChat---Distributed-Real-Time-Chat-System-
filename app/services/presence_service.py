"""
Presence service — Redis-backed online/offline user tracking.
Uses Redis sorted sets with timestamp scores for efficient presence queries.
"""

import time
import logging
from typing import Optional

import redis.asyncio as aioredis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PresenceService:
    """
    Tracks user presence (online/offline) per room using Redis sorted sets.
    
    Key format: presence:{room_id}
    Value: user_id
    Score: last_seen timestamp (unix epoch)
    
    Users with score > (now - PRESENCE_TIMEOUT) are considered online.
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self.timeout = settings.PRESENCE_TIMEOUT_SECONDS

    async def set_online(self, room_id: str, user_id: str, username: str) -> None:
        """Mark a user as online in a room."""
        key = f"presence:{room_id}"
        now = time.time()
        await self.redis.zadd(key, {user_id: now})
        # Store username mapping for display
        await self.redis.hset(f"usernames", user_id, username)
        logger.debug(f"User {username} ({user_id}) online in room {room_id}")

    async def set_offline(self, room_id: str, user_id: str) -> None:
        """Remove a user from the online set in a room."""
        key = f"presence:{room_id}"
        await self.redis.zrem(key, user_id)
        logger.debug(f"User {user_id} offline in room {room_id}")

    async def heartbeat(self, room_id: str, user_id: str) -> None:
        """Update the last-seen timestamp for a user (heartbeat pulse)."""
        key = f"presence:{room_id}"
        now = time.time()
        await self.redis.zadd(key, {user_id: now})

    async def get_online_users(self, room_id: str) -> list[dict]:
        """
        Get all online users in a room.
        
        Returns list of {"user_id": str, "username": str} for users
        whose last-seen timestamp is within the timeout window.
        """
        key = f"presence:{room_id}"
        now = time.time()
        cutoff = now - self.timeout

        # Remove stale entries
        await self.redis.zremrangebyscore(key, 0, cutoff)

        # Get remaining (online) users
        user_ids = await self.redis.zrangebyscore(key, cutoff, "+inf")

        online_users = []
        for uid in user_ids:
            uid_str = uid if isinstance(uid, str) else uid.decode()
            username = await self.redis.hget("usernames", uid_str)
            if username:
                username = username if isinstance(username, str) else username.decode()
            online_users.append({
                "user_id": uid_str,
                "username": username or "Unknown",
            })

        return online_users

    async def is_online(self, room_id: str, user_id: str) -> bool:
        """Check if a specific user is online in a room."""
        key = f"presence:{room_id}"
        score = await self.redis.zscore(key, user_id)
        if score is None:
            return False
        return (time.time() - score) < self.timeout

    async def remove_user_from_all_rooms(self, user_id: str) -> None:
        """Remove a user from all presence sets (on disconnect)."""
        # Scan for all presence keys
        async for key in self.redis.scan_iter(match="presence:*"):
            key_str = key if isinstance(key, str) else key.decode()
            await self.redis.zrem(key_str, user_id)
        logger.debug(f"User {user_id} removed from all rooms presence")
