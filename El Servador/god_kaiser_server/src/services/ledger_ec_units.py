"""
Ledger EC unit adapter (AUT-1350 / U1).

Ledger DB columns (``ec_*_ms_cm``, ``nutrient_solution_batches``) store **mS/cm**.
Operational fertigation (Plan / Assist / Logic / FE targets) uses **µS/cm** SSOT.

ALL ×1000 / ÷1000 between these worlds MUST go through this module — one boundary.
Do not inline scale factors in Assist, dose calculators, or FE.
"""

from __future__ import annotations

from typing import Optional

# Exact factor: 1 mS/cm = 1000 µS/cm
US_PER_MS = 1000.0


def ledger_ms_cm_to_us_cm(ms_cm: float) -> float:
    """Read boundary: Ledger mS/cm → operational µS/cm."""
    return float(ms_cm) * US_PER_MS


def us_cm_to_ledger_ms_cm(us_cm: float) -> float:
    """Write boundary: operational µS/cm → Ledger mS/cm."""
    return float(us_cm) / US_PER_MS


def optional_ledger_ms_cm_to_us_cm(ms_cm: Optional[float]) -> Optional[float]:
    """Nullable read helper for Assist / composition ledger reads."""
    if ms_cm is None:
        return None
    return ledger_ms_cm_to_us_cm(ms_cm)


def optional_us_cm_to_ledger_ms_cm(us_cm: Optional[float]) -> Optional[float]:
    """Nullable write helper when persisting operational EC into Ledger."""
    if us_cm is None:
        return None
    return us_cm_to_ledger_ms_cm(us_cm)
