"""
Tank / Nutrient Ledger Pydantic Schemas (AUT-1217).

Write-path DTOs for tanks, tank↔subzone assignments, and nutrient-solution
batch ledger entries. Pattern mirrors SensorSubzoneAssignment (AUT-1155) and
Plant/LifecycleEvent responses.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..db.models.nutrient_solution_batch import (
    NUTRIENT_BATCH_ACQUISITION_METHODS,
    NUTRIENT_BATCH_ENTRY_TYPES,
    NUTRIENT_BATCH_QUALIFIERS,
)
from ..db.models.tank import TANK_OPERATION_MODES

_ENTRY_TYPE_SET = set(NUTRIENT_BATCH_ENTRY_TYPES)
_ACQUISITION_METHOD_SET = set(NUTRIENT_BATCH_ACQUISITION_METHODS)
_QUALIFIER_SET = set(NUTRIENT_BATCH_QUALIFIERS)
_OPERATION_MODE_SET = set(TANK_OPERATION_MODES)


# =============================================================================
# Tank
# =============================================================================


class TankCreate(BaseModel):
    """Request schema for creating a tank."""

    zone_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Zone this tank belongs to (zones.zone_id)",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable tank name",
    )
    operation_mode: str = Field(
        ...,
        description=f"One of: {sorted(_OPERATION_MODE_SET)}",
    )
    nominal_volume_l: Optional[float] = Field(
        None,
        ge=0,
        description="Optional nominal volume in liters",
    )
    fresh_water_ec_us_cm: Optional[float] = Field(
        None,
        ge=0,
        description="Configured fresh-water EC (µS/cm); omit = not configured",
    )
    fresh_water_ph: Optional[float] = Field(
        None,
        ge=0,
        le=14,
        description="Configured fresh-water pH; omit = not configured",
    )

    @field_validator("operation_mode")
    @classmethod
    def validate_operation_mode(cls, v: str) -> str:
        if v not in _OPERATION_MODE_SET:
            raise ValueError(
                f"operation_mode must be one of {sorted(_OPERATION_MODE_SET)}"
            )
        return v


class TankUpdate(BaseModel):
    """Partial update for tank attributes (AUT-1381 — Frischwasser/Volumen)."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    nominal_volume_l: Optional[float] = Field(None, ge=0)
    operation_mode: Optional[str] = None
    fresh_water_ec_us_cm: Optional[float] = Field(
        None,
        ge=0,
        description="Set fresh-water EC; null clears (not configured)",
    )
    fresh_water_ph: Optional[float] = Field(
        None,
        ge=0,
        le=14,
        description="Set fresh-water pH; null clears (not configured)",
    )

    @field_validator("operation_mode")
    @classmethod
    def validate_operation_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in _OPERATION_MODE_SET:
            raise ValueError(
                f"operation_mode must be one of {sorted(_OPERATION_MODE_SET)}"
            )
        return v


class TankResponse(BaseModel):
    """Response schema for a single tank."""

    id: uuid.UUID = Field(..., description="Tank UUID")
    zone_id: str = Field(..., description="Owning zone (zones.zone_id)")
    name: str = Field(..., description="Tank name")
    nominal_volume_l: Optional[float] = Field(None, description="Nominal volume (L)")
    fresh_water_ec_us_cm: Optional[float] = Field(
        None, description="Configured fresh-water EC (µS/cm); null = not configured"
    )
    fresh_water_ph: Optional[float] = Field(
        None, description="Configured fresh-water pH; null = not configured"
    )
    operation_mode: str = Field(..., description="drain_to_waste | recirculating")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Tank ↔ Subzone Assignment (AUT-1155 pattern)
# =============================================================================


class TankSubzoneAssignRequest(BaseModel):
    """Request to assign a tank to a subzone_config (n:m)."""

    subzone_config_id: uuid.UUID = Field(
        ...,
        description="UUID of the subzone_configs row to assign",
    )


class TankSubzoneAssignmentInfo(BaseModel):
    """Single tank→subzone assignment record (mirrors SensorSubzoneAssignmentInfo)."""

    id: str = Field(..., description="UUID of the assignment record")
    tank_id: str = Field(..., description="UUID of the tank")
    subzone_config_id: str = Field(..., description="UUID of the subzone_config")
    assigned_at: str = Field(..., description="ISO-8601 timestamp (UTC)")
    assigned_by: Optional[int] = Field(
        None, description="User ID of the assigning operator"
    )

    model_config = ConfigDict(from_attributes=True)


class TankSubzoneRemoveResponse(BaseModel):
    """Response after removing a tank↔subzone assignment."""

    success: bool = True
    message: str = "Tank assignment removed"
    tank_id: str
    subzone_config_id: str


# =============================================================================
# Tank ↔ ESP Device Assignment (n:1, AUT-1223 Q2)
# =============================================================================
# Cardinality n:1 (nullable FK esp_devices.tank_id -> tanks.id), analogous to
# ESPDevice.zone_id. NOT the n:m tank_subzone_assignments junction above —
# devices measure/mix in exactly one tank at a time.


class TankDeviceSummary(BaseModel):
    """Lightweight ESP device summary for Tank→devices listing (AUT-1223)."""

    device_id: str = Field(..., description="ESP device_id (e.g. ESP_12AB34CD)")
    name: Optional[str] = Field(None, description="Human-readable device name")
    zone_id: Optional[str] = Field(None, description="Device zone (zones.zone_id)")
    status: str = Field(..., description="Device status (online, offline, ...)")
    hardware_type: str = Field(..., description="Hardware type")

    model_config = ConfigDict(from_attributes=True)


class TankDevicesResponse(BaseModel):
    """Response for GET /v1/tanks/{tank_id}/devices."""

    tank_id: str = Field(..., description="Tank UUID")
    devices: List[TankDeviceSummary] = Field(
        default_factory=list, description="ESP devices currently assigned to this tank"
    )
    count: int = Field(0, ge=0, description="Number of assigned devices")


class TankDeviceAssignResponse(BaseModel):
    """Response after assigning an ESP device to a tank (n:1, AUT-1223)."""

    tank_id: str = Field(..., description="UUID of the tank")
    device_id: str = Field(..., description="ESP device_id (e.g. ESP_12AB34CD)")


class TankDeviceUnassignResponse(BaseModel):
    """Response after clearing a tank↔device assignment (n:1, AUT-1223)."""

    success: bool = True
    message: str = "Tank device assignment cleared"
    tank_id: str
    device_id: str


# =============================================================================
# Tank Targets (Soll from plan_segment@now, AUT-1225 Q4)
# =============================================================================
# Canonical Soll = plan_segment@now via Tank.zone_id (+ optional
# tank_subzone_assignments). Read-only projection — no target_ec/target_ph
# columns on Tank, no rule setpoint or sensor threshold involvement.


class TankMeasureTarget(BaseModel):
    """Resolved (or unresolved) target for a single measure at evaluation time."""

    measure: str = Field(..., description="target_ec | target_ph")
    value: Optional[float] = Field(
        None, description="Resolved setpoint value; None if no covering segment"
    )
    unit: Optional[str] = Field(None, description="Unit for the resolved value")
    segment_id: Optional[uuid.UUID] = Field(
        None, description="plan_segments.id of the covering segment, if any"
    )
    from_ts: Optional[datetime] = Field(None, description="Covering segment start (UTC)")
    to_ts: Optional[datetime] = Field(
        None, description="Covering segment end (UTC); None = open-ended"
    )
    resolved_via: str = Field(
        ..., description="How the segment was resolved: zone | subzone | none"
    )


class TankTargetsResponse(BaseModel):
    """Response for GET /v1/tanks/{tank_id}/targets (AUT-1225 Q4)."""

    tank_id: uuid.UUID = Field(..., description="Tank UUID")
    zone_id: str = Field(..., description="Tank's owning zone (zones.zone_id)")
    subzone_config_id: Optional[uuid.UUID] = Field(
        None, description="Subzone used for resolution, if any assignment exists"
    )
    at: datetime = Field(..., description="Evaluation time (UTC)")
    domain: str = Field("nutrient_solution", description="Plan domain evaluated")
    targets: List[TankMeasureTarget] = Field(
        default_factory=list,
        description="Always includes target_ec and target_ph entries",
    )
    assigned_device_ids: List[str] = Field(
        default_factory=list,
        description="ESP device_ids currently assigned to this tank (empty-state helper)",
    )


# =============================================================================
# Tank running volume (Anker + Flow-Delta, AUT-1377 A3)
# =============================================================================
# Display facade over resolve_v_real — typed volume_l only, no name/GPIO guess.


class TankVolumeResponse(BaseModel):
    """Response for GET /v1/tanks/{tank_id}/volume (AUT-1377 / AUT-1563)."""

    tank_id: uuid.UUID = Field(..., description="Tank UUID")
    volume_l: Optional[float] = Field(
        None,
        description=(
            "Running volume (L) from persisted dose_config.volume_l; "
            "None when unresolved (fail-closed)"
        ),
    )
    source: Optional[str] = Field(
        None,
        description="dose_config.volume_l | None if unresolved",
    )
    anchor_liters: Optional[float] = Field(
        None, description="Typed volume_l used as the volume truth"
    )
    flow_delta_l: Optional[float] = Field(
        None, description="Unused after AUT-1563 (GPIO14 is not volume truth)"
    )
    anchor_at: Optional[datetime] = Field(
        None, description="Unused after AUT-1563 (no level-name anchor)"
    )
    level_gpio: Optional[int] = Field(
        None, description="Unused after AUT-1563 (no GPIO guessed as volume)"
    )
    level_device_id: Optional[str] = Field(
        None, description="Unused after AUT-1563 (no level-name device)"
    )
    nominal_volume_l: Optional[float] = Field(
        None,
        description="Tank nominal capacity (L) — NOT the running Ist volume",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description=(
            "Known sensor/model gaps, e.g. drain_not_in_flow (DtW/outflow not in "
            "GPIO14 flow path — no invented subtraction)"
        ),
    )


# =============================================================================
# Nutrient Solution Batch (Ledger)
# =============================================================================


class NutrientBatchCreate(BaseModel):
    """Request schema for appending a ledger entry to a tank."""

    entry_type: str = Field(
        ...,
        description=f"One of: {sorted(_ENTRY_TYPE_SET)}",
    )
    volume_l: float = Field(
        ...,
        ge=0,
        description="Volume in liters this entry represents (≥ 0)",
    )
    components: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Component list. Each item is either product-form "
            '({"kind":"product","name":str,"dose_ml_per_l"|'
            '"dose_g_per_l"|"dose_ml_absolute":float,'
            '"ec_contribution_ms_cm":float?}) or '
            "salt-form "
            '({"kind":"salt","name":str,"conc_g_per_l":float,'
            '"elements":{...}?,"ec_contribution_ms_cm":float?}). '
            "Forms must not be mixed on one item. "
            "AUT-1352: dose_ml_absolute alone is allowed when V_alt unknown. "
            "ec_contribution_ms_cm is optional (entered EC contribution "
            "for the control-anchor check; never auto-derived)."
        ),
    )
    acquisition_method: str = Field(
        ...,
        description=f"One of: {sorted(_ACQUISITION_METHOD_SET)}",
    )
    qualifier: str = Field(
        ...,
        description=f"One of: {sorted(_QUALIFIER_SET)}",
    )
    occurred_at: Optional[datetime] = Field(
        None,
        description="Backdatable wall-clock time (UTC); default = now",
    )
    recipe_label: Optional[str] = Field(
        None,
        max_length=200,
        description="Optional free-text recipe/profile name",
    )
    ec_measured_after: Optional[float] = Field(
        None,
        description="Measured EC (mS/cm) after this entry, if any",
    )
    ec_was_measured: bool = Field(
        False,
        description=(
            "Whether EC was actually measured. Distinguishes "
            "'never measured' from a real 0 reading."
        ),
    )
    ph_measured_after: Optional[float] = Field(
        None,
        description="Measured pH after this entry, if any",
    )
    ph_was_measured: bool = Field(
        False,
        description=(
            "Whether pH was actually measured. Distinguishes "
            "'never measured' from a real 0 reading."
        ),
    )

    @field_validator("entry_type")
    @classmethod
    def validate_entry_type(cls, v: str) -> str:
        if v not in _ENTRY_TYPE_SET:
            raise ValueError(f"entry_type must be one of {sorted(_ENTRY_TYPE_SET)}")
        return v

    @field_validator("acquisition_method")
    @classmethod
    def validate_acquisition_method(cls, v: str) -> str:
        if v not in _ACQUISITION_METHOD_SET:
            raise ValueError(
                f"acquisition_method must be one of {sorted(_ACQUISITION_METHOD_SET)}"
            )
        return v

    @field_validator("qualifier")
    @classmethod
    def validate_qualifier(cls, v: str) -> str:
        if v not in _QUALIFIER_SET:
            raise ValueError(f"qualifier must be one of {sorted(_QUALIFIER_SET)}")
        return v

    @model_validator(mode="after")
    def validate_components_and_measurements(self) -> "NutrientBatchCreate":
        _validate_components(self.components)

        if not self.ec_was_measured and self.ec_measured_after is not None:
            raise ValueError(
                "ec_measured_after must be omitted when ec_was_measured=false"
            )
        if self.ec_was_measured and self.ec_measured_after is None:
            raise ValueError(
                "ec_measured_after is required when ec_was_measured=true"
            )

        if not self.ph_was_measured and self.ph_measured_after is not None:
            raise ValueError(
                "ph_measured_after must be omitted when ph_was_measured=false"
            )
        if self.ph_was_measured and self.ph_measured_after is None:
            raise ValueError(
                "ph_measured_after is required when ph_was_measured=true"
            )

        return self


class NutrientBatchResponse(BaseModel):
    """Response schema for a persisted ledger entry."""

    id: uuid.UUID = Field(..., description="Batch entry UUID")
    tank_id: uuid.UUID = Field(..., description="Owning tank UUID")
    entry_type: str = Field(..., description="Ledger entry type")
    occurred_at: datetime = Field(..., description="When the entry occurred (UTC)")
    created_at: datetime = Field(..., description="Server insert timestamp (UTC)")
    recipe_label: Optional[str] = Field(None, description="Optional recipe label")
    volume_l: float = Field(..., description="Volume in liters")
    components: List[Dict[str, Any]] = Field(
        default_factory=list, description="Component list"
    )
    ec_measured_after: Optional[float] = Field(None, description="EC after entry")
    ec_was_measured: bool = Field(..., description="Whether EC was measured")
    ph_measured_after: Optional[float] = Field(None, description="pH after entry")
    ph_was_measured: bool = Field(..., description="Whether pH was measured")
    acquisition_method: str = Field(..., description="How volume_l was determined")
    qualifier: str = Field(..., description="Confidence qualifier")
    prior_volume_l: Optional[float] = Field(
        None,
        description=(
            "AUT-1346: Tank volume (L) immediately before this entry. "
            "NULL for legacy/unknown rows — never invented."
        ),
    )
    prior_ec_ms_cm: Optional[float] = Field(
        None,
        description=(
            "AUT-1346: Last known EC before this entry (ledger convention). "
            "NULL when unknown."
        ),
    )
    warnings: List[str] = Field(
        default_factory=list,
        description=(
            "AUT-1218: Non-blocking hints (e.g. EC control-anchor drift). "
            "HTTP 2xx is returned regardless — never a reject. Transient; "
            "not persisted on the ledger row."
        ),
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Salt Calculator Assist (AUT-1343 / PKG-01) — read-only expectation
# =============================================================================


class SaltCalculatorAssistRequest(BaseModel):
    """
    Read-only dose-expectation request (AUT-1343).

    Does not persist and does not command actuators. System-EC is the
    operating truth (``current_ec_us_cm``). AUT-1355: concentration is preferably
    resolved from tank pumps (dose_role part_a / part_b); request fields are
    runtime fallback only — never invented by the server.
    """

    current_ec_us_cm: float = Field(
        ...,
        ge=0,
        description="System-EC (µS/cm) — Betriebswahrheit (AUT-1268)",
    )
    target_ec_us_cm: float = Field(
        ...,
        ge=0,
        description="Ziel-EC (µS/cm) from plan_segment or operator assist target",
    )
    concentration: Optional[float] = Field(
        None,
        gt=0,
        description=(
            "AUT-1355: Shared empiric ml→EC fallback when pump A/B unset. "
            "Prefer pump SSOT via tank dose_role; optional."
        ),
    )
    concentration_a: Optional[float] = Field(
        None,
        gt=0,
        description="Optional override for stock A (else pump part_a / shared fallback)",
    )
    concentration_b: Optional[float] = Field(
        None,
        gt=0,
        description="Optional override for stock B (else pump part_b / shared fallback)",
    )
    volume_alt_l: Optional[float] = Field(
        None,
        gt=0,
        description=(
            "Manual V_alt override (L). When omitted, resolved from latest "
            "ledger prior_volume_l / reconstructed volume."
        ),
    )
    volume_zugabe_l: float = Field(
        0.0,
        ge=0,
        description=(
            "Frischwasser-Zugabe (L). >0 = manual override (AUT-1385). "
            "0 = resolve from latest measured fresh_water_refill ledger, else no dilution."
        ),
    )
    ec_wasser_us_cm: Optional[float] = Field(
        None,
        ge=0,
        description=(
            "Frischwasser-EC override (µS/cm). When omitted with volume_zugabe_l>0, "
            "resolved from tank.fresh_water_ec_us_cm — never a silent hardcode."
        ),
    )
    safety_factor: Optional[float] = Field(
        None,
        gt=0,
        description="Optional multiplier passed through to calculate_dose_ml",
    )
    max_delta_per_dose: Optional[float] = Field(
        None,
        gt=0,
        description="Optional AUT-1118 cap (µS/cm) passed to calculate_dose_ml",
    )
    fresh_batch: bool = Field(
        False,
        description=(
            "AUT-1404: explicit Frischbatch mode — dose-up from Frischwasser-EC "
            "instead of measured EC. Not the default for a running tank."
        ),
    )


class SaltCalculatorAssistResponse(BaseModel):
    """Assistenz-Erwartung — keine Betriebswahrheit, keine Dosierung."""

    volume_alt_l: float = Field(..., description="Resolved V_alt (L)")
    volume_alt_source: str = Field(
        ...,
        description=(
            "manual_override | v_real_anchor_flow | v_real_minus_measured_zugabe | "
            "ledger_prior_volume | ledger_reconstructed"
        ),
    )
    volume_zugabe_l: float = Field(..., description="Frischwasser-Zugabe (L)")
    volume_zugabe_source: str = Field(
        ...,
        description="manual | measured | none (AUT-1385)",
    )
    volume_zugabe_occurred_at: Optional[datetime] = Field(
        None,
        description="AUT-1398: when measured refill was recorded (ledger occurred_at)",
    )
    volume_zugabe_label: Optional[str] = Field(
        None,
        description="AUT-1398: human label for measured origin (recipe_label / Nachfüllung)",
    )
    volume_neu_l: float = Field(..., description="V_alt + V_zugabe (L)")
    ec_wasser_us_cm: Optional[float] = Field(
        None,
        description="EC_wasser used (µS/cm); null when no dilution / not configured",
    )
    ec_wasser_source: Optional[str] = Field(
        None,
        description="request_override | tank_config | none",
    )
    ec_after_dilution_us_cm: float = Field(
        ...,
        description="EC' after fresh-water dilution (µS/cm)",
    )
    dose_a_ml: float = Field(..., description="Expected stock A dose (ml), 1:1 share")
    dose_b_ml: float = Field(..., description="Expected stock B dose (ml), 1:1 share")
    expected_ec_us_cm: float = Field(
        ...,
        description="Expected EC after A+B dose (µS/cm); assist only",
    )
    concentration: float = Field(
        ...,
        description="Legacy Spiegel — concentration used for A (AUT-1355: prefer concentration_a/b)",
    )
    concentration_a: Optional[float] = Field(
        None,
        description="AUT-1355: concentration used for stock A (pump part_a or fallback)",
    )
    concentration_b: Optional[float] = Field(
        None,
        description="AUT-1355: concentration used for stock B (pump part_b or fallback)",
    )
    suggestion_kind: str = Field(
        ...,
        description="AUT-1404: dose_up | dilute | within_tolerance | unavailable",
    )
    fresh_water_suggest_l: Optional[float] = Field(
        None,
        description="AUT-1404 Fall 2: suggested Frischwasser liters (null when not dilute)",
    )
    operator_message: str = Field(
        ...,
        description="AUT-1404: Klartext for the operator (direction + reason)",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Non-blocking hints (e.g. V_alt source, assist ≠ truth)",
    )


def _validate_components(components: List[Dict[str, Any]]) -> None:
    """Validate each component is product-form XOR salt-form (not mixed fields)."""
    for idx, raw in enumerate(components):
        if not isinstance(raw, dict):
            raise ValueError(f"components[{idx}] must be an object")

        kind = raw.get("kind")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"components[{idx}].name must be a non-empty string")

        if kind == "product":
            has_ml = "dose_ml_per_l" in raw and raw["dose_ml_per_l"] is not None
            has_g = "dose_g_per_l" in raw and raw["dose_g_per_l"] is not None
            has_abs = (
                "dose_ml_absolute" in raw and raw["dose_ml_absolute"] is not None
            )
            # AUT-1352: logic doses may carry dose_ml_absolute alone when V_alt
            # (hence dose_ml_per_l) is unknown — absolute ml is primary truth (Q2).
            if has_ml and has_g:
                raise ValueError(
                    f"components[{idx}] product form requires exactly one of "
                    "dose_ml_per_l or dose_g_per_l"
                )
            if not has_ml and not has_g and not has_abs:
                raise ValueError(
                    f"components[{idx}] product form requires dose_ml_per_l, "
                    "dose_g_per_l, or dose_ml_absolute"
                )
            if "conc_g_per_l" in raw or "elements" in raw:
                raise ValueError(
                    f"components[{idx}] product form must not include salt fields "
                    "(conc_g_per_l/elements)"
                )
            if has_ml or has_g:
                dose_key = "dose_ml_per_l" if has_ml else "dose_g_per_l"
                dose = raw[dose_key]
                if not isinstance(dose, (int, float)) or isinstance(dose, bool):
                    raise ValueError(f"components[{idx}].{dose_key} must be a number")
                if float(dose) < 0:
                    raise ValueError(f"components[{idx}].{dose_key} must be ≥ 0")
            if has_abs:
                abs_dose = raw["dose_ml_absolute"]
                if not isinstance(abs_dose, (int, float)) or isinstance(abs_dose, bool):
                    raise ValueError(
                        f"components[{idx}].dose_ml_absolute must be a number"
                    )
                if float(abs_dose) < 0:
                    raise ValueError(
                        f"components[{idx}].dose_ml_absolute must be ≥ 0"
                    )

        elif kind == "salt":
            if "dose_ml_per_l" in raw or "dose_g_per_l" in raw:
                raise ValueError(
                    f"components[{idx}] salt form must not include product dose fields"
                )
            conc = raw.get("conc_g_per_l")
            if not isinstance(conc, (int, float)) or isinstance(conc, bool):
                raise ValueError(
                    f"components[{idx}].conc_g_per_l is required and must be a number"
                )
            if float(conc) < 0:
                raise ValueError(f"components[{idx}].conc_g_per_l must be ≥ 0")
            elements = raw.get("elements")
            if elements is not None and not isinstance(elements, dict):
                raise ValueError(
                    f"components[{idx}].elements must be an object when provided"
                )

        else:
            raise ValueError(
                f"components[{idx}].kind must be 'product' or 'salt', got {kind!r}"
            )

        # Optional EC contribution (both forms) — entered value only.
        if "ec_contribution_ms_cm" in raw:
            ec_contrib = raw["ec_contribution_ms_cm"]
            if not isinstance(ec_contrib, (int, float)) or isinstance(ec_contrib, bool):
                raise ValueError(
                    f"components[{idx}].ec_contribution_ms_cm must be a number when provided"
                )
            if float(ec_contrib) < 0:
                raise ValueError(
                    f"components[{idx}].ec_contribution_ms_cm must be ≥ 0"
                )
