"""
Tank Service

AUT-1217 — business logic for tank create, subzone assignment, and
nutrient-solution ledger writes.

Modelled after SubzoneService sensor↔subzone assignment methods (AUT-1155).
No dosing-pump or automation-rule (rule_metadata.dose_config) dependency —
manual bookkeeping must work end-to-end.

AUT-1225 Q4 adds a thin read-only Soll projection (get_targets_at_now):
canonical Soll = plan_segment@now via Tank.zone_id (+ optional subzone via
tank_subzone_assignments). Does NOT touch rule setpoints or sensor
thresholds — see Q1 decision.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import WATER_DOMAIN, domain_allows_tank
from ..core.logging_config import get_logger
from ..db.models.esp import ESPDevice
from ..db.models.nutrient_solution_batch import NutrientSolutionBatch
from ..db.models.plan_segment import PlanSegment
from ..db.models.subzone import SubzoneConfig
from ..db.models.tank import Tank
from ..db.models.tank_subzone_assignment import TankSubzoneAssignment
from ..db.models.zone import Zone
from ..db.repositories.actuator_repo import ActuatorRepository
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.nutrient_solution_batch_repo import NutrientSolutionBatchRepository
from ..db.repositories.plan_segment_repo import PlanSegmentRepository
from ..db.repositories.tank_repo import TankRepository
from ..db.repositories.tank_subzone_assignment_repo import TankSubzoneAssignmentRepository
from ..schemas.tank import (
    NutrientBatchCreate,
    NutrientBatchResponse,
    TankCreate,
    TankDeviceAssignResponse,
    TankMeasureTarget,
    TankResponse,
    TankSubzoneAssignmentInfo,
    TankTargetsResponse,
    TankUpdate,
    TankVolumeResponse,
    SaltCalculatorAssistRequest,
    SaltCalculatorAssistResponse,
)
from ..sensors.dose_calculators.active.ec_control_anchor import check_ec_control_anchor
from ..sensors.dose_calculators.active.salt_calculator_assist import compute_salt_calculator_assist
from .ledger_ec_units import (
    optional_ledger_ms_cm_to_us_cm,
    us_cm_to_ledger_ms_cm,
)
from .tank_volume_truth import resolve_v_real

# AUT-1377: Flow path is refill inflow only (GPIO14) — never invent DtW subtraction.
VOLUME_LIMITATION_DRAIN_NOT_IN_FLOW = "drain_not_in_flow"

logger = get_logger(__name__)

# AUT-1225 Q4: v1 targets domain/measures — mirrors PLAN_DOMAINS/PLAN_MEASURES
# subset actually populated for nutrient_solution (plan_segment.py docstring).
TARGET_DOMAIN = "nutrient_solution"
TARGET_MEASURES: tuple[str, ...] = ("target_ec", "target_ph")
_MEASURE_UNITS: dict[str, str] = {
    # AUT-1268 / E1: plan + sensor + logic use µS/cm (not mS/cm)
    "target_ec": "µS/cm",
    "target_ph": "pH",
}


class TankService:
    """Service for tank / assignment / ledger write operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tank_repo = TankRepository(session)
        self.assignment_repo = TankSubzoneAssignmentRepository(session)
        self.batch_repo = NutrientSolutionBatchRepository(session)
        self.esp_repo = ESPRepository(session)
        self.actuator_repo = ActuatorRepository(session)
        self.plan_segment_repo = PlanSegmentRepository(session)

    async def create_tank(self, data: TankCreate) -> TankResponse:
        """
        Create a tank in an existing zone.

        Raises:
            ValueError: If zone does not exist or volume is invalid
        """
        zone = await self._get_zone(data.zone_id)
        if zone is None:
            raise ValueError(f"Zone '{data.zone_id}' not found")

        if data.nominal_volume_l is not None and data.nominal_volume_l < 0:
            raise ValueError("nominal_volume_l must be ≥ 0")

        tank = await self.tank_repo.create(
            zone_id=data.zone_id,
            name=data.name,
            operation_mode=data.operation_mode,
            nominal_volume_l=data.nominal_volume_l,
            fresh_water_ec_us_cm=data.fresh_water_ec_us_cm,
            fresh_water_ph=data.fresh_water_ph,
        )
        logger.info(
            "Tank created: id=%s name=%s zone_id=%s",
            tank.id,
            tank.name,
            tank.zone_id,
        )
        return TankResponse.model_validate(tank)

    async def update_tank(self, tank_id: uuid.UUID, data: TankUpdate) -> TankResponse:
        """
        Partial update of tank attributes (AUT-1381).

        Raises:
            ValueError: If tank missing or validation fails
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        payload = data.model_dump(exclude_unset=True)
        if "nominal_volume_l" in payload and payload["nominal_volume_l"] is not None:
            if payload["nominal_volume_l"] < 0:
                raise ValueError("nominal_volume_l must be ≥ 0")

        for key, value in payload.items():
            setattr(tank, key, value)
        await self.session.flush()
        await self.session.refresh(tank)
        return TankResponse.model_validate(tank)

    async def list_tanks(self) -> List[TankResponse]:
        """Return all tanks (AUT-1223 Q3 — read-all for device↔tank assignment UI)."""
        tanks = await self.tank_repo.get_all(limit=1000)
        return [TankResponse.model_validate(tank) for tank in tanks]

    async def get_tank(self, tank_id: uuid.UUID) -> Optional[TankResponse]:
        """Return a single tank by id, or None if it does not exist."""
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            return None
        return TankResponse.model_validate(tank)

    async def assign_subzone(
        self,
        tank_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
        assigned_by: Optional[int] = None,
    ) -> TankSubzoneAssignmentInfo:
        """
        Assign a tank to a subzone_config via the n:m junction table.

        Raises:
            ValueError: If tank/subzone missing or already assigned
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        subzone = await self._get_subzone_config(subzone_config_id)
        if subzone is None:
            raise ValueError(f"SubzoneConfig '{subzone_config_id}' not found")

        existing = await self.assignment_repo.get_assignment(
            tank_id=tank_id,
            subzone_config_id=subzone_config_id,
        )
        if existing is not None:
            raise ValueError(
                f"Tank '{tank_id}' is already assigned to " f"subzone_config '{subzone_config_id}'"
            )

        row = await self.assignment_repo.assign(
            tank_id=tank_id,
            subzone_config_id=subzone_config_id,
            assigned_by=assigned_by,
        )
        logger.info(
            "Tank %s assigned to subzone_config %s (assignment id=%s)",
            tank_id,
            subzone_config_id,
            row.id,
        )
        return TankSubzoneAssignmentInfo(
            id=str(row.id),
            tank_id=str(row.tank_id),
            subzone_config_id=str(row.subzone_config_id),
            assigned_at=row.assigned_at.isoformat(),
            assigned_by=row.assigned_by,
        )

    async def remove_subzone(
        self,
        tank_id: uuid.UUID,
        subzone_config_id: uuid.UUID,
    ) -> bool:
        """
        Remove a tank↔subzone assignment.

        Returns:
            True if deleted, False if assignment did not exist

        Raises:
            ValueError: If tank does not exist
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        deleted = await self.assignment_repo.unassign(
            tank_id=tank_id,
            subzone_config_id=subzone_config_id,
        )
        if deleted:
            logger.info(
                "Tank %s removed from subzone_config %s",
                tank_id,
                subzone_config_id,
            )
        return deleted

    # =========================================================================
    # Tank ↔ ESP Device Assignment (n:1, AUT-1223 Q2)
    # =========================================================================
    # Cardinality n:1 via nullable esp_devices.tank_id FK — analogous to
    # ESPDevice.zone_id. NOT the n:m tank_subzone_assignments junction above.

    async def get_devices_for_tank(self, tank_id: uuid.UUID) -> List[ESPDevice]:
        """
        Return all ESP devices currently assigned to a tank.

        Raises:
            ValueError: If tank does not exist
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")
        return await self.esp_repo.get_by_tank_id(tank_id)

    async def get_tank_for_device(self, esp_device_id: str) -> Optional[Tank]:
        """Return the tank an ESP device is currently assigned to, or None."""
        device = await self.esp_repo.get_by_device_id(esp_device_id)
        if device is None or device.tank_id is None:
            return None
        return await self.tank_repo.get_by_id(device.tank_id)

    async def assign_device(
        self,
        tank_id: uuid.UUID,
        esp_device_id: str,
    ) -> TankDeviceAssignResponse:
        """
        Assign an ESP device to a tank (n:1 — replaces any previous assignment).

        Raises:
            ValueError: If tank or device does not exist
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        device = await self.esp_repo.get_by_device_id(esp_device_id)
        if device is None:
            raise ValueError(f"ESP device '{esp_device_id}' not found")

        if not domain_allows_tank(device.domain):
            raise ValueError(
                f"Tank assignment requires domain '{WATER_DOMAIN}' "
                f"(device '{esp_device_id}' has domain {device.domain!r})"
            )

        previous_tank_id = device.tank_id
        device.tank_id = tank.id
        await self.session.flush()
        await self.session.refresh(device)

        logger.info(
            "ESP device %s assigned to tank %s (previous tank=%s)",
            esp_device_id,
            tank_id,
            previous_tank_id,
        )
        return TankDeviceAssignResponse(tank_id=str(tank.id), device_id=device.device_id)

    async def clear_device_assignment(self, esp_device_id: str) -> bool:
        """
        Clear the tank assignment for an ESP device.

        Returns:
            True if a tank assignment existed and was cleared, False otherwise

        Raises:
            ValueError: If device does not exist
        """
        device = await self.esp_repo.get_by_device_id(esp_device_id)
        if device is None:
            raise ValueError(f"ESP device '{esp_device_id}' not found")

        if device.tank_id is None:
            return False

        device.tank_id = None
        await self.session.flush()
        await self.session.refresh(device)

        logger.info("Tank assignment cleared for ESP device %s", esp_device_id)
        return True

    async def create_batch(
        self,
        tank_id: uuid.UUID,
        data: NutrientBatchCreate,
    ) -> NutrientBatchResponse:
        """
        Append a ledger entry for a tank.

        Persists first, then runs the non-blocking EC control-anchor check
        (AUT-1218). Drift warnings are returned on the response only —
        they never block or roll back the ledger write.

        AUT-1346: derives ``prior_volume_l`` / ``prior_ec_ms_cm`` from existing
        ledger history when possible (nullable — never invented/backfilled).

        AUT-1350 (U1) — Ledger EC boundary:
        API + DB remain ledger-native **mS/cm** (``*_ms_cm`` fields). Cross to
        operational µS/cm ONLY via ``ledger_ec_units`` /
        ``read_ledger_prior_ec_us_cm`` / ``to_ledger_ec_ms_cm``. No inline ×1000.

        Raises:
            ValueError: If tank missing (schema validators cover field rules)
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        # Ledger-native mS/cm (same unit as NutrientBatchCreate / anchor).
        prior_volume_l, prior_ec_ms_cm = await self._derive_prior_state(tank_id)

        # Schema already validated entry_type / components / acquisition /
        # qualifier / measurement consistency. Persist first (anchor must
        # never prevent the write).
        row: NutrientSolutionBatch = await self.batch_repo.create_entry(
            tank_id=tank_id,
            entry_type=data.entry_type,
            volume_l=data.volume_l,
            components=list(data.components),
            acquisition_method=data.acquisition_method,
            qualifier=data.qualifier,
            occurred_at=data.occurred_at,
            recipe_label=data.recipe_label,
            ec_measured_after=data.ec_measured_after,
            ec_was_measured=data.ec_was_measured,
            ph_measured_after=data.ph_measured_after,
            ph_was_measured=data.ph_was_measured,
            prior_volume_l=prior_volume_l,
            prior_ec_ms_cm=prior_ec_ms_cm,
        )
        # AUT-1218: fail-open EC control anchor AFTER persist (response only).
        # AUT-1346: pass prior_* when known (defaults remain 0/None-safe).
        # Anchor stays in ledger mS (same side of AUT-1350 boundary).
        warnings = await check_ec_control_anchor(
            session=self.session,
            components=list(data.components),
            volume_l=data.volume_l,
            ec_measured_after=data.ec_measured_after,
            ec_was_measured=data.ec_was_measured,
            prior_volume_l=prior_volume_l if prior_volume_l is not None else 0.0,
            prior_ec_ms_cm=prior_ec_ms_cm,
        )
        logger.info(
            "Ledger entry created: id=%s tank_id=%s entry_type=%s " "prior_volume_l=%s warnings=%d",
            row.id,
            tank_id,
            row.entry_type,
            prior_volume_l,
            len(warnings),
        )
        response = NutrientBatchResponse.model_validate(row)
        response.warnings = warnings
        return response

    async def _resolve_pump_concentrations(
        self, tank_id: uuid.UUID
    ) -> Tuple[Optional[float], Optional[float], List[str]]:
        """
        AUT-1355: Resolve stock A/B concentration from tank-assigned pumps
        via ``dose_role`` (part_a / part_b). No backfill — NULL when unset.
        """
        notes: List[str] = []
        conc_a: Optional[float] = None
        conc_b: Optional[float] = None
        devices = await self.esp_repo.get_by_tank_id(tank_id)
        for device in devices:
            actuators = await self.actuator_repo.get_by_esp(device.id)
            for act in actuators:
                role = (act.dose_role or "").strip().lower()
                value = act.concentration
                if value is None or value <= 0:
                    continue
                if role == "part_a" and conc_a is None:
                    conc_a = float(value)
                    notes.append(
                        f"concentration_a from pump {device.device_id}:GPIO{act.gpio} (dose_role=part_a)"
                    )
                elif role == "part_b" and conc_b is None:
                    conc_b = float(value)
                    notes.append(
                        f"concentration_b from pump {device.device_id}:GPIO{act.gpio} (dose_role=part_b)"
                    )
        return conc_a, conc_b, notes

    async def compute_dose_assist(
        self,
        tank_id: uuid.UUID,
        data: SaltCalculatorAssistRequest,
    ) -> SaltCalculatorAssistResponse:
        """
        AUT-1343: read-only salt calculator feedforward expectation.

        Resolves V_alt from request override or ledger prior/reconstruction,
        dilutes with EC_wasser, then calls ``calculate_dose_ml`` (A:B 1:1).
        Never persists and never commands actuators.

        AUT-1355: concentration A/B from tank pumps (dose_role); request fields
        are runtime fallback only.

        AUT-1385: ``volume_zugabe_l`` from request override (>0) or latest
        ``fresh_water_refill`` ledger row; when measured zugabe meets post-fill
        V_real, V_alt becomes V_neu − zugabe (no double-count).

        Raises:
            ValueError: tank missing, V_alt unresolved, or calculator input error
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        (
            volume_zugabe_l,
            volume_zugabe_source,
            volume_zugabe_occurred_at,
            volume_zugabe_label,
        ) = await self._resolve_volume_zugabe(tank_id, data.volume_zugabe_l)
        volume_alt_l, volume_alt_source, resolve_notes = await self._resolve_volume_alt(
            tank_id, data.volume_alt_l
        )
        # Retrospektive Nachfüllung: V_real is post-fill (~20 L). Mixing mass
        # balance requires V_alt = V_neu − zugabe, not V_alt = V_neu.
        if (
            volume_zugabe_source == "measured"
            and volume_zugabe_l > 0
            and volume_alt_source == "v_real_anchor_flow"
            and volume_alt_l > volume_zugabe_l
        ):
            volume_alt_l = float(volume_alt_l) - float(volume_zugabe_l)
            volume_alt_source = "v_real_minus_measured_zugabe"
            resolve_notes.append(
                f"V_alt = V_real − measured zugabe ({volume_zugabe_l} L) "
                "(AUT-1385 no double-count)"
            )

        pump_a, pump_b, pump_notes = await self._resolve_pump_concentrations(tank_id)
        # Precedence: explicit request override → pump SSOT → shared request fallback.
        concentration_a = data.concentration_a if data.concentration_a is not None else pump_a
        concentration_b = data.concentration_b if data.concentration_b is not None else pump_b
        if concentration_a is None:
            concentration_a = data.concentration
        if concentration_b is None:
            concentration_b = data.concentration

        ec_wasser, ec_wasser_source = self._resolve_ec_wasser(
            tank, data.ec_wasser_us_cm, volume_zugabe_l
        )

        # AUT-1404 D3: Fall-3 Totband = covering plan_segment.tolerance (no magic).
        ec_tolerance_us_cm = await self._resolve_target_ec_tolerance(tank)

        result = compute_salt_calculator_assist(
            current_ec_us_cm=data.current_ec_us_cm,
            target_ec_us_cm=data.target_ec_us_cm,
            volume_alt_l=volume_alt_l,
            concentration_a=concentration_a,
            concentration_b=concentration_b,
            volume_zugabe_l=volume_zugabe_l,
            ec_wasser_us_cm=ec_wasser,
            safety_factor=data.safety_factor,
            max_delta_per_dose=data.max_delta_per_dose,
            fresh_batch=bool(data.fresh_batch),
            ec_tolerance_us_cm=ec_tolerance_us_cm,
        )
        # AUT-1404: operator-facing Klartext only — drop GPIO/dose_role diagnostic notes.
        notes = list(result["notes"])
        if volume_zugabe_source == "measured":
            notes.append("Gemessene Frischwasser-Nachfüllung eingerechnet.")
        return SaltCalculatorAssistResponse(
            volume_alt_l=result["volume_alt_l"],
            volume_alt_source=volume_alt_source,
            volume_zugabe_l=result["volume_zugabe_l"],
            volume_zugabe_source=volume_zugabe_source,
            volume_zugabe_occurred_at=volume_zugabe_occurred_at,
            volume_zugabe_label=volume_zugabe_label,
            volume_neu_l=result["volume_neu_l"],
            ec_wasser_us_cm=result["ec_wasser_us_cm"],
            ec_wasser_source=ec_wasser_source,
            ec_after_dilution_us_cm=result["ec_after_dilution_us_cm"],
            dose_a_ml=result["dose_a_ml"],
            dose_b_ml=result["dose_b_ml"],
            expected_ec_us_cm=result["expected_ec_us_cm"],
            concentration=result["concentration"],
            concentration_a=result.get("concentration_a"),
            concentration_b=result.get("concentration_b"),
            suggestion_kind=result["suggestion_kind"],
            fresh_water_suggest_l=result.get("fresh_water_suggest_l"),
            operator_message=result["operator_message"],
            notes=notes,
        )

    async def read_ledger_prior_ec_us_cm(self, tank_id: uuid.UUID) -> Optional[float]:
        """
        AUT-1350: Assist/composition **read** boundary.

        Ledger stores mS/cm → convert once via ``ledger_ec_units`` to µS/cm.
        Does not invent values; returns None when ledger has no measured EC.
        """
        _volume, prior_ec_ms_cm = await self._derive_prior_state(tank_id)
        return optional_ledger_ms_cm_to_us_cm(prior_ec_ms_cm)

    @staticmethod
    def to_ledger_ec_ms_cm(us_cm: float) -> float:
        """
        AUT-1350: **write** boundary — operational µS/cm → Ledger mS/cm.

        Use before persisting EC that originated in the µS/cm SSOT world
        (e.g. future Logic→Ledger). Batch API fields that are already mS
        must NOT pass through this helper again.
        """
        return us_cm_to_ledger_ms_cm(us_cm)

    async def _derive_prior_state(
        self, tank_id: uuid.UUID
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        AUT-1346: prior volume/EC before a new ledger write.

        Returns ``(prior_volume_l, prior_ec_ms_cm)`` in **ledger-native mS/cm**.
        Operational µS readers must use ``read_ledger_prior_ec_us_cm`` (AUT-1350).
        Returns (None, None) when history cannot provide a value — never invents.
        """
        entries = await self.batch_repo.get_by_tank(tank_id, limit=500)
        prior_volume = self._reconstruct_volume_l(entries)
        prior_ec: Optional[float] = None
        for entry in entries:  # newest first
            if entry.ec_was_measured and entry.ec_measured_after is not None:
                prior_ec = entry.ec_measured_after
                break
        return prior_volume, prior_ec

    @staticmethod
    def _resolve_ec_wasser(
        tank: Tank,
        request_override: Optional[float],
        volume_zugabe_l: float = 0.0,
    ) -> Tuple[Optional[float], str]:
        """
        AUT-1381 / AUT-1404: Frischwasser-EC — request override → tank field → none.

        Always resolve when tank has a value (needed for Fall-2 dilute / Frischbatch).
        No silent DEFAULT_EC_WASSER. Dilution with missing EC fails in assist.
        ``volume_zugabe_l`` retained for call-site compatibility (unused).
        """
        _ = volume_zugabe_l
        if request_override is not None and request_override >= 0:
            return float(request_override), "request_override"
        if tank.fresh_water_ec_us_cm is not None and tank.fresh_water_ec_us_cm >= 0:
            return float(tank.fresh_water_ec_us_cm), "tank_config"
        return None, "none"

    async def _resolve_target_ec_tolerance(self, tank: Tank) -> float:
        """
        AUT-1404 D3: Fall-3 Totband from covering plan_segment.tolerance.

        Returns 0.0 when no segment or tolerance unset — never invents a band.
        """
        subzone_config_id = await self._pick_subzone_for_targets(tank.id)
        segment = await self.plan_segment_repo.resolve_at(
            zone_id=tank.zone_id,
            domain=TARGET_DOMAIN,
            measure="target_ec",
            at=datetime.now(timezone.utc),
            subzone_config_id=subzone_config_id,
        )
        if segment is None or segment.tolerance is None:
            return 0.0
        return max(0.0, float(segment.tolerance))

    async def _resolve_volume_zugabe(
        self,
        tank_id: uuid.UUID,
        override: float,
    ) -> Tuple[float, str, Optional[datetime], Optional[str]]:
        """
        AUT-1385: Frischwasser-Zugabe for Assist.

        Precedence: request override (>0) → latest ledger ``fresh_water_refill``
        → 0 (none). Never invents a volume. Assist formula unchanged — only input.

        AUT-1398: also returns occurred_at + label for FE origin display.
        """
        if override is not None and float(override) > 0:
            return float(override), "manual", None, None

        entries = await self.batch_repo.get_by_tank(tank_id, limit=50)
        for entry in entries:
            if entry.entry_type != "fresh_water_refill":
                continue
            if entry.volume_l is not None and float(entry.volume_l) > 0:
                label = entry.recipe_label or "Nachfüllung"
                occurred = entry.occurred_at
                return float(entry.volume_l), "measured", occurred, str(label)
        return 0.0, "none", None, None

    async def _resolve_volume_alt(
        self,
        tank_id: uuid.UUID,
        override: Optional[float],
    ) -> Tuple[float, str, List[str]]:
        """
        Resolve V_alt (AUT-1381):
        manual override → V_real (Anker±Flow, A3) → ledger reconstruct → prior.
        """
        notes: List[str] = []
        if override is not None and override > 0:
            return override, "manual_override", notes

        # AUT-1377 / AUT-1381: running volume before ledger/nominal guesswork.
        truth = await resolve_v_real(self.session, tank_id)
        if truth is not None and truth.volume_l is not None and truth.volume_l > 0:
            notes.append(f"V_real via {truth.source}")
            return float(truth.volume_l), "v_real_anchor_flow", notes

        # Same value create_batch would persist as prior_volume_l for a new row.
        prior_volume_l, _prior_ec = await self._derive_prior_state(tank_id)
        if prior_volume_l is not None and prior_volume_l > 0:
            return prior_volume_l, "ledger_reconstructed", notes

        entries = await self.batch_repo.get_by_tank(tank_id, limit=100)
        for entry in entries:
            if entry.prior_volume_l is not None and entry.prior_volume_l > 0:
                return entry.prior_volume_l, "ledger_prior_volume", notes

        raise ValueError(
            "V_alt unresolved: provide volume_alt_l override, configure "
            "level-anchor+flow (V_real), or ledger prior_volume_l / volume history"
        )

    @staticmethod
    def _reconstruct_volume_l(
        entries_newest_first: List[NutrientSolutionBatch],
    ) -> Optional[float]:
        """
        Reconstruct tank volume from ledger since the latest full_reset.

        Returns None when no volume-bearing history exists.
        """
        if not entries_newest_first:
            return None

        chrono = list(reversed(entries_newest_first))
        start = 0
        for idx, entry in enumerate(chrono):
            if entry.entry_type == "full_reset":
                start = idx
        chrono = chrono[start:]

        volume: Optional[float] = None
        for entry in chrono:
            if entry.entry_type == "full_reset":
                volume = float(entry.volume_l)
            elif entry.entry_type in ("top_up_dose", "fresh_water_refill"):
                if volume is None:
                    volume = float(entry.volume_l)
                else:
                    volume += float(entry.volume_l)
            elif entry.entry_type == "withdrawal":
                if volume is None:
                    continue
                volume = max(0.0, volume - float(entry.volume_l))
            # remeasurement_only / system_incident: no volume change
        return volume

    # =========================================================================
    # Targets: canonical Soll from plan_segment@now (n:1, AUT-1225 Q4)
    # =========================================================================
    # Read-only projection. Canonical Soll = plan_segment@now via
    # Tank.zone_id (+ optional subzone via tank_subzone_assignments). No
    # target_ec/target_ph columns exist on Tank; rule setpoints and sensor
    # thresholds are untouched (Q1 decision).

    async def get_volume_truth(self, tank_id: uuid.UUID) -> TankVolumeResponse:
        """
        AUT-1377: running tank volume for display (Anker ± Flow-Delta).

        Reuses ``resolve_v_real`` (same helper as K2 auto-cal). Fail-closed:
        ``volume_l=None`` when unresolved. Always advertises
        ``drain_not_in_flow`` — outflow/DtW is not on the GPIO14 flow path.

        Raises:
            ValueError: If tank does not exist
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        limitations: List[str] = [VOLUME_LIMITATION_DRAIN_NOT_IN_FLOW]
        truth = await resolve_v_real(self.session, tank_id)
        if truth is None:
            return TankVolumeResponse(
                tank_id=tank.id,
                volume_l=None,
                source=None,
                anchor_liters=None,
                flow_delta_l=None,
                anchor_at=None,
                level_gpio=None,
                level_device_id=None,
                nominal_volume_l=tank.nominal_volume_l,
                limitations=limitations,
            )

        return TankVolumeResponse(
            tank_id=tank.id,
            volume_l=truth.volume_l,
            source=truth.source,
            anchor_liters=truth.anchor_liters,
            flow_delta_l=truth.flow_delta_l,
            anchor_at=truth.anchor_at,
            level_gpio=truth.level_gpio,
            level_device_id=truth.level_device_id,
            nominal_volume_l=tank.nominal_volume_l,
            limitations=limitations,
        )

    async def get_targets_at_now(self, tank_id: uuid.UUID) -> TankTargetsResponse:
        """
        Resolve the current (now) target_ec / target_ph Soll for a tank.

        Resolution:
        1. Load tank (404/ValueError if missing).
        2. Pick the first tank↔subzone assignment (ordered by assigned_at
           asc, id asc for determinism), if any — used as the optional
           subzone_config_id for PlanSegmentRepository.resolve_at.
        3. For each of target_ec / target_ph, resolve the covering
           plan_segment at "now" (UTC). Missing segment → value=None,
           resolved_via="none".

        Raises:
            ValueError: If tank does not exist
        """
        tank = await self.tank_repo.get_by_id(tank_id)
        if tank is None:
            raise ValueError(f"Tank '{tank_id}' not found")

        subzone_config_id = await self._pick_subzone_for_targets(tank_id)
        now = datetime.now(timezone.utc)

        targets: List[TankMeasureTarget] = []
        for measure in TARGET_MEASURES:
            segment = await self.plan_segment_repo.resolve_at(
                zone_id=tank.zone_id,
                domain=TARGET_DOMAIN,
                measure=measure,
                at=now,
                subzone_config_id=subzone_config_id,
            )
            targets.append(await self._to_measure_target(measure, segment, subzone_config_id))

        devices = await self.esp_repo.get_by_tank_id(tank_id)
        return TankTargetsResponse(
            tank_id=tank.id,
            zone_id=tank.zone_id,
            subzone_config_id=subzone_config_id,
            at=now,
            domain=TARGET_DOMAIN,
            targets=targets,
            assigned_device_ids=[d.device_id for d in devices],
        )

    async def _pick_subzone_for_targets(self, tank_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Deterministically pick one subzone assignment (assigned_at asc, id asc)."""
        assignments: List[TankSubzoneAssignment] = await self.assignment_repo.get_by_tank(tank_id)
        if not assignments:
            return None
        first = min(assignments, key=lambda a: (a.assigned_at, str(a.id)))
        return first.subzone_config_id

    async def _to_measure_target(
        self,
        measure: str,
        segment: Optional[PlanSegment],
        subzone_config_id: Optional[uuid.UUID],
    ) -> TankMeasureTarget:
        """Map a resolved (or missing) PlanSegment to a TankMeasureTarget."""
        if segment is None:
            return TankMeasureTarget(
                measure=measure,
                value=None,
                unit=None,
                segment_id=None,
                from_ts=None,
                to_ts=None,
                resolved_via="none",
            )

        resolved_via = "zone"
        if subzone_config_id is not None:
            assigned_ids = await self.plan_segment_repo.get_subzone_assignment_ids(segment.id)
            if subzone_config_id in assigned_ids:
                resolved_via = "subzone"

        return TankMeasureTarget(
            measure=measure,
            value=segment.value,
            unit=_MEASURE_UNITS.get(measure),
            segment_id=segment.id,
            from_ts=segment.from_ts,
            to_ts=segment.to_ts,
            resolved_via=resolved_via,
        )

    async def _get_zone(self, zone_id: str) -> Optional[Zone]:
        result = await self.session.execute(select(Zone).where(Zone.zone_id == zone_id))
        return result.scalar_one_or_none()

    async def _get_subzone_config(self, subzone_config_id: uuid.UUID) -> Optional[SubzoneConfig]:
        result = await self.session.execute(
            select(SubzoneConfig).where(SubzoneConfig.id == subzone_config_id)
        )
        return result.scalar_one_or_none()
