# FINALE PHASEN - ESP32 Pending-Mode Integration

**Version:** 3.1 - ESP32 + Server Analyse kombiniert
**Datum:** 2026-01-18
**Status:** Vollständig validiert gegen El Servador Codebase
**Analyst:** Claude Opus 4.5

---

# 📊 SERVER-ANALYSE ERGEBNISSE (El Servador)

## Bestätigte Server-Infrastruktur

### MQTT Handler System (VOLLSTÄNDIG VORHANDEN)

| Handler | Topic | Status | Code-Location |
|---------|-------|--------|---------------|
| **HeartbeatHandler** | `kaiser/god/esp/{esp_id}/system/heartbeat` | ✅ | `heartbeat_handler.py:55-225` |
| **ErrorEventHandler** | `kaiser/god/esp/{esp_id}/system/error` | ✅ | `error_handler.py:67-233` |
| **SensorHandler** | `kaiser/god/esp/{esp_id}/sensor/{gpio}/data` | ✅ | `sensor_handler.py:78-337` |
| **ActuatorHandler** | `kaiser/god/esp/{esp_id}/actuator/{gpio}/status` | ✅ | `actuator_handler.py:44-96` |
| **ConfigHandler** | `kaiser/god/esp/{esp_id}/config_response` | ✅ | `config_handler.py:76-100` |
| **ZoneAckHandler** | `kaiser/god/esp/{esp_id}/zone/ack` | ✅ | `zone_ack_handler.py:59-100` |

### Device Status System (esp.py:137-187)

```
pending_approval → Neues Gerät nach Auto-Discovery (heartbeat_handler.py:265)
approved         → Admin hat freigegeben (API: POST /devices/{id}/approve)
online           → ESP sendet aktiv Heartbeats (heartbeat_handler.py:156)
offline          → Heartbeat-Timeout > 300s (heartbeat_handler.py:38)
rejected         → Admin hat abgelehnt + 5min Cooldown (heartbeat_handler.py:135-145)
```

### Publisher Commands (publisher.py)

| Methode | Topic | QoS | Zeilen |
|---------|-------|-----|--------|
| `publish_actuator_command()` | `.../actuator/{gpio}/command` | 2 | 64-98 |
| `publish_sensor_command()` | `.../sensor/{gpio}/command` | 1 | 100-145 |
| `publish_config()` | `.../esp/{esp_id}/config` | 2 | 207-267 |
| `publish_system_command()` | `.../system/command` | 2 | 269-312 |
| `publish_pi_enhanced_response()` | `.../sensor/{gpio}/processed` | 1 | 314-348 |

### Error-Handler Trust-Philosophy (error_handler.py:11-16)

> **KRITISCH:** Server TRUSTS ESP32 Hardware Status COMPLETELY!
> - NO re-validation of ESP error codes
> - Error info is for ENRICHMENT only (user messages, troubleshooting)
> - Unknown error codes are stored with generic message

### Error-Handler Payload-Erwartung (error_handler.py:73-81)

```json
{
  "error_code": 1023,            // Required (int)
  "severity": 2,                 // Required (0=INFO, 1=WARNING, 2=ERROR, 3=CRITICAL)
  "category": "HARDWARE",        // Optional (enriched via mapping)
  "message": "...",              // Optional (enriched via mapping)
  "context": {...},              // Optional (ESP-spezifisch)
  "timestamp": 1735818000        // Optional (Unix timestamp)
}
```

### Error-Code Ranges (error_codes.py)

**ESP32 (1000-4999):**
- 1000-1999: HARDWARE (GPIO, I2C, Sensors, Actuators)
- 2000-2999: SERVICE (NVS, Config, Storage)
- 3000-3999: COMMUNICATION (WiFi, MQTT, HTTP)
- 4000-4999: APPLICATION (State, Operations, Commands)

**Server (5000-5999):**
- 5000-5099: CONFIG_ERROR
- 5100-5199: MQTT_ERROR
- 5200-5299: VALIDATION_ERROR
- 5300-5399: DATABASE_ERROR
- 5400-5499: SERVICE_ERROR
- 5500-5599: AUDIT_ERROR
- 5600-5699: SEQUENCE_ERROR

**⚠️ LÜCKE:** Diagnostics-Error-Codes 4100-4199 fehlen!

---

## ⚠️ BESTÄTIGTER BUG: Route-Ordering (KRITISCH)

**Problem:** FastAPI Route-Ordering verursacht 404 für `/devices/pending`

**Analyse (esp.py):**
```
Zeile 201:  @router.get("/devices/{esp_id}")     ← Wildcard matched ALLES!
Zeile 1076: @router.get("/devices/pending")      ← Wird NIE erreicht!
```

**Request: `GET /api/v1/esp/devices/pending`**
1. FastAPI matched `{esp_id}` = "pending"
2. Sucht Device mit ID "pending" in DB
3. Findet nichts → 404 Not Found

**Fix:** Spezifische Route `/devices/pending` MUSS VOR Wildcard `/{esp_id}` stehen!

---

## Heartbeat-Payload Verarbeitung (heartbeat_handler.py:60-73)

**Was der Server vom ESP erwartet:**
```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "master_zone_id": "master",
  "zone_assigned": true,
  "ts": 1735818000,
  "uptime": 123456,
  "heap_free": 45000,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 2,
  "gpio_status": [...]
}
```

**Was der Server speichert (device_metadata):**
```json
{
  "discovery_source": "heartbeat",
  "heartbeat_count": 42,
  "initial_heap_free": 98304,
  "initial_wifi_rssi": -45,
  "last_heap_free": 45000,
  "last_wifi_rssi": -45,
  "gpio_status": [...],
  "gpio_reserved_count": 5
}
```

---

### WebSocket Broadcasts (für Frontend Live-Updates)

| Event | Handler | Daten |
|-------|---------|-------|
| `esp_health` | heartbeat_handler.py:196-208 | status, heap_free, wifi_rssi, uptime |
| `error_event` | error_handler.py:190-211 | error_code, severity, troubleshooting |
| `sensor_data` | sensor_handler.py:286-294 | value, gpio, sensor_type |
| `device_discovered` | heartbeat_handler.py:422-431 | device_id, timestamp |
| `actuator_status` | actuator_handler.py | state, value, runtime_ms |

---

## 📊 ESP32-ANALYSE ZUSAMMENFASSUNG

### Was bereits implementiert ist (✅)

| Feature | Status | Code-Location |
|---------|--------|---------------|
| **ErrorTracker MQTT Publishing** | ✅ EXISTIERT | [error_tracker.cpp:280-321](El Trabajante/src/error_handling/error_tracker.cpp#L280-L321) |
| **MQTT Callback-System** | ✅ EXISTIERT | [main.cpp:90-96](El Trabajante/src/main.cpp#L90-L96) |
| **Offline-Queue (100 msg)** | ✅ EXISTIERT | [mqtt_client.cpp:779-795](El Trabajante/src/services/communication/mqtt_client.cpp#L779-L795) |
| **HealthMonitor Diagnostics** | ✅ EXISTIERT | [health_monitor.cpp:200-239](El Trabajante/src/error_handling/health_monitor.cpp#L200-L239) |
| **Watchdog 3-Mode-System** | ✅ EXISTIERT | [main.cpp:1381-1434](El Trabajante/src/main.cpp#L1381-L1434) |
| **Early-Return Pattern (loop)** | ✅ EXISTIERT | [main.cpp:1541-1570](El Trabajante/src/main.cpp#L1541-L1570) |

### Was fehlt und implementiert werden muss (❌)

| Feature | Status | Beschreibung |
|---------|--------|--------------|
| **STATE_PENDING_APPROVAL** | ❌ FEHLT | Neuer SystemState muss hinzugefügt werden |
| **TopicBuilder.buildErrorTopic()** | ❌ FEHLT | Error-Topic ist in ErrorTracker hardcoded |
| **Heartbeat-ACK Handling** | ❌ FEHLT | ESP empfängt keine Server-ACKs |
| **Pending-Mode Loop-Logic** | ❌ FEHLT | Limitierter Betrieb bei pending |
| **Server-Status Subscription** | ❌ FEHLT | ESP weiß nicht ob es "approved" ist |

### Bugs/Inkonsistenzen gefunden (⚠️)

| Issue | Location | Problem |
|-------|----------|---------|
| **Kaiser-ID hardcoded** | [error_tracker.cpp:295](El Trabajante/src/error_handling/error_tracker.cpp#L295) | `"kaiser/god/esp/"` statt TopicBuilder |
| **Timestamp millis() statt Unix** | [error_tracker.cpp:313](El Trabajante/src/error_handling/error_tracker.cpp#L313) | Server erwartet Unix-Timestamp |
| **Kein Context-Objekt** | [error_tracker.cpp:298-314](El Trabajante/src/error_handling/error_tracker.cpp#L298-L314) | Plan sah `context` Feld vor, fehlt |

---

# PHASE 0: Bug-Fixes (MUSS zuerst!)

**Ziel:** Bestehenden Code konsistent machen bevor neue Features

## Phase 0A: ErrorTracker Topic über TopicBuilder (P0 - 15 min)

### Problem
Error-Topic ist hardcoded in [error_tracker.cpp:295](El Trabajante/src/error_handling/error_tracker.cpp#L295):
```cpp
String topic = "kaiser/god/esp/" + mqtt_esp_id_ + "/system/error";
// Problem: "god" ist hardcoded, sollte aus TopicBuilder kommen!
```

### Lösung

**Schritt 1: TopicBuilder erweitern**

**Datei:** `El Trabajante/src/utils/topic_builder.h` - nach Zeile 38 hinzufügen:
```cpp
// Error Topic (Phase 0A: Konsistenz-Fix)
static const char* buildErrorTopic();
```

**Datei:** `El Trabajante/src/utils/topic_builder.cpp` - nach Zeile 208 hinzufügen:
```cpp
// Error Topic - Pattern: kaiser/{kaiser_id}/esp/{esp_id}/system/error
const char* TopicBuilder::buildErrorTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/error",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}
```

**Schritt 2: ErrorTracker anpassen**

**Datei:** `El Trabajante/src/error_handling/error_tracker.cpp`

**Zeile 2 hinzufügen:**
```cpp
#include "utils/topic_builder.h"
```

**Zeile 295 ersetzen:**
```cpp
// ALT:
String topic = "kaiser/god/esp/" + mqtt_esp_id_ + "/system/error";

// NEU:
String topic = String(TopicBuilder::buildErrorTopic());
```

**Schritt 3: Timestamp auf Unix-Format ändern**

**Zeile 312-313 ersetzen:**
```cpp
// ALT:
payload += "\",\"ts\":";
payload += String(millis());

// NEU: Unix-Timestamp für Server-Kompatibilität
payload += "\",\"ts\":";
payload += String(timeManager.getUnixTimestamp());
```

**Hinweis:** `timeManager` ist bereits global verfügbar (siehe mqtt_client.cpp:617)

### Verifikation
```bash
# Nach Build: MQTT-Traffic prüfen
mosquitto_sub -h localhost -t "kaiser/+/esp/+/system/error" -v

# Erwartetes Topic-Format:
# kaiser/god/esp/ESP_12AB34CD/system/error
# (nicht mehr hardcoded "god")
```

---

## Phase 0B: ErrorTracker Context-Feld hinzufügen (P1 - 20 min)

### Problem
Server-Handler erwartet `context` Feld ([error_handler.py:73-81](El Servador/god_kaiser_server/src/mqtt/handlers/error_handler.py#L73-L81)), aber ESP sendet es nicht.

### Lösung

**Datei:** `El Trabajante/src/error_handling/error_tracker.h`

**Zeile 130 (publishErrorToMqtt Signatur) ändern:**
```cpp
// ALT:
void publishErrorToMqtt(uint16_t error_code, ErrorSeverity severity, const char* message);

// NEU: Optional context parameter
void publishErrorToMqtt(
  uint16_t error_code,
  ErrorSeverity severity,
  const char* message,
  const char* context_json = nullptr  // Optional: zusätzlicher Context
);
```

**Datei:** `El Trabajante/src/error_handling/error_tracker.cpp`

**Zeile 280 Signatur ändern:**
```cpp
void ErrorTracker::publishErrorToMqtt(
  uint16_t error_code,
  ErrorSeverity severity,
  const char* message,
  const char* context_json
) {
```

**Nach Zeile 313 (vor `payload += "}";`) einfügen:**
```cpp
  // Optional context field
  if (context_json != nullptr && strlen(context_json) > 0) {
    payload += ",\"context\":";
    payload += context_json;  // Bereits formatiertes JSON
  } else {
    // Default context mit Basis-Diagnostics
    payload += ",\"context\":{\"heap_free\":";
    payload += String(ESP.getFreeHeap());
    payload += ",\"uptime_ms\":";
    payload += String(millis());
    payload += "}";
  }
```

### Verwendungsbeispiel
```cpp
// Mit explizitem Context:
char context[100];
snprintf(context, sizeof(context),
         "{\"gpio\":%d,\"value\":%.2f}", gpio, value);
errorTracker.publishErrorToMqtt(1040, ERROR_SEVERITY_ERROR,
                                 "Sensor read failed", context);

// Ohne Context (nutzt Default):
errorTracker.publishErrorToMqtt(3011, ERROR_SEVERITY_ERROR,
                                 "MQTT connection failed");
```

---

# PHASE 1: STATE_PENDING_APPROVAL Implementation

**Ziel:** Neuen SystemState einführen für Server-Approval-Flow

## Phase 1A: SystemState erweitern (P0 - 10 min)

### Problem
Es gibt keinen State für "Warte auf Server-Genehmigung":
```cpp
// system_types.h:9-23 - aktuelle States:
enum SystemState {
  STATE_BOOT = 0,
  STATE_WIFI_SETUP,
  // ...
  STATE_OPERATIONAL,          // Zeile 18
  // ...
  STATE_SAFE_MODE_PROVISIONING,  // Zeile 21
  STATE_ERROR                    // Zeile 22
};
```

### Lösung

**Datei:** `El Trabajante/src/models/system_types.h`

**Zeile 18-19 erweitern (nach STATE_OPERATIONAL, vor STATE_LIBRARY_DOWNLOADING):**
```cpp
  STATE_OPERATIONAL,
  STATE_PENDING_APPROVAL,           // ✅ NEU: Warte auf Server-Genehmigung
  STATE_LIBRARY_DOWNLOADING,        // ⚠️ OPTIONAL - nur für OTA Library Mode (10%)
```

**getSystemStateString() in health_monitor.cpp erweitern (Zeile 220-234):**
```cpp
case STATE_PENDING_APPROVAL:
  state_str = "PENDING_APPROVAL";
  break;
```

---

## Phase 1B: Pending-Mode Loop-Logic (P0 - 1h)

### Design-Entscheidung nach Robin's Anforderung

> "Der esp braucht nicht jedesmal eine rückantwort vom Server, er kann sie bekommen es sollte aber keine Prozesse behindern."

**Pending-Mode Verhalten:**
- ✅ WiFi aufrechterhalten
- ✅ MQTT aufrechterhalten
- ✅ Heartbeat weiter senden
- ✅ Health-Diagnostics weiter senden
- ✅ Error-Events weiter senden
- ❌ Sensoren NICHT auslesen (Server ignoriert ohne Approval)
- ❌ Aktoren NICHT steuern (nicht freigegeben)
- ✅ Watchdog NICHT triggern (ESP ist funktional!)

### Implementation

**Datei:** `El Trabajante/src/main.cpp`

**Zeile 1541-1570 erweitern (nach STATE_SAFE_MODE_PROVISIONING Check):**

```cpp
void loop() {
  // ============================================
  // PHASE 0: WATCHDOG FEED (immer, außer bei Error)
  // ============================================
  feedWatchdog("MAIN_LOOP");                     // Zeile 1521

  // ============================================
  // STATE: SAFE_MODE_PROVISIONING (bestehend)
  // ============================================
  if (g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING) {
    provisionManager.loop();
    if (provisionManager.isConfigReceived()) {
      ESP.restart();
    }
    delay(100);
    return;
  }

  // ============================================
  // STATE: PENDING_APPROVAL (NEU - Phase 1B)
  // ============================================
  if (g_system_config.current_state == STATE_PENDING_APPROVAL) {
    // LIMITIERTER BETRIEB
    // ✅ WiFi/MQTT aufrecht erhalten (für Heartbeat + ACK)
    wifiManager.loop();
    mqttClient.loop();

    // ✅ Health-Monitoring (Server sieht dass ESP pending ist)
    healthMonitor.loop();

    // ❌ KEINE Sensor-Messungen (Server ignoriert eh)
    // ❌ KEINE Aktor-Steuerung (nicht freigegeben)

    // ✅ Watchdog wird NICHT blockiert (ESP ist funktional)
    // feedWatchdog wurde oben bereits aufgerufen

    delay(100);  // Reduzierte CPU-Last im Pending-Mode
    return;
  }

  // ============================================
  // STATE: NORMAL OPERATION (bestehend)
  // ============================================
  wifiManager.loop();                            // Zeile 1586
  mqttClient.loop();                             // Zeile 1587
  sensorManager.performAllMeasurements();        // Zeile 1590
  actuatorManager.processActuatorLoops();        // Zeile 1593
  healthMonitor.loop();                          // Zeile 1603

  delay(10);                                     // Zeile 1605
}
```

### Wann wird STATE_PENDING_APPROVAL gesetzt?

**Option A: Bei erstmaligem MQTT-Connect (Discovery-Flow)**

**Datei:** `El Trabajante/src/main.cpp` - in setup() nach MQTT-Connect (ca. Zeile 670-700)

```cpp
// Nach erfolgreichem MQTT-Connect prüfen ob ESP bereits approved ist
if (mqttClient.isConnected()) {
  // Prüfe NVS ob ESP bereits approved wurde
  bool was_approved = configManager.wasDeviceApproved();

  if (!was_approved) {
    // Erstmaliger Connect: Warte auf Server-Approval
    g_system_config.current_state = STATE_PENDING_APPROVAL;
    configManager.saveSystemConfig(g_system_config);
    LOG_INFO("Device pending approval - waiting for server confirmation");
  } else {
    // Bereits approved: Direkt zu OPERATIONAL
    g_system_config.current_state = STATE_OPERATIONAL;
  }
}
```

**Option B: Server sendet Status via Heartbeat-ACK (empfohlen)**

Siehe Phase 2 - Server teilt ESP mit ob es approved ist.

---

## Phase 1C: Approval-Status Persistierung (P1 - 30 min)

### NVS-Keys erweitern

**Datei:** `El Trabajante/src/services/config/config_manager.h`

```cpp
// In public section hinzufügen:
bool wasDeviceApproved() const;
void setDeviceApproved(bool approved);
```

**Datei:** `El Trabajante/src/services/config/config_manager.cpp`

```cpp
// NVS-Key Konstante (Namespace: "system")
const char* NVS_KEY_DEVICE_APPROVED = "dev_approved";

bool ConfigManager::wasDeviceApproved() const {
  bool approved = false;
  storage_manager_.getBool(NVS_KEY_DEVICE_APPROVED, approved);
  return approved;
}

void ConfigManager::setDeviceApproved(bool approved) {
  storage_manager_.setBool(NVS_KEY_DEVICE_APPROVED, approved);
  LOG_INFO("Device approval status saved: " + String(approved ? "APPROVED" : "PENDING"));
}
```

**NVS_KEYS.md aktualisieren:**
```markdown
| dev_approved | bool | Device Approval Status (Server-confirmed) |
```

---

# PHASE 2: Server-Communication für Approval

**Ziel:** ESP erfährt vom Server ob es approved ist

## Phase 2A: Heartbeat-ACK Subscription (P1 - 45 min)

### Problem
ESP sendet Heartbeat, aber empfängt keine Antwort vom Server.

### Lösung: Subscription zu Heartbeat-ACK Topic

**Datei:** `El Trabajante/src/utils/topic_builder.h` - nach Zeile 26 hinzufügen:
```cpp
// Heartbeat ACK Topic (Phase 2A: Server → ESP)
static const char* buildHeartbeatAckTopic();
```

**Datei:** `El Trabajante/src/utils/topic_builder.cpp` - nach buildSystemHeartbeatTopic():
```cpp
const char* TopicBuilder::buildHeartbeatAckTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/heartbeat/ack",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}
```

**Datei:** `El Trabajante/src/main.cpp` - Zeile 730-741 (Subscriptions) erweitern:

```cpp
// Bestehende Subscriptions...
mqttClient.subscribe(TopicBuilder::buildConfigTopic());
mqttClient.subscribe(TopicBuilder::buildSystemCommandTopic());
// ...

// NEU: Heartbeat-ACK (Server → ESP)
mqttClient.subscribe(TopicBuilder::buildHeartbeatAckTopic());
LOG_INFO("Subscribed to heartbeat ACK topic");
```

---

## Phase 2B: Heartbeat-ACK Handler (P1 - 45 min)

### Server-Payload Erwartung
```json
{
  "status": "pending_approval" | "approved" | "online" | "rejected",
  "config_available": true | false,
  "server_time": 1705056000
}
```

### ESP-Handler Implementation

**Datei:** `El Trabajante/src/main.cpp` - in MQTT Callback (ca. Zeile 743-889)

```cpp
// In der Lambda-Funktion mqttClient.setCallback() hinzufügen:

// Heartbeat-ACK Handler (Phase 2B)
String heartbeat_ack_topic = String(TopicBuilder::buildHeartbeatAckTopic());
if (topic == heartbeat_ack_topic) {
  handleHeartbeatAck(payload);
  return;
}
```

**Neue Funktion hinzufügen (vor loop()):**

```cpp
// ============================================
// Heartbeat-ACK Handler (Phase 2B)
// ============================================
void handleHeartbeatAck(const String& payload) {
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, payload);

  if (error) {
    LOG_WARNING("Heartbeat ACK parse error: " + String(error.c_str()));
    return;
  }

  const char* status = doc["status"] | "unknown";
  bool config_available = doc["config_available"] | false;

  LOG_DEBUG("Heartbeat ACK received - Status: " + String(status));

  // ============================================
  // Status-basierte State-Transitions
  // ============================================

  if (strcmp(status, "approved") == 0 || strcmp(status, "online") == 0) {
    // ✅ Server hat ESP genehmigt!
    if (g_system_config.current_state == STATE_PENDING_APPROVAL) {
      LOG_INFO("Device APPROVED by server - transitioning to OPERATIONAL");

      // Approval persistieren
      configManager.setDeviceApproved(true);

      // State-Transition
      g_system_config.current_state = STATE_OPERATIONAL;
      configManager.saveSystemConfig(g_system_config);

      // Optional: Config anfordern wenn verfügbar
      if (config_available) {
        LOG_INFO("Server has config available - will receive via config topic");
      }
    }
  }
  else if (strcmp(status, "pending_approval") == 0) {
    // ⏳ ESP noch nicht genehmigt
    if (g_system_config.current_state != STATE_PENDING_APPROVAL) {
      LOG_INFO("Device status: PENDING APPROVAL");
      g_system_config.current_state = STATE_PENDING_APPROVAL;
      // NICHT in NVS speichern - temporärer Zustand
    }
  }
  else if (strcmp(status, "rejected") == 0) {
    // ❌ ESP wurde abgelehnt
    LOG_WARNING("Device REJECTED by server!");
    errorTracker.trackError(ERROR_DEVICE_REJECTED, ERROR_SEVERITY_ERROR,
                            "Device rejected by server");

    // Optional: In Safe-Mode gehen oder Retry-Logic
    g_system_config.current_state = STATE_ERROR;
    configManager.saveSystemConfig(g_system_config);
  }
}
```

### Neuen Error-Code definieren

**Datei:** `El Trabajante/src/models/error_codes.h` - Application Errors (4000er):

```cpp
// Application Errors: Device Discovery (4200-4209)
#define ERROR_DEVICE_REJECTED       4200  // Device rejected by server
#define ERROR_APPROVAL_TIMEOUT      4201  // Timeout waiting for approval
```

---

## Phase 2C: Server-Side Heartbeat-ACK Implementation (P1)

### Problem
Server sendet aktuell KEINE Heartbeat-ACKs.

### Lösung

**Datei:** `El Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py`

**Nach Zeile 220 (nach DB-Commit) hinzufügen:**

```python
# ============================================
# Phase 2C: Optional Heartbeat-ACK senden
# ============================================
await self._send_heartbeat_ack(
    esp_id=esp_id_str,
    status=esp_device.status,
    config_available=await self._has_pending_config(esp_device)
)
```

**Neue Methode in HeartbeatHandler hinzufügen:**

```python
async def _send_heartbeat_ack(
    self,
    esp_id: str,
    status: str,
    config_available: bool = False
) -> None:
    """
    Send optional heartbeat ACK to ESP.

    ESP wartet NICHT darauf - Fire-and-Forget Pattern!
    QoS 0 da nicht kritisch.
    """
    topic = f"kaiser/god/esp/{esp_id}/system/heartbeat/ack"

    payload = {
        "status": status,  # "pending_approval", "approved", "online", etc.
        "config_available": config_available,
        "server_time": int(datetime.now(timezone.utc).timestamp())
    }

    # QoS 0 = Fire-and-Forget (ESP blockiert nicht darauf!)
    await self.mqtt_publisher.publish(topic, json.dumps(payload), qos=0)

    self.logger.debug(f"Heartbeat ACK sent to {esp_id}: {status}")

async def _has_pending_config(self, esp_device) -> bool:
    """Check if server has unsent config for this ESP."""
    # TODO: Implementieren wenn Config-Push-System existiert
    return False
```

---

# PHASE 3: Server Route-Fix & Frontend

**Ziel:** Server-Bug fixen + Frontend für Pending-Devices

## Phase 3A: Route-Ordering-Bug Fix (P0 - 5 min!)

### Problem
Route-Ordering-Bug in FastAPI verursacht 404 für `/devices/pending`:

```python
# PROBLEM in esp.py:
@router.get("/devices/{esp_id}")           # Zeile 200 - Matched ALLES!
async def get_device(...):

@router.get("/devices/pending")            # Zeile 1076 - Wird nie erreicht!
async def list_pending_devices(...):
```

### Lösung

**Datei:** `El Servador/god_kaiser_server/src/api/v1/esp.py`

**Route-Reihenfolge ändern:**

1. Finde `@router.get("/devices/pending")` (aktuell ca. Zeile 1076)
2. VERSCHIEBE die komplette Funktion VOR `@router.get("/devices/{esp_id}")`

```python
# RICHTIGE REIHENFOLGE:
@router.get("/devices/pending")            # ← ZUERST spezifische Route!
async def list_pending_devices(...):
    ...

@router.get("/devices/{esp_id}")           # ← DANN Wildcard-Route!
async def get_device(...):
    ...
```

### Verifikation
```bash
curl http://localhost:8000/api/v1/esp/devices/pending
# Sollte: 200 OK mit Liste der pending devices
```

---

## Phase 3B: Frontend Pending-Devices (BEREITS IMPLEMENTIERT! ✅)

### Was bereits existiert (keine Arbeit nötig):

| Komponente | Status | Beschreibung |
|------------|--------|--------------|
| **PendingDevicesPanel.vue** | ✅ VOLLSTÄNDIG | Popover mit Approve/Reject, Signal-Stärke, TimeAgo |
| **ActionBar.vue** | ✅ VOLLSTÄNDIG | Iridescent Button wenn `pendingCount > 0` |
| **esp.ts Store** | ✅ VOLLSTÄNDIG | `fetchPendingDevices()`, `approveDevice()`, `rejectDevice()` |
| **esp.ts API** | ✅ VOLLSTÄNDIG | `getPendingDevices()`, `approveDevice()`, `rejectDevice()` |
| **WebSocket Events** | ✅ VOLLSTÄNDIG | `device_discovered`, `device_approved`, `device_rejected` Handler |
| **types/index.ts** | ✅ VOLLSTÄNDIG | `PendingESPDevice`, `ESPApprovalRequest`, etc. |
| **useToast.ts** | ✅ VOLLSTÄNDIG | Toast mit Actions-Support |
| **DashboardView.vue** | ✅ VOLLSTÄNDIG | `showPendingDevices` State, Event-Binding |

**Referenz-Dateien:**
- `El Frontend/src/components/esp/PendingDevicesPanel.vue` (484 Zeilen, vollständig)
- `El Frontend/src/components/dashboard/ActionBar.vue` (Zeilen 105-114 + 169-262 CSS)
- `El Frontend/src/stores/esp.ts` (Zeilen 685-760: pending actions, 1821-1860: WS handlers)
- `El Frontend/src/api/esp.ts` (Zeilen 661-703: API methods)

---

## Phase 3C: ESPCard Status-Badge erweitern (P1 - 1h) ⚠️ MUSS IMPLEMENTIERT WERDEN

### Problem
ESPCard.vue kennt keinen `pending_approval` Status:

```typescript
// ESPCard.vue:247-257 (AKTUELL):
const stateInfo = computed(() => {
  const status = connectionStatus.value
  if (status === 'online') {
    return { label: 'Online', variant: 'success' }
  } else if (status === 'offline') {
    return { label: 'Offline', variant: 'gray' }
  } else if (status === 'error') {
    return { label: 'Fehler', variant: 'danger' }
  }
  return { label: 'Unbekannt', variant: 'gray' }  // ← Pending wird als "Unbekannt" angezeigt!
})
```

### Lösung

**Datei:** `El Frontend/src/components/esp/ESPCard.vue`

**Schritt 1: connectionStatus computed erweitern (ca. Zeile 234)**

```typescript
const connectionStatus = computed(() => {
  // Pending-Status hat Vorrang (vor online/offline)
  if (props.esp.status === 'pending_approval') return 'pending'
  if (props.esp.status === 'approved') return 'approved'
  if (props.esp.status === 'rejected') return 'rejected'

  // Bestehende Logik
  if (props.esp.connected === true || props.esp.status === 'online') return 'online'
  if (props.esp.system_state === 'ERROR') return 'error'
  if (props.esp.connected === false || props.esp.status === 'offline') return 'offline'
  return 'unknown'
})
```

**Schritt 2: stateInfo computed erweitern (ca. Zeile 247)**

```typescript
const stateInfo = computed(() => {
  const status = connectionStatus.value

  const statusMap: Record<string, { label: string; variant: string }> = {
    pending: { label: 'Wartet auf Freigabe', variant: 'warning' },
    approved: { label: 'Freigegeben', variant: 'info' },
    rejected: { label: 'Abgelehnt', variant: 'danger' },
    online: { label: 'Online', variant: 'success' },
    offline: { label: 'Offline', variant: 'gray' },
    error: { label: 'Fehler', variant: 'danger' },
  }

  return statusMap[status] ?? { label: 'Unbekannt', variant: 'gray' }
})
```

**Schritt 3: Optional - Inline Approve-Button in ESPCard**

Falls Pending-Devices auch im OrbitalLayout angezeigt werden sollen:

```vue
<!-- Nach Status-Badge, nur für pending Status -->
<div
  v-if="esp.status === 'pending_approval'"
  class="esp-card__pending-actions"
>
  <button
    class="esp-card__approve-btn"
    @click.stop="handleApprove"
  >
    <Check class="w-4 h-4" />
    <span>Freigeben</span>
  </button>
</div>
```

```typescript
// Script
import { Check } from 'lucide-vue-next'

async function handleApprove() {
  const toast = useToast()
  try {
    await espStore.approveDevice(getDeviceId(props.esp))
    toast.success(`${props.esp.name || getDeviceId(props.esp)} freigegeben`)
  } catch (err) {
    toast.error('Freigabe fehlgeschlagen')
  }
}
```

### Architektur-Entscheidung

**Frage:** Sollen Pending-Devices im ESPOrbitalLayout angezeigt werden?

**Option A (Empfohlen): Nur im PendingDevicesPanel**
- ✅ Klare Trennung: Panel = Warteschlange, OrbitalLayout = genehmigte Geräte
- ✅ Bereits vollständig implementiert
- ✅ Weniger UI-Clutter

**Option B: Auch im OrbitalLayout mit speziellem Styling**
- ⚠️ Erfordert Filter-Änderung in DashboardView
- ⚠️ Mehr visuelle Komplexität

**Empfehlung:** Option A beibehalten. Das PendingDevicesPanel ist bereits gut implementiert.

---

# 🖥️ FRONTEND PATTERNS-REFERENZ

## Toast-Verwendung (useToast.ts)

```typescript
import { useToast } from '@/composables/useToast'

const toast = useToast()

// Einfache Toasts
toast.success('Gerät freigegeben')
toast.error('Freigabe fehlgeschlagen')
toast.warning('Verbindung verloren')
toast.info('Neues Gerät entdeckt')

// Mit Action-Button
toast.info('Neues Gerät gefunden', {
  actions: [{
    label: 'Freigeben',
    onClick: () => approveDevice(deviceId)
  }]
})

// Persistent (kein Auto-Dismiss)
toast.error('Kritischer Fehler', { persistent: true })
```

## ESP Store Actions (esp.ts)

```typescript
import { useEspStore } from '@/stores/esp'

const espStore = useEspStore()

// Pending Device Actions
await espStore.fetchPendingDevices()
await espStore.approveDevice(deviceId, { name, zone_id })
await espStore.rejectDevice(deviceId, reason)

// Computed
espStore.pendingDevices      // PendingESPDevice[]
espStore.pendingCount        // number
espStore.isPendingLoading    // boolean
```

## Badge Variants (Badge.vue)

| Variant | Farbe | Verwendung |
|---------|-------|------------|
| `success` | Grün | Online, Approved |
| `warning` | Gelb | Pending, Warning |
| `danger` | Rot | Error, Rejected |
| `info` | Blau | Info-Status |
| `gray` | Grau | Offline, Unknown |

## WebSocket Event Types

```typescript
// In esp.ts bereits konfiguriert:
const ws = useWebSocket({
  filters: {
    types: [
      'esp_health',
      'sensor_data',
      'actuator_status',
      'device_discovered',    // ← NEU: Pending
      'device_approved',      // ← NEU: Approved
      'device_rejected',      // ← NEU: Rejected
      // ...
    ]
  }
})
```

---

# 🎯 KORRIGIERTE IMPLEMENTATIONS-REIHENFOLGE

| # | Phase | Aufgabe | Status | Aufwand |
|---|-------|---------|--------|---------|
| 1 | **3A** | Server Route-Ordering-Bug Fix | 🔴 **KRITISCH** | 5 min |
| 2 | **3C** | ESPCard Status-Badge erweitern | 🔴 **KRITISCH** | 45 min |
| 3 | **0A** | TopicBuilder.buildErrorTopic() + ErrorTracker Fix | 🟡 Bug-Fix | 15 min |
| 4 | **0B** | ErrorTracker Context-Feld + Unix-Timestamp | 🟡 Konsistenz | 20 min |
| 5 | **1A** | STATE_PENDING_APPROVAL zu SystemState | 🟡 ESP32 | 10 min |
| 6 | **1B** | Pending-Mode Loop-Logic | 🟡 ESP32 | 1h |
| 7 | **1C** | Approval-Status NVS Persistierung | 🟡 ESP32 | 30 min |
| 8 | **2A** | Heartbeat-ACK Topic + Subscription | 🟢 Optional | 45 min |
| 9 | **2B** | Heartbeat-ACK Handler | 🟢 Optional | 45 min |
| 10 | **2C** | Server Heartbeat-ACK Implementation | 🟢 Optional | 30 min |
| ~~11~~ | ~~**3B**~~ | ~~Frontend Pending-Devices Panel~~ | ✅ **BEREITS FERTIG** | 0 min |

**Gesamt geschätzt:** ~5h 25min (stark reduziert - Frontend ist bereits 80% fertig!)

### Schnellster Weg zum funktionierenden System:

1. **Phase 3A** (5 min) - Server Route-Fix → API funktioniert
2. **Phase 3C** (45 min) - ESPCard Status-Badge → UI zeigt pending korrekt

**Das reicht bereits für ein funktionierendes Pending-Device-System!**
Die ESP32-seitigen Änderungen (Phase 0-2) sind für erweiterte Funktionalität.

---

# ✅ CODE-QUALITY CHECKLISTE

## Patterns die eingehalten werden MÜSSEN

- [ ] **Singleton-Pattern:** Alle Manager über `::getInstance()` zugreifen
- [ ] **TopicBuilder verwenden:** NIEMALS Topics hardcoden
- [ ] **ErrorTracker für Fehler:** NIEMALS direkt loggen ohne Tracking
- [ ] **Error-Codes aus error_codes.h:** NIEMALS Magic Numbers
- [ ] **State-Changes in NVS:** IMMER `configManager.saveSystemConfig()` aufrufen
- [ ] **Loop Early-Return:** IMMER delay() vor return in special states
- [ ] **Watchdog-Feeding:** IMMER am Anfang von loop() (außer bei blocked states)

## Verifikations-Checkliste

### Phase 0 (Bug-Fixes)
- [ ] TopicBuilder.buildErrorTopic() kompiliert
- [ ] ErrorTracker nutzt TopicBuilder (kein hardcoded "god")
- [ ] Error-Payload enthält `context` Feld
- [ ] Error-Payload enthält Unix-Timestamp (nicht millis)

### Phase 1 (STATE_PENDING_APPROVAL)
- [ ] SystemState enum enthält STATE_PENDING_APPROVAL
- [ ] getSystemStateString() gibt "PENDING_APPROVAL" zurück
- [ ] loop() hat early-return für STATE_PENDING_APPROVAL
- [ ] WiFi/MQTT laufen weiter im Pending-Mode
- [ ] Sensoren/Aktoren sind DEAKTIVIERT im Pending-Mode
- [ ] Watchdog triggert NICHT im Pending-Mode
- [ ] Approval-Status wird in NVS persistiert

### Phase 2 (Server-Communication)
- [ ] ESP subscribed zu heartbeat/ack Topic
- [ ] Heartbeat-ACK Handler parsed JSON korrekt
- [ ] State-Transition zu OPERATIONAL bei "approved"
- [ ] Server sendet Heartbeat-ACKs nach jedem Heartbeat

### Phase 3 (Server + Frontend)
- [ ] `/devices/pending` gibt 200 OK (Phase 3A Route-Fix)
- [ ] Frontend kann Pending-Devices laden
- [ ] Approve-Button funktioniert
- [ ] ESPCard zeigt "Wartet auf Freigabe" statt "Unbekannt" (Phase 3C)
- [ ] Badge-Variant ist `warning` (gelb) für pending

---

# 📚 REFERENZEN

## ESP32 Code-Locations

| Modul | Header | Implementation |
|-------|--------|----------------|
| ErrorTracker | `src/error_handling/error_tracker.h` | `error_tracker.cpp` |
| HealthMonitor | `src/error_handling/health_monitor.h` | `health_monitor.cpp` |
| MQTTClient | `src/services/communication/mqtt_client.h` | `mqtt_client.cpp` |
| TopicBuilder | `src/utils/topic_builder.h` | `topic_builder.cpp` |
| ConfigManager | `src/services/config/config_manager.h` | `config_manager.cpp` |
| SystemTypes | `src/models/system_types.h` | - |
| ErrorCodes | `src/models/error_codes.h` | - |

## Server Code-Locations

| Modul | Datei |
|-------|-------|
| Heartbeat Handler | `src/mqtt/handlers/heartbeat_handler.py` |
| ESP API | `src/api/v1/esp.py` |
| Error Handler | `src/mqtt/handlers/error_handler.py` |

## Dokumentation

| Thema | Datei |
|-------|-------|
| MQTT-Protokoll | `El Trabajante/docs/Mqtt_Protocoll.md` |
| NVS-Keys | `El Trabajante/docs/NVS_KEYS.md` |
| API-Referenz | `El Trabajante/docs/API_REFERENCE.md` |
| Server-Doku | `.claude/CLAUDE_SERVER.md` |

---

**Erstellt:** 2026-01-18 nach gründlicher Codebase-Analyse
**Letzte Aktualisierung:** Version 3.1 - Mit vollständiger Frontend-Analyse

---

## Änderungshistorie

| Version | Datum | Änderungen |
|---------|-------|------------|
| 3.1 | 2026-01-18 | Frontend-Analyse hinzugefügt, Phase 3B als bereits implementiert markiert, Phase 3C (ESPCard Status-Badge) hinzugefügt, Pattern-Referenzen erweitert |
| 3.0 | 2026-01-18 | Server-Analyse integriert, Route-Bug bestätigt, Heartbeat-Payload dokumentiert |
| 2.0 | 2026-01-17 | Initiale Pattern-konforme Version |
