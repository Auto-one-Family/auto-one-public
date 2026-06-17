"""
Cross-ESP Tests - Multi-device orchestration scenarios.

NOTE: Uses REAL MQTT topic structure for authentic routing validation.
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Validation of multi-ESP message routing logic
- Pre-production testing of distributed systems
- Seamless CI/CD → Staging → Production flow

Tests verify:
1. Sensor on ESP-A triggers actuator on ESP-B
2. Broadcast commands affect all ESPs
3. Zone-based orchestration
4. Emergency stop propagation across devices
5. Multi-ESP coordination patterns

Real-world scenarios:
- Greenhouse with separate sensor and actuator ESPs
- Multi-zone irrigation systems
- Distributed environmental monitoring
"""

import pytest
import time


class TestCrossESPOrchestration:
    """Test orchestration across multiple ESP32 devices."""

    def test_sensor_to_actuator_cross_esp(self, multiple_mock_esp32):
        """
        Sensor reading on ESP-002 triggers actuator on ESP-001.

        Real-world scenario: Soil moisture sensor in Field A
        controls irrigation pump in Field B.
        """
        esps = multiple_mock_esp32

        # Read sensor on ESP-002
        sensor_response = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
        assert sensor_response["status"] == "ok"
        moisture = sensor_response["data"]["raw_value"]

        # Decision logic (server-side): If moisture < 2500, activate pump
        if moisture < 2500:
            # Activate pump on ESP-001 (different ESP!)
            pump_response = esps["esp1"].handle_command(
                "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
            )
            assert pump_response["status"] == "ok"
            assert pump_response["state"] is True

            # Verify pump state
            pump_state = esps["esp1"].get_actuator_state(5)
            assert pump_state is not None
            assert pump_state.state is True

    def test_multiple_sensors_single_actuator(self, multiple_mock_esp32):
        """
        Multiple sensors across ESPs control a single actuator.

        Real-world scenario: Temperature sensors in multiple zones
        control a single ventilation fan.
        """
        esps = multiple_mock_esp32

        # Read temperatures from ESP-002 and ESP-003
        temp_esp2 = esps["esp2"].handle_command("sensor_read", {"gpio": 35})
        temp_esp3 = esps["esp3"].handle_command("sensor_read", {"gpio": 35})

        assert temp_esp2["status"] == "ok"
        assert temp_esp3["status"] == "ok"

        avg_temp = (temp_esp2["data"]["raw_value"] + temp_esp3["data"]["raw_value"]) / 2

        # If average temperature > 1700, activate pump on ESP-001
        if avg_temp > 1700:
            fan_response = esps["esp1"].handle_command(
                "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
            )
            assert fan_response["status"] == "ok"

    def test_broadcast_emergency_all_esps(self, multiple_mock_esp32):
        """
        Broadcast emergency stop affects ALL ESPs.

        Validates: kaiser/broadcast/emergency topic routing.
        """
        esps = multiple_mock_esp32

        # Turn on actuators on multiple ESPs
        esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        esps["esp1"].handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        esps["esp3"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Verify actuators are ON
        assert esps["esp1"].get_actuator_state(5).state is True
        assert esps["esp1"].get_actuator_state(6).state is True
        assert esps["esp3"].get_actuator_state(5).state is True

        # Broadcast emergency (simulated)
        for esp in esps.values():
            esp.handle_command("emergency_stop", {})

        # Verify all actuators stopped
        assert esps["esp1"].get_actuator_state(5).state is False
        assert esps["esp1"].get_actuator_state(6).state is False
        assert esps["esp3"].get_actuator_state(5).state is False

    def test_broadcast_emergency_topic_validation(self, multiple_mock_esp32):
        """
        Validate that emergency stop publishes to broadcast topic.

        Validates: kaiser/broadcast/emergency topic structure.
        """
        esps = multiple_mock_esp32

        # Turn on actuators on ESP-001
        esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        esps["esp1"].handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        esps["esp1"].clear_published_messages()

        # Trigger emergency stop
        response = esps["esp1"].handle_command("emergency_stop", {})
        assert response["status"] == "ok"

        # Get published messages
        messages = esps["esp1"].get_published_messages()

        # Verify broadcast emergency topic
        broadcast_messages = [m for m in messages if m["topic"] == "kaiser/broadcast/emergency"]
        assert len(broadcast_messages) == 1, "Should publish to broadcast emergency topic"

        # Verify broadcast message payload
        broadcast_msg = broadcast_messages[0]
        assert broadcast_msg["payload"]["esp_id"] == esps["esp1"].esp_id
        assert "stopped_actuators" in broadcast_msg["payload"]
        assert "timestamp" in broadcast_msg["payload"]

    def test_zone_based_coordination(self, multiple_mock_esp32):
        """
        Zone-based coordination: All ESPs in zone react to condition.

        Real-world scenario: All irrigation pumps in "Zone-A"
        activate when any sensor detects low moisture.
        """
        esps = multiple_mock_esp32

        # Simulate low moisture detection on ESP-002
        moisture = esps["esp2"].handle_command("sensor_read", {"gpio": 34})

        if moisture["data"]["raw_value"] < 2500:
            # Activate all pumps in zone (ESP-001 and ESP-003)
            esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
            esps["esp3"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

            # Verify both pumps activated
            assert esps["esp1"].get_actuator_state(5).state is True
            assert esps["esp3"].get_actuator_state(5).state is True


class TestCrossESPDataFlow:
    """Test data flow and message routing across ESPs."""

    def test_mqtt_message_isolation(self, multiple_mock_esp32):
        """
        Verify MQTT messages are correctly routed to specific ESPs.

        ESP-001 actuator commands should NOT affect ESP-003 actuators.
        """
        esps = multiple_mock_esp32

        esps["esp1"].clear_published_messages()
        esps["esp3"].clear_published_messages()

        # Control actuator on ESP-001
        esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Get published messages
        esp1_messages = esps["esp1"].get_published_messages()
        esp3_messages = esps["esp3"].get_published_messages()

        # Verify ESP-001 published status + response (2 messages)
        actuator_msgs = [m for m in esp1_messages if "/actuator/" in m["topic"]]
        assert len(actuator_msgs) == 2  # status + response
        assert "test-esp-001" in actuator_msgs[0]["topic"]

        # Verify ESP-003 did NOT publish anything
        assert len(esp3_messages) == 0

    def test_concurrent_operations_multiple_esps(self, multiple_mock_esp32):
        """
        Test concurrent operations across multiple ESPs.

        Real-world scenario: Reading sensors and controlling actuators
        simultaneously across all ESPs.
        """
        esps = multiple_mock_esp32

        # Clear messages
        for esp in esps.values():
            esp.clear_published_messages()

        # Concurrent operations
        # ESP-002: Read all sensors
        esps["esp2"].handle_command("sensor_read", {"gpio": 34})
        esps["esp2"].handle_command("sensor_read", {"gpio": 35})
        esps["esp2"].handle_command("sensor_read", {"gpio": 36})

        # ESP-001: Control actuators
        esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        esps["esp1"].handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # ESP-003: Mixed operations
        esps["esp3"].handle_command("sensor_read", {"gpio": 34})
        esps["esp3"].handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # Verify all operations succeeded
        esp2_messages = esps["esp2"].get_published_messages()
        esp1_messages = esps["esp1"].get_published_messages()
        esp3_messages = esps["esp3"].get_published_messages()

        # Count by type
        esp2_sensor_msgs = [m for m in esp2_messages if "/sensor/" in m["topic"]]
        esp1_actuator_msgs = [m for m in esp1_messages if "/actuator/" in m["topic"]]
        esp3_sensor_msgs = [m for m in esp3_messages if "/sensor/" in m["topic"]]
        esp3_actuator_msgs = [m for m in esp3_messages if "/actuator/" in m["topic"]]

        # 3 sensors × 2 (with zone) = 6, actuators × 2 (status + response)
        assert len(esp2_sensor_msgs) == 6  # 3 sensors × 2 (zone topic)
        assert len(esp1_actuator_msgs) == 4  # 2 actuators × 2 (status + response)
        assert len(esp3_sensor_msgs) == 2  # 1 sensor × 2 (zone topic)
        assert len(esp3_actuator_msgs) == 2  # 1 actuator × 2 (status + response)

    def test_message_ordering_across_esps(self, multiple_mock_esp32):
        """
        Test message ordering is preserved per-ESP.

        Messages from same ESP should maintain order.
        """
        esps = multiple_mock_esp32

        esps["esp1"].clear_published_messages()

        # Execute sequence of commands on ESP-001
        commands = [
            {"gpio": 5, "value": 1},
            {"gpio": 6, "value": 1},
            {"gpio": 5, "value": 0},
            {"gpio": 6, "value": 0},
        ]

        for cmd in commands:
            esps["esp1"].handle_command("actuator_set", {**cmd, "mode": "digital"})

        # Verify message order (each command publishes status + response)
        messages = esps["esp1"].get_published_messages()
        status_msgs = [m for m in messages if "/status" in m["topic"]]

        assert len(status_msgs) == 4  # 4 commands × 1 status each

        # Check GPIO order in status topics
        assert "actuator/5/status" in status_msgs[0]["topic"]
        assert "actuator/6/status" in status_msgs[1]["topic"]
        assert "actuator/5/status" in status_msgs[2]["topic"]
        assert "actuator/6/status" in status_msgs[3]["topic"]


class TestCrossESPErrorHandling:
    """Test error handling in multi-ESP scenarios."""

    def test_one_esp_failure_doesnt_affect_others(self, multiple_mock_esp32):
        """
        Failure on one ESP should not affect other ESPs.

        Real-world scenario: Network issue on one ESP shouldn't
        stop other ESPs from functioning.
        """
        esps = multiple_mock_esp32

        # Simulate error on ESP-001 (invalid command)
        response_esp1 = esps["esp1"].handle_command("invalid_command", {})
        assert response_esp1["status"] == "error"

        # ESP-002 and ESP-003 should still work
        response_esp2 = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
        assert response_esp2["status"] == "ok"

        response_esp3 = esps["esp3"].handle_command("sensor_read", {"gpio": 34})
        assert response_esp3["status"] == "ok"

    def test_partial_emergency_stop(self, multiple_mock_esp32):
        """
        Test emergency stop on specific ESP doesn't affect others.

        ESP-specific emergency stop (not broadcast).
        """
        esps = multiple_mock_esp32

        # Turn on actuators on all ESPs
        esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        esps["esp3"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Emergency stop only ESP-001
        esps["esp1"].handle_command("emergency_stop", {})

        # Verify ESP-001 stopped
        assert esps["esp1"].get_actuator_state(5).state is False

        # Verify ESP-003 still running
        assert esps["esp3"].get_actuator_state(5).state is True


class TestRealWorldScenarios:
    """Test real-world greenhouse automation scenarios."""

    def test_greenhouse_irrigation_automation(self, multiple_mock_esp32):
        """
        Complete greenhouse irrigation workflow.

        Scenario:
        1. Sensors on ESP-002 monitor soil moisture
        2. Server decides irrigation needed
        3. Pumps on ESP-001 activate
        4. Flow sensor on ESP-002 confirms water flow
        """
        esps = multiple_mock_esp32

        # Step 1: Read soil moisture
        moisture = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
        assert moisture["status"] == "ok"

        # Step 2: Decision logic
        if moisture["data"]["raw_value"] < 2500:
            # Step 3: Activate pump
            pump = esps["esp1"].handle_command(
                "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
            )
            assert pump["status"] == "ok"

            # Step 4: Check flow sensor (would be updated in real hardware)
            flow = esps["esp2"].handle_command("sensor_read", {"gpio": 36})
            assert flow["status"] == "ok"

    def test_multi_zone_temperature_control(self, multiple_mock_esp32):
        """
        Multi-zone temperature control with coordinated ventilation.

        Scenario:
        1. Temperature sensors on ESP-002 and ESP-003
        2. If any zone > threshold, activate fans
        3. Different fan speeds based on temperature
        """
        esps = multiple_mock_esp32

        # Read temperatures from both zones
        temp_zone1 = esps["esp2"].handle_command("sensor_read", {"gpio": 35})
        temp_zone2 = esps["esp3"].handle_command("sensor_read", {"gpio": 35})

        assert temp_zone1["status"] == "ok"
        assert temp_zone2["status"] == "ok"

        max_temp = max(temp_zone1["data"]["raw_value"], temp_zone2["data"]["raw_value"])

        # Control ventilation based on max temperature
        if max_temp > 1700:
            # High temperature - full speed
            fan = esps["esp1"].handle_command(
                "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
            )
            assert fan["status"] == "ok"
        elif max_temp > 1600:
            # Medium temperature - half speed (if PWM available)
            pass  # Would use PWM in real scenario


@pytest.mark.performance
class TestCrossESPPerformance:
    """Test performance characteristics of multi-ESP orchestration."""

    def test_concurrent_sensor_reads(self, multiple_mock_esp32):
        """
        Test reading sensors from multiple ESPs concurrently.

        Performance target: All reads complete in < 1 second.
        """
        esps = multiple_mock_esp32

        start_time = time.time()

        # Read sensors from all ESPs
        results = []
        results.append(esps["esp2"].handle_command("sensor_read", {"gpio": 34}))
        results.append(esps["esp2"].handle_command("sensor_read", {"gpio": 35}))
        results.append(esps["esp2"].handle_command("sensor_read", {"gpio": 36}))
        results.append(esps["esp3"].handle_command("sensor_read", {"gpio": 34}))
        results.append(esps["esp3"].handle_command("sensor_read", {"gpio": 35}))

        elapsed = time.time() - start_time

        # All reads succeeded
        assert all(r["status"] == "ok" for r in results)

        # Performance target
        assert elapsed < 1.0, f"Concurrent reads too slow: {elapsed:.3f}s"

    def test_rapid_cross_esp_coordination(self, multiple_mock_esp32):
        """
        Test rapid coordination between ESPs.

        Simulates fast sensor-to-actuator responses.
        """
        esps = multiple_mock_esp32

        start_time = time.time()

        # 10 rapid sensor → actuator cycles
        for i in range(10):
            # Read sensor
            sensor = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
            assert sensor["status"] == "ok"

            # Control actuator
            value = i % 2  # Toggle
            actuator = esps["esp1"].handle_command(
                "actuator_set", {"gpio": 5, "value": value, "mode": "digital"}
            )
            assert actuator["status"] == "ok"

        elapsed = time.time() - start_time

        # Performance target: 10 cycles in < 2 seconds
        assert elapsed < 2.0, f"Coordination too slow: {elapsed:.3f}s"
