"""
Light Sensor Library: Processing, Validation, Calibration

Supports:
- TSL2561: I2C lux sensor (0-40000 lux)
- BH1750: I2C lux sensor (1-65535 lux)
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class LightProcessor(BaseSensorProcessor):
    """
    Light Sensor Processor (TSL2561, BH1750).

    Supports:
    - TSL2561: I2C lux sensor (0-40000 lux)
    - BH1750: I2C lux sensor (1-65535 lux)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Light sensors are typically used for continuous environmental monitoring.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 60  # Read every 60 seconds (light changes slowly)
    SUPPORTS_ON_DEMAND = False

    # Sensor Specifications
    TSL2561_MIN = 0.0  # lux
    TSL2561_MAX = 40000.0  # lux
    BH1750_MIN = 1.0  # lux
    BH1750_MAX = 65535.0  # lux

    # Typical ranges (indoor/outdoor)
    TYPICAL_INDOOR_MIN = 50.0  # lux (dim indoor)
    TYPICAL_INDOOR_MAX = 1000.0  # lux (bright indoor)
    TYPICAL_OUTDOOR_MIN = 10000.0  # lux (overcast)
    TYPICAL_OUTDOOR_MAX = 100000.0  # lux (bright sunlight)

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "light"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process light sensor raw value.

        Args:
            raw_value: Raw lux reading
            calibration: Optional calibration data
                - "offset": float - Light offset correction (lux)
                - "sensor_model": str - "tsl2561" or "bh1750" (for range validation)
            params: Optional processing parameters
                - "sensor_model": str - Sensor model ("tsl2561" or "bh1750")
                - "decimal_places": int - Decimal places for rounding (default: 0)

        Returns:
            ProcessingResult with light value in lux, quality assessment
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
                unit="lux",
                quality="error",
                metadata={"error": validation.error},
            )

        # Apply calibration offset if provided
        value = raw_value
        if calibration and "offset" in calibration:
            offset = calibration.get("offset", 0.0)
            value = raw_value + offset

        # Ensure value is non-negative
        value = max(0.0, value)

        # Round if specified
        decimal_places = 0
        if params and "decimal_places" in params:
            decimal_places = params.get("decimal_places", 0)
        value = round(value, decimal_places)

        # Determine quality
        quality = self._assess_quality(value)

        return ProcessingResult(
            value=value,
            unit="lux",
            quality=quality,
            metadata={
                "sensor_model": sensor_model or "unknown",
                "raw_value": raw_value,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate light sensor raw value.

        Args:
            raw_value: Raw light reading in lux

        Returns:
            ValidationResult indicating validity
        """
        # Check for negative values
        if raw_value < 0:
            return ValidationResult(
                valid=False,
                error=f"Light value cannot be negative: {raw_value} lux",
            )

        # Check reasonable upper limit (100,000 lux is very bright sunlight)
        if raw_value > 100000:
            return ValidationResult(
                valid=False,
                error=f"Light value exceeds maximum: {raw_value} lux > 100000 lux",
            )

        # Check typical range and provide warnings
        warnings = []
        if raw_value < self.TYPICAL_INDOOR_MIN:
            warnings.append(
                f"Light value very low (dim): {raw_value} lux < {self.TYPICAL_INDOOR_MIN} lux"
            )
        elif raw_value > self.TYPICAL_OUTDOOR_MAX:
            warnings.append(
                f"Light value very high (bright): {raw_value} lux > {self.TYPICAL_OUTDOOR_MAX} lux"
            )

        return ValidationResult(
            valid=True,
            warnings=warnings if warnings else None,
        )

    def _assess_quality(self, value: float) -> str:
        """
        Assess light reading quality.

        Args:
            value: Light value in lux

        Returns:
            Quality indicator ("excellent", "good", "fair", "poor", "bad")
        """
        if value < 50:
            return "poor"  # Very dim, may indicate sensor issue or night
        elif value < 200:
            return "fair"  # Dim indoor lighting
        elif value < 1000:
            return "good"  # Normal indoor lighting
        elif value < 10000:
            return "excellent"  # Bright indoor or overcast outdoor
        elif value < 100000:
            return "excellent"  # Bright outdoor
        else:
            return "bad"  # Extremely bright, may indicate sensor saturation

    def get_value_range(self) -> Dict[str, float]:
        """Get expected light value range."""
        return {"min": self.TYPICAL_INDOOR_MIN, "max": self.TYPICAL_OUTDOOR_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw light value range."""
        return {"min": 0.0, "max": 100000.0}
