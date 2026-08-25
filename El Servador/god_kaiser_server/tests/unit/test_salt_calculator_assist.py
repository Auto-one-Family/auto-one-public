"""
Unit Tests: AUT-1343 / AUT-1404 — Salt calculator assist.

Direction gate before motor; dilution when EC_ist > EC_ziel; no dosing.
"""

import pytest

from src.sensors.dose_calculators.active.linear_dose_calculator import calculate_dose_ml
from src.sensors.dose_calculators.active.salt_calculator_assist import (
    DEFAULT_EC_WASSER_US_CM,
    calculate_ab_dose_expectation,
    calculate_dilution_water_l,
    compute_salt_calculator_assist,
    dilute_ec_us_cm,
)


class TestDilution:
    def test_dilution_volume_weighted(self) -> None:
        # (10 L @ 1400 + 10 L @ 488) / 20 = 944
        result = dilute_ec_us_cm(
            prior_ec_us_cm=1400.0,
            prior_volume_l=10.0,
            ec_wasser_us_cm=488.0,
            volume_zugabe_l=10.0,
        )
        assert result == pytest.approx(944.0)

    def test_dilution_zero_zugabe_unchanged(self) -> None:
        result = dilute_ec_us_cm(
            prior_ec_us_cm=1400.0,
            prior_volume_l=20.0,
            ec_wasser_us_cm=488.0,
            volume_zugabe_l=0.0,
        )
        assert result == pytest.approx(1400.0)

    def test_legacy_constant_still_defined_for_explicit_callers(self) -> None:
        # AUT-1381: constant must NOT be a silent runtime default.
        assert DEFAULT_EC_WASSER_US_CM == pytest.approx(488.0)

    def test_dilution_without_ec_wasser_raises(self) -> None:
        with pytest.raises(ValueError, match="Frischwasser-EC nicht konfiguriert"):
            compute_salt_calculator_assist(
                current_ec_us_cm=1400.0,
                target_ec_us_cm=1500.0,
                volume_alt_l=10.0,
                volume_zugabe_l=5.0,
                concentration=2.0,
            )


class TestAbOneToOne:
    def test_ab_doses_equal_one_to_one(self) -> None:
        dose_a, dose_b, expected_ec = calculate_ab_dose_expectation(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1400.0,
            volume_l=20.0,
            concentration=4.0,
        )
        assert dose_a == pytest.approx(dose_b)
        assert dose_a == pytest.approx(1000.0)  # 400*20*0.5/4
        assert expected_ec == pytest.approx(1400.0)

    def test_ab_uses_calculate_dose_ml(self) -> None:
        """Assist must call the same formula as AUT-1112 per component."""
        expected_single = calculate_dose_ml(
            current_value=1000.0,
            target_value=1400.0,
            volume_l=20.0,
            components=[{"concentration": 4.0, "ratio_share": 0.5}],
        )
        dose_a, dose_b, _ = calculate_ab_dose_expectation(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1400.0,
            volume_l=20.0,
            concentration=4.0,
        )
        assert dose_a == pytest.approx(expected_single)
        assert dose_b == pytest.approx(expected_single)


class TestComputePipeline:
    def test_dilution_then_dose(self) -> None:
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1400.0,
            target_ec_us_cm=1500.0,
            volume_alt_l=10.0,
            volume_zugabe_l=10.0,
            ec_wasser_us_cm=488.0,
            concentration=2.0,
        )
        assert result["suggestion_kind"] == "dose_up"
        assert result["ec_after_dilution_us_cm"] == pytest.approx(944.0)
        assert result["volume_neu_l"] == pytest.approx(20.0)
        assert result["dose_a_ml"] == pytest.approx(result["dose_b_ml"])
        # delta from 944 → 1500 = 556; each: 556*20*0.5/2 = 2780
        assert result["dose_a_ml"] == pytest.approx(2780.0)
        assert result["expected_ec_us_cm"] == pytest.approx(1500.0)
        assert "dosiert nichts" in result["operator_message"].lower()

    def test_volume_alt_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="volume_alt_l"):
            compute_salt_calculator_assist(
                current_ec_us_cm=1000.0,
                target_ec_us_cm=1200.0,
                volume_alt_l=0.0,
                concentration=1.0,
            )


class TestDirectionGateAut1404:
    def test_ec_above_target_suggests_dilute_not_salt(self) -> None:
        """Regression: EC 1500→1400 must NOT call salt motor."""
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1500.0,
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
            concentration=4.0,
            ec_wasser_us_cm=488.0,
        )
        assert result["suggestion_kind"] == "dilute"
        assert result["dose_a_ml"] == pytest.approx(0.0)
        assert result["dose_b_ml"] == pytest.approx(0.0)
        expected_w = calculate_dilution_water_l(
            volume_l=20.0,
            ec_ist_us_cm=1500.0,
            ec_ziel_us_cm=1400.0,
            ec_fw_us_cm=488.0,
        )
        assert result["fresh_water_suggest_l"] == pytest.approx(expected_w)
        # Bau-Go: expected_ec must NOT be rewritten to target on dilute advice
        assert result["expected_ec_us_cm"] == pytest.approx(1500.0)
        assert "Frischwasser-/Level-Regel" in result["operator_message"]

    def test_within_tolerance_uses_plan_segment_band(self) -> None:
        """D3: Totband is caller-supplied (plan_segment.tolerance), not a magic 20."""
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1405.0,
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
            concentration=4.0,
            ec_wasser_us_cm=488.0,
            ec_tolerance_us_cm=10.0,
        )
        assert result["suggestion_kind"] == "within_tolerance"
        assert result["dose_a_ml"] == pytest.approx(0.0)
        assert result["fresh_water_suggest_l"] is None

    def test_default_tolerance_zero_is_not_magic_band(self) -> None:
        """Without plan_segment tolerance, 1405 vs 1400 is outside band → dilute."""
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1405.0,
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
            concentration=4.0,
            ec_wasser_us_cm=488.0,
        )
        assert result["suggestion_kind"] == "dilute"

    def test_fresh_batch_doses_from_fresh_water_ec(self) -> None:
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1500.0,  # ignored for start when fresh_batch
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
            concentration=4.0,
            ec_wasser_us_cm=488.0,
            fresh_batch=True,
        )
        assert result["suggestion_kind"] == "dose_up"
        assert result["dose_a_ml"] > 0
        assert result["dose_b_ml"] > 0
        assert result["fresh_water_suggest_l"] is None

    def test_above_target_without_fw_ec_unavailable(self) -> None:
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1500.0,
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
            concentration=4.0,
        )
        assert result["suggestion_kind"] == "unavailable"
        assert result["dose_a_ml"] == pytest.approx(0.0)
        assert "Frischwasser-EC" in result["operator_message"]

    def test_dose_up_without_concentration_unavailable(self) -> None:
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1400.0,
            volume_alt_l=20.0,
        )
        assert result["suggestion_kind"] == "unavailable"
        assert result["dose_a_ml"] == pytest.approx(0.0)
        assert "nicht kalibriert" in result["operator_message"].lower()


class TestPerPumpConcentrationAut1355:
    def test_ab_different_concentrations_equal_volume(self) -> None:
        """AUT-1367: unequal c + equal volume_share → equal ml (1:1 volume)."""
        dose_a, dose_b, expected_ec = calculate_ab_dose_expectation(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1400.0,
            volume_l=20.0,
            concentration_a=4.0,
            concentration_b=8.0,
        )
        # ratio_share = c/(c_a+c_b) → A:4/12, B:8/12; dose = 400*20*r/c → equal
        assert dose_a == pytest.approx(dose_b)
        assert dose_a == pytest.approx(400.0 * 20.0 * (4.0 / 12.0) / 4.0)
        assert expected_ec == pytest.approx(1400.0)

    def test_shared_concentration_fallback_unchanged(self) -> None:
        """Legacy single concentration still yields equal A/B (regression)."""
        dose_a, dose_b, _ = calculate_ab_dose_expectation(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1400.0,
            volume_l=20.0,
            concentration=4.0,
        )
        assert dose_a == pytest.approx(dose_b)
        assert dose_a == pytest.approx(1000.0)

    def test_pipeline_reports_concentration_a_b(self) -> None:
        result = compute_salt_calculator_assist(
            current_ec_us_cm=1000.0,
            target_ec_us_cm=1200.0,
            volume_alt_l=10.0,
            concentration_a=2.0,
            concentration_b=4.0,
        )
        assert result["concentration_a"] == pytest.approx(2.0)
        assert result["concentration_b"] == pytest.approx(4.0)
        # 1:1 volume intent → equal ml despite unequal concentration
        assert result["dose_a_ml"] == pytest.approx(result["dose_b_ml"])
