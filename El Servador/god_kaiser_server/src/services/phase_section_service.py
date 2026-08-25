"""
Plant-phase SECTIONS — the time axis.

A section is a half-open interval ``[start, end)`` on one plant and one
phase axis (light/growth or nutrient). It is derived from occurred
``phase_changed`` / ``nutrient_phase_changed`` events. When no transition
exists yet, the current ``plants.phase`` (or ``nutrient_phase``) is
materialised as an open interval from planting/created_at.

Actions (Schnitt, Entlauben, …) sit on a marked sensor window that must
overlap the covering section and inherit the plant's zone/subzone
(WHERE), never a tank id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Iterable, Optional
from uuid import UUID

from ..db.models.plant import Plant, PlantLifecycleEvent
from ..db.repositories.plant_repo import PlantRepository
from .growth_phase_vocabulary import MEASURE_EVENT_TYPES, normalize_growth_phase


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_to_utc_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def plant_timeline_origin(plant: Plant) -> datetime:
    """Earliest plausible start for a synthesised current-phase section."""
    planting = getattr(plant, "planting_date", None)
    if isinstance(planting, datetime):
        return _as_utc(planting)
    if isinstance(planting, date):
        return _date_to_utc_start(planting)
    created = getattr(plant, "created_at", None)
    if isinstance(created, datetime):
        return _as_utc(created)
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PhaseSection:
    plant_id: UUID
    phase: str
    axis: str
    start: datetime
    end: Optional[datetime]
    source_event_id: Optional[UUID]
    zone_id: Optional[str]
    subzone_id: Optional[UUID]

    def covers(self, at: datetime) -> bool:
        instant = _as_utc(at)
        if instant < self.start:
            return False
        if self.end is not None and instant >= self.end:
            return False
        return True

    def overlaps(self, window_start: datetime, window_end: datetime) -> bool:
        start = _as_utc(window_start)
        end = _as_utc(window_end)
        section_end = self.end
        if section_end is None:
            return end > self.start
        return start < section_end and end > self.start


def build_phase_sections(
    plant: Plant,
    events: Iterable[PlantLifecycleEvent],
    *,
    axis: str = "light",
    now: Optional[datetime] = None,
) -> list[PhaseSection]:
    """Derive explicit intervals from lifecycle events (or the current enum)."""
    if axis not in ("light", "nutrient"):
        raise ValueError(f"axis must be 'light' or 'nutrient', got {axis!r}")

    event_type = "phase_changed" if axis == "light" else "nutrient_phase_changed"
    zone_id = PlantRepository.resolve_effective_zone_id(plant)
    subzone_id = plant.subzone_id
    occurred = sorted(
        (ev for ev in events if ev.event_type == event_type and ev.event_status == "occurred"),
        key=lambda ev: _as_utc(ev.event_timestamp),
    )

    if not occurred:
        current = plant.phase if axis == "light" else plant.nutrient_phase
        canonical = normalize_growth_phase(current)
        if canonical is None:
            return []
        return [
            PhaseSection(
                plant_id=plant.plant_id,
                phase=canonical,
                axis=axis,
                start=plant_timeline_origin(plant),
                end=None,
                source_event_id=None,
                zone_id=zone_id,
                subzone_id=subzone_id,
            )
        ]

    sections: list[PhaseSection] = []
    for index, ev in enumerate(occurred):
        phase = normalize_growth_phase(ev.new_phase)
        if phase is None:
            continue
        start = _as_utc(ev.event_timestamp)
        end = _as_utc(occurred[index + 1].event_timestamp) if index + 1 < len(occurred) else None
        sections.append(
            PhaseSection(
                plant_id=plant.plant_id,
                phase=phase,
                axis=axis,
                start=start,
                end=end,
                source_event_id=ev.event_id,
                zone_id=zone_id,
                subzone_id=subzone_id,
            )
        )
    return sections


def section_covering(
    sections: list[PhaseSection],
    at: datetime,
) -> Optional[PhaseSection]:
    instant = _as_utc(at)
    for section in sections:
        if section.covers(instant):
            return section
    return None


def section_overlapping_window(
    sections: list[PhaseSection],
    window_start: datetime,
    window_end: datetime,
) -> Optional[PhaseSection]:
    """Prefer the section that covers window_start; else first overlap."""
    covering = section_covering(sections, window_start)
    if covering is not None and covering.overlaps(window_start, window_end):
        return covering
    for section in sections:
        if section.overlaps(window_start, window_end):
            return section
    return None


def is_measure_event_type(event_type: str) -> bool:
    return event_type in MEASURE_EVENT_TYPES


def validate_action_window(
    window_start: Optional[datetime],
    window_end: Optional[datetime],
    *,
    required: bool,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Normalise the marked action range.

    Executed actions require a real interval. Planned actions may omit it.
    """
    if window_start is None and window_end is None:
        if required:
            raise ValueError(
                "Executed actions require linked_sensor_window_start and "
                "linked_sensor_window_end (the marked time range)."
            )
        return None, None
    if window_start is None or window_end is None:
        raise ValueError(
            "linked_sensor_window_start and linked_sensor_window_end must " "be provided together."
        )
    start = _as_utc(window_start)
    end = _as_utc(window_end)
    if end <= start:
        raise ValueError("linked_sensor_window_end must be after linked_sensor_window_start")
    return start, end
