"""
Moisture Sensor Library - Capacitive Soil Moisture Sensor

Processes raw ADC values from capacitive soil moisture sensors into calibrated
moisture percentage measurements.

Capacitive Soil Moisture Sensor Specifications:
- Measurement Range: 0-100% (relative moisture percentage)
- ADC Range: 0-4095 (ESP32 12-bit ADC)
- Voltage Range: 0-3.3V
- Resolution: ~0.024% per ADC step (12-bit)
- Response Time: < 1 second

Calibration:
- Two-point calibration: Dry (0%) and Wet (100%)
- Dry calibration: Sensor in air (typical ADC ~3200)
- Wet calibration: Sensor in water/saturated soil (typical ADC ~1500)
- Linear mapping: moisture % = (raw - dry) / (wet - dry) * 100

Important Notes:
- ⚠️ ESP32 ADC1 PINS ONLY (GPIO32-39) - ADC2 conflicts with WiFi!
- Some sensors use inverted logic (HIGH voltage = DRY soil)
- Capacitive sensors are more stable than resistive (no corrosion)
- Readings may drift over time - periodic recalibration recommended
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class MoistureSensorProcessor(BaseSensorProcessor):
    """
    Capacitive Soil Moisture Sensor Processor.

    Converts raw ADC values to calibrated moisture percentage using
    two-point linear calibration (dry/wet points).

    Features:
    - Two-point calibration (dry = 0%, wet = 100%)
    - Invert logic support (HIGH voltage = DRY for some sensors)
    - Quality assessment based on value range
    - ADC-to-voltage conversion with clamping (0-100%)

    ESP32 Setup:
    - Sensor: Capacitive Soil Moisture Sensor v1.2 (or compatible)
    - Connection: AOUT → GPIO32-39 (ADC1 pins only!)
    - Power: VCC → 3.3V, GND → GND
    - Hardware: 0.1µF capacitor between AOUT and GND (noise reduction)
    - ADC: 12-bit (0-4095 range)

    Important:
    - ⚠️ Use ADC1 pins ONLY (GPIO32-39) - ADC2 (GPIO0, 2, 4, 12-15, 25-27) conflicts with WiFi!
    - Different soil types affect readings (clay vs sand vs loam)
    - Sensor should not be fully submerged (only sensing pad in soil)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Soil moisture sensors are typically used for continuous monitoring.
    # Slower interval than temperature since soil moisture changes gradually.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 300  # 5 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 60  # Read every 60 seconds
    SUPPORTS_ON_DEMAND = False
    RECOMMENDED_FRESHNESS_HOURS = 2
    RECOMMENDED_CALIBRATION_INTERVAL_DAYS = 90

    # ESP32 ADC configuration
    ADC_MAX = 4095  # 12-bit ADC (ESP32 ADC1: GPIO32-39 only, ADC2 conflicts with WiFi!)
    ADC_VOLTAGE_RANGE = 3.3  # Volts (ESP32 ADC reference voltage)

    # Moisture measurement range (percentage)
    MOISTURE_MIN = 0.0  # % (Dry, sensor in air)
    MOISTURE_MAX = 100.0  # % (Wet/Saturated, sensor in water)

    # Quality assessment thresholds (based on agricultural best practices)
    MOISTURE_TYPICAL_MIN = 20.0  # % (Healthy soil moisture minimum for most plants)
    MOISTURE_TYPICAL_MAX = 80.0  # % (Healthy soil moisture maximum, avoid root rot)
    VERY_DRY_THRESHOLD = 10.0  # % (Very dry, approaching permanent wilting point)
    SATURATED_THRESHOLD = 95.0  # % (Saturated, possible sensor in water or waterlogged soil)

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "moisture"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process raw ADC value into moisture percentage.

        Args:
            raw_value: Raw ADC value (0-4095)
            calibration: Optional calibration data
                - "dry_value": float - ADC value when dry (in air)
                - "wet_value": float - ADC value when wet (in water/saturated)
                - "invert": bool - If set and params omit invert, used for inversion
            params: Optional processing parameters
                - "invert": bool - Invert logic (HIGH voltage = DRY); overrides calibration["invert"]
                - "decimal_places": int - Decimal places for rounding (default: 1)

        Returns:
            ProcessingResult with moisture value, unit "%", quality assessment

        Example:
            # Basic usage without calibration
            result = processor.process(raw_value=2500)
            # Uses default mapping

            # With calibration
            calibration = {"dry_value": 3200, "wet_value": 1500}
            result = processor.process(raw_value=2350, calibration=calibration)
            # moisture = (2350 - 3200) / (1500 - 3200) * 100 = 50%

            # With invert logic (sensor outputs HIGH when DRY)
            result = processor.process(
                raw_value=2500,
                calibration=calibration,
                params={"invert": True}
            )
            # Moisture calculated, then inverted: moisture = 100 - moisture
        """
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="%",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Convert ADC to voltage (for metadata)
        voltage = self._adc_to_voltage(raw_value)

        # Step 3: Apply calibration if available
        if calibration and "dry_value" in calibration and "wet_value" in calibration:
            dry_value = calibration["dry_value"]
            wet_value = calibration["wet_value"]
            moisture = self._adc_to_moisture_calibrated(raw_value, dry_value, wet_value)
            calibrated = True
        else:
            # No calibration - use default linear mapping
            # Default: dry ~3200 ADC, wet ~1500 ADC
            moisture = self._adc_to_moisture_default(raw_value)
            calibrated = False

        # Step 4: Apply invert logic if enabled (HIGH voltage = DRY)
        # params["invert"] overrides calibration["invert"] when both are set.
        invert = False
        if params and "invert" in params:
            invert = bool(params["invert"])
        elif calibration is not None and "invert" in calibration:
            invert = bool(calibration["invert"])
        if invert:
            moisture = 100.0 - moisture

        # Step 5: Clamp to valid range (0-100%)
        moisture = max(self.MOISTURE_MIN, min(self.MOISTURE_MAX, moisture))

        # Step 6: Round to decimal places
        decimal_places = 1  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        moisture = round(moisture, decimal_places)

        # Step 7: Assess quality
        quality = self._assess_quality(moisture, calibrated)

        # Step 8: Return result
        return ProcessingResult(
            value=moisture,
            unit="%",
            quality=quality,
            metadata={
                "voltage": voltage,
                "calibrated": calibrated,
                "inverted": invert,
                "raw_value": raw_value,
                "warnings": validation.warnings,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate raw ADC value.

        Checks if value is within ADC range (0-4095).

        Args:
            raw_value: Raw ADC value

        Returns:
            ValidationResult with validation status
        """
        if raw_value < 0 or raw_value > self.ADC_MAX:
            return ValidationResult(
                valid=False,
                error=f"ADC value {raw_value} out of range (0-{self.ADC_MAX})",
            )

        # Warning if value is near extremes (might indicate sensor issues)
        warnings = []
        if raw_value < 100:
            warnings.append("Very low ADC value (<100) - sensor may be disconnected or in water")
        elif raw_value > 4000:
            warnings.append("Very high ADC value (>4000) - sensor may be disconnected or very dry")

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        Perform two-point moisture calibration.

        Calibration procedure:
        1. Dry calibration: Place sensor in air, record ADC value
        2. Wet calibration: Place sensor in water/saturated soil, record ADC value
        3. Calculate linear mapping: moisture % = (raw - dry) / (wet - dry) * 100

        Args:
            calibration_points: [
                {"raw": 3200, "reference": 0.0},    # Dry (0%)
                {"raw": 1500, "reference": 100.0},  # Wet (100%)
            ]
            method: "linear" (only linear supported for moisture)

        Returns:
            Calibration data dict:
            {
                "dry_value": float,  # ADC value when dry
                "wet_value": float,  # ADC value when wet
                "method": "linear",
                "points": int
            }

        Raises:
            ValueError: If less than 2 points or method not supported
        """
        if len(calibration_points) < 2:
            raise ValueError("Moisture calibration requires at least 2 points (dry/wet)")

        if method != "linear":
            raise ValueError(f"Calibration method '{method}' not supported for moisture")

        # Extract dry and wet points
        # Typically point[0] = dry (0%), point[1] = wet (100%)
        dry_point = None
        wet_point = None

        for point in calibration_points:
            if point["reference"] == 0.0:
                dry_point = point
            elif point["reference"] == 100.0:
                wet_point = point

        # If not explicitly marked, assume first = dry, second = wet
        if dry_point is None or wet_point is None:
            dry_point = calibration_points[0]
            wet_point = calibration_points[1]

        dry_value = dry_point["raw"]
        wet_value = wet_point["raw"]

        return {
            "dry_value": dry_value,
            "wet_value": wet_value,
            "method": "linear",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters."""
        return {
            "invert": False,  # No invert by default
            "decimal_places": 1,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected moisture value range (0-100%)."""
        return {"min": self.MOISTURE_MIN, "max": self.MOISTURE_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected ADC range (0-4095)."""
        return {"min": 0.0, "max": self.ADC_MAX}

    # Private helper methods

    def _adc_to_voltage(self, adc_value: float) -> float:
        """
        Convert ADC value to voltage.

        Args:
            adc_value: Raw ADC value (0-4095)

        Returns:
            Voltage (0-3.3V)
        """
        return (adc_value / self.ADC_MAX) * self.ADC_VOLTAGE_RANGE

    def _adc_to_moisture_calibrated(
        self, adc_value: float, dry_value: float, wet_value: float
    ) -> float:
        """
        Convert ADC to moisture percentage using calibration.

        Linear mapping: moisture % = (raw - dry) / (wet - dry) * 100

        Physical Background:
        - Capacitive sensors: Soil dielectric constant changes with moisture
        - Higher moisture → lower capacitance → lower ADC value (typically)
        - Linear relationship assumed (good approximation 0-100% range)

        Calibration Points:
        - Dry (0%): Sensor in air (typical ADC: 3000-3500)
        - Wet (100%): Sensor in water/saturated soil (typical ADC: 1000-1500)

        Numerical Example:
        - dry_value = 3200, wet_value = 1500, adc = 2350
        - moisture = (2350 - 3200) / (1500 - 3200) * 100 = (-850) / (-1700) * 100 = 50%

        Args:
            adc_value: Raw ADC value (0-4095 for 12-bit)
            dry_value: ADC value when dry (in air)
            wet_value: ADC value when wet (in water/saturated)

        Returns:
            Moisture percentage (0-100%)

        Note:
            - Result can be <0% or >100% if adc_value outside calibration range
            - Caller (process()) clamps to [0, 100] after this function
        """
        # EDGE CASE: Division by zero protection
        # Occurs if dry_value == wet_value (invalid calibration)
        # This should never happen in practice, but protects against:
        # - User error (same value for both calibration points)
        # - Sensor malfunction (stuck ADC reading)
        if dry_value == wet_value:
            # Return 50% (middle value) as safe fallback
            # Rationale: Better than crash, signals "unknown" moisture
            # Quality assessment will mark this as "poor" due to uncalibrated flag
            return 50.0

        # Linear interpolation between dry (0%) and wet (100%)
        # Note: For capacitive sensors, dry_value > wet_value (inverted)
        moisture = ((adc_value - dry_value) / (wet_value - dry_value)) * 100.0

        return moisture

    def _adc_to_moisture_default(self, adc_value: float) -> float:
        """
        Convert ADC to moisture percentage using default mapping (no calibration).

        Default calibration values (typical for capacitive sensors):
        - Dry (in air): 3200 ADC → 0%
        - Wet (in water): 1500 ADC → 100%

        Args:
            adc_value: Raw ADC value

        Returns:
            Moisture percentage (0-100%)
        """
        DEFAULT_DRY_VALUE = 3200.0
        DEFAULT_WET_VALUE = 1500.0

        moisture = (
            (adc_value - DEFAULT_DRY_VALUE) / (DEFAULT_WET_VALUE - DEFAULT_DRY_VALUE)
        ) * 100.0

        return moisture

    def _assess_quality(self, moisture: float, calibrated: bool) -> str:
        """
        Assess data quality based on moisture percentage and calibration status.

        Quality Assessment Logic:

        Quality Tiers:
        - "error": Outside physical range 0-100% (should never happen due to clamping)
        - "poor": Very dry (<10%) or saturated (>95%) - possible sensor issues
        - "good": Healthy soil moisture (20-80%) - optimal plant growth range
        - "fair": Marginal range (10-20% or 80-95%) - acceptable but not optimal

        Agricultural Context:
        - 20-80%: Optimal range for most plants (good root aeration + water availability)
        - 10-20%: Approaching wilting point (plants start to stress)
        - 80-95%: High moisture (possible root rot risk for some plants)
        - <10%: Very dry (sensor possibly disconnected or in air)
        - >95%: Saturated (sensor possibly in water, not soil)

        Calibration Impact:
        - Calibrated sensors: More reliable readings → affects quality tier
        - Uncalibrated: Uses default mapping (±10% accuracy) → may affect interpretation

        Args:
            moisture: Moisture percentage (0-100%)
            calibrated: Whether 2-point calibration was applied

        Returns:
            Quality string: "good", "fair", "poor", "error"

        Examples:
            - 45%, calibrated=True → "good" (optimal range)
            - 15%, calibrated=True → "fair" (approaching dry)
            - 5%, calibrated=False → "poor" (very dry, uncalibrated)
            - 98%, calibrated=True → "poor" (saturated, possible sensor in water)
        """
        # Error: Outside physical range (shouldn't happen due to clamping in process())
        if moisture < self.MOISTURE_MIN or moisture > self.MOISTURE_MAX:
            return "error"

        # Poor: Very dry or saturated (possible sensor malfunction or extreme conditions)
        if moisture < self.VERY_DRY_THRESHOLD or moisture > self.SATURATED_THRESHOLD:
            return "poor"

        # Good: Within typical healthy soil moisture range (optimal for most plants)
        if self.MOISTURE_TYPICAL_MIN <= moisture <= self.MOISTURE_TYPICAL_MAX:
            return "good"

        # Fair: Outside typical range but still valid (marginal conditions)
        return "fair"
