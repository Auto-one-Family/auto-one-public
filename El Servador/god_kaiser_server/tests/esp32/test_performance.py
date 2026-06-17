"""
Performance/Load Tests - ESP32 system stress testing.

NOTE: Uses REAL MQTT topic structure for realistic performance metrics.
This design choice enables:
- Performance tests run against both Mock clients AND real hardware
- Real-world performance validation
- Load testing with production-identical message patterns

Tests verify:
1. High-frequency sensor reads
2. Concurrent actuator commands
3. Large sensor/actuator counts
4. MQTT message throughput
5. System responsiveness under load

NOTE: Performance targets based on real hardware capabilities:
- ESP32 Dev Board: 20 sensors, 12 actuators
- XIAO ESP32-C3: 10 sensors, 6 actuators
- MQTT: ~100 messages/second typical, 1000+ messages/second max
"""

import pytest
import time
from time import perf_counter
import random


@pytest.mark.performance
class TestSensorPerformance:
    """Test sensor reading performance and throughput."""

    def test_rapid_sensor_reads(self, mock_esp32_with_sensors):
        """
        Test 100 rapid consecutive sensor reads.

        Performance target: < 1 second for 100 reads (Mock).
        Real hardware target: < 10 seconds.
        """
        start_time = perf_counter()

        for i in range(100):
            response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        # Performance target
        assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for 100 reads"

        # Throughput calculation (guard against near-zero elapsed on fast systems)
        throughput = 100 / max(elapsed, 1e-9)
        print(f"Sensor read throughput: {throughput:.1f} reads/second")

    def test_many_sensors_concurrent(self, mock_esp32):
        """
        Test ESP with 20 sensors (ESP32 Dev Board limit).

        Performance target: < 2 seconds for 20 sensors.
        """
        # Setup 20 sensors on analog-capable GPIOs
        sensor_gpios = list(range(32, 52))  # GPIO 32-51
        for gpio in sensor_gpios:
            mock_esp32.set_sensor_value(gpio, random.random() * 4095, sensor_type="analog")

        # Read all sensors
        start_time = perf_counter()
        results = []
        for gpio in sensor_gpios:
            response = mock_esp32.handle_command("sensor_read", {"gpio": gpio})
            results.append(response)
        elapsed = perf_counter() - start_time

        # Verify all succeeded
        assert all(r["status"] == "ok" for r in results), "Some sensor reads failed"

        # Performance target
        assert elapsed < 2.0, f"Too slow: {elapsed:.3f}s for 20 sensors"

        print(f"20 sensors read in {elapsed:.3f}s ({20/max(elapsed, 1e-9):.1f} reads/second)")

    def test_sensor_read_with_mqtt_publishing(self, mock_esp32_with_sensors):
        """
        Test sensor reads including MQTT message publishing.

        Each read generates MQTT publishes - tests realistic throughput.
        Note: With zone configured, each sensor_read publishes 2 messages:
        - Primary topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
        - Zone topic: kaiser/god/zone/{master_zone_id}/esp/{esp_id}/subzone/{subzone_id}/sensor/{gpio}/data
        """
        mock_esp32_with_sensors.clear_published_messages()

        start_time = perf_counter()

        # Read sensor 50 times
        for i in range(50):
            response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        # Verify MQTT messages published (2 per read when zone configured)
        messages = mock_esp32_with_sensors.get_published_messages()
        # Zone-configured ESP publishes to both primary and zone topics
        expected_messages = 50 * 2  # 2 messages per sensor_read
        assert (
            len(messages) == expected_messages
        ), f"Expected {expected_messages} messages, got {len(messages)}"

        # Performance target: < 0.5 seconds
        assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s"

        print(f"50 sensor reads + MQTT publishes: {elapsed:.3f}s ({len(messages)} messages)")

    def test_burst_sensor_reads(self, mock_esp32):
        """
        Test burst reading from multiple sensors.

        Simulates reading all sensors in quick succession.
        """
        # Setup 10 sensors
        sensor_gpios = [32, 33, 34, 35, 36, 37, 38, 39, 25, 26]
        for gpio in sensor_gpios:
            mock_esp32.set_sensor_value(gpio, random.random() * 4095)

        iterations = 10  # 10 full sweeps = 100 reads
        start_time = perf_counter()

        for _ in range(iterations):
            for gpio in sensor_gpios:
                response = mock_esp32.handle_command("sensor_read", {"gpio": gpio})
                assert response["status"] == "ok"

        elapsed = perf_counter() - start_time
        total_reads = iterations * len(sensor_gpios)

        assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for {total_reads} reads"

        print(
            f"{total_reads} reads in {elapsed:.3f}s ({total_reads/max(elapsed, 1e-9):.1f} reads/second)"
        )


@pytest.mark.performance
class TestActuatorPerformance:
    """Test actuator control performance."""

    def test_rapid_actuator_toggles(self, mock_esp32):
        """
        Test 50 rapid ON/OFF toggles.

        Performance target: < 1 second for 50 toggles.
        """
        start_time = perf_counter()

        for i in range(50):
            value = i % 2  # Toggle 0/1
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 5, "value": value, "mode": "digital"}
            )
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for 50 toggles"

        print(f"50 actuator toggles: {elapsed:.3f}s ({50/max(elapsed, 1e-9):.1f} toggles/second)")

    def test_pwm_value_changes(self, mock_esp32):
        """
        Test rapid PWM value changes.

        Simulates smooth dimming/speed control.
        """
        start_time = perf_counter()

        # Ramp up: 0.0 → 1.0 in 0.1 steps (11 values)
        for pwm in [i / 10 for i in range(11)]:
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 7, "value": pwm, "mode": "pwm"}
            )
            assert response["status"] == "ok"
            assert response["pwm_value"] == pwm

        # Ramp down: 1.0 → 0.0
        for pwm in [i / 10 for i in range(10, -1, -1)]:
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 7, "value": pwm, "mode": "pwm"}
            )
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        # 22 PWM changes should complete quickly
        assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s"

        print(f"22 PWM changes: {elapsed:.3f}s")

    def test_multiple_actuators_concurrent(self, mock_esp32):
        """
        Test controlling 12 actuators concurrently (ESP32 Dev Board limit).

        Performance target: < 1 second.
        """
        # Setup 12 actuators
        actuator_gpios = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]

        start_time = perf_counter()

        # Turn all ON
        for gpio in actuator_gpios:
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": gpio, "value": 1, "mode": "digital"}
            )
            assert response["status"] == "ok"

        # Turn all OFF
        for gpio in actuator_gpios:
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": gpio, "value": 0, "mode": "digital"}
            )
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        # 24 commands (12 ON + 12 OFF)
        assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for 24 commands"

        print(f"24 actuator commands: {elapsed:.3f}s")


@pytest.mark.performance
class TestMQTTThroughput:
    """Test MQTT message throughput."""

    def test_message_burst(self, mock_esp32):
        """
        Test MQTT message burst performance.

        Performance target: > 100 messages/second.

        Note: With zone configured, each operation publishes multiple messages:
        - sensor_read: 2 messages (primary + zone topic)
        - actuator_set: 2 messages (status + response)
        """
        mock_esp32.clear_published_messages()

        start_time = perf_counter()

        for i in range(100):
            # Sensor reads generate MQTT publishes (2 per read with zone)
            mock_esp32.handle_command("sensor_read", {"gpio": 34})
            # Actuator commands generate MQTT publishes (status + response)
            mock_esp32.handle_command(
                "actuator_set", {"gpio": 5, "value": i % 2, "mode": "digital"}
            )

        elapsed = perf_counter() - start_time

        messages = mock_esp32.get_published_messages()
        # With zone config: sensor_read=2 msgs, actuator_set=2 msgs (status + response)
        # 100 * (2 + 2) = 400 messages
        expected_min = 200  # At minimum
        assert (
            len(messages) >= expected_min
        ), f"Expected at least {expected_min} messages, got {len(messages)}"

        # Throughput: > 100 messages/second
        throughput = len(messages) / elapsed
        assert throughput > 100, f"Too slow: {throughput:.1f} msg/s (need > 100)"

        # Performance target: < 2 seconds
        assert elapsed < 2.0, f"Too slow: {elapsed:.3f}s"

        print(f"{len(messages)} MQTT messages: {elapsed:.3f}s ({throughput:.1f} msg/s)")

    def test_sustained_throughput(self, mock_esp32):
        """
        Test sustained MQTT throughput over 5 seconds.

        Simulates continuous sensor polling + actuator control.
        """
        mock_esp32.clear_published_messages()

        start_time = perf_counter()
        duration = 5.0  # 5 seconds

        count = 0
        while (perf_counter() - start_time) < duration:
            # Alternate sensor read and actuator command
            if count % 2 == 0:
                mock_esp32.handle_command("sensor_read", {"gpio": 34})
            else:
                mock_esp32.handle_command(
                    "actuator_set", {"gpio": 5, "value": count % 2, "mode": "digital"}
                )
            count += 1

        elapsed = perf_counter() - start_time
        messages = mock_esp32.get_published_messages()

        throughput = len(messages) / elapsed

        print(
            f"Sustained throughput: {throughput:.1f} msg/s over {elapsed:.1f}s ({len(messages)} messages)"
        )

        # Should sustain > 50 msg/s
        assert throughput > 50, f"Sustained throughput too low: {throughput:.1f} msg/s"

    def test_large_payload_messages(self, mock_esp32):
        """
        Test handling of larger MQTT payloads.

        Config messages can be larger than sensor/actuator messages.
        """
        start_time = perf_counter()

        # Send 20 config get commands (larger responses)
        for i in range(20):
            response = mock_esp32.handle_command("config_get", {})
            assert response["status"] == "ok"

        elapsed = perf_counter() - start_time

        # Should still be fast despite larger payloads
        assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s"

        print(f"20 config gets: {elapsed:.3f}s")


@pytest.mark.performance
@pytest.mark.slow
class TestSystemLoad:
    """Test system behavior under load."""

    def test_mixed_load(self, mock_esp32):
        """
        Test mixed workload: sensors + actuators + config.

        Simulates realistic system load.
        """
        # Setup sensors
        for gpio in [32, 33, 34, 35]:
            mock_esp32.set_sensor_value(gpio, random.random() * 4095)

        mock_esp32.clear_published_messages()

        start_time = perf_counter()

        # Mixed operations
        operations = 0
        for i in range(50):
            # Read sensors (40% of operations)
            if i % 5 < 2:
                gpio = random.choice([32, 33, 34, 35])
                mock_esp32.handle_command("sensor_read", {"gpio": gpio})
                operations += 1

            # Control actuators (40% of operations)
            elif i % 5 < 4:
                gpio = random.choice([5, 6, 7])
                value = random.choice([0, 1])
                mock_esp32.handle_command(
                    "actuator_set", {"gpio": gpio, "value": value, "mode": "digital"}
                )
                operations += 1

            # Config operations (20% of operations)
            else:
                mock_esp32.handle_command("config_get", {})
                operations += 1

        elapsed = perf_counter() - start_time

        assert operations == 50
        assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for {operations} operations"

        print(f"Mixed load: {operations} operations in {elapsed:.3f}s")

    def test_stress_test_1000_operations(self, mock_esp32):
        """
        Stress test: 1000 rapid operations.

        Performance target: < 10 seconds.
        """
        # Setup
        for gpio in [32, 33, 34]:
            mock_esp32.set_sensor_value(gpio, random.random() * 4095)

        mock_esp32.clear_published_messages()

        start_time = perf_counter()

        for i in range(1000):
            if i % 2 == 0:
                mock_esp32.handle_command("sensor_read", {"gpio": 34})
            else:
                mock_esp32.handle_command(
                    "actuator_set", {"gpio": 5, "value": i % 2, "mode": "digital"}
                )

        elapsed = perf_counter() - start_time

        assert elapsed < 10.0, f"Stress test too slow: {elapsed:.3f}s for 1000 operations"

        throughput = 1000 / elapsed
        print(f"Stress test: 1000 operations in {elapsed:.3f}s ({throughput:.1f} ops/s)")

    def test_emergency_stop_under_load(self, mock_esp32):
        """
        Test emergency stop responsiveness under load.

        Emergency stop must be fast even when system is busy.
        """
        # Setup actuators
        for gpio in [5, 6, 7, 8]:
            mock_esp32.handle_command("actuator_set", {"gpio": gpio, "value": 1, "mode": "digital"})

        # Simulate load
        for i in range(20):
            mock_esp32.handle_command("sensor_read", {"gpio": 34})

        # Emergency stop
        start_time = perf_counter()
        response = mock_esp32.handle_command("emergency_stop", {})
        elapsed = perf_counter() - start_time

        assert response["status"] == "ok"

        # Emergency stop must be FAST (< 50ms even under load)
        assert elapsed < 0.05, f"Emergency stop too slow: {elapsed*1000:.1f}ms"

        # Verify all stopped
        for gpio in [5, 6, 7, 8]:
            actuator = mock_esp32.get_actuator_state(gpio)
            assert actuator is not None
            assert actuator.state is False

        print(f"Emergency stop under load: {elapsed*1000:.1f}ms")


@pytest.mark.performance
class TestResponseTimes:
    """Test command response times."""

    def test_ping_response_time(self, mock_esp32):
        """
        Test ping response time.

        Target: < 50ms (Mock), < 500ms (Real hardware).
        """
        response_times = []

        for _ in range(10):
            start = perf_counter()
            response = mock_esp32.handle_command("ping", {})
            elapsed = perf_counter() - start

            assert response["status"] == "ok"
            response_times.append(elapsed * 1000)  # Convert to ms

        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)

        print(f"Ping times: avg={avg_time:.1f}ms, max={max_time:.1f}ms")

        # Mock should be very fast
        assert avg_time < 50, f"Average ping too slow: {avg_time:.1f}ms"
        assert max_time < 100, f"Max ping too slow: {max_time:.1f}ms"

    def test_actuator_response_time(self, mock_esp32):
        """
        Test actuator command response time.

        Target: < 100ms.
        """
        response_times = []

        for i in range(20):
            start = perf_counter()
            response = mock_esp32.handle_command(
                "actuator_set", {"gpio": 5, "value": i % 2, "mode": "digital"}
            )
            elapsed = perf_counter() - start

            assert response["status"] == "ok"
            response_times.append(elapsed * 1000)

        avg_time = sum(response_times) / len(response_times)

        print(f"Actuator command avg response: {avg_time:.1f}ms")

        assert avg_time < 100, f"Actuator commands too slow: {avg_time:.1f}ms"

    def test_config_get_response_time(self, mock_esp32):
        """
        Test config get response time.

        Config operations can be slower due to NVS access.
        Target: < 200ms.
        """
        response_times = []

        for _ in range(10):
            start = perf_counter()
            response = mock_esp32.handle_command("config_get", {})
            elapsed = perf_counter() - start

            assert response["status"] == "ok"
            response_times.append(elapsed * 1000)

        avg_time = sum(response_times) / len(response_times)

        print(f"Config get avg response: {avg_time:.1f}ms")

        # Config can be slower but should still be reasonable
        assert avg_time < 200, f"Config get too slow: {avg_time:.1f}ms"
