# Actuator Command Flow

## Overview

Complete actuator command reception, validation, execution, and status reporting flow. This demonstrates how El Trabajante receives commands from God-Kaiser via MQTT, validates safety requirements, controls physical actuators, and reports results.

## Files Analyzed

- `src/main.cpp` (lines 357-363) - MQTT callback actuator routing
- `src/services/actuator/actuator_manager.cpp` (lines 1-778) - Actuator management
- `src/services/actuator/actuator_manager.h` (lines 1-101) - Actuator manager interface
- `src/services/actuator/safety_controller.cpp` - Safety interlocks
- `src/services/actuator/safety_controller.h` (lines 1-51) - Safety controller interface
- `src/models/actuator_types.h` (lines 1-138) - Actuator data structures
- `src/services/actuator/actuator_drivers/iactuator_driver.h` - Driver interface
- `src/services/actuator/actuator_drivers/pump_actuator.cpp/.h` - Pump implementation
- `src/services/actuator/actuator_drivers/valve_actuator.cpp/.h` - Valve implementation
- `src/services/actuator/actuator_drivers/pwm_actuator.cpp/.h` - PWM implementation
- `src/utils/topic_builder.cpp` (lines 69-106) - Topic generation
- `src/services/communication/mqtt_client.cpp` - MQTT publishing with offline buffer

## Prerequisites

- Actuator Manager initialized (boot sequence Phase 5)
- At least one actuator configured
- MQTT client connected
- Safety Controller operational

## Trigger

MQTT message received on actuator command topic with wildcard subscription.

---

## MQTT Topics

### Command Topic (Subscribed)

**Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/+/command`

**Wildcard:** `+` matches any GPIO number

**Example:** `kaiser/god/esp/ESP_AB12CD/actuator/5/command`

### Response Topics (Published)

| Topic Pattern | Purpose |
|---------------|---------|
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response` | Command acknowledgment |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status` | Current actuator state |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert` | Safety alerts |

---

## Command Payload Format

```json
{
  "command": "ON",
  "value": 1.0,
  "duration": 0,
  "timestamp": 1234567890,
  "command_id": "cmd_abc123"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | String | Yes | Command type: ON, OFF, PWM, TOGGLE |
| `value` | Number | No | For PWM: 0.0-1.0, For binary: 0.0 or 1.0 |
| `duration` | Number | No | Duration in seconds (0 = indefinite). If > 0: actuator auto-switches OFF after N seconds (processActuatorLoops, F1 2026-03-11) |
| `timestamp` | Number | No | Unix timestamp |
| `command_id` | String | No | Unique command identifier |

---

## Flow Steps

### STEP 1: MQTT Message Reception

**File:** `src/main.cpp` (lines 357-363)

**Code:**

```cpp
// Actuator commands
String actuator_command_prefix = String(TopicBuilder::buildActuatorCommandTopic(0));
actuator_command_prefix.replace("/0/command", "/");
if (topic.startsWith(actuator_command_prefix)) {
  actuatorManager.handleActuatorCommand(topic, payload);
  return;
}
```

**Topic Matching:**
1. Build prefix: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/`
2. Check if incoming topic starts with prefix
3. If match → Route to ActuatorManager

**Example Match:**
- Subscription: `kaiser/god/esp/ESP_AB12CD/actuator/+/command`
- Incoming: `kaiser/god/esp/ESP_AB12CD/actuator/5/command`
- Result: ✅ Match → Handle command

---

### STEP 2: Extract GPIO from Topic

**File:** `src/services/actuator/actuator_manager.cpp` (lines 485-490)

**Code:**

```cpp
bool ActuatorManager::handleActuatorCommand(const String& topic, const String& payload) {
  uint8_t gpio = extractGPIOFromTopic(topic);
  if (gpio == 255) {
    LOG_ERROR("Invalid actuator command topic: " + topic);
    return false;
  }
  // ...
}
```

**GPIO Extraction Logic:**

**File:** `src/services/actuator/actuator_manager.cpp` (lines 467-483)

```cpp
uint8_t ActuatorManager::extractGPIOFromTopic(const String& topic) const {
  int actuator_idx = topic.indexOf("/actuator/");
  if (actuator_idx == -1) {
    return 255;
  }
  int gpio_start = actuator_idx + 10;
  int gpio_end = topic.indexOf('/', gpio_start);
  if (gpio_end == -1) {
    return 255;
  }
  String gpio_str = topic.substring(gpio_start, gpio_end);
  gpio_str.trim();
  if (gpio_str.length() == 0) {
    return 255;
  }
  return static_cast<uint8_t>(gpio_str.toInt());
}
```

**Example:**
- Topic: `kaiser/god/esp/ESP_AB12CD/actuator/5/command`
- Extracted GPIO: `5`

---

### STEP 3: Parse Command Payload

**File:** `src/services/actuator/actuator_manager.cpp` (lines 492-497)

**Code:**

```cpp
ActuatorCommand command;
command.gpio = gpio;
command.command = extractJSONString(payload, "command");
command.value = extractJSONFloat(payload, "value", 0.0f);
command.duration_s = extractJSONUInt32(payload, "duration", 0);
command.timestamp = millis();
```

**JSON Parsing:**

Uses lightweight string parsing (not ArduinoJson) for performance:

```cpp
String extractJSONString(const String& json, const String& key) {
  String pattern = "\"" + key + "\":";
  int key_pos = json.indexOf(pattern);
  if (key_pos == -1) {
    return "";
  }
  // ... extract value between quotes or until comma/}
  return value;
}
```

**Parsed Command Structure:**

```cpp
struct ActuatorCommand {
  uint8_t gpio = 255;
  String command = "";        // "ON","OFF","PWM","TOGGLE","STOP"
  float value = 0.0f;         // 0.0 - 1.0 (PWM) or binary (>=0.5)
  uint32_t duration_s = 0;    // Optional hold duration
  unsigned long timestamp = 0;
};
```

---

### STEP 4: Command Routing

**File:** `src/services/actuator/actuator_manager.cpp` (lines 499-513)

**Code:**

```cpp
bool success = false;
if (command.command.equalsIgnoreCase("ON")) {
  success = controlActuatorBinary(gpio, true);
} else if (command.command.equalsIgnoreCase("OFF")) {
  success = controlActuatorBinary(gpio, false);
} else if (command.command.equalsIgnoreCase("PWM")) {
  success = controlActuator(gpio, command.value);
} else if (command.command.equalsIgnoreCase("TOGGLE")) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (actuator) {
    success = controlActuatorBinary(gpio, !actuator->config.current_state);
  }
} else {
  LOG_ERROR("Unknown actuator command: " + command.command);
}
```

### Supported Commands

| Command | Description | Value Range | Actuator Types |
|---------|-------------|-------------|----------------|
| `ON` | Turn on | Ignored | Pump, Valve, Relay |
| `OFF` | Turn off | Ignored | Pump, Valve, Relay |
| `PWM` | Set PWM | 0.0 - 1.0 | PWM |
| `TOGGLE` | Toggle state | Ignored | Pump, Valve, Relay |

---

### STEP 4b: Duration Auto-Off (ON with duration > 0)

When `command` is `ON` and `duration_s > 0`, the ActuatorManager stores `command_duration_end_ms = millis() + (duration_s * 1000)` in `RegisteredActuator`. Each loop iteration, `processActuatorLoops()` checks: if `millis() >= command_duration_end_ms` and actuator is ON, it calls `controlActuatorBinary(gpio, false)` and clears the timer. This implements RuleConfigPanel "Auto-Abschaltung (Sek.)" behavior. Duration 0 = no auto-off (only device-level `runtime_protection.max_runtime_ms` applies).

**Rule vs. Device:** The `duration` in the MQTT payload comes from the **Rule-Action** (`duration_seconds`), not from ActuatorConfig. Device `max_runtime_ms` is sent via Config-Push (`safety_constraints.max_runtime` in seconds → converted to ms, SAFETY-P1 Mechanism C, 2026-03-30). Default: 3600000ms (1h). See `.claude/reference/logic/MAX_RUNTIME_ABGRENZUNG.md` for full documentation.

**File:** `src/services/actuator/actuator_manager.cpp` (handleActuatorCommand, processActuatorLoops)

---

### STEP 5a: Binary Control (ON/OFF)

**File:** `src/services/actuator/actuator_manager.cpp` (lines 371-388)

**Code:**

```cpp
bool ActuatorManager::controlActuatorBinary(uint8_t gpio, bool state) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    return false;
  }

  if (actuator->emergency_stopped) {
    LOG_WARNING("Actuator GPIO " + String(gpio) + " is emergency stopped");
    return false;
  }

  bool success = actuator->driver->setBinary(state);
  actuator->config = actuator->driver->getConfig();
  if (success) {
    publishActuatorStatus(gpio);
  }
  return success;
}
```

**Safety Checks:**
1. Actuator exists and has driver
2. Not in emergency stop state
3. Driver executes command via `setBinary()`

**State Update:**
- Driver updates `config.current_state` internally
- Driver updates `config.last_command_ts` internally
- Driver tracks `accumulated_runtime_ms` (for pumps)
- Status published automatically on success

---

### STEP 5b: PWM Control

**File:** `src/services/actuator/actuator_manager.cpp` (lines 337-369)

**Code:**

```cpp
bool ActuatorManager::controlActuator(uint8_t gpio, float value) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    LOG_ERROR("controlActuator: actuator not found on GPIO " + String(gpio));
    errorTracker.trackError(ERROR_ACTUATOR_NOT_FOUND,
                            ERROR_SEVERITY_ERROR,
                            "Actuator missing");
    return false;
  }

  if (actuator->emergency_stopped) {
    LOG_WARNING("Actuator GPIO " + String(gpio) + " is emergency stopped");
    return false;
  }

  float normalized_value = value;
  if (isPwmActuatorType(actuator->config.actuator_type)) {
    normalized_value = constrain(value, 0.0f, 1.0f);
  } else if (!validateActuatorValue(actuator->config.actuator_type, value)) {
    LOG_ERROR("Actuator value out of range for GPIO " + String(gpio));
    errorTracker.trackError(ERROR_COMMAND_INVALID,
                            ERROR_SEVERITY_ERROR,
                            "Actuator value invalid");
    return false;
  }

  bool success = actuator->driver->setValue(normalized_value);
  actuator->config = actuator->driver->getConfig();
  if (success) {
    publishActuatorStatus(gpio);
  }
  return success;
}
```

**Value Validation:**
- PWM actuators: Constrained to 0.0 - 1.0
- Binary actuators: Validated via `validateActuatorValue()` helper
- Driver handles conversion internally

**Driver Processing:**
- PWM actuators: Convert 0.0-1.0 to 0-255 internally
- Binary actuators: Treat >=0.5 as ON, <0.5 as OFF
- Valve actuators: Map 0.0-1.0 to 3 positions (0, 1, 2)

**Examples:**
- PWM: 0.0 → 0% duty, 0.5 → 50% duty, 1.0 → 100% duty
- Binary: 0.0 → OFF, 0.5+ → ON
- Valve: 0.0-0.33 → Position 0, 0.33-0.66 → Position 1, 0.66-1.0 → Position 2

---

### STEP 6: Driver Execution

**Actuator Driver Interface:**

**File:** `src/services/actuator/actuator_drivers/iactuator_driver.h` (lines 10-32)

```cpp
class IActuatorDriver {
public:
  virtual ~IActuatorDriver() = default;

  // Lifecycle
  virtual bool begin(const ActuatorConfig& config) = 0;
  virtual void end() = 0;
  virtual bool isInitialized() const = 0;

  // Control operations
  virtual bool setValue(float normalized_value) = 0;  // 0.0 - 1.0
  virtual bool setBinary(bool state) = 0;             // true = ON/OPEN

  // Safety
  virtual bool emergencyStop(const String& reason) = 0;
  virtual bool clearEmergency() = 0;
  virtual void loop() = 0;  // Optional periodic processing

  // Status
  virtual ActuatorStatus getStatus() const = 0;
  virtual const ActuatorConfig& getConfig() const = 0;
  virtual String getType() const = 0;
};
```

### Driver Implementations

#### Pump Actuator (Binary)

**File:** `src/services/actuator/actuator_drivers/pump_actuator.cpp` (lines 88-149)

```cpp
bool PumpActuator::setValue(float normalized_value) {
  bool desired_state = normalized_value >= 0.5f;
  return setBinary(desired_state);
}

bool PumpActuator::setBinary(bool state) {
  return applyState(state, false);
}

bool PumpActuator::applyState(bool state, bool force) {
  if (!initialized_) {
    LOG_ERROR("PumpActuator::applyState called before init");
    return false;
  }

  if (!force && emergency_stopped_) {
    LOG_WARNING("PumpActuator: command ignored, emergency active");
    return false;
  }

  if (state && !force && !canActivate()) {
    LOG_WARNING("PumpActuator: runtime protection prevented activation on GPIO " + String(gpio_));
    errorTracker.trackError(ERROR_ACTUATOR_SET_FAILED,
                            ERROR_SEVERITY_WARNING,
                            "Pump runtime protection triggered");
    return false;
  }

  if (state == running_) {
    return true;
  }

  int level = state ? HIGH : LOW;
  if (config_.inverted_logic) {
    level = (level == HIGH) ? LOW : HIGH;
  }

  digitalWrite(gpio_, level);

  unsigned long now = millis();
  if (state) {
    activation_start_ms_ = now;
    recordActivation(now);
  } else if (activation_start_ms_ != 0) {
    accumulated_runtime_ms_ += now - activation_start_ms_;
    config_.accumulated_runtime_ms = accumulated_runtime_ms_;
    activation_start_ms_ = 0;
    last_stop_ms_ = now;
  }

  running_ = state;
  config_.current_state = state;
  config_.current_pwm = state ? 255 : 0;
  config_.last_command_ts = now;

  LOG_INFO("PumpActuator GPIO " + String(gpio_) + (state ? " ON" : " OFF"));
  return true;
}
```

**Runtime Protection:**

**File:** `src/services/actuator/actuator_drivers/pump_actuator.cpp` (lines 163-190)

```cpp
bool PumpActuator::canActivate() const {
  if (!initialized_) {
    return false;
  }

  unsigned long now = millis();

  // Check cooldown after max runtime
  if (accumulated_runtime_ms_ >= protection_.max_runtime_ms && last_stop_ms_ != 0) {
    unsigned long since_stop = now - last_stop_ms_;
    if (since_stop < protection_.cooldown_ms) {
      return false;
    }
  }

  // Check activation frequency limit
  unsigned long window_start = now - protection_.activation_window_ms;
  uint16_t activations_in_window = 0;
  for (uint8_t i = 0; i < ACTIVATION_HISTORY; i++) {
    if (activation_timestamps_[i] >= window_start && activation_timestamps_[i] != 0) {
      activations_in_window++;
    }
  }

  if (activations_in_window >= protection_.max_activations_per_hour) {
    return false;
  }

  return true;
}
```

**Hardware:** Simple GPIO HIGH/LOW control with inverted logic support

**Runtime Protection Parameters:**
- `max_runtime_ms`: Maximum continuous runtime (default: 3600000ms = 1 hour)
- `max_activations_per_hour`: Maximum activations per hour (default: 60)
- `cooldown_ms`: Cooldown period after max runtime (default: 30000ms = 30s)
- `activation_window_ms`: Time window for activation counting (default: 3600000ms = 1 hour)

---

#### Valve Actuator (Position Control with 2 GPIOs)

**File:** `src/services/actuator/actuator_drivers/valve_actuator.cpp` (lines 112-196)

```cpp
bool ValveActuator::setValue(float normalized_value) {
  if (!initialized_) {
    LOG_ERROR("ValveActuator::setValue before init");
    return false;
  }

  if (emergency_stopped_) {
    LOG_WARNING("ValveActuator: command ignored, emergency active");
    return false;
  }

  normalized_value = constrain(normalized_value, 0.0f, 1.0f);
  uint8_t target = 0;
  if (normalized_value >= 0.66f) {
    target = kMaxValvePosition;  // Position 2 (fully open)
  } else if (normalized_value >= 0.33f) {
    target = kValveMidPosition;  // Position 1 (mid)
  }
  // else target = 0 (closed)

  return moveToPosition(target);
}

bool ValveActuator::setBinary(bool state) {
  return moveToPosition(state ? kMaxValvePosition : 0);
}

bool ValveActuator::moveToPosition(uint8_t target_pos) {
  if (!initialized_) {
    return false;
  }

  if (target_pos > kMaxValvePosition) {
    target_pos = kMaxValvePosition;
  }

  if (target_pos == current_position_ && !is_moving_) {
    return true;
  }

  int8_t delta = static_cast<int8_t>(target_pos) - static_cast<int8_t>(current_position_);
  if (delta == 0) {
    target_position_ = target_pos;
    stopMovement();
    current_position_ = target_pos;
    config_.current_state = current_position_ > 0;
    config_.current_pwm = current_position_ * 127;
    return true;
  }

  uint32_t half_transition = transition_time_ms_ / 2;
  move_duration_ms_ = static_cast<uint32_t>(abs(delta)) * half_transition;
  if (move_duration_ms_ == 0) {
    move_duration_ms_ = half_transition;
  }

  applyDirection(delta);
  digitalWrite(enable_pin_, HIGH);
  is_moving_ = true;
  emergency_stopped_ = false;
  move_start_ms_ = millis();
  target_position_ = target_pos;

  LOG_INFO("ValveActuator moving from " + String(current_position_) +
           " to " + String(target_position_) + " (" + String(move_duration_ms_) + "ms)");
  return true;
}
```

**Hardware:** Dual GPIO (direction + enable) for stepper/latching valve control

**Position Mapping:**
- 0.0 - 0.33: Position 0 (closed)
- 0.33 - 0.66: Position 1 (mid)
- 0.66 - 1.0: Position 2 (fully open)

**Movement:** Asynchronous - `loop()` method completes movement after `move_duration_ms_`

---

#### PWM Actuator (Variable Speed)

**File:** `src/services/actuator/actuator_drivers/pwm_actuator.cpp` (lines 74-126)

```cpp
bool PWMActuator::setValue(float normalized_value) {
  if (!initialized_) {
    LOG_ERROR("PWMActuator::setValue before init");
    return false;
  }

  if (emergency_stopped_) {
    LOG_WARNING("PWMActuator command ignored, emergency active");
    return false;
  }

  if (!validateActuatorValue(ActuatorTypeTokens::PWM, normalized_value)) {
    LOG_ERROR("PWMActuator: invalid value " + String(normalized_value));
    errorTracker.trackError(ERROR_COMMAND_INVALID,
                            ERROR_SEVERITY_ERROR,
                            "PWMActuator value invalid");
    return false;
  }

  normalized_value = constrain(normalized_value, 0.0f, 1.0f);
  uint8_t pwm_value = static_cast<uint8_t>(normalized_value * 255.0f);
  return applyValue(pwm_value);
}

bool PWMActuator::setBinary(bool state) {
  return setValue(state ? 1.0f : 0.0f);
}

bool PWMActuator::applyValue(uint8_t pwm_value, bool force_publish) {
  if (!initialized_ || pwm_channel_ == 255) {
    return false;
  }

  float percent = (pwm_value / 255.0f) * 100.0f;
  if (!pwmController.writePercent(pwm_channel_, percent)) {
    LOG_ERROR("PWMActuator: writePercent failed on channel " + String(pwm_channel_));
    errorTracker.trackError(ERROR_PWM_SET_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "PWMActuator write failed");
    return false;
  }

  pwm_value_ = pwm_value;
  config_.current_pwm = pwm_value;
  config_.current_state = pwm_value > 0;
  if (force_publish) {
    config_.last_command_ts = millis();
  }

  LOG_INFO("PWMActuator channel " + String(pwm_channel_) +
           " value set to " + String(pwm_value));
  return true;
}
```

**Hardware:** ESP32 LEDC PWM peripheral via PWMController abstraction

**PWM Conversion:**
- Input: 0.0 - 1.0 (normalized float)
- Internal: 0 - 255 (uint8_t)
- Hardware: 0 - 100% via `pwmController.writePercent()`

---

### STEP 7: Publish Response

**File:** `src/services/actuator/actuator_manager.cpp` (lines 515-520)

**Code:**

```cpp
publishActuatorResponse(command,
                        success,
                        success ? "Command executed" : "Command failed");
if (success) {
  publishActuatorStatus(gpio);
}
```

**Response Payload Builder:**

**File:** `src/services/actuator/actuator_manager.cpp` (lines 737-756)

```cpp
String ActuatorManager::buildResponsePayload(const ActuatorCommand& command,
                                             bool success,
                                             const String& message) const {
  // Phase 7: Get zone information from global variables
  extern KaiserZone g_kaiser;
  extern SystemConfig g_system_config;
  
  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
  payload += "\"ts\":" + String(millis()) + ",";
  payload += "\"gpio\":" + String(command.gpio) + ",";
  payload += "\"command\":\"" + command.command + "\",";
  payload += "\"value\":" + String(command.value, 3) + ",";
  payload += "\"duration\":" + String(command.duration_s) + ",";
  payload += "\"success\":" + String(success ? "true" : "false") + ",";
  payload += "\"message\":\"" + message + "\"";
  payload += "}";
  return payload;
}
```

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response`

**File:** `src/utils/topic_builder.cpp` (lines 85-90)

**Response Payload:**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "ts": 1234567890,
  "gpio": 5,
  "command": "ON",
  "value": 1.0,
  "duration": 0,
  "success": true,
  "message": "Command executed"
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `esp_id` | String | ESP32 unique identifier |
| `zone_id` | String | Hierarchical zone assignment (Phase 7) |
| `ts` | Number | Milliseconds since boot (not Unix timestamp) |
| `gpio` | Number | GPIO pin number |
| `command` | String | Command type executed |
| `value` | Number | Value sent (3 decimal places) |
| `duration` | Number | Duration in seconds (if specified) |
| `success` | Boolean | Command execution result |
| `message` | String | Human-readable status message |

**QoS:** 1 (at least once)

**Publishing:**

**File:** `src/services/actuator/actuator_manager.cpp` (lines 758-764)

```cpp
void ActuatorManager::publishActuatorResponse(const ActuatorCommand& command,
                                              bool success,
                                              const String& message) {
  const char* topic = TopicBuilder::buildActuatorResponseTopic(command.gpio);
  String payload = buildResponsePayload(command, success, message);
  mqttClient.safePublish(String(topic), payload, 1);
}
```

**Note:** Uses `safePublish()` which includes retry logic and circuit breaker protection

---

### STEP 8: Publish Status

**File:** `src/services/actuator/actuator_manager.cpp` (lines 716-727)

**Code:**

```cpp
void ActuatorManager::publishActuatorStatus(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    return;
  }

  ActuatorStatus status = actuator->driver->getStatus();
  actuator->config = actuator->driver->getConfig();
  String payload = buildStatusPayload(status, actuator->config);
  const char* topic = TopicBuilder::buildActuatorStatusTopic(gpio);
  mqttClient.safePublish(String(topic), payload, 1);
}
```

**Status Payload Builder:**

**File:** `src/services/actuator/actuator_manager.cpp` (lines 696-714)

```cpp
String ActuatorManager::buildStatusPayload(const ActuatorStatus& status, const ActuatorConfig& config) const {
  // Phase 7: Get zone information from global variables (extern from main.cpp)
  extern KaiserZone g_kaiser;
  extern SystemConfig g_system_config;
  
  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
  payload += "\"subzone_id\":\"" + config.subzone_id + "\",";
  payload += "\"ts\":" + String(millis()) + ",";
  payload += "\"gpio\":" + String(status.gpio) + ",";
  payload += "\"type\":\"" + config.actuator_type + "\",";
  payload += "\"state\":" + String(status.current_state ? "true" : "false") + ",";
  payload += "\"pwm\":" + String(status.current_pwm) + ",";
  payload += "\"runtime_ms\":" + String(status.runtime_ms) + ",";
  payload += "\"emergency\":\"" + String(emergencyStateToString(status.emergency_state)) + "\"";
  payload += "}";
  return payload;
}
```

**Status Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status`

**File:** `src/utils/topic_builder.cpp` (lines 77-82)

**Status Payload:**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "subzone_id": "section_A",
  "ts": 1234567890,
  "gpio": 5,
  "type": "pump",
  "state": true,
  "pwm": 0,
  "runtime_ms": 123456,
  "emergency": "normal"
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `esp_id` | String | ESP32 unique identifier |
| `zone_id` | String | Hierarchical zone assignment (Phase 7) |
| `subzone_id` | String | Actuator-specific subzone |
| `ts` | Number | Milliseconds since boot |
| `gpio` | Number | GPIO pin number |
| `type` | String | Actuator type (pump, valve, pwm, relay) |
| `state` | Boolean | Current ON/OFF state |
| `pwm` | Number | Current PWM value (0-255) |
| `runtime_ms` | Number | Accumulated runtime in milliseconds |
| `emergency` | String | Emergency state: "normal", "active", "clearing", "resuming" |

**Publish Frequency:**
- After every successful command execution (with `command_source` field set to issuer)
- Post-reconnect: `publishAllActuatorStatus()` broadcasts all actuator states once (50ms stagger between actuators)
- After emergency stop/clear operations

---

## Complete Flow Sequence Diagram

```
MQTT Message Received on actuator command topic
  │
  ├─► main.cpp: MQTT callback (line 345)
  │     ├─► Topic starts with actuator command prefix?
  │     └─► YES → actuatorManager.handleActuatorCommand(topic, payload)
  │
  ├─► STEP 1: Extract GPIO from topic
  │     └─► extractGPIOFromTopic() (line 467)
  │           ├─► Find "/actuator/" position
  │           ├─► Extract GPIO number
  │           └─► GPIO == 255? → ERROR, return false
  │
  ├─► STEP 2: Parse JSON payload
  │     ├─► extractJSONString("command") (line 494)
  │     ├─► extractJSONFloat("value", 0.0) (line 495)
  │     └─► extractJSONUInt32("duration", 0) (line 496)
  │
  ├─► STEP 3: Command routing (lines 499-513)
  │     ├─► "ON" → controlActuatorBinary(gpio, true)
  │     ├─► "OFF" → controlActuatorBinary(gpio, false)
  │     ├─► "PWM" → controlActuator(gpio, value)
  │     └─► "TOGGLE" → controlActuatorBinary(gpio, !current_state)
  │
  ├─► STEP 4: Safety checks
  │     ├─► Actuator exists? (findActuator())
  │     ├─► Emergency stop active? (emergency_stopped flag)
  │     └─► Runtime protection? (canActivate() for pumps)
  │
  ├─► STEP 5: Driver execution
  │     ├─► Binary: driver->setBinary(state)
  │     │     ├─► Pump: applyState() → digitalWrite() + runtime tracking
  │     │     ├─► Valve: moveToPosition() → GPIO control + async movement
  │     │     └─► PWM: setValue() → setBinary() → applyValue()
  │     │
  │     └─► PWM: driver->setValue(normalized_value)
  │           └─► PWM: applyValue() → pwmController.writePercent()
  │
  ├─► STEP 6: State update
  │     └─► actuator->config = driver->getConfig()
  │
  ├─► STEP 7: Publish response (lines 515-520)
  │     ├─► buildResponsePayload() (line 737)
  │     ├─► Topic: kaiser/.../actuator/{gpio}/response
  │     └─► mqttClient.safePublish() (line 763)
  │
  └─► STEP 8: Publish status (if success)
        ├─► driver->getStatus()
        ├─► buildStatusPayload() (line 696)
        ├─► Topic: kaiser/.../actuator/{gpio}/status
        └─► mqttClient.safePublish() (line 726)
```

**Error Paths:**

```
Command Failure
  │
  ├─► Actuator not found → ERROR response, no status publish
  ├─► Emergency stop active → ERROR response, alert published
  ├─► Runtime protection → ERROR response, alert published
  ├─► Driver failure → ERROR response, error tracked
  └─► MQTT publish failure → Command executed locally, buffered for retry
```

---

## Safety Mechanisms

### Emergency Stop Check

**Every command** checks emergency stop status:

```cpp
if (actuator->emergency_stopped) {
  LOG_WARNING("Actuator GPIO " + String(gpio) + " is emergency stopped");
  publishActuatorAlert(gpio, "emergency_stop", "Actuator under emergency stop");
  return false;
}
```

**Emergency Stop Sources:**
1. ESP-specific emergency: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency`
2. Broadcast emergency: `kaiser/broadcast/emergency`
3. SafetyController manual trigger

---

### GPIO Conflict Detection

**Before configuration:**

```cpp
if (!gpio_manager_->isPinAvailable(config.gpio)) {
  LOG_ERROR("ActuatorManager: GPIO " + String(config.gpio) + " not available");
  return false;
}
```

**Prevents:**
- Multiple actuators on same GPIO
- Actuator on sensor GPIO
- Actuator on reserved GPIO (UART, Boot, etc.)

---

### Runtime Protection

**Pump Runtime Protection:**

**File:** `src/services/actuator/actuator_drivers/pump_actuator.h` (lines 10-15)

```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;      // 1h continuous runtime cap
  uint16_t max_activations_per_hour = 60;        // Duty-cycle protection
  unsigned long cooldown_ms = 30000UL;           // 30s cooldown after cutoff
  unsigned long activation_window_ms = 3600000UL;
};
```

**Protection Logic:**

**File:** `src/services/actuator/actuator_drivers/pump_actuator.cpp` (lines 163-190)

The `canActivate()` method checks:
1. **Cooldown Check:** If max runtime reached, enforce cooldown period
2. **Activation Frequency:** Limit activations per hour (sliding window)
3. **History Tracking:** Maintains last 60 activation timestamps

**Behavior:**
- Protection checked **before** activation (not during runtime)
- If protection triggered → Command rejected, alert published
- Protection parameters configurable via `setRuntimeProtection()`
- **Non-blocking:** Other actuators unaffected

**Note:** Runtime protection is **hardware safety** (prevents overheating/wear), not business logic. Documented in `docs/ZZZ.md` as "Server-Centric Pragmatic Deviations".

---

## Error Handling

### Command Failures

**Causes:**
- Actuator not configured
- GPIO not available
- Driver initialization failed
- Emergency stop active
- Invalid command/value

**Behavior:**
1. Log error
2. Track via ErrorTracker
3. Publish error response
4. **Do not crash** - continue operation

**Error Response Example:**

```json
{
  "esp_id": "ESP_AB12CD",
  "gpio": 5,
  "command": "ON",
  "value": 1.0,
  "success": false,
  "message": "Actuator not found",
  "timestamp": 1234567890
}
```

---

### Driver Failures

**Hardware Issues:**
- GPIO write failure (rare)
- PWM channel not available
- Valve pulse timeout

**Recovery:**
1. Retry once (immediate)
2. If still failing → Mark actuator error state
3. Publish alert
4. Continue with other actuators

---

### MQTT Publish Failures

**Behavior:**
- Log warning
- Track error
- **Command still executed** locally
- Retry on next status publish cycle

**Offline Buffer:** Response/status messages buffered if broker unavailable

**File:** `src/services/communication/mqtt_client.cpp` (lines 257-303)

The MQTT client includes offline buffering:
- Max 100 messages buffered
- Automatically flushed when connection restored
- Uses `safePublish()` for retry logic with circuit breaker protection

---

## Performance Metrics

### Command Processing Time

| Operation | Duration |
|-----------|----------|
| Topic parsing | <1ms |
| JSON parsing | 1-5ms |
| Safety checks | <1ms |
| GPIO write | <1µs |
| PWM write | ~10µs |
| Response publish | 10-20ms |
| Status publish | 10-20ms |

**Total:** 20-50ms per command

---

### Throughput

**Tested:** 100 commands/second per actuator

**Practical:** 10-20 commands/second typical

**Limit:** MQTT QoS 1 + network latency

---

## Memory Usage

### Per Command

| Allocation | Size |
|------------|------|
| ActuatorCommand struct | ~48 bytes |
| JSON parsing buffers | ~256 bytes |
| Response payload | ~256 bytes |
| Status payload | ~384 bytes |

**Total:** ~950 bytes per command (stack, temporary)

---

### Per Actuator

| Allocation | Size |
|------------|------|
| ActuatorConfig | ~128 bytes |
| Driver instance | ~64 bytes |
| RegisteredActuator | ~200 bytes |

**Total:** ~400 bytes per actuator

**Max Actuators:**
- ESP32 WROOM: 12 actuators
- XIAO ESP32C3: 8 actuators

**Total Memory:** ~4.8KB (12 actuators)

---

## Integration with God-Kaiser

### Command Flow (God-Kaiser → ESP)

```
User/Automation → God-Kaiser → MQTT Broker → ESP32 → Actuator
```

### Status Flow (ESP → God-Kaiser)

```
Actuator → ESP32 → MQTT Broker → God-Kaiser → Database/UI
```

### Automation Example

**Scenario:** Turn on irrigation pump based on soil moisture

1. ESP publishes soil moisture sensor reading
2. God-Kaiser receives sensor data
3. God-Kaiser automation rule triggered (moisture < 30%)
4. God-Kaiser publishes pump ON command
5. ESP receives command
6. ESP validates and executes
7. ESP publishes response + status
8. God-Kaiser confirms pump is running

---

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

**Output:** Full command details, driver operations

### Serial Monitor Example

```
[INFO] MQTT message received: kaiser/god/esp/ESP_AB12CD/actuator/5/command
[DEBUG] Payload: {"command":"ON","value":1.0}
[DEBUG] Extracted GPIO: 5
[DEBUG] Command: ON
[DEBUG] Actuator found: Pump (GPIO 5)
[DEBUG] Emergency stop: inactive
[DEBUG] Executing: digitalWrite(5, HIGH)
[INFO] Actuator GPIO 5 set to ON
[INFO] Published response: kaiser/god/esp/ESP_AB12CD/actuator/5/response
[INFO] Published status: kaiser/god/esp/ESP_AB12CD/actuator/5/status
```

### MQTT Monitoring

**Subscribe to all actuator topics:**

```bash
mosquitto_sub -h 192.168.0.198 -p 8883 -t "kaiser/+/esp/+/actuator/#" -v
```

---

## Common Issues

### Command Not Executed

**Symptoms:** Response shows `success: false`

**Diagnosis:**
1. Check emergency stop status
2. Verify actuator configured
3. Check GPIO availability
4. Enable debug logging

**Solutions:**
- Clear emergency stop
- Configure actuator via MQTT
- Verify GPIO wiring

---

### Actuator Not Responding

**Symptoms:** Command succeeds but actuator doesn't activate

**Diagnosis:**
1. Check physical wiring
2. Check GPIO pin number
3. Check inverted logic setting
4. Test with multimeter

**Solutions:**
- Verify connections
- Check power supply
- Reconfigure with correct GPIO/invert

---

### Slow Command Response

**Symptoms:** Delays between command and execution

**Diagnosis:**
1. Check network latency
2. Check MQTT QoS settings
3. Check WiFi signal strength

**Solutions:**
- Move closer to access point
- Reduce QoS to 0 (testing only)
- Check broker load

---

## Next Flows

From actuator commands:

→ [Runtime Actuator Config Flow](05-runtime-actuator-config-flow.md) - For adding/modifying actuators  
→ [Error Recovery Flow](07-error-recovery-flow.md) - For emergency stop handling  
→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - For message dispatch  

---

## Related Documentation

- [Boot Sequence](01-boot-sequence.md) - Actuator Manager initialization
- `docs/API_REFERENCE.md` - ActuatorManager API
- `src/models/actuator_types.h` - Actuator data structures
- `src/services/actuator/safety_controller.h` - Safety system
- `.claude/reference/logic/MAX_RUNTIME_ABGRENZUNG.md` - Rule duration vs. Device max_runtime

---

**End of Actuator Command Flow Documentation**

