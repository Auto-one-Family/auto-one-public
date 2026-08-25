"""
Salt Composition Reference Library (AUT-1418 / B1)

Editable guaranteed-analysis table per salt/product. Element mass fractions
are elemental % (not oxide). Distinct from stock_mix_recipes (name + g/L only).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin

SALT_SOURCE_TYPES: tuple[str, ...] = (
    "stoichiometric",
    "manufacturer_label",
    "beleg_offen",
)

_SOURCE_TYPE_CHECK = (
    "source_type IN ("
    + ", ".join(repr(s) for s in SALT_SOURCE_TYPES)
    + ")"
)


class SaltComposition(Base, TimestampMixin):
    """Guaranteed analysis (elemental %) for one salt/product."""

    __tablename__ = "salt_compositions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Canonical identity for salt composition rows",
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        doc="Display/salt name matching stock_mix component names when applicable",
    )

    formula: Mapped[Optional[str]] = mapped_column(
        String(120),
        nullable=True,
        doc="Optional chemical formula (stoichiometric salts)",
    )

    n_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental N mass % of salt (NULL if unknown / beleg_offen)",
    )
    p_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental P mass % of salt",
    )
    k_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental K mass % of salt",
    )
    ca_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental Ca mass % of salt",
    )
    mg_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental Mg mass % of salt",
    )
    s_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4),
        nullable=True,
        doc="Elemental S mass % of salt",
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="stoichiometric | manufacturer_label | beleg_offen",
    )

    source_note: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
        server_default=text("''"),
        doc="Stoichiometric derivation or label reference / BELEG-offen note",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        doc="Soft-deactivate without deleting identity",
    )

    __table_args__ = (
        CheckConstraint(_SOURCE_TYPE_CHECK, name="ck_salt_compositions_source_type"),
        Index(
            "uq_salt_compositions_active_name",
            "name",
            unique=True,
            postgresql_where=text("active IS TRUE"),
        ),
    )
