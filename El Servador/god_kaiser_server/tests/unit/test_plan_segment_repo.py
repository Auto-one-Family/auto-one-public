"""
Unit tests for plan_segment data model (AUT-1232 / Welle 5 T2).

Covers Given/When/Then from the issue:
1. Segment uniqueness at a tick between two abutting EC segments
2. Additive non-effect: CrossESPLogic.follows_plan defaults to False
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.logic import CrossESPLogic
from src.db.models.plan_segment import PlanSegment
from src.db.models.zone import Zone
from src.db.repositories.plan_segment_repo import PlanSegmentRepository


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_plan_t2", name="Zelt Plan T2")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


@pytest.mark.asyncio
async def test_resolve_at_returns_unique_segment_between_abutting_intervals(
    db_session: AsyncSession, zone: Zone
) -> None:
    """GWT-1: mid-interval tick resolves Segment A (1.8), not both/null."""
    t0 = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)

    segment_a = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        value=1.8,
        from_ts=t0,
        to_ts=t1,
        interp="step",
        status="active",
    )
    segment_b = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        value=2.2,
        from_ts=t1,
        to_ts=None,
        interp="step",
        status="planned",
    )
    db_session.add_all([segment_a, segment_b])
    await db_session.flush()

    repo = PlanSegmentRepository(db_session)
    mid = t0 + timedelta(days=7)
    resolved = await repo.resolve_at(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        at=mid,
    )

    assert resolved is not None
    assert resolved.id == segment_a.id
    assert resolved.value == 1.8

    at_boundary = await repo.resolve_at(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        at=t1,
    )
    assert at_boundary is not None
    assert at_boundary.id == segment_b.id
    assert at_boundary.value == 2.2


@pytest.mark.asyncio
async def test_cross_esp_logic_follows_plan_defaults_false(
    db_session: AsyncSession,
) -> None:
    """GWT-2: new/migrated rules stay non-subscribing (additive opt-in)."""
    rule = CrossESPLogic(
        rule_name="aut1232_non_subscriber",
        description="Existing-style rule without plan abo",
        trigger_conditions=[
            {
                "type": "sensor",
                "esp_id": "ESP_AABBCC12",
                "gpio": 34,
                "operator": ">",
                "value": 7.0,
            }
        ],
        actions=[
            {
                "type": "actuator",
                "esp_id": "ESP_AABBCC12",
                "gpio": 5,
                "command": "OFF",
                "value": 0.0,
            }
        ],
        logic_operator="AND",
        enabled=True,
        priority=50,
        cooldown_seconds=60,
    )
    db_session.add(rule)
    await db_session.flush()
    await db_session.refresh(rule)

    assert rule.follows_plan is False
    assert rule.plan_zone_id is None
    assert rule.plan_subzone_config_id is None
    assert rule.plan_domain is None
    assert rule.plan_measure is None
    # Static condition value untouched
    assert rule.conditions[0]["value"] == 7.0


@pytest.mark.asyncio
async def test_plan_segment_covers_half_open_interval() -> None:
    """Unit-level half-open [from, to) semantics on the model helper."""
    from_ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
    to_ts = datetime(2026, 7, 10, tzinfo=timezone.utc)
    seg = PlanSegment(
        zone_id="z",
        domain="nutrient_solution",
        measure="target_ph",
        value=5.8,
        from_ts=from_ts,
        to_ts=to_ts,
        interp="step",
        status="planned",
    )
    assert seg.covers(from_ts) is True
    assert seg.covers(from_ts + timedelta(days=1)) is True
    assert seg.covers(to_ts) is False
    assert seg.covers(to_ts - timedelta(seconds=1)) is True
