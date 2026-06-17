# Actuator-System Vollanalyse

**Erstellt:** 2026-01-09
**Version:** 3.0 (Phase A - Vollständige Verifizierung)
**Status:** Analyse verifiziert gegen tatsächlichen Code
**Analysierte Dateien:** 18 Dateien, ~8.500 Zeilen

---

## 1. Executive Summary

Diese Analyse dokumentiert den vollständigen Datenfluss des Actuator-Systems über alle drei Architekturschichten (ESP32 → Server → Frontend).

**Kernerkenntnisse:**
- ESP32 (El Trabajante): Vollständig implementiert mit Safety Features
- Server (El Servador): Vollständiger MQTT→WebSocket-Handler-Chain, REST API mit `/command` Endpoint
- Frontend (El Frontend): **KRITISCHE LÜCKE** - Keine `sendCommand()` API-Funktion, keine Control-UI

---

## 2. ESP32 Layer (El Trabajante) - Source of Truth

### 2.1 MQTT Topics

#### Outbound (ESP32 → Server)

| Topic | Payload | Trigger | Code-Location |
|-------|---------|---------|---------------|
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status` | `{esp_id, zone_id, subzone_id, ts, gpio, type, state, pwm, runtime_ms, emergency}` | Nach jedem State-Change | [actuator_manager.cpp:771-782](El Trabajante/src/services/actuator/actuator_manager.cpp#L771-L782) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response` | `{esp_id, zone_id, ts, gpio, command, value, duration, success, message}` | Nach Command-Ausführung | [actuator_manager.cpp:816-822](El Trabajante/src/services/actuator/actuator_manager.cpp#L816-L822) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert` | `{esp_id, zone_id, ts, gpio, alert_type, message}` | Bei Safety-Events | [actuator_manager.cpp:824-844](El Trabajante/src/services/actuator/actuator_manager.cpp#L824-L844) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` | `{status, timestamp}` oder `{error}` | Bei Emergency-Stop | [main.cpp:520, 583-626](El Trabajante/src/main.cpp#L520) |

**Topic-Building:** [topic_builder.cpp:86-124](El Trabajante/src/utils/topic_builder.cpp#L86-L124)

#### Inbound (Server → ESP32)

| Topic | Payload | Handler | Code-Location |
|-------|---------|---------|---------------|
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command` | `{command, value?, duration?}` | `handleActuatorCommand()` | [main.cpp:567-573](El Trabajante/src/main.cpp#L567-L573) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/+/command` | Wildcard für alle GPIOs | Subscription Pattern | [main.cpp:517-519](El Trabajante/src/main.cpp#L517-L519) |
| `kaiser/broadcast/emergency` | `{reason}` | Global Emergency Stop | [main.cpp:516](El Trabajante/src/main.cpp#L516) |

### 2.2 Commands (ActuatorCommand Struct)

**Datei:** [actuator_types.h:63-69](El Trabajante/src/models/actuator_types.h#L63-L69)

```cpp
struct ActuatorCommand {
  uint8_t gpio = 255;
  String command = "";        // "ON", "OFF", "PWM", "TOGGLE", "STOP"
  float value = 0.0f;         // 0.0 - 1.0 (PWM) oder binary (>=0.5)
  uint32_t duration_s = 0;    // Optional hold duration
  unsigned long timestamp = 0;
};
```

| Command | Value | Beschreibung | Code-Location |
|---------|-------|--------------|---------------|
| `ON` | - | Einschalten (digital HIGH) | [actuator_manager.cpp:552](El Trabajante/src/services/actuator/actuator_manager.cpp#L552) |
| `OFF` | - | Ausschalten (digital LOW) | [actuator_manager.cpp:554](El Trabajante/src/services/actuator/actuator_manager.cpp#L554) |
| `PWM` | 0.0-1.0 | PWM-Wert setzen | [actuator_manager.cpp:556](El Trabajante/src/services/actuator/actuator_manager.cpp#L556) |
| `TOGGLE` | - | State umkehren | [actuator_manager.cpp:558](El Trabajante/src/services/actuator/actuator_manager.cpp#L558) |
| `STOP` | - | Sofortiger Stopp (= OFF) | Zeile 65 in actuator_types.h |

### 2.3 Actuator Types (ActuatorTypeTokens)

**Datei:** [actuator_types.h:17-23](El Trabajante/src/models/actuator_types.h#L17-L23)

| Type | Token | PWM | Binary | Safety Features |
|------|-------|-----|--------|-----------------|
| Pumpe | `"pump"` | Nein | Ja | maxRuntime=3600s, cooldown=30s, max_activations/h=60 |
| Ventil | `"valve"` | Nein | Ja | supportsAuxGpio |
| Relais | `"relay"` | Nein | Ja | invertedLogic möglich |
| PWM | `"pwm"` | Ja | Nein | 0-255 (intern), 0.0-1.0 (API) |

**Helper-Funktionen:** [actuator_types.h:113-129](El Trabajante/src/models/actuator_types.h#L113-L129)
- `isBinaryActuatorType()` - prüft pump/valve/relay
- `isPwmActuatorType()` - prüft pwm
- `validateActuatorValue()` - validiert Wertbereich

### 2.4 EmergencyState Enum

**Datei:** [actuator_types.h:10-15](El Trabajante/src/models/actuator_types.h#L10-L15)

| State | Wert | String | Beschreibung |
|-------|------|--------|--------------|
| `EMERGENCY_NORMAL` | 0 | `"normal"` | Normalbetrieb |
| `EMERGENCY_ACTIVE` | 1 | `"active"` | Emergency aktiv |
| `EMERGENCY_CLEARING` | 2 | `"clearing"` | Wird aufgehoben |
| `EMERGENCY_RESUMING` | 3 | `"resuming"` | Wiederherstellung läuft |

### 2.5 Error Codes

**Datei:** [error_codes.h:43-46](El Trabajante/src/models/error_codes.h#L43-L46)

| Code | Name | Beschreibung | Recovery |
|------|------|--------------|----------|
| 1050 | `ERROR_ACTUATOR_SET_FAILED` | Failed to set actuator state | Retry command |
| 1051 | `ERROR_ACTUATOR_INIT_FAILED` | Failed to initialize actuator | Check hardware |
| 1052 | `ERROR_ACTUATOR_NOT_FOUND` | Actuator not configured or not found | Configure actuator |
| 1053 | `ERROR_ACTUATOR_CONFLICT` | Actuator GPIO conflict with sensor | Use different GPIO |

### 2.6 Alert Types

**Datei:** [actuator_types.h:94-100](El Trabajante/src/models/actuator_types.h#L94-L100)

```cpp
struct ActuatorAlert {
  unsigned long timestamp = 0;
  uint8_t gpio = 255;
  String alert_type = "";   // "runtime_protection", "emergency_stop", "overcurrent"
  String message = "";
  String actuator_type = "";
};
```

| Alert Type | Trigger | Beschreibung | Code-Location |
|------------|---------|--------------|---------------|
| `"emergency_stop"` | `emergencyStopActuator()` | Manueller Emergency-Stop | [actuator_manager.cpp:431](El Trabajante/src/services/actuator/actuator_manager.cpp#L431) |
| `"runtime_protection"` | `processActuatorLoops()` | Timeout überschritten (1h) | [actuator_manager.cpp:504-505](El Trabajante/src/services/actuator/actuator_manager.cpp#L504-L505) |
| `"overcurrent"` | Driver Detection | Strombegrenzung ausgelöst | Driver-spezifisch |

### 2.7 Safety Features

#### 2.7.1 Basis RuntimeProtection (alle Aktoren)

**Datei:** [actuator_types.h:32-36](El Trabajante/src/models/actuator_types.h#L32-L36)

```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;  // 1h default
  bool timeout_enabled = true;               // Enable/disable timeout protection
  unsigned long activation_start_ms = 0;     // Timestamp when actuator was activated
};
```

#### 2.7.2 Erweiterte RuntimeProtection (PumpActuator)

**Datei:** [pump_actuator.h:10-15](El Trabajante/src/services/actuator/actuator_drivers/pump_actuator.h#L10-L15)

```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;      // 1h continuous runtime cap
  uint16_t max_activations_per_hour = 60;        // Duty-cycle protection
  unsigned long cooldown_ms = 30000UL;           // 30s cooldown after cutoff
  unsigned long activation_window_ms = 3600000UL;
};
```

| Feature | Parameter | Default | Verhalten bei Trigger |
|---------|-----------|---------|----------------------|
| Max Runtime | `max_runtime_ms` | 3600000 (1h) | Auto-OFF, Alert `"runtime_protection"` |
| Cooldown | `cooldown_ms` | 30000 (30s) | Commands blockiert bis Cooldown abgelaufen |
| Max Activations | `max_activations_per_hour` | 60 | `canActivate()` gibt false zurück |
| Timeout Protection | `timeout_enabled` | true | Timeout-Tracking aktiv/inaktiv |

#### 2.7.3 Safety-Checks in `controlActuator()`

**Datei:** [actuator_manager.cpp:338-380](El Trabajante/src/services/actuator/actuator_manager.cpp#L338-L380)

```cpp
bool controlActuator(uint8_t gpio, float value) {
  // Check 1: Actuator existiert
  if (!actuator || !actuator->driver) → return ERROR_ACTUATOR_NOT_FOUND

  // Check 2: Emergency-Stop aktiv? (Zeilen 348-351)
  if (actuator->emergency_stopped) → return false  // BLOCKED

  // Check 3: Value im erlaubten Bereich? (Zeilen 354-362)
  if (isPwmActuatorType) {
    normalized_value = constrain(value, 0.0f, 1.0f);
  } else if (!validateActuatorValue(...)) {
    return ERROR_COMMAND_INVALID
  }

  // Check 4: Driver-Operation (Zeile 364)
  bool success = actuator->driver->setValue(normalized_value);

  // Check 5: Runtime-Protection Tracking (Zeilen 368-375)
  if (success && state_changed_to_on) {
    config.runtime_protection.activation_start_ms = millis();
  }
}
```

#### 2.7.4 Timeout-Protection Loop

**Datei:** [actuator_manager.cpp:478-517](El Trabajante/src/services/actuator/actuator_manager.cpp#L478-L517)

```cpp
void processActuatorLoops() {
  // Muss periodisch aufgerufen werden (alle 100-500ms)
  for (each actuator) {
    if (timeout_enabled && current_state) {
      unsigned long runtime = millis() - activation_start_ms;

      if (runtime > max_runtime_ms) {
        emergencyStopActuator(gpio);
        publishActuatorAlert(gpio, "runtime_protection",
                            "Actuator exceeded max runtime");
        activation_start_ms = 0;  // Reset
      }
    }

    // Driver Loop Processing
    driver->loop();
  }
}
```

---

## 3. Server Layer (El Servador)

### 3.1 MQTT Handler Chain

```
MQTT Message → Subscriber → Handler → Service → DB → WebSocket
```

| Handler | Topic Pattern | WebSocket Event | Code-Location |
|---------|---------------|-----------------|---------------|
| `ActuatorStatusHandler` | `.../actuator/{gpio}/status` | `actuator_status` | [actuator_handler.py:44-217](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py#L44-L217) |
| `ActuatorResponseHandler` | `.../actuator/{gpio}/response` | `actuator_response` | [actuator_response_handler.py:54-160](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L54-L160) |
| `ActuatorAlertHandler` | `.../actuator/{gpio}/alert` | `actuator_alert` | [actuator_alert_handler.py:66-197](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L66-L197) |

### 3.2 WebSocket Events

| Event Type | Payload | Code-Location |
|------------|---------|---------------|
| `actuator_status` | `{esp_id, gpio, actuator_type, state, value, emergency, timestamp}` | [actuator_handler.py:194-208](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py#L194-L208) |
| `actuator_response` | `{esp_id, gpio, command, value, success, message, timestamp}` | [actuator_response_handler.py:137-151](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L137-L151) |
| `actuator_alert` | `{esp_id, gpio, alert_type, severity, message, zone_id, timestamp}` | [actuator_alert_handler.py:173-189](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L173-L189) |

**Alert Severity Mapping:** [actuator_alert_handler.py:44-49](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L44-L49)
```python
ALERT_SEVERITY = {
    "emergency_stop": "critical",
    "runtime_protection": "warning",
    "safety_violation": "critical",
    "hardware_error": "error",
}
```

### 3.3 REST API Endpoints

**Router-Prefix:** `/v1/actuators`

| Method | Endpoint | Beschreibung | Code-Location |
|--------|----------|--------------|---------------|
| GET | `/` | Liste aller Aktoren (mit Pagination + Filter) | [actuators.py:158-208](El Servador/god_kaiser_server/src/api/v1/actuators.py#L158-L208) |
| GET | `/{esp_id}/{gpio}` | Einzelnen Aktor abrufen | [actuators.py:216-263](El Servador/god_kaiser_server/src/api/v1/actuators.py#L216-L263) |
| POST | `/{esp_id}/{gpio}` | Aktor erstellen/aktualisieren | [actuators.py:271-386](El Servador/god_kaiser_server/src/api/v1/actuators.py#L271-L386) |
| **POST** | **`/{esp_id}/{gpio}/command`** | **Command senden** | [actuators.py:394-483](El Servador/god_kaiser_server/src/api/v1/actuators.py#L394-L483) |
| GET | `/{esp_id}/{gpio}/status` | Aktor-Status abrufen | [actuators.py:491-562](El Servador/god_kaiser_server/src/api/v1/actuators.py#L491-L562) |
| POST | `/emergency_stop` | Globaler Emergency-Stop | [actuators.py:570-703](El Servador/god_kaiser_server/src/api/v1/actuators.py#L570-L703) |
| DELETE | `/{esp_id}/{gpio}` | Aktor löschen | [actuators.py:711-790](El Servador/god_kaiser_server/src/api/v1/actuators.py#L711-L790) |
| GET | `/{esp_id}/{gpio}/history` | Command-Historie abrufen | [actuators.py:798-861](El Servador/god_kaiser_server/src/api/v1/actuators.py#L798-L861) |

### 3.4 Command Endpoint Detail

**Datei:** [actuators.py:394-483](El Servador/god_kaiser_server/src/api/v1/actuators.py#L394-L483)

```python
@router.post("/{esp_id}/{gpio}/command")
async def send_command(
    esp_id: str,
    gpio: int,
    command: ActuatorCommand,  # {command: ON/OFF/PWM/TOGGLE, value: 0.0-1.0, duration: 0-86400}
    ...
):
    # 1. Lookup ESP + Actuator
    # 2. Check enabled status
    # 3. Call ActuatorService.send_command() - INCLUDES SAFETY VALIDATION
    # 4. Return ActuatorCommandResponse
```

**KRITISCH:** `SafetyService.validate_actuator_command()` wird automatisch aufgerufen!

### 3.5 Database Schema

#### ActuatorConfig

**Datei:** [actuator.py:17-169](El Servador/god_kaiser_server/src/db/models/actuator.py#L17-L169)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | UUID | Primary key |
| esp_id | UUID | FK → ESPDevice (CASCADE) |
| gpio | Integer | GPIO pin (0-39) |
| actuator_type | String(50) | digital/pwm/servo |
| actuator_name | String(100) | Human-readable name |
| enabled | Boolean | Activation status |
| min_value | Float | Minimum value (0.0) |
| max_value | Float | Maximum value (1.0) |
| timeout_seconds | Integer | Auto-shutoff timeout |
| **safety_constraints** | JSON | `{max_runtime, cooldown_period}` |
| **config_status** | String(20) | pending/applied/failed |
| **config_error** | String(50) | Error code if failed |

#### ActuatorState

**Datei:** [actuator.py:172-299](El Servador/god_kaiser_server/src/db/models/actuator.py#L172-L299)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | UUID | Primary key |
| esp_id | UUID | FK → ESPDevice |
| gpio | Integer | GPIO pin |
| current_value | Float | Current value (0.0-1.0) |
| **state** | String(20) | **idle/active/error/emergency_stop** |
| last_command | String(50) | Last command type |
| runtime_seconds | Integer | Total runtime |
| data_source | String(20) | production/mock/test/simulation |

#### ActuatorHistory

**Datei:** [actuator.py:301-426](El Servador/god_kaiser_server/src/db/models/actuator.py#L301-L426)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | UUID | Primary key |
| esp_id | UUID | FK → ESPDevice |
| gpio | Integer | GPIO pin |
| command_type | String(50) | set/stop/EMERGENCY_STOP/ALERT_* |
| value | Float | Command value |
| issued_by | String(100) | user:123, logic:456, esp32, system |
| success | Boolean | Command success |
| timestamp | DateTime | Command time |

### 3.6 Type Mapping (ESP32 → Server)

**Datei:** [actuator.py (Schemas):72-82](El Servador/god_kaiser_server/src/schemas/actuator.py#L72-L82)

```python
ACTUATOR_TYPE_MAPPING = {
    "pump": "digital",
    "valve": "digital",
    "relay": "digital",
    "pwm": "pwm",
    "digital": "digital",
    "servo": "servo",
}
```

---

## 4. Frontend Layer (El Frontend)

### 4.1 API Client

**Datei:** [actuators.ts](El Frontend/src/api/actuators.ts)

```typescript
// EXISTIERENDE Funktionen (Config-Management):
createOrUpdate(espId, gpio, config)  // POST /v1/actuators/{esp_id}/{gpio}
delete(espId, gpio)                  // DELETE /v1/actuators/{esp_id}/{gpio}
get(espId, gpio)                     // GET /v1/actuators/{esp_id}/{gpio}
list(params?)                        // GET /v1/actuators/

// ❌ FEHLT KOMPLETT:
// sendCommand(espId, gpio, command, value?)
// emergencyStop(espId?, gpio?, reason)
```

### 4.2 Debug API (Mock ESPs only)

**Datei:** [debug.ts:176-232](El Frontend/src/api/debug.ts#L176-L232)

```typescript
// NUR für Mock ESPs:
addActuator(espId, config)                      // POST /debug/mock-esp/{espId}/actuators
setActuatorState(espId, gpio, state, pwmValue)  // POST /debug/mock-esp/{espId}/actuators/{gpio}
emergencyStop(espId, reason)                    // POST /debug/mock-esp/{espId}/emergency-stop
clearEmergency(espId)                           // POST /debug/mock-esp/{espId}/clear-emergency
```

### 4.3 Store (esp.ts)

**Datei:** [esp.ts:856-927](El Frontend/src/stores/esp.ts#L856-L927)

**Actions:**
| Action | Mock ESP | Real ESP | Beschreibung |
|--------|----------|----------|--------------|
| `addActuator()` | ✅ | ❌ Error | Aktor hinzufügen |
| `setActuatorState()` | ✅ | ❌ Error | State setzen |
| `emergencyStop()` | ✅ | ❌ Error | Emergency-Stop |
| `clearEmergency()` | ✅ | ❌ Error | Emergency aufheben |
| `sendActuatorCommand()` | ❌ | ❌ | **FEHLT KOMPLETT** |

**WebSocket Filter:** [esp.ts:94-99](El Frontend/src/stores/esp.ts#L94-L99)
```typescript
// VERIFIZIERT: Diese Events sind im Filter (Zeile 98):
types: ['esp_health', 'sensor_data', 'actuator_status', 'actuator_alert',
        'config_response', 'zone_assignment', 'sensor_health']
// ❌ FEHLT: 'actuator_response' ist NICHT im Filter!
```

**WebSocket Handler:** [esp.ts:1552-1559](El Frontend/src/stores/esp.ts#L1552-L1559)
```typescript
// VERIFIZIERT: Diese Handler sind registriert:
ws.on('esp_health', handleEspHealth),           // ✅ Zeile 1553
ws.on('sensor_data', handleSensorData),         // ✅ Zeile 1554
ws.on('actuator_status', handleActuatorStatus), // ✅ Zeile 1555
ws.on('actuator_alert', handleActuatorAlert),   // ✅ Zeile 1556
ws.on('config_response', handleConfigResponse), // ✅ Zeile 1557
ws.on('zone_assignment', handleZoneAssignment), // ✅ Zeile 1558
ws.on('sensor_health', handleSensorHealth),     // ✅ Zeile 1559
// ❌ FEHLT: handleActuatorResponse ist NICHT registriert!
```

**Handler-Implementierungen:**
| Handler | Existiert? | Zeile | Beschreibung |
|---------|------------|-------|--------------|
| `handleActuatorStatus` | ✅ | 1288-1313 | Verarbeitet state-Updates |
| `handleActuatorAlert` | ✅ | 1064-1095 | Verarbeitet Emergency/Timeout-Alerts |
| `handleActuatorResponse` | ❌ **FEHLT** | - | Verarbeitet Command-Bestätigungen |

### 4.4 Types

**Datei:** [index.ts](El Frontend/src/types/index.ts)

**Existierende Types (verifiziert):**
| Type | Zeile | Status |
|------|-------|--------|
| `MockActuator` | 144-152 | ✅ OK |
| `MockActuatorConfig` | 198-211 | ✅ OK |
| `ActuatorConfigCreate` | 590-605 | ✅ OK |
| `ActuatorConfigResponse` | 607-626 | ✅ OK |
| `ActuatorDragData` | 564-571 | ✅ OK |
| `MessageType` (hat `actuator_response`) | 228-242 | ✅ Deklariert |

**Fehlende Types:**
| Type | Beschreibung | Priorität |
|------|--------------|-----------|
| `ActuatorCommandType` | `'ON' \| 'OFF' \| 'PWM' \| 'TOGGLE'` | 🔴 KRITISCH |
| `ActuatorCommandRequest` | Request-Body für sendCommand | 🔴 KRITISCH |
| `ActuatorCommandResponse` | REST Response vom Server | 🔴 KRITISCH |
| `ActuatorResponseEvent` | WebSocket Event Payload | 🟡 WICHTIG |
| `ActuatorAlertEvent` | WebSocket Event Payload | 🟡 WICHTIG |

```typescript
// Vorhandene MockActuator Definition (Zeile 144-152):
interface MockActuator {
  gpio: number
  actuator_type: string       // 'pump', 'valve', 'relay', 'pwm'
  name: string | null
  state: boolean              // ON/OFF
  pwm_value: number           // 0-255 für PWM
  emergency_stopped: boolean  // Emergency-Stop aktiv?
  last_command: string | null // ISO Timestamp
}
```

### 4.5 UI Components

| Component | Existiert | Zeigt an | Controls | Code-Location |
|-----------|-----------|----------|----------|---------------|
| `ActuatorSatellite.vue` | ✅ | Status, E-STOP, PWM% | ❌ Keine | [ActuatorSatellite.vue](El Frontend/src/components/esp/ActuatorSatellite.vue) |
| `ActuatorSidebar.vue` | ✅ | Drag & Drop für neue Aktoren | ❌ Keine | [ActuatorSidebar.vue](El Frontend/src/components/dashboard/ActuatorSidebar.vue) |
| `ActuatorControl.vue` | ❌ | - | - | **FEHLT** |

**ActuatorSatellite zeigt:**
- Emergency-Stop: "E-STOP" Badge (danger)
- PWM-Wert: "0%-100%"
- Binary: "AN" oder "AUS"
- **KEINE Toggle-Buttons, KEINE PWM-Slider**

---

## 5. Lücken-Matrix (Verifiziert 2026-01-09)

### 5.0 ESP32 → Server (MQTT) - VOLLSTÄNDIG

| Topic | Handler | WebSocket Event | Status |
|-------|---------|-----------------|--------|
| `.../actuator/{gpio}/status` | ✅ [actuator_handler.py:44](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py#L44) | ✅ `actuator_status` (Zeile 196-206) | ✅ OK |
| `.../actuator/{gpio}/response` | ✅ [actuator_response_handler.py:66](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L66) | ✅ `actuator_response` (Zeile 141-149) | ✅ OK |
| `.../actuator/{gpio}/alert` | ✅ [actuator_alert_handler.py:66](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L66) | ✅ `actuator_alert` (Zeile 177-185) | ✅ OK |

### 5.1 Server → Frontend (WebSocket)

| Event | Server sendet? | Frontend Filter? | Frontend Handler? | Status |
|-------|---------------|------------------|------------------|--------|
| `actuator_status` | ✅ [Zeile 196-206](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py#L196-L206) | ✅ [esp.ts:98](El%20Frontend/src/stores/esp.ts#L98) | ✅ [Zeile 1288-1313](El%20Frontend/src/stores/esp.ts#L1288-L1313) | ✅ OK |
| `actuator_response` | ✅ [Zeile 141-149](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L141-L149) | ❌ **FEHLT in Zeile 98** | ❌ **FEHLT** | ❌ **LÜCKE** |
| `actuator_alert` | ✅ [Zeile 177-185](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L177-L185) | ✅ [esp.ts:98](El%20Frontend/src/stores/esp.ts#L98) | ✅ [Zeile 1064-1095](El%20Frontend/src/stores/esp.ts#L1064-L1095) | ✅ OK |

### 5.2 Frontend → Server (REST API)

| Endpoint | Server | Frontend API | Status |
|----------|--------|--------------|--------|
| `POST /v1/actuators/{esp}/{gpio}/command` | ✅ [actuators.py:394-483](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L394-L483) | ❌ **FEHLT** | ❌ **LÜCKE** |
| `POST /v1/actuators/emergency_stop` | ✅ [actuators.py:570-703](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L570-L703) | ❌ **FEHLT** | ❌ **LÜCKE** |
| `GET /v1/actuators/{esp}/{gpio}/status` | ✅ [actuators.py:486-536](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L486-L536) | ❌ **FEHLT** | ⚠️ Optional |
| `GET /v1/actuators/{esp}/{gpio}/history` | ✅ [actuators.py:706-788](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L706-L788) | ❌ **FEHLT** | ⚠️ Optional |

### 5.3 Priorisierte Lücken-Liste

| # | Lücke | Layer | Datei:Zeile | Priorität | Aufwand |
|---|-------|-------|-------------|-----------|---------|
| 1 | `sendCommand()` fehlt | Frontend API | `actuators.ts` | 🔴 P0 | 30min |
| 2 | `actuator_response` fehlt im Filter | Frontend Store | `esp.ts:98` | 🔴 P0 | 5min |
| 3 | `handleActuatorResponse()` fehlt | Frontend Store | `esp.ts` | 🔴 P0 | 1h |
| 4 | Command-Types fehlen | Frontend Types | `types/index.ts` | 🟡 P1 | 30min |
| 5 | `emergencyStop()` fehlt | Frontend API | `actuators.ts` | 🟡 P1 | 15min |
| 6 | `ActuatorControl.vue` fehlt | Frontend UI | `components/esp/` | 🟡 P1 | 3h |
| 7 | `getStatus()` fehlt | Frontend API | `actuators.ts` | 🟢 P2 | 15min |
| 8 | `getHistory()` fehlt | Frontend API | `actuators.ts` | 🟢 P2 | 15min |

### 5.4 Feature-Matrix (Zusammenfassung)

| Feature | ESP32 | Server | Frontend | Status | Priorität |
|---------|-------|--------|----------|--------|-----------|
| **Status Publishing** | ✅ MQTT | ✅ WS Event | ✅ Handler | COMPLETE | - |
| **Response Publishing** | ✅ MQTT | ✅ WS Event | ❌ Filter+Handler | **KRITISCH** | **P0** |
| **Alert Publishing** | ✅ MQTT | ✅ WS Event | ✅ Handler | COMPLETE | - |
| **Command API** | ✅ Subscribe | ✅ Endpoint | ❌ FEHLT | **KRITISCH** | **P0** |
| **Command UI** | - | - | ❌ FEHLT | **KRITISCH** | **P0** |
| **Emergency Stop API** | ✅ | ✅ Endpoint | ⚠️ Mock only | PARTIAL | P1 |
| **Emergency Stop UI** | - | - | ⚠️ Mock only | PARTIAL | P1 |
| **Config Sync** | ✅ | ✅ Phase 4 | ✅ Phase 4 | COMPLETE | - |
| **Runtime Display** | ✅ | ✅ DB | ❌ Nicht angezeigt | PARTIAL | P2 |
| **Cooldown Display** | ✅ | ✅ DB | ❌ Nicht angezeigt | PARTIAL | P2 |
| **PWM Slider** | ✅ | ✅ | ❌ FEHLT | **KRITISCH** | **P0** |

### 5.1 Kritische Lücken (P0)

1. **Keine `sendCommand()` API-Funktion im Frontend**
   - Server-Endpoint existiert: `POST /v1/actuators/{esp_id}/{gpio}/command`
   - Frontend-API-Client hat KEINE entsprechende Funktion
   - **Lösung:** API-Funktion in `actuators.ts` hinzufügen

2. **Keine Control-Buttons in ActuatorSatellite**
   - Nur Status-Anzeige implementiert
   - Keine ON/OFF Toggle-Buttons
   - Kein PWM-Slider
   - **Lösung:** Control-UI in `ActuatorSatellite.vue` oder separate `ActuatorControl.vue`

3. **Store-Actions nur für Mock ESPs**
   - `setActuatorState()` sendet an Mock-API, nicht an Command-Endpoint
   - Echte ESPs können nicht gesteuert werden
   - **Lösung:** `sendActuatorCommand()` Action hinzufügen

### 5.2 Partielle Lücken (P1-P2)

4. **Emergency-Stop nur für Mock ESPs**
   - Server-Endpoint existiert: `POST /v1/actuators/emergency_stop`
   - Frontend ruft falschen Endpoint auf (Debug-API)
   - **Lösung:** Echte API verwenden

5. **Runtime/Cooldown nicht im UI angezeigt**
   - Daten existieren in DB und WebSocket
   - UI zeigt diese Information nicht an
   - **Lösung:** UI-Erweiterung

---

## 6. Implementierungsplan

### Phase 1: API-Layer (Geschätzt: 30min)

**Datei:** `El Frontend/src/api/actuators.ts`

```typescript
// Hinzuzufügen:
async sendCommand(
  espId: string,
  gpio: number,
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE',
  value?: number,
  duration?: number
): Promise<ActuatorCommandResponse> {
  return api.post(`/v1/actuators/${espId}/${gpio}/command`, {
    command,
    value: value ?? (command === 'ON' ? 1.0 : 0.0),
    duration: duration ?? 0
  })
}

async emergencyStop(
  espId?: string,
  gpio?: number,
  reason: string = 'User initiated'
): Promise<EmergencyStopResponse> {
  return api.post('/v1/actuators/emergency_stop', {
    esp_id: espId,
    gpio,
    reason
  })
}
```

### Phase 2: Store-Layer (Geschätzt: 1h)

**Datei:** `El Frontend/src/stores/esp.ts`

```typescript
// Hinzuzufügen in actions:
async function sendActuatorCommand(
  espId: string,
  gpio: number,
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE',
  value?: number
): Promise<boolean> {
  try {
    const response = await actuatorsApi.sendCommand(espId, gpio, command, value)
    return response.command_sent
  } catch (error) {
    console.error('Failed to send actuator command:', error)
    return false
  }
  // Response kommt via WebSocket 'actuator_response'
}

async function emergencyStopDevice(
  espId?: string,
  gpio?: number,
  reason: string = 'User initiated'
): Promise<boolean> {
  try {
    await actuatorsApi.emergencyStop(espId, gpio, reason)
    return true
  } catch (error) {
    console.error('Failed to send emergency stop:', error)
    return false
  }
}
```

### Phase 3: UI-Layer (Geschätzt: 2-3h)

**Datei:** `El Frontend/src/components/esp/ActuatorSatellite.vue`

Erweiterungen:
1. **Toggle-Button** für ON/OFF (digital actuators)
2. **PWM-Slider** für PWM-Aktoren (0-100%)
3. **Emergency-Stop-Button** (mit Bestätigungsdialog)
4. **Runtime-Anzeige** (verbleibende Zeit)
5. **Cooldown-Indikator** (wenn aktiv)

### Phase 4: Response-Handling (Geschätzt: 30min)

**Datei:** `El Frontend/src/stores/esp.ts`

Erweitern des `actuator_response` Handlers:
- Toast-Notification bei Erfolg/Fehler
- Error-Code-Mapping zu benutzerfreundlichen Meldungen

---

## 7. Code-Referenzen

### ESP32

| Datei | Zeilen | Relevante Funktionen |
|-------|--------|---------------------|
| [actuator_types.h](El Trabajante/src/models/actuator_types.h) | 1-149 | Enums, Structs, Helpers |
| [actuator_manager.cpp](El Trabajante/src/services/actuator/actuator_manager.cpp) | 338-575 | Control, Commands, Safety |
| [pump_actuator.h](El Trabajante/src/services/actuator/actuator_drivers/pump_actuator.h) | 10-15 | Extended RuntimeProtection |
| [error_codes.h](El Trabajante/src/models/error_codes.h) | 43-46 | Error Codes |
| [topic_builder.cpp](El Trabajante/src/utils/topic_builder.cpp) | 86-124 | MQTT Topics |

### Server

| Datei | Zeilen | Relevante Funktionen |
|-------|--------|---------------------|
| [actuators.py (API)](El Servador/god_kaiser_server/src/api/v1/actuators.py) | 394-483 | send_command endpoint |
| [actuator_handler.py](El Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py) | 44-217 | Status Handler |
| [actuator.py (Models)](El Servador/god_kaiser_server/src/db/models/actuator.py) | 17-426 | DB Models |
| [actuator.py (Schemas)](El Servador/god_kaiser_server/src/schemas/actuator.py) | 280-332 | ActuatorCommand |

### Frontend

| Datei | Zeilen | Relevante Funktionen |
|-------|--------|---------------------|
| [actuators.ts](El Frontend/src/api/actuators.ts) | 4-63 | API Client (INCOMPLETE) |
| [esp.ts](El Frontend/src/stores/esp.ts) | 856-927, 1288-1313 | Store Actions, WS Handlers |
| [ActuatorSatellite.vue](El Frontend/src/components/esp/ActuatorSatellite.vue) | 1-343 | Display Component |
| [debug.ts](El Frontend/src/api/debug.ts) | 176-232 | Mock ESP Control |

---

## 8. Risiken & Mitigationen

| Risiko | Impact | Mitigation |
|--------|--------|------------|
| Command-Latenz | Mittel | Optimistic UI Updates |
| Emergency-Stop-Race | Hoch | Server-seitige Validierung priorisieren |
| PWM-Slider-Flooding | Mittel | Debounce/Throttle (100ms) |
| WebSocket-Disconnect | Hoch | Reconnect + State-Sync |

---

## 9. Fazit

Das Actuator-System ist in ESP32 und Server **vollständig implementiert**. Die **kritische Lücke** liegt im Frontend:

1. ❌ **API-Funktion `sendCommand()` fehlt** (Server-Endpoint existiert)
2. ❌ **Store-Action `sendActuatorCommand()` fehlt**
3. ❌ **UI-Controls (Buttons, Slider) fehlen**

**Geschätzter Gesamtaufwand:** 4-5 Stunden

---

*Dokumentation erstellt durch KI-Agent basierend auf Code-Analyse.*
*Verifiziert gegen tatsächlichen Code am 2026-01-09.*
