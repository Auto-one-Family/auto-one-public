import logging
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.inbound_inbox_service import InboundInboxService


@pytest.mark.asyncio
async def test_append_creates_missing_parent_directory(tmp_path: Path):
    file_path = tmp_path / "missing" / "nested" / "critical-inbound.jsonl"
    inbox = InboundInboxService(file_path=str(file_path))

    await inbox.append(
        topic="kaiser/god/esp/ESP_01/system/intent_outcome",
        payload={"intent_id": "intent-1", "outcome": "accepted"},
        correlation_id="corr-1",
    )

    stats = await inbox.stats()
    assert file_path.exists()
    assert stats["pending"] == 1


@pytest.mark.asyncio
async def test_list_pending_when_file_missing_returns_empty_without_crash(tmp_path: Path):
    file_path = tmp_path / "critical-inbound.jsonl"
    inbox = InboundInboxService(file_path=str(file_path))

    pending = await inbox.list_pending(limit=10)

    assert pending == []


@pytest.mark.asyncio
async def test_append_permission_error_logs_and_does_not_raise(tmp_path: Path, caplog):
    file_path = tmp_path / "critical-inbound.jsonl"
    inbox = InboundInboxService(file_path=str(file_path))

    caplog.set_level(logging.ERROR)
    with patch("pathlib.Path.write_text", side_effect=PermissionError("denied")):
        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={"intent_id": "intent-1", "outcome": "accepted"},
            correlation_id="corr-1",
        )

    assert "action=failed context=persist" in caplog.text
    pending = await inbox.list_pending(limit=10)
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_parallel_append_same_service_consistent(tmp_path: Path):
    file_path = tmp_path / "critical-inbound.jsonl"
    inbox = InboundInboxService(file_path=str(file_path))

    async def _append_event(idx: int):
        await inbox.append(
            topic="kaiser/god/esp/ESP_01/system/intent_outcome",
            payload={"intent_id": f"intent-{idx}", "outcome": "accepted"},
            correlation_id=f"corr-{idx}",
        )

    await asyncio.gather(*[_append_event(i) for i in range(25)])
    stats = await inbox.stats()

    assert stats["pending"] == 25
