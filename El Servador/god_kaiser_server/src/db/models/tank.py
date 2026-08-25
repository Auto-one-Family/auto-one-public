"""
Tank Model: Nutrient Solution Reservoir

AUT-1211 — foundation entity for a future nutrient-balance ledger and
plant-lifecycle-event docking (out of scope here; see plant.py
PlantLifecycleEvent for the event log this will eventually attach to).

A tank is a mixing/reservoir vessel that feeds one or more subzones (e.g.
one tank -> one pump -> two pots) with the same nutrient solution. Tank
belongs to exactly one zone (n:1, analogous to ESPDevice.zone_id), while
the tank-to-subzone relationship is n:m via TankSubzoneAssignment — modelled
after SensorSubzoneAssignment (AUT-1155) rather than the deprecated
assigned_subzones JSON column (AUT-227), since that column is legacy/
read-only and unrelated to this new entity.
"""

import uuid
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


TANK_OPERATION_MODES: tuple[str, ...] = (
    "drain_to_waste",
    "recirculating",
)

_OPERATION_MODE_CHECK = f"operation_mode IN ({', '.join(repr(m) for m in TANK_OPERATION_MODES)})"


class Tank(Base, TimestampMixin):
    """
    Tank Model.

    Represents a nutrient solution reservoir (mixing tank) that supplies one
    or more subzones within a single zone. The subzone assignment is a
    separate n:m junction table (see TankSubzoneAssignment); this table only
    carries the tank's own attributes and its mandatory zone.

    Attributes:
        id: Primary key (UUID)
        zone_id: Zone this tank belongs to (FK to zones.zone_id, mandatory)
        name: Human-readable tank name/identifier
        nominal_volume_l: Optional nominal volume in liters (real-world tanks
            are often not exactly known, hence nullable)
        operation_mode: 'drain_to_waste' or 'recirculating'
        created_at / updated_at: Standard timestamp mixin
    """

    __tablename__ = "tanks"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Zone (n:1, mandatory — analogous to ESPDevice.zone_id)
    zone_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Zone identifier (FK to zones.zone_id)",
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Human-readable tank name/identifier",
    )

    nominal_volume_l: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Optional nominal volume in liters (NULL if not precisely known)",
    )

    # AUT-1381 W3: Frischwasser-Qualität am Tank (eine Stelle) — kein stilles Hardcode.
    # NULL = nicht konfiguriert (Assist bei Verdünnung fail-closed).
    fresh_water_ec_us_cm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Configured fresh-water EC (µS/cm); NULL = not configured",
    )
    fresh_water_ph: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Configured fresh-water pH; NULL = not configured",
    )

    operation_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Operation mode: 'drain_to_waste' or 'recirculating'",
    )

    __table_args__ = (CheckConstraint(_OPERATION_MODE_CHECK, name="ck_tanks_operation_mode"),)

    def __repr__(self) -> str:
        return f"<Tank(name='{self.name}', zone_id='{self.zone_id}')>"
