# Runtime Configuration Flow - Server & Frontend Perspektive

## Overview

Wie Server und Frontend ESP32-Sensoren und -Aktoren zur Laufzeit konfigurieren.
Kombinierte Dokumentation für Sensor- und Actuator-Konfiguration.

**Korrespondiert mit:**
- [El Trabajante/docs/system-flows/04-runtime-sensor-config-flow.md](../../../El Trabajante/docs/system-flows/04-runtime-sensor-config-flow.md)
- [El Trabajante/docs/system-flows/05-runtime-actuator-config-flow.md](../../../El Trabajante/docs/system-flows/05-runtime-actuator-config-flow.md)

**Status:** ✅ **SERVER-SEITIG VOLLSTÄNDIG IMPLEMENTIERT** - ⚠️ **FRONTEND-INTEGRATION FEHLT**

---

## ✅ SERVER-SEITE: VOLLSTÄNDIG IMPLEMENTIERT

**Server und ESP32 nutzen dieselbe Topic-Struktur für Config-Messages:**

| Komponente | Topic | Payload-Struktur |
|------------|-------|------------------|
| **ESP32 erwartet** | `kaiser/{kaiser_id}/esp/{esp_id}/config` | `{"sensors": [...], "actuators": [...]}` |
| **Server sendet** | `kaiser/{kaiser_id}/esp/{esp_id}/config` | `{"sensors": [...], "actuators": [...]}` ✅ |

**Implementierungsstatus:**
- ✅ Server-REST-APIs: `/v1/sensors/{esp_id}/{gpio}`, `/v1/actuators/{esp_id}/{gpio}`
- ✅ Config-Response-Handler: `config_handler.py` - Verarbeitet ESP32-Responses mit Audit-Log
- ✅ Config-Publishing: `publish_config()` in `publisher.py:160-203`
- ✅ APIs publishen Config nach DB-Save via `ESPService.send_config()`
- ✅ WebSocket-Broadcast für Config-Responses implementiert

---

## ⚠️ FRONTEND-SEITE: NUR MOCK-ESPS

**Frontend hat KEINE echte Config-Integration:**

**Implementierungsdetails:**
1. ✅ `MQTT_TOPIC_ESP_CONFIG` in `constants.py:27`
2. ✅ `TopicBuilder.build_config_topic()` in `topics.py:83-97`
3. ✅ `Publisher.publish_config()` in `publisher.py:134-194`
4. ✅ `ConfigPayloadBuilder` in `config_builder.py` für ESP32-kompatible Payloads
5. ⚠️ Frontend Production-APIs noch ausstehend

---

## Voraussetzungen

- [ ] Server läuft (`localhost:8000`)
- [ ] Frontend läuft (`localhost:5173`)
- [ ] MQTT Broker erreichbar
- [ ] ESP32 registriert und online
- [ ] User eingeloggt mit entsprechenden Rechten (Operator/Admin)

---

## Teil 1: ESP32-Erwartung (Verifiziert)

### 1.1 MQTT Topics

| Richtung | Topic | Zweck | QoS |
|----------|-------|-------|-----|
| Server → ESP | `kaiser/{kaiser_id}/esp/{esp_id}/config` | Config senden | 1 |
| ESP → Server | `kaiser/{kaiser_id}/esp/{esp_id}/config_response` | Response | 1 |

**Code-Location (ESP32):**
- Topic-Building: [El Trabajante/src/utils/topic_builder.cpp:124-138](../../../El Trabajante/src/utils/topic_builder.cpp)
- Config-Handler: [El Trabajante/src/main.cpp:349-355](../../../El Trabajante/src/main.cpp)

### 1.2 Config-Payload-Struktur (ESP32-Erwartung)

**Sensor + Actuator Config (kombiniert):**
```json
{
  "sensors": [
    {
      "gpio": 4,
      "sensor_type": "ph_sensor",
      "sensor_name": "Water pH",
      "subzone_id": "irrigation",
      "active": true,
      "raw_mode": true
    }
  ],
  "actuators": [
    {
      "gpio": 5,
      "actuator_type": "pump",
      "actuator_name": "Water Pump",
      "subzone_id": "irrigation",
      "active": true,
      "critical": false,
      "inverted_logic": false,
      "default_state": false
    }
  ]
}
```

**Code-Location (ESP32):**
- Sensor-Handler: [El Trabajante/src/services/sensor/sensor_manager.cpp:114-241](../../../El Trabajante/src/services/sensor/sensor_manager.cpp)
- Actuator-Handler: [El Trabajante/src/services/actuator/actuator_manager.cpp:626-694](../../../El Trabajante/src/services/actuator/actuator_manager.cpp)

### 1.3 Config-Response-Struktur (ESP32 sendet)

**Success:**
```json
{
  "type": "sensor",
  "status": "success",
  "count": 1,
  "message": "Configured 1 sensor(s) successfully"
}
```

**Error:**
```json
{
  "type": "sensor",
  "status": "error",
  "error_code": "GPIO_CONFLICT",
  "message": "GPIO 4 already in use by actuator",
  "failed_item": { "gpio": 4, "sensor_type": "ph_sensor", ... }
}
```

**Error Codes:** (aus [El Trabajante/src/models/error_codes.h](../../../El Trabajante/src/models/error_codes.h))
- `JSON_PARSE_ERROR` - Ungültiges JSON
- `MISSING_FIELD` - Pflichtfeld fehlt (`gpio`, `sensor_type`, `sensor_name` oder `actuator_type`, `actuator_name`)
- `TYPE_MISMATCH` - Falscher Datentyp
- `VALIDATION_FAILED` - Validierung fehlgeschlagen
- `GPIO_CONFLICT` - GPIO bereits belegt
- `NVS_WRITE_FAILED` - NVS-Speicher voll oder Fehler
- `UNKNOWN_ERROR` - Unbekannter Fehler

**Code-Location (ESP32):**
- Response-Builder: [El Trabajante/src/services/config/config_response.cpp:1-72](../../../El Trabajante/src/services/config/config_response.cpp)

### 1.4 Sensor Config Fields

| Feld | ESP32 (Payload) | Required | Default | Aliase |
|------|-----------------|----------|---------|--------|
| `gpio` | `gpio` | ✅ | - | - |
| `sensor_type` | `sensor_type` | ✅ | - | - |
| `sensor_name` | `sensor_name` | ✅ | - | `name` |
| `subzone_id` | `subzone_id` | ❌ | `""` | - |
| `active` | `active` | ❌ | `true` | - |
| `raw_mode` | `raw_mode` | ❌ | `true` | - |

**Removal-Trigger:** `"active": false` → Sensor wird entfernt und aus NVS gelöscht

### 1.5 Actuator Config Fields

| Feld | ESP32 (Payload) | Required | Default | Aliase |
|------|-----------------|----------|---------|--------|
| `gpio` | `gpio` | ✅ | - | - |
| `actuator_type` | `actuator_type` | ✅ | - | `type` |
| `actuator_name` | `actuator_name` | ✅ | - | `name` |
| `aux_gpio` | `aux_gpio` | ❌ | `255` | - |
| `subzone_id` | `subzone_id` | ❌ | `""` | - |
| `active` | `active` | ❌ | `true` | - |
| `critical` | `critical` | ❌ | `false` | - |
| `inverted_logic` | `inverted_logic` | ❌ | `false` | - |
| `default_state` | `default_state` | ❌ | `false` | - |
| `default_pwm` | `default_pwm` | ❌ | `0` | - |

**Removal-Trigger:** `"active": false` → Actuator wird entfernt und aus NVS gelöscht

---

## Teil 2: Server-Implementierung (Verifiziert)

### 2.1 REST API Endpoints

#### Sensor-Endpoints

**Create/Update Sensor:**
```
POST /v1/sensors/{esp_id}/{gpio}
```

**Request Body:**
```json
{
  "sensor_type": "ph_sensor",
  "name": "Water pH",
  "enabled": true,
  "interval_ms": 5000,
  "processing_mode": "pi_enhanced",
  "calibration": null,
  "threshold_min": 6.0,
  "threshold_max": 8.0,
  "metadata": {}
}
```

**Delete Sensor:**
```
DELETE /v1/sensors/{esp_id}/{gpio}
```

**Code-Location:**
- API: [El Servador/god_kaiser_server/src/api/v1/sensors.py:261-397](../../../El Servador/god_kaiser_server/src/api/v1/sensors.py)
- Schema: `SensorConfigCreate` (Zeilen 100-129)
- DB-Model: `SensorConfig` (Zeilen 54-97)

#### Actuator-Endpoints

**Create/Update Actuator:**
```
POST /v1/actuators/{esp_id}/{gpio}
```

**Request Body:**
```json
{
  "actuator_type": "pump",
  "name": "Water Pump",
  "enabled": true,
  "max_runtime_seconds": 3600,
  "cooldown_seconds": 60,
  "pwm_frequency": null,
  "metadata": {}
}
```

**Delete Actuator:**
```
DELETE /v1/actuators/{esp_id}/{gpio}
```

**Safety:** Delete sendet automatisch `OFF`-Command vor dem Löschen (Zeile 704-711)

**Code-Location:**
- API: [El Servador/god_kaiser_server/src/api/v1/actuators.py:268-719](../../../El Servador/god_kaiser_server/src/api/v1/actuators.py)
- Schema: `ActuatorConfigCreate` (Zeilen 109-147)
- DB-Model: `ActuatorConfig` (Zeilen 59-106)

### 2.2 Field-Name-Mapping (Server ↔ ESP32)

| ESP32 Field | Server Model Field | Server Schema Field | Notes |
|-------------|-------------------|---------------------|-------|
| `sensor_name` | `sensor_name` | `name` | ⚠️ Different names |
| `actuator_name` | `actuator_name` | `name` | ⚠️ Different names |
| `raw_mode` | - | - | ESP32-only, Server ignoriert |
| `pi_enhanced` | `pi_enhanced` | `processing_mode` | Boolean ↔ String ("pi_enhanced"/"raw") |
| `sample_interval_ms` | `sample_interval_ms` | `interval_ms` | ⚠️ Different names |
| `calibration_data` | `calibration_data` | `calibration` | ⚠️ Different names |
| `sensor_metadata` | `sensor_metadata` | `metadata` | ⚠️ Different names |
| `actuator_metadata` | `actuator_metadata` | `metadata` | ⚠️ Different names |

### 2.3 MQTT Config-Publishing Status

**✅ VOLLSTÄNDIG IMPLEMENTIERT!**

Die REST APIs (`POST /v1/sensors`, `POST /v1/actuators`) speichern in der DB **UND** senden MQTT-Config-Messages an ESP32.

**Implementierte Komponenten:**

1. **Publisher-Methode:** `publisher.publish_config(esp_id, config)` ✅
   - Location: [El Servador/god_kaiser_server/src/mqtt/publisher.py:134-194](../../../El Servador/god_kaiser_server/src/mqtt/publisher.py)

2. **Topic-Builder:** `TopicBuilder.build_config_topic(esp_id)` ✅
   - Location: [El Servador/god_kaiser_server/src/mqtt/topics.py:83-97](../../../El Servador/god_kaiser_server/src/mqtt/topics.py)

3. **Constants:** `MQTT_TOPIC_ESP_CONFIG` ✅
   - Location: [El Servador/god_kaiser_server/src/core/constants.py:27](../../../El Servador/god_kaiser_server/src/core/constants.py)

4. **Config Payload Builder:** `ConfigPayloadBuilder` ✅
   - Location: [El Servador/god_kaiser_server/src/services/config_builder.py](../../../El Servador/god_kaiser_server/src/services/config_builder.py)
   - Konvertiert DB-Models zu ESP32-kompatiblem Payload-Format

5. **API Integration:** ✅
   - `sensors.py:338-352` - Sensor Create/Update publishes config
   - `actuators.py:333-347` - Actuator Create/Update publishes config
   - Beide rufen `ESPService.send_config()` nach DB-Save auf

**Implementiertes Code-Pattern:**

```python
# In sensors.py und actuators.py nach DB-Save (Dependency Injection):
config_builder: ConfigPayloadBuilder = get_config_builder(db)
combined_config = await config_builder.build_combined_config(esp_id, db)

esp_service: ESPService = get_esp_service(db)  # via Dependency Injection
config_sent = await esp_service.send_config(esp_id, combined_config)

if config_sent:
    logger.info(f"Config published to ESP {esp_id} after sensor/actuator create/update")
```

**Dependencies:** (in `deps.py`)
- `get_config_builder(db)` - ConfigPayloadBuilder
- `get_esp_service(db)` - ESPService
- `get_audit_log_repo(db)` - AuditLogRepository

### 2.4 Config-Response-Handler (✅ Funktioniert)

**Subscribed Topic:** `kaiser/god/esp/+/config_response`

**Handler:** `config_handler.py`

**Verarbeitung:**
1. Topic parsen → `esp_id` extrahieren
2. Payload validieren → `status`, `type`, `count`, `message`
3. Bei Success:
   - Log: `✅ Config Response from {esp_id}: {type} ({count} items) - {message}`
   - **Audit-Log:** Response wird in `audit_logs` Tabelle gespeichert ✅
   - WebSocket Broadcast (siehe Teil 2.5)
4. Bei Error:
   - Log: `❌ Config FAILED on {esp_id}: {type} - {message} (Error: {error_code})`
   - **Audit-Log:** Error mit Details wird in `audit_logs` Tabelle gespeichert ✅

### 2.4.1 Audit-Log für Config-Responses (✅ NEU IMPLEMENTIERT)

**Model:** `AuditLog` in `db/models/audit_log.py`

**Repository:** `AuditLogRepository` in `db/repositories/audit_log_repo.py`

**Felder:**
```python
{
    "event_type": "config_response",
    "severity": "info" | "error",
    "source_type": "esp32",
    "source_id": "{esp_id}",
    "status": "success" | "error",
    "message": "{ESP32 message}",
    "details": {
        "config_type": "sensor" | "actuator",
        "count": 3,
        "failed_item": {...}  # nur bei Fehler
    },
    "error_code": "MISSING_FIELD",  # nur bei Fehler
    "error_description": "Required field missing"
}
```

**Query-Methoden:**
- `get_esp_config_history(esp_id)` - Config-Response-Historie für ein ESP
- `get_errors(start_time, end_time)` - Alle Fehler in Zeitraum
- `get_event_counts()` - Statistiken nach Event-Typ
   - WebSocket Broadcast mit Error-Details

**Code-Location:**
- Handler: [El Servador/god_kaiser_server/src/mqtt/handlers/config_handler.py:35-122](../../../El Servador/god_kaiser_server/src/mqtt/handlers/config_handler.py)
- Validation: `_validate_payload()` (Zeilen 124-160)

### 2.5 WebSocket Broadcast (✅ Funktioniert)

**Event-Type:** `"config_response"`

**Payload:**
```json
{
  "esp_id": "ESP_12AB34CD",
  "config_type": "sensor",
  "status": "success",
  "count": 1,
  "message": "Configured 1 sensor(s) successfully",
  "timestamp": 1234567890
}
```

**Code-Location:**
- Broadcast: [El Servador/god_kaiser_server/src/mqtt/handlers/config_handler.py:103-116](../../../El Servador/god_kaiser_server/src/mqtt/handlers/config_handler.py)
- WebSocket-Manager: [El Servador/god_kaiser_server/src/websocket/manager.py](../../../El Servador/god_kaiser_server/src/websocket/manager.py)

---

## Teil 3: Frontend-Implementierung (❌ **NICHT IMPLEMENTIERT**)

### 3.1 Aktueller Status: **NUR MOCK-ESPS**

**Das Frontend hat KEINE echte Config-Integration mit Server-APIs.**

**Was existiert (nur für Mock-ESPs):**

**API:** [El Frontend/src/api/debug.ts](../../src/api/debug.ts)
```typescript
// NUR für Mock-ESPs!
// Sensor hinzufügen
async addSensor(espId: string, config: MockSensorConfig): Promise<CommandResponse>
// POST /debug/mock-esp/{espId}/sensors

// Actuator hinzufügen
async addActuator(espId: string, config: MockActuatorConfig): Promise<CommandResponse>
// POST /debug/mock-esp/{espId}/actuators
```

**UI:** [El Frontend/src/views/MockEspDetailView.vue](../../src/views/MockEspDetailView.vue)
- Sensor-Form: Zeilen 55-155
- Actuator-Form: Zeilen 84-161
- Nutzt `mockEspStore.addSensor()` und `mockEspStore.addActuator()`

**Store:** [El Frontend/src/stores/mockEsp.ts](../../src/stores/mockEsp.ts)
- `addSensor()`: Zeilen 137-149
- `addActuator()`: Zeilen 200-212
- Nutzt `debugApi`

### 3.2 Was FEHLT: Echte Config-Integration

❌ **Echte Sensor/Actuator-APIs nicht integriert**

Obwohl die APIs existieren, werden sie NICHT verwendet:
- ✅ `src/api/sensors.ts` existiert mit `createOrUpdate()`
- ✅ `src/api/actuators.ts` existiert mit `createOrUpdate()`
- ❌ **ABER:** Keine View/Store nutzt diese echten APIs

❌ **WebSocket-Handling nicht integriert**

- ✅ `src/composables/useConfigResponse.ts` existiert
- ❌ **ABER:** Keine View verwendet dieses Composable

❌ **DeviceDetailView nutzt nur Mock-Logik**

- `src/views/DeviceDetailView.vue` prüft `isMock()` und verwendet nur Mock-Funktionen
- Keine Integration mit echten Server-APIs

### 3.3 Was implementiert werden sollte

**1. API-Integration:**

```typescript
// El Frontend/src/api/sensors.ts (NEU)
export const sensorsApi = {
  /**
   * Create or update sensor configuration
   */
  async createOrUpdate(
    espId: string,
    gpio: number,
    config: SensorConfigCreate
  ): Promise<SensorConfigResponse> {
    const response = await api.post<SensorConfigResponse>(
      `/v1/sensors/${espId}/${gpio}`,
      config
    )
    return response.data
  },

  /**
   * Delete sensor configuration
   */
  async delete(espId: string, gpio: number): Promise<void> {
    await api.delete(`/v1/sensors/${espId}/${gpio}`)
  }
}

// El Frontend/src/api/actuators.ts (NEU)
export const actuatorsApi = {
  async createOrUpdate(...) { ... }
  async delete(...) { ... }
}
```

**2. WebSocket-Handling:**

```typescript
// El Frontend/src/composables/useConfigResponse.ts (NEU)
import { ref } from 'vue'
import { useWebSocket } from './useWebSocket'

export function useConfigResponse() {
  const lastResponse = ref<ConfigResponse | null>(null)
  const ws = useWebSocket()

  ws.on('config_response', (data: ConfigResponse) => {
    lastResponse.value = data

    if (data.status === 'success') {
      // Show success notification
      showNotification('success', data.message)
      // Refresh sensor/actuator list
      refreshList(data.esp_id)
    } else {
      // Show error notification
      showNotification('error', `Config failed: ${data.message}`)
    }
  })

  return { lastResponse }
}
```

**3. UI-Feedback:**

```vue
<!-- El Frontend/src/views/EspDetailView.vue (NEU) -->
<script setup lang="ts">
import { useConfigResponse } from '@/composables/useConfigResponse'

const { lastResponse } = useConfigResponse()

async function addSensor() {
  try {
    // Call real API
    await sensorsApi.createOrUpdate(espId.value, newSensor.gpio, newSensor)

    // Show loading state
    showNotification('info', 'Sending config to ESP...')

    // WebSocket will handle response and show success/error
  } catch (err) {
    showNotification('error', 'Failed to save config')
  }
}
</script>

<template>
  <!-- Config Response Indicator -->
  <div v-if="lastResponse" class="config-status">
    <Badge :variant="lastResponse.status === 'success' ? 'success' : 'danger'">
      {{ lastResponse.message }}
    </Badge>
  </div>
</template>
```

---

## Teil 4: Kompletter Config-Flow (SOLLTE-Implementierung)

### 4.1 Timeline: Sensor hinzufügen

```
Zeit    Frontend                 Server                      ESP32
────────────────────────────────────────────────────────────────────────
t=0     User klickt "Add Sensor" -                           -
        │
t=0.1s  Form ausfüllen           -                           -
        GPIO: 4
        Type: ph_sensor
        Name: Water pH
        │
t=0.5s  User klickt "Save"       -                           -
        │
t=0.51s API Request ─────────────────────────────────────────────────────►
        POST /v1/sensors/ESP_12AB/4
        {
          "sensor_type": "ph_sensor",
          "name": "Water pH",
          "enabled": true,
          "processing_mode": "pi_enhanced"
        }
        │                        │
        │                        ▼
        │                   1. Validate Request
        │                   2. Check ESP exists
        │                   3. Save to DB
        │                      sensor_repo.create()
        │                        │
        │                        ▼
        │                   4. Build Config Payload
        │                      sensors = [{
        │                        gpio: 4,
        │                        sensor_type: "ph_sensor",
        │                        sensor_name: "Water pH",
        │                        raw_mode: true
        │                      }]
        │                        │
        │                        ▼
        │                   5. MQTT Publish
        │                      publisher.publish_config()
        │                      Topic: kaiser/god/esp/ESP_12AB/config
        │                      QoS: 1
        │                        │
        │   ◄────────────────────────────────────────────────────────────
        │   HTTP 200 OK
        │   { "id": 1, "gpio": 4, ... }
        │
        │   Show notification:
        │   "Config sent, awaiting confirmation..."
        │                        │
        │                        └─────────────────────────────────────────►
        │                                                    │
        │                                                    ▼
        │                                               MQTT Subscriber
        │                                               handleSensorConfig()
        │                                               - Parse JSON
        │                                               - Validate fields
        │                                               - Configure sensor
        │                                               - Save to NVS
        │                                                    │
        │                                                    ▼
        │                                               MQTT Publish Response
        │                        ◄─────────────────────────────────────────
        │                        Topic: .../config_response
        │                        {
        │                          "type": "sensor",
        │                          "status": "success",
        │                          "count": 1,
        │                          "message": "Configured 1 sensor(s) successfully"
        │                        }
        │                        │
        │                        ▼
        │                   config_handler()
        │                   - Log success
        │                   - WebSocket Broadcast
        │                        │
        │   ◄────────────────────────────────────────────────────────────
        │   WebSocket: {
        │     "type": "config_response",
        │     "esp_id": "ESP_12AB34CD",
        │     "status": "success",
        │     ...
        │   }
        │
t=1.0s  useConfigResponse() empfängt Event
        │
        ▼
        Show notification:
        "Sensor configured successfully!"
        │
        ▼
        Refresh sensor list
        Neue Konfiguration sichtbar
```

### 4.2 Error-Handling Timeline

```
Zeit    Event                        Reaktion
────────────────────────────────────────────────────────────────────────
t=0.5s  HTTP 400 Bad Request         Frontend: Validation-Error anzeigen
        (Missing required field)     "Field 'sensor_type' is required"

t=0.5s  HTTP 404 Not Found           Frontend: Error-Toast
        (ESP not found)              "ESP device not found"

t=0.5s  HTTP 500 Server Error        Frontend: Error-Toast
                                     "Server error, please try again"

t=1.0s  WebSocket: config_response   Frontend: Error-Notification
        { status: "error",           "Config failed: GPIO already in use"
          error_code: "GPIO_CONFLICT",
          message: "GPIO 4 already in use by actuator" }

t=5.0s  Timeout (kein Response)      Frontend: Warning
                                     "Config sent, but no confirmation received"
```

---

## Teil 5: Troubleshooting

### 5.1 Config wird nicht angewendet

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| HTTP 200 aber kein Response | ESP nicht verbunden | Heartbeat prüfen (`GET /v1/esp/devices/{esp_id}`) |
| HTTP 200 aber keine MQTT-Message | `publish_config()` nicht implementiert | ⚠️ **Server-Bug** - siehe Teil 2.3 |
| Response: "MISSING_FIELD" | Payload unvollständig | Server-Payload-Generation prüfen |
| Response: "GPIO_CONFLICT" | GPIO bereits belegt | Anderen GPIO wählen oder alten entfernen |
| Response: "NVS_WRITE_FAILED" | NVS voll | ESP neu flashen oder NVS löschen |
| Kein WebSocket-Event | Frontend nicht connected | WebSocket-Verbindung prüfen |
| WebSocket-Event aber keine UI-Änderung | Handler nicht implementiert | ⚠️ **Frontend-Implementierung fehlt** - siehe Teil 3.3 |

### 5.2 Debugging-Schritte

**1. Server-Logs prüfen:**

```bash
cd "El Servador"

# Nach Config-API-Call suchen
# Erfolg: "Sensor created: ESP_12AB34CD GPIO 4 by admin"
# Fehler: "ESP device 'ESP_12AB34CD' not found"

# Nach MQTT-Publishing suchen (sollte vorhanden sein, ist aber NICHT implementiert!)
# Erfolg: "Publishing config to ESP_12AB34CD: 1 sensors, 0 actuators"
# ⚠️ FEHLT: Diese Log-Message erscheint NICHT, weil publish_config() nicht existiert!

# Nach Config-Response suchen
# Erfolg: "✅ Config Response from ESP_12AB34CD: sensor (1 items) - Configured 1 sensor(s) successfully"
# Fehler: "❌ Config FAILED on ESP_12AB34CD: sensor - GPIO 4 already in use (Error: GPIO_CONFLICT)"
```

**2. ESP32 Serial Monitor:**

```bash
cd "El Trabajante"
~/.platformio/penv/Scripts/platformio.exe device monitor

# Nach Config-Message suchen
[INFO] MQTT: Received message on topic: kaiser/god/esp/ESP_12AB34CD/config
[INFO] Config: Processing sensor config...
[INFO] Config: Configured 1 sensor(s) successfully
[INFO] MQTT: Published config response: success
```

**3. Frontend DevTools:**

```javascript
// WebSocket-Events im Browser-Console prüfen
localStorage.setItem('debug', 'websocket:*')

// Console zeigt:
// websocket:config_response {esp_id: "ESP_12AB34CD", status: "success", ...}
```

**4. MQTT-Broker-Logs:**

```bash
# MQTT-Message direkt abfangen (mosquitto_sub)
mosquitto_sub -h localhost -t "kaiser/god/esp/+/config" -v
# Sollte zeigen: kaiser/god/esp/ESP_12AB34CD/config {"sensors": [...]}
# ⚠️ Zeigt NICHTS, weil Server nicht published!

mosquitto_sub -h localhost -t "kaiser/god/esp/+/config_response" -v
# Zeigt: kaiser/god/esp/ESP_12AB34CD/config_response {"status": "success", ...}
```

---

## Teil 6: Code-Locations Referenz

### ESP32 (El Trabajante/)

| Komponente | Pfad | Zeilen | Funktion |
|------------|------|--------|----------|
| **Config-Topic-Building** | [src/utils/topic_builder.cpp](../../../El Trabajante/src/utils/topic_builder.cpp) | 124-138 | `buildConfigTopic()`, `buildConfigResponseTopic()` |
| **Config-Routing** | [src/main.cpp](../../../El Trabajante/src/main.cpp) | 349-355 | MQTT-Subscribe und Handler-Routing |
| **Sensor Config** | [src/services/sensor/sensor_manager.cpp](../../../El Trabajante/src/services/sensor/sensor_manager.cpp) | 114-241 | `configureSensor()` - Verarbeitet Sensor-Config |
| **Actuator Config** | [src/services/actuator/actuator_manager.cpp](../../../El Trabajante/src/services/actuator/actuator_manager.cpp) | 626-694 | `handleActuatorConfig()` - Verarbeitet Actuator-Config |
| **Config Response** | [src/services/config/config_response.cpp](../../../El Trabajante/src/services/config/config_response.cpp) | 1-72 | `publishSuccess()`, `publishError()` |
| **Error Codes** | [src/models/error_codes.h](../../../El Trabajante/src/models/error_codes.h) | - | Alle ConfigErrorCode-Definitionen |

### Server (El Servador/)

| Komponente | Pfad | Zeilen | Funktion |
|------------|------|--------|----------|
| **Sensor API** | [god_kaiser_server/src/api/v1/sensors.py](../../../El Servador/god_kaiser_server/src/api/v1/sensors.py) | 273-431 | `POST /{esp_id}/{gpio}`, `DELETE /{esp_id}/{gpio}` + Config Publishing |
| **Actuator API** | [god_kaiser_server/src/api/v1/actuators.py](../../../El Servador/god_kaiser_server/src/api/v1/actuators.py) | 280-447 | `POST /{esp_id}/{gpio}`, `DELETE /{esp_id}/{gpio}` + Config Publishing |
| **Config Handler** | [god_kaiser_server/src/mqtt/handlers/config_handler.py](../../../El Servador/god_kaiser_server/src/mqtt/handlers/config_handler.py) | 35-122 | `handle_config_ack()` - Verarbeitet Config-Responses |
| **Publisher** | [god_kaiser_server/src/mqtt/publisher.py](../../../El Servador/god_kaiser_server/src/mqtt/publisher.py) | 134-194 | ✅ `publish_config()` - Publishes combined config |
| **Topic Builder** | [god_kaiser_server/src/mqtt/topics.py](../../../El Servador/god_kaiser_server/src/mqtt/topics.py) | 83-97 | ✅ `build_config_topic()` - Builds combined config topic |
| **Constants** | [god_kaiser_server/src/core/constants.py](../../../El Servador/god_kaiser_server/src/core/constants.py) | 27 | ✅ `MQTT_TOPIC_ESP_CONFIG` - Combined config topic pattern |
| **Config Builder** | [god_kaiser_server/src/services/config_builder.py](../../../El Servador/god_kaiser_server/src/services/config_builder.py) | 1-222 | ✅ `ConfigPayloadBuilder` - ESP32-kompatible Payloads |
| **ESP Service** | [god_kaiser_server/src/services/esp_service.py](../../../El Servador/god_kaiser_server/src/services/esp_service.py) | 256-286 | ✅ `send_config()` - Sends config via MQTT |

### Frontend (El Frontend/)

| Komponente | Pfad | Zeilen | Status |
|------------|------|--------|--------|
| **Mock API** | [src/api/debug.ts](../../src/api/debug.ts) | 127-149 | ✅ Funktioniert (nur Mock-ESPs) |
| **Mock View** | [src/views/MockEspDetailView.vue](../../src/views/MockEspDetailView.vue) | 141-161 | ✅ Funktioniert (nur Mock-ESPs) |
| **Mock Store** | [src/stores/mockEsp.ts](../../src/stores/mockEsp.ts) | 137-212 | ✅ Funktioniert (nur Mock-ESPs) |
| **Real Sensor API** | [src/api/sensors.ts](../../src/api/sensors.ts) | 8-22 | ✅ **EXISTIERT ABER NICHT VERWENDET** |
| **Real Actuator API** | [src/api/actuators.ts](../../src/api/actuators.ts) | 8-22 | ✅ **EXISTIERT ABER NICHT VERWENDET** |
| **Config Response Hook** | [src/composables/useConfigResponse.ts](../../src/composables/useConfigResponse.ts) | 18-97 | ✅ **EXISTIERT ABER NICHT VERWENDET** |
| **DeviceDetailView** | [src/views/DeviceDetailView.vue](../../src/views/DeviceDetailView.vue) | - | ⚠️ **NUTZT NUR MOCK-APIs** |

---

## Teil 7: Implementierungs-Roadmap

### Phase 1: Server Config-Publishing ✅ ABGESCHLOSSEN

**Status:** VOLLSTÄNDIG IMPLEMENTIERT

**Implementierte Komponenten:**
1. ✅ `MQTT_TOPIC_ESP_CONFIG` in `constants.py:27`
2. ✅ `TopicBuilder.build_config_topic(esp_id)` in `topics.py:83-97`
3. ✅ `Publisher.publish_config(esp_id, config)` in `publisher.py:134-194`
4. ✅ `ConfigPayloadBuilder` in `config_builder.py` für ESP32-kompatible Payloads
5. ✅ Sensor-API: Ruft `send_config()` nach DB-Save auf (`sensors.py:338-352`)
6. ✅ Actuator-API: Ruft `send_config()` nach DB-Save auf (`actuators.py:333-347`)

**Implementiertes Code-Pattern:**
```python
# In sensors.py und actuators.py nach DB-Save (BEREITS IMPLEMENTIERT):
config_builder: ConfigPayloadBuilder = get_config_builder(db)
combined_config = await config_builder.build_combined_config(esp_id, db)

esp_service = ESPService(esp_repo, get_mqtt_publisher())
config_sent = await esp_service.send_config(esp_id, combined_config)
```

### Phase 2: Frontend Config-APIs (HIGH)

**Aufwand:** ~4-6 Stunden

**Aufgaben:**
1. ✅ `src/api/sensors.ts` erstellen
2. ✅ `src/api/actuators.ts` erstellen
3. ✅ `src/composables/useConfigResponse.ts` erstellen (WebSocket-Handling)
4. ✅ `src/views/EspDetailView.vue` erstellen (echte ESPs)
5. ✅ TypeScript-Types erweitern: `SensorConfigCreate`, `ActuatorConfigCreate`
6. ✅ UI-Notifications integrieren: Success/Error-Toasts

### Phase 3: Frontend WebSocket-Integration (MEDIUM)

**Aufwand:** ~2-3 Stunden

**Aufgaben:**
1. ✅ WebSocket-Hook erweitern: `config_response` Event-Handler
2. ✅ Notification-System integrieren
3. ✅ Auto-Refresh nach Success-Response
4. ✅ Error-Handling: Timeout-Detection, Retry-Logik

### Phase 4: Testing & Documentation (MEDIUM)

**Aufwand:** ~3-4 Stunden

**Aufgaben:**
1. ✅ Integration-Tests: Server → ESP32
2. ✅ E2E-Tests: Frontend → Server → ESP32 → Frontend
3. ✅ Error-Scenario-Tests: GPIO-Conflict, Timeout, etc.
4. ✅ Dokumentation aktualisieren: Dieses Dokument als "VOLLSTÄNDIG IMPLEMENTIERT" markieren

---

## Teil 8: Verifizierungscheckliste

### ESP32-Seite

- [x] Config-Topic korrekt: `kaiser/{kaiser_id}/esp/{esp_id}/config`
- [x] Response-Topic korrekt: `kaiser/{kaiser_id}/esp/{esp_id}/config_response`
- [x] Sensor Required Fields: `gpio`, `sensor_type`, `sensor_name`
- [x] Actuator Required Fields: `gpio`, `actuator_type`, `actuator_name`
- [x] Error Codes vollständig dokumentiert
- [x] QoS: 1 für Config-Messages

### Server-Seite (Config-Sending)

- [x] REST API Endpoints dokumentiert: `/v1/sensors/{esp_id}/{gpio}`, `/v1/actuators/{esp_id}/{gpio}`
- [x] Request Bodies dokumentiert
- [x] Config-Publishing implementiert (`publisher.py:134-194`)
- [x] DB-Speicherung dokumentiert
- [x] `publish_config()` existiert (`publisher.py:134-194`)
- [x] `build_config_topic()` existiert (`topics.py:83-97`)
- [x] `ConfigPayloadBuilder` existiert (`config_builder.py`)
- [x] APIs rufen `send_config()` nach DB-Save auf

### Server-Seite (Config-Response)

- [x] Config Response Handler existiert: `config_handler.py`
- [x] Handler-Funktion: `handle_config_ack()`
- [x] WebSocket Event-Type: `"config_response"`
- [x] Error-Handling implementiert
- [x] Payload-Validation implementiert

### Frontend-Seite

- [ ] ❌ **Echte Config UI implementiert** (Nur Mock-ESPs funktionieren)
- [ ] ❌ **Echte API-Calls integriert** (APIs existieren aber werden nicht verwendet)
- [ ] ❌ **WebSocket Event-Handling integriert** (Composable existiert aber nicht verwendet)
- [ ] ❌ **User Feedback implementiert** (Keine Success/Error-Notifications)

---

## Zusammenfassung

**Was funktioniert:** ✅
- ESP32 Config-Empfang und -Response (vollständig implementiert)
- Server Config-Response-Handling mit Audit-Log (vollständig implementiert)
- Server WebSocket-Broadcast (vollständig implementiert)
- Frontend Mock-ESP-System (vollständig implementiert)
- **Server Config-Publishing (`publish_config()`)** ✅ VOLLSTÄNDIG IMPLEMENTIERT
- **Server Topic-Builder (`build_config_topic()`)** ✅ VOLLSTÄNDIG IMPLEMENTIERT
- **ConfigPayloadBuilder für ESP32-kompatible Payloads** ✅ VOLLSTÄNDIG IMPLEMENTIERT
- **API Integration (Sensor/Actuator APIs rufen send_config auf)** ✅ VOLLSTÄNDIG IMPLEMENTIERT

**Was fehlt:** ❌
- **Frontend echte Config-APIs** (APIs existieren aber werden nicht verwendet)
- **Frontend WebSocket-Handling** (Composable existiert aber nicht integriert)
- **Echte ESP Config-UI** (nur Mock-ESPs funktionieren)
- **User Feedback für Config-Operations** (keine Notifications)

**Nächste Schritte:**
1. ~~**KRITISCH:** Server Config-Publishing implementieren~~ ✅ **ABGESCHLOSSEN**
2. **HIGH:** DeviceDetailView echte Server-APIs integrieren (Phase 2)
3. **HIGH:** useConfigResponse Composable in Views integrieren (Phase 3)
4. **MEDIUM:** Success/Error-Notifications implementieren
5. **LOW:** Audit-Log Query-Methoden für Config-Historie erweitern

---

**Letzte Verifizierung:** 2025-12-27
**Verifiziert gegen Code-Version:** Latest (2025-12-27)
**Dokumentation erstellt von:** Claude Sonnet 4.5 (KI-Agent)
**Code-Analyse durchgeführt von:** Claude Opus 4.5
**Verifizierte Komponenten:**
- ✅ ESP32: El Trabajante - Vollständig implementiert (Config-Empfang/-Response)
- ✅ Server: El Servador - **VOLLSTÄNDIG IMPLEMENTIERT** (Config-Publishing + Response-Handling)
- ⚠️ Frontend: El Frontend - APIs/Composables existieren aber nicht integriert (nur Mock-ESPs)
