"""Hardware profile validation for F4 Hardware-Test-Flow."""

from pathlib import Path
from typing import Any

import yaml

# GPIO constraints per board type.
# Source of truth: gpio_validation_service.py (SYSTEM_RESERVED_PINS_WROOM, SYSTEM_RESERVED_PINS_C3).
# Keep these sets synchronized when adding new board types.
BOARD_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "ESP32_WROOM": {
        "system_reserved": {0, 1, 2, 3, 6, 7, 8, 9, 10, 11, 12},
        "input_only": {34, 35, 36, 39},
        "i2c_default": {"sda": 21, "scl": 22},
        "gpio_range": range(0, 40),
    },
    "XIAO_ESP32_C3": {
        "system_reserved": {18, 19},
        "input_only": set(),
        "i2c_default": {"sda": 4, "scl": 5},
        "gpio_range": range(0, 22),
    },
}

# Sensor types registered in firmware (El Trabajante/src/models/sensor_registry.cpp).
# Only these types have ESP32 driver support and can produce sensor data.
FIRMWARE_PROVEN_SENSOR_TYPES = {"ds18b20", "sht31", "bmp280", "bme280"}
FIRMWARE_REGISTERED_SENSOR_TYPES = FIRMWARE_PROVEN_SENSOR_TYPES | {"ph", "ec", "moisture"}

# Types known to the server but WITHOUT firmware driver support.
# Cannot be used in F4 hardware tests (no ESP32 driver to produce data).
SERVER_ONLY_SENSOR_TYPES = {"co2", "light", "flow"}

# For hardware-test profile validation, only firmware-registered types are valid.
VALID_SENSOR_TYPES = FIRMWARE_REGISTERED_SENSOR_TYPES

VALID_ACTUATOR_TYPES = {"relay", "pump", "valve", "pwm", "pwm_fan"}

VALID_INTERFACES = {"ONEWIRE", "I2C", "ANALOG"}


def validate_profile(profile_path: str) -> list[str]:
    """Validate a hardware profile YAML file.

    Args:
        profile_path: Path to the YAML profile file.

    Returns:
        List of error messages. Empty list means the profile is valid.
    """
    errors: list[str] = []
    path = Path(profile_path)

    if not path.exists():
        errors.append(f"Profile file not found: {profile_path}")
        return errors

    with open(path) as f:
        profile = yaml.safe_load(f)

    if not isinstance(profile, dict):
        errors.append("Profile must be a YAML mapping")
        return errors

    # Required top-level keys
    for key in ("name", "description", "version", "esp"):
        if key not in profile:
            errors.append(f"Missing required key: {key}")

    # Board validation
    esp = profile.get("esp", {})
    board = esp.get("board", "ESP32_WROOM")
    constraints = BOARD_CONSTRAINTS.get(board)
    if not constraints:
        errors.append(f"Unknown board type: {board}")
        return errors

    used_gpios: set[int] = set()

    # Sensor validation
    for i, sensor in enumerate(profile.get("sensors", [])):
        prefix = f"sensors[{i}]"
        gpio = sensor.get("gpio")
        stype = sensor.get("type")
        interface = sensor.get("interface")

        if not stype:
            errors.append(f"{prefix}: missing 'type'")
        elif stype not in VALID_SENSOR_TYPES:
            errors.append(f"{prefix}: unknown sensor type '{stype}'")

        if not sensor.get("name"):
            errors.append(f"{prefix}: missing 'name'")

        if interface and interface not in VALID_INTERFACES:
            errors.append(f"{prefix}: unknown interface '{interface}'")

        if gpio is None:
            errors.append(f"{prefix}: missing 'gpio'")
        else:
            if gpio in constraints["system_reserved"]:
                errors.append(f"{prefix} ({stype}): GPIO {gpio} is system-reserved")
            if gpio not in constraints["gpio_range"]:
                errors.append(f"{prefix} ({stype}): GPIO {gpio} out of range for {board}")
            # I2C sensors can share the SDA pin
            if interface != "I2C" and gpio in used_gpios:
                errors.append(f"{prefix} ({stype}): GPIO {gpio} already in use")
            used_gpios.add(gpio)

    # Actuator validation
    for i, actuator in enumerate(profile.get("actuators", [])):
        prefix = f"actuators[{i}]"
        gpio = actuator.get("gpio")
        atype = actuator.get("type")

        if not atype:
            errors.append(f"{prefix}: missing 'type'")
        elif atype not in VALID_ACTUATOR_TYPES:
            errors.append(f"{prefix}: unknown actuator type '{atype}'")

        if not actuator.get("name"):
            errors.append(f"{prefix}: missing 'name'")

        if gpio is None:
            errors.append(f"{prefix}: missing 'gpio'")
        else:
            if gpio in constraints["system_reserved"]:
                errors.append(f"{prefix} ({atype}): GPIO {gpio} is system-reserved")
            if gpio in constraints["input_only"]:
                errors.append(
                    f"{prefix} ({atype}): GPIO {gpio} is input-only (cannot drive actuator)"
                )
            if gpio in used_gpios:
                errors.append(f"{prefix} ({atype}): GPIO {gpio} already in use")
            used_gpios.add(gpio)

    return errors
