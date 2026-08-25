"""
EC (Electrical Conductivity) Sensor Library

Processes raw ADC values from analog EC sensors into calibrated electrical conductivity
measurements with temperature compensation and unit conversion.

EC Sensor Specifications:
- Measurement Range: 0-20000 µS/cm (0-20 mS/cm)
- ADC Range: 0-4095 (ESP32 12-bit ADC) or 0-32767 (ADS1115 16-bit)
- Voltage Range: 0-3.3V (ESP32) or 0-5V (ADS1115)
- Resolution: ~4.88 µS/cm per ADC step (12-bit ESP32)
- Temperature Dependency: ~2% per °C deviation from 25°C

Calibration:
- Two-point calibration using KCl buffer solutions
- Low point: 1413 µS/cm (0.01 M KCl at 25°C)
- High point: 12880 µS/cm (0.1 M KCl at 25°C)
- Linear conversion: EC = slope * voltage + offset

Temperature Compensation:
- Reference temperature: 25°C
- Formula: EC_25C = EC_raw / (1 + 0.02 * (T - 25))
- Coefficient: 2% per °C

Important Notes:
- ⚠️ ESP32 ADC1 PINS ONLY (GPIO32-39) - ADC2 conflicts with WiFi!
- ESP32 ADC accuracy: ±10% (consider using external ADS1115 for precision)
- Temperature compensation is critical for accuracy
- Calibration must be performed at known temperature (ideally 25°C)
"""

from typing import Any, Dict, Optional

from ...adc_normalization import (
    ADC_SOURCE_ADS1115,
    ADC_SOURCE_INTERNAL,
    DEFAULT_PGA_GAIN,
    raw_to_voltage,
    resolve_adc_descriptor,
)
from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)

# TDS (ppm) approximation: TDS_ppm ≈ EC_µS/cm * EC_TO_TDS_PPM_FACTOR.
EC_TO_TDS_PPM_FACTOR = 0.5  # NaCl approximation; range 0.47–0.70 depending on solution type


class ECSensorProcessor(BaseSensorProcessor):
    """
    Electrical Conductivity (EC) Sensor Processor.

    Converts raw ADC values to calibrated EC measurements using
    two-point linear calibration with temperature compensation.

    Features:
    - Two-point calibration (1413 µS/cm and 12880 µS/cm buffers)
    - Temperature compensation (~2% per °C)
    - Unit conversion (µS/cm, mS/cm, ppm)
    - Quality assessment based on value range and calibration status
    - Support for 12-bit (ESP32) and 16-bit (ADS1115) ADC

    ESP32 Setup:
    - Sensor: DFRobot Gravity EC Sensor (or compatible)
    - Connection: AOUT → GPIO32-39 (ADC1 pins only!)
    - Power: VCC → 3.3V or 5V, GND → GND
    - Hardware: 0.1µF capacitor between AOUT and GND (noise reduction)
    - Optional: ADS1115 16-bit ADC for better accuracy

    Important:
    - ⚠️ Use ADC1 pins ONLY (GPIO32-39) - ADC2 conflicts with WiFi!
    - Temperature compensation is CRITICAL for accurate readings
    - Calibrate at 25°C or apply temperature compensation
    - Different water types affect readings (freshwater vs seawater)
    """

    # =========================================================================
    # OPERATING MODE RECOMMENDATIONS (Phase 2A)
    # =========================================================================
    # DFR0300 is designed for continuous operation. Use a 5 s stagger after the
    # pH 30 s interval to prevent the EC HF-signal from disturbing the pH
    # measurement chain. For simultaneous pH/EC deployments a DFR0504 signal
    # isolator is recommended (per DFRobot documentation on shared nutrient
    # solution interference).
    RECOMMENDED_MODE = "on_demand"  # AUT-685: electrode drift under continuous operation
    RECOMMENDED_TIMEOUT_SECONDS = 0  # No timeout for on-demand sensors
    RECOMMENDED_INTERVAL_SECONDS = 35  # 5 s stagger after pH 30 s interval when triggered
    SUPPORTS_ON_DEMAND = True
    RECOMMENDED_FRESHNESS_HOURS = 24
    RECOMMENDED_CALIBRATION_INTERVAL_DAYS = 30

    # ESP32 ADC configuration
    ADC_MAX_12BIT = 4095  # ESP32 12-bit ADC (0-3.3V)
    ADC_MAX_16BIT = 32767  # ADS1115 16-bit ADC (0-5V, for precision applications)
    ADC_VOLTAGE_RANGE_3V3 = 3.3  # ESP32 ADC voltage range
    ADC_VOLTAGE_RANGE_5V = 5.0  # ADS1115 ADC voltage range (optional external ADC)

    # EC measurement range (microSiemens per centimeter)
    EC_MIN = 0.0  # µS/cm (pure water, distilled water ~0.5 µS/cm)
    EC_MAX = 20000.0  # µS/cm (20 mS/cm, seawater ~50000 µS/cm, but outside typical range)
    EC_TYPICAL_MIN = 100.0  # µS/cm (typical minimum for natural water, tap water ~200-800)
    EC_TYPICAL_MAX = 15000.0  # µS/cm (hydroponics: 1000-3000, aquaculture: 500-10000)

    # Temperature compensation constants (CRITICAL for accurate EC measurements)
    # Based on industry standard for aqueous solutions (ASTM D1125-95)
    REFERENCE_TEMP = 25.0  # °C (calibration reference temperature, industry standard)
    TEMP_COEFFICIENT = 0.02  # 2% per °C (typical for ionic solutions, varies 1.8-2.2% by solution)

    EC_STABILITY_STD_DEV_US_CM = 15.0  # Target stability threshold at reference solution

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "ec"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process raw ADC value into EC measurement.

        Args:
            raw_value: Raw ADC value (0-4095 for 12-bit or 0-32767 for 16-bit)
            calibration: Optional calibration data
                - "slope": float - Linear slope (EC per volt)
                - "offset": float - Linear offset (EC at 0V)
                - "adc_type": str - "12bit" or "16bit" (default: "12bit")
            params: Optional processing parameters
                - "unit": str - Output unit: "us_cm" (default / SSOT), "ppm"
                  (AUT-1350: optional ``ms_cm`` removed — treated as µS/cm)
                - "temperature_compensation": float - Temperature in °C for compensation
                - "decimal_places": int - Decimal places for rounding (default: 1)

        Returns:
            ProcessingResult with EC value, unit, quality assessment

        Example:
            # Basic usage without calibration
            result = processor.process(raw_value=1800)

            # With calibration
            calibration = {"slope": 5000, "offset": -2000}
            result = processor.process(raw_value=1800, calibration=calibration)

            # With temperature compensation (at 30°C)
            result = processor.process(
                raw_value=1800,
                calibration=calibration,
                params={"temperature_compensation": 30.0}
            )
            # EC compensated: EC_25C = EC_raw / (1 + 0.02 * (30 - 25))

            # Unit SSOT is µS/cm (AUT-1350); ppm still available via params.unit
        """
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="µS/cm",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Determine acquisition source and convert RAW -> voltage.
        # New, PGA-exact path: calibration carries adc_source='ads1115' + pga_gain.
        # Legacy path: calibration carries adc_type ('12bit'/'16bit') only.
        adc_source, pga_gain = resolve_adc_descriptor(calibration)
        adc_type = "12bit"  # Default (legacy discriminator, kept for metadata)
        if calibration and "adc_type" in calibration:
            adc_type = calibration["adc_type"]

        if adc_source == ADC_SOURCE_ADS1115:
            # Single normalization for the external 16-bit ADC.
            voltage = raw_to_voltage(raw_value, adc_source=ADC_SOURCE_ADS1115, pga_gain=pga_gain)
        else:
            # Internal ADC (default) or legacy adc_type='16bit' backward-compat path.
            voltage = self._adc_to_voltage(raw_value, adc_type)

        # Step 3: Apply calibration if available
        if calibration and "slope" in calibration and "offset" in calibration:
            # Primary path: voltage-based calibration (ec_1point / ec_2point new format)
            slope = calibration["slope"]
            offset = calibration["offset"]
            ec_value = self._voltage_to_ec_calibrated(voltage, slope, offset)
            calibrated = True
        elif calibration and "cell_factor" in calibration:
            # Backward-compat path: old ec_1point sessions that stored only cell_factor.
            # cell_factor = reference_EC / raw_ADC → EC = cell_factor * raw_adc
            cell_factor = calibration["cell_factor"]
            ec_value = max(self.EC_MIN, min(self.EC_MAX, cell_factor * raw_value))
            calibrated = True
        else:
            # No calibration - use default conversion
            ec_value = self._voltage_to_ec_default(voltage)
            calibrated = False

        # Step 4: Temperature compensation (optional)
        if params and "temperature_compensation" in params:
            temp = params["temperature_compensation"]
            ec_value = self._apply_temperature_compensation(ec_value, temp)

        # Step 5: Clamp to valid range
        ec_value = max(self.EC_MIN, min(self.EC_MAX, ec_value))

        # Step 6: Unit conversion (if requested)
        unit_type = "us_cm"  # Default
        if params and "unit" in params:
            unit_type = params["unit"].lower()

        ec_value, unit_str = self._convert_unit(ec_value, unit_type)

        # Step 7: Round to decimal places
        decimal_places = 1  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        ec_value = round(ec_value, decimal_places)

        # Step 8: Assess quality
        stability_params = self._extract_stability_params(params, calibration, adc_type)
        quality = self._assess_quality(
            ec_value,
            calibrated,
            unit_type,
            stable=stability_params.get("stable"),
            ec_stddev=stability_params.get("ec_stddev"),
        )

        metadata = {
            "voltage": voltage,
            "calibrated": calibrated,
            "raw_value": raw_value,
            "warnings": validation.warnings,
            "adc_type": adc_type,
            "adc_source": adc_source,
        }
        if adc_source == ADC_SOURCE_ADS1115 and pga_gain is not None:
            metadata["pga_gain"] = pga_gain
        metadata.update(stability_params)

        # Step 9: Return result
        return ProcessingResult(
            value=ec_value,
            unit=unit_str,
            quality=quality,
            metadata=metadata,
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """
        Validate raw ADC value with automatic 12-bit/16-bit detection.

        Checks if value is within ADC range (0-4095 for 12-bit or 0-32767 for 16-bit).

        ADC Auto-Detection Logic:
        - ESP32 built-in ADC: 12-bit (0-4095, 0-3.3V)
        - ADS1115 external ADC: 16-bit (0-32767, 0-5V)
        - Detection: If raw_value > 4095 → assume 16-bit ADC

        EDGE CASE:
        - 16-bit ADC reading <4095 will be treated as 12-bit
        - This is acceptable: voltage conversion still works correctly
        - Example: ADS1115 reading 2048 → treated as 12-bit
          - 12-bit: 2048/4095 * 3.3V = 1.65V
          - 16-bit: 2048/32767 * 5V = 0.31V
          - Impact: Only affects voltage metadata, not EC calculation if calibrated

        Args:
            raw_value: Raw ADC value

        Returns:
            ValidationResult with validation status

        Note:
            - For production use with 16-bit ADC, consider explicit adc_type parameter
            - Current auto-detection is pragmatic trade-off for ease of use
        """
        # ADC Auto-Detection: Assume 16-bit if value exceeds 12-bit max
        max_value = self.ADC_MAX_16BIT if raw_value > self.ADC_MAX_12BIT else self.ADC_MAX_12BIT

        # Validate range
        if raw_value < 0 or raw_value > max_value:
            return ValidationResult(
                valid=False,
                error=f"ADC value {raw_value} out of range (0-{max_value})",
            )

        # Warning if value is near extremes (possible sensor issue)
        warnings = []
        if raw_value < 100:
            warnings.append(
                "Very low ADC value (<100) - sensor may be disconnected or in pure water"
            )
        elif raw_value > (max_value - 100):
            warnings.append(f"Very high ADC value (>{max_value - 100}) - check sensor connection")

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        Perform two-point EC calibration.

        Calibration procedure:
        1. Prepare buffer solutions (1413 µS/cm and 12880 µS/cm KCl)
        2. Ensure temperature is 25°C (or use temp compensation later)
        3. Measure ADC values in each buffer
        4. Calculate slope and offset: EC = slope * voltage + offset

        Args:
            calibration_points: [
                {"raw": 1500, "reference": 1413},   # Low: 1413 µS/cm (0.01 M KCl)
                {"raw": 3000, "reference": 12880},  # High: 12880 µS/cm (0.1 M KCl)
            ]
            method: "linear" (only linear supported for EC)

        Returns:
            Calibration data dict:
            {
                "slope": float,       # EC per volt
                "offset": float,      # EC at 0V
                "method": "linear",
                "points": int,
                "adc_type": "12bit" or "16bit"
            }

        Raises:
            ValueError: If less than 2 points or method not supported
        """
        if len(calibration_points) < 2:
            raise ValueError("EC calibration requires at least 2 points")

        if method != "linear":
            raise ValueError(f"Calibration method '{method}' not supported for EC")

        # Extract points
        point1 = calibration_points[0]
        point2 = calibration_points[1]

        raw1 = point1["raw"]
        ec1 = point1["reference"]

        raw2 = point2["raw"]
        ec2 = point2["reference"]

        # Determine ADC type based on raw values
        adc_type = "16bit" if (raw1 > self.ADC_MAX_12BIT or raw2 > self.ADC_MAX_12BIT) else "12bit"

        # Convert ADC to voltage
        voltage1 = self._adc_to_voltage(raw1, adc_type)
        voltage2 = self._adc_to_voltage(raw2, adc_type)

        # Calculate slope and offset
        # EC = slope * voltage + offset
        slope = (ec2 - ec1) / (voltage2 - voltage1)
        offset = ec1 - (slope * voltage1)

        return {
            "slope": slope,
            "offset": offset,
            "method": "linear",
            "points": len(calibration_points),
            "adc_type": adc_type,
        }

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters."""
        return {
            "unit": "us_cm",  # µS/cm default
            "temperature_compensation": None,  # No temp compensation by default
            "decimal_places": 1,
        }

    def get_value_range(self) -> Dict[str, float]:
        """Get expected EC value range (0-20000 µS/cm)."""
        return {"min": self.EC_MIN, "max": self.EC_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected ADC range (0-4095 for 12-bit)."""
        return {"min": 0.0, "max": self.ADC_MAX_12BIT}

    # Private helper methods

    def _adc_to_voltage(self, adc_value: float, adc_type: str = "12bit") -> float:
        """
        Convert ADC value to voltage (legacy adc_type discriminator).

        Args:
            adc_value: Raw ADC value
            adc_type: "12bit" (ESP32, 0-3.3V) or "16bit" (legacy ADS1115, 0-5V)

        Returns:
            Voltage in volts

        Note:
            The 12-bit branch delegates to the shared ``raw_to_voltage`` so that
            the internal-ADC normalization lives in exactly one place. The
            "16bit" branch is preserved for backward compatibility with EC
            calibrations stored before the PGA-exact adc_source path existed;
            new ADS1115 sensors use adc_source='ads1115' + pga_gain instead.
        """
        # nicht im Produktiv-Pfad / reine Konsolidierung auf adc_normalization
        if adc_type == "16bit":
            return raw_to_voltage(
                adc_value, adc_source=ADC_SOURCE_ADS1115, pga_gain=DEFAULT_PGA_GAIN
            )
        return raw_to_voltage(adc_value, adc_source=ADC_SOURCE_INTERNAL)

    def _voltage_to_ec_calibrated(self, voltage: float, slope: float, offset: float) -> float:
        """
        Convert voltage to EC using calibration.

        Args:
            voltage: Voltage in volts
            slope: Calibration slope (EC per volt)
            offset: Calibration offset (EC at 0V)

        Returns:
            EC value in µS/cm
        """
        ec = slope * voltage + offset

        # Clamp to valid range
        ec = max(self.EC_MIN, min(self.EC_MAX, ec))

        return ec

    def _voltage_to_ec_default(self, voltage: float) -> float:
        """
        Convert voltage to EC using default conversion (no calibration).

        Default assumption: Linear mapping based on typical sensor behavior
        - 0V → 0 µS/cm
        - 3.3V → ~20000 µS/cm (ESP32)

        Args:
            voltage: Voltage in volts

        Returns:
            EC value in µS/cm
        """
        # Default linear mapping: ~6060 µS/cm per volt (for 3.3V → 20000 µS/cm)
        DEFAULT_SLOPE = 6060.0
        DEFAULT_OFFSET = 0.0

        ec = DEFAULT_SLOPE * voltage + DEFAULT_OFFSET

        # Clamp to valid range
        ec = max(self.EC_MIN, min(self.EC_MAX, ec))

        return ec

    def _apply_temperature_compensation(self, ec: float, temperature: float) -> float:
        """
        Apply temperature compensation to EC reading.

        EC sensors are temperature-sensitive (~2% per °C from reference temp).
        This compensates for temperature effects to get EC at 25°C.

        Formula: EC_25C = EC_raw / (1 + 0.02 * (T - 25))

        Physical Background:
        - Ionic mobility increases with temperature → higher EC at higher temps
        - Standard reference: 25°C (industry convention)
        - Coefficient 0.02 (2% per °C) is typical for aqueous solutions

        Numerical Examples:
        - At 25°C (reference): EC_raw = 1000 µS/cm → EC_25C = 1000 µS/cm (no change)
        - At 30°C (+5°C):      EC_raw = 1000 µS/cm → EC_25C = 1000 / 1.1 ≈ 909 µS/cm
        - At 20°C (-5°C):      EC_raw = 1000 µS/cm → EC_25C = 1000 / 0.9 ≈ 1111 µS/cm

        Args:
            ec: EC value at measured temperature (µS/cm)
            temperature: Temperature in °C

        Returns:
            Temperature-compensated EC value (EC at 25°C) in µS/cm

        Note:
            - Compensation is CRITICAL for accurate EC measurements
            - Without temp compensation, readings can vary ±10% across 20-30°C range
            - Formula validated against industry standards (ASTM D1125-95)
        """
        temp_difference = temperature - self.REFERENCE_TEMP
        temp_factor = 1 + self.TEMP_COEFFICIENT * temp_difference

        # EDGE CASE: Avoid division by zero
        # This would require temp = -25°C (factor = 1 + 0.02 * (-50) = 0)
        # Extremely unlikely in practice (sensor range: -40°C to +85°C)
        if temp_factor == 0:
            return ec

        # Apply compensation formula
        ec_compensated = ec / temp_factor

        # Clamp to valid sensor range (prevent numerical overflow)
        # Important: Compensation at very low temps can exceed sensor max
        ec_compensated = max(self.EC_MIN, min(self.EC_MAX, ec_compensated))

        return ec_compensated

    def _convert_unit(self, ec_us_cm: float, unit_type: str) -> tuple[float, str]:
        """
        Convert EC from µS/cm to other units.

        Unit Conversion Details:

        1. µS/cm (SSOT, AUT-1350 / AUT-1268):
           - Default and only conductivity unit for operational paths
           - Legacy ``ms_cm`` requests are ignored (no /1000) — emit µS/cm

        2. µS/cm → ppm (Total Dissolved Solids):
           - Conversion: multiply by 0.5 (APPROXIMATION)
           - Example: 1000 µS/cm ≈ 500 ppm
           - WARNING: This is an approximation!
             - Factor varies by solution type:
               - KCl solutions: 0.50-0.55
               - NaCl solutions: 0.47-0.50
               - Mixed nutrient solutions: 0.50-0.70
             - For accurate TDS, measure gravimetrically or use solution-specific factor
           - Use case: Hydroponics, aquaculture (industry standard approximation)

        Args:
            ec_us_cm: EC value in µS/cm (microSiemens per centimeter)
            unit_type: "us_cm" (µS/cm), "ppm" (TDS); ``ms_cm`` → µS/cm (capped)

        Returns:
            Tuple of (converted_value, unit_string)

        Note:
            - ppm conversion is industry-standard approximation (±20% error possible)
            - Ledger mS/cm lives in ``ledger_ec_units``, not in the sensor path
        """
        if unit_type == "ppm":
            # TDS (ppm) ≈ EC (µS/cm) * EC_TO_TDS_PPM_FACTOR (approximation for typical solutions)
            return (ec_us_cm * EC_TO_TDS_PPM_FACTOR, "ppm")
        # Default + legacy ms_cm: µS/cm SSOT (AUT-1350 — no /1000 path)
        return (ec_us_cm, "µS/cm")

    def _extract_stability_params(
        self,
        params: Optional[Dict[str, Any]],
        calibration: Optional[Dict[str, Any]],
        adc_type: str,
    ) -> Dict[str, Any]:
        """Extract sampling stability metadata from ingest params."""
        if not params:
            return {}

        result: Dict[str, Any] = {}
        if "sample_count" in params:
            result["sample_count"] = int(params["sample_count"])
        if "stable" in params:
            result["stable"] = bool(params["stable"])
        if "adc_stddev" in params:
            adc_stddev = float(params["adc_stddev"])
            result["adc_stddev"] = adc_stddev
            slope_per_count = self._estimate_slope_per_adc_count(calibration, adc_type)
            if slope_per_count is not None:
                result["ec_stddev"] = round(adc_stddev * slope_per_count, 2)
        if "temp_compensated" in params:
            result["temp_compensated"] = bool(params["temp_compensated"])
        return result

    def _estimate_slope_per_adc_count(
        self,
        calibration: Optional[Dict[str, Any]],
        adc_type: str,
    ) -> Optional[float]:
        """Estimate µS/cm per ADC count for stddev conversion."""
        if calibration and "slope" in calibration:
            adc_max = self.ADC_MAX_16BIT if adc_type == "16bit" else self.ADC_MAX_12BIT
            voltage_range = (
                self.ADC_VOLTAGE_RANGE_5V if adc_type == "16bit" else self.ADC_VOLTAGE_RANGE_3V3
            )
            return calibration["slope"] * (voltage_range / adc_max)

        # Default uncalibrated slope: 20000 µS/cm over full ADC range
        adc_max = self.ADC_MAX_16BIT if adc_type == "16bit" else self.ADC_MAX_12BIT
        return self.EC_MAX / adc_max

    def _assess_quality(
        self,
        ec_value: float,
        calibrated: bool,
        unit_type: str,
        *,
        stable: Optional[bool] = None,
        ec_stddev: Optional[float] = None,
    ) -> str:
        """
        Assess data quality.

        Quality tiers:
        - "good": Typical range (100-15000 µS/cm), calibrated
        - "fair": Valid range but uncalibrated OR extreme values
        - "poor": Near sensor limits, uncalibrated

        Args:
            ec_value: EC value (in current unit)
            calibrated: Whether calibration was applied
            unit_type: Current unit type (for range conversion)

        Returns:
            Quality string: "good", "fair", "poor", "error"
        """
        # Convert to µS/cm for quality assessment (ms_cm output removed AUT-1350)
        if unit_type == "ppm":
            ec_us_cm = ec_value / 0.5
        else:
            ec_us_cm = ec_value

        # Error: Outside physical range (shouldn't happen due to clamping)
        if ec_us_cm < self.EC_MIN or ec_us_cm > self.EC_MAX:
            return "error"

        # Good: Within typical range and calibrated
        if calibrated and self.EC_TYPICAL_MIN <= ec_us_cm <= self.EC_TYPICAL_MAX:
            base_quality = "good"
        elif calibrated or (self.EC_TYPICAL_MIN <= ec_us_cm <= self.EC_TYPICAL_MAX):
            base_quality = "fair"
        else:
            base_quality = "poor"

        unstable = stable is False or (
            ec_stddev is not None and ec_stddev > self.EC_STABILITY_STD_DEV_US_CM
        )
        if unstable and base_quality == "good":
            return "fair"
        return base_quality
