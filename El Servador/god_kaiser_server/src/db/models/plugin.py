"""
Plugin Configuration and Execution History Models

Phase 4C.1.2: DB-Persistenz fuer das AutoOps Plugin-System.
- PluginConfig: Plugin-Konfiguration und Metadaten
- PluginExecution: Ausfuehrungshistorie mit Status und Ergebnis
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, _utc_now


class PluginConfig(Base, TimestampMixin):
    """Plugin configuration persisted in DB, synced from in-memory PluginRegistry."""

    __tablename__ = "plugin_configs"

    plugin_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capabilities: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    schedule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )


class PluginExecution(Base):
    """Single plugin execution record with status, result, and timing."""

    __tablename__ = "plugin_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plugin_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("plugin_configs.plugin_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    triggered_by_user: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by_rule: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
