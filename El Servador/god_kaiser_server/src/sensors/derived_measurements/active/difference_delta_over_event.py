"""
Difference / delta-over-event formula (AUT-1394 / M-2).

Pure function: derived = value_t1 - value_t0.

Style mirror of ``concentration_from_delta_ec`` (signatur-/Fehlervertrag),
but this module is independent — Auto-Cal / dose calculators are untouched.

Directly imported via ``derived_measurements.registry`` (no auto-discovery).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def difference_delta_over_event(
    value_t0: float,
    value_t1: float,
    formula_params: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """
    Compute t1 − t0 from two measured values.

    Args:
        value_t0: Measurement at earlier hook (e.g. on_start).
        value_t1: Measurement at later hook (e.g. after_settle / on_complete).
        formula_params: Reserved for formula-specific params from the binding;
            unused by this wave-1 formula (no invented knobs).

    Returns:
        Finite float delta, or None when inputs are non-finite / non-numeric.
    """
    del formula_params  # wave-1: no params required
    try:
        t0 = float(value_t0)
        t1 = float(value_t1)
    except (TypeError, ValueError):
        return None

    if not all(map(_is_finite, (t0, t1))):
        return None

    return t1 - t0


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
