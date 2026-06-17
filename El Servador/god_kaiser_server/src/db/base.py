"""
SQLAlchemy Base and Declarative Base
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models"""

    pass


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """
    Mixin for automatic created_at and updated_at timestamps.

    All models that inherit from this mixin will automatically track
    creation and update times.

    Note: Uses timezone-aware UTC datetimes for consistency with
    PostgreSQL TIMESTAMP WITH TIME ZONE columns.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
        doc="Timestamp when the record was created (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
        doc="Timestamp when the record was last updated (UTC)",
    )
