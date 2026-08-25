"""AUT-1371: 1:1 port of FE concentrationFromDeltaEc."""

from src.sensors.dose_calculators.active.concentration_from_delta_ec import (
    concentration_from_delta_ec,
)


def test_concentration_from_delta_ec_matches_fe_example():
    # FE contract: 800→1000, V=100 L, ml=50 → 400
    assert concentration_from_delta_ec(800, 1000, 100, 50) == 400.0


def test_concentration_from_delta_ec_rejects_non_positive_volume_or_dose():
    assert concentration_from_delta_ec(800, 1000, 0, 50) is None
    assert concentration_from_delta_ec(800, 1000, 100, 0) is None
    assert concentration_from_delta_ec(800, 1000, -1, 50) is None


def test_concentration_from_delta_ec_rejects_non_finite():
    assert concentration_from_delta_ec(float("nan"), 1000, 100, 50) is None
    assert concentration_from_delta_ec(800, float("inf"), 100, 50) is None
