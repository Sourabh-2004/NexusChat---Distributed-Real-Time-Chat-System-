"""
Redis Pub/Sub implementation of the MessageBroker interface.

Provides cross-instance message distribution for the chat system.
Includes automatic reconnection, dead letter handling, and error resilience.
"""

import json
import asyncio
import logging
import time
from typing import Callable, Dict, Set

import redis.asyncio as aioredis
from app.messaging.base import MessageBroker
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RedisBroker(MessageBroker):
    """
    Redis Pub/Sub message broker for distributed message delivery.
    
    Architecture:
    - Uses a dedicated Redis connection for Pub/Sub (separate from cache)
    - Background listener task processes incoming messages
    - Automatic reconnection with exponential backoff on failures
    - Dead letter queue (Redis list) for failed message delivery
    """

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._callbacks: Dict[str, Callable] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False
        self._reconnect_delay = 1  # Initial reconnect delay in seconds
        self._max_reconnect_delay = 30

    async def connect(self) -> None:
        """Establish Redis connection and start the Pub/Sub listener."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                retry_on_timeout=True,
            )
            self._pubsub = self._redis.pubsub()
            # Subscribe to a dummy channel to prevent pubsub.listen() from busy-looping
            # when there are zero subscriptions, which starves the asyncio event loop.
            await self._pubsub.subscribe("system:dummy")
            
            self._running = True
            self._listener_task = asyncio.create_task(self._listen())
            self._reconnect_delay = 1  # Reset on successful connect
            logger.info("Redis Pub/Sub broker connected")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Gracefully shutdown the broker."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("Redis Pub/Sub broker disconnected")

    async def publish(self, channel: str, message: dict) -> None:
        """
        Publish a message to a Redis Pub/Sub channel.
        
        Includes retry logic for transient Redis failures.
        """
        if not self._redis:
            logger.error("Cannot publish: Redis not connected")
            return

        payload = json.dumps(message)
        retries = 3

        for attempt in range(retries):
            try:
                await self._redis.publish(channel, payload)
                logger.debug(f"Published to {channel}: {payload[:100]}...")
                return
            except Exception as e:
                logger.warning(
                    f"Publish attempt {attempt + 1}/{retries} failed for {channel}: {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    # All retries exhausted — send to dead letter queue
                    await self.publish_dead_letter(channel, message, str(e))

    async def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to a channel with a message handler callback."""
        if not self._pubsub:
            logger.error("Cannot subscribe: Pub/Sub not initialized")
            return

        self._callbacks[channel] = callback
        await self._pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        if not self._pubsub:
            return

        self._callbacks.pop(channel, None)
        await self._pubsub.unsubscribe(channel)
        logger.info(f"Unsubscribed from channel: {channel}")

    async def publish_dead_letter(
        self, original_channel: str, message: dict, error: str
    ) -> None:
        """
        Push a failed message to the dead letter queue (Redis list).
        
        Dead letters can be inspected and replayed manually for debugging.
        """
        if not self._redis:
            logger.error("Cannot write to DLQ: Redis not connected")
            return

        dead_letter = {
            "original_channel": original_channel,
            "message": message,
            "error": error,
            "timestamp": time.time(),
        }
        try:
            await self._redis.lpush("dead_letter_queue", json.dumps(dead_letter))
            # Keep DLQ bounded
            await self._redis.ltrim("dead_letter_queue", 0, 9999)
            logger.warning(f"Message sent to DLQ: channel={original_channel}, error={error}")
        except Exception as e:
            logger.error(f"Failed to write to DLQ: {e}")

    async def _listen(self) -> None:
        """
        Background listener that processes incoming Pub/Sub messages.
        
        Runs continuously, dispatching messages to registered callbacks.
        Handles reconnection on connection failures.
        """
        while self._running:
            try:
                async for message in self._pubsub.listen():
                    if not self._running:
                        break

                    if message["type"] == "message":
                        channel = message["channel"]
                        if isinstance(channel, bytes):
                            channel = channel.decode()

                        callback = self._callbacks.get(channel)
                        if callback:
                            try:
                                data = json.loads(message["data"])
                                await callback(channel, data)
                            except json.JSONDecodeError:
                                logger.error(f"Invalid JSON on channel {channel}")
                            except Exception as e:
                                logger.error(
                                    f"Callback error on channel {channel}: {e}"
                                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"Pub/Sub listener error: {e}")
                # Exponential backoff reconnection
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )
                try:
                    await self._reconnect()
                except Exception as re:
                    logger.error(f"Reconnection failed: {re}")

    async def _reconnect(self) -> None:
        """Attempt to reconnect to Redis and re-subscribe to all channels."""
        logger.info("Attempting Redis Pub/Sub reconnection...")
        self._redis = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            retry_on_timeout=True,
        )
        self._pubsub = self._redis.pubsub()

        # Re-subscribe to all channels
        for channel in self._callbacks:
            await self._pubsub.subscribe(channel)
            logger.info(f"Re-subscribed to channel: {channel}")

        self._reconnect_delay = 1  # Reset delay on success
        logger.info("Redis Pub/Sub reconnected successfully")
