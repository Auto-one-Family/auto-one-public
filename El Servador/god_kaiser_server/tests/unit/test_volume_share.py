"""AUT-1366 R1 / AUT-1367 R2: volume_share SSOT + ratio_share derivation."""

from __future__ import annotations

import pytest

from src.sensors.dose_calculators.active.volume_share import (
    compute_ratio_shares_from_volume,
    resolve_volume_shares,
)


def test_resolve_volume_shares_explicit_one_to_one() -> None:
    shares = resolve_volume_shares(
        [
            {"concentration": 1.5, "volume_share": 0.5},
            {"concentration": 1.0, "volume_share": 0.5},
        ]
    )
    assert shares == [0.5, 0.5]
    assert abs(sum(shares) - 1.0) < 1e-9


def test_resolve_volume_shares_explicit_unequal() -> None:
    shares = resolve_volume_shares(
        [
            {"volume_share": 0.25},
            {"volume_share": 0.75},
        ]
    )
    assert shares == [0.25, 0.75]


def test_resolve_volume_shares_missing_falls_back_to_equal() -> None:
    """Fehlt volume_share ⇒ heutiges Verhalten (gleiche shares / 1:1)."""
    shares = resolve_volume_shares(
        [
            {"concentration": 4.0, "ratio_share": 0.5},
            {"concentration": 8.0, "ratio_share": 0.5},
        ]
    )
    assert shares == [0.5, 0.5]


def test_resolve_volume_shares_partial_missing_falls_back_to_equal() -> None:
    shares = resolve_volume_shares(
        [
            {"volume_share": 0.5},
            {"concentration": 1.0},  # missing volume_share
        ]
    )
    assert shares == [0.5, 0.5]


def test_resolve_volume_shares_null_or_invalid_falls_back() -> None:
    assert resolve_volume_shares([{"volume_share": None}, {"volume_share": 0.5}]) == [
        0.5,
        0.5,
    ]
    assert resolve_volume_shares([{"volume_share": 0}, {"volume_share": 0.5}]) == [
        0.5,
        0.5,
    ]
    assert resolve_volume_shares([{"volume_share": "x"}, {"volume_share": 0.5}]) == [
        0.5,
        0.5,
    ]


def test_resolve_volume_shares_empty() -> None:
    assert resolve_volume_shares([]) == []


def test_resolve_volume_shares_three_channel_equal_fallback() -> None:
    shares = resolve_volume_shares([{}, {}, {}])
    assert len(shares) == 3
    assert all(abs(s - 1.0 / 3.0) < 1e-12 for s in shares)


def test_compute_ratio_shares_one_to_one_volume_unequal_c() -> None:
    ratios = compute_ratio_shares_from_volume(
        [
            {"concentration": 3.0, "volume_share": 0.5},
            {"concentration": 2.0, "volume_share": 0.5},
        ]
    )
    assert ratios[0] == pytest.approx(3.0 / 5.0)
    assert ratios[1] == pytest.approx(2.0 / 5.0)
    assert abs(sum(ratios) - 1.0) < 1e-12


def test_compute_ratio_shares_equal_c_is_half() -> None:
    ratios = compute_ratio_shares_from_volume(
        [{"concentration": 4.0}, {"concentration": 4.0}]
    )
    assert ratios == [0.5, 0.5]
