"""
Dashboard User Assignment Model

Junction table for n:m assignment of dashboards to users.
Additive alongside the existing owner_id/is_shared model.
Operators can explicitly grant individual users access to dashboards
that they neither own nor that are globally shared.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class DashboardUserAssignment(Base):
    """
    Dashboard User Assignment Model.

    Represents an explicit per-user assignment to a specific dashboard.
    Additive: owner_id and is_shared on the dashboards table are not changed.

    Attributes:
        id: Primary key (UUID)
        dashboard_id: Foreign key to the assigned dashboard
        user_id: Foreign key to the assigned user
        assigned_at: Timestamp when the assignment was created (UTC)
        assigned_by: User ID of the operator who created the assignment
    """

    __tablename__ = "dashboard_user_assignments"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned dashboard",
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to the assigned user",
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
        UniqueConstraint("dashboard_id", "user_id", name="uq_dashboard_user_assignment"),
        Index("idx_dashboard_assignment_dashboard_id", "dashboard_id"),
        Index("idx_dashboard_assignment_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<DashboardUserAssignment("
            f"dashboard_id='{self.dashboard_id}', "
            f"user_id={self.user_id})>"
        )
