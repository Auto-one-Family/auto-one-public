"""
AUT-1396 [M-3]: Lifecycle measure-binding hooks — observe-only.

Pflicht:
1) Fehlschlagende Mess-Bindung blockiert/verzögert/bricht Sequenz NIE ab.
2) Regel ohne Mess-Bindung → identity attach, zero runtime work.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.logic.actions.base import ActionResult
from src.services.logic.actions.sequence_executor import (
    SequenceActionExecutor,
    SequenceStatus,
)
from src.services.logic.measure_binding_hooks import (
    MEASURE_BINDING_RESULTS_KEY,
    MEASURE_BINDING_RUNTIME_KEY,
    MEASURE_BINDINGS_ACTION_KEY,
    attach_measure_bindings_to_sequences,
    init_measure_binding_runtime,
    run_measure_binding_hook,
)
from src.services.logic.measure_live_reader import MeasureReadFailure, MeasureReadSuccess


def _binding(**overrides):
    base = {
        "sensor_refs": [{"esp_id": "ESP_12AB34CD", "gpio": 34, "sensor_type": "ec"}],
        "hooks": ["on_start", "on_complete"],
        "formula_id": "difference",
        "formula_params": {},
        "output_target": "execution_metadata",
    }
    base.update(overrides)
    return base


def test_attach_without_bindings_returns_same_list_identity():
    actions = [{"type": "sequence", "steps": [{"delay_seconds": 0.01}]}]
    out = attach_measure_bindings_to_sequences(actions, None)
    assert out is actions
    out2 = attach_measure_bindings_to_sequences(actions, {})
    assert out2 is actions
    out3 = attach_measure_bindings_to_sequences(actions, {"dose_config": {"target_value": 1.0}})
    assert out3 is actions


def test_attach_copies_bindings_onto_sequence_action_only():
    actions = [
        {"type": "actuator", "esp_id": "ESP_1", "gpio": 1},
        {"type": "sequence", "steps": [{"delay_seconds": 1}]},
    ]
    out = attach_measure_bindings_to_sequences(actions, {"measure_bindings": [_binding()]})
    assert out is not actions
    assert MEASURE_BINDINGS_ACTION_KEY not in out[0]
    assert out[1][MEASURE_BINDINGS_ACTION_KEY][0]["formula_id"] == "difference"
    # Original list untouched
    assert MEASURE_BINDINGS_ACTION_KEY not in actions[1]


@pytest.mark.asyncio
async def test_failing_live_read_marks_failed_does_not_raise():
    meta: dict = {}
    init_measure_binding_runtime(meta, [_binding()])
    session = MagicMock()

    with patch(
        "src.services.logic.measure_binding_hooks.read_live_sensor_for_measure",
        new=AsyncMock(
            return_value=MeasureReadFailure(
                ok=False,
                reason="missing",
                esp_id="ESP_12AB34CD",
                gpio=34,
                sensor_type="ec",
            )
        ),
    ):
        await run_measure_binding_hook(meta, hook="on_start", session=session)
        await run_measure_binding_hook(meta, hook="on_complete", session=session)

    state = meta[MEASURE_BINDING_RUNTIME_KEY]["by_index"]["0"]
    assert state["status"] == "failed"
    assert "fehlt/veraltet" in (state["error"] or "")
    results = meta[MEASURE_BINDING_RESULTS_KEY]
    assert len(results) == 1
    assert results[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_happy_path_difference_formula():
    meta: dict = {}
    init_measure_binding_runtime(meta, [_binding()])
    session = MagicMock()

    values = iter(
        [
            MeasureReadSuccess(
                ok=True,
                value=800.0,
                age_seconds=1.0,
                sensor_type="ec",
                operating_mode="continuous",
                measurement_freshness_hours=None,
            ),
            MeasureReadSuccess(
                ok=True,
                value=1000.0,
                age_seconds=1.0,
                sensor_type="ec",
                operating_mode="continuous",
                measurement_freshness_hours=None,
            ),
        ]
    )

    with patch(
        "src.services.logic.measure_binding_hooks.read_live_sensor_for_measure",
        new=AsyncMock(side_effect=lambda *a, **k: next(values)),
    ):
        await run_measure_binding_hook(meta, hook="on_start", session=session)
        await run_measure_binding_hook(meta, hook="on_complete", session=session)

    state = meta[MEASURE_BINDING_RUNTIME_KEY]["by_index"]["0"]
    assert state["status"] == "ok"
    assert state["derived_value"] == 200.0
    assert meta[MEASURE_BINDING_RESULTS_KEY][0]["derived_value"] == 200.0


async def _wait_sequence(executor: SequenceActionExecutor, sequence_id: str) -> dict:
    for _ in range(100):
        status = executor.get_sequence_status(sequence_id)
        if status and status.get("status") in (
            "completed",
            "failed",
            "cancelled",
            "timeout",
        ):
            return status
        await asyncio.sleep(0.02)
    raise AssertionError(f"sequence {sequence_id} did not finish")


@pytest.mark.asyncio
async def test_sequence_completes_when_measure_binding_fails():
    """Pflicht: fehlschlagende Mess-Bindung bricht Sequenz NIE ab."""
    ws = AsyncMock()
    ws.broadcast = AsyncMock()
    executor = SequenceActionExecutor(websocket_manager=ws)

    action = {
        "type": "sequence",
        "sequence_id": "seq-mb-fail-1",
        "steps": [{"delay_seconds": 0.01}],
        "_measure_bindings": [_binding()],
    }

    async def _session_gen():
        yield MagicMock()

    with (
        patch(
            "src.services.logic.measure_binding_hooks.read_live_sensor_for_measure",
            new=AsyncMock(
                return_value=MeasureReadFailure(
                    ok=False,
                    reason="stale",
                    esp_id="ESP_12AB34CD",
                    gpio=34,
                    sensor_type="ec",
                )
            ),
        ),
        patch(
            "src.db.session.get_session",
            new=_session_gen,
        ),
    ):
        result = await executor.execute(action, {"rule_id": "r1", "rule_name": "t"})
        assert result.success is True
        status = await _wait_sequence(executor, "seq-mb-fail-1")

    assert status["status"] == SequenceStatus.COMPLETED.value
    progress = executor._sequences["seq-mb-fail-1"]
    meta = progress.metadata or {}
    assert meta[MEASURE_BINDING_RESULTS_KEY][0]["status"] == "failed"
    assert "fehlt/veraltet" in (meta[MEASURE_BINDING_RESULTS_KEY][0]["error"] or "")


@pytest.mark.asyncio
async def test_sequence_without_bindings_skips_hook_work():
    """Kein Binding → Fast-path, run_measure_binding_hook wird nicht aufgerufen."""
    ws = AsyncMock()
    ws.broadcast = AsyncMock()
    executor = SequenceActionExecutor(websocket_manager=ws)

    action = {
        "type": "sequence",
        "sequence_id": "seq-mb-none-1",
        "steps": [{"delay_seconds": 0.01}],
    }

    with patch(
        "src.services.logic.measure_binding_hooks.run_measure_binding_hook",
        new=AsyncMock(),
    ) as hook_mock:
        result = await executor.execute(action, {"rule_id": "r1"})
        assert result.success is True
        status = await _wait_sequence(executor, "seq-mb-none-1")
        hook_mock.assert_not_called()

    assert status["status"] == "completed"
    progress = executor._sequences["seq-mb-none-1"]
    assert MEASURE_BINDING_RUNTIME_KEY not in (progress.metadata or {})
