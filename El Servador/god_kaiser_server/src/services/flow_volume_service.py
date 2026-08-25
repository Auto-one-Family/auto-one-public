"""
Flow volume accumulation (AUT-1121 Variante A / AUT-1288).

Integrates stored flow sensor readings (L/min) over a time window to liters.
No new table — reads ``sensor_data`` via existing repository patterns
(``SensorRepository.get_data_range``), analogous to
``LogicRepository.get_execution_count_last_24h`` / ``get_dose_ml_last_24h``.

Variante B (``SUM(dose_ml)``) is NOT used for the Nachfüll-Kette: the refill
rule runs without ``duration_seconds`` / ``dose_ml`` (Level-Low→ON unbounded,
Level-High→OFF). Documented for AUT-1121 DoD / AUT-1288.

Important — LogicExecutionHistory.execution_time_ms:
  That field is rule-dispatch wall-clock latency, NOT pump runtime. For
  level-based refill, pass the ON→OFF event span into
  ``accumulate_flow_volume_l`` (see ``accumulate_refill_volume_l``).

AUT-1288 dock: ESP_57E1D4 GPIO 14. Erfassung only — NOT a stop criterion
(stop remains GPIO 26 / AUT-1308).

[MESSEN] Robin: FS300A Messbereich 1–60 L/min. If real Nachfüll flow is
below 1 L/min, readings may stay ~0 and accumulation yields 0 — do not guess.
ISR path unverified while pump OFF (pulse count=0 expected); confirm counting
during a controlled pump run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.logic import LogicExecutionHistory
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.sensor_repo import SensorRepository


logger = get_logger(__name__)

# AUT-1288 — Nachfüll-Mengenerfassung (Anzeige/Buchhaltung, nicht Regelung)
REFILL_FLOW_DEVICE_ID = "ESP_57E1D4"
REFILL_FLOW_GPIO = 14
REFILL_FLOW_SENSOR_TYPE = "flow"


@dataclass(frozen=True)
class FlowVolumeResult:
    """Result of a flow volume integration over a time window."""

    volume_l: float
    start: datetime
    end: datetime
    sample_count: int
    esp_id: UUID
    gpio: int


def integrate_flow_rate_to_volume_l(
    samples: Sequence[tuple[datetime, float]],
) -> float:
    """
    Trapezoidal integration of flow rate (L/min) → volume (liters).

    Args:
        samples: Sorted (timestamp, flow_l_per_min) pairs. Unsorted input is
            sorted by timestamp before integration.

    Returns:
        Cumulative volume in liters (0.0 if fewer than 2 samples).
    """
    if len(samples) < 2:
        return 0.0

    ordered = sorted(samples, key=lambda item: item[0])
    volume_l = 0.0
    for (t0, v0), (t1, v1) in zip(ordered, ordered[1:]):
        if t1 <= t0:
            continue
        dt_min = (t1 - t0).total_seconds() / 60.0
        if dt_min <= 0:
            continue
        # Trapezoid: average rate × duration in minutes → liters
        volume_l += ((max(0.0, v0) + max(0.0, v1)) / 2.0) * dt_min
    return volume_l


def execution_window(
    execution: LogicExecutionHistory,
) -> tuple[datetime, datetime]:
    """
    AUT-1121 Variante A window: ``[timestamp - execution_time_ms, timestamp]``.

    Note: ``execution_time_ms`` is dispatch latency. Prefer an explicit
    ON→OFF span for refill volume (AUT-1288).
    """
    end = execution.timestamp
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    duration_ms = max(0, int(execution.execution_time_ms or 0))
    start = end - timedelta(milliseconds=duration_ms)
    return start, end


class FlowVolumeService:
    """Accumulate flow volume from ``sensor_data`` over time windows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sensor_repo = SensorRepository(session)
        self.esp_repo = ESPRepository(session)

    async def accumulate_flow_volume_l(
        self,
        esp_id: UUID,
        gpio: int,
        start: datetime,
        end: datetime,
        *,
        sensor_type: str = REFILL_FLOW_SENSOR_TYPE,
    ) -> FlowVolumeResult:
        """
        Integrate flow readings in ``[start, end]`` to liters (Variante A core).

        Uses ``processed_value`` (L/min) from ``sensor_data``; falls back to
        ``raw_value`` only when processed is NULL (legacy rows).

        Rows with ``quality == "error"`` are skipped (ISR/stop spikes must not
        inflate Nachfüll liters — e.g. 134 L/min at pump OFF).
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end < start:
            start, end = end, start

        rows = await self.sensor_repo.get_data_range(esp_id, gpio, start, end)
        samples: list[tuple[datetime, float]] = []
        skipped_error = 0
        for row in rows:
            if sensor_type and row.sensor_type:
                if str(row.sensor_type).lower() != sensor_type.lower():
                    continue
            quality = getattr(row, "quality", None)
            if quality is not None and str(quality).lower() == "error":
                skipped_error += 1
                continue
            value = row.processed_value
            if value is None:
                value = row.raw_value
            if value is None:
                continue
            ts = row.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            samples.append((ts, float(value)))

        if skipped_error:
            logger.info(
                "AUT-1288 flow volume: skipped %s sample(s) with quality=error "
                "esp_id=%s gpio=%s window=%s..%s",
                skipped_error,
                esp_id,
                gpio,
                start.isoformat(),
                end.isoformat(),
            )

        volume_l = integrate_flow_rate_to_volume_l(samples)
        return FlowVolumeResult(
            volume_l=round(volume_l, 4),
            start=start,
            end=end,
            sample_count=len(samples),
            esp_id=esp_id,
            gpio=gpio,
        )

    async def accumulate_flow_volume_for_execution(
        self,
        esp_id: UUID,
        gpio: int,
        execution: LogicExecutionHistory,
        *,
        sensor_type: str = REFILL_FLOW_SENSOR_TYPE,
    ) -> FlowVolumeResult:
        """
        AUT-1121 Variante A: integrate over
        ``[timestamp - execution_time_ms, timestamp]``.

        For Nachfüll without dose/duration, use ``accumulate_refill_volume_l``
        with the pump ON→OFF span instead.
        """
        start, end = execution_window(execution)
        return await self.accumulate_flow_volume_l(
            esp_id, gpio, start, end, sensor_type=sensor_type
        )

    async def accumulate_refill_volume_l(
        self,
        start: datetime,
        end: datetime,
        *,
        device_id: str = REFILL_FLOW_DEVICE_ID,
        gpio: int = REFILL_FLOW_GPIO,
        esp_uuid: Optional[UUID] = None,
    ) -> FlowVolumeResult:
        """
        AUT-1288: Nachfüll-Volumen über GPIO 14 (Anzeige/Buchhaltung).

        Pass the refill event window (actuator ON timestamp → OFF timestamp).
        Does NOT act as stop criterion (that remains GPIO 26 / AUT-1308).

        [MESSEN]: If real Zulauf < 1 L/min (FS300A lower bound), expect ~0.
        """
        resolved_esp = esp_uuid
        if resolved_esp is None:
            device = await self.esp_repo.get_by_device_id(device_id)
            if device is None:
                raise ValueError(f"ESP device not found: {device_id}")
            resolved_esp = device.id

        result = await self.accumulate_flow_volume_l(
            resolved_esp, gpio, start, end, sensor_type=REFILL_FLOW_SENSOR_TYPE
        )
        if result.sample_count == 0:
            logger.info(
                "AUT-1288 refill volume: no flow samples in window "
                "device_id=%s gpio=%s start=%s end=%s — "
                "check pump run / ISR / [MESSEN] flow < 1 L/min",
                device_id,
                gpio,
                start.isoformat(),
                end.isoformat(),
            )
        return result
