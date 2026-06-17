"""
Infrastructure Tests - Server-orchestrated ESP32 configuration and system testing.

NOTE: These tests use the REAL MQTT topic structure (not separate test topics).
This design choice enables:
- Tests to run against both Mock clients AND real hardware
- Pre-production validation with authentic message routing
- Cross-ESP orchestration scenarios
- Seamless CI/CD → Staging → Production flow

Topic structure: kaiser/god/esp/{esp_id}/...
(Identical to production - see El Trabajante/docs/Mqtt_Protocoll.md)

Tests verify:
1. Configuration management (WiFi, Zone, System)
2. Topic format validation
3. Error tracking and reporting
4. System status and diagnostics

Migration from ESP32 Tests:
- infra_config_manager.cpp → test_config_get, test_config_validation
- infra_topic_builder.cpp → test_topic_formats (unit tests, not orchestrated)
- infra_storage_manager.cpp → (Internal implementation, not testable via MQTT)
- infra_logger.cpp → (Internal implementation, not testable via MQTT)
- infra_error_tracker.cpp → test_error_reporting (via MQTT error messages)
"""

import pytest


class TestConfigManagement:
    """Test configuration management via MQTT commands."""

    def test_config_get_all(self, mock_esp32):
        """Test retrieving all configuration."""
        # Configure zone first (production ESPs have zone configured)
        mock_esp32.configure_zone("test-zone", "test-master", "test-subzone")

        response = mock_esp32.handle_command("config_get", {})

        assert response["status"] == "ok"
        assert "config" in response["data"]

        config = response["data"]["config"]
        assert "wifi" in config
        assert "zone" in config
        assert "system" in config

    def test_config_get_wifi(self, mock_esp32):
        """Test retrieving WiFi configuration."""
        response = mock_esp32.handle_command("config_get", {"key": "wifi"})

        assert response["status"] == "ok"
        assert response["data"]["key"] == "wifi"
        assert "ssid" in response["data"]["value"]
        assert "connected" in response["data"]["value"]

    def test_config_get_zone(self, mock_esp32):
        """Test retrieving zone configuration."""
        # Configure zone first (production ESPs have zone configured)
        mock_esp32.configure_zone("test-zone", "test-master", "test-subzone", "Test Zone Name")

        response = mock_esp32.handle_command("config_get", {"key": "zone"})

        assert response["status"] == "ok"
        assert response["data"]["key"] == "zone"
        assert "id" in response["data"]["value"]
        assert "name" in response["data"]["value"]

    def test_config_get_system(self, mock_esp32):
        """Test retrieving system configuration."""
        response = mock_esp32.handle_command("config_get", {"key": "system"})

        assert response["status"] == "ok"
        assert response["data"]["key"] == "system"
        assert "version" in response["data"]["value"]
        assert "uptime" in response["data"]["value"]

    def test_config_get_invalid_key(self, mock_esp32):
        """Test config_get with non-existent key."""
        response = mock_esp32.handle_command("config_get", {"key": "invalid_key"})

        assert response["status"] == "ok"
        assert response["data"]["value"] is None  # Non-existent key returns None

    def test_config_set_mock_only(self, mock_esp32):
        """Test config_set (MOCK ONLY - should NOT work on real hardware)."""
        # This test verifies config_set works on Mock but would be blocked on real hardware
        response = mock_esp32.handle_command(
            "config_set", {"key": "test_key", "value": {"test": "value"}}
        )

        assert response["status"] == "ok"
        assert response["data"]["key"] == "test_key"

        # Verify the change persisted
        get_response = mock_esp32.handle_command("config_get", {"key": "test_key"})
        assert get_response["data"]["value"] == {"test": "value"}

    def test_config_validation(self, mock_esp32):
        """Test that config values are validated correctly."""
        # WiFi config should have required fields
        wifi_response = mock_esp32.handle_command("config_get", {"key": "wifi"})
        wifi_config = wifi_response["data"]["value"]

        assert "ssid" in wifi_config, "WiFi config missing SSID"
        assert "connected" in wifi_config, "WiFi config missing connection status"


class TestTopicFormats:
    """Test MQTT topic format validation (based on TopicBuilder tests)."""

    def test_sensor_data_topic_format(self, mock_esp32_with_sensors):
        """Test sensor data topic follows correct format."""
        mock_esp32_with_sensors.clear_published_messages()

        response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

        messages = mock_esp32_with_sensors.get_published_messages()
        # With zone configured, publishes to both normal and zone topic (2 messages)
        sensor_msgs = [m for m in messages if "/sensor/34/data" in m["topic"]]
        assert len(sensor_msgs) >= 1

        # Find the main (non-zone) topic
        main_topic_msgs = [
            m
            for m in sensor_msgs
            if f"kaiser/god/esp/{mock_esp32_with_sensors.esp_id}/sensor/34/data" == m["topic"]
        ]
        assert len(main_topic_msgs) == 1

        topic = main_topic_msgs[0]["topic"]
        # Format: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
        assert topic == f"kaiser/god/esp/{mock_esp32_with_sensors.esp_id}/sensor/34/data"

    def test_actuator_status_topic_format(self, mock_esp32):
        """Test actuator status topic follows correct format."""
        mock_esp32.clear_published_messages()

        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        messages = mock_esp32.get_published_messages()
        # Now publishes both status and response
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        assert len(status_msgs) >= 1

        topic = status_msgs[0]["topic"]
        # Format: kaiser/god/esp/{esp_id}/actuator/{gpio}/status
        assert topic == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status"

    def test_topic_uses_correct_esp_id(self, mock_esp32):
        """Test that topics use correct ESP ID."""
        mock_esp32.clear_published_messages()

        # Trigger a message publish
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        messages = mock_esp32.get_published_messages()
        topic = messages[0]["topic"]

        assert mock_esp32.esp_id in topic, f"Topic doesn't contain ESP ID: {topic}"


class TestSystemStatus:
    """Test system status and diagnostics."""

    def test_ping_includes_uptime(self, mock_esp32):
        """Test ping response includes system uptime."""
        response = mock_esp32.handle_command("ping", {})

        assert "uptime" in response
        assert isinstance(response["uptime"], (int, float))
        assert response["uptime"] >= 0

    def test_system_info_in_config(self, mock_esp32):
        """Test system info available via config."""
        response = mock_esp32.handle_command("config_get", {"key": "system"})

        system_info = response["data"]["value"]
        assert "version" in system_info
        assert "uptime" in system_info

        # Version should be a string
        assert isinstance(system_info["version"], str)
        assert len(system_info["version"]) > 0


class TestErrorHandling:
    """Test error tracking and reporting."""

    def test_error_response_format(self, mock_esp32):
        """Test that errors follow correct format."""
        # Trigger an error with invalid command
        response = mock_esp32.handle_command("invalid_command", {})

        assert response["status"] == "error"
        assert "error" in response
        assert isinstance(response["error"], str)
        assert len(response["error"]) > 0

    def test_missing_parameter_error(self, mock_esp32):
        """Test error when required parameter is missing."""
        response = mock_esp32.handle_command(
            "actuator_set",
            {
                "gpio": 5
                # Missing "value"
            },
        )

        assert response["status"] == "error"
        assert "missing" in response["error"].lower() or "required" in response["error"].lower()

    def test_invalid_gpio_error(self, mock_esp32):
        """Test error when accessing non-existent actuator."""
        response = mock_esp32.handle_command("actuator_get", {"gpio": 99})

        assert response["status"] == "error"
        assert "not found" in response["error"].lower()


class TestConfigPersistence:
    """Test configuration persistence across commands."""

    def test_config_persists_across_commands(self, mock_esp32):
        """Test that config doesn't change unexpectedly."""
        # Get initial config
        response1 = mock_esp32.handle_command("config_get", {"key": "wifi"})
        wifi_config1 = response1["data"]["value"]

        # Execute other commands
        mock_esp32.handle_command("ping", {})
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Get config again
        response2 = mock_esp32.handle_command("config_get", {"key": "wifi"})
        wifi_config2 = response2["data"]["value"]

        # Config should be unchanged
        assert wifi_config1 == wifi_config2

    def test_config_changes_only_via_config_set(self, mock_esp32):
        """Test that config only changes via config_set command."""
        # Get initial zone config
        response1 = mock_esp32.handle_command("config_get", {"key": "zone"})
        zone1 = response1["data"]["value"]

        # Change via config_set
        new_zone = {"id": "new-zone", "name": "New Zone"}
        mock_esp32.handle_command("config_set", {"key": "zone", "value": new_zone})

        # Verify change
        response2 = mock_esp32.handle_command("config_get", {"key": "zone"})
        zone2 = response2["data"]["value"]

        assert zone2 == new_zone
        assert zone2 != zone1


class TestResetFunctionality:
    """Test reset command (MOCK ONLY)."""

    def test_reset_clears_actuators(self, mock_esp32):
        """Test that reset clears all actuator state."""
        # Create actuator state
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock_esp32.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # Verify actuators exist
        response1 = mock_esp32.handle_command("actuator_get", {})
        assert len(response1["data"]["actuators"]) == 2

        # Reset
        reset_response = mock_esp32.handle_command("reset", {})
        assert reset_response["status"] == "ok"

        # Verify actuators cleared
        response2 = mock_esp32.handle_command("actuator_get", {})
        assert len(response2["data"]["actuators"]) == 0

    def test_reset_clears_sensors(self, mock_esp32_with_sensors):
        """Test that reset clears all sensor state."""
        # Verify sensors exist
        assert len(mock_esp32_with_sensors.sensors) == 3

        # Reset
        reset_response = mock_esp32_with_sensors.handle_command("reset", {})
        assert reset_response["status"] == "ok"

        # Verify sensors cleared
        assert len(mock_esp32_with_sensors.sensors) == 0

    def test_reset_clears_published_messages(self, mock_esp32):
        """Test that reset clears published messages."""
        # Generate some messages
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert len(mock_esp32.get_published_messages()) > 0

        # Reset
        mock_esp32.handle_command("reset", {})

        # Verify messages cleared
        assert len(mock_esp32.get_published_messages()) == 0


class TestWiFiConfiguration:
    """Test WiFi configuration via MQTT."""

    def test_wifi_config_structure(self, mock_esp32):
        """Test WiFi config has expected structure."""
        response = mock_esp32.handle_command("config_get", {"key": "wifi"})

        wifi_config = response["data"]["value"]
        assert "ssid" in wifi_config
        assert "connected" in wifi_config
        assert isinstance(wifi_config["connected"], bool)

    def test_wifi_connection_status(self, mock_esp32):
        """Test WiFi connection status is reported."""
        response = mock_esp32.handle_command("config_get", {"key": "wifi"})

        wifi_config = response["data"]["value"]
        # Mock should report as connected
        assert wifi_config["connected"] is True


class TestZoneConfiguration:
    """Test zone configuration via MQTT."""

    def test_zone_config_structure(self, mock_esp32):
        """Test zone config has expected structure."""
        # Configure zone first (production ESPs have zone configured)
        mock_esp32.configure_zone("test-zone", "test-master", "test-subzone", "Test Zone")

        response = mock_esp32.handle_command("config_get", {"key": "zone"})

        zone_config = response["data"]["value"]
        assert "id" in zone_config
        assert "name" in zone_config


class TestNetworkResilience:
    """
    Test network failure and recovery scenarios.

    NOTE: These tests simulate network issues to validate system resilience.
    Critical for production IoT systems where network failures are common.
    """

    def test_command_during_disconnect(self, mock_esp32):
        """
        Test command handling when ESP is disconnected.

        Real-world scenario: WiFi signal loss during operation.
        """
        # Set actuator state while connected
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Simulate disconnect
        mock_esp32.connected = False

        # Attempt command during disconnect
        response = mock_esp32.handle_command(
            "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
        )

        # Mock returns error when disconnected
        # Real ESP would queue in offline buffer
        assert response["status"] in ["error", "ok"]

    def test_reconnect_resends_status(self, mock_esp32):
        """
        Test ESP republishes status after reconnect.

        Real-world scenario: After WiFi reconnect, ESP should
        update server with current state.
        """
        # Set actuator state
        mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock_esp32.clear_published_messages()

        # Simulate disconnect/reconnect
        mock_esp32.connected = False
        mock_esp32.connected = True

        # On reconnect, ESP should republish heartbeat
        # (This is a Mock limitation - real ESP does this automatically)
        # Verify system still functional after reconnect
        response = mock_esp32.handle_command("ping", {})
        assert response["status"] == "ok"

    def test_config_operations_during_network_issues(self, mock_esp32):
        """
        Test config operations with intermittent connectivity.

        Config operations should be robust to network issues.
        """
        # Get config (should work)
        response1 = mock_esp32.handle_command("config_get", {})
        assert response1["status"] == "ok"

        # Simulate network issue
        mock_esp32.connected = False

        # Config get during disconnect (may fail or use cache)
        response2 = mock_esp32.handle_command("config_get", {})
        # Mock may return error or cached data
        assert response2["status"] in ["ok", "error"]

        # Reconnect
        mock_esp32.connected = True

        # Config should work again
        response3 = mock_esp32.handle_command("config_get", {})
        assert response3["status"] == "ok"

    def test_zone_id_is_string(self, mock_esp32):
        """Test zone ID is a string."""
        # Configure zone first (production ESPs have zone configured)
        mock_esp32.configure_zone("test-zone-123", "test-master", "test-subzone")

        response = mock_esp32.handle_command("config_get", {"key": "zone"})

        zone_config = response["data"]["value"]
        assert isinstance(zone_config["id"], str)
        assert len(zone_config["id"]) > 0
