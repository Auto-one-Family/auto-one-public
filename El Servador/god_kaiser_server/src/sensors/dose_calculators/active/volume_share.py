"""
volume_share SSOT + ratio_share derivation (AUT-1366 R1 / AUT-1367 R2).

Intended *volume* share of each stock/channel in a multi-component dose
(e.g. Stock A : Stock B = 1:1 → volume_share 0.5 / 0.5). Stored on
``rule_metadata.dose_config.components[i].volume_share`` — additive JSONB,
no new table.

R2: Assist and LogicEngine share ``compute_ratio_shares_from_volume`` so
EC ``ratio_share`` is derived as:

    ratio_share_i = (volume_share_i × c_i) / Σ_j (volume_share_j × c_j)

``calculate_dose_ml`` stays unchanged — only the origin of ``ratio_share``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def resolve_volume_shares(
    components: Sequence[Mapping[str, Any]],
) -> list[float]:
    """
    Read ``volume_share`` from each component; fallback to equal shares ``1/n``.

    Fallback triggers when:
    - ``components`` is empty → ``[]``
    - any entry lacks a usable ``volume_share`` (missing / None / non-numeric / ≤0)
    - resolved shares do not sum to a positive total

    Equal shares match the implicit 2-channel 1:1 volume intent.
    """
    n = len(components)
    if n == 0:
        return []

    shares: list[float] = []
    for component in components:
        raw = component.get("volume_share")
        if raw is None:
            return _equal_shares(n)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return _equal_shares(n)
        if value <= 0:
            return _equal_shares(n)
        shares.append(value)

    total = sum(shares)
    if total <= 0:
        return _equal_shares(n)
    return shares


def compute_ratio_shares_from_volume(
    components: Sequence[Mapping[str, Any]],
    *,
    concentrations: Optional[Sequence[float]] = None,
) -> list[float]:
    """
    Derive EC ``ratio_share`` values from volume shares × concentrations.

    ``ratio_share_i = (volume_share_i × c_i) / Σ_j (volume_share_j × c_j)``.

    Concentrations come from ``concentrations[i]`` when provided, else from
    ``component[\"concentration\"]``. Missing/non-positive concentration raises
    ``ValueError`` (same contract as ``calculate_dose_ml``).

    Special case equal volume shares → ``ratio_share_i = c_i / Σc``.
    Result always sums to 1.0 when n > 0 (EC contribution split preserved).
    """
    n = len(components)
    if n == 0:
        return []
    if concentrations is not None and len(concentrations) != n:
        raise ValueError(
            f"concentrations length {len(concentrations)} != components length {n}"
        )

    volume_shares = resolve_volume_shares(components)
    concs: list[float] = []
    for i, component in enumerate(components):
        if concentrations is not None:
            raw = concentrations[i]
        else:
            raw = component.get("concentration")
        try:
            conc = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"component concentration must be > 0, got {raw!r}"
            ) from exc
        if conc <= 0:
            raise ValueError(f"component concentration must be > 0, got {conc}")
        concs.append(conc)

    weights = [vs * c for vs, c in zip(volume_shares, concs)]
    total = sum(weights)
    if total <= 0:
        return _equal_shares(n)
    return [w / total for w in weights]


def _equal_shares(n: int) -> list[float]:
    if n <= 0:
        return []
    share = 1.0 / n
    return [share] * n
