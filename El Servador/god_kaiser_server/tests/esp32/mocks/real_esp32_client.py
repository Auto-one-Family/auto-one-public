"""
Real ESP32 Client - MQTT connection to actual ESP32 hardware.

Provides identical API to MockESP32Client but communicates with real devices via MQTT.

IMPORTANT: Uses the REAL MQTT topic structure (identical to MockESP32Client).

Rationale:
- Enables integration tests against actual hardware
- Pre-production validation with real ESP32 devices
- Staging environment testing before deployment
- Seamless transition from Mock → Real hardware testing

Used for:
- Integration tests against actual hardware
- Pre-production validation
- Staging environment testing
"""

import paho.mqtt.client as mqtt
import json
import time
import threading
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PendingCommand:
    """Track a pending command waiting for response."""

    command: str
    params: Dict[str, Any]
    timestamp: float
    event: threading.Event
    response: Optional[Dict[str, Any]] = None


class RealESP32Client:
    """
    Real ESP32 Client - MQTT connection to actual ESP32 hardware.

    Provides identical API to MockESP32Client for seamless test transitions.

    Usage:
        client = RealESP32Client(
            esp_id="esp32-001",
            broker_host="localhost",
            broker_port=1883
        )
        response = client.handle_command("ping", {})
        client.disconnect()
    """

    def __init__(
        self,
        esp_id: str,
        broker_host: str,
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 5,
        kaiser_id: str = "god",
    ):
        """
        Initialize connection to real ESP32 via MQTT.

        Args:
            esp_id: ESP32 device ID to test
            broker_host: MQTT broker address
            broker_port: MQTT broker port (default: 1883)
            username: Optional MQTT username
            password: Optional MQTT password
            timeout: Command response timeout in seconds (default: 5)
            kaiser_id: Kaiser ID for topic construction (default: "god")
        """
        self.esp_id = esp_id
        self.kaiser_id = kaiser_id
        self.timeout = timeout
        self.connected = False

        # Response tracking
        self.pending_commands: Dict[str, PendingCommand] = {}
        self.response_lock = threading.Lock()

        # Published messages tracking (for test verification)
        self.published_messages = []
        self.messages_lock = threading.Lock()

        # MQTT client setup
        client_id = f"test-client-{esp_id}-{int(time.time())}"
        self.mqtt_client = mqtt.Client(client_id=client_id)

        if username and password:
            self.mqtt_client.username_pw_set(username, password)

        # Set callbacks
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message

        # Connect to broker
        try:
            self.mqtt_client.connect(broker_host, broker_port, keepalive=60)
            self.mqtt_client.loop_start()

            # Wait for connection (up to 5 seconds)
            for _ in range(50):
                if self.connected:
                    break
                time.sleep(0.1)

            if not self.connected:
                raise ConnectionError(
                    f"Failed to connect to MQTT broker at {broker_host}:{broker_port}"
                )

            logger.info(
                f"RealESP32Client connected to {broker_host}:{broker_port} for ESP {esp_id}"
            )

        except Exception as e:
            raise ConnectionError(f"MQTT connection failed: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker for ESP {self.esp_id}")

            # Subscribe to all relevant topics for this ESP
            self._subscribe_to_topics()
        else:
            logger.error(f"Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker."""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnect from MQTT broker (rc={rc})")

    def _subscribe_to_topics(self):
        """Subscribe to all topics for monitoring this ESP."""
        # Actuator status messages
        self.mqtt_client.subscribe(f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/actuator/+/status")

        # Sensor data messages
        self.mqtt_client.subscribe(f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/sensor/+/data")

        # System responses
        self.mqtt_client.subscribe(f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/system/response")

        # Config responses
        self.mqtt_client.subscribe(f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/config/response")

        logger.debug(f"Subscribed to topics for ESP {self.esp_id}")

    def _on_message(self, client, userdata, msg):
        """Callback when message received from MQTT broker."""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            payload = {"raw": msg.payload.decode()}

        logger.debug(f"Received message on {topic}: {payload}")

        # Store message for verification
        with self.messages_lock:
            self.published_messages.append(
                {"topic": topic, "payload": payload, "timestamp": time.time()}
            )

        # Match to pending commands
        # (This is simplified - real implementation would need more sophisticated matching)
        with self.response_lock:
            for cmd_id, pending in list(self.pending_commands.items()):
                # Check if this message is a response to the pending command
                if self._is_response_for_command(topic, payload, pending):
                    pending.response = payload
                    pending.event.set()
                    del self.pending_commands[cmd_id]
                    break

    def _is_response_for_command(
        self, topic: str, payload: Dict[str, Any], pending: PendingCommand
    ) -> bool:
        """Check if a message is the response for a pending command."""
        # Simplified matching logic
        if pending.command == "actuator_set":
            gpio = pending.params.get("gpio")
            return f"actuator/{gpio}/status" in topic
        elif pending.command == "sensor_read":
            gpio = pending.params.get("gpio")
            return f"sensor/{gpio}/data" in topic
        elif pending.command == "config_get":
            return "config/response" in topic or "config" in topic
        elif pending.command == "ping":
            return "system/response" in topic or "health" in topic

        return False

    def handle_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send command to real ESP32 and wait for response.

        Uses real MQTT topics - identical to production.

        Args:
            command: Command type (ping, actuator_set, sensor_read, etc.)
            params: Command parameters

        Returns:
            Response dict with status and data
        """
        if not self.connected:
            return {
                "status": "error",
                "error": "Not connected to MQTT broker",
                "timestamp": time.time(),
            }

        # Generate command ID
        cmd_id = f"{command}_{time.time()}"

        # Create pending command tracker
        pending = PendingCommand(
            command=command, params=params, timestamp=time.time(), event=threading.Event()
        )

        with self.response_lock:
            self.pending_commands[cmd_id] = pending

        # Build and publish command
        topic = self._build_command_topic(command, params)
        payload = self._build_command_payload(command, params)

        try:
            result = self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
            result.wait_for_publish(timeout=2)

            if not result.is_published():
                return {
                    "status": "error",
                    "error": "Failed to publish command",
                    "timestamp": time.time(),
                }

        except Exception as e:
            return {"status": "error", "error": f"Publish failed: {e}", "timestamp": time.time()}

        # Wait for response
        if pending.event.wait(timeout=self.timeout):
            return pending.response or {
                "status": "ok",
                "command": command,
                "timestamp": time.time(),
            }
        else:
            # Timeout
            with self.response_lock:
                self.pending_commands.pop(cmd_id, None)

            return {
                "status": "error",
                "error": f"Timeout waiting for response ({self.timeout}s)",
                "command": command,
                "timestamp": time.time(),
            }

    def _build_command_topic(self, command: str, params: Dict[str, Any]) -> str:
        """Build MQTT topic for command (production topic structure)."""
        if command == "actuator_set":
            gpio = params.get("gpio")
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/actuator/{gpio}/command"
        elif command == "sensor_read":
            # Sensor reads are typically triggered by sensor manager, not direct commands
            # For testing, we might use a config or system command
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/system/command"
        elif command in ["config_get", "config_set"]:
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/config"
        elif command == "emergency_stop":
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/actuator/emergency"
        elif command == "ping":
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/system/command"
        else:
            return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/system/command"

    def _build_command_payload(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build MQTT payload for command."""
        payload = {"command": command, "timestamp": time.time()}
        payload.update(params)
        return payload

    # Test helper methods (for API compatibility with MockESP32Client)

    def get_actuator_state(self, gpio: int) -> Optional[Any]:
        """
        Get current actuator state (requires querying via MQTT).

        Note: This is a simplified implementation for testing.
        """
        response = self.handle_command("actuator_get", {"gpio": gpio})
        if response.get("status") == "ok":
            return response.get("data")
        return None

    def get_sensor_state(self, gpio: int) -> Optional[Any]:
        """
        Get current sensor state (requires querying via MQTT).

        Note: This is a simplified implementation for testing.
        """
        response = self.handle_command("sensor_get", {"gpio": gpio})
        if response.get("status") == "ok":
            return response.get("data")
        return None

    def set_sensor_value(self, gpio: int, raw_value: float, sensor_type: str = "analog"):
        """
        Set sensor value for testing.

        Note: Not applicable for real hardware - sensors have actual values.
        This method exists for API compatibility but does nothing.
        """
        logger.warning(
            "set_sensor_value() called on RealESP32Client - ignored (real hardware has actual sensor values)"
        )

    def get_published_messages(self) -> list:
        """Get all published messages (for test verification)."""
        with self.messages_lock:
            return self.published_messages.copy()

    def clear_published_messages(self):
        """Clear published messages list."""
        with self.messages_lock:
            self.published_messages.clear()

    def reset(self):
        """Reset client state (clear messages, etc.)."""
        self.clear_published_messages()
        with self.response_lock:
            self.pending_commands.clear()

    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.connected = False
            logger.info(f"Disconnected from MQTT broker for ESP {self.esp_id}")
