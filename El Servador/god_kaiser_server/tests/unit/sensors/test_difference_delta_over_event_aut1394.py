"""
AUT-1394 [M-2]: difference / delta_over_event formula + explicit registry.

Given two measured values (t0, t1).
When difference_delta_over_event is called.
Then returns t1 − t0 as a pure function (no side effects).
"""

from src.sensors.derived_measurements.active.difference_delta_over_event import (
    difference_delta_over_event,
)
from src.sensors.derived_measurements.registry import (
    FORMULA_REGISTRY,
    get_formula,
    list_formula_ids,
)


def test_difference_delta_over_event_computes_t1_minus_t0():
    assert difference_delta_over_event(800.0, 1000.0) == 200.0
    assert difference_delta_over_event(5.0, 3.0) == -2.0


def test_difference_delta_over_event_rejects_non_finite():
    assert difference_delta_over_event(float("nan"), 1.0) is None
    assert difference_delta_over_event(1.0, float("inf")) is None


def test_difference_delta_over_event_rejects_non_numeric():
    assert difference_delta_over_event("x", 1.0) is None  # type: ignore[arg-type]


def test_registry_maps_both_wave1_ids_explicitly():
    assert set(list_formula_ids()) == {"delta_over_event", "difference"}
    assert get_formula("difference") is difference_delta_over_event
    assert get_formula("delta_over_event") is difference_delta_over_event
    # Direct map — no dynamic loader keys
    assert FORMULA_REGISTRY["difference"] is difference_delta_over_event


def test_registry_unknown_formula_returns_none():
    assert get_formula("rate") is None
