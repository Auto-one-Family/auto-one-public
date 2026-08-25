"""
Actuator Subzone Assignment Model

n:m Actuator-Subzone-Zuordnung (Verortung / Auswertung)

Junction table for explicit n:m assignment of actuator configs to subzone configs.
Additive alongside the existing assigned_gpios / first-match resolution model.

Design notes / risk evaluation:
- assigned_gpios on subzone_configs remains canonical for ESP32 config-push
  and for control-path resolution via get_subzone_by_gpio().
- Logic Engine ActuatorActionExecutor (subzone skip) and Safety/ConflictManager
  are NOT consumers of this table — Verortung only (Monitor, UI coverage).
- assigned_subzones JSON on actuator_configs stays DEPRECATED/dead (AUT-227).
- Own table (not a generic entity_type junction): mirrors SensorSubzoneAssignment
  (AUT-1155) and TankSubzoneAssignment (AUT-1211) so real FKs + CASCADE stay intact.
- Technical UUID PK; uniqueness via UniqueConstraint (no composite PK).

Pattern: modelled 1:1 after SensorSubzoneAssignment (AUT-1155).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class ActuatorSubzoneAssignment(Base):
    """
    Actuator Subzone Assignment Model.

    Represents an explicit n:m assignment between an actuator_config and a
    subzone_config. Both sides cascade-delete: removing either the actuator or
    the subzone automatically removes the assignment.

    Attributes:
        id: Primary key (UUID)
        actuator_config_id: Foreign key to actuator_configs.id
        subzone_config_id: Foreign key to subzone_configs.id
        assigned_at: Timestamp when the assignment was created (UTC)
        assigned_by: User ID of the operator who created the assignment
    """

    __tablename__ = "actuator_subzone_assignments"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    actuator_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("actuator_configs.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned actuator config",
    )

    subzone_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned subzone config",
    )

    # Assignment metadata
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
        doc="Timestamp when the assignment was created (UTC)",
    )

    assigned_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        doc="User ID of the operator who created the assignment",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "actuator_config_id",
            "subzone_config_id",
            name="uq_actuator_subzone_assignment",
        ),
        Index("idx_actuator_subzone_actuator_config_id", "actuator_config_id"),
        Index("idx_actuator_subzone_subzone_config_id", "subzone_config_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActuatorSubzoneAssignment("
            f"actuator_config_id='{self.actuator_config_id}', "
            f"subzone_config_id='{self.subzone_config_id}')>"
        )
