# ESP32 Anmeldeprozess - Vollständige Analyse

**Analysiert:** 2026-01-23
**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓
**Firmware-Version:** v4.0 (Phase 2)
**Analyst:** KI-Agent Claude
**Codebase:** El Trabajante (~13.300 Zeilen)

---

## 1. Executive Summary

### Kurze Zusammenfassung des Flows
Der ESP32-Anmeldeprozess im AutomationOne-Framework ist ein mehrstufiger Workflow:

1. **Boot** → Serial init, GPIO Safe-Mode, NVS laden
2. **WiFi** → Verbindung mit konfigurierten Credentials (oder AP-Mode für Provisioning)
3. **MQTT** → Verbindung zum God-Kaiser Server mit Last-Will Testament
4. **Heartbeat** → Erster Heartbeat triggert Server-Registrierung
5. **Approval-Check** → Entweder `STATE_PENDING_APPROVAL` oder `STATE_OPERATIONAL`
6. **ACK-Empfang** → Server sendet Heartbeat-ACK mit Approval-Status
7. **State-Transition** → `PENDING_APPROVAL` → `OPERATIONAL` (ohne Reboot!)
8. **Persistierung** → Approval wird in NVS gespeichert (überlebt Reboot)

### Wichtigste Erkenntnisse
- **Keine Auto-Discovery:** ESPs MÜSSEN via Heartbeat-ACK approved werden
- **Kein Reboot nötig:** Approval erfolgt live via MQTT
- **Server-Centric:** ESP sendet nur Rohdaten, Server entscheidet
- **Dual State-Storage:** SystemState im RAM + NVS-Persistierung separat

### Potenzielle Probleme/Lücken
- `STATE_PENDING_APPROVAL` wird NICHT in NVS persistiert (transient) - gewollt?
- Bei MQTT-Disconnect kann ESP nicht wissen ob Approval erfolgt ist
- Heartbeat-ACK mit `status: "pending_approval"` überschreibt lokalen Approval-Status nicht

### Update 2026-04-17 (Transport-/Pending-Hardening)
- `CONFIG_PENDING_AFTER_RESET`: Heartbeat-ACK triggert keinen direkten Pending-Exit mehr; die Exit-Pruefung erfolgt auf `config_commit` (reduziert Last im MQTT-Callback-Pfad).
- Runtime-Readiness-Snapshot nutzt aktive In-Memory-Manager (`sensorManager`/`actuatorManager`) statt NVS-Reloads im ACK-Pfad.
- Bootstrap-Heartbeat nach ACK-Subscription wird deferred im normalen MQTT-Loop gesendet (nicht mehr direkt in `MQTT_EVENT_SUBSCRIBED`).
- Stale `MQTT_EVENT_SUBSCRIBED`-Bootstrap-Trigger werden bei disconnected Zustand verworfen.
- `publishHeartbeat(force=true)` sendet nicht mehr im disconnected Zustand.

---

## 2. Boot-Sequenz

### Entry Point
**Datei:** [main.cpp:120](main.cpp#L120)
**Funktion:** `setup()`

### Initialisierungs-Reihenfolge (exakt)

| Schritt | Modul | Datei:Zeile | Beschreibung |
|---------|-------|-------------|--------------|
| 1 | Serial | [main.cpp:124](main.cpp#L124) | `Serial.begin(115200)` |
| 2 | Boot Banner | [main.cpp:140](main.cpp#L140) | Version + Chip Info |
| 3 | Boot-Button Check | [main.cpp:172-231](main.cpp#L172) | Factory Reset (10s Hold) |
| 4 | GPIO Safe-Mode | [main.cpp:241](main.cpp#L241) | `gpioManager.initializeAllPinsToSafeMode()` |
| 5 | Logger | [main.cpp:246](main.cpp#L246) | `logger.begin()` |
| 6 | StorageManager | [main.cpp:253](main.cpp#L253) | `storageManager.begin()` |
| 7 | ConfigManager | [main.cpp:261-269](main.cpp#L261) | `configManager.begin()`, `loadAllConfigs()` |
| 8 | Boot-Loop-Detection | [main.cpp:305-350](main.cpp#L305) | 5 Boots in <60s → Safe-Mode |
| 9 | Watchdog Config | [main.cpp:359-398](main.cpp#L359) | Conditional: Provisioning vs Production |
| 10 | Provisioning Check | [main.cpp:430](main.cpp#L430) | WiFi-Config fehlt → AP-Mode |
| 11 | ErrorTracker | [main.cpp:562](main.cpp#L562) | `errorTracker.begin()` |
| 12 | TopicBuilder | [main.cpp:567-568](main.cpp#L567) | `setEspId()`, `setKaiserId()` |
| 13 | WiFiManager | [main.cpp:602](main.cpp#L602) | `wifiManager.begin()` |
| 14 | MQTT Connect | [main.cpp:670-684](main.cpp#L670) | `mqttClient.begin()`, `connect()` |
| 15 | MQTT Subscriptions | [main.cpp:702-742](main.cpp#L702) | 10+ Topics subscribed |
| 16 | Initial Heartbeat | [main.cpp:699](main.cpp#L699) | `publishHeartbeat(true)` |
| 17 | Approval Check | [main.cpp:1319-1329](main.cpp#L1319) | `isDeviceApproved()` → State setzen |

### ESP-ID Generierung

**Datei:** [config_manager.cpp:1255](../services/config/config_manager.cpp#L1255)
**Funktion:** `generateESPIdIfMissing()`

```cpp
// Format: ESP_{6 hex chars from MAC}
// Beispiel: ESP_D0B19C

WiFi.mode(WIFI_STA);  // Muss vor macAddress() aufgerufen werden
uint8_t mac[6];
WiFi.macAddress(mac);

char esp_id[32];
snprintf(esp_id, sizeof(esp_id), "ESP_%02X%02X%02X",
         mac[3], mac[4], mac[5]);  // Nur letzte 3 MAC-Bytes
```

**Wokwi-Simulation:** Verwendet `WOKWI_ESP_ID` Compile-Time Konstante oder Default `ESP_WOKWI001`

### Approval-Check beim Boot

**Datei:** [main.cpp:1319-1329](main.cpp#L1319)

```cpp
if (!configManager.isDeviceApproved()) {
  g_system_config.current_state = STATE_PENDING_APPROVAL;
  // Sensors/Actuators DISABLED until approval
} else {
  g_system_config.current_state = STATE_OPERATIONAL;
  // Normal operation
}
```

---

## 3. WiFi-Verbindung

### Konfiguration

**NVS Namespace:** `wifi_config`
**NVS Keys:**

| Key | Typ | Beschreibung |
|-----|-----|--------------|
| `ssid` | String | WiFi SSID |
| `password` | String | WiFi Passwort |
| `server_address` | String | MQTT Broker IP (Default: 192.168.0.198) |
| `mqtt_port` | UInt16 | MQTT Port (Default: 8883) |
| `mqtt_username` | String | MQTT User (leer = Anonymous) |
| `mqtt_password` | String | MQTT Passwort |
| `configured` | Bool | Config-Status |

### Verbindungsherstellung

**Datei:** [wifi_manager.cpp:63-160](../services/communication/wifi_manager.cpp#L63)

```cpp
bool WiFiManager::connect(const WiFiConfig& config) {
  WiFi.begin(config.ssid.c_str(), config.password.c_str());

  // Wait with timeout
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start_time > WIFI_TIMEOUT_MS) {
      return false;  // Timeout
    }
    delay(100);
  }

  // Success → NTP sync
  timeManager.begin();
  return true;
}
```

### Timing-Parameter

| Parameter | Wert | Datei:Zeile |
|-----------|------|-------------|
| `WIFI_TIMEOUT_MS` | 20000ms (20s) | [wifi_manager.cpp:10](../services/communication/wifi_manager.cpp#L10) |
| `RECONNECT_INTERVAL_MS` | 30000ms (30s) | [wifi_manager.cpp:8](../services/communication/wifi_manager.cpp#L8) |
| `MAX_RECONNECT_ATTEMPTS` | 10 | [wifi_manager.cpp:9](../services/communication/wifi_manager.cpp#L9) |

### Circuit Breaker

**Konfiguration:** [wifi_manager.cpp:32](../services/communication/wifi_manager.cpp#L32)
- **Failures to Open:** 10
- **Recovery Timeout:** 60s
- **Half-Open Test Timeout:** 15s

### Provisioning-Modus

**Trigger:** `!g_wifi_config.configured || g_wifi_config.ssid.length() == 0`

**AP-Mode:**
- SSID: `AutoOne-{ESP_ID}` (z.B. `AutoOne-ESP_D0B19C`)
- Password: `provision`
- IP: `192.168.4.1`
- Timeout: 10 Minuten

---

## 4. MQTT-Verbindung

### Initialisierung

**Datei:** [mqtt_client.cpp:69-80](../services/communication/mqtt_client.cpp#L69)

```cpp
bool MQTTClient::begin() {
  mqtt_.setCallback(staticCallback);
  initialized_ = true;
  return true;
}
```

### Verbindung

**Datei:** [mqtt_client.cpp:85-271](../services/communication/mqtt_client.cpp#L85)

**Last-Will Testament (LWT):**
- **Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/will`
- **Payload:** `{"status":"offline","reason":"unexpected_disconnect","timestamp":<unix_timestamp>}`
- **QoS:** 1 (At Least Once)
- **Retain:** true (God-Kaiser kann offline-Status später abrufen)
- **Datei:** [mqtt_client.cpp:174-190](../services/communication/mqtt_client.cpp#L174)

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

**Port-Fallback:**
- Versucht erst Port 8883 (TLS)
- Bei Fehler automatisch Fallback auf Port 1883 (plain MQTT)

### Subscribed Topics

**Datei:** [main.cpp:702-742](main.cpp#L702)

| Topic | Beschreibung | Zeile |
|-------|--------------|-------|
| `kaiser/{id}/esp/{esp}/system/command` | System-Befehle | 703 |
| `kaiser/{id}/esp/{esp}/config` | Config-Updates | 704 |
| `kaiser/broadcast/emergency` | Emergency-Stop | 705 |
| `kaiser/{id}/esp/{esp}/actuator/+/command` | Aktor-Befehle (Wildcard) | 708 |
| `kaiser/{id}/esp/{esp}/actuator/emergency` | ESP-Emergency | 709 |
| `kaiser/{id}/esp/{esp}/zone/assign` | Zone-Assignment | 712 |
| `kaiser/{id}/esp/{esp}/subzone/assign` | Subzone-Assignment | 725 |
| `kaiser/{id}/esp/{esp}/subzone/remove` | Subzone-Removal | 726 |
| `kaiser/{id}/esp/{esp}/sensor/+/command` | Sensor-Befehle | 732 |
| **`kaiser/{id}/esp/{esp}/system/heartbeat/ack`** | **Approval-ACK** | **741** |

### Timing-Parameter

| Parameter | Wert | Datei:Zeile |
|-----------|------|-------------|
| `RECONNECT_BASE_DELAY_MS` | 1000ms (1s) | [mqtt_client.cpp:19](../services/communication/mqtt_client.cpp#L19) |
| `RECONNECT_MAX_DELAY_MS` | 60000ms (60s) | [mqtt_client.cpp:20](../services/communication/mqtt_client.cpp#L20) |
| `MAX_RECONNECT_ATTEMPTS` | 10 (aber via Circuit Breaker umgangen) | [mqtt_client.cpp:21](../services/communication/mqtt_client.cpp#L21) |

### Circuit Breaker

**Konfiguration:** [mqtt_client.cpp:55](../services/communication/mqtt_client.cpp#L55)
- **Failures to Open:** 5
- **Recovery Timeout:** 30s (30000ms)
- **Half-Open Test Timeout:** 10s (10000ms)

### HALF_OPEN Bypass (ERGÄNZT - 2026-01-23)

**Datei:** [mqtt_client.cpp:742-744](../services/communication/mqtt_client.cpp#L742)

```cpp
// Bei HALF_OPEN sofort Reconnect versuchen - das ist der Sinn von HALF_OPEN!
if (circuit_breaker_.getState() == CircuitState::HALF_OPEN) {
  return true;  // Sofort versuchen, kein Backoff!
}
```

**Bedeutung:** Wenn Circuit Breaker von OPEN zu HALF_OPEN wechselt, wird der Exponential-Backoff ignoriert und sofort ein Reconnect-Versuch gestartet. Dies verhindert eine Race-Condition, bei der HALF_OPEN timeout zurück zu OPEN ohne Test wechseln würde.

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

---

## 5. Heartbeat-System

### Heartbeat-Intervall

**Konstante:** `HEARTBEAT_INTERVAL_MS = 60000` (60 Sekunden)
**Datei:** [mqtt_client.h:111](../services/communication/mqtt_client.h#L111)

### Heartbeat-Topic

**Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat`
**Datei:** [topic_builder.cpp:127-132](../utils/topic_builder.cpp#L127)

**Beispiel:** `kaiser/god/esp/ESP_D0B19C/system/heartbeat`

### Heartbeat-Payload

**Datei:** [mqtt_client.cpp:617-679](../services/communication/mqtt_client.cpp#L617)

```json
{
  "esp_id": "ESP_D0B19C",
  "zone_id": "zone_1",
  "master_zone_id": "greenhouse",
  "zone_assigned": true,
  "ts": 1706012345,
  "uptime": 3600,
  "heap_free": 180000,
  "wifi_rssi": -65,
  "sensor_count": 3,
  "actuator_count": 2,
  "gpio_status": [
    {
      "gpio": 32,
      "owner": "sensor",
      "component": "DS18B20",
      "mode": 0,
      "safe": false
    }
  ],
  "gpio_reserved_count": 5,
  "config_status": {
    "wifi_configured": true,
    "zone_assigned": true,
    "system_configured": true,
    "subzone_count": 1,
    "boot_count": 5,
    "state": 8
  }
}
```

### config_status Felder (KORRIGIERT - 2026-01-23)

**Datei:** [config_manager.cpp:1214-1250](../services/config/config_manager.cpp#L1214) (`getDiagnosticsJSON()`)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `wifi_configured` | bool | WiFi-Config geladen UND configured=true |
| `zone_assigned` | bool | Zone-Config geladen UND zone_assigned=true |
| `system_configured` | bool | System-Config geladen |
| `subzone_count` | int | Anzahl konfigurierter Subzones |
| `boot_count` | int | Boot-Counter aus SystemConfig |
| `state` | int | SystemState Enum-Wert (z.B. 8=OPERATIONAL, 9=PENDING_APPROVAL) |

**WICHTIG:** `sensor_count` und `actuator_count` sind NICHT in `config_status`, sondern auf Top-Level des Heartbeat-Payloads!

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

### Erster Heartbeat

**Trigger:** Nach erfolgreicher MQTT-Verbindung
**Datei:** [main.cpp:699](main.cpp#L699)

```cpp
mqttClient.publishHeartbeat(true);  // force=true bypasses throttle
```

**Wichtig:** `force=true` umgeht das 60s-Throttling für den initialen Heartbeat.

---

## 6. State Machine

### State-Enum

**Datei:** [system_types.h:9-24](../models/system_types.h#L9)

```cpp
enum SystemState {
  STATE_BOOT = 0,
  STATE_WIFI_SETUP,
  STATE_WIFI_CONNECTED,
  STATE_MQTT_CONNECTING,
  STATE_MQTT_CONNECTED,
  STATE_AWAITING_USER_CONFIG,
  STATE_ZONE_CONFIGURED,
  STATE_SENSORS_CONFIGURED,
  STATE_OPERATIONAL,
  STATE_PENDING_APPROVAL,           // Awaiting server approval
  STATE_LIBRARY_DOWNLOADING,        // OTA (optional)
  STATE_SAFE_MODE,
  STATE_SAFE_MODE_PROVISIONING,     // Safe-Mode mit aktivem AP
  STATE_ERROR
};
```

### State-Übergänge (Anmeldeprozess)

```
                  ┌─────────────────────────────────────────┐
                  │                                         │
   ┌──────────────▼──────────────┐                         │
   │      STATE_BOOT (0)         │                         │
   │   (Serial, GPIO, NVS)       │                         │
   └──────────────┬──────────────┘                         │
                  │                                         │
   ┌──────────────▼──────────────┐                         │
   │ WiFi Config vorhanden?      │───NO───┐                │
   └──────────────┬──────────────┘        │                │
                  │ YES                    │                │
                  │                        ▼                │
   ┌──────────────▼──────────────┐ ┌─────────────────────┐ │
   │   STATE_WIFI_CONNECTED      │ │ STATE_SAFE_MODE_    │ │
   │   (WiFi + NTP)              │ │ PROVISIONING        │ │
   └──────────────┬──────────────┘ │ (AP-Mode aktiv)     │ │
                  │                 └──────────┬──────────┘ │
                  │                            │ Config     │
   ┌──────────────▼──────────────┐            │ empfangen  │
   │   STATE_MQTT_CONNECTED      │            │            │
   │   (MQTT + Subscriptions)    │            ▼            │
   └──────────────┬──────────────┘    ESP.restart() ───────┘
                  │
   ┌──────────────▼──────────────┐
   │ isDeviceApproved() ?        │
   └──────────────┬──────────────┘
         │                │
        YES              NO
         │                │
         ▼                ▼
   ┌──────────────┐ ┌─────────────────────┐
   │    STATE_    │ │ STATE_PENDING_      │
   │  OPERATIONAL │ │ APPROVAL            │◄──────┐
   │     (8)      │ │     (9)             │       │
   └──────────────┘ │ (Limited Operation) │       │
         ▲          └──────────┬──────────┘       │
         │                     │                   │
         │         Heartbeat-ACK received          │
         │         status: "approved"              │
         │                     │                   │
         │                     ▼                   │
         │          ┌────────────────────┐         │
         └──────────│ setDeviceApproved  │         │
                    │ (true, timestamp)  │         │
                    └────────────────────┘         │
                                                   │
                    Heartbeat-ACK received         │
                    status: "pending_approval"     │
                              │                    │
                              └────────────────────┘
```

### Initialer State

**Bei erstem Boot:** `STATE_PENDING_APPROVAL` (wenn nicht approved)
**Nach Approval:** `STATE_OPERATIONAL` (aus NVS geladen)

### State-Persistierung

**NVS Namespace:** `system_config`
**NVS Key:** `state` (UInt8)
**Datei:** [config_manager.cpp:1088](../services/config/config_manager.cpp#L1088)

**WICHTIG:** `STATE_PENDING_APPROVAL` wird NICHT persistiert - es ist ein transient State!

---

## 7. Approval-Verarbeitung (Heartbeat-ACK Handler)

### Heartbeat-ACK Topic

**Pattern:** `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat/ack`
**Datei:** [topic_builder.cpp:134-141](../utils/topic_builder.cpp#L134)

### Erwartetes ACK-Payload

**Datei:** [main.cpp:1227-1237](main.cpp#L1227)

```json
{
  "status": "approved",         // "approved" | "online" | "pending_approval" | "rejected"
  "config_available": true,     // Server hat Config für diesen ESP
  "server_time": 1706012345     // Unix timestamp für Sync
}
```

### Status-Werte und Reaktionen

| Status | Aktion | Datei:Zeile |
|--------|--------|-------------|
| `approved` / `online` | `STATE_OPERATIONAL`, NVS speichern | [main.cpp:1246-1269](main.cpp#L1246) |
| `pending_approval` | `STATE_PENDING_APPROVAL` (ohne NVS) | [main.cpp:1272-1278](main.cpp#L1272) |
| `rejected` | `STATE_ERROR`, Approval löschen | [main.cpp:1280-1302](main.cpp#L1280) |

### Approval-Handler Code

**Datei:** [main.cpp:1217-1308](main.cpp#L1217)

```cpp
// Phase 2: Heartbeat-ACK Handler (Server → ESP)
String heartbeat_ack_topic = TopicBuilder::buildSystemHeartbeatAckTopic();
if (topic == heartbeat_ack_topic) {
  // Parse JSON
  const char* status = doc["status"] | "unknown";

  if (strcmp(status, "approved") == 0 || strcmp(status, "online") == 0) {
    // → Persist approval to NVS
    configManager.setDeviceApproved(true, approval_ts);

    // → State transition (NO REBOOT)
    g_system_config.current_state = STATE_OPERATIONAL;
    configManager.saveSystemConfig(g_system_config);
  }
}
```

---

## 8. NVS-Persistierung

### Namespace: `system_config`

**Datei:** [config_manager.cpp:1076](../services/config/config_manager.cpp#L1076)

| Key | Typ | Beschreibung | Datei:Zeile |
|-----|-----|--------------|-------------|
| `esp_id` | String | ESP-Identifikation | [config_manager.cpp:1082](../services/config/config_manager.cpp#L1082) |
| `dev_name` | String | Device Name (Default: "ESP32") | [config_manager.cpp:1085](../services/config/config_manager.cpp#L1085) |
| `state` | UInt8 | SystemState Enum | [config_manager.cpp:1088](../services/config/config_manager.cpp#L1088) |
| `sfm_reason` | String | Safe-Mode Reason | [config_manager.cpp:1091](../services/config/config_manager.cpp#L1091) |
| `boot_count` | UInt16 | Boot Counter | [config_manager.cpp:1098](../services/config/config_manager.cpp#L1098) |
| **`dev_appr`** | Bool | **Device Approved** | [config_manager.cpp:1142](../services/config/config_manager.cpp#L1142) |
| **`appr_ts`** | UInt32 | **Approval Timestamp** | [config_manager.cpp:1143](../services/config/config_manager.cpp#L1143) |

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

### Approval-Status lesen

**Datei:** [config_manager.cpp:1145-1156](../services/config/config_manager.cpp#L1145)

```cpp
bool ConfigManager::isDeviceApproved() const {
  if (!storageManager.beginNamespace("system_config", true)) {
    return false;  // Default: not approved
  }
  bool approved = storageManager.getBool("dev_appr", false);
  storageManager.endNamespace();
  return approved;
}
```

### Approval-Status schreiben

**Datei:** [config_manager.cpp:1158-1177](../services/config/config_manager.cpp#L1158) *(korrigiert: endet Zeile 1177, nicht 1175)*

```cpp
void ConfigManager::setDeviceApproved(bool approved, time_t timestamp) {
  if (!storageManager.beginNamespace("system_config", false)) {
    LOG_ERROR("ConfigManager: Cannot save approval status - namespace error");
    return;
  }

  storageManager.putBool(NVS_DEV_APPROVED, approved);
  if (timestamp > 0) {
    storageManager.putULong(NVS_APPR_TS, (unsigned long)timestamp);
  }

  storageManager.endNamespace();

  if (approved) {
    LOG_INFO("ConfigManager: Device approval saved (approved=true, ts=" +
             String((unsigned long)timestamp) + ")");
  } else {
    LOG_INFO("ConfigManager: Device approval cleared (pending/rejected)");
  }
}
```

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

---

## 9. Timing-Parameter

### Zusammenfassung aller kritischen Timings

| Parameter | Wert | Einheit | Datei:Zeile |
|-----------|------|---------|-------------|
| **Heartbeat-Intervall** | 60000 | ms | [mqtt_client.h:111](../services/communication/mqtt_client.h#L111) |
| **WiFi-Connect-Timeout** | 20000 | ms | [wifi_manager.cpp:10](../services/communication/wifi_manager.cpp#L10) |
| **WiFi-Reconnect-Intervall** | 30000 | ms | [wifi_manager.cpp:8](../services/communication/wifi_manager.cpp#L8) |
| **WiFi-Max-Reconnects** | 10 | count | [wifi_manager.cpp:9](../services/communication/wifi_manager.cpp#L9) |
| **MQTT-Reconnect-Base** | 1000 | ms | [mqtt_client.cpp:19](../services/communication/mqtt_client.cpp#L19) |
| **MQTT-Reconnect-Max** | 60000 | ms | [mqtt_client.cpp:20](../services/communication/mqtt_client.cpp#L20) |
| **MQTT-Circuit-Open** | 5 | failures | [mqtt_client.cpp:55](../services/communication/mqtt_client.cpp#L55) |
| **MQTT-Circuit-Recovery** | 30000 | ms | [mqtt_client.cpp:55](../services/communication/mqtt_client.cpp#L55) |
| **WiFi-Circuit-Open** | 10 | failures | [wifi_manager.cpp:32](../services/communication/wifi_manager.cpp#L32) |
| **WiFi-Circuit-Recovery** | 60000 | ms | [wifi_manager.cpp:32](../services/communication/wifi_manager.cpp#L32) |
| **Provisioning-Timeout** | 600000 | ms | [main.cpp:478](main.cpp#L478) |
| **Boot-Loop-Detection** | 5 boots / 60s | | [main.cpp:332](main.cpp#L332) |

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist ✓

### Watchdog-Konfiguration

**Provisioning-Mode:** [main.cpp:366-377](main.cpp#L366)
- Timeout: 300s (5 Minuten)
- Feed-Interval: 60s
- Panic: disabled

**Production-Mode:** [main.cpp:385-396](main.cpp#L385)
- Timeout: 60s
- Feed-Interval: 10s
- Panic: enabled (auto-reboot)

---

## 10. Server-Schnittstelle

### ESP32 → Server (Publish)

| Topic | Payload | QoS | Trigger |
|-------|---------|-----|---------|
| `kaiser/{id}/esp/{esp}/system/heartbeat` | Heartbeat JSON | 0 | Alle 60s + nach Connect |
| `kaiser/{id}/esp/{esp}/system/will` | Offline-Status | 1 | LWT (auto bei Disconnect) |
| `kaiser/{id}/esp/{esp}/sensor/{gpio}/data` | Sensor-Daten | 0/1 | Je nach Config |
| `kaiser/{id}/esp/{esp}/actuator/{gpio}/status` | Aktor-Status | 0 | Nach Aktor-Änderung |
| `kaiser/{id}/esp/{esp}/actuator/{gpio}/response` | Command-ACK | 1 | Nach Command |
| `kaiser/{id}/esp/{esp}/zone/ack` | Zone-ACK | 1 | Nach Zone-Assignment |
| `kaiser/{id}/esp/{esp}/config_response` | Config-ACK | 1 | Nach Config-Push |

### Server → ESP32 (Subscribe)

| Topic | Erwartetes Payload | QoS | Handler |
|-------|-------------------|-----|---------|
| `kaiser/{id}/esp/{esp}/system/heartbeat/ack` | Approval-Status | 1 | [main.cpp:1224](main.cpp#L1224) |
| `kaiser/{id}/esp/{esp}/system/command` | Befehle (factory_reset, etc.) | 1 | [main.cpp:857](main.cpp#L857) |
| `kaiser/{id}/esp/{esp}/config` | Sensor/Actuator Config | 2 | [main.cpp:752](main.cpp#L752) |
| `kaiser/{id}/esp/{esp}/actuator/+/command` | Aktor-Befehle | 1 | [main.cpp:762](main.cpp#L762) |
| `kaiser/{id}/esp/{esp}/zone/assign` | Zone-Assignment | 1 | [main.cpp:986](main.cpp#L986) |
| `kaiser/broadcast/emergency` | Emergency-Stop | 1 | [main.cpp:826](main.cpp#L826) |

---

## 11. Sequenzdiagramm

```
┌──────┐          ┌──────┐          ┌─────────────┐          ┌────────┐
│ ESP32│          │ WiFi │          │ MQTT Broker │          │ Server │
└──┬───┘          └──┬───┘          └──────┬──────┘          └───┬────┘
   │                  │                     │                     │
   │  setup()         │                     │                     │
   ├──────────────────┤                     │                     │
   │  GPIO Safe-Mode  │                     │                     │
   │  NVS Load        │                     │                     │
   │                  │                     │                     │
   │  WiFi.begin()    │                     │                     │
   ├─────────────────►│                     │                     │
   │                  │  DHCP               │                     │
   │  IP assigned     │◄────────────────────│                     │
   │◄─────────────────┤                     │                     │
   │                  │                     │                     │
   │  mqtt.connect()  │                     │                     │
   ├─────────────────────────────────────────►                    │
   │                  │                     │  LWT registered     │
   │  CONNACK         │                     │                     │
   │◄─────────────────────────────────────────                    │
   │                  │                     │                     │
   │  subscribe(heartbeat/ack)              │                     │
   ├─────────────────────────────────────────►                    │
   │                  │                     │                     │
   │  publishHeartbeat(force=true)          │                     │
   ├─────────────────────────────────────────►                    │
   │                  │                     │  Heartbeat          │
   │                  │                     ├─────────────────────►
   │                  │                     │                     │
   │                  │                     │  (Server prüft:     │
   │                  │                     │   ESP bekannt?      │
   │                  │                     │   Approved?)        │
   │                  │                     │                     │
   │                  │                     │  Heartbeat-ACK      │
   │                  │                     │◄─────────────────────
   │  ACK received    │                     │                     │
   │◄─────────────────────────────────────────                    │
   │                  │                     │                     │
   │  if (status == "approved")             │                     │
   │    setDeviceApproved(true)             │                     │
   │    current_state = OPERATIONAL         │                     │
   │                  │                     │                     │
   │  loop()          │                     │                     │
   ├──────────────────────────────────────────────────────────────┤
   │  (Heartbeat alle 60s)                  │                     │
   │                  │                     │                     │
```

---

## 12. Offene Fragen / Unklarheiten

### Zu klären mit Server-Team

1. **Heartbeat-ACK Timing:** Wie schnell antwortet der Server auf Heartbeats?
   - Aktuell: ESP wartet nicht aktiv auf ACK
   - Bei Netzwerk-Latenz kann ACK nach Heartbeat-Throttle ankommen

2. **Rejection Recovery:** Wie kommt ESP aus `STATE_ERROR` nach Rejection wieder raus?
   - Aktuell: Manueller Reset nötig
   - Kein automatischer Recovery-Pfad implementiert

3. **Approval-Sync:** Was passiert wenn ESP approved ist aber Server Approval verliert?
   - ESP bleibt `OPERATIONAL` weil NVS `dev_appr=true` hat
   - Server könnte `rejected` senden → ESP geht in `STATE_ERROR`

### Vermutungen zu verifizieren

1. **Server Heartbeat-Timeout:** 300s (5 Min) → Zu verifizieren mit Server-Code
2. **Auto-Discovery disabled:** Server registriert unbekannte ESPs als "pending" → Zu verifizieren
3. **Zone-Assignment Pflicht:** Ist Zone-Assignment vor Config-Push nötig? → Unklar

---

## 13. Code-Referenz-Index

| Funktion/Feature | Datei | Zeile | Beschreibung |
|------------------|-------|-------|--------------|
| Entry Point | main.cpp | 120 | `setup()` Funktion |
| GPIO Safe-Mode | main.cpp | 241 | `gpioManager.initializeAllPinsToSafeMode()` |
| ESP-ID Generierung | config_manager.cpp | 1255 | MAC → `ESP_XXXXXX` |
| WiFi Connect | wifi_manager.cpp | 85 | `connectToNetwork()` |
| MQTT Connect | mqtt_client.cpp | 153 | `connectToBroker()` |
| MQTT Subscriptions | main.cpp | 702-742 | 10+ Topics subscribed |
| Initial Heartbeat | main.cpp | 699 | `publishHeartbeat(true)` |
| Heartbeat Publish | mqtt_client.cpp | 617 | `publishHeartbeat()` |
| Heartbeat-ACK Handler | main.cpp | 1218-1308 | Approval-Verarbeitung |
| Approval Check | main.cpp | 1319 | `isDeviceApproved()` |
| Approval Read | config_manager.cpp | 1145 | `isDeviceApproved()` |
| Approval Write | config_manager.cpp | 1158 | `setDeviceApproved()` |
| State Enum | system_types.h | 9-24 | `SystemState` Definition |
| Topic Builder | topic_builder.cpp | 127 | `buildSystemHeartbeatTopic()` |
| Heartbeat-ACK Topic | topic_builder.cpp | 136 | `buildSystemHeartbeatAckTopic()` |
| NVS Keys Approval | config_manager.cpp | 1142-1143 | `dev_appr`, `appr_ts` |
| Watchdog Feed | main.cpp | 1496 | `feedWatchdog()` |
| Main Loop | main.cpp | 1633 | `loop()` Funktion |

---

**Ende der Analyse**

*Diese Dokumentation bildet die Grundlage für die Server-seitige Implementierung der ESP32-Registration und -Approval.*

---

## 14. Verifizierungszusammenfassung (ERGÄNZT - 2026-01-23)

### Verifizierte Code-Stellen

| Modul | Datei | Zeilen | Status |
|-------|-------|--------|--------|
| MQTT Konstanten | mqtt_client.cpp | 19-21 | ✅ Verifiziert |
| MQTT Circuit Breaker | mqtt_client.cpp | 55 | ✅ Verifiziert |
| MQTT LWT | mqtt_client.cpp | 174-190 | ✅ Verifiziert |
| MQTT Heartbeat | mqtt_client.cpp | 617-679 | ✅ Verifiziert |
| MQTT HALF_OPEN Bypass | mqtt_client.cpp | 742-744 | ✅ Verifiziert (ERGÄNZT) |
| HEARTBEAT_INTERVAL_MS | mqtt_client.h | 111 | ✅ Verifiziert |
| WiFi Konstanten | wifi_manager.cpp | 8-10 | ✅ Verifiziert |
| WiFi Circuit Breaker | wifi_manager.cpp | 32 | ✅ Verifiziert |
| TopicBuilder Heartbeat | topic_builder.cpp | 127-132 | ✅ Verifiziert |
| TopicBuilder ACK | topic_builder.cpp | 134-141 | ✅ Verifiziert |
| isDeviceApproved() | config_manager.cpp | 1145-1156 | ✅ Verifiziert |
| setDeviceApproved() | config_manager.cpp | 1158-1177 | ✅ Korrigiert (war 1158-1175) |
| getDiagnosticsJSON() | config_manager.cpp | 1214-1250 | ✅ Verifiziert (ERGÄNZT) |
| generateESPIdIfMissing() | config_manager.cpp | 1255-1290 | ✅ Verifiziert |
| NVS Keys | config_manager.cpp | 1142-1143 | ✅ Verifiziert |

### Korrekturen durchgeführt

1. **setDeviceApproved() Zeilennummern:** 1158-1175 → 1158-1177
2. **config_status JSON:** `sensor_count`/`actuator_count` entfernt (waren falsch dokumentiert als Teil von config_status, sind aber Top-Level im Heartbeat-Payload)
3. **config_status Feld hinzugefügt:** `system_configured` (bool)
4. **LWT Details ergänzt:** Datei-Referenz, QoS-Bedeutung

### Ergänzungen hinzugefügt

1. **HALF_OPEN Bypass:** Circuit Breaker Bypass-Logik für sofortige Reconnects bei HALF_OPEN State
2. **getDiagnosticsJSON() Dokumentation:** Vollständige Feldbeschreibung
3. **Verifiziert-Marker:** Bei allen kritischen Sections

---

**Verifiziert:** 2026-01-23 durch ESP32-Firmware-Spezialist
**Alle Zeilennummern gegen Codebase geprüft ✓**
