# Runtime Actuator Configuration Flow

## Overview

Dynamic actuator configuration via MQTT allows God-Kaiser to add, modify, or remove actuators without reflashing firmware. Similar to sensor configuration but with additional safety validations and emergency stop integration.

## Files Analyzed

- `src/main.cpp` (lines 349-355, 828-831) - MQTT routing, handleActuatorConfig()
- `src/services/actuator/actuator_manager.cpp` (lines 166-323, 525-694) - createDriver(), configureActuator(), removeActuator(), parseActuatorDefinition(), handleActuatorConfig(), validateActuatorConfig()
- `src/services/actuator/actuator_manager.h` (lines 1-100) - Actuator manager interface
- `src/services/config/config_manager.cpp` (lines 625-726) - saveActuatorConfig(), loadActuatorConfig(), validateActuatorConfig()
- `src/services/config/config_manager.h` (lines 57-65) - Config manager actuator interface
- `src/services/config/storage_manager.cpp/.h` - NVS operations abstraction
- `src/services/config/config_response.cpp` (lines 1-72) - Response publishing
- `src/services/config/config_response.h` (lines 1-31) - Response builder interface
- `src/utils/json_helpers.h` (lines 9-82) - JSON field extraction helpers
- `src/utils/topic_builder.cpp` (lines 124-138) - Topic generation
- `src/models/actuator_types.h` (lines 1-138) - ActuatorConfig, ActuatorCommand, ActuatorStatus structures, ActuatorTypeTokens
- `src/models/config_types.h` (lines 1-74) - ConfigResponsePayload, ConfigType, ConfigStatus
- `src/models/error_codes.h` (lines 130-191) - ConfigErrorCode enum and string conversion
- `src/services/actuator/actuator_drivers/` - Driver implementations (PumpActuator, PWMActuator, ValveActuator)

## Prerequisites

- MQTT client connected
- Actuator Manager initialized
- Safety Controller operational
- Config Manager operational
- NVS accessible

## Trigger

MQTT message on: `kaiser/{kaiser_id}/esp/{esp_id}/config`

---

## Configuration Payload Format

```json
{
  "sensors": [],
  "actuators": [
    {
      "gpio": 5,
      "actuator_type": "pump",
      "actuator_name": "Water Pump 1",
      "subzone_id": "irrigation",
      "active": true,
      "critical": false,
      "inverted_logic": false,
      "default_state": false
    },
    {
      "gpio": 18,
      "actuator_type": "pwm",
      "actuator_name": "Exhaust Fan",
      "subzone_id": "ventilation",
      "active": true,
      "default_pwm": 128
    }
  ]
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `gpio` | Number | Primary GPIO pin (0-39) |
| `actuator_type` | String | "pump", "valve", "pwm", "relay" |
| `actuator_name` | String | Human-readable name |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `aux_gpio` | Number | 255 | Secondary GPIO (valves) |
| `subzone_id` | String | "" | Subzone identifier |
| `active` | Boolean | true | Enable/disable |
| `critical` | Boolean | false | Critical actuator flag |
| `inverted_logic` | Boolean | false | LOW=ON for relays |
| `default_state` | Boolean | false | Failsafe state |
| `default_pwm` | Number | 0 | Default PWM (0-255) |

---

## Flow Steps

### STEP 1: MQTT Callback Routing

**File:** `src/main.cpp` (lines 349-355, 828-831)

**Code:**

```cpp
// In MQTT callback (lines 349-355)
String config_topic = String(TopicBuilder::buildConfigTopic());
if (topic == config_topic) {
  handleSensorConfig(payload);
  handleActuatorConfig(payload);
  return;
}

// Handler function (lines 828-831)
void handleActuatorConfig(const String& payload) {
  LOG_INFO("Handling actuator configuration from MQTT");
  actuatorManager.handleActuatorConfig(payload);
}
```

**Routing:** Same topic handles both sensors and actuators. Each handler processes its relevant array.

---

### STEP 2: Parse Configuration JSON

**File:** `src/services/actuator/actuator_manager.cpp` (lines 626-694)

**Code:**

```cpp
bool ActuatorManager::handleActuatorConfig(const String& payload) {
  LOG_INFO("Handling actuator configuration from MQTT");

  DynamicJsonDocument doc(4096);
  DeserializationError error = deserializeJson(doc, payload);
  if (error) {
    String message = "Failed to parse actuator config JSON: " + String(error.c_str());
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::ACTUATOR, ConfigErrorCode::JSON_PARSE_ERROR, message);
    return false;
  }

  JsonArray actuators = doc["actuators"].as<JsonArray>();
  if (actuators.isNull()) {
    String message = "Actuator config missing 'actuators' array";
    LOG_ERROR(message);
    ConfigResponseBuilder::publishError(
        ConfigType::ACTUATOR, ConfigErrorCode::MISSING_FIELD, message);
    return false;
  }

  size_t total = actuators.size();
  if (total == 0) {
    String message = "Actuator config array is empty";
    LOG_WARNING(message);
    ConfigResponseBuilder::publishError(
        ConfigType::ACTUATOR, ConfigErrorCode::MISSING_FIELD, message);
    return false;
  }
  
  uint8_t configured = 0;
  for (JsonObject actuatorObj : actuators) {
    ActuatorConfig config;
    String parse_error;
    ConfigErrorCode error_code = ConfigErrorCode::NONE;
    JsonVariantConst failed_variant = actuatorObj;
    JsonObjectConst actuatorObjConst = actuatorObj;

    if (!parseActuatorDefinition(actuatorObjConst, config, parse_error, error_code)) {
      if (parse_error.isEmpty()) {
        parse_error = "Invalid actuator definition";
      }
      if (error_code == ConfigErrorCode::NONE) {
        error_code = ConfigErrorCode::VALIDATION_FAILED;
      }
      ConfigResponseBuilder::publishError(
          ConfigType::ACTUATOR, error_code, parse_error, failed_variant);
      continue;
    }

    if (!configureActuator(config)) {
      String message = "Failed to configure actuator on GPIO " + String(config.gpio);
      LOG_ERROR(message);
      ConfigResponseBuilder::publishError(
          ConfigType::ACTUATOR, ConfigErrorCode::UNKNOWN_ERROR, message, failed_variant);
      continue;
    }

    configured++;
  }

  if (configured == total) {
    String message = "Configured " + String(configured) + " actuator(s) successfully";
    ConfigResponseBuilder::publishSuccess(ConfigType::ACTUATOR, configured, message);
    return true;
  }

  return configured > 0;
}
```

**JSON Buffer:** 4096 bytes (supports up to ~10 actuators per message)

**Error Handling:**
- JSON parse error → Publish error response, abort
- Missing 'actuators' array → Publish error, abort
- Empty array → Warning, abort
- Individual actuator errors → Continue with next actuator

---

### STEP 3: Parse Individual Actuator

**File:** `src/services/actuator/actuator_manager.cpp` (lines 525-624)

**Code:**

```cpp
bool ActuatorManager::parseActuatorDefinition(const JsonObjectConst& obj,
                                              ActuatorConfig& config,
                                              String& error_message,
                                              ConfigErrorCode& error_code) const {
  config = ActuatorConfig();
  error_message = "";
  error_code = ConfigErrorCode::NONE;

  // Validate 'gpio' field (required)
  if (!obj.containsKey("gpio")) {
    error_message = "Actuator config missing required field 'gpio'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  int gpio_value = 255;
  if (!JsonHelpers::extractInt(obj, "gpio", gpio_value)) {
    error_message = "Actuator field 'gpio' must be an integer";
    error_code = ConfigErrorCode::TYPE_MISMATCH;
    return false;
  }
  config.gpio = static_cast<uint8_t>(gpio_value);

  // Optional 'aux_gpio' field
  int aux_gpio_value = 255;
  if (JsonHelpers::extractInt(obj, "aux_gpio", aux_gpio_value)) {
    config.aux_gpio = static_cast<uint8_t>(aux_gpio_value);
  }

  // Validate 'actuator_type' field (required, accepts 'type' as alias)
  if (obj.containsKey("actuator_type")) {
    if (!JsonHelpers::extractString(obj, "actuator_type", config.actuator_type)) {
      error_message = "Actuator field 'actuator_type' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else if (obj.containsKey("type")) {
    if (!JsonHelpers::extractString(obj, "type", config.actuator_type)) {
      error_message = "Actuator field 'type' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else {
    error_message = "Actuator config missing required field 'actuator_type'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  if (config.actuator_type.length() == 0) {
    error_message = "Actuator type cannot be empty";
    error_code = ConfigErrorCode::VALIDATION_FAILED;
    return false;
  }

  // Validate 'actuator_name' field (required, accepts 'name' as alias)
  if (obj.containsKey("actuator_name")) {
    if (!JsonHelpers::extractString(obj, "actuator_name", config.actuator_name)) {
      error_message = "Actuator field 'actuator_name' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else if (obj.containsKey("name")) {
    if (!JsonHelpers::extractString(obj, "name", config.actuator_name)) {
      error_message = "Actuator field 'name' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else {
    error_message = "Actuator config missing required field 'actuator_name'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  // Optional fields
  JsonHelpers::extractString(obj, "subzone_id", config.subzone_id, "");

  bool bool_value = false;
  if (JsonHelpers::extractBool(obj, "active", bool_value, true)) {
    config.active = bool_value;
  } else {
    config.active = true;
  }

  if (JsonHelpers::extractBool(obj, "critical", bool_value, false)) {
    config.critical = bool_value;
  }

  if (JsonHelpers::extractBool(obj, "inverted_logic", bool_value, false)) {
    config.inverted_logic = bool_value;
  } else if (JsonHelpers::extractBool(obj, "inverted", bool_value, false)) {
    config.inverted_logic = bool_value;
  }

  if (JsonHelpers::extractBool(obj, "default_state", bool_value, false)) {
    config.default_state = bool_value;
  }

  int default_pwm_value = 0;
  if (JsonHelpers::extractInt(obj, "default_pwm", default_pwm_value)) {
    default_pwm_value = constrain(default_pwm_value, 0, 255);
    config.default_pwm = static_cast<uint8_t>(default_pwm_value);
  }

  return true;
}
```

### Required Fields

| Field | Type | Validation | Aliases | Error Code |
|-------|------|------------|---------|------------|
| `gpio` | Number | 0-39, not 255 | - | MISSING_FIELD, TYPE_MISMATCH |
| `actuator_type` | String | Non-empty | `type` | MISSING_FIELD, TYPE_MISMATCH |
| `actuator_name` | String | Non-empty | `name` | MISSING_FIELD, TYPE_MISMATCH |

### Optional Fields

| Field | Type | Default | Aliases | Description |
|-------|------|---------|---------|-------------|
| `aux_gpio` | Number | 255 | - | Secondary GPIO (valves) |
| `subzone_id` | String | "" | - | Subzone identifier |
| `active` | Boolean | true | - | Enable/disable (false = removal) |
| `critical` | Boolean | false | - | Critical actuator flag |
| `inverted_logic` | Boolean | false | `inverted` | LOW=ON for relays |
| `default_state` | Boolean | false | - | Failsafe state |
| `default_pwm` | Number | 0 | - | Default PWM (0-255, constrained) |

**Field Aliases:** Supports both `actuator_type`/`type` and `actuator_name`/`name` for backward compatibility.

---

### STEP 4: Validate Actuator Configuration

**File:** `src/services/actuator/actuator_manager.cpp` (lines 154-164)

**Code:**

```cpp
bool ActuatorManager::validateActuatorConfig(const ActuatorConfig& config) const {
  if (config.gpio == 255) {
    LOG_ERROR("Actuator config missing GPIO");
    return false;
  }
  if (config.actuator_type.length() == 0) {
    LOG_ERROR("Actuator config missing type");
    return false;
  }
  return true;
}
```

**Additional Validation in ConfigManager:**

**File:** `src/services/config/config_manager.cpp` (lines 716-726)

```cpp
bool ConfigManager::validateActuatorConfig(const ActuatorConfig& config) const {
  if (config.gpio == 255 || config.gpio > 39) {
    LOG_WARNING("ConfigManager: Invalid actuator GPIO " + String(config.gpio));
    return false;
  }
  if (config.actuator_type.length() == 0) {
    LOG_WARNING("ConfigManager: Actuator type is empty");
    return false;
  }
  return true;
}
```

**Validation Rules:**
1. GPIO must not be 255 (invalid marker)
2. GPIO must be 0-39 (ESP32 valid range)
3. Actuator type must not be empty

---

### STEP 5: Configure Actuator (with skip-unchanged optimization)

**File:** `src/services/actuator/actuator_manager.cpp` (lines 187+)

Since R20-P11 the method uses a 3-path optimization to avoid unnecessary GPIO glitches,
NVS wear and log spam when the server pushes identical or soft-changed configs.

**Code (simplified — see source for full implementation):**

```cpp
bool ActuatorManager::configureActuator(const ActuatorConfig& incoming_config) {
  if (!initialized_ && !begin()) return false;

  ActuatorConfig config = incoming_config;
  if (!validateActuatorConfig(config)) return false;

  // 1. Deactivation (unchanged)
  if (!config.active) {
    removeActuator(config.gpio);
    return true;
  }

  // 2. GPIO conflict check (sensor vs actuator — defense-in-depth)
  if (sensorManager.hasSensorOnGPIO(config.gpio)) { return false; }

  // 3. R20-P11: Skip-unchanged + soft-update optimization
  RegisteredActuator* existing = findActuator(config.gpio);
  if (existing) {
    const ActuatorConfig& prev = existing->config;

    bool structural_changed = (prev.actuator_type != config.actuator_type) ||
                              (prev.aux_gpio      != config.aux_gpio);

    bool soft_changed = (prev.actuator_name != config.actuator_name)   ||
                        (prev.subzone_id    != config.subzone_id)       ||
                        (prev.critical      != config.critical)         ||
                        (prev.inverted_logic!= config.inverted_logic)   ||
                        (prev.default_state != config.default_state)    ||
                        (prev.default_pwm   != config.default_pwm);

    if (!structural_changed && !soft_changed) {
      // PATH A: Fully identical — skip
      LOG_I(TAG, "config unchanged, skipping");
      return true;  // No GPIO touch, no NVS write
    }

    if (!structural_changed) {
      // PATH B: Soft-only change — in-place update, 1x NVS save, no GPIO release
      existing->config.actuator_name = config.actuator_name;
      existing->config.subzone_id    = config.subzone_id;
      existing->config.critical      = config.critical;
      existing->config.inverted_logic= config.inverted_logic;
      existing->config.default_state = config.default_state;
      existing->config.default_pwm   = config.default_pwm;
      configManager.saveActuatorConfig(actuators, count);
      publishActuatorStatus(config.gpio);
      return true;
    }

    // PATH C: Structural change — full remove + re-create
    existing->driver->setBinary(false);  // emergency stop before teardown
    removeActuator(config.gpio);
  }

  // New actuator or after structural remove: create driver, register, persist NVS
  auto driver = createDriver(config.actuator_type);
  if (!driver) return false;
  if (!driver->begin(config)) return false;

  slot->driver = std::move(driver);
  slot->config = slot->driver->getConfig();
  // ... persist to NVS, publish status
}
```

**3-Path Decision Matrix:**

| Path | Condition | GPIO | NVS Writes | Driver | Log |
|------|-----------|------|------------|--------|-----|
| A: Unchanged | No fields differ | Untouched | 0 | Untouched | "config unchanged, skipping" |
| B: Soft-change | Only name/subzone/critical/inverted/default differ | Untouched | 1 | Untouched | "Soft update on GPIO X" |
| C: Structural | actuator_type or aux_gpio differ (or new actuator) | Release + Re-allocate | 2 | Destroy + Create | "Structural reconfiguration on GPIO X" |

**Compared Fields (all fields from `parseActuatorDefinition`):**

| Category | Fields | Triggers |
|----------|--------|----------|
| Structural | `actuator_type`, `aux_gpio` | Path C (full remove + re-create) |
| Soft | `actuator_name`, `subzone_id`, `critical`, `inverted_logic`, `default_state`, `default_pwm` | Path B (in-place update) |
| Implicit | `gpio` | Lookup key (not compared, used by `findActuator`) |
| Pre-checked | `active` | Handled before comparison (removal path) |

**Operations:**
1. Auto-initialize if not initialized
2. Validate configuration
3. Handle deactivation (removal if `active=false`)
4. Check GPIO conflict with sensors
5. Check for existing actuator and compare all config fields
6. **Path A:** Skip if unchanged (0 NVS writes, no GPIO touch)
7. **Path B:** Soft-update in-place if only metadata changed (1 NVS write, no GPIO touch)
8. **Path C:** Full remove + re-create if type/aux_gpio changed (2 NVS writes, GPIO release + allocate)
9. Check actuator array capacity (MAX_ACTUATORS: 8 for XIAO, 12 for ESP32)
10. Create actuator driver
11. Initialize driver with config
12. Register in array (config retrieved from driver)
13. Persist all actuators to NVS
14. Publish status

**Note:** GPIO reservation handled by driver during `begin()`, not here.
Steps 9-14 only apply to Path C and new actuators (not Path A or B).

---

### STEP 6: Create Actuator Driver

**File:** `src/services/actuator/actuator_manager.cpp` (lines 166-181)

**Code:**

```cpp
std::unique_ptr<IActuatorDriver> ActuatorManager::createDriver(const String& actuator_type) const {
  if (actuator_type == ActuatorTypeTokens::PUMP) {
    return std::unique_ptr<IActuatorDriver>(new PumpActuator());
  }
  if (actuator_type == ActuatorTypeTokens::PWM) {
    return std::unique_ptr<IActuatorDriver>(new PWMActuator());
  }
  if (actuator_type == ActuatorTypeTokens::VALVE) {
    return std::unique_ptr<IActuatorDriver>(new ValveActuator());
  }
  if (actuator_type == ActuatorTypeTokens::RELAY) {
    return std::unique_ptr<IActuatorDriver>(new PumpActuator());  // Relay handled like pump (binary)
  }
  LOG_ERROR("Unknown actuator type: " + actuator_type);
  return nullptr;
}
```

**Supported Types:**

| Type Token | Driver Class | Description |
|------------|--------------|-------------|
| `"pump"` | `PumpActuator` | Binary ON/OFF control |
| `"valve"` | `ValveActuator` | Dual GPIO (open/close) |
| `"pwm"` | `PWMActuator` | Variable speed (0-255) |
| `"relay"` | `PumpActuator` | Binary (same as pump) |

**Driver Interface:**

```cpp
class IActuatorDriver {
public:
  virtual bool begin(const ActuatorConfig& config) = 0;
  virtual void end() = 0;
  virtual bool setState(bool state) = 0;
  virtual bool setPWM(uint8_t value) = 0;
  virtual bool setValue(float value) = 0;  // Normalized 0.0-1.0
  virtual bool setBinary(bool state) = 0;
  virtual bool getState() const = 0;
  virtual uint8_t getPWM() const = 0;
  virtual ActuatorConfig getConfig() const = 0;
  virtual void emergencyStop(const String& reason) = 0;
  virtual bool clearEmergency() = 0;
  virtual void loop() = 0;
  virtual ~IActuatorDriver() = default;
};
```

---

### STEP 7: Remove Actuator from Manager

**File:** `src/services/actuator/actuator_manager.cpp` (lines 285-323)

**Code:**

```cpp
bool ActuatorManager::removeActuator(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator) {
    return false;
  }

  LOG_INFO("Actuator Manager: Removing actuator on GPIO " + String(gpio));
  
  // Phase 7: Safety - stop actuator before removal
  if (actuator->driver) {
    LOG_INFO("  Stopping actuator before removal");
    actuator->driver->setState(false);
    actuator->driver->end();
    actuator->driver.reset();
  }

  actuator->in_use = false;
  actuator->gpio = 255;
  actuator->config = ActuatorConfig();
  actuator->emergency_stopped = false;
  actuator_count_ = actuator_count_ > 0 ? actuator_count_ - 1 : 0;
  
  // Phase 7: Persist removal to NVS immediately (save remaining actuators)
  ActuatorConfig actuators[MAX_ACTUATORS];
  uint8_t count = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use) {
      actuators[count++] = actuators_[i].config;
    }
  }
  if (!configManager.saveActuatorConfig(actuators, count)) {
    LOG_ERROR("Actuator Manager: Failed to persist config to NVS");
  } else {
    LOG_INFO("  ✅ Configuration persisted to NVS");
  }
  
  LOG_INFO("Actuator removed from GPIO " + String(gpio));
  return true;
}
```

**Operations:**
1. Find actuator in registry
2. Stop actuator (setState(false))
3. End driver (cleanup)
4. Reset driver pointer
5. Clear slot (in_use=false, gpio=255)
6. Decrement actuator count
7. Persist remaining actuators to NVS

---

### STEP 8: Persist to NVS

**File:** `src/services/config/config_manager.cpp` (lines 625-671)

**Code:**

```cpp
bool ConfigManager::saveActuatorConfig(const ActuatorConfig actuators[], uint8_t actuator_count) {
  LOG_INFO("ConfigManager: Saving Actuator configurations...");
  
  if (!storageManager.beginNamespace("actuator_config", false)) {
    LOG_ERROR("ConfigManager: Failed to open actuator_config namespace");
    return false;
  }
  
  bool success = storageManager.putUInt8("actuator_count", actuator_count);
  char key_buffer[64];
  
  for (uint8_t i = 0; i < actuator_count; i++) {
    const ActuatorConfig& config = actuators[i];
    if (!validateActuatorConfig(config)) {
      continue;
    }
    
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "gpio");
    success &= storageManager.putUInt8(key_buffer, config.gpio);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "aux_gpio");
    success &= storageManager.putUInt8(key_buffer, config.aux_gpio);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "type");
    success &= storageManager.putString(key_buffer, config.actuator_type);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "name");
    success &= storageManager.putString(key_buffer, config.actuator_name);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "subzone");
    success &= storageManager.putString(key_buffer, config.subzone_id);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "active");
    success &= storageManager.putBool(key_buffer, config.active);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "critical");
    success &= storageManager.putBool(key_buffer, config.critical);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "inverted");
    success &= storageManager.putBool(key_buffer, config.inverted_logic);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "default_state");
    success &= storageManager.putBool(key_buffer, config.default_state);
    buildActuatorKey(key_buffer, sizeof(key_buffer), i, "default_pwm");
    success &= storageManager.putUInt8(key_buffer, config.default_pwm);
  }
  
  storageManager.endNamespace();
  
  if (!success) {
    LOG_ERROR("ConfigManager: Failed to save actuator configurations");
  }
  
  return success;
}
```

**Key Building Helper:**

```cpp
static void buildActuatorKey(char* buffer, size_t buffer_size, uint8_t index, const char* field) {
  snprintf(buffer, buffer_size, "actuator_%d_%s", index, field);
}
```

### NVS Keys

**Namespace:** `actuator_config`

**Keys:**
- `actuator_count` (uint8_t) - Total actuator count
- `actuator_{i}_gpio` (uint8_t) - Primary GPIO pin
- `actuator_{i}_aux_gpio` (uint8_t) - Secondary GPIO (valves)
- `actuator_{i}_type` (String) - Actuator type
- `actuator_{i}_name` (String) - Actuator name
- `actuator_{i}_subzone` (String) - Subzone ID
- `actuator_{i}_active` (bool) - Active flag
- `actuator_{i}_critical` (bool) - Critical flag
- `actuator_{i}_inverted` (bool) - Inverted logic flag
- `actuator_{i}_default_state` (bool) - Default state
- `actuator_{i}_default_pwm` (uint8_t) - Default PWM value

**Example NVS Layout:**

```
Namespace: actuator_config
  actuator_count = 2
  actuator_0_gpio = 5
  actuator_0_aux_gpio = 255
  actuator_0_type = "pump"
  actuator_0_name = "Water Pump 1"
  actuator_0_subzone = "irrigation"
  actuator_0_active = true
  actuator_0_critical = false
  actuator_0_inverted = false
  actuator_0_default_state = false
  actuator_0_default_pwm = 0
  actuator_1_gpio = 18
  actuator_1_aux_gpio = 255
  actuator_1_type = "pwm"
  actuator_1_name = "Exhaust Fan"
  actuator_1_subzone = "ventilation"
  actuator_1_active = true
  actuator_1_critical = false
  actuator_1_inverted = false
  actuator_1_default_state = false
  actuator_1_default_pwm = 128
```

**Note:** All actuators saved together (not individual saves). Removal saves remaining actuators.

---

## Safety Considerations

### Emergency Stop Integration

Newly configured actuators:
- Start in safe state (OFF)
- Inherit current emergency stop status
- Cannot be activated if emergency stop active

### Runtime Stability (R20-P11)

Repeated config pushes (e.g. subzone reassignment, heartbeat-triggered config sync):
- Identical config: actuator state preserved (running actuators stay ON)
- Soft-change only: GPIO untouched, driver untouched, no glitch on relay/pump pins
- Structural change: `setBinary(false)` before teardown to prevent uncontrolled pin states

### GPIO Conflicts

Additional checks vs sensors:
- Verify GPIO not used by sensor
- Verify GPIO not used by another actuator
- Verify GPIO not reserved (Boot, UART, etc.)

### Critical Actuators

```cpp
config.critical = true;  // Priority in recovery
```

Critical actuators:
- Restored first after emergency stop
- Higher priority in power management
- Extra logging/monitoring

---

## Driver Types

### Pump Driver (Binary)

```cpp
std::unique_ptr<IActuatorDriver> ActuatorManager::createDriver(const String& actuator_type) const {
  if (actuator_type == ActuatorTypeTokens::PUMP) {
    return std::unique_ptr<IActuatorDriver>(new PumpActuator());
  }
  // ...
}
```

**Supports:** ON/OFF, runtime tracking

### Valve Driver (Dual GPIO)

**Supports:** Open/Close with pulse control, latching valves

### PWM Driver (Variable)

**Supports:** 0-255 duty cycle, smooth transitions

### Relay Driver (Binary)

**Supports:** Inverted logic, bounce protection

---

### STEP 9: Publish Response

**File:** `src/services/config/config_response.cpp` (lines 1-72)

**Success Response:**

```json
{
  "status": "success",
  "type": "actuator",
  "count": 2,
  "message": "Configured 2 actuator(s) successfully"
}
```

**Error Response:**

```json
{
  "status": "error",
  "type": "actuator",
  "count": 0,
  "message": "Actuator config missing required field 'gpio'",
  "error_code": "MISSING_FIELD",
  "failed_item": {
    "actuator_type": "pump",
    "actuator_name": "Pump1"
  }
}
```

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config_response`

**QoS:** 1 (at least once)

**Implementation:** Same as sensor config flow (uses `ConfigResponseBuilder::publishSuccess()` / `publishError()`)

---

## Timing Analysis

| Operation | Duration | Notes |
|-----------|----------|-------|
| JSON parse | 5-20ms | |
| Field validation | <1ms per field | |
| GPIO conflict check | <1ms | |
| Config comparison (R20-P11) | <1ms | 8 field comparisons |
| Soft-update in-place (R20-P11) | <1ms + NVS | Path B: no driver touch |
| Driver creation | <1ms | Path C only |
| Driver initialization | 50-200ms (hardware setup) | Path C only |
| NVS write | 10-50ms per actuator | Path A: 0 writes, Path B: 1 write, Path C: 2 writes |
| Response publish | 10-20ms | |

**Total:** 100-300ms per actuator

**Driver Init Overhead:**
- Pump/Relay: ~50ms (GPIO setup)
- Valve: ~100ms (dual GPIO setup)
- PWM: ~150ms (LEDC channel allocation)

---

## Memory Usage

| Allocation | Size |
|------------|------|
| JSON buffer | 4096 bytes (stack) |
| ActuatorConfig struct | ~128 bytes |
| Driver instance | ~64-128 bytes (varies by type) |
| RegisteredActuator | ~200 bytes |
| Temp strings | ~256 bytes |

**Total:** ~4.5KB per config operation

**Stack Usage:**
- JSON parsing buffer: 4096 bytes (stack)
- ConfigResponsePayload: ~512 bytes (stack)
- Temporary strings: ~256 bytes (stack)

**Heap Usage:**
- ActuatorConfig structs: ~128 bytes × actuator_count (heap)
- Driver instances: ~64-128 bytes × actuator_count (heap, via unique_ptr)
- String allocations: Variable (depends on actuator names/types)

**Max Actuators:**
- ESP32 WROOM: 12 actuators
- XIAO ESP32C3: 8 actuators

**Total Memory:** ~2.4KB (12 actuators) + driver overhead

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
- Abort entire operation (no actuators processed)

### Missing Required Fields

**Causes:** 
- `gpio`, `actuator_type`, or `actuator_name` missing from JSON

**Detection:** `!obj.containsKey()` check

**Recovery:**
- Publish error for that actuator with `MISSING_FIELD`
- Include `failed_item` in response
- Continue processing other actuators

### Type Mismatch Errors

**Causes:**
- Field present but wrong type (e.g., `gpio` as string)

**Detection:** `JsonHelpers::extractInt/String/Bool()` returns false

**Recovery:**
- Publish error with `TYPE_MISMATCH`
- Include `failed_item` in response
- Continue processing other actuators

### Validation Failures

**Causes:**
- GPIO = 255 (invalid marker)
- GPIO > 39 (out of range)
- actuator_type empty string

**Detection:** `ActuatorManager::validateActuatorConfig()` or `ConfigManager::validateActuatorConfig()` returns false

**Recovery:**
- Publish error with `VALIDATION_FAILED`
- Include `failed_item` in response
- Continue processing other actuators

### GPIO Conflicts

**Causes:** 
- GPIO already in use by sensor
- GPIO already in use by another actuator
- GPIO reserved by GPIOManager

**Detection:** 
- `SensorManager::hasSensorOnGPIO()` returns true
- `GPIOManager::isPinAvailable()` returns false

**Recovery:**
- Publish error with `GPIO_CONFLICT` (if implemented)
- Track error via ErrorTracker
- Continue processing other actuators

**Error Codes:** `ERROR_GPIO_CONFLICT`

### Driver Creation Failures

**Causes:**
- Unknown actuator type
- Driver constructor failed

**Detection:** `createDriver()` returns `nullptr`

**Recovery:**
- Publish error with `UNKNOWN_ERROR`
- Continue processing other actuators

### Driver Initialization Failures

**Causes:**
- Hardware initialization failed
- GPIO setup failed
- PWM channel allocation failed

**Detection:** `driver->begin(config)` returns false

**Recovery:**
- Publish error with `UNKNOWN_ERROR`
- Track error via ErrorTracker
- Continue processing other actuators

**Error Codes:** `ERROR_ACTUATOR_INIT_FAILED`

### Maximum Actuator Count Reached

**Causes:**
- `actuator_count_ >= MAX_ACTUATORS` (8 for XIAO, 12 for ESP32)

**Detection:** `getFreeSlot()` returns `nullptr`

**Recovery:**
- Publish error with `UNKNOWN_ERROR`
- Track error via ErrorTracker
- Continue processing other actuators

**Error Codes:** `ERROR_ACTUATOR_INIT_FAILED`

### NVS Write Failures

**Causes:** 
- NVS namespace full
- NVS corruption
- StorageManager operation failed

**Detection:** `StorageManager::put*()` returns false

**Recovery:**
- Actuator configured in RAM (ActuatorManager)
- **Not persisted to NVS** (lost on reboot)
- Log warning
- Continue operation

**Impact:** Actuator works until reboot, then lost

### Partial Success Handling

**Behavior:**
- Success response only published if **all** actuators succeed
- Individual errors published immediately per actuator
- Processing continues for remaining actuators

**Example:**
```json
// Request: 3 actuators
// Result: 2 succeed, 1 fails
// Response: No success message (only individual error for failed actuator)
```

---

## Complete Flow Sequence

```
MQTT Config Message (kaiser/{kaiser_id}/esp/{esp_id}/config)
  │
  ├─► STEP 1: MQTT Callback Routing (main.cpp:349-355, 828-831)
  │     └─► Topic match → handleActuatorConfig()
  │
  ├─► STEP 2: Parse Configuration JSON (actuator_manager.cpp:626-694)
  │     ├─► DynamicJsonDocument(4096 bytes)
  │     ├─► Extract "actuators" array
  │     └─► Validate array exists and not empty
  │
  ├─► STEP 3: Parse Individual Actuator (actuator_manager.cpp:525-624)
  │     │
  │     ├─► Extract required fields (gpio, actuator_type, actuator_name)
  │     │     ├─► JsonHelpers::extractInt() for gpio
  │     │     ├─► JsonHelpers::extractString() for actuator_type (or "type")
  │     │     └─► JsonHelpers::extractString() for actuator_name (or "name")
  │     │
  │     ├─► Extract optional fields (aux_gpio, subzone_id, active, critical, etc.)
  │     │     └─► JsonHelpers::extractInt/String/Bool() with defaults
  │     │
  │     ├─► STEP 4: Validate Configuration (actuator_manager.cpp:154-164)
  │     │     ├─► GPIO != 255
  │     │     └─► actuator_type not empty
  │     │
  │     ├─► If active=false:
  │     │     └─► STEP 7: Remove Actuator
  │     │           ├─► Stop actuator (setState(false))
  │     │           ├─► End driver
  │     │           ├─► Clear slot
  │     │           └─► Persist remaining actuators to NVS
  │     │
  │     └─► If active=true:
  │           ├─► STEP 5: Configure in ActuatorManager
  │           │     ├─► Check GPIO conflict with sensors
  │           │     ├─► Check if exists (reconfiguration)
  │           │     ├─► Stop existing if type changed
  │           │     ├─► Remove existing for reconfiguration
  │           │     ├─► Check MAX_ACTUATORS limit
  │           │     ├─► STEP 6: Create driver
  │           │     ├─► Initialize driver (hardware setup)
  │           │     └─► Register in actuator array
  │           │
  │           └─► STEP 8: Persist to NVS
  │                 ├─► Collect all active actuators
  │                 ├─► Save all fields (gpio, aux_gpio, type, name, etc.)
  │                 └─► Update actuator_count
  │
  └─► STEP 9: Publish Response (config_response.cpp)
        ├─► Build ConfigResponsePayload
        ├─► Serialize to JSON (512 bytes buffer)
        └─► Publish to config_response topic (QoS 1)
```

## Runtime Reconfiguration

**Phase 7 Feature:** Actuators can be reconfigured at runtime without removal.

**Behavior:**
- If actuator exists on same GPIO → Remove existing, create new
- Sensor conflict check performed
- Type change triggers emergency stop before removal
- All actuators saved together to NVS
- GPIO remains reserved (handled by driver)

**Example:**
```json
// Initial config
{"gpio": 5, "actuator_type": "pump", "actuator_name": "Pump A"}

// Runtime update
{"gpio": 5, "actuator_type": "pwm", "actuator_name": "Variable Pump"}
// → Stops existing pump, removes it, creates new PWM driver, persists
```

---

## Integration with God-Kaiser

### Configuration Workflow

1. User adds actuator in God-Kaiser UI
2. God-Kaiser validates actuator type and GPIO (client-side)
3. God-Kaiser publishes config to ESP via MQTT
   - Topic: `kaiser/{kaiser_id}/esp/{esp_id}/config`
   - Payload: JSON with `actuators` array
4. ESP receives and processes configuration
   - Validates fields
   - Checks GPIO conflicts
   - Creates and initializes driver
   - Registers actuator
   - Persists to NVS
5. ESP publishes response
   - Topic: `kaiser/{kaiser_id}/esp/{esp_id}/config_response`
   - Payload: Success or error details
6. God-Kaiser receives response and confirms in UI
7. Actuator immediately ready for commands
   - Can receive commands via `actuator/{gpio}/command` topic

### Update Workflow

1. User modifies actuator in God-Kaiser UI
2. God-Kaiser publishes updated config (same GPIO)
3. ESP detects existing actuator (runtime reconfiguration)
4. ESP stops existing actuator
5. ESP removes existing actuator
6. ESP creates new driver with updated config
7. ESP persists updated config to NVS
8. ESP publishes success response
9. Actuator continues operation with new config

### Removal Workflow

1. User deactivates actuator in God-Kaiser UI
2. God-Kaiser publishes config with `"active": false`
3. ESP detects deactivation flag
4. ESP stops actuator safely
5. ESP removes actuator from ActuatorManager
6. ESP persists remaining actuators to NVS
7. ESP publishes success response
8. Actuator stops accepting commands

---

## Related Components

### GPIOManager Integration

**Purpose:** Hardware safety and pin conflict prevention

**Methods Used:**
- `isPinAvailable(gpio)` - Check if GPIO free
- GPIO reservation handled by driver during `begin()`

**Conflict Prevention:**
- Prevents actuator on sensor GPIO
- Prevents multiple actuators on same GPIO
- Validates against reserved GPIOs (UART, Boot, etc.)

### SensorManager Integration

**Purpose:** Cross-component GPIO conflict detection

**Methods Used:**
- `hasSensorOnGPIO(gpio)` - Check if sensor uses GPIO

**Conflict Prevention:**
- Prevents actuator on sensor GPIO
- Ensures hardware safety

### StorageManager Integration

**Purpose:** NVS abstraction layer

**Namespace:** `actuator_config`

**Operations:**
- `beginNamespace("actuator_config", read_only)` - Open namespace
- `putUInt8(key, value)` - Store GPIO, aux_gpio, count, default_pwm
- `putString(key, value)` - Store type, name, subzone
- `putBool(key, value)` - Store active, critical, inverted, default_state flags
- `getUInt8(key, default)` - Read GPIO, aux_gpio, count, default_pwm
- `getStringObj(key, default)` - Read strings
- `getBool(key, default)` - Read booleans
- `endNamespace()` - Close namespace

### ErrorTracker Integration

**Errors Tracked:**
- `ERROR_ACTUATOR_INIT_FAILED` - Actuator configuration/driver failure
- `ERROR_GPIO_CONFLICT` - GPIO already in use
- `ERROR_ACTUATOR_NOT_FOUND` - Actuator missing (for commands)

**Severity:** ERROR level

### TopicBuilder Integration

**Topics Used:**
- `buildConfigTopic()` - Input topic
- `buildConfigResponseTopic()` - Response topic
- `buildActuatorStatusTopic(gpio)` - Status publish after config

**Dynamic Values:**
- `{kaiser_id}` - From global `g_kaiser.kaiser_id`
- `{esp_id}` - From `ConfigManager::getESPId()`

### Driver Integration

**Driver Lifecycle:**
1. Created via `createDriver(actuator_type)`
2. Initialized via `driver->begin(config)`
3. Config retrieved via `driver->getConfig()` (may modify config)
4. Stopped via `driver->setState(false)` before removal
5. Cleaned up via `driver->end()` before removal

**Driver Responsibilities:**
- GPIO reservation (during `begin()`)
- Hardware initialization
- State management
- Emergency stop handling

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

**Output:** Full actuator details, driver operations, GPIO conflicts

### Serial Monitor Example

**Successful Configuration:**
```
[INFO] MQTT message received: kaiser/god/esp/ESP_AB12CD/config
[INFO] Handling actuator configuration from MQTT
[DEBUG] Extracted GPIO: 5
[DEBUG] Actuator type: pump
[DEBUG] Actuator name: Water Pump 1
[INFO] Actuator Manager: Runtime reconfiguration on GPIO 5
[INFO]   Actuator type changed: relay → pump
[INFO]   Stopping actuator before removal
[INFO] Actuator Manager: Removing actuator on GPIO 5
[INFO]   ✅ Configuration persisted to NVS
[INFO] Actuator configured on GPIO 5 type: pump
[INFO]   ✅ Configuration persisted to NVS
[INFO] ConfigResponse published [actuator] status=success
```

**Error Example:**
```
[INFO] MQTT message received: kaiser/god/esp/ESP_AB12CD/config
[INFO] Handling actuator configuration from MQTT
[ERROR] GPIO 5 already used by sensor
[ERROR] ConfigResponse publish failed for topic: kaiser/god/esp/ESP_AB12CD/config_response
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
    "sensors": [],
    "actuators": [
      {
        "gpio": 5,
        "actuator_type": "pump",
        "actuator_name": "Test Pump",
        "subzone_id": "test_zone",
        "active": true,
        "critical": false,
        "inverted_logic": false,
        "default_state": false
      }
    ]
  }'
```

### NVS Inspection

**Using PlatformIO NVS Tool:**
```bash
pio run --target nvsmonitor
```

**Expected NVS Structure:**
```
Namespace: actuator_config
  actuator_count = 2
  actuator_0_gpio = 5
  actuator_0_aux_gpio = 255
  actuator_0_type = "pump"
  actuator_0_name = "Water Pump 1"
  actuator_0_subzone = "irrigation"
  actuator_0_active = true
  actuator_0_critical = false
  actuator_0_inverted = false
  actuator_0_default_state = false
  actuator_0_default_pwm = 0
  actuator_1_gpio = 18
  actuator_1_aux_gpio = 255
  actuator_1_type = "pwm"
  actuator_1_name = "Exhaust Fan"
  actuator_1_subzone = "ventilation"
  actuator_1_active = true
  actuator_1_critical = false
  actuator_1_inverted = false
  actuator_1_default_state = false
  actuator_1_default_pwm = 128
```

## Next Flows

→ [Actuator Command Flow](03-actuator-command-flow.md) - Control configured actuators  
→ [Error Recovery Flow](07-error-recovery-flow.md) - Emergency stop handling  
→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - Message dispatch  
→ [Boot Sequence](01-boot-sequence.md) - Actuator loading from NVS on startup  

---

**End of Runtime Actuator Configuration Flow Documentation**

