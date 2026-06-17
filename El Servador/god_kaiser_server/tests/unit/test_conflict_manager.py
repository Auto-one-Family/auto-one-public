import pytest
from unittest.mock import AsyncMock

from src.services.logic.safety.conflict_manager import ConflictManager


@pytest.mark.asyncio
async def test_conflict_manager_broadcasts_structured_arbitration_event():
    websocket_manager = AsyncMock()
    manager = ConflictManager(websocket_manager=websocket_manager)

    # First rule acquires lock.
    first_ok, first_conflict = await manager.acquire_actuator(
        esp_id="ESP_TEST_001",
        gpio=16,
        rule_id="rule-winner",
        priority=1,
        command="ON",
    )
    assert first_ok is True
    assert first_conflict is None

    # Second rule loses by lower conflict priority.
    second_ok, second_conflict = await manager.acquire_actuator(
        esp_id="ESP_TEST_001",
        gpio=16,
        rule_id="rule-loser",
        priority=5,
        command="OFF",
    )
    assert second_ok is False
    assert second_conflict is not None
    assert second_conflict.trace_id

    websocket_manager.broadcast.assert_awaited()
    ws_event_type, ws_payload = websocket_manager.broadcast.call_args_list[0].args
    assert ws_event_type == "conflict.arbitration"
    assert ws_payload["trace_id"] == second_conflict.trace_id
    assert ws_payload["arbitration_mode"] == "first_wins"
    assert ws_payload["winner_rule_id"] == "rule-winner"
    assert ws_payload["loser_rule_id"] == "rule-loser"
