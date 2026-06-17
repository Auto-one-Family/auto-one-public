"""
Scale Multi-Device Tests (SCALE Category).

Tests device fleet isolation, zone-based orchestration, and broadcast emergency
across many MockESP32Clients.

Pattern: MockESP32Client (synchron), inline fixtures.
"""

import pytest

from tests.esp32.mocks.mock_esp32_client import MockESP32Client

# =========================================================================
# Fleet Device Isolation
# =========================================================================


class TestFleetIsolation:
    """10 ESPs with independent state - no cross-contamination."""

    @pytest.fixture
    def fleet(self):
        """10 ESPs, each with a sensor and actuator."""
        esps = []
        for i in range(10):
            esp = MockESP32Client(esp_id=f"ESP_FLEET{i:04d}")
            esp.configure_zone(f"zone_{i}", "main_zone")
            esp.configure_actuator(gpio=25, actuator_type="pump", name=f"Pump {i}")
            esp.set_sensor_value(
                gpio=34, raw_value=20.0 + i, sensor_type="DS18B20", name=f"Temp {i}"
            )
            esp.clear_published_messages()
            esps.append(esp)
        yield esps
        for esp in esps:
            esp.reset()

    def test_sensor_values_independent(self, fleet):
        """Each ESP has its own sensor value."""
        for i, esp in enumerate(fleet):
            result = esp.handle_command("sensor_read", {"gpio": 34})
            assert result["status"] == "ok"
            assert result["data"]["raw_value"] == 20.0 + i

    def test_actuator_state_independent(self, fleet):
        """Controlling one ESP's actuator doesn't affect others."""
        # Turn on only ESP 3
        fleet[3].handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})

        # ESP 3 is on
        assert fleet[3].get_actuator_state(25).state is True

        # All others remain off
        for i, esp in enumerate(fleet):
            if i != 3:
                assert esp.get_actuator_state(25).state is False, f"ESP {i} should be off"

    def test_emergency_stop_only_affects_target(self, fleet):
        """Emergency stop on one ESP doesn't stop others."""
        # Activate all
        for esp in fleet:
            esp.handle_command("actuator_set", {"gpio": 25, "value": 0.7, "mode": "pwm"})

        # Emergency stop only ESP 5
        fleet[5].handle_command("emergency_stop", {"reason": "test"})

        # ESP 5 stopped
        assert fleet[5].get_actuator_state(25).pwm_value == 0.0
        assert fleet[5].get_actuator_state(25).emergency_stopped is True

        # All others still active
        for i, esp in enumerate(fleet):
            if i != 5:
                assert (
                    esp.get_actuator_state(25).pwm_value == 0.7
                ), f"ESP {i} should still be at 0.7"
                assert esp.get_actuator_state(25).emergency_stopped is False

    def test_published_messages_isolated_per_device(self, fleet):
        """MQTT messages are only in the publishing device's history."""
        fleet[0].handle_command("sensor_read", {"gpio": 34})
        fleet[1].handle_command("sensor_read", {"gpio": 34})

        msgs_0 = fleet[0].get_published_messages()
        msgs_1 = fleet[1].get_published_messages()

        # Each ESP only has its own messages
        for msg in msgs_0:
            assert fleet[0].esp_id in msg["topic"]
        for msg in msgs_1:
            assert fleet[1].esp_id in msg["topic"]

    def test_10_esps_all_unique_ids(self, fleet):
        """All ESPs have unique IDs."""
        ids = [esp.esp_id for esp in fleet]
        assert len(set(ids)) == 10


# =========================================================================
# Zone-Based Orchestration
# =========================================================================


class TestZoneOrchestration:
    """ESPs in different zones with zone-based topic routing."""

    @pytest.fixture
    def zone_fleet(self):
        """3 ESPs in 2 different zones."""
        esp_a1 = MockESP32Client(esp_id="ESP_ZA001")
        esp_a1.configure_zone("greenhouse_a", "main_zone")
        esp_a1.set_sensor_value(gpio=34, raw_value=28.0, sensor_type="DS18B20")
        esp_a1.configure_actuator(gpio=25, actuator_type="fan")

        esp_a2 = MockESP32Client(esp_id="ESP_ZA002")
        esp_a2.configure_zone("greenhouse_a", "main_zone")
        esp_a2.configure_actuator(gpio=25, actuator_type="pump")

        esp_b1 = MockESP32Client(esp_id="ESP_ZB001")
        esp_b1.configure_zone("greenhouse_b", "secondary_zone")
        esp_b1.set_sensor_value(gpio=34, raw_value=22.0, sensor_type="DS18B20")
        esp_b1.configure_actuator(gpio=25, actuator_type="valve")

        for esp in [esp_a1, esp_a2, esp_b1]:
            esp.clear_published_messages()

        yield {"a1": esp_a1, "a2": esp_a2, "b1": esp_b1}
        for esp in [esp_a1, esp_a2, esp_b1]:
            esp.reset()

    def test_sensor_topics_contain_correct_esp_id(self, zone_fleet):
        """Sensor data topics include the publishing ESP's ID."""
        zone_fleet["a1"].handle_command("sensor_read", {"gpio": 34})
        zone_fleet["b1"].handle_command("sensor_read", {"gpio": 34})

        msgs_a1 = zone_fleet["a1"].get_published_messages()
        msgs_b1 = zone_fleet["b1"].get_published_messages()

        assert any("ESP_ZA001" in m["topic"] for m in msgs_a1)
        assert any("ESP_ZB001" in m["topic"] for m in msgs_b1)

    def test_actuator_commands_target_correct_esp(self, zone_fleet):
        """Actuator commands only affect the target ESP."""
        zone_fleet["a1"].handle_command("actuator_set", {"gpio": 25, "value": 0.8, "mode": "pwm"})

        assert zone_fleet["a1"].get_actuator_state(25).pwm_value == 0.8
        assert zone_fleet["a2"].get_actuator_state(25).state is False
        assert zone_fleet["b1"].get_actuator_state(25).state is False

    def test_cross_zone_devices_independent(self, zone_fleet):
        """Devices in different zones don't interfere."""
        zone_fleet["a1"].handle_command("emergency_stop", {"reason": "zone_a_issue"})

        # Zone A ESP stopped
        assert zone_fleet["a1"].get_actuator_state(25).emergency_stopped is True

        # Zone A other ESP unaffected (per-device isolation)
        assert zone_fleet["a2"].get_actuator_state(25).emergency_stopped is False

        # Zone B unaffected
        assert zone_fleet["b1"].get_actuator_state(25).emergency_stopped is False


# =========================================================================
# Fleet Emergency Broadcast
# =========================================================================


class TestFleetEmergencyBroadcast:
    """Emergency broadcast across all devices in a fleet."""

    @pytest.fixture
    def active_fleet(self):
        """10 ESPs all with active actuators."""
        esps = []
        for i in range(10):
            esp = MockESP32Client(esp_id=f"ESP_BCAST{i:04d}")
            esp.configure_zone("broadcast_zone", "main_zone")
            esp.configure_actuator(gpio=25, actuator_type="pump")
            esp.configure_actuator(gpio=26, actuator_type="valve")
            esp.handle_command("actuator_set", {"gpio": 25, "value": 0.7, "mode": "pwm"})
            esp.handle_command("actuator_set", {"gpio": 26, "value": 1, "mode": "digital"})
            esp.clear_published_messages()
            esps.append(esp)
        yield esps
        for esp in esps:
            esp.reset()

    def test_emergency_all_devices_stopped(self, active_fleet):
        """Emergency stop on each device stops all its actuators."""
        for esp in active_fleet:
            esp.handle_command("emergency_stop", {"reason": "broadcast_test"})

        for i, esp in enumerate(active_fleet):
            assert esp.get_actuator_state(25).pwm_value == 0.0, f"ESP {i} pump should be off"
            assert esp.get_actuator_state(26).state is False, f"ESP {i} valve should be off"
            assert esp.get_actuator_state(25).emergency_stopped is True
            assert esp.get_actuator_state(26).emergency_stopped is True

    def test_emergency_publishes_broadcast_topic(self, active_fleet):
        """Each ESP publishes to broadcast/emergency topic."""
        for esp in active_fleet:
            esp.handle_command("emergency_stop", {"reason": "test"})

        for esp in active_fleet:
            messages = esp.get_published_messages()
            broadcast_msgs = [m for m in messages if "broadcast/emergency" in m["topic"]]
            assert len(broadcast_msgs) >= 1, f"{esp.esp_id} should publish broadcast emergency"

    def test_fleet_recovery_after_broadcast_emergency(self, active_fleet):
        """All devices can recover after emergency."""
        # Stop all
        for esp in active_fleet:
            esp.handle_command("emergency_stop", {"reason": "test"})

        # Clear all
        for esp in active_fleet:
            esp.handle_command("clear_emergency", {})

        # All can accept commands again
        for esp in active_fleet:
            result = esp.handle_command("actuator_set", {"gpio": 25, "value": 0.5, "mode": "pwm"})
            assert result["status"] == "ok"
            assert esp.get_actuator_state(25).pwm_value == 0.5
