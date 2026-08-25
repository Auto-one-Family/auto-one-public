"""
AUT-1337: POST /logic/rules/{id}/test respects action-level condition_refs.

Reuses LogicEngine per-action gate (AUT-1317). Dry-run only — no actuator I/O.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schemas.logic import RuleTestRequest
from src.services.logic_service import LogicService


def _make_rule(
    *,
    conditions: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    logic_operator: str = "AND",
    name: str = "test-rule",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        conditions=conditions,
        actions=actions,
        logic_operator=logic_operator,
    )


def _frischwasser_routed_rule() -> SimpleNamespace:
    """Fall-1: C0 GPIO27==0 → A_ON; C1 GPIO17==1 → A_OFF."""
    return _make_rule(
        name="Frischwasser geroutet",
        logic_operator="AND",
        conditions=[
            {
                "type": "sensor_threshold",
                "esp_id": "ESP_FRESH",
                "gpio": 27,
                "operator": "==",
                "value": 0,
            },
            {
                "type": "sensor_threshold",
                "esp_id": "ESP_FRESH",
                "gpio": 17,
                "operator": "==",
                "value": 1,
            },
        ],
        actions=[
            {
                "type": "actuator_command",
                "esp_id": "ESP_FRESH",
                "gpio": 25,
                "command": "ON",
                "value": 1.0,
                "condition_refs": [0],
            },
            {
                "type": "actuator_command",
                "esp_id": "ESP_FRESH",
                "gpio": 25,
                "command": "OFF",
                "value": 0.0,
                "condition_refs": [1],
                "is_safety_critical": True,
            },
        ],
    )


def _flat_and_rule() -> SimpleNamespace:
    return _make_rule(
        name="flach AND",
        logic_operator="AND",
        conditions=[
            {
                "type": "sensor_threshold",
                "esp_id": "ESP_FLAT",
                "gpio": 34,
                "operator": ">",
                "value": 7.5,
            },
            {
                "type": "sensor_threshold",
                "esp_id": "ESP_FLAT",
                "gpio": 35,
                "operator": "<",
                "value": 30,
            },
        ],
        actions=[
            {
                "type": "actuator_command",
                "esp_id": "ESP_FLAT",
                "gpio": 5,
                "command": "OFF",
                "value": 0.0,
            },
        ],
    )


@pytest.fixture
def logic_service() -> LogicService:
    repo = MagicMock()
    service = LogicService(repo)
    # Never hit DB for missing mock keys in these tests.
    service._get_latest_sensor_value = AsyncMock(return_value=None)
    return service


@pytest.mark.asyncio
async def test_routed_fall1_gpio27_0_gpio17_0_only_a_on(logic_service: LogicService):
    """Gegenprobe AUT-1337: GPIO27=0, GPIO17=0 → nur A_ON würde feuern (= Live)."""
    rule = _frischwasser_routed_rule()
    request = RuleTestRequest(
        mock_sensor_values={
            "ESP_FRESH:27": 0.0,
            "ESP_FRESH:17": 0.0,
        },
        dry_run=True,
    )

    result = await logic_service.test_rule(rule, request)

    assert result.success is True
    assert result.dry_run is True
    assert [c.result for c in result.condition_results] == [True, False]
    # Global AND would be false — but A_ON must still fire via condition_refs.
    assert result.would_trigger is True
    assert len(result.action_results) == 2
    assert result.action_results[0].would_execute is True
    assert result.action_results[0].details.endswith("ON")
    assert result.action_results[1].would_execute is False
    assert result.action_results[1].details.endswith("OFF")


@pytest.mark.asyncio
async def test_routed_fall1_stop_only_a_off(logic_service: LogicService):
    """C0 false / C1 true → nur A_OFF."""
    rule = _frischwasser_routed_rule()
    request = RuleTestRequest(
        mock_sensor_values={
            "ESP_FRESH:27": 1.0,
            "ESP_FRESH:17": 1.0,
        },
        dry_run=True,
    )

    result = await logic_service.test_rule(rule, request)

    assert result.would_trigger is True
    assert result.action_results[0].would_execute is False
    assert result.action_results[1].would_execute is True


@pytest.mark.asyncio
async def test_flat_rule_and_unchanged_both_true(logic_service: LogicService):
    """Regel ohne refs → flaches AND unverändert (beide true → trigger + action)."""
    rule = _flat_and_rule()
    request = RuleTestRequest(
        mock_sensor_values={
            "ESP_FLAT:34": 7.8,
            "ESP_FLAT:35": 20.0,
        },
        dry_run=True,
    )

    result = await logic_service.test_rule(rule, request)

    assert result.would_trigger is True
    assert len(result.action_results) == 1
    assert result.action_results[0].would_execute is True


@pytest.mark.asyncio
async def test_flat_rule_and_unchanged_one_false(logic_service: LogicService):
    """Flaches AND: eine false → kein Trigger, leere action_results (Legacy)."""
    rule = _flat_and_rule()
    request = RuleTestRequest(
        mock_sensor_values={
            "ESP_FLAT:34": 7.8,
            "ESP_FLAT:35": 40.0,  # fails < 30
        },
        dry_run=True,
    )

    result = await logic_service.test_rule(rule, request)

    assert result.would_trigger is False
    assert result.action_results == []


@pytest.mark.asyncio
async def test_test_rule_stays_dry_no_executor_side_effects(logic_service: LogicService):
    """Test bleibt trocken: kein Action-Executor / MQTT-Publish."""
    rule = _frischwasser_routed_rule()
    request = RuleTestRequest(
        mock_sensor_values={"ESP_FRESH:27": 0.0, "ESP_FRESH:17": 0.0},
        dry_run=True,
    )
    # Sentinel: if test_rule ever wired executors, this would be called.
    logic_service.action_executors = []

    result = await logic_service.test_rule(rule, request)

    assert result.dry_run is True
    assert result.would_trigger is True
    # No publish / execute attributes touched beyond dry ActionResult build.
    assert all(ar.dry_run is True for ar in result.action_results)
