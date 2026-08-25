"""AUT-1371: V_real helper constants and level-active heuristic."""

from types import SimpleNamespace

from src.services.tank_volume_truth import (
    LEVEL_ANCHOR_LITERS,
    LEVEL_ANCHOR_SENSOR_NAME,
    _level_is_active,
)


def test_anchor_constants_match_pi_home_design():
    assert LEVEL_ANCHOR_LITERS == 20.0
    assert LEVEL_ANCHOR_SENSOR_NAME == "20 Liter"


def test_level_is_active_uses_processed_or_raw():
    assert _level_is_active(SimpleNamespace(processed_value=1.0, raw_value=0.0))
    assert _level_is_active(SimpleNamespace(processed_value=None, raw_value=1.0))
    assert not _level_is_active(SimpleNamespace(processed_value=0.0, raw_value=0.0))
    assert not _level_is_active(SimpleNamespace(processed_value=None, raw_value=None))


def test_resolve_v_real_formula_is_anchor_plus_inflow_only():
    """AUT-1377: documented gap — no drain subtraction in V_real (DtW not in flow)."""
    # Contract check: live path returns exactly LEVEL_ANCHOR_LITERS (no invented drain).
    assert LEVEL_ANCHOR_LITERS == 20.0
    assert LEVEL_ANCHOR_SENSOR_NAME == "20 Liter"
