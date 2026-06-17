# Runtime Sensor Configuration Flow

## Overview

Dynamic sensor configuration via MQTT allows God-Kaiser to add, modify, or remove sensors without reflashing the ESP32 firmware. This enables flexible sensor deployment and runtime reconfiguration for changing greenhouse/farm layouts.

## Files Analyzed

- `src/main.cpp` (lines 349-355, 674-826) - MQTT routing, handleSensorConfig(), parseAndConfigureSensor()
- `src/services/sensor/sensor_manager.cpp` (lines 114-241) - configureSensor(), removeSensor(), findSensorConfig()
- `src/services/sensor/sensor_manager.h` (lines 1-167) - Sensor manager interface
- `src/services/config/config_manager.cpp` (lines 396-623) - saveSensorConfig(), removeSensorConfig(), validateSensorConfig()
- `src/services/config/config_manager.h` (lines 1-57) - Config manager interface
- `src/services/config/storage_manager.cpp/.h` - NVS operations abstraction
- `src/services/config/config_response.cpp` (lines 1-72) - Response publishing
- `src/services/config/config_response.h` (lines 1-31) - Response builder interface
- `src/utils/json_helpers.h` (lines 9-82) - JSON field extraction helpers
- `src/utils/topic_builder.cpp` (lines 124-138) - Topic generation
- `src/models/sensor_types.h` (lines 1-86) - SensorConfig and SensorReading structures (incl. UART fields)
- `src/models/sensor_registry.cpp` - SensorCapability registry (`is_uart`, `co2`, `mhz19_co2`)
- `src/drivers/mhz19_uart.cpp/.h` - MH-Z19/SEN0220 UART driver (`Serial2`, RAW PPM)
- `src/models/config_types.h` (lines 1-74) - ConfigResponsePayload, ConfigType, ConfigStatus
- `src/models/error_codes.h` (lines 130-191) - ConfigErrorCode enum and string conversion

## Prerequisites

- MQTT client connected
- Sensor Manager initialized
- Config Manager operational
- NVS accessible

## Trigger

MQTT message received on configuration topic: `kaiser/{kaiser_id}/esp/{esp_id}/config`

---

## MQTT Topics

**Input Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config`

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config_response`

---

## Configuration Payload Format

```json
{
  "sensors": [
    {
      "gpio": 4,
      "sensor_type": "temp_ds18b20",
      "sensor_name": "Greenhouse Temperature",
      "subzone_id": "section_A",
      "active": true,
      "raw_mode": true
    },
    {
      "gpio": 34,
      "sensor_type": "ph_sensor",
      "sensor_name": "Water pH",
      "subzone_id": "irrigation",
      "active": true,
      "raw_mode": true
    },
    {
      "gpio": 18,
      "sensor_type": "co2",
      "sensor_name": "Greenhouse CO2",
      "subzone_id": "section_A",
      "active": true,
      "raw_mode": true,
      "interface_type": "UART",
      "uart_rx_pin": 18,
      "uart_tx_pin": 17,
      "uart_baud": 9600
    }
  ],
  "actuators": []
}
```

**Note:** Same topic handles both sensors and actuators. This flow focuses on sensors only.

---

## Flow Steps

### STEP 1: MQTT Callback Routing

**File:** `src/main.cpp` (lines 349-355)

**Code:**

```cpp
// Handle sensor configuration
String config_topic = String(TopicBuilder::buildConfigTopic());
if (topic == config_topic) {
  handleSensorConfig(payload);
  handleActuatorConfig(payload);
  return;
}
```

**Routing:** Both handlers called - each processes relevant array

---

### STEP 2: Parse Configuration JSON

**File:** `src/main.cpp` (lines 674-715)

**Code:**

```cpp
void handleSensorConfig(const String& payload) {
  LOG_INFO("Handling sensor configuration from MQTT");

  DynamicJsonDocument doc(4096);
  DeserializationError error = deserializeJson(doc, payload);
  if (error) {
    String message = "Failed to parse sensor config JSON: " + String(error.c_str());
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::JSON_PARSE_ERROR, message);
    return;
  }

  JsonArray sensors = doc["sensors"].as<JsonArray>();
  if (sensors.isNull()) {
    String message = "Sensor config missing 'sensors' array";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message);
    return;
  }

  size_t total = sensors.size();
  if (total == 0) {
    String message = "Sensor config array is empty";
    LOG_WARNING(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message);
    return;
  }

  uint8_t success_count = 0;
  for (JsonObject sensorObj : sensors) {
    if (parseAndConfigureSensor(sensorObj)) {
      success_count++;
    }
  }

  if (success_count == total) {
    String message = "Configured " + String(success_count) + " sensor(s) successfully";
    ConfigResponseBuilder::publishSuccess(ConfigType::SENSOR, success_count, message);
  }
}
```

**JSON Buffer:** 4096 bytes (supports up to ~10 sensors per message)

**Error Handling:**
- JSON parse error → Publish error response, abort
- Missing 'sensors' array → Publish error, abort
- Empty array → Warning, abort
- Individual sensor errors → Continue with next sensor

---

### STEP 3: Parse Individual Sensor

**File:** `src/main.cpp` (lines 718-825)

**Code:**

```cpp
bool parseAndConfigureSensor(const JsonObjectConst& sensor_obj) {
  SensorConfig config;
  JsonVariantConst failed_variant = sensor_obj;

  // Validate 'gpio' field (required)
  if (!sensor_obj.containsKey("gpio")) {
    String message = "Sensor config missing required field 'gpio'";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message, failed_variant);
    return false;
  }

  int gpio_value = 255;
  if (!JsonHelpers::extractInt(sensor_obj, "gpio", gpio_value)) {
    String message = "Sensor field 'gpio' must be an integer";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::TYPE_MISMATCH, message, failed_variant);
    return false;
  }
  config.gpio = static_cast<uint8_t>(gpio_value);

  // Validate 'sensor_type' field (required)
  if (!sensor_obj.containsKey("sensor_type")) {
    String message = "Sensor config missing required field 'sensor_type'";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message, failed_variant);
    return false;
  }
  if (!JsonHelpers::extractString(sensor_obj, "sensor_type", config.sensor_type)) {
    String message = "Sensor field 'sensor_type' must be a string";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::TYPE_MISMATCH, message, failed_variant);
    return false;
  }

  // Validate 'sensor_name' field (required)
  if (!sensor_obj.containsKey("sensor_name")) {
    String message = "Sensor config missing required field 'sensor_name'";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message, failed_variant);
    return false;
  }
  if (!JsonHelpers::extractString(sensor_obj, "sensor_name", config.sensor_name)) {
    String message = "Sensor field 'sensor_name' must be a string";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::TYPE_MISMATCH, message, failed_variant);
    return false;
  }

  // Optional fields
  JsonHelpers::extractString(sensor_obj, "subzone_id", config.subzone_id, "");

  bool bool_value = true;
  if (JsonHelpers::extractBool(sensor_obj, "active", bool_value, true)) {
    config.active = bool_value;
  } else {
    config.active = true;
  }

  if (JsonHelpers::extractBool(sensor_obj, "raw_mode", bool_value, true)) {
    config.raw_mode = bool_value;
  } else {
    config.raw_mode = true;
  }

  // Tombstone deletes (active=false) BEFORE validateSensorConfig() — AUT-527:
  // UART tombstones may omit uart_rx/tx; validation would reject the delete.
  if (!config.active) {
    bool removed = sensorManager.removeSensor(config.gpio, config.onewire_address,
                                             config.i2c_address);
    if (!removed && config.sensor_type == "co2") {
      if (config.gpio != 17) removed = sensorManager.removeSensor(17, "", 0);
      if (!removed && config.gpio != 18) removed = sensorManager.removeSensor(18, "", 0);
    }
    if (!removed) {
      LOG_WARNING("Sensor removal requested, but no sensor on GPIO " + String(config.gpio));
    }
    LOG_INFO("Sensor removed: GPIO " + String(config.gpio));
    return true;
  }

  // Validate config (active sensors only)
  if (!configManager.validateSensorConfig(config)) {
    String message = "Sensor validation failed for GPIO " + String(config.gpio);
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::VALIDATION_FAILED, message, failed_variant);
    return false;
  }

  // Configure sensor
  if (!sensorManager.configureSensor(config)) {
    String message = "Failed to configure sensor on GPIO " + String(config.gpio);
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::UNKNOWN_ERROR, message, failed_variant);
    return false;
  }

  // Persist to NVS
  if (!configManager.saveSensorConfig(config)) {
    String message = "Failed to save sensor config to NVS for GPIO " + String(config.gpio);
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::NVS_WRITE_FAILED, message, failed_variant);
    return false;
  }

  LOG_INFO("Sensor configured: GPIO " + String(config.gpio) + " (" + config.sensor_type + ")");
  return true;
}
```

### JSON Field Parsing

**File:** `src/utils/json_helpers.h` (lines 9-82)

The parsing uses helper functions from `JsonHelpers` namespace:

**extractInt():**
```cpp
bool extractInt(const JsonObjectConst& obj, const char* key, int& out, int default_val = 0)
```
- Checks if key exists
- Validates type (long, int, float, double)
- Returns false if key missing or wrong type
- Sets `out` to default if extraction fails

**extractString():**
```cpp
bool extractString(const JsonObjectConst& obj, const char* key, String& out, const String& default_val = "")
```
- Checks if key exists
- Validates type (const char*, String)
- Returns false if key missing or wrong type
- Sets `out` to default if extraction fails

**extractBool():**
```cpp
bool extractBool(const JsonObjectConst& obj, const char* key, bool& out, bool default_val = false)
```
- Checks if key exists
- Accepts bool, int/long (non-zero = true), or string ("true"/"1" = true)
- Returns false if key missing or wrong type
- Sets `out` to default if extraction fails

### Required Fields

| Field | Type | Validation | Error Code |
|-------|------|------------|------------|
| `gpio` | Number | 0-39, not 255, not reserved | MISSING_FIELD, TYPE_MISMATCH |
| `sensor_type` | String | Non-empty | MISSING_FIELD, TYPE_MISMATCH |
| `sensor_name` | String | Non-empty | MISSING_FIELD, TYPE_MISMATCH |

### Optional Fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `subzone_id` | String | "" | Empty string if not provided |
| `active` | Boolean | true | Used for removal if false |
| `raw_mode` | Boolean | true | Server-centric mode (always true in practice) |
| `onewire_address` | String | "" | 16 hex chars for DS18B20 (OneWire bus) |
| `i2c_address` | Number | 0 | 7-bit I2C address (e.g. 0x44 for SHT31) |
| `interface_type` | String | "" | Bus hint from server (e.g. `"UART"` for CO2) |
| `uart_rx_pin` | Number | 255 | ESP RX ← sensor TX (255 = unset) |
| `uart_tx_pin` | Number | 255 | ESP TX → sensor RX (255 = unset) |
| `uart_baud` | Number | 9600 | UART baud rate (9600–115200 for CO2) |
| `operating_mode` | String | `"continuous"` | `continuous`, `on_demand`, `paused`, `scheduled` |
| `measurement_interval_seconds` | Number | 30 | 1–300 seconds |

---

### STEP 3.1: Interface-Specific Fields (UART CO2)

**Files:** `src/main.cpp` (`parseAndConfigureSensorWithTracking`), `src/models/sensor_registry.cpp`, `src/services/config/config_manager.cpp` (`validateSensorConfig`)

**Registry types:** `co2`, `mhz19_co2` → `SensorCapability.is_uart = true`, server type `co2`.

**Parsing (optional MQTT fields):**

```cpp
JsonHelpers::extractString(sensor_obj, "interface_type", config.interface_type, "");

int uart_rx = 255;
int uart_tx = 255;
int uart_baud = 9600;
JsonHelpers::extractInt(sensor_obj, "uart_rx_pin", uart_rx, 255);
JsonHelpers::extractInt(sensor_obj, "uart_tx_pin", uart_tx, 255);
JsonHelpers::extractInt(sensor_obj, "uart_baud", uart_baud, 9600);
config.uart_rx_pin = static_cast<uint8_t>(uart_rx);
config.uart_tx_pin = static_cast<uint8_t>(uart_tx);
config.uart_baud = static_cast<uint32_t>(uart_baud);
```

**UART CO2 detection** (any of):

1. `findSensorCapability(sensor_type)->is_uart == true`
2. `interface_type` equals `"UART"` (case-insensitive)
3. Both `uart_rx_pin` and `uart_tx_pin` set (not 255, not 0)

**Validation rules (`validateSensorConfig`):**

| Rule | Failure |
|------|---------|
| `uart_rx_pin` / `uart_tx_pin` required | != 255 and != 0 |
| `uart_baud` in range | 9600–115200 |
| UART pins not board-reserved | `GPIOManager::isPinReserved()` |
| `gpio` | Logical sensor slot / MQTT topic index — **not ADC** for UART CO2 |

**Pin semantics (AUT-527 / ESP32-S3):**

| Field | Example | Role |
|-------|---------|------|
| `gpio` | 18 | Logical slot → topic `.../sensor/18/data` |
| `uart_rx_pin` | 18 | ESP RX ← MH-Z19 TX |
| `uart_tx_pin` | 17 | ESP TX → MH-Z19 RX |
| `uart_baud` | 9600 | MH-Z19 default 9600 8N1 |

**Tombstone / removal (AUT-527):** `parseAndConfigureSensorWithTracking()` prüft `active=false` **vor** `validateSensorConfig()`. CO₂-Löschung: Firmware-Fallback entfernt NVS-Slot auf GPIO **17** und/oder **18**, wenn der Tombstone-GPIO nicht matcht. Server sendet bei `DELETE` für `co2` zwei Tombstones (DB-`gpio` + UART1-Komplement) — siehe `sensors.py::_build_sensor_delete_tombstones()`.

**Reference payload:**

```json
{
  "gpio": 18,
  "sensor_type": "co2",
  "sensor_name": "Greenhouse CO2",
  "subzone_id": "section_A",
  "active": true,
  "raw_mode": true,
  "interface_type": "UART",
  "uart_rx_pin": 18,
  "uart_tx_pin": 17,
  "uart_baud": 9600
}
```

---

### STEP 4: Configure Sensor in Manager

**File:** `src/services/sensor/sensor_manager.cpp` (lines 114-197)

**Code:**

```cpp
bool SensorManager::configureSensor(const SensorConfig& config) {
    if (!initialized_) {
        LOG_ERROR("Sensor Manager not initialized");
        return false;
    }
    
    // Validate GPIO
    if (config.gpio == 255) {
        LOG_ERROR("Sensor Manager: Invalid GPIO (255)");
        errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "Invalid GPIO for sensor");
        return false;
    }
    
    // Phase 7: Check if sensor already exists (runtime reconfiguration support)
    SensorConfig* existing = findSensorConfig(config.gpio);
    if (existing) {
        // Runtime reconfiguration: Update existing sensor
        LOG_INFO("Sensor Manager: Updating existing sensor on GPIO " + String(config.gpio));
        
        // Check if sensor type changed
        bool type_changed = (existing->sensor_type != config.sensor_type);
        if (type_changed) {
            LOG_INFO("  Sensor type changed: " + existing->sensor_type + " → " + config.sensor_type);
        }
        
        // Update configuration
        *existing = config;
        existing->active = true;
        
        // Phase 7: Persist to NVS immediately
        if (!configManager.saveSensorConfig(config)) {
            LOG_ERROR("Sensor Manager: Failed to persist sensor config to NVS");
        } else {
            LOG_INFO("  ✅ Configuration persisted to NVS");
        }
        
        LOG_INFO("Sensor Manager: Updated sensor on GPIO " + String(config.gpio) + 
                 " (" + config.sensor_type + ")");
        return true;
    }
    
    // New sensor: Check if we have space
    if (sensor_count_ >= MAX_SENSORS) {
        LOG_ERROR("Sensor Manager: Maximum sensor count reached");
        errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "Maximum sensor count reached");
        return false;
    }
    
    // Check GPIO availability
    if (!gpio_manager_->isPinAvailable(config.gpio)) {
        LOG_ERROR("Sensor Manager: GPIO " + String(config.gpio) + " not available");
        errorTracker.trackError(ERROR_GPIO_CONFLICT, ERROR_SEVERITY_ERROR,
                               "GPIO conflict for sensor");
        return false;
    }
    
    // Reserve GPIO
    if (!gpio_manager_->requestPin(config.gpio, "sensor", config.sensor_name.c_str())) {
        LOG_ERROR("Sensor Manager: Failed to reserve GPIO " + String(config.gpio));
        errorTracker.trackError(ERROR_GPIO_RESERVED, ERROR_SEVERITY_ERROR,
                               "Failed to reserve GPIO");
        return false;
    }
    
    // Add sensor
    sensors_[sensor_count_] = config;
    sensors_[sensor_count_].active = true;
    sensor_count_++;
    
    // Phase 7: Persist to NVS immediately
    if (!configManager.saveSensorConfig(config)) {
        LOG_ERROR("Sensor Manager: Failed to persist sensor config to NVS");
    } else {
        LOG_INFO("  ✅ Configuration persisted to NVS");
    }
    
    LOG_INFO("Sensor Manager: Configured new sensor on GPIO " + String(config.gpio) + 
             " (" + config.sensor_type + ")");
    
    return true;
}
```

**Operations:**
1. Check for existing sensor (reconfiguration)
2. Check sensor array capacity (max 10)
3. Validate GPIO availability
4. Reserve GPIO pin
5. Add to sensor registry
6. Persist to NVS

**UART CO2 branch** (`sensor_manager.cpp`, when `is_uart` / `interface_type=UART`):

1. Validate `uart_rx_pin` + `uart_tx_pin` (`hasValidUartPinConfig` — pins != 255 and != 0)
2. Reserve **both** UART pins via `GPIOManager::requestPin()` (plus logical `gpio` if distinct)
3. Initialize `Mhz19UartReader` → `Serial2.begin(baud, SERIAL_8N1, rx, tx)`
4. Store config; set `uart_configured_at_ms = millis()` (warmup gate, not NVS)
5. Persist to NVS (incl. `sen_%d_if`, `sen_%d_urx`, `sen_%d_utx`, `sen_%d_ubd`)

**UART CO2 removal:** `removeSensor()` releases RX/TX pins, calls `mhz19UartReader.end()`.

**UART CO2 measurement** (after config — see [Sensor Reading Flow](02-sensor-reading-flow.md)):

- Warmup: 180s after configure → `valid=false`, `quality=warming_up`
- After warmup: `readRawPpm()` → `raw_value` = PPM, `raw_mode=true`
- **No** `readRawAnalog()` — avoids ADC2+WiFi false zero on wrong GPIO

**Error codes:** `ERROR_UART_INIT_FAILED` (1033), `ERROR_UART_READ_TIMEOUT` (1034), `ERROR_UART_CHECKSUM_FAILED` (1035), `ERROR_UART_INVALID_PPM` (1036)

---

### STEP 5: Validate Sensor Configuration

**File:** `src/services/config/config_manager.cpp` (lines 603-623)

**Code:**

```cpp
bool ConfigManager::validateSensorConfig(const SensorConfig& config) const {
  // GPIO must be valid (not 255)
  if (config.gpio == 255) {
    LOG_WARNING("ConfigManager: Invalid GPIO (255)");
    return false;
  }
  
  // Sensor type must not be empty
  if (config.sensor_type.length() == 0) {
    LOG_WARNING("ConfigManager: Sensor type is empty");
    return false;
  }
  
  // GPIO must be in valid range (0-39 for ESP32)
  if (config.gpio > 39) {
    LOG_WARNING("ConfigManager: GPIO out of range: " + String(config.gpio));
    return false;
  }
  
  return true;
}
```

**Validation Rules:**
1. GPIO must not be 255 (invalid marker)
2. GPIO must be 0-39 (ESP32 valid range)
3. Sensor type must not be empty
4. **UART CO2:** `uart_rx_pin` / `uart_tx_pin` required (not 255, not 0); `uart_baud` 9600–115200; UART pins not reserved
5. **I2C:** GPIO validation skipped (shared bus); see `sensor_manager.cpp` I2C branch

---

### STEP 6: Persist to NVS

**File:** `src/services/config/config_manager.cpp` (lines 396-453)

**Code:**

```cpp
bool ConfigManager::saveSensorConfig(const SensorConfig& config) {
  if (!validateSensorConfig(config)) {
    LOG_ERROR("ConfigManager: Sensor config validation failed");
    return false;
  }
  
  if (!storageManager.beginNamespace("sensor_config", false)) {
    LOG_ERROR("ConfigManager: Failed to open sensor_config namespace");
    return false;
  }
  
  // Find index for this GPIO (or use next available)
  uint8_t sensor_count = storageManager.getUInt8("sensor_count", 0);
  int8_t existing_index = -1;
  
  // Check if sensor already exists
  char key_buffer[64];
  for (uint8_t i = 0; i < sensor_count; i++) {
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "gpio");
    uint8_t stored_gpio = storageManager.getUInt8(key_buffer, 255);
    if (stored_gpio == config.gpio) {
      existing_index = i;
      break;
    }
  }
  
  uint8_t index = (existing_index >= 0) ? existing_index : sensor_count;
  
  // Save sensor fields
  bool success = true;
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "gpio");
  success &= storageManager.putUInt8(key_buffer, config.gpio);
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "type");
  success &= storageManager.putString(key_buffer, config.sensor_type);
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "name");
  success &= storageManager.putString(key_buffer, config.sensor_name);
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "subzone");
  success &= storageManager.putString(key_buffer, config.subzone_id);
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "active");
  success &= storageManager.putBool(key_buffer, config.active);
  buildSensorKey(key_buffer, sizeof(key_buffer), index, "raw_mode");
  success &= storageManager.putBool(key_buffer, config.raw_mode);
  
  // Update count if new sensor
  if (existing_index < 0) {
    success &= storageManager.putUInt8("sensor_count", sensor_count + 1);
  }
  
  storageManager.endNamespace();
  
  if (success) {
    LOG_INFO("ConfigManager: Saved sensor config for GPIO " + String(config.gpio));
  } else {
    LOG_ERROR("ConfigManager: Failed to save sensor config");
  }
  
  return success;
}
```

**Key Building Helper:**

```cpp
static void buildSensorKey(char* buffer, size_t buffer_size, uint8_t index, const char* field) {
  snprintf(buffer, buffer_size, "sensor_%d_%s", index, field);
}
```

**Operations:**
1. Validate configuration
2. Open NVS namespace `sensor_config`
3. Find existing sensor by GPIO (for updates)
4. Save all sensor fields using indexed keys
5. Update sensor count if new sensor
6. Close namespace

### NVS Keys

**Namespace:** `sensor_config`

**Keys:**
- `sensor_count` (uint8_t) - Total sensor count
- `sensor_{i}_gpio` (uint8_t) - GPIO pin
- `sensor_{i}_type` (String) - Sensor type
- `sensor_{i}_name` (String) - Sensor name
- `sensor_{i}_subzone` (String) - Subzone ID
- `sensor_{i}_active` (bool) - Active flag
- `sensor_{i}_raw_mode` (bool) - Raw mode flag

**UART CO2 keys (implementation in `config_manager.cpp`, prefix `sen_%d_*`):**

- `sen_%d_if` (String) - Interface type (e.g. `"UART"`)
- `sen_%d_urx` (uint8_t) - UART RX pin
- `sen_%d_utx` (uint8_t) - UART TX pin
- `sen_%d_ubd` (uint32_t) - UART baud rate

See `docs/NVS_KEYS.md` for full sensor NVS schema.

**Example NVS Layout:**

```
Namespace: sensor_config
  sensor_count = 2
  sensor_0_gpio = 4
  sensor_0_type = "temp_ds18b20"
  sensor_0_name = "Greenhouse Temperature"
  sensor_0_subzone = "section_A"
  sensor_0_active = true
  sensor_0_raw_mode = true
  sensor_1_gpio = 34
  sensor_1_type = "ph_sensor"
  sensor_1_name = "Water pH"
  sensor_1_subzone = "irrigation"
  sensor_1_active = true
  sensor_1_raw_mode = true
  sen_2_gpio = 18
  sen_2_type = "co2"
  sen_2_if = "UART"
  sen_2_urx = 18
  sen_2_utx = 17
  sen_2_ubd = 9600
```

---

### STEP 7: Remove Sensor from Manager

**File:** `src/services/sensor/sensor_manager.cpp` (lines 200-241)

**Code:**

```cpp
bool SensorManager::removeSensor(uint8_t gpio) {
    if (!initialized_) {
        LOG_ERROR("Sensor Manager not initialized");
        return false;
    }
    
    SensorConfig* config = findSensorConfig(gpio);
    if (!config) {
        LOG_WARNING("Sensor Manager: Sensor on GPIO " + String(gpio) + " not found");
        return false;
    }
    
    LOG_INFO("Sensor Manager: Removing sensor on GPIO " + String(gpio));
    
    // Release GPIO
    gpio_manager_->releasePin(gpio);
    LOG_INFO("  ✅ GPIO " + String(gpio) + " released");
    
    // Remove sensor (shift array)
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].gpio == gpio) {
            // Shift remaining sensors
            for (uint8_t j = i; j < sensor_count_ - 1; j++) {
                sensors_[j] = sensors_[j + 1];
            }
            sensor_count_--;
            sensors_[sensor_count_].gpio = 255;
            sensors_[sensor_count_].active = false;
            break;
        }
    }
    
    // Phase 7: Persist removal to NVS immediately
    if (!configManager.removeSensorConfig(gpio)) {
        LOG_ERROR("Sensor Manager: Failed to remove sensor config from NVS");
    } else {
        LOG_INFO("  ✅ Configuration removed from NVS");
    }
    
    LOG_INFO("Sensor Manager: Removed sensor on GPIO " + String(gpio));
    return true;
}
```

**Operations:**
1. Find sensor in registry
2. Release GPIO pin via GPIOManager
3. Shift array (remove gap)
4. Decrement sensor count
5. Clear last array element
6. Remove from NVS

---

### STEP 8: Remove Sensor from NVS

**File:** `src/services/config/config_manager.cpp` (lines 524-601)

**Code:**

```cpp
bool ConfigManager::removeSensorConfig(uint8_t gpio) {
  if (!storageManager.beginNamespace("sensor_config", false)) {
    LOG_ERROR("ConfigManager: Failed to open sensor_config namespace");
    return false;
  }
  
  uint8_t sensor_count = storageManager.getUInt8("sensor_count", 0);
  int8_t found_index = -1;
  
  // Find sensor index
  char key_buffer[64];
  for (uint8_t i = 0; i < sensor_count; i++) {
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "gpio");
    uint8_t stored_gpio = storageManager.getUInt8(key_buffer, 255);
    if (stored_gpio == gpio) {
      found_index = i;
      break;
    }
  }
  
  if (found_index < 0) {
    storageManager.endNamespace();
    LOG_WARNING("ConfigManager: Sensor config for GPIO " + String(gpio) + " not found");
    return false;
  }
  
  // Remove sensor by shifting remaining sensors
  char next_key_buffer[64];
  for (uint8_t i = found_index; i < sensor_count - 1; i++) {
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "gpio");
    uint8_t next_gpio = storageManager.getUInt8(next_key_buffer, 255);
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "type");
    String next_type = storageManager.getStringObj(next_key_buffer, "");
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "name");
    String next_name = storageManager.getStringObj(next_key_buffer, "");
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "subzone");
    String next_subzone = storageManager.getStringObj(next_key_buffer, "");
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "active");
    bool next_active = storageManager.getBool(next_key_buffer, false);
    buildSensorKey(next_key_buffer, sizeof(next_key_buffer), i + 1, "raw_mode");
    bool next_raw_mode = storageManager.getBool(next_key_buffer, true);
    
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "gpio");
    storageManager.putUInt8(key_buffer, next_gpio);
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "type");
    storageManager.putString(key_buffer, next_type);
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "name");
    storageManager.putString(key_buffer, next_name);
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "subzone");
    storageManager.putString(key_buffer, next_subzone);
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "active");
    storageManager.putBool(key_buffer, next_active);
    buildSensorKey(key_buffer, sizeof(key_buffer), i, "raw_mode");
    storageManager.putBool(key_buffer, next_raw_mode);
  }
  
  // Clear last sensor
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "gpio");
  storageManager.putUInt8(key_buffer, 255);
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "type");
  storageManager.putString(key_buffer, "");
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "name");
  storageManager.putString(key_buffer, "");
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "subzone");
  storageManager.putString(key_buffer, "");
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "active");
  storageManager.putBool(key_buffer, false);
  buildSensorKey(key_buffer, sizeof(key_buffer), sensor_count - 1, "raw_mode");
  storageManager.putBool(key_buffer, true);
  
  // Update count
  storageManager.putUInt8("sensor_count", sensor_count - 1);
  
  storageManager.endNamespace();
  
  LOG_INFO("ConfigManager: Removed sensor config for GPIO " + String(gpio));
  return true;
}
```

**Operations:**
1. Open NVS namespace
2. Find sensor index by GPIO
3. Shift all sensors after found index forward
4. Clear last sensor entry (set to default values)
5. Decrement sensor count
6. Close namespace

---

### STEP 9: Publish Response

**File:** `src/services/config/config_response.cpp` (lines 1-72)

**Success Response:**

```cpp
bool ConfigResponseBuilder::publishSuccess(ConfigType type,
                                           uint8_t count,
                                           const String& message) {
  ConfigResponsePayload payload;
  payload.status = ConfigStatus::SUCCESS;
  payload.type = type;
  payload.count = count;
  payload.message = message;
  payload.error_code = "NONE";
  payload.failed_item.clear();
  return publish(payload);
}
```

**Error Response:**

```cpp
bool ConfigResponseBuilder::publishError(ConfigType type,
                                        ConfigErrorCode error_code,
                                        const String& message,
                                        JsonVariantConst failed_item) {
  ConfigResponsePayload payload;
  payload.status = ConfigStatus::ERROR;
  payload.type = type;
  payload.count = 0;
  payload.message = message;
  payload.error_code = String(configErrorCodeToString(error_code));
  payload.failed_item.clear();

  if (!failed_item.isNull()) {
    payload.failed_item.set(failed_item);
  }

  return publish(payload);
}
```

**Payload Building:**

```cpp
String ConfigResponseBuilder::buildJsonPayload(const ConfigResponsePayload& payload) {
  DynamicJsonDocument doc(512);
  doc["status"] = configStatusToString(payload.status);
  doc["type"] = configTypeToString(payload.type);
  doc["count"] = payload.count;
  if (payload.message.length() > 0) {
    doc["message"] = payload.message;
  } else {
    doc["message"] = payload.status == ConfigStatus::SUCCESS ? "ok" : "error";
  }

  if (payload.status == ConfigStatus::ERROR) {
    const String code = payload.error_code.length() > 0 ? payload.error_code : "UNKNOWN_ERROR";
    doc["error_code"] = code;
    if (payload.failed_item.size() > 0 && payload.failed_item.is<JsonObject>()) {
      doc["failed_item"] = payload.failed_item.as<JsonObjectConst>();
    }
  }

  String json;
  serializeJson(doc, json);
  return json;
}
```

**Publishing:**

```cpp
bool ConfigResponseBuilder::publish(const ConfigResponsePayload& payload) {
  String json_payload = buildJsonPayload(payload);
  String topic = String(TopicBuilder::buildConfigResponseTopic());

  bool published = mqttClient.safePublish(topic, json_payload, 1);
  if (published) {
    LOG_INFO("ConfigResponse published [" + String(configTypeToString(payload.type)) +
             "] status=" + String(configStatusToString(payload.status)));
  } else {
    LOG_ERROR("ConfigResponse publish failed for topic: " + topic);
  }

  return published;
}
```

**Success Payload:**

```json
{
  "status": "success",
  "type": "sensor",
  "count": 2,
  "message": "Configured 2 sensor(s) successfully"
}
```

**Error Payload:**

```json
{
  "status": "error",
  "type": "sensor",
  "count": 0,
  "message": "Sensor config missing required field 'gpio'",
  "error_code": "MISSING_FIELD",
  "failed_item": {
    "sensor_type": "temp_ds18b20",
    "sensor_name": "Test Sensor"
  }
}
```

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config_response`

**QoS:** 1 (at least once)

### Error Codes

**File:** `src/models/error_codes.h` (lines 130-191)

| Enum Value | String Value | Description |
|------------|--------------|-------------|
| `ConfigErrorCode::NONE` | "NONE" | No error |
| `ConfigErrorCode::JSON_PARSE_ERROR` | "JSON_PARSE_ERROR" | JSON parsing failed |
| `ConfigErrorCode::MISSING_FIELD` | "MISSING_FIELD" | Required field missing |
| `ConfigErrorCode::TYPE_MISMATCH` | "TYPE_MISMATCH" | Field type incorrect |
| `ConfigErrorCode::VALIDATION_FAILED` | "VALIDATION_FAILED" | Config validation failed |
| `ConfigErrorCode::GPIO_CONFLICT` | "GPIO_CONFLICT" | GPIO already in use |
| `ConfigErrorCode::NVS_WRITE_FAILED` | "NVS_WRITE_FAILED" | NVS storage write failed |
| `ConfigErrorCode::OUT_OF_RANGE` | "OUT_OF_RANGE" | Value out of valid range |
| `ConfigErrorCode::UNKNOWN_ERROR` | "UNKNOWN_ERROR" | Unknown/unhandled error |

---

## Complete Flow Sequence

```
MQTT Config Message (kaiser/{kaiser_id}/esp/{esp_id}/config)
  │
  ├─► STEP 1: MQTT Callback Routing (main.cpp:349-355)
  │     └─► Topic match → handleSensorConfig()
  │
  ├─► STEP 2: Parse Configuration JSON (main.cpp:674-715)
  │     ├─► DynamicJsonDocument(4096 bytes)
  │     ├─► Extract "sensors" array
  │     └─► Validate array exists and not empty
  │
  ├─► STEP 3: Parse Individual Sensor (main.cpp:718-825)
  │     │
  │     ├─► Extract required fields (gpio, sensor_type, sensor_name)
  │     │     ├─► JsonHelpers::extractInt() for gpio
  │     │     ├─► JsonHelpers::extractString() for sensor_type
  │     │     └─► JsonHelpers::extractString() for sensor_name
  │     │
  │     ├─► Extract optional fields (subzone_id, active, raw_mode, onewire, i2c, uart)
  │     │     └─► JsonHelpers::extractString/Bool/Int() with defaults
  │     │
  │     ├─► STEP 3.1: UART CO2 fields (if co2/mhz19_co2 or interface_type=UART)
  │     │     └─► uart_rx_pin, uart_tx_pin, uart_baud (parsed before active check)
  │     │
  │     ├─► If active=false: (BEFORE validation — AUT-527)
  │     │     ├─► STEP 7: removeSensor() → release GPIO (+ UART rx/tx for CO2)
  │     │     │     └─► CO2 fallback: also try GPIO 17 and 18
  │     │     └─► removeSensor() → removeSensorConfig() / NVS shift
  │     │
  │     ├─► STEP 5: Validate Configuration (active=true only)
  │     │     ├─► GPIO != 255, GPIO 0-39, sensor_type not empty
  │     │     └─► UART: uart_rx_pin/uart_tx_pin required
  │     │
  │     └─► If active=true:
  │           ├─► STEP 4: Configure in SensorManager
  │           │     ├─► Check if exists (reconfiguration)
  │           │     ├─► Check MAX_SENSORS limit
  │           │     ├─► I2C branch OR UART CO2 branch OR OneWire/ADC branch
  │           │     │     └─► UART: reserve rx+tx, Mhz19UartReader.begin(), warmup timestamp
  │           │     ├─► Check GPIO availability (non-I2C)
  │           │     ├─► Reserve GPIO via GPIOManager
  │           │     └─► Add/update in sensor registry
  │           │
  │           └─► STEP 6: Persist to NVS
  │                 ├─► Find existing index or create new
  │                 ├─► Save all fields (gpio, type, name, subzone, active, raw_mode)
  │                 └─► Update sensor_count if new
  │
  └─► STEP 9: Publish Response (config_response.cpp)
        ├─► Build ConfigResponsePayload
        ├─► Serialize to JSON (512 bytes buffer)
        └─► Publish to config_response topic (QoS 1)
```

## Runtime Reconfiguration

**Phase 7 Feature:** Sensors can be reconfigured at runtime without removal.

**Behavior:**
- If sensor exists on same GPIO → Update configuration
- Sensor type can change (logged)
- All fields updated in-place
- NVS updated immediately
- GPIO remains reserved (no release/re-reserve)

**Example:**
```json
// Initial config
{"gpio": 4, "sensor_type": "ph_sensor", "sensor_name": "pH Sensor"}

// Runtime update
{"gpio": 4, "sensor_type": "ec_sensor", "sensor_name": "EC Sensor"}
// → Updates existing sensor, changes type, persists to NVS
```

---

## Timing Analysis

| Operation | Duration |
|-----------|----------|
| JSON parse | 5-20ms |
| Field validation | <1ms per field |
| GPIO reservation | <1ms |
| NVS write | 10-50ms per sensor |
| Response publish | 10-20ms |

**Total:** 50-200ms for 2-sensor config

---

## Memory Usage

| Allocation | Size |
|------------|------|
| JSON buffer | 4096 bytes (stack) |
| SensorConfig struct | ~128 bytes |
| Temp strings | ~256 bytes |

**Total:** ~4.5KB per config operation

**Stack Usage:**
- JSON parsing buffer: 4096 bytes (stack)
- ConfigResponsePayload: ~512 bytes (stack)
- Temporary strings: ~256 bytes (stack)

**Heap Usage:**
- SensorConfig structs: ~128 bytes × sensor_count (heap)
- String allocations: Variable (depends on sensor names/types)

---

## Error Handling

### JSON Parse Errors

**Causes:** 
- Malformed JSON syntax
- Buffer too small (4096 bytes exceeded)
- Invalid encoding

**Detection:** `DeserializationError` from `deserializeJson()`

**Recovery:** 
- Publish error response with `JSON_PARSE_ERROR`
- Abort entire operation (no sensors processed)

**Error Response:**
```json
{
  "status": "error",
  "type": "sensor",
  "error_code": "JSON_PARSE_ERROR",
  "message": "Failed to parse sensor config JSON: ..."
}
```

### Missing Required Fields

**Causes:** 
- `gpio`, `sensor_type`, or `sensor_name` missing from JSON

**Detection:** `!sensor_obj.containsKey()` check

**Recovery:**
- Publish error for that sensor with `MISSING_FIELD`
- Include `failed_item` in response
- Continue processing other sensors

### Type Mismatch Errors

**Causes:**
- Field present but wrong type (e.g., `gpio` as string)

**Detection:** `JsonHelpers::extractInt/String/Bool()` returns false

**Recovery:**
- Publish error with `TYPE_MISMATCH`
- Include `failed_item` in response
- Continue processing other sensors

### Validation Failures

**Causes:**
- GPIO = 255 (invalid marker)
- GPIO > 39 (out of range)
- sensor_type empty string
- **UART CO2:** missing/invalid `uart_rx_pin` or `uart_tx_pin` (255 or 0); `uart_baud` out of range; reserved UART pins

**Detection:** `ConfigManager::validateSensorConfig()` returns false

**Recovery:**
- Publish error with `VALIDATION_FAILED`
- Include `failed_item` in response
- Continue processing other sensors

### GPIO Conflicts

**Causes:** 
- GPIO already in use by another sensor/actuator
- GPIO reserved by GPIOManager

**Detection:** `GPIOManager::isPinAvailable()` returns false

**Recovery:**
- Publish error with `GPIO_CONFLICT` (if implemented)
- Track error via ErrorTracker
- Continue processing other sensors

**Note:** GPIO conflict detection happens in SensorManager, not ConfigManager

### NVS Write Failures

**Causes:** 
- NVS namespace full
- NVS corruption
- StorageManager operation failed

**Detection:** `StorageManager::put*()` returns false

**Recovery:**
- Sensor configured in RAM (SensorManager)
- **Not persisted to NVS** (lost on reboot)
- Publish error with `NVS_WRITE_FAILED`
- Log warning

**Impact:** Sensor works until reboot, then lost

### Maximum Sensor Count Reached

**Causes:**
- `sensor_count_ >= MAX_SENSORS` (10)

**Detection:** Check in `SensorManager::configureSensor()`

**Recovery:**
- Publish error with `UNKNOWN_ERROR`
- Track error via ErrorTracker
- Continue processing other sensors

### Partial Success Handling

**Behavior:**
- Success response only published if **all** sensors succeed
- Individual errors published immediately per sensor
- Processing continues for remaining sensors

**Example:**
```json
// Request: 3 sensors
// Result: 2 succeed, 1 fails
// Response: No success message (only individual error for failed sensor)
```

---

## Integration with God-Kaiser

### Configuration Workflow

1. User adds sensor in God-Kaiser UI
2. God-Kaiser validates sensor type and GPIO (client-side)
3. God-Kaiser publishes config to ESP via MQTT
   - Topic: `kaiser/{kaiser_id}/esp/{esp_id}/config`
   - Payload: JSON with `sensors` array
4. ESP receives and processes configuration
   - Validates fields
   - Configures sensor in SensorManager
   - Persists to NVS
5. ESP publishes response
   - Topic: `kaiser/{kaiser_id}/esp/{esp_id}/config_response`
   - Payload: Success or error details
6. God-Kaiser receives response and confirms in UI
7. Sensor immediately starts publishing data
   - Next measurement cycle includes new sensor
   - Topic: `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data`

### Update Workflow

1. User modifies sensor in God-Kaiser UI
2. God-Kaiser publishes updated config (same GPIO)
3. ESP detects existing sensor (runtime reconfiguration)
4. ESP updates configuration in-place
5. ESP persists updated config to NVS
6. ESP publishes success response
7. Sensor continues operation with new config

### Removal Workflow

1. User deactivates sensor in God-Kaiser UI (`DELETE /sensors/{esp_id}/{config_id}`)
2. God-Kaiser publishes config with `"active": false` (MQTT config push)
3. **CO₂ (AUT-527):** Server appends **two** tombstones — DB `gpio` (e.g. 18) **and** UART1 complement (17) — each with `uart_rx_pin`/`uart_tx_pin`/`uart_baud=9600`
4. ESP processes **`active=false` before validation** (`main.cpp`)
5. ESP `removeSensor()` releases GPIO (+ UART rx/tx); CO₂ fallback tries GPIO 17/18 if primary gpio miss
6. NVS entry removed via `removeSensorConfig()` inside `removeSensor()`
7. ESP publishes success in aggregated `config_response`
8. Sensor stops publishing data

**Symptom:** GPIO 18 „belegt“ after UI delete → stale NVS slot on GPIO **17** (UART pair). Fix: delete CO₂ again (dual tombstone) or factory reset NVS.

---

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

### MQTT Monitoring

**Subscribe to config topics:**
```bash
mosquitto_sub -h 192.168.0.198 -p 8883 \
  -t "kaiser/+/esp/+/config" \
  -t "kaiser/+/esp/+/config_response" \
  -v
```

**Publish test configuration:**
```bash
mosquitto_pub -h 192.168.0.198 -p 8883 \
  -t "kaiser/god/esp/ESP_AB12CD/config" \
  -m '{
    "sensors": [
      {
        "gpio": 4,
        "sensor_type": "ph_sensor",
        "sensor_name": "Test pH Sensor",
        "subzone_id": "test_zone",
        "active": true,
        "raw_mode": true
      }
    ],
    "actuators": []
  }'
```

**Publish UART CO2 configuration (ESP32-S3 example):**
```bash
mosquitto_pub -h 192.168.0.198 -p 1883 \
  -t "kaiser/god/esp/ESP_AEAE64/config" \
  -m '{
    "sensors": [
      {
        "gpio": 18,
        "sensor_type": "co2",
        "sensor_name": "CO2 Sensor",
        "subzone_id": "greenhouse",
        "active": true,
        "raw_mode": true,
        "interface_type": "UART",
        "uart_rx_pin": 18,
        "uart_tx_pin": 17,
        "uart_baud": 9600
      }
    ],
    "actuators": []
  }'
```

### Serial Monitor Output

**Successful Configuration:**
```
[INFO] MQTT message received: kaiser/god/esp/ESP_AB12CD/config
[INFO] Handling sensor configuration from MQTT
[DEBUG] Extracted GPIO: 4
[DEBUG] Sensor type: ph_sensor
[DEBUG] Sensor name: Test pH Sensor
[INFO] ConfigManager: Sensor config validation passed
[INFO] Sensor Manager: Configured new sensor on GPIO 4 (ph_sensor)
[INFO]   ✅ Configuration persisted to NVS
[INFO] ConfigManager: Saved sensor config for GPIO 4
[INFO] Sensor configured: GPIO 4 (ph_sensor)
[INFO] ConfigResponse published [sensor] status=success
```

**Successful UART CO2 Configuration:**
```
[INFO] Handling sensor configuration from MQTT
[INFO] ConfigManager: UART sensor 'co2' rx=18 tx=17 baud=9600
[INFO] Sensor Manager: Configured UART CO2 'co2' Serial2 rx=18 tx=17 baud=9600 (logical GPIO 18)
[INFO]   ✅ Configuration persisted to NVS
[INFO] ConfigResponse published [sensor] status=success
[DEBUG] SensorManager: CO2 warmup (178s remaining)
```

**Successful UART CO2 Tombstone (delete):**
```
[INFO] Sensor removed: GPIO 17
[INFO] Sensor removed: GPIO 18
[INFO] ConfigResponse … success=3 failed=0
```

**UART CO2 configure failure (GPIO ghost):**
```
[ERROR] Sensor validation failed for GPIO 18
[ERROR] GPIO 18 reserved by sensor/co2 (UART RX GPIO 18 not available)
```
→ Prior CO₂ slot still in NVS on GPIO 17; run UI delete (dual tombstone) before re-adding on GPIO 18.

**Error Example:**
```
[INFO] MQTT message received: kaiser/god/esp/ESP_AB12CD/config
[INFO] Handling sensor configuration from MQTT
[ERROR] Sensor config missing required field 'gpio'
[ERROR] ConfigResponse publish failed for topic: kaiser/god/esp/ESP_AB12CD/config_response
```

### NVS Inspection

**Using PlatformIO NVS Tool:**
```bash
pio run --target nvsmonitor
```

**Manual NVS Read (ESP-IDF):**
```bash
esptool.py read_flash 0x9000 0x6000 nvs.bin
nvs_partition_gen.py dump nvs.bin
```

**Expected NVS Structure:**
```
Namespace: sensor_config
  sensor_count = 2
  sensor_0_gpio = 4
  sensor_0_type = "ph_sensor"
  sensor_0_name = "Test pH Sensor"
  sensor_0_subzone = "test_zone"
  sensor_0_active = true
  sensor_0_raw_mode = true
  sensor_1_gpio = 34
  sensor_1_type = "ec_sensor"
  sensor_1_name = "EC Sensor"
  sensor_1_subzone = ""
  sensor_1_active = true
  sensor_1_raw_mode = true
```

---

## Related Components

### GPIOManager Integration

**Purpose:** Hardware safety and pin conflict prevention

**Methods Used:**
- `isPinAvailable(gpio)` - Check if GPIO free
- `requestPin(gpio, "sensor", name)` - Reserve GPIO
- `releasePin(gpio)` - Release GPIO on removal

**UART CO2:** Reserves `uart_rx_pin` and `uart_tx_pin` (and logical `gpio` when distinct). Removal releases all three and ends `Serial2`.

**Conflict Prevention:**
- Prevents multiple sensors on same GPIO
- Prevents sensor/actuator GPIO conflicts
- Validates against reserved GPIOs (UART, Boot, etc.)

### StorageManager Integration

**Purpose:** NVS abstraction layer

**Namespace:** `sensor_config`

**Operations:**
- `beginNamespace("sensor_config", read_only)` - Open namespace
- `putUInt8(key, value)` - Store GPIO, count
- `putString(key, value)` - Store type, name, subzone
- `putBool(key, value)` - Store active, raw_mode flags
- `getUInt8(key, default)` - Read GPIO, count
- `getStringObj(key, default)` - Read strings
- `getBool(key, default)` - Read booleans
- `endNamespace()` - Close namespace

### ErrorTracker Integration

**Errors Tracked:**
- `ERROR_SENSOR_INIT_FAILED` - Sensor configuration failure
- `ERROR_GPIO_CONFLICT` - GPIO already in use
- `ERROR_GPIO_RESERVED` - GPIO reservation failed
- `ERROR_UART_INIT_FAILED` (1033) - UART CO2 init / missing pins
- `ERROR_UART_READ_TIMEOUT` (1034) - MH-Z19 read timeout
- `ERROR_UART_CHECKSUM_FAILED` (1035) - Invalid UART frame
- `ERROR_UART_INVALID_PPM` (1036) - PPM out of range

**Severity:** ERROR level

### TopicBuilder Integration

**Topics Used:**
- `buildConfigTopic()` - Input topic
- `buildConfigResponseTopic()` - Response topic

**Dynamic Values:**
- `{kaiser_id}` - From global `g_kaiser.kaiser_id`
- `{esp_id}` - From `ConfigManager::getESPId()`

## Next Flows

→ [Sensor Reading Flow](02-sensor-reading-flow.md) - How configured sensors are read  
→ [Runtime Actuator Config Flow](05-runtime-actuator-config-flow.md) - Similar flow for actuators  
→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - Message dispatch  
→ [Boot Sequence](01-boot-sequence.md) - Sensor loading from NVS on startup  

---

**End of Runtime Sensor Configuration Flow Documentation**

