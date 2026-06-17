"""
CO2 Sensor Library: Processing, Validation, Calibration

Supports:
- MHZ19: UART-based CO2 sensor (0-5000 ppm)
- SCD30: I2C CO2 sensor (400-10000 ppm)
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class CO2Processor(BaseSensorProcessor):
    """
    CO2 Sensor Processor (MHZ19, SCD30).

    Supports:
    - MHZ19: UART-based CO2 sensor (0-5000 ppm)
    - SCD30: I2C CO2 sensor (400-10000 ppm)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # CO2 sensors are typically used for continuous air quality monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 30  # Read every 30 seconds
    SUPPORTS_ON_DEMAND = False

    # Sensor Specifications
    MHZ19_MIN = 0.0  # ppm
    MHZ19_MAX = 5000.0  # ppm
    SCD30_MIN = 400.0  # ppm
    SCD30_MAX = 10000.0  # ppm

    # Typical ranges
    TYPICAL_MIN = 400.0  # ppm (outdoor air)
    TYPICAL_MAX = 2000.0  # ppm (indoor air, acceptable)

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "co2"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process CO2 sensor raw value.

        Args:
            raw_value: Raw CO2 reading in ppm
            calibration: Optional calibration data
                - "offset": float - CO2 offset correction (ppm)
                - "sensor_model": str - "mhz19" or "scd30" (for range validation)
            params: Optional processing parameters
                - "sensor_model": str - Sensor model ("mhz19" or "scd30")
                - "decimal_places": int - Decimal places for rounding (default: 0)

        Returns:
            ProcessingResult with CO2 value in ppm, quality assessment
        """
        # Determine sensor model
        sensor_model = None
        if params:
            sensor_model = params.get("sensor_model", "").lower()
        if calibration and not sensor_model:
            sensor_model = calibration.get("sensor_model", "").lower()

        # Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=raw_value,
                unit="ppm",
                quality="error",
                metadata={"error": validation.error},
            )

        # Apply calibration offset if provided
        value = raw_value
        if calibration and "offset" in calibration:
            offset = calibration.get("offset", 0.0)
            value = raw_value + offset

        # Round if specified
        decimal_places = 0
        if params and "decimal_places" in params:
            decimal_places = params.get("decimal_places", 0)
        value = round(value, decimal_places)

        # Determine quality
        quality = self._assess_quality(value)

        return ProcessingResult(
            value=value,
            unit="ppm",
            quality=quality,
            metadata={
                "sensor_model": sensor_model or "unknown",
                "raw_value": raw_value,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate CO2 sensor raw value.

        Args:
            raw_value: Raw CO2 reading in ppm

        Returns:
            ValidationResult indicating validity
        """
        # Check for negative values
        if raw_value < 0:
            return ValidationResult(
                valid=False,
                error=f"CO2 value cannot be negative: {raw_value} ppm",
            )

        # Check reasonable upper limit (10,000 ppm is very high)
        if raw_value > 10000:
            return ValidationResult(
                valid=False,
                error=f"CO2 value exceeds maximum: {raw_value} ppm > 10000 ppm",
            )

        # Check typical range and provide warnings
        warnings = []
        if raw_value < self.TYPICAL_MIN:
            warnings.append(
                f"CO2 value below typical minimum: {raw_value} ppm < {self.TYPICAL_MIN} ppm"
            )
        elif raw_value > self.TYPICAL_MAX:
            warnings.append(
                f"CO2 value above typical maximum: {raw_value} ppm > {self.TYPICAL_MAX} ppm"
            )

        return ValidationResult(
            valid=True,
            warnings=warnings if warnings else None,
        )

    def _assess_quality(self, value: float) -> str:
        """
        Assess CO2 reading quality.

        Args:
            value: CO2 value in ppm

        Returns:
            Quality indicator ("excellent", "good", "fair", "poor", "bad")
        """
        if value < 400:
            return "excellent"  # Very fresh air
        elif value < 1000:
            return "good"  # Good indoor air quality
        elif value < 1500:
            return "fair"  # Acceptable but not ideal
        elif value < 2000:
            return "poor"  # Poor air quality, ventilation needed
        else:
            return "bad"  # Very poor air quality

    def get_value_range(self) -> Dict[str, float]:
        """Get expected CO2 value range."""
        return {"min": self.TYPICAL_MIN, "max": self.TYPICAL_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw CO2 value range."""
        return {"min": 0.0, "max": 10000.0}
