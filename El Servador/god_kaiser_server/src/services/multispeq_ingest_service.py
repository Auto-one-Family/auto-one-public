"""MultispeQ Ingest Service.

Bulk-import pipeline for MultispeQ / PhotosynQ snapshot measurements
(AUT-217). Used by both the manual upload endpoint and the future
PhotosynQ API-pull worker.

Pipeline (per measurement):

1. ``parser.expand_to_sensor_rows()`` — fan out the parsed measurement
   into one ``sensor_data``-compatible row per MultispeQ value
   (GPIO base 200, deterministic offsets).
2. Plant-Matching — resolve ``custom_fields["AutomationOne-Plant-ID"]``
   via :class:`PlantRepository.get_by_external_id`. Unmatched rows are
   counted as ``needs_review`` but still inserted (with ``plant_id=None``).
3. Device-Lookup — find an existing ``esp_devices`` row (status ``virtual``)
   for ``device_serial``. No auto-create here; missing devices are silently
   skipped (the HTTP endpoint pre-creates virtual devices on demand).
4. Dedup — ``sensor_data.sensor_metadata->>'measurement_id'`` plus
   ``sensor_type`` is treated as the natural key. Duplicates are counted
   and skipped.
5. INSERT — bulk-insert via ``insert(...).on_conflict_do_nothing()`` so
   parallel ingests stay race-safe.
6. Logic-Engine — non-blocking ``asyncio.create_task`` per imported row
   (only when an engine instance is registered).
7. Audit-Log — best-effort summary entry per ingest call.

The service is intentionally session-scoped (one session per call) and
performs its own commit so it can be reused from background workers.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_module
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import AuditSeverity, AuditSourceType
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorData
from ..db.repositories.audit_log_repo import AuditLogRepository
from ..db.repositories.plant_repo import PlantRepository
from ..integrations.multispeq.parser import (
    expand_to_sensor_rows,
    parse_photosynq_measurement,
    validate_calibration,
)
from .logic_engine import get_logic_engine

logger = get_logger(__name__)


# Stable GPIO base for the virtual MultispeQ device. Offsets 0..8 are
# assigned by ``expand_to_sensor_rows`` (see parser.py).
MULTISPEQ_GPIO_BASE: int = 200

# Audit event type kept local — single-feature scope.
_EVENT_MULTISPEQ_INGEST = "multispeq_ingest"


class ImportSource(str, Enum):
    """Origin of a MultispeQ ingest call."""

    manual_upload = "manual_upload"
    api_pull = "api_pull"


class IngestResult:
    """Mutable result aggregator returned by :meth:`IngestService.ingest`."""

    def __init__(self) -> None:
        self.imported: int = 0
        self.skipped_duplicates: int = 0
        self.needs_review: int = 0
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "skipped_duplicates": self.skipped_duplicates,
            "needs_review": self.needs_review,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


class IngestService:
    """Service that ingests parsed MultispeQ measurements into ``sensor_data``.

    Usage::

        service = IngestService(session)
        result = await service.ingest(
            measurements=[...],  # list of normalized measurement dicts
            source=ImportSource.manual_upload,
            zone_id="zone-a",
            subzone_id=None,
            calibration_date=date.today(),
            kaiser_id=None,
        )
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.logger = get_logger(__name__)
        self.plant_repo = PlantRepository(session)
        self.audit_repo = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest(
        self,
        measurements: list[dict],
        source: ImportSource,
        zone_id: str,
        subzone_id: Optional[str],
        calibration_date: date,
        kaiser_id: Optional[str],
        dry_run: bool = False,
        actor_user_id: Optional[int] = None,
    ) -> IngestResult:
        """Run the full ingest pipeline.

        Args:
            measurements: Normalized measurement dicts. Each dict must contain
                ``device_serial`` (str), ``timestamp`` (datetime, UTC), and
                ``sensor_values`` (dict of raw PhotosynQ key → value). Optional
                keys: ``measurement_id``, ``custom_fields``, ``protocol_id``.
            source: Import origin (manual upload vs. API pull).
            zone_id: Target zone ID (snapshot only — written to sensor_data).
            subzone_id: Optional subzone ID.
            calibration_date: Calibration validity date (audit context).
            kaiser_id: Optional tenant filter for plant lookups.
            dry_run: When True, no rows are inserted, no logic engine is
                triggered, and no audit log is written. Counts are still
                computed exactly as for a real run.
            actor_user_id: Optional ``user_accounts.id`` for audit ``source_id``.

        Returns:
            :class:`IngestResult` with imported / skipped / needs-review
            counters and any warnings/errors.
        """
        result = IngestResult()
        rows_to_insert: list[dict] = []
        # Track logic-engine triggers per (esp_uuid, gpio, sensor_type, value).
        logic_triggers: list[tuple[uuid_module.UUID, int, str, float]] = []

        for index, measurement in enumerate(measurements):
            try:
                await self._process_measurement(
                    measurement=measurement,
                    index=index,
                    zone_id=zone_id,
                    subzone_id=subzone_id,
                    kaiser_id=kaiser_id,
                    source=source,
                    rows_to_insert=rows_to_insert,
                    logic_triggers=logic_triggers,
                    result=result,
                )
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.exception(
                    "MultispeQ measurement #%d failed: %s", index, exc
                )
                result.errors.append(f"measurement[{index}]: {exc}")

        # Bulk insert with ON CONFLICT DO NOTHING for race-safety.
        if rows_to_insert and not dry_run:
            try:
                stmt = pg_insert(SensorData).values(rows_to_insert)
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_sensor_data_esp_gpio_type_timestamp",
                )
                exec_result = await self.session.execute(stmt)
                inserted = exec_result.rowcount or 0
                # rowcount may be -1 on some drivers; fall back to optimistic count.
                if inserted < 0:
                    inserted = len(rows_to_insert)
                # Anything not inserted is a duplicate hit at the DB level.
                if inserted < len(rows_to_insert):
                    result.skipped_duplicates += len(rows_to_insert) - inserted
                result.imported += inserted
                await self.session.commit()
            except Exception as exc:
                await self.session.rollback()
                self.logger.exception("Bulk insert failed: %s", exc)
                result.errors.append(f"bulk_insert: {exc}")
                return result
        elif rows_to_insert and dry_run:
            # Dry-run accounting: rows that would have been written.
            result.imported += len(rows_to_insert)

        # Fire-and-forget logic engine evaluation per inserted row.
        if logic_triggers and not dry_run:
            engine = get_logic_engine()
            if engine is not None:
                for esp_uuid, gpio, sensor_type, value in logic_triggers:
                    asyncio.create_task(
                        engine.evaluate_sensor_data(
                            esp_id=str(esp_uuid),
                            gpio=gpio,
                            sensor_type=sensor_type,
                            value=value,
                            zone_id=zone_id,
                            subzone_id=subzone_id,
                        )
                    )
            else:
                self.logger.debug(
                    "LogicEngine not initialised — skipping evaluation for "
                    "%d MultispeQ rows",
                    len(logic_triggers),
                )

        # Best-effort audit log (never blocks the caller).
        if not dry_run:
            await self._audit_safe(
                actor_user_id=actor_user_id,
                source=source,
                zone_id=zone_id,
                subzone_id=subzone_id,
                calibration_date=calibration_date,
                kaiser_id=kaiser_id,
                result=result,
                measurement_count=len(measurements),
            )

        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _process_measurement(
        self,
        *,
        measurement: dict,
        index: int,
        zone_id: str,
        subzone_id: Optional[str],
        kaiser_id: Optional[str],
        source: ImportSource,
        rows_to_insert: list[dict],
        logic_triggers: list[tuple[uuid_module.UUID, int, str, float]],
        result: IngestResult,
    ) -> None:
        device_serial = measurement.get("device_serial")
        if not device_serial:
            result.errors.append(f"measurement[{index}]: missing device_serial")
            return

        timestamp = measurement.get("timestamp")
        if not isinstance(timestamp, datetime):
            result.errors.append(
                f"measurement[{index}]: missing or invalid timestamp"
            )
            return
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        measurement_id = measurement.get("measurement_id")
        if not measurement_id:
            result.errors.append(
                f"measurement[{index}]: missing measurement_id"
            )
            return

        # 1. Parse PhotosynQ payload into internal sensor_type → float dict.
        sensor_values = measurement.get("sensor_values") or {}
        parsed = parse_photosynq_measurement(sensor_values)
        if not parsed:
            result.warnings.append(
                f"measurement[{index}] ({measurement_id}): no recognised "
                "PhotosynQ fields, skipping"
            )
            return

        # Calibration warnings are non-fatal.
        for warning in validate_calibration(parsed):
            result.warnings.append(
                f"measurement[{index}] ({measurement_id}): {warning}"
            )

        # 2. Plant-Matching.
        custom_fields = measurement.get("custom_fields") or {}
        external_plant_id = custom_fields.get("AutomationOne-Plant-ID")
        plant_uuid: Optional[uuid_module.UUID] = None
        if external_plant_id:
            plant = await self.plant_repo.get_by_external_id(
                external_id=str(external_plant_id),
                kaiser_id=kaiser_id,
            )
            if plant is not None:
                plant_uuid = plant.plant_id
            else:
                result.needs_review += 1
                result.warnings.append(
                    f"measurement[{index}] ({measurement_id}): plant "
                    f"'{external_plant_id}' not found — flagged for review"
                )
        else:
            # No plant tag at all — also flag for manual assignment.
            result.needs_review += 1

        # 3. Device-Lookup (virtual ESP).
        esp_device = await self._get_virtual_device(device_serial)
        if esp_device is None:
            result.warnings.append(
                f"measurement[{index}] ({measurement_id}): no virtual ESP "
                f"for device_serial='{device_serial}', skipping"
            )
            return

        # 4. Build candidate rows. We pass esp_uuid as the row's esp_id field.
        rows = expand_to_sensor_rows(
            parsed=parsed,
            esp_id=str(esp_device.id),
            gpio_base=MULTISPEQ_GPIO_BASE,
            timestamp=timestamp,
            plant_id=plant_uuid,
        )

        data_source_value = (
            "multispeq_upload"
            if source == ImportSource.manual_upload
            else "multispeq_api_pull"
        )

        for row in rows:
            # Per-row dedup: skip if (measurement_id, sensor_type) already exists.
            if await self._is_duplicate(measurement_id, row["sensor_type"]):
                result.skipped_duplicates += 1
                continue

            metadata = {
                "measurement_id": measurement_id,
                "source": source.value,
            }
            if measurement.get("protocol_id") is not None:
                metadata["protocol_id"] = measurement["protocol_id"]
            if external_plant_id:
                metadata["external_plant_id"] = external_plant_id

            # Overwrite parser defaults with ingest-specific fields.
            row["esp_id"] = esp_device.id
            row["processing_mode"] = "imported"
            row["data_source"] = data_source_value
            row["zone_id"] = zone_id
            row["subzone_id"] = subzone_id
            row["device_name"] = esp_device.name
            row["sensor_metadata"] = metadata

            rows_to_insert.append(row)
            logic_triggers.append(
                (
                    esp_device.id,
                    row["gpio"],
                    row["sensor_type"],
                    float(row["processed_value"]),
                )
            )

    async def _get_virtual_device(
        self, device_serial: str
    ) -> Optional[ESPDevice]:
        """Find an existing virtual ESP for ``device_serial``.

        Only devices with ``status == 'virtual'`` qualify. Returns ``None`` if
        no matching active device exists.
        """
        stmt = select(ESPDevice).where(
            ESPDevice.device_id == device_serial,
            ESPDevice.status == "virtual",
            ESPDevice.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _is_duplicate(
        self, measurement_id: str, sensor_type: str
    ) -> bool:
        """Check whether a row with ``(measurement_id, sensor_type)`` exists."""
        stmt = select(func.count(SensorData.id)).where(
            SensorData.sensor_type == sensor_type,
            SensorData.sensor_metadata["measurement_id"].astext
            == measurement_id,
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()
        return bool(count and count > 0)

    async def _audit_safe(
        self,
        *,
        actor_user_id: Optional[int],
        source: ImportSource,
        zone_id: str,
        subzone_id: Optional[str],
        calibration_date: date,
        kaiser_id: Optional[str],
        result: IngestResult,
        measurement_count: int,
    ) -> None:
        """Best-effort audit log — never blocks the caller on failure."""
        try:
            severity = (
                AuditSeverity.WARNING if result.errors else AuditSeverity.INFO
            )
            details: dict[str, Any] = {
                "source": source.value,
                "zone_id": zone_id,
                "subzone_id": subzone_id,
                "calibration_date": calibration_date.isoformat(),
                "kaiser_id": kaiser_id,
                "measurement_count": measurement_count,
                **result.to_dict(),
            }
            await self.audit_repo.create(
                event_type=_EVENT_MULTISPEQ_INGEST,
                severity=severity,
                source_type=AuditSourceType.API,
                source_id=str(actor_user_id) if actor_user_id is not None else None,
                status="success" if not result.errors else "failed",
                message=(
                    f"MultispeQ ingest ({source.value}): "
                    f"{result.imported} imported, "
                    f"{result.skipped_duplicates} duplicates, "
                    f"{result.needs_review} need review"
                ),
                details=details,
            )
            await self.session.commit()
        except Exception as exc:  # pragma: no cover - audit must not fail caller
            self.logger.warning(
                "Failed to write audit log for MultispeQ ingest: %s", exc
            )
