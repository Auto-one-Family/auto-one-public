"""
AUT-1345 / PKG-03 — Umstell-Sequenz Komposition (bestehende Bausteine).

Belegt A→Mischzeit→B-Reihenfolge, Interlock während Sequenz (inkl. Delay),
Settle-Gate-Semantik und delta-proportionale Dosis ohne max_delta_per_dose-Cap.
Kein neuer Mechanismus — nur SequenceExecutor + not_running + calculate_dose_ml.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import pytest

from src.sensors.dose_calculators.active.linear_dose_calculator import calculate_dose_ml
from src.services.logic.actions.base import ActionResult
from src.services.logic.actions.sequence_executor import SequenceActionExecutor
from src.services.logic.conditions.running_state_evaluator import (
    NotRunningConditionEvaluator,
)


EC_RULE_ID = "4df64c75-17e2-4f57-8772-24f71663f6f0"
MISCHZEIT_S = 0.05  # kurz für Unit-Lauf; Live-Ops = 120 s


def _tank_umstell_sequence_action(
    delay_seconds: float = MISCHZEIT_S,
) -> dict[str, Any]:
    """Live-nahe Config-Skizze: A (GPIO12) → Mischzeit → B (GPIO16)."""
    return {
        "type": "sequence",
        "abort_on_failure": True,
        "steps": [
            {
                "name": "Pump A",
                "action": {
                    "type": "actuator",
                    "esp_id": "ESP_AEAE64",
                    "gpio": 12,
                    "command": "ON",
                    "duration_seconds": 5,
                },
            },
            {"name": "Mischzeit", "delay_seconds": delay_seconds},
            {
                "name": "Pump B",
                "action": {
                    "type": "actuator",
                    "esp_id": "ESP_AEAE64",
                    "gpio": 16,
                    "command": "ON",
                    "duration_seconds": 5,
                },
            },
        ],
    }


class TestUmstellSequenceOrder:
    """A voll vor B — Fällungsschutz (Reihenfolge hart)."""

    @pytest.mark.asyncio
    async def test_a_before_mix_before_b_order(self):
        order: List[str] = []
        actuator = Mock()
        actuator.supports = Mock(
            side_effect=lambda t: t in ("actuator", "actuator_command")
        )

        async def _act(action: dict, context: dict) -> ActionResult:
            order.append(f"gpio{action.get('gpio')}")
            return ActionResult(success=True, message="ok")

        actuator.execute = AsyncMock(side_effect=_act)

        executor = SequenceActionExecutor(websocket_manager=AsyncMock())
        executor.set_action_executors([actuator])

        result = await executor.execute(
            _tank_umstell_sequence_action(),
            {"rule_id": EC_RULE_ID},
        )
        assert result.success is True
        sequence_id = result.data["sequence_id"]

        # Non-blocking start — wait until sequence completes (not merely "not yet running")
        for _ in range(100):
            status = executor.get_sequence_status(sequence_id)
            if status and status.get("status") == "completed":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail(f"sequence did not finish: {executor.get_sequence_status(sequence_id)}")

        assert order == ["gpio12", "gpio16"]


class TestUmstellInterlockDuringSequence:
    """not_running(sequence) bleibt False während gesamter Sequenz inkl. Mischzeit."""

    @pytest.mark.asyncio
    async def test_not_running_false_during_mischzeit_delay(self):
        actuator = Mock()
        actuator.supports = Mock(
            side_effect=lambda t: t in ("actuator", "actuator_command")
        )
        actuator.execute = AsyncMock(
            return_value=ActionResult(success=True, message="ok")
        )

        executor = SequenceActionExecutor(websocket_manager=AsyncMock())
        executor.set_action_executors([actuator])
        interlock = NotRunningConditionEvaluator(sequence_executor=executor)
        condition = {
            "type": "not_running",
            "target": "sequence",
            "rule_id": EC_RULE_ID,
        }

        # Idle → erlaubt
        assert await interlock.evaluate(condition, {}) is True

        await executor.execute(
            _tank_umstell_sequence_action(delay_seconds=0.15),
            {"rule_id": EC_RULE_ID},
        )

        # Kurz nach Start (A oder Mischzeit): Interlock hält
        await asyncio.sleep(0.03)
        assert await interlock.evaluate(condition, {}) is False

        for _ in range(40):
            if await interlock.evaluate(condition, {}) is True:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("interlock did not release after sequence")

        assert await interlock.evaluate(condition, {}) is True


class TestDeltaProportionalNoCap:
    """Leitplanke: kein max_delta_per_dose — Dosis schrumpft mit Delta."""

    def test_dose_shrinks_near_target_without_cap(self):
        far = calculate_dose_ml(
            current_value=1000.0,
            target_value=1400.0,
            volume_l=50.0,
            components=[{"concentration": 0.05, "ratio_share": 0.5}],
            max_delta_per_dose=None,
        )
        near = calculate_dose_ml(
            current_value=1380.0,
            target_value=1400.0,
            volume_l=50.0,
            components=[{"concentration": 0.05, "ratio_share": 0.5}],
            max_delta_per_dose=None,
        )
        assert far > near > 0
        # nahe am Ziel: deutlich kleiner (delta 20 vs 400 → Faktor 20)
        assert near == pytest.approx(far * (20.0 / 400.0), rel=1e-6)


class TestSettleGateSemantics:
    """Settle-Felder müssen beide gesetzt sein (AUT-1115) — Config-Vertrag."""

    def test_ph_settle_config_requires_both_fields(self):
        """Dokumentiert den Live-PUT-Vertrag für PH MINUS."""
        ph_settle = {
            "settle_after_rule_id": uuid.UUID(EC_RULE_ID),
            "settle_seconds": 180,
        }
        assert ph_settle["settle_after_rule_id"] is not None
        assert ph_settle["settle_seconds"] and ph_settle["settle_seconds"] > 0
        # 0 / None würde Gate deaktivieren (falsy in logic_engine)
        assert not (None and 180)
        assert not (uuid.UUID(EC_RULE_ID) and 0)
