"""
Mock Actuator Handler for Mock-ESP Simulation.

Handles incoming actuator commands for Mock-ESPs:
- Receives commands via MQTT (Server → Mock-ESP)
- Updates internal actuator state (ON/OFF/PWM)
- Publishes response and status messages (Mock-ESP → Server)
- Handles emergency stop events

This enables Mock-ESPs to fully integrate with the Logic Engine.

Topic Patterns:
- Command: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command
- Response: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response
- Status: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status
- Emergency: kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency
- Broadcast Emergency: kaiser/broadcast/emergency
"""

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from ...core.logging_config import get_logger
from ...core.scheduler import get_central_scheduler, JobCategory
from ...mqtt.topics import TopicBuilder

if TYPE_CHECKING:
    from .scheduler import SimulationScheduler, MockESPRuntime

logger = get_logger(__name__)


# Command types supported by actuators
VALID_COMMANDS = {"ON", "OFF", "PWM", "TOGGLE"}


class MockActuatorHandler:
    """
    Handles actuator commands for Mock-ESPs.

    This class processes incoming MQTT actuator commands and simulates
    the behavior of a real ESP32 by:
    1. Receiving commands (ON/OFF/PWM/TOGGLE)
    2. Updating internal state
    3. Publishing response messages
    4. Publishing status updates

    Thread-Safety:
        MQTT callbacks come from the Paho-MQTT thread. All state changes
        use asyncio.Lock for thread-safe async operations.
    """

    def __init__(self, scheduler: "SimulationScheduler", mqtt_publish: Optional[Callable] = None):
        """
        Initialize MockActuatorHandler.

        Args:
            scheduler: SimulationScheduler instance for accessing runtime state
            mqtt_publish: Callback for MQTT publishing
                         Signature: def publish(topic: str, payload: dict, qos: int = 1)
        """
        self._scheduler = scheduler
        self._mqtt_publish = mqtt_publish
        self._lock = asyncio.Lock()

    def set_mqtt_callback(self, callback: Callable) -> None:
        """Set the MQTT publish callback."""
        self._mqtt_publish = callback

    # ================================================================
    # COMMAND HANDLING
    # ================================================================

    async def handle_command(self, topic: str, payload_str: str) -> bool:
        """
        Handle incoming actuator command from MQTT.

        Expected topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command

        Expected payload:
        {
            "command": "ON",
            "value": 1.0,
            "duration": 0,
            "timestamp": 1735818000,
            "command_id": "cmd_abc123"
        }

        Args:
            topic: MQTT topic string
            payload_str: JSON payload string

        Returns:
            True if command processed successfully
        """
        try:
            # Step 1: Parse topic
            parsed = self._parse_command_topic(topic)
            if not parsed:
                logger.error(f"[MockActuator] Failed to parse topic: {topic}")
                return False

            esp_id, gpio = parsed

            # Step 2: Check if mock is active
            runtime = self._scheduler.get_runtime(esp_id)
            if not runtime:
                logger.debug(f"[MockActuator] Command for non-active mock: {esp_id}")
                return False

            # Step 3: Parse and validate payload
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                logger.error(f"[MockActuator] Invalid JSON payload: {e}")
                await self._publish_response(
                    esp_id, gpio, "UNKNOWN", 0.0, 0, False, f"Invalid JSON payload: {e}"
                )
                return False

            validation_result = self._validate_command_payload(payload)
            if not validation_result["valid"]:
                logger.error(
                    f"[MockActuator] Invalid payload for {esp_id} GPIO {gpio}: "
                    f"{validation_result['error']}"
                )
                await self._publish_response(
                    esp_id,
                    gpio,
                    payload.get("command", "UNKNOWN"),
                    0.0,
                    0,
                    False,
                    validation_result["error"],
                )
                return False

            # Step 4: Extract command data
            command = validation_result["command"]
            value = validation_result["value"]
            duration = validation_result["duration"]

            logger.info(
                f"[MockActuator] Command received: {esp_id} GPIO {gpio} "
                f"command={command} value={value} duration={duration}"
            )

            # Step 5: Execute command
            async with self._lock:
                success, message = await self._execute_command(
                    esp_id, gpio, command, value, duration
                )

            # Step 6: Publish response
            await self._publish_response(esp_id, gpio, command, value, duration, success, message)

            # Step 7: Publish status (only if command succeeded)
            if success:
                await self._publish_status(esp_id, gpio)

            return success

        except Exception as e:
            logger.error(f"[MockActuator] Error handling command: {e}", exc_info=True)
            return False

    async def handle_emergency(self, topic: str, payload_str: str, esp_id: str) -> bool:
        """
        Handle ESP-specific emergency topic (emergency_stop or clear_emergency).

        Payload must contain "command": "emergency_stop" | "clear_emergency".
        - clear_emergency: Clears emergency flag, actuators become controllable again.
        - emergency_stop or missing/other: Sets emergency_stopped and turns off all actuators.

        Args:
            topic: MQTT topic string
            payload_str: JSON payload string
            esp_id: ESP device ID

        Returns:
            True if processed successfully
        """
        try:
            runtime = self._scheduler.get_runtime(esp_id)
            if not runtime:
                logger.warning(f"[MockActuator] Emergency for unknown mock: {esp_id}")
                return False

            # Parse payload to distinguish clear_emergency from emergency_stop
            command = "emergency_stop"
            try:
                if payload_str and payload_str.strip():
                    payload = json.loads(payload_str)
                    command = (payload.get("command") or "emergency_stop").strip().lower()
            except (json.JSONDecodeError, AttributeError):
                pass

            if command == "clear_emergency":
                return await self.clear_emergency(esp_id)

            logger.warning(f"[MockActuator] Emergency stop received for {esp_id}")

            async with self._lock:
                # Set emergency flag
                runtime.emergency_stopped = True

                # Turn off all actuators
                for gpio in list(runtime.actuator_states.keys()):
                    runtime.actuator_states[gpio] = False
                    runtime.actuator_pwm_values[gpio] = 0
                    runtime.last_commands[gpio] = "EMERGENCY_STOP"

                    # Publish status for each actuator
                    await self._publish_status(esp_id, gpio)

            logger.info(f"[MockActuator] Emergency stop executed for {esp_id}")
            return True

        except Exception as e:
            logger.error(f"[MockActuator] Error handling emergency: {e}", exc_info=True)
            return False

    async def handle_broadcast_emergency(self, topic: str, payload_str: str) -> bool:
        """
        Handle broadcast emergency for ALL active mocks.

        Payload "command": "clear_emergency" → clear emergency on each mock.
        Otherwise → emergency stop on each mock (same as before).

        Args:
            topic: MQTT topic string
            payload_str: JSON payload string

        Returns:
            True if all processed successfully
        """
        command = "emergency_stop"
        try:
            if payload_str and payload_str.strip():
                payload = json.loads(payload_str)
                command = (payload.get("command") or "emergency_stop").strip().lower()
        except (json.JSONDecodeError, AttributeError):
            pass

        if command == "clear_emergency":
            logger.info("[MockActuator] Broadcast clear_emergency received")
            success = True
            for esp_id in self._scheduler.get_active_mocks():
                if not await self.clear_emergency(esp_id):
                    success = False
            return success

        logger.critical("[MockActuator] Broadcast emergency stop received!")
        success = True
        for esp_id in self._scheduler.get_active_mocks():
            if not await self.handle_emergency(topic, payload_str, esp_id):
                success = False
        return success

    async def emergency_stop(self, esp_id: str, reason: Optional[str] = None) -> bool:
        """
        Trigger emergency stop for a specific ESP (direct API call).

        Paket X: Direct emergency stop without MQTT message.

        Args:
            esp_id: ESP device ID
            reason: Optional reason for emergency stop

        Returns:
            True if emergency stop activated successfully
        """
        # Create a dummy payload for handle_emergency
        payload = {"reason": reason} if reason else {}
        payload_str = json.dumps(payload)
        topic = f"kaiser/god/esp/{esp_id}/actuator/emergency"

        return await self.handle_emergency(topic, payload_str, esp_id)

    async def clear_emergency(self, esp_id: str) -> bool:
        """
        Clear emergency stop for a specific ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            True if emergency cleared successfully
        """
        runtime = self._scheduler.get_runtime(esp_id)
        if not runtime:
            return False

        async with self._lock:
            runtime.emergency_stopped = False
            logger.info(f"[MockActuator] Emergency cleared for {esp_id}")

            # Publish status for all actuators
            for gpio in runtime.actuator_states.keys():
                await self._publish_status(esp_id, gpio)

        return True

    # ================================================================
    # TOPIC PARSING
    # ================================================================

    def _parse_command_topic(self, topic: str) -> Optional[Tuple[str, int]]:
        """
        Parse actuator command topic to extract esp_id and gpio.

        Expected format: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command

        Args:
            topic: MQTT topic string

        Returns:
            Tuple of (esp_id, gpio) or None if parse fails
        """
        # Pattern matches: kaiser/{any}/esp/{esp_id}/actuator/{gpio}/command
        # esp_id can be MOCK_XXX or any alphanumeric with underscores
        pattern = r"kaiser/[a-zA-Z0-9_]+/esp/([A-Za-z0-9_]+)/actuator/(\d+)/command"
        match = re.match(pattern, topic)

        if match:
            esp_id = match.group(1)
            gpio = int(match.group(2))
            return (esp_id, gpio)

        return None

    # ================================================================
    # PAYLOAD VALIDATION
    # ================================================================

    def _validate_command_payload(self, payload: dict) -> dict:
        """
        Validate actuator command payload.

        Required fields: command
        Optional fields: value, duration, timestamp, command_id

        Args:
            payload: Parsed JSON payload dict

        Returns:
            {
                "valid": bool,
                "error": str,
                "command": str,
                "value": float,
                "duration": int
            }
        """
        # Check required field: command
        command = payload.get("command", "").upper()
        if not command:
            return {
                "valid": False,
                "error": "Missing required field: command",
                "command": "",
                "value": 0.0,
                "duration": 0,
            }

        if command not in VALID_COMMANDS:
            return {
                "valid": False,
                "error": f"Unknown command: {command}. Valid: {VALID_COMMANDS}",
                "command": command,
                "value": 0.0,
                "duration": 0,
            }

        # Validate value for PWM command
        value = payload.get("value", 1.0)
        if command == "PWM":
            try:
                value = float(value)
                if not (0.0 <= value <= 1.0):
                    return {
                        "valid": False,
                        "error": f"PWM value out of range (0.0-1.0): {value}",
                        "command": command,
                        "value": value,
                        "duration": 0,
                    }
            except (ValueError, TypeError):
                return {
                    "valid": False,
                    "error": f"PWM value must be numeric: {value}",
                    "command": command,
                    "value": 0.0,
                    "duration": 0,
                }

        # Validate duration (optional, default 0 = unlimited)
        duration = payload.get("duration", 0)
        try:
            duration = int(duration)
            if duration < 0:
                duration = 0
        except (ValueError, TypeError):
            duration = 0

        return {
            "valid": True,
            "error": "",
            "command": command,
            "value": float(value),
            "duration": duration,
        }

    # ================================================================
    # COMMAND EXECUTION
    # ================================================================

    async def _execute_command(
        self, esp_id: str, gpio: int, command: str, value: float, duration: int
    ) -> Tuple[bool, str]:
        """
        Execute actuator command and update runtime state.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            command: Command type (ON/OFF/PWM/TOGGLE)
            value: Value for PWM command (0.0-1.0)
            duration: Auto-off duration in seconds (0 = unlimited)

        Returns:
            Tuple of (success: bool, message: str)
        """
        runtime = self._scheduler.get_runtime(esp_id)
        if not runtime:
            return (False, f"Mock {esp_id} not active")

        # Check emergency stop
        if runtime.emergency_stopped:
            return (False, "Emergency stopped - command rejected")

        # Check if GPIO is configured as actuator
        # Initialize state if not present (for first command)
        if gpio not in runtime.actuator_states:
            runtime.actuator_states[gpio] = False
            runtime.actuator_pwm_values[gpio] = 0
            runtime.actuator_runtime_ms[gpio] = 0
            runtime.last_commands[gpio] = ""

        # Execute command based on type
        if command == "ON":
            runtime.actuator_states[gpio] = True
            runtime.actuator_pwm_values[gpio] = 255
            runtime.last_commands[gpio] = "ON"
            message = "Actuator turned ON"

        elif command == "OFF":
            runtime.actuator_states[gpio] = False
            runtime.actuator_pwm_values[gpio] = 0
            runtime.last_commands[gpio] = "OFF"
            message = "Actuator turned OFF"

            # Cancel any pending auto-off job
            self._cancel_auto_off_job(esp_id, gpio)

        elif command == "PWM":
            pwm_value = int(value * 255)
            runtime.actuator_states[gpio] = pwm_value > 0
            runtime.actuator_pwm_values[gpio] = pwm_value
            runtime.last_commands[gpio] = "PWM"
            message = f"PWM set to {pwm_value} ({value:.2%})"

        elif command == "TOGGLE":
            current_state = runtime.actuator_states.get(gpio, False)
            new_state = not current_state
            runtime.actuator_states[gpio] = new_state
            runtime.actuator_pwm_values[gpio] = 255 if new_state else 0
            runtime.last_commands[gpio] = "TOGGLE"
            message = f"Actuator toggled to {'ON' if new_state else 'OFF'}"

        else:
            return (False, f"Unknown command: {command}")

        # Handle duration-based auto-off
        if duration > 0 and command in ("ON", "PWM", "TOGGLE"):
            if runtime.actuator_states.get(gpio, False):  # Only if actuator is ON
                self._schedule_auto_off(esp_id, gpio, duration)
                message += f" (auto-off in {duration}s)"

        logger.debug(f"[MockActuator] {esp_id} GPIO {gpio}: {message}")
        return (True, message)

    # ================================================================
    # AUTO-OFF SCHEDULING
    # ================================================================

    def _schedule_auto_off(self, esp_id: str, gpio: int, duration: int) -> None:
        """
        Schedule automatic turn-off after duration.

        Uses APScheduler to create a one-time job.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            duration: Seconds until auto-off
        """
        scheduler = get_central_scheduler()
        # Job ID without "mock_" prefix - category adds it automatically
        job_id = f"{esp_id}_auto_off_{gpio}"

        # Remove existing auto-off job if present
        self._cancel_auto_off_job(esp_id, gpio)

        # Schedule new auto-off job using add_onetime_job
        run_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
        scheduler.add_onetime_job(
            job_id=job_id,
            func=self._auto_off_callback,
            run_at=run_at,
            args=[esp_id, gpio],
            category=JobCategory.MOCK_ESP,
        )

        logger.debug(
            f"[MockActuator] Scheduled auto-off for {esp_id} GPIO {gpio} "
            f"in {duration}s (job_id=mock_{job_id})"
        )

    def _cancel_auto_off_job(self, esp_id: str, gpio: int) -> bool:
        """
        Cancel pending auto-off job.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number

        Returns:
            True if job was found and removed
        """
        scheduler = get_central_scheduler()
        # Full job_id includes category prefix
        full_job_id = f"mock_{esp_id}_auto_off_{gpio}"
        return scheduler.remove_job(full_job_id)

    async def _auto_off_callback(self, esp_id: str, gpio: int) -> None:
        """
        Callback for automatic turn-off after duration.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
        """
        runtime = self._scheduler.get_runtime(esp_id)
        if not runtime:
            return

        logger.info(f"[MockActuator] Auto-off triggered for {esp_id} GPIO {gpio}")

        async with self._lock:
            # Turn off actuator
            runtime.actuator_states[gpio] = False
            runtime.actuator_pwm_values[gpio] = 0
            runtime.last_commands[gpio] = "AUTO_OFF"

        # Publish status update
        await self._publish_status(esp_id, gpio)

    # ================================================================
    # MQTT PUBLISHING
    # ================================================================

    async def _publish_response(
        self,
        esp_id: str,
        gpio: int,
        command: str,
        value: float,
        duration: int,
        success: bool,
        message: str,
    ) -> bool:
        """
        Publish actuator command response to MQTT.

        Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            command: Command that was executed
            value: Value parameter
            duration: Duration parameter
            success: Whether command succeeded
            message: Response message

        Returns:
            True if published successfully
        """
        if not self._mqtt_publish:
            logger.warning("[MockActuator] No MQTT publish callback set")
            return False

        runtime = self._scheduler.get_runtime(esp_id)
        kaiser_id = runtime.kaiser_id if runtime else "god"
        zone_id = runtime.zone_id if runtime else ""

        topic = TopicBuilder.build_actuator_response_topic(esp_id, gpio, kaiser_id)

        payload = {
            "esp_id": esp_id,
            "zone_id": zone_id,
            "ts": int(time.time() * 1000),  # MILLISECONDS (CRITICAL!)
            "gpio": gpio,
            "command": command,
            "value": round(value, 3),
            "duration": duration,
            "success": success,
            "message": message,
        }

        try:
            self._mqtt_publish(topic, payload, 1)
            logger.debug(
                f"[MockActuator] Published response: {esp_id} GPIO {gpio} " f"success={success}"
            )
            return True
        except Exception as e:
            logger.error(f"[MockActuator] Failed to publish response: {e}")
            return False

    async def _publish_status(self, esp_id: str, gpio: int) -> bool:
        """
        Publish actuator status to MQTT.

        Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number

        Returns:
            True if published successfully
        """
        if not self._mqtt_publish:
            logger.warning("[MockActuator] No MQTT publish callback set")
            return False

        runtime = self._scheduler.get_runtime(esp_id)
        if not runtime:
            return False

        kaiser_id = runtime.kaiser_id
        zone_id = runtime.zone_id

        # Get actuator state
        state = runtime.actuator_states.get(gpio, False)
        pwm_value = runtime.actuator_pwm_values.get(gpio, 0)
        last_command = runtime.last_commands.get(gpio, "")
        runtime_ms = runtime.actuator_runtime_ms.get(gpio, 0)
        emergency = "active" if runtime.emergency_stopped else "normal"

        # Get actuator type from DB config (normalized to server type)
        actuator_type = await self._get_actuator_type(esp_id, gpio)

        topic = TopicBuilder.build_actuator_status_topic(esp_id, gpio, kaiser_id)

        payload = {
            "esp_id": esp_id,
            "zone_id": zone_id,
            "subzone_id": "",
            "ts": int(time.time() * 1000),  # MILLISECONDS (CRITICAL!)
            "gpio": gpio,
            "actuator_type": actuator_type,
            "type": actuator_type,  # Alias for compatibility
            "state": state,  # BOOLEAN (CRITICAL!)
            "value": pwm_value,  # INTEGER 0-255 (CRITICAL!)
            "pwm": pwm_value,  # Alias for compatibility
            "last_command": last_command,
            "runtime_ms": runtime_ms,
            "emergency": emergency,
            "error": None,
        }

        try:
            self._mqtt_publish(topic, payload, 1)
            logger.debug(
                f"[MockActuator] Published status: {esp_id} GPIO {gpio} "
                f"state={state} pwm={pwm_value}"
            )
            return True
        except Exception as e:
            logger.error(f"[MockActuator] Failed to publish status: {e}")
            return False

    async def _get_actuator_type(self, esp_id: str, gpio: int) -> str:
        """
        Get actuator type from database configuration.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number

        Returns:
            Actuator type string (default: "relay")
        """
        try:
            from ...db.session import get_session
            from ...db.repositories import ESPRepository

            async for session in get_session():
                esp_repo = ESPRepository(session)
                device = await esp_repo.get_by_device_id(esp_id)

                if device and device.device_metadata:
                    sim_config = device.device_metadata.get("simulation_config", {})
                    actuators = sim_config.get("actuators", {})
                    actuator_config = actuators.get(str(gpio), {})
                    raw_type = actuator_config.get("actuator_type", "relay")
                    # Normalize ESP32 type to server type (relay/pump/valve → digital)
                    from ...schemas.actuator import normalize_actuator_type

                    return normalize_actuator_type(raw_type)

                break

        except Exception as e:
            logger.debug(f"[MockActuator] Could not get actuator type: {e}")

        return "digital"

    # ================================================================
    # ACTUATOR INITIALIZATION
    # ================================================================

    async def initialize_actuators(self, esp_id: str, runtime: "MockESPRuntime") -> int:
        """
        Initialize actuator states from database configuration.

        Called when a mock is started to set up initial actuator states.

        Args:
            esp_id: ESP device ID
            runtime: Mock runtime instance

        Returns:
            Number of actuators initialized
        """
        try:
            from ...db.session import get_session
            from ...db.repositories import ESPRepository

            async for session in get_session():
                esp_repo = ESPRepository(session)
                device = await esp_repo.get_by_device_id(esp_id)

                if not device or not device.device_metadata:
                    return 0

                sim_config = device.device_metadata.get("simulation_config", {})
                actuators = sim_config.get("actuators", {})

                count = 0
                for gpio_str, config in actuators.items():
                    try:
                        gpio = int(gpio_str)
                        initial_state = config.get("initial_state", False)
                        initial_pwm = config.get("initial_pwm", 0)

                        runtime.actuator_states[gpio] = initial_state
                        runtime.actuator_pwm_values[gpio] = initial_pwm
                        runtime.actuator_runtime_ms[gpio] = 0
                        runtime.last_commands[gpio] = ""

                        count += 1
                        logger.debug(
                            f"[MockActuator] Initialized {esp_id} GPIO {gpio}: "
                            f"state={initial_state}, pwm={initial_pwm}"
                        )

                    except ValueError as e:
                        logger.error(f"Invalid GPIO '{gpio_str}' in actuator config: {e}")

                return count

        except Exception as e:
            logger.error(f"[MockActuator] Failed to initialize actuators: {e}", exc_info=True)
            return 0
