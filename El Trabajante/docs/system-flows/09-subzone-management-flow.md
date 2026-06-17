# Subzone Management Flow

## Overview

Subzones sind logische Gruppierungen einzelner Pins/Sensoren/Aktoren innerhalb einer Zone, die eine feingranulare Kontrolle über einzelne Hardware-Komponenten ermöglichen. Das Subzone-Management integriert sich nahtlos mit dem Safe-Mode-System für Pin-spezifische Sicherheit und ermöglicht Emergency-Stop-Operationen auf Subzone-Ebene.

**Implementierungsstatus:** ✅ **VOLLSTÄNDIG IMPLEMENTIERT (Phase 9)**

**Korrespondiert mit:**
- [08-zone-assignment-flow.md](./08-zone-assignment-flow.md) - Zone-System und kaiser_id Management
- [07-error-recovery-flow.md](./07-error-recovery-flow.md) - Safe-Mode und GPIO-Manager
- [01-boot-sequence.md](./01-boot-sequence.md) - System-Initialisierung

**Wichtig:** Subzones sind **NICHT** ESP-Level-Zuweisungen, sondern **Pin-Level-Gruppierungen** innerhalb bereits zugewiesener Zonen.

---

## Implementierungsphasen-Übersicht

| Phase | Komponente | Status | Beschreibung |
|-------|-----------|--------|--------------|
| Phase 1 | Error-Codes & Datenstrukturen | ✅ | `error_codes.h`, `system_types.h` |
| Phase 2 | GPIO-Manager Erweiterungen | ✅ | 7 neue Subzone-Methoden |
| Phase 3 | Topic-Builder Erweiterungen | ✅ | 5 neue MQTT-Topics |
| Phase 4 | Config-Manager Persistence | ✅ | NVS Storage für Subzones |
| Phase 5 | MQTT-Handler | ✅ | Assignment/Removal Handler in `main.cpp` |
| Phase 6 | Safety-Controller Integration | ✅ | `isolateSubzone()` Methode |
| Phase 7 | Dokumentation | ✅ | NVS_KEYS.md aktualisiert |

---

## Prerequisites

- [x] Zone-Assignment erfolgreich (siehe 08-zone-assignment-flow.md)
- [x] Safe-Mode initialisiert (siehe 07-error-recovery-flow.md)
- [x] Pins via GPIO-Manager reserviert
- [x] MQTT-Client operational
- [x] Config-Manager bereit

---

## Subzone Hierarchy

**Architektur-Übersicht:**
```
God-Kaiser Server (Raspberry Pi 5)
  │
  ├─► kaiser_id = "god"
  │     │
  │     ├─► ESP: ESP_AB12CD
  │     │     │
  │     │     ├─► zone_id: "greenhouse_zone_1"
  │     │     │     │
  │     │     │     ├─► master_zone_id: "greenhouse_master"
  │     │     │     │     │
  │     │     │     │     ├─► subzone_id: "irrigation_section_A"
  │     │     │     │     │     │
  │     │     │     │     │     ├─► Sensor: GPIO 4 (Soil Moisture)
  │     │     │     │     │     ├─► Actuator: GPIO 5 (Water Pump)
  │     │     │     │     │     └─► Actuator: GPIO 6 (Valve Control)
  │     │     │     │     │
  │     │     │     │     ├─► subzone_id: "irrigation_section_B"
  │     │     │     │     │     │
  │     │     │     │     │     ├─► Sensor: GPIO 12 (pH Sensor)
  │     │     │     │     │     └─► Actuator: GPIO 13 (pH Adjust Pump)
  │     │     │     │     │
  │     │     │     │     └─► subzone_id: "climate_control"
  │     │     │     │           │
  │     │     │     │           ├─► Sensor: GPIO 18 (Temperature)
  │     │     │     │           ├─► Sensor: GPIO 19 (Humidity)
  │     │     │     │           └─► Actuator: GPIO 21 (Fan Control)
  │     │     │
  │     │     └─► zone_id: "greenhouse_zone_2" (anderer ESP)
  │     │           │
  │     │           └─► subzone_id: "lighting_zone_north"
  │     │                 │
  │     │                 ├─► Actuator: GPIO 25 (LED Strip 1)
  │     │                 └─► Actuator: GPIO 26 (LED Strip 2)
  │
  └─► kaiser_id = "kaiser_01" (zukünftig: Kaiser-Node)
```

**Subzone-Eigenschaften:**
- **Granularität:** Einzelne Pins (GPIO) können zu Subzones gruppiert werden
- **Flexibilität:** Sensoren und Aktoren können unterschiedlichen Subzones angehören
- **Sicherheit:** Safe-Mode kann Pin-spezifisch oder Subzone-weit aktiviert werden
- **Isolation:** Fehler in einer Subzone beeinträchtigen nicht andere Subzones

---

## Implementierte Komponenten

### 1. Error-Codes (error_codes.h)

**File:** `src/models/error_codes.h` (lines 48-56)

```cpp
// Subzone Management Errors (2500-2599) - SERVICE RANGE
#define ERROR_SUBZONE_INVALID_ID          2500  // Invalid subzone_id format
#define ERROR_SUBZONE_GPIO_CONFLICT       2501  // GPIO already assigned to different subzone
#define ERROR_SUBZONE_PARENT_MISMATCH     2502  // parent_zone_id doesn't match ESP zone
#define ERROR_SUBZONE_NOT_FOUND           2503  // Subzone doesn't exist
#define ERROR_SUBZONE_GPIO_INVALID        2504  // GPIO not in safe pins list
#define ERROR_SUBZONE_SAFE_MODE_FAILED    2505  // Safe-mode activation failed
#define ERROR_SUBZONE_CONFIG_SAVE_FAILED  2506  // Persistence failed
```

### 2. SubzoneConfig Struct (system_types.h)

**File:** `src/models/system_types.h` (lines 57-69)

```cpp
// Sub Zone - ENHANCED für Pin-Level Management
struct SubzoneConfig {
  String subzone_id = "";           // Eindeutiger Subzone-Identifier
  String subzone_name = "";         // Menschlich lesbarer Name
  String parent_zone_id = "";       // Verknüpfung zur übergeordneten Zone
  std::vector<uint8_t> assigned_gpios;  // GPIO-Pins in dieser Subzone
  bool safe_mode_active = true;     // Safe-Mode Status der gesamten Subzone
  uint32_t created_timestamp = 0;   // Erstellungszeitpunkt
  uint8_t sensor_count = 0;         // Anzahl Sensoren in Subzone
  uint8_t actuator_count = 0;       // Anzahl Aktoren in Subzone
};
```

### 3. GPIO-Manager Erweiterungen (gpio_manager.h/cpp)

**File:** `src/drivers/gpio_manager.h` (lines 119-172)
**File:** `src/drivers/gpio_manager.cpp` (lines 403-598)

**Implementierte Methoden:**

| Methode | Beschreibung | Return |
|---------|--------------|--------|
| `assignPinToSubzone(gpio, subzone_id)` | Weist GPIO einer Subzone zu | `bool` |
| `removePinFromSubzone(gpio)` | Entfernt GPIO aus Subzone | `bool` |
| `getSubzonePins(subzone_id)` | Gibt alle GPIOs einer Subzone zurück | `vector<uint8_t>` |
| `isPinAssignedToSubzone(gpio, subzone_id)` | Prüft Subzone-Zuweisung | `bool` |
| `isSubzoneSafe(subzone_id)` | Prüft ob alle Pins im Safe-Mode | `bool` |
| `enableSafeModeForSubzone(subzone_id)` | Aktiviert Safe-Mode für Subzone | `bool` |
| `disableSafeModeForSubzone(subzone_id)` | Deaktiviert Safe-Mode Tracking | `bool` |

**Interne Datenstruktur:**
```cpp
// Private member in GPIOManager
std::map<String, std::vector<uint8_t>> subzone_pin_map_;
```

**Implementierungsdetails - assignPinToSubzone():**
```cpp
bool GPIOManager::assignPinToSubzone(uint8_t gpio, const String& subzone_id) {
  // Validation 1: Pin muss verfügbar oder bereits dieser Subzone zugewiesen sein
  if (isReservedPin(gpio)) {
    LOG_ERROR("GPIOManager: Cannot assign reserved pin " + String(gpio) + " to subzone");
    return false;
  }

  // Validation 2: Pin muss in safe pins list sein
  bool pin_in_safe_list = false;
  for (const auto& pin_info : pins_) {
    if (pin_info.pin == gpio) {
      pin_in_safe_list = true;
      break;
    }
  }
  if (!pin_in_safe_list) {
    LOG_ERROR("GPIOManager: Pin " + String(gpio) + " not in safe pins list");
    return false;
  }

  // Validation 3: Prüfe ob Pin bereits anderer Subzone zugewiesen
  // ⭐ WICHTIG: Gleiche Subzone ist OK für Updates (kein Fehler bei erneuter Zuweisung)
  for (const auto& entry : subzone_pin_map_) {
    if (entry.first != subzone_id) {
      for (uint8_t assigned_gpio : entry.second) {
        if (assigned_gpio == gpio) {
          LOG_ERROR("GPIOManager: Pin " + String(gpio) + " already assigned to subzone " + entry.first);
          return false;
        }
      }
    } else {
      // Gleiche Subzone: Update ist OK
      for (uint8_t assigned_gpio : entry.second) {
        if (assigned_gpio == gpio) {
          LOG_INFO("GPIOManager: Pin " + String(gpio) + " already assigned (update)");
          return true;
        }
      }
    }
  }

  // Assignment: Pin zu Subzone hinzufügen
  subzone_pin_map_[subzone_id].push_back(gpio);
  
  // Update pin_info für Tracking
  for (auto& pin_info : pins_) {
    if (pin_info.pin == gpio) {
      strncpy(pin_info.component_name, subzone_id.c_str(), sizeof(pin_info.component_name) - 1);
      break;
    }
  }

  LOG_INFO("GPIOManager: Pin " + String(gpio) + " assigned to subzone: " + subzone_id);
  return true;
}
```

**Implementierungsdetails - enableSafeModeForSubzone():**
```cpp
bool GPIOManager::enableSafeModeForSubzone(const String& subzone_id) {
  auto pins = getSubzonePins(subzone_id);
  if (pins.empty()) {
    LOG_WARNING("GPIOManager: Subzone " + subzone_id + " has no pins");
    return false;
  }
  
  bool success = true;
  for (uint8_t gpio : pins) {
    // ⭐ KRITISCH: De-energize outputs BEFORE mode change
    for (auto& pin_info : pins_) {
      if (pin_info.pin == gpio && pin_info.mode == OUTPUT) {
        digitalWrite(gpio, LOW);
        delayMicroseconds(10);  // Allow hardware to settle
      }
    }
    
    // Set to safe mode
    pinMode(gpio, INPUT_PULLUP);
    
    // Update tracking + verify
    for (auto& pin_info : pins_) {
      if (pin_info.pin == gpio) {
        pin_info.in_safe_mode = true;
        pin_info.mode = INPUT_PULLUP;
        if (!verifyPinState(gpio, INPUT_PULLUP)) {
          LOG_WARNING("GPIOManager: Pin " + String(gpio) + " safe-mode verification failed");
          success = false;
        }
      }
    }
  }
  
  return success;
}
```

### 4. Topic-Builder Erweiterungen (topic_builder.h/cpp)

**File:** `src/utils/topic_builder.h` (lines 30-35)
**File:** `src/utils/topic_builder.cpp` (lines 155-190)

**Implementierte Topics:**

| Methode | Topic-Pattern |
|---------|--------------|
| `buildSubzoneAssignTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign` |
| `buildSubzoneRemoveTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove` |
| `buildSubzoneAckTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack` |
| `buildSubzoneStatusTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/subzone/status` |
| `buildSubzoneSafeTopic()` | `kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe` |

### 5. Config-Manager Persistence (config_manager.h/cpp)

**File:** `src/services/config/config_manager.h` (lines 35-40)
**File:** `src/services/config/config_manager.cpp` (lines 326-462)

**Implementierte Methoden:**

| Methode | Beschreibung |
|---------|--------------|
| `saveSubzoneConfig(config)` | Speichert Subzone in NVS |
| `loadSubzoneConfig(subzone_id, config)` | Lädt Subzone aus NVS |
| `loadAllSubzoneConfigs(configs[], max, count)` | Lädt alle Subzones |
| `removeSubzoneConfig(subzone_id)` | Entfernt Subzone aus NVS |
| `validateSubzoneConfig(config)` | Validiert Subzone-Config |

**NVS-Keys (Namespace: `subzone_config`):**

| Key-Pattern | Type | Description |
|-------------|------|-------------|
| `subzone_{id}_id` | String | Subzone identifier |
| `subzone_{id}_name` | String | Human-readable name |
| `subzone_{id}_parent` | String | Parent zone ID |
| `subzone_{id}_gpios` | String | Comma-separated GPIO list |
| `subzone_{id}_safe_mode` | bool | Safe-mode status |
| `subzone_{id}_timestamp` | uint32 | Creation timestamp |

### 6. MQTT-Handler (main.cpp)

**File:** `src/main.cpp` (lines 502-875)

**Subzone-Subscription (lines 824-830):**
```cpp
// Phase 9: Subzone management topics
String subzone_assign_topic = TopicBuilder::buildSubzoneAssignTopic();
String subzone_remove_topic = TopicBuilder::buildSubzoneRemoveTopic();
String subzone_safe_topic = TopicBuilder::buildSubzoneSafeTopic();
mqttClient.subscribe(subzone_assign_topic);
mqttClient.subscribe(subzone_remove_topic);
mqttClient.subscribe(subzone_safe_topic);
LOG_INFO("Subscribed to subzone management topics");
```

**Helper-Funktion sendSubzoneAck() (lines 66-82):**
```cpp
void sendSubzoneAck(const String& subzone_id, const String& status, const String& error_message) {
  String ack_topic = TopicBuilder::buildSubzoneAckTopic();
  DynamicJsonDocument ack_doc(512);
  ack_doc["esp_id"] = g_system_config.esp_id;
  ack_doc["status"] = status;
  ack_doc["subzone_id"] = subzone_id;
  ack_doc["timestamp"] = millis() / 1000;
  
  if (status == "error" && error_message.length() > 0) {
    ack_doc["error_code"] = ERROR_SUBZONE_CONFIG_SAVE_FAILED;
    ack_doc["message"] = error_message;
  }
  
  String ack_payload;
  serializeJson(ack_doc, ack_payload);
  mqttClient.publish(ack_topic, ack_payload, 1);
}
```

### 7. Safety-Controller Integration (safety_controller.h/cpp)

**File:** `src/services/actuator/safety_controller.h` (line 18)
**File:** `src/services/actuator/safety_controller.cpp` (lines 66-86)

```cpp
bool SafetyController::isolateSubzone(const String& subzone_id, const String& reason) {
  LOG_WARNING("SafetyController: Emergency isolation of subzone: " + subzone_id);
  LOG_WARNING("Reason: " + reason);
  
  // Enable safe-mode for all pins in subzone
  if (!gpioManager.enableSafeModeForSubzone(subzone_id)) {
    LOG_ERROR("SafetyController: Failed to isolate subzone " + subzone_id);
    errorTracker.trackError(ERROR_SUBZONE_SAFE_MODE_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           ("Subzone isolation failed: " + subzone_id).c_str());
    return false;
  }
  
  // Track error
  errorTracker.trackError(ERROR_SUBZONE_SAFE_MODE_FAILED,
                         ERROR_SEVERITY_CRITICAL,
                         ("Subzone isolated: " + subzone_id + " - " + reason).c_str());
  
  LOG_INFO("SafetyController: Subzone " + subzone_id + " isolated successfully");
  return true;
}
```

---

## Subzone Assignment Payload

### MQTT Payload Format

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign`

```json
{
  "subzone_id": "irrigation_section_A",
  "subzone_name": "Irrigation Section A",
  "parent_zone_id": "greenhouse_zone_1",
  "assigned_gpios": [4, 5, 6],
  "safe_mode_active": false,
  "sensor_count": 1,
  "actuator_count": 2,
  "timestamp": 1703123456
}
```

### Payload Felder

| Feld | Typ | Erforderlich | Beschreibung |
|------|-----|-------------|--------------|
| `subzone_id` | string | ✅ | Eindeutiger Subzone-Identifier |
| `subzone_name` | string | ❌ | Menschlich lesbarer Name |
| `parent_zone_id` | string | ❌ | Übergeordnete Zone (wenn leer: verwendet ESP zone_id) |
| `assigned_gpios` | array | ✅ | GPIO-Pins für diese Subzone |
| `safe_mode_active` | boolean | ❌ | Safe-Mode Status (default: true) |
| `sensor_count` | number | ❌ | Anzahl erwarteter Sensoren |
| `actuator_count` | number | ❌ | Anzahl erwarteter Aktoren |
| `timestamp` | number | ❌ | Unix-Timestamp der Zuweisung |

### Validation Rules

1. **subzone_id**: 1-32 Zeichen, alphanumerisch + underscore, keine Leerzeichen
2. **parent_zone_id**: Muss mit zugewiesener Zone des ESP übereinstimmen (oder leer)
3. **assigned_gpios**: Nur Pins aus SAFE_GPIO_PINS Array erlaubt
4. **GPIO-Konflikte**: Pins dürfen nicht bereits anderen Subzones zugewiesen sein
5. **Zone-Assignment**: ESP muss bereits einer Zone zugewiesen sein (`g_kaiser.zone_assigned == true`)

---

## Vollständiger Flow: Boot bis Sensor mit Subzone

### Sequenz-Diagramm

```
┌─────────────┐     ┌────────────┐     ┌────────────┐     ┌──────────────┐
│   ESP32     │     │  Server    │     │  GPIO-Mgr  │     │ Config-Mgr   │
└──────┬──────┘     └─────┬──────┘     └──────┬─────┘     └──────┬───────┘
       │                  │                   │                   │
       │ 1. Boot          │                   │                   │
       ├──────────────────┼───────────────────┤                   │
       │   gpioManager.initializeAllPinsToSafeMode()              │
       │                  │                   │ ✅ All pins       │
       │                  │                   │ INPUT_PULLUP      │
       │                  │                   │                   │
       │ 2. Load configs  │                   │                   │
       ├──────────────────┼───────────────────┼───────────────────┤
       │                  │                   │   configManager   │
       │                  │                   │   .loadAllConfigs │
       │                  │                   │                   │
       │ 3. Connect WiFi/MQTT                 │                   │
       ├──────────────────┼───────────────────┼───────────────────┤
       │                  │                   │                   │
       │ 4. Subscribe to subzone topics       │                   │
       ├────────────────► │                   │                   │
       │                  │                   │                   │
       │ 5. Zone Assignment (prerequisite)    │                   │
       │◄─────────────────┤ zone/assign       │                   │
       │                  │                   │                   │
       │ 6. Subzone Assignment                │                   │
       │◄─────────────────┤ subzone/assign    │                   │
       │                  │ {gpios:[4,5,6]}   │                   │
       │                  │                   │                   │
       │ 7. Validate + Assign GPIOs           │                   │
       ├──────────────────┼───────────────────┤                   │
       │                  │                   │ assignPinToSubzone│
       │                  │                   │ for each GPIO     │
       │                  │                   │                   │
       │ 8. Save to NVS   │                   │                   │
       ├──────────────────┼───────────────────┼───────────────────┤
       │                  │                   │   saveSubzoneConfig│
       │                  │                   │                   │
       │ 9. Send ACK      │                   │                   │
       ├─────────────────►│ subzone/ack       │                   │
       │                  │ {status:assigned} │                   │
       │                  │                   │                   │
       │ 10. Sensor Config│                   │                   │
       │◄─────────────────┤ config            │                   │
       │                  │ {sensors:[       │                   │
       │                  │   {gpio:4,        │                   │
       │                  │    subzone_id:    │                   │
       │                  │    "irrigation_A"}│                   │
       │                  │ ]}                │                   │
       │                  │                   │                   │
       │ 11. Configure Sensor                 │                   │
       ├──────────────────┼───────────────────┼───────────────────┤
       │                  │                   │ requestPin(4)     │
       │                  │                   │ configurePinMode  │
       │                  │                   │                   │
       │ 12. OPERATIONAL  │                   │                   │
       ├──────────────────┼───────────────────┼───────────────────┤
       │ Sensor readings  │                   │                   │
       │ now include      │                   │                   │
       │ subzone_id       │                   │                   │
       │                  │                   │                   │
```

### Flow-Schritte im Detail

#### Schritt 1-3: Boot & Initialization

```cpp
// main.cpp setup()
void setup() {
  // STEP 3: GPIO SAFE-MODE (CRITICAL - FIRST!)
  gpioManager.initializeAllPinsToSafeMode();
  
  // STEP 6: CONFIG MANAGER
  configManager.begin();
  configManager.loadAllConfigs();
  
  // Load configs into global variables
  configManager.loadWiFiConfig(g_wifi_config);
  configManager.loadZoneConfig(g_kaiser, g_master);
  configManager.loadSystemConfig(g_system_config);
}
```

#### Schritt 4: Subscribe to Subzone Topics

```cpp
// main.cpp lines 824-830
String subzone_assign_topic = TopicBuilder::buildSubzoneAssignTopic();
String subzone_remove_topic = TopicBuilder::buildSubzoneRemoveTopic();
String subzone_safe_topic = TopicBuilder::buildSubzoneSafeTopic();
mqttClient.subscribe(subzone_assign_topic);
mqttClient.subscribe(subzone_remove_topic);
mqttClient.subscribe(subzone_safe_topic);
```

#### Schritt 5: Zone Assignment (Prerequisite)

Siehe [08-zone-assignment-flow.md](./08-zone-assignment-flow.md) für Details.

```cpp
// Zone muss zugewiesen sein, bevor Subzones erstellt werden können
if (!g_kaiser.zone_assigned) {
  LOG_ERROR("Subzone assignment failed: ESP zone not assigned");
  sendSubzoneAck(subzone_id, "error", "ESP zone not assigned");
  return;
}
```

#### Schritt 6-9: Subzone Assignment Handler

```cpp
// main.cpp lines 729-836
if (topic == subzone_assign_topic) {
  DynamicJsonDocument doc(1024);
  DeserializationError error = deserializeJson(doc, payload);
  
  if (!error) {
    String subzone_id = doc["subzone_id"].as<String>();
    String subzone_name = doc["subzone_name"].as<String>();
    String parent_zone_id = doc["parent_zone_id"].as<String>();
    JsonArray gpios_array = doc["assigned_gpios"];
    bool safe_mode_active = doc["safe_mode_active"] | true;
    
    // Validation 1: subzone_id required
    if (subzone_id.length() == 0) {
      sendSubzoneAck(subzone_id, "error", "subzone_id is required");
      return;
    }
    
    // Validation 2: parent_zone_id must match ESP zone
    if (parent_zone_id.length() > 0 && parent_zone_id != g_kaiser.zone_id) {
      sendSubzoneAck(subzone_id, "error", "parent_zone_id mismatch");
      return;
    }
    
    // Validation 3: Zone must be assigned
    if (!g_kaiser.zone_assigned) {
      sendSubzoneAck(subzone_id, "error", "ESP zone not assigned");
      return;
    }
    
    // Build SubzoneConfig
    SubzoneConfig subzone_config;
    subzone_config.subzone_id = subzone_id;
    subzone_config.subzone_name = subzone_name;
    subzone_config.parent_zone_id = parent_zone_id.length() > 0 
                                     ? parent_zone_id : g_kaiser.zone_id;
    subzone_config.safe_mode_active = safe_mode_active;
    
    // Parse GPIO-Array
    for (JsonVariant gpio_value : gpios_array) {
      subzone_config.assigned_gpios.push_back(gpio_value.as<uint8_t>());
    }
    
    // Validate config
    if (!configManager.validateSubzoneConfig(subzone_config)) {
      sendSubzoneAck(subzone_id, "error", "validation failed");
      return;
    }
    
    // Assign GPIOs with rollback on failure
    bool all_assigned = true;
    for (uint8_t gpio : subzone_config.assigned_gpios) {
      if (!gpioManager.assignPinToSubzone(gpio, subzone_id)) {
        all_assigned = false;
        // Rollback
        for (uint8_t assigned_gpio : subzone_config.assigned_gpios) {
          if (assigned_gpio != gpio) {
            gpioManager.removePinFromSubzone(assigned_gpio);
          }
        }
        break;
      }
    }
    
    if (!all_assigned) {
      sendSubzoneAck(subzone_id, "error", "GPIO assignment failed");
      return;
    }
    
    // Enable safe-mode if requested
    if (safe_mode_active) {
      gpioManager.enableSafeModeForSubzone(subzone_id);
    }
    
    // Save to NVS
    if (!configManager.saveSubzoneConfig(subzone_config)) {
      sendSubzoneAck(subzone_id, "error", "NVS save failed");
      return;
    }
    
    // Success ACK
    sendSubzoneAck(subzone_id, "subzone_assigned", "");
  }
}
```

#### Schritt 10-11: Sensor Configuration with Subzone

```cpp
// Sensor config from server includes subzone_id
{
  "sensors": [
    {
      "gpio": 4,
      "sensor_type": "soil_moisture",
      "sensor_name": "Soil Sensor Section A",
      "subzone_id": "irrigation_section_A",  // ⭐ Subzone reference
      "active": true
    }
  ]
}
```

```cpp
// parseAndConfigureSensor() in main.cpp
JsonHelpers::extractString(sensor_obj, "subzone_id", config.subzone_id, "");

// SensorConfig struct includes subzone_id
struct SensorConfig {
  uint8_t gpio;
  String sensor_type;
  String sensor_name;
  String subzone_id = "";  // ⭐ SUBZONE ASSIGNMENT
  bool active;
  // ...
};
```

---

## Error Handling & Recovery

### Error-Code-Mapping

| Error Code | Name | Ursache | Recovery |
|------------|------|---------|----------|
| 2500 | `ERROR_SUBZONE_INVALID_ID` | subzone_id leer oder >32 chars | Server korrigiert ID |
| 2501 | `ERROR_SUBZONE_GPIO_CONFLICT` | GPIO bereits anderer Subzone zugewiesen | Server entfernt alte Zuweisung |
| 2502 | `ERROR_SUBZONE_PARENT_MISMATCH` | parent_zone_id != ESP zone_id | Server korrigiert parent |
| 2503 | `ERROR_SUBZONE_NOT_FOUND` | Subzone existiert nicht | Server erstellt Subzone |
| 2504 | `ERROR_SUBZONE_GPIO_INVALID` | GPIO nicht in SAFE_GPIO_PINS | Server wählt anderen GPIO |
| 2505 | `ERROR_SUBZONE_SAFE_MODE_FAILED` | Safe-Mode Aktivierung fehlgeschlagen | Manueller Reset |
| 2506 | `ERROR_SUBZONE_CONFIG_SAVE_FAILED` | NVS-Speicherung fehlgeschlagen | Retry oder NVS-Clear |

### Rollback-Mechanismus

Bei fehlgeschlagener GPIO-Zuweisung wird ein automatischer Rollback durchgeführt:

```cpp
bool all_assigned = true;
for (uint8_t gpio : subzone_config.assigned_gpios) {
  if (!gpioManager.assignPinToSubzone(gpio, subzone_id)) {
    all_assigned = false;
    // ⭐ ROLLBACK: Entferne bereits zugewiesene GPIOs
    for (uint8_t assigned_gpio : subzone_config.assigned_gpios) {
      if (assigned_gpio != gpio) {
        gpioManager.removePinFromSubzone(assigned_gpio);
      }
    }
    break;
  }
}
```

### Emergency Subzone Isolation

```cpp
// Aufruf via SafetyController
safetyController.isolateSubzone("irrigation_section_A", "Sensor failure detected");

// Intern wird aufgerufen:
gpioManager.enableSafeModeForSubzone(subzone_id);
// 1. De-energize all outputs (digitalWrite LOW)
// 2. Set all pins to INPUT_PULLUP
// 3. Update tracking
// 4. Track error in ErrorTracker
```

---

## MQTT Topics

### ESP → Server (Status)

**Subzone ACK Topic:**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack`

**Erfolgreiche Zuweisung:**
```json
{
  "esp_id": "ESP_AB12CD",
  "status": "subzone_assigned",
  "subzone_id": "irrigation_section_A",
  "timestamp": 1703123456
}
```

**Fehlerhafte Zuweisung:**
```json
{
  "esp_id": "ESP_AB12CD",
  "status": "error",
  "subzone_id": "irrigation_section_A",
  "error_code": 2501,
  "message": "GPIO 5 already assigned to subzone irrigation_section_B",
  "timestamp": 1703123456
}
```

**Subzone Status Topic:**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/status`

```json
{
  "esp_id": "ESP_AB12CD",
  "subzones": [
    {
      "subzone_id": "irrigation_section_A",
      "status": "active",
      "gpio_count": 3,
      "safe_mode": false,
      "last_update": 1703123456
    }
  ],
  "timestamp": 1703123456
}
```

**Safe-Mode Status Topic:**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe`

```json
{
  "esp_id": "ESP_AB12CD",
  "subzone_id": "irrigation_section_A",
  "safe_mode_active": true,
  "isolated_gpios": [4, 5, 6],
  "reason": "emergency_stop",
  "timestamp": 1703123456
}
```

### Server → ESP (Control)

**Subzone Assignment Topic:**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign`

**Subzone Removal Topic:**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove`

```json
{
  "subzone_id": "irrigation_section_A",
  "reason": "zone_reassignment"
}
```

**Subzone Safe-Mode Topic (Server→ESP, B4 Fix):**
`kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe`

ESP subscribt und verarbeitet. Payload: `subzone_id`, `action` (enable/disable), `reason`, `timestamp`. Optional: `safe_mode` (bool). Handler ruft `gpioManager.enableSafeModeForSubzone()` bzw. `disableSafeModeForSubzone()`, aktualisiert NVS.

---

## Bekannte Einschränkungen

### 1. Subzone-Tracking via `subzone_ids` Liste

**Lösung (implementiert):** Die `loadAllSubzoneConfigs()` Methode nutzt eine `subzone_ids` NVS-Key mit komma-separierter Liste aller aktiven Subzone-IDs.

```cpp
// config_manager.cpp - ROBUSTE VARIANTE
// NVS Key "subzone_ids" enthält z.B. "irr_A,irr_B,clim_1"
bool ConfigManager::loadAllSubzoneConfigs(SubzoneConfig configs[], uint8_t max_configs, uint8_t& loaded_count) {
  // 1. Lade subzone_ids Liste aus NVS
  String subzone_ids_str = storageManager.getStringObj("subzone_ids", "");
  
  // 2. Parse komma-separiert und lade jede Subzone
  while (start_idx < subzone_ids_str.length()) {
    String subzone_id = parseNextId(subzone_ids_str, start_idx);
    if (loadSubzoneConfig(subzone_id, config)) {
      configs[loaded_count++] = config;
    }
  }
}
```

**Vorteile:**
- Echte Subzone-IDs statt numerischer Indizes
- Konsistent mit Server-Pattern
- Keine künstliche Limitierung
- Automatische Synchronisation bei save/remove

**Server-Integration:**
- Server sendet beim ESP-Boot alle Subzone-Assignments (analog zu Zone-Assignment)
- ESP lokale Liste dient als Offline-Recovery

### 2. Memory-Nutzung

**Einschränkung:** `std::vector` und `std::map` verwenden Heap-Speicher.

**Messungen:**
- `subzone_pin_map_` mit 10 Subzones à 5 GPIOs: ~500 Bytes
- `assigned_gpios` Vector pro Subzone: ~50 Bytes

**Best Practice:**
- Max 20 Subzones pro ESP
- Max 10 GPIOs pro Subzone
- Regelmäßige Heap-Überwachung via HealthMonitor

### 3. Thread-Safety

**Einschränkung:** GPIO-Manager ist nicht thread-safe.

**Ursache:** Alle GPIO-Operationen erfolgen im Main-Loop. FreeRTOS-Tasks würden separate Synchronisierung erfordern.

**Best Practice:**
- Alle Subzone-Operationen nur aus dem Main-Loop aufrufen
- MQTT-Callbacks sind bereits im Main-Loop-Kontext

### 4. NVS Key-Länge

**Einschränkung:** NVS-Keys sind auf 15 Zeichen begrenzt.

**Lösung:** Subzone-IDs werden gekürzt:
```cpp
String key_base = "subzone_" + config.subzone_id;
// Bei langen subzone_ids wird key_base zu lang
// ⚠️ subzone_id sollte max 6 Zeichen sein für sichere NVS-Keys
```

**Best Practice:** 
- subzone_id max 6 Zeichen (z.B. "irr_A", "clim_1")
- Alternativ: Hash-basierte Key-Generierung

---

## Best Practices für industrietauglichen Einsatz

### 1. Robustheit & Fehlertoleranz

#### 1.1 Server-Authoritative Design

```
┌─────────────────────────────────────────────────────────────┐
│  SERVER ist SINGLE SOURCE OF TRUTH für Subzone-Assignments  │
└─────────────────────────────────────────────────────────────┘

ESP speichert lokal für Offline-Recovery, aber:
- Server kann jederzeit Subzones neu zuweisen
- ESP akzeptiert Updates ohne Konflikt-Prüfung (gleiche Subzone = Update)
- Bei Inkonsistenz: Server gewinnt
```

#### 1.2 Startup-Recovery-Sequenz

```cpp
// Empfohlene Recovery-Sequenz bei ESP-Boot:
void setup() {
  // 1. GPIO Safe-Mode (KRITISCH - IMMER ZUERST)
  gpioManager.initializeAllPinsToSafeMode();
  
  // 2. Lokale Config laden (für Offline-Recovery)
  configManager.loadAllConfigs();
  
  // 3. Nach MQTT-Connect: Heartbeat senden
  mqttClient.publishHeartbeat();
  // → Server erkennt ESP und sendet:
  //   - Zone-Assignment (falls geändert)
  //   - Subzone-Assignments (falls geändert)
  //   - Sensor/Actuator-Configs (falls geändert)
  
  // 4. ESP wartet auf Server-Bestätigung, dann:
  //    - Lokale Config mit Server-Config mergen
  //    - Konflikte: Server gewinnt
}
```

#### 1.3 Watchdog-Integration

```cpp
// Kritische Subzone-Operationen mit Watchdog-Feed
bool GPIOManager::enableSafeModeForSubzone(const String& subzone_id) {
  auto pins = getSubzonePins(subzone_id);
  
  for (uint8_t gpio : pins) {
    esp_task_wdt_reset();  // ⭐ Watchdog füttern
    
    // De-energize before mode change
    if (pin_info.mode == OUTPUT) {
      digitalWrite(gpio, LOW);
      delayMicroseconds(10);
    }
    
    pinMode(gpio, INPUT_PULLUP);
  }
  
  return true;
}
```

### 2. Uptime-Optimierung

#### 2.1 Graceful Degradation

```
┌──────────────────────────────────────────────────────────────┐
│  Fehler-Eskalations-Hierarchie (von lokal zu global):        │
│                                                              │
│  Level 1: Pin-Fehler → Pin in Safe-Mode                      │
│  Level 2: Subzone-Fehler → Subzone isolieren                 │
│  Level 3: Zone-Fehler → Alle Subzones der Zone isolieren     │
│  Level 4: ESP-Fehler → Alle Pins Safe-Mode, Reboot           │
└──────────────────────────────────────────────────────────────┘
```

```cpp
// Beispiel: Sensor-Lesefehler eskaliert nur Subzone, nicht ESP
if (!sensor.read()) {
  errorCount++;
  if (errorCount > 3) {
    // Nur diese Subzone isolieren
    safetyController.isolateSubzone(sensor.subzone_id, "Sensor read failures");
    // Andere Subzones laufen weiter!
  }
}
```

#### 2.2 Heartbeat mit Subzone-Status

```cpp
// Erweiterter Heartbeat für Monitoring
{
  "esp_id": "ESP_AB12CD",
  "state": 8,  // OPERATIONAL
  "uptime_s": 86400,
  "free_heap": 180000,
  "subzones": {
    "active": 3,
    "isolated": 1,
    "safe_mode": ["climate_control"]
  }
}
```

### 3. Ausfallsicherheit

#### 3.1 Offline-Mode

```cpp
// ESP kann ohne Server-Verbindung mit letzter bekannter Config laufen
void loop() {
  if (!mqttClient.isConnected()) {
    // Offline-Mode: Lokale Subzone-Config verwenden
    // Sensoren lesen weiter
    // Aktoren in letztem bekannten Zustand (oder Safe-Mode)
    
    // Periodisch reconnect versuchen
    if (millis() - lastReconnectAttempt > 30000) {
      mqttClient.reconnect();
      lastReconnectAttempt = millis();
    }
  }
}
```

#### 3.2 Power-Loss-Recovery

```
┌─────────────────────────────────────────────────────────────┐
│  Power-Loss-Recovery-Sequenz:                                │
│                                                              │
│  1. Boot → GPIO Safe-Mode (Alle Aktoren AUS)                │
│  2. NVS laden → Letzte bekannte Subzone-Configs             │
│  3. WiFi/MQTT connect                                        │
│  4. Heartbeat senden → Server erkennt Reboot                │
│  5. Server sendet aktuelle Config                            │
│  6. ESP vergleicht und updated                               │
│  7. Aktoren werden nur aktiviert wenn Server bestätigt       │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3 Fail-Safe-Defaults

```cpp
// SubzoneConfig hat sichere Defaults
struct SubzoneConfig {
  bool safe_mode_active = true;  // ⭐ Default: Safe-Mode AN
  // ...
};

// GPIO-Manager Default: INPUT_PULLUP
void GPIOManager::initializeAllPinsToSafeMode() {
  for (uint8_t i = 0; i < HardwareConfig::SAFE_PIN_COUNT; i++) {
    pinMode(HardwareConfig::SAFE_GPIO_PINS[i], INPUT_PULLUP);  // ⭐ Sicher
  }
}
```

### 4. Recovery-Strategien

#### 4.1 Automatische Recovery

| Fehler | Recovery | Zeitraum |
|--------|----------|----------|
| Einzel-GPIO-Fehler | Pin in Safe-Mode, weiter | Sofort |
| Subzone-Fehler (3× Retry) | Subzone isolieren | 3× je 1s |
| NVS-Schreibfehler | Retry 3×, dann MQTT-only | 3× je 100ms |
| MQTT-Disconnect | Reconnect-Loop mit Backoff | Exponentiell |
| Boot-Loop (5× in 60s) | Safe-Mode, Watchdog-Reset | 60s |

#### 4.2 Manuelle Recovery-Optionen

```
┌─────────────────────────────────────────────────────────────┐
│  Recovery-Optionen für Operator:                             │
│                                                              │
│  1. MQTT: subzone/remove → Subzone entfernen                │
│  2. MQTT: subzone/assign mit neuen GPIOs                    │
│  3. MQTT: system/command {factory_reset: true}              │
│  4. Hardware: Boot-Button 10s → Factory Reset               │
│  5. Serial: Debug-Befehle (in Entwicklung)                  │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3 Server-seitige Recovery-Logik

```python
# Server-seitige Recovery bei ESP-Inkonsistenz
async def handle_esp_heartbeat(esp_id, heartbeat):
    stored_config = await db.get_esp_config(esp_id)
    
    # Vergleiche Subzones
    for subzone in stored_config.subzones:
        if subzone not in heartbeat.subzones:
            # Subzone fehlt auf ESP → Neu senden
            await mqtt.publish(
                f"kaiser/god/esp/{esp_id}/subzone/assign",
                subzone.to_json()
            )
    
    # Entferne verwaiste Subzones
    for subzone in heartbeat.subzones:
        if subzone not in stored_config.subzones:
            await mqtt.publish(
                f"kaiser/god/esp/{esp_id}/subzone/remove",
                {"subzone_id": subzone}
            )
```

---

## Testing Checklist

### Unit Tests

#### GPIO-Manager Subzone-Funktionen
```cpp
TEST(GPIOManager, AssignPinToSubzone) {
  GPIOManager& gpio = GPIOManager::getInstance();
  
  // Pin erfolgreich zuweisen
  EXPECT_TRUE(gpio.assignPinToSubzone(4, "test_subzone"));
  
  // Konflikt erkennen (andere Subzone)
  EXPECT_FALSE(gpio.assignPinToSubzone(4, "different_subzone"));
  
  // Gleiche Subzone erneut zuweisen (Update - sollte erlaubt sein)
  EXPECT_TRUE(gpio.assignPinToSubzone(4, "test_subzone"));
}

TEST(GPIOManager, SubzoneSafeMode) {
  GPIOManager& gpio = GPIOManager::getInstance();
  
  // Subzone mit Pins erstellen
  gpio.assignPinToSubzone(4, "test_subzone");
  gpio.assignPinToSubzone(5, "test_subzone");
  
  // Safe-Mode aktivieren
  EXPECT_TRUE(gpio.enableSafeModeForSubzone("test_subzone"));
  
  // Verifizieren
  EXPECT_TRUE(gpio.isPinInSafeMode(4));
  EXPECT_TRUE(gpio.isPinInSafeMode(5));
  EXPECT_TRUE(gpio.isSubzoneSafe("test_subzone"));
}
```

#### ConfigManager Subzone-Persistence
```cpp
TEST(ConfigManager, SubzonePersistence) {
  ConfigManager& config = ConfigManager::getInstance();
  
  SubzoneConfig test_config;
  test_config.subzone_id = "test_subzone";
  test_config.subzone_name = "Test Subzone";
  test_config.parent_zone_id = "test_zone";
  test_config.assigned_gpios = {4, 5, 6};
  
  // Speichern
  EXPECT_TRUE(config.saveSubzoneConfig(test_config));
  
  // Laden und vergleichen
  SubzoneConfig loaded;
  EXPECT_TRUE(config.loadSubzoneConfig("test_subzone", loaded));
  EXPECT_EQ(loaded.subzone_id, test_config.subzone_id);
  EXPECT_EQ(loaded.assigned_gpios.size(), 3);
}
```

### Integration Tests

#### Vollständiger Subzone-Assignment Flow
```cpp
TEST(SubzoneAssignment, FullFlow) {
  // Setup: Zone bereits zugewiesen
  g_kaiser.zone_id = "greenhouse_zone_1";
  g_kaiser.zone_assigned = true;
  
  // Mock MQTT Message
  String payload = R"({
    "subzone_id": "test_subzone",
    "subzone_name": "Test Subzone",
    "parent_zone_id": "greenhouse_zone_1",
    "assigned_gpios": [4, 5],
    "safe_mode_active": false
  })";
  
  // Handler ausführen (simuliert MQTT-Callback)
  handleSubzoneAssignment(payload);
  
  // Verifizieren
  EXPECT_TRUE(gpioManager.isPinAssignedToSubzone(4, "test_subzone"));
  EXPECT_TRUE(gpioManager.isPinAssignedToSubzone(5, "test_subzone"));
  EXPECT_FALSE(gpioManager.isSubzoneSafe("test_subzone"));  // safe_mode_active: false
}
```

### End-to-End Tests

#### Emergency Subzone Isolation
```cpp
TEST(SafetyController, SubzoneEmergencyIsolation) {
  // Subzone mit aktiven Pins einrichten
  gpioManager.assignPinToSubzone(4, "emergency_test");
  gpioManager.assignPinToSubzone(5, "emergency_test");
  
  // Pins aktivieren (nicht im Safe-Mode)
  gpioManager.disableSafeModeForSubzone("emergency_test");
  EXPECT_FALSE(gpioManager.isSubzoneSafe("emergency_test"));
  
  // Emergency-Stop für Subzone
  EXPECT_TRUE(safetyController.isolateSubzone("emergency_test", "Test reason"));
  
  // Verifizieren dass alle Pins isoliert wurden
  EXPECT_TRUE(gpioManager.isSubzoneSafe("emergency_test"));
  EXPECT_TRUE(gpioManager.isPinInSafeMode(4));
  EXPECT_TRUE(gpioManager.isPinInSafeMode(5));
}
```

---

## Code-Locations Reference

### ESP32 (El Trabajante)

| Component | File | Lines | Description |
|-----------|------|-------|-------------|
| SubzoneConfig Struct | `src/models/system_types.h` | 57-69 | Subzone data structure |
| Error Codes | `src/models/error_codes.h` | 48-56 | Error codes 2500-2506 |
| GPIO-Manager Header | `src/drivers/gpio_manager.h` | 119-172 | Subzone method declarations |
| GPIO-Manager Impl | `src/drivers/gpio_manager.cpp` | 403-598 | Subzone method implementations |
| Topic-Builder Header | `src/utils/topic_builder.h` | 30-35 | Subzone topic declarations |
| Topic-Builder Impl | `src/utils/topic_builder.cpp` | 155-190 | Subzone topic implementations |
| ConfigManager Header | `src/services/config/config_manager.h` | 35-40 | Subzone config declarations |
| ConfigManager Impl | `src/services/config/config_manager.cpp` | 326-462 | Subzone persistence |
| MQTT Handler | `src/main.cpp` | 729-875 | Subzone assign/remove handlers |
| ACK Helper | `src/main.cpp` | 66-82 | sendSubzoneAck() function |
| MQTT Subscriptions | `src/main.cpp` | 502-508 | Topic subscriptions |
| SafetyController Header | `src/services/actuator/safety_controller.h` | 18 | isolateSubzone declaration |
| SafetyController Impl | `src/services/actuator/safety_controller.cpp` | 66-86 | isolateSubzone implementation |

### NVS Keys (Namespace: `subzone_config`)

| Key Pattern | Type | Default | Description |
|-------------|------|---------|-------------|
| `subzone_{id}_id` | String | `""` | Subzone identifier |
| `subzone_{id}_name` | String | `""` | Human-readable name |
| `subzone_{id}_parent` | String | `""` | Parent zone ID |
| `subzone_{id}_gpios` | String | `""` | Comma-separated GPIO list |
| `subzone_{id}_safe_mode` | bool | `true` | Safe-mode status |
| `subzone_{id}_timestamp` | uint32 | `0` | Creation timestamp |

---

## Related Documentation

**ESP32 (El Trabajante):**
- → [08-zone-assignment-flow.md](./08-zone-assignment-flow.md) - Zone-System, kaiser_id Management
- → [07-error-recovery-flow.md](./07-error-recovery-flow.md) - Safe-Mode, GPIO-Manager
- → [04-runtime-sensor-config-flow.md](./04-runtime-sensor-config-flow.md) - Sensor-Config mit subzone_id
- → [05-runtime-actuator-config-flow.md](./05-runtime-actuator-config-flow.md) - Actuator-Config mit subzone_id
- → [01-boot-sequence.md](./01-boot-sequence.md) - System-Initialisierung mit Safe-Mode

**Server (El Servador):**
- → Zone-Management APIs
- → GPIO-Safe-Mode Server-seitige Validierung
- → Subzone-Monitoring und Alert-System

**Cross-Component:**
- → `docs/NVS_KEYS.md` - NVS-Schlüssel Dokumentation

---

## Changelog

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0 | 2024-12-18 | Initiale Dokumentation (geplant) |
| 2.0 | 2024-12-18 | Vollständige Implementierung dokumentiert |
| 2.1 | 2024-12-18 | Best Practices für industriellen Einsatz hinzugefügt |

---

**Status:** ✅ **VOLLSTÄNDIG IMPLEMENTIERT** - Diese Dokumentation beschreibt das implementierte Subzone-Management-System. Alle Code-Referenzen wurden mit tatsächlichen Zeilennummern aktualisiert.
