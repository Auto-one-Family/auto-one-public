"""
Pressure & Temperature Sensor Library - BMP280 I2C Sensor

Processes raw pressure and temperature values from BMP280 digital sensor.

NAMING CLARIFICATION (BMP280 vs. BME280):
- BMP280 (this file): Pressure + Temperature only — NO humidity.
- BME280 (see bme280.py): BMP280 + dedicated humidity sensor.
Processor types `bmp280_*` and `bme280_*` are intentionally distinct
in `sensor_type_registry.MULTI_VALUE_SENSORS`. Do NOT alias
`bme280_*` -> `bmp280_*`; multi-value device assembly relies on
per-device sub-type prefixes.

BMP280 is a dual-purpose sensor providing both:
- Barometric Pressure (hPa)
- Temperature (°C)

ESP32-side processing (Adafruit_BMP280 library) already converts raw sensor
data to hPa and °C, so server processors focus on:
- Validation of value ranges
- Optional calibration offset
- Unit conversion (pressure: hPa/Pa/mmHg/inHg, temp: °C/°F/K)
- Quality assessment
- Optional sea-level correction (pressure)

Sensor Specifications:
- Pressure Range: 300-1100 hPa (sea level to ~9000m altitude)
- Pressure Resolution: 0.01 hPa (with oversampling x16)
- Pressure Accuracy: ±1 hPa
- Temperature Range: -40°C to +85°C
- Temperature Resolution: 0.01°C
- Temperature Accuracy: ±1°C (less accurate than SHT31's ±0.2°C)
- Communication: I2C (Address: 0x76 or 0x77)
- Power: 3.3V or 5V

ESP32 Setup:
- Library: Adafruit_BMP280
- I2C: GPIO21 (SDA), GPIO22 (SCL)
- Address: 0x76 (default, SDO to GND) or 0x77 (SDO to VCC)
- Multiple sensors: Use different I2C addresses or I2C multiplexer (TCA9548A)

Important Notes:
- BMP280 provides BOTH pressure and temperature (dual sensor)
- Temperature accuracy is lower than dedicated sensors (SHT31)
- Use SHT31 for high-accuracy temperature measurements
- BMP280 temperature is primarily for pressure compensation
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class BMP280PressureProcessor(BaseSensorProcessor):
    """
    BMP280 Pressure Sensor Processor.

    Processes barometric pressure readings from BMP280 I2C sensor.

    Features:
    - Offset calibration (optional)
    - Unit conversion (hPa, Pa, mmHg, inHg)
    - Sea-level pressure correction (altitude compensation)
    - Quality assessment based on typical atmospheric range

    ESP32 Setup:
    - Library: Adafruit_BMP280
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x76 (default) or 0x77
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Pressure sensors are typically used for continuous environmental monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 300  # 5 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 60  # Read every 60 seconds
    SUPPORTS_ON_DEMAND = False

    # BMP280 Pressure Specifications (based on Bosch BMP280 datasheet)
    PRESSURE_MIN = 300.0  # hPa (sensor minimum, ~9000m altitude)
    PRESSURE_MAX = 1100.0  # hPa (sensor maximum, ~500m below sea level)
    PRESSURE_TYPICAL_MIN = 950.0  # hPa (typical sea-level minimum, strong low pressure system)
    PRESSURE_TYPICAL_MAX = 1050.0  # hPa (typical sea-level maximum, strong high pressure system)
    RESOLUTION = 0.01  # hPa (with oversampling x16, 0.18 Pa RMS noise)

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "bmp280_pressure"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process BMP280 pressure reading.

        Args:
            raw_value: Pressure in hPa (already processed by ESP32 Adafruit_BMP280 library)
            calibration: Optional calibration data
                - "offset": float - Pressure offset correction (hPa)
            params: Optional processing parameters
                - "unit": str - Output unit ("hpa", "pa", "mmhg", "inhg")
                - "altitude": float - Altitude in meters for sea-level correction
                - "decimal_places": int - Decimal places for rounding (default: 1)

        Returns:
            ProcessingResult with pressure value, unit, quality assessment

        Example:
            # Basic usage
            result = processor.process(raw_value=1013.25)
            # result.value = 1013.2, result.unit = "hPa", result.quality = "good"

            # With offset calibration
            result = processor.process(
                raw_value=1013.25,
                calibration={"offset": 2.0}
            )
            # result.value = 1015.2

            # Sea-level correction (at 500m altitude)
            result = processor.process(
                raw_value=1013.25,
                params={"altitude": 500.0}
            )
            # Corrected to sea level

            # Unit conversion (Pa)
            result = processor.process(
                raw_value=1013.25,
                params={"unit": "pa"}
            )
            # result.value = 101325, result.unit = "Pa"
        """
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="hPa",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Apply calibration offset (if provided)
        pressure_hpa = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            pressure_hpa += calibration["offset"]
            calibrated = True

        # Step 3: Sea-level correction (if altitude provided)
        if params and "altitude" in params:
            altitude = params["altitude"]
            pressure_hpa = self._apply_sea_level_correction(pressure_hpa, altitude)

        # Step 4: Unit conversion
        unit_type = "hpa"
        if params and "unit" in params:
            unit_type = params["unit"].lower()

        pressure_value, unit_str = self._convert_unit(pressure_hpa, unit_type)

        # Step 5: Round to decimal places
        decimal_places = 1  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        pressure_value = round(pressure_value, decimal_places)

        # Step 6: Quality assessment
        quality = self._assess_quality(pressure_hpa, calibrated)

        # Step 7: Return result
        return ProcessingResult(
            value=pressure_value,
            unit=unit_str,
            quality=quality,
            metadata={
                "raw_hpa": raw_value,
                "calibrated": calibrated,
                "warnings": validation.warnings,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate BMP280 pressure reading.

        Checks if pressure is within sensor's physical range (300-1100 hPa).

        Args:
            raw_value: Pressure in hPa

        Returns:
            ValidationResult with validity status and optional warnings
        """
        # Check absolute limits
        if raw_value < self.PRESSURE_MIN or raw_value > self.PRESSURE_MAX:
            return ValidationResult(
                valid=False,
                error=f"Pressure {raw_value} hPa out of sensor range "
                f"({self.PRESSURE_MIN}-{self.PRESSURE_MAX} hPa)",
            )

        # Warnings for extreme values
        warnings = []
        if raw_value < self.PRESSURE_TYPICAL_MIN:
            warnings.append(
                f"Pressure {raw_value} hPa below typical range "
                f"(very low pressure or high altitude)"
            )
        elif raw_value > self.PRESSURE_TYPICAL_MAX:
            warnings.append(
                f"Pressure {raw_value} hPa above typical range " f"(very high pressure system)"
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """
        Perform BMP280 pressure calibration.

        BMP280 is factory-calibrated and typically very accurate.
        Simple offset calibration can be performed if needed.

        Args:
            calibration_points: List of calibration points
                [{"raw": 1013.25, "reference": 1015.0}]
            method: Calibration method ("offset" - only supported)

        Returns:
            Calibration data dict: {"offset": float}

        Raises:
            ValueError: If method is not "offset" or insufficient points
        """
        if len(calibration_points) < 1:
            raise ValueError("BMP280 pressure calibration requires at least 1 point")

        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for BMP280 pressure. "
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
        """Get default processing parameters."""
        return {
            "unit": "hpa",
            "altitude": None,  # No sea-level correction by default
            "decimal_places": 1,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected pressure value range (hPa)."""
        return {"min": self.PRESSURE_MIN, "max": self.PRESSURE_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (same as value range for digital sensor)."""
        return {"min": self.PRESSURE_MIN, "max": self.PRESSURE_MAX}

    # Private helper methods

    def _apply_sea_level_correction(self, pressure: float, altitude: float) -> float:
        """
        Apply sea-level correction to pressure reading.

        Uses simplified barometric formula to convert station pressure to
        sea-level pressure based on altitude.

        Formula: P_sealevel = P_measured / (1 - altitude / 44330) ** 5.255

        Physical Background:
        - Atmospheric pressure decreases ~12 hPa per 100m altitude gain
        - Standard atmosphere model assumes isothermal conditions (15°C)
        - Barometric formula based on hydrostatic equilibrium

        Constants:
        - 44330m: Scale height of Earth's atmosphere
        - 5.255: Adiabatic index (γ/(γ-1) where γ=1.4 for air)

        Numerical Examples:
        - Sea level (0m):     1013.25 hPa → 1013.25 hPa (no change)
        - 500m altitude:      950.0 hPa → ~1008 hPa (realistic sea-level pressure)
        - -50m (below sea):   1020.0 hPa → ~1024 hPa (higher than measured)
        - 3000m (high alt):   ~700 hPa → ~1013 hPa (accuracy degrades)

        Accuracy:
        - Excellent: 0-1000m (±1 hPa error)
        - Good: 1000-3000m (±3 hPa error)
        - Poor: >3000m (temperature effects dominate, use full formula)

        Args:
            pressure: Measured pressure at altitude (hPa)
            altitude: Altitude above sea level (meters)

        Returns:
            Sea-level corrected pressure (hPa)

        Note:
            - For high-accuracy applications >3000m, use full barometric formula
              with actual temperature profile
            - Negative altitudes (below sea level) are supported
        """
        # Barometric formula constants (Standard Atmosphere Model)
        ALTITUDE_CONSTANT = 44330.0  # meters (scale height)
        EXPONENT = 5.255  # adiabatic index

        # Calculate correction factor
        factor = 1 - (altitude / ALTITUDE_CONSTANT)

        # EDGE CASE: Avoid division by zero or negative values
        # factor <= 0 occurs at altitude >= 44330m (edge of atmosphere)
        # In practice: sensor range 300-1100 hPa limits altitude to ~9000m
        if factor <= 0:
            return pressure  # Return uncorrected (extreme altitude)

        # Apply barometric formula
        pressure_sealevel = pressure / (factor**EXPONENT)

        # Clamp to sensor physical range
        # Important: Very high altitudes + correction can exceed sensor max
        pressure_sealevel = max(self.PRESSURE_MIN, min(self.PRESSURE_MAX, pressure_sealevel))

        return pressure_sealevel

    def _convert_unit(self, pressure_hpa: float, unit_type: str) -> tuple[float, str]:
        """
        Convert pressure from hPa to other units.

        Unit Conversion Details:

        1. hPa → Pa (Pascal, SI unit):
           - Conversion: multiply by 100
           - 1 hPa = 100 Pa (exact)
           - Example: 1013.25 hPa = 101325 Pa (standard atmosphere)
           - Use case: Scientific applications, SI-standard compliance

        2. hPa → mmHg (millimeters of mercury):
           - Conversion: multiply by 0.750062
           - 1 hPa = 0.750062 mmHg (based on mercury density at 0°C)
           - Example: 1013.25 hPa ≈ 760 mmHg (standard atmosphere)
           - Use case: Medical applications (blood pressure), meteorology (Europe/Asia)

        3. hPa → inHg (inches of mercury):
           - Conversion: multiply by 0.02953
           - 1 hPa = 0.0295300 inHg (approximated to 0.02953)
           - Example: 1013.25 hPa ≈ 29.92 inHg (standard atmosphere)
           - Use case: Aviation, meteorology (USA)

        Args:
            pressure_hpa: Pressure in hPa (hectopascal, millibar)
            unit_type: "hpa", "pa", "mmhg", "inhg"

        Returns:
            Tuple of (converted_value, unit_string)

        Note:
            - hPa and mbar are equivalent (1 hPa = 1 mbar)
            - Mercury-based units (mmHg, inHg) assume standard gravity and 0°C
        """
        if unit_type == "pa":
            # Pascal = hPa * 100 (exact SI conversion)
            return (pressure_hpa * 100.0, "Pa")
        elif unit_type == "mmhg":
            # mmHg = hPa * 0.750062 (based on mercury density)
            return (pressure_hpa * 0.750062, "mmHg")
        elif unit_type == "inhg":
            # inHg = hPa * 0.02953 (approximation of 0.0295300)
            return (pressure_hpa * 0.02953, "inHg")
        else:
            # Default: hPa (most common unit in meteorology)
            return (pressure_hpa, "hPa")

    def _assess_quality(self, pressure_hpa: float, calibrated: bool) -> str:
        """
        Assess data quality.

        Quality tiers:
        - "good": Within typical atmospheric range (950-1050 hPa)
        - "fair": Valid but outside typical range

        Args:
            pressure_hpa: Pressure value in hPa
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", "error"
        """
        # Error: Outside physical range (shouldn't happen due to clamping)
        if pressure_hpa < self.PRESSURE_MIN or pressure_hpa > self.PRESSURE_MAX:
            return "error"

        # Good: Within typical atmospheric range
        if self.PRESSURE_TYPICAL_MIN <= pressure_hpa <= self.PRESSURE_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical range but valid
        return "fair"


class BMP280TemperatureProcessor(BaseSensorProcessor):
    """
    BMP280 Temperature Sensor Processor.

    Processes temperature readings from BMP280 I2C sensor.

    Features:
    - Offset calibration (optional)
    - Unit conversion (°C, °F, K)
    - Quality assessment

    Note: BMP280 temperature accuracy (±1°C) is lower than dedicated sensors
    like SHT31 (±0.2°C). Use SHT31 for high-accuracy temperature measurements.
    BMP280 temperature is primarily for internal pressure compensation.

    ESP32 Setup:
    - Library: Adafruit_BMP280
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x76 (default) or 0x77
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Temperature sensors are typically used for continuous environmental monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 30  # Read every 30 seconds
    SUPPORTS_ON_DEMAND = False

    # BMP280 Temperature Specifications
    TEMP_MIN = -40.0  # °C (sensor minimum)
    TEMP_MAX = 85.0  # °C (sensor maximum)
    TEMP_TYPICAL_MIN = -20.0  # °C (typical operating range)
    TEMP_TYPICAL_MAX = 85.0  # °C (typical operating range)
    RESOLUTION = 0.01  # °C

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "bmp280_temp"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process BMP280 temperature reading.

        Args:
            raw_value: Temperature in °C (already processed by ESP32 library)
            calibration: Optional calibration data
                - "offset": float - Temperature offset correction (°C)
            params: Optional processing parameters
                - "unit": str - Output unit ("celsius", "fahrenheit", "kelvin")
                - "decimal_places": int - Decimal places for rounding (default: 2)

        Returns:
            ProcessingResult with temperature value, unit, quality assessment

        Example:
            # Basic usage
            result = processor.process(raw_value=23.5)
            # result.value = 23.5, result.unit = "°C"

            # With offset calibration
            result = processor.process(
                raw_value=23.5,
                calibration={"offset": 0.5}
            )
            # result.value = 24.0

            # Fahrenheit conversion
            result = processor.process(
                raw_value=0.0,
                params={"unit": "fahrenheit"}
            )
            # result.value = 32.0, result.unit = "°F"
        """
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="°C",
                quality="error",
                metadata={"error": validation.error},
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
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate BMP280 temperature reading.

        Checks if temperature is within sensor's physical range (-40°C to +85°C).

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

        # Warnings for extreme values
        warnings = []
        if raw_value < self.TEMP_TYPICAL_MIN:
            warnings.append(
                f"Temperature {raw_value}°C below typical range "
                f"(accuracy may be reduced below {self.TEMP_TYPICAL_MIN}°C)"
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        """
        Perform BMP280 temperature calibration.

        BMP280 is factory-calibrated. Simple offset calibration can be performed if needed.

        Args:
            calibration_points: List of calibration points
                [{"raw": 23.5, "reference": 24.0}]
            method: Calibration method ("offset" - only supported)

        Returns:
            Calibration data dict: {"offset": float}

        Raises:
            ValueError: If method is not "offset" or insufficient points
        """
        if len(calibration_points) < 1:
            raise ValueError("BMP280 temperature calibration requires at least 1 point")

        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for BMP280 temperature. "
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
        """Get default processing parameters."""
        return {
            "unit": "celsius",
            "decimal_places": 2,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected temperature value range (Celsius)."""
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (same as value range for digital sensor)."""
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def _assess_quality(self, temp_celsius: float, calibrated: bool) -> str:
        """
        Assess data quality.

        Quality tiers:
        - "good": Within typical operating range (-20°C to 85°C)
        - "fair": Valid but outside typical range

        Args:
            temp_celsius: Temperature in °C
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", "error"
        """
        # Error: Outside physical range
        if temp_celsius < self.TEMP_MIN or temp_celsius > self.TEMP_MAX:
            return "error"

        # Good: Within typical range
        if self.TEMP_TYPICAL_MIN <= temp_celsius <= self.TEMP_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical but valid
        return "fair"
