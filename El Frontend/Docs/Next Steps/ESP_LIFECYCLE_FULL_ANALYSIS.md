# ESP-Lifecycle & Server-Kommunikation - Vollständige Analyse

**Projekt:** AutomationOne Framework
**Erstellt:** 2026-01-27
**Zielgruppe:** Frontend-Entwickler, Manager-Team, System Architects
**Status:** ✅ Vollständig analysiert

---

## Executive Summary

Diese Dokumentation bietet eine **vollständige Analyse** des ESP32-Lifecycle im AutomationOne Framework. Sie deckt alle Phasen ab: von der ersten Stromzufuhr über die Auto-Discovery bis zum operativen Betrieb.

### Kernerkenntnisse

| Aspekt | Details |
|--------|---------|
| **ESP Lifecycle-Phasen** | 14 SystemStates (BOOT → OPERATIONAL) |
| **MQTT Topics (ESP → Server)** | 15 verschiedene Topics |
| **MQTT Topics (Server → ESP)** | 8 verschiedene Topics |
| **HTTP REST Endpoints** | 40+ ESP-relevante Endpoints |
| **WebSocket Events** | 12 Real-Time Event-Types |
| **Datenbank-Tabellen** | 8 relevante Tabellen |
| **Audit-Log Event-Types** | 25+ Event-Types |

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ESP32 ("El Trabajante")                                                │
│  Firmware: C++ / PlatformIO                                            │
│  States: BOOT → WIFI → MQTT → PENDING_APPROVAL → OPERATIONAL          │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ MQTT (QoS 0-2)
┌─────────────────────────────────────────────────────────────────────────┐
│  God-Kaiser Server ("El Servador")                                      │
│  Framework: Python / FastAPI                                           │
│  MQTT Handler: 12 spezialisierte Handler                               │
│  Database: PostgreSQL (SQLAlchemy Async)                               │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ WebSocket / REST API
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend ("El Frontend")                                               │
│  Framework: Vue 3 / TypeScript                                         │
│  WebSocket: Singleton Service mit Auto-Reconnect                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. ESP-Lifecycle State-Diagram

### 1.1 SystemState Enum (14 Zustände)

```cpp
// El Trabajante/src/models/system_types.h:9-24
enum SystemState {
  STATE_BOOT = 0,                 // 🟡 Initialer Zustand
  STATE_WIFI_SETUP,               // 🟡 WiFi-Konfiguration
  STATE_WIFI_CONNECTED,           // 🟢 WiFi verbunden
  STATE_MQTT_CONNECTING,          // 🟡 MQTT-Verbindungsaufbau
  STATE_MQTT_CONNECTED,           // 🟢 MQTT verbunden
  STATE_AWAITING_USER_CONFIG,     // 🟡 Wartet auf Sensor/Aktor-Config
  STATE_ZONE_CONFIGURED,          // 🟢 Zone zugewiesen
  STATE_SENSORS_CONFIGURED,       // 🟢 Sensoren bereit
  STATE_OPERATIONAL,              // 🟢 Voll operativ
  STATE_PENDING_APPROVAL,         // 🟡 Wartet auf Admin-Freigabe
  STATE_LIBRARY_DOWNLOADING,      // 🟡 OTA-Library Download
  STATE_SAFE_MODE,                // 🔴 Safe-Mode (Boot-Loop)
  STATE_SAFE_MODE_PROVISIONING,   // 🔴 Safe-Mode mit AP aktiv
  STATE_ERROR                     // 🔴 Fataler Fehler
};
```

### 1.2 Vollständiges Lifecycle-Diagramm

```
                         ┌──────────────────┐
                         │    POWER ON      │
                         └────────┬─────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ BOOT SEQUENCE (main.cpp:120-555)                                        │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. Serial Init (115200 baud)                                           │
│ 2. Boot Banner (Chip Model, CPU Freq, Heap)                           │
│ 3. Factory Reset Check (GPIO 0 für 10s)                               │
│ 4. GPIO Safe-Mode (alle Pins → INPUT_PULLUP) ⭐ KRITISCH              │
│ 5. Logger System                                                        │
│ 6. Storage Manager (NVS)                                               │
│ 7. Config Manager (WiFi, Zone, Sensors laden)                          │
│ 8. Watchdog Configuration                                              │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐           ┌─────────────────────────────────┐
│ CONFIG PRESENT  │           │ NO CONFIG (Provisioning Mode)   │
└────────┬────────┘           ├─────────────────────────────────┤
         │                    │ 1. ProvisionManager.begin()     │
         │                    │ 2. WiFi AP starten              │
         │                    │    SSID: AutoOne-{ESP_ID}       │
         │                    │    IP: 192.168.4.1              │
         │                    │ 3. HTTP Server (Port 80)        │
         │                    │    POST /provision              │
         │                    │ 4. Wait for Config (10 Min)     │
         │                    ├─────────────────────────────────┤
         │                    │ [Config erhalten]               │
         │                    │    → saveWiFiConfig()           │
         │                    │    → ESP.restart()              │
         │                    │                                 │
         │                    │ [Timeout 10 Min]                │
         │                    │    → STATE_SAFE_MODE_PROVISIONING│
         │                    │    → loop() weiter mit AP       │
         │                    └─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ NORMAL BOOT (mit Config)                                                │
├─────────────────────────────────────────────────────────────────────────┤
│ STATE_WIFI_SETUP                                                        │
│    └─→ WiFiManager.connect()                                           │
│        └─→ Circuit Breaker (5 Fehler → 30s Pause)                     │
│                                                                         │
│ STATE_WIFI_CONNECTED                                                    │
│    └─→ MQTTClient.connect()                                            │
│        ├─→ Last-Will (LWT) setzen                                      │
│        │   Topic: kaiser/{kaiser_id}/esp/{esp_id}/system/will          │
│        │   Payload: {"status":"offline", "reason":"unexpected_disconnect"}│
│        └─→ Subscribe auf alle relevanten Topics                        │
│                                                                         │
│ STATE_MQTT_CONNECTED                                                    │
│    └─→ Erster Heartbeat publizieren                                    │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ AUTO-DISCOVERY (Server-seitig)                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ESP sendet: kaiser/god/esp/{esp_id}/system/heartbeat                   │
│                                                                         │
│ Server (HeartbeatHandler):                                              │
│    └─→ ESP unbekannt?                                                  │
│        ├─→ JA: _discover_new_device()                                  │
│        │      ├─→ Create ESPDevice(status="pending_approval")          │
│        │      ├─→ AuditLog: DEVICE_DISCOVERED                          │
│        │      ├─→ WebSocket: device_discovered                         │
│        │      └─→ Heartbeat-ACK: status="pending_approval"             │
│        │                                                                │
│        └─→ NEIN: Normaler Heartbeat-Flow                               │
│                                                                         │
│ ESP Status: STATE_PENDING_APPROVAL                                      │
│    └─→ WiFi/MQTT aktiv, aber Sensoren/Aktoren NICHT aktiviert         │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ADMIN APPROVAL (Frontend/API)                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Frontend zeigt: "Neue Geräte zur Freigabe"                             │
│                                                                         │
│ Admin klickt "Genehmigen":                                              │
│    └─→ POST /api/v1/esp/{esp_id}/approve                               │
│        ├─→ DB Update: status = "approved"                              │
│        ├─→ AuditLog: DEVICE_APPROVED                                   │
│        └─→ WebSocket: device_approved                                  │
│                                                                         │
│ ODER Admin klickt "Ablehnen":                                           │
│    └─→ POST /api/v1/esp/{esp_id}/reject                                │
│        ├─→ DB Update: status = "rejected"                              │
│        ├─→ AuditLog: DEVICE_REJECTED                                   │
│        └─→ WebSocket: device_rejected                                  │
│        └─→ Cooldown: 8 Stunden vor Re-Discovery                        │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ OPERATIONAL (Normal Operation)                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Nächstes Heartbeat nach Approval:                                       │
│    └─→ Server sieht status = "approved"                                │
│        ├─→ DB Update: status = "online"                                │
│        ├─→ AuditLog: DEVICE_ONLINE                                     │
│        └─→ Heartbeat-ACK: status="online"                              │
│                                                                         │
│ ESP Status: STATE_OPERATIONAL                                           │
│                                                                         │
│ loop():                                                                 │
│    ├─→ feedWatchdog() (alle 10s)                                       │
│    ├─→ wifiManager.loop() (Reconnect-Logic)                            │
│    ├─→ mqttClient.loop() (Message Processing)                          │
│    │      └─→ publishHeartbeat() (alle 60s)                            │
│    ├─→ sensorManager.performAllMeasurements()                          │
│    ├─→ actuatorManager.processActuatorLoops()                          │
│    └─→ healthMonitor.loop()                                            │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐           ┌─────────────────────────────────┐
│ HEARTBEAT OK    │           │ HEARTBEAT TIMEOUT (>300s)       │
│ (alle 60s)      │           ├─────────────────────────────────┤
└─────────────────┘           │ Server:                         │
                              │    └─→ DB: status = "offline"   │
                              │    └─→ AuditLog: DEVICE_OFFLINE │
                              │    └─→ WebSocket: esp_health    │
                              │            (status="offline")   │
                              └─────────────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────────────┐
                              │ RECONNECT (Heartbeat wieder da) │
                              ├─────────────────────────────────┤
                              │ Server:                         │
                              │    └─→ DB: status = "online"    │
                              │    └─→ AuditLog: DEVICE_ONLINE  │
                              │    └─→ WebSocket: esp_health    │
                              │            (status="online")    │
                              └─────────────────────────────────┘
```

### 1.3 LWT (Last-Will-Testament) - Instant Offline Detection

```
ESP32 Verbindung bricht ab (Stromausfall, Netzwerk-Fehler)
         │
         ▼
Mosquitto Broker erkennt: Keepalive Timeout (60s)
         │
         ▼
Broker publiziert automatisch LWT-Message:
    Topic: kaiser/god/esp/{esp_id}/system/will
    Payload: {"status":"offline", "reason":"unexpected_disconnect", "ts":123456}
         │
         ▼
Server (LWTHandler) empfängt:
    ├─→ DB Update: status = "offline"
    ├─→ AuditLog: LWT_RECEIVED (severity: WARNING)
    └─→ WebSocket: esp_health (status="offline", reason="lwt")
         │
         ▼
Frontend: Sofortige UI-Aktualisierung (statt 300s Timeout)
```

---

## 2. MQTT-Protokoll (Vollständige Referenz)

### 2.1 ESP → Server (Publish Topics)

| Topic | Payload-Schema | QoS | Intervall | Handler |
|-------|----------------|-----|-----------|---------|
| `kaiser/god/esp/{esp_id}/sensor/{gpio}/data` | `{ts, gpio, sensor_type, raw, value, unit, quality, raw_mode}` | 1 | ~30s | SensorHandler |
| `kaiser/god/esp/{esp_id}/sensor/batch` | `{ts, readings: [...]}` | 1 | ~60s | SensorHandler |
| `kaiser/god/esp/{esp_id}/actuator/{gpio}/status` | `{ts, gpio, actuator_type, state, value, runtime_ms}` | 1 | On Change | ActuatorHandler |
| `kaiser/god/esp/{esp_id}/actuator/{gpio}/response` | `{ts, gpio, command, success, message}` | 1 | Nach Command | ActuatorResponseHandler |
| `kaiser/god/esp/{esp_id}/actuator/{gpio}/alert` | `{ts, gpio, alert_type, reason, error_code}` | 1 | On Alert | ActuatorAlertHandler |
| `kaiser/god/esp/{esp_id}/system/heartbeat` | `{ts, uptime, heap_free, wifi_rssi, sensor_count, actuator_count, gpio_status}` | 0 | 60s | HeartbeatHandler |
| `kaiser/god/esp/{esp_id}/system/diagnostics` | `{ts, error_count, wifi_reconnects, mqtt_reconnects}` | 0 | On Change | DiagnosticsHandler |
| `kaiser/god/esp/{esp_id}/system/error` | `{ts, error_code, category, message, severity}` | 1 | On Error | ErrorHandler |
| `kaiser/god/esp/{esp_id}/config_response` | `{status, type, count, failed_count, failures}` | 2 | Nach Config | ConfigHandler |
| `kaiser/god/esp/{esp_id}/zone/ack` | `{esp_id, zone_id, status, error_message}` | 1 | Nach Assign | ZoneAckHandler |
| `kaiser/god/esp/{esp_id}/subzone/ack` | `{esp_id, subzone_id, status, error_message}` | 1 | Nach Assign | SubzoneAckHandler |
| `kaiser/god/esp/{esp_id}/system/will` | `{status:"offline", reason, timestamp}` | 0 | LWT | LWTHandler |

### 2.2 Server → ESP (Subscribe Topics)

| Topic | Payload-Schema | QoS | Trigger | Beschreibung |
|-------|----------------|-----|---------|--------------|
| `kaiser/god/esp/{esp_id}/actuator/{gpio}/command` | `{command, value, duration}` | 1 | API/Logic | Aktor-Befehl |
| `kaiser/god/esp/{esp_id}/system/command` | `{command, params}` | 1 | API | System-Befehl (REBOOT, RESET) |
| `kaiser/god/esp/{esp_id}/config` | `{sensors, actuators, zones}` | 2 | API | Config-Update |
| `kaiser/god/esp/{esp_id}/zone/assign` | `{zone_id, master_zone_id}` | 1 | API | Zone-Zuweisung |
| `kaiser/god/esp/{esp_id}/subzone/assign` | `{subzone_id, gpios}` | 1 | API | Subzone-Zuweisung |
| `kaiser/god/esp/{esp_id}/subzone/remove` | `{subzone_id}` | 1 | API | Subzone entfernen |
| `kaiser/god/esp/{esp_id}/system/heartbeat/ack` | `{status, timestamp}` | 0 | Heartbeat | Heartbeat-Bestätigung |
| `kaiser/broadcast/emergency` | `{command: "STOP"}` | 1 | API | Global Emergency-Stop |

### 2.3 Heartbeat-Payload (Detailliert)

```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zelt_1",
  "master_zone_id": "master",
  "zone_assigned": true,
  "ts": 1735818000,
  "uptime": 3600,
  "heap_free": 98304,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 1,
  "gpio_status": [
    {
      "gpio": 4,
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
    "sensor_count": 3,
    "actuator_count": 1,
    "subzone_count": 2,
    "nvs_errors": 0,
    "boot_count": 1
  }
}
```

---

## 3. HTTP REST API (ESP-Lifecycle Endpoints)

### 3.1 Device Registration & Discovery

| Endpoint | Method | Beschreibung | Auth |
|----------|--------|--------------|------|
| `POST /api/v1/esp/devices` | POST | Manuelles Registrieren | Operator |
| `GET /api/v1/esp/devices` | GET | Alle Geräte auflisten | User |
| `GET /api/v1/esp/devices/pending` | GET | Pending Devices (zur Freigabe) | Operator |
| `GET /api/v1/esp/devices/{esp_id}` | GET | Geräte-Details | User |
| `PATCH /api/v1/esp/devices/{esp_id}` | PATCH | Gerät aktualisieren | Operator |
| `DELETE /api/v1/esp/devices/{esp_id}` | DELETE | Gerät löschen (CASCADE) | Admin |

### 3.2 Approval Workflow

| Endpoint | Method | Beschreibung | Request Body |
|----------|--------|--------------|--------------|
| `POST /api/v1/esp/devices/{esp_id}/approve` | POST | Gerät freigeben | `{name?, zone_id?, zone_name?}` |
| `POST /api/v1/esp/devices/{esp_id}/reject` | POST | Gerät ablehnen | `{reason}` |

### 3.3 Device Management

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `POST /api/v1/esp/devices/{esp_id}/config` | POST | Config via MQTT senden |
| `POST /api/v1/esp/devices/{esp_id}/restart` | POST | Neustart-Befehl senden |
| `POST /api/v1/esp/devices/{esp_id}/reset` | POST | Factory Reset (confirm required) |
| `GET /api/v1/esp/devices/{esp_id}/health` | GET | Health-Metriken abrufen |
| `GET /api/v1/esp/devices/{esp_id}/gpio-status` | GET | GPIO Pin-Status |

### 3.4 Sensor Management

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `GET /api/v1/sensors/` | GET | Alle Sensoren auflisten |
| `POST /api/v1/sensors/{esp_id}/{gpio}` | POST | Sensor konfigurieren |
| `GET /api/v1/sensors/{esp_id}/{gpio}` | GET | Sensor-Config abrufen |
| `DELETE /api/v1/sensors/{esp_id}/{gpio}` | DELETE | Sensor löschen |
| `GET /api/v1/sensors/data` | GET | Time-Series Daten abfragen |

### 3.5 Actuator Management

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `GET /api/v1/actuators/` | GET | Alle Aktoren auflisten |
| `POST /api/v1/actuators/{esp_id}/{gpio}` | POST | Aktor konfigurieren |
| `POST /api/v1/actuators/{esp_id}/{gpio}/command` | POST | Aktor-Befehl senden |
| `GET /api/v1/actuators/{esp_id}/{gpio}/status` | GET | Aktor-Status abrufen |
| `POST /api/v1/actuators/emergency_stop` | POST | Global Emergency-Stop |

### 3.6 Mock ESP (Debug)

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `POST /api/v1/debug/mock-esp` | POST | Mock-ESP erstellen |
| `GET /api/v1/debug/mock-esp` | GET | Alle Mock-ESPs |
| `DELETE /api/v1/debug/mock-esp/{esp_id}` | DELETE | Mock-ESP löschen |
| `POST /api/v1/debug/mock-esp/{esp_id}/sensor/{gpio}` | POST | Sensor-Wert setzen |

---

## 4. Event-Typen Master-Liste

### 4.1 Audit-Log Event-Types (25+)

| Event-Type | Severity | Source | Trigger | Beschreibung |
|------------|----------|--------|---------|--------------|
| **ESP Lifecycle** |
| `DEVICE_DISCOVERED` | INFO | mqtt | Erstes Heartbeat | Neues Gerät erkannt |
| `DEVICE_APPROVED` | INFO | user | Admin Approval | Gerät freigegeben |
| `DEVICE_REJECTED` | WARNING | user | Admin Rejection | Gerät abgelehnt |
| `DEVICE_ONLINE` | INFO | mqtt | Heartbeat nach Approval | Gerät online |
| `DEVICE_OFFLINE` | WARNING | mqtt | Heartbeat Timeout | Gerät offline |
| `DEVICE_REDISCOVERED` | INFO | mqtt | Heartbeat nach Cooldown | Re-Discovery |
| `LWT_RECEIVED` | WARNING | mqtt | LWT Message | Unexpected Disconnect |
| **Config** |
| `CONFIG_RESPONSE` | INFO | mqtt | Config-ACK | Config angewendet |
| `CONFIG_PUBLISHED` | INFO | system | API Call | Config gesendet |
| `CONFIG_FAILED` | ERROR | mqtt | Config-Error | Config fehlgeschlagen |
| **Auth** |
| `LOGIN_SUCCESS` | INFO | user | Login | Erfolgreicher Login |
| `LOGIN_FAILED` | WARNING | user | Login | Fehlgeschlagener Login |
| `LOGOUT` | INFO | user | Logout | Benutzer abgemeldet |
| **System** |
| `EMERGENCY_STOP` | CRITICAL | user | API Call | Notfall-Stop |
| `SERVICE_START` | INFO | system | Server Start | Server gestartet |
| `SERVICE_STOP` | INFO | system | Server Stop | Server gestoppt |
| **Errors** |
| `MQTT_ERROR` | ERROR | mqtt | Handler Error | MQTT-Fehler |
| `VALIDATION_ERROR` | WARNING | mqtt | Payload Invalid | Validierungs-Fehler |
| `DATABASE_ERROR` | CRITICAL | system | DB Error | Datenbank-Fehler |

### 4.2 WebSocket Event-Types (12)

| Event-Type | Trigger | Frontend-Handler | Beschreibung |
|------------|---------|------------------|--------------|
| `sensor_data` | MQTT Sensor Data | SensorSidebar, Dashboard | Sensor-Messwert |
| `actuator_status` | MQTT Actuator Status | ActuatorSidebar | Aktor-Status Update |
| `actuator_response` | MQTT Actuator Response | CommandHistory | Befehl-Bestätigung |
| `actuator_alert` | MQTT Actuator Alert | Alerts, Dashboard | Safety-Alert |
| `esp_health` | MQTT Heartbeat | StatusBar, ESPCard | Device Health |
| `device_discovered` | Auto-Discovery | DevicesPanel (pending) | Neues Gerät |
| `device_approved` | Admin Approval | DevicesPanel | Gerät freigegeben |
| `device_rejected` | Admin Rejection | DevicesPanel | Gerät abgelehnt |
| `device_rediscovered` | Re-Discovery | DevicesPanel | Re-Discovery |
| `config_response` | MQTT Config ACK | SystemConfigView | Config-Bestätigung |
| `zone_assignment` | MQTT Zone ACK | ZonePanel | Zone zugewiesen |
| `error_event` | MQTT Error | Alerts, SystemMonitor | System-Fehler |

---

## 5. Datenbank-Schema

### 5.1 esp_devices (Haupt-Tabelle)

| Spalte | Typ | Index | Beschreibung |
|--------|-----|-------|--------------|
| `id` | UUID | PK | System-ID |
| `device_id` | String(50) | UNIQUE | ESP-ID (z.B. ESP_12AB34CD) |
| `name` | String(100) | - | Menschenlesbar |
| `zone_id` | String(50) | INDEX | Zone-Identifier |
| `zone_name` | String(100) | - | Zone-Name |
| `status` | String(20) | INDEX | Status (siehe 1.1) |
| `last_seen` | DateTime | INDEX | Letzter Heartbeat |
| `health_status` | String(20) | - | healthy/degraded/critical |
| `discovered_at` | DateTime | - | Discovery-Timestamp |
| `approved_at` | DateTime | - | Approval-Timestamp |
| `approved_by` | String(100) | - | Admin-User |
| `rejection_reason` | String(500) | - | Ablehnungsgrund |
| `device_metadata` | JSON | - | Zusätzliche Daten |

### 5.2 esp_heartbeat_logs (Time-Series)

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `id` | UUID | Log-ID |
| `esp_id` | UUID (FK) | Foreign Key |
| `device_id` | String(50) | Denormalisiert für Queries |
| `timestamp` | DateTime | Heartbeat-Zeit |
| `heap_free` | Integer | Freier RAM |
| `wifi_rssi` | Integer | WiFi-Signal |
| `uptime` | Integer | Uptime in Sekunden |
| `health_status` | String(20) | Berechneter Status |
| `data_source` | String(20) | production/mock/test |

**Retention:** 7 Tage (konfigurierbar)

### 5.3 audit_logs (Event-Log)

| Spalte | Typ | Index | Beschreibung |
|--------|-----|-------|--------------|
| `id` | UUID | PK | Event-ID |
| `event_type` | String(50) | INDEX | Event-Typ |
| `severity` | String(20) | INDEX | info/warning/error/critical |
| `source_type` | String(30) | INDEX | esp32/user/system/mqtt |
| `source_id` | String(100) | INDEX | Identifier |
| `status` | String(20) | - | success/failed/pending |
| `message` | Text | - | Beschreibung |
| `details` | JSON | - | Zusätzliche Daten |
| `created_at` | DateTime | INDEX | Zeitstempel |

**Retention:** Konfigurierbar (Default: 90 Tage)

### 5.4 Status-Übergangs-Matrix

| Von | Nach | Trigger | AuditLog |
|-----|------|---------|----------|
| (neu) | `pending_approval` | Erstes Heartbeat | DEVICE_DISCOVERED |
| `pending_approval` | `approved` | Admin Approval | DEVICE_APPROVED |
| `pending_approval` | `rejected` | Admin Rejection | DEVICE_REJECTED |
| `approved` | `online` | Heartbeat nach Approval | DEVICE_ONLINE |
| `online` | `offline` | Timeout (>300s) | DEVICE_OFFLINE |
| `online` | `offline` | LWT empfangen | LWT_RECEIVED |
| `offline` | `online` | Heartbeat | DEVICE_ONLINE |
| `rejected` | `pending_approval` | Heartbeat nach 8h | DEVICE_REDISCOVERED |

---

## 6. Frontend WebSocket Integration

### 6.1 WebSocket Service (Singleton)

```typescript
// El Frontend/src/services/websocket.ts

class WebSocketService {
  // Singleton Pattern
  private static instance: WebSocketService;

  // Connection State
  private ws: WebSocket | null;
  private status: 'connecting' | 'connected' | 'disconnected';

  // Subscriptions
  private subscriptions: Map<string, {filters, callback}>;

  // Auto-Reconnect
  private reconnectAttempts: number;
  private maxReconnectDelay: 30000; // 30s max

  // Token Handling
  private tokenExpiry: number | null;

  // Methoden
  connect(): void;
  disconnect(): void;
  subscribe(filters, callback): string;
  unsubscribe(subId): void;
  on(type, callback): () => void;
  onConnect(callback): void;
}
```

### 6.2 Filter-System

```typescript
interface WebSocketFilters {
  types?: MessageType[]        // ['sensor_data', 'actuator_status']
  esp_ids?: string[]           // ['ESP_12AB34CD']
  sensor_types?: string[]      // ['temperature', 'humidity']
  topicPattern?: string        // Regex (optional)
}
```

### 6.3 Reconnect-Logik

```
Attempt 1: 1s ± 100ms
Attempt 2: 2s ± 200ms
Attempt 3: 4s ± 400ms
Attempt 4: 8s ± 800ms
Attempt 5: 16s ± 1600ms
Attempt 6+: 30s ± 3000ms (max)
```

### 6.4 Tab Visibility Handling

- Bei Tab sichtbar → Reconnect prüfen
- Token Refresh vor Reconnect (wenn expiring)
- Max 10 Reconnect-Versuche

---

## 7. Message-Flow Zusammenfassung

### 7.1 Discovery & Approval Flow

```
┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────┐
│  ESP32   │      │ MQTT Broker  │      │   Server     │      │ Frontend │
└────┬─────┘      └──────┬───────┘      └──────┬───────┘      └────┬─────┘
     │                   │                      │                   │
     │ Heartbeat         │                      │                   │
     │──────────────────>│                      │                   │
     │                   │ Heartbeat            │                   │
     │                   │─────────────────────>│                   │
     │                   │                      │                   │
     │                   │                      │ [Unknown ESP]     │
     │                   │                      │ Create pending    │
     │                   │                      │ AuditLog          │
     │                   │                      │                   │
     │                   │                      │ WebSocket         │
     │                   │                      │ device_discovered │
     │                   │                      │──────────────────>│
     │                   │                      │                   │
     │                   │ Heartbeat-ACK        │                   │
     │                   │ (status=pending)     │                   │
     │<──────────────────│<─────────────────────│                   │
     │                   │                      │                   │
     │                   │                      │    Admin klickt   │
     │                   │                      │    "Genehmigen"   │
     │                   │                      │<──────────────────│
     │                   │                      │                   │
     │                   │                      │ POST /approve     │
     │                   │                      │ DB: approved      │
     │                   │                      │ AuditLog          │
     │                   │                      │                   │
     │                   │                      │ WebSocket         │
     │                   │                      │ device_approved   │
     │                   │                      │──────────────────>│
     │                   │                      │                   │
     │ Heartbeat (60s)   │                      │                   │
     │──────────────────>│                      │                   │
     │                   │ Heartbeat            │                   │
     │                   │─────────────────────>│                   │
     │                   │                      │                   │
     │                   │                      │ [status=approved] │
     │                   │                      │ DB: online        │
     │                   │                      │ AuditLog          │
     │                   │                      │                   │
     │                   │                      │ WebSocket         │
     │                   │                      │ esp_health        │
     │                   │                      │ (status=online)   │
     │                   │                      │──────────────────>│
     │                   │                      │                   │
     │                   │ Heartbeat-ACK        │                   │
     │                   │ (status=online)      │                   │
     │<──────────────────│<─────────────────────│                   │
     │                   │                      │                   │
     │ ✅ OPERATIONAL    │                      │                   │
     │                   │                      │                   │
```

### 7.2 Sensor Data Flow

```
┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────┐
│  ESP32   │      │ MQTT Broker  │      │   Server     │      │ Frontend │
└────┬─────┘      └──────┬───────┘      └──────┬───────┘      └────┬─────┘
     │                   │                      │                   │
     │ Sensor Data       │                      │                   │
     │ (raw_mode=true)   │                      │                   │
     │──────────────────>│                      │                   │
     │                   │ Sensor Data          │                   │
     │                   │─────────────────────>│                   │
     │                   │                      │                   │
     │                   │                      │ SensorHandler:    │
     │                   │                      │ - Validate        │
     │                   │                      │ - Pi-Enhanced?    │
     │                   │                      │ - DB Insert       │
     │                   │                      │                   │
     │                   │                      │ WebSocket         │
     │                   │                      │ sensor_data       │
     │                   │                      │──────────────────>│
     │                   │                      │                   │
     │                   │                      │ Logic Engine      │
     │                   │                      │ (async trigger)   │
     │                   │                      │                   │
```

---

## 8. Lücken & Empfehlungen

### 8.1 Identifizierte Lücken

| Bereich | Lücke | Impact | Empfehlung |
|---------|-------|--------|------------|
| **System Monitor** | Event-Type Filter vs DataSource-Filter Redundanz | Verwirrung | EVENT-TYPEN entfernen (siehe Filterchaos.md) |
| **Server-Bug** | `/audit/events/aggregated` ignoriert `selectedDataSources` | 6.8x Traffic | Fix: `sources: selectedDataSources.value` |
| **dataSource Mapping** | 15 von 31 Event-Types ohne Mapping | Filter-Inkonsistenz | `determineDataSource()` erweitern |
| **Frontend** | Keine Retry-Logic für WebSocket Messages | Message Loss | Best-Effort ist akzeptabel |

### 8.2 Fehlende Event-Types im Frontend (System Monitor)

Diese Event-Types existieren im Server, werden aber im Frontend nicht explizit gehandelt:

| Event-Type | Sollte angezeigt werden | Aktuell |
|------------|-------------------------|---------|
| `config_published` | Ja | ❌ Fehlt |
| `config_failed` | Ja | ❌ Fehlt |
| `device_online` | Ja | ⚠️ Via esp_health |
| `device_offline` | Ja | ⚠️ Via esp_health |
| `lwt_received` | Ja | ⚠️ Via esp_health |
| `service_start` | Optional | ❌ Fehlt |
| `service_stop` | Optional | ❌ Fehlt |
| `emergency_stop` | Ja | ❌ Fehlt |

### 8.3 Empfohlene Verbesserungen

1. **DataSource-Filter Server-seitig nutzen**
   - Zeile 797 in SystemMonitorView.vue: `sources: selectedDataSources.value`
   - Performance-Gewinn: 6.8x weniger Traffic

2. **Event-Type-Filter entfernen**
   - ~150 Zeilen Code-Reduktion
   - Siehe: `.claude/Next Steps/Filterchaos.md`

3. **Fehlende dataSource-Mappings hinzufügen**
   - `determineDataSource()` erweitern für alle 31 Types

4. **Emergency-Stop Events im Frontend**
   - Dedizierter Handler für `emergency_stop`
   - Visual Alert mit Sound (optional)

---

## 9. Code-Referenzen

### 9.1 ESP32 Firmware

| Komponente | Datei | Zeilen |
|------------|-------|--------|
| Boot-Sequenz | `El Trabajante/src/main.cpp` | 120-555 |
| SystemState Enum | `El Trabajante/src/models/system_types.h` | 9-24 |
| MQTT Client | `El Trabajante/src/services/communication/mqtt_client.cpp` | 85-679 |
| Heartbeat Publish | `El Trabajante/src/services/communication/mqtt_client.cpp` | 617-679 |
| LWT Setup | `El Trabajante/src/services/communication/mqtt_client.cpp` | 176-189 |
| Topic Builder | `El Trabajante/src/utils/topic_builder.cpp` | 52-225 |
| Provisioning | `El Trabajante/src/services/provisioning/provision_manager.cpp` | 47-305 |

### 9.2 Server

| Komponente | Datei | Zeilen |
|------------|-------|--------|
| Heartbeat Handler | `El Servador/.../mqtt/handlers/heartbeat_handler.py` | 61-1113 |
| Sensor Handler | `El Servador/.../mqtt/handlers/sensor_handler.py` | 48-662 |
| Actuator Handler | `El Servador/.../mqtt/handlers/actuator_handler.py` | 32-436 |
| LWT Handler | `El Servador/.../mqtt/handlers/lwt_handler.py` | 50-176 |
| WebSocket Manager | `El Servador/.../websocket/manager.py` | 1-400 |
| ESP Device Model | `El Servador/.../db/models/esp.py` | 1-240 |
| Audit Log Model | `El Servador/.../db/models/audit_log.py` | 1-240 |
| ESP REST API | `El Servador/.../api/v1/esp.py` | 1-900 |

### 9.3 Frontend

| Komponente | Datei |
|------------|-------|
| WebSocket Service | `El Frontend/src/services/websocket.ts` |
| System Monitor | `El Frontend/src/views/SystemMonitorView.vue` |
| DataSourceSelector | `El Frontend/src/components/system-monitor/DataSourceSelector.vue` |
| ESP Store | `El Frontend/src/stores/esp.ts` |

---

## 10. Changelog

| Version | Datum | Autor | Änderungen |
|---------|-------|-------|------------|
| 1.0 | 2026-01-27 | Claude (Opus 4.5) | Initiale vollständige Analyse |

---

**Ende der Dokumentation**
