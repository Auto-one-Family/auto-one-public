"""
MQTT Handler: Sensor Response for Calibration Sessions (S-P5)

Processes sensor command responses during active calibration sessions:
- Parses sensor/{gpio}/response topic
- Validates response payload (raw, quality, intent_id)
- If an active calibration session exists for the sensor, emits a measurement event
- Point persistence is done only via calibration session points API

Expected response payload from ESP32 (E-P4 enhanced):
{
    "success": true,
    "gpio": 4,
    "sensor_type": "moisture",
    "raw": 2150,
    "value": 52.3,
    "unit": "%",
    "quality": "good",
    "intent_id": "abc-123",
    "correlation_id": "def-456",
    "ttl_ms": 5000,
    "timestamp": 1712345678,
    "stable": true,
    "adc_stddev": 12.5
}

Resilience: Uses resilient_session() with circuit breaker protection.

If the device omits ``raw``/``raw_value``, we do **not** substitute the latest DB row:
that row may belong to periodic (continuous) sampling, not the manual measure command
(H2 / calibration wizard). The operator gets ``calibration_measurement_failed`` instead.

AUT-488: Extended ``calibration_measurement_received`` with live EC preview fields:
- ``preview_ec_us_cm``: Server-computed EC estimate (µS/cm) at 25°C reference
- ``preview_available``: Whether a meaningful preview could be computed
- ``stable``: Measurement stability flag (from ESP or derived from adc_stddev)
- ``adc_stddev``: Raw ADC standard deviation (from ESP, for expert view)
- ``temperature_used``: Temperature applied for ATC (°C)
- ``temperature_default``: True when 25°C default was used (no session temperature)
"""

from typing import Optional

from ...core.logging_config import get_logger
from ...db.repositories.calibration_session_repo import CalibrationSessionRepository
from ...db.repositories.sensor_repo import SensorRepository
from ...db.session import resilient_session
from ...sensors.adc_normalization import (
    ADC_SOURCE_INTERNAL,
    raw_to_voltage,
    resolve_adc_descriptor,
)
from ...sensors.sensor_type_registry import normalize_sensor_type
from ..topics import TopicBuilder

logger = get_logger(__name__)

# ESP32 ADC constants — internal-ADC fallback. The canonical RAW->voltage
# normalization lives in sensors.adc_normalization (raw_to_voltage); these are
# retained for documentation / parity with the 12-bit internal path.
_ADC_MAX = 4095.0
_ADC_VOLTAGE = 3.3

# Temperature coefficient for EC ATC — matches ECSensorProcessor.TEMP_COEFFICIENT (AUT-299).
_EC_TEMP_COEFFICIENT = 0.02

# Default EC slope when no calibration exists (linear mapping: 3.3V → 20000 µS/cm).
# Matches ECSensorProcessor._voltage_to_ec_default(): slope = 20000 / 3.3 ≈ 6060.
_EC_DEFAULT_SLOPE = 6060.0
_EC_DEFAULT_OFFSET = 0.0

# Stability threshold: adc_stddev above this value → mark as unstable.
# Aligned with ECSensorProcessor.EC_STABILITY_STD_DEV_US_CM = 15.0 in ADC-space.
# For 12-bit ESP32 ADC at typical EC range (ADC ~600–2500), 30 ADC counts ≈ 20 µS/cm
# variation — operator-visible yellow badge, not a hard gate (AUT-457 HW constraint).
_STABLE_ADC_STDDEV_THRESHOLD = 30.0


class CalibrationResponseHandler:
    """
    Handles sensor command responses in the context of calibration sessions.

    Flow:
    1. Parse topic → extract esp_id, gpio
    2. Validate payload (success, raw value present)
    3. Check for active calibration session
    4. If active session exists: broadcast measurement for explicit API commit
    """

    async def handle_sensor_response(self, topic: str, payload: dict) -> bool:
        """
        Handle sensor command response for calibration.

        Args:
            topic: MQTT topic (kaiser/+/esp/{esp_id}/sensor/{gpio}/response)
            payload: Parsed JSON payload from ESP32

        Returns:
            True if processed (regardless of whether calibration was involved)
        """
        # Step 1: Parse topic
        parsed = TopicBuilder.parse_sensor_response_topic(topic)
        if not parsed:
            logger.debug("CalibrationResponseHandler: Could not parse topic: %s", topic)
            return False

        esp_id = parsed["esp_id"]
        gpio = parsed["gpio"]

        # Step 2: Validate payload
        if not isinstance(payload, dict):
            logger.warning("CalibrationResponseHandler: Invalid payload type for %s", topic)
            return False

        success = payload.get("success", False)
        if not success:
            logger.info(
                "CalibrationResponseHandler: Sensor response failed for %s/GPIO%d: %s",
                esp_id,
                gpio,
                payload.get("error", "unknown"),
            )
            # Broadcast failure event for frontend awareness
            await self._broadcast_calibration_event(
                "calibration_measurement_failed",
                esp_id=esp_id,
                gpio=gpio,
                error=payload.get("error", "Measurement failed on device"),
                correlation_id=payload.get("correlation_id"),
                request_id=payload.get("request_id"),
            )
            return True

        quality = payload.get("quality", "good")
        intent_id = payload.get("intent_id")
        correlation_id = payload.get("correlation_id")
        sensor_type = payload.get("sensor_type", "unknown")

        # AUT-488 B7/B8: Extract stability and stddev from ESP payload (pass-through).
        adc_stddev_raw = payload.get("adc_stddev")
        adc_stddev: Optional[float] = float(adc_stddev_raw) if adc_stddev_raw is not None else None
        # AUT-488 B9: stable flag — prefer ESP-provided value, derive from adc_stddev fallback.
        stable_raw = payload.get("stable")
        if stable_raw is not None:
            stable: bool = bool(stable_raw)
        elif adc_stddev is not None:
            stable = adc_stddev <= _STABLE_ADC_STDDEV_THRESHOLD
        else:
            stable = True  # No stability data → assume stable (conservative default)

        # Step 3: Check for active calibration session
        active_session = None
        ambiguous_fallback = False
        normalized_type = normalize_sensor_type(sensor_type) if sensor_type else "unknown"
        request_id = payload.get("request_id")
        try:
            async with resilient_session() as session:
                cal_repo = CalibrationSessionRepository(session)
                if normalized_type != "unknown":
                    active_session = await cal_repo.get_active_session(
                        esp_id,
                        gpio,
                        normalized_type,
                    )
                if not active_session:
                    recent_sessions = await cal_repo.get_sessions_for_sensor(
                        esp_id=esp_id,
                        gpio=gpio,
                        sensor_type=None,
                        limit=5,
                    )
                    non_terminal_sessions = [c for c in recent_sessions if not c.is_terminal]
                    # AUT-1014 (B6): the fallback is only safe to accept when exactly one
                    # session is in flight AND its type matches the response — otherwise two
                    # co-located sensors (e.g. pH+EC on the same gpio=0) could be confused.
                    if len(non_terminal_sessions) == 1 and (
                        normalized_type == "unknown"
                        or non_terminal_sessions[0].sensor_type == normalized_type
                    ):
                        active_session = non_terminal_sessions[0]
                        normalized_type = active_session.sensor_type
                    elif non_terminal_sessions:
                        ambiguous_fallback = True

                raw_value = payload.get("raw", payload.get("raw_value"))
                if raw_value is None:
                    logger.warning(
                        "CalibrationResponseHandler: No raw/raw_value in MQTT payload for %s/GPIO%d "
                        "(no DB fallback — latest row may be from interval sampling, not this measure)",
                        esp_id,
                        gpio,
                    )
                    await self._broadcast_calibration_event(
                        "calibration_measurement_failed",
                        esp_id=esp_id,
                        gpio=gpio,
                        error=(
                            "Sensorantwort ohne Rohwert — bitte erneut messen oder Firmware prüfen "
                            "(Rohwert muss in der MQTT-Antwort enthalten sein)."
                        ),
                        correlation_id=correlation_id,
                        request_id=request_id if isinstance(request_id, str) else None,
                    )
                    return True

                if not active_session:
                    if ambiguous_fallback:
                        # AUT-1014 (B6): multiple concurrent sessions or a type mismatch at
                        # this gpio — do not silently guess the sensor, report a misassignment.
                        logger.warning(
                            "CalibrationResponseHandler: Ambiguous session fallback for "
                            "%s/GPIO%d/%s (multiple active sessions or type mismatch) — "
                            "reporting misassignment instead of a silent success.",
                            esp_id,
                            gpio,
                            normalized_type,
                        )
                        await self._broadcast_calibration_event(
                            "calibration_measurement_failed",
                            esp_id=esp_id,
                            gpio=gpio,
                            error=(
                                "Mehrdeutige Sensor-Zuordnung — mehrere aktive Kalibrier-Sessions "
                                "oder Typ-Mismatch am selben GPIO. Messung wird nicht zugeordnet."
                            ),
                            correlation_id=correlation_id,
                            request_id=request_id if isinstance(request_id, str) else None,
                        )
                        return True
                    # No active calibration — this is a normal sensor response
                    logger.debug(
                        "CalibrationResponseHandler: No active session for %s/GPIO%d/%s",
                        esp_id,
                        gpio,
                        normalized_type,
                    )
                    # AUT-488 A3: Compute EC preview even without an active session
                    # (no calibration points available → raw-ADC-based default estimate).
                    preview_fields = self._compute_ec_preview(
                        sensor_type=normalized_type,
                        raw_value=float(raw_value),
                        session=None,
                    )
                    # NOTE: without a session we cannot resolve the sensor's
                    # adc_source reliably (gpio=0 is shared for ADS1115); the
                    # default internal normalization is used for this low-
                    # confidence (preview_available=False) estimate.
                    # Still broadcast the raw measurement for frontend live display
                    await self._broadcast_calibration_event(
                        "calibration_measurement_received",
                        esp_id=esp_id,
                        gpio=gpio,
                        sensor_type=normalized_type,
                        raw=float(raw_value),
                        quality=quality,
                        intent_id=intent_id,
                        correlation_id=correlation_id,
                        request_id=request_id if isinstance(request_id, str) else None,
                        stable=stable,
                        adc_stddev=adc_stddev,
                        **preview_fields,
                    )
                    return True

                # Step 4: Only broadcast raw measurement.
                # Point persistence is explicitly handled by
                # POST /v1/calibration/sessions/{id}/points with reference assignment.
                logger.info(
                    "CalibrationResponseHandler: Measurement received for active session %s "
                    "(raw=%.1f, quality=%s)",
                    active_session.id,
                    float(raw_value),
                    quality,
                )
                # Resolve the sensor's acquisition source so the preview uses the
                # same RAW->voltage normalization as measurement/calibration.
                adc_source = ADC_SOURCE_INTERNAL
                pga_gain = None
                try:
                    sensor_cfg_id = getattr(active_session, "sensor_config_id", None)
                    if sensor_cfg_id is not None:
                        sensor_cfg = await SensorRepository(session).get_by_id(sensor_cfg_id)
                        if sensor_cfg is not None and getattr(sensor_cfg, "adc_source", None):
                            adc_source, pga_gain = resolve_adc_descriptor(
                                {
                                    "adc_source": sensor_cfg.adc_source,
                                    "pga_gain": getattr(sensor_cfg, "pga_gain", None),
                                }
                            )
                except Exception:  # noqa: BLE001 — preview is best-effort
                    adc_source, pga_gain = ADC_SOURCE_INTERNAL, None

                # AUT-488 A3: Compute EC live preview using session state and calibration points.
                preview_fields = self._compute_ec_preview(
                    sensor_type=normalized_type,
                    raw_value=float(raw_value),
                    session=active_session,
                    adc_source=adc_source,
                    pga_gain=pga_gain,
                )
                await self._broadcast_calibration_event(
                    "calibration_measurement_received",
                    esp_id=esp_id,
                    gpio=gpio,
                    sensor_type=normalized_type,
                    session_id=str(active_session.id),
                    raw=float(raw_value),
                    raw_value=float(raw_value),
                    measured_at=payload.get("timestamp"),
                    quality=quality,
                    intent_id=intent_id,
                    correlation_id=correlation_id,
                    request_id=request_id if isinstance(request_id, str) else None,
                    stable=stable,
                    adc_stddev=adc_stddev,
                    **preview_fields,
                )

        except Exception as e:
            logger.error(
                "CalibrationResponseHandler: Error processing %s/GPIO%d: %s",
                esp_id,
                gpio,
                e,
                exc_info=True,
            )
            return False

        return True

    @staticmethod
    def _compute_ec_preview(
        sensor_type: str,
        raw_value: float,
        session: object,  # CalibrationSession ORM instance or None
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> dict:
        """
        Compute a live EC preview value from the current raw ADC reading.

        AUT-488 A3 — Server-centric EC estimate for calibration wizard live display.

        Preview strategy (in order of precision):
        1. ec_linear_2point with BOTH reference_low + reference_high captured:
           Full linear calibration → accurate preview (same as final calibration).
        2. ec_linear_2point with ONE point captured (reference_low OR reference_high):
           Single-point extrapolation using the captured point and default slope direction.
        3. ec_2point with 'air' + 'reference' or ec_1point with 'reference' captured:
           Use captured slope from existing points.
        4. No captured points / no session / non-EC sensor:
           Default linear mapping (ADC → voltage → EC with DEFAULT_SLOPE).
           ``preview_available`` is False to signal low confidence.

        Temperature compensation (AUT-299):
           Uses ``session.session_metadata.calibration_temperature`` when available.
           Falls back to 25.0°C (industry standard reference); sets temperature_default=True.

        Returns:
            dict with keys:
                preview_ec_us_cm: float | None — EC estimate at 25°C reference
                preview_available: bool — False for raw-default estimates (no cal. points)
                temperature_used: float | None — Temperature applied for ATC
                temperature_default: bool — True when 25°C default was used
        """
        result: dict = {
            "preview_ec_us_cm": None,
            "preview_available": False,
            "temperature_used": None,
            "temperature_default": True,
        }

        if sensor_type != "ec":
            # Only EC sensors produce a meaningful µS/cm preview.
            return result

        # ── Resolve temperature for ATC ─────────────────────────────────────
        temperature = 25.0
        temperature_default = True
        if session is not None:
            metadata = getattr(session, "session_metadata", None) or {}
            cal_temp = metadata.get("calibration_temperature")
            if cal_temp is not None:
                try:
                    temperature = float(cal_temp)
                    temperature_default = False
                except (TypeError, ValueError):
                    pass

        result["temperature_used"] = temperature
        result["temperature_default"] = temperature_default

        # ── Convert raw ADC → voltage via shared normalization (matches ECSensorProcessor) ──
        voltage = raw_to_voltage(raw_value, adc_source=adc_source, pga_gain=pga_gain)

        # ── Extract captured calibration points from session (if any) ───────
        points: list[dict] = []
        cal_method: str = ""
        if session is not None:
            cal_method = getattr(session, "method", "") or ""
            raw_pts = getattr(session, "calibration_points", None) or {}
            if isinstance(raw_pts, dict):
                pts_list = raw_pts.get("points", [])
                if isinstance(pts_list, list):
                    points = pts_list

        # ── Strategy 1: ec_linear_2point with both reference points ─────────
        if cal_method == "ec_linear_2point" and len(points) >= 2:
            low_point = next(
                (p for p in points if str(p.get("point_role", "")).lower() == "reference_low"),
                None,
            )
            high_point = next(
                (p for p in points if str(p.get("point_role", "")).lower() == "reference_high"),
                None,
            )
            if low_point and high_point:
                try:
                    raw_low = float(low_point["raw"])
                    ref_low = float(low_point["reference"])
                    raw_high = float(high_point["raw"])
                    ref_high = float(high_point["reference"])

                    # AUT-299: normalize references to 25°C (same as _compute_ec_linear_2point)
                    temp_factor = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                    ref_low_at_T = ref_low * temp_factor
                    ref_high_at_T = ref_high * temp_factor

                    v_low = raw_to_voltage(raw_low, adc_source=adc_source, pga_gain=pga_gain)
                    v_high = raw_to_voltage(raw_high, adc_source=adc_source, pga_gain=pga_gain)
                    if abs(v_high - v_low) > 1e-6 and raw_high > raw_low:
                        slope = (ref_high_at_T - ref_low_at_T) / (v_high - v_low)
                        offset = ref_low_at_T - slope * v_low
                        ec_raw = slope * voltage + offset
                        # ATC: normalize to EC@25°C
                        temp_factor_atc = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                        if abs(temp_factor_atc) > 1e-6:
                            ec_25c = ec_raw / temp_factor_atc
                        else:
                            ec_25c = ec_raw
                        result["preview_ec_us_cm"] = round(max(0.0, min(20000.0, ec_25c)), 1)
                        result["preview_available"] = True
                        return result
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass  # Fall through to lower-precision strategies

        # ── Strategy 2: ec_linear_2point with ONE reference point ───────────
        if cal_method == "ec_linear_2point" and len(points) == 1:
            captured = points[0]
            role = str(captured.get("point_role", "")).lower()
            if role in ("reference_low", "reference_high"):
                try:
                    raw_pt = float(captured["raw"])
                    ref_pt = float(captured["reference"])
                    # AUT-299: normalize to 25°C
                    temp_factor = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                    ref_pt_at_T = ref_pt * temp_factor
                    v_pt = raw_to_voltage(raw_pt, adc_source=adc_source, pga_gain=pga_gain)
                    if abs(v_pt) > 1e-6:
                        # Single-point: force offset=0, derive slope from one point.
                        # This gives a coarse estimate but is better than the default.
                        slope = ref_pt_at_T / v_pt
                        offset = 0.0
                        ec_raw = slope * voltage + offset
                        temp_factor_atc = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                        if abs(temp_factor_atc) > 1e-6:
                            ec_25c = ec_raw / temp_factor_atc
                        else:
                            ec_25c = ec_raw
                        result["preview_ec_us_cm"] = round(max(0.0, min(20000.0, ec_25c)), 1)
                        # Single-point: preview_available=True but reduced confidence
                        result["preview_available"] = True
                        return result
                except (KeyError, TypeError, ValueError):
                    pass

        # ── Strategy 3: ec_2point (air+reference) or ec_1point with captured points ──
        if cal_method in ("ec_2point", "ec_1point") and len(points) >= 1:
            # Determine air+reference or just reference
            air_point = next(
                (p for p in points if str(p.get("point_role", "")).lower() == "air"),
                None,
            )
            ref_point = next(
                (p for p in points if str(p.get("point_role", "")).lower() == "reference"),
                None,
            )
            if air_point and ref_point:
                try:
                    raw_air = float(air_point["raw"])
                    ref_air = float(air_point.get("reference", 0.0))
                    raw_ref = float(ref_point["raw"])
                    ref_ref = float(ref_point["reference"])
                    # AUT-299: normalize
                    actual_at_T = ref_ref * (1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0))
                    v_air = raw_to_voltage(raw_air, adc_source=adc_source, pga_gain=pga_gain)
                    v_ref = raw_to_voltage(raw_ref, adc_source=adc_source, pga_gain=pga_gain)
                    if abs(v_ref - v_air) > 1e-6:
                        slope = (actual_at_T - ref_air) / (v_ref - v_air)
                        offset = ref_air - slope * v_air
                        ec_raw = slope * voltage + offset
                        temp_factor_atc = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                        if abs(temp_factor_atc) > 1e-6:
                            ec_25c = ec_raw / temp_factor_atc
                        else:
                            ec_25c = ec_raw
                        result["preview_ec_us_cm"] = round(max(0.0, min(20000.0, ec_25c)), 1)
                        result["preview_available"] = True
                        return result
                except (KeyError, TypeError, ValueError):
                    pass
            elif ref_point and not air_point and cal_method == "ec_1point":
                try:
                    raw_ref = float(ref_point["raw"])
                    ref_ref = float(ref_point["reference"])
                    actual_at_T = ref_ref * (1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0))
                    v_ref = raw_to_voltage(raw_ref, adc_source=adc_source, pga_gain=pga_gain)
                    if abs(v_ref) > 1e-6:
                        slope = actual_at_T / v_ref
                        offset = 0.0
                        ec_raw = slope * voltage + offset
                        temp_factor_atc = 1.0 + _EC_TEMP_COEFFICIENT * (temperature - 25.0)
                        if abs(temp_factor_atc) > 1e-6:
                            ec_25c = ec_raw / temp_factor_atc
                        else:
                            ec_25c = ec_raw
                        result["preview_ec_us_cm"] = round(max(0.0, min(20000.0, ec_25c)), 1)
                        result["preview_available"] = True
                        return result
                except (KeyError, TypeError, ValueError):
                    pass

        # ── Strategy 4 (fallback): Default linear mapping — no calibration data ──
        # preview_available=False signals to the frontend that this is a rough estimate.
        ec_default = _EC_DEFAULT_SLOPE * voltage + _EC_DEFAULT_OFFSET
        ec_default = max(0.0, min(20000.0, ec_default))
        result["preview_ec_us_cm"] = round(ec_default, 1)
        result["preview_available"] = False
        return result

    @staticmethod
    async def _broadcast_calibration_event(
        event_type: str,
        *,
        esp_id: str,
        gpio: int,
        correlation_id: Optional[str] = None,
        **data: object,
    ) -> None:
        """
        Broadcast calibration event via WebSocket (best-effort).

        Uses broadcast_threadsafe since MQTT handlers run in thread pool.
        """
        try:
            from ...websocket.manager import WebSocketManager

            ws = await WebSocketManager.get_instance()
            await ws.broadcast(
                message_type=event_type,
                data={
                    "esp_id": esp_id,
                    "gpio": gpio,
                    **{k: v for k, v in data.items() if v is not None},
                },
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.debug("CalibrationResponseHandler: WS broadcast failed: %s", e)


# ── Module-level convenience function (same pattern as sensor_handler) ────────

_handler_instance: Optional[CalibrationResponseHandler] = None


def get_calibration_response_handler() -> CalibrationResponseHandler:
    """Get singleton handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = CalibrationResponseHandler()
    return _handler_instance


async def handle_sensor_response(topic: str, payload: dict) -> bool:
    """
    Handle sensor response message (convenience function for subscriber registration).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if processed successfully
    """
    handler = get_calibration_response_handler()
    return await handler.handle_sensor_response(topic, payload)
