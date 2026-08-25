"""
Planned climate targets + derived VPD band (AUT-1239 / Welle 6 K2).

Climate is the second domain in the SAME plan_segment model as EC/pH.
Resolution uses PlanSegmentRepository.resolve_at — identical read path to
tank_service.get_targets_at_now / plan_setpoint_resolver (no second path).

VPD is NEVER stored as a plan_segment measure. It is derived from the two
planned targets (temperature + humidity) via the shared Magnus-Tetens
helper in vpd_calculator.calculate_vpd (formula ≠ live sensor_handler trigger).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.plan_segment import PlanSegment
from ..db.repositories.plan_segment_repo import PlanSegmentRepository
from .vpd_calculator import calculate_vpd

CLIMATE_DOMAIN = "climate"
CLIMATE_MEASURES: tuple[str, ...] = (
    "target_temperature",
    "target_humidity",
)


@dataclass(frozen=True)
class PlannedVpdBand:
    """Derived VPD band from planned T/RH — never a stored setpoint."""

    computable: bool
    reason: Optional[str]
    vpd_kpa: Optional[float]
    vpd_min_kpa: Optional[float]
    vpd_max_kpa: Optional[float]
    source: str = "planned_targets"


@dataclass(frozen=True)
class ClimateMeasureTarget:
    measure: str
    value: Optional[float]
    tolerance: Optional[float]
    segment_id: Optional[UUID]
    from_ts: Optional[datetime]
    to_ts: Optional[datetime]
    resolved_via: str  # zone | subzone | none


@dataclass(frozen=True)
class ClimateTargetsAt:
    zone_id: str
    subzone_config_id: Optional[UUID]
    at: datetime
    domain: str
    targets: list[ClimateMeasureTarget]
    vpd_band: PlannedVpdBand


def derive_vpd_band_from_planned(
    temperature_c: Optional[float],
    humidity_rh: Optional[float],
    temperature_tolerance: Optional[float] = None,
    humidity_tolerance: Optional[float] = None,
) -> PlannedVpdBand:
    """Derive a VPD band from two planned setpoint values.

    Reuses ``calculate_vpd`` (single formula). Does not invent agronomic
    defaults — missing inputs yield an explicit non-computable reason.
    Optional tolerances expand the band via corner evaluation; without
    tolerances the band collapses to a point (min == max == centre).
    """
    if temperature_c is None and humidity_rh is None:
        return PlannedVpdBand(
            computable=False,
            reason="missing_target_temperature_and_humidity",
            vpd_kpa=None,
            vpd_min_kpa=None,
            vpd_max_kpa=None,
        )
    if temperature_c is None:
        return PlannedVpdBand(
            computable=False,
            reason="missing_target_temperature",
            vpd_kpa=None,
            vpd_min_kpa=None,
            vpd_max_kpa=None,
        )
    if humidity_rh is None:
        return PlannedVpdBand(
            computable=False,
            reason="missing_target_humidity",
            vpd_kpa=None,
            vpd_min_kpa=None,
            vpd_max_kpa=None,
        )

    centre = calculate_vpd(temperature_c, humidity_rh)
    if centre is None:
        return PlannedVpdBand(
            computable=False,
            reason="inputs_out_of_range",
            vpd_kpa=None,
            vpd_min_kpa=None,
            vpd_max_kpa=None,
        )

    t_tol = temperature_tolerance if temperature_tolerance is not None else 0.0
    h_tol = humidity_tolerance if humidity_tolerance is not None else 0.0

    if t_tol == 0.0 and h_tol == 0.0:
        return PlannedVpdBand(
            computable=True,
            reason=None,
            vpd_kpa=centre,
            vpd_min_kpa=centre,
            vpd_max_kpa=centre,
        )

    # Corner evaluation: VPD rises with T and falls with RH.
    low = calculate_vpd(temperature_c - t_tol, humidity_rh + h_tol)
    high = calculate_vpd(temperature_c + t_tol, humidity_rh - h_tol)
    if low is None or high is None:
        return PlannedVpdBand(
            computable=False,
            reason="inputs_out_of_range",
            vpd_kpa=None,
            vpd_min_kpa=None,
            vpd_max_kpa=None,
        )

    return PlannedVpdBand(
        computable=True,
        reason=None,
        vpd_kpa=centre,
        vpd_min_kpa=min(low, high),
        vpd_max_kpa=max(low, high),
    )


def _resolved_via(segment: Optional[PlanSegment], subzone_config_id: Optional[UUID]) -> str:
    if segment is None:
        return "none"
    if subzone_config_id is not None:
        return "subzone"
    return "zone"


def _to_measure_target(
    measure: str,
    segment: Optional[PlanSegment],
    subzone_config_id: Optional[UUID],
) -> ClimateMeasureTarget:
    if segment is None:
        return ClimateMeasureTarget(
            measure=measure,
            value=None,
            tolerance=None,
            segment_id=None,
            from_ts=None,
            to_ts=None,
            resolved_via="none",
        )
    return ClimateMeasureTarget(
        measure=measure,
        value=segment.value,
        tolerance=segment.tolerance,
        segment_id=segment.id,
        from_ts=segment.from_ts,
        to_ts=segment.to_ts,
        resolved_via=_resolved_via(segment, subzone_config_id),
    )


async def resolve_climate_targets_at(
    *,
    session: AsyncSession,
    zone_id: str,
    at: Optional[datetime] = None,
    subzone_config_id: Optional[UUID] = None,
    _repo: Optional[PlanSegmentRepository] = None,
) -> ClimateTargetsAt:
    """Resolve climate plan_segments@at and derive VPD band (AUT-1239).

    Uses the same ``PlanSegmentRepository.resolve_at`` path as nutrient
    targets / plan_setpoint_resolver — no climate-specific query path.
    """
    effective_at = at or datetime.now(timezone.utc)
    repo = _repo or PlanSegmentRepository(session)

    targets: list[ClimateMeasureTarget] = []
    segments: dict[str, Optional[PlanSegment]] = {}
    for measure in CLIMATE_MEASURES:
        segment = await repo.resolve_at(
            zone_id=zone_id,
            domain=CLIMATE_DOMAIN,
            measure=measure,
            at=effective_at,
            subzone_config_id=subzone_config_id,
        )
        segments[measure] = segment
        targets.append(_to_measure_target(measure, segment, subzone_config_id))

    temp_seg = segments["target_temperature"]
    hum_seg = segments["target_humidity"]
    vpd_band = derive_vpd_band_from_planned(
        temperature_c=temp_seg.value if temp_seg is not None else None,
        humidity_rh=hum_seg.value if hum_seg is not None else None,
        temperature_tolerance=temp_seg.tolerance if temp_seg is not None else None,
        humidity_tolerance=hum_seg.tolerance if hum_seg is not None else None,
    )

    return ClimateTargetsAt(
        zone_id=zone_id,
        subzone_config_id=subzone_config_id,
        at=effective_at,
        domain=CLIMATE_DOMAIN,
        targets=targets,
        vpd_band=vpd_band,
    )
