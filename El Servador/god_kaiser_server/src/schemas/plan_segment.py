"""
Pydantic schemas for plan_segment / applied_setpoint_log (AUT-1232 / AUT-1239).

API surface for T4/T5 can reuse these; T2 only needs model+schema consistency.
Climate domain writes (target_temperature / target_humidity) use the same
create/update schemas — no second climate schema.
"""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..db.models.applied_setpoint_log import APPLIED_SETPOINT_ORIGINS
from ..db.models.plan_segment import (
    PLAN_DOMAINS,
    PLAN_INTERPS,
    PLAN_MEASURES,
    PLAN_SEGMENT_STATUSES,
)
from ..services.growth_phase_vocabulary import normalize_growth_phase

_DOMAIN_SET = frozenset(PLAN_DOMAINS)
_MEASURE_SET = frozenset(PLAN_MEASURES)
_INTERP_SET = frozenset(PLAN_INTERPS)
_STATUS_SET = frozenset(PLAN_SEGMENT_STATUSES)


class PlanSegmentCreate(BaseModel):
    """Create a plan segment (zone-mandatory, subzones via separate assignment)."""

    zone_id: str = Field(..., min_length=1, max_length=50)
    domain: str = Field(..., description=f"One of {sorted(PLAN_DOMAINS)}")
    measure: str = Field(..., description=f"One of {sorted(PLAN_MEASURES)}")
    value: Optional[float] = Field(
        None,
        description="Numeric setpoint (EC/pH or climate T/RH); no domain defaults",
    )
    recipe_ref: Optional[str] = Field(
        None,
        max_length=100,
        description="stock_mix_recipes.id (UUID string) or legacy free-text label (AUT-1361)",
    )
    from_ts: datetime
    to_ts: Optional[datetime] = None
    interp: str = Field("step", description=f"One of {sorted(PLAN_INTERPS)}")
    phase_ref: Optional[str] = Field(None, max_length=64)
    status: str = Field("planned", description=f"One of {sorted(PLAN_SEGMENT_STATUSES)}")
    tolerance: Optional[float] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if v not in _DOMAIN_SET:
            raise ValueError(f"domain must be one of {sorted(_DOMAIN_SET)}")
        return v

    @field_validator("measure")
    @classmethod
    def validate_measure(cls, v: str) -> str:
        if v not in _MEASURE_SET:
            raise ValueError(f"measure must be one of {sorted(_MEASURE_SET)}")
        return v

    @field_validator("interp")
    @classmethod
    def validate_interp(cls, v: str) -> str:
        if v not in _INTERP_SET:
            raise ValueError(f"interp must be one of {sorted(_INTERP_SET)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _STATUS_SET:
            raise ValueError(f"status must be one of {sorted(_STATUS_SET)}")
        return v

    @field_validator("phase_ref")
    @classmethod
    def validate_phase_ref(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        canonical = normalize_growth_phase(v)
        if canonical is None:
            raise ValueError(f"phase_ref '{v}' is not a PLANT_PHASES key or known alias")
        return canonical


class PlanSegmentUpdate(BaseModel):
    """Partial update for a plan segment. Only provided fields are changed."""

    domain: Optional[str] = Field(None, description=f"One of {sorted(PLAN_DOMAINS)}")
    measure: Optional[str] = Field(None, description=f"One of {sorted(PLAN_MEASURES)}")
    value: Optional[float] = Field(
        None,
        description="Numeric setpoint (EC/pH or climate T/RH); no domain defaults",
    )
    recipe_ref: Optional[str] = Field(
        None,
        max_length=100,
        description="stock_mix_recipes.id (UUID string) or legacy free-text label (AUT-1361)",
    )
    from_ts: Optional[datetime] = None
    to_ts: Optional[datetime] = None
    interp: Optional[str] = Field(None, description=f"One of {sorted(PLAN_INTERPS)}")
    phase_ref: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, description=f"One of {sorted(PLAN_SEGMENT_STATUSES)}")
    tolerance: Optional[float] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DOMAIN_SET:
            raise ValueError(f"domain must be one of {sorted(_DOMAIN_SET)}")
        return v

    @field_validator("measure")
    @classmethod
    def validate_measure(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _MEASURE_SET:
            raise ValueError(f"measure must be one of {sorted(_MEASURE_SET)}")
        return v

    @field_validator("interp")
    @classmethod
    def validate_interp(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _INTERP_SET:
            raise ValueError(f"interp must be one of {sorted(_INTERP_SET)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _STATUS_SET:
            raise ValueError(f"status must be one of {sorted(_STATUS_SET)}")
        return v

    @field_validator("phase_ref")
    @classmethod
    def validate_phase_ref(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        canonical = normalize_growth_phase(v)
        if canonical is None:
            raise ValueError(f"phase_ref '{v}' is not a PLANT_PHASES key or known alias")
        return canonical


class PlanSegmentResponse(BaseModel):
    """Plan segment response."""

    id: uuid.UUID
    zone_id: str
    domain: str
    measure: str
    value: Optional[float] = None
    recipe_ref: Optional[str] = None
    from_ts: datetime
    to_ts: Optional[datetime] = None
    interp: str
    phase_ref: Optional[str] = None
    status: str
    tolerance: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClimateMeasureTargetResponse(BaseModel):
    """Resolved (or unresolved) climate measure at evaluation time (AUT-1239)."""

    measure: str = Field(..., description="target_temperature | target_humidity")
    value: Optional[float] = Field(
        None, description="Resolved setpoint; None if no covering segment"
    )
    tolerance: Optional[float] = Field(
        None, description="Optional ± from segment; unused when None (no defaults)"
    )
    segment_id: Optional[uuid.UUID] = None
    from_ts: Optional[datetime] = None
    to_ts: Optional[datetime] = None
    resolved_via: str = Field(..., description="zone | subzone | none")


class PlannedVpdBandResponse(BaseModel):
    """Derived VPD band — never a stored plan_segment measure (AUT-1239)."""

    computable: bool
    reason: Optional[str] = Field(
        None,
        description=(
            "Set when computable=False: missing_target_temperature | "
            "missing_target_humidity | missing_target_temperature_and_humidity | "
            "inputs_out_of_range"
        ),
    )
    vpd_kpa: Optional[float] = None
    vpd_min_kpa: Optional[float] = None
    vpd_max_kpa: Optional[float] = None
    source: str = Field(
        "planned_targets",
        description="Always planned_targets — not live sensors",
    )


class ClimateTargetsAtResponse(BaseModel):
    """GET /v1/plan-segments/climate-at — climate Soll + derived VPD band."""

    zone_id: str
    subzone_config_id: Optional[uuid.UUID] = None
    at: datetime
    domain: str = Field("climate")
    targets: List[ClimateMeasureTargetResponse]
    vpd_band: PlannedVpdBandResponse


class AppliedSetpointLogResponse(BaseModel):
    """Applied setpoint log response (read by T6)."""

    id: uuid.UUID
    zone_id: str
    subzone_config_id: Optional[uuid.UUID] = None
    domain: str
    measure: str
    applied_value: float
    effective_at: datetime
    rule_id: Optional[uuid.UUID] = None
    segment_id: Optional[uuid.UUID] = None
    origin: str = Field(..., description=f"One of {sorted(APPLIED_SETPOINT_ORIGINS)}")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
