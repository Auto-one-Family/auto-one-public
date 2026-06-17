"""
In-memory MQTT test client used for offline publish/subscribe validation.

Features:
- publish(topic, payload, qos=0, retain=False)
- subscribe(topic, callback=None)
- wait_for_message(topic, timeout=5)
- clear() for test isolation

This avoids external broker dependencies while keeping the API surface
compatible with a real MQTT client. Useful for pre-flight tests when no ESP
hardware or broker is available.
"""

import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional


class InMemoryMQTTTestClient:
    """Lightweight, synchronous MQTT test double."""

    def __init__(self):
        self._messages: List[Dict[str, Any]] = []
        self._subscribers: defaultdict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(
            list
        )

    async def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> None:
        """Store message and notify subscribers (async-compatible)."""
        message = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
            "timestamp": time.time(),
        }
        self._messages.append(message)

        for callback in self._subscribers.get(topic, []):
            callback(message)

    def subscribe(
        self, topic: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> None:
        """Register a callback for a topic."""
        cb = callback or (lambda _msg: None)
        self._subscribers[topic].append(cb)

    def wait_for_message(self, topic: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Block until a message for topic arrives or timeout expires.

        Raises:
            TimeoutError: if no message is received within timeout.
        """
        deadline = time.time() + timeout
        last_checked = 0

        while time.time() < deadline:
            # Scan any new messages since last check
            for idx in range(last_checked, len(self._messages)):
                message = self._messages[idx]
                if message["topic"] == topic:
                    return message
            last_checked = len(self._messages)
            time.sleep(0.01)

        raise TimeoutError(f"No message for topic '{topic}' within {timeout}s")

    def clear(self) -> None:
        """Clear stored messages (test isolation)."""
        self._messages.clear()

    def message_count(self, topic: Optional[str] = None) -> int:
        """Return number of stored messages, optionally filtered by topic."""
        if topic is None:
            return len(self._messages)
        return sum(1 for msg in self._messages if msg["topic"] == topic)
