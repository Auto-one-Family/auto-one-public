"""
Unit Tests für MQTT Topic Validation.

Location: tests/unit/test_topic_validation.py
Keine DB-Abhängigkeit - reine Logik.

Phase 3 Test-Suite: Topic Building, Parsing und Pattern Matching.
"""

import pytest

from src.mqtt.topics import TopicBuilder
from src.core.validators import (
    validate_mqtt_topic,
    validate_esp_id,
    validate_gpio,
    validate_zone_id,
)
from src.core import constants


class TestTopicBuilderBuild:
    """Test TopicBuilder build methods."""

    def test_build_sensor_data_topic(self):
        """Build sensor data topic correctly."""
        topic = TopicBuilder.build_sensor_data_topic("ESP_12AB34CD", 34, "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"

    def test_build_sensor_data_topic_default_kaiser_id(self):
        """Build sensor data topic with default kaiser_id."""
        topic = TopicBuilder.build_sensor_data_topic("ESP_12AB34CD", 34)
        assert "kaiser/" in topic
        assert "esp/ESP_12AB34CD/sensor/34/data" in topic

    def test_build_actuator_command_topic(self):
        """Build actuator command topic correctly."""
        topic = TopicBuilder.build_actuator_command_topic("ESP_12AB34CD", 5)
        assert "kaiser/" in topic
        assert "esp/ESP_12AB34CD/actuator/5/command" in topic

    def test_build_heartbeat_topic(self):
        """Build heartbeat topic correctly."""
        topic = TopicBuilder.build_heartbeat_topic("ESP_12AB34CD", "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/system/heartbeat"

    def test_build_heartbeat_topic_default_kaiser_id(self):
        """Build heartbeat topic with default kaiser_id."""
        topic = TopicBuilder.build_heartbeat_topic("ESP_12AB34CD")
        assert "system/heartbeat" in topic

    def test_build_actuator_status_topic(self):
        """Build actuator status topic correctly."""
        topic = TopicBuilder.build_actuator_status_topic("ESP_12AB34CD", 18, "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"

    def test_build_actuator_response_topic(self):
        """Build actuator response topic correctly."""
        topic = TopicBuilder.build_actuator_response_topic("ESP_12AB34CD", 5, "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/actuator/5/response"

    def test_build_actuator_alert_topic(self):
        """Build actuator alert topic correctly."""
        topic = TopicBuilder.build_actuator_alert_topic("ESP_12AB34CD", 5, "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/actuator/5/alert"

    def test_build_sensor_batch_topic(self):
        """Build sensor batch topic correctly."""
        topic = TopicBuilder.build_sensor_batch_topic("ESP_12AB34CD", "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/sensor/batch"

    def test_build_heartbeat_metrics_topic(self):
        """Build heartbeat metrics topic correctly."""
        topic = TopicBuilder.build_heartbeat_metrics_topic("ESP_12AB34CD", "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/system/heartbeat_metrics"

    def test_build_heartbeat_metrics_topic_default_kaiser_id(self):
        """Build heartbeat metrics topic with default kaiser_id."""
        topic = TopicBuilder.build_heartbeat_metrics_topic("ESP_12AB34CD")
        assert "system/heartbeat_metrics" in topic
        assert "esp/ESP_12AB34CD" in topic

    def test_build_system_diagnostics_topic(self):
        """Build system diagnostics topic correctly."""
        topic = TopicBuilder.build_system_diagnostics_topic("ESP_12AB34CD", "god")
        assert topic == "kaiser/god/esp/ESP_12AB34CD/system/diagnostics"

    def test_build_zone_assign_topic(self):
        """Build zone assignment topic correctly."""
        topic = TopicBuilder.build_zone_assign_topic("ESP_12AB34CD")
        assert "zone/assign" in topic
        assert "esp/ESP_12AB34CD" in topic

    def test_build_subzone_assign_topic(self):
        """Build subzone assignment topic correctly."""
        topic = TopicBuilder.build_subzone_assign_topic("ESP_12AB34CD")
        assert "subzone/assign" in topic
        assert "esp/ESP_12AB34CD" in topic


class TestTopicBuilderParse:
    """Test TopicBuilder parse methods."""

    def test_parse_sensor_data_topic(self):
        """Parse sensor data topic extracts all components."""
        result = TopicBuilder.parse_sensor_data_topic("kaiser/god/esp/ESP_12AB34CD/sensor/34/data")
        assert result is not None
        assert result["kaiser_id"] == "god"
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 34
        assert result["type"] == "sensor_data"

    def test_parse_sensor_data_topic_different_gpio(self):
        """Parse sensor data topic with different GPIO pins."""
        result = TopicBuilder.parse_sensor_data_topic("kaiser/god/esp/ESP_AABBCC/sensor/0/data")
        assert result is not None
        assert result["gpio"] == 0

        result = TopicBuilder.parse_sensor_data_topic("kaiser/god/esp/ESP_AABBCC/sensor/39/data")
        assert result is not None
        assert result["gpio"] == 39

    def test_parse_heartbeat_topic(self):
        """Parse heartbeat topic."""
        result = TopicBuilder.parse_heartbeat_topic("kaiser/god/esp/ESP_12AB34CD/system/heartbeat")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "heartbeat"

    def test_parse_heartbeat_topic_legacy_format(self):
        """Parse legacy heartbeat topic (without /system/)."""
        result = TopicBuilder.parse_heartbeat_topic("kaiser/god/esp/ESP_12AB34CD/heartbeat")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "heartbeat"

    def test_parse_lwt_topic(self):
        """Parse LWT topic."""
        result = TopicBuilder.parse_lwt_topic("kaiser/god/esp/ESP_12AB34CD/system/will")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "lwt"

    def test_parse_config_response_topic(self):
        """Parse config response topic."""
        result = TopicBuilder.parse_config_response_topic(
            "kaiser/god/esp/ESP_12AB34CD/config_response"
        )
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "config_response"

    def test_parse_actuator_status_topic(self):
        """Parse actuator status topic."""
        result = TopicBuilder.parse_actuator_status_topic(
            "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"
        )
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 18
        assert result["type"] == "actuator_status"

    def test_parse_actuator_response_topic(self):
        """Parse actuator response topic."""
        result = TopicBuilder.parse_actuator_response_topic(
            "kaiser/god/esp/ESP_12AB34CD/actuator/5/response"
        )
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 5
        assert result["type"] == "actuator_response"

    def test_parse_actuator_alert_topic(self):
        """Parse actuator alert topic."""
        result = TopicBuilder.parse_actuator_alert_topic(
            "kaiser/god/esp/ESP_12AB34CD/actuator/5/alert"
        )
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 5
        assert result["type"] == "actuator_alert"

    def test_parse_zone_ack_topic(self):
        """Parse zone ACK topic."""
        result = TopicBuilder.parse_zone_ack_topic("kaiser/god/esp/ESP_12AB34CD/zone/ack")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "zone_ack"

    def test_parse_subzone_ack_topic(self):
        """Parse subzone ACK topic."""
        result = TopicBuilder.parse_subzone_ack_topic("kaiser/god/esp/ESP_12AB34CD/subzone/ack")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "subzone_ack"

    def test_parse_heartbeat_metrics_topic(self):
        """Parse heartbeat metrics topic."""
        result = TopicBuilder.parse_heartbeat_metrics_topic(
            "kaiser/god/esp/ESP_12AB34CD/system/heartbeat_metrics"
        )
        assert result is not None
        assert result["kaiser_id"] == "god"
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "heartbeat_metrics"

    def test_parse_heartbeat_metrics_parser_does_not_match_core_heartbeat(self):
        """heartbeat_metrics parser must not parse core heartbeat topics."""
        result = TopicBuilder.parse_heartbeat_metrics_topic(
            "kaiser/god/esp/ESP_12AB34CD/system/heartbeat"
        )
        assert result is None

    def test_parse_heartbeat_parser_does_not_match_heartbeat_metrics(self):
        """Core heartbeat parser must not parse heartbeat_metrics topics."""
        result = TopicBuilder.parse_heartbeat_topic(
            "kaiser/god/esp/ESP_12AB34CD/system/heartbeat_metrics"
        )
        assert result is None

    def test_parse_heartbeat_metrics_via_generic(self):
        """Generic parse_topic routes heartbeat_metrics correctly."""
        result = TopicBuilder.parse_topic("kaiser/god/esp/ESP_12AB34CD/system/heartbeat_metrics")
        assert result is not None
        assert result["type"] == "heartbeat_metrics"

    def test_parse_system_error_topic(self):
        """Parse system error topic."""
        result = TopicBuilder.parse_system_error_topic("kaiser/god/esp/ESP_12AB34CD/system/error")
        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "system_error"

    def test_parse_invalid_topic_returns_none(self):
        """Invalid topics return None."""
        assert TopicBuilder.parse_sensor_data_topic("invalid/topic") is None
        assert TopicBuilder.parse_heartbeat_topic("wrong/format") is None
        assert TopicBuilder.parse_lwt_topic("something/else") is None
        assert TopicBuilder.parse_config_response_topic("") is None

    def test_parse_topic_generic_method(self):
        """Generic parse_topic tries all parsers."""
        # Sensor data
        result = TopicBuilder.parse_topic("kaiser/god/esp/ESP_12AB34CD/sensor/34/data")
        assert result is not None
        assert result["type"] == "sensor_data"

        # Heartbeat
        result = TopicBuilder.parse_topic("kaiser/god/esp/ESP_12AB34CD/system/heartbeat")
        assert result is not None
        assert result["type"] == "heartbeat"

        # LWT
        result = TopicBuilder.parse_topic("kaiser/god/esp/ESP_12AB34CD/system/will")
        assert result is not None
        assert result["type"] == "lwt"


class TestTopicPatternMatching:
    """Test MQTT wildcard pattern matching."""

    def test_matches_single_level_wildcard(self):
        """Single-level wildcard (+) matches one segment."""
        pattern = "kaiser/god/esp/+/sensor/+/data"
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/ESP_12AB34CD/sensor/34/data", pattern)
            is True
        )
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/ESP_OTHER/sensor/99/data", pattern)
            is True
        )
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/MOCK_TEST/sensor/0/data", pattern)
            is True
        )

    def test_matches_multi_level_wildcard(self):
        """Multi-level wildcard (#) matches multiple segments."""
        pattern = "kaiser/god/esp/+/actuator/#"
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/actuator/5/status", pattern
            )
            is True
        )
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/actuator/5/response", pattern
            )
            is True
        )
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/actuator/5/alert", pattern
            )
            is True
        )

    def test_no_match_different_prefix(self):
        """Non-matching prefix fails."""
        pattern = "kaiser/god/esp/+/sensor/+/data"
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/other/esp/ESP_12AB34CD/sensor/34/data", pattern
            )
            is False
        )
        assert TopicBuilder.matches_subscription("something/else/entirely", pattern) is False

    def test_no_match_different_suffix(self):
        """Non-matching suffix fails."""
        pattern = "kaiser/god/esp/+/sensor/+/data"
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/sensor/34/status", pattern
            )
            is False
        )
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/sensor/34/response", pattern
            )
            is False
        )

    def test_exact_match_without_wildcard(self):
        """Exact pattern matches only exact topic."""
        pattern = "kaiser/god/esp/ESP_SPECIFIC/sensor/34/data"
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/ESP_SPECIFIC/sensor/34/data", pattern)
            is True
        )
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/ESP_OTHER/sensor/34/data", pattern)
            is False
        )

    def test_heartbeat_subscription_pattern(self):
        """Heartbeat subscription pattern matches correctly."""
        pattern = "kaiser/god/esp/+/system/heartbeat"
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/system/heartbeat", pattern
            )
            is True
        )
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/MOCK_ESP_001/system/heartbeat", pattern
            )
            is True
        )

    def test_config_response_subscription_pattern(self):
        """Config response subscription pattern matches correctly."""
        pattern = "kaiser/god/esp/+/config_response"
        assert (
            TopicBuilder.matches_subscription(
                "kaiser/god/esp/ESP_12AB34CD/config_response", pattern
            )
            is True
        )
        assert (
            TopicBuilder.matches_subscription("kaiser/god/esp/ESP_AABBCC/config_response", pattern)
            is True
        )


class TestValidators:
    """Test topic and ID validators."""

    def test_validate_esp_id_valid_standard(self):
        """Valid ESP IDs with 6-8 hex chars pass validation."""
        valid, error = validate_esp_id("ESP_12AB34CD")
        assert valid is True
        assert error is None

        valid, error = validate_esp_id("ESP_D0B19C")
        assert valid is True
        assert error is None

        valid, error = validate_esp_id("ESP_AABBCC")
        assert valid is True
        assert error is None

    def test_validate_esp_id_valid_mock(self):
        """Valid MOCK ESP IDs pass validation."""
        # Pattern: MOCK_[A-Z0-9]+ (no underscores after MOCK_)
        valid, error = validate_esp_id("MOCK_ESP001")
        assert valid is True
        assert error is None

        valid, error = validate_esp_id("MOCK_TEST123")
        assert valid is True
        assert error is None

    def test_validate_esp_id_invalid_format(self):
        """Invalid ESP IDs fail validation."""
        valid, error = validate_esp_id("invalid")
        assert valid is False
        assert error is not None

        valid, error = validate_esp_id("ESP_")
        assert valid is False
        assert error is not None

        valid, error = validate_esp_id("esp_12AB34CD")  # lowercase
        assert valid is False
        assert error is not None

    def test_validate_esp_id_invalid_hex(self):
        """ESP ID with non-hex characters fails validation."""
        valid, error = validate_esp_id("ESP_GGHHII")  # G, H, I not hex
        assert valid is False
        assert error is not None

    def test_validate_esp_id_empty(self):
        """Empty ESP ID fails validation."""
        valid, error = validate_esp_id("")
        assert valid is False
        assert error is not None

    def test_validate_gpio_wroom_valid(self):
        """GPIO validation for ESP32 WROOM - valid pins."""
        # Standard GPIO pins (not reserved, not out of range)
        valid, error = validate_gpio(34, constants.HARDWARE_TYPE_ESP32_WROOM)
        assert valid is True
        assert error is None

        valid, error = validate_gpio(13, constants.HARDWARE_TYPE_ESP32_WROOM)
        assert valid is True
        assert error is None

        valid, error = validate_gpio(39, constants.HARDWARE_TYPE_ESP32_WROOM)
        assert valid is True
        assert error is None

    def test_validate_gpio_wroom_reserved(self):
        """GPIO validation for ESP32 WROOM - reserved (flash) pins."""
        # Reserved flash pins: 6, 7, 8, 9, 10, 11
        for pin in [6, 7, 8, 9, 10, 11]:
            valid, error = validate_gpio(pin, constants.HARDWARE_TYPE_ESP32_WROOM)
            assert valid is False, f"GPIO {pin} should be reserved on WROOM"
            assert error is not None

    def test_validate_gpio_wroom_out_of_range(self):
        """GPIO validation for ESP32 WROOM - out of range."""
        valid, error = validate_gpio(40, constants.HARDWARE_TYPE_ESP32_WROOM)
        assert valid is False
        assert error is not None

        valid, error = validate_gpio(-1, constants.HARDWARE_TYPE_ESP32_WROOM)
        assert valid is False
        assert error is not None

    def test_validate_gpio_xiao_valid(self):
        """GPIO validation for XIAO ESP32-C3 - valid pins."""
        valid, error = validate_gpio(4, constants.HARDWARE_TYPE_XIAO_ESP32C3)
        assert valid is True
        assert error is None

        valid, error = validate_gpio(0, constants.HARDWARE_TYPE_XIAO_ESP32C3)
        assert valid is True
        assert error is None

    def test_validate_gpio_xiao_reserved(self):
        """GPIO validation for XIAO ESP32-C3 - reserved (USB) pins."""
        # Reserved USB pins: 18, 19
        for pin in [18, 19]:
            valid, error = validate_gpio(pin, constants.HARDWARE_TYPE_XIAO_ESP32C3)
            assert valid is False, f"GPIO {pin} should be reserved on XIAO"
            assert error is not None

    def test_validate_gpio_xiao_out_of_range(self):
        """GPIO validation for XIAO ESP32-C3 - out of range."""
        valid, error = validate_gpio(22, constants.HARDWARE_TYPE_XIAO_ESP32C3)
        assert valid is False
        assert error is not None

    def test_validate_mqtt_topic_valid(self):
        """Valid MQTT topics pass validation."""
        valid, error = validate_mqtt_topic("kaiser/god/esp/ESP_12AB34CD/sensor/34/data")
        assert valid is True
        assert error is None

        valid, error = validate_mqtt_topic("simple/topic")
        assert valid is True
        assert error is None

    def test_validate_mqtt_topic_with_wildcards(self):
        """MQTT topics with wildcards pass validation."""
        valid, error = validate_mqtt_topic("kaiser/god/esp/+/sensor/+/data")
        assert valid is True
        assert error is None

        valid, error = validate_mqtt_topic("kaiser/god/esp/#")
        assert valid is True
        assert error is None

    def test_validate_mqtt_topic_empty(self):
        """Empty MQTT topic fails validation."""
        valid, error = validate_mqtt_topic("")
        assert valid is False
        assert error is not None

    def test_validate_mqtt_topic_invalid_wildcard_position(self):
        """MQTT topic with # not at end fails validation."""
        valid, error = validate_mqtt_topic("kaiser/#/sensor")
        assert valid is False
        assert error is not None

    def test_validate_mqtt_topic_multiple_multilevel_wildcards(self):
        """MQTT topic with multiple # fails validation."""
        valid, error = validate_mqtt_topic("kaiser/#/esp/#")
        assert valid is False
        assert error is not None

    def test_validate_zone_id_valid(self):
        """Valid zone IDs pass validation."""
        valid, error = validate_zone_id("greenhouse_1")
        assert valid is True
        assert error is None

        valid, error = validate_zone_id("zone-alpha")
        assert valid is True
        assert error is None

        valid, error = validate_zone_id("ZoneA123")
        assert valid is True
        assert error is None

    def test_validate_zone_id_empty(self):
        """Empty zone ID fails validation."""
        valid, error = validate_zone_id("")
        assert valid is False
        assert error is not None

    def test_validate_zone_id_invalid_chars(self):
        """Zone ID with invalid characters fails validation."""
        valid, error = validate_zone_id("zone with spaces")
        assert valid is False
        assert error is not None

        valid, error = validate_zone_id("zone@special!")
        assert valid is False
        assert error is not None


class TestTopicBuilderValidation:
    """Test TopicBuilder's built-in validation methods."""

    def test_validate_esp_id_method(self):
        """TopicBuilder.validate_esp_id validates format."""
        assert TopicBuilder.validate_esp_id("ESP_12AB34CD") is True
        assert TopicBuilder.validate_esp_id("ESP_AABBCC") is True
        assert TopicBuilder.validate_esp_id("ESP_D0B19C") is True
        assert TopicBuilder.validate_esp_id("invalid") is False
        assert TopicBuilder.validate_esp_id("ESP_GGG") is False

    def test_validate_gpio_method_wroom(self):
        """TopicBuilder.validate_gpio validates GPIO for WROOM."""
        assert TopicBuilder.validate_gpio(34, constants.HARDWARE_TYPE_ESP32_WROOM) is True
        assert TopicBuilder.validate_gpio(6, constants.HARDWARE_TYPE_ESP32_WROOM) is False
        assert TopicBuilder.validate_gpio(40, constants.HARDWARE_TYPE_ESP32_WROOM) is False

    def test_validate_gpio_method_xiao(self):
        """TopicBuilder.validate_gpio validates GPIO for XIAO."""
        assert TopicBuilder.validate_gpio(4, constants.HARDWARE_TYPE_XIAO_ESP32C3) is True
        assert TopicBuilder.validate_gpio(18, constants.HARDWARE_TYPE_XIAO_ESP32C3) is False
        assert TopicBuilder.validate_gpio(22, constants.HARDWARE_TYPE_XIAO_ESP32C3) is False


class TestIntentOutcomeLifecycleTopicParse:
    def test_parse_intent_outcome_lifecycle_topic(self):
        parsed = TopicBuilder.parse_intent_outcome_lifecycle_topic(
            "kaiser/god/esp/ESP_12AB34CD/system/intent_outcome/lifecycle"
        )
        assert parsed["esp_id"] == "ESP_12AB34CD"
        assert parsed["type"] == "intent_outcome_lifecycle"

    def test_parse_intent_outcome_topic_does_not_match_lifecycle(self):
        assert (
            TopicBuilder.parse_intent_outcome_topic(
                "kaiser/god/esp/ESP_12AB34CD/system/intent_outcome/lifecycle"
            )
            is None
        )
