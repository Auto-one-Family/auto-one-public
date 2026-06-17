"""Unit tests: command_intents orchestration_state (sent vs inbound intent_outcome)."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from src.db.models.command_contract import CommandIntent
from src.db.repositories.command_contract_repo import CommandContractRepository
from src.mqtt.publisher import Publisher


def test_publish_actuator_command_payload_includes_intent_id_with_correlation():
    client = MagicMock()
    client.publish.return_value = True
    pub = Publisher(mqtt_client=client)
    pub.publish_actuator_command("ESP_1", 4, "ON", 1.0, correlation_id="cid-99")
    _topic, payload_str, _qos = client.publish.call_args[0]
    payload = json.loads(payload_str)
    assert payload["correlation_id"] == "cid-99"
    assert payload["intent_id"] == "cid-99"


def test_publish_sensor_command_payload_includes_intent_and_correlation():
    client = MagicMock()
    client.publish.return_value = True
    pub = Publisher(mqtt_client=client)
    success, request_id = pub.publish_sensor_command("ESP_1", 4, "measure")
    assert success is True
    _topic, payload_str, _qos = client.publish.call_args[0]
    payload = json.loads(payload_str)
    assert payload["request_id"] == request_id
    assert payload["correlation_id"] == request_id
    assert payload["intent_id"] == request_id


@pytest.mark.asyncio
async def test_record_intent_publish_sent_inserts_sent(db_session):
    repo = CommandContractRepository(db_session)
    row = await repo.record_intent_publish_sent(
        intent_id="corr-uuid-1",
        correlation_id="corr-uuid-1",
        esp_id="ESP_X",
        flow="command",
    )
    assert row.orchestration_state == "sent"
    assert row.intent_id == "corr-uuid-1"
    await db_session.commit()

    result = await db_session.execute(
        select(CommandIntent).where(CommandIntent.intent_id == "corr-uuid-1")
    )
    loaded = result.scalar_one()
    assert loaded.orchestration_state == "sent"


@pytest.mark.asyncio
async def test_upsert_intent_after_sent_moves_to_accepted(db_session):
    repo = CommandContractRepository(db_session)
    await repo.record_intent_publish_sent(
        intent_id="intent-a",
        correlation_id="intent-a",
        esp_id="ESP_X",
        flow="command",
    )
    await repo.upsert_intent(
        {
            "intent_id": "intent-a",
            "correlation_id": "intent-a",
            "flow": "command",
            "outcome": "accepted",
            "ts": 1735818000,
        },
        esp_id="ESP_X",
    )
    await db_session.commit()

    result = await db_session.execute(
        select(CommandIntent).where(CommandIntent.intent_id == "intent-a")
    )
    assert result.scalar_one().orchestration_state == "accepted"


@pytest.mark.asyncio
async def test_record_sent_does_not_downgrade_ack_pending(db_session):
    repo = CommandContractRepository(db_session)
    await repo.upsert_intent(
        {
            "intent_id": "intent-b",
            "correlation_id": "c-b",
            "flow": "command",
            "outcome": "applied",
            "ts": 1735818000,
        },
        esp_id="ESP_X",
    )
    assert (
        await db_session.execute(select(CommandIntent).where(CommandIntent.intent_id == "intent-b"))
    ).scalar_one().orchestration_state == "ack_pending"

    await repo.record_intent_publish_sent(
        intent_id="intent-b",
        correlation_id="c-b",
        esp_id="ESP_X",
        flow="command",
    )
    await db_session.commit()

    result = await db_session.execute(
        select(CommandIntent).where(CommandIntent.intent_id == "intent-b")
    )
    assert result.scalar_one().orchestration_state == "ack_pending"


@pytest.mark.asyncio
async def test_record_intent_publish_sent_parallel_same_intent_is_idempotent(test_engine):
    """Parallel writes with same intent_id must converge to a single row."""
    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def _writer(correlation_id: str) -> None:
        async with async_session_maker() as session:
            repo = CommandContractRepository(session)
            await repo.record_intent_publish_sent(
                intent_id="intent-parallel-1",
                correlation_id=correlation_id,
                esp_id="ESP_X",
                flow="command",
            )
            await session.commit()

    await asyncio.gather(_writer("corr-a"), _writer("corr-b"))

    async with async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(CommandIntent).where(CommandIntent.intent_id == "intent-parallel-1")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].intent_id == "intent-parallel-1"


@pytest.mark.asyncio
async def test_terminal_outcome_promotes_intent_state_to_terminal_failed(db_session):
    repo = CommandContractRepository(db_session)
    await repo.record_intent_publish_sent(
        intent_id="intent-term-fail",
        correlation_id="corr-term-fail",
        esp_id="ESP_X",
        flow="command",
    )
    await repo.upsert_outcome(
        {
            "intent_id": "intent-term-fail",
            "correlation_id": "corr-term-fail",
            "flow": "command",
            "outcome": "failed",
            "is_final": True,
            "ts": 1735818000,
        },
        esp_id="ESP_X",
    )
    await db_session.commit()
    loaded = (
        await db_session.execute(
            select(CommandIntent).where(CommandIntent.intent_id == "intent-term-fail")
        )
    ).scalar_one()
    assert loaded.orchestration_state == "terminal_failed"


@pytest.mark.asyncio
async def test_terminal_state_is_not_downgraded_by_late_non_terminal_intent(db_session):
    repo = CommandContractRepository(db_session)
    await repo.record_intent_publish_sent(
        intent_id="intent-no-downgrade",
        correlation_id="corr-no-downgrade",
        esp_id="ESP_X",
        flow="command",
    )
    await repo.upsert_outcome(
        {
            "intent_id": "intent-no-downgrade",
            "correlation_id": "corr-no-downgrade",
            "flow": "command",
            "outcome": "failed",
            "is_final": True,
            "ts": 1735818000,
        },
        esp_id="ESP_X",
    )
    await repo.upsert_intent(
        {
            "intent_id": "intent-no-downgrade",
            "correlation_id": "corr-no-downgrade",
            "flow": "command",
            "outcome": "accepted",
            "ts": 1735818001,
        },
        esp_id="ESP_X",
    )
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(CommandIntent).where(CommandIntent.intent_id == "intent-no-downgrade")
        )
    ).scalar_one()
    assert loaded.orchestration_state == "terminal_failed"


@pytest.mark.asyncio
async def test_terminal_outcome_replay_repairs_stale_non_terminal_intent_state(db_session):
    repo = CommandContractRepository(db_session)
    payload = {
        "intent_id": "intent-heal-stale",
        "correlation_id": "corr-heal-stale",
        "flow": "command",
        "outcome": "failed",
        "is_final": True,
        "ts": 1735818000,
    }
    await repo.record_intent_publish_sent(
        intent_id="intent-heal-stale",
        correlation_id="corr-heal-stale",
        esp_id="ESP_X",
        flow="command",
    )
    await repo.upsert_outcome(payload, esp_id="ESP_X")

    broken_intent = (
        await db_session.execute(select(CommandIntent).where(CommandIntent.intent_id == "intent-heal-stale"))
    ).scalar_one()
    broken_intent.orchestration_state = "ack_pending"
    await db_session.flush()

    await repo.upsert_outcome(payload, esp_id="ESP_X")
    await db_session.commit()

    loaded = (
        await db_session.execute(select(CommandIntent).where(CommandIntent.intent_id == "intent-heal-stale"))
    ).scalar_one()
    assert loaded.orchestration_state == "terminal_failed"
