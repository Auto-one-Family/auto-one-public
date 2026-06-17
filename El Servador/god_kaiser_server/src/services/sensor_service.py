"""
Sensor Service - Business Logic for Sensor Operations

Phase: 5 (Week 9-10) - API Layer
Priority: 🟡 HIGH
Status: IMPLEMENTED

Provides:
- Sensor configuration CRUD
- Sensor data processing
- Data query with aggregation
- Calibration management

This service provides shared business logic used by both:
- REST API endpoints (api/v1/sensors.py)
- MQTT handlers (mqtt/handlers/sensor_handler.py)

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 135-145)
"""

import uuid
from math import ceil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.exceptions import MeasurementBusyError
from ..core.logging_config import get_logger
from .calibration_payloads import resolve_calibration_for_processor
from ..db.models.sensor import SensorConfig, SensorData
from ..db.repositories import ESPRepository, SensorRepository
from ..db.repositories.command_contract_repo import CommandContractRepository
from ..mqtt.publisher import Publisher
from ..sensors.library_loader import LibraryLoader as SensorLibraryLoader

logger = get_logger(__name__)

# Cooldown window (seconds) for on-demand measurement busy-guard (AUT-302).
# A second /measure call within this window for the same (esp_id, gpio) is
# rejected with HTTP 429 to prevent MQTT burst → ESP publish-queue overflow.
# Tuned for fast manual probing: allow one request every ~2 seconds.
_MEASURE_COOLDOWN_SECONDS: float = 2.0
# Module-level dict so the cooldown survives across FastAPI request-scoped SensorService instances.
_measure_cooldown: Dict[tuple[str, int], float] = {}


class SensorService:
    """
    Sensor business logic service.

    Handles sensor configuration, data processing, and queries.
    """

    def __init__(
        self,
        sensor_repo: SensorRepository,
        esp_repo: ESPRepository,
        publisher: Optional[Publisher] = None,
        library_loader: Optional[SensorLibraryLoader] = None,
    ):
        """
        Initialize SensorService.

        Args:
            sensor_repo: Sensor repository
            esp_repo: ESP repository
            publisher: MQTT publisher for sensor commands (optional)
            library_loader: Sensor library loader (optional, created if not provided)
        """
        self.sensor_repo = sensor_repo
        self.esp_repo = esp_repo
        self.publisher = publisher or Publisher()
        self.library_loader = library_loader or SensorLibraryLoader()

    # =========================================================================
    # Configuration Management
    # =========================================================================

    async def get_config(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str | None = None,
    ) -> Optional[SensorConfig]:
        """
        Get sensor configuration.

        Args:
            esp_id: ESP device ID (ESP_XXXXXXXX format)
            gpio: GPIO pin number
            sensor_type: Sensor type for multi-value disambiguation (e.g. 'sht31_temp').
                         When omitted, returns first config on this GPIO.

        Returns:
            SensorConfig or None if not found
        """
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            return None

        if sensor_type:
            return await self.sensor_repo.get_by_esp_gpio_and_type(esp_device.id, gpio, sensor_type)

        # Legacy fallback: returns first config (may be wrong for multi-value)
        configs = await self.sensor_repo.get_all_by_esp_and_gpio(esp_device.id, gpio)
        if len(configs) > 1:
            logger.warning(
                "get_config without sensor_type for multi-value GPIO: "
                "esp=%s gpio=%s (%d configs). Returning first.",
                esp_id,
                gpio,
                len(configs),
            )
        return configs[0] if configs else None

    async def create_or_update_config(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        name: Optional[str] = None,
        enabled: bool = True,
        interval_ms: int = 30000,
        processing_mode: str = "pi_enhanced",
        calibration: Optional[Dict[str, Any]] = None,
        threshold_min: Optional[float] = None,
        threshold_max: Optional[float] = None,
        warning_min: Optional[float] = None,
        warning_max: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        onewire_address: Optional[str] = None,
        i2c_address: Optional[int] = None,
    ) -> SensorConfig:
        """
        Create or update sensor configuration.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            sensor_type: Sensor type (ph, temperature, etc.)
            name: Human-readable name
            enabled: Whether sensor is enabled
            interval_ms: Reading interval in milliseconds
            processing_mode: Processing mode (pi_enhanced, local, raw)
            calibration: Calibration data
            threshold_min: Minimum value threshold
            threshold_max: Maximum value threshold
            warning_min: Warning threshold (low)
            warning_max: Warning threshold (high)
            metadata: Custom metadata

        Returns:
            Created or updated SensorConfig
        """
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            raise ValueError(f"ESP device '{esp_id}' not found")

        # Address-aware lookup: use specific repo method when address is provided
        # to correctly distinguish multiple sensors on the same GPIO (R20-P1 fix)
        if onewire_address is not None:
            existing = await self.sensor_repo.get_by_esp_gpio_type_and_onewire(
                esp_device.id, gpio, sensor_type, onewire_address
            )
        elif i2c_address is not None:
            existing = await self.sensor_repo.get_by_esp_gpio_type_and_i2c(
                esp_device.id, gpio, sensor_type, i2c_address
            )
        else:
            existing = await self.sensor_repo.get_by_esp_gpio_and_type(
                esp_device.id, gpio, sensor_type
            )

        if existing:
            # Update existing
            existing.sensor_type = sensor_type
            existing.name = name
            existing.enabled = enabled
            existing.interval_ms = interval_ms
            existing.processing_mode = processing_mode
            existing.calibration = calibration or existing.calibration
            existing.threshold_min = threshold_min
            existing.threshold_max = threshold_max
            existing.warning_min = warning_min
            existing.warning_max = warning_max
            existing.metadata = metadata or existing.metadata
            if onewire_address is not None:
                existing.onewire_address = onewire_address
            if i2c_address is not None:
                existing.i2c_address = i2c_address

            logger.info(f"Sensor config updated: {esp_id} GPIO {gpio}")
            return existing
        else:
            # Create new
            sensor = SensorConfig(
                esp_id=esp_device.id,
                gpio=gpio,
                sensor_type=sensor_type,
                name=name,
                enabled=enabled,
                interval_ms=interval_ms,
                processing_mode=processing_mode,
                calibration=calibration or {},
                threshold_min=threshold_min,
                threshold_max=threshold_max,
                warning_min=warning_min,
                warning_max=warning_max,
                onewire_address=onewire_address,
                i2c_address=i2c_address,
                metadata=metadata or {},
            )
            await self.sensor_repo.create(sensor)

            logger.info(f"Sensor config created: {esp_id} GPIO {gpio} type={sensor_type}")
            return sensor

    async def delete_config(
        self,
        esp_id: str,
        gpio: int | None = None,
        config_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Delete sensor configuration.

        Supports lookup by config_id (preferred, T08-Fix-D) or by gpio (legacy).

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number (legacy, may fail for multi-value sensors)
            config_id: SensorConfig UUID primary key (preferred)

        Returns:
            True if deleted, False if not found
        """

        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            return False

        if config_id is not None:
            sensor = await self.sensor_repo.get_by_id(config_id)
            if not sensor or sensor.esp_id != esp_device.id:
                return False
        elif gpio is not None:
            sensor = await self.sensor_repo.get_by_esp_and_gpio(esp_device.id, gpio)
            if not sensor:
                return False
        else:
            return False

        await self.sensor_repo.delete(sensor.id)
        logger.info(f"Sensor config deleted: {esp_id} config_id={sensor.id}")
        return True

    # =========================================================================
    # Data Processing
    # =========================================================================

    async def process_reading(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process a sensor reading using Pi-Enhanced processing.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin
            sensor_type: Sensor type
            raw_value: Raw ADC value (0-4095)
            calibration: Calibration data (or use stored)
            params: Processing parameters
            timestamp: Unix timestamp

        Returns:
            Processed result dictionary
        """
        # Get stored config if calibration not provided
        if calibration is None:
            config = await self.get_config(esp_id, gpio)
            if config and config.calibration_data:
                calibration = resolve_calibration_for_processor(config.calibration_data)

        # Get processor from library
        processor = self.library_loader.get_processor(sensor_type)
        if not processor:
            logger.warning(f"No processor found for sensor type: {sensor_type}")
            return {
                "success": False,
                "error": f"No processor for sensor type: {sensor_type}",
                "raw_value": raw_value,
            }

        # Process the reading
        try:
            result = processor.process(
                raw_value=raw_value,
                calibration=calibration or {},
                params=params or {},
            )

            # Store the processed reading
            await self._store_reading(
                esp_id=esp_id,
                gpio=gpio,
                sensor_type=sensor_type,
                raw_value=raw_value,
                processed_value=result.get("value"),
                unit=result.get("unit"),
                quality=result.get("quality", "good"),
                timestamp=timestamp,
            )

            return {
                "success": True,
                "processed_value": result.get("value"),
                "unit": result.get("unit"),
                "quality": result.get("quality", "good"),
                "metadata": result.get("metadata", {}),
            }

        except Exception as e:
            logger.error(f"Processing failed for {sensor_type}: {e}")
            return {
                "success": False,
                "error": str(e),
                "raw_value": raw_value,
            }

    async def _store_reading(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        raw_value: float,
        processed_value: Optional[float],
        unit: Optional[str],
        quality: str,
        timestamp: Optional[int] = None,
    ) -> None:
        """Store sensor reading in database."""
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            logger.warning(f"Cannot store reading: ESP {esp_id} not found")
            return

        reading = SensorData(
            esp_id=esp_device.id,
            gpio=gpio,
            sensor_type=sensor_type,
            raw_value=raw_value,
            processed_value=processed_value,
            unit=unit,
            quality=quality,
            timestamp=(
                datetime.fromtimestamp(timestamp, tz=timezone.utc)
                if timestamp
                else datetime.now(timezone.utc)
            ),
            zone_id=esp_device.zone_id,
            device_name=esp_device.name,
        )

        await self.sensor_repo.store_reading(reading)

    # =========================================================================
    # Data Queries
    # =========================================================================

    async def query_data(
        self,
        esp_id: Optional[str] = None,
        gpio: Optional[int] = None,
        sensor_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        quality: Optional[str] = None,
        limit: int = 100,
    ) -> List[SensorData]:
        """
        Query sensor data with filters.

        Args:
            esp_id: Filter by ESP device ID
            gpio: Filter by GPIO
            sensor_type: Filter by sensor type
            start_time: Start of time range
            end_time: End of time range
            quality: Filter by quality level
            limit: Max results

        Returns:
            List of SensorData readings
        """
        esp_db_id = None
        if esp_id:
            esp_device = await self.esp_repo.get_by_device_id(esp_id)
            if esp_device:
                esp_db_id = esp_device.id

        return await self.sensor_repo.query_data(
            esp_id=esp_db_id,
            gpio=gpio,
            sensor_type=sensor_type,
            start_time=start_time,
            end_time=end_time,
            quality=quality,
            limit=limit,
        )

    async def get_latest_reading(
        self,
        esp_id: str,
        gpio: int,
    ) -> Optional[SensorData]:
        """
        Get latest reading for a sensor.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin

        Returns:
            Latest SensorData or None
        """
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            return None

        return await self.sensor_repo.get_latest_reading(esp_device.id, gpio)

    async def get_stats(
        self,
        esp_id: str,
        gpio: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get statistical summary for sensor data.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Statistics dictionary
        """
        esp_device = await self.esp_repo.get_by_device_id(esp_id)
        if not esp_device:
            return {"error": "ESP not found"}

        return await self.sensor_repo.get_stats(
            esp_id=esp_device.id,
            gpio=gpio,
            start_time=start_time,
            end_time=end_time,
        )

    # =========================================================================
    # Calibration
    # =========================================================================

    async def calibrate(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        calibration_points: List[Dict[str, float]],
        method: str = "linear",
        save_to_config: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculate calibration from reference points.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin
            sensor_type: Sensor type
            calibration_points: List of {raw, reference} points
            method: Calibration method (linear, offset, polynomial)
            save_to_config: Save to database config

        Returns:
            Calibration result
        """
        if len(calibration_points) < 1:
            return {"success": False, "error": "At least 1 calibration point required"}

        # Calculate calibration based on method
        if method == "offset" and len(calibration_points) >= 1:
            # Simple offset calibration
            point = calibration_points[0]
            offset = point["reference"] - point["raw"]
            calibration = {"offset": offset}

        elif method == "linear" and len(calibration_points) >= 2:
            # Linear calibration (y = mx + b)
            p1, p2 = calibration_points[0], calibration_points[1]
            slope = (p2["reference"] - p1["reference"]) / (p2["raw"] - p1["raw"])
            offset = p1["reference"] - slope * p1["raw"]
            calibration = {"slope": slope, "offset": offset}

        elif method == "polynomial" and len(calibration_points) >= 3:
            # Would need numpy for polynomial fitting
            # Fallback to linear
            p1, p2 = calibration_points[0], calibration_points[-1]
            slope = (p2["reference"] - p1["reference"]) / (p2["raw"] - p1["raw"])
            offset = p1["reference"] - slope * p1["raw"]
            calibration = {"slope": slope, "offset": offset}
        else:
            # Default to offset
            point = calibration_points[0]
            offset = point["reference"] - point["raw"]
            calibration = {"offset": offset}

        # Save to config if requested
        saved = False
        if save_to_config:
            config = await self.get_config(esp_id, gpio)
            if config:
                config.calibration = calibration
                saved = True
                logger.info(f"Calibration saved for {esp_id} GPIO {gpio}: {calibration}")

        return {
            "success": True,
            "calibration": calibration,
            "sensor_type": sensor_type,
            "method": method,
            "saved": saved,
        }

    # =========================================================================
    # On-Demand Measurement (Phase 2D)
    # =========================================================================

    async def trigger_measurement(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str | None = None,
        sample_count: int | None = None,
        sample_delay_ms: int | None = None,
        timeout_ms: int | None = None,
    ) -> Dict[str, Any]:
        """
        Trigger a manual measurement for a sensor.

        Used for on_demand operating mode sensors.

        Args:
            esp_id: ESP device ID (e.g., "ESP_12AB34CD")
            gpio: Sensor GPIO pin
            sensor_type: Sensor type for multi-value disambiguation

        Returns:
            dict with success status and request_id

        Raises:
            ValueError: If ESP or sensor not found, or sensor disabled
            RuntimeError: If ESP is offline or MQTT publish fails
        """
        # 1. Validate ESP exists and is online
        esp = await self.esp_repo.get_by_device_id(esp_id)

        if not esp:
            raise ValueError(f"ESP device not found: {esp_id}")

        if esp.status != "online":
            raise RuntimeError(f"ESP device is offline: {esp_id} (status: {esp.status})")

        # 2. Validate sensor exists and is enabled
        if sensor_type:
            sensor = await self.sensor_repo.get_by_esp_gpio_and_type(esp.id, gpio, sensor_type)
        else:
            configs = await self.sensor_repo.get_all_by_esp_and_gpio(esp.id, gpio)
            if len(configs) > 1:
                logger.warning(
                    "trigger_measurement without sensor_type for multi-value GPIO: "
                    "esp=%s gpio=%s (%d configs). Returning first.",
                    esp_id,
                    gpio,
                    len(configs),
                )
            sensor = configs[0] if configs else None

        if not sensor:
            raise ValueError(f"Sensor not found: {esp_id}/GPIO {gpio}")

        if not sensor.enabled:
            raise ValueError(f"Sensor is disabled: {esp_id}/GPIO {gpio}")

        resolved_sensor_type = sensor.sensor_type
        command_params: dict[str, int] = {}
        if resolved_sensor_type in ("ec", "ph"):
            command_params["sample_count"] = sample_count if sample_count is not None else 30
            command_params["sample_delay_ms"] = sample_delay_ms if sample_delay_ms is not None else 100
            command_params["timeout_ms"] = timeout_ms if timeout_ms is not None else 15000
        else:
            if sample_count is not None:
                command_params["sample_count"] = sample_count
            if sample_delay_ms is not None:
                command_params["sample_delay_ms"] = sample_delay_ms
            if timeout_ms is not None:
                command_params["timeout_ms"] = timeout_ms

        # 3. Busy-guard: reject rapid-fire duplicates within the cooldown window
        cooldown_key = (esp_id, gpio)
        now_ts = datetime.now(timezone.utc).timestamp()
        last_triggered = _measure_cooldown.get(cooldown_key)
        if last_triggered is not None and (now_ts - last_triggered) < _MEASURE_COOLDOWN_SECONDS:
            elapsed = now_ts - last_triggered
            retry_after_seconds = max(1, int(ceil(_MEASURE_COOLDOWN_SECONDS - elapsed)))
            logger.warning(
                "trigger_measurement rejected — measurement busy: esp=%s gpio=%s "
                "(%.1fs since last trigger, cooldown=%.1fs)",
                esp_id,
                gpio,
                elapsed,
                _MEASURE_COOLDOWN_SECONDS,
            )
            raise MeasurementBusyError(
                esp_id=esp_id,
                gpio=gpio,
                retry_after_seconds=retry_after_seconds,
            )

        # 4. Publish MQTT command via Publisher
        success, request_id = self.publisher.publish_sensor_command(
            esp_id=esp_id,
            gpio=gpio,
            command="measure",
            correlation_id=None,
            command_params=command_params or None,
        )

        if not success:
            raise RuntimeError(f"Failed to publish measurement command to {esp_id}/GPIO {gpio}")

        # Record timestamp for busy-guard — only after successful publish
        _measure_cooldown[cooldown_key] = datetime.now(timezone.utc).timestamp()

        logger.info(
            f"Measurement triggered for {esp_id}/GPIO {gpio} "
            f"(sensor_type: {sensor.sensor_type}, request_id: {request_id})"
        )
        await self._persist_measurement_intent_sent(
            intent_id=request_id,
            esp_id=esp_id,
        )

        return {
            "success": True,
            "request_id": request_id,
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": sensor.sensor_type,
            "message": "Measurement command sent",
        }

    async def _persist_measurement_intent_sent(self, *, intent_id: str, esp_id: str) -> None:
        """
        Persist outgoing measurement intent as orchestration_state='sent'.

        This keeps manual sensor measurements in the same command contract spine
        as actuator commands: sent -> accepted/ack_pending -> terminal outcome.
        """
        session = getattr(self.sensor_repo, "session", None)
        if session is None:
            return
        try:
            contract_repo = CommandContractRepository(session)
            await contract_repo.record_intent_publish_sent(
                intent_id=intent_id,
                correlation_id=intent_id,
                esp_id=esp_id,
                flow="command",
            )
        except Exception:
            logger.warning(
                "Measurement intent contract persistence failed (continuing): "
                "intent_id=%s esp_id=%s",
                intent_id,
                esp_id,
                exc_info=True,
            )
