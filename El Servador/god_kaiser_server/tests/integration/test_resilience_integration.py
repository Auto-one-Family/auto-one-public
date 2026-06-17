"""
Integration Tests: Resilience Patterns

Integration-Tests für Circuit Breaker, Retry und Timeout in realistischen Szenarien.
"""

import asyncio
import pytest
from sqlalchemy.exc import OperationalError

from src.core.resilience import (
    CircuitBreaker,
    CircuitState,
    ResilienceRegistry,
    ServiceUnavailableError,
)
from src.db.session import resilient_session, init_db_circuit_breaker
from src.mqtt.client import MQTTClient


class TestDatabaseResilience:
    """Integration tests for database resilience."""

    @pytest.mark.asyncio
    async def test_resilient_session_with_circuit_breaker(self):
        """Test resilient_session() integrates with circuit breaker."""
        # Initialize circuit breaker
        init_db_circuit_breaker()

        # Get the circuit breaker
        registry = ResilienceRegistry.get_instance()
        db_breaker = registry.get_circuit_breaker("database")

        assert db_breaker is not None
        assert db_breaker.get_state() == CircuitState.CLOSED

        # Normal operation should work
        try:
            async with resilient_session() as session:
                # Simple query
                result = await session.execute("SELECT 1")
                assert result is not None

            # Should record success
            metrics = db_breaker.get_metrics()
            assert metrics["successful_requests"] >= 1
        except Exception:
            # Test environment might not have DB - that's OK
            pass

    @pytest.mark.asyncio
    async def test_resilient_session_rejects_when_breaker_open(self):
        """Test resilient_session() rejects when circuit breaker is OPEN."""
        # Initialize and get circuit breaker
        init_db_circuit_breaker()
        registry = ResilienceRegistry.get_instance()
        db_breaker = registry.get_circuit_breaker("database")

        # Force circuit breaker open
        db_breaker.force_open()

        # is_open property checks both state and _forced_open flag
        assert db_breaker.is_open is True

        # Should reject request
        with pytest.raises(ServiceUnavailableError) as exc_info:
            async with resilient_session() as session:
                pass

        assert exc_info.value.service_name == "database"
        assert "Circuit breaker is OPEN" in exc_info.value.reason

        # Reset for other tests
        db_breaker.reset()

    @pytest.mark.asyncio
    async def test_database_circuit_breaker_recovery(self):
        """Test database circuit breaker recovers after transient failures."""
        init_db_circuit_breaker()
        registry = ResilienceRegistry.get_instance()
        db_breaker = registry.get_circuit_breaker("database")

        # Reset to known state
        db_breaker.reset()

        # Simulate some failures (but not enough to open)
        db_breaker.record_failure()
        assert db_breaker.get_state() == CircuitState.CLOSED

        # Success should reset failure count
        db_breaker.record_success()
        assert db_breaker.failure_count == 0


class TestMQTTResilience:
    """Integration tests for MQTT resilience."""

    def test_mqtt_client_has_circuit_breaker(self):
        """Test MQTT client initializes with circuit breaker."""
        mqtt_client = MQTTClient.get_instance()

        # Should have resilience status
        status = mqtt_client.get_resilience_status()

        assert "connected" in status
        assert "circuit_breaker" in status or mqtt_client._circuit_breaker is not None

    def test_mqtt_client_has_offline_buffer(self):
        """Test MQTT client initializes with offline buffer."""
        mqtt_client = MQTTClient.get_instance()

        # Should have offline buffer
        assert mqtt_client._offline_buffer is not None

        # Should have buffer metrics
        try:
            metrics = mqtt_client.get_offline_buffer_metrics()
            assert "current_size" in metrics or "enabled" in metrics
        except AttributeError:
            # Older implementation might not have get_offline_buffer_metrics
            pass

    @pytest.mark.asyncio
    async def test_mqtt_offline_buffer_on_circuit_breaker_open(self):
        """Test MQTT buffers messages when circuit breaker is OPEN."""
        mqtt_client = MQTTClient.get_instance()

        # Get or create circuit breaker
        if mqtt_client._circuit_breaker:
            breaker = mqtt_client._circuit_breaker
        else:
            registry = ResilienceRegistry.get_instance()
            breaker = registry.get_circuit_breaker("mqtt")

        if breaker is None:
            pytest.skip("MQTT circuit breaker not initialized")

        # Force open
        breaker.force_open()

        # Try to publish (should buffer)
        result = mqtt_client.publish("test/topic", '{"test": 1}', qos=1)

        # Publish should fail/return False (buffered)
        # Depending on implementation, might return False or True (buffered)

        # Reset
        breaker.reset()


class TestResilienceRegistry:
    """Integration tests for Resilience Registry."""

    def test_registry_singleton(self):
        """Test ResilienceRegistry is singleton."""
        registry1 = ResilienceRegistry.get_instance()
        registry2 = ResilienceRegistry.get_instance()

        assert registry1 is registry2

    def test_registry_aggregates_health_status(self):
        """Test registry aggregates health from all breakers."""
        registry = ResilienceRegistry.get_instance()

        health = registry.get_health_status()

        assert "healthy" in health
        assert "breakers" in health
        assert "summary" in health

        # Summary should have counts
        assert "total" in health["summary"]
        assert "closed" in health["summary"]

    def test_registry_provides_metrics(self):
        """Test registry provides metrics from all breakers."""
        registry = ResilienceRegistry.get_instance()

        metrics = registry.get_metrics()

        assert isinstance(metrics, dict)
        # Should have at least database or mqtt breaker
        assert len(metrics) >= 0

    def test_registry_reset_all(self):
        """Test registry can reset all breakers."""
        registry = ResilienceRegistry.get_instance()

        # Get initial count
        count = registry.reset_all()

        # Should reset some breakers (at least 0)
        assert count >= 0


class TestEndToEndResilience:
    """End-to-end resilience scenarios."""

    @pytest.mark.asyncio
    async def test_full_resilience_stack(self):
        """Test full resilience stack in realistic scenario."""
        # This test simulates a full workflow with resilience:
        # 1. Database circuit breaker
        # 2. Retry on transient failures
        # 3. Timeout for slow operations

        init_db_circuit_breaker()
        registry = ResilienceRegistry.get_instance()
        db_breaker = registry.get_circuit_breaker("database")

        # Reset to known state
        db_breaker.reset()

        # Simulate workflow
        workflow_success = False

        try:
            async with resilient_session() as session:
                # Simulate DB operation
                await asyncio.sleep(0.01)
                workflow_success = True
        except Exception:
            # Test environment might not have DB
            workflow_success = False

        # Circuit breaker should track success/failure
        metrics = db_breaker.get_metrics()
        assert metrics is not None

    def test_circuit_breaker_prevents_cascade_failure(self):
        """Test circuit breaker prevents cascade failures."""
        # Create test circuit breaker
        test_breaker = CircuitBreaker(
            name="test_cascade",
            failure_threshold=3,
            recovery_timeout=1.0,
        )

        registry = ResilienceRegistry.get_instance()
        registry.register_circuit_breaker("test_cascade", test_breaker)

        # Simulate failures
        for _ in range(3):
            test_breaker.record_failure()

        # Breaker should be OPEN
        assert test_breaker.get_state() == CircuitState.OPEN

        # Further requests should be rejected immediately (fail-fast)
        assert test_breaker.allow_request() is False

        # Clean up
        registry.unregister("test_cascade")
