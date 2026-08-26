"""
Pydantic schemas for stock_mix_recipes (AUT-1361 / P9).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..db.models.plant import NUTRIENT_PHASES
from .actuator import DOSE_ROLES

StockMixCoverage = Literal["universal", "phase_specific"]

_DOSE_ROLE_RE = re.compile(r"^(part_a|part_b|ph_down|generic)$")
_COVERAGE_RE = re.compile(r"^(universal|phase_specific)$")
_NUTRIENT_PHASE_SET = frozenset(NUTRIENT_PHASES)


class StockMixComponent(BaseModel):
    """One salt/product line in a stock recipe."""

    name: str = Field(..., min_length=1, max_length=120)
    target_g_per_l: float = Field(..., ge=0, description="Target g/L of stock solution")
    salt_composition_id: Optional[uuid.UUID] = Field(
        None,
        description="AUT-1419: soft ref to salt_compositions.id (no hard FK)",
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("component name must not be empty")
        return cleaned


class StockMixRecipeCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    dose_role: str = Field(..., description="part_a | part_b | ph_down | generic")
    coverage: StockMixCoverage
    nutrient_phase: Optional[str] = Field(
        None, description="Required when coverage=phase_specific"
    )
    components: list[StockMixComponent] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True

    @field_validator("dose_role")
    @classmethod
    def validate_dose_role(cls, value: str) -> str:
        if not _DOSE_ROLE_RE.match(value):
            raise ValueError(f"dose_role must be one of {DOSE_ROLES}")
        return value

    @field_validator("coverage")
    @classmethod
    def validate_coverage(cls, value: str) -> str:
        if not _COVERAGE_RE.match(value):
            raise ValueError("coverage must be universal or phase_specific")
        return value

    @field_validator("nutrient_phase")
    @classmethod
    def validate_nutrient_phase(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _NUTRIENT_PHASE_SET:
            raise ValueError(f"nutrient_phase must be one of NUTRIENT_PHASES")
        return value

    @model_validator(mode="after")
    def coverage_phase_consistency(self) -> StockMixRecipeCreate:
        if self.coverage == "universal" and self.nutrient_phase is not None:
            raise ValueError("universal coverage requires nutrient_phase=null")
        if self.coverage == "phase_specific" and self.nutrient_phase is None:
            raise ValueError("phase_specific coverage requires nutrient_phase")
        return self


class StockMixRecipeUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    dose_role: Optional[str] = None
    coverage: Optional[StockMixCoverage] = None
    nutrient_phase: Optional[str] = None
    components: Optional[list[StockMixComponent]] = Field(None, min_length=1)
    metadata: Optional[dict[str, Any]] = None
    active: Optional[bool] = None

    @field_validator("dose_role")
    @classmethod
    def validate_dose_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _DOSE_ROLE_RE.match(value):
            raise ValueError(f"dose_role must be one of {DOSE_ROLES}")
        return value

    @field_validator("nutrient_phase")
    @classmethod
    def validate_nutrient_phase(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _NUTRIENT_PHASE_SET:
            raise ValueError("nutrient_phase must be one of NUTRIENT_PHASES")
        return value


class StockMixRecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    label: str
    dose_role: str
    coverage: str
    nutrient_phase: Optional[str]
    components: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(validation_alias="meta")
    # AUT-1419 B2 — feedforward NPK (always theoretical / computed when present)
    computed_elements: Optional[dict[str, Any]] = None
    computed_npk: Optional[dict[str, Any]] = None
    npk_status: Optional[str] = None
    npk_missing_salts: Optional[list[Any]] = None
    npk_computed_at: Optional[datetime] = None
    active: bool
    created_at: datetime
    updated_at: datetime


class StockMixPhaseResolveResponse(BaseModel):
    """AUT-1420 B3: Rolle×phase_ref resolve for week-grid (reuses lookup)."""

    nutrient_phase: Optional[str] = None
    part_a: Optional[StockMixRecipeResponse] = None
    part_b: Optional[StockMixRecipeResponse] = None
    resolved: bool = False
    detail: Optional[str] = None
