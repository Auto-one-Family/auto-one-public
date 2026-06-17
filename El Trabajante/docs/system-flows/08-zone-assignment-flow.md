# Zone Assignment Flow

## Overview

Hierarchical zone management (Phase 7) allows God-Kaiser to organize ESPs into logical zones representing physical locations (greenhouses, sections, rows). This enables zone-based automation, monitoring, and control across large deployments.

**Important:** This flow describes **runtime zone assignment** via MQTT. For initial provisioning (first-time setup), see [Provisioning Documentation](../Dynamic%20Zones%20and%20Provisioning/PROVISIONING.md) and [Boot Sequence](01-boot-sequence.md).

## Files Analyzed

- `src/main.cpp` (lines 247-248, 329-340, 415-489) - TopicBuilder initialization, zone assignment subscription and handler
- `src/services/config/config_manager.cpp` (lines 170-286) - Zone config loading, saving, and updateZoneAssignment()
- `src/models/system_types.h` (lines 23-48) - Zone data structures (KaiserZone, MasterZone)
- `src/utils/topic_builder.cpp` (lines 9, 19-22) - TopicBuilder kaiser_id buffer and setKaiserId()
- `src/services/communication/mqtt_client.cpp` (lines 380-408) - Heartbeat with zone info
- `src/services/communication/mqtt_client.h` (line 59) - publish() default QoS
- `docs/NVS_KEYS.md` - Zone configuration keys documentation

## Prerequisites

- MQTT client connected
- Config Manager operational
- ESP successfully provisioned
- Initial heartbeat sent

## Trigger

MQTT message on: `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

---

## Zone Hierarchy

**System Architecture:**
```
God-Kaiser/Kaiser (Pi) → ESP → zone_id → master_zone_id → subzone_id → Sensor/Actuator
```

**Kaiser-ID Bedeutung:**
- `kaiser_id` identifiziert den **übergeordneten Pi** (God-Kaiser Server oder Kaiser-Node), **NICHT** den ESP
- **Aktueller Stand (2025):** System funktioniert nur mit God-Kaiser Server (`kaiser_id = "god"`)
- **Roadmap:** Kaiser-Nodes (Raspberry Pi Zero/3) sind geplant für Skalierung, aber noch nicht implementiert

**Hierarchie-Details:**
```
God-Kaiser Server (Raspberry Pi 5)
  │
  ├─► kaiser_id = "god" (aktuelle Implementierung)
  │     │
  │     ├─► ESP: ESP_AB12CD
  │     │     │
  │     │     ├─► zone_id: "greenhouse_zone_1"
  │     │     │     │
  │     │     │     ├─► master_zone_id: "greenhouse_master"
  │     │     │     │
  │     │     │     └─► subzone_id: "section_A" (Sensor/Actuator-Level)
  │     │     │
  │     │     └─► zone_id: "greenhouse_zone_2" (anderer ESP)
  │     │
  │     └─► ESP: ESP_CD34EF (unassigned, kaiser_id = "god")
  │
  └─► kaiser_id = "kaiser_01" (geplant, noch nicht implementiert)
        └─► ESP: ESP_EF56GH (zukünftig über Kaiser-Node)
```

**Wichtig:** 
- Alle ESPs kommunizieren aktuell direkt mit God-Kaiser (`kaiser/god/...`)
- Kaiser-Nodes sind ein zukünftiges Feature für Skalierung (100+ ESPs)
- Die Topic-Struktur `kaiser/{kaiser_id}/...` ist bereits vorbereitet für zukünftige Kaiser-Nodes

---

## Zone Data Structures

**File:** `src/models/system_types.h`

**File:** `src/models/system_types.h` (lines 23-39, 41-48)

```cpp
// Kaiser Zone - ENHANCED (Phase 7: Dynamic Zones)
struct KaiserZone {
  // Primary Zone Identification (NEW - Phase 7)
  String zone_id = "";              // Primary zone identifier (e.g., "greenhouse_zone_1")
  String master_zone_id = "";       // Parent zone for hierarchy (e.g., "greenhouse")
  String zone_name = "";            // Human-readable zone name
  bool zone_assigned = false;       // Zone configuration status
  
  // Kaiser Communication (Existing)
  String kaiser_id = "";            // Overarching Pi identifier ("god" = God-Kaiser Server, "kaiser_XX" = Kaiser-Node)
  String kaiser_name = "";          // Kaiser name (optional)
  String system_name = "";          // System name (optional)
  bool connected = false;           // MQTT connection status
  bool id_generated = false;        // Kaiser ID generation flag
};

// Master Zone - Legacy (kept for compatibility)
struct MasterZone {
  String master_zone_id = "";
  String master_zone_name = "";
  bool assigned = false;
  bool is_master_esp = false;
};
```

---

## Zone Assignment Payload

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

**Example:** `kaiser/god/esp/ESP_AB12CD/zone/assign`

**Payload:**

```json
{
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "zone_name": "Greenhouse Section 1",
  "kaiser_id": "kaiser_production_001",
  "timestamp": 1234567890
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `zone_id` | String | Yes | Unique zone identifier |
| `master_zone_id` | String | Yes | Parent master zone ID |
| `zone_name` | String | Yes | Human-readable zone name |
| `kaiser_id` | String | Yes | Overarching Pi identifier ("god" = God-Kaiser Server, "kaiser_XX" = Kaiser-Node for future use) |
| `timestamp` | Number | No | Assignment timestamp |

---

## Flow Steps

### STEP 1: MQTT Subscription (During Boot)

**File:** `src/main.cpp` (lines 329-340)

**Code:**

```cpp
// Phase 7: Zone assignment topic subscription
String zone_assign_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                          g_system_config.esp_id + "/zone/assign";
if (g_kaiser.kaiser_id.length() == 0) {
  zone_assign_topic = "kaiser/god/esp/" + g_system_config.esp_id + "/zone/assign";
}

mqttClient.subscribe(zone_assign_topic);
LOG_INFO("Subscribed to system + actuator + zone assignment topics");
```

**Subscription Logic:**
- If `g_kaiser.kaiser_id` is empty (unassigned): Subscribe to `kaiser/god/esp/{esp_id}/zone/assign`
- If `g_kaiser.kaiser_id` is set (assigned): Subscribe to `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`
- Subscription happens during Phase 2 (Communication Layer) initialization

**Note:** The ESP subscribes to ONE topic during boot based on loaded `g_kaiser.kaiser_id`:
- If `kaiser_id` is empty: subscribes to `kaiser/god/esp/{esp_id}/zone/assign`
- If `kaiser_id` is set: subscribes to `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

**Aktueller Stand:**
- Alle ESPs kommunizieren aktuell mit God-Kaiser Server (`kaiser_id = "god"`)
- Kaiser-Nodes sind geplant, aber noch nicht implementiert
- Die Topic-Struktur ist bereits zukunftsfähig vorbereitet

---

### STEP 2: MQTT Message Reception

**File:** `src/main.cpp` (lines 415-421)

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
  // ...
}
```

**Topic Matching:**
- Unassigned ESP: `kaiser/god/esp/{esp_id}/zone/assign`
- Assigned ESP: `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

---

### STEP 3: Parse Zone Information

**File:** `src/main.cpp` (lines 426-440)

**Code:**

```cpp
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
  
  // Update zone configuration...
} else {
  LOG_ERROR("Failed to parse zone assignment JSON");
  // No acknowledgment sent on parse error
}
```

**JSON Buffer:** 512 bytes

**Validation:**
- No explicit validation of field presence (missing fields default to empty String)
- No validation of zone_id format or length
- No validation of kaiser_id format
- Empty strings are accepted (will be stored as-is in NVS)
- JSON parsing errors are logged but no acknowledgment is sent

**Error Handling:**
- If JSON parsing fails: Error logged, no acknowledgment sent, handler returns
- If `updateZoneAssignment()` fails: Error acknowledgment sent with `status: "error"`
- If NVS write fails: Error logged, error acknowledgment sent

---

### STEP 4: Update Configuration

**File:** `src/main.cpp` (lines 442-476)

**Code:**

```cpp
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
  
  // Send acknowledgment (use TopicBuilder for consistency)
  String ack_topic = TopicBuilder::buildZoneAckTopic();
  DynamicJsonDocument ack_doc(384);
  ack_doc["esp_id"] = g_system_config.esp_id;
  ack_doc["status"] = "zone_assigned";
  ack_doc["zone_id"] = zone_id;
  ack_doc["master_zone_id"] = master_zone_id;
  ack_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
  ack_doc["seq"] = mqttClient.getNextSeq();
  if (correlationId.length() > 0) {
    ack_doc["correlation_id"] = correlationId;
  }

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
```

**Heartbeat Behavior:**
- `publishHeartbeat()` checks `HEARTBEAT_INTERVAL_MS` before publishing (line 383)
- After zone assignment, `publishHeartbeat()` is called immediately (line 475)
- If interval hasn't elapsed since last heartbeat, heartbeat is skipped (normal throttling)
- Next scheduled heartbeat (via `mqttClient.loop()`) will include new zone info
- Heartbeat topic uses `TopicBuilder::buildSystemHeartbeatTopic()` which uses updated kaiser_id
} else {
  LOG_ERROR("❌ Failed to save zone configuration");
  
  // Send error acknowledgment (use TopicBuilder for consistency)
  String ack_topic = TopicBuilder::buildZoneAckTopic();
  DynamicJsonDocument err_doc(384);
  err_doc["esp_id"] = g_system_config.esp_id;
  err_doc["status"] = "error";
  err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
  err_doc["seq"] = mqttClient.getNextSeq();
  err_doc["message"] = "Failed to save zone config";
  if (correlationId.length() > 0) {
    err_doc["correlation_id"] = correlationId;
  }
  String error_response;
  serializeJson(err_doc, error_response);
  mqttClient.publish(ack_topic, error_response);
}
```

**Operations:**
1. Call `configManager.updateZoneAssignment()` to persist zone config to NVS
2. Update global zone variables (`g_kaiser`)
3. Reconfigure TopicBuilder with new kaiser_id (if provided)
4. Update system state to `STATE_ZONE_CONFIGURED`
5. Persist system state to NVS via `configManager.saveSystemConfig()`
6. Send acknowledgment on acknowledgment topic
7. Send updated heartbeat (immediately, bypassing heartbeat interval)

**Order of Operations:**
- NVS persistence happens FIRST (via `updateZoneAssignment()`)
- Global variables updated AFTER successful NVS save
- TopicBuilder updated AFTER global variables
- Acknowledgment sent AFTER all updates complete

---

### STEP 5: Persist to NVS

**File:** `src/services/config/config_manager.cpp` (lines 257-286)

**Code:**

```cpp
// Phase 7: Dynamic Zone Assignment
bool ConfigManager::updateZoneAssignment(const String& zone_id, 
                                        const String& master_zone_id, 
                                        const String& zone_name, 
                                        const String& kaiser_id) {
  LOG_INFO("ConfigManager: Updating zone assignment...");
  LOG_INFO("  Zone ID: " + zone_id);
  LOG_INFO("  Master Zone: " + master_zone_id);
  LOG_INFO("  Zone Name: " + zone_name);
  LOG_INFO("  Kaiser ID: " + kaiser_id);
  
  // Update kaiser_ structure
  kaiser_.zone_id = zone_id;
  kaiser_.master_zone_id = master_zone_id;
  kaiser_.zone_name = zone_name;
  kaiser_.zone_assigned = true;
  
  // Update kaiser_id if provided
  if (kaiser_id.length() > 0) {
    kaiser_.kaiser_id = kaiser_id;
  }
  
  // Persist to NVS via saveZoneConfig()
  bool success = saveZoneConfig(kaiser_, master_);
  
  if (success) {
    LOG_INFO("ConfigManager: Zone assignment updated successfully");
  } else {
    LOG_ERROR("ConfigManager: Failed to update zone assignment");
  }
  
  return success;
}
```

**NVS Persistence:** `saveZoneConfig()` saves all zone fields to NVS namespace `zone_config`.

### NVS Keys

**Namespace:** `zone_config`

**Phase 7 Keys (Hierarchical Zone Info):**
- `zone_id` (String) - Primary zone identifier
- `master_zone_id` (String) - Parent master zone ID
- `zone_name` (String) - Human-readable zone name
- `zone_assigned` (bool) - Zone assignment status flag

**Existing Keys (Kaiser Communication):**
- `kaiser_id` (String) - Kaiser instance ID
- `kaiser_name` (String) - Kaiser name (optional)
- `connected` (bool) - MQTT connection status
- `id_generated` (bool) - Kaiser ID generation flag

**Legacy Keys (Backward Compatibility):**
- `legacy_master_zone_id` (String) - Legacy master zone ID
- `legacy_master_zone_name` (String) - Legacy master zone name
- `is_master_esp` (bool) - Legacy master ESP flag

---

### STEP 6: Reconfigure Topic Builder

**File:** `src/utils/topic_builder.cpp` (lines 19-22)

**Code:**

```cpp
void TopicBuilder::setKaiserId(const char* kaiser_id) {
  strncpy(kaiser_id_, kaiser_id, sizeof(kaiser_id_) - 1);
  kaiser_id_[sizeof(kaiser_id_) - 1] = '\0';
}
```

**Effect:** All subsequent MQTT topics built via `TopicBuilder` use new Kaiser ID

**Example:**

Before (unassigned):
```
kaiser/god/esp/ESP_AB12CD/sensor/4/data
kaiser/god/esp/ESP_AB12CD/system/heartbeat
```

After (assigned):
```
kaiser/kaiser_production_001/esp/ESP_AB12CD/sensor/4/data
kaiser/kaiser_production_001/esp/ESP_AB12CD/system/heartbeat
```

**Important:** TopicBuilder uses static buffer `kaiser_id_[64]` with default value `"god"` (line 9). After zone assignment, all new topics use the updated kaiser_id.

**Note:** Existing subscriptions are NOT automatically updated. The ESP continues to listen on the old topic until reconnection. See "MQTT Subscription Behavior" section below.

---

### STEP 7: Publish Acknowledgment

**Acknowledgment Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/ack`

**Success Payload:**

```json
{
  "esp_id": "ESP_AB12CD",
  "status": "zone_assigned",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "ts": 1234567890,
  "seq": 42,
  "correlation_id": "uuid-v4"
}
```

**correlation_id:** Echoed from zone/assign payload. Der Server (`MQTTCommandBridge`) matched wartende Aufrufe **nur** über diese UUID (kein FIFO-Fallback); fehlt das Echo → REST-ACK-Timeout trotz erfolgreicher NVS.

**Error Payload:**

```json
{
  "esp_id": "ESP_AB12CD",
  "status": "error",
  "message": "Failed to save zone config",
  "ts": 1234567890,
  "seq": 43,
  "correlation_id": "uuid-v4"
}
```

**QoS:** 1 (at least once) - Default QoS for `mqttClient.publish()` is 1 (see `mqtt_client.h` line 59)

**Note:** Acknowledgment topic is built using `g_kaiser.kaiser_id` AFTER it's updated (line 449), so it uses the NEW kaiser_id if provided in assignment payload. The acknowledgment is published on the new kaiser topic.

---

### STEP 8: Publish Updated Heartbeat

**File:** `src/services/communication/mqtt_client.cpp` (lines 380-408)

**Code:**

```cpp
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

**Heartbeat Includes Zone Information:**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "zone_assigned": true,
  "ts": 1234567890,
  "uptime": 12345,
  "heap_free": 250000,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 2
}
```

**Note:** Heartbeat uses manual string concatenation (not DynamicJsonDocument) for efficiency. Topic is built via `TopicBuilder::buildSystemHeartbeatTopic()` which uses the current `kaiser_id_` from TopicBuilder.

---

## Zone Assignment Workflow

### Initial Assignment

1. ESP boots with no zone assignment (after provisioning, see [Boot Sequence](01-boot-sequence.md))
2. ESP subscribes to: `kaiser/god/esp/{esp_id}/zone/assign` (default when `kaiser_id` is empty)
3. ESP publishes initial heartbeat with `zone_assigned: false`
4. **Wichtig:** Server lehnt unbekannte ESPs ab - ESP muss zuerst über REST API registriert werden
5. God-Kaiser erkennt registrierten ESP (nicht via Auto-Discovery)
6. User assigns ESP to zone in UI
7. God-Kaiser publishes zone assignment via MQTT
8. ESP receives, configures, and acknowledges
9. ESP republishes heartbeat with zone info
10. God-Kaiser confirms in UI

**Hinweis:** Auto-Discovery via Heartbeat ist deaktiviert. ESPs müssen zuerst über `POST /api/v1/esp/register` registriert werden, bevor sie Zone Assignments erhalten können.

### Reassignment

1. User changes ESP zone in God-Kaiser UI
2. God-Kaiser publishes new zone assignment on current Kaiser topic (`kaiser/{current_kaiser_id}/esp/{esp_id}/zone/assign`)
3. ESP receives and processes assignment (ESP still subscribed to old topic)
4. ESP updates configuration (NVS + globals + TopicBuilder)
5. ESP acknowledges on NEW Kaiser topic (`kaiser/{new_kaiser_id}/esp/{esp_id}/zone/ack`) - uses updated kaiser_id
6. ESP publishes heartbeat with new zone info (on NEW Kaiser topic via TopicBuilder)
7. ESP continues to listen on OLD subscription until reboot
8. **Important:** ESP does NOT automatically resubscribe after reconnection - subscriptions only happen during `setup()` Phase 2
9. After ESP reboot, subscriptions are re-established using new kaiser_id from NVS

**Important:** MQTT subscriptions are NOT automatically updated when kaiser_id changes. The ESP will:
- Continue receiving messages on old topic (if still subscribed via broker's persistent session)
- Publish new messages on new topic (via TopicBuilder)
- Resubscribe to new topics only after ESP reboot (during `setup()` Phase 2)
- **Limitation:** If ESP doesn't reboot, it may miss zone assignment messages on new kaiser topic until reboot

**Aktueller Stand:**
- Alle ESPs verwenden aktuell `kaiser_id = "god"` (God-Kaiser Server)
- Topic-Migration zu anderen `kaiser_id` Werten ist für zukünftige Kaiser-Nodes vorbereitet
- Bei Zone Assignment wird `kaiser_id` im Payload mitgesendet, aber aktuell immer `"god"`

---

## MQTT Topic Migration

### Before Zone Assignment

| Topic Type | Pattern | Example |
|------------|---------|---------|
| Sensor Data | `kaiser/god/esp/{esp_id}/sensor/{gpio}/data` | `kaiser/god/esp/ESP_AB12CD/sensor/4/data` |
| Actuator Command | `kaiser/god/esp/{esp_id}/actuator/{gpio}/command` | `kaiser/god/esp/ESP_AB12CD/actuator/5/command` |
| Config | `kaiser/god/esp/{esp_id}/config` | `kaiser/god/esp/ESP_AB12CD/config` |
| Heartbeat | `kaiser/god/esp/{esp_id}/system/heartbeat` | `kaiser/god/esp/ESP_AB12CD/system/heartbeat` |
| Zone Assign | `kaiser/god/esp/{esp_id}/zone/assign` | `kaiser/god/esp/ESP_AB12CD/zone/assign` |

### After Zone Assignment

| Topic Type | Pattern | Example |
|------------|---------|---------|
| Sensor Data | `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/sensor/4/data` |
| Actuator Command | `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/actuator/5/command` |
| Config | `kaiser/{kaiser_id}/esp/{esp_id}/config` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/config` |
| Heartbeat | `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/system/heartbeat` |
| Zone Assign | `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/zone/assign` |
| Zone ACK | `kaiser/{kaiser_id}/esp/{esp_id}/zone/ack` | `kaiser/kaiser_prod_001/esp/ESP_AB12CD/zone/ack` |

### MQTT Subscription Behavior

**During Boot (Phase 2):**
- ESP subscribes to zone assignment topic based on loaded `g_kaiser.kaiser_id`
- If `kaiser_id` is empty: subscribes to `kaiser/god/esp/{esp_id}/zone/assign`
- If `kaiser_id` is set: subscribes to `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

**After Zone Assignment:**
- ESP updates `TopicBuilder::kaiser_id_` immediately
- All NEW topics built via TopicBuilder use new kaiser_id
- Existing subscriptions remain active (no automatic unsubscribe/resubscribe)
- ESP will resubscribe to new topics only after MQTT reconnection

**During MQTT Reconnection:**
- `mqttClient.loop()` detects disconnection and calls `reconnect()` → `connectToBroker()`
- `connectToBroker()` only establishes connection, does NOT resubscribe
- PubSubClient maintains subscriptions if broker supports persistent sessions
- **Important:** Subscriptions are NOT automatically rebuilt after reconnection
- If ESP reboots, subscriptions are re-established during `setup()` (lines 329-340) using current `g_kaiser.kaiser_id`
- After zone assignment, ESP continues listening on old subscription until reboot or manual unsubscribe

---

## Sensor/Actuator Subzone Integration

### Sensor with Subzone

**Configuration:**

```json
{
  "gpio": 4,
  "sensor_type": "temp_ds18b20",
  "sensor_name": "Temperature",
  "subzone_id": "section_A"
}
```

**Published Data:**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "subzone_id": "section_A",
  "gpio": 4,
  "sensor_type": "temp_ds18b20",
  "value": 23.5,
  "unit": "°C"
}
```

**Hierarchy:**

```
Kaiser: god (God-Kaiser Server - aktueller Stand)
  └─► Master Zone: greenhouse_master
      └─► Zone: greenhouse_zone_1
          └─► ESP: ESP_AB12CD
              └─► Subzone: section_A
                  └─► Sensor: GPIO 4 (Temperature)
```

**Hinweis:** `kaiser_id = "god"` identifiziert den God-Kaiser Server. Kaiser-Nodes (`kaiser_01`, etc.) sind geplant, aber noch nicht implementiert.

---

## State Machine

### Zone Assignment States

```
STATE_BOOT
  │
  └─► STATE_PROVISIONED (WiFi configured)
      │
      └─► STATE_CONNECTED (MQTT connected)
          │
          └─► STATE_ZONE_CONFIGURED (Zone assigned)
              │
              └─► STATE_OPERATIONAL (Normal operation)
```

**State Tracking:**

**File:** `src/models/system_types.h` (lines 8-21)

```cpp
enum SystemState {
  STATE_BOOT = 0,
  STATE_WIFI_SETUP,
  STATE_WIFI_CONNECTED,
  STATE_MQTT_CONNECTING,
  STATE_MQTT_CONNECTED,
  STATE_AWAITING_USER_CONFIG,
  STATE_ZONE_CONFIGURED,        // Zone assignment complete
  STATE_SENSORS_CONFIGURED,
  STATE_OPERATIONAL,
  STATE_LIBRARY_DOWNLOADING,    // Optional - OTA Library Mode
  STATE_SAFE_MODE = 10,
  STATE_ERROR = 11
};
```

**State Transition:**
- Zone assignment sets `g_system_config.current_state = STATE_ZONE_CONFIGURED` (value: 6)
- State is persisted to NVS via `configManager.saveSystemConfig()`

---

## God-Kaiser Integration

### Zone Management Features

1. **ESP Registration (Required)**
   - **Wichtig:** Auto-Discovery via Heartbeat ist deaktiviert
   - ESPs müssen zuerst über REST API registriert werden: `POST /api/v1/esp/register`
   - God-Kaiser lehnt Heartbeats von unbekannten ESPs ab
   - Nach Registrierung: God-Kaiser subscribes to `kaiser/god/esp/{esp_id}/system/heartbeat`
   - Displays registered ESPs in UI (unassigned ESPs zeigen `zone_assigned: false`)

2. **Zone Assignment UI**
   - Drag-and-drop ESP assignment
   - Hierarchical zone tree
   - Bulk zone operations

3. **Zone-Based Monitoring**
   - Filter by zone/master zone
   - Zone-level dashboards
   - Zone aggregation (avg temp per zone)

4. **Zone-Based Automation**
   - Rules apply to entire zone
   - Zone emergency stop
   - Zone-level schedules

---

## Benefits of Zone Organization

### Scalability

- **100 ESPs:** Organize by greenhouse/section
- **1000 ESPs:** Multi-site deployments
- **Hierarchical:** Easy to navigate large installations

### Automation

- **Zone Rules:** "Turn on fans in greenhouse_zone_1 if avg temp > 28°C"
- **Master Zone Rules:** "Emergency stop all actuators in greenhouse_master"

### Monitoring

- **Zone Dashboards:** View all sensors in a zone
- **Zone Alerts:** Alert if any sensor in zone fails
- **Zone Reports:** Daily/weekly reports per zone

### Maintenance

- **Zone Filtering:** Show only ESPs in specific zone
- **Batch Updates:** Update config for all ESPs in zone
- **Zone Isolation:** Test new features in test zone

---

## Error Handling

### Zone Assignment Failures

**Causes:**
- NVS write failure
- Invalid zone ID format
- Network timeout

**Recovery:**
- ESP remains in previous state
- Publishes error acknowledgment
- Can be retried by God-Kaiser

### Topic Migration Issues

**Causes:**
- MQTT broker ACL restrictions (new kaiser_id not authorized)
- Topic buffer overflow (256-byte buffer in TopicBuilder)
- Subscription mismatch (listening on old topic, publishing on new)

**Mitigation:**
- TopicBuilder validates buffer size (truncation detection)
- ESP continues to listen on old subscription until reconnection
- After reconnection, ESP automatically subscribes to new topics
- Fallback: If kaiser_id is empty, defaults to "god"

**Known Limitation:**
- No automatic unsubscribe/resubscribe when kaiser_id changes
- ESP must reboot to update subscriptions (subscriptions only happen during `setup()` Phase 2, lines 329-340)
- This is intentional to avoid subscription storms during zone reassignment
- **Workaround:** God-Kaiser should publish zone assignments on BOTH old and new kaiser topics during transition period, or wait for ESP reboot

**Subscription Persistence:**
- PubSubClient uses clean session by default (subscriptions lost on disconnect)
- Subscriptions are NOT maintained across MQTT reconnections
- Subscriptions are only re-established during ESP boot (`setup()` Phase 2)

---

## Performance Impact

**Zone Assignment Operation:**
- Duration: 50-150ms (NVS writes + MQTT publish)
- NVS Writes: 7-9 keys via `saveZoneConfig()`:
  - Phase 7 keys: zone_id, master_zone_id, zone_name, zone_assigned
  - Kaiser keys: kaiser_id, kaiser_name, connected, id_generated
  - Legacy keys: legacy_master_zone_id, legacy_master_zone_name, is_master_esp
- MQTT Messages: 2 (ack QoS 1 + heartbeat QoS 0)
- Memory: ~1KB temporary (JSON buffers: 512 bytes for parsing + 256 bytes for ack)
- CPU: <1% (synchronous operation in loop context)
- Blocking: Yes (blocks `loop()` during processing)

**Ongoing Impact:**
- Memory: Zone info cached in `g_kaiser` global (minimal overhead)
- Topic strings: Built on-demand via TopicBuilder (256-byte static buffer)
- MQTT traffic: No additional overhead (heartbeat already includes zone info)
- CPU: <0.1% (zone info included in existing heartbeat)

**NVS Storage:**
- Zone config namespace: ~500 bytes (7-9 keys × ~50-60 bytes average)
- Total NVS usage: ~8KB (with sensors/actuators at full capacity)

---

## Debugging

### Enable Debug Logging

```cpp
logger.setLogLevel(LOG_DEBUG);
```

### MQTT Monitoring

```bash
# Monitor zone assignments
mosquitto_sub -h 192.168.0.198 -p 8883 \
  -t "kaiser/+/esp/+/zone/assign" \
  -t "kaiser/+/esp/+/zone/ack" \
  -v

# Monitor heartbeats for zone info
mosquitto_sub -h 192.168.0.198 -p 8883 \
  -t "kaiser/+/esp/+/system/heartbeat" \
  -v
```

---

## Boot Sequence Integration

**File:** `src/main.cpp` (lines 170-190)

During boot, zone configuration is loaded from NVS:

```cpp
// Load zone configuration
configManager.loadZoneConfig(g_kaiser, g_master);

// Configure TopicBuilder with loaded kaiser_id
TopicBuilder::setEspId(g_system_config.esp_id.c_str());
TopicBuilder::setKaiserId(g_kaiser.kaiser_id.c_str());
```

**Boot Behavior:**
- If zone_assigned = true: ESP starts with zone info, subscribes to assigned kaiser topic
- If zone_assigned = false: ESP starts unassigned, subscribes to `kaiser/god/...` topic
- System state loaded from NVS (may be STATE_ZONE_CONFIGURED if previously assigned)

**See:** [Boot Sequence](01-boot-sequence.md) for complete initialization flow

---

## Zone Loading from NVS

**File:** `src/services/config/config_manager.cpp` (lines 170-204)

```cpp
bool ConfigManager::loadZoneConfig(KaiserZone& kaiser, MasterZone& master) {
  if (!storageManager.beginNamespace("zone_config", true)) {
    return false;
  }
  
  // Load Hierarchical Zone Info (Phase 7)
  kaiser.zone_id = storageManager.getStringObj("zone_id", "");
  kaiser.master_zone_id = storageManager.getStringObj("master_zone_id", "");
  kaiser.zone_name = storageManager.getStringObj("zone_name", "");
  kaiser.zone_assigned = storageManager.getBool("zone_assigned", false);
  
  // Load Kaiser zone (Existing)
  kaiser.kaiser_id = storageManager.getStringObj("kaiser_id", "");
  kaiser.kaiser_name = storageManager.getStringObj("kaiser_name", "");
  kaiser.connected = storageManager.getBool("connected", false);
  kaiser.id_generated = storageManager.getBool("id_generated", false);
  
  // Load Master zone (Legacy - kept for compatibility)
  master.master_zone_id = storageManager.getStringObj("legacy_master_zone_id", "");
  master.master_zone_name = storageManager.getStringObj("legacy_master_zone_name", "");
  master.is_master_esp = storageManager.getBool("is_master_esp", false);
  
  storageManager.endNamespace();
  return true;
}
```

**Default Values:** All strings default to empty `""`, booleans default to `false` if not found in NVS.

---

## Related Documentation

**ESP32 (El Trabajante):**
- → [Boot Sequence](01-boot-sequence.md) - Zone loading during boot, Provisioning integration
- → [Provisioning Documentation](../Dynamic%20Zones%20and%20Provisioning/PROVISIONING.md) - Initial WiFi/Server setup
- → [Dynamic Zones Implementation](../Dynamic%20Zones%20and%20Provisioning/DYNAMIC_ZONES_IMPLEMENTATION.md) - Implementation summary
- → [MQTT Protocol](../Mqtt_Protocoll.md) - Zone Assignment Topics specification
- → [Sensor Reading Flow](02-sensor-reading-flow.md) - Zone info in sensor data
- → [MQTT Message Routing](06-mqtt-message-routing-flow.md) - Zone assignment handler integration

**Server (El Servador):**
- → `.claude/CLAUDE_SERVER.md` - Server documentation, Zone Assignment Publisher (to be implemented)
- → `El Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py` - Heartbeat processing, ESP registration

---

**End of Zone Assignment Flow Documentation**

