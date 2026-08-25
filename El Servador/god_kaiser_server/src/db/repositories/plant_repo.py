"""
Plant Repository: CRUD + lookup methods for the Plant entity.

AUT-222 — Phyta Plants Schema. Pattern parallels :class:`ESPRepository`:
soft-delete-aware listing helpers and explicit ``include_deleted`` flags
on lookups.
"""

import uuid
from datetime import datetime, time, timezone
from typing import NamedTuple, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.nutrient_solution_batch import NutrientSolutionBatch
from ..models.plant import Plant, PlantLifecycleEvent
from ..models.sensor import SensorData
from ..models.tank_subzone_assignment import TankSubzoneAssignment
from ..models.zone import Zone
from .base_repo import BaseRepository


class ZonePhaseHistograms(NamedTuple):
    """Both phase-axis histograms for a single zone.

    AUT-1194: Two-axis zone plant summary.  Returned by
    :meth:`PlantRepository.get_zone_phase_histogram` so that callers always
    receive both axes and the axis-identity of each histogram is unambiguous
    in the field name.

    Attributes:
        light_growth: Phase-count mapping for the light/growth axis
            (``Plant.phase`` column).  Every active plant in the zone
            contributes exactly one entry.
        nutrient: Phase-count mapping for the nutrient/fertilizer axis
            (``Plant.nutrient_phase`` column, AUT-1183).  Only plants with
            a non-NULL ``nutrient_phase`` are counted; plants that predate
            AUT-1183 or have never had a nutrient-phase event are excluded.
    """

    light_growth: dict[str, int]
    nutrient: dict[str, int]


# AUT-981 — Late-Binding plant-subzone occupancy. Events of these types mark
# entry/exit of a plant's *current* subzone; see ``_plant_occupies_at``.
_OCCUPANCY_OPEN_EVENT_TYPES = frozenset({"transplanted", "subzone_moved"})
_OCCUPANCY_CLOSE_EVENT_TYPES = frozenset({"harvest_completed", "archived"})


class PlantRepository(BaseRepository[Plant]):
    """
    Plant Repository with plant-specific queries.

    Extends BaseRepository with QR code / external ID lookups and
    soft-delete-aware listing.

    Soft-Delete:
    - All listing methods exclude soft-deleted plants by default.
    - ``include_deleted=True`` is provided for audit / admin queries.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Plant, session)

    @staticmethod
    def _not_deleted():
        """Filter clause to exclude soft-deleted plants."""
        return Plant.deleted_at.is_(None)

    @staticmethod
    def effective_zone_id_expr():
        """
        Single SQL expression for a plant's effective zone (AUT-1073).

        ``COALESCE(subzone_configs.parent_zone_id, plants.zone_id)``

        Ortseinheit parent wins when present; ``plants.zone_id`` is the
        fallback for direct zone assignment (or zoneless Ortseinheit).
        Requires ``SubzoneConfig`` in the statement's FROM/JOIN
        (typically ``OUTER JOIN`` on ``Plant.subzone_id``).

        All zone-scoped plant queries (list filter, phase histogram, phi2
        aggregate) MUST use this helper — do not inline a second copy.
        """
        from ..models.subzone import SubzoneConfig

        return func.coalesce(SubzoneConfig.parent_zone_id, Plant.zone_id)

    @staticmethod
    def resolve_effective_zone_id(plant: Plant) -> Optional[str]:
        """
        Python mirror of :meth:`effective_zone_id_expr` for response mapping.

        Same COALESCE semantics without a SQL join — uses the eagerly
        loaded ``plant.subzone`` relationship when present.
        """
        subzone_parent = plant.subzone.parent_zone_id if plant.subzone is not None else None
        if subzone_parent is not None:
            return subzone_parent
        return plant.zone_id

    async def get_by_plant_id(
        self,
        plant_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its primary key.

        Args:
            plant_id: Plant UUID.
            include_deleted: If True, also return soft-deleted plants.

        Returns:
            ``Plant`` instance or ``None`` if not found.
        """
        stmt = select(Plant).options(selectinload(Plant.subzone)).where(Plant.plant_id == plant_id)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_qr_code(
        self,
        qr_code: str,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its QR code (e.g. ``PL-A1B2C3D4``).

        QR codes are unique per ``(kaiser_id, qr_code)`` for active rows;
        for lookup we treat the code as globally unique among active plants.
        """
        stmt = select(Plant).where(Plant.qr_code == qr_code)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self,
        external_id: str,
        kaiser_id: Optional[str] = None,
        *,
        include_deleted: bool = False,
    ) -> Optional[Plant]:
        """
        Get a plant by its ``external_plant_id``.

        Args:
            external_id: External plant ID (PhotosynQ etc.).
            kaiser_id: Optional tenant filter.
            include_deleted: If True, also return soft-deleted plants.
        """
        conditions = [Plant.external_plant_id == external_id]
        if kaiser_id is not None:
            conditions.append(Plant.kaiser_id == kaiser_id)
        if not include_deleted:
            conditions.append(self._not_deleted())

        stmt = select(Plant).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(
        self,
        kaiser_id: Optional[str] = None,
        phase: Optional[str] = None,
        nutrient_phase: Optional[str] = None,
        zone_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Plant]:
        """
        List active (non-soft-deleted) plants.

        Args:
            kaiser_id: Optional tenant filter.
            phase: Optional light/growth phase filter (e.g. ``'veg-frueh'``).
            nutrient_phase: Optional nutrient/fertilizer phase filter (AUT-1183).
            zone_id: Optional effective-zone filter (AUT-1073) — matches
                ``COALESCE(subzone.parent_zone_id, plant.zone_id)``.
            skip: Pagination offset.
            limit: Maximum number of rows.
        """
        from ..models.subzone import SubzoneConfig

        conditions = [self._not_deleted()]
        if kaiser_id is not None:
            conditions.append(Plant.kaiser_id == kaiser_id)
        if phase is not None:
            conditions.append(Plant.phase == phase)
        if nutrient_phase is not None:
            conditions.append(Plant.nutrient_phase == nutrient_phase)

        stmt = select(Plant).options(selectinload(Plant.subzone))
        # OUTER JOIN so plants with only plants.zone_id (no Ortseinheit)
        # still match the effective-zone filter (AUT-1073).
        if zone_id is not None:
            stmt = stmt.outerjoin(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            conditions.append(self.effective_zone_id_expr() == zone_id)

        stmt = (
            stmt.where(and_(*conditions))
            .order_by(Plant.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_zone_names_by_id(self, zone_ids: set[str]) -> dict[str, str]:
        """Return display names for the provided parent zone identifiers."""
        if not zone_ids:
            return {}

        stmt = select(Zone.zone_id, Zone.name).where(Zone.zone_id.in_(zone_ids))
        result = await self.session.execute(stmt)
        return {zone_id: name for zone_id, name in result.all()}

    async def get_sensor_data_for_plant(
        self,
        plant_id: uuid.UUID,
        cutoff: datetime,
        limit: int,
    ) -> list[SensorData]:
        """
        Get sensor_data rows for a plant within a time window.

        Args:
            plant_id: Plant UUID (matches ``sensor_data.plant_id``).
            cutoff: Earliest timestamp to include (inclusive).
            limit: Maximum number of rows to return (newest first).

        Returns:
            List of ``SensorData`` instances ordered by timestamp descending.
        """
        stmt = (
            select(SensorData)
            .where(
                and_(
                    SensorData.plant_id == plant_id,
                    SensorData.timestamp >= cutoff,
                )
            )
            .order_by(SensorData.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_zone_phase_histogram(
        self,
        zone_id: str,
    ) -> ZonePhaseHistograms:
        """
        Return phase-count histograms for **both** phase axes for all active
        plants in a zone.

        AUT-1194: Extended from the original single-axis implementation so
        that callers always receive both the light/growth axis and the
        nutrient/fertilizer axis (AUT-1183).  The field names in the returned
        :class:`ZonePhaseHistograms` NamedTuple make the axis identity
        unambiguous — the ``light_growth`` key is always the light/growth
        axis, ``nutrient`` is always the nutrient/fertilizer axis.

        Plants are resolved via :meth:`effective_zone_id_expr`
        (``COALESCE(subzone.parent_zone_id, plant.zone_id)``, AUT-1073).
        Only non-soft-deleted plants are counted. Plants with a direct
        ``plants.zone_id`` and no Ortseinheit are included.

        NOTE (AUT-1156 / AUT-1073): plants in Ortseinheiten with
        ``parent_zone_id=NULL`` and without a direct ``plants.zone_id``
        remain excluded from zone-scoped aggregates until one of those
        is set. No data is lost.

        Args:
            zone_id: Zone identifier string.

        Returns:
            :class:`ZonePhaseHistograms` with two dicts:
            - ``light_growth``: ``phase`` (str) → count (int), light/growth axis.
            - ``nutrient``: ``nutrient_phase`` (str) → count (int), nutrient axis.
              Empty when no plant in the zone has a non-NULL ``nutrient_phase``.
        """
        from ..models.subzone import SubzoneConfig

        effective_zone = self.effective_zone_id_expr()

        # ── Light/growth axis (Plant.phase — non-nullable, every plant counted) ──
        light_stmt = (
            select(Plant.phase, func.count(Plant.plant_id))
            .outerjoin(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(
                and_(
                    effective_zone == zone_id,
                    Plant.deleted_at.is_(None),
                )
            )
            .group_by(Plant.phase)
        )
        light_result = await self.session.execute(light_stmt)
        light_growth: dict[str, int] = {phase: int(count) for phase, count in light_result.all()}

        # ── Nutrient/fertilizer axis (Plant.nutrient_phase — nullable, AUT-1183) ──
        # Only plants with an explicitly set nutrient_phase are counted; plants
        # that predate AUT-1183 or have never had a nutrient_phase_changed event
        # will have NULL and are excluded from this histogram.
        nutrient_stmt = (
            select(Plant.nutrient_phase, func.count(Plant.plant_id))
            .outerjoin(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(
                and_(
                    effective_zone == zone_id,
                    Plant.deleted_at.is_(None),
                    Plant.nutrient_phase.isnot(None),
                )
            )
            .group_by(Plant.nutrient_phase)
        )
        nutrient_result = await self.session.execute(nutrient_stmt)
        nutrient: dict[str, int] = {phase: int(count) for phase, count in nutrient_result.all()}

        return ZonePhaseHistograms(light_growth=light_growth, nutrient=nutrient)

    async def get_zone_avg_phi2(
        self,
        zone_id: str,
        phi2_sensor_type: str,
        cutoff: datetime,
    ) -> Optional[float]:
        """
        Return the average ``processed_value`` of phi2 sensor readings for
        plants in a given zone over a time window.

        Uses a subquery to collect relevant plant IDs first, then aggregates
        ``sensor_data`` to avoid accidental cross-products.

        Args:
            zone_id: Zone identifier string.
            phi2_sensor_type: ``sensor_type`` value to filter on (e.g. ``"phi2"``).
            cutoff: Only include readings at or after this timestamp.

        Returns:
            Average as ``float`` or ``None`` if no matching rows exist.
        """
        from ..models.subzone import SubzoneConfig

        # AUT-1073: same effective-zone expression as histogram / list filter.
        plant_id_stmt = (
            select(Plant.plant_id)
            .outerjoin(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(
                and_(
                    self.effective_zone_id_expr() == zone_id,
                    Plant.deleted_at.is_(None),
                )
            )
        )
        avg_stmt = select(func.avg(SensorData.processed_value)).where(
            and_(
                SensorData.plant_id.in_(plant_id_stmt),
                SensorData.sensor_type == phi2_sensor_type,
                SensorData.timestamp >= cutoff,
                SensorData.processed_value.isnot(None),
            )
        )
        result = await self.session.execute(avg_stmt)
        avg_value = result.scalar_one_or_none()
        return float(avg_value) if avg_value is not None else None

    @staticmethod
    def _plant_occupies_at(plant: Plant, ts: datetime) -> bool:
        """
        Whether ``plant`` occupied its *current* subzone at ``ts``.

        Sweeps ``transplanted``/``subzone_moved`` (open) and
        ``harvest_completed``/``archived`` (close) lifecycle events in
        chronological order and returns the occupancy state at ``ts``
        (half-open: an open event at ``ts`` counts as occupied, a close
        event at ``ts`` does not). Plants without any lifecycle events
        fall back to ``planting_date``/``deleted_at``.

        AUT-1207: only ``event_status == 'occurred'`` events count towards
        occupancy — planned, reverted, and test-data events must never
        affect derived plant state, same principle as
        :meth:`get_plant_phase_at`.
        """
        events = [e for e in plant.lifecycle_events if e.event_status == "occurred"]
        if not events:
            if plant.planting_date is None:
                return plant.deleted_at is None or plant.deleted_at >= ts
            start = datetime.combine(plant.planting_date, time.min, tzinfo=timezone.utc)
            if ts < start:
                return False
            return plant.deleted_at is None or plant.deleted_at >= ts

        boundaries = [
            (event.event_timestamp, event.event_type in _OCCUPANCY_OPEN_EVENT_TYPES)
            for event in events
            if event.event_type in _OCCUPANCY_OPEN_EVENT_TYPES
            or event.event_type in _OCCUPANCY_CLOSE_EVENT_TYPES
        ]
        if not any(is_open for _, is_open in boundaries):
            if plant.planting_date is not None:
                start = datetime.combine(plant.planting_date, time.min, tzinfo=timezone.utc)
                boundaries.insert(0, (start, True))
        boundaries.sort(key=lambda boundary: boundary[0])

        occupied = False
        for boundary_ts, is_open in boundaries:
            if boundary_ts > ts:
                break
            occupied = is_open
        return occupied

    async def get_plant_for_sensor_reading(
        self,
        sensor_subzone_id: str,
        measurement_ts: datetime,
    ) -> Optional[Plant]:
        """
        Late-Binding: resolve the plant occupying ``sensor_subzone_id`` at
        ``measurement_ts`` (query-time join, never written at ingest — see
        AUT-1081/AUT-981).

        Joins the subzone string bridge (``Plant.subzone_id`` ->
        ``SubzoneConfig.id`` -> ``SubzoneConfig.subzone_id``) to find
        candidate plants currently located in that subzone, then filters by
        occupancy at ``measurement_ts`` via :meth:`_plant_occupies_at`.

        Returns ``None`` when no plant matches or when more than one plant
        matches (ambiguous — data integrity issue rather than a guess).
        """
        from ..models.subzone import SubzoneConfig

        stmt = (
            select(Plant)
            .join(SubzoneConfig, SubzoneConfig.id == Plant.subzone_id)
            .where(SubzoneConfig.subzone_id == sensor_subzone_id)
            .options(selectinload(Plant.lifecycle_events))
        )
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()

        matches = [plant for plant in candidates if self._plant_occupies_at(plant, measurement_ts)]
        if len(matches) != 1:
            return None
        return matches[0]

    async def get_plant_phase_at(
        self,
        plant_id: uuid.UUID,
        measurement_ts: datetime,
    ) -> Optional[str]:
        """
        Late-Binding: resolve a plant's **light/growth** lifecycle phase at
        ``measurement_ts``.

        AUT-1183 NOTE — axis: This method is specific to the light/growth
        phase axis (``phase_changed`` events, ``Plant.phase`` column).
        For the nutrient/fertilizer axis use
        :meth:`get_plant_nutrient_phase_at`.

        Returns the ``new_phase`` of the last ``phase_changed`` event at or
        before ``measurement_ts``. When ``measurement_ts`` predates the
        plant's *first* recorded ``phase_changed`` event, that event's
        ``previous_phase`` is used instead of the plant's current ``phase``
        — otherwise a later transition stored on ``Plant.phase`` would leak
        into an earlier query. Only plants with zero ``phase_changed``
        events ever fall back to ``Plant.phase``.

        AUT-1205: ``add_lifecycle_event`` (and the status/correction PATCH)
        re-derive ``Plant.phase`` via this helper after every write, so the
        stored column and this chronological lookup stay the same source of
        truth. A backdated event is persisted in full but only wins the
        current state when it is the chronologically latest ``occurred``
        transition on this axis.

        AUT-1207: only ``event_status == 'occurred'`` events are considered
        — a planned, reverted, or test-data event must never set the
        derived phase, per the wave's acceptance criteria.
        """
        stmt = (
            select(PlantLifecycleEvent.new_phase)
            .where(
                and_(
                    PlantLifecycleEvent.plant_id == plant_id,
                    PlantLifecycleEvent.event_type == "phase_changed",
                    PlantLifecycleEvent.event_status == "occurred",
                    PlantLifecycleEvent.event_timestamp <= measurement_ts,
                )
            )
            .order_by(PlantLifecycleEvent.event_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        new_phase = result.scalar_one_or_none()
        if new_phase is not None:
            return new_phase

        earliest_stmt = (
            select(PlantLifecycleEvent.previous_phase)
            .where(
                and_(
                    PlantLifecycleEvent.plant_id == plant_id,
                    PlantLifecycleEvent.event_type == "phase_changed",
                    PlantLifecycleEvent.event_status == "occurred",
                )
            )
            .order_by(PlantLifecycleEvent.event_timestamp.asc())
            .limit(1)
        )
        result = await self.session.execute(earliest_stmt)
        earliest_previous_phase = result.scalar_one_or_none()
        if earliest_previous_phase is not None:
            return earliest_previous_phase

        plant = await self.get_by_plant_id(plant_id, include_deleted=True)
        return plant.phase if plant is not None else None

    async def get_plant_nutrient_phase_at(
        self,
        plant_id: uuid.UUID,
        measurement_ts: datetime,
    ) -> Optional[str]:
        """
        Late-Binding: resolve a plant's **nutrient/fertilizer** phase at
        ``measurement_ts`` (AUT-1183).

        Symmetric counterpart to :meth:`get_plant_phase_at` for the second
        phase axis. Queries ``nutrient_phase_changed`` events instead of
        ``phase_changed`` and falls back to ``Plant.nutrient_phase`` when no
        event predates ``measurement_ts``.

        Returns ``None`` when neither events nor a set ``nutrient_phase``
        value exist (plant predates AUT-1183 or nutrient axis never set).

        AUT-1205: same write-path contract as :meth:`get_plant_phase_at` —
        ``add_lifecycle_event`` / status-correction re-derive
        ``Plant.nutrient_phase`` via this helper so stored column and
        chronological lookup stay one source of truth.

        AUT-1207: only ``event_status == 'occurred'`` events are considered
        — see :meth:`get_plant_phase_at`.
        """
        stmt = (
            select(PlantLifecycleEvent.new_phase)
            .where(
                and_(
                    PlantLifecycleEvent.plant_id == plant_id,
                    PlantLifecycleEvent.event_type == "nutrient_phase_changed",
                    PlantLifecycleEvent.event_status == "occurred",
                    PlantLifecycleEvent.event_timestamp <= measurement_ts,
                )
            )
            .order_by(PlantLifecycleEvent.event_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        new_phase = result.scalar_one_or_none()
        if new_phase is not None:
            return new_phase

        earliest_stmt = (
            select(PlantLifecycleEvent.previous_phase)
            .where(
                and_(
                    PlantLifecycleEvent.plant_id == plant_id,
                    PlantLifecycleEvent.event_type == "nutrient_phase_changed",
                    PlantLifecycleEvent.event_status == "occurred",
                )
            )
            .order_by(PlantLifecycleEvent.event_timestamp.asc())
            .limit(1)
        )
        result = await self.session.execute(earliest_stmt)
        earliest_previous_phase = result.scalar_one_or_none()
        if earliest_previous_phase is not None:
            return earliest_previous_phase

        plant = await self.get_by_plant_id(plant_id, include_deleted=True)
        return plant.nutrient_phase if plant is not None else None

    async def get_lifecycle_event_by_id(
        self,
        plant_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> Optional[PlantLifecycleEvent]:
        """
        Look up a single lifecycle event, scoped to its plant (AUT-1207).

        Used by the status-update endpoint — the plant scoping prevents an
        event_id from one plant being addressed through another plant's URL.
        """
        stmt = select(PlantLifecycleEvent).where(
            and_(
                PlantLifecycleEvent.event_id == event_id,
                PlantLifecycleEvent.plant_id == plant_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lifecycle_events(
        self,
        plant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PlantLifecycleEvent]:
        """
        Get lifecycle events for a plant ordered chronologically (oldest first).

        Args:
            plant_id: Plant UUID.
            skip: Pagination offset.
            limit: Maximum number of rows to return.

        Returns:
            List of ``PlantLifecycleEvent`` instances ordered by
            ``event_timestamp ASC`` (chronological log order).
        """
        stmt = (
            select(PlantLifecycleEvent)
            .where(PlantLifecycleEvent.plant_id == plant_id)
            .order_by(PlantLifecycleEvent.event_timestamp.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_tank_incident_events_for_plant(
        self,
        plant: Plant,
    ) -> list[NutrientSolutionBatch]:
        """
        Get tank-level system-incident ledger entries relevant to a plant.

        A ``system_incident`` entry in the nutrient-balance ledger (e.g. the
        shared reservoir crashing to an acidic pH and being fully reset)
        affects every plant fed by that tank — it is NOT a per-plant
        ``PlantLifecycleEvent`` (that table's ``plant_id`` FK is mandatory,
        see its docstring). This joins the plant's subzone to its tank(s)
        via ``TankSubzoneAssignment`` and returns matching incidents since
        the plant's ``planting_date`` (an incident before that date cannot
        have affected this specific plant).

        Args:
            plant: Plant instance. Plants without a ``subzone_id`` (not yet
                assigned to a subzone) yield an empty list.

        Returns:
            List of ``NutrientSolutionBatch`` rows with
            ``entry_type == 'system_incident'``, ordered by
            ``occurred_at ASC``.
        """
        if plant.subzone_id is None:
            return []

        if plant.planting_date is None:
            start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        else:
            start = datetime.combine(plant.planting_date, time.min, tzinfo=timezone.utc)
        stmt = (
            select(NutrientSolutionBatch)
            .join(
                TankSubzoneAssignment,
                TankSubzoneAssignment.tank_id == NutrientSolutionBatch.tank_id,
            )
            .where(
                TankSubzoneAssignment.subzone_config_id == plant.subzone_id,
                NutrientSolutionBatch.entry_type == "system_incident",
                NutrientSolutionBatch.occurred_at >= start,
            )
            .order_by(NutrientSolutionBatch.occurred_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(
        self,
        plant_id: uuid.UUID,
        deleted_by: int,
    ) -> Optional[Plant]:
        """
        Soft-delete a plant by setting ``deleted_at`` and ``deleted_by``.

        Args:
            plant_id: Plant UUID.
            deleted_by: ``user_accounts.id`` of the deleting user.

        Returns:
            Updated ``Plant`` instance or ``None`` if not found.
        """
        plant = await self.get_by_plant_id(plant_id, include_deleted=False)
        if plant is None:
            return None

        plant.deleted_at = datetime.now(timezone.utc)
        plant.deleted_by = deleted_by

        await self.session.flush()
        await self.session.refresh(plant)
        return plant
