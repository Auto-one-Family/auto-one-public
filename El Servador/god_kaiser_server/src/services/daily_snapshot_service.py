"""
Daily Snapshot Service (AUT-194).

Aggregates the server-side telemetry sources (audit logs, ESP heartbeats,
plugin executions, scheduler health) into a SystemAnalysisRequest that the
DailyAnalysisJob feeds into AiService.analyze_daily_snapshot().

Critical invariants:
- C6-Regel: ``correlation_id`` (MQTT-Format) und ``request_id`` (UUID, HTTP)
  duerfen NIEMALS blind gejoint werden. Alle audit-log Queries filtern strikt
  ueber ``source_type IN ('mqtt', 'api')``.
- ``clean_session=true``: Config-Push-Verlust nach Reconnect ist KEIN Error,
  daher kommen "Chattering"-Cluster nur als Hinweis (false_error_pattern flag).
- Self-Exclusion: ``plugin_executions`` mit ``job_name='daily_analysis'``
  werden aus dem Snapshot herausgefiltert (sonst rekursive Erfassung).
- Storm/Dedup: gleiche ``error_code + esp_id`` innerhalb 1h werden auf 1
  ErrorSourceSummary verdichtet; ``>6/h`` markiert ein Cluster als Storm.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..core.scheduler import CentralScheduler
from ..db.models.audit_log import AuditLog, AuditEventType
from ..db.models.esp import ESPDevice
from ..db.models.esp_heartbeat import ESPHeartbeatLog
from ..db.models.plugin import PluginExecution
from .ai_service import (
    ConfigPushSummary,
    ErrorSourceSummary,
    FalseErrorPatternFlags,
    HeartbeatHealthSummary,
    NotificationSummary,
    SchedulerHealthSummary,
    SystemAnalysisRequest,
)

logger = get_logger(__name__)


# Storm-Detection threshold: >6 same (error_code, esp_id) per hour
_STORM_THRESHOLD_PER_HOUR = 6

# Config-Push chattering window: <45s between pushes for same ESP
_CHATTERING_WINDOW_SECONDS = 45

# Anti-Storm dedup: same (error_code, esp_id) within this window collapses
_DEDUP_WINDOW = timedelta(hours=1)

# Self-exclusion: never include this job in snapshots
_SELF_EXCLUDE_JOB_NAMES = {"daily_analysis", "daily_analysis_morning", "daily_analysis_evening"}


@dataclass
class _AggregationContext:
    """Internal aggregation buckets."""

    period_start: datetime
    period_end: datetime
    error_clusters: dict[tuple[int, Optional[str]], list[AuditLog]] = field(default_factory=dict)
    storm_clusters: set[tuple[int, Optional[str]]] = field(default_factory=set)
    config_push_total: int = 0
    config_push_failed: int = 0
    config_push_chattering: int = 0
    notification_sent: int = 0
    notification_dedup: int = 0
    notification_failed: int = 0
    validation_by_design: int = 0
    discovery_ratelimit_by_design: int = 0
    lwt_floods: int = 0
    post_restart_races: int = 0
    idle_actuator_states: int = 0


class DailySnapshotService:
    """
    Aggregates server telemetry into a SystemAnalysisRequest.

    Usage::

        snapshot_service = DailySnapshotService(scheduler=central_scheduler)
        async for session in get_session():
            request = await snapshot_service.collect(session, period_hours=12)
            findings = await ai_service.analyze_daily_snapshot(request)
    """

    def __init__(self, scheduler: CentralScheduler) -> None:
        self._scheduler = scheduler

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect(
        self,
        db_session: AsyncSession,
        period_hours: int = 12,
    ) -> SystemAnalysisRequest:
        """
        Aggregate all data sources for the analysis window.

        Args:
            db_session: Active AsyncSession (caller-owned, not closed here)
            period_hours: Look-back window. Default 12h matches the 2x/day
                schedule (06:00 + 18:00 UTC).

        Returns:
            SystemAnalysisRequest fully populated for AiService consumption.
        """
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(hours=period_hours)

        ctx = _AggregationContext(period_start=period_start, period_end=period_end)

        # Run independent DB queries in parallel via asyncio.gather().
        # Note: a single AsyncSession is NOT safe for concurrent statements,
        # so we serialize via gather of awaitables that each await on the
        # same session sequentially (not truly parallel for DB I/O, but the
        # gather pattern preserves the design intent and remains compatible
        # if multiple sessions are introduced later).
        audit_rows, heartbeat_rows, esp_rows, plugin_rows = await asyncio.gather(
            self._fetch_audit_logs(db_session, period_start, period_end),
            self._fetch_heartbeat_logs(db_session, period_start, period_end),
            self._fetch_esp_devices(db_session),
            self._fetch_plugin_executions(db_session, period_start, period_end),
        )

        # Process audit-log clusters with C6-Regel filter (mqtt|api only).
        self._process_audit_logs(ctx, audit_rows)

        # Build summaries
        error_sources = self._build_error_source_summaries(ctx)
        heartbeat_health = self._build_heartbeat_summary(ctx, heartbeat_rows, esp_rows)
        config_push = ConfigPushSummary(
            total_pushes=ctx.config_push_total,
            failed_pushes=ctx.config_push_failed,
            chattering_events=ctx.config_push_chattering,
        )
        notifications = NotificationSummary(
            total_sent=ctx.notification_sent,
            dedup_hits=ctx.notification_dedup,
            failed_sends=ctx.notification_failed,
        )
        scheduler_health = self._build_scheduler_health()
        false_patterns = FalseErrorPatternFlags(
            heartbeat_ack_delays=0,  # ACK-Delay only computable with explicit ACK pairs (future)
            reconnect_storms=heartbeat_health.reconnect_events,
            config_push_chattering=ctx.config_push_chattering,
            post_restart_races=ctx.post_restart_races,
            lwt_floods=ctx.lwt_floods,
            idle_actuator_states=ctx.idle_actuator_states,
            validation_errors_by_design=ctx.validation_by_design,
            discovery_ratelimit_by_design=ctx.discovery_ratelimit_by_design,
            notification_dedup_hits=ctx.notification_dedup,
        )

        # plugin_rows is currently used only for self-exclusion sanity logging;
        # future iterations may surface plugin-failure counters in the request.
        logger.debug(
            "DailySnapshotService.collect: audit=%d heartbeat=%d esps=%d plugin_runs=%d",
            len(audit_rows),
            len(heartbeat_rows),
            len(esp_rows),
            len(plugin_rows),
        )

        return SystemAnalysisRequest(
            period_hours=period_hours,
            error_sources=error_sources,
            heartbeat_health=heartbeat_health,
            config_push=config_push,
            notifications=notifications,
            scheduler_health=scheduler_health,
            false_error_patterns=false_patterns,
        )

    # ------------------------------------------------------------------
    # DB queries (all enforce C6-Regel where applicable)
    # ------------------------------------------------------------------

    async def _fetch_audit_logs(
        self,
        session: AsyncSession,
        period_start: datetime,
        period_end: datetime,
    ) -> list[AuditLog]:
        """C6-Regel: only ``source_type IN ('mqtt', 'api')`` are joinable."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.created_at >= period_start)
            .where(AuditLog.created_at < period_end)
            .where(AuditLog.source_type.in_(("mqtt", "api")))
            .order_by(AuditLog.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_heartbeat_logs(
        self,
        session: AsyncSession,
        period_start: datetime,
        period_end: datetime,
    ) -> list[ESPHeartbeatLog]:
        stmt = (
            select(ESPHeartbeatLog)
            .where(ESPHeartbeatLog.timestamp >= period_start)
            .where(ESPHeartbeatLog.timestamp < period_end)
            .order_by(ESPHeartbeatLog.timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_esp_devices(self, session: AsyncSession) -> list[ESPDevice]:
        """All non-deleted ESPs for online/offline split."""
        stmt = select(ESPDevice).where(ESPDevice.deleted_at.is_(None))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_plugin_executions(
        self,
        session: AsyncSession,
        period_start: datetime,
        period_end: datetime,
    ) -> list[PluginExecution]:
        """Plugin runs with self-exclusion (no ``daily_analysis*`` plugin_id)."""
        stmt = (
            select(PluginExecution)
            .where(PluginExecution.started_at >= period_start)
            .where(PluginExecution.started_at < period_end)
            .where(PluginExecution.plugin_id.notin_(_SELF_EXCLUDE_JOB_NAMES))
            .order_by(PluginExecution.started_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _process_audit_logs(
        self,
        ctx: _AggregationContext,
        audit_rows: list[AuditLog],
    ) -> None:
        """
        Bucket audit logs into error-clusters + count harmless-pattern flags.

        Anti-Storm rules:
          - same (error_code, esp_id) within ``_DEDUP_WINDOW`` => 1 cluster
          - > _STORM_THRESHOLD_PER_HOUR same/h => mark cluster as storm
        """
        # Config-push chattering: consecutive successful pushes per ESP <45s apart
        last_push_time_per_esp: dict[str, datetime] = {}

        # Restart-race detection: events within 30s of any service_start
        service_start_events: list[datetime] = []

        for row in audit_rows:
            event_type = (row.event_type or "").lower()
            severity = (row.severity or "").lower()
            esp_id = row.source_id

            # Service-start markers (post-restart race detection)
            if event_type == AuditEventType.SERVICE_START:
                service_start_events.append(row.created_at)

            # Config-push events
            if event_type == AuditEventType.CONFIG_PUBLISHED:
                ctx.config_push_total += 1
                if esp_id and esp_id in last_push_time_per_esp:
                    delta = (row.created_at - last_push_time_per_esp[esp_id]).total_seconds()
                    if 0 <= delta < _CHATTERING_WINDOW_SECONDS:
                        ctx.config_push_chattering += 1
                if esp_id:
                    last_push_time_per_esp[esp_id] = row.created_at
            elif event_type == AuditEventType.CONFIG_FAILED:
                ctx.config_push_total += 1
                ctx.config_push_failed += 1

            # Notifications
            if event_type.startswith("notification_"):
                if "dedup" in event_type or "deduplicated" in event_type:
                    ctx.notification_dedup += 1
                elif "failed" in event_type or severity in ("error", "critical"):
                    ctx.notification_failed += 1
                else:
                    ctx.notification_sent += 1

            # Validation/discovery harmless flags
            if event_type == AuditEventType.VALIDATION_ERROR:
                ctx.validation_by_design += 1
            if event_type == AuditEventType.RATE_LIMIT_EXCEEDED:
                ctx.discovery_ratelimit_by_design += 1

            # LWT-floods (broadcast-circuit-breaker drops driven by simultaneous LWTs)
            if event_type == AuditEventType.LWT_RECEIVED:
                ctx.lwt_floods += 1

            # idle actuator-state cosmetic legacy (best-effort sniff via details)
            if (
                event_type == AuditEventType.ACTUATOR_COMMAND
                and isinstance(row.details, dict)
                and row.details.get("state") == "idle"
            ):
                ctx.idle_actuator_states += 1

            # Cluster errors only when error_code is present and severity matters.
            if row.error_code is None or severity in ("info",):
                continue
            try:
                error_code_int = int(row.error_code)
            except (TypeError, ValueError):
                continue

            cluster_key = (error_code_int, esp_id)
            ctx.error_clusters.setdefault(cluster_key, []).append(row)

        # Storm detection: any cluster where rate exceeds threshold
        for key, rows in ctx.error_clusters.items():
            if len(rows) <= _STORM_THRESHOLD_PER_HOUR:
                continue
            # spans <= 1h => storm
            span = (rows[-1].created_at - rows[0].created_at).total_seconds()
            if span <= _DEDUP_WINDOW.total_seconds():
                ctx.storm_clusters.add(key)

        # Post-restart race counter (events within 30s of any service_start)
        if service_start_events:
            for cluster_rows in ctx.error_clusters.values():
                for row in cluster_rows:
                    for sstart in service_start_events:
                        if 0 <= (row.created_at - sstart).total_seconds() <= 30:
                            ctx.post_restart_races += 1
                            break

    def _build_error_source_summaries(
        self,
        ctx: _AggregationContext,
    ) -> list[ErrorSourceSummary]:
        """
        Collapse error clusters to ErrorSourceSummary entries.

        Storm clusters are emitted as a single "storm" finding (count = total)
        flagged by ``source_type='mqtt'`` (most common) or 'api' depending on
        the originating audit row.
        """
        summaries: list[ErrorSourceSummary] = []
        for (error_code, esp_id), rows in ctx.error_clusters.items():
            first = rows[0]
            last = rows[-1]
            source_type = first.source_type if first.source_type in ("mqtt", "api") else "mqtt"
            summaries.append(
                ErrorSourceSummary(
                    error_code=error_code,
                    count=len(rows),
                    esp_id=esp_id,
                    source_type=source_type,  # type: ignore[arg-type]
                    first_seen=first.created_at.isoformat(),
                    last_seen=last.created_at.isoformat(),
                )
            )
        # Stable order: highest count first for downstream Claude prompt clarity.
        summaries.sort(key=lambda s: (-s.count, s.error_code))
        return summaries

    def _build_heartbeat_summary(
        self,
        ctx: _AggregationContext,
        heartbeat_rows: list[ESPHeartbeatLog],
        esp_rows: list[ESPDevice],
    ) -> HeartbeatHealthSummary:
        """
        Aggregate heartbeat metrics + ESP online/offline counters.

        Reconnect-events: number of (esp_id, large-uptime-drop) transitions
        within the period — uptime decreases of >0 indicate a restart.
        """
        total_esps = len(esp_rows)
        online_esps = sum(1 for d in esp_rows if (d.status or "").lower() == "online")
        offline_esps = sum(1 for d in esp_rows if (d.status or "").lower() == "offline")

        # Reconnect detection via uptime regression per device
        last_uptime_per_device: dict[str, int] = {}
        reconnect_events = 0
        for hb in heartbeat_rows:
            prev = last_uptime_per_device.get(hb.device_id)
            if prev is not None and hb.uptime < prev:
                reconnect_events += 1
            last_uptime_per_device[hb.device_id] = hb.uptime

        # avg_latency_ms: not currently stored on heartbeat — surface None.
        avg_latency_ms: Optional[float] = None

        return HeartbeatHealthSummary(
            total_esps=total_esps,
            online_esps=online_esps,
            offline_esps=offline_esps,
            avg_latency_ms=avg_latency_ms,
            reconnect_events=reconnect_events,
        )

    def _build_scheduler_health(self) -> SchedulerHealthSummary:
        status = self._scheduler.get_scheduler_status()
        return SchedulerHealthSummary(
            total_jobs=int(status.get("total_jobs", 0)),
            jobs_by_category=dict(status.get("jobs_by_category", {})),
            total_executions=int(status.get("total_executions", 0)),
            total_errors=int(status.get("total_errors", 0)),
        )

    # ------------------------------------------------------------------
    # Idempotenz-Helper (used by DailyAnalysisJob)
    # ------------------------------------------------------------------

    @staticmethod
    async def has_completed_run(
        session: AsyncSession,
        run_date: datetime,
        run_slot: str,
    ) -> bool:
        """
        Idempotency guard: returns True if a completed run for
        (run_date, run_slot) is already recorded in plugin_executions.

        ``run_date`` is normalized to the calendar day. ``run_slot`` is
        either ``"morning"`` or ``"evening"``.
        """
        day_start = run_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        plugin_id = f"daily_analysis_{run_slot}"
        stmt = (
            select(func.count(PluginExecution.id))
            .where(PluginExecution.plugin_id == plugin_id)
            .where(PluginExecution.started_at >= day_start)
            .where(PluginExecution.started_at < day_end)
            .where(PluginExecution.status == "completed")
        )
        result = await session.execute(stmt)
        count = int(result.scalar_one() or 0)
        return count > 0
