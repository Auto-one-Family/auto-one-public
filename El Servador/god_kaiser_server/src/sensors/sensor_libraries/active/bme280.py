"""
BME280 Sensor Library - Temperature, Pressure, Humidity (I2C)

The BME280 is a 3-in-1 environmental sensor providing:
- Temperature (°C)
- Barometric Pressure (hPa)
- Relative Humidity (%RH)

It is the humidity-capable successor of the BMP280 (which only provides
temperature + pressure). Wiring and protocol are identical to BMP280
(I2C, addresses 0x76 / 0x77). The Adafruit_BME280 library on the ESP32
already converts raw sensor data to °C / hPa / %RH, so server processors
focus on validation, optional offset calibration, unit handling and
quality assessment.

NAMING CLARIFICATION (BMP280 vs. BME280):
- BMP280 = Pressure + Temperature only (no humidity)
- BME280 = BMP280 + Humidity sensor (drop-in successor)
- The processor types `bmp280_*` and `bme280_*` are intentionally distinct
  in `sensor_type_registry.MULTI_VALUE_SENSORS` so that a BME280 device is
  reported with three sub-sensors. Do NOT alias `bme280_temp` to
  `bmp280_temp` — they are different physical sensors with different
  accuracy characteristics.

Sensor Specifications (Bosch BME280 datasheet):
- Temperature: -40°C to +85°C, ±1°C accuracy, 0.01°C resolution
- Pressure:    300-1100 hPa,    ±1 hPa accuracy, 0.01 hPa resolution
- Humidity:    0-100% RH,       ±3% RH accuracy, 0.008% RH resolution
- Communication: I2C (Address 0x76 default, 0x77 if SDO -> VCC)
"""

from typing import Any, Dict, Optional

from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)


class BME280TemperatureProcessor(BaseSensorProcessor):
    """
    BME280 Temperature Sensor Processor.

    Same characteristics as BMP280 temperature (the underlying silicon is
    derived from BMP280), but reported under its own ``bme280_temp`` type
    so multi-value device assembly stays clean.
    """

    # Operating mode recommendations
    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180
    RECOMMENDED_INTERVAL_SECONDS = 30
    SUPPORTS_ON_DEMAND = False

    # Specifications
    TEMP_MIN = -40.0
    TEMP_MAX = 85.0
    TEMP_TYPICAL_MIN = -20.0
    TEMP_TYPICAL_MAX = 85.0
    RESOLUTION = 0.01

    def get_sensor_type(self) -> str:
        return "bme280_temp"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="°C",
                quality="error",
                metadata={"error": validation.error},
            )

        temp_celsius = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            temp_celsius += calibration["offset"]
            calibrated = True

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

        decimal_places = 2
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        value = round(value, decimal_places)

        quality = self._assess_quality(temp_celsius)

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
        if raw_value < self.TEMP_MIN or raw_value > self.TEMP_MAX:
            return ValidationResult(
                valid=False,
                error=f"Temperature {raw_value}°C out of sensor range "
                f"({self.TEMP_MIN}°C to {self.TEMP_MAX}°C)",
            )
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
        if len(calibration_points) < 1:
            raise ValueError("BME280 temperature calibration requires at least 1 point")
        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for BME280 temperature. "
                "Only 'offset' method is supported."
            )
        total_offset = 0.0
        for point in calibration_points:
            total_offset += point["reference"] - point["raw"]
        return {
            "offset": total_offset / len(calibration_points),
            "method": "offset",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        return {"unit": "celsius", "decimal_places": 2}

    def get_value_range(self) -> Dict[str, float]:
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        return {"min": self.TEMP_MIN, "max": self.TEMP_MAX}

    def _assess_quality(self, temp_celsius: float) -> str:
        if temp_celsius < self.TEMP_MIN or temp_celsius > self.TEMP_MAX:
            return "error"
        if self.TEMP_TYPICAL_MIN <= temp_celsius <= self.TEMP_TYPICAL_MAX:
            return "good"
        return "fair"


class BME280PressureProcessor(BaseSensorProcessor):
    """
    BME280 Pressure Sensor Processor.

    Pressure pipeline mirrors BMP280 (offset calibration, optional sea-level
    correction, unit conversion). Reported under its own ``bme280_pressure``
    type to keep multi-value device assembly consistent.
    """

    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 300
    RECOMMENDED_INTERVAL_SECONDS = 60
    SUPPORTS_ON_DEMAND = False

    PRESSURE_MIN = 300.0
    PRESSURE_MAX = 1100.0
    PRESSURE_TYPICAL_MIN = 950.0
    PRESSURE_TYPICAL_MAX = 1050.0
    RESOLUTION = 0.01

    def get_sensor_type(self) -> str:
        return "bme280_pressure"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="hPa",
                quality="error",
                metadata={"error": validation.error},
            )

        pressure_hpa = raw_value
        calibrated = False
        if calibration and "offset" in calibration:
            pressure_hpa += calibration["offset"]
            calibrated = True

        if params and "altitude" in params and params["altitude"] is not None:
            pressure_hpa = self._apply_sea_level_correction(pressure_hpa, params["altitude"])

        unit_type = "hpa"
        if params and "unit" in params:
            unit_type = params["unit"].lower()
        pressure_value, unit_str = self._convert_unit(pressure_hpa, unit_type)

        decimal_places = 1
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        pressure_value = round(pressure_value, decimal_places)

        quality = self._assess_quality(pressure_hpa)

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
        if raw_value < self.PRESSURE_MIN or raw_value > self.PRESSURE_MAX:
            return ValidationResult(
                valid=False,
                error=f"Pressure {raw_value} hPa out of sensor range "
                f"({self.PRESSURE_MIN}-{self.PRESSURE_MAX} hPa)",
            )
        warnings = []
        if raw_value < self.PRESSURE_TYPICAL_MIN:
            warnings.append(
                f"Pressure {raw_value} hPa below typical range "
                f"(very low pressure or high altitude)"
            )
        elif raw_value > self.PRESSURE_TYPICAL_MAX:
            warnings.append(
                f"Pressure {raw_value} hPa above typical range (very high pressure system)"
            )
        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        if len(calibration_points) < 1:
            raise ValueError("BME280 pressure calibration requires at least 1 point")
        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for BME280 pressure. "
                "Only 'offset' method is supported."
            )
        total_offset = 0.0
        for point in calibration_points:
            total_offset += point["reference"] - point["raw"]
        return {
            "offset": total_offset / len(calibration_points),
            "method": "offset",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        return {"unit": "hpa", "altitude": None, "decimal_places": 1}

    def get_value_range(self) -> Dict[str, float]:
        return {"min": self.PRESSURE_MIN, "max": self.PRESSURE_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        return {"min": self.PRESSURE_MIN, "max": self.PRESSURE_MAX}

    def _apply_sea_level_correction(self, pressure: float, altitude: float) -> float:
        ALTITUDE_CONSTANT = 44330.0
        EXPONENT = 5.255
        factor = 1 - (altitude / ALTITUDE_CONSTANT)
        if factor <= 0:
            return pressure
        pressure_sealevel = pressure / (factor**EXPONENT)
        return max(self.PRESSURE_MIN, min(self.PRESSURE_MAX, pressure_sealevel))

    def _convert_unit(self, pressure_hpa: float, unit_type: str) -> tuple[float, str]:
        if unit_type == "pa":
            return (pressure_hpa * 100.0, "Pa")
        elif unit_type == "mmhg":
            return (pressure_hpa * 0.750062, "mmHg")
        elif unit_type == "inhg":
            return (pressure_hpa * 0.02953, "inHg")
        return (pressure_hpa, "hPa")

    def _assess_quality(self, pressure_hpa: float) -> str:
        if pressure_hpa < self.PRESSURE_MIN or pressure_hpa > self.PRESSURE_MAX:
            return "error"
        if self.PRESSURE_TYPICAL_MIN <= pressure_hpa <= self.PRESSURE_TYPICAL_MAX:
            return "good"
        return "fair"


class BME280HumidityProcessor(BaseSensorProcessor):
    """
    BME280 Humidity Sensor Processor.

    BME280 delivers humidity in % RH already pre-converted by the ESP32-side
    Adafruit_BME280 library. Pipeline (validation, optional offset calibration,
    clamping, condensation warning) follows the SHT31 humidity processor.

    Spec (Bosch BME280 datasheet):
    - Range:    0-100 % RH (physical)
    - Accuracy: ±3 % RH (typical 20-80 % RH)
    - Note:     Slightly less accurate than SHT31 (±2 % RH) but cheaper and
                combined with pressure + temperature.
    """

    RECOMMENDED_MODE = "continuous"
    RECOMMENDED_TIMEOUT_SECONDS = 180
    RECOMMENDED_INTERVAL_SECONDS = 30
    SUPPORTS_ON_DEMAND = False

    HUMIDITY_MIN = 0.0
    HUMIDITY_MAX = 100.0
    HUMIDITY_TYPICAL_MIN = 20.0
    HUMIDITY_TYPICAL_MAX = 80.0
    RESOLUTION = 0.008

    CONDENSATION_THRESHOLD = 95.0
    LOW_THRESHOLD = 5.0

    def get_sensor_type(self) -> str:
        return "bme280_humidity"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
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

        quality = self._assess_quality(humidity)

        condensation_warning_enabled = True
        if params and "condensation_warning" in params:
            condensation_warning_enabled = params["condensation_warning"]

        metadata: Dict[str, Any] = {
            "raw_humidity": raw_value,
            "calibrated": calibrated,
            "warnings": validation.warnings,
        }
        if condensation_warning_enabled and humidity > self.CONDENSATION_THRESHOLD:
            if metadata.get("warnings") is None:
                metadata["warnings"] = []
            metadata["warnings"].append(
                f"High humidity ({humidity}% RH) may indicate condensation. "
                "Consider activating heater element."
            )

        return ProcessingResult(
            value=humidity,
            unit="%RH",
            quality=quality,
            metadata=metadata,
        )

    def validate(self, raw_value: float) -> ValidationResult:
        if raw_value < self.HUMIDITY_MIN or raw_value > self.HUMIDITY_MAX:
            return ValidationResult(
                valid=False,
                error=f"Humidity {raw_value}% RH out of physical range "
                f"({self.HUMIDITY_MIN}-{self.HUMIDITY_MAX}% RH)",
            )

        warnings = []
        if raw_value < self.LOW_THRESHOLD:
            warnings.append(
                f"Very low humidity ({raw_value}% RH). "
                "Check sensor connection and environmental conditions."
            )
        if raw_value > self.CONDENSATION_THRESHOLD:
            warnings.append(
                f"Very high humidity ({raw_value}% RH). "
                "Possible condensation on sensor."
            )
        if raw_value < self.HUMIDITY_TYPICAL_MIN or raw_value > self.HUMIDITY_TYPICAL_MAX:
            warnings.append(
                f"Humidity {raw_value}% RH outside typical accuracy range "
                f"({self.HUMIDITY_TYPICAL_MIN}-{self.HUMIDITY_TYPICAL_MAX}% RH). "
                "Accuracy may be reduced to ±5% RH."
            )

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "offset",
    ) -> Dict[str, Any]:
        if len(calibration_points) < 1:
            raise ValueError("BME280 humidity calibration requires at least 1 point")
        if method != "offset":
            raise ValueError(
                f"Calibration method '{method}' not supported for BME280 humidity. "
                "Only 'offset' method is supported."
            )
        total_offset = 0.0
        for point in calibration_points:
            total_offset += point["reference"] - point["raw"]
        return {
            "offset": total_offset / len(calibration_points),
            "method": "offset",
            "points": len(calibration_points),
        }

    def get_default_params(self) -> Dict[str, Any]:
        return {"decimal_places": 1, "condensation_warning": True}

    def get_value_range(self) -> Dict[str, float]:
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def get_raw_value_range(self) -> Dict[str, float]:
        return {"min": self.HUMIDITY_MIN, "max": self.HUMIDITY_MAX}

    def _assess_quality(self, humidity: float) -> str:
        if humidity < self.HUMIDITY_MIN or humidity > self.HUMIDITY_MAX:
            return "error"
        if humidity < self.LOW_THRESHOLD or humidity > self.CONDENSATION_THRESHOLD:
            return "poor"
        if self.HUMIDITY_TYPICAL_MIN <= humidity <= self.HUMIDITY_TYPICAL_MAX:
            return "good"
        return "fair"
