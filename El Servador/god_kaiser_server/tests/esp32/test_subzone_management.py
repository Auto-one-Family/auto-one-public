"""
ESP32-Orchestrated Subzone Management Tests

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Tests the complete Subzone workflow from Server to ESP32 and back.
Uses MockESP32Client with subzone extensions to simulate ESP32 behavior.

Test Categories:
- Subzone Assignment Flow
- Subzone Removal Flow
- Safe-Mode Emergency Flow
- GPIO Conflict Detection
- Multi-ESP Subzone Coordination
- Error Handling & Recovery

References:
- El Trabajante/docs/system-flows/09-subzone-management-flow.md
- El Frontend/Docs/System Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md
"""

import pytest
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from .mocks.mock_esp32_client import MockESP32Client, SystemState, ActuatorState

# =============================================================================
# Extended Mock ESP32 with Subzone Support
# =============================================================================


@dataclass
class SubzoneConfigMock:
    """Mock subzone configuration matching ESP32 SubzoneConfig struct."""

    subzone_id: str
    subzone_name: str = ""
    parent_zone_id: str = ""
    assigned_gpios: List[int] = field(default_factory=list)
    safe_mode_active: bool = True
    created_timestamp: int = 0
    sensor_count: int = 0
    actuator_count: int = 0


class MockESP32WithSubzones(MockESP32Client):
    """
    Extended MockESP32Client with subzone management capabilities.

    Simulates ESP32 subzone operations matching El Trabajante implementation:
    - Subzone assignment and removal
    - GPIO-to-subzone mapping
    - Subzone-level safe-mode control
    - ACK message generation
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Subzone storage
        self.subzones: Dict[str, SubzoneConfigMock] = {}
        self.gpio_to_subzone: Dict[int, str] = {}  # GPIO -> subzone_id mapping

        # Error codes (matching error_codes.h)
        self.ERROR_SUBZONE_INVALID_ID = 2500
        self.ERROR_SUBZONE_GPIO_CONFLICT = 2501
        self.ERROR_SUBZONE_PARENT_MISMATCH = 2502
        self.ERROR_SUBZONE_NOT_FOUND = 2503
        self.ERROR_SUBZONE_GPIO_INVALID = 2504
        self.ERROR_SUBZONE_SAFE_MODE_FAILED = 2505
        self.ERROR_SUBZONE_CONFIG_SAVE_FAILED = 2506

        # Add subzone command handlers
        self._register_subzone_handlers()

    def _register_subzone_handlers(self):
        """Register subzone-specific command handlers."""
        # Override handle_command to include subzone commands
        original_handle = self.handle_command

        def extended_handle(command: str, params: Dict[str, Any]) -> Dict[str, Any]:
            subzone_handlers = {
                "subzone_assign": self._handle_subzone_assign,
                "subzone_remove": self._handle_subzone_remove,
                "subzone_safe_mode": self._handle_subzone_safe_mode,
                "subzone_status": self._handle_subzone_status,
            }

            handler = subzone_handlers.get(command)
            if handler:
                return handler(params)
            return original_handle(command, params)

        self.handle_command = extended_handle

    # =========================================================================
    # Subzone Command Handlers
    # =========================================================================

    def _handle_subzone_assign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle subzone assignment from Server.

        Matches ESP32 behavior from main.cpp lines 729-836.

        Expected params:
        {
            "subzone_id": "irrigation_section_A",
            "subzone_name": "Irrigation Section A",
            "parent_zone_id": "greenhouse_zone_1",
            "assigned_gpios": [4, 5, 6],
            "safe_mode_active": true,
            "timestamp": 1734523800
        }
        """
        subzone_id = params.get("subzone_id", "")
        subzone_name = params.get("subzone_name", "")
        parent_zone_id = params.get("parent_zone_id", "")
        assigned_gpios = params.get("assigned_gpios", [])
        safe_mode_active = params.get("safe_mode_active", True)

        # Validation 1: subzone_id required
        if not subzone_id or len(subzone_id) == 0:
            return self._send_subzone_ack(
                subzone_id or "unknown",
                "error",
                self.ERROR_SUBZONE_INVALID_ID,
                "subzone_id is required",
            )

        # Validation 2: Zone must be assigned
        if not self.zone or not self.zone.zone_id:
            return self._send_subzone_ack(
                subzone_id, "error", self.ERROR_SUBZONE_PARENT_MISMATCH, "ESP zone not assigned"
            )

        # Validation 3: parent_zone_id must match ESP zone
        if parent_zone_id and parent_zone_id != self.zone.zone_id:
            return self._send_subzone_ack(
                subzone_id,
                "error",
                self.ERROR_SUBZONE_PARENT_MISMATCH,
                f"parent_zone_id '{parent_zone_id}' doesn't match ESP zone '{self.zone.zone_id}'",
            )

        # Use ESP's zone_id if parent not provided
        actual_parent = parent_zone_id or self.zone.zone_id

        # Validation 4: Check GPIO conflicts
        for gpio in assigned_gpios:
            existing_subzone = self.gpio_to_subzone.get(gpio)
            if existing_subzone and existing_subzone != subzone_id:
                return self._send_subzone_ack(
                    subzone_id,
                    "error",
                    self.ERROR_SUBZONE_GPIO_CONFLICT,
                    f"GPIO {gpio} already assigned to subzone {existing_subzone}",
                )

        # Assignment successful - create or update subzone
        subzone = SubzoneConfigMock(
            subzone_id=subzone_id,
            subzone_name=subzone_name,
            parent_zone_id=actual_parent,
            assigned_gpios=assigned_gpios,
            safe_mode_active=safe_mode_active,
            created_timestamp=int(time.time()),
        )

        # Clear old GPIO mappings if updating
        if subzone_id in self.subzones:
            old_subzone = self.subzones[subzone_id]
            for gpio in old_subzone.assigned_gpios:
                if self.gpio_to_subzone.get(gpio) == subzone_id:
                    del self.gpio_to_subzone[gpio]

        # Store subzone and update GPIO mapping
        self.subzones[subzone_id] = subzone
        for gpio in assigned_gpios:
            self.gpio_to_subzone[gpio] = subzone_id

        # Enable safe-mode for subzone if requested
        if safe_mode_active:
            self._enable_safe_mode_for_subzone(subzone_id)

        # Send success ACK
        return self._send_subzone_ack(subzone_id, "subzone_assigned")

    def _handle_subzone_remove(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subzone removal from Server."""
        subzone_id = params.get("subzone_id", "")
        reason = params.get("reason", "manual")

        if subzone_id not in self.subzones:
            return self._send_subzone_ack(
                subzone_id,
                "error",
                self.ERROR_SUBZONE_NOT_FOUND,
                f"Subzone '{subzone_id}' not found",
            )

        # Enable safe-mode before removal
        self._enable_safe_mode_for_subzone(subzone_id)

        # Clear GPIO mappings
        subzone = self.subzones[subzone_id]
        for gpio in subzone.assigned_gpios:
            if self.gpio_to_subzone.get(gpio) == subzone_id:
                del self.gpio_to_subzone[gpio]

        # Remove subzone
        del self.subzones[subzone_id]

        return self._send_subzone_ack(subzone_id, "subzone_removed")

    def _handle_subzone_safe_mode(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subzone safe-mode control."""
        subzone_id = params.get("subzone_id", "")
        action = params.get("action", "enable")
        reason = params.get("reason", "manual")

        if subzone_id not in self.subzones:
            return self._send_subzone_ack(
                subzone_id,
                "error",
                self.ERROR_SUBZONE_NOT_FOUND,
                f"Subzone '{subzone_id}' not found",
            )

        subzone = self.subzones[subzone_id]

        if action == "enable":
            success = self._enable_safe_mode_for_subzone(subzone_id)
            subzone.safe_mode_active = True
        else:
            success = self._disable_safe_mode_for_subzone(subzone_id)
            subzone.safe_mode_active = False

        # Publish safe-mode status
        self._publish_subzone_safe_status(subzone_id, action == "enable", reason)

        return {
            "status": "ok",
            "subzone_id": subzone_id,
            "safe_mode_active": subzone.safe_mode_active,
        }

    def _handle_subzone_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subzone status request."""
        subzones_data = []
        for subzone_id, subzone in self.subzones.items():
            subzones_data.append(
                {
                    "subzone_id": subzone.subzone_id,
                    "subzone_name": subzone.subzone_name,
                    "parent_zone_id": subzone.parent_zone_id,
                    "assigned_gpios": subzone.assigned_gpios,
                    "safe_mode_active": subzone.safe_mode_active,
                    "gpio_count": len(subzone.assigned_gpios),
                }
            )

        return {
            "status": "ok",
            "esp_id": self.esp_id,
            "subzones": subzones_data,
            "total_count": len(subzones_data),
        }

    # =========================================================================
    # Safe-Mode Management
    # =========================================================================

    def _enable_safe_mode_for_subzone(self, subzone_id: str) -> bool:
        """Enable safe-mode for all GPIOs in a subzone."""
        if subzone_id not in self.subzones:
            return False

        subzone = self.subzones[subzone_id]

        # Stop all actuators in this subzone
        for gpio in subzone.assigned_gpios:
            if gpio in self.actuators:
                actuator = self.actuators[gpio]
                actuator.state = False
                actuator.pwm_value = 0.0
                actuator.emergency_stopped = True
                self._publish_actuator_status(gpio)

        return True

    def _disable_safe_mode_for_subzone(self, subzone_id: str) -> bool:
        """Disable safe-mode tracking for a subzone."""
        if subzone_id not in self.subzones:
            return False

        subzone = self.subzones[subzone_id]

        # Clear emergency stops for actuators in this subzone
        for gpio in subzone.assigned_gpios:
            if gpio in self.actuators:
                self.actuators[gpio].emergency_stopped = False

        return True

    # =========================================================================
    # ACK and Status Publishing
    # =========================================================================

    def _send_subzone_ack(
        self,
        subzone_id: str,
        status: str,
        error_code: Optional[int] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send subzone ACK message via MQTT."""
        payload = {
            "esp_id": self.esp_id,
            "status": status,
            "subzone_id": subzone_id,
            "ts": int(time.time()),
        }

        if error_code is not None:
            payload["error_code"] = error_code
        if message:
            payload["message"] = message

        topic = f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/subzone/ack"
        self.published_messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": 1,
                "retain": False,
            }
        )

        return {
            "status": status,
            "subzone_id": subzone_id,
            "error_code": error_code,
            "message": message,
        }

    def _publish_subzone_safe_status(self, subzone_id: str, safe_mode_active: bool, reason: str):
        """Publish subzone safe-mode status."""
        if subzone_id not in self.subzones:
            return

        subzone = self.subzones[subzone_id]
        payload = {
            "esp_id": self.esp_id,
            "subzone_id": subzone_id,
            "safe_mode_active": safe_mode_active,
            "isolated_gpios": subzone.assigned_gpios,
            "reason": reason,
            "timestamp": int(time.time()),
        }

        topic = f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/subzone/safe"
        self.published_messages.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": 1,
                "retain": False,
            }
        )

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    def get_subzone_config(self, subzone_id: str) -> Optional[SubzoneConfigMock]:
        """Get subzone configuration for testing."""
        return self.subzones.get(subzone_id)

    def get_subzone_for_gpio(self, gpio: int) -> Optional[str]:
        """Get subzone ID for a GPIO."""
        return self.gpio_to_subzone.get(gpio)

    def is_gpio_in_subzone(self, gpio: int, subzone_id: str) -> bool:
        """Check if GPIO is assigned to a specific subzone."""
        return self.gpio_to_subzone.get(gpio) == subzone_id


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_esp32_with_zone():
    """Create MockESP32 with zone configured."""
    esp = MockESP32WithSubzones(esp_id="ESP_TEST001")
    esp.configure_zone(
        zone_id="greenhouse_zone_1",
        master_zone_id="greenhouse_master",
        zone_name="Greenhouse Zone 1",
    )
    return esp


@pytest.fixture
def mock_esp32_no_zone():
    """Create MockESP32 without zone configured."""
    return MockESP32WithSubzones(esp_id="ESP_NO_ZONE")


@pytest.fixture
def mock_esp32_with_actuators():
    """Create MockESP32 with zone and pre-configured actuators."""
    esp = MockESP32WithSubzones(esp_id="ESP_ACTUATOR")
    esp.configure_zone(
        zone_id="greenhouse_zone_1",
        master_zone_id="greenhouse_master",
    )
    # Pre-configure actuators
    esp.configure_actuator(gpio=5, actuator_type="pump", name="Water Pump")
    esp.configure_actuator(gpio=6, actuator_type="valve", name="Water Valve")
    esp.configure_actuator(gpio=18, actuator_type="pwm", name="Fan Control")
    return esp


@pytest.fixture
def multiple_mock_esp32_with_zones():
    """Create multiple MockESP32s for cross-ESP testing."""
    esps = {}

    # ESP-A: Sensors station in zone A
    esp_a = MockESP32WithSubzones(esp_id="ESP_ZONE_A_SENSORS")
    esp_a.configure_zone(
        zone_id="greenhouse_zone_a",
        master_zone_id="greenhouse_master",
    )
    esp_a.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
    esp_a.set_sensor_value(gpio=21, raw_value=65.2, sensor_type="SHT31")
    esps["zone_a_sensors"] = esp_a

    # ESP-B: Actuators station in zone A
    esp_b = MockESP32WithSubzones(esp_id="ESP_ZONE_A_ACTUATORS")
    esp_b.configure_zone(
        zone_id="greenhouse_zone_a",
        master_zone_id="greenhouse_master",
    )
    esp_b.configure_actuator(gpio=5, actuator_type="pump")
    esp_b.configure_actuator(gpio=6, actuator_type="fan")
    esps["zone_a_actuators"] = esp_b

    # ESP-C: Different zone
    esp_c = MockESP32WithSubzones(esp_id="ESP_ZONE_B")
    esp_c.configure_zone(
        zone_id="greenhouse_zone_b",
        master_zone_id="greenhouse_master",
    )
    esps["zone_b"] = esp_c

    return esps


# =============================================================================
# Test: Subzone Assignment Flow
# =============================================================================


class TestSubzoneAssignment:
    """Test subzone assignment from Server to ESP32."""

    def test_subzone_assign_basic(self, mock_esp32_with_zone):
        """Test basic subzone assignment."""
        esp = mock_esp32_with_zone

        assignment_payload = {
            "subzone_id": "irrigation_pump",
            "subzone_name": "Irrigation Pump Control",
            "parent_zone_id": "greenhouse_zone_1",
            "assigned_gpios": [5, 6],
            "safe_mode_active": True,
            "timestamp": int(time.time()),
        }

        response = esp.handle_command("subzone_assign", assignment_payload)

        assert response["status"] == "subzone_assigned"
        assert response["subzone_id"] == "irrigation_pump"

        # Verify internal ESP configuration
        subzone = esp.get_subzone_config("irrigation_pump")
        assert subzone is not None
        assert subzone.assigned_gpios == [5, 6]
        assert subzone.safe_mode_active is True

        # Verify ACK message was published
        ack_messages = [
            msg for msg in esp.get_published_messages() if msg["topic"].endswith("/subzone/ack")
        ]
        assert len(ack_messages) == 1

        ack_payload = ack_messages[0]["payload"]
        assert ack_payload["status"] == "subzone_assigned"
        assert ack_payload["subzone_id"] == "irrigation_pump"

    def test_subzone_assign_zone_required(self, mock_esp32_no_zone):
        """Test subzone assignment fails without zone."""
        esp = mock_esp32_no_zone

        response = esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "test_subzone",
                "assigned_gpios": [5],
            },
        )

        assert response["status"] == "error"
        assert response["error_code"] == esp.ERROR_SUBZONE_PARENT_MISMATCH

    def test_subzone_assign_zone_mismatch(self, mock_esp32_with_zone):
        """Test subzone assignment fails with wrong parent_zone_id."""
        esp = mock_esp32_with_zone

        response = esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "test_subzone",
                "parent_zone_id": "wrong_zone",  # Doesn't match ESP zone
                "assigned_gpios": [5],
            },
        )

        assert response["status"] == "error"
        assert response["error_code"] == esp.ERROR_SUBZONE_PARENT_MISMATCH

    def test_subzone_assign_gpio_conflict(self, mock_esp32_with_zone):
        """Test GPIO conflict detection."""
        esp = mock_esp32_with_zone

        # First assignment
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "subzone_1",
                "assigned_gpios": [5],
                "safe_mode_active": True,
            },
        )

        # Second assignment with same GPIO
        response = esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "subzone_2",
                "assigned_gpios": [5],  # Conflict!
                "safe_mode_active": True,
            },
        )

        assert response["status"] == "error"
        assert response["error_code"] == esp.ERROR_SUBZONE_GPIO_CONFLICT
        assert "GPIO 5 already assigned" in response["message"]

    def test_subzone_update_same_id(self, mock_esp32_with_zone):
        """Test updating existing subzone (same ID)."""
        esp = mock_esp32_with_zone

        # Initial assignment
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "update_test",
                "assigned_gpios": [5, 6],
            },
        )

        # Update with new GPIOs
        response = esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "update_test",
                "assigned_gpios": [5, 6, 18],  # Added GPIO 18
            },
        )

        assert response["status"] == "subzone_assigned"

        subzone = esp.get_subzone_config("update_test")
        assert subzone.assigned_gpios == [5, 6, 18]


# =============================================================================
# Test: Safe-Mode Emergency Flow
# =============================================================================


class TestSubzoneSafeMode:
    """Test subzone safe-mode and emergency operations."""

    def test_safe_mode_enable(self, mock_esp32_with_actuators):
        """Test enabling safe-mode for subzone."""
        esp = mock_esp32_with_actuators

        # Create subzone with actuator GPIOs
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "emergency_test",
                "assigned_gpios": [5, 6],
                "safe_mode_active": False,
            },
        )

        # Activate actuators
        esp.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        esp.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # Verify actuators are active
        assert esp.get_actuator_state(5).state is True
        assert esp.get_actuator_state(6).state is True

        # Enable safe-mode
        response = esp.handle_command(
            "subzone_safe_mode",
            {
                "subzone_id": "emergency_test",
                "action": "enable",
                "reason": "emergency_stop",
            },
        )

        assert response["status"] == "ok"
        assert response["safe_mode_active"] is True

        # Verify actuators are stopped
        assert esp.get_actuator_state(5).state is False
        assert esp.get_actuator_state(6).state is False
        assert esp.get_actuator_state(5).emergency_stopped is True

    def test_safe_mode_disable(self, mock_esp32_with_actuators):
        """Test disabling safe-mode for subzone."""
        esp = mock_esp32_with_actuators

        # Create subzone in safe-mode
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "safe_test",
                "assigned_gpios": [5, 6],
                "safe_mode_active": True,
            },
        )

        # Disable safe-mode
        response = esp.handle_command(
            "subzone_safe_mode",
            {
                "subzone_id": "safe_test",
                "action": "disable",
                "reason": "normal_operation",
            },
        )

        assert response["status"] == "ok"
        assert response["safe_mode_active"] is False

        # Verify actuators can be controlled
        assert esp.get_actuator_state(5).emergency_stopped is False

    def test_actuator_blocked_in_safe_mode(self, mock_esp32_with_actuators):
        """Test actuators cannot be controlled when in safe-mode."""
        esp = mock_esp32_with_actuators

        # Create subzone with safe-mode active
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "blocked_test",
                "assigned_gpios": [5, 6],
                "safe_mode_active": True,
            },
        )

        # Try to activate actuator - should fail (emergency_stopped)
        response = esp.handle_command(
            "actuator_set",
            {
                "gpio": 5,
                "value": 1,
                "mode": "digital",
            },
        )

        assert response["status"] == "error"
        assert "emergency stopped" in response["error"].lower()


# =============================================================================
# Test: Subzone Removal Flow
# =============================================================================


class TestSubzoneRemoval:
    """Test subzone removal from Server to ESP32."""

    def test_subzone_remove_success(self, mock_esp32_with_zone):
        """Test successful subzone removal."""
        esp = mock_esp32_with_zone

        # Create subzone
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "to_remove",
                "assigned_gpios": [5, 6],
            },
        )

        # Verify it exists
        assert esp.get_subzone_config("to_remove") is not None

        # Remove it
        response = esp.handle_command(
            "subzone_remove",
            {
                "subzone_id": "to_remove",
                "reason": "maintenance",
            },
        )

        assert response["status"] == "subzone_removed"

        # Verify it's gone
        assert esp.get_subzone_config("to_remove") is None

        # Verify GPIOs are freed
        assert esp.get_subzone_for_gpio(5) is None
        assert esp.get_subzone_for_gpio(6) is None

    def test_subzone_remove_not_found(self, mock_esp32_with_zone):
        """Test removing non-existent subzone."""
        esp = mock_esp32_with_zone

        response = esp.handle_command(
            "subzone_remove",
            {
                "subzone_id": "non_existent",
            },
        )

        assert response["status"] == "error"
        assert response["error_code"] == esp.ERROR_SUBZONE_NOT_FOUND


# =============================================================================
# Test: Multi-ESP Subzone Coordination
# =============================================================================


class TestMultiESPSubzoneCoordination:
    """Test cross-ESP subzone coordination."""

    def test_cross_esp_zone_coordination(self, multiple_mock_esp32_with_zones):
        """Test subzone coordination across multiple ESPs in same zone."""
        esps = multiple_mock_esp32_with_zones

        # ESP-A (Sensors) - Zone-A
        esp_a = esps["zone_a_sensors"]
        esp_a.handle_command(
            "subzone_assign",
            {
                "subzone_id": "sensor_section",
                "assigned_gpios": [4, 21],
                "parent_zone_id": "greenhouse_zone_a",
            },
        )

        # ESP-B (Actuators) - Zone-A
        esp_b = esps["zone_a_actuators"]
        esp_b.handle_command(
            "subzone_assign",
            {
                "subzone_id": "actuator_section",
                "assigned_gpios": [5, 6],
                "parent_zone_id": "greenhouse_zone_a",
            },
        )

        # Both should have their subzones
        a_subzone = esp_a.get_subzone_config("sensor_section")
        b_subzone = esp_b.get_subzone_config("actuator_section")

        assert a_subzone is not None
        assert b_subzone is not None
        assert a_subzone.parent_zone_id == "greenhouse_zone_a"
        assert b_subzone.parent_zone_id == "greenhouse_zone_a"

        # Both should have sent ACKs
        a_acks = [
            msg
            for msg in esp_a.get_published_messages()
            if msg["payload"].get("status") == "subzone_assigned"
        ]
        b_acks = [
            msg
            for msg in esp_b.get_published_messages()
            if msg["payload"].get("status") == "subzone_assigned"
        ]

        assert len(a_acks) == 1
        assert len(b_acks) == 1

    def test_different_zones_isolation(self, multiple_mock_esp32_with_zones):
        """Test subzones in different zones are isolated."""
        esps = multiple_mock_esp32_with_zones

        esp_a = esps["zone_a_sensors"]
        esp_b = esps["zone_b"]

        # Create subzone in zone A
        esp_a.handle_command(
            "subzone_assign",
            {
                "subzone_id": "zone_a_subzone",
                "assigned_gpios": [4],
            },
        )

        # Create subzone with same ID in zone B (should succeed - different ESP)
        esp_b.handle_command(
            "subzone_assign",
            {
                "subzone_id": "zone_b_subzone",
                "assigned_gpios": [4],  # Same GPIO, different ESP
            },
        )

        # Both should succeed independently
        assert esp_a.get_subzone_config("zone_a_subzone") is not None
        assert esp_b.get_subzone_config("zone_b_subzone") is not None


# =============================================================================
# Test: GPIO-Subzone Mapping
# =============================================================================


class TestGPIOSubzoneMapping:
    """Test GPIO to subzone mapping."""

    def test_gpio_mapping_created(self, mock_esp32_with_zone):
        """Test GPIO-to-subzone mapping is created."""
        esp = mock_esp32_with_zone

        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "mapping_test",
                "assigned_gpios": [4, 5, 6],
            },
        )

        # Verify mapping
        assert esp.is_gpio_in_subzone(4, "mapping_test")
        assert esp.is_gpio_in_subzone(5, "mapping_test")
        assert esp.is_gpio_in_subzone(6, "mapping_test")
        assert not esp.is_gpio_in_subzone(18, "mapping_test")

    def test_gpio_mapping_cleared_on_update(self, mock_esp32_with_zone):
        """Test GPIO mapping is cleared when subzone is updated."""
        esp = mock_esp32_with_zone

        # Initial assignment with GPIOs 4, 5
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "update_mapping",
                "assigned_gpios": [4, 5],
            },
        )

        assert esp.is_gpio_in_subzone(4, "update_mapping")
        assert esp.is_gpio_in_subzone(5, "update_mapping")

        # Update to only GPIO 6
        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "update_mapping",
                "assigned_gpios": [6],
            },
        )

        # Old GPIOs should be unmapped
        assert not esp.is_gpio_in_subzone(4, "update_mapping")
        assert not esp.is_gpio_in_subzone(5, "update_mapping")
        # New GPIO should be mapped
        assert esp.is_gpio_in_subzone(6, "update_mapping")


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestSubzoneErrorHandling:
    """Test error handling in subzone operations."""

    def test_invalid_subzone_id(self, mock_esp32_with_zone):
        """Test handling of invalid subzone_id."""
        esp = mock_esp32_with_zone

        response = esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "",  # Empty ID
                "assigned_gpios": [5],
            },
        )

        assert response["status"] == "error"
        assert response["error_code"] == esp.ERROR_SUBZONE_INVALID_ID

    def test_error_ack_contains_all_fields(self, mock_esp32_no_zone):
        """Test error ACK contains all required fields."""
        esp = mock_esp32_no_zone

        esp.handle_command(
            "subzone_assign",
            {
                "subzone_id": "error_test",
                "assigned_gpios": [5],
            },
        )

        # Find error ACK
        ack_messages = [
            msg for msg in esp.get_published_messages() if msg["payload"].get("status") == "error"
        ]

        assert len(ack_messages) == 1
        ack = ack_messages[0]["payload"]

        assert "esp_id" in ack
        assert "status" in ack
        assert "subzone_id" in ack
        assert "error_code" in ack
        assert "message" in ack
        assert "ts" in ack
