"""
Safety Checks Service

Safety validation for actuator commands, emergency stop handling.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..core.logging_config import get_logger
from ..core.metrics import increment_safety_trigger
from ..db.repositories import ActuatorRepository, ESPRepository

logger = get_logger(__name__)


class EmergencyState(Enum):
    """
    Emergency State Enum (MUST match ESP32 EmergencyState).

    Values match ESP32 actuator_types.h:
    - EMERGENCY_NORMAL = "normal"
    - EMERGENCY_ACTIVE = "active"
    - EMERGENCY_CLEARING = "clearing"
    - EMERGENCY_RESUMING = "resuming"
    """

    NORMAL = "normal"
    ACTIVE = "active"
    CLEARING = "clearing"
    RESUMING = "resuming"


@dataclass
class SafetyCheckResult:
    """
    Result of safety validation check.

    Attributes:
        valid: Whether the command is safe to execute
        error: Error message if validation failed
        warnings: Optional list of warnings
    """

    valid: bool
    error: Optional[str] = None
    warnings: Optional[list[str]] = None


class SafetyService:
    """
    Safety validation for actuator commands.

    Validates commands before execution, handles emergency stops.
    Thread-safe for MQTT callback invocations.
    """

    # Process-wide emergency state: shared across all SafetyService instances.
    _global_emergency_stop_active: dict[str, bool] = {}
    _global_lock = asyncio.Lock()

    def __init__(self, actuator_repo: ActuatorRepository, esp_repo: ESPRepository):
        """
        Initialize Safety Service.

        Args:
            actuator_repo: ActuatorRepository instance
            esp_repo: ESPRepository instance
        """
        self.actuator_repo = actuator_repo
        self.esp_repo = esp_repo
        # Keep instance fields as aliases to shared process-wide state.
        self._emergency_stop_active = SafetyService._global_emergency_stop_active
        self._lock = SafetyService._global_lock

    def _is_emergency_stop_active_unlocked(self, esp_id: Optional[str] = None) -> bool:
        """
        Check emergency flags without acquiring the lock.

        MUST ONLY be called when the caller already holds self._lock.
        """
        if "__ALL__" in self._emergency_stop_active:
            return True

        if esp_id:
            return self._emergency_stop_active.get(esp_id, False)

        return len(self._emergency_stop_active) > 0

    async def validate_actuator_command(
        self, esp_id: str, gpio: int, command: str, value: float
    ) -> SafetyCheckResult:
        """
        Validate actuator command before execution.

        Checks:
        - Emergency stop status
        - PWM value range (0.0-1.0)
        - GPIO conflicts
        - Timeout constraints

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            command: Command type (ON, OFF, PWM, TOGGLE)
            value: Command value (0.0-1.0 for PWM)

        Returns:
            SafetyCheckResult indicating if command is safe
        """
        async with self._lock:
            # Check emergency stop first (absolute priority)
            if self._is_emergency_stop_active_unlocked(esp_id):
                return SafetyCheckResult(
                    valid=False,
                    error=f"Emergency stop is active for ESP {esp_id}",
                )

            # Check global emergency stop
            if self._is_emergency_stop_active_unlocked():
                return SafetyCheckResult(
                    valid=False,
                    error="Global emergency stop is active",
                )

            # Validate value range
            if value < 0.0 or value > 1.0:
                return SafetyCheckResult(
                    valid=False,
                    error=f"Value {value} out of range [0.0, 1.0]. PWM values must be 0.0-1.0, not 0-255!",
                )

            # Check safety constraints
            return await self.check_safety_constraints(esp_id, gpio, value)

    async def check_safety_constraints(
        self, esp_id: str, gpio: int, value: float
    ) -> SafetyCheckResult:
        """
        Check safety constraints for actuator.

        Checks:
        - Actuator exists and is enabled
        - Value is within min_value/max_value range
        - GPIO conflicts (if any)
        - Timeout constraints

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            value: Command value

        Returns:
            SafetyCheckResult
        """
        warnings = []

        # Lookup ESP device
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            return SafetyCheckResult(
                valid=False,
                error=f"ESP device not found: {esp_id}",
            )

        # V1-22: Online Guard — Commands to offline ESPs are silently dropped
        # by the MQTT broker (clean_session=true). Reject early with clear feedback.
        if not esp_device.is_online:
            return SafetyCheckResult(
                valid=False,
                error=f"ESP device is offline: {esp_id} (status={esp_device.status})",
            )

        # Lookup actuator config
        actuator_config = await self.actuator_repo.get_by_esp_and_gpio(esp_device.id, gpio)

        if not actuator_config:
            return SafetyCheckResult(
                valid=False,
                error=f"Actuator config not found: esp_id={esp_id}, gpio={gpio}",
            )

        # Check if actuator is enabled
        if not actuator_config.enabled:
            return SafetyCheckResult(
                valid=False,
                error=f"Actuator is disabled: {actuator_config.actuator_name}",
            )

        # Check value range
        if value < actuator_config.min_value or value > actuator_config.max_value:
            return SafetyCheckResult(
                valid=False,
                error=(
                    f"Value {value} out of allowed range "
                    f"[{actuator_config.min_value}, {actuator_config.max_value}]"
                ),
            )

        # Check timeout (if actuator is currently active)
        actuator_state = await self.actuator_repo.get_state(esp_device.id, gpio)
        if actuator_state and actuator_config.timeout_seconds:
            # Check if actuator has been running too long
            # Note: This is a basic check. Full timeout enforcement is done on ESP32 side.
            if actuator_state.state in ("on", "pwm"):
                warnings.append(
                    f"Actuator is already active. Timeout: {actuator_config.timeout_seconds}s"
                )

        # Check GPIO conflicts (same GPIO used by multiple actuators on same ESP)
        # This is already enforced by unique constraint in DB, but we can add a warning
        all_actuators = await self.actuator_repo.get_by_esp(esp_device.id)
        gpio_conflicts = [a for a in all_actuators if a.gpio == gpio and a.id != actuator_config.id]
        if gpio_conflicts:
            warnings.append(
                f"GPIO {gpio} is used by multiple actuators: {[a.actuator_name for a in gpio_conflicts]}"
            )

        return SafetyCheckResult(
            valid=True,
            warnings=warnings if warnings else None,
        )

    async def emergency_stop_all(self) -> None:
        """
        Emergency stop all ESPs.

        Sets global emergency stop flag. All actuator commands will be blocked.
        """
        async with self._lock:
            self._emergency_stop_active["__ALL__"] = True
            increment_safety_trigger()
            logger.critical("EMERGENCY STOP ACTIVATED: All ESPs stopped")

    async def emergency_stop_esp(self, esp_id: str) -> None:
        """
        Emergency stop specific ESP.

        Args:
            esp_id: ESP device ID to stop
        """
        async with self._lock:
            self._emergency_stop_active[esp_id] = True
            increment_safety_trigger()
            logger.critical(f"EMERGENCY STOP ACTIVATED: ESP {esp_id} stopped")

    async def clear_emergency_stop(self, esp_id: Optional[str] = None) -> None:
        """
        Clear emergency stop for specific ESP or all ESPs.

        Args:
            esp_id: ESP device ID to clear, or None to clear global emergency stop
        """
        async with self._lock:
            if esp_id is None:
                # Clear global emergency stop
                self._emergency_stop_active.pop("__ALL__", None)
                logger.info("EMERGENCY STOP CLEARED: All ESPs")
            else:
                # Clear specific ESP emergency stop
                self._emergency_stop_active.pop(esp_id, None)
                logger.info(f"EMERGENCY STOP CLEARED: ESP {esp_id}")

    async def is_emergency_stop_active(self, esp_id: Optional[str] = None) -> bool:
        """
        Check if emergency stop is active.

        Args:
            esp_id: Optional ESP device ID to check. If None, checks global emergency stop.

        Returns:
            True if emergency stop is active, False otherwise
        """
        async with self._lock:
            return self._is_emergency_stop_active_unlocked(esp_id)
