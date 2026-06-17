"""
ESP Heartbeat Repository: Time-Series Heartbeat Data Operations

Provides database operations for ESP heartbeat history:
- Log heartbeats with calculated health status
- Query heartbeat history by device or time range
- Cleanup old heartbeat entries (retention policy)

Phase: ESP-Heartbeat-Persistierung
Priority: HIGH
Status: IMPLEMENTED
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.esp_heartbeat import ESPHeartbeatLog, determine_health_status
from .base_repo import BaseRepository
from ...core.logging_config import get_logger

logger = get_logger(__name__)

_RUNTIME_TELEMETRY_KEYS = frozenset(
    {
        "persistence_degraded",
        "persistence_degraded_reason",
        "runtime_state_degraded",
        "mqtt_circuit_breaker_open",
        "wifi_circuit_breaker_open",
        "network_degraded",
        "critical_outcome_drop_count",
        "publish_outbox_drop_count",
        "persistence_drift_count",
        "payload_degraded",
        "degraded_fields",
        "heartbeat_degraded_count",
        "metrics_schema_version",
        "handover_contract_reject",
        "handover_contract_reject_startup",
        "handover_contract_reject_runtime",
        "handover_epoch",
        "session_epoch",
        "metrics_delta_ts",
        "metrics_freshness_seconds",
        "publish_queue_drop_count",
        "publish_queue_hwm",
        "publish_queue_shed_count",
        "safe_publish_retry_count",
        "adoption_delta_count",
    }
)


def extract_heartbeat_runtime_telemetry(payload: dict) -> dict:
    """Subset of heartbeat JSON for JSONB persistence (avoids duplicating core columns)."""
    out: dict = {}
    for key in _RUNTIME_TELEMETRY_KEYS:
        if key in payload:
            out[key] = payload[key]
    return out


class ESPHeartbeatRepository(BaseRepository[ESPHeartbeatLog]):
    """
    Repository for ESP Heartbeat history operations.

    Provides optimized queries for time-series heartbeat data.
    Designed for high-volume inserts and time-range queries.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        super().__init__(ESPHeartbeatLog, session)

    async def log_heartbeat(
        self,
        esp_uuid: uuid.UUID,
        device_id: str,
        payload: dict,
        data_source: str = "production",
    ) -> Optional[ESPHeartbeatLog]:
        """
        Log a heartbeat to history.

        Non-blocking: Errors are logged but don't propagate.
        This ensures heartbeat logging doesn't crash the handler.

        Args:
            esp_uuid: ESP device UUID (FK to esp_devices)
            device_id: Device identifier (e.g. "ESP_12AB34CD")
            payload: Heartbeat payload from MQTT
            data_source: Source type (production, mock, test)

        Returns:
            Created ESPHeartbeatLog or None if failed
        """
        try:
            # Extract metrics from payload
            heap_free = payload.get("heap_free", payload.get("free_heap", 0))
            wifi_rssi = payload.get("wifi_rssi", 0)
            uptime = payload.get("uptime", 0)
            sensor_count = payload.get("sensor_count", payload.get("active_sensors", 0))
            actuator_count = payload.get("actuator_count", payload.get("active_actuators", 0))
            gpio_reserved_count = payload.get("gpio_reserved_count", 0)
            runtime_telemetry = extract_heartbeat_runtime_telemetry(payload)
            runtime_telemetry.setdefault("handover_contract_reject", 0)
            runtime_telemetry.setdefault("handover_contract_reject_startup", 0)
            runtime_telemetry.setdefault("handover_contract_reject_runtime", 0)

            # Calculate health status
            health_status = determine_health_status(
                wifi_rssi,
                heap_free,
                runtime_telemetry=runtime_telemetry or None,
            )

            # Create heartbeat log entry
            heartbeat = ESPHeartbeatLog(
                esp_id=esp_uuid,
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                heap_free=heap_free,
                wifi_rssi=wifi_rssi,
                uptime=uptime,
                sensor_count=sensor_count,
                actuator_count=actuator_count,
                gpio_reserved_count=gpio_reserved_count,
                data_source=data_source,
                health_status=health_status,
                runtime_telemetry=runtime_telemetry or None,
            )

            self.session.add(heartbeat)
            await self.session.flush()

            logger.debug(
                f"Heartbeat logged for {device_id}: "
                f"heap={heap_free // 1024}KB, rssi={wifi_rssi}dBm, "
                f"health={health_status}"
            )
            return heartbeat

        except Exception as e:
            # Non-blocking: Log error but don't propagate
            logger.error(f"Failed to log heartbeat for {device_id}: {e}")
            return None

    async def get_history(
        self,
        device_id: str,
        after: datetime,
        limit: int = 1000,
    ) -> list[ESPHeartbeatLog]:
        """
        Get heartbeat history for a specific device.

        Args:
            device_id: Device identifier (e.g. "ESP_12AB34CD")
            after: Start timestamp (inclusive)
            limit: Maximum number of records

        Returns:
            List of heartbeat logs (newest first)
        """
        stmt = (
            select(ESPHeartbeatLog)
            .where(
                and_(
                    ESPHeartbeatLog.device_id == device_id,
                    ESPHeartbeatLog.timestamp >= after,
                )
            )
            .order_by(desc(ESPHeartbeatLog.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_heartbeats_after(
        self,
        after: datetime,
        limit: int = 500,
    ) -> list[ESPHeartbeatLog]:
        """
        Get all heartbeats after timestamp (for EventAggregator).

        Args:
            after: Start timestamp (inclusive)
            limit: Maximum number of records

        Returns:
            List of heartbeat logs (newest first)
        """
        stmt = (
            select(ESPHeartbeatLog)
            .where(ESPHeartbeatLog.timestamp >= after)
            .order_by(desc(ESPHeartbeatLog.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_device(
        self,
        device_id: str,
    ) -> Optional[ESPHeartbeatLog]:
        """
        Get the most recent heartbeat for a device.

        Args:
            device_id: Device identifier

        Returns:
            Latest heartbeat or None
        """
        stmt = (
            select(ESPHeartbeatLog)
            .where(ESPHeartbeatLog.device_id == device_id)
            .order_by(desc(ESPHeartbeatLog.timestamp))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_device(
        self,
        device_id: str,
        after: Optional[datetime] = None,
    ) -> int:
        """
        Count heartbeats for a device.

        Args:
            device_id: Device identifier
            after: Optional start timestamp

        Returns:
            Number of heartbeats
        """
        conditions = [ESPHeartbeatLog.device_id == device_id]
        if after:
            conditions.append(ESPHeartbeatLog.timestamp >= after)

        stmt = select(func.count()).select_from(ESPHeartbeatLog).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def cleanup_old_entries(
        self,
        cutoff_date: datetime,
        batch_size: int = 5000,
        dry_run: bool = True,
    ) -> dict:
        """
        Delete heartbeat entries older than cutoff date.

        Args:
            cutoff_date: Delete entries older than this date
            batch_size: Maximum entries to delete per call
            dry_run: If True, only count without deleting

        Returns:
            Dict with cleanup stats
        """
        # Count entries to delete
        count_stmt = (
            select(func.count())
            .select_from(ESPHeartbeatLog)
            .where(ESPHeartbeatLog.timestamp < cutoff_date)
        )
        count_result = await self.session.execute(count_stmt)
        total_to_delete = count_result.scalar_one()

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would delete {total_to_delete} heartbeat logs "
                f"older than {cutoff_date}"
            )
            return {
                "status": "dry_run",
                "would_delete": total_to_delete,
                "cutoff_date": cutoff_date.isoformat(),
            }

        if total_to_delete == 0:
            return {
                "status": "success",
                "deleted": 0,
                "message": "No heartbeat logs to delete",
            }

        # Delete in batches using subquery
        subquery = (
            select(ESPHeartbeatLog.id)
            .where(ESPHeartbeatLog.timestamp < cutoff_date)
            .limit(batch_size)
        )

        delete_stmt = delete(ESPHeartbeatLog).where(ESPHeartbeatLog.id.in_(subquery))

        result = await self.session.execute(delete_stmt)
        deleted_count = result.rowcount

        logger.info(
            f"Deleted {deleted_count}/{total_to_delete} heartbeat logs " f"older than {cutoff_date}"
        )

        return {
            "status": "success",
            "deleted": deleted_count,
            "remaining": total_to_delete - deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    async def get_health_stats(
        self,
        device_id: str,
        hours: int = 24,
    ) -> dict:
        """
        Get health statistics for a device over time.

        Args:
            device_id: Device identifier
            hours: Time window in hours

        Returns:
            Dict with health stats (min/max/avg heap, rssi, etc.)
        """
        after = datetime.now(timezone.utc) - timedelta(hours=hours)

        stmt = select(
            func.count().label("count"),
            func.min(ESPHeartbeatLog.heap_free).label("min_heap"),
            func.max(ESPHeartbeatLog.heap_free).label("max_heap"),
            func.avg(ESPHeartbeatLog.heap_free).label("avg_heap"),
            func.min(ESPHeartbeatLog.wifi_rssi).label("min_rssi"),
            func.max(ESPHeartbeatLog.wifi_rssi).label("max_rssi"),
            func.avg(ESPHeartbeatLog.wifi_rssi).label("avg_rssi"),
            func.max(ESPHeartbeatLog.uptime).label("max_uptime"),
        ).where(
            and_(
                ESPHeartbeatLog.device_id == device_id,
                ESPHeartbeatLog.timestamp >= after,
            )
        )

        result = await self.session.execute(stmt)
        row = result.one()

        return {
            "device_id": device_id,
            "hours": hours,
            "count": row.count,
            "heap": {
                "min": row.min_heap,
                "max": row.max_heap,
                "avg": round(row.avg_heap) if row.avg_heap else None,
            },
            "rssi": {
                "min": row.min_rssi,
                "max": row.max_rssi,
                "avg": round(row.avg_rssi) if row.avg_rssi else None,
            },
            "max_uptime": row.max_uptime,
        }
