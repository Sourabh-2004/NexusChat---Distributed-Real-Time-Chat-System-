"""
Abstract message broker interface.

This abstraction allows swapping the underlying message transport
(Redis Pub/Sub, Apache Kafka, RabbitMQ, etc.) without changing
business logic. All broker implementations must conform to this interface.
"""

from abc import ABC, abstractmethod
from typing import Callable, Any


class MessageBroker(ABC):
    """
    Abstract interface for a distributed message broker.
    
    Responsibilities:
    - Publish messages to named channels
    - Subscribe to channels with callback handlers
    - Handle connection lifecycle and reconnection
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close all connections and cleanup."""
        ...

    @abstractmethod
    async def publish(self, channel: str, message: dict) -> None:
        """
        Publish a message to a channel.
        
        Args:
            channel: Channel name (e.g., "room:{room_id}")
            message: JSON-serializable message dict
        """
        ...

    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable) -> None:
        """
        Subscribe to a channel with a callback handler.
        
        Args:
            channel: Channel name to subscribe to
            callback: Async function called with (channel, message) on each message
        """
        ...

    @abstractmethod
    async def unsubscribe(self, channel: str) -> None:
        """
        Unsubscribe from a channel.
        
        Args:
            channel: Channel name to unsubscribe from
        """
        ...

    @abstractmethod
    async def publish_dead_letter(self, original_channel: str, message: dict, error: str) -> None:
        """
        Send a failed message to the dead letter queue.
        
        Args:
            original_channel: The channel the message was intended for
            message: The failed message
            error: Error description
        """
        ...
