"""
Email Log Model: Tracks email delivery status per notification.

Phase C V1.1: Email-Status-Tracking
Providers: Resend (primary), SMTP (fallback)
Statuses: pending → sent | failed | permanently_failed
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class EmailLog(Base, TimestampMixin):
    """Tracks individual email send attempts with provider and status."""

    __tablename__ = "email_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Template name: alert_critical, alert_digest, test",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Email provider: resend or smtp",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'pending'"),
        doc="Delivery status: pending, sent, failed, permanently_failed",
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
