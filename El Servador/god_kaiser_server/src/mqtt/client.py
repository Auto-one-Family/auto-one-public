"""
MQTT Client Wrapper (Singleton)

Provides singleton MQTT client with:
- Paho-MQTT integration
- TLS/SSL support
- Auto-reconnect with exponential backoff
- Connection state management
- Callback handling
- Circuit Breaker integration for resilience
- Offline buffer for graceful degradation
"""

import asyncio
import json
import logging
import os
import ssl
import threading
import time
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from ..core.config import get_settings
from ..core.logging_config import get_logger
from ..core.resilience import (
    CircuitBreaker,
    ResilienceRegistry,
)
from .topics import TopicBuilder


class _MQTTDisconnectRateLimiter(logging.Filter):
    """
    Logging filter that rate-limits MQTT disconnect warnings.

    Allows only one "MQTT broker unavailable" message per 60 seconds.
    This prevents log spam when the broker is down.
    """

    def __init__(self, interval_seconds: float = 60.0):
        super().__init__()
        self._interval = interval_seconds
        self._last_log_time: float = 0.0
        self._suppressed_count: int = 0
        self._lock = threading.Lock()
        self._marker = "MQTT broker unavailable"

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records, rate-limiting MQTT disconnect warnings.

        Returns True if the record should be logged.
        """
        # Only filter warnings containing our marker
        if self._marker not in str(record.msg):
            return True

        with self._lock:
            current_time = time.time()
            elapsed = current_time - self._last_log_time

            if elapsed >= self._interval:
                # Time to log - include suppressed count if any
                if self._suppressed_count > 0:
                    record.msg = (
                        f"{record.msg} [{self._suppressed_count} identical messages suppressed]"
                    )
                self._last_log_time = current_time
                self._suppressed_count = 0
                return True
            else:
                # Suppress this message
                self._suppressed_count += 1
                return False


# Create module-level rate limiter (survives instance recreation)
_disconnect_rate_limiter = _MQTTDisconnectRateLimiter(interval_seconds=60.0)

logger = get_logger(__name__)
# Add the rate limiter filter to the logger
logger.addFilter(_disconnect_rate_limiter)


class MQTTClient:
    """
    Singleton MQTT Client wrapper around paho-mqtt.

    Features:
    - TLS/SSL support
    - Auto-reconnect with exponential backoff
    - Connection state tracking
    - Callback registry
    - Thread-safe operations

    Usage:
        client = MQTTClient.get_instance()
        await client.connect()
        await client.subscribe("topic/pattern", callback_func)
        await client.publish("topic", payload, qos=1)
    """

    _instance: Optional["MQTTClient"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize MQTT client (called only once due to singleton)."""
        if self._initialized:
            return

        self.settings = get_settings()
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.reconnect_delay = 1  # seconds
        self.max_reconnect_delay = 60  # seconds
        self.on_message_callback: Optional[Callable] = None
        self._subscriber: Optional[object] = (
            None  # Subscriber instance for re-subscription on reconnect
        )

        # Rate-limiting for disconnect warnings (thread-safe)
        self._disconnect_lock = threading.Lock()
        self._last_disconnect_log_time: float = 0.0
        self._disconnect_suppressed_count: int = 0
        self._DISCONNECT_LOG_INTERVAL: float = 60.0  # Log at most once per minute

        # Circuit Breaker for MQTT operations
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._init_circuit_breaker()

        # Offline buffer for graceful degradation
        self._offline_buffer = None
        self._init_offline_buffer()

        # Event loop reference for thread-safe async scheduling
        # Captured during connect() which runs from the main async context
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        self._initialized = True
        logger.info("MQTTClient singleton initialized (with resilience patterns)")

    def _init_circuit_breaker(self) -> None:
        """Initialize and register the MQTT circuit breaker."""
        try:
            resilience_settings = self.settings.resilience

            self._circuit_breaker = CircuitBreaker(
                name="mqtt",
                failure_threshold=resilience_settings.circuit_breaker_mqtt_failure_threshold,
                recovery_timeout=float(resilience_settings.circuit_breaker_mqtt_recovery_timeout),
                half_open_timeout=float(resilience_settings.circuit_breaker_mqtt_half_open_timeout),
            )

            # Register in global registry
            registry = ResilienceRegistry.get_instance()
            registry.register_circuit_breaker("mqtt", self._circuit_breaker)

            logger.info(
                f"[resilience] MQTT CircuitBreaker registered: "
                f"threshold={resilience_settings.circuit_breaker_mqtt_failure_threshold}, "
                f"recovery={resilience_settings.circuit_breaker_mqtt_recovery_timeout}s"
            )
        except Exception as e:
            logger.warning(f"[resilience] Failed to initialize MQTT circuit breaker: {e}")
            self._circuit_breaker = None

    def _init_offline_buffer(self) -> None:
        """Initialize the offline buffer for graceful degradation."""
        try:
            from .offline_buffer import MQTTOfflineBuffer

            self._offline_buffer = MQTTOfflineBuffer()
            logger.info("[resilience] MQTT OfflineBuffer initialized")
        except Exception as e:
            logger.warning(f"[resilience] Failed to initialize offline buffer: {e}")
            self._offline_buffer = None

    @classmethod
    def get_instance(cls) -> "MQTTClient":
        """
        Get singleton instance.

        Returns:
            MQTTClient instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def connect(
        self,
        broker: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: Optional[bool] = None,
    ) -> bool:
        """
        Connect to MQTT broker.

        Args:
            broker: MQTT broker hostname (defaults to settings)
            port: MQTT broker port (defaults to settings)
            username: MQTT username (defaults to settings)
            password: MQTT password (defaults to settings)
            use_tls: Enable TLS (defaults to settings)

        Returns:
            True if connection successful, False otherwise
        """
        # Capture the event loop for thread-safe async scheduling in publish()
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                self._event_loop = asyncio.get_event_loop()
            except RuntimeError:
                self._event_loop = None
                logger.warning(
                    "No event loop available - offline buffering may not work from background threads"
                )

        # Use settings if not provided
        broker = broker or self.settings.mqtt.broker_host
        port = port or self.settings.mqtt.broker_port
        username = username or self.settings.mqtt.username
        password = password or self.settings.mqtt.password
        use_tls = use_tls if use_tls is not None else self.settings.mqtt.use_tls

        try:
            from ..core.metrics import increment_connect_attempt

            increment_connect_attempt()
        except Exception:
            pass

        try:
            # Create paho-mqtt client with UNIQUE client ID
            # BUG V FIX: Append process ID to prevent multiple instances with same ID
            # MQTT only allows ONE connection per client_id - duplicate IDs cause reconnect loops
            base_id = self.settings.mqtt.client_id or "god_kaiser"
            client_id = f"{base_id}_{os.getpid()}"
            logger.info(f"MQTT Client ID: {client_id} (PID-based for uniqueness)")

            self.client = mqtt.Client(
                client_id=client_id,
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
            # Prevent unbounded reconnect amplification under config-push bursts.
            self.client.max_queued_messages_set(50)

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.on_subscribe = self._on_subscribe
            self.client.on_publish = self._on_publish

            # Set username/password if provided
            if username and password:
                self.client.username_pw_set(username, password)
                logger.debug(f"MQTT credentials set for user: {username}")

            # Configure TLS if enabled
            if use_tls:
                self._configure_tls()

            # Set keepalive
            keepalive = self.settings.mqtt.keepalive

            # Configure auto-reconnect with exponential backoff
            # Min delay: 1s, Max delay: 60s
            self.client.reconnect_delay_set(min_delay=1, max_delay=60)
            logger.debug("Auto-reconnect configured: min=1s, max=60s (exponential backoff)")

            # LWT: Broker publishes this if server disconnects unexpectedly (SAFETY-P5)
            _server_status_topic = TopicBuilder.build_server_status_topic()
            self.client.will_set(
                topic=_server_status_topic,
                payload=json.dumps(
                    {
                        "status": "offline",
                        "timestamp": int(time.time()),
                        "reason": "unexpected_disconnect",
                    }
                ),
                qos=1,
                retain=True,
            )
            logger.debug("[SAFETY-P5] LWT configured: %s", _server_status_topic)

            # Connect to broker
            logger.info(f"Connecting to MQTT broker: {broker}:{port} (TLS: {use_tls})")
            self.client.connect(broker, port, keepalive)

            # Start network loop (non-blocking)
            self.client.loop_start()

            # Wait for connection (timeout: 10 seconds)
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if self.connected:
                logger.info("MQTT client connected successfully")
                return True
            else:
                logger.error("MQTT connection timeout")
                return False

        except Exception as e:
            logger.error(f"MQTT connection failed: {e}", exc_info=True)
            return False

    def _configure_tls(self):
        """Configure TLS/SSL for secure connection."""
        try:
            ca_cert = self.settings.mqtt.ca_cert_path
            client_cert = self.settings.mqtt.client_cert_path
            client_key = self.settings.mqtt.client_key_path

            if ca_cert:
                # Server certificate verification
                self.client.tls_set(
                    ca_certs=ca_cert,
                    certfile=client_cert,
                    keyfile=client_key,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLSv1_2,
                )
                logger.info("TLS configured with CA certificate verification")
            else:
                # TLS without certificate verification (insecure!)
                self.client.tls_set(
                    cert_reqs=ssl.CERT_NONE,
                    tls_version=ssl.PROTOCOL_TLSv1_2,
                )
                self.client.tls_insecure_set(True)
                logger.warning("TLS configured WITHOUT certificate verification (insecure)")

        except Exception as e:
            logger.error(f"TLS configuration failed: {e}", exc_info=True)
            raise

    def disconnect(self) -> bool:
        """
        Disconnect from MQTT broker gracefully.

        Returns:
            True if disconnect successful
        """
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
                self.connected = False
                logger.info("MQTT client disconnected")
                return True
            return False
        except Exception as e:
            logger.error(f"MQTT disconnect failed: {e}", exc_info=True)
            return False

    def subscribe(
        self,
        topic: str,
        qos: int = 1,
        callback: Optional[Callable] = None,
    ) -> bool:
        """
        Subscribe to MQTT topic.

        Args:
            topic: MQTT topic (supports wildcards: +, #)
            qos: QoS level (0, 1, or 2)
            callback: Message callback function (optional, uses global if None)

        Returns:
            True if subscription successful
        """
        if not self.client or not self.connected:
            logger.error("Cannot subscribe: MQTT client not connected")
            return False

        try:
            result, mid = self.client.subscribe(topic, qos)

            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Subscribed to topic: {topic} (QoS {qos})")
                return True
            else:
                logger.error(f"Subscribe failed for topic {topic}: {result}")
                return False

        except Exception as e:
            logger.error(f"Subscribe exception for topic {topic}: {e}", exc_info=True)
            return False

    def _schedule_buffer_add(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        """
        Thread-safe scheduling of offline buffer add.

        publish() can be called from paho-mqtt's network thread where there
        is no running asyncio event loop. Using asyncio.create_task() from
        that thread would raise RuntimeError or silently fail.
        Instead, use run_coroutine_threadsafe() with the captured event loop.
        """
        if not self._offline_buffer:
            return

        try:
            # Try current thread's running loop first (works when called from async context)
            loop = asyncio.get_running_loop()
            loop.create_task(self._offline_buffer.add(topic, payload, qos, retain))
        except RuntimeError:
            # No running loop in this thread (paho callback thread) - use stored loop
            if self._event_loop and not self._event_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._offline_buffer.add(topic, payload, qos, retain),
                    self._event_loop,
                )
            else:
                logger.warning(f"Cannot buffer message for {topic}: no event loop available")

    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """
        Publish message to MQTT topic with circuit breaker protection.

        Args:
            topic: MQTT topic
            payload: Message payload (JSON string)
            qos: QoS level (0, 1, or 2)
            retain: Retain flag

        Returns:
            True if publish successful, False if failed or circuit breaker rejected

        Note:
            If circuit breaker is OPEN, message is buffered for later delivery
        """
        # Circuit Breaker check
        if self._circuit_breaker and not self._circuit_breaker.allow_request():
            logger.warning(f"[resilience] MQTT publish blocked by Circuit Breaker: {topic}")
            # Buffer the message for later
            self._schedule_buffer_add(topic, payload, qos, retain)
            logger.debug(f"[resilience] Message buffered: {topic}")
            return False

        if not self.client or not self.connected:
            logger.error("Cannot publish: MQTT client not connected")
            # Record failure for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            # Buffer the message
            self._schedule_buffer_add(topic, payload, qos, retain)
            return False

        try:
            result = self.client.publish(topic, payload, qos, retain)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published to {topic} (QoS {qos}): {payload[:100]}...")
                # Record success for circuit breaker
                if self._circuit_breaker:
                    self._circuit_breaker.record_success()
                # Prometheus counter
                from ..core.metrics import increment_mqtt_published

                increment_mqtt_published()
                return True
            else:
                logger.error(f"Publish failed for topic {topic}: {result.rc}")
                # Record failure for circuit breaker
                if self._circuit_breaker:
                    self._circuit_breaker.record_failure()
                from ..core.metrics import increment_mqtt_publish_error

                increment_mqtt_publish_error()
                return False

        except Exception as e:
            logger.error(f"Publish exception for topic {topic}: {e}", exc_info=True)
            # Record failure for circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            from ..core.metrics import increment_mqtt_publish_error

            increment_mqtt_publish_error()
            return False

    def clear_retained_message(self, topic: str) -> bool:
        """
        Clear a retained MQTT message by publishing an empty payload with retain=True.

        The broker removes the retained message when it receives an empty retain publish.
        Used to clean up stale LWT or emergency retained messages.

        Args:
            topic: MQTT topic whose retained message should be deleted (must be non-empty)

        Returns:
            True if publish succeeded, False on empty topic or publish failure
        """
        if not topic:
            return False

        if not self.client or not self.connected:
            logger.error("Cannot clear retained message: MQTT client not connected")
            return False

        try:
            result = self.client.publish(topic, "", 0, True)
            if result.rc == 0:
                from ..core.metrics import increment_mqtt_published

                increment_mqtt_published()
                logger.debug(f"Cleared retained message on topic: {topic}")
                return True
            logger.error(f"Failed to clear retained message on {topic}: rc={result.rc}")
            return False
        except Exception as e:
            logger.error(f"Exception clearing retained message on {topic}: {e}", exc_info=True)
            return False

    def set_on_message_callback(self, callback: Callable):
        """
        Set global message callback.

        Args:
            callback: ``callback(topic: str, payload: str, retain: bool = False)``
                — ``retain`` is the Paho RETAIN flag on delivery (MQTT 3.1.1).
        """
        self.on_message_callback = callback
        logger.debug("Global message callback registered")

    def set_subscriber(self, subscriber: object):
        """
        Set Subscriber instance for auto re-subscription on reconnect.

        Args:
            subscriber: Subscriber instance with subscribe_all() method
        """
        self._subscriber = subscriber
        logger.debug("Subscriber instance registered for auto re-subscription")

    def is_connected(self) -> bool:
        """
        Check if client is connected.

        Returns:
            True if connected
        """
        return self.connected

    # Internal callbacks
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connection is established."""
        if rc == 0:
            self.connected = True
            self.reconnect_delay = 1  # Reset reconnect delay
            # Reset rate-limiting on successful connect
            with self._disconnect_lock:
                self._last_disconnect_log_time = 0.0
                self._disconnect_suppressed_count = 0
            logger.info(f"MQTT connected with result code: {rc}")

            # Reset circuit breaker on successful connection
            if self._circuit_breaker:
                self._circuit_breaker.reset()
                logger.info("[resilience] MQTT CircuitBreaker reset on connect")

            # SAFETY-P5: Publish online status (overwrites any retained LWT)
            try:
                server_status_topic = TopicBuilder.build_server_status_topic()
                self.client.publish(
                    server_status_topic,
                    json.dumps(
                        {
                            "status": "online",
                            "timestamp": int(time.time()),
                        }
                    ),
                    qos=1,
                    retain=True,
                )
                logger.info("[SAFETY-P5] Server status published: online")
            except Exception as _e:
                logger.warning("[SAFETY-P5] Failed to publish online status: %s", _e)

            # Auto re-subscribe to all topics if this is a reconnection
            if self._subscriber and hasattr(self._subscriber, "subscribe_all"):
                logger.info("Reconnected to MQTT broker - re-subscribing to all topics...")
                try:
                    self._subscriber.subscribe_all()
                    logger.info("Re-subscription complete")
                except Exception as e:
                    logger.error(f"Failed to re-subscribe after reconnect: {e}", exc_info=True)

            # Flush offline buffer on reconnect (thread-safe)
            if self._offline_buffer and not self._offline_buffer.is_empty:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._flush_offline_buffer())
                except RuntimeError:
                    if self._event_loop and not self._event_loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            self._flush_offline_buffer(), self._event_loop
                        )
                    else:
                        logger.warning("Cannot flush offline buffer: no event loop available")
        else:
            self.connected = False
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized",
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            logger.error(f"MQTT connection failed: {error_msg}")

    async def _flush_offline_buffer(self) -> None:
        """Flush offline buffer after reconnection."""
        if not self._offline_buffer:
            return

        try:
            count = await self._offline_buffer.flush_all(self)
            if count > 0:
                logger.info(f"[resilience] Flushed {count} messages from offline buffer")
        except Exception as e:
            logger.error(f"[resilience] Failed to flush offline buffer: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """
        Callback when disconnected from MQTT broker.

        Implements time-based rate-limiting for disconnect logs to prevent log spam
        when broker is unavailable (logs max once per minute).

        Args:
            client: MQTT client instance
            userdata: User data
            rc: Disconnect reason code
        """
        self.connected = False

        # Disconnect reason codes
        disconnect_reasons = {
            0: "Clean disconnect",
            1: "Connection refused - incorrect protocol version",
            2: "Connection refused - invalid client identifier",
            3: "Connection refused - server unavailable",
            4: "Connection refused - bad username or password",
            5: "Connection refused - not authorized",
            7: "Connection refused - broker unavailable",
        }

        reason = disconnect_reasons.get(rc, f"Unknown reason (code: {rc})")
        try:
            from ..core.metrics import increment_disconnect_reason

            increment_disconnect_reason(reason if rc != 0 else "clean_disconnect")
        except Exception:
            pass

        if rc == 0:
            logger.info(f"MQTT client disconnected: {reason}")
            with self._disconnect_lock:
                self._last_disconnect_log_time = 0.0
                self._disconnect_suppressed_count = 0
        else:
            # Thread-safe time-based rate-limiting to prevent log spam
            with self._disconnect_lock:
                current_time = time.time()
                time_since_last = current_time - self._last_disconnect_log_time

                if time_since_last >= self._DISCONNECT_LOG_INTERVAL:
                    suppressed = self._disconnect_suppressed_count
                    self._last_disconnect_log_time = current_time
                    self._disconnect_suppressed_count = 0
                    should_log = True
                else:
                    self._disconnect_suppressed_count += 1
                    should_log = False
                    suppressed = 0

            if should_log:
                if suppressed > 0:
                    logger.warning(
                        f"MQTT broker unavailable: {reason}. "
                        f"Auto-reconnect active (exponential backoff, max 60s). "
                        f"[{suppressed} identical messages suppressed]"
                    )
                else:
                    logger.warning(
                        f"MQTT broker unavailable: {reason}. "
                        "Auto-reconnect active (exponential backoff, max 60s)."
                    )
            # Else: silent - no log output to prevent spam

    def _on_message(self, client, userdata, msg):
        """Callback when message is received."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            logger.debug(f"Message received on {topic}: {payload[:100]}...")

            # Prometheus counter
            from ..core.metrics import increment_mqtt_received

            increment_mqtt_received()

            # Call global callback if registered (retain=True = broker replay of a
            # retained publication, e.g. stale LWT after server subscribe — see AUT-341)
            if self.on_message_callback:
                retain_flag = bool(getattr(msg, "retain", False))
                self.on_message_callback(topic, payload, retain_flag)
            else:
                logger.warning(f"No message callback registered for topic: {topic}")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            from ..core.metrics import increment_mqtt_receive_error

            increment_mqtt_receive_error()

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback when subscription is confirmed."""
        logger.debug(f"Subscription confirmed (mid={mid}, QoS={granted_qos})")

    def _on_publish(self, client, userdata, mid):
        """Callback when message is published."""
        logger.debug(f"Message published (mid={mid})")

    # Resilience-related methods
    def get_circuit_breaker(self) -> Optional[CircuitBreaker]:
        """Get the MQTT circuit breaker instance."""
        return self._circuit_breaker

    def get_offline_buffer_metrics(self) -> dict:
        """Get offline buffer metrics."""
        if self._offline_buffer:
            return self._offline_buffer.get_metrics()
        return {"enabled": False}

    def get_resilience_status(self) -> dict:
        """
        Get combined resilience status for MQTT client.

        Returns:
            Dictionary with circuit breaker and buffer status
        """
        status = {
            "connected": self.connected,
        }

        if self._circuit_breaker:
            status["circuit_breaker"] = self._circuit_breaker.get_metrics()
        else:
            status["circuit_breaker"] = {"enabled": False}

        if self._offline_buffer:
            status["offline_buffer"] = self._offline_buffer.get_metrics()
        else:
            status["offline_buffer"] = {"enabled": False}

        return status
