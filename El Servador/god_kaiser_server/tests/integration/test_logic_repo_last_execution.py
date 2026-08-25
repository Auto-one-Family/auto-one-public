"""
Integration Tests: LogicRepository.get_last_execution (AUT-1020 skip-marker fix)

Regression coverage for the self-extending PH-MINUS cooldown bug: cooldown/settle/
rate-limit skip markers must never be picked up by get_last_execution() as the
cooldown reference, or the cooldown window never expires (skip logged -> becomes
"last execution" -> next evaluation skips again -> new skip logged -> ...).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.logic import CrossESPLogic, LogicExecutionHistory
from src.db.repositories.logic_repo import LogicRepository


def _make_rule() -> CrossESPLogic:
    return CrossESPLogic(
        rule_name="PH MINUS",
        trigger_conditions={
            "type": "sensor",
            "esp_id": "ESP_AABBCC",
            "gpio": 4,
            "sensor_type": "ph",
            "operator": ">",
            "value": 6.5,
        },
        actions=[
            {
                "type": "actuator_command",
                "esp_id": "ESP_AABBCC",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "duration": 0,
            }
        ],
        enabled=True,
        priority=10,
        cooldown_seconds=150,
    )


@pytest.mark.asyncio
async def test_skip_markers_do_not_self_extend_cooldown_reference(db_session: AsyncSession):
    """Reproduces the live incident: 1 real execution, then repeated cooldown skip
    markers logged every ~30s (much faster than the 150s cooldown). get_last_execution()
    must keep returning the real execution, never one of the skip markers — otherwise
    the cooldown reference perpetually refreshes and never expires."""
    rule = _make_rule()
    db_session.add(rule)
    await db_session.flush()

    repo = LogicRepository(db_session)

    real_execution_time = datetime.now(timezone.utc) - timedelta(seconds=140)
    real_execution = LogicExecutionHistory(
        logic_rule_id=rule.id,
        trigger_data={"type": "rule_update"},
        actions_executed=rule.actions,
        success=True,
        execution_time_ms=42,
        timestamp=real_execution_time,
        is_skip=False,
    )
    db_session.add(real_execution)
    await db_session.flush()

    # Simulate 4 consecutive sensor-driven evaluations blocked by cooldown (~30s apart),
    # each writing its own skip marker — exactly the live pattern (44 skips/hour).
    for i in range(4):
        await repo.log_execution(
            rule_id=rule.id,
            trigger_data={},
            actions=[],
            success=False,
            execution_ms=0,
            error_message=f"cooldown_active:{143 - i * 27}s",
            metadata={"cooldown_seconds": 150, "consecutive_skip_count": 1},
            is_skip=True,
        )

    last = await repo.get_last_execution(rule.id)

    assert last is not None
    assert last.id == real_execution.id
    assert last.is_skip is False
    assert last.success is True


@pytest.mark.asyncio
async def test_get_last_execution_returns_none_when_only_skips_logged(db_session: AsyncSession):
    """A rule that has never actually executed (only cooldown/settle/rate-limit skips)
    must report no last execution — not the most recent skip marker."""
    rule = _make_rule()
    db_session.add(rule)
    await db_session.flush()

    repo = LogicRepository(db_session)
    await repo.log_execution(
        rule_id=rule.id,
        trigger_data={},
        actions=[],
        success=False,
        execution_ms=0,
        error_message="cooldown_active:120s",
        metadata={"consecutive_skip_count": 1},
        is_skip=True,
    )

    last = await repo.get_last_execution(rule.id)

    assert last is None


@pytest.mark.asyncio
async def test_log_execution_persists_is_skip_flag(db_session: AsyncSession):
    """log_execution(is_skip=...) must be wired through to the persisted row;
    default (omitted) must remain False for real execution logging call sites."""
    rule = _make_rule()
    db_session.add(rule)
    await db_session.flush()

    repo = LogicRepository(db_session)

    real = await repo.log_execution(
        rule_id=rule.id,
        trigger_data={"value": 6.8},
        actions=rule.actions,
        success=True,
        execution_ms=10,
    )
    skip = await repo.log_execution(
        rule_id=rule.id,
        trigger_data={},
        actions=[],
        success=False,
        execution_ms=0,
        error_message="rate_limit:hourly cap reached",
        is_skip=True,
    )

    assert real.is_skip is False
    assert skip.is_skip is True
