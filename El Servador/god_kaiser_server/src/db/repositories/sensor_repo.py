"""
Sensor Repository: Sensor Config and Data Queries
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, delete, func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...services.calibration_payloads import canonicalize_calibration_data
from ..models.sensor import SensorConfig, SensorData
from ..models.esp import ESPDevice
from ..models.enums import DataSource
from .base_repo import BaseRepository

logger = get_logger(__name__)


class SensorRepository(BaseRepository[SensorConfig]):
    """
    Sensor Repository with sensor-specific queries.

    Manages both SensorConfig and SensorData models.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(SensorConfig, session)

    async def create(self, sensor: Optional[SensorConfig] = None, **fields) -> SensorConfig:
        """
        Create a new sensor config.

        Accepts either a SensorConfig instance or model field kwargs.
        """
        if sensor is None:
            sensor = SensorConfig(**fields)
        self.session.add(sensor)
        await self.session.flush()
        await self.session.refresh(sensor)
        return sensor

    async def create_if_not_exists(self, **fields) -> tuple[SensorConfig, bool]:
        """
        Create a sensor config only if no duplicate exists; return existing otherwise.

        Uses IntegrityError catch to handle race conditions safely.
        The COALESCE-based unique index (V19-F02+F13) ensures this works
        even when onewire_address/i2c_address are NULL.

        Returns:
            Tuple of (SensorConfig, created: bool).
            created=True if a new row was inserted, False if existing was returned.
        """
        esp_id = fields.get("esp_id")
        gpio = fields.get("gpio")
        sensor_type = fields.get("sensor_type", "")
        i2c_address = fields.get("i2c_address")

        # Check for existing config first (fast path, avoids unnecessary INSERT)
        if i2c_address is not None:
            existing = await self.get_by_esp_gpio_type_and_i2c(
                esp_id, gpio, sensor_type, i2c_address
            )
        else:
            existing = await self.get_by_esp_gpio_and_type(esp_id, gpio, sensor_type)
        if existing:
            return existing, False

        # Try to create — catch IntegrityError for race conditions
        sensor = SensorConfig(**fields)
        try:
            self.session.add(sensor)
            await self.session.flush()
            await self.session.refresh(sensor)
            return sensor, True
        except IntegrityError:
            await self.session.rollback()
            logger.debug(
                "Duplicate sensor_config caught: esp=%s gpio=%s type=%s — returning existing",
                esp_id,
                gpio,
                sensor_type,
            )
            # Re-fetch after rollback
            if i2c_address is not None:
                existing = await self.get_by_esp_gpio_type_and_i2c(
                    esp_id, gpio, sensor_type, i2c_address
                )
            else:
                existing = await self.get_by_esp_gpio_and_type(esp_id, gpio, sensor_type)
            if existing:
                return existing, False
            raise

    async def get_by_esp_and_gpio(self, esp_id: uuid.UUID, gpio: int) -> Optional[SensorConfig]:
        """
        Get sensor by ESP ID and GPIO (crash-safe for multi-value sensors).

        DEPRECATED: Prefer get_all_by_esp_and_gpio() or get_by_esp_gpio_and_type()
        for explicit multi-value sensor handling.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number

        Returns:
            SensorConfig or None if not found. Returns first config if multiple exist.
        """
        configs = await self.get_all_by_esp_and_gpio(esp_id, gpio)
        if len(configs) > 1:
            logger.warning(
                "Multiple configs for esp=%s gpio=%s: %s. Returning first.",
                esp_id,
                gpio,
                [c.sensor_type for c in configs],
            )
        return configs[0] if configs else None

    async def get_all_by_esp_and_gpio(self, esp_id: uuid.UUID, gpio: int) -> list[SensorConfig]:
        """
        Get ALL sensors on a specific GPIO (Multi-Value Support).

        For multi-value sensors like SHT31, multiple sensor_configs
        can exist on the same GPIO (e.g., sht31_temp + sht31_humidity).

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number

        Returns:
            List of SensorConfig instances on this GPIO
        """
        stmt = select(SensorConfig).where(SensorConfig.esp_id == esp_id, SensorConfig.gpio == gpio)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_esp_gpio_and_type(
        self, esp_id: uuid.UUID, gpio: int, sensor_type: str
    ) -> Optional[SensorConfig]:
        """
        Get sensor by ESP ID, GPIO, and sensor_type (Multi-Value Support).

        For multi-value sensors, this returns the specific sensor_type
        on a GPIO (e.g., only sht31_temp, not sht31_humidity).

        BUG-08 fix: Uses list-based approach instead of scalar_one_or_none()
        to avoid MultipleResultsFound when multiple OneWire sensors (e.g.
        2x DS18B20) share the same (esp_id, gpio, sensor_type) but differ
        only by onewire_address.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            sensor_type: Sensor type string (e.g., 'sht31_temp')

        Returns:
            SensorConfig or None if not found. Returns first config if multiple exist.
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.gpio == gpio,
            func.lower(SensorConfig.sensor_type) == sensor_type.lower(),
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if len(rows) > 1:
            logger.warning(
                "Multiple configs for esp=%s gpio=%s type=%s: %d results. "
                "OneWire/I2C without address? Returning first match.",
                esp_id,
                gpio,
                sensor_type,
                len(rows),
            )
        return rows[0] if rows else None

    async def get_by_esp(self, esp_id: uuid.UUID) -> list[SensorConfig]:
        """
        Get all sensors for an ESP device.

        Args:
            esp_id: ESP device UUID

        Returns:
            List of SensorConfig instances
        """
        stmt = select(SensorConfig).where(SensorConfig.esp_id == esp_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_esp(self, esp_id: uuid.UUID) -> int:
        """
        Count sensors for an ESP device.

        Args:
            esp_id: ESP device UUID

        Returns:
            Number of sensors
        """
        stmt = (
            select(func.count())
            .select_from(SensorConfig)
            .where(
                SensorConfig.esp_id == esp_id,
                SensorConfig.enabled
                == True,  # noqa: E712 — only count enabled configs to match ESP count
                SensorConfig.interface_type
                != "VIRTUAL",  # exclude server-side virtual sensors (e.g. VPD) — ESP never receives them
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_enabled(self) -> list[SensorConfig]:
        """
        Get all enabled sensors.

        Returns:
            List of enabled SensorConfig instances
        """
        stmt = select(SensorConfig).where(SensorConfig.enabled == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pi_enhanced(self) -> list[SensorConfig]:
        """
        Get all Pi-Enhanced sensors.

        Returns:
            List of Pi-Enhanced SensorConfig instances
        """
        stmt = select(SensorConfig).where(SensorConfig.pi_enhanced == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sensor_type(self, sensor_type: str) -> list[SensorConfig]:
        """
        Get sensors by type.

        Args:
            sensor_type: Sensor type (temperature, humidity, ph, etc.)

        Returns:
            List of SensorConfig instances
        """
        stmt = select(SensorConfig).where(SensorConfig.sensor_type == sensor_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def query_paginated(
        self,
        esp_device_id: Optional[str] = None,
        sensor_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        runtime_only: bool = True,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[tuple[SensorConfig, Optional[str]]], int]:
        """
        Query sensors with DB-side filtering and pagination.

        Returns list of (SensorConfig, esp_device_id) and total count.
        """
        filters = []
        if esp_device_id:
            filters.append(ESPDevice.device_id == esp_device_id)
        if sensor_type:
            filters.append(func.lower(SensorConfig.sensor_type) == sensor_type.lower())
        if enabled is not None:
            filters.append(SensorConfig.enabled == enabled)
        if runtime_only:
            filters.append(ESPDevice.deleted_at.is_(None))
        elif not include_deleted:
            filters.append(ESPDevice.deleted_at.is_(None))

        count_stmt = (
            select(func.count(SensorConfig.id))
            .select_from(SensorConfig)
            .join(ESPDevice, SensorConfig.esp_id == ESPDevice.id)
        )
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = select(SensorConfig, ESPDevice.device_id).join(
            ESPDevice, SensorConfig.esp_id == ESPDevice.id
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = (
            stmt.order_by(SensorConfig.created_at.desc(), SensorConfig.id.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        return rows, total

    # SensorData operations
    async def save_data(
        self,
        esp_id: uuid.UUID,
        gpio: int,
        sensor_type: str,
        raw_value: float,
        processed_value: Optional[float] = None,
        unit: Optional[str] = None,
        processing_mode: str = "raw",
        quality: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
        data_source: str = DataSource.PRODUCTION.value,
        zone_id: Optional[str] = None,
        subzone_id: Optional[str] = None,
        device_name: Optional[str] = None,
    ) -> Optional[SensorData]:
        """
        Save sensor data. Returns None if a duplicate already exists.

        Duplicates are detected via UNIQUE constraint on
        (esp_id, gpio, sensor_type, timestamp). This handles MQTT QoS 1
        redelivery where the broker resends a message if PUBACK is delayed.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            sensor_type: Sensor type
            raw_value: Raw sensor value
            processed_value: Processed value (optional)
            unit: Measurement unit (optional)
            processing_mode: Processing mode (raw, pi_enhanced, local)
            quality: Data quality (good, fair, poor, error)
            timestamp: ESP32 timestamp (converted to datetime). If None, uses server time as fallback.
            metadata: Additional metadata
            data_source: Data source (production, mock, test, simulation)
            zone_id: Zone ID at measurement time (Phase 0.1)
            subzone_id: Subzone ID at measurement time (Phase 0.1)
            device_name: Device name at measurement time (T02-Fix1)

        Returns:
            Created SensorData instance, or None if duplicate was silently ignored
        """
        # Ensure timezone-aware UTC timestamp for TIMESTAMPTZ column
        ts = timestamp or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # PostgreSQL fast path: idempotent insert without exception noise.
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name == "postgresql":
            insert_stmt = (
                pg_insert(SensorData)
                .values(
                    esp_id=esp_id,
                    gpio=gpio,
                    sensor_type=sensor_type,
                    raw_value=raw_value,
                    processed_value=processed_value,
                    unit=unit,
                    processing_mode=processing_mode,
                    quality=quality,
                    timestamp=ts,
                    sensor_metadata=metadata,  # Model field is sensor_metadata
                    data_source=data_source,
                    zone_id=zone_id,
                    subzone_id=subzone_id,
                    device_name=device_name,
                )
                .on_conflict_do_nothing(constraint="uq_sensor_data_esp_gpio_type_timestamp")
                .returning(SensorData.id)
            )
            inserted_id = (await self.session.execute(insert_stmt)).scalar_one_or_none()
            if inserted_id is None:
                logger.debug(
                    "Duplicate sensor_data ignored: esp=%s, gpio=%s, type=%s, ts=%s",
                    esp_id,
                    gpio,
                    sensor_type,
                    ts,
                )
                return None

            created = await self.session.get(SensorData, inserted_id)
            return created

        # Generic fallback (e.g. SQLite in unit tests): use nested transaction so
        # duplicate errors do not roll back the surrounding ingest transaction.
        sensor_data = SensorData(
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=sensor_type,
            raw_value=raw_value,
            processed_value=processed_value,
            unit=unit,
            processing_mode=processing_mode,
            quality=quality,
            timestamp=ts,
            sensor_metadata=metadata,  # Model field is sensor_metadata
            data_source=data_source,
            zone_id=zone_id,
            subzone_id=subzone_id,
            device_name=device_name,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(sensor_data)
                await self.session.flush()
            await self.session.refresh(sensor_data)
            return sensor_data
        except IntegrityError:
            logger.debug(
                "Duplicate sensor_data ignored: esp=%s, gpio=%s, type=%s, ts=%s",
                esp_id,
                gpio,
                sensor_type,
                ts,
            )
            return None

    async def get_latest_data(
        self, esp_id: uuid.UUID, gpio: int, sensor_type: Optional[str] = None, limit: int = 1
    ) -> list[SensorData]:
        """
        Get latest sensor data.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            sensor_type: Optional sensor type filter (required for multi-value
                         sensors like SHT31 where temp and humidity share a GPIO)
            limit: Number of latest records

        Returns:
            List of latest SensorData instances
        """
        filters = [SensorData.esp_id == esp_id, SensorData.gpio == gpio]
        if sensor_type:
            filters.append(SensorData.sensor_type == sensor_type)

        stmt = select(SensorData).where(*filters).order_by(SensorData.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_reading(
        self, esp_id: uuid.UUID, gpio: int, sensor_type: Optional[str] = None
    ) -> Optional[SensorData]:
        """
        Get latest sensor reading (single item).

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            sensor_type: Optional sensor type filter (required for multi-value
                         sensors like SHT31 where temp and humidity share a GPIO)

        Returns:
            Latest SensorData instance or None
        """
        data = await self.get_latest_data(esp_id, gpio, sensor_type=sensor_type, limit=1)
        return data[0] if data else None

    async def get_latest_reading_for_esp(
        self,
        esp_id: uuid.UUID,
        sensor_type: str,
    ) -> Optional[SensorData]:
        """
        Get latest sensor reading for an ESP device regardless of GPIO pin.

        Used for cross-sensor lookups where the GPIO of the partner sensor is
        unknown (e.g. ATC: find the latest temperature reading for an EC sensor's
        ESP without knowing which GPIO the temperature sensor is on).

        Args:
            esp_id: ESP device UUID
            sensor_type: Sensor type to search for (e.g. "temperature", "sht31_temp")

        Returns:
            Latest SensorData instance or None
        """
        stmt = (
            select(SensorData)
            .where(SensorData.esp_id == esp_id, SensorData.sensor_type == sensor_type)
            .order_by(SensorData.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_readings_batch(
        self,
        sensor_keys: list[tuple[uuid.UUID, int]],
    ) -> dict[tuple[uuid.UUID, int], SensorData]:
        """
        Get latest reading for multiple sensors in a single batch query.

        This method optimizes the common pattern of fetching the latest reading
        for many sensors by using a subquery with MAX(timestamp) instead of
        N individual queries.

        Uses index: idx_esp_gpio_timestamp (esp_id, gpio, timestamp)

        NOTE: For multi-value sensors (e.g. SHT31 with temp + humidity on same
        GPIO), use get_latest_readings_batch_by_config() instead, which includes
        sensor_type in the key to avoid collisions.

        Args:
            sensor_keys: List of (esp_id, gpio) tuples identifying sensors

        Returns:
            Dict mapping (esp_id, gpio) tuple to latest SensorData.
            Sensors without any readings are not included in the result.

        Example:
            >>> keys = [(uuid1, 34), (uuid2, 35), (uuid3, 36)]
            >>> readings = await repo.get_latest_readings_batch(keys)
            >>> latest = readings.get((uuid1, 34))  # SensorData or None
        """
        if not sensor_keys:
            return {}

        # Subquery: Get MAX(timestamp) per (esp_id, gpio)
        max_timestamp_subq = (
            select(
                SensorData.esp_id,
                SensorData.gpio,
                func.max(SensorData.timestamp).label("max_ts"),
            )
            .where(tuple_(SensorData.esp_id, SensorData.gpio).in_(sensor_keys))
            .group_by(SensorData.esp_id, SensorData.gpio)
            .subquery()
        )

        # Main query: Join with subquery to get full SensorData rows
        stmt = select(SensorData).join(
            max_timestamp_subq,
            and_(
                SensorData.esp_id == max_timestamp_subq.c.esp_id,
                SensorData.gpio == max_timestamp_subq.c.gpio,
                SensorData.timestamp == max_timestamp_subq.c.max_ts,
            ),
        )

        result = await self.session.execute(stmt)
        data_list = result.scalars().all()

        # Build lookup dict: (esp_id, gpio) → SensorData
        return {(d.esp_id, d.gpio): d for d in data_list}

    async def get_latest_readings_batch_by_config(
        self,
        sensor_keys: list[tuple[uuid.UUID, int, str]],
    ) -> dict[tuple[uuid.UUID, int, str], SensorData]:
        """
        Get latest reading for multiple sensors including sensor_type in key.

        This variant correctly handles multi-value sensors (e.g. SHT31 with
        sht31_temp + sht31_humidity on the same GPIO) by grouping on
        (esp_id, gpio, sensor_type) instead of just (esp_id, gpio).

        Args:
            sensor_keys: List of (esp_id, gpio, sensor_type) tuples

        Returns:
            Dict mapping (esp_id, gpio, sensor_type) to latest SensorData.
            Sensors without any readings are not included in the result.

        Example:
            >>> keys = [(uuid1, 21, 'sht31_temp'), (uuid1, 21, 'sht31_humidity')]
            >>> readings = await repo.get_latest_readings_batch_by_config(keys)
            >>> latest_temp = readings.get((uuid1, 21, 'sht31_temp'))
            >>> latest_hum = readings.get((uuid1, 21, 'sht31_humidity'))
        """
        if not sensor_keys:
            return {}

        # Subquery: Get MAX(timestamp) per (esp_id, gpio, sensor_type)
        max_timestamp_subq = (
            select(
                SensorData.esp_id,
                SensorData.gpio,
                SensorData.sensor_type,
                func.max(SensorData.timestamp).label("max_ts"),
            )
            .where(
                tuple_(SensorData.esp_id, SensorData.gpio, SensorData.sensor_type).in_(sensor_keys)
            )
            .group_by(SensorData.esp_id, SensorData.gpio, SensorData.sensor_type)
            .subquery()
        )

        # Main query: Join with subquery to get full SensorData rows
        stmt = select(SensorData).join(
            max_timestamp_subq,
            and_(
                SensorData.esp_id == max_timestamp_subq.c.esp_id,
                SensorData.gpio == max_timestamp_subq.c.gpio,
                SensorData.sensor_type == max_timestamp_subq.c.sensor_type,
                SensorData.timestamp == max_timestamp_subq.c.max_ts,
            ),
        )

        result = await self.session.execute(stmt)
        data_list = result.scalars().all()

        # Build lookup dict: (esp_id, gpio, sensor_type) → SensorData
        return {(d.esp_id, d.gpio, d.sensor_type): d for d in data_list}

    # Resolution string → PostgreSQL date_trunc interval mapping
    _RESOLUTION_MAP = {
        "1m": "minute",
        "5m": None,  # special: uses date_trunc + integer division trick
        "1h": "hour",
        "1d": "day",
    }

    async def query_data(
        self,
        esp_id: Optional[uuid.UUID] = None,
        gpio: Optional[int] = None,
        sensor_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        quality: Optional[str] = None,
        data_source: Optional[DataSource] = None,
        zone_id: Optional[str] = None,
        subzone_id: Optional[str] = None,
        sensor_config_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        resolution: Optional[str] = None,
        before_timestamp: Optional[datetime] = None,
    ) -> list:
        """
        Query sensor data with optional filters.

        Args:
            esp_id: Optional ESP device UUID
            gpio: Optional GPIO pin number
            sensor_type: Optional sensor type filter
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            quality: Optional quality filter
            data_source: Optional data source filter (production, mock, test, simulation)
            zone_id: Optional zone filter (Phase 0.1)
            subzone_id: Optional subzone filter (Phase 0.1)
            sensor_config_id: Optional sensor config UUID filter (T13-R2)
            limit: Maximum number of records (default: 100)
            resolution: Time resolution for aggregation (raw, 1m, 5m, 1h, 1d)
            before_timestamp: Cursor for pagination — only return data before this timestamp

        Returns:
            List of SensorData instances (raw) or list of Row tuples (aggregated)
        """
        # Build common filter conditions
        filters = []

        # T13-R2: If sensor_config_id provided, resolve to esp_id + gpio + sensor_type
        if sensor_config_id is not None:
            config = await self.session.execute(
                select(SensorConfig).where(SensorConfig.id == sensor_config_id)
            )
            config_obj = config.scalar_one_or_none()
            if config_obj:
                filters.append(SensorData.esp_id == config_obj.esp_id)
                if config_obj.gpio is not None:
                    filters.append(SensorData.gpio == config_obj.gpio)
                filters.append(func.lower(SensorData.sensor_type) == config_obj.sensor_type.lower())

        if esp_id is not None:
            filters.append(SensorData.esp_id == esp_id)
        if gpio is not None:
            filters.append(SensorData.gpio == gpio)
        if sensor_type:
            filters.append(func.lower(SensorData.sensor_type) == sensor_type.lower())
        if start_time:
            filters.append(SensorData.timestamp >= start_time)
        if end_time:
            filters.append(SensorData.timestamp <= end_time)
        if quality:
            filters.append(SensorData.quality == quality.lower())
        else:
            # AUT-723 E3: warming_up is quality-only, not a numeric chart Y.
            # Explicit ?quality=warming_up still returns those rows.
            filters.append(
                or_(SensorData.quality.is_(None), SensorData.quality != "warming_up")
            )
        if data_source:
            filters.append(SensorData.data_source == data_source.value)
        if zone_id is not None:
            filters.append(SensorData.zone_id == zone_id)
        if subzone_id is not None:
            filters.append(SensorData.subzone_id == subzone_id)
        if before_timestamp is not None:
            filters.append(SensorData.timestamp < before_timestamp)

        # Aggregated query path
        if resolution and resolution != "raw" and resolution in self._RESOLUTION_MAP:
            return await self._query_aggregated(filters, resolution, limit)

        # Raw query path
        stmt = select(SensorData)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(SensorData.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _query_aggregated(
        self,
        filters: list,
        resolution: str,
        limit: int,
    ) -> list:
        """
        Execute aggregated sensor data query using PostgreSQL date_trunc.

        Returns list of Row tuples with:
        (bucket, avg_raw, avg_processed, min_val, max_val, sample_count, sensor_type, unit)
        """
        from sqlalchemy import literal_column

        trunc_interval = self._RESOLUTION_MAP.get(resolution)

        if resolution == "5m":
            # 5-minute buckets: floor timestamp to nearest 5-min boundary
            # PostgreSQL: date_trunc('hour', ts) + INTERVAL '5 min' * floor(extract(minute from ts)/5)
            bucket = (
                func.date_trunc("hour", SensorData.timestamp)
                + literal_column("INTERVAL '5 min'")
                * func.floor(func.extract("minute", SensorData.timestamp) / 5)
            ).label("bucket")
        else:
            bucket = func.date_trunc(trunc_interval, SensorData.timestamp).label("bucket")

        stmt = (
            select(
                bucket,
                func.avg(SensorData.raw_value).label("avg_raw"),
                func.avg(SensorData.processed_value).label("avg_processed"),
                func.min(SensorData.processed_value).label("min_val"),
                func.max(SensorData.processed_value).label("max_val"),
                func.count().label("sample_count"),
                SensorData.sensor_type,
                func.max(SensorData.unit).label("unit"),
            )
            .group_by(bucket, SensorData.sensor_type)
            .order_by(bucket.desc())
        )

        if filters:
            stmt = stmt.where(and_(*filters))

        # No hard limit for aggregated queries (data is already reduced),
        # but apply a generous safety cap
        stmt = stmt.limit(min(limit, 10000))

        result = await self.session.execute(stmt)
        return list(result.all())

    async def get_data_range(
        self,
        esp_id: uuid.UUID,
        gpio: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[SensorData]:
        """
        Get sensor data within time range.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of SensorData instances
        """
        stmt = (
            select(SensorData)
            .where(
                SensorData.esp_id == esp_id,
                SensorData.gpio == gpio,
                SensorData.timestamp >= start_time,
                SensorData.timestamp <= end_time,
            )
            .order_by(SensorData.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # Calibration operations
    async def update_calibration(
        self,
        esp_id: uuid.UUID,
        gpio: int,
        calibration_data: dict,
        sensor_type: str | None = None,
    ) -> Optional[SensorConfig]:
        """
        Update calibration data for a sensor.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            calibration_data: Calibration parameters (sensor-specific)
            sensor_type: Required for Multi-Value sensors (e.g. sht31_temp, sht31_humidity).
                If omitted and multiple configs exist on (esp_id, gpio), raises ValueError.

        Returns:
            Updated SensorConfig or None if not found
        """
        if sensor_type is not None:
            sensor_config = await self.get_by_esp_gpio_and_type(esp_id, gpio, sensor_type)
        else:
            configs = await self.get_all_by_esp_and_gpio(esp_id, gpio)
            if not configs:
                sensor_config = None
            elif len(configs) == 1:
                sensor_config = configs[0]
            else:
                logger.warning(
                    "update_calibration called without sensor_type but (esp_id=%s, gpio=%s) "
                    "has %d configs. Multi-Value sensors require sensor_type.",
                    esp_id,
                    gpio,
                    len(configs),
                )
                raise ValueError(
                    f"Multiple sensor configs on (esp_id={esp_id}, gpio={gpio}). "
                    "Pass sensor_type for Multi-Value sensors (e.g. sht31_temp, sht31_humidity)."
                )

        if not sensor_config:
            return None

        sensor_config.calibration_data = canonicalize_calibration_data(
            calibration_data,
            source="sensor_repo_update",
        )
        await self.session.flush()
        await self.session.refresh(sensor_config)
        return sensor_config

    async def get_calibration(
        self,
        esp_id: uuid.UUID,
        gpio: int,
        sensor_type: str | None = None,
    ) -> Optional[dict]:
        """
        Get calibration data for a sensor.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            sensor_type: Sensor type for multi-value disambiguation (e.g. 'sht31_temp').
                         Required when multiple sensors share a GPIO.

        Returns:
            Calibration data dict or None if not found/not calibrated
        """
        if sensor_type:
            sensor_config = await self.get_by_esp_gpio_and_type(esp_id, gpio, sensor_type)
        else:
            configs = await self.get_all_by_esp_and_gpio(esp_id, gpio)
            if not configs:
                return None
            if len(configs) > 1:
                logger.warning(
                    "get_calibration called without sensor_type for multi-value GPIO: "
                    "esp=%s gpio=%s (%d configs). Returning first.",
                    esp_id,
                    gpio,
                    len(configs),
                )
            sensor_config = configs[0]
        if not sensor_config:
            return None
        return canonicalize_calibration_data(
            sensor_config.calibration_data,
            source="sensor_repo_read",
        )

    async def get_calibration_key_usage(self) -> dict[str, int]:
        """
        Analyze calibration_data keys defensively (NULL/json-null/object safe).

        Returns:
            Dict mapping calibration key -> number of sensor rows containing that key.
        """
        try:
            dialect_name = self.session.bind.dialect.name
        except (AttributeError, TypeError):
            dialect_name = ""

        if dialect_name == "postgresql":
            stmt = text(
                """
                SELECT k.key, COUNT(*) AS usage_count
                FROM sensor_configs sc
                CROSS JOIN LATERAL jsonb_object_keys(
                    CASE
                        WHEN sc.calibration_data IS NULL THEN NULL::jsonb
                        WHEN jsonb_typeof(sc.calibration_data::jsonb) = 'object' THEN sc.calibration_data::jsonb
                        ELSE NULL::jsonb
                    END
                ) AS k(key)
                GROUP BY k.key
                ORDER BY k.key
                """
            )
        else:
            # SQLite-compatible fallback for unit tests and local analysis.
            stmt = text(
                """
                SELECT je.key AS key, COUNT(*) AS usage_count
                FROM sensor_configs sc
                JOIN json_each(
                    CASE
                        WHEN sc.calibration_data IS NULL THEN NULL
                        WHEN json_type(sc.calibration_data) = 'object' THEN sc.calibration_data
                        ELSE NULL
                    END
                ) AS je
                GROUP BY je.key
                ORDER BY je.key
                """
            )

        result = await self.session.execute(stmt)
        return {str(row.key): int(row.usage_count) for row in result}

    async def get_stats(
        self,
        esp_id: uuid.UUID,
        gpio: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        sensor_type: Optional[str] = None,
    ) -> dict:
        """
        Get statistical summary for sensor data.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            sensor_type: Optional sensor type filter for multi-value sensors

        Returns:
            Dictionary with statistics:
            - min_value: Minimum processed value
            - max_value: Maximum processed value
            - avg_value: Average processed value
            - std_dev: Standard deviation
            - reading_count: Total number of readings
            - quality_distribution: Dict with quality level counts
        """
        filters = [SensorData.esp_id == esp_id, SensorData.gpio == gpio]

        if sensor_type:
            filters.append(func.lower(SensorData.sensor_type) == sensor_type.lower())

        if start_time:
            filters.append(SensorData.timestamp >= start_time)
        if end_time:
            filters.append(SensorData.timestamp <= end_time)

        # DB-side aggregation to avoid loading large datasets into memory where supported.
        # SQLite lacks stddev_pop, so we conditionally compute std_dev in Python for SQLite.
        try:
            dialect_name = self.session.bind.dialect.name
        except (AttributeError, TypeError):
            dialect_name = ""
        supports_stddev = dialect_name not in ("sqlite",)

        # Use COALESCE(processed_value, raw_value) to handle rows where processed_value is null
        value_col = func.coalesce(SensorData.processed_value, SensorData.raw_value)
        agg_columns = [
            func.count().label("reading_count"),
            func.min(value_col).label("min_value"),
            func.max(value_col).label("max_value"),
            func.avg(value_col).label("avg_value"),
        ]
        if supports_stddev:
            agg_columns.append(func.stddev_pop(value_col).label("std_dev"))

        # AUT-645: exclude implausible/errored readings from aggregation.
        # quality="critical" is set by sensor_handler.py when a value fails
        # SENSOR_PHYSICAL_LIMITS — these outliers must not skew MIN/MAX/AVG.
        # quality_stmt keeps all qualities for the diagnostic distribution.
        agg_filters = [*filters, SensorData.quality.notin_(["critical", "error"])]
        agg_stmt = select(*agg_columns).where(*agg_filters)

        quality_stmt = (
            select(SensorData.quality, func.count().label("count"))
            .where(*filters)
            .group_by(SensorData.quality)
        )

        agg_result = await self.session.execute(agg_stmt)
        agg_row = agg_result.one()

        # If no readings, return empty stats
        if agg_row.reading_count == 0:
            return {
                "min_value": None,
                "max_value": None,
                "avg_value": None,
                "std_dev": None,
                "reading_count": 0,
                "quality_distribution": {},
            }

        quality_distribution: dict[str, int] = {}
        q_result = await self.session.execute(quality_stmt)
        for quality, count in q_result.all():
            key = quality or "unknown"
            quality_distribution[key] = count

        # std_dev handling: if DB supports stddev_pop use it; otherwise compute in Python (SQLite)
        std_dev = None
        if supports_stddev:
            std_dev = agg_row.std_dev if agg_row.reading_count > 1 else 0.0
        else:
            # Fetch values (non-null) for Python-side stddev; small test datasets are acceptable.
            # Use agg_filters to mirror the same quality exclusion as the main agg_stmt.
            values_stmt = (
                select(func.coalesce(SensorData.processed_value, SensorData.raw_value))
                .where(*agg_filters)
                .where(
                    or_(SensorData.processed_value.isnot(None), SensorData.raw_value.isnot(None))
                )
            )
            values_result = await self.session.execute(values_stmt)
            values = [v for (v,) in values_result.all() if v is not None]
            if len(values) > 1:
                import statistics

                std_dev = statistics.pstdev(values)  # population stddev to mirror stddev_pop
            elif len(values) == 1:
                std_dev = 0.0

        return {
            "min_value": agg_row.min_value,
            "max_value": agg_row.max_value,
            "avg_value": agg_row.avg_value,
            "std_dev": std_dev,
            "reading_count": agg_row.reading_count,
            "quality_distribution": quality_distribution,
        }

    # Data source filtering operations
    async def get_by_source(
        self,
        source: DataSource,
        limit: int = 100,
        esp_id: Optional[uuid.UUID] = None,
    ) -> list[SensorData]:
        """
        Get sensor data filtered by data source.

        Args:
            source: Data source (production, mock, test, simulation)
            limit: Maximum number of records
            esp_id: Optional ESP device UUID filter

        Returns:
            List of SensorData instances
        """
        stmt = select(SensorData).where(
            SensorData.data_source == source.value,
            # AUT-723 E3: warming_up is quality-only — exclude before limit
            # so /data/by-source does not drop a full page of chartable rows.
            or_(SensorData.quality.is_(None), SensorData.quality != "warming_up"),
        )
        if esp_id:
            stmt = stmt.where(SensorData.esp_id == esp_id)
        stmt = stmt.order_by(SensorData.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_production_only(self, limit: int = 100) -> list[SensorData]:
        """
        Get only production sensor data (excludes mock/test/simulation).

        Args:
            limit: Maximum number of records

        Returns:
            List of production SensorData instances
        """
        return await self.get_by_source(DataSource.PRODUCTION, limit)

    async def cleanup_test_data(self, older_than_hours: int = 24) -> int:
        """
        Delete test sensor data older than specified hours.

        Only deletes data with data_source='test'. Does not affect
        mock, simulation, or production data.

        Args:
            older_than_hours: Delete data older than this many hours

        Returns:
            Number of deleted records
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        stmt = delete(SensorData).where(
            SensorData.data_source == DataSource.TEST.value,
            SensorData.timestamp < cutoff,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_by_source(self) -> dict[str, int]:
        """
        Count sensor data entries grouped by data source.

        Returns:
            Dictionary mapping data source to count
            Example: {"production": 1000, "mock": 50, "test": 25}
        """
        stmt = select(SensorData.data_source, func.count(SensorData.id)).group_by(
            SensorData.data_source
        )
        result = await self.session.execute(stmt)
        return {source: count for source, count in result.all()}

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
    # =========================================================================

    async def get_by_i2c_address(
        self, esp_id: uuid.UUID, i2c_address: int
    ) -> Optional[SensorConfig]:
        """
        Get first sensor by ESP ID and I2C address.

        Used for validating I2C address conflicts. Returns first match
        because multi-value sensors (e.g. SHT31 temp+humidity) share the
        same I2C address — scalar_one_or_none() would crash.

        Args:
            esp_id: ESP device UUID
            i2c_address: I2C address (0-127)

        Returns:
            First matching SensorConfig or None if not found
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.interface_type == "I2C",
            SensorConfig.i2c_address == i2c_address,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_by_i2c_address(
        self, esp_id: uuid.UUID, i2c_address: int
    ) -> list[SensorConfig]:
        """
        Get all sensors by ESP ID and I2C address.

        Returns all matches (not just first) so callers can filter
        sibling sub-types from real conflicts.

        Args:
            esp_id: ESP device UUID
            i2c_address: I2C address (0-127)

        Returns:
            List of matching SensorConfig entries (may be empty)
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.interface_type == "I2C",
            SensorConfig.i2c_address == i2c_address,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_onewire_address(
        self, esp_id: uuid.UUID, onewire_address: str
    ) -> Optional[SensorConfig]:
        """
        Get sensor by ESP ID and OneWire device address.

        Used for validating OneWire address conflicts.

        Args:
            esp_id: ESP device UUID
            onewire_address: OneWire device address (16 char hex string)

        Returns:
            SensorConfig or None if not found
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.interface_type == "ONEWIRE",
            SensorConfig.onewire_address == onewire_address,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_esp_gpio_type_and_onewire(
        self, esp_id: uuid.UUID, gpio: int, sensor_type: str, onewire_address: str
    ) -> Optional[SensorConfig]:
        """
        Get sensor by ESP ID, GPIO, sensor_type, AND OneWire address (4-way lookup).

        **Use-Case:** Multiple DS18B20 OneWire sensors on same GPIO pin.
        Each sensor has unique 64-bit ROM address (onewire_address).

        This is the most specific lookup for OneWire sensors, ensuring
        we match the exact device when multiple DS18B20s share a bus.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number (OneWire bus pin, e.g., 4)
            sensor_type: Sensor type (e.g., 'ds18b20')
            onewire_address: OneWire ROM code (16 hex chars, e.g., '28FF641E8D3C0C79')

        Returns:
            SensorConfig if found, None otherwise

        Example:
            # ESP has 3 DS18B20 sensors on GPIO 4
            # Lookup specific sensor by ROM code
            sensor = await repo.get_by_esp_gpio_type_and_onewire(
                esp_id=uuid,
                gpio=4,
                sensor_type='ds18b20',
                onewire_address='28FF641E8D3C0C79'
            )
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.gpio == gpio,
            func.lower(SensorConfig.sensor_type) == sensor_type.lower(),
            SensorConfig.onewire_address == onewire_address,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_esp_gpio_type_and_i2c(
        self, esp_id: uuid.UUID, gpio: int, sensor_type: str, i2c_address: int
    ) -> Optional[SensorConfig]:
        """
        Get sensor by ESP ID, GPIO, sensor_type, AND I2C address (4-way lookup).

        **Use-Case:** Multiple I2C sensors of same type at different addresses.
        For example: 2x SHT31 sensors at 0x44 and 0x45 on same I2C bus.

        This is the most specific lookup for I2C sensors, ensuring
        we match the exact device when multiple same-type sensors exist.

        Args:
            esp_id: ESP device UUID
            gpio: GPIO pin number (I2C bus SDA pin, e.g., 21)
            sensor_type: Sensor type (e.g., 'sht31_temp', 'sht31_humidity')
            i2c_address: I2C device address (7-bit, 0-127)

        Returns:
            SensorConfig if found, None otherwise

        Example:
            # ESP has 2x SHT31 sensors at 0x44 and 0x45
            # Lookup specific sensor by I2C address
            sensor = await repo.get_by_esp_gpio_type_and_i2c(
                esp_id=uuid,
                gpio=21,
                sensor_type='sht31_temp',
                i2c_address=0x44
            )
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id,
            SensorConfig.gpio == gpio,
            func.lower(SensorConfig.sensor_type) == sensor_type.lower(),
            SensorConfig.i2c_address == i2c_address,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_interface(
        self, esp_id: uuid.UUID, interface_type: str
    ) -> list[SensorConfig]:
        """
        Get all sensors of a specific interface type for an ESP.

        Useful for:
        - Listing all I2C sensors (to show I2C bus status)
        - Listing all OneWire sensors (to show OneWire bus status)

        Args:
            esp_id: ESP device UUID
            interface_type: Interface type (I2C, ONEWIRE, ANALOG, DIGITAL)

        Returns:
            List of SensorConfig instances
        """
        stmt = select(SensorConfig).where(
            SensorConfig.esp_id == esp_id, SensorConfig.interface_type == interface_type
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
