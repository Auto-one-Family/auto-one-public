"""
pH Sensor Library - Reference Implementation

Processes raw ADC values from analog pH sensors into calibrated pH measurements.

Typical pH sensor output:
- ADC range: 0-4095 (ESP32 12-bit ADC)
- Voltage range: 0-3.3V
- pH range: 0-14
- Neutral pH (7.0) typically corresponds to ~1.5V (ADC ~1860)

Calibration:
- Two-point calibration using pH 4.0 and pH 7.0 buffer solutions
- Calculates slope and offset for linear conversion
- Optional temperature compensation
"""

from typing import Any, Dict, Optional

from ...adc_normalization import (
    ADC_SOURCE_ADS1115,
    ADC_SOURCE_INTERNAL,
    raw_to_voltage,
    resolve_adc_descriptor,
)
from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class PHSensorProcessor(BaseSensorProcessor):
    """
    pH sensor processor for analog pH sensors.

    Converts raw ADC values to calibrated pH measurements using
    two-point linear calibration.

    Features:
    - Two-point calibration (pH 4.0 and pH 7.0 buffers)
    - Temperature compensation (optional)
    - Quality assessment based on value range and calibration status
    - Voltage-to-pH conversion
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # SEN0169-V2 is designed for 24/7 continuous operation in nutrient solution.
    # Ag/AgCl reference electrode loses KCl gel over time in ion-rich solutions
    # (KCl depletion); recommended maintenance interval: every 14 days in
    # hydroponics. Stagger EC at 35 s to avoid measurement overlap — the EC
    # HF-signal disturbs the pH measurement chain (DFR0504 isolator recommended
    # for simultaneous pH/EC deployments, per DFRobot documentation).
    RECOMMENDED_MODE = "on_demand"  # AUT-685: electrode drift under continuous operation
    RECOMMENDED_TIMEOUT_SECONDS = 0  # No timeout for on-demand sensors
    RECOMMENDED_INTERVAL_SECONDS = 30  # Measurement interval when triggered on demand
    SUPPORTS_ON_DEMAND = True
    RECOMMENDED_FRESHNESS_HOURS = 24
    RECOMMENDED_CALIBRATION_INTERVAL_DAYS = 14  # KCl depletion risk in hydroponics

    # ESP32 ADC configuration
    ADC_MAX = 4095  # 12-bit ADC (internal ESP32)
    ADC_VOLTAGE_RANGE = 3.3  # Volts
    ADC_MAX_16BIT = 32767  # ADS1115 16-bit single-ended max count

    # pH sensor range
    PH_MIN = 0.0
    PH_MAX = 14.0

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "ph"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process raw ADC value into pH measurement.

        Args:
            raw_value: Raw ADC value (0-4095)
            calibration: {"slope": float, "offset": float}
            params: {"temperature_compensation": float (°C), "decimal_places": int}

        Returns:
            ProcessingResult with pH value, unit "pH", quality
        """
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="pH",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Convert ADC to voltage (source-aware: internal 12-bit or ADS1115
        # PGA-exact). The acquisition source/pga is carried in the calibration data.
        adc_source, pga_gain = resolve_adc_descriptor(calibration)
        voltage = self._adc_to_voltage(raw_value, adc_source=adc_source, pga_gain=pga_gain)

        # Step 3: Apply calibration if available
        if calibration and "slope" in calibration and "offset" in calibration:
            slope = calibration["slope"]
            offset = calibration["offset"]
            ph_value = self._voltage_to_ph_calibrated(voltage, slope, offset)
            calibrated = True
        else:
            # No calibration - use default conversion (neutral pH at 1.5V)
            ph_value = self._voltage_to_ph_default(voltage)
            calibrated = False

        # Step 4: Temperature compensation (optional)
        if params and "temperature_compensation" in params:
            temp = params["temperature_compensation"]
            ph_value = self._apply_temperature_compensation(ph_value, temp)

        # Step 5: Round to decimal places
        decimal_places = 2  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        ph_value = round(ph_value, decimal_places)

        # Step 6: Assess quality
        quality = self._assess_quality(ph_value, calibrated)

        # Step 7: Return result
        metadata = {
            "voltage": voltage,
            "calibrated": calibrated,
            "raw_value": raw_value,
            "adc_source": adc_source,
        }
        if adc_source == ADC_SOURCE_ADS1115 and pga_gain is not None:
            metadata["pga_gain"] = pga_gain
        return ProcessingResult(
            value=ph_value,
            unit="pH",
            quality=quality,
            metadata=metadata,
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate raw ADC value with automatic 12-bit/16-bit detection.

        Checks if value is within ADC range (0-4095 for internal 12-bit ESP32 ADC
        or 0-32767 for the external ADS1115 16-bit ADC). If a value exceeds the
        12-bit max it is assumed to come from a 16-bit ADC.
        """
        max_value = self.ADC_MAX_16BIT if raw_value > self.ADC_MAX else self.ADC_MAX
        if raw_value < 0 or raw_value > max_value:
            return ValidationResult(
                valid=False,
                error=f"Raw value {raw_value} out of range (0-{max_value})",
            )

        # Warning if value is near extremes (might be out of pH sensor range)
        warnings = []
        if raw_value < 100:
            warnings.append(
                "Value very low — Ag/AgCl reference electrode exhausted or KCl gel depleted "
                "(SEN0169-V2: refill/replace electrode; verify wiring if sensor is new)"
            )
        elif raw_value > (max_value - 95):
            warnings.append("Value very high - check sensor connection")

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform two-point pH calibration.

        Args:
            calibration_points: [
                {"raw": 2150, "reference": 7.0},  # pH 7.0 buffer
                {"raw": 1800, "reference": 4.0},  # pH 4.0 buffer
            ]
            method: "linear" (only linear supported for pH)

        Returns:
            {"slope": float, "offset": float}
        """
        if len(calibration_points) < 2:
            raise ValueError("pH calibration requires at least 2 points")

        if method != "linear":
            raise ValueError(f"Calibration method '{method}' not supported for pH")

        # Extract points
        point1 = calibration_points[0]
        point2 = calibration_points[1]

        raw1 = point1["raw"]
        ph1 = point1["reference"]

        raw2 = point2["raw"]
        ph2 = point2["reference"]

        # Convert ADC to voltage (not im Produktiv-Pfad / reine Konsolidierung auf adc_normalization)
        voltage1 = self._adc_to_voltage(raw1, adc_source=adc_source, pga_gain=pga_gain)
        voltage2 = self._adc_to_voltage(raw2, adc_source=adc_source, pga_gain=pga_gain)

        # Calculate slope and offset
        # pH = slope * voltage + offset
        slope = (ph2 - ph1) / (voltage2 - voltage1)
        offset = ph1 - (slope * voltage1)

        return {
            "slope": slope,
            "offset": offset,
            "method": "linear",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters."""
        return {
            "temperature_compensation": None,  # No temp compensation by default
            "decimal_places": 2,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected pH value range (0-14)."""
        return {"min": self.PH_MIN, "max": self.PH_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected ADC range (0-4095)."""
        return {"min": 0.0, "max": self.ADC_MAX}

    # Private helper methods

    def _adc_to_voltage(
        self,
        adc_value: float,
        adc_source: str = ADC_SOURCE_INTERNAL,
        pga_gain: Optional[str] = None,
    ) -> float:
        """
        Convert ADC value to voltage via the shared normalization.

        Args:
            adc_value: Raw ADC value (0-4095 internal, 0-32767 ADS1115)
            adc_source: "internal" (ESP32 12-bit, 0-3.3V) or "ads1115" (PGA-exact)
            pga_gain: ADS1115 PGA gain (only for adc_source="ads1115")

        Returns:
            Voltage in volts
        """
        return raw_to_voltage(adc_value, adc_source=adc_source, pga_gain=pga_gain)

    def _voltage_to_ph_calibrated(self, voltage: float, slope: float, offset: float) -> float:
        """
        Convert voltage to pH using calibration.

        Args:
            voltage: Voltage (0-3.3V)
            slope: Calibration slope
            offset: Calibration offset

        Returns:
            pH value (0-14)
        """
        ph = slope * voltage + offset

        # Clamp to valid pH range
        ph = max(self.PH_MIN, min(self.PH_MAX, ph))

        return ph

    def _voltage_to_ph_default(self, voltage: float) -> float:
        """
        Convert voltage to pH using default conversion (no calibration).

        Assumes neutral pH (7.0) at 1.5V.
        Slope approximately -3.5 pH/V (typical for pH sensors).

        Args:
            voltage: Voltage (0-3.3V)

        Returns:
            pH value (0-14)
        """
        # Default calibration: pH 7.0 at 1.5V, slope -3.5
        NEUTRAL_VOLTAGE = 1.5
        DEFAULT_SLOPE = -3.5

        ph = 7.0 + DEFAULT_SLOPE * (voltage - NEUTRAL_VOLTAGE)

        # Clamp to valid pH range
        ph = max(self.PH_MIN, min(self.PH_MAX, ph))

        return ph

    def _apply_temperature_compensation(self, ph: float, temperature: float) -> float:
        """
        Apply temperature compensation to pH reading.

        pH electrodes are temperature-sensitive. This compensates for
        temperature effects (typically 0.003 pH/°C deviation from 25°C).

        Args:
            ph: pH value at measured temperature
            temperature: Temperature in °C

        Returns:
            Temperature-compensated pH value
        """
        REFERENCE_TEMP = 25.0  # °C
        TEMP_COEFFICIENT = 0.003  # pH/°C

        temp_difference = temperature - REFERENCE_TEMP
        compensation = temp_difference * TEMP_COEFFICIENT * (7.0 - ph)

        ph_compensated = ph + compensation

        # Clamp to valid range
        ph_compensated = max(self.PH_MIN, min(self.PH_MAX, ph_compensated))

        return ph_compensated

    def _assess_quality(self, ph_value: float, calibrated: bool) -> str:
        """
        Assess data quality.

        Args:
            ph_value: Calculated pH value
            calibrated: Whether calibration was applied

        Returns:
            Quality string: "good", "fair", "poor", "error"
        """
        # Check if pH is within expected range
        if ph_value < self.PH_MIN or ph_value > self.PH_MAX:
            return "error"

        # Good quality: calibrated and within typical range (3-11)
        if calibrated and 3.0 <= ph_value <= 11.0:
            return "good"

        # Fair quality: calibrated but at extremes, or not calibrated but reasonable
        if calibrated or (4.0 <= ph_value <= 10.0):
            return "fair"

        # Poor quality: not calibrated and at extremes
        return "poor"
