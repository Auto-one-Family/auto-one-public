"""Regression tests for hardware_type restore in the actuator config push (AUT-997/AUT-998).

Bug: build_actuator_payload() restored the ESP32 hardware token only when
``payload["actuator_type"] == "digital"``. But apply_actuator_mapping() runs the
``actuator_type_to_esp32`` transform first, which maps "digital" -> "relay", so the
condition was never true (dead code). Every binary actuator — including pumps and
valves — was therefore pushed to the ESP32 as "relay", regardless of its real
hardware_type. This silently breaks pump-only dosing logic (``hardware_type == "pump"``).

Fix: compare against the ORIGINAL DB value ``actuator.actuator_type`` (nullable=False,
always present, still "digital" at that point) instead of the already-transformed payload.
"""

from types import SimpleNamespace

from src.services.config_builder import ConfigPayloadBuilder


def _actuator(actuator_type: str, hardware_type: str | None) -> SimpleNamespace:
    """Minimal ActuatorConfig-like object accepted by build_actuator_payload()."""
    return SimpleNamespace(
        gpio=26,
        actuator_type=actuator_type,
        hardware_type=hardware_type,
        actuator_name="Dosing Pump",
        enabled=True,
        actuator_metadata={},
        safety_constraints={"max_runtime": 60, "cooldown_period": 30},
        fail_safe_on_disconnect=True,
        flow_rate_ml_s=2.5,
    )


def test_pump_is_pushed_as_pump_not_relay() -> None:
    """A pump stored as actuator_type='digital' must reach the ESP32 as 'pump'."""
    builder = ConfigPayloadBuilder()
    payload = builder.build_actuator_payload(_actuator("digital", "pump"))
    assert payload["actuator_type"] == "pump"


def test_valve_is_pushed_as_valve() -> None:
    """Same restore mechanism preserves 'valve'."""
    builder = ConfigPayloadBuilder()
    payload = builder.build_actuator_payload(_actuator("digital", "valve"))
    assert payload["actuator_type"] == "valve"


def test_plain_relay_stays_relay() -> None:
    """hardware_type='relay' is unchanged (regression guard for the common case)."""
    builder = ConfigPayloadBuilder()
    payload = builder.build_actuator_payload(_actuator("digital", "relay"))
    assert payload["actuator_type"] == "relay"


def test_unmigrated_row_falls_back_to_relay() -> None:
    """Not-yet-migrated rows (hardware_type=None) keep the ESP32 default 'relay'."""
    builder = ConfigPayloadBuilder()
    payload = builder.build_actuator_payload(_actuator("digital", None))
    assert payload["actuator_type"] == "relay"


def test_pwm_is_unaffected() -> None:
    """PWM never takes the digital->relay path, so it is unaffected by the fix."""
    builder = ConfigPayloadBuilder()
    payload = builder.build_actuator_payload(_actuator("pwm", "pwm"))
    assert payload["actuator_type"] == "pwm"
