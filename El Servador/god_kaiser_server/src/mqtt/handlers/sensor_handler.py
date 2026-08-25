"""
MQTT Handler: Sensor Data Messages

Processes incoming sensor data from ESP32 devices:
- Parses sensor data topics
- Validates payloads (with structured error codes)
- Triggers Pi-Enhanced processing if enabled
- Saves data to database

Resilience Patterns:
- Uses resilient_session() with circuit breaker protection
- Timeout handling for overall operation
- Best-effort WebSocket broadcast

Error Codes:
- Uses ValidationErrorCode for payload validation errors
- Uses ConfigErrorCode for ESP device lookup errors
- Uses ServiceErrorCode for processing failures
"""

import asyncio
import time as _time_module
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ...core.config import get_settings
from ...core.error_codes import (
    ConfigErrorCode,
    ServiceErrorCode,
    ValidationErrorCode,
    get_error_code_description,
)
from ...core.logging_config import get_logger
from ...core.task_registry import create_tracked_task
from ...core.metrics import (
    increment_sensor_implausible,
    observe_sensor_e2e_latency_ms,
    update_sensor_value,
)
from ...utils.sensor_formatters import format_sensor_message
from ...utils.zone_subzone_resolver import resolve_zone_subzone_for_sensor
from ...core.resilience import (
    ServiceUnavailableError,
)
from sqlalchemy.orm.attributes import flag_modified

from ...db.models.enums import DataSource
from ...db.repositories import (
    ESPRepository,
    SensorRepository,
    SubzoneRepository,
)
from ...services.calibration_payloads import resolve_calibration_for_processor
from ...sensors.adc_normalization import ADC_SOURCE_ADS1115, ADC_SOURCE_INTERNAL
from ...services.device_scope_service import DeviceScopeService
from ...db.session import resilient_session
from ...schemas.sensor import QUALITY_LEVELS
from ..publisher import Publisher
from ..topics import TopicBuilder

logger = get_logger(__name__)


class SensorDataHandler:
    """
    Handles incoming sensor data messages from ESP32 devices.

    Flow:
    1. Parse topic → extract esp_id, gpio
    2. Validate payload structure
    3. Lookup ESP device and sensor config (with resilience)
    4. Check Pi-Enhanced mode
    5. Physical range validation (post-processing)
    6. Save data to database (with resilience)
    7. Trigger Pi-Enhanced processing if needed

    Resilience:
    - Uses resilient_session() for database operations (circuit breaker)
    - Timeout protection for overall handler operation
    - Best-effort WebSocket broadcast (no retry)
    """

    # Physical sensor limits from datasheets.
    # Values outside these ranges are DEFINITELY sensor errors.
    # Organized by sensor_type as used in MQTT payloads.
    SENSOR_PHYSICAL_LIMITS: dict[str, dict[str, float]] = {
        # Temperature sensors
        "sht31": {"min": -40.0, "max": 125.0},
        "sht31_temp": {"min": -40.0, "max": 125.0},
        "sht31_humidity": {"min": 0.0, "max": 100.0},
        "ds18b20": {"min": -55.0, "max": 125.0},
        "bmp280_temp": {"min": -40.0, "max": 85.0},
        "bmp280_pressure": {"min": 300.0, "max": 1100.0},
        "bme280_temp": {"min": -40.0, "max": 85.0},
        "bme280_pressure": {"min": 300.0, "max": 1100.0},
        "bme280_humidity": {"min": 0.0, "max": 100.0},
        # Analytical sensors
        "ph": {"min": 0.0, "max": 14.0},
        "ec": {"min": 0.0, "max": 20000.0},
        # Environmental sensors
        "moisture": {"min": 0.0, "max": 100.0},
        "soil_moisture": {"min": 0.0, "max": 100.0},
        "co2": {"min": 0.0, "max": 50000.0},  # AUT-576: SEN0220/MH-Z16 range 0-50000 ppm
        "light": {"min": 0.0, "max": 200000.0},
        "flow": {"min": 0.0, "max": 1000.0},
    }

    # Throttle interval for last_seen updates (seconds).
    # Heartbeat timeout is 300s, so 60s ensures last_seen stays current.
    LAST_SEEN_THROTTLE_SECONDS = 60
    LOGIC_FRESHNESS_SECONDS = 120
    STALE_DROP_SECONDS = 86400
    FUTURE_DRIFT_SECONDS = 30

    def __init__(self, publisher: Optional[Publisher] = None):
        """
        Initialize sensor data handler.

        Args:
            publisher: Publisher instance for Pi-Enhanced responses
        """
        self.publisher = publisher or Publisher()

        # Load resilience settings
        settings = get_settings()
        self._handler_timeout = settings.resilience.timeout_sensor_processing

        # In-memory cache for last_seen throttling per ESP
        self._last_seen_cache: dict[str, datetime] = {}

    async def handle_sensor_data(self, topic: str, payload: dict) -> bool:
        """
        Handle sensor data message.

        Expected topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data

        Expected payload:
        {
            "ts": 1735818000,            // or "timestamp" - both accepted
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,                 // or "raw_value" - both accepted
            "value": 0.0,
            "unit": "",
            "quality": "stale",
            "raw_mode": true             // optional, defaults to True
        }

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload dict

        Returns:
            True if message processed successfully, False otherwise
        """
        try:
            # Step 1: Parse topic
            parsed_topic = TopicBuilder.parse_sensor_data_topic(topic)
            if not parsed_topic:
                logger.error(
                    f"[{ValidationErrorCode.MISSING_REQUIRED_FIELD}] "
                    f"Failed to parse sensor data topic: {topic}"
                )
                return False

            esp_id_str = parsed_topic["esp_id"]
            gpio = parsed_topic["gpio"]

            logger.debug(
                f"Processing sensor data: esp_id={esp_id_str}, gpio={gpio}, "
                f"sensor_type={payload.get('sensor_type')}"
            )

            # Step 2: Validate payload
            validation_result = self._validate_payload(payload)
            if not validation_result["valid"]:
                error_code = validation_result.get(
                    "error_code", ValidationErrorCode.MISSING_REQUIRED_FIELD
                )
                logger.error(
                    f"[{error_code}] Invalid sensor data payload from {esp_id_str}: "
                    f"{validation_result['error']}",
                    extra={"failure_class": "sensor_payload_validation"},
                )
                return False

            # PKG-03: End-to-end latency observation (ESP32 publish -> server receive).
            # Observed BEFORE DB write so the histogram reflects ingest latency, not
            # persistence/logic cost. Accepts both "ts" and "timestamp" (alias in
            # ESP32 payloads). Unit detection: Wokwi/NTP firmware publishes seconds
            # (>1e9 but <1e10). Values >1e10 are treated as milliseconds.
            payload_ts_raw = payload.get("ts", payload.get("timestamp"))
            if isinstance(payload_ts_raw, (int, float)) and payload_ts_raw > 0:
                payload_ts_seconds = (
                    float(payload_ts_raw) / 1000.0
                    if payload_ts_raw > 1e10
                    else float(payload_ts_raw)
                )
                latency_ms = (_time_module.time() - payload_ts_seconds) * 1000.0
                # NTP-drift sanity guard: only observe latencies within [0, 5 min).
                # Negative values => ESP clock ahead of server; very large values =>
                # stale replay or unsynced firmware. Both should not pollute the
                # histogram.
                if 0 < latency_ms < 300_000:
                    observe_sensor_e2e_latency_ms(
                        sensor_type=str(payload.get("sensor_type", "unknown")),
                        latency_ms=latency_ms,
                    )

            # Step 3: Get database session and repositories (with resilience)
            try:
                async with resilient_session() as session:
                    esp_repo = ESPRepository(session)
                    sensor_repo = SensorRepository(session)
                    subzone_repo = SubzoneRepository(session)

                    # Step 4: Lookup ESP device
                    esp_device = await esp_repo.get_by_device_id(esp_id_str)
                    if not esp_device:
                        logger.error(
                            f"[{ConfigErrorCode.ESP_DEVICE_NOT_FOUND}] "
                            f"ESP device not found: {esp_id_str} - "
                            f"{get_error_code_description(ConfigErrorCode.ESP_DEVICE_NOT_FOUND)}"
                        )
                        return False

                    # Step 5: Extract sensor_type FIRST (needed for multi-value lookup)
                    # Normalize to lowercase — ESP32 sends lowercase, but DB may have mixed case
                    sensor_type = payload.get("sensor_type", "unknown").lower()

                    # Step 5.5: Extract interface-specific addresses for 4-way lookup
                    # DS18B20 sensors send ROM code to distinguish multiple sensors on same GPIO
                    onewire_address = payload.get("onewire_address")
                    # I2C sensors send address to distinguish multiple sensors at different addresses
                    i2c_address = payload.get("i2c_address")

                    # Step 6: Lookup sensor config (Multi-Value Support + OneWire/I2C Support)
                    sensor_config = None

                    if i2c_address is not None and i2c_address != 0:
                        # I2C Sensor: 4-way lookup (esp_id, gpio, sensor_type, i2c_address)
                        # Multiple I2C sensors can exist at different addresses on same bus
                        logger.debug(f"I2C sensor detected: gpio={gpio}, addr=0x{i2c_address:02X}")
                        sensor_config = await sensor_repo.get_by_esp_gpio_type_and_i2c(
                            esp_device.id, gpio, sensor_type, i2c_address
                        )
                        if not sensor_config:
                            logger.warning(
                                f"I2C sensor config not found: esp_id={esp_id_str}, "
                                f"gpio={gpio}, type={sensor_type}, addr=0x{i2c_address:02X}. "
                                f"Saving data without config."
                            )
                    elif onewire_address:
                        # OneWire Sensor: 4-way lookup (esp_id, gpio, sensor_type, onewire_address)
                        # Multiple DS18B20 sensors can share same GPIO (bus pin)
                        logger.debug(f"OneWire sensor detected: gpio={gpio}, rom={onewire_address}")
                        sensor_config = await sensor_repo.get_by_esp_gpio_type_and_onewire(
                            esp_device.id, gpio, sensor_type, onewire_address
                        )
                        if not sensor_config:
                            logger.warning(
                                f"OneWire sensor config not found: esp_id={esp_id_str}, "
                                f"gpio={gpio}, type={sensor_type}, rom={onewire_address}. "
                                f"Saving data without config."
                            )
                    else:
                        # Standard Sensor: 3-way lookup (esp_id, gpio, sensor_type)
                        # e.g., Analog sensors (pH, EC) or single I2C without address in payload
                        sensor_config = await sensor_repo.get_by_esp_gpio_and_type(
                            esp_device.id, gpio, sensor_type
                        )
                        if not sensor_config:
                            logger.warning(
                                f"Sensor config not found: esp_id={esp_id_str}, gpio={gpio}, "
                                f"type={sensor_type}. Saving data without config."
                            )

                    # Step 7: Extract remaining data from payload
                    # Accept both "raw" and "raw_value" for compatibility
                    raw_value = float(payload.get("raw", payload.get("raw_value")))
                    # raw_mode defaults to True (ESP32 always works in raw mode)
                    raw_mode = payload.get("raw_mode", True)

                    sampling_metadata: dict[str, Any] = {}
                    if payload.get("sample_count") is not None:
                        sampling_metadata["sample_count"] = int(payload["sample_count"])
                    if payload.get("adc_stddev") is not None:
                        sampling_metadata["adc_stddev"] = float(payload["adc_stddev"])
                    if payload.get("stable") is not None:
                        sampling_metadata["stable"] = bool(payload["stable"])
                    window_ms: float | None = (
                        float(payload["window_ms"])
                        if payload.get("window_ms") is not None
                        else None
                    )

                    # AUT-327: EC ADC reads 0 on disconnected probe or power fault → drop before persist.
                    # A raw ADC of 0 on an ESP32 12-bit ADC (range 0–4095) is physically implausible
                    # for a connected EC probe and indicates a hardware fault, not a valid measurement.
                    if sensor_type == "ec" and raw_mode and raw_value == 0.0:
                        logger.warning(
                            "[AUT-327] EC raw=0 dropped (disconnected probe?): esp_id=%s gpio=%s",
                            payload.get("esp_id"),
                            payload.get("gpio"),
                        )
                        return False

                    value = payload.get("value", 0.0)
                    quality = payload.get("quality", "unknown")
                    # PKG-HW-01: Ingest without matching sensor_configs row — not "good" path;
                    # keeps operator/observability distinct from calibrated good readings.
                    if not sensor_config and quality not in ("error", "critical"):
                        quality = "degraded"

                    # Unit resolution: registry > payload (avoids Latin-1/UTF-8 encoding issues)
                    from ...sensors.sensor_type_registry import (
                        get_unit_for_sensor_type,
                        sanitize_unit_encoding,
                    )

                    registry_unit = get_unit_for_sensor_type(sensor_type)
                    payload_unit = payload.get("unit", "")
                    unit = registry_unit or sanitize_unit_encoding(payload_unit)

                    # Step 8: Determine processing mode
                    processing_mode = "raw"
                    processed_value = None
                    # AUT-299/AUT-320: initialised before pi_enhanced block so metadata build
                    # (step 8d) can read ATC provenance regardless of processing path.
                    ec_extra_params: dict = {}
                    ph_extra_params: dict = {}

                    if (
                        sensor_config
                        and sensor_config.pi_enhanced
                        and raw_mode
                        and quality != "warming_up"
                    ):
                        # Pi-Enhanced processing needed
                        processing_mode = "pi_enhanced"

                        # ATC pre-lookup: for EC sensors, fetch latest temperature from
                        # this ESP before calling the processor (session available here).
                        if sensor_type == "ec":
                            ec_extra_params.update(sampling_metadata)
                            atc_temp, atc_source = await self._try_get_ec_temperature(
                                esp_device, session, sensor_config=sensor_config
                            )
                            if atc_source == "default_25c_degraded":
                                # AUT-672: Explicitly linked sensor went dark (age >= MAX_AGE).
                                # Emit Warning (not abort) — measurement continues with 25 °C.
                                await self._emit_atc_degraded_warning(
                                    esp_id_str=esp_id_str,
                                    gpio=gpio,
                                    sensor_type=sensor_type,
                                    session=session,
                                )
                            if atc_temp is not None:
                                ec_extra_params["temperature_compensation"] = atc_temp
                                logger.debug(
                                    "[EC-ATC] Using temperature %.2f°C for ATC on %s GPIO %s (source=%s)",
                                    atc_temp,
                                    esp_id_str,
                                    gpio,
                                    atc_source,
                                )
                            else:
                                atc_temp = 25.0  # ECSensorProcessor.REFERENCE_TEMP fallback
                                atc_source = "default_25"
                                ec_extra_params["temperature_compensation"] = atc_temp
                                logger.debug(
                                    "[EC-ATC] No temperature sensor available — using reference temp 25.0°C for ATC on %s GPIO %s",
                                    esp_id_str,
                                    gpio,
                                )
                            # Transport the ATC source into extra_params for metadata enrichment.
                            # Filtered out before passing to processor (processor ignores unknown keys
                            # but we strip it explicitly below to keep the interface clean).
                            ec_extra_params["_atc_source"] = atc_source
                            ec_extra_params["temp_compensated"] = atc_source not in (
                                "default_25",
                                None,
                            )

                        # AUT-320: ATC pre-lookup for pH sensors.
                        # PHSensorProcessor._apply_temperature_compensation() applies
                        # pH_compensated = pH_raw + slope_factor * (T - 25.0) when
                        # params["temperature_compensation"] is present.
                        # Default without a linked temp sensor: 25.0°C → no change.
                        if sensor_type == "ph":
                            ph_atc_temp, ph_atc_source = await self._try_get_atc_temperature(
                                esp_device,
                                session,
                                sensor_config=sensor_config,
                                log_prefix="pH-ATC",
                            )
                            if ph_atc_source == "default_25c_degraded":
                                # AUT-672: Explicitly linked sensor went dark (age >= MAX_AGE).
                                # Emit Warning (not abort) — measurement continues with 25 °C.
                                await self._emit_atc_degraded_warning(
                                    esp_id_str=esp_id_str,
                                    gpio=gpio,
                                    sensor_type=sensor_type,
                                    session=session,
                                )
                            if ph_atc_temp is not None:
                                ph_extra_params["temperature_compensation"] = ph_atc_temp
                                logger.debug(
                                    "[pH-ATC] Using temperature %.2f°C for ATC on %s GPIO %s (source=%s)",
                                    ph_atc_temp,
                                    esp_id_str,
                                    gpio,
                                    ph_atc_source,
                                )
                            else:
                                ph_atc_temp = 25.0  # PHSensorProcessor reference temp fallback
                                ph_atc_source = "default_25c"
                                ph_extra_params["temperature_compensation"] = ph_atc_temp
                                logger.debug(
                                    "[pH-ATC] No temperature sensor available — using reference temp 25.0°C for ATC on %s GPIO %s",
                                    esp_id_str,
                                    gpio,
                                )
                            # Transport ATC source for metadata enrichment.
                            # Stripped before passing to processor (internal transport key).
                            ph_extra_params["_atc_source"] = ph_atc_source

                        # Merge sensor-specific extra params (EC or pH; mutually exclusive
                        # for any single sensor_type within one message).
                        merged_extra_params = {**ec_extra_params, **ph_extra_params}
                        if window_ms is not None:
                            merged_extra_params["time_window"] = window_ms / 1000.0

                        # Trigger Pi-Enhanced processing (pass raw_mode!)
                        pi_result = await self._trigger_pi_enhanced_processing(
                            esp_id_str,
                            gpio,
                            sensor_type,
                            raw_value,
                            sensor_config,
                            raw_mode=raw_mode,  # Pass raw_mode to processor
                            extra_params=merged_extra_params,
                        )

                        if pi_result:
                            processed_value = pi_result["processed_value"]
                            unit = pi_result["unit"]
                            quality = pi_result["quality"]
                            proc_meta = pi_result.get("metadata") or {}
                            if proc_meta.get("ec_stddev") is not None:
                                sampling_metadata["ec_stddev"] = proc_meta["ec_stddev"]
                            if proc_meta.get("calibrated") is not None:
                                sampling_metadata["calibrated"] = proc_meta["calibrated"]

                            # Publish processed data back to ESP
                            self.publisher.publish_pi_enhanced_response(
                                esp_id_str,
                                gpio,
                                processed_value,
                                unit,
                                quality,
                                retry=False,
                            )

                            logger.debug(
                                f"Pi-Enhanced processing complete: raw={raw_value}, "
                                f"processed={processed_value} {unit}"
                            )
                        else:
                            # Processing failed, mark quality
                            quality = "error"
                            logger.error(
                                f"[{ServiceErrorCode.OPERATION_TIMEOUT}] "
                                f"Pi-Enhanced processing failed: esp_id={esp_id_str}, "
                                f"gpio={gpio}, sensor_type={sensor_type} - "
                                f"{get_error_code_description(ServiceErrorCode.OPERATION_TIMEOUT)}"
                            )

                    elif not raw_mode:
                        # ESP already processed locally
                        processing_mode = "local"
                        processed_value = value

                    elif raw_mode and sensor_type == "ds18b20":
                        # Safety net: DS18B20 raw int16 must always be converted
                        # to Celsius, even when pi_enhanced=False.
                        # Formula: raw_int16 * 0.0625 = Celsius (12-bit resolution).
                        # Without this, raw integers (e.g. 280 for ~17.5°C) would be
                        # stored directly as the processed_value in Celsius.
                        DS18B20_RESOLUTION = 0.0625
                        processing_mode = "raw_conversion"
                        processed_value = float(raw_value) * DS18B20_RESOLUTION
                        logger.debug(
                            "[DS18B20] Raw conversion (pi_enhanced=False): raw=%s → %.2f°C",
                            raw_value,
                            processed_value,
                        )

                    elif raw_mode and sensor_type in ("sht31_temp", "sht31"):
                        # AUT-645 Safety net: SHT31 raw 16-bit register → Celsius.
                        # Mirrors DS18B20 safety net above. Without this, raw I2C values
                        # (e.g. 26895 for ~26.6 °C) land directly as processed_value.
                        # Formula from SHT31 datasheet: T [°C] = -45 + 175 * raw / 65535
                        processing_mode = "raw_conversion"
                        processed_value = -45.0 + 175.0 * (float(raw_value) / 65535.0)
                        logger.debug(
                            "[SHT31] Raw conversion (pi_enhanced=False): raw=%s → %.2f°C",
                            raw_value,
                            processed_value,
                        )

                    elif raw_mode and sensor_type == "sht31_humidity":
                        # AUT-645 Safety net: SHT31 raw 16-bit register → %RH.
                        # Formula from SHT31 datasheet: RH [%] = 100 * raw / 65535
                        processing_mode = "raw_conversion"
                        processed_value = 100.0 * (float(raw_value) / 65535.0)
                        logger.debug(
                            "[SHT31] Raw conversion (pi_enhanced=False): raw=%s → %.2f%%RH",
                            raw_value,
                            processed_value,
                        )

                    # Fallback: if no processing branch produced a value,
                    # use raw_value so processed_value is never NULL in DB.
                    # Exception: warming_up readings keep processed_value=None (AUT-975).
                    if processed_value is None and quality != "warming_up":
                        processed_value = raw_value

                    # Step 8b: Physical range validation (post-processing)
                    # Check processed value against sensor physical limits.
                    # Values outside datasheet range get quality="critical" but are
                    # still saved (never discarded) for diagnostic purposes.
                    #
                    # Validated modes: pi_enhanced (server-processed), local (ESP-processed,
                    # physical units), raw_conversion (safety-net converted, physical units).
                    # Excluded: "raw" mode — ADC counts (0-4095) use different scales than
                    # physical limits (e.g. moisture: ADC 0-4095 vs. physical 0-100 %).
                    display_val = processed_value if processed_value is not None else value
                    skip_range_check = (
                        processing_mode not in ("pi_enhanced", "local", "raw_conversion")
                        or processed_value is None
                    )
                    if (
                        display_val is not None
                        and quality not in ("error",)
                        and not skip_range_check
                    ):
                        range_result = self._check_physical_range(sensor_type, float(display_val))
                        if range_result == "implausible":
                            logger.warning(
                                f"Implausible sensor value: esp_id={esp_id_str}, "
                                f"gpio={gpio}, sensor_type={sensor_type}, "
                                f"value={display_val}, "
                                f"limits={self.SENSOR_PHYSICAL_LIMITS.get(sensor_type)}"
                            )
                            quality = "critical"
                            increment_sensor_implausible(sensor_type, esp_id_str)

                    # Step 8c: Detect data source (mock/test/production)
                    data_source = self._detect_data_source(esp_device, payload)

                    # Step 8d: Resolve zone_id/subzone_id at measurement time (Phase 0.1)
                    # T13-R1: Pass sensor_config_id and sensor_type for I2C GPIO-0 resolution
                    # T13-R2: DeviceScopeService has 30s in-memory cache (avoids DB query per message)
                    scope_service = DeviceScopeService(session)
                    zone_id, subzone_id = await resolve_zone_subzone_for_sensor(
                        esp_id_str,
                        gpio,
                        esp_repo,
                        subzone_repo,
                        sensor_config_id=str(sensor_config.id) if sensor_config else None,
                        sensor_type=sensor_type,
                        sensor_config=sensor_config,
                        scope_service=scope_service,
                    )

                    # Step 9: Save data to database
                    # Convert ESP32 timestamp to UTC datetime
                    # BUG-05 fix: ts<=0 (Wokwi without NTP) → use server timestamp
                    # NTP fix: time_valid=false → ESP has no synchronized time → use server timestamp
                    time_valid = payload.get(
                        "time_valid", True
                    )  # Default True for old firmware without flag
                    esp32_timestamp_raw = payload.get("ts", payload.get("timestamp"))

                    if (
                        not time_valid
                        or esp32_timestamp_raw is None
                        or esp32_timestamp_raw <= 0
                        or esp32_timestamp_raw < 1577836800
                    ):
                        esp32_timestamp = datetime.now(timezone.utc)
                    else:
                        esp32_timestamp = datetime.fromtimestamp(
                            (
                                esp32_timestamp_raw / 1000
                                if esp32_timestamp_raw > 1e10
                                else esp32_timestamp_raw
                            ),
                            tz=timezone.utc,
                        )

                    now_utc = datetime.now(timezone.utc)
                    event_age_seconds = (now_utc - esp32_timestamp).total_seconds()
                    stale_for_logic = (
                        event_age_seconds > self.LOGIC_FRESHNESS_SECONDS
                        or event_age_seconds < -self.FUTURE_DRIFT_SECONDS
                    )
                    stale_drop = event_age_seconds > self.STALE_DROP_SECONDS

                    # Hard drop only for extreme replay data to protect ingest and logic.
                    if stale_drop:
                        logger.warning(
                            "Dropping stale sensor event: esp_id=%s gpio=%s sensor=%s age=%.1fs",
                            esp_id_str,
                            gpio,
                            sensor_type,
                            event_age_seconds,
                        )
                        return True

                    # Build metadata with interface addresses for historical traceability
                    sensor_metadata = {"raw_mode": raw_mode}
                    sensor_metadata.update(sampling_metadata)
                    if i2c_address:
                        sensor_metadata["i2c_address"] = i2c_address
                    if onewire_address:
                        sensor_metadata["onewire_address"] = onewire_address
                    # AUT-299: Enrich metadata for EC sensors with ATC provenance
                    if sensor_type == "ec" and ec_extra_params:
                        atc_source_meta = ec_extra_params.get("_atc_source", "default_25")
                        sensor_metadata["temp_compensation_value"] = ec_extra_params.get(
                            "temperature_compensation", 25.0
                        )
                        sensor_metadata["temp_source"] = atc_source_meta
                        sensor_metadata["temp_compensated"] = ec_extra_params.get(
                            "temp_compensated", False
                        )
                    # AUT-320: Enrich metadata for pH sensors with ATC provenance
                    if sensor_type == "ph" and ph_extra_params:
                        ph_atc_source_meta = ph_extra_params.get("_atc_source", "default_25c")
                        sensor_metadata["temp_used"] = ph_extra_params.get(
                            "temperature_compensation", 25.0
                        )
                        sensor_metadata["temp_source"] = ph_atc_source_meta

                    # AUT-723 E3: warming_up is quality-only. Firmware often
                    # publishes value=0 during warmup; persisting that raw 0
                    # becomes a fake chart Y (pH 0.00). Skip save_data; keep
                    # live WS with value=None (AUT-975 '--').
                    if quality == "warming_up":
                        logger.info(
                            "Skipping sensor_data persist for warming_up "
                            "(AUT-723 E3, no numeric chart Y): esp_id=%s gpio=%s",
                            esp_id_str,
                            gpio,
                        )
                        await self._update_last_seen_throttled(esp_id_str, esp_repo)
                        await session.commit()
                        try:
                            from ...websocket.manager import WebSocketManager

                            ws_manager = await WebSocketManager.get_instance()
                            message = format_sensor_message(
                                sensor_type=sensor_type,
                                gpio=gpio,
                                value=None,
                                unit=unit,
                            )
                            await ws_manager.broadcast(
                                "sensor_data",
                                {
                                    "esp_id": esp_id_str,
                                    "message": message,
                                    "severity": "info",
                                    "device_id": esp_id_str,
                                    "gpio": gpio,
                                    "sensor_type": sensor_type,
                                    "value": None,
                                    "unit": unit,
                                    "quality": quality,
                                    "timestamp": esp32_timestamp_raw,
                                    "zone_id": zone_id,
                                    "subzone_id": subzone_id,
                                    "config_id": (str(sensor_config.id) if sensor_config else None),
                                    "i2c_address": i2c_address if i2c_address else None,
                                    "onewire_address": (
                                        onewire_address if onewire_address else None
                                    ),
                                    **sampling_metadata,
                                },
                            )
                        except Exception as e:
                            logger.warning("Failed to broadcast warming_up via WebSocket: %s", e)
                        return True

                    sensor_data = await sensor_repo.save_data(
                        esp_id=esp_device.id,
                        gpio=gpio,
                        sensor_type=sensor_type,
                        raw_value=raw_value,
                        processed_value=processed_value,
                        unit=unit,
                        processing_mode=processing_mode,
                        quality=quality,
                        timestamp=esp32_timestamp,
                        metadata=sensor_metadata,
                        data_source=data_source,
                        zone_id=zone_id,
                        subzone_id=subzone_id,
                        device_name=esp_device.name,
                    )

                    # MQTT QoS 1 dedup: save_data returns None for duplicate messages
                    if sensor_data is None:
                        return True

                    # Step 9a: Secondary health indicator — update last_seen (throttled)
                    await self._update_last_seen_throttled(esp_id_str, esp_repo)

                    # Step 9b: Update sensor config on successful data save
                    if sensor_config:
                        # Activate config on first successful data receipt
                        if sensor_config.config_status == "pending":
                            sensor_config.config_status = "active"
                            logger.info(
                                f"Sensor config activated: esp_id={esp_id_str}, "
                                f"gpio={gpio}, sensor_type={sensor_type}, "
                                f"config_status: pending → active"
                            )

                        # Update latest reading in sensor_metadata
                        latest_value = processed_value if processed_value is not None else raw_value
                        updated_metadata = dict(sensor_config.sensor_metadata or {})
                        updated_metadata["latest_value"] = latest_value
                        updated_metadata["latest_timestamp"] = esp32_timestamp.isoformat()
                        updated_metadata["latest_quality"] = quality
                        sensor_config.sensor_metadata = updated_metadata
                        flag_modified(sensor_config, "sensor_metadata")

                    # Commit transaction
                    await session.commit()

                    logger.info(
                        f"Sensor data saved: id={sensor_data.id}, esp_id={esp_id_str}, "
                        f"gpio={gpio}, processing_mode={processing_mode}"
                    )

                    # Update Prometheus metrics for Grafana alerting
                    display_value = processed_value if processed_value is not None else raw_value
                    update_sensor_value(esp_id_str, sensor_type, display_value)

                    # ═══════════════════════════════════════════════════════
                    # THRESHOLD → NOTIFICATION PIPELINE (Phase 4A.7)
                    # Alerts are ALWAYS evaluated. Notifications are
                    # suppressed if sensor/device is in suppression mode.
                    # ═══════════════════════════════════════════════════════
                    if sensor_config:
                        try:
                            await self._evaluate_thresholds_and_notify(
                                session=session,
                                sensor_config=sensor_config,
                                esp_id_str=esp_id_str,
                                gpio=gpio,
                                sensor_type=sensor_type,
                                value=display_value,
                            )
                        except Exception as e:
                            # Threshold evaluation MUST NOT block data processing
                            logger.warning(
                                f"Threshold evaluation failed for {esp_id_str} GPIO {gpio}: {e}"
                            )

                    # WebSocket Broadcast (best-effort, outside transaction)
                    try:
                        from ...websocket.manager import WebSocketManager

                        ws_manager = await WebSocketManager.get_instance()

                        # Einheitliche Message generieren (Server-Centric)
                        # warming_up: keep value=None so frontend shows '--' (AUT-975)
                        display_value = (
                            None
                            if quality == "warming_up"
                            else (processed_value if processed_value is not None else raw_value)
                        )
                        message = format_sensor_message(
                            sensor_type=sensor_type,
                            gpio=gpio,
                            value=display_value,
                            unit=unit,
                        )

                        await ws_manager.broadcast(
                            "sensor_data",
                            {
                                "esp_id": esp_id_str,
                                "message": message,  # Menschenverstandliche Message
                                "severity": "info",
                                "device_id": esp_id_str,
                                "gpio": gpio,
                                "sensor_type": sensor_type,
                                "value": display_value,
                                "unit": unit,
                                "quality": quality,
                                "timestamp": esp32_timestamp_raw,
                                "zone_id": zone_id,
                                "subzone_id": subzone_id,
                                "config_id": str(sensor_config.id) if sensor_config else None,
                                "i2c_address": i2c_address if i2c_address else None,
                                "onewire_address": onewire_address if onewire_address else None,
                                **sampling_metadata,
                            },
                        )
                    except Exception as e:
                        logger.warning(f"Failed to broadcast sensor data via WebSocket: {e}")

                    # ═══════════════════════════════════════════════════════
                    # VPD COMPUTATION HOOK (PB-01)
                    # Event-driven: compute and persist VPD when SHT31 data
                    # arrives. VPD is stored as sensor_data with gpio=0.
                    # Quality guard: skip VPD if source reading has quality=error
                    # to avoid computing VPD from invalid sensor values (P3-fix).
                    # ═══════════════════════════════════════════════════════
                    if sensor_type == "sht31_temp":
                        if quality == "error":
                            logger.warning(
                                f"Skipping VPD computation: {sensor_type} quality=error "
                                f"(esp={esp_id_str}, gpio={gpio}, value={processed_value})"
                            )
                        else:
                            try:
                                await self._try_compute_vpd(
                                    esp_device=esp_device,
                                    trigger_sensor_type=sensor_type,
                                    trigger_gpio=gpio,
                                    trigger_value=processed_value,
                                    timestamp=esp32_timestamp,
                                    data_source=data_source,
                                    zone_id=zone_id,
                                    subzone_id=subzone_id,
                                    session=session,
                                )
                            except Exception as e:
                                logger.debug(f"VPD computation skipped for {esp_id_str}: {e}")

                    # Reconnect-bootstrap guard (AUT-125):
                    # During the adoption phase right after an ESP reconnect,
                    # analog sensors (e.g. soil moisture) can briefly report 0 %
                    # due to ADC charge relaxation. Skip logic evaluation while
                    # the adoption cycle is still ongoing to avoid spurious
                    # actuator triggers from these bootstrap artefacts. The data
                    # is still persisted, broadcast and counted in metrics.
                    skip_logic_for_adoption = False
                    try:
                        from ...services.state_adoption_service import (
                            get_state_adoption_service,
                        )

                        adoption_svc = get_state_adoption_service()
                        if adoption_svc is not None and await adoption_svc.is_adopting(esp_id_str):
                            skip_logic_for_adoption = True
                            logger.info(
                                "reconnect_bootstrap_guard: skipping logic eval for %s "
                                "GPIO %s (%s value=%.3f) during adoption phase",
                                esp_id_str,
                                gpio,
                                sensor_type,
                                float(
                                    processed_value if processed_value is not None else raw_value
                                ),
                            )
                    except Exception as e:
                        # Guard must never block ingest — log and continue.
                        logger.debug(f"Adoption-phase guard check failed (continuing): {e}")

                    # Logic trigger is freshness-gated on event-time.
                    if stale_for_logic:
                        logger.info(
                            "Stale-observe: logic trigger skipped for %s GPIO %s (%s age=%.1fs)",
                            esp_id_str,
                            gpio,
                            sensor_type,
                            event_age_seconds,
                        )
                    elif skip_logic_for_adoption:
                        # Already logged above; explicit branch keeps control flow obvious.
                        pass
                    else:
                        try:
                            from ...services.logic_engine import get_logic_engine

                            async def trigger_logic_evaluation():
                                try:
                                    logic_engine = get_logic_engine()
                                    if logic_engine:
                                        await logic_engine.evaluate_sensor_data(
                                            esp_id=esp_id_str,
                                            gpio=gpio,
                                            sensor_type=sensor_type,
                                            value=processed_value or raw_value,
                                            zone_id=zone_id,
                                            subzone_id=subzone_id,
                                            quality=quality,
                                        )
                                    else:
                                        logger.debug(
                                            "Logic Engine not yet initialized, skipping evaluation"
                                        )
                                except Exception as e:
                                    logger.error(f"Error in logic evaluation: {e}", exc_info=True)

                            # Create non-blocking task with done callback for visibility
                            task = create_tracked_task(
                                trigger_logic_evaluation(),
                                name=f"logic_eval_{esp_id_str}_{gpio}",
                            )

                            def _on_logic_task_done(t: asyncio.Task) -> None:
                                if t.cancelled():
                                    logger.warning(
                                        f"Logic evaluation task cancelled for {esp_id_str} GPIO {gpio}"
                                    )
                                elif t.exception():
                                    logger.error(
                                        f"Logic evaluation task failed for {esp_id_str} GPIO {gpio}: "
                                        f"{t.exception()}",
                                        exc_info=t.exception(),
                                    )

                            task.add_done_callback(_on_logic_task_done)
                        except Exception as e:
                            logger.warning(f"Failed to trigger logic evaluation: {e}")

                    return True

            except ServiceUnavailableError as e:
                # Database circuit breaker is OPEN
                logger.warning(
                    f"[resilience] Sensor data handling blocked: {e.service_name} unavailable. "
                    f"Data from {esp_id_str} GPIO {gpio} will be dropped."
                )
                return False

        except Exception as e:
            logger.error(
                f"Error handling sensor data: {e}",
                exc_info=True,
            )
            return False

    # ─── VPD Computation (PB-01) ────────────────────────────────────

    # Max age for partner reading: if the partner value is older than this,
    # we skip VPD computation to avoid stale cross-sensor calculations.
    _VPD_MAX_AGE = timedelta(seconds=60)

    async def _try_compute_vpd(
        self,
        esp_device,
        trigger_sensor_type: str,
        trigger_gpio: int,
        trigger_value: float,
        timestamp: datetime,
        data_source: str,
        zone_id: Optional[str],
        subzone_id: Optional[str],
        session,
    ) -> None:
        """Compute and persist VPD if both T and RH are available for this ESP.

        Called after every sht31_temp or sht31_humidity data save. Looks up the
        partner reading (humidity for temp, temp for humidity) on the SAME gpio.
        If both values are fresh (within _VPD_MAX_AGE), VPD is calculated, saved
        as sensor_data with gpio=0, and broadcast via WebSocket.

        On first VPD save for an ESP, a SensorConfig row is created so VPD
        appears in the frontend sensor dropdown (Block 7).
        """
        from ...services.vpd_calculator import calculate_vpd

        sensor_repo = SensorRepository(session)

        # Determine which value we have and which we need
        if trigger_sensor_type == "sht31_temp":
            partner_type = "sht31_humidity"
            temp_value = trigger_value
            rh_reading = await sensor_repo.get_latest_reading(
                esp_id=esp_device.id,
                gpio=trigger_gpio,
                sensor_type=partner_type,
            )
            if rh_reading is None:
                return
            if (timestamp - rh_reading.timestamp) > self._VPD_MAX_AGE:
                return
            rh_value = rh_reading.processed_value
        else:
            # trigger is sht31_humidity
            partner_type = "sht31_temp"
            rh_value = trigger_value
            temp_reading = await sensor_repo.get_latest_reading(
                esp_id=esp_device.id,
                gpio=trigger_gpio,
                sensor_type=partner_type,
            )
            if temp_reading is None:
                return
            if (timestamp - temp_reading.timestamp) > self._VPD_MAX_AGE:
                return
            temp_value = temp_reading.processed_value

        if temp_value is None or rh_value is None:
            return

        # Calculate VPD
        vpd = calculate_vpd(float(temp_value), float(rh_value))
        if vpd is None:
            return

        # Save VPD as sensor_data with gpio=0 (virtual sensor convention)
        vpd_data = await sensor_repo.save_data(
            esp_id=esp_device.id,
            gpio=0,
            sensor_type="vpd",
            raw_value=vpd,
            processed_value=vpd,
            unit="kPa",
            processing_mode="computed",
            quality="good",
            timestamp=timestamp,
            metadata={"source_temp_type": "sht31_temp", "source_rh_type": "sht31_humidity"},
            data_source=data_source,
            zone_id=zone_id,
            subzone_id=subzone_id,
            device_name=esp_device.name,
        )

        # Duplicate (same timestamp) — silently skip
        if vpd_data is None:
            return

        # Ensure SensorConfig exists for VPD (Block 7 — backend approach)
        # Uses create_if_not_exists to prevent race condition duplicates (V19-F02)
        await sensor_repo.create_if_not_exists(
            esp_id=esp_device.id,
            gpio=0,
            sensor_type="vpd",
            sensor_name="VPD (berechnet)",
            interface_type="VIRTUAL",
            enabled=True,
            pi_enhanced=False,
            config_status="active",
        )

        # Update simulation_config so REST API returns current VPD value.
        # Without this, _build_mock_esp_response defaults to raw_value=0.
        if esp_device.device_metadata:
            sim_sensors = esp_device.device_metadata.get("simulation_config", {}).get("sensors", {})
            for entry in sim_sensors.values():
                if entry.get("sensor_type") == "vpd" and entry.get("gpio") == 0:
                    entry["raw_value"] = vpd
                    entry["quality"] = "good"
                    flag_modified(esp_device, "device_metadata")
                    break

        await session.commit()

        esp_id_str = esp_device.device_id

        logger.info(
            f"VPD computed and saved: esp_id={esp_id_str}, vpd={vpd} kPa "
            f"(T={temp_value}°C, RH={rh_value}%)"
        )

        # WebSocket broadcast for VPD (separate from original sensor broadcast)
        try:
            from ...websocket.manager import WebSocketManager
            from ...utils.sensor_formatters import format_sensor_message

            ws_manager = await WebSocketManager.get_instance()
            message = format_sensor_message(
                sensor_type="vpd",
                gpio=0,
                value=vpd,
                unit="kPa",
            )
            await ws_manager.broadcast(
                "sensor_data",
                {
                    "esp_id": esp_id_str,
                    "message": message,
                    "severity": "info",
                    "device_id": esp_id_str,
                    "gpio": 0,
                    "sensor_type": "vpd",
                    "value": vpd,
                    "unit": "kPa",
                    "quality": "good",
                    "timestamp": int(timestamp.timestamp()),
                    "zone_id": zone_id,
                    "subzone_id": subzone_id,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast VPD data via WebSocket: {e}")

    # ─── ATC Temperature Lookup (shared: EC + pH) ─────────────────

    # Age thresholds for ATC temperature cache classification (AUT-321 / AUT-672).
    #
    # Two-tier usable-cache policy (AUT-672: Soft-Fallback):
    #   < _ATC_FRESH_AGE  : fresh reading → use directly, source = "ok" variant
    #   < _ATC_MAX_AGE    : stale but usable → use with source = "cached_temp"
    #   >= _ATC_MAX_AGE   : too old — Priority-1 (explicit link): "default_25c_degraded"
    #                        + Warning; Priority-2 (auto-discovery): "default_25c" (silent)
    #
    # _ATC_STALE_AGE is retained for reference; no longer a hard decision boundary.
    _ATC_MAX_AGE = timedelta(minutes=5)
    _ATC_FRESH_AGE = timedelta(seconds=5)
    _ATC_STALE_AGE = timedelta(seconds=90)

    async def _try_get_atc_temperature(
        self,
        esp_device,
        session,
        sensor_config=None,
        log_prefix: str = "ATC",
    ) -> tuple[Optional[float], str]:
        """Look up the latest temperature reading for automatic temperature compensation.

        Shared implementation used by both EC (AUT-299) and pH (AUT-320) sensors.

        Priority 1 (AUT-299): If sensor_config.temp_sensor_config_id is set, fetch the
        reading from the explicitly linked temperature sensor (cross-ESP capable).

        Priority 2 (existing behavior): Same-ESP auto-discovery — searches for the most
        recent temperature reading (sensor_type "temperature" or "sht31_temp") on the
        same ESP device regardless of GPIO pin.

        AUT-672 — Soft-Fallback policy (supersedes AUT-321 Hard-Abort):
            age < _ATC_FRESH_AGE  → fresh → source label "config:<uuid>" / "same_esp"
            age < _ATC_MAX_AGE    → stale but usable → source label "cached_temp"
            age ≥ _ATC_MAX_AGE (Priority-1 only, explicit link configured):
                                  → returns (None, "default_25c_degraded"); caller emits
                                    Warning-Event then continues with 25 °C reference.
            reading absent/None (Priority-1, Setup):
                                  → returns (None, "default_25c") silently (sensor not yet
                                    connected — no error, no event).
            no sensor configured or auto-discovery all expired:
                                  → returns (None, "default_25c") silently.

        Args:
            esp_device: ESPDevice ORM instance (provides device UUID)
            session: Active async database session
            sensor_config: Optional SensorConfig ORM instance for explicit temp link
            log_prefix: Log tag prefix for sensor-type-specific log lines (e.g. "EC-ATC", "pH-ATC")

        Returns:
            Tuple of (temperature_celsius_or_None, source_label) where source_label is
            one of "config:<uuid>", "same_esp", "cached_temp", "default_25c_degraded",
            or "default_25c". "read_failed" is no longer returned (AUT-672).
        """
        sensor_repo = SensorRepository(session)
        now_utc = datetime.now(timezone.utc)

        # Priority 1: Explicitly configured temp sensor (cross-ESP capable)
        if sensor_config is not None and sensor_config.temp_sensor_config_id is not None:
            linked_config = await sensor_repo.get_by_id(sensor_config.temp_sensor_config_id)
            if linked_config is not None:
                reading = await sensor_repo.get_latest_reading(
                    esp_id=linked_config.esp_id,
                    gpio=linked_config.gpio,
                    sensor_type=linked_config.sensor_type,
                )
                if reading is not None and reading.processed_value is not None:
                    ts = reading.timestamp
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = now_utc - ts
                    if age < self._ATC_FRESH_AGE:
                        # Fresh reading — use directly with explicit config label
                        source_label = f"config:{sensor_config.temp_sensor_config_id}"
                        logger.debug(
                            "[%s] Using linked temp sensor %s (%.2f°C, age=%.0fs, fresh) for ATC",
                            log_prefix,
                            sensor_config.temp_sensor_config_id,
                            float(reading.processed_value),
                            age.total_seconds(),
                        )
                        return (float(reading.processed_value), source_label)
                    if age < self._ATC_MAX_AGE:
                        # Stale but within usable window — mark as cached_temp
                        logger.debug(
                            "[%s] Using linked temp sensor %s (%.2f°C, age=%.0fs, cached_temp) for ATC",
                            log_prefix,
                            sensor_config.temp_sensor_config_id,
                            float(reading.processed_value),
                            age.total_seconds(),
                        )
                        return (float(reading.processed_value), "cached_temp")
                    # age >= MAX_AGE: explicitly configured sensor went dark — real degradation
                    logger.warning(
                        "[%s] Linked temp sensor %s reading expired (age=%.0fs >= %.0fs) — degraded, using 25 °C fallback",
                        log_prefix,
                        sensor_config.temp_sensor_config_id,
                        age.total_seconds(),
                        self._ATC_MAX_AGE.total_seconds(),
                    )
                    return (None, "default_25c_degraded")
                # Linked sensor configured but no reading yet (Setup: sensor not yet connected)
                logger.debug(
                    "[%s] Linked temp sensor %s has no valid reading yet — using 25 °C fallback (Setup)",
                    log_prefix,
                    sensor_config.temp_sensor_config_id,
                )
                return (None, "default_25c")

        # Priority 2: Same-ESP auto-discovery (existing behavior)
        # Ghost-Dependency-Fix (AUT-672/Edit-3): only use a reading when it is within
        # _ATC_MAX_AGE.  Readings older than that are skipped entirely so that a stale
        # DB entry from an old or removed sensor never blocks measurement.
        for temp_type in ("temperature", "sht31_temp"):
            reading = await sensor_repo.get_latest_reading_for_esp(
                esp_id=esp_device.id,
                sensor_type=temp_type,
            )
            if reading is None:
                continue
            if reading.processed_value is None:
                continue
            ts = reading.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = now_utc - ts
            if age >= self._ATC_MAX_AGE:
                # Beyond outer guard: too stale to use
                logger.debug(
                    "[%s] Same-ESP temp sensor %s reading too stale (age=%.0fs >= %.0fs), skipping",
                    log_prefix,
                    temp_type,
                    age.total_seconds(),
                    self._ATC_MAX_AGE.total_seconds(),
                )
                continue
            if age < self._ATC_FRESH_AGE:
                # Fresh reading from same-ESP discovery
                return (float(reading.processed_value), "same_esp")
            # FRESH_AGE ≤ age < MAX_AGE: stale but usable
            logger.debug(
                "[%s] Same-ESP temp sensor %s (%.2f°C, age=%.0fs, cached_temp) for ATC",
                log_prefix,
                temp_type,
                float(reading.processed_value),
                age.total_seconds(),
            )
            return (float(reading.processed_value), "cached_temp")

        # No temperature sensor configured or discoverable — 25 °C reference is correct
        return (None, "default_25c")

    async def _emit_atc_degraded_warning(
        self,
        esp_id_str: str,
        gpio: int,
        sensor_type: str,
        session,
    ) -> None:
        """Emit WS warning event and write audit log when the explicitly linked ATC sensor
        has gone dark (age >= _ATC_MAX_AGE).  Measurement continues with 25 °C fallback.
        Only fired for the real degradation case (AUT-672/Edit-5):
          - temp_sensor_config_id configured AND reading expired beyond MAX_AGE.
        NOT fired for: Setup (reading is None), auto-discovery, or no sensor configured.

        Args:
            esp_id_str: ESP device ID string
            gpio: GPIO pin number of the pH/EC sensor
            sensor_type: "ph" or "ec"
            session: Active async database session (for audit log write)
        """
        warning_message = (
            f"ATC sensor degraded for {sensor_type.upper()} sensor on "
            f"{esp_id_str} GPIO {gpio} — measuring with 25 °C reference temperature"
        )

        # Audit log (pattern from error_handler.py / heartbeat_handler.py)
        try:
            from ...db.repositories.audit_log_repo import AuditLogRepository
            from ...db.models.audit_log import AuditEventType, AuditSeverity

            audit_repo = AuditLogRepository(session)
            await audit_repo.log_device_event(
                esp_id=esp_id_str,
                event_type=AuditEventType.MQTT_ERROR,
                status="degraded",
                message=warning_message,
                severity=AuditSeverity.WARNING,
                details={
                    "gpio": gpio,
                    "sensor_type": sensor_type,
                    "atc_source": "default_25c",
                    "action": "measurement_continued_with_fallback",
                },
            )
        except Exception as audit_err:
            logger.warning(
                "[%s-ATC] Failed to write audit log for degraded warning: %s",
                sensor_type.upper(),
                audit_err,
            )

        # WebSocket error_event broadcast (best-effort, pattern from handle_sensor_data)
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "error_event",
                {
                    "esp_id": esp_id_str,
                    "message": warning_message,
                    "severity": "warning",
                    "device_id": esp_id_str,
                    "gpio": gpio,
                    "sensor_type": sensor_type,
                    "error_type": "atc_degraded",
                    "atc_source": "default_25c",
                },
            )
        except Exception as ws_err:
            logger.warning(
                "[%s-ATC] Failed to broadcast degraded warning via WebSocket: %s",
                sensor_type.upper(),
                ws_err,
            )

    async def _try_get_ec_temperature(
        self,
        esp_device,
        session,
        sensor_config=None,
    ) -> tuple[Optional[float], str]:
        """Backward-compatible shim: delegates to _try_get_atc_temperature for EC sensors.

        Kept for call-site compatibility (AUT-299). New callers should use
        _try_get_atc_temperature() directly with an explicit log_prefix.
        """
        return await self._try_get_atc_temperature(
            esp_device=esp_device,
            session=session,
            sensor_config=sensor_config,
            log_prefix="EC-ATC",
        )

    # ─── Threshold Evaluation ─────────────────────────────────────

    async def _evaluate_thresholds_and_notify(
        self,
        session,
        sensor_config,
        esp_id_str: str,
        gpio: int,
        sensor_type: str,
        value: float,
    ) -> None:
        """
        Evaluate sensor value against thresholds and route notification.

        Pipeline:
        1. Get effective thresholds (custom from alert_config > global from sensor_config)
        2. Check value against thresholds → determine severity
        3. Check suppression status (sensor-level + device-level)
        4. Route notification via NotificationRouter (unless suppressed)
        5. Alert is always logged (even when suppressed)
        """
        from ...services.alert_suppression_service import AlertSuppressionService
        from ...services.notification_router import NotificationRouter
        from ...schemas.notification import NotificationCreate

        suppression_svc = AlertSuppressionService(session)

        # Step 1: Get effective thresholds
        thresholds = suppression_svc.get_effective_thresholds(sensor_config)

        # Step 1b: Enrich with zone-aware thresholds (Phase 5)
        try:
            from ...services.zone_aware_thresholds import ZoneAwareThresholdService
            from ...db.models.esp import ESPDevice

            esp_device = await session.get(ESPDevice, sensor_config.esp_id)
            zone_id = esp_device.zone_id if esp_device else None
            if zone_id:
                zone_thresh_svc = ZoneAwareThresholdService(session)
                phase_thresholds = await zone_thresh_svc.get_thresholds(zone_id, sensor_type)
                if phase_thresholds:
                    if not thresholds:
                        thresholds = phase_thresholds
                    else:
                        for k, v in phase_thresholds.items():
                            if k not in thresholds:
                                thresholds[k] = v
        except Exception as e:
            logger.debug(f"Zone-aware threshold enrichment skipped: {e}")

        if not thresholds:
            return  # No thresholds configured — nothing to evaluate

        # Step 2: Check value against thresholds
        severity = suppression_svc.check_thresholds(value, thresholds)
        if not severity:
            return  # Value within bounds — no alert

        # Apply severity override if configured
        override = suppression_svc.get_severity_override(sensor_config)
        if override:
            severity = override

        # Step 3: Check suppression
        is_suppressed, suppression_reason = await suppression_svc.is_sensor_suppressed(
            sensor_config
        )

        # Step 4: Build notification payload
        sensor_name = sensor_config.sensor_name or f"{sensor_type} GPIO {gpio}"
        unit = (
            sensor_config.sensor_metadata.get("latest_unit", "")
            if sensor_config.sensor_metadata
            else ""
        )

        # Compute measurement age for mode-context enrichment
        measurement_age_seconds = None
        effective_operating_mode = sensor_config.operating_mode or "continuous"
        if sensor_config.sensor_metadata and isinstance(sensor_config.sensor_metadata, dict):
            latest_ts = sensor_config.sensor_metadata.get("latest_timestamp")
            if latest_ts:
                try:
                    from datetime import datetime as _dt, timezone as _tz

                    if isinstance(latest_ts, str):
                        ts_dt = _dt.fromisoformat(latest_ts.replace("Z", "+00:00"))
                    elif isinstance(latest_ts, (int, float)):
                        ts_dt = _dt.fromtimestamp(latest_ts, tz=_tz.utc)
                    else:
                        ts_dt = None
                    if ts_dt:
                        if ts_dt.tzinfo is None:
                            ts_dt = ts_dt.replace(tzinfo=_tz.utc)
                        measurement_age_seconds = int((_dt.now(_tz.utc) - ts_dt).total_seconds())
                except (ValueError, TypeError, OSError):
                    pass

        alert_metadata = {
            "esp_id": esp_id_str,
            "gpio": gpio,
            "sensor_type": sensor_type,
            "sensor_config_id": str(sensor_config.id),
            "value": value,
            "severity": severity,
            "thresholds": thresholds,
            "operating_mode": effective_operating_mode,
            "measurement_age_seconds": measurement_age_seconds,
        }

        # Phase 4B: Correlation ID for grouping related threshold alerts
        threshold_correlation_id = f"threshold_{esp_id_str}_{sensor_type}"

        if is_suppressed:
            # ISA-18.2 Audit-Trail: ALWAYS persist alert to DB, even when suppressed.
            # Uses NotificationRouter.persist_suppressed() for pattern-conformity
            # (Service → Repository, no direct repo access from handler).
            try:
                alert_metadata["suppressed"] = True
                alert_metadata["suppression_reason"] = suppression_reason
                suppressed_notification = NotificationCreate(
                    severity=severity,
                    category="data_quality",
                    title=f"[Suppressed] Schwellenwert-Alarm: {sensor_name}",
                    body=(
                        f"Sensor '{sensor_name}' ({sensor_type}) auf {esp_id_str} GPIO {gpio} "
                        f"hat Wert {value}{unit} — {severity}-Schwellenwert überschritten. "
                        f"(Suppressed: {suppression_reason})"
                    ),
                    source="sensor_threshold",
                    metadata=alert_metadata,
                    correlation_id=threshold_correlation_id,
                )
                router = NotificationRouter(session)
                await router.persist_suppressed(suppressed_notification)
                await session.commit()
                logger.debug(
                    f"Suppressed alert persisted (audit-trail): {esp_id_str} GPIO {gpio}, "
                    f"severity={severity}, reason={suppression_reason}"
                )
            except Exception as e:
                logger.warning(f"Failed to persist suppressed alert: {e}")
            return  # Suppressed — persisted but not routed (no WS, no email)

        # Step 5: Route notification (unsuppressed → full pipeline)
        notification = NotificationCreate(
            severity=severity,
            category="data_quality",
            title=f"Schwellenwert-Alarm: {sensor_name}",
            body=(
                f"Sensor '{sensor_name}' ({sensor_type}) auf {esp_id_str} GPIO {gpio} "
                f"hat Wert {value}{unit} — {severity}-Schwellenwert überschritten."
            ),
            source="sensor_threshold",
            metadata=alert_metadata,
            correlation_id=threshold_correlation_id,
        )

        try:
            router = NotificationRouter(session)
            await router.route(notification)
            logger.info(
                f"Threshold alert routed: {esp_id_str} GPIO {gpio}, "
                f"severity={severity}, value={value}"
            )
        except Exception as e:
            logger.error(f"Failed to route threshold notification: {e}")

    async def _update_last_seen_throttled(self, esp_id: str, esp_repo: ESPRepository) -> None:
        """
        Update ESP last_seen as secondary health indicator (throttled).

        Only updates DB at most once per LAST_SEEN_THROTTLE_SECONDS per ESP.
        Does NOT change device status — that remains the heartbeat_handler's job.
        Ensures check_device_timeouts() won't mark an ESP as offline while
        sensor data is still flowing.
        """
        now = datetime.now(timezone.utc)
        last_update = self._last_seen_cache.get(esp_id)
        if last_update and (now - last_update).total_seconds() < self.LAST_SEEN_THROTTLE_SECONDS:
            return  # Throttled — skip

        self._last_seen_cache[esp_id] = now
        try:
            await esp_repo.update_last_seen(esp_id, now)
        except Exception as e:
            logger.debug(f"Failed to update last_seen for {esp_id}: {e}")

    @classmethod
    def _check_physical_range(cls, sensor_type: str, value: float) -> str | None:
        """
        Check if a sensor value is within physical datasheet limits.

        Args:
            sensor_type: Sensor type identifier (e.g. "sht31", "ds18b20")
            value: Processed or raw sensor value in physical units

        Returns:
            "implausible" if value is outside physical limits, None otherwise
        """
        limits = cls.SENSOR_PHYSICAL_LIMITS.get(sensor_type)
        if limits is not None and (value < limits["min"] or value > limits["max"]):
            return "implausible"
        return None

    def _validate_payload(self, payload: dict) -> dict:
        """
        Validate sensor data payload structure.

        Required fields: ts OR timestamp, esp_id, gpio, sensor_type, raw OR raw_value
        Optional fields: raw_mode (defaults to True)

        Args:
            payload: Payload dict to validate

        Returns:
            {"valid": bool, "error": str, "error_code": int}
        """
        # Check required fields (with alternatives for compatibility)
        # Accept both "ts" and "timestamp"
        if "ts" not in payload and "timestamp" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: ts or timestamp",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        if "esp_id" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: esp_id",
                "error_code": ValidationErrorCode.INVALID_ESP_ID,
            }

        if "gpio" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: gpio",
                "error_code": ValidationErrorCode.INVALID_GPIO,
            }

        if "sensor_type" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: sensor_type",
                "error_code": ValidationErrorCode.INVALID_SENSOR_TYPE,
            }

        # Accept both "raw" and "raw_value"
        if "raw" not in payload and "raw_value" not in payload:
            return {
                "valid": False,
                "error": "Missing required field: raw or raw_value",
                "error_code": ValidationErrorCode.MISSING_REQUIRED_FIELD,
            }

        # raw_mode is optional (defaults to True if not provided)
        if "raw_mode" not in payload:
            payload["raw_mode"] = True

        # Type validation
        ts_value = payload.get("ts", payload.get("timestamp"))
        if not isinstance(ts_value, (int, float)):
            return {
                "valid": False,
                "error": "Field 'ts/timestamp' must be numeric (Unix timestamp)",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # BUG-05 fix: ts<=0 is valid (Wokwi without NTP) — server will use its own timestamp
        # Log warning but do NOT reject the payload
        if ts_value <= 0:
            logger.warning(
                "Payload ts<=0 (value=%s) from esp_id=%s — will use server timestamp",
                ts_value,
                payload.get("esp_id", "unknown"),
            )

        if not isinstance(payload["gpio"], int):
            return {
                "valid": False,
                "error": "Field 'gpio' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # raw_mode validation (must be boolean if provided)
        if not isinstance(payload["raw_mode"], bool):
            return {
                "valid": False,
                "error": "Field 'raw_mode' must be boolean",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate raw value (should be numeric)
        raw_value = payload.get("raw", payload.get("raw_value"))
        try:
            float(raw_value)
        except (ValueError, TypeError):
            return {
                "valid": False,
                "error": "Field 'raw/raw_value' must be numeric",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate quality field (optional, but must be valid if present)
        quality = payload.get("quality")
        if quality is not None:
            if quality not in QUALITY_LEVELS:
                return {
                    "valid": False,
                    "error": (
                        f"Invalid quality value: '{quality}'. "
                        f"Must be one of {list(QUALITY_LEVELS)}"
                    ),
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            # If ESP reports quality as "error", log a warning
            if quality == "error":
                logger.warning(
                    f"ESP reported quality='error' for sensor data: "
                    f"esp_id={payload.get('esp_id')}, gpio={payload.get('gpio')}, "
                    f"sensor_type={payload.get('sensor_type')}"
                )

        # Validate error_code field (optional, ESP reports sensor-specific errors)
        error_code = payload.get("error_code")
        if error_code is not None:
            if not isinstance(error_code, int):
                return {
                    "valid": False,
                    "error": "Field 'error_code' must be integer",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

            # Log any non-zero error codes from ESP
            if error_code != 0:
                logger.warning(
                    f"ESP reported error_code={error_code} for sensor: "
                    f"esp_id={payload.get('esp_id')}, gpio={payload.get('gpio')}"
                )

        if payload.get("sample_count") is not None and not isinstance(payload["sample_count"], int):
            return {
                "valid": False,
                "error": "Field 'sample_count' must be integer",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        if payload.get("adc_stddev") is not None:
            try:
                float(payload["adc_stddev"])
            except (ValueError, TypeError):
                return {
                    "valid": False,
                    "error": "Field 'adc_stddev' must be numeric",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

        if payload.get("stable") is not None and not isinstance(payload["stable"], bool):
            return {
                "valid": False,
                "error": "Field 'stable' must be boolean",
                "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
            }

        # Validate i2c_address field (optional, for I2C sensor identification)
        i2c_address = payload.get("i2c_address")
        if i2c_address is not None:
            if not isinstance(i2c_address, int):
                return {
                    "valid": False,
                    "error": "Field 'i2c_address' must be integer",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }
            # I2C 7-bit address range: 0x00-0x7F (0-127)
            if i2c_address < 0 or i2c_address > 127:
                return {
                    "valid": False,
                    "error": f"Field 'i2c_address' must be 0-127, got {i2c_address}",
                    "error_code": ValidationErrorCode.FIELD_TYPE_MISMATCH,
                }

        return {"valid": True, "error": "", "error_code": ValidationErrorCode.NONE}

    def _detect_data_source(self, esp_device, payload: dict) -> str:
        """
        Detect the data source based on device and payload.

        Detection priority:
        1. Explicit _test_mode flag in payload → TEST
        2. Explicit _source field in payload → use value
        3. Device hardware_type == "MOCK_ESP32" → MOCK
        4. Device capabilities.mock == True → MOCK
        5. ESP ID starts with "MOCK_" → MOCK
        6. ESP ID starts with "TEST_" → TEST
        7. ESP ID starts with "SIM_" → SIMULATION
        8. Default → PRODUCTION

        Args:
            esp_device: ESPDevice instance
            payload: MQTT payload dict

        Returns:
            Data source string value
        """
        esp_id = payload.get("esp_id", getattr(esp_device, "device_id", "unknown"))
        detection_reason = None

        # Priority 1: Explicit test mode flag
        if payload.get("_test_mode"):
            detection_reason = "payload._test_mode=True"
            result = DataSource.TEST.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Priority 2: Explicit source field
        if "_source" in payload:
            source_value = payload["_source"].lower()
            try:
                result = DataSource(source_value).value
                detection_reason = f"payload._source='{source_value}'"
                logger.debug(
                    f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})"
                )
                return result
            except ValueError:
                logger.warning(f"Unknown data source: {source_value}, defaulting to production")
                return DataSource.PRODUCTION.value

        # Priority 3: Device hardware_type
        if hasattr(esp_device, "hardware_type") and esp_device.hardware_type == "MOCK_ESP32":
            detection_reason = "esp_device.hardware_type='MOCK_ESP32'"
            result = DataSource.MOCK.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Priority 4: Device capabilities flag
        if hasattr(esp_device, "capabilities") and esp_device.capabilities:
            if esp_device.capabilities.get("mock"):
                detection_reason = "esp_device.capabilities.mock=True"
                result = DataSource.MOCK.value
                logger.debug(
                    f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})"
                )
                return result

        # Priority 5-7: ESP ID prefix detection
        if esp_id.startswith("MOCK_"):
            detection_reason = f"esp_id prefix 'MOCK_'"
            result = DataSource.MOCK.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result
        if esp_id.startswith("TEST_"):
            detection_reason = f"esp_id prefix 'TEST_'"
            result = DataSource.TEST.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result
        if esp_id.startswith("SIM_"):
            detection_reason = f"esp_id prefix 'SIM_'"
            result = DataSource.SIMULATION.value
            logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
            return result

        # Default
        detection_reason = "default (no matching criteria)"
        result = DataSource.PRODUCTION.value
        logger.debug(f"DataSource detection [{esp_id}]: {result} (reason: {detection_reason})")
        return result

    async def _trigger_pi_enhanced_processing(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        raw_value: float,
        sensor_config,
        raw_mode: bool = True,
        extra_params: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Trigger Pi-Enhanced sensor processing.

        Uses library_loader to dynamically load sensor library
        and process raw value.

        Args:
            esp_id: ESP device ID string
            gpio: GPIO pin number
            sensor_type: Sensor type (ph, temperature, etc.)
            raw_value: Raw sensor value
            sensor_config: SensorConfig instance with processing params
            raw_mode: Whether ESP sent RAW value (True) or pre-converted (False)
                     For DS18B20: raw_mode=True means 12-bit integer (400 = 25°C)

        Returns:
            {
                "processed_value": float,
                "unit": str,
                "quality": str
            }
            or None if processing failed
        """
        try:
            from ...sensors.library_loader import get_library_loader
            from ...sensors.sensor_type_registry import normalize_sensor_type

            # Get library loader instance
            loader = get_library_loader()

            # Normalize sensor type (ESP32 → Server Processor)
            normalized_type = normalize_sensor_type(sensor_type)

            # DEBUG: Enhanced logging for sensor processing flow
            logger.info(
                f"[Pi-Enhanced] Processing: esp_id={esp_id}, gpio={gpio}, "
                f"sensor_type='{sensor_type}' → normalized='{normalized_type}'"
            )

            # Get processor for sensor type (normalization happens in get_processor too)
            processor = loader.get_processor(sensor_type)

            # DEBUG: Log processor selection result
            if processor:
                logger.info(
                    f"[Pi-Enhanced] Processor found: {type(processor).__name__} "
                    f"for '{normalized_type}'"
                )
            else:
                logger.error(
                    f"[Pi-Enhanced] No processor found for sensor type: '{sensor_type}'. "
                    f"Normalized: '{normalized_type}'. "
                    f"Available processors: {loader.get_available_sensors()}"
                )
                return None

            # Process raw value using sensor library
            # Extract processing params from metadata if available
            processing_params = {}
            if sensor_config and sensor_config.sensor_metadata:
                processing_params = sensor_config.sensor_metadata.get("processing_params") or {}

            # Always pass raw_mode to processor (Pi-Enhanced mode indicator)
            # For DS18B20: raw_mode=True means ESP sent 12-bit integer (400 = 25°C)
            processing_params["raw_mode"] = raw_mode

            # Merge caller-supplied extra params (e.g. ATC temperature_compensation for EC).
            # Strip internal transport keys (prefixed with "_") before passing to processor.
            if extra_params:
                processor_params = {k: v for k, v in extra_params.items() if not k.startswith("_")}
                processing_params.update(processor_params)

            proc_calibration = None
            if sensor_config and sensor_config.calibration_data:
                proc_calibration = resolve_calibration_for_processor(sensor_config.calibration_data)

            # AUT-948 B1+B4: sensor_configs.adc_source is the SSOT for current
            # hardware routing. calibration_data.derived carries provenance only
            # (what ADC was active at calibration time). Inject the DB column so
            # resolve_adc_descriptor() in ph_sensor/ec_sensor uses the correct
            # RAW->voltage formula regardless of when calibration was performed.
            if sensor_config:
                if proc_calibration is None:
                    proc_calibration = {}
                db_src = sensor_config.adc_source  # NOT NULL, "internal"|"ads1115"
                cal_src = proc_calibration.get("adc_source", ADC_SOURCE_INTERNAL)
                if cal_src != db_src:
                    logger.warning(
                        "[AUT-948] adc_source mismatch esp_id=%s gpio=%d: "
                        "calibration_data.derived=%r vs sensor_configs=%r "
                        "— using column SSOT; recalibration recommended",
                        esp_id,
                        gpio,
                        cal_src,
                        db_src,
                    )
                proc_calibration["adc_source"] = db_src
                if db_src == ADC_SOURCE_ADS1115 and sensor_config.pga_gain is not None:
                    proc_calibration["pga_gain"] = sensor_config.pga_gain

            result = processor.process(
                raw_value=raw_value,
                calibration=proc_calibration,
                params=processing_params,
            )

            # DEBUG: Enhanced result logging
            logger.info(
                f"[Pi-Enhanced] SUCCESS: esp_id={esp_id}, gpio={gpio}, "
                f"sensor_type='{sensor_type}' → raw={raw_value} → "
                f"processed={result.value} {result.unit}, quality={result.quality}"
            )

            return {
                "processed_value": result.value,
                "unit": result.unit,
                "quality": result.quality,
                "metadata": result.metadata,
            }

        except Exception as e:
            logger.error(
                f"Pi-Enhanced processing failed: sensor_type={sensor_type}, " f"error={e}",
                exc_info=True,
            )
            return None


# Global handler instance
_handler_instance: Optional[SensorDataHandler] = None


def get_sensor_handler() -> SensorDataHandler:
    """
    Get singleton sensor data handler instance.

    Returns:
        SensorDataHandler instance
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = SensorDataHandler()
    return _handler_instance


async def handle_sensor_data(topic: str, payload: dict) -> bool:
    """
    Handle sensor data message (convenience function).

    Args:
        topic: MQTT topic string
        payload: Parsed JSON payload dict

    Returns:
        True if message processed successfully
    """
    handler = get_sensor_handler()
    return await handler.handle_sensor_data(topic, payload)
