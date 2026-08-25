"""
EC Control Anchor - Volume-Weighted Mixing Sanity Check

AUT-1211 follow-up (verify-plan, Stufe 2/3): a non-blocking sanity check
for NutrientSolutionBatch entries. EC alone cannot tell individual
nutrient concentrations apart, so it is used here only as a control
anchor (comparison value), never as the source of truth for what was
actually dosed.

Deliberately NOT an extension of calculate_dose_ml() (linear_dose_calculator.py):
that function solves the opposite direction of the problem — "how much ml
of ONE dosing action moves current_value towards target_value" — while this
module answers "given the volumes/EC-contributions that went into a tank,
what combined EC would we expect, so we can flag when a measurement looks
off". Different inputs (a mixing history vs. a single current/target
delta), different output semantics (a mixing target that never triggers to
be transferred to a pump) and different callers — bolting this onto
calculate_dose_ml would make its already-simple signature overloaded with
unrelated concerns. Hence a separate module, following the same "keep the
model deliberately simple" principle documented there.

Only EC is modeled this way. pH is intentionally NOT supported: pH is not
linearly mixable due to carbonate buffering in tap/source water (mixing
two solutions of pH A and B does not yield a volume-weighted average pH).
pH stays iterative/remeasured, per the same principle as calculate_dose_ml.

No ion-balance model, no automatic root-cause diagnosis: this module never
attempts to explain WHY a measured EC deviates (e.g. "too much Calcinit").
It only computes a linear, volume-weighted expected EC and flags drift
above a threshold that must come from real configuration — no invented
default percentage.

AUT-1350: The mixing formula is **scale-invariant** (same unit in → same unit
out). Prefer ``calculate_expected_ec`` with unit-agnostic keys. Ledger batch
paths keep historic ``*_ms_cm`` names and call in **mS/cm**; Assist dilution
calls in **µS/cm**. Cross Ledger↔µS only via ``services.ledger_ec_units``.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ....core.logging_config import get_logger
from ....db.repositories.system_config_repo import SystemConfigRepository

logger = get_logger(__name__)

EC_DRIFT_THRESHOLD_CONFIG_KEY = "nutrient_batch.ec_drift_threshold_pct"

# AUT-1352 B4: pH doses share top_up_dose volume path but are excluded from EC mix.
PH_EC_EXCLUDED_ROLES = frozenset({"ph_minus", "ph_plus", "ph_acid", "ph_base"})


def exclude_from_ec_composition(component: Dict[str, Any]) -> bool:
    """True when a ledger component must not enter EC composition math."""
    if not isinstance(component, dict):
        return False
    if component.get("exclude_from_ec_composition") is True:
        return True
    role = component.get("role")
    if isinstance(role, str) and role.strip().lower() in PH_EC_EXCLUDED_ROLES:
        return True
    name = component.get("name")
    if isinstance(name, str):
        label = name.strip().lower().replace(" ", "").replace("_", "-")
        return any(
            token in label
            for token in (
                "ph-minus",
                "ph-plus",
                "phminus",
                "phplus",
                "phsäure",
                "phsaeure",
            )
        )
    return False


def _component_ec_contribution(component: Dict[str, Any]) -> Optional[float]:
    """Prefer scale-free key; accept legacy ``ec_contribution_ms_cm``."""
    # AUT-1352 B4: pH-tagged doses stay in V_alt but never enter EC composition.
    if exclude_from_ec_composition(component):
        return None
    if "ec_contribution" in component and component["ec_contribution"] is not None:
        return float(component["ec_contribution"])
    if (
        "ec_contribution_ms_cm" in component
        and component["ec_contribution_ms_cm"] is not None
    ):
        return float(component["ec_contribution_ms_cm"])
    return None


def calculate_expected_ec(
    components: List[Dict[str, Any]],
    volume_l: float,
    prior_volume_l: float = 0.0,
    prior_ec: Optional[float] = None,
    *,
    prior_ec_ms_cm: Optional[float] = None,
) -> Optional[float]:
    """
    Scale-invariant volume-weighted expected EC (AUT-1350).

    Unit is **caller-defined** (µS/cm for Assist, mS/cm for Ledger anchor) —
    no ×/÷1000 inside. Historic alias: ``calculate_expected_ec_ms_cm``.

    Each component MAY carry ``ec_contribution`` (preferred) or legacy
    ``ec_contribution_ms_cm``. Components without a contribution are skipped.

    Args:
        components: Entry component list (see NutrientSolutionBatch).
        volume_l: Volume in liters of the new addition.
        prior_volume_l: Volume already in the tank (0.0 = nothing to mix into).
        prior_ec: Prior EC in the **same unit** as contributions.
        prior_ec_ms_cm: Legacy kw-only alias for ``prior_ec`` (Ledger call sites).

    Returns:
        Expected EC in the caller's unit, or None if no contribution supplied.
    """
    if volume_l <= 0:
        return None

    if prior_ec is None:
        prior_ec = prior_ec_ms_cm

    contributing = [
        c
        for c in components
        if isinstance(c, dict) and _component_ec_contribution(c) is not None
    ]
    if not contributing:
        return None

    new_addition_ec = sum(
        float(_component_ec_contribution(c) or 0.0) for c in contributing
    )

    if prior_volume_l > 0 and prior_ec is not None:
        total_volume_l = prior_volume_l + volume_l
        return (prior_volume_l * prior_ec + volume_l * new_addition_ec) / total_volume_l

    return new_addition_ec


# Legacy name kept for Ledger/anchor call sites (same function, scale-free).
calculate_expected_ec_ms_cm = calculate_expected_ec


async def check_ec_control_anchor(
    session: AsyncSession,
    components: List[Dict[str, Any]],
    volume_l: float,
    ec_measured_after: Optional[float],
    ec_was_measured: bool,
    prior_volume_l: float = 0.0,
    prior_ec_ms_cm: Optional[float] = None,
) -> List[str]:
    """
    Non-blocking EC control-anchor check for a NutrientSolutionBatch entry.

    Fail-open, NEVER raises, NEVER blocks the batch entry from being saved —
    same principle as LogicService._check_pi_enhanced_warning (DP7). Skips
    entirely (no warning, no exception) when: EC was not measured, no
    component supplied an EC contribution, or no drift threshold is
    configured — a missing/null/empty threshold is NOT replaced with an
    invented default percentage.

    Returns:
        Zero or more human-readable warning strings for the API response
        (transient; never persisted on the ledger row). Empty list = No-Op.
    """
    if not ec_was_measured or ec_measured_after is None:
        return []

    try:
        # Ledger-native mS/cm (same side of AUT-1350 boundary as create_batch).
        expected_ec = calculate_expected_ec(
            components,
            volume_l,
            prior_volume_l,
            prior_ec_ms_cm=prior_ec_ms_cm,
        )
        if expected_ec is None or expected_ec <= 0:
            return []

        config_repo = SystemConfigRepository(session)
        threshold_entry = await config_repo.get_by_key(EC_DRIFT_THRESHOLD_CONFIG_KEY)
        if threshold_entry is None:
            return []

        threshold_value = threshold_entry.config_value
        if isinstance(threshold_value, dict) and "value" in threshold_value:
            threshold_value = threshold_value["value"]
        # Deactivated slot (seeded key with null/empty) — same No-Op as missing key.
        if threshold_value is None or threshold_value == "":
            return []

        threshold_pct = float(threshold_value)

        drift_pct = abs(ec_measured_after - expected_ec) / expected_ec * 100.0
        if drift_pct > threshold_pct:
            message = (
                f"EC-Kontrollanker: gemessene EC {ec_measured_after:.3f} mS/cm "
                f"weicht {drift_pct:.1f}% von erwarteter EC {expected_ec:.3f} mS/cm "
                f"ab (Schwellwert {threshold_pct:.1f}%)"
            )
            logger.warning(message)
            return [message]
        return []
    except Exception as e:
        logger.warning("EC-Kontrollanker-Check uebersprungen (fail-open): %s", e)
        return []
