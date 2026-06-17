from types import SimpleNamespace

from src.services.actuator_service import ActuatorService


def test_is_noop_delta_off_when_already_off():
    state = SimpleNamespace(state="off", current_value=0.0)
    assert ActuatorService._is_noop_delta("OFF", 0.0, state) is True


def test_is_noop_delta_on_when_already_on():
    state = SimpleNamespace(state="on", current_value=1.0)
    assert ActuatorService._is_noop_delta("ON", 1.0, state) is True


def test_is_noop_delta_false_when_state_differs():
    state = SimpleNamespace(state="off", current_value=0.0)
    assert ActuatorService._is_noop_delta("ON", 1.0, state) is False


def test_is_noop_delta_on_with_duration_when_already_on():
    # AUT-588: duration > 0 forces re-send even when state matches (ESP timer restart).
    state = SimpleNamespace(state="on", current_value=1.0)
    assert ActuatorService._is_noop_delta("ON", 1.0, state, duration=8) is False


def test_is_noop_delta_on_without_duration_when_already_on_is_still_noop():
    # Baseline: duration=0 (or default) keeps existing no-op behavior.
    state = SimpleNamespace(state="on", current_value=1.0)
    assert ActuatorService._is_noop_delta("ON", 1.0, state, duration=0) is True
