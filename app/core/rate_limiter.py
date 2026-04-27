"""
Redis-backed sliding window rate limiter.
Shared across all FastAPI instances for accurate distributed rate limiting.
"""

import time
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter backed by Redis sorted sets.
    
    Each request adds a timestamped entry. Entries older than the window
    are pruned. If count exceeds the limit, the request is denied.
    """

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> bool:
        """
        Check if a request is within the rate limit.
        
        Args:
            key: Unique identifier (e.g., "ratelimit:api:{user_id}")
            limit: Maximum requests allowed in the window
            window_seconds: Size of the sliding window in seconds
        
        Returns:
            True if allowed, raises HTTPException if rate limited.
        """
        now = time.time()
        window_start = now - window_seconds

        pipe = self.redis.pipeline()
        # Remove entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Count entries in the window
        pipe.zcard(key)
        # Add the current request
        pipe.zadd(key, {f"{now}": now})
        # Set TTL on the key to auto-cleanup
        pipe.expire(key, window_seconds + 1)

        results = await pipe.execute()
        request_count = results[1]

        if request_count >= limit:
            retry_after = int(window_seconds - (now - window_start))
            logger.warning(
                f"Rate limit exceeded for key={key}, count={request_count}, limit={limit}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
                headers={"Retry-After": str(max(1, retry_after))},
            )
        return True

    async def check_ws_rate_limit(
        self,
        user_id: str,
        limit: int = 30,
        window_seconds: int = 60,
    ) -> bool:
        """Rate limit check specifically for WebSocket messages."""
        key = f"ratelimit:ws:{user_id}"
        return await self.check_rate_limit(key, limit, window_seconds)
