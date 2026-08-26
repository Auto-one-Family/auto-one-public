"""
MultispeQ Repository: Snapshot lookups and analytics queries.

Encapsulates all direct DB access for MultispeQ sensor_data rows so that
the API layer (``api/v1/multispeq.py``) does not need to call
``db.execute`` directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.esp import ESPDevice
from ..models.sensor import SensorData


class MultispeQRepository:
    """
    Repository for MultispeQ-specific sensor_data operations.

    Does not extend ``BaseRepository`` because its primary model
    (``SensorData``) is shared with ``SensorRepository``.  All queries
    are scoped to MultispeQ-relevant rows (virtual ESP devices or
    explicit ``plant_id`` / sensor_type filters).
    """

    # Marker on ``esp_devices.status`` that identifies virtual MultispeQ devices.
    _VIRTUAL_ESP_STATUS = "virtual"

    # Allowed grouping fields for aggregate queries.  Mapped to actual
    # SensorData columns to prevent SQL injection via query parameters.
    _AGGREGATE_GROUP_FIELDS: dict[str, Any] = {
        "zone_id": SensorData.zone_id,
        "subzone_id": SensorData.subzone_id,
        "plant_id": SensorData.plant_id,
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_snapshot_by_id(
        self, snapshot_id: uuid.UUID
    ) -> Optional[SensorData]:
        """
        Look up a single ``sensor_data`` row by primary key.

        Args:
            snapshot_id: ``sensor_data.id`` UUID.

        Returns:
            ``SensorData`` instance or ``None`` if not found.
        """
        stmt = select(SensorData).where(SensorData.id == snapshot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign_plant(
        self,
        snapshot_id: uuid.UUID,
        plant_id: uuid.UUID,
    ) -> None:
        """
        Update ``sensor_data.plant_id`` for a snapshot row.

        The caller is responsible for calling ``db.commit()`` after this
        method returns so that the surrounding request context decides when
        to finalise the transaction.

        Args:
            snapshot_id: ``sensor_data.id`` UUID of the snapshot to update.
            plant_id: New plant UUID to assign.
        """
        stmt = (
            update(SensorData)
            .where(SensorData.id == snapshot_id)
            .values(plant_id=plant_id)
        )
        await self.session.execute(stmt)

    async def get_aggregates(
        self,
        sensor_type: str,
        cutoff: datetime,
        group_by: str,
    ) -> list[dict[str, Any]]:
        """
        Return boxplot quintile statistics grouped by zone, subzone, or plant.

        Only rows from virtual MultispeQ ESP devices (``esp_devices.status ==
        'virtual'``) are considered.

        Args:
            sensor_type: ``SensorData.sensor_type`` to filter on.
            cutoff: Earliest timestamp to include (inclusive).
            group_by: One of ``"zone_id"``, ``"subzone_id"``, ``"plant_id"``.

        Returns:
            List of dicts with keys:
            ``group_label, min, q1, median, q3, max, n``.

        Raises:
            ValueError: When ``group_by`` is not a recognised key.
        """
        group_column = self._AGGREGATE_GROUP_FIELDS.get(group_by)
        if group_column is None:
            raise ValueError(
                f"Unsupported group_by '{group_by}'. "
                f"Allowed values: {sorted(self._AGGREGATE_GROUP_FIELDS.keys())}."
            )

        median_expr = func.percentile_cont(0.5).within_group(
            SensorData.processed_value.asc()
        )
        q1_expr = func.percentile_cont(0.25).within_group(
            SensorData.processed_value.asc()
        )
        q3_expr = func.percentile_cont(0.75).within_group(
            SensorData.processed_value.asc()
        )

        stmt = (
            select(
                group_column.label("group_label"),
                func.min(SensorData.processed_value).label("min"),
                q1_expr.label("q1"),
                median_expr.label("median"),
                q3_expr.label("q3"),
                func.max(SensorData.processed_value).label("max"),
                func.count().label("n"),
            )
            .join(ESPDevice, ESPDevice.id == SensorData.esp_id)
            .where(
                and_(
                    SensorData.sensor_type == sensor_type,
                    SensorData.timestamp >= cutoff,
                    SensorData.processed_value.is_not(None),
                    ESPDevice.status == self._VIRTUAL_ESP_STATUS,
                )
            )
            .group_by(group_column)
            .order_by(group_column)
        )

        rows = (await self.session.execute(stmt)).all()

        data: list[dict[str, Any]] = []
        for row in rows:
            label = row.group_label
            if label is not None and not isinstance(label, str):
                label = str(label)
            data.append(
                {
                    "group_label": label,
                    "min": float(row.min) if row.min is not None else None,
                    "q1": float(row.q1) if row.q1 is not None else None,
                    "median": (
                        float(row.median) if row.median is not None else None
                    ),
                    "q3": float(row.q3) if row.q3 is not None else None,
                    "max": float(row.max) if row.max is not None else None,
                    "n": int(row.n),
                }
            )
        return data

    async def get_correlation_data(
        self,
        x_type: str,
        cutoff: datetime,
    ) -> list[tuple[Optional[float], Optional[dict], Any]]:
        """
        Return raw rows for scatter / correlation plots.

        Only rows from virtual MultispeQ ESP devices are considered.
        Python-side filtering of ``sensor_metadata`` by a specific key
        remains the caller's responsibility so this method stays reusable.

        Args:
            x_type: ``SensorData.sensor_type`` for the X axis.
            cutoff: Earliest timestamp to include (inclusive).

        Returns:
            List of ``(processed_value, sensor_metadata, plant_id)`` tuples.
        """
        stmt = (
            select(
                SensorData.processed_value,
                SensorData.sensor_metadata,
                SensorData.plant_id,
            )
            .join(ESPDevice, ESPDevice.id == SensorData.esp_id)
            .where(
                and_(
                    SensorData.sensor_type == x_type,
                    SensorData.timestamp >= cutoff,
                    SensorData.processed_value.is_not(None),
                    ESPDevice.status == self._VIRTUAL_ESP_STATUS,
                )
            )
            .order_by(SensorData.timestamp.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(r.processed_value, r.sensor_metadata, r.plant_id) for r in rows]
