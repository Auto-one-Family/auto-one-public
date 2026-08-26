"""
Salt calculator composition assist — thin orchestration over AUT-1112 (AUT-1343).

Read-only feedforward expectation. Does NOT invent chemistry numbers.
Does NOT dose actuators. Does NOT modify ``calculate_dose_ml``.

AUT-1404: Direction gate BEFORE calling the motor:
  Fall 1 EC_ist < Ziel → dose-up via calculate_ab_dose_expectation
  Fall 2 EC_ist > Ziel → dilute (Frischwasser-L), never salt
  Fall 3 within tolerance → no suggestion
  Frischbatch (explicit) → Fall 1 from EC_fw instead of EC_ist
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .ec_control_anchor import calculate_expected_ec
from .linear_dose_calculator import calculate_dose_ml
from .volume_share import compute_ratio_shares_from_volume

# Legacy constant retained for explicit test callers only (AUT-1381).
# MUST NOT be used as a silent schema/runtime default — tank config or request required.
DEFAULT_EC_WASSER_US_CM = 488.0

SuggestionKind = str  # dose_up | dilute | within_tolerance | unavailable


def dilute_ec_us_cm(
    *,
    prior_ec_us_cm: float,
    prior_volume_l: float,
    ec_wasser_us_cm: float,
    volume_zugabe_l: float,
) -> float:
    """
    Volume-weighted dilution via ``calculate_expected_ec`` (no new solver).

    When ``volume_zugabe_l`` <= 0, returns ``prior_ec_us_cm`` unchanged.
    """
    if volume_zugabe_l <= 0:
        return prior_ec_us_cm
    if prior_volume_l <= 0:
        return ec_wasser_us_cm

    expected = calculate_expected_ec(
        components=[{"ec_contribution": ec_wasser_us_cm}],
        volume_l=volume_zugabe_l,
        prior_volume_l=prior_volume_l,
        prior_ec=prior_ec_us_cm,
    )
    if expected is None:
        return prior_ec_us_cm
    return expected


def calculate_dilution_water_l(
    *,
    volume_l: float,
    ec_ist_us_cm: float,
    ec_ziel_us_cm: float,
    ec_fw_us_cm: float,
) -> float:
    """
    AUT-1404 Fall 2: Frischwasser W [L] to reach EC_ziel by dilution.

    W = V · (EC_ist − EC_ziel) / (EC_ziel − EC_fw)
    Requires EC_ziel > EC_fw and EC_ist > EC_ziel.
    """
    if volume_l <= 0:
        raise ValueError(f"volume_l must be > 0, got {volume_l}")
    if ec_ziel_us_cm <= ec_fw_us_cm:
        raise ValueError("Ziel per Verdünnung nicht erreichbar (Ziel-EC ≤ Frischwasser-EC)")
    if ec_ist_us_cm <= ec_ziel_us_cm:
        raise ValueError("Verdünnung nur wenn gemessener EC über dem Ziel liegt")
    return volume_l * (ec_ist_us_cm - ec_ziel_us_cm) / (ec_ziel_us_cm - ec_fw_us_cm)


def calculate_ab_dose_expectation(
    *,
    current_ec_us_cm: float,
    target_ec_us_cm: float,
    volume_l: float,
    concentration: Optional[float] = None,
    concentration_a: Optional[float] = None,
    concentration_b: Optional[float] = None,
    volume_share_a: Optional[float] = None,
    volume_share_b: Optional[float] = None,
    safety_factor: Optional[float] = None,
    max_delta_per_dose: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    A:B volume-ratio dose via ``calculate_dose_ml`` (AUT-1112).

    Caller MUST ensure current_ec < target_ec (AUT-1404 direction gate).
    Motor uses abs(delta) — do not call when EC is already above target.
    """
    conc_a = concentration_a if concentration_a is not None else concentration
    conc_b = concentration_b if concentration_b is not None else concentration
    if conc_a is None or conc_a <= 0:
        raise ValueError(f"concentration_a must be > 0, got {conc_a}")
    if conc_b is None or conc_b <= 0:
        raise ValueError(f"concentration_b must be > 0, got {conc_b}")

    base_a: Dict[str, Any] = {"concentration": conc_a}
    base_b: Dict[str, Any] = {"concentration": conc_b}
    if volume_share_a is not None:
        base_a["volume_share"] = volume_share_a
    if volume_share_b is not None:
        base_b["volume_share"] = volume_share_b

    ratio_a, ratio_b = compute_ratio_shares_from_volume([base_a, base_b])
    component_a: Dict[str, Any] = {
        "concentration": conc_a,
        "ratio_share": ratio_a,
    }
    component_b: Dict[str, Any] = {
        "concentration": conc_b,
        "ratio_share": ratio_b,
    }
    dose_a = calculate_dose_ml(
        current_value=current_ec_us_cm,
        target_value=target_ec_us_cm,
        volume_l=volume_l,
        components=[component_a],
        safety_factor=safety_factor,
        max_delta_per_dose=max_delta_per_dose,
    )
    dose_b = calculate_dose_ml(
        current_value=current_ec_us_cm,
        target_value=target_ec_us_cm,
        volume_l=volume_l,
        components=[component_b],
        safety_factor=safety_factor,
        max_delta_per_dose=max_delta_per_dose,
    )

    delta = target_ec_us_cm - current_ec_us_cm
    if max_delta_per_dose is not None and max_delta_per_dose > 0:
        if abs(delta) > max_delta_per_dose:
            sign = 1.0 if delta >= 0 else -1.0
            expected_ec = current_ec_us_cm + sign * max_delta_per_dose
        else:
            expected_ec = target_ec_us_cm
    else:
        expected_ec = target_ec_us_cm

    return dose_a, dose_b, expected_ec


def compute_salt_calculator_assist(
    *,
    current_ec_us_cm: float,
    target_ec_us_cm: float,
    volume_alt_l: float,
    concentration: Optional[float] = None,
    concentration_a: Optional[float] = None,
    concentration_b: Optional[float] = None,
    volume_zugabe_l: float = 0.0,
    ec_wasser_us_cm: Optional[float] = None,
    safety_factor: Optional[float] = None,
    max_delta_per_dose: Optional[float] = None,
    fresh_batch: bool = False,
    ec_tolerance_us_cm: float = 0.0,
) -> Dict[str, Any]:
    """
    Full assist pipeline with AUT-1404 direction gate.

    ``ec_tolerance_us_cm`` is the plan_segment Totband (±µS/cm) for Fall 3.
    Default 0 — callers must pass the covering target_ec segment.tolerance
    (no magic number here).

    Raises:
        ValueError: invalid volumes / missing EC_wasser when diluting input
    """
    if volume_alt_l <= 0:
        raise ValueError(f"volume_alt_l must be > 0, got {volume_alt_l}")

    if volume_zugabe_l > 0 and (ec_wasser_us_cm is None or ec_wasser_us_cm < 0):
        raise ValueError(
            "Frischwasser-EC nicht konfiguriert: setze tank.fresh_water_ec_us_cm "
            "oder übergebe ec_wasser_us_cm (kein stiller Ersatzwert)"
        )

    conc_a = concentration_a if concentration_a is not None else concentration
    conc_b = concentration_b if concentration_b is not None else concentration
    legacy_concentration = conc_a if conc_a is not None else conc_b
    if legacy_concentration is None:
        legacy_concentration = 0.0
    concentrations_ready = (
        conc_a is not None
        and conc_a > 0
        and conc_b is not None
        and conc_b > 0
    )

    # Measured/already-applied zugabe: update working EC for dose-up only.
    ec_wasser_effective = (
        float(ec_wasser_us_cm) if ec_wasser_us_cm is not None else 0.0
    )
    ec_after_input_dilution = dilute_ec_us_cm(
        prior_ec_us_cm=current_ec_us_cm,
        prior_volume_l=volume_alt_l,
        ec_wasser_us_cm=ec_wasser_effective,
        volume_zugabe_l=volume_zugabe_l,
    )
    volume_neu = volume_alt_l + max(0.0, volume_zugabe_l)

    # Direction start EC: Frischbatch → EC_fw; otherwise sensor (after measured zugabe).
    if fresh_batch:
        if ec_wasser_us_cm is None or ec_wasser_us_cm < 0:
            return _assist_result(
                volume_alt_l=volume_alt_l,
                volume_zugabe_l=volume_zugabe_l,
                volume_neu_l=volume_neu,
                ec_wasser_us_cm=None,
                ec_after_dilution_us_cm=current_ec_us_cm,
                dose_a_ml=0.0,
                dose_b_ml=0.0,
                expected_ec_us_cm=current_ec_us_cm,
                concentration=legacy_concentration,
                concentration_a=conc_a,
                concentration_b=conc_b,
                suggestion_kind="unavailable",
                fresh_water_suggest_l=None,
                operator_message=(
                    "Frischbatch braucht den Frischwasser-EC am Tank — nicht hinterlegt."
                ),
                notes=["Frischbatch: Frischwasser-EC fehlt."],
            )
        ec_start = float(ec_wasser_us_cm)
        volume_for_dose = volume_alt_l
        ec_after_dilution_us_cm = ec_start
    else:
        ec_start = ec_after_input_dilution
        volume_for_dose = volume_neu
        ec_after_dilution_us_cm = ec_after_input_dilution

    delta = target_ec_us_cm - ec_start
    tol = max(0.0, float(ec_tolerance_us_cm))

    # Fall 3 — within tolerance
    if abs(delta) <= tol:
        return _assist_result(
            volume_alt_l=volume_alt_l,
            volume_zugabe_l=volume_zugabe_l,
            volume_neu_l=volume_neu,
            ec_wasser_us_cm=ec_wasser_us_cm if volume_zugabe_l > 0 or fresh_batch else None,
            ec_after_dilution_us_cm=ec_after_dilution_us_cm,
            dose_a_ml=0.0,
            dose_b_ml=0.0,
            expected_ec_us_cm=ec_start,
            concentration=legacy_concentration,
            concentration_a=conc_a,
            concentration_b=conc_b,
            suggestion_kind="within_tolerance",
            fresh_water_suggest_l=None,
            operator_message="Ist und Ziel liegen nah beieinander — kein Vorschlag.",
            notes=["Nur Vorschlag — dosiert nichts."],
        )

    # Fall 2 — above target: dilute, never salt (unless Frischbatch from EC_fw)
    if delta < 0:
        if fresh_batch:
            return _assist_result(
                volume_alt_l=volume_alt_l,
                volume_zugabe_l=volume_zugabe_l,
                volume_neu_l=volume_neu,
                ec_wasser_us_cm=ec_wasser_us_cm,
                ec_after_dilution_us_cm=ec_after_dilution_us_cm,
                dose_a_ml=0.0,
                dose_b_ml=0.0,
                expected_ec_us_cm=ec_start,
                concentration=legacy_concentration,
                concentration_a=conc_a,
                concentration_b=conc_b,
                suggestion_kind="unavailable",
                fresh_water_suggest_l=None,
                operator_message=(
                    "Frischbatch: Frischwasser-EC liegt schon über dem Ziel — "
                    "Salz senkt den EC nicht."
                ),
                notes=["Frischbatch: Start-EC über Ziel."],
            )
        if ec_wasser_us_cm is None or ec_wasser_us_cm < 0:
            return _assist_result(
                volume_alt_l=volume_alt_l,
                volume_zugabe_l=volume_zugabe_l,
                volume_neu_l=volume_neu,
                ec_wasser_us_cm=None,
                ec_after_dilution_us_cm=ec_after_dilution_us_cm,
                dose_a_ml=0.0,
                dose_b_ml=0.0,
                expected_ec_us_cm=current_ec_us_cm,
                concentration=legacy_concentration,
                concentration_a=conc_a,
                concentration_b=conc_b,
                suggestion_kind="unavailable",
                fresh_water_suggest_l=None,
                operator_message=(
                    "EC liegt über dem Ziel — zum Verdünnen fehlt der Frischwasser-EC am Tank."
                ),
                notes=["Fall 2: Frischwasser-EC nicht hinterlegt."],
            )
        if target_ec_us_cm <= float(ec_wasser_us_cm):
            return _assist_result(
                volume_alt_l=volume_alt_l,
                volume_zugabe_l=volume_zugabe_l,
                volume_neu_l=volume_neu,
                ec_wasser_us_cm=ec_wasser_us_cm,
                ec_after_dilution_us_cm=ec_after_dilution_us_cm,
                dose_a_ml=0.0,
                dose_b_ml=0.0,
                expected_ec_us_cm=current_ec_us_cm,
                concentration=legacy_concentration,
                concentration_a=conc_a,
                concentration_b=conc_b,
                suggestion_kind="unavailable",
                fresh_water_suggest_l=None,
                operator_message=(
                    "Ziel per Verdünnung nicht erreichbar "
                    "(Ziel-EC ist nicht höher als der Frischwasser-EC)."
                ),
                notes=["Fall 2: Ziel ≤ Frischwasser-EC."],
            )
        # Suggest additional Frischwasser from current working state
        # (after any already-measured zugabe).
        water_l = calculate_dilution_water_l(
            volume_l=volume_for_dose,
            ec_ist_us_cm=ec_start,
            ec_ziel_us_cm=target_ec_us_cm,
            ec_fw_us_cm=float(ec_wasser_us_cm),
        )
        return _assist_result(
            volume_alt_l=volume_alt_l,
            volume_zugabe_l=volume_zugabe_l,
            volume_neu_l=volume_neu,
            ec_wasser_us_cm=ec_wasser_us_cm,
            ec_after_dilution_us_cm=ec_after_dilution_us_cm,
            dose_a_ml=0.0,
            dose_b_ml=0.0,
            # Advice only — EC remains current until Frischwasser-Regel runs.
            expected_ec_us_cm=ec_start,
            concentration=legacy_concentration,
            concentration_a=conc_a,
            concentration_b=conc_b,
            suggestion_kind="dilute",
            fresh_water_suggest_l=water_l,
            operator_message=(
                "EC liegt über dem Ziel — Salz würde ihn weiter anheben. "
                f"Vorschlag: ca. {water_l:.1f} L Frischwasser zum Verdünnen. "
                "Ausführung über die Frischwasser-/Level-Regel, nicht über diesen Rechner."
            ),
            notes=["Fall 2: Verdünnen, kein Salz."],
        )

    # Fall 1 — below target: dose salt via motor (unchanged calculate_dose_ml path)
    if not concentrations_ready:
        return _assist_result(
            volume_alt_l=volume_alt_l,
            volume_zugabe_l=volume_zugabe_l,
            volume_neu_l=volume_neu,
            ec_wasser_us_cm=ec_wasser_us_cm if volume_zugabe_l > 0 or fresh_batch else None,
            ec_after_dilution_us_cm=ec_after_dilution_us_cm,
            dose_a_ml=0.0,
            dose_b_ml=0.0,
            expected_ec_us_cm=ec_start,
            concentration=legacy_concentration,
            concentration_a=conc_a,
            concentration_b=conc_b,
            suggestion_kind="unavailable",
            fresh_water_suggest_l=None,
            operator_message=(
                "Wirkstärke der Stammlösungen ist nicht kalibriert — "
                "kein präziser ml-Vorschlag."
            ),
            notes=["Fall 1: Konzentration nicht kalibriert."],
        )

    dose_a, dose_b, expected_ec = calculate_ab_dose_expectation(
        current_ec_us_cm=ec_start,
        target_ec_us_cm=target_ec_us_cm,
        volume_l=volume_for_dose,
        concentration_a=conc_a,
        concentration_b=conc_b,
        safety_factor=safety_factor,
        max_delta_per_dose=max_delta_per_dose,
    )
    batch_note = "Frischbatch: Start am Frischwasser-EC. " if fresh_batch else ""
    return _assist_result(
        volume_alt_l=volume_alt_l,
        volume_zugabe_l=volume_zugabe_l,
        volume_neu_l=volume_neu,
        ec_wasser_us_cm=ec_wasser_us_cm if volume_zugabe_l > 0 or fresh_batch else None,
        ec_after_dilution_us_cm=ec_after_dilution_us_cm,
        dose_a_ml=dose_a,
        dose_b_ml=dose_b,
        expected_ec_us_cm=expected_ec,
        concentration=legacy_concentration if legacy_concentration else (conc_a or 0.0),
        concentration_a=conc_a,
        concentration_b=conc_b,
        suggestion_kind="dose_up",
        fresh_water_suggest_l=None,
        operator_message=(
            f"{batch_note}Vorschlag zum Aufdosieren — zuerst Stock A, dann Stock B. "
            "Dosiert nichts."
        ),
        notes=["Fall 1: Aufdosieren.", "Nur Vorschlag — dosiert nichts."],
    )


def _assist_result(
    *,
    volume_alt_l: float,
    volume_zugabe_l: float,
    volume_neu_l: float,
    ec_wasser_us_cm: Optional[float],
    ec_after_dilution_us_cm: float,
    dose_a_ml: float,
    dose_b_ml: float,
    expected_ec_us_cm: float,
    concentration: float,
    concentration_a: Optional[float],
    concentration_b: Optional[float],
    suggestion_kind: SuggestionKind,
    fresh_water_suggest_l: Optional[float],
    operator_message: str,
    notes: List[str],
) -> Dict[str, Any]:
    return {
        "volume_alt_l": volume_alt_l,
        "volume_zugabe_l": volume_zugabe_l,
        "volume_neu_l": volume_neu_l,
        "ec_wasser_us_cm": ec_wasser_us_cm,
        "ec_after_dilution_us_cm": ec_after_dilution_us_cm,
        "dose_a_ml": dose_a_ml,
        "dose_b_ml": dose_b_ml,
        "expected_ec_us_cm": expected_ec_us_cm,
        "concentration": concentration,
        "concentration_a": concentration_a,
        "concentration_b": concentration_b,
        "suggestion_kind": suggestion_kind,
        "fresh_water_suggest_l": fresh_water_suggest_l,
        "operator_message": operator_message,
        "notes": notes,
    }
