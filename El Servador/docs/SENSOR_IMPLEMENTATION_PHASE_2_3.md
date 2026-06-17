# Sensor-Library Implementierung - Phase 2 & 3

**Erstellt:** 2025-01-02
**Status:** Implementierungs-Anleitung für KI-Agenten
**Basis:** ESP32-Hardware, MQTT-Protokoll, Pi-Enhanced Architecture, Web-Recherche

---

## Executive Summary

Dieses Dokument definiert die **vollständige Implementierung der verbleibenden 5 Sensor-Processing-Libraries** (Phase 2 & 3) für den God-Kaiser Server. Es ist speziell für KI-Agenten geschrieben, um:

1. **Präzise Implementierung** nach etabliertem Pattern (Phase 1 als Referenz)
2. **Zielgerichtete Analyse** der Hardware-Anforderungen und Sensor-Spezifikationen
3. **Konsistente Code-Qualität** mit umfassenden Tests
4. **MQTT-Protokoll-Konformität** gemäß ESP32-Firmware-Vorgaben

### Status Phase 1 (✅ ABGESCHLOSSEN):
- ✅ **DS18B20** Temperature Processor (`temperature.py`)
- ✅ **SHT31** Temperature Processor (`temperature.py`)
- ✅ **SHT31** Humidity Processor (`humidity.py`)
- ✅ Unit-Tests: `test_temperature_processor.py`, `test_humidity_processor.py`

### Verbleibend Phase 2 & 3:
- ⏳ **EC Sensor** (Electrical Conductivity) - Analog ADC
- ⏳ **Moisture Sensor** (Capacitive Soil Moisture) - Analog ADC
- ⏳ **BMP280** (Pressure + Temperature) - I2C Digital
- ⏳ **CO2 Sensor** (SEN0220/MH-Z16 kanonisch, MH-Z19 kompatibel) - UART; SCD30 optional I2C
- ⏳ **Light Sensor** (TSL2561/BH1750) - I2C Digital
- ⏳ **Flow Sensor** (YFS201) - GPIO Interrupt

---

## Inhaltsverzeichnis

1. [Architektur-Kontext](#1-architektur-kontext)
2. [Phase 2: Wichtige Sensoren (Woche 3-4)](#2-phase-2-wichtige-sensoren)
   - [2.1 EC Sensor Implementation](#21-ec-sensor-electrical-conductivity)
   - [2.2 Moisture Sensor Implementation](#22-moisture-sensor-capacitive)
   - [2.3 BMP280 Pressure Sensor Implementation](#23-bmp280-pressure--temperature)
3. [Phase 3: Nice-to-Have Sensoren (Woche 5-6)](#3-phase-3-nice-to-have-sensoren)
   - [3.1 CO2 Sensor Implementation](#31-co2-sensor-mhz19scd30)
   - [3.2 Light Sensor Implementation](#32-light-sensor-tsl2561bh1750)
   - [3.3 Flow Sensor Implementation](#33-flow-sensor-yfs201)
4. [ESP32 Hardware-Spezifikationen](#4-esp32-hardware-spezifikationen)
5. [Testing-Strategie](#5-testing-strategie)
6. [MQTT-Integration](#6-mqtt-integration)
7. [Code-Qualitäts-Standards](#7-code-qualitäts-standards)
8. [Troubleshooting & Debugging](#8-troubleshooting--debugging)

---

## 1. Architektur-Kontext

### 1.1 Pi-Enhanced Processing Pattern (Referenz)

**Alle Sensor-Libraries folgen diesem etablierten Pattern aus Phase 1:**

```python
from typing import Any, Dict, Optional
from ...base_processor import (
    BaseSensorProcessor,
    ProcessingResult,
    ValidationResult,
)

class {SensorName}Processor(BaseSensorProcessor):
    """
    {Sensor-Beschreibung}

    Sensor Specifications:
    - Range: {min} - {max} {unit}
    - Resolution: {resolution}
    - Communication: {protocol}
    - Accuracy: {accuracy}

    ESP32 Setup:
    - Library: {esp32_library}
    - GPIO/Bus: {hardware_setup}
    - Hardware: {additional_requirements}
    """

    # Constants
    {SENSOR_MIN} = {value}
    {SENSOR_MAX} = {value}

    def get_sensor_type(self) -> str:
        """Return sensor type identifier."""
        return "{sensor_type_id}"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """Process raw sensor value."""
        # Step 1: Validate
        # Step 2: Apply calibration
        # Step 3: Convert units (if applicable)
        # Step 4: Round to decimal places
        # Step 5: Assess quality
        # Step 6: Return result

    def validate(self, raw_value: float) -> ValidationResult:
        """Validate raw sensor value."""

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """Perform sensor calibration (if supported)."""

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters."""

    def get_value_range(self) -> Dict[str, float]:
        """Get expected value range."""

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range."""

    def _assess_quality(self, value: float, calibrated: bool) -> str:
        """Assess data quality."""
```

### 1.2 Referenz-Implementierungen (Phase 1)

**KI-Agent Anweisung:** Vor Implementierung IMMER diese Dateien lesen:

| Datei | Zweck |
|-------|-------|
| [temperature.py](../god_kaiser_server/src/sensors/sensor_libraries/active/temperature.py) | Referenz für **Digital I2C** (SHT31) und **OneWire** (DS18B20) Sensoren |
| [humidity.py](../god_kaiser_server/src/sensors/sensor_libraries/active/humidity.py) | Referenz für **Quality Assessment** mit Condensation Warning |
| [ph_sensor.py](../god_kaiser_server/src/sensors/sensor_libraries/active/ph_sensor.py) | Referenz für **Analog ADC** Sensoren mit 2-Punkt-Calibration |
| [base_processor.py](../god_kaiser_server/src/sensors/base_processor.py) | **Abstract Base Class** - Interface-Definition |
| [test_temperature_processor.py](../tests/unit/test_temperature_processor.py) | Referenz für **Unit-Test-Pattern** |

---

## 2. Phase 2: Wichtige Sensoren (Woche 3-4)

### 2.1 EC Sensor (Electrical Conductivity)

**Priorität:** 🟡 HOCH
**Komplexität:** Medium
**Geschätzte Zeit:** 4-5 Stunden (inkl. Tests)

#### 2.1.1 Sensor-Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Sensor-Typ** | Analog EC Probe (z.B. DFRobot Gravity EC Sensor) |
| **Measurement Range** | 0 - 20,000 µS/cm (0 - 20 mS/cm) |
| **Accuracy** | ±5% (bei 25°C) |
| **Resolution** | ADC-abhängig (12-bit ESP32: ~4.88 µS/cm per step) |
| **Communication** | Analog ADC (0-3.3V) |
| **Temperature Dependency** | ~2% pro °C Abweichung von 25°C |
| **Calibration** | 2-Punkt (Low: 1413 µS/cm, High: 12880 µS/cm) |

#### 2.1.2 ESP32 Hardware-Setup

**⚠️ KRITISCH - ESP32 ADC Limitations:**

```
Problem: ESP32 ADC ist nicht genau genug für präzise EC-Messungen (±10% Fehler)

Lösung 1 (EMPFOHLEN): Externe ADC verwenden
- Hardware: ADS1115 (16-bit, I2C)
- Accuracy: ±0.015% (deutlich besser als ESP32)
- I2C Address: 0x48 (default)
- ESP32 Library: Adafruit_ADS1X15

Lösung 2 (Akzeptabel): ESP32 ADC mit Calibration
- Nur ADC1 Pins verwenden (GPIO32-39)
- NICHT ADC2 (Konflikt mit WiFi!)
- Multisampling: 10-100 Samples pro Reading
- esp_adc_cal_characterize() für Calibration
- 0.1µF Kondensator für Noise-Reduktion
```

**Hardware-Konfiguration:**

```cpp
// ESP32-Side (Referenz - wird NICHT im Server implementiert)
// Nur zur Information für Kontext-Verständnis

// Option 1: ADS1115 External ADC (16-bit)
#include <Adafruit_ADS1X15.h>
Adafruit_ADS1115 ads;  // I2C address 0x48
ads.begin();
int16_t adc_value = ads.readADC_SingleEnded(0);  // Channel 0
float voltage = ads.computeVolts(adc_value);

// Option 2: ESP32 ADC1 (12-bit)
#include <esp_adc_cal.h>
int adc_value = analogRead(GPIO_PIN);  // GPIO32-39 only!
// Apply calibration + multisampling
```

#### 2.1.3 Server-Side Implementation

**Datei:** `El Servador/god_kaiser_server/src/sensors/sensor_libraries/active/ec_sensor.py`

**Klasse:** `ECSensorProcessor(BaseSensorProcessor)`

**sensor_type ID:** `"ec"`

**Implementierungs-Details:**

```python
class ECSensorProcessor(BaseSensorProcessor):
    """
    EC (Electrical Conductivity) Sensor Processor.

    Converts raw ADC voltage to EC measurement in µS/cm, mS/cm, or ppm (TDS).
    Supports temperature compensation and 2-point calibration.

    Sensor Specifications:
    - Measurement Range: 0 - 20,000 µS/cm (0 - 20 mS/cm)
    - Accuracy: ±5% (at 25°C, with calibration)
    - Communication: Analog ADC (0-3.3V or 0-5V via ADS1115)
    - Temperature Coefficient: ~2% per °C

    ESP32 Setup:
    - Option A (Recommended): ADS1115 16-bit ADC (I2C 0x48)
    - Option B (Acceptable): ESP32 ADC1 (GPIO32-39) with calibration
    - Hardware: 0.1µF capacitor on ADC input for noise reduction

    Calibration:
    - 2-Point: Low (1413 µS/cm), High (12880 µS/cm)
    - Method: Linear slope + offset

    Important Notes:
    - EC readings are highly temperature-dependent
    - Always apply temperature compensation if available
    - TDS (ppm) is approximated as EC * 0.5 (varies by solution)
    """

    # ADC Configuration (depends on hardware)
    ADC_MAX_12BIT = 4095  # ESP32 native ADC
    ADC_MAX_16BIT = 32767  # ADS1115
    ADC_VOLTAGE_ESP32 = 3.3  # Volts
    ADC_VOLTAGE_ADS1115 = 5.0  # Volts (configurable)

    # EC Measurement Range
    EC_MIN = 0.0  # µS/cm
    EC_MAX = 20000.0  # µS/cm (20 mS/cm)
    EC_TYPICAL_MIN = 100.0  # µS/cm (typical minimum for calibrated sensors)
    EC_TYPICAL_MAX = 15000.0  # µS/cm (typical maximum)

    # Temperature Compensation
    REFERENCE_TEMP = 25.0  # °C (calibration reference)
    TEMP_COEFFICIENT = 0.02  # 2% per °C

    def get_sensor_type(self) -> str:
        return "ec"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process EC sensor reading.

        Args:
            raw_value: ADC value (0-4095 for 12-bit, 0-32767 for 16-bit)
                       OR voltage (0-3.3V or 0-5V) if ESP32 already converted
            calibration: {"slope": float, "offset": float, "adc_type": "12bit"|"16bit"}
            params: {
                "temperature_compensation": float (°C),
                "output_unit": "us_cm"|"ms_cm"|"ppm",
                "decimal_places": int,
                "adc_type": "12bit"|"16bit",
                "adc_voltage": float (3.3 or 5.0)
            }

        Returns:
            ProcessingResult with EC value, unit, quality
        """
        # Step 1: Validate
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="µS/cm",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Determine ADC type and voltage
        adc_type = "12bit"  # Default
        adc_voltage = self.ADC_VOLTAGE_ESP32  # Default

        if params:
            adc_type = params.get("adc_type", "12bit")
            adc_voltage = params.get("adc_voltage", self.ADC_VOLTAGE_ESP32)

        if calibration and "adc_type" in calibration:
            adc_type = calibration["adc_type"]

        # Step 3: Convert ADC to Voltage (if raw_value is ADC count)
        # Check if raw_value is already voltage (< 10)
        if raw_value < 10:  # Likely already voltage
            voltage = raw_value
        else:  # ADC count
            adc_max = self.ADC_MAX_16BIT if adc_type == "16bit" else self.ADC_MAX_12BIT
            voltage = (raw_value / adc_max) * adc_voltage

        # Step 4: Voltage → EC (using calibration)
        if calibration and "slope" in calibration and "offset" in calibration:
            ec_us_cm = calibration["slope"] * voltage + calibration["offset"]
            calibrated = True
        else:
            # Default: Simple linear mapping (example, adjust for real sensor)
            # Assumption: 0V = 0 µS/cm, 3.3V = 20000 µS/cm
            ec_us_cm = (voltage / adc_voltage) * self.EC_MAX
            calibrated = False

        # Clamp to valid range
        ec_us_cm = max(self.EC_MIN, min(self.EC_MAX, ec_us_cm))

        # Step 5: Temperature compensation (if provided)
        if params and "temperature_compensation" in params:
            temp = params["temperature_compensation"]
            # EC increases by ~2% per °C above 25°C
            temp_factor = 1 + self.TEMP_COEFFICIENT * (temp - self.REFERENCE_TEMP)
            ec_us_cm = ec_us_cm / temp_factor

        # Step 6: Unit conversion
        output_unit = "us_cm"
        if params and "output_unit" in params:
            output_unit = params["output_unit"]

        if output_unit == "ms_cm":
            value = ec_us_cm / 1000
            unit_str = "mS/cm"
        elif output_unit == "ppm":
            # TDS (ppm) ≈ EC * 0.5 (approximation, varies by solution)
            value = ec_us_cm * 0.5
            unit_str = "ppm"
        else:
            value = ec_us_cm
            unit_str = "µS/cm"

        # Step 7: Round to decimal places
        decimal_places = 1  # Default
        if params and "decimal_places" in params:
            decimal_places = params["decimal_places"]
        value = round(value, decimal_places)

        # Step 8: Quality assessment
        quality = self._assess_quality(ec_us_cm, calibrated)

        # Step 9: Return result
        return ProcessingResult(
            value=value,
            unit=unit_str,
            quality=quality,
            metadata={
                "voltage": voltage,
                "ec_us_cm": ec_us_cm,
                "calibrated": calibrated,
                "raw_value": raw_value,
                "warnings": validation.warnings,
            },
        )

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        Perform 2-point EC calibration.

        Args:
            calibration_points: [
                {"raw": 1500, "reference": 1413},   # Low: 1413 µS/cm buffer
                {"raw": 3000, "reference": 12880},  # High: 12.88 mS/cm buffer
            ]
            method: "linear" (only supported method)

        Returns:
            {"slope": float, "offset": float, "method": "linear"}

        Calibration Procedure:
        1. Prepare buffer solutions:
           - Low: 1413 µS/cm (0.01 M KCl)
           - High: 12880 µS/cm (0.1 M KCl)
        2. Ensure temperature is 25°C (or use temp compensation)
        3. Measure RAW ADC values in each buffer
        4. Calculate slope and offset
        """
        if len(calibration_points) < 2:
            raise ValueError("EC calibration requires at least 2 points")

        if method != "linear":
            raise ValueError(f"Method '{method}' not supported. Only 'linear' supported.")

        # Extract calibration points
        point1 = calibration_points[0]
        point2 = calibration_points[1]

        raw1 = point1["raw"]
        ec1 = point1["reference"]

        raw2 = point2["raw"]
        ec2 = point2["reference"]

        # Convert RAW to voltage (assume 12-bit ESP32 ADC)
        voltage1 = (raw1 / self.ADC_MAX_12BIT) * self.ADC_VOLTAGE_ESP32
        voltage2 = (raw2 / self.ADC_MAX_12BIT) * self.ADC_VOLTAGE_ESP32

        # Calculate slope and offset
        # EC = slope * voltage + offset
        slope = (ec2 - ec1) / (voltage2 - voltage1)
        offset = ec1 - (slope * voltage1)

        return {
            "slope": slope,
            "offset": offset,
            "method": "linear",
            "points": len(calibration_points),
            "adc_type": "12bit",  # Adjust if using 16-bit
        }
```

**⚠️ Web-Recherche Referenz:**
- [GreenPonik ESP32 EC Library](https://github.com/GreenPonik/esp32-read-ph-and-ec-with-ADC-example)
- [DFRobot EC Sensor Calibration](https://wiki.dfrobot.com/Gravity__Analog_Electrical_Conductivity_Sensor___Meter_V2__K=1__SKU_DFR0300)

#### 2.1.4 Unit-Tests

**Datei:** `El Servador/god_kaiser_server/tests/unit/test_ec_sensor_processor.py`

**Test-Cases (Minimum):**

1. ✅ `test_get_sensor_type()` - Sensor-ID "ec"
2. ✅ `test_process_valid_ec()` - Basic processing
3. ✅ `test_process_with_calibration()` - 2-Punkt-Calibration
4. ✅ `test_process_temperature_compensation()` - Temp-Correction
5. ✅ `test_process_unit_conversion_ms_cm()` - µS/cm → mS/cm
6. ✅ `test_process_unit_conversion_ppm()` - µS/cm → ppm (TDS)
7. ✅ `test_validate_out_of_range()` - Range validation
8. ✅ `test_calibrate_two_point()` - Calibration calculation
9. ✅ `test_quality_assessment()` - Quality: good/fair/poor

---

### 2.2 Moisture Sensor (Capacitive)

**Priorität:** 🟡 HOCH
**Komplexität:** Low
**Geschätzte Zeit:** 3-4 Stunden (inkl. Tests)

#### 2.2.1 Sensor-Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Sensor-Typ** | Capacitive Soil Moisture Sensor |
| **Measurement Range** | 0-100% (Moisture Percentage) |
| **Accuracy** | ±3% (after calibration) |
| **Resolution** | ADC-abhängig (12-bit: ~0.024% per step) |
| **Communication** | Analog ADC (0-3.3V) |
| **Calibration** | 2-Punkt (Dry = 0%, Wet = 100%) |
| **Response Time** | < 1 second |

#### 2.2.2 ESP32 Hardware-Setup

```
Hardware: Capacitive Soil Moisture Sensor v1.2 (oder ähnlich)
- Operating Voltage: 3.3V - 5V
- Output: Analog Voltage (0-3V typical)
- Interface: 3-pin (VCC, GND, AOUT)

ESP32 Connection:
- VCC → 3.3V (ESP32)
- GND → GND
- AOUT → GPIO32-39 (ADC1 only! NOT ADC2)

⚠️ WICHTIG:
- ESP32 ADC2 kollidiert mit WiFi → Nur ADC1 verwenden!
- Empfohlen: 0.1µF Kondensator zwischen AOUT und GND (Noise-Reduction)
- Multisampling: 10-50 Samples pro Reading für Stabilität
```

#### 2.2.3 Server-Side Implementation

**Datei:** `moisture.py`
**Klasse:** `MoistureSensorProcessor`
**sensor_type ID:** `"moisture"`

**Implementierungs-Hinweise:**

```python
class MoistureSensorProcessor(BaseSensorProcessor):
    """
    Capacitive Soil Moisture Sensor Processor.

    Converts raw ADC voltage to moisture percentage (0-100%).
    Simple 2-point linear calibration (dry = 0%, wet = 100%).

    Sensor Specifications:
    - Range: 0-100% moisture
    - Accuracy: ±3% (with calibration)
    - Communication: Analog ADC (0-3.3V)
    - Response Time: < 1 second

    ESP32 Setup:
    - GPIO: ADC1 pins only (GPIO32-39) - WiFi conflict with ADC2!
    - Hardware: 0.1µF capacitor for noise reduction
    - Multisampling: 10-50 samples recommended

    Calibration Procedure:
    1. Dry Calibration: Measure sensor in air (ADC value = dry_value)
    2. Wet Calibration: Measure sensor in water/saturated soil (ADC value = wet_value)
    3. Linear mapping: moisture% = (raw - dry) / (wet - dry) * 100

    Important Notes:
    - Capacitive sensors are more stable than resistive (no corrosion)
    - Readings may drift over time (recalibrate periodically)
    - Different soil types may affect readings
    """

    ADC_MAX = 4095  # ESP32 12-bit
    ADC_VOLTAGE = 3.3  # Volts

    MOISTURE_MIN = 0.0  # % (completely dry)
    MOISTURE_MAX = 100.0  # % (saturated)

    def get_sensor_type(self) -> str:
        return "moisture"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process moisture sensor reading.

        Args:
            raw_value: ADC value (0-4095)
            calibration: {"dry_value": float, "wet_value": float}
            params: {"decimal_places": int, "invert": bool}

        Returns:
            ProcessingResult with moisture %, unit "%", quality

        Note:
        - Some sensors output HIGH voltage when DRY (inverted logic)
        - Use "invert": True in params to flip reading
        """
        # Step 1: Validate
        # Step 2: Apply calibration (linear mapping)
        # Step 3: Clamp to 0-100%
        # Step 4: Invert if needed (some sensors: high voltage = dry)
        # Step 5: Round
        # Step 6: Quality assessment
        # Step 7: Return

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        2-point calibration (dry + wet).

        Args:
            calibration_points: [
                {"raw": 3200, "reference": 0.0},    # Dry (in air)
                {"raw": 1500, "reference": 100.0},  # Wet (in water)
            ]

        Returns:
            {"dry_value": float, "wet_value": float}
        """
```

**Referenz:** [Capacitive Soil Moisture Sensor Tutorial](https://how2electronics.com/capacitive-soil-moisture-sensor-esp32-esp8266/)

---

### 2.3 BMP280 Pressure + Temperature

**Priorität:** 🟡 HOCH
**Komplexität:** Low
**Geschätzte Zeit:** 4-5 Stunden (inkl. Tests für 2 Prozessoren)

#### 2.3.1 Sensor-Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Sensor-Typ** | Digital Barometric Pressure Sensor (I2C/SPI) |
| **Pressure Range** | 300 - 1100 hPa |
| **Pressure Accuracy** | ±1 hPa |
| **Pressure Resolution** | 0.01 hPa (Oversampling x16) |
| **Temperature Range** | -40°C to +85°C |
| **Temperature Accuracy** | ±1°C |
| **Communication** | I2C (Address: 0x76 or 0x77) |
| **Response Time** | 5.5 ms (typical) |

#### 2.3.2 ESP32 Hardware-Setup

```
Hardware: BMP280 Breakout Board (Adafruit, DFRobot, etc.)

I2C Connection (Recommended):
- VCC → 3.3V (ESP32)
- GND → GND
- SDA → GPIO21 (ESP32 default I2C SDA)
- SCL → GPIO22 (ESP32 default I2C SCL)

I2C Address:
- 0x76 (default, SDO pin to GND)
- 0x77 (if SDO pin to VCC)

ESP32 Library:
- Adafruit_BMP280 (Arduino Library Manager)
- Wire.h (I2C communication)

Multiple Sensors:
- Use different I2C addresses (0x76 and 0x77)
- Or use I2C multiplexer (TCA9548A)
```

#### 2.3.3 Server-Side Implementation

**Datei:** `pressure.py`
**Klassen:**
1. `BMP280PressureProcessor` (sensor_type: `"bmp280_pressure"`)
2. `BMP280TemperatureProcessor` (sensor_type: `"bmp280_temp"`)

**Implementierungs-Hinweise:**

```python
class BMP280PressureProcessor(BaseSensorProcessor):
    """
    BMP280 Barometric Pressure Sensor Processor.

    ESP32-side library (Adafruit_BMP280) already converts raw sensor data to hPa.
    Server-side processing focuses on:
    - Validation of pressure range
    - Unit conversion (hPa, Pa, mmHg, inHg)
    - Quality assessment
    - Optional altitude compensation

    Sensor Specifications:
    - Pressure Range: 300 - 1100 hPa
    - Accuracy: ±1 hPa
    - Resolution: 0.01 hPa (Oversampling x16)
    - Communication: I2C (0x76 or 0x77)

    ESP32 Setup:
    - Library: Adafruit_BMP280
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Multiple sensors: Use different addresses (0x76, 0x77)

    Unit Conversions:
    - 1 hPa = 100 Pa
    - 1 hPa = 0.75006 mmHg
    - 1 hPa = 0.02953 inHg

    Altitude Estimation:
    - Pressure decreases by ~12 Pa per meter altitude
    - Sea level pressure: ~1013.25 hPa (standard)
    """

    PRESSURE_MIN = 300.0  # hPa (sensor minimum)
    PRESSURE_MAX = 1100.0  # hPa (sensor maximum)
    PRESSURE_TYPICAL_MIN = 950.0  # hPa (typical low pressure)
    PRESSURE_TYPICAL_MAX = 1050.0  # hPa (typical high pressure)

    def get_sensor_type(self) -> str:
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
            raw_value: Pressure in hPa (from Adafruit_BMP280)
            calibration: {"offset": float} (optional pressure offset)
            params: {
                "unit": "hpa"|"pa"|"mmhg"|"inhg",
                "decimal_places": int,
                "sea_level_correction": float (altitude in meters)
            }

        Returns:
            ProcessingResult with pressure value, unit, quality
        """
        # Step 1: Validate
        # Step 2: Apply offset calibration (if any)
        # Step 3: Unit conversion
        # Step 4: Sea level correction (optional)
        # Step 5: Round
        # Step 6: Quality assessment
        # Step 7: Return


class BMP280TemperatureProcessor(BaseSensorProcessor):
    """
    BMP280 Temperature Sensor Processor.

    Same sensor as BMP280Pressure but processes temperature reading.
    Temperature data is used for pressure compensation internally,
    but can also be read as standalone value.

    Note: BMP280 temperature accuracy (±1°C) is lower than SHT31 (±0.2°C).
    Use SHT31 if high temperature accuracy is required.
    """

    TEMP_MIN = -40.0  # °C
    TEMP_MAX = 85.0  # °C

    def get_sensor_type(self) -> str:
        return "bmp280_temp"

    # Similar implementation to SHT31TemperatureProcessor
    # (see temperature.py for reference)
```

**Referenz:**
- [BMP280 Datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp280-ds001.pdf)
- [ESP32 BMP280 Tutorial](https://randomnerdtutorials.com/esp32-bme280-arduino-ide-pressure-temperature-humidity/)

---

## 3. Phase 3: Nice-to-Have Sensoren (Woche 5-6)

### 3.1 CO2 Sensor (SEN0220 / MH-Z16 / MH-Z19)

**Priorität:** 🟢 MITTEL
**Komplexität:** High
**Geschätzte Zeit:** 6-8 Stunden (inkl. Tests)

> **Kanonische Hardware (AUT-527):** DFRobot SEN0220 = Winsen MH-Z16, UART, 0–50000 ppm.
> ESP32-S3 DevKitC-1 N8R8: UART1 TX=GPIO17, RX=GPIO18.
> Firmware-Driver: `El Trabajante/src/drivers/mhz19_uart.cpp` — bereits korrekt für MH-Z16 (50000 ppm, Serial2).

#### 3.1.1 Sensor-Spezifikationen

| Eigenschaft | SEN0220 / MH-Z16 | MH-Z19B | SCD30 |
|-------------|-----------------|---------|-------|
| **Technology** | NDIR | NDIR | NDIR + SHT31 |
| **CO2 Range** | 0 - 50000 ppm | 0 - 5000 ppm | 400 - 10000 ppm |
| **CO2 Accuracy** | ±(50ppm + 5%) | ±(50ppm + 5%) | ±(30ppm + 3%) |
| **Communication** | UART (9600 baud) | UART (9600 baud) | I2C (0x61) |
| **Warm-up Time** | 3 minutes | 3 minutes | 2 seconds (data after 2 min) |
| **Calibration** | ABC (Auto Baseline Correction) | ABC | Manual 1-Point (400 ppm) |
| **Temperature** | Not included | Not included | ±0.3°C |
| **Humidity** | Not included | Not included | ±2% RH |

#### 3.1.2 ESP32 Hardware-Setup

**Kanonisch: SEN0220 / MH-Z16 auf ESP32-S3 DevKitC-1 (AUT-527)**

```
UART1 Connection (ESP32-S3 DevKitC-1 N8R8):
- VCC → 5V (External power! SEN0220/MH-Z16 requires 150mA peak)
- GND → GND
- TX (Sensor) → GPIO18 (ESP RX, uart_rx_pin=18)
- RX (Sensor) → GPIO17 (ESP TX, uart_tx_pin=17)

ESP32-S3 UART-Belegung:
- UART0: 43/44 (reserviert, Boot-Log)
- UART1: GPIO17 (TX), GPIO18 (RX) — CO2 Sensor
- USB-CDC: GPIO19/20 (reserviert)

Firmware-Driver: El Trabajante/src/drivers/mhz19_uart.cpp
  - Serial2 (UART1), 9600 8N1
  - MH-Z19/MH-Z16 9-Byte-Frame, RAW ppm
  - Warmup-Phase ~3 min → quality="warming_up"

Config-Push vom Server (AUT-527):
  interface_type: "UART"
  uart_rx_pin: 18   (ESP RX ← Sensor TX)
  uart_tx_pin: 17   (ESP TX → Sensor RX)
  uart_baud:   9600

Löschen (AUT-527): `DELETE /sensors/{esp_id}/{config_id}` → Server `_build_sensor_delete_tombstones()` sendet für `co2` zwei Einträge mit `"active": false` (GPIO aus DB + UART1-Komplement 17↔18), inkl. `uart_rx_pin`/`uart_tx_pin`. ESP verarbeitet Tombstone **vor** `validateSensorConfig()`.

⚠️ WICHTIG:
- Sensor needs 5V power (NOT 3.3V!)
- GPIO17/18 durch driver reserviert, kein ADC-Konflikt
- Allow 3 minutes warm-up before readings
```

**Option B: SCD30 (I2C)**

```
I2C Connection:
- VCC → 5V (SCD30 requires 3.3-5.5V, 75mA peak)
- GND → GND
- SDA → GPIO8 (ESP32-S3 I2C SDA) / GPIO21 (WROOM)
- SCL → GPIO9 (ESP32-S3 I2C SCL) / GPIO22 (WROOM)

I2C Address: 0x61 (fixed)

ESP32 Library:
- SparkFun_SCD30 (Arduino Library Manager)
- Wire.h

Features:
- Integrated SHT31 (Temperature + Humidity)
- Auto-calibration + Manual calibration
- Altitude compensation
```

#### 3.1.3 Server-Side Implementation

**Datei:** `co2.py`
**Klassen:**
1. `MHZ19CO2Processor` (sensor_type: `"mhz19_co2"`) — auch für SEN0220/MH-Z16 (50000 ppm range)
2. `SCD30CO2Processor` (sensor_type: `"scd30_co2"`)

**Komplexität-Hinweise:**

1. **UART Communication (SEN0220/MH-Z16/MH-Z19):**
   - ESP32 sendet 9-byte Kommando
   - Sensor antwortet mit 9-byte Response
   - Checksum-Validation im Firmware-Driver (`mhz19_uart.cpp`)
   - Server verarbeitet nur fertige PPM-Werte vom ESP32
   - `interface_type="UART"` wird von `_infer_interface_type()` fuer Sensortyp `"co2"` automatisch gesetzt

2. **Calibration:**
   - ABC (Automatic Baseline Correction): 400 ppm outdoor air
   - Manual: Expose sensor to 400 ppm for 20 minutes
   - Single-point calibration only

3. **Quality Assessment:**
   - Indoor Air Quality Levels:
     - Good: 400-600 ppm
     - Fair: 600-1000 ppm
     - Poor: 1000-2000 ppm
     - Bad: >2000 ppm (ventilation required)

**Implementierungs-Template:**

```python
class MHZ19CO2Processor(BaseSensorProcessor):
    """
    MHZ-19/MH-Z16/SEN0220 NDIR CO2 Sensor Processor.

    ESP32-side driver (mhz19_uart.cpp) handles UART communication and checksum validation.
    Server-side processing focuses on:
    - Validation of CO2 range (0-50000 ppm for SEN0220/MH-Z16)
    - Quality assessment (Indoor Air Quality levels)
    - Optional altitude compensation

    Sensor Specifications (SEN0220 / MH-Z16):
    - Range: 0 - 50000 ppm (parts per million)
    - Accuracy: ±(50ppm + 5%)
    - Communication: UART (9600 baud, 8N1)
    - Warm-up: 3 minutes

    ESP32-S3 Setup (AUT-527):
    - Driver: mhz19_uart.cpp, Serial2
    - uart_rx_pin=18 (ESP RX), uart_tx_pin=17 (ESP TX)
    - Power: 5V, 150mA peak (external power recommended)
    - Warm-up: quality="warming_up" during first ~3 min

    Indoor Air Quality Levels:
    - Excellent: 400-600 ppm (outdoor air level)
    - Good: 600-1000 ppm (acceptable)
    - Fair: 1000-1500 ppm (drowsiness possible)
    - Poor: 1500-2000 ppm (poor concentration)
    - Bad: >2000 ppm (ventilation required immediately)
    """

    CO2_MIN = 0.0  # ppm
    CO2_MAX = 50000.0  # ppm (SEN0220/MH-Z16 limit; MH-Z19B: 5000 ppm)
    CO2_OUTDOOR = 400.0  # ppm (typical outdoor level)
    CO2_EXCELLENT_MAX = 600.0  # ppm
    CO2_GOOD_MAX = 1000.0  # ppm
    CO2_FAIR_MAX = 1500.0  # ppm
    CO2_POOR_MAX = 2000.0  # ppm

    def get_sensor_type(self) -> str:
        return "mhz19_co2"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process MHZ-19/MH-Z16/SEN0220 CO2 reading.

        Args:
            raw_value: CO2 in ppm (from mhz19_uart.cpp driver)
            calibration: {"offset": float} (optional ppm offset)
            params: {
                "altitude_compensation": float (meters above sea level),
                "decimal_places": int
            }

        Returns:
            ProcessingResult with CO2 ppm, unit "ppm", quality
        """
```

**Referenz:**
- [DFRobot SEN0220 Wiki](https://wiki.dfrobot.com/Infrared_CO2_Sensor_0-50000ppm_SKU__SEN0220)
- [Winsen MH-Z16 Datasheet](https://www.winsen-sensor.com/d/files/infrared-gas-sensor/mh-z16-co2-detection-module-manual.pdf)
- [MHZ-19B Manual](https://www.winsen-sensor.com/d/files/infrared-gas-sensor/mh-z19b-co2-ver1_0.pdf)
- [SCD30 Datasheet](https://www.sensirion.com/en/environmental-sensors/carbon-dioxide-sensors/carbon-dioxide-sensors-scd30/)

---

### 3.2 Light Sensor (TSL2561/BH1750)

**Priorität:** 🟢 MITTEL
**Komplexität:** Low
**Geschätzte Zeit:** 3-4 Stunden (inkl. Tests)

#### 3.2.1 Sensor-Spezifikationen

| Eigenschaft | TSL2561 | BH1750 |
|-------------|---------|---------|
| **Range** | 0.1 - 40,000 lux | 1 - 65,535 lux |
| **Resolution** | 0.1 lux | 1 lux |
| **Accuracy** | ±20% | ±20% |
| **Communication** | I2C (0x29, 0x39, 0x49) | I2C (0x23, 0x5C) |
| **Response Time** | 13.7 ms - 402 ms | 120 ms |
| **Spectrum** | Broadband + IR | Visible light (human eye) |

#### 3.2.2 ESP32 Hardware-Setup

**Option A: TSL2561**

```
I2C Connection:
- VCC → 3.3V
- GND → GND
- SDA → GPIO21
- SCL → GPIO22

I2C Address: 0x39 (default, ADDR pin floating)
- 0x29 (ADDR → GND)
- 0x49 (ADDR → VCC)

ESP32 Library: Adafruit_TSL2561

Features:
- Dual photodiodes (Broadband + IR)
- Automatic gain control
- Human eye response approximation
```

**Option B: BH1750 (Recommended for simplicity)**

```
I2C Connection:
- VCC → 3.3V
- GND → GND
- SDA → GPIO21
- SCL → GPIO22

I2C Address: 0x23 (default, ADDR pin → GND)
- 0x5C (ADDR → VCC)

ESP32 Library: BH1750 by Christopher Laws

Features:
- Single photodiode (visible light)
- Very simple protocol
- Direct lux output
```

#### 3.2.3 Server-Side Implementation

**Datei:** `light.py`
**Klasse:** `LightSensorProcessor` (sensor_type: `"light"`)

**Implementierungs-Hinweise:**

```python
class LightSensorProcessor(BaseSensorProcessor):
    """
    Light Sensor Processor (TSL2561/BH1750/Generic).

    ESP32-side library already converts raw sensor data to lux.
    Server-side processing focuses on:
    - Validation of lux range
    - Quality assessment (light levels)
    - Optional unit conversion (lux, fc)

    Sensor Specifications:
    - Range: 0.1 - 65,535 lux (sensor-dependent)
    - Accuracy: ±20%
    - Communication: I2C
    - Resolution: 0.1 - 1 lux

    ESP32 Setup:
    - Library: BH1750 (simple) or Adafruit_TSL2561 (advanced)
    - I2C: GPIO21 (SDA), GPIO22 (SCL)
    - Address: 0x23 (BH1750) or 0x39 (TSL2561)

    Light Levels (Reference):
    - Moonlight: 0.1 lux
    - Living room: 50-100 lux
    - Office: 300-500 lux
    - Sunlight (indirect): 10,000 lux
    - Sunlight (direct): 100,000 lux

    Unit Conversions:
    - 1 lux ≈ 0.0929 fc (foot-candle)
    """

    LUX_MIN = 0.0
    LUX_MAX = 100000.0  # Upper limit (direct sunlight)

    # Quality thresholds (for indoor environments)
    LUX_DARK = 10.0  # Below this: dark
    LUX_DIM = 100.0  # 10-100: dim
    LUX_NORMAL = 500.0  # 100-500: normal indoor
    LUX_BRIGHT = 10000.0  # 500-10000: bright

    def get_sensor_type(self) -> str:
        return "light"
```

**Referenz:** [BH1750 Tutorial](https://lastminuteengineers.com/bh1750-ambient-light-sensor-arduino-tutorial/)

---

### 3.3 Flow Sensor (YFS201)

**Priorität:** 🟢 MITTEL
**Komplexität:** Medium
**Geschätzte Zeit:** 5-6 Stunden (inkl. Tests)

#### 3.3.1 Sensor-Spezifikationen

| Eigenschaft | Wert |
|-------------|------|
| **Sensor-Typ** | Hall Effect Flow Sensor |
| **Flow Range** | 1 - 30 L/min (YF-S201) |
| **Output** | Pulse frequency (Hz) |
| **Accuracy** | ±10% |
| **Pulse Factor** | ~4.5 pulses/second per L/min (calibration required) |
| **Operating Voltage** | 5V DC |
| **Current** | 15 mA @ 5V |

#### 3.3.2 ESP32 Hardware-Setup

```
Flow Sensor Connection:
- Red (VCC) → 5V (External power)
- Black (GND) → GND
- Yellow (Signal) → GPIO25 (Interrupt-capable pin)

Interrupt Configuration:
- Mode: RISING edge
- Debounce: Software debounce recommended (10ms)
- Counter: Increment on each pulse

ESP32 Code Pattern:
volatile unsigned int pulseCount = 0;
void IRAM_ATTR pulseCounter() {
    pulseCount++;
}

setup() {
    pinMode(GPIO25, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(GPIO25), pulseCounter, RISING);
}

loop() {
    // Calculate flow every 1 second
    detachInterrupt(GPIO25);
    float flow_L_per_min = pulseCount / calibrationFactor;
    pulseCount = 0;
    attachInterrupt(GPIO25, pulseCounter, RISING);
}

Calibration Factor:
- YF-S201: 4.5 pulses/sec per L/min (typical)
- Actual factor varies per sensor → measure with known flow rate
```

#### 3.3.3 Server-Side Implementation

**Datei:** `flow.py`
**Klasse:** `FlowSensorProcessor` (sensor_type: `"flow"`)

**Komplexität-Hinweise:**

1. **Pulse Counting:** ESP32 zählt Pulses, berechnet Flow Rate
2. **Time Windowing:** ESP32 sendet Pulses pro Time-Window (z.B. 1 second)
3. **Server Processing:**
   - Convert pulses → Flow Rate (L/min, mL/min, gal/min)
   - Validate range
   - Quality assessment

**Implementierungs-Template:**

```python
class FlowSensorProcessor(BaseSensorProcessor):
    """
    Flow Sensor Processor (Hall Effect, e.g., YF-S201).

    ESP32-side code counts pulses using GPIO interrupt and calculates flow rate.
    Server-side processing focuses on:
    - Validation of flow range
    - Unit conversion (L/min, mL/min, gal/min)
    - Quality assessment

    Sensor Specifications:
    - Flow Range: 1 - 30 L/min (YF-S201)
    - Output: Pulse frequency (Hz)
    - Calibration Factor: ~4.5 pulses/sec per L/min (sensor-specific)
    - Accuracy: ±10%

    ESP32 Setup:
    - GPIO: Interrupt-capable pin (e.g., GPIO25)
    - Interrupt: RISING edge
    - Power: 5V DC, 15mA

    Important Notes:
    - Calibration factor varies per sensor (measure with known flow)
    - Minimum flow: 1 L/min (below this, sensor may not trigger)
    - Air in line: Can cause erratic readings
    """

    FLOW_MIN = 0.0  # L/min (zero flow)
    FLOW_MAX = 50.0  # L/min (upper limit for YF-S201)
    FLOW_TYPICAL_MIN = 1.0  # L/min (sensor minimum detection)

    def get_sensor_type(self) -> str:
        return "flow"

    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        """
        Process flow sensor reading.

        Args:
            raw_value: Flow rate in L/min (calculated by ESP32)
            calibration: {"factor": float} (pulses/sec per L/min)
            params: {
                "unit": "l_min"|"ml_min"|"gal_min",
                "decimal_places": int
            }

        Returns:
            ProcessingResult with flow rate, unit, quality

        Note:
        - ESP32 already calculated flow rate using pulseCount / calibrationFactor
        - Server mainly validates and converts units
        """
```

**Referenz:** [Water Flow Sensor Tutorial](https://randomnerdtutorials.com/esp32-water-flow-sensor/)

---

## 4. ESP32 Hardware-Spezifikationen

### 4.1 ESP32 ADC Limitations (KRITISCH!)

**Für KI-Agent: Diese Information ist ESSENTIELL für ADC-basierte Sensoren (EC, Moisture, pH)**

| Problem | Beschreibung | Lösung |
|---------|--------------|--------|
| **ADC2 + WiFi Conflict** | ADC2 kann NICHT verwendet werden wenn WiFi aktiv ist | ⚠️ **NUR ADC1-Pins verwenden (GPIO32-39)** |
| **Accuracy** | ±10% Fehler, nicht-linear bei <100mV und >2.5V | ✅ Externe ADC (ADS1115, 16-bit) für präzise Messungen |
| **Noise** | Rauschen durch WiFi, Power Supply | ✅ 0.1µF Kondensator + Multisampling (10-100 Samples) |
| **Calibration** | Factory calibration ungenau | ✅ `esp_adc_cal_characterize()` verwenden |

**ADC1 Pins (ESP32 WROOM):**
- GPIO32, GPIO33, GPIO34, GPIO35, GPIO36, GPIO39 (ADC1_CH4-CH7, ADC1_CH0-CH3)

**ADC2 Pins (NIEMALS mit WiFi!):**
- GPIO0, GPIO2, GPIO4, GPIO12, GPIO13, GPIO14, GPIO15, GPIO25, GPIO26, GPIO27

**Empfehlung für Analog-Sensoren:**

```python
# Metadata sollte ADC-Typ enthalten:
metadata={
    "adc_type": "12bit" | "16bit",  # ESP32 native oder ADS1115
    "adc_voltage": 3.3 | 5.0,        # Voltage range
    "multisampling": 10,             # Anzahl Samples
}
```

### 4.2 I2C Bus-Management

**Für KI-Agent: Multiple I2C-Sensoren am gleichen Bus**

```
ESP32 Default I2C Pins:
- SDA: GPIO21
- SCL: GPIO22

I2C Bus kann mehrere Sensoren gleichzeitig unterstützen:
- SHT31: 0x44 oder 0x45
- BMP280: 0x76 oder 0x77
- BH1750: 0x23 oder 0x5C
- SCD30: 0x61
- ADS1115: 0x48

⚠️ Adress-Konflikte vermeiden:
- Jeder Sensor muss unique Address haben
- Bei Conflict: I2C Multiplexer (TCA9548A) verwenden
```

### 4.3 GPIO Pin-Zuordnung (Referenz)

| Sensor-Typ | Kommunikation | ESP32 Pins | Bemerkungen |
|------------|---------------|-----------|-------------|
| **pH, EC, Moisture** | ADC | GPIO32-39 (ADC1) | ⚠️ NICHT ADC2! |
| **DS18B20** | OneWire | Beliebig (z.B. GPIO17) | 4.7kΩ Pull-up |
| **SHT31, BMP280, BH1750** | I2C | GPIO21 (SDA), GPIO22 (SCL) | Default I2C |
| **SCD30** | I2C | GPIO21 (SDA), GPIO22 (SCL) | I2C 0x61 |
| **MHZ-19B** | UART | GPIO16 (RX2), GPIO17 (TX2) | 5V Power! |
| **Flow Sensor** | Interrupt | Beliebig (z.B. GPIO25) | Interrupt-fähig |

---

## 5. Testing-Strategie

### 5.1 Unit-Test Template

**Für KI-Agent: Alle Sensor-Prozessoren MÜSSEN diese Tests haben**

**Datei:** `tests/unit/test_{sensor_type}_processor.py`

**Minimum Test-Cases (12 Tests pro Processor):**

```python
import pytest
from god_kaiser_server.src.sensors.sensor_libraries.active.{module} import {ProcessorClass}

class Test{ProcessorClass}:
    """Unit tests for {Sensor} processor."""

    @pytest.fixture
    def processor(self):
        return {ProcessorClass}()

    # 1. Basic Tests
    def test_get_sensor_type(self, processor):
        """Test sensor type identifier."""
        assert processor.get_sensor_type() == "{sensor_type_id}"

    def test_process_valid_value(self, processor):
        """Test processing valid sensor reading."""
        result = processor.process(raw_value={valid_value})
        assert result.value == pytest.approx({expected_value}, rel=0.01)
        assert result.unit == "{expected_unit}"
        assert result.quality == "good"

    # 2. Calibration Tests
    def test_process_with_calibration(self, processor):
        """Test processing with calibration."""
        calibration = {calibration_dict}
        result = processor.process(raw_value={value}, calibration=calibration)
        assert result.metadata["calibrated"] is True

    def test_calibrate_two_point(self, processor):
        """Test 2-point calibration (if supported)."""
        calibration_points = [{point1}, {point2}]
        calibration = processor.calibrate(calibration_points)
        assert "slope" in calibration or "offset" in calibration

    # 3. Validation Tests
    def test_validate_valid_value(self, processor):
        """Test validation of valid value."""
        validation = processor.validate({valid_value})
        assert validation.valid is True

    def test_validate_below_minimum(self, processor):
        """Test validation of value below range."""
        validation = processor.validate({below_min_value})
        assert validation.valid is False

    def test_validate_above_maximum(self, processor):
        """Test validation of value above range."""
        validation = processor.validate({above_max_value})
        assert validation.valid is False

    # 4. Unit Conversion Tests (if applicable)
    def test_process_unit_conversion(self, processor):
        """Test unit conversion."""
        params = {"unit": "{alternate_unit}"}
        result = processor.process(raw_value={value}, params=params)
        assert result.unit == "{alternate_unit}"

    # 5. Quality Assessment Tests
    def test_process_quality_good(self, processor):
        """Test quality assessment: good."""
        result = processor.process(raw_value={typical_value})
        assert result.quality == "good"

    def test_process_quality_fair(self, processor):
        """Test quality assessment: fair."""
        result = processor.process(raw_value={edge_value})
        assert result.quality == "fair"

    def test_process_quality_poor(self, processor):
        """Test quality assessment: poor."""
        result = processor.process(raw_value={extreme_value})
        assert result.quality == "poor"

    # 6. Parameter Tests
    def test_get_default_params(self, processor):
        """Test default parameters."""
        params = processor.get_default_params()
        assert isinstance(params, dict)
```

### 5.2 Test-Coverage-Ziel

**Für KI-Agent: Minimum Coverage-Requirements**

- ✅ **Unit-Tests:** >80% Code Coverage pro Processor
- ✅ **Line Coverage:** Alle process(), validate(), calibrate() Methoden
- ✅ **Branch Coverage:** Alle if/else Zweige getestet
- ✅ **Edge Cases:** Min/Max Werte, Calibration On/Off, Unit Conversions

**Coverage prüfen:**

```bash
cd "El Servador"
poetry run pytest god_kaiser_server/tests/unit/test_{sensor}_processor.py --cov=god_kaiser_server/src/sensors/sensor_libraries/active/{sensor}.py --cov-report=term
```

---

## 6. MQTT-Integration

### 6.1 Topic-Schema (Referenz)

**Für KI-Agent: MQTT-Topics sind bereits implementiert, KEINE Änderung nötig**

**Sensor Data (ESP32 → Server):**

```
Topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
QoS: 1
Payload: {
    "ts": 1735818000,
    "esp_id": "ESP_12AB34CD",
    "gpio": 34,
    "sensor_type": "{sensor_type_id}",  # ← Mapping zu Processor
    "raw": 2150,
    "value": 0.0,
    "unit": "",
    "quality": "stale",
    "raw_mode": true
}
```

**Pi-Enhanced Response (Server → ESP32):**

```
Topic: kaiser/god/esp/{esp_id}/pi_enhanced/response
QoS: 1
Payload: {
    "value": 7.2,
    "unit": "pH",
    "quality": "good"
}
```

### 6.2 Sensor-Type Mapping

**Für KI-Agent: Diese Tabelle definiert sensor_type → Processor Mapping**

| ESP32 `sensor_type` | Server Processor | Library File | Status |
|---------------------|------------------|--------------|--------|
| `"ph"` | `PHSensorProcessor` | `ph_sensor.py` | ✅ Phase 0 |
| `"ds18b20"` | `DS18B20Processor` | `temperature.py` | ✅ Phase 1 |
| `"sht31_temp"` | `SHT31TemperatureProcessor` | `temperature.py` | ✅ Phase 1 |
| `"sht31_humidity"` | `SHT31HumidityProcessor` | `humidity.py` | ✅ Phase 1 |
| `"ec"` | `ECSensorProcessor` | `ec_sensor.py` | ⏳ Phase 2 |
| `"moisture"` | `MoistureSensorProcessor` | `moisture.py` | ⏳ Phase 2 |
| `"bmp280_pressure"` | `BMP280PressureProcessor` | `pressure.py` | ⏳ Phase 2 |
| `"bmp280_temp"` | `BMP280TemperatureProcessor` | `pressure.py` | ⏳ Phase 2 |
| `"mhz19_co2"` | `MHZ19CO2Processor` | `co2.py` | ⏳ Phase 3 |
| `"scd30_co2"` | `SCD30CO2Processor` | `co2.py` | ⏳ Phase 3 |
| `"light"` | `LightSensorProcessor` | `light.py` | ⏳ Phase 3 |
| `"flow"` | `FlowSensorProcessor` | `flow.py` | ⏳ Phase 3 |

### 6.3 MQTT Handler Integration (bereits implementiert)

**Für KI-Agent: KEINE Änderung nötig - nur zur Information**

```python
# mqtt/handlers/sensor_handler.py (Line 275-320)

async def _trigger_pi_enhanced_processing(
    self,
    esp_id: str,
    gpio: int,
    sensor_type: str,  # ← verwendet für Processor-Lookup
    raw_value: float,
    sensor_config,
) -> Optional[dict]:
    """
    Pi-Enhanced Processing Flow (bereits implementiert).

    1. Get Library Loader
    2. loader.get_processor(sensor_type)  # ← Dynamische Processor-Auswahl
    3. processor.process(raw_value, calibration, params)
    4. Return processed value
    """
    from ...sensors.library_loader import get_library_loader

    loader = get_library_loader()
    processor = loader.get_processor(sensor_type)  # ← Magic happens here!

    if not processor:
        logger.error(f"No processor found for sensor type: {sensor_type}")
        return None

    result = processor.process(
        raw_value=raw_value,
        calibration=sensor_config.calibration_data if sensor_config else None,
        params=sensor_config.metadata.get("processing_params") if sensor_config else None,
    )

    return {
        "processed_value": result.value,
        "unit": result.unit,
        "quality": result.quality,
    }
```

---

## 7. Code-Qualitäts-Standards

### 7.1 Pflicht-Anforderungen

**Für KI-Agent: ALLE diese Standards MÜSSEN erfüllt sein**

| Standard | Requirement | Validierung |
|----------|-------------|-------------|
| **Type Hints** | Alle Methoden vollständig annotiert | mypy check |
| **Docstrings** | Google-Style Docstrings für Public Methods | Manual review |
| **Error Handling** | Graceful Degradation, keine unhandled Exceptions | pytest |
| **Logging** | logger.error, logger.warning bei Fehlern | Manual review |
| **Unit-Tests** | >80% Code Coverage | pytest --cov |
| **Integration-Tests** | MQTT Flow getestet | pytest integration/ |
| **Validation** | Input-Validation mit ValidationResult | pytest |
| **Quality Assessment** | Sinnvolle quality: "good", "fair", "poor", "error" | pytest |

### 7.2 Code-Review-Checkliste

**Für KI-Agent: Vor Completion ALLE Punkte prüfen**

- [ ] Folgt Base-Processor Interface korrekt (`BaseSensorProcessor`)
- [ ] Alle Abstract Methods implementiert (`process`, `validate`, `get_sensor_type`)
- [ ] Sensor-Type eindeutig und konsistent (MQTT-Mapping)
- [ ] RAW-Value-Range korrekt validiert (Min/Max)
- [ ] Calibration (wenn unterstützt) funktioniert und getestet
- [ ] Params korrekt verarbeitet (Unit-Conversion, Decimal Places)
- [ ] Quality Assessment sinnvoll und getestet
- [ ] Error Messages präzise und hilfreich
- [ ] Unit-Tests PASS (>80% Coverage)
- [ ] Docstrings vollständig (Class, Methods, Args, Returns)
- [ ] Type Hints korrekt (mypy clean)
- [ ] Logging bei kritischen Pfaden (nicht im Sensor-Processor selbst!)

---

## 8. Troubleshooting & Debugging

### 8.1 Häufige Probleme

**Für KI-Agent: Debug-Referenz bei Problemen**

| Problem | Ursache | Lösung |
|---------|---------|--------|
| **"No processor found for sensor type"** | sensor_type Mismatch | Check `get_sensor_type()` return value vs. MQTT payload |
| **ADC value out of range** | ESP32 ADC2 verwendet (WiFi conflict) | Nur ADC1 Pins verwenden (GPIO32-39) |
| **EC/pH readings unstable** | ESP32 ADC noise | Externe ADC (ADS1115) verwenden + 0.1µF Kondensator |
| **I2C sensor not detected** | Adress conflict | Check I2C address (i2cdetect), change jumper/ADDR pin |
| **CO2 sensor always reads 400 ppm** | Sensor in ABC mode | Disable ABC or expose to different CO2 levels |
| **Flow sensor reads 0** | Flow below minimum threshold | YF-S201 minimum: 1 L/min |
| **Calibration not applied** | calibration_data not stored in DB | Check SensorConfig.calibration_data field |
| **Quality always "poor"** | _assess_quality() logic error | Review quality thresholds in Processor |

### 8.2 Testing-Workflow

**Für KI-Agent: Schritt-für-Schritt Test-Prozess**

```bash
# 1. Unit-Tests für neuen Sensor
cd "El Servador"
poetry run pytest god_kaiser_server/tests/unit/test_{sensor}_processor.py -v

# 2. Coverage Check (Minimum: 80%)
poetry run pytest god_kaiser_server/tests/unit/test_{sensor}_processor.py --cov=god_kaiser_server/src/sensors/sensor_libraries/active/{sensor}.py --cov-report=term

# 3. Integration-Test (MQTT Flow)
poetry run pytest god_kaiser_server/tests/integration/test_sensor_mqtt_flow.py -v -k "test_{sensor}"

# 4. Library Loader Verification
poetry run python -c "from god_kaiser_server.src.sensors.library_loader import get_library_loader; loader = get_library_loader(); print(f'Available sensors: {loader.get_available_sensors()}'); processor = loader.get_processor('{sensor_type}'); print(f'Processor: {processor}')"

# 5. Manual Processing Test
poetry run python -c "from god_kaiser_server.src.sensors.sensor_libraries.active.{sensor} import {ProcessorClass}; p = {ProcessorClass}(); result = p.process({test_value}); print(f'Result: {result.value} {result.unit}, Quality: {result.quality}')"
```

---

## 9. Implementation Checklist (Phase 2 & 3)

**Für KI-Agent: Track Progress pro Sensor**

### Phase 2 (Woche 3-4) 🟡 HOCH

#### EC Sensor
- [ ] Implementierung: `ec_sensor.py` - `ECSensorProcessor`
- [ ] 2-Punkt-Calibration implementiert
- [ ] Temperature Compensation implementiert
- [ ] Unit-Conversion: µS/cm, mS/cm, ppm
- [ ] Unit-Tests: `test_ec_sensor_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow
- [ ] Dokumentation: Hardware-Setup (ADS1115 vs. ESP32 ADC)

#### Moisture Sensor
- [ ] Implementierung: `moisture.py` - `MoistureSensorProcessor`
- [ ] 2-Punkt-Calibration (dry/wet)
- [ ] Invert-Logic (high voltage = dry)
- [ ] Unit-Tests: `test_moisture_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow

#### BMP280 Pressure + Temperature
- [ ] Implementierung: `pressure.py`
  - [ ] `BMP280PressureProcessor`
  - [ ] `BMP280TemperatureProcessor`
- [ ] Unit-Conversion: hPa, Pa, mmHg, inHg
- [ ] Sea-Level Correction (altitude compensation)
- [ ] Unit-Tests: `test_bmp280_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow (2 Sensoren gleichzeitig)

### Phase 3 (Woche 5-6) 🟢 MITTEL

#### CO2 Sensor
- [ ] Implementierung: `co2.py`
  - [ ] `MHZ19CO2Processor`
  - [ ] `SCD30CO2Processor` (optional)
- [ ] IAQ (Indoor Air Quality) Levels
- [ ] Altitude Compensation
- [ ] Unit-Tests: `test_co2_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow

#### Light Sensor
- [ ] Implementierung: `light.py` - `LightSensorProcessor`
- [ ] Unit-Conversion: lux, fc
- [ ] Light Level Assessment (dark, dim, normal, bright)
- [ ] Unit-Tests: `test_light_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow

#### Flow Sensor
- [ ] Implementierung: `flow.py` - `FlowSensorProcessor`
- [ ] Unit-Conversion: L/min, mL/min, gal/min
- [ ] Pulse-to-Flow Calculation
- [ ] Unit-Tests: `test_flow_processor.py` (>80% Coverage)
- [ ] Integration-Test: MQTT Flow

---

## 10. Web-Recherche Referenzen

**Für KI-Agent: Nutze diese Quellen für detaillierte Sensor-Spezifikationen**

### ESP32 ADC:
- [ESP32 ADC Tutorial - ElectronicsHub](https://www.electronicshub.org/esp32-adc-tutorial/)
- [ESP32 ADC Calibration - ESP32 Forum](https://esp32.com/viewtopic.php?t=26009)
- [ESP-IDF ADC Documentation](https://docs.espressif.com/projects/esp-idf/en/v4.4/esp32/api-reference/peripherals/adc.html)

### Analog Sensors (pH, EC, Moisture):
- [GreenPonik ESP32 EC+pH Library](https://github.com/GreenPonik/esp32-read-ph-and-ec-with-ADC-example)
- [DFRobot pH Sensor with ESP32](https://community.dfrobot.com/makelog-308047.html)
- [Capacitive Moisture Sensor Tutorial](https://how2electronics.com/capacitive-soil-moisture-sensor-esp32-esp8266/)

### Digital Sensors (I2C, OneWire):
- [DS18B20 with ESP32 - ElectronicWings](https://www.electronicwings.com/esp32/ds18b20-sensor-interfacing-with-esp32)
- [SHT31 with ESP32 - Adafruit](https://learn.adafruit.com/adafruit-sht31-d-temperature-and-humidity-sensor-breakout/wiring-and-test)
- [BMP280 with ESP32 - Random Nerd Tutorials](https://randomnerdtutorials.com/esp32-bme280-arduino-ide-pressure-temperature-humidity/)
- [BH1750 Light Sensor Tutorial](https://lastminuteengineers.com/bh1750-ambient-light-sensor-arduino-tutorial/)

### Special Sensors (CO2, Flow):
- [MHZ-19B Manual](https://www.winsen-sensor.com/d/files/infrared-gas-sensor/mh-z19b-co2-ver1_0.pdf)
- [SCD30 Datasheet](https://www.sensirion.com/en/environmental-sensors/carbon-dioxide-sensors/carbon-dioxide-sensors-scd30/)
- [Water Flow Sensor Tutorial](https://randomnerdtutorials.com/esp32-water-flow-sensor/)

---

## 11. Zusammenfassung & Next Steps

### 11.1 Implementierungs-Reihenfolge (Empfehlung)

**Für KI-Agent: Folge dieser Reihenfolge für optimale Lernkurve**

1. **Start:** EC Sensor (ähnlich pH - ADC Pattern bekannt)
2. **Danach:** Moisture Sensor (einfachster ADC Sensor)
3. **Dann:** BMP280 (2 Processors, I2C Pattern)
4. **Später:** Light Sensor (einfachster I2C Sensor)
5. **Später:** Flow Sensor (Interrupt-Pattern, komplex)
6. **Zuletzt:** CO2 Sensor (UART, komplexeste Implementation)

### 11.2 Geschätzte Zeitaufwand

| Phase | Sensoren | Zeit (inkl. Tests) |
|-------|----------|-------------------|
| **Phase 2** | EC, Moisture, BMP280 (3 Sensoren, 4 Processors) | 12-15 Stunden |
| **Phase 3** | CO2, Light, Flow (3 Sensoren, 3 Processors) | 14-18 Stunden |
| **Total** | 6 Sensoren, 7 Processors | **26-33 Stunden** |

### 11.3 Erfolgs-Kriterien

**Für KI-Agent: Definition of Done**

✅ **Alle Processors implementiert** (7 Stück)
✅ **Alle Unit-Tests PASS** (>80% Coverage)
✅ **Integration-Tests PASS** (MQTT Flow)
✅ **Library Loader erkennt alle Sensoren** (`loader.get_available_sensors()`)
✅ **Docstrings vollständig** (Class + Methods)
✅ **Type Hints korrekt** (mypy clean)
✅ **Code-Review-Checkliste erfüllt** (alle Punkte ✓)

---

**Ende des Implementierungs-Dokuments**

**Für KI-Agent: Dieses Dokument enthält ALLE Informationen für erfolgreiche Implementation von Phase 2 & 3. Bei Unklarheiten:**
1. Konsultiere Referenz-Implementierungen (Phase 1)
2. Nutze Web-Recherche-Links für Sensor-Details
3. Befolge Code-Qualitäts-Standards strikt
4. Teste gründlich (>80% Coverage)

**Viel Erfolg! 🚀**
