"""
Unit Tests: MQTT Offline Buffer

Tests für MQTT Offline Buffer gemäß Paket C.
"""

import asyncio
import pytest
import time

from src.mqtt.offline_buffer import MQTTOfflineBuffer


class TestOfflineBufferBasic:
    """Basic offline buffer functionality."""

    @pytest.mark.asyncio
    async def test_buffer_initialization(self):
        """Test buffer initializes empty."""
        buffer = MQTTOfflineBuffer(max_size=100)

        assert buffer.size == 0
        assert buffer.is_empty is True
        assert buffer.is_full is False

    @pytest.mark.asyncio
    async def test_add_message(self):
        """Test adding message to buffer."""
        buffer = MQTTOfflineBuffer(max_size=10)

        success = await buffer.add("test/topic", '{"data": 1}', qos=1)

        assert success is True
        assert buffer.size == 1
        assert buffer.is_empty is False

    @pytest.mark.asyncio
    async def test_buffer_full_drops_oldest(self):
        """Test buffer drops oldest message when full."""
        buffer = MQTTOfflineBuffer(max_size=3)

        # Add 4 messages
        await buffer.add("topic1", '{"msg": 1}', qos=1)
        await buffer.add("topic2", '{"msg": 2}', qos=1)
        await buffer.add("topic3", '{"msg": 3}', qos=1)
        await buffer.add("topic4", '{"msg": 4}', qos=1)

        # Size should be capped at max_size
        assert buffer.size == 3

        # Check metrics
        metrics = buffer.get_metrics()
        assert metrics["messages_added"] == 4
        assert metrics["messages_dropped"] == 1


class TestOfflineBufferFlush:
    """Test buffer flush operations."""

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self):
        """Test flushing empty buffer."""
        buffer = MQTTOfflineBuffer(max_size=10)

        # Mock MQTT client
        class MockMQTTClient:
            def publish(self, topic, payload, qos, retain):
                return True

        client = MockMQTTClient()
        flushed = await buffer.flush(client)

        assert flushed == 0

    @pytest.mark.asyncio
    async def test_flush_successful(self):
        """Test successful buffer flush."""
        buffer = MQTTOfflineBuffer(max_size=10, flush_batch_size=5)

        # Add messages
        for i in range(3):
            await buffer.add(f"topic{i}", f'{{"msg": {i}}}', qos=1)

        # Mock MQTT client
        class MockMQTTClient:
            def __init__(self):
                self.published = []

            def publish(self, topic, payload, qos, retain):
                self.published.append(topic)
                return True

        client = MockMQTTClient()
        flushed = await buffer.flush(client)

        assert flushed == 3
        assert buffer.is_empty is True
        assert len(client.published) == 3

    @pytest.mark.asyncio
    async def test_flush_requeues_failed_messages(self):
        """Test failed messages are re-queued."""
        buffer = MQTTOfflineBuffer(max_size=10)

        await buffer.add("topic1", '{"msg": 1}', qos=1)
        await buffer.add("topic2", '{"msg": 2}', qos=1)

        # Mock client that fails second message
        class MockMQTTClient:
            def __init__(self):
                self.count = 0

            def publish(self, topic, payload, qos, retain):
                self.count += 1
                if self.count == 2:
                    return False  # Fail second message
                return True

        client = MockMQTTClient()
        flushed = await buffer.flush(client)

        assert flushed == 1  # Only first succeeded
        assert buffer.size == 1  # Second message re-queued

    @pytest.mark.asyncio
    async def test_flush_all(self):
        """Test flush_all processes entire buffer."""
        buffer = MQTTOfflineBuffer(max_size=100, flush_batch_size=5)

        # Add 12 messages (more than one batch)
        for i in range(12):
            await buffer.add(f"topic{i}", f'{{"msg": {i}}}', qos=1)

        # Mock client
        class MockMQTTClient:
            def __init__(self):
                self.published = []

            def publish(self, topic, payload, qos, retain):
                self.published.append(topic)
                return True

        client = MockMQTTClient()
        flushed = await buffer.flush_all(client)

        assert flushed == 12
        assert buffer.is_empty is True
        assert len(client.published) == 12

    @pytest.mark.asyncio
    async def test_flush_max_attempts(self):
        """Test messages dropped after max attempts."""
        buffer = MQTTOfflineBuffer(max_size=10)

        await buffer.add("topic1", '{"msg": 1}', qos=1)

        # Mock client that always fails
        class FailingMQTTClient:
            def publish(self, topic, payload, qos, retain):
                return False

        client = FailingMQTTClient()

        # Flush multiple times (should drop after 3 attempts)
        for _ in range(4):
            await buffer.flush(client)

        # Message should be dropped after 3 attempts
        metrics = buffer.get_metrics()
        assert metrics["messages_failed"] >= 1


class TestOfflineBufferMetrics:
    """Test buffer metrics collection."""

    @pytest.mark.asyncio
    async def test_metrics_track_operations(self):
        """Test metrics track all operations."""
        buffer = MQTTOfflineBuffer(max_size=5)

        # Add messages
        for i in range(7):  # Exceeds max_size
            await buffer.add(f"topic{i}", f'{{"msg": {i}}}', qos=1)

        metrics = buffer.get_metrics()

        assert metrics["current_size"] == 5
        assert metrics["max_size"] == 5
        assert metrics["messages_added"] == 7
        assert metrics["messages_dropped"] == 2
        assert metrics["utilization_percent"] == 100.0

    @pytest.mark.asyncio
    async def test_metrics_oldest_message_age(self):
        """Test metrics track oldest message age."""
        buffer = MQTTOfflineBuffer(max_size=10)

        await buffer.add("topic1", '{"msg": 1}', qos=1)
        await asyncio.sleep(0.15)

        metrics = buffer.get_metrics()
        assert metrics["oldest_message_age_seconds"] >= 0.1


class TestOfflineBufferPeek:
    """Test buffer peek operation."""

    @pytest.mark.asyncio
    async def test_peek_messages(self):
        """Test peeking at buffered messages."""
        buffer = MQTTOfflineBuffer(max_size=10)

        await buffer.add("topic1", '{"msg": 1}', qos=1)
        await buffer.add("topic2", '{"msg": 2}', qos=1)
        await buffer.add("topic3", '{"msg": 3}', qos=1)

        # Peek first 2 messages
        messages = await buffer.peek(count=2)

        assert len(messages) == 2
        assert messages[0]["topic"] == "topic1"
        assert messages[1]["topic"] == "topic2"

        # Buffer should still have all messages
        assert buffer.size == 3


class TestOfflineBufferClear:
    """Test buffer clear operation."""

    @pytest.mark.asyncio
    async def test_clear_buffer(self):
        """Test clearing all buffered messages."""
        buffer = MQTTOfflineBuffer(max_size=10)

        for i in range(5):
            await buffer.add(f"topic{i}", f'{{"msg": {i}}}', qos=1)

        assert buffer.size == 5

        cleared = await buffer.clear()

        assert cleared == 5
        assert buffer.size == 0
        assert buffer.is_empty is True
