"""
AutoOps Context - Shared state across plugin executions.

The context holds:
- User-provided configuration (sensors, preferences)
- Current system state (discovered ESPs, health)
- Execution history (what was done, what failed)
- User answers to questions
- Device mode (mock vs real hardware)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class DeviceMode(str, Enum):
    """How devices are created and managed."""

    MOCK = "mock"  # Mock ESP via debug API (default, safe)
    REAL = "real"  # Real ESP via device registration API
    HYBRID = "hybrid"  # Use existing real devices, fill gaps with mocks


class SimulationPattern(str, Enum):
    """Sensor value simulation patterns for mock devices.

    Must match server-side VariationPattern enum in schemas/debug.py.
    """

    CONSTANT = "constant"
    RANDOM = "random"
    DRIFT = "drift"


def _get_logger(name: str) -> logging.Logger:
    """Get a logger, preferring the server's logging_config if available."""
    try:
        from ...core.logging_config import get_logger

        return get_logger(name)
    except (ImportError, ValueError):
        return logging.getLogger(name)


@dataclass
class SensorSpec:
    """User-specified sensor to configure."""

    sensor_type: str  # DS18B20, SHT31, PH, etc.
    name: Optional[str] = None  # Human-readable name
    gpio: Optional[int] = None  # Specific GPIO (None = auto-assign)
    count: int = 1  # How many of this type
    interface_type: Optional[str] = None  # I2C, ONEWIRE, ANALOG, DIGITAL
    i2c_address: Optional[int] = None
    onewire_address: Optional[str] = None
    raw_value: float = 0.0  # Initial value for mock sensors
    unit: str = ""  # Unit of measurement
    interval_seconds: float = 30.0  # Reading interval
    variation_pattern: SimulationPattern = SimulationPattern.CONSTANT
    variation_range: float = 0.0  # +/- range for simulation


@dataclass
class ActuatorSpec:
    """User-specified actuator to configure."""

    actuator_type: str  # relay, pump, valve, pwm_fan, etc.
    name: Optional[str] = None
    gpio: Optional[int] = None
    count: int = 1
    initial_state: bool = False
    pwm_value: float = 0.0


@dataclass
class ESPSpec:
    """Full specification for an ESP to configure."""

    name: Optional[str] = None
    device_id: Optional[str] = None  # Auto-generated if None
    hardware_type: str = "ESP32_WROOM"  # ESP32_WROOM, XIAO_ESP32_C3
    zone_name: Optional[str] = None
    subzone_name: Optional[str] = None
    sensors: list[SensorSpec] = field(default_factory=list)
    actuators: list[ActuatorSpec] = field(default_factory=list)
    auto_heartbeat: bool = True
    heartbeat_interval: int = 60
    device_mode: DeviceMode = DeviceMode.MOCK


@dataclass
class SystemSnapshot:
    """Snapshot of the current system state."""

    timestamp: str = ""
    esp_devices: list[dict[str, Any]] = field(default_factory=list)
    total_sensors: int = 0
    total_actuators: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    zones: list[str] = field(default_factory=list)
    server_health: dict[str, Any] = field(default_factory=dict)
    mqtt_connected: bool = False
    mock_devices: int = 0
    real_devices: int = 0


@dataclass
class AutoOpsContext:
    """
    Shared context for AutoOps agent execution.

    Passed to every plugin and maintained across the session.
    """

    # Server connection
    server_url: str = "http://localhost:8000"
    auth_token: Optional[str] = None
    username: str = "admin"
    password: str = "admin123"

    # Device mode
    device_mode: DeviceMode = DeviceMode.MOCK

    # User-provided specs
    esp_specs: list[ESPSpec] = field(default_factory=list)

    # User answers to questions
    user_answers: dict[str, Any] = field(default_factory=dict)

    # System state
    system_snapshot: Optional[SystemSnapshot] = None

    # Execution tracking
    session_id: str = ""
    started_at: str = ""
    actions_log: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Configuration
    dry_run: bool = False
    verbose: bool = True
    auto_approve: bool = False  # Skip confirmation for destructive actions
    max_retries: int = 3  # API retry attempts
    retry_delay: float = 1.0  # Base delay between retries (exponential backoff)

    # Phase 4C.4: Extra context data (trigger info, config overrides, user context)
    extra: dict[str, Any] = field(default_factory=dict)

    # Results from previous plugin runs (shared between plugins)
    created_devices: list[dict[str, Any]] = field(default_factory=list)
    configured_sensors: list[dict[str, Any]] = field(default_factory=list)
    configured_actuators: list[dict[str, Any]] = field(default_factory=list)
    diagnosed_issues: list[dict[str, Any]] = field(default_factory=list)
    fixed_issues: list[dict[str, Any]] = field(default_factory=list)
    cleaned_resources: list[dict[str, Any]] = field(default_factory=list)

    # Logger (set after init)
    _logger: Optional[logging.Logger] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.session_id:
            import uuid

            self.session_id = str(uuid.uuid4())[:8]
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()
        self._logger = _get_logger(f"autoops.session.{self.session_id}")

    @property
    def logger(self) -> logging.Logger:
        """Get the session logger."""
        if self._logger is None:
            self._logger = _get_logger(f"autoops.session.{self.session_id}")
        return self._logger

    def log_action(self, action: str, target: str, result: str, details: dict | None = None):
        """Log an action to the execution history."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "result": result,
            "details": details or {},
        }
        self.actions_log.append(entry)
        self.logger.info("Action: %s -> %s: %s", action, target, result)

    def log_error(self, error: str):
        """Log an error."""
        timestamped = f"[{datetime.now(timezone.utc).isoformat()}] {error}"
        self.errors.append(timestamped)
        self.logger.error("AutoOps Error: %s", error)

    def log_warning(self, warning: str):
        """Log a warning."""
        self.logger.warning("AutoOps Warning: %s", warning)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the current context state."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "server_url": self.server_url,
            "authenticated": self.auth_token is not None,
            "device_mode": self.device_mode.value,
            "esp_specs_count": len(self.esp_specs),
            "created_devices": len(self.created_devices),
            "configured_sensors": len(self.configured_sensors),
            "configured_actuators": len(self.configured_actuators),
            "diagnosed_issues": len(self.diagnosed_issues),
            "fixed_issues": len(self.fixed_issues),
            "cleaned_resources": len(self.cleaned_resources),
            "total_actions": len(self.actions_log),
            "total_errors": len(self.errors),
        }

    @property
    def is_mock_mode(self) -> bool:
        """Check if we're operating in mock device mode."""
        return self.device_mode in (DeviceMode.MOCK, DeviceMode.HYBRID)

    @property
    def is_real_mode(self) -> bool:
        """Check if we're operating in real device mode."""
        return self.device_mode in (DeviceMode.REAL, DeviceMode.HYBRID)
