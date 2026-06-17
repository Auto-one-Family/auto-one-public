# Sensor Library Flow - Server & Frontend Perspektive

## Overview

Wie das dynamische Sensor-Library-System auf dem Server funktioniert und wie neue Sensoren integriert werden. Vollständige Dokumentation des Pi-Enhanced Processing-Systems mit automatischem Library-Deployment zu ESP32-Geräten.

**Korrespondiert mit:** `El Trabajante/docs/system-flows/02-sensor-reading-flow.md` (Sensor-Messungen), `El Servador/god_kaiser_server/src/sensors/` (Server-Implementation)

---

## Voraussetzungen

- [ ] Server läuft (`localhost:8000`)
- [ ] Frontend läuft (`localhost:5173`)
- [ ] **Library-System initialisiert:** `src/sensors/sensor_libraries/active/` enthält Libraries
- [ ] **ESP32 mit Pi-Enhanced Mode:** Sensor-Config hat `pi_enhanced: true`
- [ ] **Sensor sendet in raw_mode:** `raw_mode: true` im Payload

---

## Teil 1: Library-System Architektur

### 1.1 Dynamic Library Loading

Das Library-System verwendet **Python's `importlib`** für dynamisches Laden von Sensor-Processing-Bibliotheken zur Laufzeit. Alle Libraries liegen in `sensor_libraries/active/` und werden automatisch entdeckt.

**Code-Location:** `src/sensors/library_loader.py` (1-285)

```python
class LibraryLoader:
    """
    Singleton library loader for sensor processors.

    Features:
    - Dynamic module import using importlib
    - Processor instance caching (one instance per sensor type)
    - Automatic discovery of new processors
    - Type validation (all processors must extend BaseSensorProcessor)
    - Library reloading for development
    - Multiple import path fallback
    """
```

**Library Discovery Process:**

```python
def _discover_libraries(self):
    """Discover and load all sensor processor libraries."""
    if not self.library_path.exists():
        logger.error(
            f"Sensor libraries path not found: {self.library_path}. "
            "No processors loaded."
        )
        return

    logger.debug(f"Discovering libraries in: {self.library_path}")

    # Scan for Python files
    for file_path in self.library_path.glob("*.py"):
        # Skip __init__.py
        if file_path.name.startswith("__"):
            continue

        module_name = file_path.stem  # e.g., "ph_sensor"

        try:
            # Import module dynamically - returns list of ALL processors
            processor_instances = self._load_library(module_name)

            for processor_instance in processor_instances:
                sensor_type = processor_instance.get_sensor_type()
                self.processors[sensor_type] = processor_instance
                logger.debug(
                    f"Loaded processor: {sensor_type} "
                    f"({processor_instance.__class__.__name__})"
                )

        except Exception as e:
            logger.error(
                f"Failed to load library '{module_name}': {e}",
                exc_info=True,
            )
```

**Zusätzliche Features:**

```python
def reload_libraries(self):
    """
    Reload all sensor libraries.
    Useful for development/hot-reload scenarios.
    """
    logger.info("Reloading sensor libraries...")
    self.processors.clear()
    self._discover_libraries()
    logger.info(
        f"Libraries reloaded. {len(self.processors)} processors available."
    )

def get_available_sensors(self) -> list[str]:
    """
    Get list of available sensor types.
    Returns: ["ph", "temperature", "humidity", "ec_sensor", ...]
    """
    return list(self.processors.keys())
```

**Library Loading mit Fallback-Imports und Multi-Processor Support:**

```python
def _load_library(self, module_name: str) -> list[BaseSensorProcessor]:
    """
    Load all sensor processor classes from a library module.
    Returns list of BaseSensorProcessor instances.
    """
    try:
        # Try multiple import paths for flexibility
        import_paths = [
            f"src.sensors.sensor_libraries.active.{module_name}",
            f"sensors.sensor_libraries.active.{module_name}",
            f"god_kaiser_server.src.sensors.sensor_libraries.active.{module_name}",
        ]

        module = None
        last_error = None

        for full_module_path in import_paths:
            try:
                module = importlib.import_module(full_module_path)
                break  # Success - exit loop
            except ImportError as e:
                last_error = e
                continue

        if module is None:
            raise ImportError(f"Could not import {module_name} from any path. Last error: {last_error}")

        # Find all classes in module that extend BaseSensorProcessor
        processor_classes = []
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseSensorProcessor)
                and obj is not BaseSensorProcessor
                and obj.__module__ == module.__name__
            ):
                processor_classes.append(obj)

        # Instantiate ALL processor classes from this module
        processor_instances = []
        for processor_class in processor_classes:
            processor_instance = processor_class()
            processor_instances.append(processor_instance)

        return processor_instances

    except Exception as e:
        logger.error(f"Failed to load processors from '{module_name}': {e}", exc_info=True)
        return []
```

### 1.2 Sensor Type Registry & Normalization

Sensor-Typen werden zwischen ESP32-Format und Server-Processor-Format normalisiert. Multi-Value-Sensoren (z.B. SHT31) werden unterstützt.

**Code-Location:** `src/sensors/sensor_type_registry.py` (1-285)

**Sensor Type Mapping (ESP32 → Server):**

```python
SENSOR_TYPE_MAPPING: Dict[str, str] = {
    # SHT31 variants
    "temperature_sht31": "sht31_temp",
    "humidity_sht31": "sht31_humidity",
    "sht31_temp": "sht31_temp",
    "sht31_humidity": "sht31_humidity",

    # DS18B20 variants
    "temperature_ds18b20": "ds18b20",
    "ds18b20": "ds18b20",

    # BMP280 variants (Phase 2)
    "pressure_bmp280": "bmp280_pressure",
    "temperature_bmp280": "bmp280_temp",
    "bmp280_pressure": "bmp280_pressure",
    "bmp280_temp": "bmp280_temp",

    # pH sensor
    "ph_sensor": "ph",
    "ph": "ph",

    # EC sensor (Phase 2)
    "ec_sensor": "ec",
    "ec": "ec",

    # Moisture sensor (Phase 2)
    "moisture": "moisture",

    # CO2 sensors (Phase 3)
    "mhz19_co2": "mhz19_co2",
    "scd30_co2": "scd30_co2",

    # Light sensor (Phase 3)
    "light": "light",
    "tsl2561": "light",
    "bh1750": "light",

    # Flow sensor (Phase 3)
    "flow": "flow",
    "yfs201": "flow",
}
```

**Multi-Value Sensor Definitions:**

```python
MULTI_VALUE_SENSORS: Dict[str, MultiValueSensorDefinition] = {
    "sht31": {
        "device_type": "i2c",
        "device_address": 0x44,  # Default SHT31 address (0x45 if ADR pin to VIN)
        "values": [
            {
                "sensor_type": "sht31_temp",
                "name": "Temperature",
                "unit": "°C",
            },
            {
                "sensor_type": "sht31_humidity",
                "name": "Humidity",
                "unit": "%RH",
            },
        ],
        "i2c_pins": {"sda": 21, "scl": 22},  # ESP32 default I2C pins
    },
    "bmp280": {
        "device_type": "i2c",
        "device_address": 0x76,  # Default BMP280 address (0x77 if SDO to VCC)
        "values": [
            {
                "sensor_type": "bmp280_pressure",
                "name": "Pressure",
                "unit": "hPa",
            },
            {
                "sensor_type": "bmp280_temp",
                "name": "Temperature",
                "unit": "°C",
            },
        ],
        "i2c_pins": {"sda": 21, "scl": 22},  # ESP32 default I2C pins
    },
    # Future multi-value sensors: "scd30": {...},  # CO2 + Temp + Humidity
}
```

**Zusätzliche Hilfsfunktionen:**

```python
def normalize_sensor_type(sensor_type: str) -> str:
    """Normalize sensor type from ESP32 format to server processor format."""

def get_multi_value_sensor_def(device_type: str) -> Optional[MultiValueSensorDefinition]:
    """Get multi-value sensor definition by device type."""

def is_multi_value_sensor(device_type: str) -> bool:
    """Check if a device type is a multi-value sensor."""

def get_device_type_from_sensor_type(sensor_type: str) -> Optional[str]:
    """Extract device type from sensor type."""

def get_all_value_types_for_device(device_type: str) -> List[str]:
    """Get all sensor types for a multi-value sensor device."""

def get_i2c_address(device_type: str, default_address: Optional[int] = None) -> Optional[int]:
    """Get I2C address for a device type."""
```

### 1.3 BaseSensorProcessor ABC

Alle Sensor-Libraries müssen diese abstrakte Basisklasse implementieren.

**Code-Location:** `src/sensors/base_processor.py` (1-214)

```python
class BaseSensorProcessor(ABC):
    """
    Abstract Base Class for all sensor processors.

    Subclasses must implement:
    - process(): Convert raw value to physical measurement
    - validate(): Check if raw value is within acceptable range
    - get_sensor_type(): Return sensor type identifier

    Optionally override:
    - calibrate(): Perform calibration (if sensor supports it)
    - get_default_params(): Return default processing parameters
    - get_value_range(): Return expected value range
    - get_raw_value_range(): Return expected raw value range
    """

    @abstractmethod
    def process(
        self,
        raw_value: float,
        calibration: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> ProcessingResult:
        pass

    @abstractmethod
    def validate(self, raw_value: float) -> ValidationResult:
        pass

    @abstractmethod
    def get_sensor_type(self) -> str:
        pass

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        Perform sensor calibration (optional).
        Override this method if sensor supports calibration.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support calibration"
        )

    def get_default_params(self) -> Dict[str, Any]:
        """Get default processing parameters."""
        return {}

    def get_value_range(self) -> Dict[str, float]:
        """Get expected value range for the sensor."""
        return {"min": float("-inf"), "max": float("inf")}

    def get_raw_value_range(self) -> Dict[str, float]:
        """Get expected raw value range (ADC/digital)."""
        return {"min": float("-inf"), "max": float("inf")}
```

**ProcessingResult & ValidationResult:**

```python
@dataclass
class ProcessingResult:
    value: float
    unit: str
    quality: str  # "excellent", "good", "fair", "poor", "bad", "error"
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ValidationResult:
    valid: bool
    error: Optional[str] = None
    warnings: Optional[list[str]] = None
```

---

## Teil 2: Pi-Enhanced Processing Flow

### 2.1 Trigger-Bedingungen

Pi-Enhanced Processing wird nur ausgelöst wenn:
1. **Sensor-Config existiert:** `sensor_config.pi_enhanced == True`
2. **ESP sendet raw_mode:** `payload["raw_mode"] == True`
3. **Library verfügbar:** Processor für `sensor_type` gefunden

**Code-Location:** `src/mqtt/handlers/sensor_handler.py:489-606`

```python
if sensor_config and sensor_config.pi_enhanced and raw_mode:
    # Pi-Enhanced processing needed
    processing_mode = "pi_enhanced"

    # Trigger Pi-Enhanced processing
    pi_result = await self._trigger_pi_enhanced_processing(
        esp_id_str,
        gpio,
        sensor_type,
        raw_value,
        sensor_config,
    )
```

### 2.2 Processing Execution

**Vollständiger Processing-Flow:**

```python
async def _trigger_pi_enhanced_processing(
    self,
    esp_id: str,
    gpio: int,
    sensor_type: str,
    raw_value: float,
    sensor_config,
) -> Optional[dict]:
    try:
        from ...sensors.library_loader import get_library_loader
        from ...sensors.sensor_type_registry import normalize_sensor_type

        # Get library loader instance
        loader = get_library_loader()

        # Normalize sensor type (ESP32 → Server Processor)
        normalized_type = normalize_sensor_type(sensor_type)

        # Get processor for sensor type
        processor = loader.get_processor(sensor_type)

        if not processor:
            logger.error(f"No processor found for sensor type: {sensor_type}")
            return None

        # Process raw value using sensor library
        processing_params = None
        if sensor_config and sensor_config.sensor_metadata:
            processing_params = sensor_config.sensor_metadata.get("processing_params")

        result = processor.process(
            raw_value=raw_value,
            calibration=sensor_config.calibration_data if sensor_config else None,
            params=processing_params,
        )

        return {
            "processed_value": result.value,
            "unit": result.unit,
            "quality": result.quality,
        }

    except Exception as e:
        logger.error(f"Pi-Enhanced processing failed: {e}")
        return None
```

### 2.3 Pi-Enhanced Response Publishing

Nach erfolgreichem Processing wird das Ergebnis zurück an den ESP32 gesendet.

**Code-Location:** `src/mqtt/publisher.py:253-287`

```python
def publish_pi_enhanced_response(
    self,
    esp_id: str,
    gpio: int,
    processed_value: float,
    unit: str,
    quality: str,
    retry: bool = False,
) -> bool:
    """
    Publish Pi-Enhanced processing result to ESP.

    Args:
        esp_id: ESP device ID
        gpio: GPIO pin number
        processed_value: Processed sensor value
        unit: Measurement unit
        quality: Data quality (excellent, good, fair, poor, bad)
        retry: Enable retry on failure

    Returns:
        True if publish successful
    """
    topic = TopicBuilder.build_pi_enhanced_response_topic(esp_id, gpio)
    payload = {
        "processed_value": processed_value,
        "unit": unit,
        "quality": quality,
        "timestamp": int(time.time()),
    }

    qos = constants.QOS_SENSOR_DATA  # QoS 1 (At least once)

    logger.debug(f"Publishing Pi-Enhanced response to {esp_id} GPIO {gpio}: {processed_value} {unit}")
    return self._publish_with_retry(topic, payload, qos, retry)
```

**Topic Structure:**
- **Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/processed`
- **QoS:** 1 (At least once)
- **Code-Location:** `src/mqtt/topics.py:116-128`

---

## Teil 3: Beispiel-Implementation (pH Sensor)

### 3.1 Library Structure

**File:** `src/sensors/sensor_libraries/active/ph_sensor.py` (1-317)

```python
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

    # ESP32 ADC configuration
    ADC_MAX = 4095  # 12-bit ADC
    ADC_VOLTAGE_RANGE = 3.3  # Volts

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
        # Step 1: Validate raw value
        validation = self.validate(raw_value)
        if not validation.valid:
            return ProcessingResult(
                value=0.0,
                unit="pH",
                quality="error",
                metadata={"error": validation.error},
            )

        # Step 2: Convert ADC to voltage
        voltage = self._adc_to_voltage(raw_value)

        # Step 3: Apply calibration if available
        if calibration and "slope" in calibration and "offset" in calibration:
            slope = calibration["slope"]
            offset = calibration["offset"]
            ph_value = self._voltage_to_ph_calibrated(voltage, slope, offset)
            calibrated = True
        else:
            # No calibration - use default conversion
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
        return ProcessingResult(
            value=ph_value,
            unit="pH",
            quality=quality,
            metadata={
                "voltage": voltage,
                "calibrated": calibrated,
                "raw_value": raw_value,
            },
        )

    def validate(self, raw_value: float) -> ValidationResult:
        """Validate raw ADC value."""
        if raw_value < 0 or raw_value > self.ADC_MAX:
            return ValidationResult(
                valid=False,
                error=f"Raw value {raw_value} out of range (0-{self.ADC_MAX})",
            )

        # Warning if value is near extremes
        warnings = []
        if raw_value < 100:
            warnings.append("Value very low - pH sensor might be disconnected")
        elif raw_value > 4000:
            warnings.append("Value very high - check sensor connection")

        return ValidationResult(valid=True, warnings=warnings if warnings else None)

    def calibrate(
        self,
        calibration_points: list[Dict[str, float]],
        method: str = "linear",
    ) -> Dict[str, Any]:
        """Perform two-point pH calibration."""
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

        # Convert ADC to voltage
        voltage1 = self._adc_to_voltage(raw1)
        voltage2 = self._adc_to_voltage(raw2)

        # Calculate slope and offset: pH = slope * voltage + offset
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
    def _adc_to_voltage(self, adc_value: float) -> float:
        """Convert ADC value to voltage."""
        return (adc_value / self.ADC_MAX) * self.ADC_VOLTAGE_RANGE

    def _voltage_to_ph_calibrated(self, voltage: float, slope: float, offset: float) -> float:
        """Convert voltage to pH using calibration."""
        ph = slope * voltage + offset
        # Clamp to valid pH range
        ph = max(self.PH_MIN, min(self.PH_MAX, ph))
        return ph

    def _voltage_to_ph_default(self, voltage: float) -> float:
        """Convert voltage to pH using default conversion."""
        # Default calibration: pH 7.0 at 1.5V, slope -3.5
        NEUTRAL_VOLTAGE = 1.5
        DEFAULT_SLOPE = -3.5

        ph = 7.0 + DEFAULT_SLOPE * (voltage - NEUTRAL_VOLTAGE)
        # Clamp to valid pH range
        ph = max(self.PH_MIN, min(self.PH_MAX, ph))
        return ph

    def _apply_temperature_compensation(self, ph: float, temperature: float) -> float:
        """Apply temperature compensation to pH reading."""
        REFERENCE_TEMP = 25.0  # °C
        TEMP_COEFFICIENT = 0.003  # pH/°C

        temp_difference = temperature - REFERENCE_TEMP
        compensation = temp_difference * TEMP_COEFFICIENT * (7.0 - ph)

        ph_compensated = ph + compensation
        # Clamp to valid range
        ph_compensated = max(self.PH_MIN, min(self.PH_MAX, ph_compensated))

        return ph_compensated

    def _assess_quality(self, ph_value: float, calibrated: bool) -> str:
        """Assess data quality."""
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
```

### 3.2 Calibration & Temperature Compensation

**Zwei-Punkt-Kalibrierung:**
```python
def calibrate(self, calibration_points: list[Dict[str, float]], method: str = "linear") -> Dict[str, Any]:
    """Perform two-point pH calibration using pH 4.0 and pH 7.0 buffer solutions."""
    # Requires calibration_points: [{"raw": 2150, "reference": 7.0}, {"raw": 1800, "reference": 4.0}]
    # Returns: {"slope": float, "offset": float, "method": "linear", "points": 2}
```

**Temperaturkompensation:**
```python
def _apply_temperature_compensation(self, ph: float, temperature: float) -> float:
    """Apply temperature compensation (0.003 pH/°C coefficient)."""
    REFERENCE_TEMP = 25.0  # °C
    TEMP_COEFFICIENT = 0.003  # pH/°C

    temp_difference = temperature - REFERENCE_TEMP
    compensation = temp_difference * TEMP_COEFFICIENT * (7.0 - ph)

    return ph + compensation  # Clamped to valid pH range
```

### 3.3 Quality Assessment

**Verbesserte Qualitätsbewertung:**
```python
def _assess_quality(self, ph_value: float, calibrated: bool) -> str:
    """Assess data quality based on value range and calibration status."""
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
```

**Qualitätskriterien:**
- **good:** Kalibriert und pH-Wert im typischen Bereich (3.0-11.0)
- **fair:** Kalibriert (aber extremes pH) oder unkaliert (aber vernünftiges pH)
- **poor:** Nicht kalibriert und extremes pH
- **error:** pH außerhalb gültigen Bereichs (0-14)

### 3.4 Validation

**Erweiterte Validierung mit Warnungen:**
```python
def validate(self, raw_value: float) -> ValidationResult:
    """Validate raw ADC value with warnings for extreme values."""
    if raw_value < 0 or raw_value > self.ADC_MAX:
        return ValidationResult(
            valid=False,
            error=f"Raw value {raw_value} out of range (0-{self.ADC_MAX})",
        )

    # Warning if value is near extremes (might be sensor issues)
    warnings = []
    if raw_value < 100:
        warnings.append("Value very low - pH sensor might be disconnected")
    elif raw_value > 4000:
        warnings.append("Value very high - check sensor connection")

    return ValidationResult(valid=True, warnings=warnings if warnings else None)
```

---

## Teil 4: Vollständiger Message Flow

### 4.1 ESP32 → Server (Raw Data)

**ESP32 sendet:**

```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 4,
  "sensor_type": "ph",
  "raw": 2150,
  "value": 0.0,
  "unit": "",
  "quality": "stale",
  "ts": 1735818000,
  "raw_mode": true
}
```

**Server empfängt via Topic:** `kaiser/god/esp/ESP_12AB34CD/sensor/4/data`

### 4.2 Server Processing

1. **Topic Parsing:** Extrahiere `esp_id`, `gpio` → `"ESP_12AB34CD"`, `4`
2. **Payload Validation:** Prüfe Required Fields (`esp_id`, `gpio`, `sensor_type`, `raw`, `raw_mode`)
3. **ESP Lookup:** Finde ESP-Device in Datenbank
4. **Sensor Config Lookup:** Hole Sensor-Konfiguration für GPIO 4
5. **Pi-Enhanced Check:** `sensor_config.pi_enhanced == True` && `raw_mode == True`
6. **Library Processing:** `ph_processor.process(raw_value=2150, calibration=..., params=...)`
7. **Result:** `ProcessingResult(value=7.2, unit="pH", quality="excellent")`

### 4.3 Server → ESP32 (Processed Data)

**Server sendet zurück:**

```json
{
  "processed_value": 7.2,
  "unit": "pH",
  "quality": "excellent",
  "timestamp": 1735818005
}
```

**ESP32 empfängt via Topic:** `kaiser/god/esp/ESP_12AB34CD/sensor/4/processed`

### 4.4 Database Storage

```sql
-- SensorData Table
INSERT INTO sensor_data (
  esp_id, gpio, sensor_type, raw_value, processed_value,
  unit, processing_mode, quality, timestamp, metadata
) VALUES (
  1, 4, 'ph', 2150, 7.2,
  'pH', 'pi_enhanced', 'excellent', '2025-01-02 10:00:00', '{"raw_mode": true}'
);
```

### 4.5 Frontend Notification

**WebSocket Broadcast:**

```json
{
  "type": "sensor_data",
  "esp_id": "ESP_12AB34CD",
  "gpio": 4,
  "sensor_type": "ph",
  "value": 7.2,
  "unit": "pH",
  "quality": "excellent",
  "timestamp": 1735818000
}
```

---

## Teil 5: Erweiterungen & Custom Sensor Integration

### 5.1 Neue Sensor-Library hinzufügen

**Schritt 1: Library erstellen**

```python
# src/sensors/sensor_libraries/active/ec_sensor.py
from ...base_processor import BaseSensorProcessor, ProcessingResult, ValidationResult

class ECSensorProcessor(BaseSensorProcessor):
    """EC (Electrical Conductivity) Sensor Processor"""

    def get_sensor_type(self) -> str:
        return "ec"

    def process(self, raw_value: float, calibration=None, params=None) -> ProcessingResult:
        # EC conversion logic here
        ec_value = (raw_value / 4095.0) * 2000  # 0-2000 µS/cm range

        return ProcessingResult(
            value=round(ec_value, 1),
            unit="µS/cm",
            quality="good"
        )

    def validate(self, raw_value: float) -> ValidationResult:
        if 0 <= raw_value <= 4095:
            return ValidationResult(valid=True)
        return ValidationResult(valid=False, error="Value out of ADC range")

# Export instance
processor = ECSensorProcessor()
```

**Schritt 2: Sensor Type Registry erweitern**

```python
# src/sensors/sensor_type_registry.py
SENSOR_TYPE_MAPPING.update({
    "ec_sensor": "ec",
    "ec": "ec",
})
```

**Schritt 3: Server neu starten**

Libraries werden automatisch beim Server-Start geladen. Kein manueller Neustart der Handler nötig.

### 5.2 Frontend Custom Sensor Management

**Geplante API-Endpunkte (noch nicht implementiert):**

```python
# library.py API (zukünftig)
@router.get("/available")
async def get_available_libraries():
    """Listet alle verfügbaren Sensor-Libraries"""
    loader = get_library_loader()
    return {"libraries": loader.get_available_sensors()}

@router.post("/validate")
async def validate_library_code(code: str):
    """Validiert hochgeladene Library-Code"""
    # Syntax check, security validation, etc.

@router.post("/upload")
async def upload_custom_library(file: UploadFile):
    """Lädt Custom Sensor-Library hoch"""
    # Save to sensor_libraries/active/
    # Trigger reload
```

**Frontend Sensor Builder (zukünftig):**

```vue
<!-- SensorLibraryManagement.vue -->
<template>
  <div class="sensor-libraries">
    <LibraryUploader @upload="handleUpload" />
    <LibraryList :libraries="libraries" />
    <SensorTester :selectedLibrary="selected" />
  </div>
</template>
```

### 5.3 Multi-Value Sensor Support

**Für Sensoren wie SHT31 (Temp + Humidity):**

```python
# sensor_config für beide Werte
sensor_configs = [
    {
        "esp_id": esp_id,
        "gpio": 21,  # I2C SDA
        "sensor_type": "sht31_temp",
        "name": "SHT31 Temperature",
        "pi_enhanced": True,
    },
    {
        "esp_id": esp_id,
        "gpio": 21,  # Same GPIO (I2C bus)
        "sensor_type": "sht31_humidity",
        "name": "SHT31 Humidity",
        "pi_enhanced": True,
    }
]
```

### 5.4 OTA Library Deployment (zukünftig)

**Geplante ESP32-Integration:**

```cpp
// ESP32: Receive and load sensor libraries via MQTT
void onLibraryUpdate(const char* library_code) {
    // Store library code in SPIFFS
    // Dynamic load using ESP32-specific mechanisms
    // Update sensor processing
}
```

---

## Teil 6: Troubleshooting

### 6.1 Library nicht gefunden

**Symptom:** `"No processor found for sensor type"`

**Lösungen:**
1. **Library-Datei prüfen:** Existiert `sensor_libraries/active/{type}_sensor.py`?
2. **Klasse prüfen:** Erbt von `BaseSensorProcessor`?
3. **Sensor Type prüfen:** Ist `get_sensor_type()` korrekt?
4. **Registry prüfen:** Mapping in `sensor_type_registry.py`?

### 6.2 Processing fehlgeschlagen

**Symptom:** `quality: "error"` in Pi-Enhanced Response

**Debug:**
```python
# Temporäres Logging hinzufügen
logger.error(f"Processing failed for {sensor_type}: {e}", exc_info=True)
```

### 6.3 ESP32 empfängt keine Response

**Prüfen:**
1. **Topic Pattern:** ESP32 subscribed auf `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/processed`?
2. **QoS Settings:** QoS 1 für Sensor-Topics?
3. **Network:** MQTT-Verbindung stabil?

---

## Teil 7: Performance & Monitoring

### 7.1 Processing Metrics

```python
# Geplante Metrics
class SensorMetrics:
    processing_time_ms: float
    success_rate: float
    error_count: int
    library_load_time: float
```

### 7.2 Health Checks

```python
# Library Health Check
async def check_library_health():
    """Prüft alle Libraries auf korrekte Funktion"""
    loader = get_library_loader()
    for sensor_type in loader.get_available_sensors():
        processor = loader.get_processor(sensor_type)
        # Test mit bekannten Werten
        test_result = processor.process(2048)  # Mid-range test
        if test_result.quality == "error":
            logger.warning(f"Library {sensor_type} health check failed")
```

---

## Teil 8: Code-Locations Referenz

| Komponente | Pfad | Zeilen |
|------------|------|--------|
| **LibraryLoader** | `src/sensors/library_loader.py` | 1-285 |
| **BaseSensorProcessor** | `src/sensors/base_processor.py` | 1-214 |
| **SensorTypeRegistry** | `src/sensors/sensor_type_registry.py` | 1-285 |
| **SensorHandler** | `src/mqtt/handlers/sensor_handler.py` | 1-606 |
| **Publisher** | `src/mqtt/publisher.py` | 253-287 |
| **TopicBuilder** | `src/mqtt/topics.py` | 116-128 |
| **pH Sensor Library** | `src/sensors/sensor_libraries/active/ph_sensor.py` | 1-317 |

---

## Verifizierungscheckliste

### Library-System
- [x] **Dynamic Import:** `importlib` für Runtime-Loading implementiert
- [x] **Singleton Pattern:** `LibraryLoader.get_instance()` implementiert
- [x] **Auto-Discovery:** Libraries in `active/` automatisch gefunden
- [x] **Type Validation:** Alle Processors erben von `BaseSensorProcessor`
- [x] **Caching:** Processor-Instanzen werden gecached
- [x] **Multi-Processor Support:** Ein Module kann mehrere Processor-Klassen enthalten
- [x] **Library Reloading:** `reload_libraries()` für Development verfügbar
- [x] **Import Fallback:** Mehrere Import-Pfade für Flexibilität

### Sensor Processing
- [x] **Pi-Enhanced Trigger:** Nur bei `pi_enhanced=true` && `raw_mode=true`
- [x] **Calibration Support:** Zwei-Punkt-Kalibrierung implementiert
- [x] **Temperature Compensation:** Optionale Temp-Kompensation
- [x] **Quality Assessment:** Automatische Qualitätsbewertung
- [x] **Error Handling:** Graceful Fallback bei Processing-Fehlern
- [x] **Parameter Support:** Sensor-spezifische Processing-Parameter
- [x] **Metadata Integration:** Zusätzliche Processing-Informationen
- [x] **Value Range Validation:** Physikalische und Raw-Value Bereiche

### ESP32 Integration
- [x] **Response Publishing:** Processed Data zurück an ESP32
- [x] **Topic Structure:** Korrekte MQTT-Topics implementiert
- [x] **QoS Settings:** At least once (QoS 1) für Sensor-Daten
- [x] **Timestamp Handling:** Unix timestamps korrekt konvertiert
- [x] **Raw Mode Detection:** Automatische Erkennung von Raw-Data

### Erweiterbarkeit
- [x] **Abstract Base Class:** Klare Interface-Definition
- [x] **Registry System:** Flexibler Sensor-Type-Mapping
- [x] **Multi-Value Support:** SHT31, BMP280 etc. unterstützt
- [x] **Plugin Architecture:** Neue Libraries einfach hinzufügbar
- [x] **Sensor Type Normalization:** Automatische ESP32→Server Format-Konvertierung
- [x] **I2C Address Management:** Zentralisierte Adress-Verwaltung
- [x] **Device Type Registry:** Unterstützung für verschiedene Kommunikationsprotokolle

---

**Letzte Verifizierung:** Dezember 2025 (aktualisiert)
**Verifiziert gegen Code-Version:** Git master branch

**Anmerkungen:**
- **Library-System vollständig funktionsfähig:** Dynamic Loading, Auto-Discovery, Caching implementiert
- **Pi-Enhanced Processing aktiv:** Server-seitige Verarbeitung für pH, Temperatur, etc.
- **ESP32 Integration vorbereitet:** Response-Publishing implementiert, Topics definiert
- **Erweiterbarkeit gegeben:** Neue Sensoren einfach durch Library-Hinzufügung integrierbar
- **Verbesserte pH Library:** Vollständige Kalibrierung, Temperaturkompensation, Qualitätsbewertung
- **Multi-Value Sensor Support:** SHT31, BMP280 mit mehreren Messwerten unterstützt
- **Erweiterte Registry:** Zusätzliche Sensor-Typen für Phase 2/3 vorbereitet
- **Development Features:** Library-Reloading für einfachere Entwicklung

Das Library-System ist **production-ready** und ermöglicht flexible Sensor-Integration ohne Server-Neustarts.








