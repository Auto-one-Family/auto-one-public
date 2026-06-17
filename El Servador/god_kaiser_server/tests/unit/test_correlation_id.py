"""
Unit tests for Correlation-ID generation and context propagation.

Tests the cross-layer tracing infrastructure:
- MQTT correlation ID format and content
- ContextVar isolation between concurrent contexts
- Integration with logging filter
"""

import asyncio
import logging
import re
import time

import pytest

from src.core.request_context import (
    clear_request_id,
    generate_mqtt_correlation_id,
    generate_request_id,
    get_request_id,
    set_request_id,
)


class TestGenerateMqttCorrelationId:
    """Tests for generate_mqtt_correlation_id()."""

    def test_format_with_seq(self):
        """Correlation ID has format {esp_id}:{topic_suffix}:{seq}:{timestamp_ms}."""
        cid = generate_mqtt_correlation_id("ESP_12AB34CD", "data", 142)
        parts = cid.split(":")
        assert len(parts) == 4
        assert parts[0] == "ESP_12AB34CD"
        assert parts[1] == "data"
        assert parts[2] == "142"
        # Timestamp is milliseconds (13+ digits)
        assert len(parts[3]) >= 13

    def test_format_without_seq(self):
        """Correlation ID uses 'no-seq' when sequence is None."""
        cid = generate_mqtt_correlation_id("ESP_001", "heartbeat", None)
        parts = cid.split(":")
        assert parts[2] == "no-seq"

    def test_contains_esp_id(self):
        """ESP device ID is the first component."""
        cid = generate_mqtt_correlation_id("ESP_AABBCCDD", "sensor", 1)
        assert cid.startswith("ESP_AABBCCDD:")

    def test_contains_seq(self):
        """Sequence number appears as third component."""
        cid = generate_mqtt_correlation_id("esp-001", "data", 999)
        assert ":999:" in cid

    def test_seq_zero_is_valid(self):
        """Sequence number 0 is a valid value (not treated as missing)."""
        cid = generate_mqtt_correlation_id("esp-001", "data", 0)
        assert ":0:" in cid

    def test_timestamp_is_recent(self):
        """Timestamp component is within 1 second of current time."""
        before_ms = int(time.time() * 1000)
        cid = generate_mqtt_correlation_id("esp", "data", 1)
        after_ms = int(time.time() * 1000)

        ts_ms = int(cid.split(":")[-1])
        assert before_ms <= ts_ms <= after_ms

    def test_different_calls_have_different_timestamps(self):
        """Two rapid calls produce different timestamps (or at least different CIDs)."""
        cid1 = generate_mqtt_correlation_id("esp", "data", 1)
        cid2 = generate_mqtt_correlation_id("esp", "data", 2)
        assert cid1 != cid2


class TestContextVarIsolation:
    """Tests for ContextVar-based request_id propagation."""

    def test_set_and_get(self):
        """set_request_id stores value retrievable by get_request_id."""
        set_request_id("test-cid-123")
        assert get_request_id() == "test-cid-123"
        clear_request_id()

    def test_clear_resets_to_none(self):
        """clear_request_id resets value to None."""
        set_request_id("some-value")
        clear_request_id()
        assert get_request_id() is None

    def test_default_is_none(self):
        """Default value without set is None."""
        clear_request_id()
        assert get_request_id() is None

    def test_generate_request_id_is_uuid(self):
        """generate_request_id returns a valid UUID string."""
        rid = generate_request_id()
        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_pattern.match(rid)

    @pytest.mark.asyncio
    async def test_async_context_isolation(self):
        """ContextVars are isolated between concurrent async tasks."""
        results = {}

        async def task(name: str, cid: str):
            set_request_id(cid)
            await asyncio.sleep(0.01)  # Yield to other tasks
            results[name] = get_request_id()

        await asyncio.gather(
            task("task_a", "cid-a"),
            task("task_b", "cid-b"),
        )

        assert results["task_a"] == "cid-a"
        assert results["task_b"] == "cid-b"
        clear_request_id()


class TestCorrelationIdInLogs:
    """Tests for correlation ID appearing in log output."""

    def test_request_id_filter_injects_field(self):
        """RequestIdFilter adds request_id attribute to log records."""
        from src.core.logging_config import RequestIdFilter

        log_filter = RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=None,
            exc_info=None,
        )

        set_request_id("ESP_001:data:42:1234567890123")
        log_filter.filter(record)

        assert record.request_id == "ESP_001:data:42:1234567890123"
        clear_request_id()

    def test_request_id_filter_dash_when_empty(self):
        """RequestIdFilter sets '-' when no request_id is set."""
        from src.core.logging_config import RequestIdFilter

        log_filter = RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=None,
            exc_info=None,
        )

        clear_request_id()
        log_filter.filter(record)

        assert record.request_id == "-"
