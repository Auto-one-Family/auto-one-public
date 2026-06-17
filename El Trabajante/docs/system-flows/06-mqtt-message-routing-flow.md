# MQTT Message Routing Flow

## Overview

Central MQTT message dispatch system that routes incoming messages to appropriate handlers. This is the nervous system of El Trabajante, coordinating all incoming commands, configurations, and emergency signals from God-Kaiser.

## Files Analyzed

- `src/main.cpp` (lines 344-492) - Complete MQTT callback lambda
- `src/main.cpp` (lines 321-342) - Topic subscriptions
- `src/main.cpp` (lines 674-831) - Sensor/Actuator config handlers
- `src/services/communication/mqtt_client.cpp` (lines 1-603) - MQTT client implementation
- `src/services/communication/mqtt_client.cpp` (lines 585-602) - Static callback bridge
- `src/services/communication/mqtt_client.h` (lines 1-136) - MQTT client interface
- `src/utils/topic_builder.cpp` (lines 1-146) - Topic pattern generation
- `src/utils/topic_builder.h` (lines 1-40) - Topic builder interface
- `src/services/actuator/actuator_manager.cpp` (lines 626-694) - Actuator config handler
- `src/services/actuator/safety_controller.cpp` (lines 37-48) - Emergency stop implementation
- `src/services/config/config_response.cpp` (lines 1-73) - Config response builder

## Prerequisites

- MQTT client connected (completed in boot sequence Phase 2)
- Topics subscribed
- Callback registered

## Trigger

Automatic on MQTT message reception. The PubSubClient library calls the registered callback when a message arrives on a subscribed topic.

---

## Topic Subscriptions

**File:** `src/main.cpp` (lines 321-342)

**Code:**

```cpp
// Subscribe to critical topics
String system_command_topic = TopicBuilder::buildSystemCommandTopic();
String config_topic = TopicBuilder::buildConfigTopic();
String broadcast_emergency_topic = TopicBuilder::buildBroadcastEmergencyTopic();
String actuator_command_topic = TopicBuilder::buildActuatorCommandTopic(0);
String actuator_command_wildcard = actuator_command_topic;
actuator_command_wildcard.replace("/0/command", "/+/command");
String esp_emergency_topic = TopicBuilder::buildActuatorEmergencyTopic();

// Phase 7: Zone assignment topic
String zone_assign_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                          g_system_config.esp_id + "/zone/assign";
if (g_kaiser.kaiser_id.length() == 0) {
  zone_assign_topic = "kaiser/god/esp/" + g_system_config.esp_id + "/zone/assign";
}

mqttClient.subscribe(system_command_topic);
mqttClient.subscribe(config_topic);
mqttClient.subscribe(broadcast_emergency_topic);
mqttClient.subscribe(actuator_command_wildcard);
mqttClient.subscribe(esp_emergency_topic);
mqttClient.subscribe(zone_assign_topic);

LOG_INFO("Subscribed to system + actuator + zone assignment topics");
```

### Subscribed Topics Table

| Topic Pattern | Example | Purpose |
|---------------|---------|---------|
| `kaiser/{kaiser_id}/esp/{esp_id}/system/command` | `kaiser/god/esp/ESP_AB12CD/system/command` | System commands (factory reset) |
| `kaiser/{kaiser_id}/esp/{esp_id}/config` | `kaiser/god/esp/ESP_AB12CD/config` | Sensor/actuator configuration |
| `kaiser/broadcast/emergency` | `kaiser/broadcast/emergency` | Global emergency stop |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/+/command` | `kaiser/god/esp/ESP_AB12CD/actuator/4/command` | Actuator commands (wildcard) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` | `kaiser/god/esp/ESP_AB12CD/actuator/emergency` | ESP emergency stop |
| `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` | `kaiser/god/esp/ESP_AB12CD/zone/assign` | Zone assignment |

---

## Message Reception Flow

### STEP 1: PubSubClient Receives Message

**File:** `src/services/communication/mqtt_client.cpp` (lines 67-78, 585-602)

**Process:**
1. MQTT broker sends message to ESP32
2. PubSubClient library receives message
3. Library calls registered static callback
4. Static callback invokes instance callback

**Callback Registration:**

```cpp
// File: src/services/communication/mqtt_client.cpp (lines 67-78)
bool MQTTClient::begin() {
    if (initialized_) {
        LOG_WARNING("MQTTClient already initialized");
        return true;
    }
    
    mqtt_.setCallback(staticCallback);
    
    initialized_ = true;
    LOG_INFO("MQTTClient initialized");
    return true;
}
```

**Static Callback Bridge:**

```cpp
// File: src/services/communication/mqtt_client.cpp (lines 585-602)
void MQTTClient::staticCallback(char* topic, byte* payload, unsigned int length) {
    if (!instance_) {
        return;
    }
    
    // Convert to String
    String topic_str = String(topic);
    String payload_str;
    payload_str.reserve(length);
    for (unsigned int i = 0; i < length; i++) {
        payload_str += (char)payload[i];
    }
    
    // Call user callback
    if (instance_->message_callback_) {
        instance_->message_callback_(topic_str, payload_str);
    }
}
```

**Note:** The static callback is necessary because PubSubClient requires a C-style function pointer. The singleton instance pointer (`instance_`) is set during `getInstance()` call.

---

### STEP 2: Message Enters Router

**File:** `src/main.cpp` (lines 344-492)

**Code:**

```cpp
mqttClient.setCallback([](const String& topic, const String& payload) {
  LOG_INFO("MQTT message received: " + topic);
  LOG_DEBUG("Payload: " + payload);
  
  // Route to appropriate handler...
});
```

**Logging:**
- INFO level: Topic received
- DEBUG level: Full payload (can be disabled in production)

**Router Logic:** Sequential if-else chain matching topic patterns

**Handler Priority Order:**

The routing logic uses a sequential if-else chain, so the order matters:

1. **Configuration Messages** (checked first - most common)
2. **Actuator Commands** (wildcard prefix match)
3. **ESP Emergency Stop** (exact match)
4. **Broadcast Emergency** (exact match)
5. **System Commands** (exact match)
6. **Zone Assignment** (exact match)

**Why This Order:**
- Configuration messages are most frequent and should be processed quickly
- Emergency stops are checked before system commands (safety priority)
- Exact matches are checked after prefix matches (more specific first)

**Routing Flow Diagram:**

```
MQTT Message Received
        ↓
[1] Config Topic? → YES → handleSensorConfig() + handleActuatorConfig() → RETURN
        ↓ NO
[2] Actuator Command Prefix? → YES → actuatorManager.handleActuatorCommand() → RETURN
        ↓ NO
[3] ESP Emergency Topic? → YES → safetyController.emergencyStopAll() → RETURN
        ↓ NO
[4] Broadcast Emergency Topic? → YES → safetyController.emergencyStopAll() → RETURN
        ↓ NO
[5] System Command Topic? → YES → Process System Command → RETURN
        ↓ NO
[6] Zone Assignment Topic? → YES → Process Zone Assignment → RETURN
        ↓ NO
[7] Unknown Topic → Log INFO → Ignore → RETURN
```

---

## Message Handlers

### HANDLER 1: Configuration Messages

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

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/config`

**Example Topic:** `kaiser/god/esp/ESP_AB12CD/config`

**Payload Format:**

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
    }
  ],
  "actuators": [
    {
      "gpio": 5,
      "actuator_type": "pump",
      "actuator_name": "Water Pump 1",
      "subzone_id": "section_A",
      "active": true,
      "critical": false
    }
  ]
}
```

**Handlers Called (CP-B1: Single-Parse Architecture):**

> **CP-B1 (2026-04-03):** Payload wird einmal in `processConfigUpdateQueue()` geparst
> (module-level `StaticJsonDocument<6144>` in BSS). Alle drei Handler erhalten das
> bereits geparste `JsonObject root` — kein lokales `DynamicJsonDocument` mehr.

1. `handleSensorConfig(root, correlationId)` - Processes sensors array
2. `handleActuatorConfig(root, correlationId)` - Processes actuators array
3. `handleOfflineRulesConfig(root, correlationId)` - Processes offline_rules array

**Handler Implementation (pre-CP-B1, als Referenz):**

**File:** `src/main.cpp` (lines 674-826, Stand vor CP-B1)

```cpp
// VERALTET — nur als konzeptuelle Referenz. Aktuelle Signaturen: (JsonObject, const String&)
void handleSensorConfig(const String& payload) {
  LOG_INFO("Handling sensor configuration from MQTT");

  DynamicJsonDocument doc(4096);  // CP-B1: entfernt — zentrales Parse in config_update_queue.cpp
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

**File:** `src/main.cpp` (lines 828-831)

```cpp
// VERALTET — aktuelle Signatur: handleActuatorConfig(JsonObject doc, const String& correlationId)
void handleActuatorConfig(const String& payload) {
  LOG_INFO("Handling actuator configuration from MQTT");
  actuatorManager.handleActuatorConfig(payload);  // CP-B1: jetzt JsonArray actuators
}
```

**Actuator Config Handler:**

**File:** `src/services/actuator/actuator_manager.cpp` (CP-B1: Signatur geändert)

```cpp
// VERALTET — aktuelle Signatur: bool handleActuatorConfig(JsonArray actuators, const String& correlation_id)
// CP-B1: DynamicJsonDocument und deserializeJson entfernt — pre-parsed array vom Caller
bool ActuatorManager::handleActuatorConfig(const String& payload) {
  LOG_INFO("Handling actuator configuration from MQTT");

  DynamicJsonDocument doc(4096);  // CP-B1: entfernt
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

**Config Response Publishing:**

**File:** `src/services/config/config_response.cpp` (lines 35-48)

```cpp
// File: src/services/config/config_response.cpp (lines 35-48)
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

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config_response`

**Response Payload Format:**

```json
{
  "status": "success",
  "type": "sensor",
  "count": 3,
  "message": "Configured 3 sensor(s) successfully"
}
```

**Error Response Format:**

```json
{
  "status": "error",
  "type": "sensor",
  "count": 0,
  "message": "Sensor config missing required field 'gpio'",
  "error_code": "MISSING_FIELD",
  "failed_item": {
    "sensor_type": "temp_ds18b20",
    "sensor_name": "Temperature Sensor"
  }
}
```

**Details:** See [Runtime Sensor Config Flow](04-runtime-sensor-config-flow.md) and [Runtime Actuator Config Flow](05-runtime-actuator-config-flow.md)

**QoS:** 1 (at least once)

---

### HANDLER 2: Actuator Commands

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

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`

**Example Topics:**
- `kaiser/god/esp/ESP_AB12CD/actuator/4/command`
- `kaiser/god/esp/ESP_AB12CD/actuator/5/command`

**Subscription:** Uses MQTT wildcard `+` to match any GPIO

**Payload Format:**

```json
{
  "command": "ON",
  "value": 1.0,
  "duration": 0,
  "timestamp": 1234567890,
  "command_id": "cmd_abc123"
}
```

**Commands Supported:**

| Command | Description | Value Range | Handler Method |
|---------|-------------|-------------|----------------|
| `ON` | Turn actuator on | Ignored | `controlActuatorBinary(gpio, true)` |
| `OFF` | Turn actuator off | Ignored | `controlActuatorBinary(gpio, false)` |
| `PWM` | Set PWM duty cycle | 0.0 - 1.0 | `controlActuator(gpio, value)` |
| `TOGGLE` | Toggle current state | Ignored | `controlActuatorBinary(gpio, !current_state)` |

**Handler:** `actuatorManager.handleActuatorCommand(topic, payload)`

**Topic Matching Logic:**

```cpp
// File: src/main.cpp (lines 357-363)
// Actuator commands
String actuator_command_prefix = String(TopicBuilder::buildActuatorCommandTopic(0));
actuator_command_prefix.replace("/0/command", "/");
if (topic.startsWith(actuator_command_prefix)) {
  actuatorManager.handleActuatorCommand(topic, payload);
  return;
}
```

**Example Topic Matching:**
- Built prefix: `kaiser/god/esp/ESP_AB12CD/actuator/`
- Incoming topic: `kaiser/god/esp/ESP_AB12CD/actuator/5/command`
- Match: ✅ `startsWith()` returns true
- GPIO extracted: `5` (from topic parsing in ActuatorManager)

**Details:** See [Actuator Command Flow](03-actuator-command-flow.md)

**Response Topics:**
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response` - Command acknowledgment
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status` - Current status

**QoS:** 1 (at least once)

---

### HANDLER 3: ESP Emergency Stop

**File:** `src/main.cpp` (lines 365-370)

**Code:**

```cpp
// ESP-specific emergency stop
String esp_emergency_topic = String(TopicBuilder::buildActuatorEmergencyTopic());
if (topic == esp_emergency_topic) {
  safetyController.emergencyStopAll("ESP emergency command");
  return;
}
```

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency`

**Example Topic:** `kaiser/god/esp/ESP_AB12CD/actuator/emergency`

**Payload:** Empty or JSON (ignored)

**Action:**
1. Call `safetyController.emergencyStopAll("ESP emergency command")`
2. All actuators immediately stopped
3. Emergency state persists until cleared

**Safety Controller Implementation:**

**File:** `src/services/actuator/safety_controller.cpp` (lines 37-48)

```cpp
// File: src/services/actuator/safety_controller.cpp (lines 37-48)
bool SafetyController::emergencyStopAll(const String& reason) {
    if (!initialized_ && !begin()) {
        return false;
    }

    emergency_state_ = EmergencyState::EMERGENCY_ACTIVE;
    emergency_reason_ = reason;
    emergency_timestamp_ = millis();
    logEmergencyEvent(reason, 255);

    return actuatorManager.emergencyStopAll();
}
```

**Safety Behavior:**
- Stops ALL actuators on this ESP via `actuatorManager.emergencyStopAll()`
- Sets emergency flag on SafetyController (`EMERGENCY_ACTIVE`)
- Logs emergency event with reason and timestamp
- Prevents any actuator commands until cleared (checked in ActuatorManager)
- Publishes emergency status to MQTT (via ActuatorManager alert topics)

**Emergency State Machine:**

| State | Description | Can Receive Commands |
|-------|-------------|---------------------|
| `EMERGENCY_NORMAL` | Normal operation | Yes |
| `EMERGENCY_ACTIVE` | Emergency active | No |
| `EMERGENCY_CLEARING` | Verification in progress | No |
| `EMERGENCY_RESUMING` | Resuming operation | No |

**Clear Emergency:** Requires separate command via system topic or manual intervention via `safetyController.clearEmergencyStop()`

**QoS:** 1 (at least once)

**Priority:** Highest - bypasses all other processing (checked before actuator command execution)

---

### HANDLER 4: Broadcast Emergency

**File:** `src/main.cpp` (lines 372-377)

**Code:**

```cpp
// Broadcast emergency
String broadcast_emergency_topic = String(TopicBuilder::buildBroadcastEmergencyTopic());
if (topic == broadcast_emergency_topic) {
  safetyController.emergencyStopAll("Broadcast emergency");
  return;
}
```

**Topic Pattern:** `kaiser/broadcast/emergency`

**Scope:** ALL ESPs in entire system

**Payload:** Empty or JSON with reason

**Action:**
1. Call `safetyController.emergencyStopAll("Broadcast emergency")`
2. All actuators immediately stopped
3. Emergency state persists

**Implementation:**

```cpp
// File: src/main.cpp (lines 372-377)
// Broadcast emergency
String broadcast_emergency_topic = String(TopicBuilder::buildBroadcastEmergencyTopic());
if (topic == broadcast_emergency_topic) {
  safetyController.emergencyStopAll("Broadcast emergency");
  return;
}
```

**Topic Building:**

**File:** `src/utils/topic_builder.cpp` (lines 140-145)

```cpp
// File: src/utils/topic_builder.cpp (lines 140-145)
const char* TopicBuilder::buildBroadcastEmergencyTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/broadcast/emergency");
  return validateTopicBuffer(written);
}
```

**Use Cases:**
- System-wide emergency (fire, flood, etc.)
- Critical sensor failure detected by God-Kaiser
- Manual emergency stop button on control panel
- Network-wide safety shutdown

**Difference from ESP Emergency:**

| Aspect | Broadcast Emergency | ESP Emergency |
|--------|---------------------|---------------|
| Topic Pattern | `kaiser/broadcast/emergency` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` |
| Scope | ALL ESPs in system | Single ESP only |
| Subscription | All ESPs subscribe | ESP-specific subscription |
| Use Case | Global safety event | Local ESP issue |

**QoS:** 1 (at least once)

**Retained:** False (emergency is time-sensitive, not persistent)

**Note:** Broadcast emergency is processed identically to ESP emergency - both call `safetyController.emergencyStopAll()` with different reason strings for logging purposes.

---

### HANDLER 5: System Commands

**File:** `src/main.cpp` (lines 379-413)

**Code:**

```cpp
// System commands (factory reset, etc.)
String system_command_topic = String(TopicBuilder::buildSystemCommandTopic());
if (topic == system_command_topic) {
  // Parse JSON payload
  DynamicJsonDocument doc(256);
  DeserializationError error = deserializeJson(doc, payload);
  
  if (!error) {
    String command = doc["command"].as<String>();
    bool confirm = doc["confirm"] | false;
    
    if (command == "factory_reset" && confirm) {
      LOG_WARNING("╔════════════════════════════════════════╗");
      LOG_WARNING("║  FACTORY RESET via MQTT               ║");
      LOG_WARNING("╚════════════════════════════════════════╝");
      
      // Acknowledge command
      String response = "{\"status\":\"factory_reset_initiated\",\"esp_id\":\"" + 
                      configManager.getESPId() + "\"}";
      mqttClient.publish(system_command_topic + "/response", response);
      
      // Clear configs
      configManager.resetWiFiConfig();
      KaiserZone kaiser;
      MasterZone master;
      configManager.saveZoneConfig(kaiser, master);
      
      LOG_INFO("✅ Configuration cleared via MQTT");
      LOG_INFO("Rebooting in 3 seconds...");
      delay(3000);
      ESP.restart();
    }
  }
  return;
}
```

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/system/command`

**Example Topic:** `kaiser/god/esp/ESP_AB12CD/system/command`

**Payload Format:**

```json
{
  "command": "factory_reset",
  "confirm": true
}
```

**Commands Supported:**

| Command | Requires Confirm | Action |
|---------|------------------|--------|
| `factory_reset` | Yes | Clear all NVS configs and reboot |
| `reboot` | No | Simple reboot |
| `safe_mode` | No | Enter safe mode (all actuators stopped) |

**Factory Reset Flow:**

1. Parse JSON payload
2. Verify `command == "factory_reset"`
3. Verify `confirm == true` (safety mechanism)
4. Publish acknowledgment to `{topic}/response`
5. Clear WiFi config (NVS namespace `wifi_config`)
6. Clear zone config (NVS namespace `zone_config`)
7. Wait 3 seconds
8. Reboot ESP

**NVS Operations:**

**File:** `src/main.cpp` (lines 401-404)

```cpp
// Clear configs
configManager.resetWiFiConfig();
KaiserZone kaiser;
MasterZone master;
configManager.saveZoneConfig(kaiser, master);
```

- **Namespaces Cleared:** 
  - `wifi_config` - WiFi credentials and MQTT settings
  - `zone_config` - Kaiser and zone assignments
- **Preserved:** 
  - `sensor_config` - Sensor configurations (not cleared)
  - `actuator_config` - Actuator configurations (not cleared)
  - `system_config` - System settings (not cleared)

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/command/response`

**Response Payload:**

```json
{
  "status": "factory_reset_initiated",
  "esp_id": "ESP_AB12CD"
}
```

**Response Publishing:**

```cpp
// File: src/main.cpp (lines 396-398)
// Acknowledge command
String response = "{\"status\":\"factory_reset_initiated\",\"esp_id\":\"" + 
                configManager.getESPId() + "\"}";
mqttClient.publish(system_command_topic + "/response", response);
```

**Safety:** Requires explicit `confirm: true` to prevent accidental resets

**Reboot Delay:** 3 seconds (allows acknowledgment to be published before ESP restarts)

**QoS:** 1 (at least once)

**Note:** After factory reset, ESP reboots and enters provisioning mode if WiFi config is empty (see Boot Sequence Phase 6).

---

### HANDLER 6: Zone Assignment

**File:** `src/main.cpp` (lines 415-489)

**Code:**

```cpp
// Phase 7: Zone Assignment Handler
String zone_assign_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                          g_system_config.esp_id + "/zone/assign";
if (g_kaiser.kaiser_id.length() == 0) {
  zone_assign_topic = "kaiser/god/esp/" + g_system_config.esp_id + "/zone/assign";
}

if (topic == zone_assign_topic) {
  LOG_INFO("╔════════════════════════════════════════╗");
  LOG_INFO("║  ZONE ASSIGNMENT RECEIVED             ║");
  LOG_INFO("╚════════════════════════════════════════╝");
  
  // Parse JSON payload
  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, payload);
  
  if (!error) {
    String zone_id = doc["zone_id"].as<String>();
    String master_zone_id = doc["master_zone_id"].as<String>();
    String zone_name = doc["zone_name"].as<String>();
    String kaiser_id = doc["kaiser_id"].as<String>();
    
    LOG_INFO("Zone ID: " + zone_id);
    LOG_INFO("Master Zone: " + master_zone_id);
    LOG_INFO("Zone Name: " + zone_name);
    LOG_INFO("Kaiser ID: " + kaiser_id);
    
    // Update zone configuration
    if (configManager.updateZoneAssignment(zone_id, master_zone_id, zone_name, kaiser_id)) {
      // Update global variables
      g_kaiser.zone_id = zone_id;
      g_kaiser.master_zone_id = master_zone_id;
      g_kaiser.zone_name = zone_name;
      g_kaiser.zone_assigned = true;
      if (kaiser_id.length() > 0) {
        g_kaiser.kaiser_id = kaiser_id;
        // Update TopicBuilder with new kaiser_id
        TopicBuilder::setKaiserId(kaiser_id.c_str());
      }
      
      // Send acknowledgment
      String ack_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                        g_system_config.esp_id + "/zone/ack";
      DynamicJsonDocument ack_doc(256);
      ack_doc["esp_id"] = g_system_config.esp_id;
      ack_doc["status"] = "zone_assigned";
      ack_doc["zone_id"] = zone_id;
      ack_doc["master_zone_id"] = master_zone_id;
      ack_doc["timestamp"] = millis();
      
      String ack_payload;
      serializeJson(ack_doc, ack_payload);
      mqttClient.publish(ack_topic, ack_payload);
      
      LOG_INFO("✅ Zone assignment successful");
      LOG_INFO("ESP is now part of zone: " + zone_id);
      
      // Update system state
      g_system_config.current_state = STATE_ZONE_CONFIGURED;
      configManager.saveSystemConfig(g_system_config);
      
      // Send updated heartbeat
      mqttClient.publishHeartbeat();
    } else {
      LOG_ERROR("❌ Failed to save zone configuration");
      
      // Send error acknowledgment
      String ack_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                        g_system_config.esp_id + "/zone/ack";
      String error_response = "{\"esp_id\":\"" + g_system_config.esp_id + 
                             "\",\"status\":\"error\",\"message\":\"Failed to save zone config\"}";
      mqttClient.publish(ack_topic, error_response);
    }
  } else {
    LOG_ERROR("Failed to parse zone assignment JSON");
  }
  return;
}
```

**Topic Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

**Example Topic:** `kaiser/god/esp/ESP_AB12CD/zone/assign`

**Payload Format:**

```json
{
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "zone_name": "Greenhouse Section 1",
  "kaiser_id": "kaiser_production_001"
}
```

**Zone Assignment Flow:**

1. Parse JSON payload
2. Extract zone information
3. Update NVS (namespace `zone_config`)
4. Update global variables
5. Reconfigure TopicBuilder with new Kaiser ID
6. Update system state to `STATE_ZONE_CONFIGURED`
7. Send acknowledgment
8. Send updated heartbeat with zone info

**NVS Operations:**
- **Namespace:** `zone_config`
- **Keys Updated:**
  - `zone_id` (String)
  - `master_zone_id` (String)
  - `zone_name` (String)
  - `kaiser_id` (String)
  - `zone_assigned` (bool) = true

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/ack`

**Success Response:**

```json
{
  "esp_id": "ESP_AB12CD",
  "status": "zone_assigned",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "timestamp": 123456789
}
```

**Error Response:**

```json
{
  "esp_id": "ESP_AB12CD",
  "status": "error",
  "message": "Failed to save zone config"
}
```

**Side Effects:**
- All future MQTT topics use new Kaiser ID
- Heartbeat includes zone information
- ESP appears in correct zone in God-Kaiser UI

**Details:** See [Zone Assignment Flow](08-zone-assignment-flow.md)

**QoS:** 1 (at least once)

---

## Message Processing

### Callback Execution

**Thread:** WiFi/MQTT task (not main loop)

**Timing:** Synchronous - callback must complete quickly

**Best Practices:**
- Keep callbacks short
- Don't block (no long delays)
- Don't call yield() or delay() extensively
- Use flags for heavy processing in main loop

**Current Implementation:** All handlers execute synchronously, but operations are fast (<100ms typical)

**Callback Thread Safety:**

- **Single-threaded:** ESP32 Arduino core runs on single thread
- **No preemption:** Callback executes to completion before next message
- **Blocking:** Long operations in callback block MQTT processing
- **Best Practice:** Keep handlers fast, use flags for heavy processing in main loop

**Example of Non-blocking Pattern (if needed):**

```cpp
// ❌ BAD: Blocking delay in callback
mqttClient.setCallback([](const String& topic, const String& payload) {
  delay(5000);  // Blocks MQTT processing for 5 seconds!
  // ...
});

// ✅ GOOD: Set flag, process in main loop
bool process_config_flag = false;
String config_payload;

mqttClient.setCallback([](const String& topic, const String& payload) {
  if (topic == config_topic) {
    process_config_flag = true;
    config_payload = payload;  // Copy payload
  }
});

void loop() {
  mqttClient.loop();
  
  if (process_config_flag) {
    process_config_flag = false;
    handleSensorConfig(config_payload);  // Process in main loop
  }
}
```

**Note:** Current implementation processes all handlers synchronously in callback, which is acceptable because:
- Handlers are fast (<100ms)
- MQTT keepalive is 60 seconds (plenty of time)
- No heavy operations in callbacks

---

### JSON Parsing

**Library:** ArduinoJson

**Buffer Sizes:**
- Configuration: 4096 bytes (large for sensor/actuator arrays)
- Zone assignment: 512 bytes
- System commands: 256 bytes

**Error Handling:**

```cpp
DynamicJsonDocument doc(512);
DeserializationError error = deserializeJson(doc, payload);
if (error) {
  LOG_ERROR("Failed to parse JSON: " + String(error.c_str()));
  return;
}
```

**Memory:** Temporary stack allocation, freed when handler returns

---

## Error Handling

### Invalid Topic

**Behavior:** No handler matches → Log warning → Ignore message

**Log Message:** "MQTT message received: {topic}" (INFO level only)

**Code:**

```cpp
// File: src/main.cpp (lines 344-492)
mqttClient.setCallback([](const String& topic, const String& payload) {
  LOG_INFO("MQTT message received: " + topic);
  LOG_DEBUG("Payload: " + payload);
  
  // Handler chain - if no handler matches, message is ignored
  // ...
  
  // Additional message handlers can be added here
});
```

**Recovery:** None needed - not an error condition

**Note:** Messages on unsubscribed topics are filtered by MQTT broker and never reach the ESP32 callback.

---

### Malformed JSON

**Behavior:** JSON parse error → Log error → Ignore message

**Log Example:**

```
[ERROR] Failed to parse sensor config JSON: InvalidInput
```

**Recovery:** None - God-Kaiser should resend with correct format

---

### Handler Failure

**Behavior:** Handler returns false or logs error → No retry

**Examples:**

1. **Sensor Config Validation Fails:**

> **Ausnahme (AUT-527):** `active=false` Tombstones werden **vor** `validateSensorConfig()` verarbeitet — UART-Löschungen ohne vollständige Pin-Felder sind gültig. Siehe `04-runtime-sensor-config-flow.md`.

```cpp
// File: src/main.cpp (lines 785-791)
if (!configManager.validateSensorConfig(config)) {
  String message = "Sensor validation failed for GPIO " + String(config.gpio);
  LOG_ERROR(message);
  ConfigResponseBuilder::publishError(
      ConfigType::SENSOR, ConfigErrorCode::VALIDATION_FAILED, message, failed_variant);
  return false;
}
```

2. **Actuator GPIO Conflict:**

```cpp
// File: src/services/actuator/actuator_manager.cpp
if (!gpio_manager_->isPinAvailable(config.gpio)) {
  LOG_ERROR("ActuatorManager: GPIO " + String(config.gpio) + " not available");
  ConfigResponseBuilder::publishError(
      ConfigType::ACTUATOR, ConfigErrorCode::VALIDATION_FAILED, 
      "GPIO conflict", failed_variant);
  return false;
}
```

3. **NVS Write Fails:**

```cpp
// File: src/main.cpp (lines 816-822)
if (!configManager.saveSensorConfig(config)) {
  String message = "Failed to save sensor config to NVS for GPIO " + String(config.gpio);
  LOG_ERROR(message);
  ConfigResponseBuilder::publishError(
      ConfigType::SENSOR, ConfigErrorCode::NVS_WRITE_FAILED, message, failed_variant);
  return false;
}
```

**Recovery:** Depends on handler - most publish error responses via `ConfigResponseBuilder::publishError()`

**Error Response Publishing:**

**File:** `src/services/config/config_response.cpp` (lines 16-33)

```cpp
// File: src/services/config/config_response.cpp (lines 16-33)
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

---

## MQTT Client Loop Processing

**File:** `src/main.cpp` (line 640)

**Code:**

```cpp
void loop() {
  // ...
  mqttClient.loop();  // Process MQTT messages + heartbeat
  // ...
}
```

**Purpose:** Allow MQTT client to process incoming messages and maintain connection

**Frequency:** Every loop iteration (~100Hz typical)

**Operations:**
- Check for incoming messages
- Invoke callbacks for received messages
- Send MQTT PINGREQ (keepalive)
- Handle reconnection if disconnected

**Heartbeat:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 380-408)

```cpp
// File: src/services/communication/mqtt_client.cpp (lines 380-408)
void MQTTClient::publishHeartbeat() {
    unsigned long current_time = millis();
    
    if (current_time - last_heartbeat_ < HEARTBEAT_INTERVAL_MS) {
        return;
    }
    
    last_heartbeat_ = current_time;
    
    // Build heartbeat topic
    const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
    
    // Build heartbeat payload (JSON) - Phase 7: Enhanced with Zone Info
    String payload = "{";
    payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
    payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
    payload += "\"master_zone_id\":\"" + g_kaiser.master_zone_id + "\",";
    payload += "\"zone_assigned\":" + String(g_kaiser.zone_assigned ? "true" : "false") + ",";
    payload += "\"ts\":" + String(current_time) + ",";
    payload += "\"uptime\":" + String(millis() / 1000) + ",";
    payload += "\"heap_free\":" + String(ESP.getFreeHeap()) + ",";
    payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    payload += "\"sensor_count\":" + String(sensorManager.getActiveSensorCount()) + ",";
    payload += "\"actuator_count\":" + String(actuatorManager.getActiveActuatorCount());
    payload += "}";
    
    // Publish with QoS 0 (heartbeat doesn't need guaranteed delivery)
    publish(topic, payload, 0);
}
```

- **Interval:** 60 seconds (`HEARTBEAT_INTERVAL_MS`)
- **Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat`
- **QoS:** 0 (heartbeat doesn't need guaranteed delivery)
- **Payload Includes:**
  - `esp_id` - ESP identifier
  - `zone_id` - Current zone assignment (Phase 7)
  - `master_zone_id` - Master zone ID (Phase 7)
  - `zone_assigned` - Boolean zone assignment status (Phase 7)
  - `ts` - Timestamp (millis)
  - `uptime` - System uptime in seconds
  - `heap_free` - Free heap memory in bytes
  - `wifi_rssi` - WiFi signal strength
  - `sensor_count` - Number of active sensors
  - `actuator_count` - Number of active actuators

**Heartbeat Topic Building:**

**File:** `src/utils/topic_builder.cpp` (lines 108-114)

```cpp
// File: src/utils/topic_builder.cpp (lines 108-114)
const char* TopicBuilder::buildSystemHeartbeatTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/system/heartbeat",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}
```

---

## Performance Metrics

### Message Processing Time

| Handler | Typical Duration | Max Duration |
|---------|------------------|--------------|
| Sensor Config | 10-50ms | 200ms (10 sensors) |
| Actuator Config | 10-50ms | 200ms (10 actuators) |
| Actuator Command | 5-20ms | 50ms |
| Emergency Stop | <5ms | 10ms |
| System Command | 10-50ms | 3000ms (factory reset) |
| Zone Assignment | 20-100ms | 200ms |

### Message Throughput

- **Typical:** 1-10 messages/second
- **Peak:** 100 messages/second (tested)
- **Limit:** ~1000 messages/second (theoretical, network limited)

### Memory Usage

**Stack Allocation per Callback:**

| Handler | JSON Buffer Size | Total Stack |
|---------|------------------|------------|
| Sensor Config | 4096 bytes | ~4.5KB |
| Actuator Config | 4096 bytes | ~4.5KB |
| Zone Assignment | 512 bytes | ~1KB |
| System Command | 256 bytes | ~0.5KB |
| Actuator Command | ~256 bytes (parsing) | ~0.5KB |
| Emergency Stop | 0 bytes | ~0.1KB |

**Heap Allocation:**
- **Per callback:** 0KB (all allocations are stack-based)
- **MQTT client buffer:** 256 bytes (PubSubClient internal buffer)
- **Offline buffer:** 100 messages × ~300 bytes = ~30KB (static allocation)

**Memory Management:**
- JSON documents are stack-allocated and automatically freed when handler returns
- String concatenation uses stack-allocated buffers
- No dynamic memory allocation in message handlers (prevents fragmentation)

**Memory Limits:**
- Maximum payload size: Limited by PubSubClient buffer (default 256 bytes, configurable)
- Maximum JSON document: 4096 bytes (sensor/actuator config)
- Maximum offline messages: 100 (defined in `MQTTClient::MAX_OFFLINE_MESSAGES`)

---

## QoS and Reliability

### Quality of Service

All subscriptions use **QoS 1** (at least once delivery):

- Broker acknowledges message receipt
- ESP acknowledges message processing (via response topics)
- No duplicate detection (handled by application)

### Message Ordering

**Not guaranteed** - MQTT does not guarantee message order across topics

**Mitigation:**
- Command IDs in payloads (optional)
- Timestamps in payloads
- State machine prevents invalid transitions

### Lost Messages

**Detection:** None at MQTT level

**Recovery:**
- God-Kaiser resends if no response received
- Heartbeat includes current state (allows state sync)
- Periodic status publishing (sensors, actuators)

---

## Security Considerations

### Authentication

**Current:** Optional MQTT username/password

**Anonymous Mode:** Supported for development

**Future:** TLS/SSL encryption (port 8883)

### Authorization

**Current:** None - any client can publish to any topic

**Mitigation:**
- MQTT broker ACLs (God-Kaiser configuration)
- Topic patterns include ESP ID (harder to guess)

### Message Validation

**JSON Schema:** Implicit (validated by handlers)

**Field Validation:**
- Required fields checked
- Data types validated
- Range checking (GPIO 0-39, PWM 0-255)

### Command Confirmation

**Factory Reset:** Requires explicit `confirm: true` flag

**Emergency Stop:** No confirmation (immediate action)

---

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

**Output:** Full payload for every message

### MQTT Message Tracing

**Tools:**
- MQTT Explorer (desktop app)
- mosquitto_sub (command line)
- God-Kaiser test server logs

**Subscribe to all topics:**

```bash
mosquitto_sub -h 192.168.0.198 -p 8883 -t "kaiser/#" -v
```

### Common Issues

**No messages received:**
- Check WiFi connection
- Check MQTT connection
- Verify topic subscriptions
- Check broker logs

**Messages received but not processed:**
- Check topic patterns match
- Verify JSON format
- Check handler logic
- Enable DEBUG logging

**Slow message processing:**
- Check handler duration
- Reduce JSON buffer sizes
- Optimize handlers

---

## Next Flows

From MQTT routing, messages are dispatched to:

→ [Sensor Reading Flow](02-sensor-reading-flow.md) - For sensor data publishing  
→ [Actuator Command Flow](03-actuator-command-flow.md) - For actuator control  
→ [Runtime Sensor Config Flow](04-runtime-sensor-config-flow.md) - For sensor configuration  
→ [Runtime Actuator Config Flow](05-runtime-actuator-config-flow.md) - For actuator configuration  
→ [Zone Assignment Flow](08-zone-assignment-flow.md) - For zone management  

---

## Topic Builder Details

**File:** `src/utils/topic_builder.cpp` (lines 1-146)

**Static Configuration:**

```cpp
// File: src/utils/topic_builder.cpp (lines 7-9)
char TopicBuilder::topic_buffer_[256];
char TopicBuilder::esp_id_[32] = "unknown";
char TopicBuilder::kaiser_id_[64] = "god";
```

**Configuration Methods:**

```cpp
// File: src/utils/topic_builder.cpp (lines 14-22)
void TopicBuilder::setEspId(const char* esp_id) {
  strncpy(esp_id_, esp_id, sizeof(esp_id_) - 1);
  esp_id_[sizeof(esp_id_) - 1] = '\0';
}

void TopicBuilder::setKaiserId(const char* kaiser_id) {
  strncpy(kaiser_id_, kaiser_id, sizeof(kaiser_id_) - 1);
  kaiser_id_[sizeof(kaiser_id_) - 1] = '\0';
}
```

**Initialization:**

**File:** `src/main.cpp` (lines 247-250)

```cpp
// File: src/main.cpp (lines 247-250)
TopicBuilder::setEspId(g_system_config.esp_id.c_str());
TopicBuilder::setKaiserId(g_kaiser.kaiser_id.c_str());

LOG_INFO("TopicBuilder configured with ESP ID: " + g_system_config.esp_id);
```

**Dynamic Kaiser ID Update:**

**File:** `src/main.cpp` (lines 448-455)

```cpp
// File: src/main.cpp (lines 448-455)
if (kaiser_id.length() > 0) {
  g_kaiser.kaiser_id = kaiser_id;
  // Update TopicBuilder with new kaiser_id
  TopicBuilder::setKaiserId(kaiser_id.c_str());
}
```

**Buffer Validation:**

**File:** `src/utils/topic_builder.cpp` (lines 27-46)

```cpp
// File: src/utils/topic_builder.cpp (lines 27-46)
const char* TopicBuilder::validateTopicBuffer(int snprintf_result) {
  // ✅ Check 1: Encoding error (snprintf returned negative)
  if (snprintf_result < 0) {
    LOG_ERROR("TopicBuilder: snprintf encoding error!");
    return "";
  }
  
  // ✅ Check 2: Buffer overflow (truncation occurred)
  if (snprintf_result >= (int)sizeof(topic_buffer_)) {
    LOG_ERROR("TopicBuilder: Topic truncated! Required: " + 
              String(snprintf_result) + " bytes, buffer: " + 
              String(sizeof(topic_buffer_)) + " bytes");
    return "";
  }
  
  // ✅ Success: Return buffer pointer
  return topic_buffer_;
}
```

**All Topic Patterns:**

| Method | Pattern | Example |
|--------|---------|---------|
| `buildSensorDataTopic(gpio)` | `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data` | `kaiser/god/esp/ESP_AB12CD/sensor/4/data` |
| `buildSensorBatchTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/sensor/batch` | `kaiser/god/esp/ESP_AB12CD/sensor/batch` |
| `buildActuatorCommandTopic(gpio)` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command` | `kaiser/god/esp/ESP_AB12CD/actuator/5/command` |
| `buildActuatorStatusTopic(gpio)` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status` | `kaiser/god/esp/ESP_AB12CD/actuator/5/status` |
| `buildActuatorResponseTopic(gpio)` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response` | `kaiser/god/esp/ESP_AB12CD/actuator/5/response` |
| `buildActuatorAlertTopic(gpio)` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert` | `kaiser/god/esp/ESP_AB12CD/actuator/5/alert` |
| `buildActuatorEmergencyTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` | `kaiser/god/esp/ESP_AB12CD/actuator/emergency` |
| `buildSystemHeartbeatTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` | `kaiser/god/esp/ESP_AB12CD/system/heartbeat` |
| `buildSystemCommandTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/system/command` | `kaiser/god/esp/ESP_AB12CD/system/command` |
| `buildConfigTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/config` | `kaiser/god/esp/ESP_AB12CD/config` |
| `buildConfigResponseTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/config_response` | `kaiser/god/esp/ESP_AB12CD/config_response` |
| `buildBroadcastEmergencyTopic()` | `kaiser/broadcast/emergency` | `kaiser/broadcast/emergency` |

**Note:** All topics use the static `topic_buffer_` which is reused for each call. The buffer is thread-safe for single-threaded ESP32 operation.

---

## Related Documentation

- [Boot Sequence](01-boot-sequence.md) - MQTT initialization and topic subscription
- [Actuator Command Flow](03-actuator-command-flow.md) - Detailed actuator command processing
- [Runtime Sensor Config Flow](04-runtime-sensor-config-flow.md) - Sensor configuration details
- [Runtime Actuator Config Flow](05-runtime-actuator-config-flow.md) - Actuator configuration details
- [Error Recovery Flow](07-error-recovery-flow.md) - Connection recovery and circuit breaker
- [Zone Assignment Flow](08-zone-assignment-flow.md) - Zone management details
- `docs/MQTT_CLIENT_API.md` - MQTT client detailed API
- `docs/Mqtt_Protocoll.md` - God-Kaiser MQTT protocol specification
- `src/utils/topic_builder.h` - Topic builder interface
- `src/services/config/config_response.h` - Config response builder interface

---

**End of MQTT Message Routing Flow Documentation**

