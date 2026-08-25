"""
Unit Tests: AUT-1116 (S6, DP4) — non-blocking deadband warning between paired rules

_check_paired_rule_deadband() / _extract_hysteresis_thresholds() back the
warnings-field mechanism on LogicRuleResponse: overlapping thresholds between
two rules linked via rule_metadata.paired_rule_id produce a warning, NEVER a
raise/reject — the Logic Engine (and rule creation/update) must keep working.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.logic_service import LogicService


def _hysteresis_condition(**kwargs):
    condition = {"type": "hysteresis", "esp_id": "ESP_001", "gpio": 4, "sensor_type": "ec"}
    condition.update(kwargs)
    return condition


class TestExtractHysteresisThresholds:
    """Pure helper: pulls activate_below/activate_above out of (possibly compound)
    condition structures, mirroring _flatten_sensor_conditions()'s descent pattern."""

    def test_flat_hysteresis_condition(self):
        conditions = [_hysteresis_condition(activate_below=1.6, deactivate_above=1.7)]
        result = LogicService._extract_hysteresis_thresholds(conditions)
        assert result == {"activate_below": 1.6}

    def test_compound_and_condition(self):
        conditions = {
            "logic": "AND",
            "conditions": [
                {"type": "time_window", "start_hour": 0, "end_hour": 23},
                _hysteresis_condition(activate_above=2.0, deactivate_below=1.9),
            ],
        }
        result = LogicService._extract_hysteresis_thresholds(conditions)
        assert result == {"activate_above": 2.0}

    def test_no_hysteresis_condition_returns_empty(self):
        conditions = [
            {"type": "sensor", "esp_id": "ESP_001", "gpio": 4, "operator": ">", "value": 2.0}
        ]
        assert LogicService._extract_hysteresis_thresholds(conditions) == {}


class TestCheckPairedRuleDeadband:
    """DP4: warns (never raises) on overlapping thresholds between paired rules."""

    def _service(self):
        return LogicService(logic_repo=AsyncMock())

    @pytest.mark.asyncio
    async def test_no_paired_rule_id_returns_no_warnings(self):
        service = self._service()
        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.6)],
            rule_metadata={},
        )
        assert warnings == []
        service.logic_repo.get_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_overlapping_thresholds_produce_warning(self):
        """EC-Anheben (activate_below=1.8) vs EC-Senken (activate_above=1.6):
        raise-threshold >= lower-threshold → no safety gap, must warn."""
        service = self._service()
        paired_id = uuid.uuid4()
        paired_rule = MagicMock()
        paired_rule.id = paired_id
        paired_rule.name = "EC Senken"
        paired_rule.conditions = [_hysteresis_condition(activate_above=1.6, deactivate_below=1.5)]
        service.logic_repo.get_by_id = AsyncMock(return_value=paired_rule)

        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.8, deactivate_above=1.9)],
            rule_metadata={"paired_rule_id": str(paired_id)},
        )

        assert len(warnings) == 1
        assert "Totband" in warnings[0]
        assert "EC Senken" in warnings[0]

    @pytest.mark.asyncio
    async def test_correct_deadband_produces_no_warning(self):
        """EC-Anheben (activate_below=1.6) vs EC-Senken (activate_above=1.9):
        clear gap between 1.6 and 1.9 → no warning (control test)."""
        service = self._service()
        paired_id = uuid.uuid4()
        paired_rule = MagicMock()
        paired_rule.id = paired_id
        paired_rule.name = "EC Senken"
        paired_rule.conditions = [_hysteresis_condition(activate_above=1.9, deactivate_below=1.8)]
        service.logic_repo.get_by_id = AsyncMock(return_value=paired_rule)

        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.6, deactivate_above=1.7)],
            rule_metadata={"paired_rule_id": str(paired_id)},
        )

        assert warnings == []

    @pytest.mark.asyncio
    async def test_paired_rule_not_found_fails_open(self):
        """Dangling paired_rule_id (e.g. deleted rule) must never raise — just no warning."""
        service = self._service()
        service.logic_repo.get_by_id = AsyncMock(return_value=None)

        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.8)],
            rule_metadata={"paired_rule_id": str(uuid.uuid4())},
        )

        assert warnings == []

    @pytest.mark.asyncio
    async def test_malformed_paired_rule_id_fails_open(self):
        """Not-a-UUID paired_rule_id must never raise — fail-open, WARNING-log only."""
        service = self._service()

        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.8)],
            rule_metadata={"paired_rule_id": "not-a-uuid"},
        )

        assert warnings == []

    @pytest.mark.asyncio
    async def test_self_referencing_paired_rule_id_skipped(self):
        """A rule cannot be paired with itself — self_rule_id guard prevents a
        spurious self-comparison warning."""
        service = self._service()
        rule_id = uuid.uuid4()

        warnings = await service._check_paired_rule_deadband(
            conditions=[_hysteresis_condition(activate_below=1.8)],
            rule_metadata={"paired_rule_id": str(rule_id)},
            self_rule_id=rule_id,
        )

        assert warnings == []
        service.logic_repo.get_by_id.assert_not_awaited()
