"""
Explicit formula_id → callable registry (AUT-1394 / M-2).

Mirrors dose_calculators: direct imports only — no pkgutil/importlib scan.
Adding a formula = new module under active/ + one line here.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .active.difference_delta_over_event import difference_delta_over_event

FormulaFn = Callable[..., Optional[float]]

# Explicit map — both wave-1 ids resolve to the same pure function.
FORMULA_REGISTRY: Dict[str, FormulaFn] = {
    "difference": difference_delta_over_event,
    "delta_over_event": difference_delta_over_event,
}


def get_formula(formula_id: str) -> Optional[FormulaFn]:
    """Return registered formula callable, or None if unknown."""
    return FORMULA_REGISTRY.get(formula_id)


def list_formula_ids() -> list[str]:
    """Stable list of registered formula ids (for tests / introspection)."""
    return sorted(FORMULA_REGISTRY.keys())
