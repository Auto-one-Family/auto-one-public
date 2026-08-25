"""
Tank Subzone Assignment Model

AUT-1211 — n:m assignment of tanks to subzone configs.

Design notes:
- A tank supplies one or more subzones (e.g. one tank -> one pump -> two
  pots); a subzone could in principle draw from more than one tank in the
  future, hence n:m rather than a single tank_id column on subzone_configs.
- Deliberately independent of the legacy assigned_subzones JSON column
  (sensor.py/actuator.py), which is DEPRECATED/read-only per AUT-227 and
  belongs to a different domain (sensor/actuator scope, not tanks).
- Pattern: modelled 1:1 after SensorSubzoneAssignment (AUT-1155), which is
  itself modelled after DashboardUserAssignment (AUT-1095).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class TankSubzoneAssignment(Base):
    """
    Tank Subzone Assignment Model.

    Represents an explicit n:m assignment between a tank and a
    subzone_config. Both sides cascade-delete: removing either the tank or
    the subzone automatically removes the assignment.

    Attributes:
        id: Primary key (UUID)
        tank_id: Foreign key to tanks.id
        subzone_config_id: Foreign key to subzone_configs.id
        assigned_at: Timestamp when the assignment was created (UTC)
        assigned_by: User ID of the operator who created the assignment
    """

    __tablename__ = "tank_subzone_assignments"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    tank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tanks.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned tank",
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
            "tank_id",
            "subzone_config_id",
            name="uq_tank_subzone_assignment",
        ),
        Index("idx_tank_subzone_tank_id", "tank_id"),
        Index("idx_tank_subzone_subzone_config_id", "subzone_config_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<TankSubzoneAssignment("
            f"tank_id='{self.tank_id}', "
            f"subzone_config_id='{self.subzone_config_id}')>"
        )
