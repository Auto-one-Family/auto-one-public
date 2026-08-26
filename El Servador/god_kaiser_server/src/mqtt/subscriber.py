"""
MQTT Subscriber

Topic subscription management and message routing to handlers.

Features:
- Async handler support with thread-pool execution
- Pattern-based routing
- Error isolation (handler failures don't crash subscriber)
- Performance monitoring
"""

import asyncio
import inspect
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

from ..core.metrics import increment_reconciliation_session
from ..core.logging_config import get_logger
from ..core.request_context import (
    clear_request_id,
    clear_correlation_id,
    generate_mqtt_correlation_id,
    set_request_id,
    set_correlation_id,
)
from ..services.inbound_inbox_service import InboundPriority, get_inbound_inbox_service
from .client import MQTTClient
from .topics import TopicBuilder

logger = get_logger(__name__)

# Suppress LWT messages delivered within this many seconds after server startup.
# Two scenarios must be handled:
#   1. Retained LWT (is_retained=True): broker replays stored will from before the restart.
#   2. Session-takeover LWT (is_retained=False): when the ESP reconnects at the same time
#      the server starts, the broker kicks the old session ("session taken over") and
#      publishes the LWT as a fresh PUBLISH — paho sees msg.retain=False. The S3 check
#      only on is_retained misses this and marks the device offline immediately.
# 120s covers: server startup (~30s) + ESP reconnect + full state-push grace window
# (STATE_PUSH_RECONNECT_DELAY_SECONDS=30s) + safety buffer. During this window the
# health_check_esps job (every 60s) still marks genuinely offline devices via heartbeat
# timeout, so no device can appear online indefinitely due to this suppression.
_STARTUP_LWT_SUPPRESS_SECONDS = 120


def _agent_debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
) -> None:
    try:
        entry = {
            "sessionId": "eea42f",
            "id": f"log_{time.time_ns()}",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        line = json.dumps(entry, ensure_ascii=True) + "\n"
        for candidate_path in (
            "/home/robin/.cursor/debug-eea42f.log",
            "/app/logs/debug-eea42f.log",
        ):
            try:
                with open(candidate_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                break
            except Exception:
                continue
    except Exception:
        pass


class Subscriber:
    """
    MQTT Subscriber with handler registry and message routing.

    Manages topic subscriptions and routes incoming messages to
    registered handler functions based on topic patterns.
    """

    def __init__(self, mqtt_client: Optional[MQTTClient] = None, max_workers: int = 10):
        """
        Initialize Subscriber.

        Args:
            mqtt_client: MQTT client instance (uses singleton if None)
            max_workers: Max concurrent handler threads (default: 10)
        """
        self.client = mqtt_client or MQTTClient.get_instance()
        self.handlers: Dict[str, Callable] = {}
        self._inbound_inbox = get_inbound_inbox_service()
        self._startup_time = time.monotonic()

        # Capture main event loop for async handler execution
        # CRITICAL: SQLAlchemy AsyncEngine is bound to this loop
        # All async handlers MUST run in this loop to avoid "Queue bound to different event loop"
        try:
            self._main_loop = asyncio.get_running_loop()
            logger.info("Captured main event loop for async handler execution")
        except RuntimeError:
            # No running loop - will be set later or handlers will create their own
            self._main_loop = None
            logger.warning("No running event loop during Subscriber init - async handlers may fail")

        # Thread pool for handler dispatch (not execution of async handlers)
        # Used to prevent blocking MQTT network loop
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="mqtt_handler_"
        )
        # Dedicated lane for response/ack topics so they don't queue behind bulk telemetry.
        self.priority_executor = ThreadPoolExecutor(
            max_workers=max(2, max_workers // 3), thread_name_prefix="mqtt_handler_prio_"
        )
        self._is_shutting_down = False

        # Performance metrics
        self.messages_processed = 0
        self.messages_failed = 0

        # Set global message callback
        self.client.set_on_message_callback(self._route_message)

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Set the main event loop for async handler execution.

        Call this if Subscriber was created before async context was available.

        Args:
            loop: The main asyncio event loop
        """
        self._main_loop = loop
        logger.info("Main event loop set for async handler execution")

    def register_handler(self, topic_pattern: str, handler: Callable) -> None:
        """
        Register handler for topic pattern.

        Args:
            topic_pattern: MQTT topic pattern (supports wildcards: +, #)
            handler: Handler ``(topic, payload)`` or ``(topic, payload, *, retain)`` if the
                handler declares a ``retain`` parameter (LWT).

        Example:
            subscriber.register_handler(
                "kaiser/god/esp/+/sensor/+/data",
                sensor_handler.handle_sensor_data
            )
        """
        self.handlers[topic_pattern] = handler
        logger.info(f"Registered handler for pattern: {topic_pattern}")

    def subscribe_all(self) -> bool:
        """
        Subscribe to all registered handler topic patterns.

        Subscribes to all patterns that have handlers registered via register_handler().
        QoS levels are determined by topic type:
        - Sensor data: QoS 1 (at least once)
        - Actuator status: QoS 1 (at least once)
        - Heartbeat: QoS 0 (at most once - fire and forget)
        - Discovery: QoS 1 (at least once)
        - Config Response: QoS 2 (exactly once, ESP→Server direction)

        Returns:
            True if all subscriptions successful
        """
        success = True

        # Subscribe to all registered handler patterns
        for pattern in self.handlers.keys():
            # Determine QoS based on topic type
            qos = self._resolve_qos_for_pattern(pattern)

            if not self.client.subscribe(pattern, qos):
                logger.error(f"Failed to subscribe to: {pattern}")
                success = False
            else:
                logger.debug(f"Subscribed to: {pattern} (QoS {qos})")

        return success

    @staticmethod
    def _resolve_qos_for_pattern(pattern: str) -> int:
        """Resolve QoS deterministically from the registered topic pattern."""
        if pattern.endswith("/system/heartbeat") or pattern.endswith("/system/heartbeat_metrics"):
            return 0  # Heartbeat lanes: fire and forget
        if "config_response" in pattern or "config/ack" in pattern:
            return 2  # Config acknowledgement lanes: exactly once
        return 1  # Default: at least once

    def subscribe(self, topic: str, qos: int = 1) -> bool:
        """
        Subscribe to specific topic.

        Args:
            topic: MQTT topic pattern
            qos: QoS level (0, 1, or 2)

        Returns:
            True if subscription successful
        """
        return self.client.subscribe(topic, qos)

    def _route_message(self, topic: str, payload_str: str, is_retained: bool = False) -> None:
        """
        Route incoming message to appropriate handler.

        Uses thread pool to execute async handlers without blocking MQTT loop.
        Each message is processed in isolation - handler failures don't affect others.

        Args:
            topic: MQTT topic
            payload_str: Message payload (JSON string)
            is_retained: True when the broker replayed a retained message (paho msg.retain)
        """
        try:
            if self._is_shutting_down:
                logger.debug("Dropping MQTT message during shutdown: %s", topic)
                return

            # S3 fix (extended): Suppress ALL LWT messages within startup grace window.
            # Covers two cases:
            #   - Retained LWT (is_retained=True): broker replays stored will on subscribe.
            #   - Session-takeover LWT (is_retained=False): concurrent ESP reconnect at
            #     startup triggers a fresh LWT publish ("session taken over" in broker log).
            # Both cases represent stale disconnect events, not the current session state.
            if "/system/will" in topic:
                elapsed = time.monotonic() - self._startup_time
                if elapsed < _STARTUP_LWT_SUPPRESS_SECONDS:
                    logger.info(
                        "Suppressing startup LWT topic=%s retained=%s (%.1fs since start, grace=%ds)",
                        topic,
                        is_retained,
                        elapsed,
                        _STARTUP_LWT_SUPPRESS_SECONDS,
                    )
                    return

            # Skip empty payloads (used to clear retained messages per MQTT spec)
            if not payload_str or not payload_str.strip():
                logger.debug(f"Empty payload on topic {topic} (retained message cleared)")
                return

            # Parse JSON payload
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                payload_len = len(payload_str)
                topic_class = (
                    "heartbeat"
                    if topic.endswith("/system/heartbeat")
                    else "heartbeat_metrics"
                    if topic.endswith("/system/heartbeat_metrics")
                    else "other"
                )
                payload_preview = payload_str[:160].replace("\n", "\\n").replace("\r", "\\r")
                logger.error(
                    "Invalid JSON payload on topic %s: %s (topic_class=%s payload_len=%s pos=%s line=%s col=%s preview=%r)",
                    topic,
                    e,
                    topic_class,
                    payload_len,
                    getattr(e, "pos", None),
                    getattr(e, "lineno", None),
                    getattr(e, "colno", None),
                    payload_preview,
                )
                self.messages_failed += 1
                return

            # Generate correlation ID from MQTT payload for cross-layer tracing
            esp_id = payload.get("esp_id", "unknown")
            seq = payload.get("seq")
            topic_suffix = topic.rsplit("/", 1)[-1] if "/" in topic else topic
            correlation_id = generate_mqtt_correlation_id(esp_id, topic_suffix, seq)
            payload_correlation_id = self._extract_payload_correlation_id(payload)
            effective_correlation_id = payload_correlation_id or correlation_id
            if payload_correlation_id and (
                ("/actuator/" in topic and topic.endswith("/response"))
                or topic.endswith("/system/intent_outcome")
            ):
                logger.warning(
                    "latency_stage stage=mqtt_subscriber_received correlation_id=%s topic=%s observed_at_ms=%s",
                    payload_correlation_id,
                    topic,
                    int(time.time() * 1000),
                )

            # Find matching handler
            handler = self._find_handler(topic)
            if handler:
                inbox_event_id = None
                is_off_response = (
                    "/actuator/" in topic
                    and topic.endswith("/response")
                    and str(payload.get("command", "")).upper() == "OFF"
                )
                # #region agent log
                if is_off_response:
                    _agent_debug_log(
                        run_id="off-latency-r1",
                        hypothesis_id="H2_SUBSCRIBER_QUEUE",
                        location="subscriber.py:_route_message:matched_handler",
                        message="OFF response matched handler",
                        data={
                            "topic": topic,
                            "correlation_id": payload.get("correlation_id"),
                            "inbox_critical": self._inbound_priority_for_topic(topic)
                            == InboundPriority.CRITICAL,
                        },
                    )
                # #endregion
                inbox_priority, latency_critical = self._classify_inbound_topic(topic)
                # Keep the durable inbox strictly for critical classes. High-frequency
                # telemetry (sensor data / heartbeat) must not synchronously block the
                # subscriber callback thread.
                if inbox_priority == InboundPriority.CRITICAL:
                    inbox_event_id = self._append_critical_inbound_event(
                        topic=topic,
                        payload=payload,
                        correlation_id=effective_correlation_id,
                        priority=inbox_priority,
                    )
                # Submit handler to thread pool for async execution
                # This prevents blocking MQTT network loop
                try:
                    target_executor = (
                        self.priority_executor
                        if latency_critical
                        else self.executor
                    )
                    # #region agent log
                    if is_off_response:
                        _agent_debug_log(
                            run_id="off-latency-r1",
                            hypothesis_id="H2_SUBSCRIBER_QUEUE",
                            location="subscriber.py:_route_message:submit_executor",
                            message="OFF response submitted to executor",
                            data={
                                "topic": topic,
                                "correlation_id": payload.get("correlation_id"),
                                "executor": (
                                    "priority"
                                    if target_executor is self.priority_executor
                                    else "default"
                                ),
                                "inbox_event_id": inbox_event_id,
                            },
                        )
                    # #endregion
                    target_executor.submit(
                        self._execute_handler,
                        handler,
                        topic,
                        payload,
                        effective_correlation_id,
                        inbox_event_id,
                        is_retained,
                    )
                except RuntimeError as submit_err:
                    submit_msg = str(submit_err).lower()
                    if (
                        self._is_shutting_down
                        or "cannot schedule new futures after shutdown" in submit_msg
                    ):
                        logger.debug(
                            "Dropping MQTT message during executor shutdown for topic %s",
                            topic,
                        )
                        return
                    raise
                self.messages_processed += 1
            else:
                logger.warning(f"No handler registered for topic: {topic}")

        except Exception as e:
            logger.error(f"Error routing message from {topic}: {e}", exc_info=True)
            self.messages_failed += 1

    def _append_critical_inbound_event(
        self,
        topic: str,
        payload: dict,
        correlation_id: str,
        priority: InboundPriority,
    ) -> Optional[str]:
        """
        Append critical inbound event via the main loop.

        Using asyncio.run() from the MQTT callback thread can bind DB resources
        to a foreign event loop and trigger intermittent "bound to different event loop"
        errors under load/reconnect conditions.
        """
        try:
            loop = self._get_valid_main_loop()
        except RuntimeError as e:
            logger.error(
                "Critical inbound append skipped for topic %s: %s",
                topic,
                e,
            )
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._inbound_inbox.append(
                    topic=topic,
                    payload=payload,
                    correlation_id=correlation_id,
                    source="live",
                    priority=priority,
                ),
                loop,
            )
            return future.result(timeout=5.0)
        except Exception as e:
            logger.error(
                "Critical inbound append failed for topic %s: %s",
                topic,
                e,
            )
            return None

    @staticmethod
    def _classify_inbound_topic(topic: str) -> tuple[Optional[InboundPriority], bool]:
        is_actuator_response = "/actuator/" in topic and topic.endswith("/response")
        is_sensor_response = "/sensor/" in topic and topic.endswith("/response")
        is_sensor_data = "/sensor/" in topic and topic.endswith("/data")
        is_intent_outcome = topic.endswith("/system/intent_outcome")
        is_intent_outcome_lifecycle = topic.endswith("/system/intent_outcome/lifecycle")
        is_critical = (
            is_actuator_response
            or is_sensor_response
            or is_intent_outcome
            or topic.endswith("/config_response")
            or topic.endswith("/zone/ack")
            or topic.endswith("/subzone/ack")
            or topic.endswith("/system/command/response")
        )
        if is_critical:
            return InboundPriority.CRITICAL, True
        if is_intent_outcome_lifecycle:
            return InboundPriority.HIGH, False
        if topic.endswith("/system/heartbeat") or is_sensor_data:
            return InboundPriority.HIGH, False
        if topic.endswith("/system/diagnostics") or topic.endswith("/system/queue_pressure"):
            return InboundPriority.NORMAL, False
        return None, False

    @staticmethod
    def _extract_payload_correlation_id(payload: dict) -> Optional[str]:
        """Return payload correlation_id when present and non-empty."""
        correlation = payload.get("correlation_id")
        if correlation is None:
            return None
        normalized = str(correlation).strip()
        return normalized if normalized else None

    @staticmethod
    def _inbound_priority_for_topic(topic: str) -> Optional[InboundPriority]:
        priority, _ = Subscriber._classify_inbound_topic(topic)
        return priority

    def _get_valid_main_loop(self) -> asyncio.AbstractEventLoop:
        """
        Get a valid main event loop for async handler execution.

        This method validates the cached loop and attempts recovery if it's invalid.
        Prevents "Queue bound to different event loop" errors.

        Returns:
            Valid event loop or None

        Raises:
            RuntimeError: If no valid event loop is available
        """
        # Check if cached loop is still valid
        if self._main_loop is not None and not self._main_loop.is_closed():
            return self._main_loop

        # Cached loop is invalid - log warning and attempt to use the set_main_loop() value
        logger.warning(
            "[Bug O Fix] Cached main event loop is invalid or closed. "
            "This may indicate an event loop lifecycle issue."
        )

        # Cannot automatically recover - the loop must be set explicitly
        raise RuntimeError(
            "Main event loop is not available or has been closed. "
            "Call set_main_loop() to set a valid event loop."
        )

    @staticmethod
    def _handler_accepts_retain(handler: Callable) -> bool:
        """True if handler signature includes a ``retain`` parameter (LWT path)."""
        try:
            return "retain" in inspect.signature(handler).parameters
        except (TypeError, ValueError):
            return False

    @staticmethod
    async def _run_handler_with_cid(
        handler: Callable,
        topic: str,
        payload: dict,
        correlation_id: str,
        retain: bool = False,
    ):
        """Run MQTT handler with correlation ID set in event loop context.

        This wrapper ensures the ContextVar is set in the CORRECT context
        (the main event loop), not in the ThreadPool worker thread where
        run_coroutine_threadsafe() is called from. ContextVars do NOT
        propagate across thread boundaries automatically (PEP 567).

        Args:
            handler: Async handler function
            topic: MQTT topic
            payload: Parsed payload dict
            correlation_id: Cross-layer correlation ID (esp_id:topic:seq:ts)
            retain: MQTT retain flag from broker delivery (passed only to handlers that accept it)
        """
        token_cid = set_correlation_id(correlation_id)
        token_req = set_request_id(correlation_id)
        try:
            if Subscriber._handler_accepts_retain(handler):
                return await handler(topic, payload, retain=retain)
            return await handler(topic, payload)
        finally:
            clear_correlation_id(token_cid)
            clear_request_id(token_req)

    @staticmethod
    def _is_critical_topic(topic: str) -> bool:
        # High-frequency sensor data must not go through synchronous durable append,
        # otherwise the callback thread stalls and latency-critical actuator responses
        # are delayed in the broker->subscriber ingress queue.
        return (
            Subscriber._inbound_priority_for_topic(topic) == InboundPriority.CRITICAL
            or topic.endswith("/system/error")
            or topic.endswith("/system/will")
        )

    @staticmethod
    def _is_latency_critical_topic(topic: str) -> bool:
        """Response lanes that should bypass bulk-worker congestion."""
        _, is_latency_critical = Subscriber._classify_inbound_topic(topic)
        return is_latency_critical

    def _execute_handler(
        self,
        handler: Callable,
        topic: str,
        payload: dict,
        correlation_id: str = "",
        inbox_event_id: Optional[str] = None,
        retain: bool = False,
    ) -> None:
        """
        Execute handler in thread pool.

        Handles both sync and async handlers transparently.

        CRITICAL FIX (2025-12-30):
        Async handlers are scheduled in the MAIN event loop using run_coroutine_threadsafe().
        This ensures SQLAlchemy AsyncEngine (bound to main loop) works correctly.
        Previously, creating a new event loop per thread caused "Queue bound to different event loop".

        BUG O FIX (2026-01-05):
        Added robust loop validation to prevent "Queue bound to different event loop" errors
        in Python 3.12+ which is stricter about event loop binding.

        CID FIX (2026-02-25):
        Correlation ID is now passed explicitly to a wrapper coroutine that sets the
        ContextVar in the event loop context. Previously, set_request_id() was called
        in the ThreadPool worker, but ContextVars don't propagate across thread boundaries.

        Args:
            handler: Handler function (sync or async)
            topic: MQTT topic
            payload: Parsed payload dict
            correlation_id: Cross-layer correlation ID (esp_id:topic:seq:ts)
        """
        try:
            is_off_response = (
                "/actuator/" in topic
                and topic.endswith("/response")
                and str(payload.get("command", "")).upper() == "OFF"
            )
            # #region agent log
            if is_off_response:
                _agent_debug_log(
                    run_id="off-latency-r1",
                    hypothesis_id="H2_SUBSCRIBER_QUEUE",
                    location="subscriber.py:_execute_handler:entry",
                    message="OFF response entered handler worker",
                    data={
                        "topic": topic,
                        "correlation_id": payload.get("correlation_id"),
                        "inbox_event_id": inbox_event_id,
                        "is_async_handler": bool(asyncio.iscoroutinefunction(handler)),
                    },
                )
            # #endregion
            # Check if handler is async (coroutine function)
            if asyncio.iscoroutinefunction(handler):
                # CRITICAL: Run async handler in MAIN event loop
                # SQLAlchemy AsyncEngine's connection pool is bound to main loop
                try:
                    main_loop = self._get_valid_main_loop()
                except RuntimeError as e:
                    logger.error(f"[Bug O] {e} - Handler for {topic} will not be executed.")
                    self.messages_failed += 1
                    return

                # Schedule coroutine in main event loop (thread-safe)
                # CID is passed as parameter to the wrapper, NOT via ContextVar
                # (ContextVars don't propagate across thread boundaries)
                future = asyncio.run_coroutine_threadsafe(
                    self._run_handler_with_cid(handler, topic, payload, correlation_id, retain),
                    main_loop,
                )

                try:
                    # Wait for completion with timeout (30 seconds)
                    result = future.result(timeout=30.0)
                    # #region agent log
                    if is_off_response:
                        _agent_debug_log(
                            run_id="off-latency-r1",
                            hypothesis_id="H2_SUBSCRIBER_QUEUE",
                            location="subscriber.py:_execute_handler:future_done",
                            message="OFF response async handler finished",
                            data={
                                "topic": topic,
                                "correlation_id": payload.get("correlation_id"),
                                "result": result,
                            },
                        )
                    # #endregion
                    if result is False:
                        logger.warning(
                            f"Handler returned False for topic {topic} - processing may have failed"
                        )
                        self._inbox_mark_attempt(inbox_event_id)
                    else:
                        self._inbox_mark_delivered(inbox_event_id)
                except TimeoutError:
                    logger.error(f"Handler timed out for topic {topic} (30s)")
                    self.messages_failed += 1
                    self._inbox_mark_attempt(inbox_event_id)
                except Exception as e:
                    # Check specifically for event loop errors
                    error_str = str(e).lower()
                    if "event loop" in error_str or "queue" in error_str:
                        logger.error(
                            f"[Bug O] Event loop error in handler for {topic}: {e}. "
                            "This may indicate the main loop reference has become invalid."
                        )
                    else:
                        logger.error(f"Async handler failed for topic {topic}: {e}")
                    self.messages_failed += 1
                    self._inbox_mark_attempt(inbox_event_id)
            else:
                # Sync handler - call directly in thread pool
                # Set CID in thread context for sync handler logging
                token_cid = set_correlation_id(correlation_id) if correlation_id else None
                token_req = set_request_id(correlation_id) if correlation_id else None
                try:
                    if self._handler_accepts_retain(handler):
                        result = handler(topic, payload, retain=retain)
                    else:
                        result = handler(topic, payload)
                    if result is False:
                        logger.warning(
                            f"Handler returned False for topic {topic} - processing may have failed"
                        )
                        self._inbox_mark_attempt(inbox_event_id)
                    else:
                        self._inbox_mark_delivered(inbox_event_id)
                finally:
                    clear_correlation_id(token_cid)
                    clear_request_id(token_req)

        except Exception as e:
            logger.error(f"Handler execution failed for topic {topic}: {e}", exc_info=True)
            self.messages_failed += 1
            self._inbox_mark_attempt(inbox_event_id)

    def _inbox_mark_delivered(self, inbox_event_id: Optional[str]) -> None:
        if not inbox_event_id:
            return
        try:
            loop = self._get_valid_main_loop()
            asyncio.run_coroutine_threadsafe(
                self._inbound_inbox.mark_delivered(inbox_event_id),
                loop,
            ).result(timeout=5.0)
        except Exception as e:
            logger.warning("Failed to ack inbox event %s: %s", inbox_event_id, e)

    def _inbox_mark_attempt(self, inbox_event_id: Optional[str]) -> None:
        if not inbox_event_id:
            return
        try:
            loop = self._get_valid_main_loop()
            asyncio.run_coroutine_threadsafe(
                self._inbound_inbox.mark_attempt(inbox_event_id),
                loop,
            ).result(timeout=5.0)
        except Exception as e:
            logger.warning("Failed to mark inbox attempt %s: %s", inbox_event_id, e)

    async def replay_pending_events(self, limit: int = 200) -> dict[str, int]:
        """
        Replay pending critical inbound events from durable inbox.
        """
        pending = await self._inbound_inbox.list_pending(limit=limit)
        replayed = 0
        failed = 0
        session_id = f"recon-{uuid4().hex[:12]}"
        total = len(pending)

        if total > 0:
            increment_reconciliation_session("start")
            logger.info(
                "reconciliation_session_start session_id=%s pending=%s",
                session_id,
                total,
            )

        for idx, event in enumerate(pending, start=1):
            event_id = event.get("id")
            topic = event.get("topic")
            payload = event.get("payload")
            if not topic or not isinstance(payload, dict):
                failed += 1
                if event_id:
                    await self._inbound_inbox.mark_attempt(event_id)
                continue

            handler = self._find_handler(topic)
            if handler is None:
                failed += 1
                if event_id:
                    await self._inbound_inbox.mark_attempt(event_id)
                continue

            correlation_id = event.get("correlation_id") or generate_mqtt_correlation_id(
                payload.get("esp_id", "unknown"),
                topic.rsplit("/", 1)[-1] if "/" in topic else topic,
                payload.get("seq"),
            )
            if event_id:
                await self._inbound_inbox.mark_attempt(event_id)
            try:
                replay_payload = dict(payload)
                replay_payload["_reconciliation"] = {
                    "session_id": session_id,
                    "phase": "start" if idx == 1 else ("end" if idx == total else "progress"),
                    "position": idx,
                    "total": total,
                    "started_at": int(datetime.now(timezone.utc).timestamp()),
                }
                increment_reconciliation_session(replay_payload["_reconciliation"]["phase"])
                if asyncio.iscoroutinefunction(handler):
                    result = await self._run_handler_with_cid(
                        handler, topic, replay_payload, correlation_id, retain=False
                    )
                else:
                    token = set_request_id(correlation_id)
                    try:
                        result = handler(topic, replay_payload)
                    finally:
                        clear_request_id(token)

                if result is False:
                    failed += 1
                    continue

                replayed += 1
                if event_id:
                    await self._inbound_inbox.mark_delivered(event_id)
            except Exception:
                failed += 1
                logger.exception("Replay failed for inbox event_id=%s topic=%s", event_id, topic)

        if total > 0:
            logger.info(
                "reconciliation_session_end session_id=%s replayed=%s failed=%s",
                session_id,
                replayed,
                failed,
            )

        return {"replayed": replayed, "failed": failed, "pending_checked": len(pending)}

    def _find_handler(self, topic: str) -> Optional[Callable]:
        """
        Find handler for topic by matching against registered patterns.

        Args:
            topic: Actual MQTT topic

        Returns:
            Handler function or None
        """
        for pattern, handler in self.handlers.items():
            if TopicBuilder.matches_subscription(topic, pattern):
                return handler
        return None

    def unregister_handler(self, topic_pattern: str) -> bool:
        """
        Unregister handler for topic pattern.

        Args:
            topic_pattern: MQTT topic pattern

        Returns:
            True if handler was removed
        """
        if topic_pattern in self.handlers:
            del self.handlers[topic_pattern]
            logger.info(f"Unregistered handler for pattern: {topic_pattern}")
            return True
        return False

    def get_registered_patterns(self) -> list:
        """
        Get list of registered topic patterns.

        Returns:
            List of topic patterns
        """
        return list(self.handlers.keys())

    def get_stats(self) -> dict:
        """
        Get subscriber performance statistics.

        Returns:
            {
                "messages_processed": int,
                "messages_failed": int,
                "success_rate": float
            }
        """
        total = self.messages_processed + self.messages_failed
        success_rate = (self.messages_processed / total * 100) if total > 0 else 0.0

        return {
            "messages_processed": self.messages_processed,
            "messages_failed": self.messages_failed,
            "success_rate": round(success_rate, 2),
        }

    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """
        Shutdown subscriber and thread pool.

        Args:
            wait: Wait for pending tasks to complete
            timeout: Max wait time in seconds (ignored in Python 3.14+)
        """
        logger.info("Shutting down MQTT subscriber...")
        self._is_shutting_down = True
        # Python 3.9-3.13 supports timeout parameter, Python 3.14+ removed it
        # Use cancel_futures instead for faster shutdown
        try:
            self.executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            # Fallback for older Python versions without cancel_futures
            self.executor.shutdown(wait=wait)
        try:
            self.priority_executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            self.priority_executor.shutdown(wait=wait)
        logger.info(f"Subscriber stats: {self.get_stats()}")
