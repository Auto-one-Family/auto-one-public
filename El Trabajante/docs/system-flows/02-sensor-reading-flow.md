# Sensor Reading Flow

## Overview

Periodic sensor measurement, processing, and MQTT publishing cycle. This flow demonstrates El Trabajante's autonomous data acquisition pattern where sensors are read on a fixed interval and published to God-Kaiser for processing and analysis.

## Files Analyzed

- `src/main.cpp` (line 643) - Loop call to performAllMeasurements()
- `src/services/sensor/sensor_manager.cpp` (lines 360-534) - Complete measurement cycle
- `src/services/sensor/sensor_manager.h` (lines 1-168) - Sensor manager interface
- `src/models/sensor_types.h` (lines 1-47) - Sensor data structures
- `src/utils/topic_builder.cpp` (lines 53-58) - Sensor topic generation
- `src/services/communication/mqtt_client.cpp` - MQTT publishing
- `src/drivers/i2c_bus.cpp` (lines 225-282) - I2C bus manager readRaw implementation
- `src/drivers/onewire_bus.cpp` (lines 185-254) - OneWire bus manager readRawTemperature implementation
- `src/services/sensor/pi_enhanced_processor.cpp` (lines 86-202) - HTTP communication with God-Kaiser
- `src/services/sensor/pi_enhanced_processor.h` (lines 1-101) - Pi-Enhanced Processor interface
- `src/models/system_types.h` - KaiserZone structure (for zone_id)

## Prerequisites

- Sensor Manager initialized (boot sequence Phase 4)
- At least one sensor configured
- MQTT client connected
- Main loop running

## Trigger

Automatic periodic measurement triggered by timer in main loop. Default interval: 30 seconds (configurable).

**File:** `src/main.cpp` (line 643)

```cpp
void loop() {
  // ...
  sensorManager.performAllMeasurements();
  // ...
}
```

---

## Flow Steps

### STEP 1: Timer Check

**File:** `src/services/sensor/sensor_manager.cpp` (lines 360-384)

**Code:**

```cpp
void SensorManager::performAllMeasurements() {
    if (!initialized_) {
        return;
    }
    
    unsigned long now = millis();
    if (now - last_measurement_time_ < measurement_interval_) {
        return;  // Not time yet
    }
    
    // Measure all active sensors
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (!sensors_[i].active) {
            continue;
        }
        
        SensorReading reading;
        if (performMeasurement(sensors_[i].gpio, reading)) {
            // Publish via MQTT
            publishSensorReading(reading);
        }
    }
    
    last_measurement_time_ = now;
}
```

**Purpose:** Prevent excessive measurements that could:
- Flood MQTT broker with messages
- Waste CPU cycles
- Drain power on battery-powered ESPs

**Timing Logic:**
- `last_measurement_time_`: Timestamp of last measurement (milliseconds), initialized to 0 in `begin()` (line 53)
- `measurement_interval_`: Default 30000ms (30 seconds) - **Note:** Declared in header (line 146) but initialization not visible in current code. Should be initialized in private constructor to 30000.
- `now - last_measurement_time_`: Elapsed time since last measurement

**Initialization:**

**File:** `src/services/sensor/sensor_manager.cpp` (lines 22-58)

```cpp
bool SensorManager::begin() {
    // ...
    initialized_ = true;
    last_measurement_time_ = 0;  // Line 53
    // Note: measurement_interval_ should be initialized to 30000 in constructor
    // ...
}
```

**File:** `src/services/sensor/sensor_manager.h` (line 146)

```cpp
unsigned long measurement_interval_;  // 30s default
```

**Recommendation:** Ensure `measurement_interval_` is initialized to 30000 in the private constructor (not visible in current codebase).

**Behavior:**
- If interval not elapsed → Return immediately (no-op)
- If interval elapsed → Proceed with measurements for all active sensors

**Configuration:** Interval can be changed dynamically (future feature)

**Architecture Note:** This implements the **Server-Centric Autonomous Measurement Pattern** where ESP32 measures periodically autonomously (standard in Industrial IoT like AWS Greengrass, Azure IoT Edge). Rationale: Minimizes MQTT traffic, server control via `measurement_interval` config.

---

### STEP 2: Iterate Active Sensors

**File:** `src/services/sensor/sensor_manager.cpp` (lines 370-381)

**Code:**

```cpp
// Measure all active sensors
for (uint8_t i = 0; i < sensor_count_; i++) {
    if (!sensors_[i].active) {
        continue;
    }
    
    SensorReading reading;
    if (performMeasurement(sensors_[i].gpio, reading)) {
        // Publish via MQTT
        publishSensorReading(reading);
    }
}
```

**Purpose:** Process each configured sensor sequentially

**Sensor Registry:**
- `sensors_[]`: Fixed-size array (max 10 sensors, defined as `MAX_SENSORS = 10`)
- `sensor_count_`: Number of configured sensors (0-10)
- `active` flag: Skip inactive sensors immediately

**Error Handling:**
- Sensor read failure → `performMeasurement()` returns false → Skip MQTT publishing → Continue with next sensor
- MQTT publish failure → Log error → Continue with next sensor
- **Non-blocking:** One sensor failure doesn't affect others

**Timing:** Serial execution (one sensor at a time)

**Memory:** `SensorReading` struct allocated on stack per iteration (~48 bytes), automatically freed after each sensor

---

### STEP 3: Perform Measurement

**File:** `src/services/sensor/sensor_manager.cpp` (lines 280-354)

**Code:**

```cpp
bool SensorManager::performMeasurement(uint8_t gpio, SensorReading& reading_out) {
    if (!initialized_) {
        LOG_ERROR("Sensor Manager not initialized");
        return false;
    }
    
    // Find sensor config
    SensorConfig* config = findSensorConfig(gpio);
    if (!config || !config->active) {
        LOG_WARNING("Sensor Manager: Sensor on GPIO " + String(gpio) + " not found or inactive");
        return false;
    }
    
    // Read raw value based on sensor type
    uint32_t raw_value = 0;
    
    if (config->sensor_type == "ph_sensor" || config->sensor_type == "ec_sensor") {
        // Analog sensor
        raw_value = readRawAnalog(gpio);
    } else if (config->sensor_type == "temperature_ds18b20") {
        // OneWire sensor
        int16_t raw_temp = 0;
        uint8_t rom[8] = {0};  // TODO: Store ROM code in SensorConfig
        if (readRawOneWire(gpio, rom, raw_temp)) {
            raw_value = (uint32_t)raw_temp;
        } else {
            reading_out.valid = false;
            reading_out.error_message = "OneWire read failed";
            return false;
        }
    } else if (config->sensor_type == "temperature_sht31" || 
               config->sensor_type.startsWith("i2c_")) {
        // I2C sensor
        uint8_t buffer[6] = {0};
        uint8_t device_addr = 0x44;  // Default SHT31 address
        if (readRawI2C(gpio, device_addr, 0x00, buffer, 6)) {
            raw_value = (uint32_t)(buffer[0] << 8 | buffer[1]);
        } else {
            reading_out.valid = false;
            reading_out.error_message = "I2C read failed";
            return false;
        }
    } else {
        // Unknown sensor type - try analog
        raw_value = readRawAnalog(gpio);
    }
    
    // Send raw data to Pi for processing
    RawSensorData raw_data;
    raw_data.gpio = gpio;
    raw_data.sensor_type = config->sensor_type;
    raw_data.raw_value = raw_value;
    raw_data.timestamp = millis();
    raw_data.metadata = "{}";
    
    ProcessedSensorData processed;
    bool success = pi_processor_->sendRawData(raw_data, processed);
    
    // Fill reading output
    reading_out.gpio = gpio;
    reading_out.sensor_type = config->sensor_type;
    reading_out.raw_value = raw_value;
    reading_out.processed_value = processed.value;
    reading_out.unit = processed.unit;
    reading_out.quality = processed.quality;
    reading_out.timestamp = millis();
    reading_out.valid = processed.valid;
    reading_out.error_message = processed.error_message;
    
    // Update config with latest reading
    config->last_raw_value = raw_value;
    config->last_reading = millis();
    
    return success;
}
```

**⚠️ Code Issue:** The `SensorReading` struct does not include `subzone_id` field (see `src/models/sensor_types.h` lines 34-44). However, `buildMQTTPayload()` attempts to access `reading.subzone_id` (line 509). This should be `config->subzone_id` instead. 

**Current Behavior:** The code may compile if String default-constructs to empty string, resulting in empty `subzone_id` in MQTT payload. To fix, `performMeasurement()` should copy `subzone_id` from config to reading, or `buildMQTTPayload()` should access it from the sensor config directly.

**Recommended Fix:**
```cpp
// In performMeasurement(), add:
reading_out.subzone_id = config->subzone_id;
```

Or in `buildMQTTPayload()`, get config and use:
```cpp
const SensorConfig* config = findSensorConfig(reading.gpio);
payload += config ? config->subzone_id : "";
```
```

**Sensor Type Routing:**

| Sensor Type | Read Method | Interface |
|-------------|-------------|-----------|
| `ph_sensor` | `readRawAnalog()` | ADC (12-bit, 0-4095) |
| `ec_sensor` | `readRawAnalog()` | ADC |
| `temperature_ds18b20` | `readRawOneWire()` | OneWire |
| `temperature_sht31` | `readRawI2C()` | I2C (0x44) |
| `i2c_*` (generic) | `readRawI2C()` | I2C |
| Unknown | `readRawAnalog()` | ADC (fallback) |

**Pi-Enhanced Processing:**

El Trabajante uses a **Server-Centric** architecture where raw sensor data is sent to God-Kaiser (Pi-Enhanced Processor) for calibration and processing:

**File:** `src/services/sensor/pi_enhanced_processor.cpp` (lines 86-164)

1. ESP reads **raw value** (ADC, I2C bytes, OneWire temp)
2. ESP builds `RawSensorData` structure:
   - `gpio`: GPIO pin number
   - `sensor_type`: Sensor type string (e.g., "ph_sensor", "temperature_ds18b20")
   - `raw_value`: Raw ADC/I2C/OneWire value
   - `timestamp`: millis() timestamp
   - `metadata`: JSON string (currently "{}")
3. ESP calls `pi_processor_->sendRawData(raw_data, processed)`
4. PiEnhancedProcessor sends HTTP POST request to God-Kaiser:
   - URL: `http://{pi_server_address}:{pi_server_port}/api/v1/sensors/process`
   - Payload: JSON with esp_id, gpio, sensor_type, raw_value, timestamp, metadata
   - Timeout: 5000ms
5. God-Kaiser processes raw data:
   - Applies calibration curves
   - Performs filtering/algorithms
   - Converts units
   - Assesses quality
6. PiEnhancedProcessor receives `ProcessedSensorData`:
   - `value`: Processed float value
   - `unit`: Unit string (e.g., "pH", "°C", "ppm")
   - `quality`: Quality assessment ("excellent", "good", "fair", "poor", "bad", "stale")
   - `valid`: Success flag
   - `error_message`: Error description if failed
7. ESP fills `SensorReading` with processed data

**Benefits:**
- Calibration updates without reflashing ESP
- Complex algorithms on powerful Pi (Python libraries)
- Consistent processing across all ESPs
- Centralized quality assessment
- Circuit breaker pattern for resilience (Phase 6+)

**Error Handling:**
- Circuit breaker blocks requests if server is down
- HTTP failures tracked and circuit opens after threshold
- Processing failures return `valid = false` but measurement continues

---

### STEP 3a: Read Raw Analog

**File:** `src/services/sensor/sensor_manager.cpp` (lines 389-399)

**Code:**

```cpp
uint32_t SensorManager::readRawAnalog(uint8_t gpio) {
    if (!initialized_) {
        return 0;
    }
    
    // Configure pin as analog input if needed
    gpio_manager_->configurePinMode(gpio, INPUT);
    
    // Read analog value (ESP32: 0-4095)
    return analogRead(gpio);
}
```

**ESP32 ADC Specifications:**
- **Resolution:** 12-bit (0-4095)
- **Voltage Range:** 0-3.3V (default)
- **Attenuation:** Configurable (0dB, 2.5dB, 6dB, 11dB)
- **ADC1 Channels:** GPIO 32-39 (8 channels)
- **ADC2 Channels:** GPIO 0, 2, 4, 12-15, 25-27 (10 channels)

**Note:** ADC2 cannot be used when WiFi is active (hardware limitation)

**Timing:** ~5-10µs per read

---

### STEP 3b: Read Raw I2C

**File:** `src/services/sensor/sensor_manager.cpp` (lines 413-421)

**Code:**

```cpp
bool SensorManager::readRawI2C(uint8_t gpio, uint8_t device_address, 
                                uint8_t reg, uint8_t* buffer, size_t len) {
    if (!initialized_ || !i2c_bus_) {
        return false;
    }
    
    // Use I2C bus manager
    return i2c_bus_->readRaw(device_address, reg, buffer, len);
}
```

**I2C Bus Manager Implementation:**

**File:** `src/drivers/i2c_bus.cpp` (lines 225-282)

The `I2CBusManager::readRaw()` method:
1. Validates bus initialization and parameters
2. Writes register address to device
3. Performs repeated start (doesn't release bus)
4. Reads requested number of bytes
5. Validates received byte count matches request
6. Returns false on any error (bus error, device not found, incomplete read)

**I2C Communication:**
- **Bus:** Shared I2C bus (SDA/SCL pins configured in I2CBusManager)
- **Frequency:** 100kHz (standard mode, configurable)
- **Addressing:** 7-bit addresses (0x08-0x77, validated)
- **Timing:** ~1-5ms per transaction (depends on bus speed and data length)
- **Error Tracking:** Errors logged via ErrorTracker with severity levels

**Common I2C Sensors:**

| Sensor | Address | Registers | Data Format |
|--------|---------|-----------|-------------|
| SHT31 (temp/humidity) | 0x44 | 0x00 | 6 bytes (temp MSB, temp LSB, CRC, hum MSB, hum LSB, CRC) |
| BME280 (temp/pressure) | 0x76 | 0xF7 | 8 bytes (pressure, temp, humidity) |
| Generic I2C | Configurable | Configurable | Raw bytes |

**Error Detection:** 
- I2C bus errors return false
- Errors tracked via `errorTracker.trackError()` with codes:
  - `ERROR_I2C_BUS_ERROR` (critical severity)
  - `ERROR_I2C_DEVICE_NOT_FOUND` (warning severity)
  - `ERROR_I2C_READ_FAILED` (error severity)

**Note:** In `performMeasurement()`, the GPIO parameter is passed but not used by `readRawI2C()`. The I2C bus is shared and GPIO is managed by I2CBusManager during initialization.

---

### STEP 3c: Read Raw OneWire

**File:** `src/services/sensor/sensor_manager.cpp` (lines 423-430)

**Code:**

```cpp
bool SensorManager::readRawOneWire(uint8_t gpio, const uint8_t rom[8], int16_t& raw_value) {
    if (!initialized_ || !onewire_bus_) {
        return false;
    }
    
    // Use OneWire bus manager
    return onewire_bus_->readRawTemperature(rom, raw_value);
}
```

**OneWire Bus Manager Implementation:**

**File:** `src/drivers/onewire_bus.cpp` (lines 185-254)

The `OneWireBusManager::readRawTemperature()` method:
1. Validates bus initialization
2. Resets OneWire bus (checks for device presence)
3. Selects device by ROM code
4. Starts temperature conversion (command 0x44, parasitic power)
5. Waits 750ms for 12-bit conversion to complete
6. Resets bus again and reselects device
7. Reads scratchpad (command 0xBE, 9 bytes)
8. Validates CRC8 checksum
9. Extracts raw 16-bit signed temperature value
10. Returns false on any error (reset failed, CRC error)

**OneWire Protocol:**
- **Single wire:** Data + power on one GPIO (configured in OneWireBusManager)
- **ROM Code:** 8-byte unique device identifier (required for device selection)
- **Resolution:** 12-bit fixed (0.0625°C per LSB)
- **Timing:** ~750ms for 12-bit conversion (hardcoded delay)
- **CRC:** 8-bit CRC validation on scratchpad data

**DS18B20 Specific:**
- Temperature range: -55°C to +125°C
- Raw value: 16-bit signed integer (range: -550 to +1250)
- Resolution: 0.0625°C per bit
- Example: 0x0191 (401 decimal) = 25.0625°C
- Conversion formula (done on server): `temp_celsius = raw_value * 0.0625`

**Multiple Sensors:** Each sensor on OneWire bus has unique ROM code. ROM code must be stored in SensorConfig (currently TODO in code line 302).

**Error Detection:**
- OneWire bus errors return false
- Errors tracked via `errorTracker.trackError()` with `ERROR_ONEWIRE_READ_FAILED`
- Common errors: Bus reset failed, CRC validation failed

**Note:** In `performMeasurement()`, ROM code is currently hardcoded to `{0}` (line 302), which will fail for actual devices. ROM code should be stored in `SensorConfig` structure.

---

### STEP 4: Build MQTT Payload

**File:** `src/services/sensor/sensor_manager.cpp` (lines 489-534)

**Code:**

```cpp
String SensorManager::buildMQTTPayload(const SensorReading& reading) const {
    String payload;
    payload.reserve(384);  // Increased for zone info
    
    // Get ESP ID and Zone info from ConfigManager
    ConfigManager& config = ConfigManager::getInstance();
    String esp_id = config.getESPId();
    
    // Phase 7: Get zone information from global variables (extern from main.cpp)
    extern KaiserZone g_kaiser;
    
    // Build JSON payload with zone information
    payload = "{";
    payload += "\"esp_id\":\"";
    payload += esp_id;
    payload += "\",";
    payload += "\"zone_id\":\"";
    payload += g_kaiser.zone_id;
    payload += "\",";
    payload += "\"subzone_id\":\"";
    payload += reading.subzone_id;  // ⚠️ NOTE: SensorReading struct doesn't have subzone_id field
    // Should be: config->subzone_id (from sensor config)
    payload += "\",";
    payload += "\"gpio\":";
    payload += String(reading.gpio);
    payload += ",";
    payload += "\"sensor_type\":\"";
    payload += reading.sensor_type;
    payload += "\",";
    payload += "\"raw_value\":";
    payload += String(reading.raw_value);
    payload += ",";
    payload += "\"processed_value\":";
    payload += String(reading.processed_value);
    payload += ",";
    payload += "\"unit\":\"";
    payload += reading.unit;
    payload += "\",";
    payload += "\"quality\":\"";
    payload += reading.quality;
    payload += "\",";
    payload += "\"timestamp\":";
    payload += String(reading.timestamp);
    payload += "}";
    
    return payload;
}
```

**Payload Structure:**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "subzone_id": "section_A",
  "gpio": 4,
  "sensor_type": "temp_ds18b20",
  "raw_value": 2350,
  "processed_value": 23.5,
  "unit": "°C",
  "quality": "good",
  "timestamp": 1234567890
}
```

**Field Descriptions:**

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `esp_id` | String | ConfigManager | ESP32 unique identifier |
| `zone_id` | String | Global g_kaiser | Hierarchical zone assignment |
| `subzone_id` | String | Sensor config | Sensor-specific subzone (⚠️ **Note:** Currently accessed from `reading.subzone_id` which doesn't exist in struct - should be from `config->subzone_id`) |
| `gpio` | Number | Sensor config | GPIO pin number |
| `sensor_type` | String | Sensor config | Sensor type identifier |
| `raw_value` | Number | Sensor read | Raw ADC/I2C/OneWire value |
| `processed_value` | Number | Pi processor | Calibrated value |
| `unit` | String | Pi processor | Unit of measurement |
| `quality` | String | Pi processor | Reading quality (good/fair/poor) |
| `timestamp` | Number | millis() | Milliseconds since boot |

**Memory:** ~256 bytes per payload (temporary, freed after publish)

---

### STEP 5: Publish to MQTT

**File:** `src/services/sensor/sensor_manager.cpp` (lines 469-487)

**Code:**

```cpp
void SensorManager::publishSensorReading(const SensorReading& reading) {
    if (!mqtt_client_ || !mqtt_client_->isConnected()) {
        LOG_WARNING("Sensor Manager: MQTT not connected, skipping publish");
        return;
    }
    
    // Build topic
    const char* topic = TopicBuilder::buildSensorDataTopic(reading.gpio);
    
    // Build payload
    String payload = buildMQTTPayload(reading);
    
    // Publish
    if (!mqtt_client_->publish(topic, payload, 1)) {
        LOG_ERROR("Sensor Manager: Failed to publish sensor data for GPIO " + String(reading.gpio));
        errorTracker.trackError(ERROR_MQTT_PUBLISH_FAILED, ERROR_SEVERITY_ERROR,
                               "Failed to publish sensor data");
    }
}
```

**Topic Generation:**

**File:** `src/utils/topic_builder.cpp` (lines 53-58)

```cpp
const char* TopicBuilder::buildSensorDataTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/sensor/%d/data",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}
```

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data`

**Example Topics:**
- `kaiser/god/esp/ESP_AB12CD/sensor/4/data`
- `kaiser/kaiser_001/esp/ESP_XY789/sensor/32/data`

**MQTT Parameters:**
- **QoS:** 1 (at least once delivery)
- **Retained:** false (not persistent)
- **Payload Format:** JSON UTF-8

**MQTT Publish Behavior:**
- Success → Returns true
- Failure → Returns false, logs error, continues
- Offline → Skipped with warning

**Offline Buffer:** MQTT client can buffer messages if broker temporarily unavailable (max 100 messages)

---

## Complete Flow Sequence Diagram

```
loop() calls performAllMeasurements()
  │
  ├─► Check timer (30s interval)
  │     └─► Too soon? → Return
  │
  ├─► For each active sensor:
  │     │
  │     ├─► Find sensor config
  │     │
  │     ├─► Read raw value
  │     │     ├─► Analog: readRawAnalog()
  │     │     ├─► I2C: readRawI2C()
  │     │     └─► OneWire: readRawOneWire()
  │     │
  │     ├─► Send to Pi-Enhanced Processor
  │     │     └─► Receive processed value
  │     │
  │     ├─► Build MQTT payload (JSON)
  │     │
  │     ├─► Publish to MQTT
  │     │     └─► Topic: kaiser/.../sensor/{gpio}/data
  │     │
  │     └─► Continue to next sensor
  │
  └─► Update last_measurement_time
```

---

## Timing Analysis

### Per Measurement Cycle

| Operation | Duration | Notes |
|-----------|----------|-------|
| Timer check | <1µs | Simple comparison |
| Sensor iteration | Variable | Depends on count |
| Analog read | 10µs | Fast |
| I2C read | 1-5ms | Bus speed dependent |
| OneWire read | 750ms | DS18B20 conversion |
| Pi processing | 10-50ms | Network latency |
| JSON build | <5ms | String concatenation |
| MQTT publish | 10-20ms | Network latency |

### Total Cycle Time

**Best Case (analog only):** ~50ms per sensor

**Typical Case (mixed sensors):** 100-200ms per sensor

**Worst Case (OneWire):** ~800ms per sensor

**Example:** 5 sensors (2 analog, 2 I2C, 1 OneWire):
- 2 × 50ms = 100ms
- 2 × 100ms = 200ms
- 1 × 800ms = 800ms
- **Total:** ~1100ms (~1.1 seconds)

### Measurement Interval

**Default:** 30 seconds

**Configurable Range:** 1 second to 1 hour

**Considerations:**
- Faster → More data, more MQTT traffic, more power
- Slower → Less responsive, less data resolution
- **Recommendation:** 10-60 seconds for most applications

---

## Error Handling

### Sensor Read Failure

**Causes:**
- Sensor disconnected
- I2C bus error
- OneWire CRC error
- GPIO conflict

**Behavior:**
1. Log error message
2. Set `reading.valid = false`
3. Set `reading.error_message`
4. Return false from performMeasurement()
5. Skip MQTT publishing
6. **Continue with next sensor**

**Error Tracking:**

```cpp
errorTracker.trackError(ERROR_SENSOR_READ_FAILED, 
                       ERROR_SEVERITY_ERROR,
                       "Sensor read failed on GPIO X");
```

---

### MQTT Publish Failure

**Causes:**
- MQTT not connected
- Network timeout
- Broker unavailable
- Message too large

**Behavior:**
1. Log error message
2. Track error via ErrorTracker
3. **Continue with next sensor**
4. Message lost (no retry for this reading)

**Offline Buffer:** If configured, messages buffered for later delivery

---

### Pi Processor Failure

**Causes:**
- God-Kaiser server down
- Network partition
- Processing error
- Circuit breaker open (Phase 6+)

**Behavior:**

**File:** `src/services/sensor/pi_enhanced_processor.cpp` (lines 86-164)

1. Circuit breaker check: If circuit breaker is OPEN or HALF_OPEN, request is blocked
2. HTTP request failure: `sendRawData()` returns false
3. `performMeasurement()` receives `processed.valid = false`
4. Reading is still filled with:
   - `processed_value = 0.0` (from ProcessedSensorData initialization)
   - `unit = ""` (empty string)
   - `quality = ""` (empty string)
   - `valid = false`
   - `error_message` set by PiEnhancedProcessor
5. **MQTT publishing still occurs** (if `performMeasurement()` returns true despite processing failure)
6. **Continue measurement cycle** - next sensor is processed

**Circuit Breaker Pattern (Phase 6+):**
- Circuit breaker tracks consecutive failures
- After threshold failures, circuit opens (blocks requests for 60 seconds)
- Prevents flooding server during outages
- Automatically transitions to HALF_OPEN for retry

**Degraded Mode:** ESP continues operating with raw data. MQTT payload includes `raw_value` even if processing failed, allowing God-Kaiser to process offline if needed.

---

## Memory Usage

### Stack Memory

| Allocation | Size | Scope |
|------------|------|-------|
| SensorReading struct | ~48 bytes | Per sensor (stack) |
| JSON payload buffer | ~384 bytes | Temporary (String with reserve) |
| I2C buffer | ~6-32 bytes | Temporary (per sensor type) |
| OneWire scratchpad | ~9 bytes | Temporary (DS18B20) |
| RawSensorData struct | ~24 bytes | Temporary (HTTP request) |
| ProcessedSensorData struct | ~32 bytes | Temporary (HTTP response) |

**Total per measurement:** ~500 bytes stack

---

### Heap Memory

**Static Allocations:**
- Sensor registry: 10 × SensorConfig = ~800 bytes
- MQTT offline buffer: 100 × MQTTMessage = ~25KB

**Dynamic Allocations:**
- JSON payload: ~256-384 bytes (temporary, freed immediately after publish)
- HTTP request payload: ~128-256 bytes (temporary, freed after HTTP call)
- HTTP response buffer: Variable (managed by HTTPClient)

**Total:** ~26KB baseline + temporary allocations (freed immediately)

**Memory Management:**
- All String objects use `reserve()` to prevent reallocation
- Temporary objects are stack-allocated and automatically freed
- No malloc()/free() in hot path
- HTTPClient manages its own buffers (not counted in SensorManager)

---

### Memory Leak Prevention

- All temporary String objects freed after publish
- No dynamic allocations in hot path
- Fixed-size buffers prevent fragmentation
- Regular garbage collection by ESP32 runtime

---

## Performance Optimization

### Current Optimizations

1. **Pre-allocated buffers:** No malloc() in measurement loop
2. **String reserve():** Prevents reallocation during JSON build
3. **Early return:** Skip inactive sensors immediately
4. **Non-blocking:** Sensor failures don't block others

### Future Optimizations

1. **Batch publishing:** Collect multiple readings, publish as array
2. **Delta compression:** Only publish changed values
3. **Adaptive interval:** Faster for rapidly changing sensors
4. **Hardware averaging:** Use ESP32 ADC averaging feature

---

## MQTT Traffic Analysis

### Message Rate

**Default (30s interval, 5 sensors):**
- 5 messages / 30s = 0.167 messages/second
- ~10 messages/minute
- ~600 messages/hour
- ~14,400 messages/day

### Bandwidth

**Per Message:**
- Topic: ~60-80 bytes (depends on kaiser_id and esp_id length)
  - Pattern: `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data`
  - Example: `kaiser/god/esp/ESP_AB12CD/sensor/4/data` = 47 bytes
- Payload: ~256-384 bytes (depends on zone_id, subzone_id, sensor_name lengths)
  - Minimum: ~200 bytes (short IDs, no subzone)
  - Typical: ~300 bytes (with zone and subzone)
  - Maximum: ~400 bytes (long zone names, sensor names)
- Total: ~316-464 bytes per message

**Per Day (5 sensors, 30s interval):**
- 14,400 messages × 350 bytes (average) = 5.0 MB/day
- ~150 MB/month

**Scalable:** 100 ESPs × 5 sensors = 500 MB/month (manageable for modern MQTT brokers)

**Network Considerations:**
- MQTT QoS 1 ensures delivery but may cause duplicates
- Broker should handle ~0.17 messages/second per ESP
- 100 ESPs = ~17 messages/second (well within broker capacity)

---

## Integration with God-Kaiser

### Message Flow

```
ESP32 → MQTT Broker → God-Kaiser
```

### God-Kaiser Processing

1. **Receive** sensor data on subscribed topics
2. **Parse** JSON payload
3. **Store** in time-series database (InfluxDB/TimescaleDB)
4. **Process** for automation rules
5. **Display** in web dashboard
6. **Alert** on threshold violations

### Data Retention

- **Real-time:** Last 24 hours in memory
- **Historical:** Downsampled to 1-minute averages
- **Long-term:** Daily aggregates

---

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

**Output:** Full sensor readings with timing information

### Serial Monitor Output Example

```
[INFO] Sensor Manager: Starting measurement cycle
[DEBUG] Sensor GPIO 4: Reading analog value
[DEBUG]   Raw value: 2048
[DEBUG]   Pi processed: 2.5V
[INFO] Published sensor data: kaiser/god/esp/ESP_AB12CD/sensor/4/data
[DEBUG] Measurement cycle complete (150ms)
```

### MQTT Message Inspection

**Subscribe to all sensor topics:**

```bash
mosquitto_sub -h 192.168.0.198 -p 8883 -t "kaiser/+/esp/+/sensor/+/data" -v
```

**Output:**

```
kaiser/god/esp/ESP_AB12CD/sensor/4/data {"esp_id":"ESP_AB12CD","zone_id":"greenhouse_zone_1",...}
```

---

## Common Issues

### No Sensor Data Published

**Symptoms:** MQTT messages not arriving at broker

**Diagnosis:**
1. Check MQTT connection: `mqttClient.isConnected()`
2. Check sensor count: `sensorManager.getActiveSensorCount()`
3. Enable DEBUG logging
4. Verify measurement interval

**Solutions:**
- Configure sensors via MQTT
- Check WiFi/MQTT connection
- Reduce measurement interval for testing

---

### Incorrect Sensor Values

**Symptoms:** Values don't match expected range

**Diagnosis:**
1. Check raw_value in MQTT payload
2. Verify sensor type matches actual sensor
3. Check GPIO wiring
4. Test sensor with multimeter

**Solutions:**
- Reconfigure sensor with correct type
- Check sensor power supply
- Verify GPIO pin assignment
- Update Pi-Enhanced calibration

---

### Slow Measurement Cycle

**Symptoms:** Loop delays, watchdog resets

**Diagnosis:**
1. Check sensor count
2. Check OneWire sensor count (slow)
3. Enable timing logs

**Solutions:**
- Reduce sensor count
- Increase measurement interval
- Use faster sensors (I2C instead of OneWire)
- Parallelize sensor reads (future feature)

---

## Next Flows

After sensor reading:

→ [Actuator Command Flow](03-actuator-command-flow.md) - For automation based on sensor data  
→ [Runtime Sensor Config Flow](04-runtime-sensor-config-flow.md) - For adding/modifying sensors  
→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - For understanding message dispatch  

---

## Related Documentation

- [Boot Sequence](01-boot-sequence.md) - Sensor Manager initialization (Phase 4)
- [MQTT Message Routing](06-mqtt-message-routing-flow.md) - Message dispatch and handler coordination
- [Runtime Sensor Config Flow](04-runtime-sensor-config-flow.md) - Dynamic sensor configuration via MQTT
- `docs/API_REFERENCE.md` - SensorManager API documentation
- `docs/NVS_KEYS.md` - Sensor config persistence in NVS
- `src/models/sensor_types.h` - Sensor data structures (SensorConfig, SensorReading)
- `src/services/sensor/pi_enhanced_processor.h` - Pi-Enhanced Processor interface
- `src/drivers/i2c_bus.h` - I2C Bus Manager interface
- `src/drivers/onewire_bus.h` - OneWire Bus Manager interface

---

**End of Sensor Reading Flow Documentation**

