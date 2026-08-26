"""Detect orphan actuator failures from external/malformed MQTT (not server-originated)."""

from __future__ import annotations

import re
from typing import Optional

MISSING_CORR_ACTUATOR_PREFIX = "missing-corr:act:"
UNKNOWN_ACTUATOR_COMMAND = "UNKNOWN_COMMAND"
ERROR_ACTUATOR_NOT_FOUND = 1052

_GPIO_FROM_MESSAGE_RE = re.compile(r"GPIO\s+(\d+)", re.IGNORECASE)


def is_missing_correlation_actuator(correlation_id: Optional[str]) -> bool:
    return bool(
        correlation_id and str(correlation_id).startswith(MISSING_CORR_ACTUATOR_PREFIX)
    )


def parse_gpio_from_actuator_error_message(message: Optional[str]) -> Optional[int]:
    if not message:
        return None
    match = _GPIO_FROM_MESSAGE_RE.search(message)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_orphan_external_actuator_failure(
    *,
    success: bool,
    correlation_id: Optional[str],
    command: str,
    has_actuator_config: bool,
) -> bool:
    """True when ESP rejected a command the server did not originate for an unconfigured GPIO."""
    if success:
        return False
    if has_actuator_config:
        return False
    if is_missing_correlation_actuator(correlation_id):
        return True
    if command == UNKNOWN_ACTUATOR_COMMAND:
        return True
    return False


def should_suppress_actuator_not_found_error_broadcast(
    *,
    error_code: Optional[int],
    message: Optional[str],
    context_gpio: Optional[int],
    has_actuator_config: bool,
) -> bool:
    if error_code != ERROR_ACTUATOR_NOT_FOUND or has_actuator_config:
        return False
    gpio = context_gpio if context_gpio is not None else parse_gpio_from_actuator_error_message(
        message
    )
    return gpio is not None
