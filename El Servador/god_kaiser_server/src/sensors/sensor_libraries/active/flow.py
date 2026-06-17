"""
Flow Sensor Library: Processing, Validation, Calibration

Supports:
- YFS201: Hall-effect flow sensor (pulses per liter)
- Generic: Pulse-based flow sensors
"""

import logging
from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


logger = logging.getLogger(__name__)


class FlowProcessor(BaseSensorProcessor):
    """
    Flow Sensor Processor (YFS201, Generic).

    Supports:
    - YFS201: Hall-effect flow sensor (pulses per liter)
    - Generic: Pulse-based flow sensors
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # Flow sensors are typically used for continuous monitoring during irrigation.
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180  # 3 minutes timeout
    RECOMMENDED_INTERVAL_SECONDS = 10  # Read every 10 seconds (faster for flow monitoring)
    SUPPORTS_ON_DEMAND = False

    # Sensor Specifications
    FS300A_PULSES_PER_LITER = 330  # FS300A G3/4 default (YFS201 was 450)
    GENERIC_MIN_FLOW = 0.0  # L/min
    GENERIC_MAX_FLOW = 30.0  # L/min (typical max for small pumps)

    # Typical ranges
    TYPICAL_MIN_FLOW = 0.0  # L/min (no flow)
    TYPICAL_MAX_FLOW = 20.0  # L/min (typical max for irrigation)

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "flow"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process flow sensor raw value.

        Args:
            raw_value: Raw pulse count or frequency (Hz) or flow rate (L/min)
            calibration: Optional calibration data
                - "pulses_per_liter": float - Pulses per liter (default: 330 for FS300A)
                - "sensor_model": str - "fs300a", "yfs201" or "generic"
            params: Optional processing parameters
                - "sensor_model": str - Sensor model ("fs300a", "yfs201" or "generic")
                - "pulses_per_liter": float - Pulses per liter (overrides calibration)
                - "input_type": str - "pulses", "frequency", or "flow_rate" (default: "pulses")
                - "time_window": float - Time window in seconds for pulse counting (default: 1.0)
                - "decimal_places": int - Decimal places for rounding (default: 2)

        Returns:
            ProcessingResult with flow value in L/min, quality assessment
        """
        # Determine sensor model
        sensor_model = None
        if params:
            sensor_model = params.get("sensor_model", "").lower()
        if calibration and not sensor_model:
            sensor_model = calibration.get("sensor_model", "").lower()

        # Get calibration factor
        calibration_factor = self.FS300A_PULSES_PER_LITER  # Default
        if calibration and "pulses_per_liter" in calibration:
            calibration_factor = calibration.get("pulses_per_liter", calibration_factor)
        if params and "pulses_per_liter" in params:
            calibration_factor = params.get("pulses_per_liter", calibration_factor)

        # Determine input type
        input_type = params.get("input_type", "pulses") if params else "pulses"
        time_window = params.get("time_window") if params else None

        # Convert raw value to flow rate (L/min)
        if input_type == "pulses":
            # Raw value is pulse count over time_window seconds
            # Flow rate = (pulses / calibration_factor) / (time_window / 60) L/min
            if time_window is None:
                logger.warning(
                    "FlowProcessor: time_window not in params — pulse count cannot be "
                    "time-normalized (window_ms missing from MQTT payload). "
                    "Returning quality=error."
                )
                return ProcessingResult(
                    value=0.0,
                    unit="L/min",
                    quality="error",
                    metadata={"error": "time_window_missing"},
                )
            if time_window > 0:
                liters = raw_value / calibration_factor
                flow_rate = liters / (time_window / 60.0)  # Convert to L/min
            else:
                flow_rate = 0.0
        elif input_type == "frequency":
            # Raw value is frequency in Hz (pulses per second)
            # Flow rate = (frequency * 60) / calibration_factor L/min
            flow_rate = (raw_value * 60.0) / calibration_factor
        elif input_type == "flow_rate":
            # Raw value is already flow rate in L/min
            flow_rate = raw_value
        else:
            return ProcessingResult(
                value=0.0,
                unit="L/min",
                quality="error",
                metadata={"error": f"Unknown input_type: {input_type}"},
            )

        # Ensure value is non-negative
        flow_rate = max(0.0, flow_rate)

        # Round if specified
        decimal_places = 2
        if params and "decimal_places" in params:
            decimal_places = params.get("decimal_places", 2)
        flow_rate = round(flow_rate, decimal_places)

        # Validate
        validation = self.validate(flow_rate)
        if not validation.valid:
            return ProcessingResult(
                value=flow_rate,
                unit="L/min",
                quality="error",
                metadata={"error": validation.error},
            )

        # Determine quality
        quality = self._assess_quality(flow_rate)

        return ProcessingResult(
            value=flow_rate,
            unit="L/min",
            quality=quality,
            metadata={
                "sensor_model": sensor_model or "unknown",
                "raw_value": raw_value,
                "pulses_per_liter": calibration_factor,
                "input_type": input_type,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate flow sensor value.

        Args:
            raw_value: Flow rate in L/min

        Returns:
            ValidationResult indicating validity
        """
        # Check for negative values
        if raw_value < 0:
            return ValidationResult(
                valid=False,
                error=f"Flow value cannot be negative: {raw_value} L/min",
            )

        # Check reasonable upper limit (100 L/min is very high for typical applications)
        if raw_value > 100:
            return ValidationResult(
                valid=False,
                error=f"Flow value exceeds maximum: {raw_value} L/min > 100 L/min",
            )

        # Check typical range and provide warnings
        warnings = []
        if raw_value > self.TYPICAL_MAX_FLOW:
            warnings.append(
                f"Flow value above typical maximum: {raw_value} L/min > {self.TYPICAL_MAX_FLOW} L/min"
            )

        return ValidationResult(
            valid=True,
            warnings=warnings if warnings else None,
        )

    def _assess_quality(self, value: float) -> str:
        """
        Assess flow reading quality.

        Args:
            value: Flow value in L/min

        Returns:
            Quality indicator ("excellent", "good", "fair", "poor", "bad")
        """
        if value == 0.0:
            return "good"  # No flow is valid
        elif value < 0.1:
            return "fair"  # Very low flow, may be noise
        elif value < 1.0:
            return "good"  # Low flow, normal for drip irrigation
        elif value < 10.0:
            return "excellent"  # Normal flow range
        elif value < 20.0:
            return "good"  # High flow, still acceptable
        else:
            return "fair"  # Very high flow, may indicate issue or high-capacity system

    def get_value_range(self) -> Dict[str, float]:
        """Get expected flow value range."""
        return {"min": self.TYPICAL_MIN_FLOW, "max": self.TYPICAL_MAX_FLOW}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw flow value range."""
        return {"min": 0.0, "max": 100.0}
