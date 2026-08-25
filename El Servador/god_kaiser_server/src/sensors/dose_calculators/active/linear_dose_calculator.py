"""
Linear Dose Calculator - Reference Implementation

AUT-1112: Computes a dose_ml estimate from (current, target, volume, components,
safety_factor) using a simple linear model:

    dose_ml ≈ |target - current| * volume_l * ratio_share / concentration * safety_factor

split across 1-2 components (e.g. EC stock solutions A+B, or a single pH-Plus/
pH-Minus component). Deliberately simple — Robin/AUT-1102: precision comes from
iterative small doses + remeasuring (closed loop), not from a complex chemistry
model. Directly imported (no auto-discovery loader): only one formula variant
is in scope right now (EC and pH share this same calculation, see AUT-1108).
"""

from typing import Any, Dict, List, Optional


def calculate_dose_ml(
    current_value: float,
    target_value: float,
    volume_l: float,
    components: List[Dict[str, Any]],
    safety_factor: Optional[float] = None,
    dilution_value: Optional[float] = None,
    max_delta_per_dose: Optional[float] = None,
) -> float:
    """
    Estimate dose_ml to move current_value towards target_value.

    Args:
        current_value: Latest measured value (e.g. EC or pH).
        target_value: Configured target value.
        volume_l: Tank/reservoir volume in liters.
        components: 1 entry (e.g. pH-Plus/pH-Minus) or 2 entries (e.g. EC A+B),
            each {"concentration": float, "ratio_share": float}. ratio_share is
            the component's share of the total *EC contribution* (e.g. 0.5/0.5).
            AUT-1366: optional ``volume_share`` on the same dict is SSOT for
            intended *volume* fraction; this function does not read it — callers
            (R2) convert volume_share×concentration → ratio_share first.
        safety_factor: Multiplier applied to the whole dose (None = 1.0).
        dilution_value: Optional multiplier for a diluted stock solution
            (e.g. 10.0 if the stock is diluted 1:10 — needs 10x more volume).
            None = no dilution adjustment. Provisional: exact semantics to be
            refined once Robin configures real dilution ratios.
        max_delta_per_dose: AUT-1118 (S8): optional cap on how much a SINGLE dose
            may change current_value (same unit as current/target; for EC that is
            µS/cm — e.g. max. 100 µS/cm jump per dose). None = uncapped (S2
            behavior unchanged). Applied to delta BEFORE the per-component split,
            so it correctly interacts with dilution_value: the cap bounds the
            value-effect this dose targets, not the resulting ml volume
            (dilution_value only scales how much liquid volume is needed to
            deliver that value-effect).

    Returns:
        Total dose in ml across all components.

    Raises:
        ValueError: on invalid inputs (volume<=0, missing components/values,
            non-positive concentration).
    """
    if current_value is None or target_value is None:
        raise ValueError("current_value and target_value are required")
    if volume_l is None or volume_l <= 0:
        raise ValueError(f"volume_l must be > 0, got {volume_l}")
    if not components:
        raise ValueError("components must contain at least 1 entry")

    delta = abs(target_value - current_value)
    if max_delta_per_dose is not None and max_delta_per_dose > 0:
        delta = min(delta, max_delta_per_dose)
    factor = safety_factor if safety_factor is not None else 1.0

    total_ml = 0.0
    for component in components:
        concentration = component.get("concentration")
        if not concentration or concentration <= 0:
            raise ValueError(f"component concentration must be > 0, got {concentration}")
        ratio_share = component.get("ratio_share", 1.0)
        total_ml += delta * volume_l * ratio_share * factor / concentration

    if dilution_value:
        total_ml *= dilution_value

    return total_ml
