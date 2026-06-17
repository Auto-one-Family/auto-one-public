import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.mqtt.subscriber import Subscriber
from src.services.inbound_inbox_service import InboundInboxService


@pytest.mark.asyncio
async def test_replay_pending_events_marks_delivered(tmp_path):
    inbox = InboundInboxService(file_path=str(tmp_path / "critical-inbound.jsonl"))

    with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.get_instance.return_value = mock_client

        subscriber = Subscriber(max_workers=1)
        subscriber.set_main_loop(asyncio.get_running_loop())
        subscriber._inbound_inbox = inbox

        called = []

        async def handler(topic: str, payload: dict):
            called.append((topic, payload["intent_id"]))
            return True

        subscriber.register_handler("kaiser/god/esp/+/system/intent_outcome", handler)

        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={
                "intent_id": "intent-1",
                "correlation_id": "corr-1",
                "flow": "command",
                "outcome": "accepted",
                "ts": 1735818000,
            },
            correlation_id="corr-1",
            source="replay-test",
        )

        summary = await subscriber.replay_pending_events(limit=10)
        stats = await inbox.stats()
        subscriber.shutdown(wait=False)

    assert summary == {"replayed": 1, "failed": 0, "pending_checked": 1}
    assert stats["acked"] == 1
    assert called == [("kaiser/god/esp/ESP_01/system/intent_outcome", "intent-1")]


@pytest.mark.asyncio
async def test_replay_pending_events_without_handler_marks_attempt(tmp_path):
    inbox = InboundInboxService(file_path=str(tmp_path / "critical-inbound.jsonl"))

    with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.get_instance.return_value = mock_client

        subscriber = Subscriber(max_workers=1)
        subscriber.set_main_loop(asyncio.get_running_loop())
        subscriber._inbound_inbox = inbox

        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={
                "intent_id": "intent-2",
                "correlation_id": "corr-2",
                "flow": "command",
                "outcome": "accepted",
                "ts": 1735818000,
            },
            correlation_id="corr-2",
            source="replay-test",
        )

        summary = await subscriber.replay_pending_events(limit=10)
        pending = await inbox.list_pending(limit=10)
        subscriber.shutdown(wait=False)

    assert summary == {"replayed": 0, "failed": 1, "pending_checked": 1}
    assert len(pending) == 1
    assert pending[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_replay_adds_reconciliation_session_markers(tmp_path):
    inbox = InboundInboxService(file_path=str(tmp_path / "critical-inbound.jsonl"))

    with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.get_instance.return_value = mock_client

        subscriber = Subscriber(max_workers=1)
        subscriber.set_main_loop(asyncio.get_running_loop())
        subscriber._inbound_inbox = inbox

        seen_phases: list[str] = []
        seen_session_ids: list[str] = []

        async def handler(topic: str, payload: dict):
            reconciliation = payload.get("_reconciliation") or {}
            seen_phases.append(str(reconciliation.get("phase")))
            seen_session_ids.append(str(reconciliation.get("session_id")))
            return True

        subscriber.register_handler("kaiser/god/esp/+/system/intent_outcome", handler)

        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={
                "intent_id": "intent-a",
                "correlation_id": "corr-a",
                "flow": "command",
                "outcome": "accepted",
                "ts": 1735818000,
            },
            correlation_id="corr-a",
            source="replay-test",
        )
        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={
                "intent_id": "intent-b",
                "correlation_id": "corr-b",
                "flow": "command",
                "outcome": "applied",
                "ts": 1735818001,
            },
            correlation_id="corr-b",
            source="replay-test",
        )

        summary = await subscriber.replay_pending_events(limit=10)
        subscriber.shutdown(wait=False)

    assert summary == {"replayed": 2, "failed": 0, "pending_checked": 2}
    assert seen_phases == ["start", "end"]
    assert len(set(seen_session_ids)) == 1


@pytest.mark.asyncio
async def test_inbound_inbox_parallel_instances_no_unhandled_exceptions(tmp_path):
    shared_file = tmp_path / "parallel" / "critical-inbound.jsonl"
    inbox_a = InboundInboxService(file_path=str(shared_file))
    inbox_b = InboundInboxService(file_path=str(shared_file))

    async def _append_many(prefix: str, inbox: InboundInboxService):
        for idx in range(10):
            await inbox.append(
                topic="kaiser/god/esp/ESP_01/system/intent_outcome",
                payload={"intent_id": f"{prefix}-{idx}", "outcome": "accepted"},
                correlation_id=f"{prefix}-{idx}",
                source="parallel-test",
            )

    await asyncio.gather(
        _append_many("a", inbox_a),
        _append_many("b", inbox_b),
    )

    inbox_reader = InboundInboxService(file_path=str(shared_file))
    pending = await inbox_reader.list_pending(limit=100)

    # Focus this integration test on stability and readable file state under concurrent writers.
    assert len(pending) >= 1
