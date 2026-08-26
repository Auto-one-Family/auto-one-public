"""
Humidity Sensor Library - Pi-Enhanced Processing

Processes raw humidity values from digital sensors into standardized relative humidity measurements.

Supported Sensors:
- SHT31 (I2C Temperature & Humidity Sensor)
- BME280 humidity is implemented in `bme280.py` (separate file because
  the BME280 ships temperature + pressure + humidity as one device).

Each processor converts raw values to calibrated humidity measurements with
validation and quality assessment.
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class SHT31HumidityProcessor(BaseSensorProcessor):
    """
    SHT31 I2C Humidity Sensor Processor.

    The SHT31 is a digital temperature and humidity sensor using I2C communication.

    Supports TWO modes:
    1. RAW Mode (Pi-Enhanced): ESP sends 16-bit unsigned integer, server converts
       - raw_value = 32768 → 100 * 32768 / 65535 = 50.0% RH
       - Set params["raw_mode"] = True
    2. Pre-Converted Mode: ESP sends humidity in % RH (legacy)
       - raw_value = 50.0 → 50.0% RH (direct)
       - Set params["raw_mode"] = False (default for backward compatibility)

    Sensor Specifications:
    - Humidity Range: 0-100% RH (Relative Humidity)
    - Resolution: 0.01% RH (typical)
    - Communication: I2C (Address: 0x44 or 0x45)
    - Accuracy: ±2% RH (20-80% RH at 25°C)
    - Response Time: 8 seconds (tau 63%)
    - Temperature Sensor: Same chip (see SHT31TemperatureProcessor)

    RAW Value Conversion (Sensirion Datasheet):
    - Formula: humidity_rh = 100 * raw_value / 65535.0
    - RAW Range: 0 - 65535 (16-bit unsigned)
    - Example: raw=32768 → 100 * 32768 / 65535 = 50.0% RH

    ESP32 Setup:
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x44 (default) or 0x45 (if ADR pin connected to VIN)
    - Command: 0x24, 0x00 (Single Shot, High Repeatability)
    - Data bytes 3-4 contain humidity (bytes 0-1 contain temperature)

    Important Notes:
    - Humidity readings are temperature-dependent
    - High humidity (>95%) may indicate condensation
    - Low humidity (<5%) may indicate sensor disconnection
    - For accurate readings, allow sensor to stabilize for 8 seconds
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Humidity sensors are typically used for continuous environmental monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 30  # Read every 30 seconds
    SUPPORTS_ON_DEMAND = False

    # SHT31 Humidity Specifications
    HUMIDITY_MIN = 0.0  # % RH (physical minimum)
    HUMIDITY_MAX = 100.0  # % RH (physical maximum)
    HUMIDITY_TYPICAL_MIN = 20.0  # % RH (typical accuracy range)
    HUMIDITY_TYPICAL_MAX = 80.0  # % RH (typical accuracy range)
    RESOLUTION = 0.01  # % RH (typical)

    # Quality thresholds
    CONDENSATION_THRESHOLD = 95.0  # % RH (likely condensation)
    LOW_THRESHOLD = 5.0  # % RH (suspiciously low, possible sensor issue)

    # RAW Mode Conversion (Pi-Enhanced)
    RAW_CONVERSION_SCALE = 100.0
    RAW_MAX_VALUE = 65535.0

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "sht31_humidity"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process SHT31 humidity reading.

        Supports TWO modes:
        1. RAW Mode (Pi-Enhanced): ESP sends 16-bit unsigned integer, server converts
           - raw_value = 32768 → 100 * 32768 / 65535 = 50.0% RH
           - Set params["raw_mode"] = True
        2. Pre-Converted Mode: ESP sends humidity in % RH
           - raw_value = 50.0 → 50.0% RH (direct)
           - Set params["raw_mode"] = False (default for backward compatibility)

        Args:
            raw_value: Humidity value
                - If raw_mode=True: 16-bit unsigned integer (0-65535)
                - If raw_mode=False: Humidity in % RH (pre-converted)
            calibration: Optional calibration data
                - "offset": float - Humidity offset correction (% RH)
            params: Optional processing parameters
                - "raw_mode": bool - Whether value is RAW 16-bit (default: False)
                - "decimal_places": int - Decimal places for rounding (default: 1)
                - "condensation_warning": bool - Warn if humidity >95% (default: True)

        Returns:
            ProcessingResult with humidity value, unit "%RH", quality assessment

        Example:
            # RAW Mode (Pi-Enhanced) - ESP sends 16-bit integer
            result = processor.process(
                raw_value=32768,  # 16-bit RAW
                params={"raw_mode": True}
            )
            # result.value = 50.0 (converted), result.unit = "%RH"

            # Pre-Converted Mode (backward compatible)
            result = processor.process(raw_value=65.5)
            # result.value = 65.5, result.unit = "%RH", result.quality = "good"
        """
        # Step 0: Check for RAW mode (Pi-Enhanced)
        raw_mode = params.get("raw_mode", False) if params else False
        original_raw_value = raw_value  # Keep original for metadata

        if raw_mode:
            # ==================================================================
            # RAW MODE CONVERSION (Sensirion Datasheet)
            # Formula: humidity_rh = 100 * raw_value / 65535.0
            # ==================================================================
            raw_int = int(raw_value)

            # Validate RAW value range (0-65535)
            if raw_int < 0 or raw_int > 65535:
                return ProcessingResult(
                    value=0.0,
                    unit="%RH",
                    quality="error",
                    metadata={
                        "error": f"SHT31 RAW humidity value {raw_int} out of range (0-65535)",
                        "raw_mode": raw_mode,
                        "original_raw_value": original_raw_value,
                    },
                )

            # Convert RAW to % RH
            raw_value = self.RAW_CONVERSION_SCALE * float(raw_int) / self.RAW_MAX_VALUE

        # Step 1: Validate converted value (now in % RH)
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="%RH",
                quality="error",
                metadata={
                    "error": validation.error,
                    "raw_mode": raw_mode,
                    "original_raw_value": original_raw_value if raw_mode else None,
                },
            )

        # Step 2: Apply calibration offset (if provided)
        humidity = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            humidity += calibration["offset"]
            calibrated = True

        # Step 3: Clamp to valid range (0-100%)
        # After calibration, ensure we don't exceed physical limits
        humidity = max(self.HUMIDITY_MIN, min(self.HUMIDITY_MAX, humidity))

        # Step 4: Round to decimal places
        decimal_places = 1  # Default (SHT31 has 0.01% RH resolution)
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        humidity = round(humidity, decimal_places)

        # Step 5: Quality assessment
        quality = self._assess_quality(humidity, calibrated)

        # Step 6: Check for condensation (if enabled)
        condensation_warning_enabled = True
        if params and "condensation_warning" in params:
            condensation_warning_enabled = params["condensation_warning"]

        metadata_dict: Dict[str, Any] = {
            "raw_humidity": raw_value,
            "calibrated": calibrated,
            "warnings": validation.warnings,
            # RAW mode metadata (Pi-Enhanced)
            "raw_mode": raw_mode,
            "original_raw_value": original_raw_value if raw_mode else None,
            "conversion_formula": (
                f"100 * {int(original_raw_value)} / 65535" if raw_mode else None
            ),
        }

        if condensation_warning_enabled and humidity > self.CONDENSATION_THRESHOLD:
            if "warnings" not in metadata_dict or metadata_dict["warnings"] is None:
                metadata_dict["warnings"] = []
            metadata_dict["warnings"].append(
                f"High humidity ({humidity}% RH) may indicate condensation. "
                "Consider activating heater element."
            )

        # Step 7: Return result
        return ProcessingResult(
            value=humidity,
            unit="%RH",
            quality=quality,
            metadata=metadata_dict,
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate SHT31 humidity reading.

        Checks if humidity is within physical range (0-100% RH).
        Provides warnings for extreme values.

        Args:
            raw_value: Relative Humidity % (0-100)

        Returns:
            ValidationResult with validity status and optional warnings
        """
        # Check absolute limits (0-100% RH)
        if raw_value < self.HUMIDITY_MIN or raw_value > self.HUMIDITY_MAX:
            return ValidationResult(
                valid=False,
                error=f"Humidity {raw_value}% RH out of physical range "
                f"({self.HUMIDITY_MIN}-{self.HUMIDITY_MAX}% RH)",
            )

        # Warnings for extreme values
        warnings = []

        # Very low humidity (possible sensor disconnection or malfunction)
        if raw_value < self.LOW_THRESHOLD:
            warnings.append(
                f"Very low humidity ({raw_value}% RH). "
                "Check sensor connection and environmental conditions."
            )

        # Very high humidity (possible condensation)
        if raw_value > self.CONDENSATION_THRESHOLD:
            warnings.append(
                f"Very high humidity ({raw_value}% RH). "
                "Possible condensation on sensor. Consider using heater element."
            )

        # Outside typical accuracy range
        if raw_value < self.HUMIDITY_TYPICAL_MIN or raw_value > self.HUMIDITY_TYPICAL_MAX:
            warnings.append(
                f"Humidity {raw_value}% RH outside typical accuracy range "
                f"({self.HUMIDITY_TYPICAL_MIN}-{self.HUMIDITY_TYPICAL_MAX}% RH). "
                "Accuracy may be reduced to ±3% RH."
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """
        Perform SHT31 humidity calibration.

        SHT31 is factory-calibrated with high accuracy (±2% RH). However,
        optional offset calibration can be performed using a reference
        humidity source (e.g., salt solutions).

        Common Salt Solutions for Humidity Calibration:
        - MgCl2 (Magnesium Chloride): 33% RH at 25°C
        - NaCl (Sodium Chloride): 75% RH at 25°C
        - KCl (Potassium Chloride): 85% RH at 25°C

        Args:
            calibration_points: List of calibration points
                [{"raw": 76.5, "reference": 75.0}]  # NaCl salt solution
            method: Calibration method ("offset" - only supported method)

        Returns:
            Calibration data dict: {"offset": float}

        Raises:
            ValueError: If method is not "offset" or insufficient points

        Example:
            # Calibration using NaCl salt solution (75% RH at 25°C)
            calibration = processor.calibrate(
                calibration_points=[{"raw": 76.5, "reference": 75.0}],
                method="offset"
            )
            # Returns: {"offset": -1.5}
        """
        if len(calibration_points) < 1:
            raise ValueError("SHT31 humidity calibration requires at least 1 point")

        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for SHT31 humidity. "
                "Only 'offset' method is supported."
            )

        # Calculate average offset from all calibration points
        total_offset = 0.0
        for point in calibration_points:
            raw = point["raw"]
            reference = point["reference"]
            offset = reference - raw
            total_offset += offset

        average_offset = total_offset / len(calibration_points)

        return {
            "offset": average_offset,
            "method": "offset",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters for SHT31 humidity."""
        return {
            "decimal_places": 1,
            "condensation_warning": True,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected humidity value range (0-100% RH)."""
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (same as value range)."""
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def _assess_quality(self, humidity: float, calibrated: bool) -> str:
        """
        Assess humidity data quality.

        Quality levels:
        - "good": Within typical accuracy range (20-80% RH)
        - "fair": Outside typical range or high/low extremes
        - "poor": Very extreme values (near 0% or 100%)
        - "error": Outside physical range (should be caught by validate)

        Args:
            humidity: Humidity in % RH
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", "poor", or "error"
        """
        # Error: Outside physical range (0-100%)
        if humidity < self.HUMIDITY_MIN or humidity > self.HUMIDITY_MAX:
            return "error"

        # Poor: Very extreme values (possible sensor issues)
        if humidity < self.LOW_THRESHOLD or humidity > self.CONDENSATION_THRESHOLD:
            return "poor"

        # Good: Within typical accuracy range (20-80% RH)
        if self.HUMIDITY_TYPICAL_MIN <= humidity <= self.HUMIDITY_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical range but within reasonable limits
        return "fair"


class BME280HumidityProcessor(BaseSensorProcessor):
    """
    BME280 I2C Humidity Sensor Processor.

    The BME280 is a combined temperature, pressure, and humidity sensor (I2C/SPI).
    Unlike the BMP280 (pressure + temperature only), the BME280 adds a humidity
    channel that outputs pre-converted %RH values via the ESP32 Adafruit_BME280 library.

    BME280 delivers humidity directly in %RH (no raw ADC conversion required server-side).
    Temperature and pressure from BME280 are handled by BMP280Processor classes since
    the underlying physics and calibration are identical.

    Sensor Specifications:
    - Humidity Range: 0-100% RH
    - Humidity Accuracy: ±3% RH (20-80% RH)
    - Response Time: 1 second
    - Communication: I2C (Address: 0x76 or 0x77)

    ESP32 Setup:
    - Library: Adafruit_BME280
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x76 (default) or 0x77
    """

    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180
    RECOMMENDED_INTERVAL_SECONDS = 30
    SUPPORTS_ON_DEMAND = False

    HUMIDITY_MIN = 0.0
    HUMIDITY_MAX = 100.0
    HUMIDITY_TYPICAL_MIN = 20.0
    HUMIDITY_TYPICAL_MAX = 80.0
    CONDENSATION_THRESHOLD = 95.0
    LOW_THRESHOLD = 5.0

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "bme280_humidity"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process BME280 humidity reading.

        ESP32 Adafruit_BME280 library delivers %RH directly (pre-converted).

        Args:
            raw_value: Humidity in % RH (pre-converted by ESP32 library)
            calibration: Optional calibration data — "offset": float (%RH)
            params: Optional processing parameters
                - "decimal_places": int (default: 1)
                - "condensation_warning": bool (default: True)

        Returns:
            ProcessingResult with humidity value, unit "%RH", quality assessment
        """
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="%RH",
                quality="error",
                metadata={"error": validation.error},
            )

        humidity = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            humidity += calibration["offset"]
            calibrated = True

        humidity = max(self.HUMIDITY_MIN, min(self.HUMIDITY_MAX, humidity))

        decimal_places = 1
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        humidity = round(humidity, decimal_places)

        quality = self._assess_quality(humidity, calibrated)

        metadata_dict: Dict[str, Any] = {
            "raw_humidity": raw_value,
            "calibrated": calibrated,
            "warnings": validation.warnings,
        }

        condensation_warning_enabled = True
        if params and "condensation_warning" in params:
            condensation_warning_enabled = params["condensation_warning"]

        if condensation_warning_enabled and humidity > self.CONDENSATION_THRESHOLD:
            if not metadata_dict["warnings"]:
                metadata_dict["warnings"] = []
            metadata_dict["warnings"].append(
                f"High humidity ({humidity}% RH) may indicate condensation."
            )

        return ProcessingResult(
            value=humidity,
            unit="%RH",
            quality=quality,
            metadata=metadata_dict,
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """Validate BME280 humidity reading (0-100% RH)."""
        if raw_value < self.HUMIDITY_MIN or raw_value > self.HUMIDITY_MAX:
            return ValidationResult(
                valid=False,
                error=f"Humidity {raw_value}% RH out of physical range "
                f"({self.HUMIDITY_MIN}-{self.HUMIDITY_MAX}% RH)",
            )

        warnings = []
        if raw_value < self.LOW_THRESHOLD:
            warnings.append(
                f"Very low humidity ({raw_value}% RH). Check sensor connection."
            )
        if raw_value > self.CONDENSATION_THRESHOLD:
            warnings.append(
                f"Very high humidity ({raw_value}% RH). Possible condensation."
            )
        if raw_value < self.HUMIDITY_TYPICAL_MIN or raw_value > self.HUMIDITY_TYPICAL_MAX:
            warnings.append(
                f"Humidity {raw_value}% RH outside typical accuracy range "
                f"({self.HUMIDITY_TYPICAL_MIN}-{self.HUMIDITY_TYPICAL_MAX}% RH)."
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """Perform BME280 humidity calibration (offset method only)."""
        if len(calibration_points) < 1:
            raise ValueError("BME280 humidity calibration requires at least 1 point")
        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported. Only 'offset' is supported."
            )

        total_offset = sum(p["reference"] - p["raw"] for p in calibration_points)
        return {
            "offset": total_offset / len(calibration_points),
            "method": "offset",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters for BME280 humidity."""
        return {"decimal_places": 1, "condensation_warning": True}

    def get_value_range(self) -> Dict[str, float]:
        """Get expected humidity value range (0-100% RH)."""
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (same as value range)."""
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def _assess_quality(self, humidity: float, calibrated: bool) -> str:
        """Assess humidity data quality."""
        if humidity < self.HUMIDITY_MIN or humidity > self.HUMIDITY_MAX:
            return "error"
        if humidity < self.LOW_THRESHOLD or humidity > self.CONDENSATION_THRESHOLD:
            return "poor"
        if self.HUMIDITY_TYPICAL_MIN <= humidity <= self.HUMIDITY_TYPICAL_MAX:
            return "good"
        return "fair"
