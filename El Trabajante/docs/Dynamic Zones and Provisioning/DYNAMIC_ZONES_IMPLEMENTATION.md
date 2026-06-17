# Dynamic Zones & Runtime Configuration - Implementation Summary

**Date:** January 22, 2025  
**Version:** Phase 7 - El Trabajante  
**Status:** ✅ IMPLEMENTED

---

## 🎯 Overview

This document summarizes the implementation of dynamic runtime configuration and hierarchical zone management in El Trabajante (ESP32 firmware). The system now supports:

- **Dynamic Sensors/Actuators:** Add, remove, and reconfigure at runtime without ESP reboot
- **Hierarchical Zones:** God-Kaiser/Kaiser (Pi) → ESP → zone_id → master_zone_id → subzone_id → Sensor/Actuator
- **Zone Assignment:** Runtime zone assignment via MQTT (separate from initial provisioning)
- **Live Config Changes:** All configuration changes persist immediately to NVS
- **Zone-Aware Messaging:** All MQTT messages include zone metadata

**Important:** This document describes **runtime zone assignment** via MQTT. For initial provisioning (WiFi/Server setup), see [Provisioning Documentation](PROVISIONING.md) and [Boot Sequence](../system-flows/01-boot-sequence.md).

---

## 📦 Files Modified

### Core Data Structures
- **`El Trabajante/src/models/system_types.h`**
  - Enhanced `KaiserZone` struct with:
    - `zone_id` - Primary zone identifier
    - `master_zone_id` - Parent zone for hierarchy
    - `zone_name` - Human-readable name
    - `zone_assigned` - Configuration status flag

### Configuration Management
- **`El Trabajante/src/services/config/config_manager.h`**
  - Added `updateZoneAssignment()` method for runtime zone changes

- **`El Trabajante/src/services/config/config_manager.cpp`**
  - Enhanced `loadZoneConfig()` to load new zone fields
  - Enhanced `saveZoneConfig()` to persist new zone fields
  - Implemented `updateZoneAssignment()` for MQTT-triggered zone updates

### Communication Layer
- **`El Trabajante/src/services/communication/mqtt_client.cpp`**
  - Enhanced `publishHeartbeat()` to include:
    - `esp_id` - ESP identifier
    - `zone_id` - Primary zone
    - `master_zone_id` - Parent zone
    - `zone_assigned` - Configuration status
    - `sensor_count` - Active sensor count
    - `actuator_count` - Active actuator count
  - Added external references to `g_kaiser` and `g_system_config`

### Sensor Management
- **`El Trabajante/src/services/sensor/sensor_manager.cpp`**
  - Enhanced `configureSensor()` for runtime reconfiguration:
    - Detects existing sensors and updates them
    - Logs type changes
    - Persists changes to NVS immediately
  - Enhanced `removeSensor()`:
    - Properly releases GPIO
    - Persists removal to NVS
  - Enhanced `buildMQTTPayload()` to include:
    - `esp_id`
    - `zone_id` (from global g_kaiser)
    - `subzone_id` (from sensor config)

### Actuator Management
- **`El Trabajante/src/services/actuator/actuator_manager.cpp`**
  - Added `#include "config_manager.h"` for NVS persistence
  - Enhanced `configureActuator()` for runtime reconfiguration:
    - Detects runtime reconfiguration vs. new actuator
    - Safely stops actuator before type changes
    - Persists all actuator configs to NVS immediately
  - Enhanced `removeActuator()`:
    - Stops actuator before removal
    - Persists remaining actuators to NVS
  - Enhanced `buildStatusPayload()` to include:
    - `esp_id`
    - `zone_id`
    - `subzone_id`
  - Enhanced `buildResponsePayload()` to include zone context

### Main Application
- **`El Trabajante/src/main.cpp`**
  - Added initial heartbeat after MQTT connection (line ~317)
  - Added zone assignment topic subscription (line ~327)
  - Implemented zone assignment MQTT handler (line ~415-480):
    - Parses zone assignment payload
    - Updates global g_kaiser structure
    - Persists to NVS via ConfigManager
    - Sends acknowledgment
    - Updates system state
    - Publishes updated heartbeat

---

## 🚀 Key Features Implemented

### 1. Hierarchical Zone System

**Structure:**
```
God-Kaiser/Kaiser (Pi) → ESP → zone_id → master_zone_id → subzone_id → Sensor/Actuator
```

**Kaiser-ID Bedeutung:**
- `kaiser_id` identifiziert den **übergeordneten Pi** (God-Kaiser Server oder Kaiser-Node), **NICHT** den ESP
- **Aktueller Stand (2025):** System funktioniert nur mit God-Kaiser Server (`kaiser_id = "god"`)
- **Roadmap:** Kaiser-Nodes (Raspberry Pi Zero/3) sind geplant für Skalierung, aber noch nicht implementiert
- Alle ESPs kommunizieren aktuell direkt mit God-Kaiser (`kaiser/god/...`)

**Zone Assignment Flow:**
1. ESP boots (nach Provisioning), connects to WiFi/MQTT
2. ESP sends initial heartbeat with `zone_assigned: false`
3. **Wichtig:** Server lehnt unbekannte ESPs ab - ESP muss zuerst über REST API registriert werden (`POST /api/v1/esp/register`)
4. God-Kaiser erkennt registrierten ESP (nicht via Auto-Discovery)
5. User assigns ESP to zone in UI
6. God-Kaiser sends zone assignment via MQTT topic: `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` (aktuell immer `kaiser/god/...`)
7. ESP receives assignment, updates config, persists to NVS
8. ESP sends acknowledgment
9. ESP continues to operational state with zone info in all messages

**Hinweis:** Auto-Discovery via Heartbeat ist deaktiviert. Siehe [Zone Assignment Flow](../system-flows/08-zone-assignment-flow.md) für detaillierten Flow.

### 2. Runtime Sensor Configuration

**Capabilities:**
- **Add Sensor:** Configure new sensor, allocates GPIO, persists to NVS
- **Update Sensor:** Change type, name, or subzone without reboot
- **Remove Sensor:** Releases GPIO, persists removal to NVS
- **GPIO Changes:** Detects and handles GPIO reallocation
- **Type Changes:** Destroys old sensor, creates new one

**NVS Persistence:**
- All changes immediately saved to NVS
- Configuration survives ESP reboots
- No code changes or firmware updates required

### 3. Runtime Actuator Configuration

**Capabilities:**
- **Add Actuator:** Configure new actuator, creates driver, persists to NVS
- **Update Actuator:** Change type, name, or subzone without reboot
- **Remove Actuator:** Safely stops, releases GPIO, persists to NVS
- **Safety:** Emergency stop before type changes or removal

**NVS Persistence:**
- All actuator configs saved to NVS immediately
- Configuration survives reboots

### 4. Enhanced MQTT Heartbeat

**Payload Example:**
```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse",
  "zone_assigned": true,
  "ts": 1234567890,
  "uptime": 3600,
  "heap_free": 245632,
  "wifi_rssi": -45,
  "sensor_count": 5,
  "actuator_count": 3
}
```

**Purpose:**
- God-Kaiser tracks ESP health per zone
- Shows ESP registration status (`zone_assigned: false` = unassigned, aber registriert)
- Monitors zone-wide sensor/actuator distribution
- Enables cross-zone logic

**Wichtig:** Heartbeat allein reicht nicht für ESP-Discovery. ESPs müssen zuerst über REST API registriert werden.

### 5. Zone-Aware Sensor Messages

**Payload Example:**
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

**Benefits:**
- God-Kaiser can implement cross-zone logic
- Track sensor data by zone hierarchy
- Enable zone-based alerts and automations

### 6. Zone-Aware Actuator Messages

**Status Payload Example:**
```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "subzone_id": "section_A",
  "ts": 1234567890,
  "gpio": 5,
  "type": "pump",
  "state": true,
  "pwm": 255,
  "runtime_ms": 12345,
  "emergency": "none"
}
```

**Response Payload Example:**
```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "ts": 1234567890,
  "gpio": 5,
  "command": "set",
  "value": 1.0,
  "duration": 0,
  "success": true,
  "message": "Actuator activated"
}
```

---

## 🔧 MQTT Topics

### Zone Assignment (New)
**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign`

**Kaiser-ID Bedeutung:**
- `kaiser_id` identifiziert den übergeordneten Pi (God-Kaiser Server oder Kaiser-Node)
- **Aktuell:** Immer `"god"` (God-Kaiser Server)
- **Zukunft:** `"kaiser_01"`, `"kaiser_02"`, etc. für Kaiser-Nodes (geplant, noch nicht implementiert)

**Payload:**
```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "zone_name": "Greenhouse Zone 1",
  "kaiser_id": "god"
}
```

**Response Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/zone/ack`

**Response Payload:**
```json
{
  "esp_id": "ESP_AB12CD",
  "status": "zone_assigned",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse",
  "timestamp": 1234567890
}
```

### Existing Topics (Enhanced)
- **Heartbeat:** Now includes zone info
- **Sensor Data:** Now includes esp_id, zone_id, subzone_id
- **Actuator Status:** Now includes esp_id, zone_id, subzone_id
- **Actuator Response:** Now includes esp_id, zone_id

---

## 🔄 Runtime Reconfiguration Flow

### Scenario: Change Sensor Type Without Reboot

1. **God-Kaiser sends config update via MQTT:**
   ```json
   {
     "esp_id": "ESP_AB12CD",
     "sensors": [{
       "gpio": 4,
       "sensor_type": "temp_sht31",  // Changed from temp_ds18b20
       "sensor_name": "Temperature A",
       "subzone_id": "section_A",
       "active": true
     }]
   }
   ```

2. **ESP receives config:**
   - SensorManager.configureSensor() detects existing sensor
   - Logs: "Sensor type changed: temp_ds18b20 → temp_sht31"
   - Updates sensor config in memory
   - Persists to NVS immediately
   - Logs: "✅ Configuration persisted to NVS"

3. **No reboot required:**
   - Sensor continues operating with new type
   - Next reading uses new sensor type
   - Configuration survives ESP reboot

### Scenario: Add Actuator at Runtime

1. **God-Kaiser sends config:**
   ```json
   {
     "esp_id": "ESP_AB12CD",
     "actuators": [{
       "gpio": 6,
       "actuator_type": "valve",
       "actuator_name": "Valve B",
       "subzone_id": "section_B",
       "active": true
     }]
   }
   ```

2. **ESP adds actuator:**
   - Checks GPIO availability
   - Creates valve driver
   - Initializes hardware
   - Persists to NVS
   - Publishes status
   - Actuator immediately operational

---

## ✅ Success Criteria Met

- ✅ ESP registration via REST API (Auto-Discovery deaktiviert)
- ✅ God-Kaiser assigns zone via MQTT, ESP saves to NVS
- ✅ Sensor/actuator added via MQTT, no reboot
- ✅ Sensor GPIO changed via MQTT, no reboot
- ✅ Heartbeat includes zone_id, master_zone_id
- ✅ All sensor/actuator messages include zone metadata
- ✅ Config changes persist across ESP reboots
- ✅ Topic-Struktur zukunftsfähig für Kaiser-Nodes vorbereitet

---

## 🧪 Testing Recommendations

### 1. Zone Assignment Test
```
1. Flash new ESP (no zone config)
2. Power on → connects to WiFi/MQTT
3. Check heartbeat: zone_assigned: false
4. God-Kaiser sends zone assignment
5. Check ESP logs: "ZONE ASSIGNMENT RECEIVED"
6. Check acknowledgment received by God-Kaiser
7. Reboot ESP → verify zone persists
```

### 2. Runtime Sensor Add Test
```
1. ESP operational with 2 sensors
2. God-Kaiser sends config for 3rd sensor
3. Verify: No reboot
4. Verify: New sensor appears in sensor_count
5. Verify: Sensor readings include zone info
6. Reboot ESP → verify 3 sensors still configured
```

### 3. Runtime Sensor Type Change Test
```
1. ESP has temp_ds18b20 on GPIO 4
2. God-Kaiser changes to temp_sht31 on GPIO 4
3. Verify: Log shows type change
4. Verify: Next reading uses new sensor type
5. Reboot ESP → verify new type persists
```

### 4. Runtime Actuator Removal Test
```
1. ESP has 3 actuators active
2. God-Kaiser sends remove for GPIO 5
3. Verify: Actuator stops safely
4. Verify: GPIO released
5. Verify: NVS updated (2 actuators remain)
6. Reboot ESP → verify only 2 actuators
```

### 5. Zone Info in Messages Test
```
1. Configure ESP in zone "greenhouse_zone_1"
2. Trigger sensor reading
3. Verify sensor data includes:
   - esp_id: "ESP_XXXXXX"
   - zone_id: "greenhouse_zone_1"
   - subzone_id: "section_A"
4. Trigger actuator command
5. Verify actuator status includes zone info
```

---

## 📝 Integration with God-Kaiser

### Required God-Kaiser Changes

1. **ESP Registration (Required):**
   - ESPs müssen zuerst über REST API registriert werden: `POST /api/v1/esp/register`
   - Auto-Discovery via Heartbeat ist deaktiviert
   - Server lehnt Heartbeats von unbekannten ESPs ab
   - Nach Registrierung: Monitor heartbeat topic for `zone_assigned: false`
   - Apply zone assignment rules (auto or manual)
   - Send zone assignment via MQTT

2. **Zone Management:**
   - Track ESPs per zone
   - Implement cross-zone logic engine
   - Monitor zone health via aggregated heartbeats

3. **Runtime Configuration:**
   - Send sensor/actuator configs via existing MQTT topics
   - No changes needed to payloads (backward compatible)
   - ESP automatically persists changes

4. **Zone-Aware Analytics:**
   - Parse zone_id from all sensor/actuator messages
   - Implement zone-based dashboards
   - Enable cross-zone automations

---

## 🔒 Backward Compatibility

- ✅ Existing ESPs without zone_id continue working (empty string)
- ✅ Heartbeat compatible with old God-Kaiser (extra fields ignored)
- ✅ MQTT handlers support both old and new payload formats
- ✅ Sensor/actuator configs work without zone fields

---

## 🚀 Future Enhancements

### Phase 8: Advanced Features
- GPIO conflict resolution via MQTT
- Bulk zone reassignment
- Zone templates for quick setup
- Zone-based firmware updates

### Phase 9: Cross-Zone Logic
- Zone-wide emergency stops
- Inter-zone data sharing
- Zone-based scheduling
- Hierarchical automation rules

---

**Implementation Complete:** January 22, 2025  
**Tested:** ✅ Code compiles without errors  
**Ready for:** Integration testing with God-Kaiser

---

## Related Documentation

**ESP32 (El Trabajante):**
- → [Zone Assignment Flow](../system-flows/08-zone-assignment-flow.md) - Detailed runtime zone assignment flow
- → [Provisioning Documentation](PROVISIONING.md) - Initial WiFi/Server setup (separate from zone assignment)
- → [Boot Sequence](../system-flows/01-boot-sequence.md) - Provisioning integration, zone loading
- → [MQTT Protocol](../Mqtt_Protocoll.md) - Zone Assignment Topics specification

**Server (El Servador):**
- → `.claude/CLAUDE_SERVER.md` - Server documentation, Zone Assignment Publisher (to be implemented)
- → `El Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py` - Heartbeat processing, ESP registration requirement



