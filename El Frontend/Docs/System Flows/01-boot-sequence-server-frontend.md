# Boot Sequence - Server & Frontend Perspektive

## Overview

Wie Server und Frontend auf den ESP32-Boot reagieren. Gespiegelte Dokumentation zu `El Trabajante/docs/system-flows/01-boot-sequence.md`.

**Korrespondiert mit:** `El Trabajante/docs/system-flows/01-boot-sequence.md`

---

## Voraussetzungen

- [ ] Server läuft (`localhost:8000`)
- [ ] Frontend läuft (`localhost:5173`)
- [ ] MQTT Broker erreichbar (Mosquitto auf Port 1883)
- [ ] **ESP32 ist vorher registriert** (via REST API `POST /api/v1/esp/devices`)

> **KRITISCH:** Auto-Discovery ist deaktiviert. Unregistrierte ESPs werden vom Heartbeat-Handler abgelehnt.

---

## Teil 1: Server-Startup-Sequenz

### Wie man den Server startet

```bash
cd "El Servador/god_kaiser_server"
poetry run uvicorn god_kaiser_server.src.main:app --reload --host 0.0.0.0 --port 8000
```

### Server-Initialisierungsreihenfolge

Die `lifespan()` Funktion in `main.py` orchestriert den Server-Start:

| Step | Aktion | Code-Location | Details |
|------|--------|---------------|---------|
| **0** | Security Validation | `main.py:91-119` | JWT Secret Key prüfen, MQTT TLS Warnung |
| **0.5** | Initialize Resilience Patterns | `main.py:121-143` | Circuit Breaker Registry für external_api, database, mqtt |
| **1** | Database Initialization | `main.py:145-157` | `init_db()`, Circuit Breaker Setup |
| **2** | MQTT Client Connection | `main.py:159-170` | `MQTTClient.get_instance().connect()` |
| **3** | Register MQTT Handlers | `main.py:172-278` | Handler für Sensor, Actuator, Heartbeat, Discovery, Config, Zone/Subzone ACK |
| **3.4** | Initialize Central Scheduler | `main.py:232-236` | `init_central_scheduler()` |
| **3.4.1** | Initialize SimulationScheduler | `main.py:238-246` | Mock-ESP Simulation Framework |
| **3.4.2** | Initialize MaintenanceService | `main.py:280-290` | Scheduled Maintenance Jobs |
| **3.5** | Recover Mock-ESP Simulations | `main.py:292-304` | DB-First Recovery nach Server-Restart |
| **4** | Subscribe to MQTT Topics | `main.py:306-312` | `Subscriber.subscribe_all()` (nur wenn connected) |
| **5** | Initialize WebSocket Manager | `main.py:314-319` | `WebSocketManager.get_instance()` |
| **6** | Initialize Services | `main.py:321-385` | Safety, Actuator, Logic Engine, Logic Scheduler |

### MQTT-Handler die auf ESP-Boot reagieren

Nach dem Start subscribed der Server auf diese Topics (mit `kaiser_id = "god"` als Default):

```
kaiser/god/esp/+/sensor/+/data          → sensor_handler.handle_sensor_data
kaiser/god/esp/+/actuator/+/status      → actuator_handler.handle_actuator_status
kaiser/god/esp/+/actuator/+/response    → actuator_response_handler.handle_actuator_response
kaiser/god/esp/+/actuator/+/alert       → actuator_alert_handler.handle_actuator_alert
kaiser/god/esp/+/system/heartbeat       → heartbeat_handler.handle_heartbeat
kaiser/god/discovery/esp32_nodes        → discovery_handler.handle_discovery
kaiser/god/esp/+/config_response        → config_handler.handle_config_ack
kaiser/god/esp/+/zone/ack               → zone_ack_handler.handle_zone_ack
kaiser/god/esp/+/subzone/ack            → subzone_ack_handler.handle_subzone_ack
kaiser/god/esp/+/actuator/+/command     → mock_actuator_command_handler (Paket G)
kaiser/god/esp/+/actuator/emergency     → mock_actuator_command_handler (Paket G)
kaiser/broadcast/emergency              → mock_actuator_command_handler (Paket G)
```

---

## Teil 2: Frontend-Startup-Sequenz

### Wie man das Frontend startet

```bash
cd "El Frontend"
npm run dev
```

### Frontend-Initialisierungsreihenfolge

Die `main.ts` orchestriert den Frontend-Start:

| Step | Aktion | Code-Location | Details |
|------|--------|---------------|---------|
| **1** | Vue App Creation | `main.ts:9` | `createApp(App)` |
| **2** | Pinia Store Init | `main.ts:11` | `app.use(createPinia())` |
| **3** | Router Init | `main.ts:12` | `app.use(router)` |
| **4** | Mount App | `main.ts:14` | `app.mount('#app')` |

### Auth-Flow beim Start (Navigation Guards)

Der Router (`router/index.ts:111-140`) führt bei jeder Navigation folgende Prüfungen durch:

```
┌─────────────────────────────────────────────────────────────┐
│                    Navigation Guard Flow                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ setupRequired === null?       │
              └───────────────────────────────┘
                       │ yes
                       ▼
              ┌───────────────────────────────┐
              │ await authStore.checkAuthStatus() │
              │ → GET /api/v1/auth/status     │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ setup_required === true?      │
              └───────────────────────────────┘
                 yes │              │ no
                     ▼              ▼
            ┌──────────────┐  ┌──────────────────────┐
            │ → /setup     │  │ requiresAuth && !auth?│
            └──────────────┘  └──────────────────────┘
                                    yes │     │ no
                                        ▼     ▼
                              ┌──────────┐  ┌──────────┐
                              │ → /login │  │ → Target │
                              └──────────┘  └──────────┘
```

### checkAuthStatus() Ablauf

Datei: `stores/auth.ts:24-63`

1. Ruft `GET /api/v1/auth/status` auf
2. Prüft `setup_required` Flag
3. Falls Setup nötig → `clearAuth()`, Return
4. Falls Token vorhanden → `GET /api/v1/auth/me` für User-Info
5. Falls 401 → Token-Refresh versuchen
6. Falls Refresh fehlschlägt → `clearAuth()`

---

## Teil 3: Server-Reaktion auf ESP-Boot

### Schritt-für-Schritt: Was passiert wenn ESP bootet

| ESP32 Step | ESP32 sendet | Server empfängt | Server reagiert |
|------------|--------------|-----------------|-----------------|
| Step 10 | WiFi + MQTT Connect | - | Connection akzeptiert |
| Nach Step 10 | Initial Heartbeat | `heartbeat_handler.py` | Prüft Registration → Update oder Reject |
| Step 10 | Subscribe Topics | - | ESP subscribed auf Commands |
| Laufend | Sensor-Daten | `sensor_handler.py` | Processing + DB-Speicherung + WebSocket Broadcast |
| Laufend | Actuator-Status | `actuator_handler.py` | Status-Update + WebSocket Broadcast |

### Heartbeat-Handling im Detail

**Datei:** `heartbeat_handler.py`

**Ablauf:**

```
┌─────────────────────────────────────────────────────────────┐
│              Heartbeat Message empfangen                     │
│   Topic: kaiser/god/esp/{esp_id}/system/heartbeat           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 1. Topic parsen → esp_id      │
              │    TopicBuilder.parse_heartbeat_topic() │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 2. Payload validieren         │
              │    Required: ts, uptime,      │
              │    heap_free, wifi_rssi       │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 3. ESP in DB suchen           │
              │    esp_repo.get_by_device_id()│
              └───────────────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             │ not found                        │ found
             ▼                                  ▼
   ┌─────────────────────┐         ┌─────────────────────┐
   │ ❌ REJECT!          │         │ 4. Status → "online"│
   │ "Device must be     │         │ 5. last_seen update │
   │ registered first"   │         │ 6. Metadata update  │
   │ (heartbeat_handler  │         │ 7. WebSocket Broadcast│
   │ :98-109)            │         │    "esp_health"     │
   └─────────────────────┘         └─────────────────────┘
```

**Expected Heartbeat Payload (vom ESP32):**

```json
{
    "esp_id": "ESP_12AB34CD",      // Optional (wird aus Topic extrahiert)
    "zone_id": "zone_main",        // Optional
    "master_zone_id": "master",    // Optional
    "zone_assigned": true,         // Optional
    "ts": 1735818000,              // REQUIRED (Unix timestamp)
    "uptime": 123456,              // REQUIRED (Sekunden)
    "heap_free": 45000,            // REQUIRED (oder free_heap)
    "wifi_rssi": -45,              // REQUIRED (dBm)
    "sensor_count": 3,             // Optional
    "actuator_count": 2            // Optional
}
```

> **Hinweise:**
> - `esp_id` wird primär aus dem **Topic** extrahiert, nicht aus dem Payload
> - Server akzeptiert sowohl `heap_free` (ESP32) als auch `free_heap` (Legacy)
> - `sensor_count`/`actuator_count` sind optional, werden in Metadata gespeichert

### Device-Registration (Voraussetzung)

**KRITISCH:** ESPs MÜSSEN vor dem ersten Heartbeat registriert werden!

**Endpoint:** `POST /api/v1/esp/devices`

**Code-Location:** `api/v1/esp.py:218-302`

**Required Fields:**
- `device_id` (string, z.B. "ESP_12AB34CD")

**Optional Fields:**
- `name` (string)
- `zone_id` (string)
- `zone_name` (string)
- `is_zone_master` (boolean)
- `ip_address` (string)
- `mac_address` (string)
- `firmware_version` (string)
- `hardware_type` (string, default: "ESP32_WROOM")
- `capabilities` (object)

**Beispiel Registration Request:**

```bash
curl -X POST http://localhost:8000/api/v1/esp/devices \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "ESP_12AB34CD",
    "name": "Growbox-Main",
    "hardware_type": "ESP32_WROOM"
  }'
```

---

## Teil 4: Frontend-Sicht (User-Flow)

### Was der User sieht während ESP bootet

#### 1. Vor ESP-Boot: User registriert ESP via Frontend

**Aktuell möglich via:**
- Mock-ESP View: `/mock-esp` (nur für Test-ESPs)
- API-Call: `POST /api/v1/esp/devices` (für echte ESPs)

**Mock-ESP erstellen (Debug API):**
```typescript
// api/debug.ts
debugApi.createMockEsp({
  device_id: "ESP_TEST001",
  name: "Test ESP",
  hardware_type: "ESP32_WROOM"
})
```

#### 2. Während ESP-Boot: User wartet

- Dashboard zeigt ESP als **"unknown"** (Initial-Status bei Registration)
- Kein WebSocket-Update bis Heartbeat empfangen

#### 3. Nach ESP-Boot: User sieht ESP online

1. ESP sendet Heartbeat → Server empfängt
2. Server sendet WebSocket-Broadcast `esp_health`
3. Frontend empfängt via MqttLogView oder Dashboard
4. ESP-Status wechselt zu "online"
5. Sensor-Daten beginnen zu fließen

### WebSocket-Events die das Frontend empfängt

**Endpoint:** `ws://{host}:8000/api/v1/ws/realtime/{client_id}?token={jwt_token}`

**Code-Location:** `views/MqttLogView.vue:56-123`

**Empfangene Event-Types:**

| Type | Beschreibung | Payload-Beispiel |
|------|--------------|------------------|
| `sensor_data` | Sensor-Messwerte | `{ esp_id, gpio, sensor_type, value, ... }` |
| `actuator_status` | Aktor-Statusänderungen | `{ esp_id, gpio, state, pwm_value, ... }` |
| `logic_execution` | Logic-Rule-Ausführung | `{ rule_id, triggered_by, actions, ... }` |
| `esp_health` | ESP-Heartbeat-Daten | `{ esp_id, status, heap_free, wifi_rssi, uptime, ... }` |
| `system_event` | System-Events | `{ event_type, message, ... }` |

**WebSocket-Verbindung herstellen:**

```typescript
// MqttLogView.vue:56-76
const clientId = `frontend_${Date.now()}`
const apiHost = import.meta.env.VITE_API_HOST || 'localhost:8000'
const wsUrl = `ws://${apiHost}/api/v1/ws/realtime/${clientId}?token=${token}`

ws.value = new WebSocket(wsUrl)

ws.value.onopen = () => {
  // Subscribe to all message types
  ws.value?.send(JSON.stringify({
    action: 'subscribe',
    filters: { types: ['sensor_data', 'actuator_status', 'logic_execution', 'esp_health', 'system_event'] }
  }))
}
```

---

## Teil 5: Kompletter Boot-Flow Timeline

```
Zeit    ESP32                    Server                      Frontend
────────────────────────────────────────────────────────────────────────
t=0     Power On                 -                           -
        │
t=0.1s  Serial.begin(115200)     -                           -
        │
t=0.2s  GPIO Safe-Mode Init      -                           -
        │
t=0.3s  Logger Init              -                           -
        │
t=0.5s  NVS/Config Load          -                           -
        │
t=1.0s  WiFi Connect Start       -                           User wartet
        │                                                    (ESP "unknown")
t=3-10s WiFi Connected           -                           -
        │
t=10s   MQTT Connect             MQTT Connection akzeptiert  -
        │
t=10.1s Initial Heartbeat ──────────────────────────────────────────────►
        │                        │
        │                        ▼
        │                   heartbeat_handler:
        │                   - ESP in DB suchen
        │                   - Status → "online"
        │                   - last_seen update
        │                        │
        │                        ▼
        │                   WebSocket Broadcast ─────────────────────────►
        │                   "esp_health"                     │
        │                                                    ▼
        │                                               ESP online anzeigen
        │
t=10.2s Subscribe Topics         -                           -
        (system/command,
         config, actuator/+/command,
         zone/assign, emergency)
        │
t=15s   Sensor-Daten ────────────────────────────────────────────────────►
        │                        │
        │                        ▼
        │                   sensor_handler:
        │                   - Payload validieren
        │                   - DB speichern
        │                   - Pi-Enhanced Processing (optional)
        │                        │
        │                        ▼
        │                   WebSocket Broadcast ─────────────────────────►
        │                   "sensor_data"                    │
        │                                                    ▼
        │                                               Sensor-Werte anzeigen
        │
t=∞     Loop: Sensors + Heartbeats alle 60s
```

---

## Teil 6: Troubleshooting

### ESP bootet, aber Server reagiert nicht

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| "Heartbeat rejected: Unknown device" in Server-Logs | ESP nicht registriert | `POST /api/v1/esp/devices` aufrufen |
| Keine Logs im Server | MQTT Broker nicht erreichbar | Mosquitto prüfen (`systemctl status mosquitto`) |
| ESP zeigt "MQTT connection failed" | Falscher Broker-Host/Port | `wifi_config.server_address` prüfen |
| Heartbeat kommt an, aber WebSocket-Event fehlt | WebSocket nicht verbunden | Browser-Console prüfen, Token gültig? |

### Frontend zeigt ESP nicht als online

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| WebSocket "Disconnected" | Token abgelaufen | Neu einloggen |
| Events kommen nicht an | Falscher VITE_API_HOST | `.env` prüfen (`VITE_API_HOST=localhost:8000`) |
| ESP bleibt "unknown" | ESP nicht registriert | Registrierung prüfen |
| ESP bleibt "offline" | Heartbeat nicht empfangen | Server-Logs für Heartbeat-Handler prüfen |

### Server-Logs prüfen

```bash
# Server im Foreground starten (sieht Logs direkt)
cd "El Servador/god_kaiser_server"
poetry run uvicorn god_kaiser_server.src.main:app --reload --log-level debug

# Nach Heartbeat-Handling suchen
# Erfolg: "Heartbeat processed: esp_id=ESP_..."
# Fehler: "❌ Heartbeat rejected: Unknown device ESP_... Device must be registered first via API."
```

### Frontend WebSocket-Debug

```javascript
// Browser Console
// WebSocket-Messages sehen
// → /mqtt-log View öffnen und auf Events warten
```

---

## Code-Locations Referenz

| Komponente | Pfad | Relevante Funktionen |
|------------|------|---------------------|
| **Server Startup** | `El Servador/god_kaiser_server/src/main.py` | `lifespan()` (Zeilen 76-488) |
| **Heartbeat Handler** | `El Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py` | `handle_heartbeat()` (Zeilen 55-177) |
| **ESP Registration API** | `El Servador/god_kaiser_server/src/api/v1/esp.py` | `register_device()` (Zeilen 232-305) |
| **ESP Service** | `El Servador/.../services/esp_service.py` | `register_device()`, `update_health()` |
| **Frontend Router** | `El Frontend/src/router/index.ts` | Navigation Guards (Zeilen 129-158) |
| **Auth Store** | `El Frontend/src/stores/auth.ts` | `checkAuthStatus()` (Zeilen 24-63) |
| **API Interceptor** | `El Frontend/src/api/index.ts` | Token-Refresh (Zeilen 31-70) |
| **WebSocket View** | `El Frontend/src/views/MqttLogView.vue` | WebSocket Subscription (Zeilen 123-131) |
| **Debug API** | `El Frontend/src/api/debug.ts` | `createMockEsp()` (Zeilen 48-51) |

---

## Verifizierungscheckliste

### ESP32-Doku Verifiziert (gegen aktuellen Code)

- [x] Boot-Reihenfolge stimmt (13 Steps in main.cpp)
- [x] `initializeAllPinsToSafeMode()` existiert (gpio_manager.cpp:31)
- [x] `heap_free` wird im Heartbeat verwendet (mqtt_client.cpp:458)
- [x] MQTT-Topics stimmen mit TopicBuilder überein
- [x] Heartbeat-Payload-Struktur korrekt

### Server-Doku Verifiziert

- [x] Startup-Reihenfolge stimmt mit main.py lifespan() überein
- [x] Heartbeat-Handler-Logic korrekt (Auto-Discovery deaktiviert)
- [x] Device-Registration-Endpoint korrekt dokumentiert
- [x] WebSocket-Manager initialisiert in Step 5

### Frontend-Doku Verifiziert

- [x] Startup-Reihenfolge stimmt mit main.ts überein
- [x] Navigation Guards korrekt dokumentiert
- [x] WebSocket-Endpoint korrekt (`/api/v1/ws/realtime/{client_id}`)
- [x] Token-Refresh-Mechanismus dokumentiert

---

**Letzte Verifizierung:** 2025-12-27
**Verifiziert gegen Code-Version:** Git master branch (Commit-Stand: 2025-12-27)

---

## Changelog

| Datum | Version | Änderungen |
|-------|---------|------------|
| 2025-12-27 | 1.2 | Server-Startup erweitert: Resilience Registry, Central Scheduler, SimulationScheduler, MaintenanceService, Mock-ESP Recovery. MQTT Handler erweitert (Zone/Subzone ACK, Mock-Command Handler). Code-Locations aktualisiert. |
| 2025-12-17 | 1.1 | Korrekturen nach Verifizierung: Server-Start-Pfad (`god_kaiser_server/`), Heartbeat-Payload Required/Optional Fields, Initial-Status "unknown", exakte Rejection-Message |
| 2025-12-17 | 1.0 | Initiale Erstellung, vollständig verifiziert gegen aktuellen Code |
