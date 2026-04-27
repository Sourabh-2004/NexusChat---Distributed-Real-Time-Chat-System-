"""
Typing service — Redis-backed typing indicator with auto-expiry.
Uses Redis keys with short TTL to automatically clear typing status.
"""

import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

TYPING_TTL_SECONDS = 3  # Typing indicator expires after 3 seconds


class TypingService:
    """
    Manages typing indicators using Redis keys with TTL.
    
    Key format: typing:{room_id}:{user_id}
    Value: username
    TTL: 3 seconds (auto-expires)
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def set_typing(self, room_id: str, user_id: str, username: str) -> None:
        """Mark a user as currently typing in a room."""
        key = f"typing:{room_id}:{user_id}"
        await self.redis.setex(key, TYPING_TTL_SECONDS, username)

    async def clear_typing(self, room_id: str, user_id: str) -> None:
        """Clear typing indicator for a user."""
        key = f"typing:{room_id}:{user_id}"
        await self.redis.delete(key)

    async def get_typing_users(self, room_id: str) -> list[dict]:
        """Get all users currently typing in a room."""
        pattern = f"typing:{room_id}:*"
        typing_users = []

        async for key in self.redis.scan_iter(match=pattern):
            key_str = key if isinstance(key, str) else key.decode()
            user_id = key_str.split(":")[-1]
            username = await self.redis.get(key_str)
            if username:
                username = username if isinstance(username, str) else username.decode()
                typing_users.append({
                    "user_id": user_id,
                    "username": username,
                })

        return typing_users
