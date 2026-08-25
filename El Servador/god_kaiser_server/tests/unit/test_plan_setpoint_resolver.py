"""
Unit tests for plan_setpoint_resolver (AUT-1233 / Welle 5 T3).

Covers Given/When/Then from the issue:
1. Subscribing rule + covering plan_segment -> plan value used, origin=plan_segment
2. Non-subscribing rule -> resolver returns None immediately, zero DB access
3. Subscribing rule without a covering segment -> static fallback, origin=static_fallback,
   never null/failure

Plus pure-function coverage for the condition-substitution and static-value-extraction
helpers used by LogicEngine._evaluate_rule at both AUT-1233 docking points.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.applied_setpoint_log import AppliedSetpointLog
from src.db.models.logic import CrossESPLogic
from src.db.models.plan_segment import PlanSegment
from src.db.models.zone import Zone
from src.services.logic.plan_setpoint_resolver import (
    ResolveResult,
    apply_resolved_value_to_conditions,
    extract_static_setpoint,
    log_applied_setpoint,
    measure_to_sensor_type,
    resolve_effective_setpoint,
)


def _make_rule(**overrides) -> CrossESPLogic:
    defaults = dict(
        rule_name="aut1233_rule",
        description="AUT-1233 test rule",
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


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_plan_t3", name="Zelt Plan T3")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


# ---------------------------------------------------------------------------
# measure_to_sensor_type
# ---------------------------------------------------------------------------


class TestMeasureToSensorType:
    def test_target_ec_maps_to_ec(self):
        assert measure_to_sensor_type("target_ec") == "ec"

    def test_target_ph_maps_to_ph(self):
        assert measure_to_sensor_type("target_ph") == "ph"

    def test_target_temperature_maps_to_temperature(self):
        assert measure_to_sensor_type("target_temperature") == "temperature"

    def test_non_numeric_measures_return_none(self):
        assert measure_to_sensor_type("recipe_ref") is None
        assert measure_to_sensor_type("light_regime") is None

    def test_none_measure_returns_none(self):
        assert measure_to_sensor_type(None) is None

    def test_target_humidity_maps_to_humidity(self):
        assert measure_to_sensor_type("target_humidity") == "humidity"


# ---------------------------------------------------------------------------
# apply_resolved_value_to_conditions
# ---------------------------------------------------------------------------


class TestApplyResolvedValueToConditions:
    def test_replaces_matching_value_leaves_others_untouched(self):
        conditions = [
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "ec",
                "operator": "<",
                "value": 1.5,
            },
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 2,
                "sensor_type": "ph",
                "operator": ">",
                "value": 6.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "ec", 2.0)

        assert result[0]["value"] == 2.0
        assert result[1]["value"] == 6.0  # different sensor_type — untouched
        # original input must never be mutated (no writeback)
        assert conditions[0]["value"] == 1.5

    def test_compound_logic_wrapper_is_preserved(self):
        conditions = {
            "logic": "AND",
            "conditions": [
                {
                    "type": "sensor",
                    "esp_id": "E1",
                    "gpio": 1,
                    "sensor_type": "ec",
                    "operator": "<",
                    "value": 1.5,
                },
            ],
        }
        result = apply_resolved_value_to_conditions(conditions, "ec", 2.0)

        assert result["logic"] == "AND"
        assert result["conditions"][0]["value"] == 2.0

    def test_between_operator_recenters_preserving_width(self):
        conditions = [
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "ec",
                "operator": "between",
                "min": 1.0,
                "max": 2.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "ec", 3.0)

        assert result[0]["min"] == 2.5
        assert result[0]["max"] == 3.5

    def test_hysteresis_cooling_mode_anchors_off_to_setpoint_upper_gap(self):
        """Cooling/pH-Minus: Aus = Soll, Ein = Soll + gap (kein Totband nach unten)."""
        conditions = [
            {
                "type": "hysteresis",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "temperature",
                "activate_above": 28.0,
                "deactivate_below": 24.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "temperature", 30.0)

        # gap = 4.0 → Aus 30, Ein 34
        assert result[0]["deactivate_below"] == 30.0
        assert result[0]["activate_above"] == 34.0

    def test_hysteresis_heating_mode_anchors_off_to_setpoint_lower_gap(self):
        """Heating/pH-Plus: Aus = Soll, Ein = Soll - gap (kein Totband nach oben)."""
        conditions = [
            {
                "type": "hysteresis",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "ph",
                "activate_below": 5.8,
                "deactivate_above": 6.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "ph", 5.9)

        assert result[0]["deactivate_above"] == 5.9
        assert result[0]["activate_below"] == 5.7

    def test_non_matching_sensor_type_returns_deep_copy_unchanged(self):
        conditions = [
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "ph",
                "operator": "<",
                "value": 6.0,
            }
        ]
        result = apply_resolved_value_to_conditions(conditions, "ec", 2.0)

        assert result[0]["value"] == 6.0
        assert result is not conditions
        assert result[0] is not conditions[0]

    def test_temperature_alias_matches_sht31_temp(self):
        conditions = [
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 1,
                "sensor_type": "sht31_temp",
                "operator": "<",
                "value": 22.0,
            },
            {
                "type": "sensor",
                "esp_id": "E1",
                "gpio": 2,
                "sensor_type": "sht31_humidity",
                "operator": ">",
                "value": 50.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "temperature", 24.0)

        assert result[0]["value"] == 24.0
        assert result[1]["value"] == 50.0
        assert conditions[0]["value"] == 22.0

    def test_humidity_alias_matches_sht31_humidity(self):
        conditions = [
            {
                "type": "hysteresis",
                "esp_id": "E1",
                "gpio": 2,
                "sensor_type": "sht31_humidity",
                "activate_above": 70.0,
                "deactivate_below": 60.0,
            },
        ]
        result = apply_resolved_value_to_conditions(conditions, "humidity", 55.0)

        assert result[0]["deactivate_below"] == 55.0
        assert result[0]["activate_above"] == 65.0


# ---------------------------------------------------------------------------
# extract_static_setpoint
# ---------------------------------------------------------------------------


class TestExtractStaticSetpoint:
    def test_prefers_dose_config_target_value(self):
        rule = _make_rule(
            plan_measure="target_ec",
            rule_metadata={"dose_config": {"target_value": 1.9}},
        )
        value, source = extract_static_setpoint(rule)

        assert value == 1.9
        assert source == "dose_config.target_value"

    def test_falls_back_to_matching_condition_value(self):
        rule = _make_rule(plan_measure="target_ec")
        value, source = extract_static_setpoint(rule)

        assert value == 1.5
        assert source == "trigger_conditions.value"

    def test_returns_none_when_nothing_matches(self):
        # trigger_conditions only reference sensor_type "ec" — measure is "ph"
        rule = _make_rule(plan_measure="target_ph")
        value, source = extract_static_setpoint(rule)

        assert value is None
        assert source is None

    def test_temperature_measure_reads_sht31_temp_condition(self):
        rule = _make_rule(
            plan_measure="target_temperature",
            trigger_conditions=[
                {
                    "type": "sensor",
                    "esp_id": "ESP_AABBCC12",
                    "gpio": 1,
                    "sensor_type": "sht31_temp",
                    "operator": "<",
                    "value": 22.5,
                }
            ],
        )
        value, source = extract_static_setpoint(rule)

        assert value == 22.5
        assert source == "trigger_conditions.value"


# ---------------------------------------------------------------------------
# resolve_effective_setpoint (DB-backed, GWT 1/2/3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResolveEffectiveSetpoint:
    async def test_non_subscribing_rule_returns_none_without_db_access(
        self, db_session: AsyncSession
    ) -> None:
        """GWT-2: non-subscribing rule — free, immediate abort, zero DB access."""
        rule = _make_rule(follows_plan=False)
        db_session.add(rule)
        await db_session.flush()

        result = await resolve_effective_setpoint(rule, session=db_session, static_value=1.5)

        assert result is None

    async def test_subscribing_rule_with_covering_segment_uses_plan_value(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        """GWT-1: a covering segment wins — origin=plan_segment, correct value+id."""
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
        await db_session.refresh(segment)

        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()

        result = await resolve_effective_setpoint(
            rule,
            session=db_session,
            static_value=1.5,
            static_value_source="trigger_conditions.value",
            at=now,
        )

        assert result is not None
        assert result.origin == "plan_segment"
        assert result.value == 2.0
        assert result.segment_id == segment.id

    async def test_subscribing_rule_without_covering_segment_falls_back_to_static(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        """GWT-3: no segment covers 'now' — static fallback, never null/failure."""
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()

        result = await resolve_effective_setpoint(
            rule,
            session=db_session,
            static_value=1.5,
            static_value_source="trigger_conditions.value",
        )

        assert result is not None
        assert result.origin == "static_fallback"
        assert result.value == 1.5
        assert result.segment_id is None
        assert result.static_value_source == "trigger_conditions.value"

    async def test_subscribing_rule_with_incomplete_plan_fields_falls_back_to_static(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        """Defensive: follows_plan=True but plan_domain/measure missing — never crash."""
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain=None,
            plan_measure=None,
        )
        db_session.add(rule)
        await db_session.flush()

        result = await resolve_effective_setpoint(
            rule, session=db_session, static_value=1.5, static_value_source="trigger_conditions.value"
        )

        assert result is not None
        assert result.origin == "static_fallback"
        assert result.value == 1.5


# ---------------------------------------------------------------------------
# log_applied_setpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLogAppliedSetpoint:
    async def test_writes_row_with_plan_segment_origin(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        now = datetime.now(timezone.utc)
        resolved = ResolveResult(value=2.0, origin="plan_segment", segment_id=uuid.uuid4())

        await log_applied_setpoint(rule, resolved, db_session, now)

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
        assert rows[0].applied_value == 2.0
        assert rows[0].origin == "plan_segment"
        assert rows[0].zone_id == zone.zone_id
        assert rows[0].domain == "nutrient_solution"
        assert rows[0].measure == "target_ec"
        assert rows[0].segment_id == resolved.segment_id

    async def test_writes_row_with_static_fallback_origin(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        resolved = ResolveResult(value=1.5, origin="static_fallback")
        await log_applied_setpoint(rule, resolved, db_session, datetime.now(timezone.utc))

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
        assert rows[0].applied_value == 1.5
        assert rows[0].origin == "static_fallback"
        assert rows[0].segment_id is None

    async def test_skips_write_when_no_concrete_value_exists(
        self, db_session: AsyncSession, zone: Zone
    ) -> None:
        """Edge case: neither plan nor static value determinable — never writes a
        NULL applied_value (NOT NULL column) and never raises."""
        rule = _make_rule(
            follows_plan=True,
            plan_zone_id=zone.zone_id,
            plan_domain="nutrient_solution",
            plan_measure="target_ec",
        )
        db_session.add(rule)
        await db_session.flush()
        await db_session.refresh(rule)

        resolved = ResolveResult(value=None, origin="static_fallback")
        await log_applied_setpoint(rule, resolved, db_session, datetime.now(timezone.utc))

        rows = (
            (
                await db_session.execute(
                    select(AppliedSetpointLog).where(AppliedSetpointLog.rule_id == rule.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 0
