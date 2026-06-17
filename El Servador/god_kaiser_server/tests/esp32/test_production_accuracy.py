"""
Production Accuracy Tests - Validates MockESP32Client matches El Trabajante exactly.

These tests ensure the mock implementation produces IDENTICAL behavior to the
real ESP32 firmware, including:
1. Complete MQTT payload structure (all fields)
2. Zone management and subzone topics
3. Multi-value sensors (SHT31 temp+humidity)
4. System state machine (12 states)
5. Actuator response/alert topics
6. Batch sensor publishing
7. Library management system
8. Complete heartbeat with system metrics
9. Bidirectional config topics

Reference: El Trabajante/docs/Mqtt_Protocoll.md
"""

import pytest
import time

from .mocks.mock_esp32_client import MockESP32Client, SystemState


# =============================================================================
# Test 1: Complete MQTT Payload Structure
# =============================================================================
class TestMQTTPayloadStructure:
    """Validate MQTT payloads match Mqtt_Protocoll.md specification."""

    def test_sensor_data_payload_has_all_required_fields(self, mock_esp32_with_sensors):
        """Sensor payload must include all required fields from spec."""
        mock = mock_esp32_with_sensors

        # Configure sensor with all fields
        mock.set_sensor_value(
            gpio=34,
            raw_value=23.5,
            sensor_type="DS18B20",
            name="Boden Temp",
            unit="°C",
            quality="good",
            library_name="dallas_temp",
        )

        mock.clear_published_messages()
        mock.handle_command("sensor_read", {"gpio": 34})

        messages = mock.get_published_messages()
        assert len(messages) >= 1

        payload = messages[0]["payload"]

        # Required fields from Mqtt_Protocoll.md
        assert "ts" in payload, "Missing timestamp (ts)"
        assert "esp_id" in payload, "Missing esp_id"
        assert "gpio" in payload, "Missing gpio"
        assert "sensor_type" in payload, "Missing sensor_type"
        assert "raw" in payload, "Missing raw value"
        assert "value" in payload, "Missing processed value"
        assert "unit" in payload, "Missing unit"
        assert "quality" in payload, "Missing quality"
        assert "sensor_name" in payload, "Missing sensor_name"
        assert "raw_mode" in payload, "Missing raw_mode flag"

        # Verify correct values
        assert payload["esp_id"] == mock.esp_id
        assert payload["gpio"] == 34
        assert payload["sensor_type"] == "DS18B20"
        assert payload["raw"] == 23.5
        assert payload["unit"] == "°C"
        assert payload["quality"] == "good"
        assert payload["sensor_name"] == "Boden Temp"

    def test_sensor_payload_includes_library_info(self, mock_esp32):
        """Sensor payload includes library metadata when configured."""
        mock_esp32.set_sensor_value(
            gpio=4,
            raw_value=24.0,
            sensor_type="DS18B20",
            library_name="dallas_temp",
            name="Test Sensor",
        )

        mock_esp32.clear_published_messages()
        mock_esp32.handle_command("sensor_read", {"gpio": 4})

        payload = mock_esp32.get_published_messages()[0]["payload"]

        assert "library_name" in payload
        assert payload["library_name"] == "dallas_temp"
        assert "library_version" in payload

    def test_sensor_payload_includes_calibration_metadata(self, mock_esp32):
        """Sensor payload includes calibration in meta when configured."""
        mock_esp32.set_sensor_value(
            gpio=4,
            raw_value=24.0,
            sensor_type="DS18B20",
            calibration={"offset": 0.5, "multiplier": 1.0},
            name="Calibrated Sensor",
        )

        mock_esp32.clear_published_messages()
        mock_esp32.handle_command("sensor_read", {"gpio": 4})

        payload = mock_esp32.get_published_messages()[0]["payload"]

        assert "meta" in payload
        assert "calibration" in payload["meta"]
        assert payload["meta"]["calibration"]["offset"] == 0.5

    def test_actuator_status_payload_has_all_fields(self, mock_esp32_with_actuators):
        """Actuator status payload must include all required fields."""
        mock = mock_esp32_with_actuators
        mock.clear_published_messages()

        mock.handle_command(
            "actuator_set",
            {"gpio": 5, "value": 1, "mode": "digital", "type": "pump", "name": "Test Pump"},
        )

        messages = mock.get_messages_by_topic_pattern("actuator/5/status")
        assert len(messages) == 1

        payload = messages[0]["payload"]

        # Required fields
        assert "ts" in payload
        assert "esp_id" in payload
        assert "gpio" in payload
        assert "type" in payload
        assert "name" in payload
        assert "state" in payload
        assert "pwm_value" in payload
        assert "target_value" in payload
        assert "emergency_stopped" in payload
        assert "last_command" in payload


# =============================================================================
# Test 2: Zone Management
# =============================================================================
class TestZoneManagement:
    """Validate zone configuration and zone-based topics."""

    def test_zone_configuration(self, mock_esp32):
        """ESP32 can be configured with zone information."""
        mock_esp32.configure_zone(
            zone_id="greenhouse",
            master_zone_id="main-greenhouse",
            subzone_id="zone-a",
            zone_name="Greenhouse Section",
            subzone_name="Zone A - Tomatoes",
        )

        assert mock_esp32.zone is not None
        assert mock_esp32.zone.zone_id == "greenhouse"
        assert mock_esp32.zone.master_zone_id == "main-greenhouse"
        assert mock_esp32.zone.subzone_id == "zone-a"

    def test_zone_topic_prefix(self, mock_esp32_with_zones):
        """Zone-based topic prefix is correctly generated."""
        prefix = mock_esp32_with_zones.get_zone_topic_prefix()

        assert prefix is not None
        assert "zone/main-greenhouse" in prefix
        assert "subzone/zone-a" in prefix
        assert mock_esp32_with_zones.esp_id in prefix

    def test_sensor_publishes_to_zone_topic(self, mock_esp32_with_zones):
        """Sensor data is published to zone-based topic when configured."""
        mock = mock_esp32_with_zones
        mock.clear_published_messages()

        mock.handle_command("sensor_read", {"gpio": 4})

        messages = mock.get_published_messages()

        # Should have both standard and zone-based topics
        standard_topics = [m for m in messages if "/zone/" not in m["topic"]]
        zone_topics = [m for m in messages if "/zone/" in m["topic"]]

        assert len(standard_topics) >= 1, "Missing standard sensor topic"
        assert len(zone_topics) >= 1, "Missing zone-based sensor topic"

        # Verify zone topic structure
        zone_topic = zone_topics[0]["topic"]
        assert "kaiser/god/zone/main-greenhouse" in zone_topic
        assert f"esp/{mock.esp_id}" in zone_topic
        assert "subzone/zone-a" in zone_topic

    def test_zone_in_heartbeat(self, mock_esp32_with_zones):
        """Heartbeat includes zone information."""
        response = mock_esp32_with_zones.handle_command("ping", {})

        assert response["zone_id"] == "greenhouse"
        assert response["master_zone_id"] == "main-greenhouse"
        assert response["zone_assigned"] is True


# =============================================================================
# Test 3: Multi-Value Sensors (SHT31)
# =============================================================================
class TestMultiValueSensors:
    """Validate multi-value sensors like SHT31 (temp + humidity)."""

    def test_sht31_multi_value_configuration(self, mock_esp32_with_sht31):
        """SHT31 can be configured with temperature and humidity."""
        mock = mock_esp32_with_sht31
        sensor = mock.sensors.get(21)

        assert sensor is not None
        assert sensor.is_multi_value is True
        assert sensor.secondary_values is not None
        assert "humidity" in sensor.secondary_values
        assert sensor.secondary_values["humidity"] == 65.2

    def test_sht31_primary_value_reading(self, mock_esp32_with_sht31):
        """SHT31 primary value (temperature) is read correctly."""
        response = mock_esp32_with_sht31.handle_command("sensor_read", {"gpio": 21})

        assert response["status"] == "ok"
        assert response["data"]["raw_value"] == 23.5
        assert response["data"]["type"] == "SHT31"

    def test_sht31_secondary_values_in_response(self, mock_esp32_with_sht31):
        """SHT31 response includes secondary values."""
        response = mock_esp32_with_sht31.handle_command("sensor_read", {"gpio": 21})

        assert "secondary_values" in response["data"]
        assert "humidity" in response["data"]["secondary_values"]
        assert response["data"]["secondary_values"]["humidity"] == 65.2

    def test_multi_value_sensor_batch_reading(self, mock_esp32_with_sht31):
        """Batch reading includes multi-value sensor data."""
        response = mock_esp32_with_sht31.handle_command("sensor_batch", {})

        assert response["status"] == "ok"
        sensors = response["data"]["sensors"]

        sht31_reading = next((s for s in sensors if s["type"] == "SHT31"), None)
        assert sht31_reading is not None
        assert "secondary_values" in sht31_reading


# =============================================================================
# Test 4: System State Machine
# =============================================================================
class TestSystemStateMachine:
    """Validate 12-state system state machine from Mqtt_Protocoll.md."""

    def test_initial_state_is_operational(self, mock_esp32):
        """New ESP32 starts in OPERATIONAL state."""
        assert mock_esp32.system_state == SystemState.OPERATIONAL

    def test_all_states_exist(self):
        """All 12 states from spec exist."""
        expected_states = [
            "BOOT",
            "WIFI_SETUP",
            "WIFI_CONNECTED",
            "MQTT_CONNECTING",
            "MQTT_CONNECTED",
            "AWAITING_USER_CONFIG",
            "ZONE_CONFIGURED",
            "SENSORS_CONFIGURED",
            "OPERATIONAL",
            "LIBRARY_DOWNLOADING",
            "SAFE_MODE",
            "ERROR",
        ]

        actual_states = [s.name for s in SystemState]

        for expected in expected_states:
            assert expected in actual_states, f"Missing state: {expected}"

    def test_safe_mode_transition(self, mock_esp32_safe_mode):
        """ESP32 can transition to SAFE_MODE."""
        mock = mock_esp32_safe_mode

        # Turn on actuators
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert mock.get_actuator_state(5).state is True

        # Enter safe mode
        mock.enter_safe_mode("test_reason")

        assert mock.system_state == SystemState.SAFE_MODE
        assert mock.get_actuator_state(5).state is False
        assert mock.get_actuator_state(5).emergency_stopped is True

    def test_safe_mode_exit(self, mock_esp32_safe_mode):
        """ESP32 can exit SAFE_MODE."""
        mock = mock_esp32_safe_mode

        mock.enter_safe_mode("test")
        assert mock.system_state == SystemState.SAFE_MODE

        mock.exit_safe_mode()
        assert mock.system_state == SystemState.OPERATIONAL
        assert mock.get_actuator_state(5).emergency_stopped is False

    def test_safe_mode_publishes_status(self, mock_esp32_safe_mode):
        """Entering SAFE_MODE publishes status message."""
        mock = mock_esp32_safe_mode
        mock.clear_published_messages()

        mock.enter_safe_mode("critical_error")

        safe_mode_msgs = mock.get_messages_by_topic_pattern("safe_mode")
        assert len(safe_mode_msgs) == 1

        payload = safe_mode_msgs[0]["payload"]
        assert payload["safe_mode"] is True
        assert payload["reason"] == "critical_error"

    def test_actuator_rejected_in_safe_mode(self, mock_esp32_safe_mode):
        """Actuator commands are rejected in SAFE_MODE."""
        mock = mock_esp32_safe_mode
        mock.enter_safe_mode("test")

        response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        assert response["status"] == "error"
        assert "SAFE_MODE" in response["error"]

    def test_state_change_publishes_diagnostics(self, mock_esp32):
        """State transitions publish diagnostics."""
        mock_esp32.clear_published_messages()

        mock_esp32.enter_safe_mode("test")

        diag_msgs = mock_esp32.get_messages_by_topic_pattern("diagnostics")
        assert len(diag_msgs) >= 1

        state_change = next((m for m in diag_msgs if "state_change" in str(m["payload"])), None)
        assert state_change is not None


# =============================================================================
# Test 5: Actuator Response/Alert Topics
# =============================================================================
class TestActuatorResponseAlertTopics:
    """Validate actuator response and alert topic publishing."""

    def test_actuator_command_publishes_response(self, mock_esp32_with_actuators):
        """Actuator command publishes to response topic."""
        mock = mock_esp32_with_actuators
        mock.clear_published_messages()

        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        response_msgs = mock.get_messages_by_topic_pattern("actuator/5/response")
        assert len(response_msgs) == 1

        payload = response_msgs[0]["payload"]
        assert "command_id" in payload
        assert payload["success"] is True
        assert "message" in payload

    def test_emergency_stop_publishes_alerts(self, mock_esp32_with_actuators):
        """Emergency stop publishes alert for each actuator."""
        mock = mock_esp32_with_actuators

        # Turn on actuators
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        mock.clear_published_messages()

        mock.handle_command("emergency_stop", {})

        alert_msgs = mock.get_messages_by_topic_pattern("/alert")
        assert len(alert_msgs) >= 2  # One for each actuator

        for alert in alert_msgs:
            assert alert["payload"]["alert_type"] == "emergency_stop"
            assert alert["payload"]["severity"] == "critical"

    def test_safe_mode_publishes_alert(self, mock_esp32_safe_mode):
        """Safe mode command rejection publishes alert."""
        mock = mock_esp32_safe_mode
        mock.enter_safe_mode("test")
        mock.clear_published_messages()

        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        alert_msgs = mock.get_messages_by_topic_pattern("/alert")
        assert len(alert_msgs) >= 1

        payload = alert_msgs[0]["payload"]
        assert payload["alert_type"] == "safe_mode"


# =============================================================================
# Test 6: Batch Sensor Publishing
# =============================================================================
class TestBatchSensorPublishing:
    """Validate batch sensor publishing."""

    def test_sensor_batch_command(self, mock_esp32_with_sensors):
        """sensor_batch command reads all sensors."""
        mock = mock_esp32_with_sensors

        response = mock.handle_command("sensor_batch", {})

        assert response["status"] == "ok"
        assert "sensors" in response["data"]
        assert len(response["data"]["sensors"]) == 3  # 3 pre-configured sensors

    def test_batch_publishes_to_batch_topic(self, mock_esp32_with_sensors):
        """Batch read publishes to sensor/batch topic."""
        mock = mock_esp32_with_sensors
        mock.clear_published_messages()

        mock.handle_command("sensor_batch", {})

        batch_msgs = mock.get_messages_by_topic_pattern("sensor/batch")
        assert len(batch_msgs) == 1

        payload = batch_msgs[0]["payload"]
        assert "sensors" in payload
        assert len(payload["sensors"]) == 3

    def test_batch_payload_includes_all_sensor_fields(self, mock_esp32_with_sensors):
        """Batch payload includes complete sensor data."""
        mock = mock_esp32_with_sensors
        mock.clear_published_messages()

        mock.handle_command("sensor_batch", {})

        batch_msgs = mock.get_messages_by_topic_pattern("sensor/batch")
        sensors = batch_msgs[0]["payload"]["sensors"]

        for sensor in sensors:
            assert "gpio" in sensor
            assert "type" in sensor
            assert "raw_value" in sensor
            assert "quality" in sensor


# =============================================================================
# Test 7: Library Management System
# =============================================================================
class TestLibrarySystem:
    """Validate library management system."""

    def test_library_install(self, mock_esp32):
        """Library can be installed."""
        response = mock_esp32.handle_command(
            "library_install", {"name": "dallas_temp", "version": "1.2.0", "sensor_type": "DS18B20"}
        )

        assert response["status"] == "ok"
        assert response["data"]["installed"] is True

    def test_library_install_publishes_events(self, mock_esp32):
        """Library install publishes ready and installed events."""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command(
            "library_install", {"name": "sht31_driver", "version": "2.0.0", "sensor_type": "SHT31"}
        )

        ready_msgs = mock_esp32.get_messages_by_topic_pattern("library/ready")
        installed_msgs = mock_esp32.get_messages_by_topic_pattern("library/installed")

        assert len(ready_msgs) == 1
        assert len(installed_msgs) == 1

        assert ready_msgs[0]["payload"]["library_name"] == "sht31_driver"

    def test_library_list(self, mock_esp32):
        """Installed libraries can be listed."""
        # Install some libraries
        mock_esp32.handle_command(
            "library_install", {"name": "lib1", "version": "1.0", "sensor_type": "test"}
        )
        mock_esp32.handle_command(
            "library_install", {"name": "lib2", "version": "2.0", "sensor_type": "test"}
        )

        response = mock_esp32.handle_command("library_list", {})

        assert response["status"] == "ok"
        assert "lib1" in response["data"]["libraries"]
        assert "lib2" in response["data"]["libraries"]

    def test_library_download_state_transition(self, mock_esp32):
        """Library download triggers state transition."""
        states_during_install = []

        def track_state(old_state, new_state):
            states_during_install.append(new_state)

        mock_esp32.on_state_change = track_state

        mock_esp32.handle_command(
            "library_install", {"name": "test_lib", "version": "1.0", "sensor_type": "test"}
        )

        # Should have transitioned through LIBRARY_DOWNLOADING
        assert SystemState.LIBRARY_DOWNLOADING in states_during_install


# =============================================================================
# Test 8: Complete Heartbeat Fields
# =============================================================================
class TestCompleteHeartbeat:
    """Validate heartbeat includes all fields from Mqtt_Protocoll.md."""

    def test_heartbeat_has_all_required_fields(self, mock_esp32_with_zones):
        """Heartbeat includes all required fields."""
        mock = mock_esp32_with_zones
        mock.clear_published_messages()

        mock.handle_command("ping", {})

        heartbeat_msgs = mock.get_messages_by_topic_pattern("system/heartbeat")
        assert len(heartbeat_msgs) == 1

        payload = heartbeat_msgs[0]["payload"]

        # Required fields from Mqtt_Protocoll.md
        assert "esp_id" in payload
        assert "zone_id" in payload
        assert "master_zone_id" in payload
        assert "zone_assigned" in payload
        assert "ts" in payload
        assert "uptime" in payload
        assert "heap_free" in payload
        assert "wifi_rssi" in payload
        assert "sensor_count" in payload
        assert "actuator_count" in payload
        assert "state" in payload
        assert "mqtt_connected" in payload
        assert "safe_mode" in payload

    def test_heartbeat_values_correct(self, mock_esp32_greenhouse):
        """Heartbeat values reflect actual ESP32 state."""
        mock = mock_esp32_greenhouse
        response = mock.handle_command("ping", {})

        assert response["sensor_count"] == 3  # DS18B20, SHT31, moisture
        assert response["actuator_count"] == 3  # pump, valve, fan
        assert response["zone_assigned"] is True
        assert response["state"] == "OPERATIONAL"

    def test_wifi_rssi_simulation(self, mock_esp32):
        """WiFi RSSI can be simulated."""
        mock_esp32.simulate_wifi_rssi_change(-75)

        response = mock_esp32.handle_command("ping", {})

        assert response["wifi_rssi"] == -75

    def test_heap_simulation(self, mock_esp32):
        """Heap memory can be simulated."""
        mock_esp32.simulate_heap_change(150000)

        response = mock_esp32.handle_command("ping", {})

        assert response["heap_free"] == 150000


# =============================================================================
# Test 9: Bidirectional Config Topics
# =============================================================================
class TestBidirectionalConfig:
    """Validate bidirectional config topic publishing."""

    def test_config_set_publishes_update(self, mock_esp32):
        """config_set publishes to config topic."""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("config_set", {"key": "measurement_interval", "value": 60})

        config_msgs = mock_esp32.get_messages_by_topic_pattern("/config")
        assert len(config_msgs) == 1

        payload = config_msgs[0]["payload"]
        assert payload["key"] == "measurement_interval"
        assert payload["value"] == 60
        assert payload["action"] == "updated"

    def test_config_retained(self, mock_esp32):
        """Config messages are retained."""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("config_set", {"key": "test_config", "value": "test_value"})

        config_msgs = mock_esp32.get_messages_by_topic_pattern("/config")
        assert config_msgs[0]["retain"] is True


# =============================================================================
# Test 10: System Commands
# =============================================================================
class TestSystemCommands:
    """Validate system-level commands."""

    def test_reboot_command(self, mock_esp32):
        """Reboot command resets uptime."""
        # Let some time pass
        time.sleep(0.1)

        original_boot = mock_esp32.boot_time

        mock_esp32.handle_command("system_command", {"action": "reboot"})

        assert mock_esp32.boot_time > original_boot

    def test_factory_reset_command(self, mock_esp32_greenhouse):
        """Factory reset clears all configuration."""
        mock = mock_esp32_greenhouse

        assert len(mock.sensors) > 0
        assert len(mock.actuators) > 0
        assert mock.zone is not None

        mock.handle_command("system_command", {"action": "factory_reset"})

        assert len(mock.sensors) == 0
        assert len(mock.actuators) == 0
        assert mock.zone is None
        assert mock.system_state == SystemState.WIFI_SETUP

    def test_diagnostics_command(self, mock_esp32_greenhouse):
        """Diagnostics returns complete system info."""
        response = mock_esp32_greenhouse.handle_command("diagnostics", {})

        assert response["status"] == "ok"
        data = response["data"]

        assert "esp_id" in data
        assert "state" in data
        assert "uptime" in data
        assert "heap_free" in data
        assert "heap_total" in data
        assert "wifi_rssi" in data
        assert "sensor_count" in data
        assert "actuator_count" in data
        assert "library_count" in data
        assert "zone_configured" in data
        assert "firmware_version" in data

    def test_diagnostics_publishes_to_topic(self, mock_esp32):
        """Diagnostics publishes to system/diagnostics topic."""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("diagnostics", {})

        diag_msgs = mock_esp32.get_messages_by_topic_pattern("system/diagnostics")
        assert len(diag_msgs) == 1


# =============================================================================
# Test 11: Complete Greenhouse Workflow
# =============================================================================
class TestGreenhouseWorkflow:
    """End-to-end greenhouse automation workflow."""

    def test_complete_greenhouse_cycle(self, mock_esp32_greenhouse):
        """Complete sensor → logic → actuator cycle with all features."""
        mock = mock_esp32_greenhouse
        mock.clear_published_messages()

        # 1. Read all sensors (batch)
        batch_response = mock.handle_command("sensor_batch", {})
        assert batch_response["status"] == "ok"

        sensors = {s["gpio"]: s for s in batch_response["data"]["sensors"]}

        # 2. Get SHT31 multi-value data
        sht31 = sensors[21]
        temp = sht31["raw_value"]
        humidity = sht31["secondary_values"]["humidity"]

        # 3. Get moisture
        moisture = sensors[34]["raw_value"]

        # 4. Decision logic
        if moisture < 2000:
            # Irrigation needed
            pump_response = mock.handle_command(
                "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
            )
            assert pump_response["status"] == "ok"

        if temp > 24:
            # Ventilation needed (PWM based on temp)
            fan_speed = min(1.0, (temp - 20) / 20)
            fan_response = mock.handle_command(
                "actuator_set", {"gpio": 7, "value": fan_speed, "mode": "pwm"}
            )
            assert fan_response["status"] == "ok"

        if humidity > 80:
            # Open ventilation valve
            valve_response = mock.handle_command(
                "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
            )
            assert valve_response["status"] == "ok"

        # 5. Verify MQTT messages
        messages = mock.get_published_messages()

        # Should have: batch, sensor/batch topic, actuator statuses, responses
        batch_msgs = mock.get_messages_by_topic_pattern("sensor/batch")
        status_msgs = mock.get_messages_by_topic_pattern("actuator")

        assert len(batch_msgs) >= 1
        assert len(status_msgs) >= 2  # At least pump and fan

        # 6. Verify zone topics
        zone_msgs = mock.get_messages_by_topic_pattern("/zone/")
        assert len(zone_msgs) >= 1  # Zone-based sensor publishing


# =============================================================================
# Test 12: Cross-ESP with Zones
# =============================================================================
class TestCrossESPWithZones:
    """Test cross-ESP communication with zone management."""

    def test_zone_based_coordination(self, multiple_mock_esp32_with_zones):
        """Sensors in zone-a control actuators in zone-a."""
        esps = multiple_mock_esp32_with_zones

        # Read temperature from Zone A sensors
        sensor_esp = esps["zone_a_sensors"]
        temp_response = sensor_esp.handle_command("sensor_read", {"gpio": 4})
        temp = temp_response["data"]["raw_value"]

        # Control Zone A actuators based on temperature
        actuator_esp = esps["zone_a_actuators"]
        if temp > 23:
            fan_response = actuator_esp.handle_command(
                "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
            )
            assert fan_response["status"] == "ok"

        # Verify Zone A actuator is ON
        assert actuator_esp.get_actuator_state(6).state is True

        # Verify Zone B actuator is OFF (should not be affected)
        assert esps["zone_b_actuators"].get_actuator_state(6).state is False

    def test_cross_zone_emergency_broadcast(self, multiple_mock_esp32_with_zones):
        """Emergency stop affects all zones."""
        esps = multiple_mock_esp32_with_zones

        # Turn on actuators in both zones
        esps["zone_a_actuators"].handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        esps["zone_b_actuators"].handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        # Verify ON
        assert esps["zone_a_actuators"].get_actuator_state(5).state is True
        assert esps["zone_b_actuators"].get_actuator_state(5).state is True

        # Emergency stop from one zone (broadcast)
        for esp in esps.values():
            esp.handle_command("emergency_stop", {})

        # All actuators should be OFF
        assert esps["zone_a_actuators"].get_actuator_state(5).state is False
        assert esps["zone_b_actuators"].get_actuator_state(5).state is False

        # All should have emergency_stopped flag
        assert esps["zone_a_actuators"].get_actuator_state(5).emergency_stopped is True
        assert esps["zone_b_actuators"].get_actuator_state(5).emergency_stopped is True


# =============================================================================
# Test 13: Topic Structure Validation
# =============================================================================
class TestTopicStructure:
    """Validate all MQTT topics match specification exactly."""

    def test_sensor_topic_structure(self, mock_esp32):
        """Sensor topic matches: kaiser/god/esp/{esp_id}/sensor/{gpio}/data"""
        mock_esp32.set_sensor_value(gpio=34, raw_value=100, sensor_type="test", name="Test")
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("sensor_read", {"gpio": 34})

        topic = mock_esp32.get_published_messages()[0]["topic"]
        assert topic == f"kaiser/god/esp/{mock_esp32.esp_id}/sensor/34/data"

    def test_actuator_status_topic_structure(self, mock_esp32):
        """Actuator status matches: kaiser/god/esp/{esp_id}/actuator/{gpio}/status"""
        mock_esp32.configure_actuator(gpio=5, actuator_type="pump", name="Test")
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        status_msgs = mock_esp32.get_messages_by_topic_pattern("/status")
        assert len(status_msgs) >= 1

        topic = status_msgs[0]["topic"]
        assert topic == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status"

    def test_actuator_response_topic_structure(self, mock_esp32):
        """Actuator response matches: kaiser/god/esp/{esp_id}/actuator/{gpio}/response"""
        mock_esp32.configure_actuator(gpio=5, actuator_type="pump", name="Test")
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        response_msgs = mock_esp32.get_messages_by_topic_pattern("/response")
        assert len(response_msgs) >= 1

        topic = response_msgs[0]["topic"]
        assert topic == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/response"

    def test_heartbeat_topic_structure(self, mock_esp32):
        """Heartbeat matches: kaiser/god/esp/{esp_id}/system/heartbeat"""
        mock_esp32.clear_published_messages()

        mock_esp32.handle_command("ping", {})

        heartbeat_msgs = mock_esp32.get_messages_by_topic_pattern("heartbeat")
        assert len(heartbeat_msgs) == 1

        topic = heartbeat_msgs[0]["topic"]
        assert topic == f"kaiser/god/esp/{mock_esp32.esp_id}/system/heartbeat"

    def test_broadcast_emergency_topic(self, mock_esp32_with_actuators):
        """Broadcast emergency matches: kaiser/broadcast/emergency"""
        mock = mock_esp32_with_actuators
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.clear_published_messages()

        mock.handle_command("emergency_stop", {})

        broadcast_msgs = [
            m for m in mock.get_published_messages() if m["topic"] == "kaiser/broadcast/emergency"
        ]
        assert len(broadcast_msgs) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov"])
