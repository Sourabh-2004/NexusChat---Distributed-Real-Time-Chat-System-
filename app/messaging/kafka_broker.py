"""
Apache Kafka message broker stub implementing the MessageBroker interface.

This is a design-ready abstraction that demonstrates how the system
can be extended to use Kafka for higher-throughput message processing.
The interface is identical to RedisBroker, enabling a drop-in swap.

To activate:
1. Install aiokafka: pip install aiokafka
2. Add a Kafka container to docker-compose.yml
3. Set BROKER_TYPE=kafka in environment
"""

import logging
from typing import Callable, Dict

from app.messaging.base import MessageBroker

logger = logging.getLogger(__name__)


class KafkaBroker(MessageBroker):
    """
    Apache Kafka implementation of MessageBroker.
    
    Design notes for production implementation:
    - Use aiokafka for async producer/consumer
    - Each room maps to a Kafka topic partition (consistent hashing)
    - Consumer group per FastAPI instance for load distribution
    - Message ordering guaranteed per partition (per room)
    - At-least-once delivery with idempotency keys
    - Schema registry for message format validation
    
    Trade-offs vs Redis Pub/Sub:
    + Higher throughput (100K+ msg/sec)
    + Message durability and replay capability
    + Better partition-based scaling
    - Higher latency (~10ms vs ~1ms)
    - More complex operational overhead
    - Requires Zookeeper/KRaft cluster management
    """

    def __init__(self, bootstrap_servers: str = "kafka:9092"):
        self.bootstrap_servers = bootstrap_servers
        self._callbacks: Dict[str, Callable] = {}
        logger.info(
            "KafkaBroker initialized (stub). "
            "Install aiokafka and configure Kafka to enable."
        )

    async def connect(self) -> None:
        """
        Production implementation would:
        - Create AIOKafkaProducer with acks='all' for durability
        - Create AIOKafkaConsumer with consumer group
        - Start producer and consumer
        """
        logger.warning(
            "KafkaBroker.connect() called but Kafka is not configured. "
            "Using Redis Pub/Sub as fallback."
        )
        raise NotImplementedError(
            "Kafka broker is not yet implemented. "
            "Use BROKER_TYPE=redis (default) or implement with aiokafka."
        )

    async def disconnect(self) -> None:
        """Stop Kafka producer and consumer."""
        logger.info("KafkaBroker disconnected (stub)")

    async def publish(self, channel: str, message: dict) -> None:
        """
        Production implementation would:
        - Serialize message to bytes (JSON/Avro/Protobuf)
        - Use consistent hashing on room_id for partition key
        - Send via AIOKafkaProducer with retries
        """
        raise NotImplementedError("Kafka publish not implemented")

    async def subscribe(self, channel: str, callback: Callable) -> None:
        """
        Production implementation would:
        - Map channel to Kafka topic
        - Assign partition based on room_id
        - Register callback for consumer message handler
        """
        self._callbacks[channel] = callback
        raise NotImplementedError("Kafka subscribe not implemented")

    async def unsubscribe(self, channel: str) -> None:
        """Remove callback and unsubscribe from topic."""
        self._callbacks.pop(channel, None)

    async def publish_dead_letter(
        self, original_channel: str, message: dict, error: str
    ) -> None:
        """
        Production implementation would:
        - Publish to a dedicated dead letter topic
        - Include original topic, partition, offset metadata
        - Configure DLT retention policy
        """
        logger.error(
            f"Dead letter (Kafka stub): channel={original_channel}, error={error}"
        )
