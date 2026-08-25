"""AUT-880: leading-edge + trailing coalescing in ``send_config_coalesced``.

Proves the three invariants from the verify-plan PASS comment:
(a) single call  -> exactly 1 leading push, 0 trailing
(b) burst        -> exactly 1 leading + at most 1 trailing push (never N immediate)
(c) terminalization parity: all callers share one correlation id and every
    published push carries that id (so the same set of correlations resolves as today)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.services.esp_service as esp_service_module
from src.services.esp_service import ESPService

_STATE_DICTS = (
    esp_service_module._pending_config_pushes,
    esp_service_module._pending_config_payloads,
    esp_service_module._pending_config_reasons,
    esp_service_module._pending_config_generations,
    esp_service_module._pending_config_fingerprints,
    esp_service_module._pending_config_handles,
)


@pytest.fixture(autouse=True)
def _clear_coalesce_state():
    for d in _STATE_DICTS:
        d.clear()
    yield
    for d in _STATE_DICTS:
        d.clear()


def _make_service() -> ESPService:
    esp_repo = MagicMock()
    esp_repo.session = AsyncMock()
    return ESPService(esp_repo=esp_repo, publisher=MagicMock())


def _session_maker_factory() -> MagicMock:
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


async def _drain(device_id: str) -> None:
    task = esp_service_module._pending_config_pushes.get(device_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout=5)


@pytest.mark.asyncio
async def test_single_config_pushes_immediately_without_trailing():
    device_id = "ESP_LEAD01"
    publishes: list[tuple[float, str, str]] = []

    async def _record(**kwargs):
        publishes.append(
            (time.perf_counter(), kwargs["reason_code"], kwargs["forced_correlation_id"])
        )
        return {"success": True, "sent": True}

    service = _make_service()
    with (
        patch.object(ESPService, "send_config", AsyncMock(side_effect=_record)),
        patch("src.services.esp_service.get_session_maker", _session_maker_factory()),
        patch("src.services.esp_service.CONFIG_PUSH_COALESCE_SECONDS", 0.3),
    ):
        t0 = time.perf_counter()
        result = await service.send_config_coalesced(
            device_id=device_id,
            config={"sensors": [{"gpio": 4}]},
            reason_code="sensor_config_change",
        )
        # Leading must fire long before the window (0.3s) closes.
        await asyncio.sleep(0.05)
        leading_count_midwindow = len(publishes)
        await _drain(device_id)

    # (a) exactly 1 leading, 0 trailing
    assert leading_count_midwindow == 1
    assert len(publishes) == 1
    leading_latency_ms = (publishes[0][0] - t0) * 1000.0
    assert leading_latency_ms < 100.0  # immediate, not window-bound (was ~5001 ms)
    # leading carries the raw reason (no coalesced: prefix) for log/measurement counting
    assert publishes[0][1] == "sensor_config_change"
    assert not publishes[0][1].startswith("coalesced:")
    # (c) published correlation id == the one returned to the caller
    assert publishes[0][2] == result["correlation_id"]


@pytest.mark.asyncio
async def test_burst_one_leading_at_most_one_trailing_shared_correlation():
    device_id = "ESP_BURST1"
    publishes: list[tuple[str, str]] = []

    async def _record(**kwargs):
        publishes.append((kwargs["reason_code"], kwargs["forced_correlation_id"]))
        return {"success": True, "sent": True}

    service = _make_service()
    caller_correlations: set[str] = set()
    with (
        patch.object(ESPService, "send_config", AsyncMock(side_effect=_record)),
        patch("src.services.esp_service.get_session_maker", _session_maker_factory()),
        patch("src.services.esp_service.CONFIG_PUSH_COALESCE_SECONDS", 0.3),
    ):
        for i in range(8):
            res = await service.send_config_coalesced(
                device_id=device_id,
                config={"sensors": [{"gpio": i}]},
                reason_code="sensor_config_change",
            )
            caller_correlations.add(res["correlation_id"])
        await _drain(device_id)

    leading = [r for r, _ in publishes if not r.startswith("coalesced:")]
    trailing = [r for r, _ in publishes if r.startswith("coalesced:")]

    # (b) exactly 1 leading + at most 1 trailing -> never N immediate pushes
    assert len(leading) == 1
    assert len(trailing) <= 1
    assert len(publishes) <= 2
    # (c) all 8 callers share one correlation id, and every push carries that id
    assert len(caller_correlations) == 1
    published_correlations = {cid for _, cid in publishes}
    assert published_correlations == caller_correlations
