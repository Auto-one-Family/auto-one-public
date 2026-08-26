"""Phase sections (WHEN) and action-window attachment."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.db.models.plant import Plant, PlantLifecycleEvent
from src.services.phase_section_service import (
    build_phase_sections,
    section_overlapping_window,
    validate_action_window,
)


def _plant(**kwargs: object) -> Plant:
    defaults = {
        "plant_id": uuid4(),
        "genotype_label": "Unit",
        "phase": "veg-frueh",
        "qr_code": f"PL-{uuid4().hex[:8].upper()}",
        "visibility": "tenant_private",
        "planting_date": datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        "zone_id": "z1",
    }
    defaults.update(kwargs)
    return Plant(**defaults)


def _event(
    plant: Plant,
    *,
    event_type: str,
    ts: datetime,
    new_phase: str | None = None,
    status: str = "occurred",
) -> PlantLifecycleEvent:
    return PlantLifecycleEvent(
        event_id=uuid4(),
        plant_id=plant.plant_id,
        event_type=event_type,
        event_timestamp=ts,
        new_phase=new_phase,
        event_status=status,
        created_by_user=1,
        created_at=ts,
    )


class TestBuildPhaseSections:
    def test_synthesises_open_section_from_current_phase(self) -> None:
        plant = _plant()
        sections = build_phase_sections(plant, [])
        assert len(sections) == 1
        assert sections[0].phase == "veg-frueh"
        assert sections[0].end is None
        assert sections[0].zone_id == "z1"
        assert sections[0].source_event_id is None

    def test_event_pairs_become_closed_then_open_intervals(self) -> None:
        plant = _plant(phase="bluete-bulk")
        t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 4, 1, tzinfo=timezone.utc)
        events = [
            _event(plant, event_type="phase_changed", ts=t0, new_phase="veg-frueh"),
            _event(plant, event_type="phase_changed", ts=t1, new_phase="bluete-bulk"),
        ]
        sections = build_phase_sections(plant, events)
        assert [s.phase for s in sections] == ["veg-frueh", "bluete-bulk"]
        assert sections[0].start == t0
        assert sections[0].end == t1
        assert sections[1].start == t1
        assert sections[1].end is None

    def test_planned_phase_change_does_not_open_a_section(self) -> None:
        plant = _plant()
        ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        events = [
            _event(
                plant,
                event_type="phase_changed",
                ts=ts,
                new_phase="bluete-bulk",
                status="planned",
            )
        ]
        sections = build_phase_sections(plant, events)
        assert len(sections) == 1
        assert sections[0].phase == "veg-frueh"
        assert sections[0].source_event_id is None


class TestActionWindow:
    def test_window_must_be_ordered(self) -> None:
        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 2, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="after"):
            validate_action_window(end, start, required=True)

    def test_executed_requires_both_ends(self) -> None:
        with pytest.raises(ValueError, match="require"):
            validate_action_window(None, None, required=True)

    def test_overlap_prefers_section_covering_start(self) -> None:
        plant = _plant(phase="bluete-bulk")
        t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 4, 1, tzinfo=timezone.utc)
        events = [
            _event(plant, event_type="phase_changed", ts=t0, new_phase="veg-frueh"),
            _event(plant, event_type="phase_changed", ts=t1, new_phase="bluete-bulk"),
        ]
        sections = build_phase_sections(plant, events)
        covering = section_overlapping_window(
            sections,
            t1 + timedelta(days=1),
            t1 + timedelta(days=3),
        )
        assert covering is not None
        assert covering.phase == "bluete-bulk"

    def test_overlap_prefers_current_section_when_window_spans_phase_change(
        self,
    ) -> None:
        plant = _plant(phase="bluete-bulk")
        t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 4, 1, 11, 30, tzinfo=timezone.utc)
        events = [
            _event(plant, event_type="phase_changed", ts=t0, new_phase="veg-frueh"),
            _event(plant, event_type="phase_changed", ts=t1, new_phase="bluete-bulk"),
        ]
        sections = build_phase_sections(plant, events)
        covering = section_overlapping_window(
            sections,
            t1 - timedelta(minutes=30),
            t1 + timedelta(minutes=30),
        )
        assert covering is not None
        assert covering.phase == "bluete-bulk"
