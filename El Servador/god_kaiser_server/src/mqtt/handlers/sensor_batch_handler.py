"""
MQTT Handler: Sensor Batch Replay (AUT-715)

Processes ``kaiser/{kaiser_id}/esp/{esp_id}/sensor/batch`` messages published
by El Trabajante's SpoolManager when an offline spool is flushed after reconnect.

Each message contains a ``readings`` list (or a single dict) of sensor readings
that were spooled during an MQTT disconnect and must now be persisted.

Flow:
  1. Parse topic → extract esp_id.
  2. Accept payload as list or {"readings": [...]} dict.
  3. For each reading: call existing sensor_repo.save_data() (no new insert_batch()).
  4. Increment Prometheus counters (BATCH_QUEUED / BATCH_REPLAYED / BATCH_SKIPPED).
  5. Emit structured log line per batch for Loki/Grafana correlation.

Pattern:
  Follows queue_pressure_handler / heartbeat_metrics_handler pattern.
  No BaseMQTTHandler (deprecated since AUT-225).
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ...core.error_codes import ValidationErrorCode
from ...core.logging_config import get_logger
from ...core.metrics import (
    BATCH_QUEUED_TOTAL,
    BATCH_REPLAYED_TOTAL,
    BATCH_SKIPPED_TOTAL,
)
from ...db.models.enums import DataSource
from ...db.repositories import ESPRepository, SensorRepository
from ...db.session import resilient_session
from ...sensors.sensor_type_registry import get_unit_for_sensor_type, sanitize_unit_encoding

logger = get_logger(__name__)

# Regex matching: kaiser/{kaiser_id}/esp/{esp_id}/sensor/batch
_BATCH_TOPIC_RE = re.compile(r"^kaiser/[^/]+/esp/(?P<esp_id>[^/]+)/sensor/batch$")


def _parse_batch_topic(topic: str) -> Optional[str]:
    """Extract esp_id from a sensor/batch topic. Returns None on mismatch."""
    m = _BATCH_TOPIC_RE.match(topic)
    if m:
        return m.group("esp_id")
    return None


def _normalize_readings(payload: Any) -> list[dict]:
    """
    Accept payload as:
      - list of reading dicts (direct SpoolManager format), OR
      - {"readings": [...]} dict (wrapped format)

    Returns an empty list on unexpected types.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        readings = payload.get("readings")
        if isinstance(readings, list):
            return readings
        # Single reading passed as flat dict — treat as single-element batch
        if all(k in payload for k in ("gpio", "sensor_type", "raw_value")):
            return [payload]
    return []


def _parse_timestamp(raw_ts: Any, boot_epoch_s: int | None = None) -> datetime:
    """
    Convert ESP32 millis-since-boot or ISO string to timezone-aware datetime.
    Falls back to server UTC now on failure (better than dropping the reading).
    """
    if raw_ts is None:
        return datetime.now(timezone.utc)
    if isinstance(raw_ts, (int, float)) and boot_epoch_s:
        # AUT-863 Option B: reconstruct wall-clock time from boot anchor + millis offset.
        return datetime.fromtimestamp(boot_epoch_s + raw_ts / 1000.0, tz=timezone.utc)
    if isinstance(raw_ts, (int, float)):
        # Millis since boot without boot anchor — use server time as fallback.
        return datetime.now(timezone.utc)
    if isinstance(raw_ts, str):
        try:
            dt = datetime.fromisoformat(raw_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class SensorBatchHandler:
    """
    Handles sensor/batch messages — offline spool replay (AUT-715).
    """

    async def handle_sensor_batch(self, topic: str, payload: dict) -> bool:
        """
        Handle MQTT sensor/batch — offline spool replay. AUT-715.

        Args:
            topic:   MQTT topic string (``kaiser/+/esp/{esp_id}/sensor/batch``)
            payload: Pre-parsed JSON payload (list or dict with 'readings' key)

        Returns:
            True if the batch was processed (even partially).
            False only on unrecoverable errors (topic parse failure, unexpected exception).
        """
        try:
            esp_id_str = _parse_batch_topic(topic)
            if not esp_id_str:
                logger.error(
                    "[%s] Failed to parse sensor/batch topic: %s",
                    ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    topic,
                )
                return False

            readings = _normalize_readings(payload)
            if not readings:
                logger.warning(
                    "sensor/batch: empty or malformed payload from esp_id=%s topic=%s",
                    esp_id_str,
                    topic,
                )
                return True  # Not a fatal error — empty spool flush is valid

            total = len(readings)
            BATCH_QUEUED_TOTAL.labels(esp_id=esp_id_str).inc(total)

            replayed = 0
            skipped = 0

            async with resilient_session() as session:
                esp_repo = ESPRepository(session)
                sensor_repo = SensorRepository(session)

                # Resolve ESP device UUID from string identifier
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if esp_device is None:
                    logger.warning(
                        "sensor/batch: unknown esp_id=%s, skipping %d readings",
                        esp_id_str,
                        total,
                    )
                    BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(total)
                    return True  # Unknown ESP — not a processing error

                esp_uuid: uuid.UUID = esp_device.id

                for reading in readings:
                    if not isinstance(reading, dict):
                        skipped += 1
                        BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(1)
                        continue

                    gpio = reading.get("gpio")
                    sensor_type = reading.get("sensor_type") or reading.get("t")
                    # Explicit None-check: raw_value=0 is valid (e.g. flow sensor with no flow).
                    # The `or` pattern would treat 0 as missing, silently dropping zero-readings.
                    raw_value_raw = reading.get("raw_value")
                    raw_value = raw_value_raw if raw_value_raw is not None else reading.get("r")
                    processed_value = reading.get("processed_value") or reading.get("pv")
                    unit = reading.get("unit") or reading.get("u")
                    quality = reading.get("quality") or reading.get("q")
                    raw_ts = reading.get("timestamp") or reading.get("ts")
                    boot_epoch_s_raw = reading.get("be")
                    boot_epoch_s: int | None = (
                        int(boot_epoch_s_raw) if boot_epoch_s_raw is not None else None
                    )
                    subzone_id = reading.get("subzone_id") or reading.get("sz")
                    onewire_address = reading.get("onewire_address") or reading.get("ow")
                    # raw_mode stored as int (0/1) by spool_manager — use explicit None-check
                    raw_mode_raw = reading.get("raw_mode")
                    raw_mode: bool = bool(raw_mode_raw) if raw_mode_raw is not None else True

                    # Minimal required fields
                    if gpio is None or not sensor_type or raw_value is None:
                        logger.debug(
                            "sensor/batch: skipping incomplete reading esp=%s: %s",
                            esp_id_str,
                            reading,
                        )
                        skipped += 1
                        BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(1)
                        continue

                    raw_value_f = float(raw_value)
                    sensor_type_str = str(sensor_type).lower()

                    # AUT-327: EC raw=0 on boot — same guard as sensor_handler.py
                    if sensor_type_str == "ec" and raw_mode and raw_value_f == 0.0:
                        logger.debug(
                            "sensor/batch: EC raw=0 dropped (boot artifact?): esp=%s gpio=%s",
                            esp_id_str,
                            gpio,
                        )
                        skipped += 1
                        BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(1)
                        continue

                    ts = _parse_timestamp(raw_ts, boot_epoch_s)

                    # Sensor config lookup — needed for pi_enhanced flag and calibration
                    sensor_config = None
                    if onewire_address:
                        sensor_config = await sensor_repo.get_by_esp_gpio_type_and_onewire(
                            esp_uuid, int(gpio), sensor_type_str, str(onewire_address)
                        )
                    else:
                        sensor_config = await sensor_repo.get_by_esp_gpio_and_type(
                            esp_uuid, int(gpio), sensor_type_str
                        )

                    # Unit: registry canonical > spool payload (avoids encoding issues)
                    registry_unit = get_unit_for_sensor_type(sensor_type_str)
                    unit_str: Optional[str] = registry_unit or (
                        sanitize_unit_encoding(str(unit)) if unit else None
                    )

                    # Route through sensor library — mirrors sensor_handler.py processing
                    processing_mode = "raw"
                    processed_value_f: Optional[float] = (
                        float(processed_value) if processed_value is not None else None
                    )

                    if sensor_config and sensor_config.pi_enhanced and raw_mode:
                        # Pi-Enhanced: call library via shared handler singleton.
                        # ATC (EC/pH temperature compensation) intentionally omitted for
                        # replays — historical timestamp makes cross-sensor ATC invalid.
                        from .sensor_handler import get_sensor_handler

                        pi_result = await get_sensor_handler()._trigger_pi_enhanced_processing(
                            esp_id_str,
                            int(gpio),
                            sensor_type_str,
                            raw_value_f,
                            sensor_config,
                            raw_mode=raw_mode,
                        )
                        if pi_result:
                            processed_value_f = pi_result["processed_value"]
                            unit_str = pi_result["unit"]
                            quality = pi_result.get("quality") or quality
                            processing_mode = "pi_enhanced"
                        else:
                            quality = str(quality) if quality else "error"

                    elif raw_mode and sensor_type_str == "ds18b20":
                        # Safety net: DS18B20 12-bit int16 → °C (same as sensor_handler.py)
                        processed_value_f = raw_value_f * 0.0625
                        processing_mode = "raw_conversion"

                    elif raw_mode and sensor_type_str in ("sht31_temp", "sht31"):
                        # Safety net: SHT31 raw register → °C (SHT31 datasheet formula)
                        processed_value_f = -45.0 + 175.0 * (raw_value_f / 65535.0)
                        processing_mode = "raw_conversion"

                    elif raw_mode and sensor_type_str == "sht31_humidity":
                        # Safety net: SHT31 raw register → %RH (SHT31 datasheet formula)
                        processed_value_f = 100.0 * (raw_value_f / 65535.0)
                        processing_mode = "raw_conversion"

                    elif not raw_mode:
                        # ESP pre-processed — use spool's processed_value as-is
                        processing_mode = "local"

                    if processed_value_f is None:
                        processed_value_f = raw_value_f

                    try:
                        result = await sensor_repo.save_data(
                            esp_id=esp_uuid,
                            gpio=int(gpio),
                            sensor_type=sensor_type_str,
                            raw_value=raw_value_f,
                            processed_value=processed_value_f,
                            unit=unit_str,
                            processing_mode=processing_mode,
                            quality=str(quality) if quality else None,
                            timestamp=ts,
                            # AUT-883: mark spool replays distinctly from live data
                            data_source=DataSource.BATCH.value,
                            zone_id=esp_device.zone_id,
                            subzone_id=str(subzone_id) if subzone_id else None,
                            device_name=esp_device.name,
                        )
                        if result is None:
                            # Duplicate — silently ignored by ON CONFLICT DO NOTHING
                            skipped += 1
                            BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(1)
                        else:
                            replayed += 1
                            BATCH_REPLAYED_TOTAL.labels(esp_id=esp_id_str).inc(1)
                    except Exception as exc:
                        logger.warning(
                            "sensor/batch: failed to save reading esp=%s gpio=%s: %s",
                            esp_id_str,
                            gpio,
                            exc,
                        )
                        skipped += 1
                        BATCH_SKIPPED_TOTAL.labels(esp_id=esp_id_str).inc(1)

                await session.commit()

            logger.info(
                "sensor/batch processed: esp_id=%s total=%d replayed=%d skipped=%d",
                esp_id_str,
                total,
                replayed,
                skipped,
                extra={
                    "event_class": "SENSOR_BATCH_REPLAY",
                    "esp_id": esp_id_str,
                    "total": total,
                    "replayed": replayed,
                    "skipped": skipped,
                },
            )
            return True

        except Exception as exc:
            logger.error(
                "Error handling sensor/batch: %s",
                exc,
                exc_info=True,
            )
            return False


# ============================================
# Module-level singleton (matches diagnostics/queue_pressure pattern)
# ============================================
_handler_instance: Optional[SensorBatchHandler] = None


def get_sensor_batch_handler() -> SensorBatchHandler:
    """Return the module-level SensorBatchHandler singleton."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = SensorBatchHandler()
    return _handler_instance


async def handle_sensor_batch(topic: str, payload: dict) -> bool:
    """
    Convenience function — registered directly with Subscriber.register_handler().

    Args:
        topic:   MQTT topic string
        payload: Pre-parsed JSON payload

    Returns:
        True if processed successfully
    """
    handler = get_sensor_batch_handler()
    return await handler.handle_sensor_batch(topic, payload)
