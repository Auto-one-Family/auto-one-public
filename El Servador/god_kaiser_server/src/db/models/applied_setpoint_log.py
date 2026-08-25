"""
Applied Setpoint Log (AUT-1232 / Welle 5 T2)

Immutable history of which setpoint value was applied at evaluation time,
including origin (plan_segment vs static_fallback). Write path is wired in T3;
T6 reads this for past-overlay. No Config-Change-History substitute for rules.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now
from .plan_segment import PLAN_DOMAINS, PLAN_MEASURES


APPLIED_SETPOINT_ORIGINS: tuple[str, ...] = (
    "plan_segment",
    "static_fallback",
)

_ORIGIN_CHECK = f"origin IN ({', '.join(repr(o) for o in APPLIED_SETPOINT_ORIGINS)})"
_DOMAIN_CHECK = f"domain IN ({', '.join(repr(d) for d in PLAN_DOMAINS)})"
_MEASURE_CHECK = f"measure IN ({', '.join(repr(m) for m in PLAN_MEASURES)})"


class AppliedSetpointLog(Base):
    """
    Immutable applied-setpoint audit row.

    Attributes:
        id: Primary key (UUID)
        zone_id: Zone of the applied value
        subzone_config_id: Optional subzone scope
        domain / measure: Same catalogs as plan_segments
        applied_value: Numeric value that was used
        effective_at: Evaluation timestamp (UTC)
        rule_id: Optional CrossESPLogic that consumed the value
        segment_id: Optional PlanSegment that supplied the value
        origin: plan_segment | static_fallback
        created_at: Insert timestamp (UTC)
    """

    __tablename__ = "applied_setpoint_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    zone_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Zone identifier (FK to zones.zone_id)",
    )

    subzone_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional subzone_config scope",
    )

    domain: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Functional domain (see PLAN_DOMAINS)",
    )

    measure: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Setpoint measure (see PLAN_MEASURES)",
    )

    applied_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Numeric value applied at evaluation time",
    )

    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Evaluation timestamp (UTC)",
    )

    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_esp_logic.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional rule that consumed this value",
    )

    segment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_segments.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional plan_segment that supplied this value",
    )

    origin: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Value origin: plan_segment | static_fallback",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        doc="Insert timestamp (UTC) — immutable log, no updated_at",
    )

    __table_args__ = (
        CheckConstraint(_ORIGIN_CHECK, name="ck_applied_setpoint_logs_origin"),
        CheckConstraint(_DOMAIN_CHECK, name="ck_applied_setpoint_logs_domain"),
        CheckConstraint(_MEASURE_CHECK, name="ck_applied_setpoint_logs_measure"),
        Index(
            "idx_applied_setpoint_logs_zone_domain_measure_at",
            "zone_id",
            "domain",
            "measure",
            "effective_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AppliedSetpointLog(zone_id={self.zone_id!r}, measure={self.measure!r}, "
            f"applied_value={self.applied_value}, origin={self.origin!r})>"
        )
