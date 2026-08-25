"""
AUT-1367 R2: Komposition trifft Rezept-Volumen-Verhältnis.

Parameter c_A = 1.5 × c_B are test parameters (AUT-1365 severity example),
not claimed operating measurements.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sensors.dose_calculators.active.salt_calculator_assist import (
    calculate_ab_dose_expectation,
)
from src.sensors.dose_calculators.active.volume_share import (
    compute_ratio_shares_from_volume,
)
from src.services.logic_engine import LogicEngine


# Test parameters from AUT-1365 severity example (not operating measurements).
_C_B = 2.0
_C_A = 1.5 * _C_B  # 3.0


@pytest.fixture
def engine() -> LogicEngine:
    return LogicEngine(
        logic_repo=MagicMock(),
        actuator_service=MagicMock(),
        websocket_manager=AsyncMock(),
        condition_evaluators=[],
        action_executors=[],
    )


def test_ratio_shares_sum_to_one_and_follow_concentration() -> None:
    shares = compute_ratio_shares_from_volume(
        [
            {"concentration": _C_A, "volume_share": 0.5},
            {"concentration": _C_B, "volume_share": 0.5},
        ]
    )
    assert abs(sum(shares) - 1.0) < 1e-12
    # Special case 1:1 volume → ratio_share_i = c_i / Σc
    assert shares[0] == pytest.approx(_C_A / (_C_A + _C_B))
    assert shares[1] == pytest.approx(_C_B / (_C_A + _C_B))


def test_assist_composition_matches_recipe_volume_ratio() -> None:
    dose_a, dose_b, expected_ec = calculate_ab_dose_expectation(
        current_ec_us_cm=1000.0,
        target_ec_us_cm=1400.0,
        volume_l=20.0,
        concentration_a=_C_A,
        concentration_b=_C_B,
        volume_share_a=0.5,
        volume_share_b=0.5,
    )
    assert dose_a == pytest.approx(dose_b)
    assert dose_a / dose_b == pytest.approx(1.0)
    assert expected_ec == pytest.approx(1400.0)


@pytest.mark.asyncio
async def test_logic_engine_composition_matches_recipe_volume_ratio(engine: LogicEngine) -> None:
    rule = MagicMock()
    rule.rule_name = "EC A/B"
    rule.rule_metadata = {
        "dose_config": {
            "target_value": 1400.0,
            "volume_l": 20.0,
            "components": [
                {"concentration": _C_A, "volume_share": 0.5, "ratio_share": 0.5},
                {"concentration": _C_B, "volume_share": 0.5, "ratio_share": 0.5},
            ],
        }
    }
    actions = [
        {
            "type": "sequence",
            "steps": [
                {"action": {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5}},
                {"action": {"type": "actuator_command", "esp_id": "ESP_B", "gpio": 6}},
            ],
        }
    ]
    result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 1000.0})
    dose_a = result[0]["steps"][0]["action"]["dose_ml"]
    dose_b = result[0]["steps"][1]["action"]["dose_ml"]
    assert dose_a == pytest.approx(dose_b)


@pytest.mark.asyncio
async def test_assist_equals_logic_engine_same_config(engine: LogicEngine) -> None:
    dose_a_assist, dose_b_assist, _ = calculate_ab_dose_expectation(
        current_ec_us_cm=1000.0,
        target_ec_us_cm=1400.0,
        volume_l=20.0,
        concentration_a=_C_A,
        concentration_b=_C_B,
        volume_share_a=0.5,
        volume_share_b=0.5,
    )
    rule = MagicMock()
    rule.rule_name = "EC A/B"
    rule.rule_metadata = {
        "dose_config": {
            "target_value": 1400.0,
            "volume_l": 20.0,
            "components": [
                {"concentration": _C_A, "volume_share": 0.5},
                {"concentration": _C_B, "volume_share": 0.5},
            ],
        }
    }
    actions = [
        {"type": "actuator_command", "esp_id": "ESP_A", "gpio": 5},
        {"type": "actuator_command", "esp_id": "ESP_B", "gpio": 6},
    ]
    result = await engine._compute_chemistry_dose_ml(rule, actions, {"value": 1000.0})
    assert result[0]["dose_ml"] == pytest.approx(dose_a_assist)
    assert result[1]["dose_ml"] == pytest.approx(dose_b_assist)


def test_equal_concentrations_match_legacy_half_share() -> None:
    """c_A == c_B → identical to historical ratio_share 0.5/0.5."""
    dose_a, dose_b, _ = calculate_ab_dose_expectation(
        current_ec_us_cm=1000.0,
        target_ec_us_cm=1400.0,
        volume_l=20.0,
        concentration=4.0,
    )
    assert dose_a == pytest.approx(1000.0)  # 400*20*0.5/4
    assert dose_b == pytest.approx(1000.0)
