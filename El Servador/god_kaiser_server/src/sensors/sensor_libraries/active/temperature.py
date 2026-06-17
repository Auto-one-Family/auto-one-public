"""
Temperature Sensor Library - Pi-Enhanced Processing

Processes raw temperature values from multiple sensor types into standardized measurements.

Supported Sensors:
- DS18B20 (OneWire Digital Temperature Sensor)
- SHT31 (I2C Temperature & Humidity Sensor)

Each processor converts raw values to calibrated temperature measurements with
unit conversion support (Celsius, Fahrenheit, Kelvin).
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class DS18B20Processor(BaseSensorProcessor):
    """
    DS18B20 OneWire Temperature Sensor Processor.

    The DS18B20 is a digital temperature sensor that uses 1-Wire communication.
    ESP32 uses the raw OneWire library and sends the 12-bit signed integer directly
    (1 LSB = 0.0625°C). Server performs the conversion to Celsius. This processor:
    - Converts raw int16 to Celsius (raw_value * 0.0625)
    - Validates temperature range
    - Applies optional calibration offset
    - Handles unit conversion (°C, °F, K)
    - Assesses data quality

    Sensor Specifications:
    - Temperature Range: -55°C to +125°C
    - Resolution: 0.0625°C (12-bit mode)
    - Communication: 1-Wire (OneWire protocol)
    - Accuracy: ±0.5°C (-10°C to +85°C)
    - Hardware: Requires 4.7kΩ pull-up resistor

    ESP32 Setup:
    - Library: DallasTemperature + OneWire
    - GPIO: Any (e.g., GPIO17)
    - Multiple sensors on same bus: Supported (unique 64-bit ROM address)

    Special Value Detection (Defense-in-Depth):
    - -127°C (RAW -2032): Sensor fault (disconnected, CRC failure)
    - +85°C (RAW 1360): Power-on reset value (factory default)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Temperature sensors are typically used for continuous monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 30  # Read every 30 seconds
    SUPPORTS_ON_DEMAND = False

    # DS18B20 Specifications
    TEMP_MIN = -55.0  # °C (datasheet minimum)
    TEMP_MAX = 125.0  # °C (datasheet maximum)
    TEMP_TYPICAL_MIN = -10.0  # °C (typical operating range)
    TEMP_TYPICAL_MAX = 85.0  # °C (typical operating range)
    RESOLUTION = 0.0625  # °C (12-bit mode)

    # DS18B20 Special RAW Values (Defense-in-Depth)
    # RAW = Temperature × 16 (12-bit resolution)
    RAW_SENSOR_FAULT = -2032  # -127°C: Sensor disconnected or CRC failure
    RAW_POWER_ON_RESET = 1360  # +85°C: Factory default before first conversion

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "ds18b20"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process DS18B20 temperature reading.

        Supports TWO modes:
        1. RAW Mode (Pi-Enhanced): ESP sends 12-bit signed integer, server converts
           - raw_value = 400 → 400 * 0.0625 = 25.0°C
           - Set params["raw_mode"] = True
        2. Pre-Converted Mode: ESP sends temperature in °C
           - raw_value = 25.0 → 25.0°C (direct)
           - Set params["raw_mode"] = False (default for backward compatibility)

        Args:
            raw_value: Temperature value
                - If raw_mode=True: 12-bit signed integer (LSB = 0.0625°C)
                - If raw_mode=False: Temperature in °C (pre-converted by ESP)
            calibration: Optional calibration data
                - "offset": float - Temperature offset correction (°C)
            params: Optional processing parameters
                - "raw_mode": bool - Whether value is RAW 12-bit (default: False)
                - "unit": str - Output unit ("celsius", "fahrenheit", "kelvin")
                - "decimal_places": int - Decimal places for rounding (default: 2)

        Returns:
            ProcessingResult with temperature value, unit, quality assessment

        Example:
            # RAW Mode (Pi-Enhanced) - ESP sends 12-bit integer
            result = processor.process(
                raw_value=400,  # 12-bit RAW
                params={"raw_mode": True}
            )
            # result.value = 25.0 (400 * 0.0625), result.unit = "°C"

            # Pre-Converted Mode (backward compatible)
            result = processor.process(raw_value=23.5)
            # result.value = 23.5, result.unit = "°C", result.quality = "good"

            # RAW Mode with Fahrenheit conversion
            result = processor.process(
                raw_value=400,
                params={"raw_mode": True, "unit": "fahrenheit"}
            )
            # result.value = 77.0 (25°C → °F), result.unit = "°F"
        """
        # Step 0: Check for RAW mode (Pi-Enhanced)
        # If raw_mode=True, convert 12-bit signed integer to Celsius first.
        # Default False: backward-compatible (ESP sends pre-converted Celsius).
        # Set params["raw_mode"] = True for Pi-Enhanced raw int16 mode.
        raw_mode = params.get("raw_mode", False) if params else False
        original_raw_value = raw_value  # Keep original for metadata

        if raw_mode:
            # ==================================================================
            # SPECIAL VALUE DETECTION (Defense-in-Depth)
            # ESP should filter these, but server validates as backup
            # ==================================================================
            raw_int = int(raw_value)

            # Check for sensor fault: -127°C (RAW = -2032)
            if raw_int == self.RAW_SENSOR_FAULT:
                return ProcessingResult(
                    value=0.0,
                    unit="°C",
                    quality="error",
                    metadata={
                        "error": "DS18B20 sensor fault: -127°C indicates disconnected sensor or CRC failure",
                        "error_code": 1060,  # ERROR_DS18B20_SENSOR_FAULT
                        "raw_mode": raw_mode,
                        "original_raw_value": original_raw_value,
                    },
                )

            # Check for power-on reset: +85°C (RAW = 1360)
            # Note: This value indicates sensor may not have completed first conversion.
            # While 85°C could be a real temperature (fire!), we mark it as "suspect"
            # to alert operators that this is a known power-on reset default value.
            # The data is still processed but flagged for review.
            if raw_int == self.RAW_POWER_ON_RESET:
                # Convert to Celsius and return with suspect quality
                converted_value = float(raw_int) * self.RESOLUTION  # 85.0°C
                return ProcessingResult(
                    value=converted_value,
                    unit="°C",
                    quality="suspect",
                    metadata={
                        "warning": "DS18B20 power-on reset value (85°C) detected. "
                        "This may indicate sensor not yet initialized or actual high temperature.",
                        "warning_code": 1061,  # ERROR_DS18B20_POWER_ON_RESET
                        "raw_mode": raw_mode,
                        "original_raw_value": original_raw_value,
                        "requires_verification": True,
                    },
                )

            # DS18B20 12-bit resolution: 1 LSB = 0.0625°C
            # RAW value is signed 16-bit: -55°C = -880, +125°C = +2000
            raw_value = float(raw_value) * self.RESOLUTION

        # Step 1: Validate converted value (now in Celsius)
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="°C",
                quality="error",
                metadata={
                    "error": validation.error,
                    "raw_mode": raw_mode,
                    "original_raw_value": original_raw_value if raw_mode else None,
                },
            )

        # Step 2: Apply calibration offset (if provided)
        temp_celsius = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            temp_celsius += calibration["offset"]
            calibrated = True

        # Step 3: Unit conversion
        unit_type = "celsius"
        if params and "unit" in params:
            unit_type = params["unit"].lower()

        if unit_type == "fahrenheit":
            value = temp_celsius * 9 / 5 + 32
            unit_str = "°F"
        elif unit_type == "kelvin":
            value = temp_celsius + 273.15
            unit_str = "K"
        else:
            value = temp_celsius
            unit_str = "°C"

        # Step 4: Round to decimal places
        decimal_places = 2  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        value = round(value, decimal_places)

        # Step 5: Quality assessment
        quality = self._assess_quality(temp_celsius, calibrated)

        # Step 6: Return result
        return ProcessingResult(
            value=value,
            unit=unit_str,
            quality=quality,
            metadata={
                "raw_celsius": raw_value,
                "calibrated": calibrated,
                "warnings": validation.warnings,
                # RAW mode metadata (Pi-Enhanced)
                "raw_mode": raw_mode,
                "original_raw_value": original_raw_value if raw_mode else None,
                "conversion_factor": self.RESOLUTION if raw_mode else None,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate DS18B20 temperature reading.

        Checks if temperature is within sensor's physical range (-55°C to +125°C).
        Provides warnings if temperature is outside typical operating range.

        Args:
            raw_value: Temperature in °C

        Returns:
            ValidationResult with validity status and optional warnings
        """
        # Check absolute limits (sensor physically cannot measure outside this)
        if raw_value < self.TEMP_MIN or raw_value > self.TEMP_MAX:
            return ValidationResult(
                valid=False,
                error=f"Temperature {raw_value}°C out of sensor range "
                f"({self.TEMP_MIN}°C to {self.TEMP_MAX}°C)",
            )

        # Warnings for extreme values (sensor works but accuracy may be reduced)
        warnings = []
        if raw_value < self.TEMP_TYPICAL_MIN:
            warnings.append(
                f"Temperature {raw_value}°C below typical range "
                f"(accuracy may be reduced below {self.TEMP_TYPICAL_MIN}°C)"
            )
        elif raw_value > self.TEMP_TYPICAL_MAX:
            warnings.append(
                f"Temperature {raw_value}°C above typical range "
                f"(accuracy may be reduced above {self.TEMP_TYPICAL_MAX}°C)"
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """
        Perform DS18B20 temperature calibration.

        DS18B20 is factory-calibrated and typically very accurate. However,
        a simple offset calibration can be performed if needed.

        Args:
            calibration_points: List of calibration points
                [{"raw": 23.5, "reference": 24.0}]  # Measured vs. reference
            method: Calibration method ("offset" - only supported method)

        Returns:
            Calibration data dict: {"offset": float}

        Raises:
            ValueError: If method is not "offset" or insufficient points

        Example:
            # Single-point offset calibration
            calibration = processor.calibrate(
                calibration_points=[{"raw": 23.5, "reference": 24.0}],
                method="offset"
            )
            # Returns: {"offset": 0.5}
        """
        if len(calibration_points) < 1:
            raise ValueError("DS18B20 calibration requires at least 1 point")

        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for DS18B20. "
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
        """Get default processing parameters for DS18B20."""
        return {
            "unit": "celsius",
            "decimal_places": 2,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected temperature value range (Celsius)."""
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """
        Get expected raw value range.

        For DS18B20 in RAW mode (Pi-Enhanced):
        - ESP sends 12-bit signed integer
        - Range: -880 (-55°C) to +2000 (+125°C)

        For pre-converted mode (backward compatible):
        - ESP sends Celsius directly
        - Range: -55.0 to +125.0

        This returns the Celsius range since it's used for validation
        AFTER conversion to Celsius.
        """
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def _assess_quality(self, temp_celsius: float, calibrated: bool) -> str:
        """
        Assess temperature data quality.

        Quality levels:
        - "good": Within typical operating range, optionally calibrated
        - "fair": Outside typical range but within absolute limits
        - "poor": Extreme values (near sensor limits)
        - "error": Outside sensor physical range (should not happen if validated)

        Args:
            temp_celsius: Temperature in Celsius
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", "poor", or "error"
        """
        # Error: Outside physical range (should be caught by validate)
        if temp_celsius < self.TEMP_MIN or temp_celsius > self.TEMP_MAX:
            return "error"

        # Good: Within typical operating range
        if self.TEMP_TYPICAL_MIN <= temp_celsius <= self.TEMP_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical range but within absolute limits
        if self.TEMP_MIN <= temp_celsius <= self.TEMP_MAX:
            return "fair"

        # Poor: Extreme values (should not reach here)
        return "poor"


class SHT31TemperatureProcessor(BaseSensorProcessor):
    """
    SHT31 I2C Temperature Sensor Processor.

    The SHT31 is a digital temperature and humidity sensor using I2C communication.

    Supports TWO modes:
    1. RAW Mode (Pi-Enhanced): ESP sends 16-bit unsigned integer, server converts
       - raw_value = 27445 → -45 + (175 * 27445 / 65535) = 23.5°C
       - Set params["raw_mode"] = True
    2. Pre-Converted Mode: ESP sends temperature in °C (legacy)
       - raw_value = 23.5 → 23.5°C (direct)
       - Set params["raw_mode"] = False (default for backward compatibility)

    Sensor Specifications:
    - Temperature Range: -40°C to +125°C
    - Resolution: 0.01°C (typical)
    - Communication: I2C (Address: 0x44 or 0x45)
    - Accuracy: ±0.2°C (0°C to +65°C)
    - Humidity Sensor: Same chip (see SHT31HumidityProcessor)

    RAW Value Conversion (Sensirion Datasheet):
    - Formula: temp_celsius = -45 + (175 * raw_value / 65535.0)
    - RAW Range: 0 - 65535 (16-bit unsigned)
    - Example: raw=27445 → -45 + (175 * 27445 / 65535) = 23.5°C

    ESP32 Setup:
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x44 (default) or 0x45 (if ADR pin connected to VIN)
    - Command: 0x24, 0x00 (Single Shot, High Repeatability)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Temperature sensors are typically used for continuous monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 30  # Read every 30 seconds
    SUPPORTS_ON_DEMAND = False

    # SHT31 Specifications
    TEMP_MIN = -40.0  # °C (datasheet minimum)
    TEMP_MAX = 125.0  # °C (datasheet maximum)
    TEMP_TYPICAL_MIN = 0.0  # °C (typical accuracy range)
    TEMP_TYPICAL_MAX = 65.0  # °C (typical accuracy range)
    RESOLUTION = 0.01  # °C (typical)

    # RAW Mode Conversion (Pi-Enhanced)
    RAW_CONVERSION_OFFSET = -45.0
    RAW_CONVERSION_SCALE = 175.0
    RAW_MAX_VALUE = 65535.0

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "sht31_temp"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process SHT31 temperature reading.

        Supports TWO modes:
        1. RAW Mode (Pi-Enhanced): ESP sends 16-bit unsigned integer, server converts
           - raw_value = 27445 → -45 + (175 * 27445 / 65535) = 23.5°C
           - Set params["raw_mode"] = True
        2. Pre-Converted Mode: ESP sends temperature in °C
           - raw_value = 23.5 → 23.5°C (direct)
           - Set params["raw_mode"] = False (default for backward compatibility)

        Args:
            raw_value: Temperature value
                - If raw_mode=True: 16-bit unsigned integer (0-65535)
                - If raw_mode=False: Temperature in °C (pre-converted)
            calibration: Optional calibration data
                - "offset": float - Temperature offset correction (°C)
            params: Optional processing parameters
                - "raw_mode": bool - Whether value is RAW 16-bit (default: False)
                - "unit": str - Output unit ("celsius" or "fahrenheit")
                - "decimal_places": int - Decimal places for rounding (default: 1)

        Returns:
            ProcessingResult with temperature value, unit, quality assessment

        Example:
            # RAW Mode (Pi-Enhanced) - ESP sends 16-bit integer
            result = processor.process(
                raw_value=27445,  # 16-bit RAW
                params={"raw_mode": True}
            )
            # result.value = 23.5 (converted), result.unit = "°C"

            # Pre-Converted Mode (backward compatible)
            result = processor.process(raw_value=23.5)
            # result.value = 23.5, result.unit = "°C", result.quality = "good"
        """
        # Step 0: Check for RAW mode (Pi-Enhanced)
        raw_mode = params.get("raw_mode", False) if params else False
        original_raw_value = raw_value  # Keep original for metadata

        if raw_mode:
            # ==================================================================
            # RAW MODE CONVERSION (Sensirion Datasheet)
            # Formula: temp_celsius = -45 + (175 * raw_value / 65535.0)
            # Real 16-bit RAW range: 0-65535 (maps to -45°C..+130°C)
            # ==================================================================
            raw_int = int(raw_value)

            # Validate RAW value range (0-65535)
            if raw_int < 0 or raw_int > 65535:
                return ProcessingResult(
                    value=0.0,
                    unit="°C",
                    quality="error",
                    metadata={
                        "error": f"SHT31 RAW value {raw_int} out of range (0-65535)",
                        "raw_mode": raw_mode,
                        "original_raw_value": original_raw_value,
                    },
                )

            # Convert RAW to Celsius
            converted = self.RAW_CONVERSION_OFFSET + (
                self.RAW_CONVERSION_SCALE * float(raw_int) / self.RAW_MAX_VALUE
            )

            # Passthrough guard: if the 16-bit conversion yields a physically
            # implausible result but the original value is already a valid
            # Celsius reading (e.g. mock devices send 22.0 °C, not 22 as a
            # 16-bit integer), treat the original value as pre-converted.
            # A real 16-bit RAW reading for typical room temperature (22°C)
            # would be ~27445, never a small integer like 22.
            if not (self.TEMP_MIN <= converted <= self.TEMP_MAX) and (
                0 < original_raw_value <= self.TEMP_MAX
            ):
                # The raw_value is already in Celsius — use it as-is.
                raw_value = original_raw_value
            else:
                raw_value = converted

        # Step 1: Validate converted value (now in Celsius)
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="°C",
                quality="error",
                metadata={
                    "error": validation.error,
                    "raw_mode": raw_mode,
                    "original_raw_value": original_raw_value if raw_mode else None,
                },
            )

        # Step 2: Apply calibration offset (if provided)
        temp_celsius = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            temp_celsius += calibration["offset"]
            calibrated = True

        # Step 3: Unit conversion
        unit_type = "celsius"
        if params and "unit" in params:
            unit_type = params["unit"].lower()

        if unit_type == "fahrenheit":
            value = temp_celsius * 9 / 5 + 32
            unit_str = "°F"
        else:
            value = temp_celsius
            unit_str = "°C"

        # Step 4: Round to decimal places
        decimal_places = 1  # Default (SHT31 has 0.01°C resolution)
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        value = round(value, decimal_places)

        # Step 5: Quality assessment
        quality = self._assess_quality(temp_celsius, calibrated)

        # Step 6: Return result
        return ProcessingResult(
            value=value,
            unit=unit_str,
            quality=quality,
            metadata={
                "raw_celsius": raw_value,
                "calibrated": calibrated,
                "warnings": validation.warnings,
                # RAW mode metadata (Pi-Enhanced)
                "raw_mode": raw_mode,
                "original_raw_value": original_raw_value if raw_mode else None,
                "conversion_formula": (
                    f"-45 + (175 * {int(original_raw_value)} / 65535)" if raw_mode else None
                ),
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate SHT31 temperature reading.

        Checks if temperature is within sensor's physical range (-40°C to +125°C).
        Provides warnings if temperature is outside typical accuracy range.

        Args:
            raw_value: Temperature in °C

        Returns:
            ValidationResult with validity status and optional warnings
        """
        # Check absolute limits
        if raw_value < self.TEMP_MIN or raw_value > self.TEMP_MAX:
            return ValidationResult(
                valid=False,
                error=f"Temperature {raw_value}°C out of sensor range "
                f"({self.TEMP_MIN}°C to {self.TEMP_MAX}°C)",
            )

        # Warnings for values outside typical accuracy range
        warnings = []
        if raw_value < self.TEMP_TYPICAL_MIN or raw_value > self.TEMP_TYPICAL_MAX:
            warnings.append(
                f"Temperature {raw_value}°C outside typical accuracy range "
                f"({self.TEMP_TYPICAL_MIN}°C to {self.TEMP_TYPICAL_MAX}°C). "
                "Accuracy may be reduced to ±0.5°C."
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """
        Perform SHT31 temperature calibration.

        SHT31 is factory-calibrated with high accuracy. Optional offset
        calibration can be performed for fine-tuning.

        Args:
            calibration_points: List of calibration points
                [{"raw": 23.5, "reference": 24.0}]
            method: Calibration method ("offset" - only supported method)

        Returns:
            Calibration data dict: {"offset": float}

        Raises:
            ValueError: If method is not "offset" or insufficient points
        """
        if len(calibration_points) < 1:
            raise ValueError("SHT31 calibration requires at least 1 point")

        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for SHT31. "
                "Only 'offset' method is supported."
            )

        # Calculate average offset
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
        """Get default processing parameters for SHT31."""
        return {
            "unit": "celsius",
            "decimal_places": 1,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected temperature value range (Celsius)."""
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (same as value range)."""
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def _assess_quality(self, temp_celsius: float, calibrated: bool) -> str:
        """
        Assess temperature data quality.

        Quality levels:
        - "good": Within typical accuracy range (0-65°C)
        - "fair": Outside typical range but within absolute limits
        - "error": Outside sensor physical range

        Args:
            temp_celsius: Temperature in Celsius
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", or "error"
        """
        # Error: Outside physical range
        if temp_celsius < self.TEMP_MIN or temp_celsius > self.TEMP_MAX:
            return "error"

        # Good: Within typical accuracy range
        if self.TEMP_TYPICAL_MIN <= temp_celsius <= self.TEMP_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical range but within absolute limits
        return "fair"
