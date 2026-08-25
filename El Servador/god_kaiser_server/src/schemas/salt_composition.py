"""
Pydantic schemas for salt_compositions (AUT-1418 / B1).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..db.models.salt_composition import SALT_SOURCE_TYPES

SaltSourceType = Literal["stoichiometric", "manufacturer_label", "beleg_offen"]

_SOURCE_TYPE_RE = re.compile(r"^(stoichiometric|manufacturer_label|beleg_offen)$")


def _pct_field() -> Field:
    return Field(
        None,
        ge=0,
        le=100,
        description="Elemental mass % of salt (NULL if unknown / beleg_offen)",
    )


class SaltCompositionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    formula: Optional[str] = Field(None, max_length=120)
    n_pct: Optional[float] = _pct_field()
    p_pct: Optional[float] = _pct_field()
    k_pct: Optional[float] = _pct_field()
    ca_pct: Optional[float] = _pct_field()
    mg_pct: Optional[float] = _pct_field()
    s_pct: Optional[float] = _pct_field()
    source_type: SaltSourceType
    source_note: str = Field("", max_length=2000)
    active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if not _SOURCE_TYPE_RE.match(value):
            raise ValueError(f"source_type must be one of {SALT_SOURCE_TYPES}")
        return value


class SaltCompositionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    formula: Optional[str] = Field(None, max_length=120)
    n_pct: Optional[float] = _pct_field()
    p_pct: Optional[float] = _pct_field()
    k_pct: Optional[float] = _pct_field()
    ca_pct: Optional[float] = _pct_field()
    mg_pct: Optional[float] = _pct_field()
    s_pct: Optional[float] = _pct_field()
    source_type: Optional[SaltSourceType] = None
    source_note: Optional[str] = Field(None, max_length=2000)
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _SOURCE_TYPE_RE.match(value):
            raise ValueError(f"source_type must be one of {SALT_SOURCE_TYPES}")
        return value


class SaltCompositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    formula: Optional[str]
    n_pct: Optional[float]
    p_pct: Optional[float]
    k_pct: Optional[float]
    ca_pct: Optional[float]
    mg_pct: Optional[float]
    s_pct: Optional[float]
    source_type: str
    source_note: str
    active: bool
    created_at: datetime
    updated_at: datetime
