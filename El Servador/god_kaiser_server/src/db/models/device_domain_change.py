"""
Device Domain Change Audit Model

AUT-1085 — Report domain field on ESP devices.
Status: IMPLEMENTED

Tracks every domain assignment change for a device.
Records old/new domain and when the change was made.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DeviceDomainChange(Base):
    """
    Audit log for device domain changes.

    Records every domain assignment change via the PATCH /devices/{esp_id}
    endpoint. The change_type is always 'manual' because the only write path
    is that single endpoint.

    Attributes:
        id: Primary key (UUID)
        esp_id: Device ID string (e.g., 'ESP_57E1D4')
        old_domain: Previous domain value (None if domain was unset)
        new_domain: New domain value (None if domain is being cleared)
        change_type: Always 'manual' (only one write path exists)
        changed_at: Timestamp of the change
    """

    __tablename__ = "device_domain_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    esp_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="ESP device ID string (e.g., ESP_57E1D4)",
    )

    old_domain: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Previous domain value (None if domain was unset before this change)",
    )

    new_domain: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="New domain value (None if domain is being cleared)",
    )

    change_type: Mapped[str] = mapped_column(
        String(20),
        default="manual",
        server_default="manual",
        nullable=False,
        doc="Change type: always 'manual' (only one write path — PATCH endpoint)",
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
        doc="Timestamp of the domain change (UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceDomainChange(esp_id='{self.esp_id}', "
            f"{self.old_domain!r} -> {self.new_domain!r})>"
        )
