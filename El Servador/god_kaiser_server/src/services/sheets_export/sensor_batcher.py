"""
Sensor batcher for the Sheets export pipeline (AUT-445 / S4).

Responsibilities:
- Pull new ``sensor_data`` rows since the last cursor.
- Enrich with ``sensor_configs`` (label / onewire / i2c) and
  ``esp_devices`` (device_id) for the spreadsheet columns mandated by
  D5 / D6.
- Map a row to the canonical 13-column Sheets payload.

The batcher does NOT touch Sheets or the cursor — it returns a
``SensorBatch`` that the orchestrating service writes through
``SheetsClient.append_rows`` and then commits the cursor on success.

Pagination is by ``(timestamp, id)`` lex-ordering so the cursor is
deterministic even with high-volume inserts that share a timestamp.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.models.esp import ESPDevice
from ...db.models.sensor import SensorConfig, SensorData

logger = get_logger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")

# Frozen column order — change only with a Linear-coordinated D-update.
SENSOR_HEADER: List[str] = [
    "timestamp_utc",
    "timestamp_local_berlin",
    "esp_id",
    "gpio",
    "sensor_type",
    "sensor_label",
    "onewire_address",
    "i2c_address",
    "value",
    "unit",
    "zone_id",
    "subzone_id",
    "config_id",
]


@dataclass
class SensorRow:
    """One sensor measurement row prepared for Sheets."""

    timestamp_utc: datetime
    sensor_data_id: uuid.UUID
    esp_device_id: Optional[str]
    gpio: int
    sensor_type: str
    sensor_label: str
    onewire_address: str
    i2c_address: str
    value: Optional[float]
    unit: str
    zone_id: str
    subzone_id: str
    config_id: str

    def to_sheet_row(self) -> List[Any]:
        local = self.timestamp_utc.astimezone(BERLIN)
        return [
            self.timestamp_utc.astimezone(timezone.utc).isoformat(),
            local.strftime("%Y-%m-%d %H:%M:%S"),
            self.esp_device_id or "",
            self.gpio,
            self.sensor_type,
            self.sensor_label,
            self.onewire_address,
            self.i2c_address,
            self.value if self.value is not None else "",
            self.unit,
            self.zone_id,
            self.subzone_id,
            self.config_id,
        ]


@dataclass
class SensorBatch:
    """All rows fetched in one tick + the new cursor anchor."""

    rows: List[SensorRow] = field(default_factory=list)
    last_row_id: Optional[uuid.UUID] = None
    last_row_timestamp: Optional[datetime] = None

    def is_empty(self) -> bool:
        return not self.rows

    def to_sheet_values(self) -> List[List[Any]]:
        return [row.to_sheet_row() for row in self.rows]


class SensorExportBatcher:
    """
    Reads ``sensor_data`` (+ joins) and produces Sheets-ready rows.

    A single instance is bound to one ``AsyncSession`` for the duration
    of one export tick.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch_batch(
        self,
        *,
        last_timestamp_iso: Optional[str],
        last_id: Optional[str],
        limit: int,
    ) -> SensorBatch:
        """
        Pull at most ``limit`` rows newer than the given cursor anchor.

        The cursor is a tuple ``(timestamp, id)``. When either component
        is missing we start from the very beginning of the table.
        """
        anchor = _parse_cursor_anchor(last_timestamp_iso, last_id)

        stmt = (
            select(
                SensorData.id,
                SensorData.timestamp,
                SensorData.esp_id,
                SensorData.gpio,
                SensorData.sensor_type,
                SensorData.processed_value,
                SensorData.raw_value,
                SensorData.unit,
                SensorData.zone_id,
                SensorData.subzone_id,
                SensorData.device_name,
                ESPDevice.device_id.label("esp_device_id"),
            )
            .outerjoin(ESPDevice, ESPDevice.id == SensorData.esp_id)
            .order_by(SensorData.timestamp.asc(), SensorData.id.asc())
            .limit(limit)
        )
        if anchor is not None:
            anchor_ts, anchor_id = anchor
            stmt = stmt.where(
                or_(
                    SensorData.timestamp > anchor_ts,
                    and_(
                        SensorData.timestamp == anchor_ts,
                        SensorData.id > anchor_id,
                    ),
                )
            )

        result = await self._session.execute(stmt)
        rows: List[Any] = list(result.all())
        if not rows:
            return SensorBatch()

        config_lookup = await self._fetch_sensor_configs(rows)
        batch = SensorBatch()
        for r in rows:
            cfg = _pick_config(r, config_lookup)
            sensor_data_id = uuid.UUID(str(r.id))
            value = (
                r.processed_value if r.processed_value is not None else r.raw_value
            )
            timestamp = _ensure_aware(r.timestamp)
            batch.rows.append(
                SensorRow(
                    timestamp_utc=timestamp,
                    sensor_data_id=sensor_data_id,
                    esp_device_id=r.esp_device_id or r.device_name,
                    gpio=int(r.gpio),
                    sensor_type=str(r.sensor_type),
                    sensor_label=str(cfg.sensor_name) if cfg is not None else "",
                    onewire_address=(
                        str(cfg.onewire_address)
                        if cfg is not None and cfg.onewire_address
                        else ""
                    ),
                    i2c_address=(
                        f"0x{int(cfg.i2c_address):02X}"
                        if cfg is not None and cfg.i2c_address is not None
                        else ""
                    ),
                    value=float(value) if value is not None else None,
                    unit=str(r.unit) if r.unit is not None else "",
                    zone_id=str(r.zone_id) if r.zone_id is not None else "",
                    subzone_id=str(r.subzone_id) if r.subzone_id is not None else "",
                    config_id=str(cfg.id) if cfg is not None else "",
                )
            )
            batch.last_row_id = sensor_data_id
            batch.last_row_timestamp = timestamp

        return batch

    async def _fetch_sensor_configs(
        self,
        rows: Sequence[Any],
    ) -> Dict[tuple, SensorConfig]:
        """
        Best-effort fetch of matching :class:`SensorConfig` rows.

        Key is ``(esp_id, gpio, sensor_type)`` — when multiple configs
        match (multi-value sensor), the first hit wins. We do not raise
        if a config is missing (sensor may have been deleted while data
        remains).
        """
        keys: set[tuple] = set()
        for r in rows:
            if r.esp_id is None:
                continue
            keys.add((r.esp_id, r.gpio, r.sensor_type))
        if not keys:
            return {}

        tuples = list(keys)
        stmt = select(SensorConfig).where(
            tuple_(
                SensorConfig.esp_id,
                SensorConfig.gpio,
                SensorConfig.sensor_type,
            ).in_(tuples)
        )
        result = await self._session.execute(stmt)
        out: Dict[tuple, SensorConfig] = {}
        for cfg in result.scalars().all():
            out[(cfg.esp_id, cfg.gpio, cfg.sensor_type)] = cfg
        return out


# -----------------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------------


def _parse_cursor_anchor(
    last_timestamp_iso: Optional[str],
    last_id: Optional[str],
) -> Optional[tuple[datetime, uuid.UUID]]:
    if not last_timestamp_iso or not last_id:
        return None
    try:
        ts = datetime.fromisoformat(last_timestamp_iso)
    except ValueError:
        logger.warning(
            "[sheets_export] Could not parse cursor timestamp %r — restarting from head",
            last_timestamp_iso,
        )
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    try:
        row_id = uuid.UUID(str(last_id))
    except (ValueError, TypeError):
        logger.warning(
            "[sheets_export] Could not parse cursor row id %r — restarting from head",
            last_id,
        )
        return None
    return ts, row_id


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _pick_config(
    row: Any,
    lookup: Dict[tuple, SensorConfig],
) -> Optional[SensorConfig]:
    if row.esp_id is None:
        return None
    return lookup.get((row.esp_id, row.gpio, row.sensor_type))
