"""
Wiring tests: LogicEngine._evaluate_rule <-> plan_setpoint_resolver
(AUT-1233 / Welle 5 T3).

Verifies the docking point behavior directly on _evaluate_rule (not just the
resolver module in isolation — see test_plan_setpoint_resolver.py):

1. Subscribing rule + covering segment -> _check_conditions receives conditions
   with the plan value substituted; one applied_setpoint_logs row
   (origin=plan_segment).
2. Non-subscribing rule -> _check_conditions receives rule.trigger_conditions
   UNCHANGED (same object, no copy); zero applied_setpoint_logs rows.
3. Subscribing rule without a covering segment -> _check_conditions receives
   the ORIGINAL (static) conditions unchanged; one applied_setpoint_logs row
   (origin=static_fallback).

_check_conditions is mocked to return False so each test exercises exactly
the read-at-tick resolve step without needing to mock the entire downstream
cooldown/rate-limit/action-execution chain — the resolve+log step happens
unconditionally before conditions are checked (matches DoD: "unabhängig
davon, ob der Wert aus einem Plan-Segment oder aus dem statischen Fallback
stammt").
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.applied_setpoint_log import AppliedSetpointLog
from src.db.models.logic import CrossESPLogic
from src.db.models.plan_segment import PlanSegment
from src.db.models.zone import Zone
from src.services.logic_engine import LogicEngine


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_plan_wiring", name="Zelt Plan Wiring")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


@pytest.fixture
async def mock_actuator_service():
    service = AsyncMock()
    service.send_command = AsyncMock()
    return service


@pytest.fixture
async def mock_websocket_manager():
    return AsyncMock()


@pytest.fixture
async def logic_engine(mock_actuator_service, mock_websocket_manager):
    """Real LogicEngine — logic_repo starts as an AsyncMock; each test swaps
    .session for the real db_session so the resolver's plan_segment queries
    hit real, per-test-isolated in-memory tables (see conftest.db_session)."""
    mock_logic_repo = AsyncMock()
    engine = LogicEngine(
        logic_repo=mock_logic_repo,
        actuator_service=mock_actuator_service,
        websocket_manager=mock_websocket_manager,
    )
    return engine


def _make_rule(**overrides) -> CrossESPLogic:
    defaults = dict(
        rule_name="aut1233_wiring_rule",
        description="AUT-1233 wiring test rule",
        trigger_conditions=[
            {
                "type": "sensor",
                "esp_id": "ESP_AABBCC12",
                "gpio": 34,
                "sensor_type": "ec",
                "operator": "<",
                "value": 1.5,
            }
        ],
        actions=[
            {
                "type": "actuator",
                "esp_id": "ESP_AABBCC12",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
            }
        ],
        logic_operator="AND",
        enabled=True,
        priority=50,
    )
    defaults.update(overrides)
    return CrossESPLogic(**defaults)


def _trigger_data() -> dict:
    return {
        "esp_id": "ESP_AABBCC12",
        "gpio": 34,
        "sensor_type": "ec",
        "value": 1.4,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


@pytest.mark.asyncio
class TestEvaluateRulePlanSetpointWiring:
    async def test_subscribing_rule_with_segment_substitutes_condition_value_and_logs(
        self, logic_engine: LogicEngine, db_session: AsyncSession, zone: Zone
    ) -> None:
        """GWT-1: covering segment -> substituted condition value + applied_setpoint_logs row."""
        now = datetime.now(timezone.utc)
        segment = PlanSegment(
            zone_id=zone.zone_id,
            domain="nutrient_solution",
            measure="target_ec",
            value=2.0,
            from_ts=now - timedelta(days=1),
            to_ts=None,
            interp="step",
            status="active",
        )
        db_session.add(segment)
        await db_session.flush()

        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        logic_engine.logic_repo.session = db_session
        logic_engine._load_cross_sensor_values = AsyncMock(return_value=({}, []))
        logic_engine._check_conditions = AsyncMock(return_value=False)

        await logic_engine._evaluate_rule(rule, _trigger_data(), logic_engine.logic_repo)

        logic_engine._check_conditions.assert_awaited_once()
        passed_conditions = logic_engine._check_conditions.call_args.args[0]
        assert passed_conditions[0]["value"] == 2.0
        # No writeback — the rule's own trigger_conditions stay untouched (Option A)
        assert rule.trigger_conditions[0]["value"] == 1.5

        rows = (
            (
                await db_session.execute(
                    select(AppliedSetpointLog).where(AppliedSetpointLog.rule_id == rule.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].origin == "plan_segment"
        assert rows[0].applied_value == 2.0
        assert rows[0].segment_id == segment.id

    async def test_non_subscribing_rule_is_bit_identical(
        self, logic_engine: LogicEngine, db_session: AsyncSession
    ) -> None:
        """GWT-2: non-subscribing rule — same object passed through, zero log rows."""
        rule = _make_rule(follows_plan=False)
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        logic_engine.logic_repo.session = db_session
        logic_engine._load_cross_sensor_values = AsyncMock(return_value=({}, []))
        logic_engine._check_conditions = AsyncMock(return_value=False)

        await logic_engine._evaluate_rule(rule, _trigger_data(), logic_engine.logic_repo)

        logic_engine._check_conditions.assert_awaited_once()
        passed_conditions = logic_engine._check_conditions.call_args.args[0]
        assert passed_conditions[0]["value"] == 1.5
        assert passed_conditions is rule.trigger_conditions  # identical object — no copy made

        rows = (await db_session.execute(select(AppliedSetpointLog))).scalars().all()
        assert len(rows) == 0

    async def test_subscribing_rule_without_segment_keeps_static_value_and_logs_fallback(
        self, logic_engine: LogicEngine, db_session: AsyncSession, zone: Zone
    ) -> None:
        """GWT-3: no covering segment — static value untouched, origin=static_fallback logged."""
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        logic_engine.logic_repo.session = db_session
        logic_engine._load_cross_sensor_values = AsyncMock(return_value=({}, []))
        logic_engine._check_conditions = AsyncMock(return_value=False)

        await logic_engine._evaluate_rule(rule, _trigger_data(), logic_engine.logic_repo)

        passed_conditions = logic_engine._check_conditions.call_args.args[0]
        assert passed_conditions[0]["value"] == 1.5  # static kept — no segment to substitute

        rows = (
            (
                await db_session.execute(
                    select(AppliedSetpointLog).where(AppliedSetpointLog.rule_id == rule.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].origin == "static_fallback"
        assert rows[0].applied_value == 1.5
        assert rows[0].segment_id is None
