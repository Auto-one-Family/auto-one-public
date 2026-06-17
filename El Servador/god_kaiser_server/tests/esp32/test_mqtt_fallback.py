"""
Tests for MQTT Port-Fallback (Safety-Critical).

Validates that the ESP32 falls back from TLS port 8883 to plain MQTT port 1883
when TLS connection fails, ensuring the device can still communicate.

Firmware reference: El Trabajante/src/services/communication/mqtt_client.cpp
    - attemptMQTTConnection() tries 8883 first, then 1883
    - Circuit breaker opens after both ports fail

These tests simulate the port fallback logic.
"""

import pytest

from .mocks.mock_esp32_client import MockESP32Client


class MQTTFallbackSimulator:
    """
    Simulates MQTT port fallback from MQTTClient::attemptMQTTConnection().

    Tracks connection attempts and logs for verification.
    """

    def __init__(self):
        self.connection_attempts: list[dict] = []
        self.log_messages: list[tuple[str, str]] = []  # (level, message)
        self._port_availability: dict[int, bool] = {8883: True, 1883: True}
        self.connected_port: int | None = None
        self.circuit_breaker_open: bool = False
        self._consecutive_failures: int = 0
        self.CIRCUIT_BREAKER_THRESHOLD = 3

    def set_port_available(self, port: int, available: bool):
        self._port_availability[port] = available

    def attempt_connection(self, server: str = "localhost") -> bool:
        """
        Simulate attemptMQTTConnection().

        Returns True if connection succeeded on any port.
        """
        if self.circuit_breaker_open:
            self.log_messages.append(("ERROR", "Circuit breaker open - skipping connection"))
            return False

        # Try primary port (8883 TLS)
        self.connection_attempts.append({"server": server, "port": 8883, "tls": True})
        if self._port_availability.get(8883, False):
            self.connected_port = 8883
            self._consecutive_failures = 0
            self.log_messages.append(("INFO", f"Connected to {server}:8883 (TLS)"))
            return True

        # Fallback to plain MQTT (1883)
        self.log_messages.append(("WARNING", "TLS failed, trying plain MQTT on 1883"))
        self.connection_attempts.append({"server": server, "port": 1883, "tls": False})
        if self._port_availability.get(1883, False):
            self.connected_port = 1883
            self._consecutive_failures = 0
            self.log_messages.append(("INFO", f"Connected to {server}:1883 (plain)"))
            return True

        # Both failed
        self.connected_port = None
        self._consecutive_failures += 1
        self.log_messages.append(
            (
                "ERROR",
                f"Both ports failed ({self._consecutive_failures}/{self.CIRCUIT_BREAKER_THRESHOLD})",
            )
        )

        if self._consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
            self.circuit_breaker_open = True
            self.log_messages.append(("CRITICAL", "Circuit breaker opened"))

        return False

    def reconnect(self, server: str = "localhost") -> bool:
        """Simulate reconnect (uses last successful port if available)."""
        if self.connected_port and self._port_availability.get(self.connected_port, False):
            self.connection_attempts.append(
                {"server": server, "port": self.connected_port, "tls": self.connected_port == 8883}
            )
            return True
        return self.attempt_connection(server)


class TestMQTTPortFallback:
    """Tests for MQTT Port-Fallback."""

    @pytest.fixture
    def sim(self):
        return MQTTFallbackSimulator()

    def test_primary_port_success_no_fallback(self, sim):
        """MF-001: Port 8883 succeeds → no fallback attempted."""
        sim.set_port_available(8883, True)

        result = sim.attempt_connection()

        assert result is True
        assert sim.connected_port == 8883
        assert len(sim.connection_attempts) == 1  # Only one attempt

    def test_tls_timeout_falls_back_to_plain(self, sim):
        """MF-002: Port 8883 fails → fallback to 1883."""
        sim.set_port_available(8883, False)
        sim.set_port_available(1883, True)

        result = sim.attempt_connection()

        assert result is True
        assert sim.connected_port == 1883
        assert len(sim.connection_attempts) == 2  # Tried both

    def test_both_ports_fail_opens_circuit_breaker(self, sim):
        """MF-003: Both ports fail N times → circuit breaker opens."""
        sim.set_port_available(8883, False)
        sim.set_port_available(1883, False)

        for _ in range(sim.CIRCUIT_BREAKER_THRESHOLD):
            sim.attempt_connection()

        assert sim.circuit_breaker_open is True
        # Next attempt is blocked
        result = sim.attempt_connection()
        assert result is False

    def test_fallback_is_logged(self, sim):
        """MF-004: Fallback to plain MQTT is logged as WARNING."""
        sim.set_port_available(8883, False)
        sim.set_port_available(1883, True)

        sim.attempt_connection()

        warnings = [msg for level, msg in sim.log_messages if level == "WARNING"]
        assert any("TLS failed" in msg and "1883" in msg for msg in warnings)

    def test_reconnect_stays_on_fallback_port(self, sim):
        """MF-005: After fallback, reconnect uses port 1883."""
        sim.set_port_available(8883, False)
        sim.set_port_available(1883, True)

        sim.attempt_connection()
        assert sim.connected_port == 1883

        # Reconnect should use last successful port
        sim.connection_attempts.clear()
        result = sim.reconnect()

        assert result is True
        assert sim.connection_attempts[-1]["port"] == 1883
