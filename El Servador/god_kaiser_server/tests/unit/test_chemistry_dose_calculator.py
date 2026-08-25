"""
Unit Tests: AUT-1112 — Chemistry dose calculator (linear_dose_calculator)

Tests calculate_dose_ml():
- Single component (e.g. pH-Plus/pH-Minus)
- Two components split by ratio_share (e.g. EC stock A+B)
- safety_factor and dilution_value multipliers
- Error cases: volume<=0, no components, missing/non-positive concentration,
  missing current/target value
"""

import pytest

from src.sensors.dose_calculators.active.linear_dose_calculator import calculate_dose_ml


class TestSingleComponentDose:
    def test_single_component_dose(self):
        # delta=2.0, volume=10L, ratio_share=1.0, concentration=5.0 -> 2*10*1/5 = 4.0 ml
        dose = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
        )
        assert dose == pytest.approx(4.0)


class TestTwoComponentDoseSplitByRatioShare:
    def test_two_component_dose_split_by_ratio_share(self):
        # delta=1.0, volume=20L, split 0.5/0.5, concentration=2.0 each
        # each component: 1*20*0.5/2 = 5.0 ml -> total 10.0 ml
        dose = calculate_dose_ml(
            current_value=1.0,
            target_value=2.0,
            volume_l=20.0,
            components=[
                {"concentration": 2.0, "ratio_share": 0.5},
                {"concentration": 2.0, "ratio_share": 0.5},
            ],
        )
        assert dose == pytest.approx(10.0)


class TestDeltaIsAbsolute:
    def test_delta_is_absolute(self):
        # current above target (e.g. pH-Minus direction) -> same magnitude as reverse
        dose_down = calculate_dose_ml(
            current_value=8.0,
            target_value=6.0,
            volume_l=10.0,
            components=[{"concentration": 4.0, "ratio_share": 1.0}],
        )
        dose_up = calculate_dose_ml(
            current_value=6.0,
            target_value=8.0,
            volume_l=10.0,
            components=[{"concentration": 4.0, "ratio_share": 1.0}],
        )
        assert dose_down == pytest.approx(dose_up)


class TestSafetyFactorApplied:
    def test_safety_factor_applied(self):
        base = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
        )
        with_factor = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            safety_factor=0.5,
        )
        assert with_factor == pytest.approx(base * 0.5)


class TestDilutionValueApplied:
    def test_dilution_value_applied(self):
        base = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
        )
        diluted = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            dilution_value=10.0,
        )
        assert diluted == pytest.approx(base * 10.0)


class TestVolumeZeroRaises:
    def test_volume_zero_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=5.0,
                target_value=7.0,
                volume_l=0,
                components=[{"concentration": 5.0, "ratio_share": 1.0}],
            )


class TestNegativeVolumeRaises:
    def test_negative_volume_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=5.0,
                target_value=7.0,
                volume_l=-5.0,
                components=[{"concentration": 5.0, "ratio_share": 1.0}],
            )


class TestEmptyComponentsRaises:
    def test_empty_components_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=5.0,
                target_value=7.0,
                volume_l=10.0,
                components=[],
            )


class TestMissingConcentrationRaises:
    def test_missing_concentration_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=5.0,
                target_value=7.0,
                volume_l=10.0,
                components=[{"ratio_share": 1.0}],
            )


class TestZeroConcentrationRaises:
    def test_zero_concentration_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=5.0,
                target_value=7.0,
                volume_l=10.0,
                components=[{"concentration": 0, "ratio_share": 1.0}],
            )


class TestMissingCurrentValueRaises:
    def test_missing_current_value_raises(self):
        with pytest.raises(ValueError):
            calculate_dose_ml(
                current_value=None,
                target_value=7.0,
                volume_l=10.0,
                components=[{"concentration": 5.0, "ratio_share": 1.0}],
            )


class TestMaxDeltaPerDoseCap:
    """AUT-1118 (S8): max_delta_per_dose caps the value-delta a single dose targets."""

    def test_delta_exceeding_cap_is_clamped(self):
        # Uncapped: delta=2.0 -> 2*10*1/5 = 4.0 ml. Capped at 0.5 -> 0.5*10*1/5 = 1.0 ml.
        capped = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            max_delta_per_dose=0.5,
        )
        assert capped == pytest.approx(1.0)

    def test_delta_under_cap_is_unaffected(self):
        uncapped = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
        )
        with_generous_cap = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            max_delta_per_dose=100.0,
        )
        assert with_generous_cap == pytest.approx(uncapped)

    def test_no_cap_matches_s2_behavior(self):
        """Regression: max_delta_per_dose=None must behave exactly like S2 (no cap param)."""
        s2_dose = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            safety_factor=0.8,
            dilution_value=2.0,
        )
        s8_dose_no_cap = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            safety_factor=0.8,
            dilution_value=2.0,
            max_delta_per_dose=None,
        )
        assert s8_dose_no_cap == pytest.approx(s2_dose)

    def test_cap_applies_per_component_consistently(self):
        # Two-component EC dose (A+B): cap must reduce BOTH components proportionally,
        # not just the total — each component still gets its own concentration/ratio_share.
        capped = calculate_dose_ml(
            current_value=1.0,
            target_value=2.0,
            volume_l=20.0,
            components=[
                {"concentration": 2.0, "ratio_share": 0.5},
                {"concentration": 2.0, "ratio_share": 0.5},
            ],
            max_delta_per_dose=0.2,
        )
        # capped delta=0.2 (< raw delta=1.0): each component 0.2*20*0.5/2 = 1.0 -> total 2.0
        assert capped == pytest.approx(2.0)

    def test_zero_cap_treated_as_no_cap(self):
        """max_delta_per_dose=0 is not a meaningful cap (would zero every dose) —
        treated as unset, matching the None default rather than silently dosing 0."""
        uncapped = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
        )
        with_zero_cap = calculate_dose_ml(
            current_value=5.0,
            target_value=7.0,
            volume_l=10.0,
            components=[{"concentration": 5.0, "ratio_share": 1.0}],
            max_delta_per_dose=0,
        )
        assert with_zero_cap == pytest.approx(uncapped)
