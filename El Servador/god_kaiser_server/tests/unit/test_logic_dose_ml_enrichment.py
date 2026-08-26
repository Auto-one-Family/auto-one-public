"""
Unit Tests: AUT-991 AO-2 — Dosier-Semantik dose_ml → duration_seconds

Tests LogicEngine._enrich_actions_with_duration():
- Resolved dose_ml to duration_seconds via flow_rate_ml_s (AO-1 dedicated column)
- Ceiling rounding (ceil, not floor)
- Passthrough for actions without dose_ml
- Skip (failed) when flow_rate_ml_s is None (uncalibrated)
- Skip (failed) when flow_rate_ml_s is 0
- Skip (failed) when ESP not found
- Mixed actions (partial enrichment)
- Minimum duration guard (duration >= 1)
- AO-5 interface contract: _flow_rate_ml_s present in enriched dict

AUT-1111: sequence-step dose_ml enrichment (descends one level into steps[]).
"""

import math
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic_engine import LogicEngine


@pytest.fixture
def engine():
    """Minimal LogicEngine instance for unit testing _enrich_actions_with_duration."""
    logic_repo = MagicMock()
    actuator_service = MagicMock()
    ws_manager = AsyncMock()
    return LogicEngine(
        logic_repo=logic_repo,
        actuator_service=actuator_service,
        websocket_manager=ws_manager,
        condition_evaluators=[],
        action_executors=[],
    )


@pytest.fixture
def mock_session():
    """Simple async session mock — only used as a passthrough to repos."""
    return AsyncMock()


def _make_esp(esp_uuid: uuid.UUID) -> MagicMock:
    """Create a minimal ESPDevice mock with a known UUID."""
    esp = MagicMock()
    esp.id = esp_uuid
    return esp


def _make_actuator(flow_rate: float | None) -> MagicMock:
    """Create a minimal ActuatorConfig mock with flow_rate_ml_s set."""
    act = MagicMock()
    act.flow_rate_ml_s = flow_rate
    return act


class TestDoseMlResolvedToDuration:
    """Test 1: dose_ml=75, flow_rate=2.5 → duration_seconds=30."""

    @pytest.mark.asyncio
    async def test_dose_ml_resolved_to_duration(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_01"
        gpio = 5
        dose_ml = 75.0
        flow_rate = 2.5
        expected_duration = 30  # ceil(75 / 2.5) = 30

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(flow_rate)
        )

        actions = [{"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": dose_ml}]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0]["duration_seconds"] == expected_duration
        assert enriched[0]["_flow_rate_ml_s"] == flow_rate


class TestDoseMlCeilingRounding:
    """Test 2: dose_ml=10, flow_rate=3.0 → duration_seconds=4 (ceil(3.333...))."""

    @pytest.mark.asyncio
    async def test_dose_ml_ceiling_rounding(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_02"
        gpio = 7
        dose_ml = 10.0
        flow_rate = 3.0
        expected_duration = math.ceil(dose_ml / flow_rate)  # ceil(3.333) = 4

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(flow_rate)
        )

        actions = [{"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": dose_ml}]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0]["duration_seconds"] == expected_duration
        assert expected_duration == 4


class TestDurationSecondsPassthrough:
    """Test 3: Action without dose_ml (with duration_seconds=20) passes through unchanged."""

    @pytest.mark.asyncio
    async def test_duration_seconds_passthrough(self, engine, mock_session):
        action = {
            "type": "actuator_command",
            "esp_id": "ESP_DOSE_03",
            "gpio": 10,
            "duration_seconds": 20,
            "command": "ON",
        }
        actions = [action]

        mock_esp_repo = AsyncMock()
        mock_actuator_repo = AsyncMock()

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0] is action  # unchanged reference
        assert enriched[0]["duration_seconds"] == 20
        # Repos should not have been called (no dose_ml in action)
        mock_esp_repo.get_by_device_id.assert_not_called()
        mock_actuator_repo.get_by_esp_and_gpio.assert_not_called()


class TestDoseMlFlowRateNoneSkip:
    """Test 4: flow_rate_ml_s=None and no duration → action in failed (AUT-1384)."""

    @pytest.mark.asyncio
    async def test_dose_ml_flow_rate_none_skip(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_04"
        gpio = 12
        action = {"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": 50.0}
        actions = [action]

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(None)  # flow_rate_ml_s is None
        )

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert enriched == []
        assert len(failed) == 1
        assert failed[0] is action


class TestDoseMlFlowRateNoneDurationFallback:
    """AUT-1384: flow_rate missing + duration_seconds>0 → pass through duration-driven."""

    @pytest.mark.asyncio
    async def test_dose_ml_flow_rate_none_uses_duration_fallback(
        self, engine, mock_session
    ):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_04B"
        gpio = 12
        action = {
            "type": "actuator_command",
            "esp_id": esp_id_str,
            "gpio": gpio,
            "dose_ml": 50.0,
            "duration_seconds": 8,
            "command": "ON",
        }
        actions = [action]

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))
        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(None)
        )

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch(
                "src.services.logic_engine.ActuatorRepository",
                return_value=mock_actuator_repo,
            ),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(
                actions, session=mock_session
            )

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0]["duration_seconds"] == 8.0
        assert enriched[0]["dose_ml"] == 50.0
        assert "_flow_rate_ml_s" not in enriched[0]


class TestDoseMlFlowRateZeroSkip:
    """Test 5: flow_rate_ml_s=0 and no duration → action in failed."""

    @pytest.mark.asyncio
    async def test_dose_ml_flow_rate_zero_skip(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_05"
        gpio = 14
        action = {"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": 30.0}
        actions = [action]

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(0.0)  # flow_rate_ml_s is 0
        )

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert enriched == []
        assert len(failed) == 1
        assert failed[0] is action


class TestDoseMlEspNotFoundSkip:
    """Test 6: ESP not found → action in failed, no crash during cache lookup."""

    @pytest.mark.asyncio
    async def test_dose_ml_esp_not_found_skip(self, engine, mock_session):
        esp_id_str = "ESP_DOSE_NOTFOUND"
        action = {
            "type": "actuator_command",
            "esp_id": esp_id_str,
            "gpio": 5,
            "dose_ml": 25.0,
        }
        actions = [action]

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=None)  # ESP not found

        mock_actuator_repo = AsyncMock()

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert enriched == []
        assert len(failed) == 1
        assert failed[0] is action
        # Actuator repo should not be called since ESP UUID is None
        mock_actuator_repo.get_by_esp_and_gpio.assert_not_called()


class TestMixedActionsPartialEnrich:
    """Test 7: One action with dose_ml (resolved), one without → both in enriched, failed=[]."""

    @pytest.mark.asyncio
    async def test_mixed_actions_partial_enrich(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_MIX"
        dose_action = {
            "type": "actuator_command",
            "esp_id": esp_id_str,
            "gpio": 5,
            "dose_ml": 60.0,
            "command": "ON",
        }
        passthrough_action = {
            "type": "actuator_command",
            "esp_id": esp_id_str,
            "gpio": 6,
            "duration_seconds": 15,
            "command": "ON",
        }
        actions = [dose_action, passthrough_action]

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(2.0)  # 60 / 2.0 = 30s
        )

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 2
        # First action should have duration_seconds resolved
        enriched_dose = next(a for a in enriched if a.get("gpio") == 5)
        assert enriched_dose["duration_seconds"] == 30
        assert "_flow_rate_ml_s" in enriched_dose
        # Second action should be unchanged (passthrough)
        enriched_pass = next(a for a in enriched if a.get("gpio") == 6)
        assert enriched_pass["duration_seconds"] == 15
        assert "_flow_rate_ml_s" not in enriched_pass


class TestMinimumDurationGuard:
    """Test 8: dose_ml=0.001, flow_rate=1.0 → duration_seconds >= 1 (never 0)."""

    @pytest.mark.asyncio
    async def test_minimum_duration_guard(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_MIN"
        gpio = 3
        dose_ml = 0.001  # ceil(0.001 / 1.0) = 1 → max(1, 1) = 1
        flow_rate = 1.0

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(flow_rate)
        )

        actions = [{"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": dose_ml}]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0]["duration_seconds"] >= 1


class TestFlowRateSnapshotInEnriched:
    """Test 9: AO-5 interface contract — enriched action contains _flow_rate_ml_s key."""

    @pytest.mark.asyncio
    async def test_flow_rate_snapshot_in_enriched(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_AO5"
        gpio = 9
        dose_ml = 100.0
        flow_rate = 5.0  # 100 / 5 = 20s

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(flow_rate)
        )

        actions = [{"type": "actuator_command", "esp_id": esp_id_str, "gpio": gpio, "dose_ml": dose_ml}]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert "_flow_rate_ml_s" in enriched[0]
        assert enriched[0]["_flow_rate_ml_s"] == flow_rate
        assert enriched[0]["duration_seconds"] == 20


class TestDoseMlOverridesExistingDuration:
    """AUT-1379 W1: when both dose_ml and duration_seconds are set, dose wins."""

    @pytest.mark.asyncio
    async def test_dose_ml_overwrites_conflicting_duration(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_DOSE_BOTH"
        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))
        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(1.5)
        )
        actions = [
            {
                "type": "actuator_command",
                "esp_id": esp_id_str,
                "gpio": 12,
                "dose_ml": 9.0,
                "duration_seconds": 5,  # would imply ≈7.5 ml — must be overwritten
                "command": "ON",
            }
        ]
        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch(
                "src.services.logic_engine.ActuatorRepository",
                return_value=mock_actuator_repo,
            ),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(
                actions, session=mock_session
            )
        assert failed == []
        assert enriched[0]["duration_seconds"] == 6  # ceil(9/1.5)
        assert enriched[0]["dose_ml"] == 9.0


class TestSequenceStepDoseMlResolved:
    """Test 10 (AUT-1111): a sequence step's dose_ml is resolved to duration_seconds."""

    @pytest.mark.asyncio
    async def test_sequence_step_dose_ml_resolved(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_SEQ_01"
        dose_ml = 75.0
        flow_rate = 2.5
        expected_duration = 30  # ceil(75 / 2.5) = 30

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(flow_rate)
        )

        sequence_action = {
            "type": "sequence",
            "sequence_id": "ec_raise_ab",
            "steps": [
                {
                    "name": "Pump A",
                    "action": {
                        "type": "actuator_command",
                        "esp_id": esp_id_str,
                        "gpio": 5,
                        "dose_ml": dose_ml,
                    },
                },
                {"delay_seconds": 10},
            ],
        }
        actions = [sequence_action]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        step_action = enriched[0]["steps"][0]["action"]
        assert step_action["duration_seconds"] == expected_duration
        assert step_action["_flow_rate_ml_s"] == flow_rate
        # Delay-only step and top-level sequence action unchanged aside from steps
        assert enriched[0]["steps"][1] == {"delay_seconds": 10}
        assert enriched[0]["sequence_id"] == "ec_raise_ab"
        # Original action dict must not be mutated in place (rule.actions stays a template)
        assert sequence_action["steps"][0]["action"].get("duration_seconds") is None


class TestSequenceStepDoseMlFailSkipsWholeSequence:
    """Test 11 (AUT-1111): unresolved step dose_ml fails the whole sequence action."""

    @pytest.mark.asyncio
    async def test_sequence_step_dose_ml_fail_skips_whole_sequence(self, engine, mock_session):
        esp_uuid = uuid.uuid4()
        esp_id_str = "ESP_SEQ_02"

        mock_esp_repo = AsyncMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=_make_esp(esp_uuid))

        mock_actuator_repo = AsyncMock()
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(
            return_value=_make_actuator(None)  # flow_rate_ml_s uncalibrated
        )

        sequence_action = {
            "type": "sequence",
            "steps": [
                {
                    "action": {
                        "type": "actuator_command",
                        "esp_id": esp_id_str,
                        "gpio": 6,
                        "dose_ml": 40.0,
                    }
                }
            ],
        }
        actions = [sequence_action]

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert enriched == []
        assert len(failed) == 1
        assert failed[0] is sequence_action


class TestSequenceWithoutDoseMlPassthrough:
    """Test 12 (AUT-1111): sequence steps without dose_ml pass through unchanged."""

    @pytest.mark.asyncio
    async def test_sequence_without_dose_ml_passthrough(self, engine, mock_session):
        sequence_action = {
            "type": "sequence",
            "steps": [
                {"action": {"type": "actuator_command", "esp_id": "ESP_SEQ_03", "gpio": 7, "command": "ON"}},
                {"delay_seconds": 5},
            ],
        }
        actions = [sequence_action]

        mock_esp_repo = AsyncMock()
        mock_actuator_repo = AsyncMock()

        with (
            patch("src.services.logic_engine.ESPRepository", return_value=mock_esp_repo),
            patch("src.services.logic_engine.ActuatorRepository", return_value=mock_actuator_repo),
        ):
            enriched, failed = await engine._enrich_actions_with_duration(actions, session=mock_session)

        assert failed == []
        assert len(enriched) == 1
        assert enriched[0]["steps"][0]["action"]["command"] == "ON"
        assert "duration_seconds" not in enriched[0]["steps"][0]["action"]
        mock_esp_repo.get_by_device_id.assert_not_called()
        mock_actuator_repo.get_by_esp_and_gpio.assert_not_called()
