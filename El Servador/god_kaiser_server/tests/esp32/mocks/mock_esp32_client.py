"""
Mock ESP32 Client - Production-accurate simulation of ESP32 MQTT behavior.

This mock provides FULL compatibility with the real ESP32 firmware from El Trabajante.
It simulates:
- Complete MQTT message structure (all fields from Mqtt_Protocoll.md)
- Zone management and subzone assignment
- Multi-value sensors (e.g., SHT31 with temp + humidity)
- System state machine (12 states)
- Actuator response/alert topics
- Batch sensor publishing
- Library management system
- Complete heartbeat with system metrics
- Bidirectional config topics

Topic structure matches production EXACTLY:
- kaiser/god/esp/{esp_id}/sensor/{gpio}/data
- kaiser/god/esp/{esp_id}/sensor/batch
- kaiser/god/esp/{esp_id}/actuator/{gpio}/command
- kaiser/god/esp/{esp_id}/actuator/{gpio}/status
- kaiser/god/esp/{esp_id}/actuator/{gpio}/response
- kaiser/god/esp/{esp_id}/actuator/{gpio}/alert
- kaiser/god/esp/{esp_id}/actuator/emergency
- kaiser/god/esp/{esp_id}/system/heartbeat
- kaiser/god/esp/{esp_id}/system/command
- kaiser/god/esp/{esp_id}/system/response
- kaiser/god/esp/{esp_id}/system/diagnostics
- kaiser/god/esp/{esp_id}/config
- kaiser/god/esp/{esp_id}/library/ready
- kaiser/god/esp/{esp_id}/library/request
- kaiser/god/esp/{esp_id}/library/installed
- kaiser/god/esp/{esp_id}/library/error
- kaiser/god/zone/{master_zone_id}/esp/{esp_id}/subzone/{subzone_id}/sensor/{gpio}/data
- kaiser/broadcast/emergency
- kaiser/broadcast/system_update

See: El Trabajante/docs/Mqtt_Protocoll.md for full specification.
"""

import json
import logging
import time
import random
from typing import Dict, Any, Optional, Callable, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

# Import TopicBuilder for consistent topic generation
from src.mqtt.topics import TopicBuilder

logger = logging.getLogger(__name__)


# =============================================================================
# Broker Mode (Phase 3: MQTT Broker Integration)
# =============================================================================
class BrokerMode(str, Enum):
    """Mode for MQTT message handling."""

    DIRECT = "direct"  # Default: In-memory storage only (fast, no broker needed)
    MQTT = "mqtt"  # Publish to real MQTT broker (for end-to-end tests)


# =============================================================================
# System State Machine (12 states from Mqtt_Protocoll.md)
# =============================================================================
class SystemState(Enum):
    """ESP32 System States - matches El Trabajante implementation."""

    BOOT = 0
    WIFI_SETUP = 1
    WIFI_CONNECTED = 2
    MQTT_CONNECTING = 3
    MQTT_CONNECTED = 4
    AWAITING_USER_CONFIG = 5
    ZONE_CONFIGURED = 6
    SENSORS_CONFIGURED = 7
    OPERATIONAL = 8
    LIBRARY_DOWNLOADING = 9
    SAFE_MODE = 10
    ERROR = 11


class QualityLevel(Enum):
    """Sensor quality levels."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    BAD = "bad"
    STALE = "stale"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class ActuatorState:
    """State of a single actuator - matches El Trabajante ActuatorStatus."""

    gpio: int
    actuator_type: str  # "pump", "valve", "fan", "relay", "pwm_motor"
    state: bool  # on/off
    pwm_value: float = 0.0  # 0.0-1.0 for PWM actuators
    target_value: float = 0.0
    last_command: Optional[str] = None
    last_command_id: Optional[str] = None
    emergency_stopped: bool = False
    timestamp: float = field(default_factory=time.time)
    # Additional fields from real ESP32
    name: str = ""
    min_value: float = 0.0
    max_value: float = 1.0
    safety_timeout_ms: int = 0
    inverted: bool = False


@dataclass
class SensorState:
    """State of a single sensor - matches El Trabajante SensorReading."""

    gpio: int
    sensor_type: str  # "DS18B20", "SHT31", "analog", "digital", "pH", etc.
    raw_value: float = 0.0
    processed_value: Optional[float] = None
    unit: str = ""
    quality: str = "good"
    last_read: float = field(default_factory=time.time)
    # Additional fields from real ESP32
    name: str = ""
    library_name: str = ""
    library_version: str = "1.0.0"
    subzone_id: Optional[str] = None
    calibration: Optional[Dict[str, float]] = None
    raw_mode: bool = False
    # For multi-value sensors
    is_multi_value: bool = False
    secondary_values: Optional[Dict[str, float]] = None  # e.g., {"humidity": 65.2}


@dataclass
class ZoneConfig:
    """Zone configuration."""

    zone_id: str
    zone_name: str
    master_zone_id: str
    subzone_id: Optional[str] = None
    subzone_name: Optional[str] = None


@dataclass
class LibraryInfo:
    """Sensor library information."""

    name: str
    version: str
    sensor_type: str
    installed: bool = False
    download_url: Optional[str] = None


# =============================================================================
# MockESP32Client - Production-Accurate Implementation
# =============================================================================
class MockESP32Client:
    """
    Mock ESP32 Client that FULLY simulates ESP32 behavior from El Trabajante.

    This implementation matches the MQTT protocol specification exactly,
    enabling tests to validate against both mock and real hardware.

    Usage:
        mock = MockESP32Client(esp_id="ESP_12AB34CD")
        mock.configure_zone("greenhouse", "main-zone", "zone-a")
        mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        response = mock.handle_command("sensor_read", {"gpio": 4})
    """

    def __init__(
        self,
        esp_id: str = "ESP_TEST001",
        kaiser_id: str = "god",
        auto_heartbeat: bool = False,
        broker_mode: BrokerMode = BrokerMode.DIRECT,
        mqtt_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Mock ESP32 Client.

        Args:
            esp_id: ESP32 device ID (format: ESP_XXXXXXXX)
            kaiser_id: Kaiser/God-Kaiser ID
            auto_heartbeat: Automatically publish heartbeat
            broker_mode: DIRECT (in-memory) or MQTT (real broker)
            mqtt_config: MQTT broker configuration (host, port, username, password)
        """
        self.esp_id = esp_id
        self.kaiser_id = kaiser_id
        self.auto_heartbeat = auto_heartbeat
        self.boot_time = time.time()

        # Broker mode (Phase 3)
        self.broker_mode = broker_mode
        self._mqtt_client: Optional[Any] = None  # paho.mqtt.client.Client
        self._mqtt_connected = False

        # State management
        self.actuators: Dict[int, ActuatorState] = {}
        self.sensors: Dict[int, SensorState] = {}
        self.libraries: Dict[str, LibraryInfo] = {}

        # Zone configuration
        self.zone: Optional[ZoneConfig] = None

        # System state machine
        self.system_state = SystemState.OPERATIONAL
        self.previous_state = SystemState.BOOT

        # System metrics (for heartbeat)
        self.heap_free = 245760  # Simulated heap
        self.wifi_rssi = -65  # Simulated WiFi strength

        # Config storage
        self.config: Dict[str, Any] = {
            "wifi": {"ssid": "MockWiFi", "connected": True, "ip": "192.168.1.100"},
            "mqtt": {"broker": "localhost", "port": 1883, "connected": True},
            "zone": None,  # Zone configuration (set via configure_zone())
            "system": {
                "version": "1.0.0-mock",
                "firmware": "el-trabajante-v1.0.0",
                "uptime": 0,
                "chip_id": esp_id,
            },
            "sensors": {},
            "actuators": {},
        }

        # Communication state
        self.connected = True
        self.last_heartbeat = time.time()
        self.last_response: Optional[Dict[str, Any]] = None
        self.published_messages: List[Dict[str, Any]] = []
        self.subscribed_topics: List[str] = []

        # Command tracking
        self.command_counter = 0
        self.pending_commands: Dict[str, Dict[str, Any]] = {}

        # Callbacks for custom behavior
        self.on_command: Optional[Callable] = None
        self.on_publish: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None

        # Connect to MQTT broker if in MQTT mode
        if broker_mode == BrokerMode.MQTT:
            self._connect_mqtt(mqtt_config or {"host": "localhost", "port": 1883})

    # =========================================================================
    # MQTT Broker Connection (Phase 3)
    # =========================================================================
    def _connect_mqtt(self, config: Dict[str, Any]) -> bool:
        """
        Connect to real MQTT broker.

        Args:
            config: Broker configuration with host, port, username, password

        Returns:
            True if connection successful
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt not installed. Install with: pip install paho-mqtt")
            return False

        try:
            client_id = f"mock_{self.esp_id}_{int(time.time() * 1000) % 100000}"
            self._mqtt_client = mqtt.Client(client_id=client_id)

            # Set credentials if provided
            if config.get("username"):
                self._mqtt_client.username_pw_set(config["username"], config.get("password", ""))

            # Connection callbacks
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self._mqtt_connected = True
                    logger.info(f"MockESP32Client {self.esp_id} connected to MQTT broker")
                else:
                    logger.error(f"MockESP32Client {self.esp_id} MQTT connect failed: rc={rc}")

            def on_disconnect(client, userdata, rc):
                self._mqtt_connected = False
                logger.info(f"MockESP32Client {self.esp_id} disconnected from MQTT broker")

            self._mqtt_client.on_connect = on_connect
            self._mqtt_client.on_disconnect = on_disconnect

            # Connect
            self._mqtt_client.connect(
                config.get("host", "localhost"), config.get("port", 1883), keepalive=60
            )
            self._mqtt_client.loop_start()

            # Wait briefly for connection
            time.sleep(0.1)
            return self._mqtt_connected

        except Exception as e:
            logger.error(f"MockESP32Client {self.esp_id} MQTT connection failed: {e}")
            return False

    def _publish_to_broker(
        self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False
    ):
        """
        Publish message to real MQTT broker if connected.

        This is called after storing in published_messages list.
        Messages are always stored locally for test assertions.

        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON serialized)
            qos: Quality of Service level (0, 1, or 2)
            retain: Retain flag
        """
        if self.broker_mode == BrokerMode.MQTT and self._mqtt_client and self._mqtt_connected:
            try:
                result = self._mqtt_client.publish(
                    topic, json.dumps(payload), qos=qos, retain=retain
                )
                if result.rc != 0:
                    logger.warning(f"MQTT publish to {topic} failed: rc={result.rc}")
            except Exception as e:
                logger.error(f"MQTT publish error: {e}")

    def disconnect_mqtt(self):
        """Disconnect from MQTT broker and clean up."""
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception as e:
                logger.warning(f"MQTT disconnect error: {e}")
            finally:
                self._mqtt_client = None
                self._mqtt_connected = False

    def is_broker_connected(self) -> bool:
        """Check if connected to MQTT broker."""
        return self._mqtt_connected

    def _store_and_publish(
        self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False
    ):
        """
        Store message locally and publish to broker if connected.

        This is the primary method for all publish operations.
        Messages are always stored in published_messages for test assertions.
        If in MQTT mode, also publishes to the real broker.

        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service (0, 1, 2)
            retain: Retain flag
        """
        message = {"topic": topic, "payload": payload, "qos": qos, "retain": retain}
        self.published_messages.append(message)
        self._publish_to_broker(topic, payload, qos, retain)

        # Also call on_publish callback if set (for server-side MQTT integration)
        # This allows the MockESPManager to route messages through the real MQTT client
        if self.on_publish:
            self.on_publish(topic, payload, qos)

    # =========================================================================
    # Zone Management
    # =========================================================================
    def configure_zone(
        self,
        zone_id: str,
        master_zone_id: str,
        subzone_id: Optional[str] = None,
        zone_name: str = "",
        subzone_name: str = "",
    ):
        """Configure zone assignment for this ESP32."""
        self.zone = ZoneConfig(
            zone_id=zone_id,
            zone_name=zone_name or zone_id,
            master_zone_id=master_zone_id,
            subzone_id=subzone_id,
            subzone_name=subzone_name or subzone_id,
        )

        # Update config
        self.config["zone"] = {
            "id": zone_id,
            "name": zone_name or zone_id,
            "master_zone_id": master_zone_id,
            "subzone_id": subzone_id,
            "subzone_name": subzone_name,
        }

        # Transition state
        if self.system_state == SystemState.AWAITING_USER_CONFIG:
            self._transition_state(SystemState.ZONE_CONFIGURED)

    def get_zone_topic_prefix(self) -> Optional[str]:
        """Get zone-based topic prefix if configured."""
        if self.zone and self.zone.subzone_id:
            return f"kaiser/{self.kaiser_id}/zone/{self.zone.master_zone_id}/esp/{self.esp_id}/subzone/{self.zone.subzone_id}"
        return None

    # =========================================================================
    # State Machine
    # =========================================================================
    def _transition_state(self, new_state: SystemState):
        """Transition to new system state."""
        self.previous_state = self.system_state
        self.system_state = new_state

        # Publish state change
        self._publish_system_diagnostics(
            {
                "event": "state_change",
                "from_state": self.previous_state.name,
                "to_state": new_state.name,
            }
        )

        if self.on_state_change:
            self.on_state_change(self.previous_state, new_state)

    def enter_safe_mode(self, reason: str = "manual"):
        """Enter safe mode - all actuators de-energized."""
        self._transition_state(SystemState.SAFE_MODE)

        # Stop all actuators
        for gpio in self.actuators:
            self.actuators[gpio].state = False
            self.actuators[gpio].pwm_value = 0.0
            self.actuators[gpio].emergency_stopped = True

        self._publish_safe_mode_status(reason)

    def exit_safe_mode(self):
        """Exit safe mode and return to operational."""
        if self.system_state == SystemState.SAFE_MODE:
            # Clear emergency stops
            for gpio in self.actuators:
                self.actuators[gpio].emergency_stopped = False

            self._transition_state(SystemState.OPERATIONAL)

    # =========================================================================
    # Command Handler
    # =========================================================================
    def handle_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming command and return response.

        Supported commands:
        - ping: Heartbeat/registration
        - actuator_set: Control actuator
        - actuator_get: Get actuator state
        - sensor_read: Read single sensor
        - sensor_batch: Read all sensors (batch)
        - config_get: Get configuration
        - config_set: Set configuration
        - emergency_stop: Stop all actuators
        - reset: Reset ESP32 state
        - library_install: Install sensor library
        - library_list: List installed libraries
        - system_command: System-level commands
        - diagnostics: Get system diagnostics
        """
        self.command_counter += 1
        command_id = f"cmd_{self.command_counter:06d}"

        if self.on_command:
            result = self.on_command(command, params)
            if result:
                return result

        handlers = {
            "ping": self._handle_ping,
            "actuator_set": self._handle_actuator_set,
            "actuator_get": self._handle_actuator_get,
            "sensor_read": self._handle_sensor_read,
            "sensor_batch": self._handle_sensor_batch,
            "config": self._handle_config,
            "config_get": self._handle_config_get,
            "config_set": self._handle_config_set,
            "emergency_stop": self._handle_emergency_stop,
            "clear_emergency": self._handle_clear_emergency,
            "reset": self._handle_reset,
            "library_install": self._handle_library_install,
            "library_list": self._handle_library_list,
            "system_command": self._handle_system_command,
            "diagnostics": self._handle_diagnostics,
            "heartbeat": self._handle_heartbeat,
        }

        handler = handlers.get(command)
        if not handler:
            return self._error_response(f"Unknown command: {command}", command_id)

        try:
            response = handler(params, command_id)
            self.last_response = response
            return response
        except Exception as e:
            return self._error_response(str(e), command_id)

    def _error_response(self, error: str, command_id: str) -> Dict[str, Any]:
        """Generate error response."""
        return {
            "status": "error",
            "error": error,
            "command_id": command_id,
            "esp_id": self.esp_id,
            "timestamp": time.time(),
        }

    # =========================================================================
    # Command Handlers
    # =========================================================================
    def _handle_ping(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle ping command - returns full heartbeat data."""
        self.last_heartbeat = time.time()
        uptime = int(time.time() - self.boot_time)

        response = {
            "status": "ok",
            "command": "pong",
            "command_id": command_id,
            "esp_id": self.esp_id,
            "zone_id": self.zone.zone_id if self.zone else None,
            "master_zone_id": self.zone.master_zone_id if self.zone else None,
            "zone_assigned": self.zone is not None,
            "ts": int(time.time()),
            "uptime": uptime,
            "heap_free": self.heap_free,
            "wifi_rssi": self.wifi_rssi,
            "sensor_count": len(self.sensors),
            "actuator_count": len(self.actuators),
            "state": self.system_state.name,
            "timestamp": time.time(),
        }

        # Publish heartbeat
        self._publish_heartbeat()

        return response

    def _handle_actuator_set(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle actuator set command with full response/alert topics."""
        gpio = params.get("gpio")
        value = params.get("value")
        mode = params.get("mode", "digital")
        actuator_type = params.get("type", "relay")
        name = params.get("name", f"actuator_{gpio}")

        if gpio is None or value is None:
            response = self._error_response("Missing gpio or value parameter", command_id)
            self._publish_actuator_response(gpio or 0, command_id, False, "Missing parameter")
            return response

        # Check zone configuration (ESP without zone cannot control actuators)
        if self.zone is None:
            response = self._error_response(
                "Zone not configured. Configure zone via MQTT or web interface before controlling actuators.",
                command_id,
            )
            self._publish_actuator_alert(
                gpio, "zone_not_configured", "Actuator command rejected - zone not configured"
            )
            return response

        # Check safe mode
        if self.system_state == SystemState.SAFE_MODE:
            response = self._error_response("System in SAFE_MODE - actuators disabled", command_id)
            self._publish_actuator_alert(
                gpio, "safe_mode", "Actuator command rejected - SAFE_MODE active"
            )
            return response

        # Create or update actuator state
        if gpio not in self.actuators:
            self.actuators[gpio] = ActuatorState(
                gpio=gpio, actuator_type=actuator_type, state=False, pwm_value=0.0, name=name
            )

        actuator = self.actuators[gpio]
        min_value = actuator.min_value if actuator.min_value is not None else 0.0
        max_value = actuator.max_value if actuator.max_value is not None else 1.0

        # Check emergency stop
        if actuator.emergency_stopped:
            response = self._error_response(f"Actuator {gpio} is emergency stopped", command_id)
            self._publish_actuator_alert(
                gpio, "emergency_stopped", "Command rejected - clear emergency first"
            )
            return response

        # Apply value
        if mode == "pwm":
            clamped_value = max(min_value, min(max_value, float(value)))
            actuator.pwm_value = clamped_value
            actuator.state = clamped_value > 0
            actuator.target_value = clamped_value
        else:
            actuator.state = bool(value)
            actuator.pwm_value = 1.0 if actuator.state else 0.0
            actuator.target_value = actuator.pwm_value

        actuator.last_command = f"set_{mode}"
        actuator.last_command_id = command_id
        actuator.timestamp = time.time()

        # Publish status and response
        self._publish_actuator_status(gpio)
        self._publish_actuator_response(gpio, command_id, True, "Command executed")

        return {
            "status": "ok",
            "command": "actuator_set",
            "command_id": command_id,
            "gpio": gpio,
            "state": actuator.state,
            "pwm_value": actuator.pwm_value,
            "data": {
                "gpio": gpio,
                "type": actuator.actuator_type,
                "name": actuator.name,
                "state": actuator.state,
                "pwm_value": actuator.pwm_value,
                "target_value": actuator.target_value,
                "mode": mode,
            },
            "timestamp": actuator.timestamp,
        }

    def _handle_actuator_get(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle actuator get command."""
        gpio = params.get("gpio")

        if gpio is None:
            # Return all actuators
            return {
                "status": "ok",
                "command": "actuator_get",
                "command_id": command_id,
                "data": {
                    "actuators": {
                        str(gpio): {
                            "gpio": gpio,
                            "type": act.actuator_type,
                            "name": act.name,
                            "state": act.state,
                            "pwm_value": act.pwm_value,
                            "target_value": act.target_value,
                            "emergency_stopped": act.emergency_stopped,
                            "last_command": act.last_command,
                            "timestamp": act.timestamp,
                        }
                        for gpio, act in self.actuators.items()
                    }
                },
                "timestamp": time.time(),
            }

        if gpio not in self.actuators:
            return self._error_response(f"Actuator on GPIO {gpio} not found", command_id)

        actuator = self.actuators[gpio]
        return {
            "status": "ok",
            "command": "actuator_get",
            "command_id": command_id,
            "gpio": gpio,
            "data": {
                "gpio": gpio,
                "type": actuator.actuator_type,
                "name": actuator.name,
                "state": actuator.state,
                "pwm_value": actuator.pwm_value,
                "target_value": actuator.target_value,
                "emergency_stopped": actuator.emergency_stopped,
                "last_command": actuator.last_command,
            },
            "timestamp": actuator.timestamp,
        }

    def _handle_sensor_read(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle sensor read command with full payload structure."""
        gpio = params.get("gpio")

        if gpio is None:
            return self._error_response("Missing gpio parameter", command_id)

        if gpio not in self.sensors:
            # Create mock sensor with default value
            self.sensors[gpio] = SensorState(
                gpio=gpio, sensor_type="analog", raw_value=0.0, unit="raw", name=f"sensor_{gpio}"
            )

        sensor = self.sensors[gpio]
        sensor.last_read = time.time()

        # Publish sensor data (single and optionally zone-based)
        self._publish_sensor_data(gpio)

        # If multi-value sensor, also publish secondary values
        if sensor.is_multi_value and sensor.secondary_values:
            for value_name, value in sensor.secondary_values.items():
                self._publish_sensor_data(gpio, secondary_value_name=value_name)

        response_data = self._build_sensor_response_data(sensor)

        return {
            "status": "ok",
            "command": "sensor_read",
            "command_id": command_id,
            "gpio": gpio,
            "data": response_data,
            "timestamp": sensor.last_read,
        }

    def _handle_sensor_batch(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle batch sensor read - all sensors at once."""
        readings = []

        for gpio, sensor in self.sensors.items():
            sensor.last_read = time.time()
            reading = self._build_sensor_response_data(sensor)
            readings.append(reading)

            # Also publish individual sensor data (including zone topics)
            self._publish_sensor_data(gpio)

            # If multi-value sensor, also publish secondary values
            if sensor.is_multi_value and sensor.secondary_values:
                for value_name in sensor.secondary_values.keys():
                    self._publish_sensor_data(gpio, secondary_value_name=value_name)

        # Publish batch message
        self._publish_sensor_batch(readings)

        return {
            "status": "ok",
            "command": "sensor_batch",
            "command_id": command_id,
            "data": {"sensors": readings, "count": len(readings)},
            "timestamp": time.time(),
        }

    def _handle_config(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """
        Handle full config command (sensors, actuators, zone, etc.).

        This simulates the ESP32 receiving a config message from the server
        with sensor and actuator configurations to apply.
        """
        configured_sensors = []
        configured_actuators = []
        failures = []

        # Process sensors configuration
        sensors_config = params.get("sensors", [])
        for sensor_cfg in sensors_config:
            gpio = sensor_cfg.get("gpio")
            if gpio is None:
                failures.append({"field": "gpio", "error": "missing"})
                continue

            sensor_type = sensor_cfg.get("sensor_type", "analog")
            sensor_name = sensor_cfg.get("sensor_name", sensor_cfg.get("name", ""))
            active = sensor_cfg.get("active", True)

            if active:
                # Create sensor state
                self.sensors[gpio] = SensorState(
                    gpio=gpio,
                    sensor_type=sensor_type,
                    raw_value=0.0,
                    name=sensor_name or f"{sensor_type}_{gpio}",
                    quality="good",
                )
                configured_sensors.append(gpio)

        # Process actuators configuration
        actuators_config = params.get("actuators", [])
        for actuator_cfg in actuators_config:
            gpio = actuator_cfg.get("gpio")
            if gpio is None:
                failures.append({"field": "gpio", "error": "missing"})
                continue

            actuator_type = actuator_cfg.get("actuator_type", "relay")
            actuator_name = actuator_cfg.get("actuator_name", actuator_cfg.get("name", ""))
            active = actuator_cfg.get("active", True)

            if active:
                # Create actuator state
                self.actuators[gpio] = ActuatorState(
                    gpio=gpio,
                    actuator_type=actuator_type,
                    state=False,
                    pwm_value=0.0,
                    name=actuator_name or f"{actuator_type}_{gpio}",
                )
                configured_actuators.append(gpio)

        # Publish config response
        status = "ok" if not failures else "partial"
        response_payload = {
            "esp_id": self.esp_id,
            "command_id": command_id,
            "status": status,
            "configured_sensors": configured_sensors,
            "configured_actuators": configured_actuators,
            "failures": failures,
            "timestamp": time.time(),
        }

        self.published_messages.append(
            {
                "topic": TopicBuilder.build_config_response_topic(self.esp_id, self.kaiser_id),
                "payload": response_payload,
                "qos": 1,
                "retain": False,
            }
        )

        return {
            "status": status,
            "command": "config",
            "command_id": command_id,
            "data": {
                "configured_sensors": configured_sensors,
                "configured_actuators": configured_actuators,
                "failures": failures,
            },
            "timestamp": time.time(),
        }

    def _handle_config_get(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle config get command."""
        key = params.get("key")

        if key:
            value = self.config.get(key)
            return {
                "status": "ok",
                "command": "config_get",
                "command_id": command_id,
                "data": {"key": key, "value": value},
                "timestamp": time.time(),
            }

        # Return all config
        return {
            "status": "ok",
            "command": "config_get",
            "command_id": command_id,
            "data": {"config": self.config},
            "timestamp": time.time(),
        }

    def _handle_config_set(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle config set command with bidirectional topic publishing."""
        key = params.get("key")
        value = params.get("value")

        if key is None or value is None:
            return self._error_response("Missing key or value parameter", command_id)

        self.config[key] = value

        # Publish config update to config topic
        self._publish_config_update(key, value)

        return {
            "status": "ok",
            "command": "config_set",
            "command_id": command_id,
            "data": {"key": key, "value": value},
            "timestamp": time.time(),
        }

    def _handle_emergency_stop(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle emergency stop command."""
        stopped_actuators = []
        timestamp = time.time()

        for gpio, actuator in self.actuators.items():
            actuator.state = False
            actuator.pwm_value = 0.0
            actuator.emergency_stopped = True
            actuator.last_command = "emergency_stop"
            actuator.last_command_id = command_id
            actuator.timestamp = timestamp
            self._publish_actuator_status(gpio)
            self._publish_actuator_alert(gpio, "emergency_stop", "Emergency stop activated")
            stopped_actuators.append(gpio)

        # Publish to device-specific emergency topic
        self.published_messages.append(
            {
                "topic": TopicBuilder.build_actuator_emergency_topic(self.esp_id, self.kaiser_id),
                "payload": {
                    "esp_id": self.esp_id,
                    "command_id": command_id,
                    "stopped_actuators": stopped_actuators,
                    "timestamp": timestamp,
                    "reason": params.get("reason", "manual"),
                },
                "qos": 1,
                "retain": False,
            }
        )

        # Publish to broadcast topic
        self.published_messages.append(
            {
                "topic": "kaiser/broadcast/emergency",
                "payload": {
                    "esp_id": self.esp_id,
                    "command_id": command_id,
                    "stopped_actuators": stopped_actuators,
                    "timestamp": timestamp,
                    "reason": params.get("reason", "manual"),
                },
                "qos": 1,
                "retain": False,
            }
        )

        return {
            "status": "ok",
            "command": "emergency_stop",
            "command_id": command_id,
            "stopped_actuators": stopped_actuators,
            "timestamp": timestamp,
        }

    def _handle_clear_emergency(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """
        Handle clear emergency command - allows recovery after emergency stop.

        Params:
            gpio: Optional - clear specific actuator. If not provided, clears all.

        This command MUST be called before actuators can be controlled again
        after an emergency stop.
        """
        gpio = params.get("gpio")
        timestamp = time.time()
        cleared_actuators = []

        if gpio is not None:
            # Clear specific actuator
            if gpio in self.actuators:
                self.actuators[gpio].emergency_stopped = False
                cleared_actuators.append(gpio)
                self._publish_actuator_status(gpio)
            else:
                return self._error_response(f"Actuator on GPIO {gpio} not found", command_id)
        else:
            # Clear all actuators
            for act_gpio, actuator in self.actuators.items():
                if actuator.emergency_stopped:
                    actuator.emergency_stopped = False
                    cleared_actuators.append(act_gpio)
                    self._publish_actuator_status(act_gpio)

        # Publish system response
        self._publish_system_response(command_id, "clear_emergency", True)

        return {
            "status": "ok",
            "command": "clear_emergency",
            "command_id": command_id,
            "cleared_actuators": cleared_actuators,
            "timestamp": timestamp,
        }

    def _handle_reset(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle reset command."""
        self.actuators.clear()
        self.sensors.clear()
        self.published_messages.clear()
        self.pending_commands.clear()
        self.boot_time = time.time()

        # Reset state machine
        self.system_state = SystemState.OPERATIONAL

        return {
            "status": "ok",
            "command": "reset",
            "command_id": command_id,
            "timestamp": time.time(),
        }

    def _handle_library_install(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle library installation request."""
        library_name = params.get("name")
        library_version = params.get("version", "latest")
        sensor_type = params.get("sensor_type")

        if not library_name:
            return self._error_response("Missing library name", command_id)

        # Simulate library installation
        self.libraries[library_name] = LibraryInfo(
            name=library_name,
            version=library_version,
            sensor_type=sensor_type or "unknown",
            installed=True,
        )

        # Transition state during download
        old_state = self.system_state
        self._transition_state(SystemState.LIBRARY_DOWNLOADING)

        # Publish library events
        self._publish_library_event("ready", library_name, library_version)
        self._publish_library_event("installed", library_name, library_version)

        # Return to previous state
        self._transition_state(old_state)

        return {
            "status": "ok",
            "command": "library_install",
            "command_id": command_id,
            "data": {"name": library_name, "version": library_version, "installed": True},
            "timestamp": time.time(),
        }

    def _handle_library_list(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle library list request."""
        return {
            "status": "ok",
            "command": "library_list",
            "command_id": command_id,
            "data": {
                "libraries": {
                    name: {
                        "name": lib.name,
                        "version": lib.version,
                        "sensor_type": lib.sensor_type,
                        "installed": lib.installed,
                    }
                    for name, lib in self.libraries.items()
                }
            },
            "timestamp": time.time(),
        }

    def _handle_system_command(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle system-level commands."""
        action = params.get("action")

        actions = {
            "reboot": self._system_reboot,
            "factory_reset": self._system_factory_reset,
            "enter_safe_mode": lambda: self.enter_safe_mode("command"),
            "exit_safe_mode": self.exit_safe_mode,
            "update_firmware": self._system_update_firmware,
        }

        handler = actions.get(action)
        if not handler:
            return self._error_response(f"Unknown system action: {action}", command_id)

        handler()

        # Publish response
        self._publish_system_response(command_id, action, True)

        return {
            "status": "ok",
            "command": "system_command",
            "command_id": command_id,
            "action": action,
            "timestamp": time.time(),
        }

    def _handle_diagnostics(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle diagnostics request."""
        diagnostics = {
            "esp_id": self.esp_id,
            "state": self.system_state.name,
            "uptime": int(time.time() - self.boot_time),
            "heap_free": self.heap_free,
            "heap_total": 327680,
            "wifi_rssi": self.wifi_rssi,
            "wifi_connected": True,
            "mqtt_connected": self.connected,
            "sensor_count": len(self.sensors),
            "actuator_count": len(self.actuators),
            "library_count": len(self.libraries),
            "zone_configured": self.zone is not None,
            "safe_mode": self.system_state == SystemState.SAFE_MODE,
            "error_count": 0,
            "last_error": None,
            "firmware_version": self.config["system"]["firmware"],
        }

        self._publish_system_diagnostics(diagnostics)

        return {
            "status": "ok",
            "command": "diagnostics",
            "command_id": command_id,
            "data": diagnostics,
            "timestamp": time.time(),
        }

    def _handle_heartbeat(self, params: Dict[str, Any], command_id: str) -> Dict[str, Any]:
        """Handle explicit heartbeat request."""
        self._publish_heartbeat()
        return self._handle_ping(params, command_id)

    # =========================================================================
    # System Actions
    # =========================================================================
    def _system_reboot(self):
        """Simulate system reboot."""
        self.boot_time = time.time()
        self._transition_state(SystemState.BOOT)
        # Quick transition through states
        self._transition_state(SystemState.WIFI_CONNECTED)
        self._transition_state(SystemState.MQTT_CONNECTED)
        if self.zone:
            self._transition_state(SystemState.ZONE_CONFIGURED)
        if self.sensors:
            self._transition_state(SystemState.SENSORS_CONFIGURED)
        self._transition_state(SystemState.OPERATIONAL)

    def _system_factory_reset(self):
        """Simulate factory reset."""
        self.actuators.clear()
        self.sensors.clear()
        self.libraries.clear()
        self.zone = None
        self.config = {
            "wifi": {"ssid": "", "connected": False},
            "system": {"version": "1.0.0", "firmware": "el-trabajante-v1.0.0"},
        }
        self._transition_state(SystemState.WIFI_SETUP)

    def _system_update_firmware(self):
        """Simulate firmware update."""
        # Just update version string
        self.config["system"]["firmware"] = "el-trabajante-v1.1.0"

    # =========================================================================
    # MQTT Publishing Methods
    # =========================================================================
    def _publish_sensor_data(self, gpio: int, secondary_value_name: Optional[str] = None):
        """
        Publish sensor data to MQTT with full payload structure.

        Topics:
        - kaiser/god/esp/{esp_id}/sensor/{gpio}/data
        - kaiser/god/zone/{master_zone_id}/esp/{esp_id}/subzone/{subzone_id}/sensor/{gpio}/data (if zone configured)
        """
        if gpio not in self.sensors:
            return

        sensor = self.sensors[gpio]

        # Determine value to publish
        if secondary_value_name and sensor.secondary_values:
            value = sensor.secondary_values.get(secondary_value_name, sensor.raw_value)
            unit = self._get_secondary_unit(sensor.sensor_type, secondary_value_name)
        else:
            value = sensor.raw_value
            unit = sensor.unit

        # Build full payload matching Mqtt_Protocoll.md
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "gpio": gpio,
            "sensor_type": sensor.sensor_type,
            "raw": sensor.raw_value,
            "value": value if sensor.processed_value is None else sensor.processed_value,
            "unit": unit or self._get_default_unit(sensor.sensor_type),
            "quality": sensor.quality,
            "sensor_name": sensor.name or f"sensor_{gpio}",
            "raw_mode": sensor.raw_mode,
        }

        # Optional fields
        if sensor.subzone_id:
            payload["subzone_id"] = sensor.subzone_id
        if sensor.library_name:
            payload["library_name"] = sensor.library_name
            payload["library_version"] = sensor.library_version
        if sensor.calibration:
            payload["meta"] = {"calibration": sensor.calibration}

        # Primary topic (use TopicBuilder for consistency)
        topic = TopicBuilder.build_sensor_data_topic(self.esp_id, gpio, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

        # Zone-based topic (if configured)
        if self.zone and self.zone.subzone_id:
            zone_topic = TopicBuilder.build_subzone_sensor_data_topic(
                self.esp_id, gpio, self.zone.master_zone_id, self.zone.subzone_id, self.kaiser_id
            )
            self._store_and_publish(zone_topic, payload, qos=1, retain=False)

        # Note: on_publish is now called by _store_and_publish()

    def _publish_sensor_batch(self, readings: List[Dict[str, Any]]):
        """Publish batch sensor data."""
        payload = {"ts": int(time.time()), "esp_id": self.esp_id, "sensors": readings}

        topic = TopicBuilder.build_sensor_batch_topic(self.esp_id, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_actuator_status(self, gpio: int):
        """Publish actuator status with full payload."""
        if gpio not in self.actuators:
            return

        actuator = self.actuators[gpio]
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "gpio": gpio,
            "type": actuator.actuator_type,
            "name": actuator.name,
            "state": actuator.state,
            "pwm_value": actuator.pwm_value,
            "target_value": actuator.target_value,
            "emergency_stopped": actuator.emergency_stopped,
            "last_command": actuator.last_command,
            "timestamp": actuator.timestamp,
        }

        topic = TopicBuilder.build_actuator_status_topic(self.esp_id, gpio, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=True)

        # Note: on_publish is now called by _store_and_publish()

    def _publish_actuator_response(self, gpio: int, command_id: str, success: bool, message: str):
        """Publish actuator command response."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "gpio": gpio,
            "command_id": command_id,
            "success": success,
            "message": message,
        }

        topic = TopicBuilder.build_actuator_response_topic(self.esp_id, gpio, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_actuator_alert(self, gpio: int, alert_type: str, message: str):
        """Publish actuator alert."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "gpio": gpio,
            "alert_type": alert_type,
            "message": message,
            "severity": "warning" if alert_type != "emergency_stop" else "critical",
        }

        topic = TopicBuilder.build_actuator_alert_topic(self.esp_id, gpio, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_heartbeat(self):
        """Publish system heartbeat aligned with current ESP payload contract."""

        payload = {
            "esp_id": self.esp_id,
            "zone_id": self.zone.zone_id if self.zone else None,
            "master_zone_id": self.zone.master_zone_id if self.zone else None,
            "zone_assigned": self.zone is not None,
            "ts": int(time.time()),
            "uptime": int(time.time() - self.boot_time),
            "heap_free": self.heap_free,
            "wifi_rssi": self.wifi_rssi,
            "sensor_count": len(self.sensors),
            "actuator_count": len(self.actuators),
            "state": self.system_state.name,
            "mqtt_connected": self.connected,
            "safe_mode": self.system_state == SystemState.SAFE_MODE,
        }

        topic = TopicBuilder.build_heartbeat_topic(self.esp_id, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=0, retain=False)

    def _publish_system_response(self, command_id: str, action: str, success: bool):
        """Publish system command response."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "command_id": command_id,
            "action": action,
            "success": success,
        }

        topic = TopicBuilder.build_system_response_topic(self.esp_id, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_system_diagnostics(self, diagnostics: Dict[str, Any]):
        """Publish system diagnostics."""
        payload = {"ts": int(time.time()), "esp_id": self.esp_id, **diagnostics}

        topic = TopicBuilder.build_system_diagnostics_topic(self.esp_id, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_config_update(self, key: str, value: Any):
        """Publish config update (bidirectional)."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "key": key,
            "value": value,
            "action": "updated",
        }

        topic = TopicBuilder.build_config_topic(self.esp_id)
        self._store_and_publish(topic, payload, qos=1, retain=True)

    def _publish_library_event(self, event: str, library_name: str, version: str):
        """Publish library event (ready, installed, error)."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "library_name": library_name,
            "version": version,
        }

        topic = TopicBuilder.build_library_event_topic(self.esp_id, event, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=False)

    def _publish_safe_mode_status(self, reason: str):
        """Publish safe mode status."""
        payload = {
            "ts": int(time.time()),
            "esp_id": self.esp_id,
            "safe_mode": True,
            "reason": reason,
            "actuators_disabled": list(self.actuators.keys()),
        }

        topic = TopicBuilder.build_safe_mode_topic(self.esp_id, self.kaiser_id)
        self._store_and_publish(topic, payload, qos=1, retain=True)

    # =========================================================================
    # Helper Methods
    # =========================================================================
    def _build_gpio_status(self) -> List[Dict[str, Any]]:
        """
        Build GPIO status array from registered sensors/actuators.

        Simulates ESP32's GPIOManager.getReservedPinsList() behavior.
        Returns list of reserved GPIO pins with owner, component, mode, and safe status.

        Mode values (from ESP32 gpio_manager.cpp):
        - 0 = INPUT (sensors)
        - 1 = OUTPUT (actuators, system pins)
        - 2 = INPUT_PULLUP

        Returns:
            List of GPIO status dicts matching GpioStatusItem schema
        """
        gpio_status = []

        # Sensoren hinzufügen (owner="sensor", mode=0 INPUT)
        for gpio, sensor in self.sensors.items():
            gpio_status.append(
                {
                    "gpio": gpio,
                    "owner": "sensor",
                    "component": sensor.sensor_type,
                    "mode": 0,  # INPUT mode for sensors
                    "safe": False,  # Active sensors are not in safe mode
                }
            )

        # Aktoren hinzufügen (owner="actuator", mode=1 OUTPUT)
        for gpio, actuator in self.actuators.items():
            gpio_status.append(
                {
                    "gpio": gpio,
                    "owner": "actuator",
                    "component": actuator.actuator_type,
                    "mode": 1,  # OUTPUT mode for actuators
                    "safe": actuator.emergency_stopped,  # Emergency-stopped = safe mode
                }
            )

        # System-Pins (I2C) - NUR wenn I2C-Sensoren vorhanden sind
        i2c_sensor_types = {"SHT31", "BME280", "BH1750", "ADS1115", "CCS811", "TSL2561"}
        has_i2c = any(s.sensor_type in i2c_sensor_types for s in self.sensors.values())

        if has_i2c:
            gpio_status.extend(
                [
                    {
                        "gpio": 21,
                        "owner": "system",
                        "component": "I2C_SDA",
                        "mode": 1,
                        "safe": False,
                    },
                    {
                        "gpio": 22,
                        "owner": "system",
                        "component": "I2C_SCL",
                        "mode": 1,
                        "safe": False,
                    },
                ]
            )

        return gpio_status

    def _build_sensor_response_data(self, sensor: SensorState) -> Dict[str, Any]:
        """Build sensor response data structure."""
        data = {
            "gpio": sensor.gpio,
            "type": sensor.sensor_type,
            "name": sensor.name,
            "raw_value": sensor.raw_value,
            "value": (
                sensor.processed_value if sensor.processed_value is not None else sensor.raw_value
            ),
            "unit": sensor.unit or self._get_default_unit(sensor.sensor_type),
            "quality": sensor.quality,
            "timestamp": sensor.last_read,
            "raw_mode": sensor.raw_mode,
        }

        if sensor.library_name:
            data["library_name"] = sensor.library_name
            data["library_version"] = sensor.library_version

        if sensor.subzone_id:
            data["subzone_id"] = sensor.subzone_id

        if sensor.calibration:
            data["calibration"] = sensor.calibration

        # Multi-value sensors
        if sensor.is_multi_value and sensor.secondary_values:
            data["secondary_values"] = sensor.secondary_values

        return data

    def _get_default_unit(self, sensor_type: str) -> str:
        """Get default unit for sensor type."""
        units = {
            "DS18B20": "°C",
            "SHT31": "°C",
            "SHT31_temp": "°C",
            "SHT31_humidity": "%RH",
            "analog": "raw",
            "digital": "bool",
            "pH": "pH",
            "EC": "mS/cm",
            "moisture": "raw",
            "light": "lux",
            "pressure": "hPa",
        }
        return units.get(sensor_type, "raw")

    def _get_secondary_unit(self, sensor_type: str, value_name: str) -> str:
        """Get unit for secondary sensor value."""
        if value_name == "humidity":
            return "%RH"
        if value_name == "temperature":
            return "°C"
        return "raw"

    # =========================================================================
    # Test Helper Methods
    # =========================================================================
    def get_actuator_state(self, gpio: int) -> Optional[ActuatorState]:
        """Get current actuator state (for test assertions)."""
        return self.actuators.get(gpio)

    def get_sensor_state(self, gpio: int) -> Optional[SensorState]:
        """Get current sensor state (for test assertions)."""
        return self.sensors.get(gpio)

    def set_sensor_value(
        self,
        gpio: int,
        raw_value: float,
        sensor_type: str = "analog",
        name: str = "",
        unit: str = "",
        quality: str = "good",
        library_name: str = "",
        subzone_id: Optional[str] = None,
        calibration: Optional[Dict[str, float]] = None,
        processed_value: Optional[float] = None,
        is_multi_value: bool = False,
        secondary_values: Optional[Dict[str, float]] = None,
        raw_mode: bool = False,
    ):
        """Set sensor value for testing with full configuration."""
        if gpio not in self.sensors:
            self.sensors[gpio] = SensorState(
                gpio=gpio,
                sensor_type=sensor_type,
                raw_value=raw_value,
                name=name or f"sensor_{gpio}",
                unit=unit,
                quality=quality,
                library_name=library_name,
                subzone_id=subzone_id,
                calibration=calibration,
                processed_value=processed_value,
                is_multi_value=is_multi_value,
                secondary_values=secondary_values,
                raw_mode=raw_mode,
            )
        else:
            sensor = self.sensors[gpio]
            sensor.raw_value = raw_value
            sensor.sensor_type = sensor_type
            if name:
                sensor.name = name
            if unit:
                sensor.unit = unit
            sensor.quality = quality
            if library_name:
                sensor.library_name = library_name
            sensor.subzone_id = subzone_id
            if calibration:
                sensor.calibration = calibration
            sensor.processed_value = processed_value
            sensor.is_multi_value = is_multi_value
            if secondary_values:
                sensor.secondary_values = secondary_values
            sensor.raw_mode = raw_mode
            sensor.last_read = time.time()

    def set_multi_value_sensor(
        self,
        gpio: int,
        sensor_type: str,
        primary_value: float,
        secondary_values: Dict[str, float],
        name: str = "",
        quality: str = "good",
    ):
        """
        Set a multi-value sensor (e.g., SHT31 with temp + humidity).

        Usage:
            mock.set_multi_value_sensor(
                gpio=21,
                sensor_type="SHT31",
                primary_value=23.5,  # Temperature
                secondary_values={"humidity": 65.2}
            )
        """
        self.set_sensor_value(
            gpio=gpio,
            raw_value=primary_value,
            sensor_type=sensor_type,
            name=name or f"{sensor_type}_{gpio}",
            quality=quality,
            is_multi_value=True,
            secondary_values=secondary_values,
        )

    def configure_actuator(
        self,
        gpio: int,
        actuator_type: str = "relay",
        name: str = "",
        min_value: float = 0.0,
        max_value: float = 1.0,
        safety_timeout_ms: int = 0,
        inverted: bool = False,
    ):
        """Pre-configure an actuator."""
        self.actuators[gpio] = ActuatorState(
            gpio=gpio,
            actuator_type=actuator_type,
            state=False,
            pwm_value=0.0,
            name=name or f"{actuator_type}_{gpio}",
            min_value=min_value,
            max_value=max_value,
            safety_timeout_ms=safety_timeout_ms,
            inverted=inverted,
        )

    def get_last_response(self) -> Optional[Dict[str, Any]]:
        """Get last command response."""
        return self.last_response

    def get_published_messages(self) -> List[Dict[str, Any]]:
        """Get all published messages (for test verification)."""
        return self.published_messages.copy()

    def get_messages_by_topic_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """Get messages matching a topic pattern."""
        return [m for m in self.published_messages if pattern in m["topic"]]

    def clear_published_messages(self):
        """Clear published messages list."""
        self.published_messages.clear()

    def reset(self):
        """Reset mock to clean state."""
        self._handle_reset({}, "reset_0")
        self.last_response = None
        self.connected = True
        self.boot_time = time.time()
        self.system_state = SystemState.OPERATIONAL

    def disconnect(self):
        """Disconnect mock client."""
        self.connected = False
        self._transition_state(SystemState.MQTT_CONNECTING)

    def reconnect(self):
        """Reconnect mock client."""
        self.connected = True
        self._transition_state(SystemState.MQTT_CONNECTED)
        if self.zone:
            self._transition_state(SystemState.ZONE_CONFIGURED)
        if self.sensors:
            self._transition_state(SystemState.SENSORS_CONFIGURED)
        self._transition_state(SystemState.OPERATIONAL)

    def simulate_wifi_rssi_change(self, rssi: int):
        """Simulate WiFi signal strength change."""
        self.wifi_rssi = rssi

    def simulate_heap_change(self, heap_free: int):
        """Simulate heap memory change."""
        self.heap_free = heap_free

    def get_system_state(self) -> SystemState:
        """Get current system state."""
        return self.system_state

    def subscribe_topic(self, topic: str):
        """Subscribe to MQTT topic (for tracking)."""
        if topic not in self.subscribed_topics:
            self.subscribed_topics.append(topic)

    def get_subscribed_topics(self) -> List[str]:
        """Get list of subscribed topics."""
        return self.subscribed_topics.copy()

    # =========================================================================
    # Hardware Simulation Methods (Phase 3: Logic Engine Integration Tests)
    # =========================================================================

    def add_ph_sensor(
        self,
        gpio: int,
        initial_ph: float = 7.0,
        calibrated: bool = False,
        drift_rate: float = 0.0,  # pH/hour
    ) -> None:
        """
        Add pH sensor with calibration state and drift simulation.

        Hardware Context:
        - pH Electrode (Haoshi H-101) + Interface Board (PH-4502C)
        - ADC1 pins required (GPIO32-39) due to WiFi coexistence
        - Value range: 0-14 pH, accuracy ±0.05
        - Drift: typical ≤0.02 pH/24h when calibrated

        Args:
            gpio: ADC1 pin (32-39 recommended for WiFi compatibility)
            initial_ph: Starting pH value (default 7.0 = neutral)
            calibrated: Whether sensor has been calibrated
            drift_rate: Simulated drift per hour (0.0 = no drift)

        Usage:
            mock.add_ph_sensor(gpio=34, initial_ph=6.5, calibrated=True)
            # Later: simulate drift
            mock.simulate_ph_drift(gpio=34, hours=24)
        """
        # Validate ADC1 pin (required for WiFi coexistence)
        adc1_pins = [32, 33, 34, 35, 36, 39]
        if gpio not in adc1_pins:
            logger.warning(
                f"GPIO {gpio} is not an ADC1 pin. pH sensors should use GPIO 32-39 for WiFi compatibility."
            )

        self.sensors[gpio] = SensorState(
            gpio=gpio,
            sensor_type="pH",
            raw_value=initial_ph,
            name=f"pH_Sensor_{gpio}",
            unit="pH",
            quality="good" if calibrated else "fair",
            calibration={
                "calibrated": calibrated,
                "drift_rate": drift_rate,
                "drift_start": time.time(),
                "initial_ph": initial_ph,
                # Two-point calibration data (pH 4.0 and pH 7.0)
                "cal_point_4": 3.0 if calibrated else None,  # Voltage at pH 4.0
                "cal_point_7": 2.5 if calibrated else None,  # Voltage at pH 7.0
            },
            raw_mode=True,  # Server processes pH conversion
        )

    def get_ph_with_drift(self, gpio: int) -> float:
        """
        Get current pH value including simulated drift.

        Args:
            gpio: pH sensor GPIO pin

        Returns:
            Current pH value with drift applied
        """
        sensor = self.sensors.get(gpio)
        if not sensor or sensor.sensor_type != "pH":
            return -1.0  # Error value

        calibration = sensor.calibration or {}
        drift_rate = calibration.get("drift_rate", 0.0)
        drift_start = calibration.get("drift_start", time.time())
        initial_ph = calibration.get("initial_ph", sensor.raw_value)

        if drift_rate == 0.0:
            return sensor.raw_value

        # Calculate drift
        hours_elapsed = (time.time() - drift_start) / 3600.0
        drift = drift_rate * hours_elapsed
        current_ph = initial_ph + drift

        # Clamp to valid pH range (values outside indicate fault)
        return current_ph

    def add_ds18b20_multi(
        self,
        gpio: int,
        count: int = 3,
        initial_temps: Optional[List[float]] = None,
        rom_addresses: Optional[List[str]] = None,
    ) -> None:
        """
        Add multiple DS18B20 sensors on same OneWire bus.

        Hardware Context:
        - OneWire protocol: multiple sensors share one GPIO
        - Each sensor has unique 64-bit ROM address
        - Special values: -127°C (fault/CRC error), +85°C (power-on reset)
        - Conversion time: 750ms for 12-bit resolution
        - 4.7kΩ pull-up resistor required

        Args:
            gpio: OneWire data pin (GPIO4, 16, 17 recommended)
            count: Number of sensors on bus
            initial_temps: Starting temperatures (default: [22.0, 22.5, 23.0, ...])
            rom_addresses: Unique ROM addresses (default: auto-generated)

        Usage:
            mock.add_ds18b20_multi(
                gpio=4,
                count=3,
                initial_temps=[22.5, 23.0, 22.8],
                rom_addresses=["28-000000000001", "28-000000000002", "28-000000000003"]
            )
        """
        # Initialize DS18B20 bus storage if not exists
        if not hasattr(self, "_ds18b20_buses"):
            self._ds18b20_buses: Dict[int, Dict[str, SensorState]] = {}

        # Generate default temperatures if not provided
        if initial_temps is None:
            initial_temps = [22.0 + i * 0.5 for i in range(count)]

        # Generate default ROM addresses if not provided
        if rom_addresses is None:
            rom_addresses = [f"28-{i:012X}" for i in range(1, count + 1)]

        # Validate count matches
        if len(initial_temps) != count:
            initial_temps = (initial_temps + [22.0] * count)[:count]
        if len(rom_addresses) != count:
            rom_addresses = [f"28-{i:012X}" for i in range(1, count + 1)]

        # Create bus entry
        self._ds18b20_buses[gpio] = {}

        # Create sensor entry for each DS18B20
        for i, (temp, rom) in enumerate(zip(initial_temps, rom_addresses)):
            sensor_state = SensorState(
                gpio=gpio,
                sensor_type="DS18B20",
                raw_value=temp,
                name=f"DS18B20_{gpio}_{rom[-4:]}",
                unit="°C",
                quality="good",
                calibration={
                    "rom_address": rom,
                    "bus_index": i,
                    "resolution": 12,  # 12-bit = 0.0625°C resolution
                    "conversion_time_ms": 750,
                },
                raw_mode=False,  # DS18B20 provides calibrated temperature
            )
            self._ds18b20_buses[gpio][rom] = sensor_state

        # Also add primary sensor to self.sensors (for backward compatibility)
        # Uses first sensor on bus
        if rom_addresses:
            first_rom = rom_addresses[0]
            self.sensors[gpio] = self._ds18b20_buses[gpio][first_rom]

    def get_ds18b20_by_rom(self, gpio: int, rom_address: str) -> Optional[SensorState]:
        """
        Get specific DS18B20 sensor by ROM address.

        Args:
            gpio: OneWire bus GPIO pin
            rom_address: 64-bit ROM address (e.g., "28-000000000001")

        Returns:
            SensorState for specific sensor, or None if not found
        """
        if not hasattr(self, "_ds18b20_buses"):
            return None
        bus = self._ds18b20_buses.get(gpio, {})
        return bus.get(rom_address)

    def set_ds18b20_value(
        self, gpio: int, rom_address: str, temperature: float, quality: str = "good"
    ) -> bool:
        """
        Set temperature value for specific DS18B20 sensor.

        Args:
            gpio: OneWire bus GPIO pin
            rom_address: 64-bit ROM address
            temperature: New temperature value
            quality: Sensor quality level

        Returns:
            True if sensor was updated, False if not found
        """
        sensor = self.get_ds18b20_by_rom(gpio, rom_address)
        if sensor is None:
            return False

        sensor.raw_value = temperature
        sensor.quality = quality
        sensor.last_read = time.time()
        return True

    def get_ds18b20_average(self, gpio: int) -> Optional[float]:
        """
        Get average temperature from all DS18B20 sensors on bus.

        Args:
            gpio: OneWire bus GPIO pin

        Returns:
            Average temperature, or None if no sensors
        """
        if not hasattr(self, "_ds18b20_buses"):
            return None

        bus = self._ds18b20_buses.get(gpio, {})
        if not bus:
            return None

        # Filter out fault values (-127°C)
        valid_temps = [
            s.raw_value for s in bus.values() if s.raw_value > -100 and s.quality != "bad"
        ]

        if not valid_temps:
            return None

        return sum(valid_temps) / len(valid_temps)

    def set_relay_state(self, gpio: int, state: bool, trigger_type: str = "active_low") -> None:
        """
        Set relay state accounting for trigger type.

        Hardware Context:
        - Active-LOW relays (common): LOW=ON, HIGH=OFF
        - Active-HIGH relays: HIGH=ON, LOW=OFF
        - Safe GPIO pins: 16, 17 (no boot glitches)
        - Strapping pins to avoid: 0, 2, 12, 15

        Args:
            gpio: Relay control pin
            state: Desired relay state (True=ON, False=OFF)
            trigger_type: "active_low" or "active_high"

        Usage:
            # Active-LOW relay (common type)
            mock.set_relay_state(gpio=16, state=True, trigger_type="active_low")
            # This sets GPIO LOW to turn relay ON
        """
        # Calculate actual GPIO level based on trigger type
        if trigger_type == "active_low":
            gpio_level = not state  # LOW = ON, HIGH = OFF
        else:  # active_high
            gpio_level = state  # HIGH = ON, LOW = OFF

        # Warn about strapping pins
        strapping_pins = [0, 2, 12, 15]
        if gpio in strapping_pins:
            logger.warning(
                f"GPIO {gpio} is a strapping pin. Relays may 'rattle' during boot. "
                f"Recommended: GPIO 16 or 17."
            )

        # Update or create actuator state
        if gpio in self.actuators:
            actuator = self.actuators[gpio]
            actuator.state = state
            actuator.target_value = 1.0 if state else 0.0
            actuator.timestamp = time.time()
            # Always update trigger type and GPIO level
            actuator._trigger_type = trigger_type
            actuator._gpio_level = gpio_level
        else:
            self.actuators[gpio] = ActuatorState(
                gpio=gpio,
                actuator_type="relay",
                state=state,
                pwm_value=0.0,
                target_value=1.0 if state else 0.0,
                name=f"Relay_{gpio}",
            )
            self.actuators[gpio]._trigger_type = trigger_type
            self.actuators[gpio]._gpio_level = gpio_level

    def get_relay_gpio_level(self, gpio: int) -> Optional[bool]:
        """
        Get actual GPIO level for relay (accounts for trigger type).

        Args:
            gpio: Relay GPIO pin

        Returns:
            Actual GPIO level (True=HIGH, False=LOW), or None if not found
        """
        actuator = self.actuators.get(gpio)
        if actuator is None:
            return None
        return getattr(actuator, "_gpio_level", actuator.state)

    def set_pwm_duty(self, gpio: int, duty_cycle: int, frequency: int = 25000) -> None:
        """
        Set PWM duty cycle for actuator.

        Hardware Context:
        - ESP32 LEDC: 16 independent channels
        - Fans: 1-25kHz, 8-bit resolution (0-255)
        - Servos: 50Hz, 1-2ms pulse width
        - Recommended pins: GPIO25, 26, 27 (have DAC capability)

        Args:
            gpio: PWM output pin
            duty_cycle: 0-255 (8-bit)
            frequency: PWM frequency in Hz (default 25kHz for fans)

        Usage:
            # Fan at 50% speed
            mock.set_pwm_duty(gpio=25, duty_cycle=128, frequency=25000)

            # Servo at 90° (center position)
            mock.set_pwm_duty(gpio=26, duty_cycle=191, frequency=50)  # ~1.5ms pulse
        """
        # Clamp duty cycle to valid range
        duty_cycle = max(0, min(255, duty_cycle))

        # Convert to 0.0-1.0 range for internal storage
        pwm_value = duty_cycle / 255.0

        if gpio in self.actuators:
            actuator = self.actuators[gpio]
            actuator.pwm_value = pwm_value
            actuator.target_value = pwm_value
            actuator.state = duty_cycle > 0
            actuator.timestamp = time.time()
            # Store frequency
            if not hasattr(actuator, "_pwm_frequency"):
                actuator._pwm_frequency = frequency
            else:
                actuator._pwm_frequency = frequency
        else:
            # Determine actuator type based on frequency
            if frequency <= 100:
                actuator_type = "servo"
            else:
                actuator_type = "pwm_motor"

            self.actuators[gpio] = ActuatorState(
                gpio=gpio,
                actuator_type=actuator_type,
                state=duty_cycle > 0,
                pwm_value=pwm_value,
                target_value=pwm_value,
                name=f"PWM_{gpio}",
            )
            self.actuators[gpio]._pwm_frequency = frequency

    def get_pwm_duty(self, gpio: int) -> Optional[int]:
        """
        Get current PWM duty cycle (0-255).

        Args:
            gpio: PWM GPIO pin

        Returns:
            Duty cycle as 0-255, or None if not configured
        """
        actuator = self.actuators.get(gpio)
        if actuator is None:
            return None
        return int(actuator.pwm_value * 255)

    def get_pwm_frequency(self, gpio: int) -> Optional[int]:
        """
        Get PWM frequency for actuator.

        Args:
            gpio: PWM GPIO pin

        Returns:
            Frequency in Hz, or None if not configured
        """
        actuator = self.actuators.get(gpio)
        if actuator is None:
            return None
        return getattr(actuator, "_pwm_frequency", 25000)

    def simulate_boot_sequence(self) -> Dict[str, Any]:
        """
        Simulate ESP32 boot sequence with strapping pin behavior.

        Hardware Context:
        - Strapping pins (GPIO 0, 2, 12, 15) may toggle during boot
        - Safe pins (GPIO 16, 17) remain stable
        - Boot sequence: BOOT → WIFI_SETUP → WIFI_CONNECTED → MQTT_CONNECTING → MQTT_CONNECTED

        Returns:
            Boot sequence result with pin behavior

        Usage:
            result = mock.simulate_boot_sequence()
            assert result["safe_pins_unchanged"] == [16, 17]
        """
        strapping_pins = [0, 2, 12, 15]
        safe_pins = [16, 17]

        # Track pre-boot state of actuators on safe pins
        safe_pin_states_before = {}
        for gpio in safe_pins:
            if gpio in self.actuators:
                safe_pin_states_before[gpio] = self.actuators[gpio].state

        # Record strapping pins that have relays
        strapping_with_relays = [gpio for gpio in strapping_pins if gpio in self.actuators]

        # Simulate boot state transitions
        boot_states = [
            SystemState.BOOT,
            SystemState.WIFI_SETUP,
            SystemState.WIFI_CONNECTED,
            SystemState.MQTT_CONNECTING,
            SystemState.MQTT_CONNECTED,
        ]

        # Add zone states if zone configured
        if self.zone:
            boot_states.append(SystemState.ZONE_CONFIGURED)
        if self.sensors:
            boot_states.append(SystemState.SENSORS_CONFIGURED)
        boot_states.append(SystemState.OPERATIONAL)

        # Transition through states
        for state in boot_states:
            self._transition_state(state)

        # Verify safe pins unchanged
        safe_pins_verified = []
        for gpio in safe_pins:
            if gpio in safe_pin_states_before:
                current_state = self.actuators[gpio].state
                if current_state == safe_pin_states_before[gpio]:
                    safe_pins_verified.append(gpio)

        return {
            "strapping_pins_toggled": strapping_with_relays,
            "safe_pins_unchanged": safe_pins_verified if safe_pin_states_before else safe_pins,
            "final_state": self.system_state,
            "boot_states": [s.name for s in boot_states],
            "boot_time_ms": int((time.time() - self.boot_time) * 1000),
        }

    def simulate_sensor_fault(self, gpio: int, fault_type: str) -> None:
        """
        Simulate sensor fault conditions.

        Hardware Context:
        - DS18B20: -127°C (disconnect/CRC), +85°C (power-on reset)
        - pH: ADC=0 or ADC=4095 (open/short circuit)
        - SHT31: I2C NACK, invalid checksum
        - Analog: ADC=0 or ADC=4095 (wire fault)

        Args:
            gpio: Sensor GPIO pin
            fault_type:
                - "disconnect": Sensor disconnected/wire break
                - "power_on_reset": DS18B20 factory reset value (+85°C)
                - "crc_error": CRC checksum failure
                - "i2c_nack": I2C device not responding
                - "short_circuit": Shorted sensor wires
                - "open_circuit": Open circuit (no sensor)

        Usage:
            mock.simulate_sensor_fault(gpio=4, fault_type="disconnect")
            # DS18B20 now reports -127°C
        """
        sensor = self.sensors.get(gpio)
        if sensor is None:
            logger.warning(f"No sensor on GPIO {gpio} to simulate fault")
            return

        sensor_type = sensor.sensor_type

        # Apply fault based on sensor type
        if sensor_type == "DS18B20":
            if fault_type == "disconnect":
                sensor.raw_value = -127.0  # DS18B20 fault indicator
                sensor.quality = "bad"
            elif fault_type == "power_on_reset":
                sensor.raw_value = 85.0  # DS18B20 power-on default
                sensor.quality = "stale"
            elif fault_type == "crc_error":
                sensor.raw_value = -127.0
                sensor.quality = "bad"
            else:
                sensor.quality = "bad"

        elif sensor_type == "pH":
            if fault_type in ["disconnect", "open_circuit"]:
                sensor.raw_value = -1.0  # Outside valid 0-14 range
                sensor.quality = "bad"
            elif fault_type == "short_circuit":
                sensor.raw_value = 15.0  # Outside valid 0-14 range
                sensor.quality = "bad"
            else:
                sensor.quality = "bad"

        elif sensor_type == "SHT31":
            if fault_type == "i2c_nack":
                sensor.raw_value = 0.0
                sensor.quality = "bad"
                if sensor.secondary_values:
                    sensor.secondary_values = {"humidity": 0.0}
            elif fault_type == "disconnect":
                sensor.raw_value = 0.0
                sensor.quality = "bad"
            else:
                sensor.quality = "bad"

        elif sensor_type in ["analog", "ADC"]:
            if fault_type == "open_circuit":
                sensor.raw_value = 4095.0  # Max ADC value (floating input)
                sensor.quality = "bad"
            elif fault_type == "short_circuit":
                sensor.raw_value = 0.0  # Min ADC value (shorted to ground)
                sensor.quality = "bad"
            else:
                sensor.quality = "bad"

        else:
            # Generic fault
            sensor.quality = "bad"

        sensor.last_read = time.time()

        # Also update DS18B20 bus if applicable
        if hasattr(self, "_ds18b20_buses") and gpio in self._ds18b20_buses:
            for rom, bus_sensor in self._ds18b20_buses[gpio].items():
                bus_sensor.raw_value = sensor.raw_value
                bus_sensor.quality = sensor.quality
                bus_sensor.last_read = time.time()

    def clear_sensor_fault(self, gpio: int) -> None:
        """
        Clear sensor fault and restore normal operation.

        Args:
            gpio: Sensor GPIO pin
        """
        sensor = self.sensors.get(gpio)
        if sensor is None:
            return

        # Restore to default good values based on sensor type
        if sensor.sensor_type == "DS18B20":
            sensor.raw_value = 22.0  # Room temperature
        elif sensor.sensor_type == "pH":
            sensor.raw_value = 7.0  # Neutral pH
        elif sensor.sensor_type == "SHT31":
            sensor.raw_value = 22.0  # Room temperature
            if sensor.secondary_values:
                sensor.secondary_values = {"humidity": 50.0}
        elif sensor.sensor_type in ["analog", "ADC"]:
            sensor.raw_value = 2048.0  # Mid-range ADC

        sensor.quality = "good"
        sensor.last_read = time.time()
