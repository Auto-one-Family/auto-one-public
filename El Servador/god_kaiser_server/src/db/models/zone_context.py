"""
Zone Context Model

Phase: K3 - Zone-Context Data Model
Status: IMPLEMENTED

Stores business-level context data per zone: plant information,
growth phase, substrate, responsible person, cycle history.
Designed for AI-ready export via the component export API.
"""

from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin
from ..types import JSONBCompat


class ZoneContext(Base, TimestampMixin):
    """
    Zone Context Model.

    Stores zone-level business data: what is growing, growth phase,
    substrate, responsible person, cycle history, and custom fields.

    Each zone_id has at most one ZoneContext row (upsert pattern).

    Attributes:
        id: Auto-increment primary key
        zone_id: Unique zone identifier (references zone assignment, not FK)
        zone_name: Human-readable zone name (cached from ESP zone assignment)
        plant_count: Number of plants in this zone
        variety: Plant variety / strain
        substrate: Growing medium description
        growth_phase: Current growth phase (e.g., 'seedling', 'vegetative', 'flower_week_3')
        planted_date: Date when current cycle was planted
        expected_harvest: Expected harvest date
        responsible_person: Person responsible for this zone
        work_hours_weekly: Estimated weekly work hours for this zone
        notes: Free-text notes
        custom_data: Extensible JSON for user-defined fields
        cycle_history: JSON array of archived growing cycles
    """

    __tablename__ = "zone_contexts"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Auto-increment primary key",
    )

    # Zone Identity (unique — one context per zone)
    zone_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        doc="Zone identifier (matches ESP zone assignment)",
    )

    zone_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Human-readable zone name (cached)",
    )

    # Plant Information
    plant_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Number of plants in zone",
    )

    variety: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Plant variety or strain",
    )

    substrate: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Growing medium (e.g., 'Coco/Perlite 70/30')",
    )

    growth_phase: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Current growth phase (e.g., 'vegetative', 'flower_week_5')",
    )

    planted_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        doc="Date current cycle was planted",
    )

    expected_harvest: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        doc="Expected harvest date",
    )

    # Operations
    responsible_person: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Person responsible for this zone",
    )

    work_hours_weekly: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Estimated weekly work hours",
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Free-text notes",
    )

    # Extensible Data
    custom_data: Mapped[dict] = mapped_column(
        JSONBCompat,
        default=dict,
        server_default="{}",
        nullable=False,
        doc="User-defined custom fields (JSON)",
    )

    # Cycle History (archived growing cycles)
    cycle_history: Mapped[list] = mapped_column(
        JSONBCompat,
        default=list,
        server_default="[]",
        nullable=False,
        doc="Array of archived growing cycles [{variety, planted, harvested, notes, ...}]",
    )

    def __repr__(self) -> str:
        return (
            f"<ZoneContext(zone_id='{self.zone_id}', "
            f"variety='{self.variety}', "
            f"phase='{self.growth_phase}')>"
        )

    @property
    def plant_age_days(self) -> Optional[int]:
        """Calculate plant age in days from planted_date."""
        if not self.planted_date:
            return None
        delta = date.today() - self.planted_date
        return delta.days

    @property
    def days_to_harvest(self) -> Optional[int]:
        """Calculate days remaining until expected harvest."""
        if not self.expected_harvest:
            return None
        delta = self.expected_harvest - date.today()
        return delta.days
