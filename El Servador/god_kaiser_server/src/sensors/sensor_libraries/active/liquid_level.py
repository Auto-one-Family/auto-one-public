"""
Liquid Level Sensor Library: Processing, Validation

Supports:
- XKC-Y26S-PNP: Capacitive non-contact liquid level switch (PNP, active_high)
- XKC-Y25-NPN: Capacitive non-contact liquid level switch (NPN, active_low)

Polarity is resolved in firmware (config field "polarity") — this processor
always receives a semantically normalized binary value (1 = liquid detected,
0 = no contact), independent of the sensor's electrical polarity.
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class LiquidLevelProcessor(BaseSensorProcessor):
    """
    Liquid Level Switch Processor (XKC-Y26S-PNP, XKC-Y25-NPN).

    Binary passthrough: raw_value 0.0 or 1.0 is both a valid state
    (no calibration, no unit conversion).
    """

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "liquid_level"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process liquid level switch raw value.

        Args:
            raw_value: Binary state from firmware (0.0 = no contact, 1.0 = detected)
            calibration: Unused (no calibration for a binary switch)
            params: Unused

        Returns:
            ProcessingResult with unchanged binary value, quality="good"
        """
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=raw_value,
                unit="",
                quality="error",
                metadata={"error": validation.error},
            )

        return ProcessingResult(
            value=float(raw_value),
            unit="",
            quality="good",
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate liquid level switch raw value.

        Args:
            raw_value: Binary state (must be 0.0 or 1.0)

        Returns:
            ValidationResult indicating validity
        """
        if raw_value not in (0.0, 1.0):
            return ValidationResult(
                valid=False,
                error=f"Liquid level value must be 0 or 1, got: {raw_value}",
            )

        return ValidationResult(valid=True)

    def get_value_range(self) -> Dict[str, float]:
        """Get expected liquid level value range."""
        return {"min": 0.0, "max": 1.0}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw liquid level value range."""
        return {"min": 0.0, "max": 1.0}
