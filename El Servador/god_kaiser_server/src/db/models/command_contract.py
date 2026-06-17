"""
Intent/Outcome Contract Models (P0.1/P0.2).

Provides persistent single source of truth for command/config intent tracking and
terminal outcome state, including correlation and ordering metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommandIntent(Base, TimestampMixin):
    """Intent-level tracking (non-terminal orchestration view)."""

    __tablename__ = "command_intents"

    __table_args__ = (
        Index("idx_command_intents_intent_id", "intent_id", unique=True),
        Index("idx_command_intents_correlation_id", "correlation_id"),
        Index("idx_command_intents_state_created_at", "orchestration_state", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    esp_id: Mapped[str] = mapped_column(String(64), nullable=False)
    flow: Mapped[str] = mapped_column(String(32), nullable=False)
    orchestration_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="accepted",
        doc=(
            "Non-terminal orchestration: "
            "sent=server MQTT publish succeeded (see record_intent_publish_sent); "
            "accepted|ack_pending=from inbound intent_outcome (upsert_intent). "
            "Typical actuator command: sent then accepted or ack_pending."
        ),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )


class CommandOutcome(Base, TimestampMixin):
    """Outcome-level contract (exactly one terminal row per intent_id)."""

    __tablename__ = "command_outcomes"

    __table_args__ = (
        Index("idx_command_outcomes_intent_id", "intent_id", unique=True),
        Index("idx_command_outcomes_correlation_id", "correlation_id"),
        Index("idx_command_outcomes_outcome_created_at", "outcome", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    esp_id: Mapped[str] = mapped_column(String(64), nullable=False)
    flow: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Contract: accepted|rejected|applied|persisted|failed|expired",
    )
    contract_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        doc="Outcome contract version (1=legacy, 2=target)",
    )
    semantic_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="legacy",
        doc="legacy|dual|target",
    )
    legacy_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="Legacy v1 status projection during dual-mode operation",
    )
    target_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="Target v2 status projection during dual-mode operation",
    )
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True when the row reached a terminal outcome for its contract mode",
    )
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    generation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seq: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    epoch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ttl_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    terminal_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
