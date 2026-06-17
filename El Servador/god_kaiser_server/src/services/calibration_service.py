"""
Calibration Service (S-P4)

Business logic for multi-point sensor calibration sessions.

Responsibilities:
- Session lifecycle management (start → collect points → finalize → apply/reject)
- Calibration computation (linear 2-point, moisture mapping)
- Integration with SensorRepository for applying results
- Validation of calibration points and transitions
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.calibration_session import CalibrationSession, CalibrationStatus
from ..db.repositories import ESPRepository, SensorRepository
from ..db.repositories.calibration_session_repo import CalibrationSessionRepository
from ..sensors.adc_normalization import (
    ADC_SOURCE_ADS1115,
    ADC_SOURCE_INTERNAL,
    raw_to_voltage,
    resolve_adc_descriptor,
)
from ..sensors.sensor_type_registry import normalize_sensor_type
from .calibration_payloads import (
    build_canonical_calibration_result,
    canonicalize_calibration_data,
)

logger = get_logger(__name__)
_SESSION_LOCKS: dict[uuid.UUID, asyncio.Lock] = {}
_SESSION_LOCKS_GUARD = asyncio.Lock()
_SENSOR_SESSION_LOCKS: dict[tuple[str, int, str], asyncio.Lock] = {}
_SENSOR_SESSION_LOCKS_GUARD = asyncio.Lock()
_ROLE_PENDING_OVERWRITES: dict[tuple[uuid.UUID, str], int] = {}
_ROLE_PENDING_GUARD = asyncio.Lock()
_OVERWRITE_ARBITRATION_WINDOW_SECONDS = 0.100

# ESP32 ADC constants — internal-ADC fallback for voltage-based calibration (pH, EC).
# The canonical RAW->voltage normalization now lives in sensors.adc_normalization
# (raw_to_voltage); these constants are retained only for documentation / parity.
# Must match ECSensorProcessor / PHSensorProcessor (12-bit internal path).
_ADC_MAX = 4095.0
_ADC_VOLTAGE = 3.3


class CalibrationError(Exception):
    """Base exception for calibration service errors."""

    def __init__(self, message: str, code: str = "CALIBRATION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class CalibrationService:
    """
    Orchestrates calibration session lifecycle.

    Usage:
        service = CalibrationService(db_session)
        session = await service.start_session(esp_id, gpio, sensor_type, user)
        session = await service.add_point(session.id, raw=2250, reference=50.0)
        session = await service.add_point(session.id, raw=1100, reference=100.0)
        result = await service.finalize(session.id)
        await service.apply(session.id)
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CalibrationSessionRepository(session)
        self.sensor_repo = SensorRepository(session)
        self.esp_repo = ESPRepository(session)
        self.session_ttl_hours = 24

    @staticmethod
    def _is_mutable_status(status: CalibrationStatus) -> bool:
        return status in (
            CalibrationStatus.PENDING,
            CalibrationStatus.COLLECTING,
        )

    @staticmethod
    def _ensure_finite(value: float, field_name: str) -> None:
        if not isfinite(float(value)):
            raise CalibrationError(f"{field_name} must be a finite number", "VALIDATION_ERROR")

    async def _ensure_session_mutable(self, cal_session: CalibrationSession) -> CalibrationSession:
        if cal_session.is_terminal:
            raise CalibrationError(
                f"Session is in terminal state: {cal_session.status.value}",
                "SESSION_TERMINAL",
            )

        session_ts = cal_session.updated_at or cal_session.created_at
        if session_ts.tzinfo is None:
            session_ts = session_ts.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - session_ts).total_seconds()
        if age_seconds > self.session_ttl_hours * 3600:
            updated = await self.repo.update_status(
                cal_session.id,
                CalibrationStatus.EXPIRED,
                failure_reason=f"Session expired after {self.session_ttl_hours}h inactivity",
            )
            if updated:
                await self._broadcast_event(
                    "calibration_session_expired",
                    {
                        "session_id": str(cal_session.id),
                        "esp_id": cal_session.esp_id,
                        "gpio": cal_session.gpio,
                        "sensor_type": cal_session.sensor_type,
                        "status": CalibrationStatus.EXPIRED.value,
                    },
                    correlation_id=cal_session.correlation_id,
                )
            raise CalibrationError("Session expired", "SESSION_EXPIRED")

        if not self._is_mutable_status(cal_session.status):
            raise CalibrationError(
                f"Session cannot be mutated from state: {cal_session.status.value}",
                "STATE_ERROR",
            )

        return cal_session

    @staticmethod
    @asynccontextmanager
    async def _session_lock(session_id: uuid.UUID):
        """
        Serialize concurrent mutations for one calibration session in-process.

        DB row locks remain the primary guard for multi-process deployments;
        this lock closes race windows in single-process async execution and tests.
        """
        async with _SESSION_LOCKS_GUARD:
            lock = _SESSION_LOCKS.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                _SESSION_LOCKS[session_id] = lock
        async with lock:
            yield

    @staticmethod
    @asynccontextmanager
    async def _sensor_lock(sensor_key: tuple[str, int, str]):
        """Serialize start-session race for one logical sensor key."""
        async with _SENSOR_SESSION_LOCKS_GUARD:
            lock = _SENSOR_SESSION_LOCKS.get(sensor_key)
            if lock is None:
                lock = asyncio.Lock()
                _SENSOR_SESSION_LOCKS[sensor_key] = lock
        async with lock:
            yield

    # ── S-P6: WebSocket broadcast helper ──────────────────────────────────

    @staticmethod
    async def _broadcast_event(
        event_type: str,
        data: dict,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Best-effort WebSocket broadcast for calibration lifecycle events."""
        try:
            from ..websocket.manager import WebSocketManager

            ws = await WebSocketManager.get_instance()
            await ws.broadcast(
                message_type=event_type,
                data=data,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.debug("CalibrationService WS broadcast failed: %s", e)

    async def _resolve_calibration_temperature(
        self,
        sensor_config,
        esp_device_id: Optional[uuid.UUID],
        session_metadata: dict,
    ) -> tuple[float, str]:
        """
        Resolve calibration temperature with strict priority:
          1) Explicit value from session_metadata (frontend/manual input)
          2) Linked temperature sensor via temp_sensor_config_id
          3) Same-ESP temperature auto-discovery
          4) Default 25.0°C
        """
        explicit_temp = session_metadata.get("calibration_temperature")
        if explicit_temp is not None:
            try:
                value = float(explicit_temp)
                if isfinite(value):
                    source = str(session_metadata.get("calibration_temperature_source") or "manual")
                    return value, source
            except (TypeError, ValueError):
                logger.warning("Invalid explicit calibration_temperature in session metadata: %s", explicit_temp)

        sensor_repo = SensorRepository(self.session)
        now_utc = datetime.now(timezone.utc)
        max_age = timedelta(minutes=5)

        if sensor_config is not None and sensor_config.temp_sensor_config_id is not None:
            linked = await sensor_repo.get_by_id(sensor_config.temp_sensor_config_id)
            if linked is not None:
                reading = await sensor_repo.get_latest_reading(
                    esp_id=linked.esp_id,
                    gpio=linked.gpio,
                    sensor_type=linked.sensor_type,
                )
                if reading is not None and reading.processed_value is not None:
                    ts = reading.timestamp if reading.timestamp.tzinfo else reading.timestamp.replace(tzinfo=timezone.utc)
                    if now_utc - ts <= max_age:
                        return float(reading.processed_value), f"config:{sensor_config.temp_sensor_config_id}"

        if esp_device_id is not None:
            for temp_type in ("temperature", "sht31_temp"):
                reading = await sensor_repo.get_latest_reading_for_esp(
                    esp_id=esp_device_id,
                    sensor_type=temp_type,
                )
                if reading is None or reading.processed_value is None:
                    continue
                ts = reading.timestamp if reading.timestamp.tzinfo else reading.timestamp.replace(tzinfo=timezone.utc)
                if now_utc - ts <= max_age:
                    return float(reading.processed_value), f"same_esp:{temp_type}"

        return 25.0, "default_25c"

    async def start_session(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        method: str = "linear_2point",
        expected_points: int = 2,
        initiated_by: Optional[str] = None,
        correlation_id: Optional[str] = None,
        session_metadata: Optional[dict] = None,
    ) -> CalibrationSession:
        """
        Start a new calibration session.

        Checks for existing active sessions and aborts them.
        Normalizes sensor_type before persisting.

        Raises:
            CalibrationError: If sensor validation fails
        """
        # Normalize sensor type (S-P1)
        normalized_type = normalize_sensor_type(sensor_type)

        async with self._sensor_lock((esp_id, gpio, normalized_type)):
            # Check for existing active session — expire it
            existing = await self.repo.get_active_session(esp_id, gpio, normalized_type)
            if existing:
                logger.info(
                    "Expiring existing active calibration session %s for %s/GPIO%d",
                    existing.id,
                    esp_id,
                    gpio,
                )
                await self.repo.update_status(
                    existing.id,
                    CalibrationStatus.EXPIRED,
                    failure_reason="Superseded by new calibration session",
                )

            # Find sensor config (optional — may not exist yet for unconfigured sensors)
            sensor_config_id = None
            sensor = None
            esp_device = await self.esp_repo.get_by_device_id(esp_id)
            if esp_device:
                sensor = await self.sensor_repo.get_by_esp_gpio_and_type(
                    esp_device.id,
                    gpio,
                    normalized_type,
                )
                if sensor:
                    sensor_config_id = sensor.id

            # Resolve calibration temperature metadata (AUT-299):
            # explicit frontend input > linked DS18B20/temp sensor > same-ESP fallback > 25.0°C.
            metadata = dict(session_metadata or {})
            resolved_temp, resolved_source = await self._resolve_calibration_temperature(
                sensor_config=sensor,
                esp_device_id=esp_device.id if esp_device else None,
                session_metadata=metadata,
            )
            metadata["calibration_temperature"] = resolved_temp
            metadata["calibration_temperature_source"] = resolved_source
            if sensor and sensor.temp_sensor_config_id:
                metadata["linked_temp_sensor_config_id"] = str(sensor.temp_sensor_config_id)

            # Create session
            cal_session = await self.repo.create(
                esp_id=esp_id,
                gpio=gpio,
                sensor_type=normalized_type,
                sensor_config_id=sensor_config_id,
                method=method,
                expected_points=expected_points,
                initiated_by=initiated_by,
                correlation_id=correlation_id,
                session_metadata=metadata,
            )

        logger.info(
            "Started calibration session %s: %s/GPIO%d type=%s method=%s",
            cal_session.id,
            esp_id,
            gpio,
            normalized_type,
            method,
        )

        # S-P6: Broadcast session started event
        await self._broadcast_event(
            "calibration_session_started",
            {
                "session_id": str(cal_session.id),
                "esp_id": esp_id,
                "gpio": gpio,
                "sensor_type": normalized_type,
                "method": method,
                "expected_points": expected_points,
                "status": cal_session.status.value,
            },
            correlation_id=correlation_id,
        )

        return cal_session

    async def add_point(
        self,
        session_id: uuid.UUID,
        raw: float,
        reference: float,
        point_role: str,
        overwrite: bool = False,
        quality: str = "good",
        intent_id: Optional[str] = None,
        measured_at: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> CalibrationSession:
        """
        Add a calibration measurement point to the session.

        point_role values:
        - Moisture calibration: "dry", "wet"
        - pH calibration: "buffer_high", "buffer_low"
        - EC calibration: "reference", "air"

        Raises:
            CalibrationError: If session is terminal or already has enough points
        """
        normalized_role = point_role.strip().lower()
        valid_roles = {
            "dry",
            "wet",
            "buffer_high",
            "buffer_low",
            "reference",
            "air",
            "reference_low",
            "reference_high",
        }
        if normalized_role not in valid_roles:
            raise CalibrationError(
                f"point_role must be one of: {', '.join(sorted(valid_roles))}", "VALIDATION_ERROR"
            )

        role_key = (session_id, normalized_role)
        if overwrite:
            await self._register_pending_overwrite(role_key)

        try:
            async with self._session_lock(session_id):
                # Release-Gate contract:
                # In mixed same-role races (overwrite=true vs overwrite=false), overwrite wins.
                # This keeps the operator-visible API deterministic (200x1 + 409x1), avoiding
                # ambiguous dual-success outcomes that cannot be used as a hard gate.
                if not overwrite:
                    await asyncio.sleep(_OVERWRITE_ARBITRATION_WINDOW_SECONDS)
                    if await self._has_pending_overwrite(role_key):
                        raise CalibrationError(
                            f"Point role '{normalized_role}' already exists (overwrite request has priority)",
                            "ROLE_POINT_EXISTS",
                        )

                cal_session = await self.repo.get_by_id_for_update(session_id)
                if not cal_session:
                    raise CalibrationError("Session not found", "SESSION_NOT_FOUND")
                await self._ensure_session_mutable(cal_session)
                self._ensure_finite(raw, "raw_value")
                self._ensure_finite(reference, "reference_value")

                payload = cal_session.calibration_points or {"points": [], "history": []}
                existing_points = payload.get("points", [])
                points = list(existing_points) if isinstance(existing_points, list) else []
                history = (
                    list(payload.get("history", []))
                    if isinstance(payload.get("history", []), list)
                    else []
                )

                existing_idx = next(
                    (
                        idx
                        for idx, item in enumerate(points)
                        if item.get("point_role") == normalized_role
                    ),
                    None,
                )
                point_id = str(uuid.uuid4())
                point = {
                    "id": point_id,
                    "point_role": normalized_role,
                    "raw": float(raw),
                    "reference": float(reference),
                    "quality": quality,
                    "timestamp": measured_at or datetime.now(timezone.utc).isoformat(),
                    "intent_id": intent_id,
                    "correlation_id": correlation_id,
                }

                audit_action = "created"
                if existing_idx is not None:
                    if not overwrite:
                        raise CalibrationError(
                            f"Point role '{normalized_role}' already exists, set overwrite=true",
                            "ROLE_POINT_EXISTS",
                        )
                    previous = points[existing_idx]
                    history.append(
                        {
                            "action": "overwritten",
                            "point_role": normalized_role,
                            "previous_point": previous,
                            "changed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    # keep stable point id for deterministic update semantics
                    point["id"] = previous.get("id", point_id)
                    points[existing_idx] = point
                    audit_action = "overwritten"
                else:
                    if len(points) >= cal_session.expected_points:
                        raise CalibrationError(
                            f"Session already has {len(points)}/{cal_session.expected_points} points",
                            "POINTS_COMPLETE",
                        )
                    points.append(point)

                updated = await self.repo.replace_calibration_points(
                    session_id,
                    {"points": points, "history": history},
                    force_collecting=True,
                    clear_result=True,
                )
                if not updated:
                    raise CalibrationError(
                        "Failed to persist calibration point", "ADD_POINT_FAILED"
                    )

                logger.info(
                    "Calibration point %s (%s) in session %s: role=%s raw=%.3f ref=%.3f",
                    audit_action,
                    point.get("id"),
                    session_id,
                    normalized_role,
                    float(raw),
                    float(reference),
                )
                return updated
        finally:
            if overwrite:
                await self._unregister_pending_overwrite(role_key)

    @staticmethod
    async def _register_pending_overwrite(role_key: tuple[uuid.UUID, str]) -> None:
        async with _ROLE_PENDING_GUARD:
            _ROLE_PENDING_OVERWRITES[role_key] = _ROLE_PENDING_OVERWRITES.get(role_key, 0) + 1

    @staticmethod
    async def _unregister_pending_overwrite(role_key: tuple[uuid.UUID, str]) -> None:
        async with _ROLE_PENDING_GUARD:
            current = _ROLE_PENDING_OVERWRITES.get(role_key, 0)
            if current <= 1:
                _ROLE_PENDING_OVERWRITES.pop(role_key, None)
            else:
                _ROLE_PENDING_OVERWRITES[role_key] = current - 1

    @staticmethod
    async def _has_pending_overwrite(role_key: tuple[uuid.UUID, str]) -> bool:
        async with _ROLE_PENDING_GUARD:
            return _ROLE_PENDING_OVERWRITES.get(role_key, 0) > 0

    async def update_point(
        self,
        session_id: uuid.UUID,
        point_id: str,
        *,
        raw: float,
        reference: float,
        point_role: str,
        quality: str = "good",
        intent_id: Optional[str] = None,
        measured_at: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> CalibrationSession:
        """Update a single calibration point by point_id."""
        async with self._session_lock(session_id):
            cal_session = await self.repo.get_by_id_for_update(session_id)
            if not cal_session:
                raise CalibrationError("Session not found", "SESSION_NOT_FOUND")
            await self._ensure_session_mutable(cal_session)
            self._ensure_finite(raw, "raw_value")
            self._ensure_finite(reference, "reference_value")

            normalized_role = point_role.strip().lower()
            if normalized_role not in {
                "dry",
                "wet",
                "buffer_high",
                "buffer_low",
                "reference",
                "air",
                "reference_low",
                "reference_high",
            }:
                raise CalibrationError(
                    "point_role must be one of: "
                    "dry, wet, buffer_high, buffer_low, reference, air, reference_low, reference_high",
                    "VALIDATION_ERROR",
                )

            payload = cal_session.calibration_points or {"points": [], "history": []}
            points = (
                list(payload.get("points", []))
                if isinstance(payload.get("points", []), list)
                else []
            )
            history = (
                list(payload.get("history", []))
                if isinstance(payload.get("history", []), list)
                else []
            )

            idx = next((i for i, p in enumerate(points) if p.get("id") == point_id), None)
            if idx is None:
                raise CalibrationError(f"Point {point_id} not found", "POINT_NOT_FOUND")

            role_conflict = next(
                (
                    p
                    for p in points
                    if p.get("id") != point_id and p.get("point_role") == normalized_role
                ),
                None,
            )
            if role_conflict:
                raise CalibrationError(
                    f"Point role '{normalized_role}' already exists, set overwrite=true",
                    "ROLE_POINT_EXISTS",
                )

            previous = points[idx]
            updated_point = {
                "id": point_id,
                "point_role": normalized_role,
                "raw": float(raw),
                "reference": float(reference),
                "quality": quality,
                "timestamp": measured_at or datetime.now(timezone.utc).isoformat(),
                "intent_id": intent_id,
                "correlation_id": correlation_id,
            }
            points[idx] = updated_point
            history.append(
                {
                    "action": "updated",
                    "point_role": normalized_role,
                    "previous_point": previous,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            session = await self.repo.replace_calibration_points(
                session_id,
                {"points": points, "history": history},
                force_collecting=True,
                clear_result=True,
            )
            if not session:
                raise CalibrationError("Failed to update calibration point", "POINT_UPDATE_FAILED")
            return session

    async def delete_point(self, session_id: uuid.UUID, point_id: str) -> CalibrationSession:
        """Delete a point from a mutable calibration session."""
        async with self._session_lock(session_id):
            cal_session = await self.repo.get_by_id_for_update(session_id)
            if not cal_session:
                raise CalibrationError("Session not found", "SESSION_NOT_FOUND")
            await self._ensure_session_mutable(cal_session)

            payload = cal_session.calibration_points or {"points": [], "history": []}
            points = (
                list(payload.get("points", []))
                if isinstance(payload.get("points", []), list)
                else []
            )
            history = (
                list(payload.get("history", []))
                if isinstance(payload.get("history", []), list)
                else []
            )

            idx = next((i for i, p in enumerate(points) if p.get("id") == point_id), None)
            if idx is None:
                raise CalibrationError(f"Point {point_id} not found", "POINT_NOT_FOUND")

            removed = points.pop(idx)
            history.append(
                {
                    "action": "deleted",
                    "point_role": removed.get("point_role"),
                    "previous_point": removed,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            session = await self.repo.replace_calibration_points(
                session_id,
                {"points": points, "history": history},
                force_collecting=True,
                clear_result=True,
            )
            if not session:
                raise CalibrationError("Failed to delete calibration point", "POINT_DELETE_FAILED")
            return session

    async def finalize(self, session_id: uuid.UUID) -> CalibrationSession:
        """
        Compute calibration result from collected points.

        Transitions session to FINALIZING with computed slope/offset.

        Raises:
            CalibrationError: If not enough points or computation fails
        """
        cal_session = await self.repo.get_by_id_for_update(session_id)
        if not cal_session:
            raise CalibrationError("Session not found", "SESSION_NOT_FOUND")

        if cal_session.status == CalibrationStatus.FINALIZING and cal_session.calibration_result:
            return cal_session

        if cal_session.status != CalibrationStatus.COLLECTING:
            raise CalibrationError(
                f"Cannot finalize from state: {cal_session.status.value}",
                "INVALID_STATE",
            )

        if not cal_session.is_ready_to_finalize:
            raise CalibrationError(
                f"Need {cal_session.expected_points} points, have {cal_session.points_collected}",
                "INSUFFICIENT_POINTS",
            )

        # Extract points
        points_data = cal_session.calibration_points or {"points": []}
        points = points_data.get("points", [])

        # Validate points based on method
        roles = {
            str(point.get("point_role", "")).lower() for point in points if isinstance(point, dict)
        }

        if cal_session.method == "moisture_2point":
            if "dry" not in roles or "wet" not in roles:
                raise CalibrationError(
                    "Finalize requires both 'dry' and 'wet' points for moisture_2point",
                    "INSUFFICIENT_POINTS",
                )
        elif cal_session.method == "ph_2point":
            if "buffer_high" not in roles or "buffer_low" not in roles:
                raise CalibrationError(
                    "Finalize requires both 'buffer_high' and 'buffer_low' points for ph_2point",
                    "INSUFFICIENT_POINTS",
                )
        elif cal_session.method == "ec_1point":
            if "reference" not in roles:
                raise CalibrationError(
                    "Finalize requires 'reference' point for ec_1point",
                    "INSUFFICIENT_POINTS",
                )
        elif cal_session.method == "ec_2point":
            if "air" not in roles or "reference" not in roles:
                raise CalibrationError(
                    "Finalize requires both 'air' and 'reference' points for ec_2point",
                    "INSUFFICIENT_POINTS",
                )
        elif cal_session.method == "ec_linear_2point":
            if "reference_low" not in roles or "reference_high" not in roles:
                raise CalibrationError(
                    "Finalize requires both 'reference_low' and 'reference_high' points for ec_linear_2point",
                    "INSUFFICIENT_POINTS",
                )
        elif cal_session.method in ("linear_2point", "linear"):
            if "dry" not in roles or "wet" not in roles:
                raise CalibrationError(
                    "Finalize requires both 'dry' and 'wet' points",
                    "INSUFFICIENT_POINTS",
                )

        # AUT-299: Read calibration_temperature from session_metadata (default 25.0°C NIST).
        cal_temp = float(
            (cal_session.session_metadata or {}).get("calibration_temperature", 25.0)
        )

        # Determine the acquisition source of the sensor being calibrated so that
        # the RAW->voltage normalization at calibration time is identical to the
        # one used at measurement time (no PGA/source drift).
        adc_source = ADC_SOURCE_INTERNAL
        pga_gain = None
        try:
            sensor_cfg = await self.sensor_repo.get_by_id(cal_session.sensor_config_id)
            if sensor_cfg is not None and getattr(sensor_cfg, "adc_source", None):
                adc_source, pga_gain = resolve_adc_descriptor(
                    {
                        "adc_source": sensor_cfg.adc_source,
                        "pga_gain": getattr(sensor_cfg, "pga_gain", None),
                    }
                )
        except Exception:  # noqa: BLE001 — permissive: fall back to internal ADC
            adc_source, pga_gain = ADC_SOURCE_INTERNAL, None

        # Compute calibration based on method
        try:
            result = self._compute_calibration(
                cal_session.method,
                cal_session.sensor_type,
                points,
                temperature=cal_temp,
                adc_source=adc_source,
                pga_gain=pga_gain,
            )
        except Exception as e:
            await self.repo.update_status(
                session_id,
                CalibrationStatus.FAILED,
                failure_reason=f"Computation error: {e}",
            )
            raise CalibrationError(f"Calibration computation failed: {e}", "COMPUTE_FAILED")

        canonical_result = build_canonical_calibration_result(
            method=cal_session.method,
            points=points,
            derived=result,
            source="calibration_session_finalize",
        )

        updated = await self.repo.set_result(session_id, canonical_result)
        if not updated:
            raise CalibrationError("Failed to set result", "SET_RESULT_FAILED")

        logger.info(
            "Finalized calibration session %s: %s",
            session_id,
            result,
        )

        # S-P6: Broadcast session finalized event
        await self._broadcast_event(
            "calibration_session_finalized",
            {
                "session_id": str(session_id),
                "esp_id": cal_session.esp_id,
                "gpio": cal_session.gpio,
                "sensor_type": cal_session.sensor_type,
                "status": updated.status.value if updated else "unknown",
                "result": canonical_result,
            },
            correlation_id=cal_session.correlation_id,
        )

        return updated

    async def apply(self, session_id: uuid.UUID) -> CalibrationSession:
        """
        Apply the calibration result to the sensor configuration.

        Persists calibration_data to the sensor's config in the DB.

        Raises:
            CalibrationError: If session not in FINALIZING state or sensor not found
        """
        cal_session = await self.repo.get_by_id_for_update(session_id)
        if not cal_session:
            raise CalibrationError("Session not found", "SESSION_NOT_FOUND")

        if cal_session.status == CalibrationStatus.APPLIED:
            return cal_session

        if cal_session.status != CalibrationStatus.FINALIZING:
            raise CalibrationError(
                f"Cannot apply: session is {cal_session.status.value}, expected FINALIZING",
                "INVALID_STATE",
            )

        if not cal_session.calibration_result:
            raise CalibrationError("No calibration result to apply", "NO_RESULT")

        if not cal_session.sensor_config_id:
            await self.repo.update_status(
                session_id,
                CalibrationStatus.FAILED,
                failure_reason="Apply blocked: no sensor_config_id bound to session",
            )
            raise CalibrationError(
                "Cannot apply without bound sensor configuration",
                "APPLY_PERSISTENCE_REQUIRED",
            )

        sensor = await self.sensor_repo.get_by_id(cal_session.sensor_config_id)
        if not sensor:
            await self.repo.update_status(
                session_id,
                CalibrationStatus.FAILED,
                failure_reason="Apply failed: sensor configuration not found",
            )
            raise CalibrationError(
                "Target sensor configuration not found for apply",
                "APPLY_PERSISTENCE_REQUIRED",
            )

        canonical_payload = canonicalize_calibration_data(
            cal_session.calibration_result,
            default_method=cal_session.method,
            source="calibration_session_apply",
        )
        if canonical_payload is None:
            await self.repo.update_status(
                session_id,
                CalibrationStatus.FAILED,
                failure_reason="Apply failed: invalid calibration_result payload",
            )
            raise CalibrationError(
                "Invalid calibration result payload for apply",
                "APPLY_PERSISTENCE_REQUIRED",
            )

        try:
            sensor.calibration_data = canonical_payload
            await self.session.flush()
            await self.session.refresh(sensor)
        except Exception as exc:
            await self.repo.update_status(
                session_id,
                CalibrationStatus.FAILED,
                failure_reason=f"Apply persistence failed: {exc}",
            )
            raise CalibrationError(
                "Calibration persistence write failed",
                "APPLY_PERSISTENCE_REQUIRED",
            ) from exc

        logger.info(
            "Applied calibration to sensor %s (session %s)",
            sensor.id,
            session_id,
        )

        updated = await self.repo.update_status(session_id, CalibrationStatus.APPLIED)
        if not updated:
            raise CalibrationError("Failed to update status", "STATUS_UPDATE_FAILED")

        # S-P6: Broadcast calibration applied event
        await self._broadcast_event(
            "calibration_session_applied",
            {
                "session_id": str(session_id),
                "esp_id": cal_session.esp_id,
                "gpio": cal_session.gpio,
                "sensor_type": cal_session.sensor_type,
                "status": "APPLIED",
                "calibration_result": canonical_payload,
            },
            correlation_id=cal_session.correlation_id,
        )

        return updated

    async def delete_session(
        self, session_id: uuid.UUID, reason: str = "User discarded session"
    ) -> CalibrationSession:
        """Delete/discard a mutable session by transitioning to REJECTED."""
        return await self.reject(session_id, reason=reason)

    async def reject(
        self, session_id: uuid.UUID, reason: str = "User rejected"
    ) -> CalibrationSession:
        """Reject a calibration session (user abort)."""
        cal_session = await self.repo.get_by_id(session_id)
        if not cal_session:
            raise CalibrationError("Session not found", "SESSION_NOT_FOUND")

        if cal_session.is_terminal:
            raise CalibrationError(
                f"Session already terminal: {cal_session.status.value}",
                "SESSION_TERMINAL",
            )

        updated = await self.repo.update_status(
            session_id,
            CalibrationStatus.REJECTED,
            failure_reason=reason,
        )
        if not updated:
            raise CalibrationError("Failed to reject", "REJECT_FAILED")

        logger.info("Rejected calibration session %s: %s", session_id, reason)

        # S-P6: Broadcast calibration rejected event
        await self._broadcast_event(
            "calibration_session_rejected",
            {
                "session_id": str(session_id),
                "esp_id": cal_session.esp_id,
                "gpio": cal_session.gpio,
                "sensor_type": cal_session.sensor_type,
                "status": "REJECTED",
                "reason": reason,
            },
            correlation_id=cal_session.correlation_id,
        )

        return updated

    async def get_session(self, session_id: uuid.UUID) -> Optional[CalibrationSession]:
        """Get a calibration session by ID."""
        return await self.repo.get_by_id(session_id)

    async def get_session_history(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[CalibrationSession]:
        """Get calibration history for a sensor."""
        if sensor_type:
            sensor_type = normalize_sensor_type(sensor_type)
        return await self.repo.get_sessions_for_sensor(esp_id, gpio, sensor_type, limit)

    # ── Private computation methods ────────────────────────────────────────

    @staticmethod
    def _compute_calibration(
        method: str,
        sensor_type: str,
        points: list[dict],
        temperature: float = 25.0,
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        Compute calibration parameters from measurement points.

        Args:
            method: Calibration method string.
            sensor_type: Normalized sensor type.
            points: List of calibration point dicts.
            temperature: Solution temperature at calibration time (°C).
                AUT-299: Used for EC temperature-compensated coefficient calculation.
                Default 25.0°C = NIST reference (no compensation applied).
            adc_source: Acquisition source ('internal' default or 'ads1115') of the
                sensor being calibrated. Selects the RAW->voltage normalization so
                calibration matches measurement.
            pga_gain: ADS1115 PGA gain (only for adc_source='ads1115').

        Returns a dict ready to be stored as calibration_data.
        """
        if method == "moisture_2point":
            return CalibrationService._compute_moisture(points)
        elif method in ("linear_2point", "linear"):
            # Legacy sessions: Feuchte mit linear_2point → gleiche derived-Form wie moisture_2point (dry/wet).
            if normalize_sensor_type(sensor_type or "") == "moisture":
                return CalibrationService._compute_moisture_from_role_points(points)
            return CalibrationService._compute_linear_2point(sensor_type, points)
        elif method == "offset":
            return CalibrationService._compute_offset(sensor_type, points)
        elif method == "ph_2point":
            return CalibrationService._compute_ph_2point(
                points, adc_source=adc_source, pga_gain=pga_gain
            )
        elif method == "ec_1point":
            return CalibrationService._compute_ec_1point(
                points, temperature=temperature, adc_source=adc_source, pga_gain=pga_gain
            )
        elif method == "ec_2point":
            return CalibrationService._compute_ec_2point(
                points, temperature=temperature, adc_source=adc_source, pga_gain=pga_gain
            )
        elif method == "ec_linear_2point":
            return CalibrationService._compute_ec_linear_2point(
                points, temperature=temperature, adc_source=adc_source, pga_gain=pga_gain
            )
        else:
            raise ValueError(f"Unknown calibration method: {method}")

    @staticmethod
    def _compute_linear_2point(sensor_type: str, points: list[dict]) -> dict:
        """2-point linear interpolation: y = slope * x + offset."""
        if len(points) < 2:
            raise ValueError("Need at least 2 points for linear calibration")

        p1 = points[0]
        p2 = points[1]

        raw1, ref1 = float(p1["raw"]), float(p1["reference"])
        raw2, ref2 = float(p2["raw"]), float(p2["reference"])

        if abs(raw2 - raw1) < 1e-6:
            raise ValueError("Raw values too close — cannot compute slope")

        slope = (ref2 - ref1) / (raw2 - raw1)
        offset = ref1 - slope * raw1

        return {
            "type": "linear_2point",
            "slope": round(slope, 6),
            "offset": round(offset, 4),
            "point1_raw": raw1,
            "point1_ref": ref1,
            "point2_raw": raw2,
            "point2_ref": ref2,
            "sensor_type": sensor_type,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _compute_moisture(points: list[dict]) -> dict:
        """Moisture 2-point: dry/wet ADC boundary mapping."""
        return CalibrationService._compute_moisture_from_role_points(points)

    @staticmethod
    def _compute_moisture_from_role_points(points: list[dict]) -> dict:
        """Derive dry/wet ADC from session points (prefer point_role dry/wet)."""
        if len(points) < 2:
            raise ValueError("Need at least 2 points for moisture calibration")

        dry_raw: float | None = None
        wet_raw: float | None = None
        for point in points:
            if not isinstance(point, dict):
                continue
            role = str(point.get("point_role", "")).lower()
            if role == "dry":
                dry_raw = float(point["raw"])
            elif role == "wet":
                wet_raw = float(point["raw"])

        if dry_raw is None or wet_raw is None:
            p1 = points[0]
            p2 = points[1]
            dry_raw = float(p1["raw"])
            wet_raw = float(p2["raw"])

        return {
            "type": "moisture_2point",
            "dry_value": dry_raw,
            "wet_value": wet_raw,
            # MoistureSensorProcessor._adc_to_moisture_calibrated already maps
            # dry_value → 0% and wet_value → 100% for both dry>wet and dry<wet.
            # Persisting invert=True when dry>wet would apply a second flip and
            # show dry soil as ~100% (BUG: calibration invert stacked on linear map).
            "invert": False,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _compute_offset(sensor_type: str, points: list[dict]) -> dict:
        """Single-point offset calibration."""
        if len(points) < 1:
            raise ValueError("Need at least 1 point for offset calibration")

        p1 = points[0]
        raw = float(p1["raw"])
        ref = float(p1["reference"])

        return {
            "type": "offset",
            "offset": round(ref - raw, 4),
            "point1_raw": raw,
            "point1_ref": ref,
            "sensor_type": sensor_type,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _adc_descriptor_fields(adc_source: str, pga_gain: Optional[str]) -> dict:
        """Return the adc_source/pga_gain fields to embed in a calibration result.

        Storing the descriptor in the calibration result guarantees that
        measurement-time normalization (process()) uses the same RAW->voltage
        mapping that was used to compute slope/offset.
        """
        fields: dict = {"adc_source": adc_source}
        if adc_source == ADC_SOURCE_ADS1115 and pga_gain is not None:
            fields["pga_gain"] = pga_gain
        return fields

    @staticmethod
    def _compute_ph_2point(
        points: list[dict],
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        pH 2-point calibration using Nernst equation.

        Formula: pH = slope * voltage_V + offset
        slope is in pH/V, matching PHSensorProcessor which converts ADC→V before applying calibration.

        Raises:
            ValueError: If slope is not negative or deviates too much from ideal
        """
        if len(points) < 2:
            raise ValueError("Need at least 2 points for pH 2-point calibration")

        # Find buffer_high and buffer_low points
        high_point = None
        low_point = None

        for p in points:
            role = str(p.get("point_role", "")).lower()
            if role == "buffer_high":
                high_point = p
            elif role == "buffer_low":
                low_point = p

        if not high_point or not low_point:
            raise ValueError("pH 2-point requires 'buffer_high' and 'buffer_low' points")

        raw_high = float(high_point["raw"])
        ref_high = float(high_point["reference"])
        raw_low = float(low_point["raw"])
        ref_low = float(low_point["reference"])

        if abs(raw_high - raw_low) < 1e-6:
            raise ValueError("Raw values too close — cannot compute slope")

        # Convert raw ADC to voltage via the shared normalization — matches
        # PHSensorProcessor (internal 12-bit or ADS1115 PGA-exact).
        voltage_high = raw_to_voltage(raw_high, adc_source=adc_source, pga_gain=pga_gain)
        voltage_low = raw_to_voltage(raw_low, adc_source=adc_source, pga_gain=pga_gain)

        # Linear regression in voltage space: pH = slope * voltage_V + offset
        slope = (ref_high - ref_low) / (voltage_high - voltage_low)
        offset = ref_high - slope * voltage_high

        # Validation: slope must be negative (higher voltage = lower pH for standard sensors)
        if slope >= 0:
            raise ValueError(f"pH slope must be negative (got {slope}). Check electrode polarity.")

        # Ideal Nernst response at 25°C: 59.16 mV/pH.
        # Our slope is pH/V → response_mV_per_pH = 1000 / abs(slope_pH_per_V)
        ideal_response_mv_per_ph = 59.16
        measured_response_mv_per_ph = (1000.0 / abs(slope)) if slope != 0 else 0

        slope_deviation_pct = (
            abs(measured_response_mv_per_ph - ideal_response_mv_per_ph)
            / ideal_response_mv_per_ph
            * 100
        )

        # Hard stop only for physically impossible deviation (> 500%).
        # IoT sensors with signal conditioning can deviate significantly from the
        # theoretical Nernst slope (59.16 mV/pH at 25°C unamplified). Amplifier
        # gains of 2–4x are common, so the effective raw-unit/pH ratio varies.
        # Values within 500% indicate a functional sensor; above that the data
        # is likely corrupt (swapped raw/reference fields or sensor disconnected).
        _HARD_LIMIT_PCT = 500.0
        if slope_deviation_pct > _HARD_LIMIT_PCT:
            raise ValueError(
                f"pH response {measured_response_mv_per_ph:.2f} mV/pH deviates {slope_deviation_pct:.1f}% from ideal {ideal_response_mv_per_ph:.2f} "
                f"(limit ±{_HARD_LIMIT_PCT:.0f}%). Check that raw and reference values are not swapped."
            )

        validation_warnings: list[str] = []
        if slope_deviation_pct > 15.0:
            validation_warnings.append(
                f"pH response {measured_response_mv_per_ph:.2f} mV/pH deviates {slope_deviation_pct:.1f}% from Nernst ideal "
                f"{ideal_response_mv_per_ph:.2f} mV/pH. This is expected for sensors with signal conditioning or amplification."
            )

        return {
            "type": "ph_2point",
            "slope": round(slope, 4),
            "offset": round(offset, 4),
            "slope_deviation_pct": round(slope_deviation_pct, 2),
            "point_high_raw": raw_high,
            "point_high_ref": ref_high,
            "point_low_raw": raw_low,
            "point_low_ref": ref_low,
            "measured_response_mv_per_ph": round(measured_response_mv_per_ph, 2),
            "ideal_response_mv_per_ph": ideal_response_mv_per_ph,
            "validation_warnings": validation_warnings,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            **CalibrationService._adc_descriptor_fields(adc_source, pga_gain),
        }

    @staticmethod
    def _compute_ec_1point(
        points: list[dict],
        temperature: float = 25.0,
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        EC 1-point calibration.

        raw is the raw ADC count (0–4095, 12-bit ESP32 ADC) — matching what the
        firmware sends in the MQTT sensor response ("raw" field).

        Derives voltage-based slope/offset: EC = slope * voltage + offset (offset = 0)
        and also stores cell_factor for backward-compatibility inspection.

        AUT-299: If calibrated at a temperature other than 25°C the reference EC value is
        normalized to 25°C using the DFR0300 temperature coefficient (2%/°C) before
        computing slope. This ensures the stored calibration is temperature-independent
        and ATC in ECSensorProcessor applies uniformly.

        cell_factor = reference_EC / raw_ADC_count.
        Typical DFR0300: raw ~625 at 1413 µS/cm → cell_factor ≈ 2.26.
        Valid range: [0.01, 100.0] — hard stop only for physically impossible values
        (sensor reads <1% of expected ADC at reference EC).
        Values outside [0.5, 10.0] generate a warning but do not block calibration.

        Args:
            points: List of calibration point dicts (requires one with point_role="reference").
            temperature: Solution temperature at calibration time in °C (default 25.0).

        Raises:
            ValueError: If raw is zero, cell_factor is non-positive, or exceeds hard limit
        """
        if len(points) < 1:
            raise ValueError("Need at least 1 point for EC 1-point calibration")

        # Find reference point
        ref_point = None
        for p in points:
            role = str(p.get("point_role", "")).lower()
            if role == "reference":
                ref_point = p
                break

        if not ref_point:
            raise ValueError("EC 1-point requires 'reference' point")

        raw = float(ref_point["raw"])
        reference = float(ref_point["reference"])

        if abs(raw) < 1e-6:
            raise ValueError("Raw ADC value too close to zero — sensor may be disconnected")

        if reference <= 0:
            raise ValueError("Reference EC value must be positive")

        # AUT-299: Compute actual EC of the solution at calibration temperature.
        # slope × voltage must yield EC@T_cal so that ATC (÷ (1+coeff*(T-25))) gives EC@25°C.
        # Matches ECSensorProcessor.TEMP_COEFFICIENT = 0.02 (2%/°C).
        _TEMP_COEFFICIENT = 0.02
        actual_at_cal_temp = reference * (1.0 + _TEMP_COEFFICIENT * (temperature - 25.0))

        # cell_factor = actual_EC@T_cal / raw_ADC — only used for validation and backward compat.
        # Hard limit: cell_factor > 100 means ADC < 1% of expected response → sensor issue.
        cell_factor = actual_at_cal_temp / raw
        _HARD_LIMIT = 100.0
        if cell_factor <= 0:
            raise ValueError(
                f"EC cell_factor {cell_factor:.3f} is not positive. "
                f"Ensure raw and reference values are not swapped."
            )
        if cell_factor >= _HARD_LIMIT:
            raise ValueError(
                f"EC cell_factor {cell_factor:.3f} exceeds hard limit {_HARD_LIMIT:.0f}. "
                f"Raw ADC {raw:.0f} is far too low for reference {reference:.1f} µS/cm. "
                f"Check probe connection and ensure sensor is submerged in reference solution."
            )

        # Soft warning: outside typical DFR0300-class range [0.5, 10.0].
        validation_warnings: list[str] = []
        _TYPICAL_MIN = 0.5
        _TYPICAL_MAX = 10.0
        if not (_TYPICAL_MIN <= cell_factor <= _TYPICAL_MAX):
            validation_warnings.append(
                f"EC cell_factor {cell_factor:.3f} is outside typical range "
                f"[{_TYPICAL_MIN}, {_TYPICAL_MAX}]. "
                f"Typical DFR0300 reads ADC ~625 at 1413 µS/cm (cell_factor ≈ 2.26). "
                f"Check probe connection and reference solution quality. "
                f"Calibration accepted with reduced confidence."
            )

        # Derive voltage-based slope/offset for ECSensorProcessor compatibility.
        # ECSensorProcessor.process() converts raw ADC → voltage, then applies:
        #   EC = slope * voltage + offset
        # 1-point: passes through origin (offset = 0).
        voltage = raw_to_voltage(raw, adc_source=adc_source, pga_gain=pga_gain)
        slope = actual_at_cal_temp / voltage  # EC@T_cal (µS/cm) per volt; ATC normalizes to EC@25°C
        offset = 0.0

        return {
            "type": "ec_1point",
            "slope": round(slope, 4),
            "offset": offset,
            "cell_factor": round(cell_factor, 6),
            "point_raw": raw,
            "point_reference": reference,
            "calibration_temperature": round(temperature, 1),
            "actual_at_cal_temp": round(actual_at_cal_temp, 2),
            "validation_warnings": validation_warnings,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            **CalibrationService._adc_descriptor_fields(adc_source, pga_gain),
        }

    @staticmethod
    def _compute_ec_2point(
        points: list[dict],
        temperature: float = 25.0,
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        EC 2-point calibration (air + reference).

        Converts raw ADC to voltage first, then computes:
        EC = slope * voltage + offset
        Air point (0 µS/cm reference) pins the offset; reference solution pins the slope.

        AUT-299: The reference-solution EC value is normalized to 25°C before computing
        slope so that the stored calibration is temperature-independent and ECSensorProcessor
        ATC applies uniformly regardless of calibration temperature.

        Args:
            points: List of calibration point dicts (requires "air" and "reference" roles).
            temperature: Solution temperature at calibration time in °C (default 25.0).

        Raises:
            ValueError: If points are invalid or voltages too close
        """
        if len(points) < 2:
            raise ValueError("Need at least 2 points for EC 2-point calibration")

        # Find air and reference points
        air_point = None
        ref_point = None

        for p in points:
            role = str(p.get("point_role", "")).lower()
            if role == "air":
                air_point = p
            elif role == "reference":
                ref_point = p

        if not air_point or not ref_point:
            raise ValueError("EC 2-point requires 'air' and 'reference' points")

        raw_air = float(air_point["raw"])
        ref_air = float(air_point["reference"])  # Should be 0
        raw_ref = float(ref_point["raw"])
        ref_ref = float(ref_point["reference"])

        # AUT-299: Compute actual EC of reference solution at calibration temperature.
        # Air point is 0 µS/cm regardless of temperature — no normalization needed for that point.
        _TEMP_COEFFICIENT = 0.02
        ref_ref_actual_at_T = ref_ref * (1.0 + _TEMP_COEFFICIENT * (temperature - 25.0))

        # Convert raw ADC to voltage before computing slope.
        # ECSensorProcessor.process() applies voltage-based formula: EC = slope * voltage + offset
        # Using raw ADC values would produce slope in EC/ADC-count (~1241x wrong).
        voltage_air = raw_to_voltage(raw_air, adc_source=adc_source, pga_gain=pga_gain)
        voltage_ref = raw_to_voltage(raw_ref, adc_source=adc_source, pga_gain=pga_gain)

        if abs(voltage_ref - voltage_air) < 1e-6:
            raise ValueError("Voltage values too close — cannot compute slope")

        slope = (ref_ref_actual_at_T - ref_air) / (voltage_ref - voltage_air)
        offset = ref_air - slope * voltage_air

        return {
            "type": "ec_2point",
            "slope": round(slope, 4),
            "offset": round(offset, 4),
            "point_air_raw": raw_air,
            "point_air_ref": ref_air,
            "point_reference_raw": raw_ref,
            "point_reference_ref": ref_ref,
            "calibration_temperature": round(temperature, 1),
            "actual_at_cal_temp": round(ref_ref_actual_at_T, 2),
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            **CalibrationService._adc_descriptor_fields(adc_source, pga_gain),
        }

    @staticmethod
    def _compute_ec_linear_2point(
        points: list[dict],
        temperature: float = 25.0,
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        EC linear 2-point calibration using standard KCl reference solutions.

        Uses two known reference solutions:
        - reference_low:  1413 µS/cm (0.01 M KCl at 25°C)
        - reference_high: 12880 µS/cm (0.1 M KCl at 25°C)

        EC is a linear sensor (voltage increases with EC), unlike pH (inverted).
        Mapping: ADC_low→ref_low, ADC_high→ref_high.

        Converts raw ADC to voltage first, then computes:
          EC = slope * voltage + offset

        This matches ECSensorProcessor.process() which applies the same formula
        in _voltage_to_ec_calibrated(). The stored calibration is temperature-
        independent: AUT-299 temperature normalization aligns the reference EC
        to 25°C so that ECSensorProcessor ATC (÷ (1 + coeff * (T - 25))) applies
        uniformly regardless of calibration temperature.

        Args:
            points: List of calibration point dicts with point_role "reference_low"
                    and "reference_high".
            temperature: Solution temperature at calibration time in °C (default 25.0).

        Raises:
            ValueError: If required points are missing, voltages are too close,
                        reference_high <= reference_low, or ADC_high <= ADC_low
                        (monotonicity violation).
        """
        if len(points) < 2:
            raise ValueError("Need at least 2 points for EC linear 2-point calibration")

        # Find reference_low and reference_high points
        low_point = None
        high_point = None

        for p in points:
            role = str(p.get("point_role", "")).lower()
            if role == "reference_low":
                low_point = p
            elif role == "reference_high":
                high_point = p

        if not low_point or not high_point:
            raise ValueError(
                "ec_linear_2point requires 'reference_low' and 'reference_high' points"
            )

        raw_low = float(low_point["raw"])
        ref_low = float(low_point["reference"])
        raw_high = float(high_point["raw"])
        ref_high = float(high_point["reference"])

        # Sanity check: reference_high must be greater than reference_low
        if ref_high <= ref_low:
            raise ValueError(
                f"reference_high ({ref_high} µS/cm) must be greater than "
                f"reference_low ({ref_low} µS/cm). Check that reference solutions are not swapped."
            )

        # Monotonicity check: higher EC solution must produce higher ADC reading
        # (EC sensor: voltage increases with conductivity)
        if raw_high <= raw_low:
            raise ValueError(
                f"ADC for reference_high ({raw_high:.0f}) must be greater than "
                f"ADC for reference_low ({raw_low:.0f}). "
                f"EC sensor output should increase with conductivity. "
                f"Check probe connection or swap the reference points."
            )

        # AUT-299: Normalize reference EC values to 25°C so the stored calibration
        # is temperature-independent (same convention as ec_1point / ec_2point).
        _TEMP_COEFFICIENT = 0.02
        temp_factor = 1.0 + _TEMP_COEFFICIENT * (temperature - 25.0)
        ref_low_at_T = ref_low * temp_factor
        ref_high_at_T = ref_high * temp_factor

        # Convert raw ADC to voltage via the shared normalization (internal 12-bit
        # or ADS1115 PGA-exact) — matches ECSensorProcessor.
        voltage_low = raw_to_voltage(raw_low, adc_source=adc_source, pga_gain=pga_gain)
        voltage_high = raw_to_voltage(raw_high, adc_source=adc_source, pga_gain=pga_gain)

        if abs(voltage_high - voltage_low) < 1e-6:
            raise ValueError("Voltage values too close — cannot compute slope")

        # Linear regression in voltage space: EC = slope * voltage + offset
        slope = (ref_high_at_T - ref_low_at_T) / (voltage_high - voltage_low)
        offset = ref_low_at_T - slope * voltage_low

        return {
            "type": "ec_linear_2point",
            "slope": round(slope, 4),
            "offset": round(offset, 4),
            "point_low_raw": raw_low,
            "point_low_ref": ref_low,
            "point_high_raw": raw_high,
            "point_high_ref": ref_high,
            "calibration_temperature": round(temperature, 1),
            "ref_low_at_cal_temp": round(ref_low_at_T, 2),
            "ref_high_at_cal_temp": round(ref_high_at_T, 2),
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            **CalibrationService._adc_descriptor_fields(adc_source, pga_gain),
        }
