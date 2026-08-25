"""
Sensor Subzone Assignment Model

AUT-1155 [B1] n:m Sensor-Subzone-Zuordnung

Junction table for explicit n:m assignment of sensor configs to subzone configs.
Additive alongside the existing assigned_gpios / first-match resolution model.

Design notes:
- assigned_gpios on subzone_configs remains canonical for ESP32 config-push flow.
  All 10 existing get_subzone_by_gpio() call-sites are unaffected.
- This table adds a server-side, UUID-keyed direct assignment layer that:
  * Makes the Sensor→Subzone relationship explicit and queryable by UUID
  * Enables n:m (e.g. a mobile sensor assigned to multiple subzones)
  * Is the foundation for retiring the legacy assigned_subzones JSON column
    (currently DEPRECATED per AUT-227) in a future migration.
- Sensor-only for AUT-1155: actuators keep get_subzone_by_gpio() for control.
  Symmetric Verortung n:m lives in ActuatorSubzoneAssignment (own table; see
  actuator_subzone_assignment.py) — not a generic entity_type junction.

Pattern: modelled 1:1 after DashboardUserAssignment (AUT-1095).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class SensorSubzoneAssignment(Base):
    """
    Sensor Subzone Assignment Model.

    Represents an explicit n:m assignment between a sensor_config and a
    subzone_config.  Both sides cascade-delete: removing either the sensor or
    the subzone automatically removes the assignment.

    Attributes:
        id: Primary key (UUID)
        sensor_config_id: Foreign key to sensor_configs.id
        subzone_config_id: Foreign key to subzone_configs.id
        assigned_at: Timestamp when the assignment was created (UTC)
        assigned_by: User ID of the operator who created the assignment
    """

    __tablename__ = "sensor_subzone_assignments"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    sensor_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configs.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned sensor config",
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
            "sensor_config_id",
            "subzone_config_id",
            name="uq_sensor_subzone_assignment",
        ),
        Index("idx_sensor_subzone_sensor_config_id", "sensor_config_id"),
        Index("idx_sensor_subzone_subzone_config_id", "subzone_config_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SensorSubzoneAssignment("
            f"sensor_config_id='{self.sensor_config_id}', "
            f"subzone_config_id='{self.subzone_config_id}')>"
        )
