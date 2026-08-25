"""
Shared grower-facing growth-phase vocabulary.

Space (WHERE) is zone / subzone. Time (WHEN) is a plant-phase section.
This module is the single mapping for phase *keys* used by:

- plants.phase / plants.nutrient_phase (write SSOT)
- zone_contexts.growth_phase (display cache + empty-zone hint)
- plan_segments.phase_ref (same keys, not a second enum)

Legacy zone-context free strings (``flower_week_5``, ``vegetative``, …)
normalize onto ``PLANT_PHASES``. Unknown values stay unknown (None)
rather than being silently invented.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from ..db.models.plant import NUTRIENT_PHASES, PLANT_PHASES

CANONICAL_PHASES: tuple[str, ...] = PLANT_PHASES
CANONICAL_PHASE_SET: frozenset[str] = frozenset(PLANT_PHASES)
NUTRIENT_PHASE_SET: frozenset[str] = frozenset(NUTRIENT_PHASES)

# Old zone-context / threshold vocabulary → canonical plant phase.
# Week numbers collapse onto the three bloom bands the plant model already has.
LEGACY_ZONE_PHASE_TO_CANONICAL: dict[str, str] = {
    "seedling": "clone",
    "clone": "clone",
    "vegetative": "veg-frueh",
    "veg": "veg-frueh",
    "pre_flower": "uebergang-vorbluete",
    "pre-flower": "uebergang-vorbluete",
    "flower": "bluete-stretch",
    "flower_early": "bluete-stretch",
    "flower_late": "bluete-bulk",
    "flower_week_1": "bluete-stretch",
    "flower_week_2": "bluete-stretch",
    "flower_week_3": "bluete-stretch",
    "flower_week_4": "bluete-stretch",
    "flower_week_5": "bluete-bulk",
    "flower_week_6": "bluete-bulk",
    "flower_week_7": "bluete-bulk",
    "flower_week_8": "bluete-bulk",
    "flower_week_9": "bluete-ende",
    "flower_week_10": "bluete-ende",
    "flush": "bluete-ende",
    "harvest": "harvested",
    "harvested": "harvested",
    "drying": "harvested",
    "curing": "harvested",
}

# Canonical plant phase → coarse bucket used by zone-aware alert thresholds.
CANONICAL_TO_THRESHOLD_BUCKET: dict[str, str] = {
    "invitro_donor": "clone",
    "invitro_initiation": "clone",
    "invitro_multiplication": "clone",
    "invitro_rooting": "clone",
    "invitro_acclimatization": "clone",
    "clone": "clone",
    "steckling_wurzelung": "clone",
    "steckling_vor_versand": "clone",
    "veg-frueh": "vegetative",
    "veg-spaet": "vegetative",
    "uebergang-vorbluete": "pre_flower",
    "bluete-stretch": "flower_early",
    "bluete-bulk": "flower_late",
    "bluete-ende": "flower_late",
    "mutter": "vegetative",
    "harvested": "drying",
    "archived": "drying",
}

MEASURE_EVENT_TYPES: frozenset[str] = frozenset(
    ("topping", "defoliation", "transplanted", "training")
)


def normalize_growth_phase(raw: Optional[str]) -> Optional[str]:
    """Map any known phase string onto ``PLANT_PHASES``.

    Returns ``None`` for empty or unknown values (no silent default).
    """
    if raw is None:
        return None
    key = raw.strip().lower().replace(" ", "_")
    if not key:
        return None
    if key in CANONICAL_PHASE_SET:
        return key
    if key in LEGACY_ZONE_PHASE_TO_CANONICAL:
        return LEGACY_ZONE_PHASE_TO_CANONICAL[key]
    if key.startswith("flower_week_"):
        suffix = key.removeprefix("flower_week_")
        try:
            week = int(suffix)
        except ValueError:
            return "bluete-stretch"
        if week <= 4:
            return "bluete-stretch"
        if week <= 8:
            return "bluete-bulk"
        return "bluete-ende"
    return None


def require_canonical_phase(raw: Optional[str]) -> str:
    """Normalize or raise ``ValueError`` when the value cannot be mapped."""
    canonical = normalize_growth_phase(raw)
    if canonical is None:
        raise ValueError(f"Unknown growth phase: {raw!r}")
    return canonical


def to_threshold_bucket(phase: Optional[str]) -> str:
    """Coarse threshold bucket; unknown/empty falls back to vegetative."""
    canonical = normalize_growth_phase(phase)
    if canonical is None:
        return "vegetative"
    return CANONICAL_TO_THRESHOLD_BUCKET.get(canonical, "vegetative")


def majority_phase(phases: list[Optional[str]]) -> Optional[str]:
    """Most frequent canonical phase; ties keep the first-seen winner."""
    counts: Counter[str] = Counter()
    order: list[str] = []
    for raw in phases:
        canonical = normalize_growth_phase(raw)
        if canonical is None:
            continue
        if canonical not in counts:
            order.append(canonical)
        counts[canonical] += 1
    if not counts:
        return None
    best = max(counts[p] for p in order)
    for phase in order:
        if counts[phase] == best:
            return phase
    return None
