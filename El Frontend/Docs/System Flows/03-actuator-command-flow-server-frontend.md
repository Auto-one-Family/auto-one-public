# Actuator Command Flow - Server & Frontend Perspektive

## Overview

Bidirektionaler Flow für Actuator-Steuerung:
1. **Server → ESP32:** Commands senden (API/Logic Engine)
2. **ESP32 → Server:** Response/Status/Alert empfangen

Gespiegelte Dokumentation zu `El Trabajante/docs/system-flows/03-actuator-command-flow.md`.

**Korrespondiert mit:** `El Trabajante/docs/system-flows/03-actuator-command-flow.md`

---

## Voraussetzungen

- [ ] Server läuft (`localhost:8000`)
- [ ] Frontend läuft (`localhost:5173`)
- [ ] MQTT Broker erreichbar (Mosquitto auf Port 1883)
- [ ] **ESP32 ist registriert und online** (Heartbeat aktiv)
- [ ] Mindestens ein Actuator konfiguriert
- [ ] Kein Emergency-Stop aktiv (sofern Command nicht E-Stop ist)

---

## Teil 1: Command senden (Server → ESP32)

### Trigger-Quellen für Actuator Commands

| Quelle | Trigger | Code-Location |
|--------|---------|---------------|
| **REST API** | User-Aktion im Frontend | `api/v1/actuators.py:339-428` |
| **Debug API** | Mock-ESP Test-Steuerung | `api/v1/debug.py` |
| **Logic Engine** | Sensor-Threshold überschritten | `services/logic/actions/actuator_executor.py:39-132` |
| **Emergency Stop** | Manuell oder automatisch | `api/v1/actuators.py:515-648` |

### REST API Endpoint

**Endpoint:** `POST /api/v1/actuators/{esp_id}/{gpio}/command`

**Code-Location:** `El Servador/god_kaiser_server/src/api/v1/actuators.py:339-428`

**Request Body:**

```json
{
    "command": "ON",      // ON, OFF, PWM, TOGGLE
    "value": 1.0,         // 0.0-1.0 für PWM
    "duration": 0         // Sekunden (0 = unbegrenzt)
}
```

**Response (Erfolg):**

```json
{
    "success": true,
    "esp_id": "ESP_12AB34CD",
    "gpio": 5,
    "command": "ON",
    "value": 1.0,
    "command_sent": true,
    "acknowledged": false,
    "safety_warnings": []
}
```

**Response (Fehler - Safety):**

```json
{
    "detail": "Command rejected by safety validation or MQTT publish failed"
}
```

**Authentifizierung:** Erfordert `OperatorUser` oder höher (Zeile 355)

### Server Command-Flow

```
┌─────────────────────────────────────────────────────────────┐
│     Command Request (API oder Logic Engine)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 1. API Endpoint aufgerufen    │
              │    send_command()             │
              │    (actuators.py:350-428)     │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 2. ESP & Actuator Lookup      │
              │    esp_repo.get_by_device_id()│
              │    actuator_repo.get_by_esp   │
              │    _and_gpio()                │
              │    (actuators.py:374-395)     │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 3. Actuator enabled?          │
              │    (actuators.py:391-395)     │
              └───────────────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             │ enabled == false                 │ enabled == true
             ▼                                  ▼
   ┌─────────────────────┐         ┌─────────────────────┐
   │ ❌ HTTP 400         │         │ 4. ActuatorService  │
   │ "Actuator is        │         │    .send_command()  │
   │  disabled"          │         │    (actuators.py    │
   └─────────────────────┘         │     :398-405)       │
                                   └─────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────────┐
                                   │ 5. Safety Validation│
                                   │    (intern in       │
                                   │     ActuatorService)│
                                   └─────────────────────┘
                                            │
                          ┌─────────────────┴─────────────────┐
                          │ valid == false                     │ valid == true
                          ▼                                    ▼
                ┌─────────────────────┐          ┌─────────────────────┐
                │ ❌ Return False     │          │ 6. MQTT Publish     │
                │ API throws HTTP 400 │          │ publish_actuator_   │
                │ "Command rejected"  │          │ command()           │
                └─────────────────────┘          │ (publisher.py:38-72)│
                                                 │ QoS: 2              │
                                                 └─────────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────────┐
                                                 │ 7. ESP32 empfängt   │
                                                 │ auf Topic:          │
                                                 │ .../actuator/{gpio}/│
                                                 │ command             │
                                                 └─────────────────────┘
```

### ActuatorService.send_command()

**Datei:** `El Servador/god_kaiser_server/src/services/actuator_service.py`

**Methode:** `send_command()` (Zeilen 44-193)

**Parameter:**

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `esp_id` | str | ESP Device ID |
| `gpio` | int | GPIO Pin-Nummer |
| `command` | str | Command-Typ (ON, OFF, PWM, TOGGLE) |
| `value` | float | Wert (0.0-1.0) |
| `duration` | int | Dauer in Sekunden (0 = unbegrenzt) |
| `issued_by` | str | Auslöser (z.B. "user:admin", "logic:rule_123") |

**Ablauf:**

1. Safety Validation aufrufen
2. Bei Erfolg: MQTT Publish
3. Command in History loggen
4. Boolean zurückgeben (True = Erfolg)

### MQTT Command Publishing

**Datei:** `El Servador/god_kaiser_server/src/mqtt/publisher.py`

**Methode:** `publish_actuator_command()` (Zeilen 38-72)

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`

**QoS:** 2 (Exactly once) - definiert in `constants.py:169`

**Retry-Logik:** 3 Versuche mit 1 Sekunde Delay (Zeilen 228-242)

**Payload (Server → ESP32):**

```json
{
    "command": "ON",
    "value": 1.0,
    "duration": 0,
    "timestamp": 1735818000
}
```

### Emergency Stop Endpoint

**Endpoint:** `POST /api/v1/actuators/emergency_stop`

**Code-Location:** `El Servador/god_kaiser_server/src/api/v1/actuators.py:515-648`

**Request Body:**

```json
{
    "esp_id": "ESP_12AB34CD",  // Optional - wenn leer: alle ESPs
    "gpio": 5,                  // Optional - wenn leer: alle Aktoren
    "reason": "Manual emergency stop"
}
```

**Response:**

```json
{
    "success": true,
    "message": "Emergency stop executed",
    "devices_stopped": 3,
    "actuators_stopped": 12,
    "reason": "Manual emergency stop",
    "timestamp": "2025-12-17T10:30:00Z",
    "details": [
        {
            "esp_id": "ESP_12AB34CD",
            "actuators": [
                {"esp_id": "ESP_12AB34CD", "gpio": 5, "success": true, "message": null}
            ]
        }
    ]
}
```

**Wichtig:** Emergency Stop sendet `OFF` Commands an alle betroffenen Aktoren via MQTT (Zeilen 577-585).

---

## Teil 2: Response/Status empfangen (ESP32 → Server)

### Topics die der Server empfängt

| Topic | Handler | QoS | Zweck |
|-------|---------|-----|-------|
| `.../actuator/{gpio}/status` | `actuator_handler.py` | 1 | Aktueller Zustand |
| `.../actuator/{gpio}/response` | `actuator_response_handler.py` | 1 | Command-Bestätigung |
| `.../actuator/{gpio}/alert` | `actuator_alert_handler.py` | 1 | Sicherheits-Alerts |

### Status Handling

**Datei:** `El Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py`

**Klasse:** `ActuatorStatusHandler`

**Methode:** `handle_actuator_status()` (Zeilen 34-186)

**Subscribed Topic:** `kaiser/god/esp/+/actuator/+/status`

**Erwarteter Payload vom ESP32:**

```json
{
    "ts": 1735818000,
    "esp_id": "ESP_12AB34CD",
    "gpio": 18,
    "actuator_type": "pump",
    "state": "on",               // oder true/false (boolean)
    "value": 255,                // oder "pwm": 255
    "last_command": "on",
    "runtime_ms": 3600000,
    "error": null
}
```

**Required Fields:** `ts`, `esp_id`, `gpio`, `actuator_type` (oder `type`), `state`, `value` (oder `pwm`)

**Payload-Validierung:** `_validate_payload()` (Zeilen 195-263)

**Server-Verarbeitung:**

| Step | Aktion | Code-Location |
|------|--------|---------------|
| 1 | Topic parsen | `actuator_handler.py:62-68` |
| 2 | Payload validieren | `actuator_handler.py:75-81` |
| 3 | ESP Lookup | `actuator_handler.py:88-92` |
| 4 | Actuator Config laden | `actuator_handler.py:94-102` |
| 5 | State konvertieren (bool→string) | `actuator_handler.py:107-110` |
| 6 | DB Update: `actuator_repo.update_state()` | `actuator_handler.py:125-135` |
| 7 | History loggen (wenn last_command) | `actuator_handler.py:138-153` |
| 8 | WebSocket Broadcast | `actuator_handler.py:170-184` |

**WebSocket Event:** `actuator_status`

**WebSocket Payload:**

```json
{
    "esp_id": "ESP_12AB34CD",
    "gpio": 18,
    "actuator_type": "pump",
    "state": "on",
    "value": 255,
    "emergency": "normal",
    "timestamp": 1735818000
}
```

### Response Handling

**Datei:** `El Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py`

**Klasse:** `ActuatorResponseHandler`

**Methode:** `handle_actuator_response()` (Zeilen 54-160)

**Subscribed Topic:** `kaiser/god/esp/+/actuator/+/response`

**Erwarteter Payload vom ESP32:**

```json
{
    "esp_id": "ESP_12AB34CD",
    "zone_id": "zone_main",
    "ts": 1733000000,
    "gpio": 25,
    "command": "ON",
    "value": 1.0,
    "duration": 0,
    "success": true,
    "message": "Command executed"
}
```

**Required Fields:** `ts`, `esp_id`, `gpio`, `command`, `success`

**Server-Verarbeitung:**

| Step | Aktion | Code-Location |
|------|--------|---------------|
| 1 | Payload validieren | `actuator_response_handler.py:67-72` |
| 2 | Timestamp konvertieren | `actuator_response_handler.py:87` |
| 3 | ESP Lookup | `actuator_response_handler.py:94-102` |
| 4 | History loggen | `actuator_response_handler.py:105-120` |
| 5 | Erfolg/Fehler loggen | `actuator_response_handler.py:125-135` |
| 6 | WebSocket Broadcast | `actuator_response_handler.py:138-151` |

**WebSocket Event:** `actuator_response`

**WebSocket Payload:**

```json
{
    "esp_id": "ESP_12AB34CD",
    "gpio": 25,
    "command": "ON",
    "value": 1.0,
    "success": true,
    "message": "Command executed",
    "timestamp": 1733000000
}
```

### Alert Handling

**Datei:** `El Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py`

**Klasse:** `ActuatorAlertHandler`

**Methode:** `handle_actuator_alert()` (Zeilen 66-197)

**Subscribed Topic:** `kaiser/god/esp/+/actuator/+/alert`

**Erwarteter Payload vom ESP32:**

```json
{
    "esp_id": "ESP_12AB34CD",
    "zone_id": "zone_main",
    "ts": 1733000000,
    "gpio": 25,
    "alert_type": "emergency_stop",
    "message": "Actuator stopped due to safety constraint"
}
```

**Required Fields:** `ts`, `esp_id`, `gpio`, `alert_type` (oder `type`)

**Alert-Types und Severity:** (Zeilen 44-49)

| Alert-Type | Severity | Beschreibung |
|------------|----------|--------------|
| `emergency_stop` | critical | Manueller oder automatischer E-Stop |
| `runtime_protection` | warning | Max Runtime überschritten, auto-gestoppt |
| `safety_violation` | critical | Safety Constraint verletzt |
| `hardware_error` | error | Hardware-Fehler erkannt |

**Server-Verarbeitung:**

| Step | Aktion | Code-Location |
|------|--------|---------------|
| 1 | Payload validieren | `actuator_alert_handler.py:79-84` |
| 2 | Severity bestimmen | `actuator_alert_handler.py:93` |
| 3 | Mit entsprechendem Level loggen | `actuator_alert_handler.py:96-111` |
| 4 | ESP Lookup | `actuator_alert_handler.py:121-129` |
| 5 | Alert in History loggen | `actuator_alert_handler.py:131-148` |
| 6 | State auf OFF setzen (bei E-Stop) | `actuator_alert_handler.py:151-168` |
| 7 | WebSocket Broadcast | `actuator_alert_handler.py:173-188` |

**WebSocket Event:** `actuator_alert`

**WebSocket Payload:**

```json
{
    "esp_id": "ESP_12AB34CD",
    "gpio": 25,
    "alert_type": "emergency_stop",
    "severity": "critical",
    "message": "Actuator stopped due to safety constraint",
    "zone_id": "zone_main",
    "timestamp": 1733000000
}
```

---

## Teil 3: Frontend-Sicht (User-Flow)

### Wo der User Aktoren steuern kann

#### 1. Actuators View (`/actuators`)

**Datei:** `El Frontend/src/views/ActuatorsView.vue`

**Features:**

- Liste aller Aktoren über alle ESPs (Zeile 39-47)
- Globaler Emergency Stop Button (Zeile 174-180)
- Quick Stats: Active/Inactive/E-Stop Count (Zeile 81-89)
- Filter nach ESP ID, Actuator Type, State (Zeile 50-71)
- Toggle ON/OFF per Actuator (Zeile 170-172)

**Datenquelle:** `mockEspStore.fetchAll()` (REST API Polling)

#### 2. Mock ESP Detail (`/mock-esp/{id}`)

**Datei:** `El Frontend/src/views/MockEspDetailView.vue`

**Features:**

- Per-Actuator ON/OFF Toggle (Zeile 200-202)
- Emergency Stop für diesen ESP (Zeile 132-135)
- Clear Emergency Button (Zeile 138-140)
- Status-Anzeige (ON/OFF, E-STOP Badge)
- Actuator hinzufügen Modal

### User-Aktionen und API Calls

| User-Aktion | UI Element | API Call | Code-Location |
|-------------|------------|----------|---------------|
| Actuator ON/OFF | Toggle Button | `mockEspStore.setActuatorState()` | `ActuatorsView.vue:170-172` |
| Emergency Stop (ESP) | Red Button | `mockEspStore.emergencyStop()` | `MockEspDetailView.vue:214-218` |
| Emergency Stop (All) | Red Button | `emergencyStopAll()` Loop | `ActuatorsView.vue:174-180` |
| Clear Emergency | Button | `mockEspStore.clearEmergency()` | `MockEspDetailView.vue:220-222` |

### Debug API Funktionen

**Datei:** `El Frontend/src/api/debug.ts`

| Funktion | Endpoint | Beschreibung |
|----------|----------|--------------|
| `setActuatorState()` | `POST /debug/mock-esp/{espId}/actuators/{gpio}` | Setzt Actuator State (Zeilen 194-206) |
| `emergencyStop()` | `POST /debug/mock-esp/{espId}/emergency-stop` | Triggert E-Stop (Zeilen 215-222) |
| `clearEmergency()` | `POST /debug/mock-esp/{espId}/clear-emergency` | Hebt E-Stop auf (Zeilen 227-232) |

### WebSocket Events im Frontend

**Datei:** `El Frontend/src/views/MqttLogView.vue`

**Event-Types die empfangen werden:**

```typescript
filters: {
  types: [
    'sensor_data',
    'actuator_status',    // ← Actuator Status Updates
    'actuator_response',  // ← Command Responses (wenn implementiert)
    'actuator_alert',     // ← Alerts (wenn implementiert)
    'logic_execution',
    'esp_health',
    'system_event'
  ]
}
```

**UI-Reaktion auf `actuator_status`:**

- Neuer Eintrag im MQTT Log erscheint
- Expandierbarer Payload zeigt Details

> **Hinweis:** Die SensorsView und ActuatorsView nutzen REST API Polling, nicht WebSocket-Push für Live-Updates. Nur `/mqtt-log` zeigt Echtzeit-Events.

---

## Teil 4: Logic Engine Integration

### Wie Sensor-Daten zu Actuator-Commands führen

**Datei:** `El Servador/god_kaiser_server/src/services/logic/actions/actuator_executor.py`

**Klasse:** `ActuatorActionExecutor`

**Methode:** `execute()` (Zeilen 39-132)

```
┌─────────────────────────────────────────────────────────────┐
│ Sensor-Daten empfangen (02-sensor-reading-flow)             │
│ sensor_handler → logic_engine.evaluate_sensor_data()        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ Logic Engine Trigger          │
              │ logic_engine.evaluate_        │
              │ sensor_data()                 │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ Rule Matching                 │
              │ "IF soil_moisture < 30%       │
              │  THEN pump ON for 5min"       │
              └───────────────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             │ Condition FALSE                  │ Condition TRUE
             ▼                                  ▼
           (Ende)                  ┌─────────────────────┐
                                   │ ActuatorActionExecutor│
                                   │ .execute()           │
                                   │ (actuator_executor   │
                                   │  .py:39-132)         │
                                   └─────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────────┐
                                   │ actuator_service.   │
                                   │ send_command()      │
                                   │ (actuator_executor  │
                                   │  .py:91-98)         │
                                   │ issued_by="logic:   │
                                   │  {rule_id}"         │
                                   └─────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────────┐
                                   │ (Same Flow as API)  │
                                   │ Safety → MQTT →     │
                                   │ ESP32               │
                                   └─────────────────────┘
```

### ActuatorActionExecutor Details

**Unterstützte Action-Types:** `"actuator_command"`, `"actuator"` (Zeile 37)

**Action-Parameter:**

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `esp_id` | str | Target ESP Device ID |
| `gpio` | int | Target GPIO Pin |
| `command` | str | ON, OFF, PWM, TOGGLE (default: ON) |
| `value` | float | 0.0-1.0 (default: 1.0) |
| `duration_seconds` | int | Dauer (0 = unbegrenzt) |

**Issued By:** `"logic:{rule_id}"` (Zeile 87)

---

## Teil 5: Kompletter Actuator-Command Timeline

```
Zeit    Frontend                 Server                      ESP32
────────────────────────────────────────────────────────────────────────
t=0     User klickt "Turn ON"    -                           -
        toggleActuator()
        (ActuatorsView.vue:115)
        │
t=0.01s mockEspStore.
        setActuatorState() ──────────────────────────────────────────────►
        (debug.ts:194-206)
        POST /debug/mock-esp/{id}/actuators/{gpio}
        │                        │
        │                        ▼
        │                   Debug API verarbeitet
        │                   (oder Production API: actuators.py:350)
        │                        │
        │                        ▼
        │                   ActuatorService.send_command()
        │                   (actuator_service.py:44)
        │                        │
        │                        ▼
        │                   Safety Validation
        │                   - Emergency Stop aktiv? ❌
        │                   - Value 0.0-1.0? ✓
        │                   - Actuator enabled? ✓
        │                        │
        │                        ▼
        │                   publisher.publish_actuator_command()
        │                   (publisher.py:38-72)
        │                   Topic: kaiser/god/esp/ESP_.../actuator/5/command
        │                   QoS: 2 (Exactly once)
        │                   Payload: {"command":"ON","value":1.0,"duration":0}
        │                        │
        │                        ▼
        │   ◄────────────────────────────────────────────────────────────
        │   HTTP Response: {success: true, command_sent: true}
        │                        │
        │                        └─────────────────────────────────────────►
        │                                                    │
        │                                                    ▼
        │                                               handleActuatorCommand()
        │                                               (actuator_manager.cpp:485-513)
        │                                               - Extract GPIO from topic
        │                                               - Parse payload
        │                                               - Safety check ✓
        │                                               - Execute: controlActuatorBinary()
        │                                                    │
        │                                                    ▼
        │                                               MQTT Publish Response
        │                                               Topic: .../actuator/5/response
        │                        ◄─────────────────────────────────────────
        │                        │
        │                        ▼
        │                   handle_actuator_response()
        │                   (actuator_response_handler.py:54-160)
        │                   - Log success ✓
        │                   - History entry
        │                   - WebSocket broadcast "actuator_response"
        │                        │
        │                                                    │
        │                                                    ▼
        │                                               MQTT Publish Status
        │                                               Topic: .../actuator/5/status
        │                        ◄─────────────────────────────────────────
        │                        │
        │                        ▼
        │                   handle_actuator_status()
        │                   (actuator_handler.py:34-186)
        │                   - DB Update: actuator_states
        │                   - WebSocket broadcast "actuator_status"
        │                        │
        │   ◄────────────────────────────────────────────────────────────
        │   WebSocket: {type:"actuator_status", state:"on", ...}
        │
t=0.1s  MqttLogView zeigt Event
        (wenn offen)
```

---

## Teil 6: Troubleshooting

### Command wird nicht ausgeführt

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| HTTP 400 "Actuator is disabled" | Actuator.enabled = false | Actuator-Config aktivieren |
| HTTP 400 "Command rejected" | Safety Validation failed | E-Stop prüfen, Value-Range prüfen |
| HTTP 404 "ESP device not found" | ESP nicht registriert | ESP via Heartbeat registrieren |
| HTTP 404 "Actuator not found" | Actuator nicht konfiguriert | Actuator über API/UI hinzufügen |
| Command gesendet, keine Response | ESP nicht verbunden | Heartbeat/Connection prüfen |
| MQTT Publish failed | Broker nicht erreichbar | Mosquitto-Status prüfen |

### Frontend zeigt falschen Status

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| Status nicht aktualisiert | REST API Polling | Manueller Page Refresh |
| Toggle springt zurück | Command failed auf ESP | Server-Logs prüfen |
| E-Stop nicht angezeigt | Alert nicht empfangen | ESP32 Alert-Publishing prüfen |

### Server-Logs prüfen

```bash
# Server mit Debug-Level starten
cd "El Servador/god_kaiser_server"
poetry run uvicorn god_kaiser_server.src.main:app --reload --log-level debug

# Nach Actuator-Commands suchen
# Erfolg: "Publishing actuator command to ESP_... GPIO 5: ON (value=1.0)"
# Safety-Fehler: (Error wird geloggt, Command nicht gesendet)
# MQTT-Fehler: "Publish failed after 3 attempts"

# Nach Status-Updates suchen
# Erfolg: "Actuator status updated: id=..., esp_id=ESP_..., gpio=5, state=on, value=255"
# Alert: "🚨 ACTUATOR ALERT [EMERGENCY_STOP]: esp_id=ESP_..., gpio=5"
```

---

## Teil 7: Code-Locations Referenz

| Komponente | Pfad | Relevante Funktionen/Zeilen |
|------------|------|----------------------------|
| **ESP32 Actuator Manager** | `El Trabajante/src/services/actuator/actuator_manager.cpp` | `handleActuatorCommand()` (485-513), `controlActuatorBinary()` (371-388), `publishActuatorStatus()` (624-678) |
| **ESP32 Topic Builder** | `El Trabajante/src/utils/topic_builder.cpp` | `buildActuatorCommandTopic()` (69-78), `buildActuatorStatusTopic()` (80-89), `buildActuatorResponseTopic()` (91-100) |
| **Server ActuatorService** | `El Servador/.../services/actuator_service.py` | `send_command()` (44-193) |
| **Server Publisher** | `El Servador/.../mqtt/publisher.py` | `publish_actuator_command()` (38-72), `_publish_with_retry()` (201-244) |
| **Server Constants** | `El Servador/.../core/constants.py` | `QOS_ACTUATOR_COMMAND = 2` (193) |
| **Server Status Handler** | `El Servador/.../mqtt/handlers/actuator_handler.py` | `handle_actuator_status()` (34-186), `_validate_payload()` (195-263) |
| **Server Response Handler** | `El Servador/.../mqtt/handlers/actuator_response_handler.py` | `handle_actuator_response()` (54-160) |
| **Server Alert Handler** | `El Servador/.../mqtt/handlers/actuator_alert_handler.py` | `handle_actuator_alert()` (66-197), `ALERT_SEVERITY` (44-49) |
| **Server API Endpoints** | `El Servador/.../api/v1/actuators.py` | `send_command()` (350-428), `emergency_stop()` (524-648) |
| **Logic Actuator Executor** | `El Servador/.../services/logic/actions/actuator_executor.py` | `execute()` (39-132) |
| **Frontend Actuators View** | `El Frontend/src/views/ActuatorsView.vue` | `toggleActuator()` (170-172), `emergencyStopAll()` (174-180) |
| **Frontend ESP Detail** | `El Frontend/src/views/MockEspDetailView.vue` | `toggleActuator()` (295-297), `emergencyStop()` (214-218) |
| **Frontend Debug API** | `El Frontend/src/api/debug.ts` | `setActuatorState()` (194-206), `emergencyStop()` (215-222) |

---

## Verifizierungscheckliste

### ESP32-Seite

- [x] Command-Topic: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`
- [x] Response-Topic: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response`
- [x] Status-Topic: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status`
- [x] Alert-Topic: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert`
- [x] Command-Types: ON, OFF, PWM, TOGGLE (set_pwm, set_angle)
- [x] QoS für Commands: 2 (Exactly once)

### Server-Seite (Command senden)

- [x] `publish_actuator_command()` auf Zeilen 38-72 in `publisher.py`
- [x] QoS 2 bestätigt (`constants.py:193`)
- [x] Retry-Logik: 3 Versuche, 1s Delay (`publisher.py:228-242`)
- [x] API Endpoint: `POST /api/v1/actuators/{esp_id}/{gpio}/command`
- [x] Emergency Stop Endpoint: `POST /api/v1/actuators/emergency_stop`

### Server-Seite (Response/Status empfangen)

- [x] `handle_actuator_status()` auf Zeilen 34-186
- [x] `handle_actuator_response()` auf Zeilen 54-160
- [x] `handle_actuator_alert()` auf Zeilen 66-197
- [x] WebSocket-Events: `actuator_status`, `actuator_response`, `actuator_alert`
- [x] DB-Update in `actuator_repo.update_state()`

### Frontend-Seite

- [x] `setActuatorState()` in `debug.ts:194-206`
- [x] `emergencyStop()` in `debug.ts:215-222`
- [x] `clearEmergency()` in `debug.ts:227-232`
- [x] WebSocket-Events werden in MqttLogView verarbeitet

---

**Letzte Verifizierung:** 2025-12-27
**Verifiziert gegen Code-Version:** Git master branch (Commit-Stand: 2025-12-27)

---

## Changelog

| Datum | Version | Änderungen |
|-------|---------|------------|
| 2025-12-27 | 1.1 | Aktualisiert Zeilennummern für Frontend-Code (ActuatorsView.vue, MockEspDetailView.vue) und QOS_ACTUATOR_COMMAND Konstante |
| 2025-12-17 | 1.0 | Initiale Erstellung, vollständig verifiziert gegen aktuellen Code |
