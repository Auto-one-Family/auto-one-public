"""
Empiric concentration from ΔEC (AUT-1371 K2).

1:1 port of FE ``concentrationFromDeltaEc``
(``El Frontend/src/components/esp/recipeMixerCalcs.ts``):

    concentration = (EC₁ − EC₀) × V_l / dose_ml

Units: EC in µS/cm, V in liters, dose in ml → µS/cm rise per ml per L.
"""

from __future__ import annotations

from typing import Optional


def concentration_from_delta_ec(
    ec0_us_cm: float,
    ec1_us_cm: float,
    volume_l: float,
    dose_ml: float,
) -> Optional[float]:
    """
    Compute empiric pump concentration from a measured EC rise.

    Returns:
        Positive concentration, or None when inputs are non-finite / non-positive
        volume/dose (same contract as the FE helper).
    """
    try:
        ec0 = float(ec0_us_cm)
        ec1 = float(ec1_us_cm)
        volume = float(volume_l)
        dose = float(dose_ml)
    except (TypeError, ValueError):
        return None

    if volume <= 0 or dose <= 0:
        return None
    if not all(map(_is_finite, (ec0, ec1, volume, dose))):
        return None

    return ((ec1 - ec0) * volume) / dose


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
