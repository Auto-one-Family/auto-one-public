"""
MQTT Offline Buffer

Provides graceful degradation when MQTT broker is unavailable:
- Buffers messages when circuit breaker is OPEN
- Flushes buffer on reconnect
- Re-queues failed messages
- Thread-safe with asyncio.Lock

Reference: ESP32 Offline Buffer pattern for reliable message delivery
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class BufferedMessage:
    """A message waiting to be sent."""

    topic: str
    payload: str  # JSON string
    qos: int
    retain: bool
    timestamp: float = field(default_factory=time.time)
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "payload": self.payload,
            "qos": self.qos,
            "retain": self.retain,
            "timestamp": self.timestamp,
            "attempts": self.attempts,
            "age_seconds": time.time() - self.timestamp,
        }


class MQTTOfflineBuffer:
    """
    Buffer for MQTT messages when broker is unavailable.

    Features:
    - Bounded deque to prevent memory exhaustion
    - Thread-safe with asyncio.Lock
    - Oldest messages dropped when buffer is full
    - Re-queue failed messages on flush
    - Metrics for monitoring

    Usage:
        buffer = MQTTOfflineBuffer(max_size=1000)

        # When circuit breaker is OPEN
        await buffer.add("topic", '{"data": 1}', qos=1)

        # When connection restored
        flushed = await buffer.flush(mqtt_client)
        print(f"Flushed {flushed} messages")
    """

    def __init__(
        self,
        max_size: Optional[int] = None,
        flush_batch_size: Optional[int] = None,
    ):
        """
        Initialize offline buffer.

        Args:
            max_size: Maximum messages to buffer (default from settings)
            flush_batch_size: Messages to flush per batch (default from settings)
        """
        settings = get_settings()

        self.max_size = max_size or settings.resilience.offline_buffer_max_size
        self.flush_batch_size = (
            flush_batch_size or settings.resilience.offline_buffer_flush_batch_size
        )

        self._buffer: Deque[BufferedMessage] = deque(maxlen=self.max_size)
        self._lock = asyncio.Lock()

        # Metrics
        self._messages_added = 0
        self._messages_dropped = 0  # Due to buffer full
        self._messages_flushed = 0
        self._messages_failed = 0
        self._last_flush_time: Optional[float] = None

        logger.info(
            f"[resilience] MQTTOfflineBuffer initialized: "
            f"max_size={self.max_size}, batch_size={self.flush_batch_size}"
        )

    @property
    def size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)

    @property
    def is_full(self) -> bool:
        """Check if buffer is full."""
        return len(self._buffer) >= self.max_size

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self._buffer) == 0

    async def add(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """
        Add a message to the buffer.

        If buffer is full, oldest messages are dropped (deque maxlen behavior).

        Args:
            topic: MQTT topic
            payload: JSON string payload
            qos: QoS level
            retain: Retain flag

        Returns:
            True if added successfully
        """
        async with self._lock:
            was_full = len(self._buffer) >= self.max_size

            message = BufferedMessage(
                topic=topic,
                payload=payload,
                qos=qos,
                retain=retain,
            )

            self._buffer.append(message)
            self._messages_added += 1

            if was_full:
                self._messages_dropped += 1
                logger.warning(
                    f"[resilience] OfflineBuffer: Buffer full, oldest message dropped. "
                    f"Size: {len(self._buffer)}/{self.max_size}"
                )

            if self._messages_added % 100 == 0:
                logger.info(f"[resilience] OfflineBuffer: {len(self._buffer)} messages buffered")

            return True

    async def add_front(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
        attempts: int = 0,
    ) -> None:
        """
        Add a message to the front of the buffer (for re-queuing failed messages).

        Args:
            topic: MQTT topic
            payload: JSON string payload
            qos: QoS level
            retain: Retain flag
            attempts: Number of previous attempts
        """
        async with self._lock:
            message = BufferedMessage(
                topic=topic,
                payload=payload,
                qos=qos,
                retain=retain,
                attempts=attempts + 1,
            )
            self._buffer.appendleft(message)

    async def flush(self, mqtt_client) -> int:
        """
        Flush buffer by sending messages to MQTT broker.

        Processes messages in batches to avoid overwhelming the broker.
        Failed messages are re-queued at the front of the buffer.

        Args:
            mqtt_client: MQTTClient instance to use for publishing

        Returns:
            Number of messages successfully flushed
        """
        if self.is_empty:
            return 0

        flushed_count = 0
        failed_messages: List[BufferedMessage] = []

        async with self._lock:
            batch_count = 0

            while self._buffer and batch_count < self.flush_batch_size:
                message = self._buffer.popleft()

                try:
                    success = mqtt_client.publish(
                        message.topic,
                        message.payload,
                        message.qos,
                        message.retain,
                    )

                    if success:
                        flushed_count += 1
                        self._messages_flushed += 1
                    else:
                        # Re-queue failed message
                        if message.attempts < 3:  # Max 3 attempts
                            message.attempts += 1
                            failed_messages.append(message)
                        else:
                            self._messages_failed += 1
                            logger.warning(
                                f"[resilience] OfflineBuffer: Dropping message after 3 attempts: "
                                f"{message.topic}"
                            )

                except Exception as e:
                    self._messages_failed += 1
                    logger.error(
                        f"[resilience] OfflineBuffer: Flush error for {message.topic}: {e}"
                    )

                    # Re-queue on error (if not too many attempts)
                    if message.attempts < 3:
                        message.attempts += 1
                        failed_messages.append(message)

                batch_count += 1

            # Re-queue failed messages at front
            for msg in reversed(failed_messages):
                self._buffer.appendleft(msg)

            self._last_flush_time = time.time()

        if flushed_count > 0:
            remaining = len(self._buffer)
            logger.info(
                f"[resilience] OfflineBuffer: Flushed {flushed_count} messages. "
                f"Remaining: {remaining}, Failed: {len(failed_messages)}"
            )

        return flushed_count

    async def flush_all(self, mqtt_client) -> int:
        """
        Flush entire buffer (all batches).

        Continues flushing until buffer is empty or all messages fail.

        Args:
            mqtt_client: MQTTClient instance

        Returns:
            Total number of messages successfully flushed
        """
        total_flushed = 0

        while not self.is_empty:
            flushed = await self.flush(mqtt_client)
            if flushed == 0:
                # No progress, stop to prevent infinite loop
                break
            total_flushed += flushed

            # Small delay between batches to prevent broker overload
            await asyncio.sleep(0.1)

        return total_flushed

    async def clear(self) -> int:
        """
        Clear all messages from buffer.

        Returns:
            Number of messages cleared
        """
        async with self._lock:
            count = len(self._buffer)
            self._buffer.clear()

            logger.warning(f"[resilience] OfflineBuffer: Cleared {count} messages")
            return count

    async def peek(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Peek at messages in buffer without removing them.

        Args:
            count: Number of messages to peek

        Returns:
            List of message dictionaries
        """
        async with self._lock:
            messages = []
            for i, msg in enumerate(self._buffer):
                if i >= count:
                    break
                messages.append(msg.to_dict())
            return messages

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get buffer metrics.

        Returns:
            Dictionary with buffer statistics
        """
        oldest_age = 0.0
        if self._buffer:
            oldest_age = time.time() - self._buffer[0].timestamp

        return {
            "current_size": len(self._buffer),
            "max_size": self.max_size,
            "utilization_percent": (
                (len(self._buffer) / self.max_size) * 100 if self.max_size > 0 else 0
            ),
            "messages_added": self._messages_added,
            "messages_dropped": self._messages_dropped,
            "messages_flushed": self._messages_flushed,
            "messages_failed": self._messages_failed,
            "oldest_message_age_seconds": oldest_age,
            "last_flush_time": self._last_flush_time,
        }

    def __repr__(self) -> str:
        return (
            f"MQTTOfflineBuffer(size={len(self._buffer)}/{self.max_size}, "
            f"flushed={self._messages_flushed}, dropped={self._messages_dropped})"
        )
