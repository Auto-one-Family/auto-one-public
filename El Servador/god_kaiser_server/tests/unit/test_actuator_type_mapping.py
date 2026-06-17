"""
Unit Tests for Actuator Type Mapping (Server → ESP32)

Tests the conversion of Server actuator types to ESP32-compatible types.

BUG-FIX Reference:
- Server stores "digital" but ESP32 expects "relay"
- See: El Trabajante/src/models/actuator_types.h (ActuatorTypeTokens)
- ESP32 valid types: "pump", "valve", "pwm", "relay"

Phase: Bug Fix - Actuator Type Mapping
Priority: CRITICAL
"""

import pytest
from unittest.mock import MagicMock

from src.core.config_mapping import (
    map_actuator_type_for_esp32,
    ESP32_ACTUATOR_TYPES,
    SERVER_TO_ESP32_ACTUATOR_TYPE,
    ConfigMappingEngine,
    DEFAULT_ACTUATOR_MAPPINGS,
)


class TestMapActuatorTypeForESP32:
    """Tests for the map_actuator_type_for_esp32 function."""

    # =========================================================================
    # Positive Tests - Main Bug Fix
    # =========================================================================

    def test_digital_maps_to_relay(self):
        """
        SCENARIO: Server stores "digital", ESP32 needs "relay"
        GIVEN: actuator_type = "digital"
        WHEN: map_actuator_type_for_esp32() is called
        THEN: Result = "relay"

        CONTEXT: This is the main bug fix - Frontend sends "relay",
        Server normalizes to "digital", ESP32 needs "relay" again.
        """
        assert map_actuator_type_for_esp32("digital") == "relay"

    def test_binary_maps_to_relay(self):
        """Alternative name 'binary' should also map to 'relay'."""
        assert map_actuator_type_for_esp32("binary") == "relay"

    def test_switch_maps_to_relay(self):
        """Alternative name 'switch' should also map to 'relay'."""
        assert map_actuator_type_for_esp32("switch") == "relay"

    # =========================================================================
    # Identity Mappings (should remain unchanged)
    # =========================================================================

    def test_relay_stays_relay(self):
        """Relay stays relay (no change needed)."""
        assert map_actuator_type_for_esp32("relay") == "relay"

    def test_pump_stays_pump(self):
        """Pump stays pump."""
        assert map_actuator_type_for_esp32("pump") == "pump"

    def test_valve_stays_valve(self):
        """Valve stays valve."""
        assert map_actuator_type_for_esp32("valve") == "valve"

    def test_pwm_stays_pwm(self):
        """PWM stays PWM."""
        assert map_actuator_type_for_esp32("pwm") == "pwm"

    # =========================================================================
    # Case Insensitivity and Whitespace Handling
    # =========================================================================

    def test_case_insensitive_digital(self):
        """Mapping is case-insensitive for 'digital'."""
        assert map_actuator_type_for_esp32("DIGITAL") == "relay"
        assert map_actuator_type_for_esp32("Digital") == "relay"
        assert map_actuator_type_for_esp32("DiGiTaL") == "relay"

    def test_case_insensitive_esp32_types(self):
        """Mapping is case-insensitive for ESP32 types."""
        assert map_actuator_type_for_esp32("PWM") == "pwm"
        assert map_actuator_type_for_esp32("Pwm") == "pwm"
        assert map_actuator_type_for_esp32("RELAY") == "relay"
        assert map_actuator_type_for_esp32("Relay") == "relay"
        assert map_actuator_type_for_esp32("PUMP") == "pump"
        assert map_actuator_type_for_esp32("VALVE") == "valve"

    def test_whitespace_trimmed(self):
        """Whitespace is trimmed from input."""
        assert map_actuator_type_for_esp32("  digital  ") == "relay"
        assert map_actuator_type_for_esp32(" pwm ") == "pwm"
        assert map_actuator_type_for_esp32("\trelay\t") == "relay"
        assert map_actuator_type_for_esp32("\n  pump  \n") == "pump"

    # =========================================================================
    # Negative Tests - Error Handling
    # =========================================================================

    def test_empty_string_raises_error(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            map_actuator_type_for_esp32("")

    def test_whitespace_only_raises_error(self):
        """Whitespace-only string raises ValueError after trim."""
        with pytest.raises(ValueError, match="must not be empty"):
            map_actuator_type_for_esp32("   ")

    def test_none_raises_error(self):
        """None raises error (TypeError or ValueError or AttributeError)."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            map_actuator_type_for_esp32(None)

    def test_unknown_type_raises_error(self):
        """Unknown type raises ValueError with helpful message."""
        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("unknown_type")

        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("motor")

        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("led")

    def test_error_message_lists_allowed_types(self):
        """Error message includes list of allowed types."""
        with pytest.raises(ValueError) as exc_info:
            map_actuator_type_for_esp32("invalid")

        error_msg = str(exc_info.value)
        # Should mention some allowed types
        assert "digital" in error_msg or "relay" in error_msg

    # =========================================================================
    # Consistency Tests
    # =========================================================================

    def test_all_esp32_types_are_valid_outputs(self):
        """All ESP32 types must be valid outputs when passed as input."""
        for esp32_type in ESP32_ACTUATOR_TYPES:
            result = map_actuator_type_for_esp32(esp32_type)
            assert result in ESP32_ACTUATOR_TYPES, f"Output '{result}' is not a valid ESP32 type"

    def test_all_mappings_produce_valid_esp32_types(self):
        """All mappings must produce ESP32-compatible types."""
        for server_type, expected_esp32_type in SERVER_TO_ESP32_ACTUATOR_TYPE.items():
            result = map_actuator_type_for_esp32(server_type)
            assert result == expected_esp32_type
            assert (
                result in ESP32_ACTUATOR_TYPES
            ), f"Mapping '{server_type}' → '{result}' is not a valid ESP32 type"

    def test_esp32_actuator_types_constant_is_frozen(self):
        """ESP32_ACTUATOR_TYPES should be immutable (frozenset)."""
        assert isinstance(ESP32_ACTUATOR_TYPES, frozenset)
        # Should contain exactly the 4 known types
        assert ESP32_ACTUATOR_TYPES == {"pump", "valve", "pwm", "relay"}


class TestConfigMappingEngineIntegration:
    """Tests for integration with ConfigMappingEngine."""

    def test_transform_registered_in_engine(self):
        """The actuator_type_to_esp32 transform is registered."""
        engine = ConfigMappingEngine()
        assert "actuator_type_to_esp32" in engine.TRANSFORMS

    def test_transform_callable(self):
        """The registered transform is callable and works correctly."""
        engine = ConfigMappingEngine()
        transform_fn = engine.TRANSFORMS["actuator_type_to_esp32"]

        assert transform_fn("digital") == "relay"
        assert transform_fn("pwm") == "pwm"
        assert transform_fn("pump") == "pump"

    def test_default_actuator_mapping_uses_transform(self):
        """DEFAULT_ACTUATOR_MAPPINGS uses the transform for actuator_type."""
        # Find the actuator_type mapping
        actuator_type_mapping = None
        for mapping in DEFAULT_ACTUATOR_MAPPINGS:
            if mapping.get("target") == "actuator_type":
                actuator_type_mapping = mapping
                break

        assert (
            actuator_type_mapping is not None
        ), "actuator_type mapping not found in DEFAULT_ACTUATOR_MAPPINGS"
        assert (
            actuator_type_mapping.get("transform") == "actuator_type_to_esp32"
        ), "actuator_type mapping should use 'actuator_type_to_esp32' transform"

    def test_engine_applies_transform_to_actuator(self):
        """ConfigMappingEngine applies the transform when building actuator payload."""
        engine = ConfigMappingEngine()

        # Create a mock actuator model with actuator_type = "digital"
        mock_actuator = MagicMock()
        mock_actuator.gpio = 5
        mock_actuator.actuator_type = "digital"  # Server stores this
        mock_actuator.actuator_name = "Test Relay"
        mock_actuator.enabled = True
        mock_actuator.actuator_metadata = {}

        payload = engine.apply_actuator_mapping(mock_actuator)

        # The payload should have "relay" not "digital"
        assert (
            payload["actuator_type"] == "relay"
        ), f"Expected 'relay' but got '{payload['actuator_type']}'"
        assert payload["gpio"] == 5
        assert payload["actuator_name"] == "Test Relay"
        assert payload["active"] is True

    def test_engine_preserves_native_esp32_types(self):
        """ConfigMappingEngine preserves native ESP32 types unchanged."""
        engine = ConfigMappingEngine()

        for esp32_type in ["pump", "valve", "pwm", "relay"]:
            mock_actuator = MagicMock()
            mock_actuator.gpio = 10
            mock_actuator.actuator_type = esp32_type
            mock_actuator.actuator_name = f"Test {esp32_type}"
            mock_actuator.enabled = True
            mock_actuator.actuator_metadata = {}

            payload = engine.apply_actuator_mapping(mock_actuator)

            assert (
                payload["actuator_type"] == esp32_type
            ), f"Type '{esp32_type}' should be preserved but got '{payload['actuator_type']}'"


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_numeric_type_raises_error(self):
        """Numeric input should raise an error."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            map_actuator_type_for_esp32(123)

    def test_list_type_raises_error(self):
        """List input should raise an error."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            map_actuator_type_for_esp32(["relay"])

    def test_dict_type_raises_error(self):
        """Dict input should raise an error."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            map_actuator_type_for_esp32({"type": "relay"})

    def test_very_long_string_raises_error(self):
        """Very long string should raise a reasonable error."""
        long_string = "relay" * 1000
        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32(long_string)

    def test_special_characters_raises_error(self):
        """Strings with special characters should fail gracefully."""
        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("relay!")

        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("pump@home")

        with pytest.raises(ValueError, match="Unknown actuator_type"):
            map_actuator_type_for_esp32("valve#1")
