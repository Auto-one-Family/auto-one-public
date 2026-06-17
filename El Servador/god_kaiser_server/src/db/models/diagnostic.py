"""
Diagnostic Report Model

Phase 4D.1.2: Persistenz fuer Diagnose-Reports.
Speichert Ergebnisse der 10 modularen System-Checks.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class DiagnosticReport(Base):
    """Single diagnostic report containing results from all system checks."""

    __tablename__ = "diagnostic_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    overall_status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, server_default="manual")
    triggered_by_user: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    export_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
