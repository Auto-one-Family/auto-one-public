# Actuator Control System - Verifizierter Implementierungsplan (V4)

**Erstellt:** 2026-01-09
**Verifiziert:** 2026-01-09 (Codebase-Analyse Claude Opus 4.5)
**Status:** ✅ Analyse abgeschlossen, Plan verifiziert und korrigiert

---

## 0. Executive Summary

### Problem
Frontend kann nur Mock-ESPs steuern. Echte ESPs erhalten keine Befehle, weil:
1. `sendCommand()` API-Funktion fehlt im Frontend
2. `handleActuatorResponse()` WebSocket-Handler fehlt (subscribed aber nicht implementiert!)
3. Keine Toast-Benachrichtigungen für Command-Feedback

### Lösung (V1)
```
Frontend → REST API → Server (SafetyService) → MQTT → ESP32
                                                    ↓
Frontend ← WebSocket ← Server ← MQTT Response ← ESP32
```

### Aufwand
- **Types:** ~50 Zeilen in `types/index.ts` (NICHT neue Datei!)
- **API:** ~40 Zeilen in `api/actuators.ts`
- **Store:** ~30 Zeilen in `stores/esp.ts`
- **Component:** ~150 Zeilen `ActuatorControl.vue`
- **Gesamt:** ~270 Zeilen, ~2-3 Stunden

---

## 1. Verifizierte Codebase-Analyse

### 1.1 Actuator Types - KORRIGIERT

**WICHTIG:** `led`, `fan`, `motor`, `rgb_led`, `servo` existieren NICHT als separate Typen!

| Type | ESP32 | Server | Frontend | Status |
|------|-------|--------|----------|--------|
| `pump` | ✅ `ActuatorTypeTokens::PUMP` | ✅ → `digital` | ✅ | V1 Ready |
| `valve` | ✅ `ActuatorTypeTokens::VALVE` | ✅ → `digital` | ✅ | V1 Ready |
| `relay` | ✅ `ActuatorTypeTokens::RELAY` | ✅ → `digital` | ✅ | V1 Ready |
| `pwm` | ✅ `ActuatorTypeTokens::PWM` | ✅ → `pwm` | ✅ | V1 Ready |
| `servo` | ❌ Nicht in ESP32 | ✅ Definiert | ❌ | V2 (wenn ESP32 unterstützt) |
| `led` | ❌ | ❌ | ❌ | Nutzt `pwm` Typ |
| `fan` | ❌ | ❌ | ❌ | Nutzt `pwm` Typ |

**Server Type-Mapping** ([actuator.py:57-64](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L57-L64)):
```python
ACTUATOR_TYPE_MAPPING = {
    "pump": "digital",
    "valve": "digital",
    "relay": "digital",
    "pwm": "pwm",
    "servo": "servo",
}
```

**Quellen:**
- ESP32: [actuator_types.h:17-22](El%20Trabajante/src/models/actuator_types.h#L17-L22)
- Server: [actuator.py:52-67](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L52-L67)
- Frontend: [actuatorDefaults.ts:89-145](El%20Frontend/src/utils/actuatorDefaults.ts#L89-L145)

---

### 1.2 Commands - UPPERCASE!

**KRITISCH:** Server erwartet und normalisiert zu UPPERCASE!

| Command | Server-Validierung | ESP32 Handler |
|---------|-------------------|---------------|
| `ON` | ✅ `ACTUATOR_COMMANDS = ["ON", "OFF", "PWM", "TOGGLE"]` | ✅ |
| `OFF` | ✅ | ✅ |
| `PWM` | ✅ (value 0.0-1.0) | ✅ |
| `TOGGLE` | ✅ | ✅ |

**Server auto-normalisiert** ([actuator.py:304-311](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L304-L311)):
```python
@field_validator("command")
def validate_command(cls, v: str) -> str:
    v = v.upper()  # Auto-uppercase!
    if v not in ACTUATOR_COMMANDS:
        raise ValueError(...)
    return v
```

---

### 1.3 Server-Endpoints (vollständig verifiziert)

| Method | Endpoint | Frontend API | Status |
|--------|----------|--------------|--------|
| GET | `/v1/actuators` | ✅ `list()` | Existiert |
| GET | `/v1/actuators/{esp_id}/{gpio}` | ✅ `get()` | Existiert |
| POST | `/v1/actuators/{esp_id}/{gpio}` | ✅ `createOrUpdate()` | Existiert |
| DELETE | `/v1/actuators/{esp_id}/{gpio}` | ✅ `delete()` | Existiert |
| **POST** | **`/v1/actuators/{esp_id}/{gpio}/command`** | ❌ **FEHLT** | **V1 KRITISCH** |
| GET | `/v1/actuators/{esp_id}/{gpio}/status` | ❌ Fehlt | Optional V1 |
| GET | `/v1/actuators/{esp_id}/{gpio}/history` | ❌ Fehlt | V2 |
| **POST** | **`/v1/actuators/emergency_stop`** | ❌ **FEHLT** | **V1 KRITISCH** |

**Quelle:** [actuators.py](El%20Servador/god_kaiser_server/src/api/v1/actuators.py)

---

### 1.4 WebSocket Events - KRITISCHE LÜCKE

**WICHTIG:** `actuator_response` ist im Filter ABER Handler fehlt!

```typescript
// esp.ts:98 - Filter ist korrekt!
types: ['esp_health', 'sensor_data', 'actuator_status', 'actuator_alert',
        'config_response', 'zone_assignment', 'sensor_health'] as MessageType[]
// ⚠️ 'actuator_response' FEHLT im Filter!
```

```typescript
// esp.ts:1552-1559 - Handler Registration
wsUnsubscribers.push(
  ws.on('esp_health', handleEspHealth),
  ws.on('sensor_data', handleSensorData),
  ws.on('actuator_status', handleActuatorStatus),
  ws.on('actuator_alert', handleActuatorAlert),
  // ❌ FEHLT: ws.on('actuator_response', handleActuatorResponse),
)
```

| Event | Filter | Handler | Server Broadcast |
|-------|--------|---------|------------------|
| `actuator_status` | ✅ | ✅ `handleActuatorStatus()` | ✅ [actuator_handler.py:194-207](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py#L194-L207) |
| `actuator_alert` | ✅ | ✅ `handleActuatorAlert()` | ✅ [actuator_alert_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py) |
| `actuator_response` | ❌ **FEHLT** | ❌ **FEHLT** | ✅ [actuator_response_handler.py:141-149](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L141-L149) |

**Server sendet** (verifiziert):
```python
# actuator_response_handler.py:141-149
await ws_manager.broadcast("actuator_response", {
    "esp_id": esp_id_str,
    "gpio": gpio,
    "command": command,
    "value": value,
    "success": success,
    "message": message,
    "timestamp": payload.get("ts", 0)
})
```

---

### 1.5 Frontend-Status (verifiziert)

#### actuatorDefaults.ts ✅
- 4 Typen konfiguriert: pump, valve, relay, pwm
- Safety-Defaults vorhanden: maxRuntimeSeconds, cooldownSeconds
- Feature-Flags vorhanden: supportsAuxGpio, supportsInvertedLogic

#### api/actuators.ts ⚠️
- ✅ `createOrUpdate()`, `delete()`, `get()`, `list()`
- ❌ `sendCommand()` **FEHLT**
- ❌ `emergencyStop()` **FEHLT**

#### stores/esp.ts ⚠️
- ✅ `handleActuatorStatus()` (Zeile 1288-1313)
- ✅ `handleActuatorAlert()` (Zeile 1064-1095)
- ❌ `handleActuatorResponse()` **FEHLT**
- ❌ Toast-Notifications für Commands **FEHLEN**

#### types/index.ts ⚠️
- ✅ `MockActuator`, `MockActuatorConfig`, `ActuatorConfigCreate`, `ActuatorConfigResponse`
- ❌ `ActuatorCommand`, `ActuatorCommandResponse` **FEHLEN**
- ❌ `ActuatorResponseEvent` **FEHLT**

---

## 2. Betroffene Dateien (KORRIGIERT)

| Datei | Aktion | Zeilen | Priorität |
|-------|--------|--------|-----------|
| [types/index.ts](El%20Frontend/src/types/index.ts) | ERWEITERN | +60 | 🔴 KRITISCH |
| [api/actuators.ts](El%20Frontend/src/api/actuators.ts) | ERWEITERN | +50 | 🔴 KRITISCH |
| [stores/esp.ts](El%20Frontend/src/stores/esp.ts) | ERWEITERN | +40 | 🔴 KRITISCH |
| [utils/actuatorDefaults.ts](El%20Frontend/src/utils/actuatorDefaults.ts) | ERWEITERN | +20 | 🟡 OPTIONAL |
| [components/esp/ActuatorControl.vue](El%20Frontend/src/components/esp/ActuatorControl.vue) | NEU | ~150 | 🟠 HIGH |
| [components/esp/ActuatorSatellite.vue](El%20Frontend/src/components/esp/ActuatorSatellite.vue) | ERWEITERN | +20 | 🟠 HIGH |

**NICHT ERFORDERLICH:**
- ~~`types/actuator.ts`~~ - In `types/index.ts` integrieren (bestehendes Pattern!)
- ~~Komplexes Capability-System~~ - Bestehende `ActuatorTypeConfig` reicht für V1

---

## 3. Implementierung

### Phase 1: Types (`types/index.ts` erweitern)

```typescript
// =============================================================================
// Actuator Command Types (V1)
// =============================================================================

/** Actuator command types - UPPERCASE wie Server! */
export type ActuatorCommandType = 'ON' | 'OFF' | 'PWM' | 'TOGGLE'

/** Command request to server */
export interface ActuatorCommandRequest {
  command: ActuatorCommandType
  value?: number      // 0.0-1.0 für PWM, default 1.0
  duration?: number   // Auto-off nach X Sekunden, default 0 (unlimited)
}

/** Server response nach Command */
export interface ActuatorCommandResponse {
  success: boolean
  esp_id: string
  gpio: number
  command: string
  value: number
  command_sent: boolean
  acknowledged: boolean  // Immer false initial, ACK via WebSocket
  safety_warnings: string[]
}

/** WebSocket actuator_response Event */
export interface ActuatorResponseEvent {
  esp_id: string
  gpio: number
  command: string
  value: number
  success: boolean
  message: string
  timestamp: number  // Unix timestamp
}

/** Emergency Stop Request */
export interface EmergencyStopRequest {
  esp_id?: string   // Optional: nur bestimmtes ESP
  gpio?: number     // Optional: nur bestimmter Aktor
  reason: string    // Pflicht: Grund für Audit-Log
}

/** Emergency Stop Response */
export interface EmergencyStopResponse {
  success: boolean
  message: string
  devices_stopped: number
  actuators_stopped: number
  reason: string
  timestamp: string
  details: Array<{
    esp_id: string
    actuators: Array<{
      esp_id: string
      gpio: number
      success: boolean
      message: string | null
    }>
  }>
}
```

**MessageType erweitern:**
```typescript
export type MessageType =
  | 'sensor_data'
  | 'actuator_status'
  | 'actuator_response'  // ← HINZUFÜGEN!
  | 'actuator_alert'
  | 'esp_health'
  | 'sensor_health'
  | 'config_response'
  | 'zone_assignment'
  | 'logic_execution'
  | 'system_event'
```

---

### Phase 2: API Client (`api/actuators.ts` erweitern)

```typescript
import api from './index'
import type {
  ActuatorConfigCreate,
  ActuatorConfigResponse,
  ActuatorCommandRequest,
  ActuatorCommandResponse,
  EmergencyStopRequest,
  EmergencyStopResponse
} from '@/types'

export const actuatorsApi = {
  // ... bestehende Funktionen ...

  /**
   * Send actuator command via REST API
   *
   * Flow: Frontend → Server (SafetyService) → MQTT → ESP32
   * Response: Via WebSocket 'actuator_response' event
   *
   * @throws 400 - Command rejected by safety validation
   * @throws 404 - Actuator not found
   */
  async sendCommand(
    espId: string,
    gpio: number,
    request: ActuatorCommandRequest
  ): Promise<ActuatorCommandResponse> {
    const response = await api.post<ActuatorCommandResponse>(
      `/v1/actuators/${espId}/${gpio}/command`,
      {
        command: request.command,  // Server auto-uppercases
        value: request.value ?? 1.0,
        duration: request.duration ?? 0
      }
    )
    return response.data
  },

  /**
   * Emergency stop - alle Aktoren sofort aus
   *
   * KRITISCH: Bypasses normale Safety-Checks!
   * Wird in Audit-Log protokolliert.
   */
  async emergencyStop(request: EmergencyStopRequest): Promise<EmergencyStopResponse> {
    const response = await api.post<EmergencyStopResponse>(
      '/v1/actuators/emergency_stop',
      request
    )
    return response.data
  },

  /**
   * Get actuator status (optional für V1)
   */
  async getStatus(
    espId: string,
    gpio: number,
    includeConfig = false
  ): Promise<ActuatorStatusResponse> {
    const response = await api.get<ActuatorStatusResponse>(
      `/v1/actuators/${espId}/${gpio}/status`,
      { params: { include_config: includeConfig } }
    )
    return response.data
  }
}
```

---

### Phase 3: Store Handler (`stores/esp.ts` erweitern)

#### 3.1 WebSocket Filter erweitern

```typescript
// Zeile ~95 - Filter erweitern
const ws = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
  filters: {
    types: [
      'esp_health',
      'sensor_data',
      'actuator_status',
      'actuator_alert',
      'actuator_response',  // ← HINZUFÜGEN!
      'config_response',
      'zone_assignment',
      'sensor_health'
    ] as MessageType[],
  },
})
```

#### 3.2 Handler implementieren

```typescript
/**
 * Handle actuator_response WebSocket event
 *
 * Wird vom Server gesendet wenn ESP32 Command bestätigt/ablehnt.
 * Zeigt Toast mit Erfolg/Fehler-Meldung.
 */
function handleActuatorResponse(message: { data: ActuatorResponseEvent }): void {
  const { esp_id, gpio, command, value, success, message: msg } = message.data
  const toast = useToast()

  if (!esp_id || gpio === undefined) {
    console.warn('[ESP Store] actuator_response missing esp_id or gpio')
    return
  }

  // Device und Actuator finden für bessere Meldung
  const device = devices.value.find(d => getDeviceId(d) === esp_id)
  const actuator = device?.actuators?.find((a: MockActuator) => a.gpio === gpio)
  const name = actuator?.name || `GPIO ${gpio}`
  const deviceName = device?.name || esp_id

  if (success) {
    // State-Update (WebSocket actuator_status macht das auch, aber sicherheitshalber)
    if (actuator) {
      actuator.state = command === 'ON' || (command === 'PWM' && value > 0)
      actuator.pwm_value = value
      actuator.last_command = new Date().toISOString()
    }

    toast.success(`${deviceName} - ${name}: ${command} ausgeführt`, { duration: 3000 })
    console.info(`[ESP Store] ✅ Actuator command confirmed: ${esp_id} GPIO ${gpio} ${command}`)
  } else {
    toast.error(`${deviceName} - ${name}: ${msg || 'Befehl fehlgeschlagen'}`, { duration: 6000 })
    console.error(`[ESP Store] ❌ Actuator command failed: ${esp_id} GPIO ${gpio} ${command}: ${msg}`)

    // Bei Fehler: Korrekten State vom Server holen
    fetchDevice(esp_id)
  }
}
```

#### 3.3 Handler registrieren

```typescript
// Zeile ~1552 - Handler Registration erweitern
wsUnsubscribers.push(
  ws.on('esp_health', handleEspHealth),
  ws.on('sensor_data', handleSensorData),
  ws.on('actuator_status', handleActuatorStatus),
  ws.on('actuator_alert', handleActuatorAlert),
  ws.on('actuator_response', handleActuatorResponse),  // ← HINZUFÜGEN!
  ws.on('config_response', handleConfigResponse),
  ws.on('zone_assignment', handleZoneAssignment),
  ws.on('sensor_health', handleSensorHealth),
)
```

---

### Phase 4: UI Component (`ActuatorControl.vue`)

```vue
<template>
  <div class="actuator-control" :class="{ 'emergency-active': actuator.emergency_stopped }">
    <!-- Emergency Banner -->
    <div v-if="actuator.emergency_stopped" class="emergency-banner">
      <AlertTriangle class="w-4 h-4" />
      <span>EMERGENCY STOP AKTIV</span>
    </div>

    <!-- Control Buttons -->
    <div class="control-buttons">
      <template v-if="isPwm">
        <!-- PWM Slider -->
        <div class="pwm-control">
          <input
            type="range"
            v-model.number="pwmPercent"
            min="0"
            max="100"
            :disabled="isLoading || actuator.emergency_stopped"
            class="pwm-slider"
          />
          <span class="pwm-value">{{ pwmPercent }}%</span>
        </div>
        <button
          @click="sendPwm"
          :disabled="isLoading || actuator.emergency_stopped"
          class="btn btn-primary"
        >
          PWM setzen
        </button>
        <!-- Quick OFF -->
        <button
          @click="sendCommand('OFF')"
          :disabled="isLoading || !actuator.state"
          class="btn btn-secondary"
        >
          AUS
        </button>
      </template>

      <template v-else>
        <!-- Binary Controls -->
        <button
          @click="sendCommand('ON')"
          :disabled="isLoading || actuator.state || actuator.emergency_stopped"
          class="btn btn-success"
        >
          <Play class="w-4 h-4 mr-1" /> EIN
        </button>
        <button
          @click="sendCommand('OFF')"
          :disabled="isLoading || !actuator.state"
          class="btn btn-danger"
        >
          <Square class="w-4 h-4 mr-1" /> AUS
        </button>
        <button
          @click="sendCommand('TOGGLE')"
          :disabled="isLoading || actuator.emergency_stopped"
          class="btn btn-secondary"
        >
          <RefreshCw class="w-4 h-4 mr-1" /> Toggle
        </button>
      </template>
    </div>

    <!-- Loading Indicator -->
    <div v-if="isLoading" class="loading-indicator">
      <Loader2 class="w-4 h-4 animate-spin" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Play, Square, RefreshCw, AlertTriangle, Loader2 } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { useToast } from '@/composables/useToast'
import { isPwmActuator } from '@/utils/actuatorDefaults'
import type { MockActuator, ActuatorCommandType } from '@/types'

const props = defineProps<{
  espId: string
  actuator: MockActuator
}>()

const toast = useToast()
const isLoading = ref(false)
const pwmPercent = ref(Math.round((props.actuator.pwm_value || 0) * 100))

const isPwm = computed(() => isPwmActuator(props.actuator.actuator_type))

async function sendCommand(command: ActuatorCommandType, value?: number) {
  if (props.actuator.emergency_stopped && command !== 'OFF') {
    toast.warning('Emergency Stop ist aktiv - nur AUS möglich')
    return
  }

  isLoading.value = true
  try {
    await actuatorsApi.sendCommand(props.espId, props.actuator.gpio, {
      command,
      value
    })
    // Erfolg wird via WebSocket actuator_response gemeldet
  } catch (error: any) {
    const msg = error.response?.data?.detail || error.message || 'Unbekannter Fehler'
    toast.error(`Befehl fehlgeschlagen: ${msg}`)
  } finally {
    isLoading.value = false
  }
}

async function sendPwm() {
  await sendCommand('PWM', pwmPercent.value / 100)
}
</script>
```

---

### Phase 5: Integration in ActuatorSatellite

```vue
<!-- In ActuatorSatellite.vue -->
<template>
  <div class="actuator-satellite">
    <!-- Bestehender Content... -->

    <!-- NEU: Control Panel -->
    <ActuatorControl
      v-if="!compact"
      :esp-id="espId"
      :actuator="actuator"
    />
  </div>
</template>

<script setup lang="ts">
import ActuatorControl from './ActuatorControl.vue'
// ...
</script>
```

---

## 4. Datenfluss (Server-Centric)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              COMMAND FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Click                                                                  │
│      ↓                                                                       │
│  ActuatorControl.vue                                                         │
│      ↓ sendCommand('ON')                                                     │
│  actuatorsApi.sendCommand()                                                  │
│      ↓ POST /v1/actuators/{esp_id}/{gpio}/command                           │
│  Server: ActuatorService.send_command()                                      │
│      ↓ SafetyService.validate_actuator_command()                            │
│      ↓ MQTT Publish: kaiser/god/esp/{esp_id}/actuator/{gpio}/command        │
│  ESP32: actuator_manager.handleActuatorCommand()                             │
│      ↓ Execute command                                                       │
│      ↓ MQTT Publish: kaiser/god/esp/{esp_id}/actuator/{gpio}/response       │
│  Server: ActuatorResponseHandler                                             │
│      ↓ Log to history                                                        │
│      ↓ WebSocket broadcast("actuator_response", {...})                      │
│  Frontend: handleActuatorResponse()                                          │
│      ↓ Toast notification                                                    │
│      ↓ State update                                                          │
│  User sees confirmation                                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementierungs-Checkliste

### Phase 1: Types (🔴 KRITISCH)
- [ ] `ActuatorCommandType` zu `types/index.ts` hinzufügen
- [ ] `ActuatorCommandRequest` zu `types/index.ts` hinzufügen
- [ ] `ActuatorCommandResponse` zu `types/index.ts` hinzufügen
- [ ] `ActuatorResponseEvent` zu `types/index.ts` hinzufügen
- [ ] `EmergencyStopRequest` zu `types/index.ts` hinzufügen
- [ ] `EmergencyStopResponse` zu `types/index.ts` hinzufügen
- [ ] `MessageType` um `'actuator_response'` erweitern

### Phase 2: API Client (🔴 KRITISCH)
- [ ] `sendCommand()` zu `api/actuators.ts` hinzufügen
- [ ] `emergencyStop()` zu `api/actuators.ts` hinzufügen
- [ ] Optional: `getStatus()` hinzufügen

### Phase 3: Store (🔴 KRITISCH)
- [ ] WebSocket Filter um `'actuator_response'` erweitern
- [ ] `handleActuatorResponse()` implementieren
- [ ] Handler in `wsUnsubscribers` registrieren
- [ ] Import für `ActuatorResponseEvent` hinzufügen

### Phase 4: UI (🟠 HIGH)
- [ ] `ActuatorControl.vue` erstellen
- [ ] In `ActuatorSatellite.vue` integrieren
- [ ] PWM-Slider für `pwm`-Typ
- [ ] Binary Buttons für `pump`, `valve`, `relay`
- [ ] Emergency-State-Warning

### Phase 5: Testing
- [ ] sendCommand() für alle 4 Typen testen
- [ ] WebSocket actuator_response Handler testen
- [ ] Emergency Stop testen
- [ ] Error-Handling testen (offline ESP, safety rejection)

---

## 6. Offene Punkte (V2)

| Feature | Status | Priorität |
|---------|--------|-----------|
| Switch Cycles Display | ESP32 trackt intern, nicht exponiert | V2 |
| Valve Position Display | ESP32 trackt, nicht exponiert | V2 |
| Command History UI | Server-Endpoint existiert | V2 |
| Runtime Display | Server speichert, UI fehlt | V2 |
| Servo Support | Server ready, ESP32 fehlt | V2+ |

---

## 7. Code-Referenzen

### ESP32 (El Trabajante)
| Datei | Beschreibung |
|-------|--------------|
| [actuator_types.h:17-22](El%20Trabajante/src/models/actuator_types.h#L17-L22) | Actuator Type Tokens |
| [actuator_manager.cpp:178-220](El%20Trabajante/src/services/actuator/actuator_manager.cpp#L178-L220) | Command Handler |
| [pump_actuator.h:58-64](El%20Trabajante/src/services/actuator/actuator_drivers/pump_actuator.h#L58-L64) | RuntimeProtection |
| [error_codes.h:25-28](El%20Trabajante/src/models/error_codes.h#L25-L28) | Error Codes 1050-1053 |

### Server (El Servador)
| Datei | Beschreibung |
|-------|--------------|
| [actuators.py:394-483](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L394-L483) | Command Endpoint |
| [actuators.py:570-703](El%20Servador/god_kaiser_server/src/api/v1/actuators.py#L570-L703) | Emergency Stop |
| [actuator.py:69](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L69) | ACTUATOR_COMMANDS |
| [actuator.py:280-332](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L280-L332) | ActuatorCommand Schema |
| [actuator_response_handler.py:141-149](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py#L141-L149) | WebSocket Broadcast |

### Frontend (El Frontend)
| Datei | Beschreibung |
|-------|--------------|
| [actuatorDefaults.ts:89-145](El%20Frontend/src/utils/actuatorDefaults.ts#L89-L145) | Type Config |
| [actuators.ts:4-63](El%20Frontend/src/api/actuators.ts#L4-L63) | API Client (CRUD only) |
| [esp.ts:98](El%20Frontend/src/stores/esp.ts#L98) | WebSocket Filter |
| [esp.ts:1288-1313](El%20Frontend/src/stores/esp.ts#L1288-L1313) | handleActuatorStatus |
| [esp.ts:1552-1559](El%20Frontend/src/stores/esp.ts#L1552-L1559) | Handler Registration |

---

## 8. Architektur-Hinweise

### Server-Centric Design (aus Hierarchie.md)
- **ESP32 ist Quelle:** Sensoren auslesen, Aktoren physisch steuern
- **Server ist Control Hub:** Befehle validieren, Safety-Checks, Logic Engine
- **Frontend ist UI:** Keine direkte ESP-Kommunikation!

### Safety-Service
Alle Commands werden vor MQTT-Publish validiert:
- Emergency-Stop aktiv? → Reject
- Actuator enabled? → Reject if disabled
- Value in range? → Clamp to 0.0-1.0
- Max runtime? → Tracked by ESP32

### Mock vs Real ESP
- **Mock ESP:** `POST /v1/debug/mock-esp/.../actuator` (direkter State-Update)
- **Real ESP:** `POST /v1/actuators/.../command` → MQTT → ESP32 → Response

---

## 8. Hardware & Instance Config (NEU)

### 8.1 ESP32-Analyse: Hardware-relevante Daten

#### A. ActuatorConfig Struktur ([actuator_types.h:38-61](El%20Trabajante/src/models/actuator_types.h#L38-L61))

```cpp
struct ActuatorConfig {
  uint8_t gpio = 255;              // Primary GPIO
  uint8_t aux_gpio = 255;          // Optional secondary pin (valves, H-bridges)
  String actuator_type = "";       // "pump", "valve", "pwm", "relay"
  String actuator_name = "";       // Human-readable label
  String subzone_id = "";          // Subzone assignment
  bool active = false;             // Enabled flag
  bool critical = false;           // Safety priority

  // Runtime & driver specific
  uint8_t pwm_channel = 255;       // Assigned PWM channel
  bool inverted_logic = false;     // LOW = ON for some relays
  uint8_t default_pwm = 0;         // PWM fallback (0-255)
  bool default_state = false;      // Failsafe state

  // Live state (RAM only)
  bool current_state = false;      // Digital ON/OFF
  uint8_t current_pwm = 0;         // PWM duty (0-255)
  unsigned long last_command_ts = 0;
  unsigned long accumulated_runtime_ms = 0; // ⭐ TOTAL runtime tracking

  // Phase 2: Runtime protection
  RuntimeProtection runtime_protection;
};
```

**Erkenntnis:** `accumulated_runtime_ms` wird getrackt, aber NICHT im MQTT-Status exponiert!

#### B. RuntimeProtection Strukturen

**Global** ([actuator_types.h:32-36](El%20Trabajante/src/models/actuator_types.h#L32-L36)):
```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;  // 1h default
  bool timeout_enabled = true;
  unsigned long activation_start_ms = 0;     // Current session start
};
```

**PumpActuator-spezifisch** ([pump_actuator.h:10-15](El%20Trabajante/src/services/actuator/actuator_drivers/pump_actuator.h#L10-L15)):
```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;      // 1h continuous cap
  uint16_t max_activations_per_hour = 60;        // ⭐ Duty-cycle protection
  unsigned long cooldown_ms = 30000UL;           // 30s cooldown
  unsigned long activation_window_ms = 3600000UL;
};

// Intern getrackt (NICHT exponiert!):
static const uint8_t ACTIVATION_HISTORY = 60;
unsigned long activation_timestamps_[ACTIVATION_HISTORY];  // ⭐ Switch cycles history
```

**Erkenntnis:** ESP32 trackt `activation_timestamps_` intern für Duty-Cycle-Protection, exponiert aber nicht die Anzahl!

#### C. PWM-Konfiguration

**PWMActuator** ([pwm_actuator.h](El%20Trabajante/src/services/actuator/actuator_drivers/pwm_actuator.h)):
```cpp
uint8_t pwm_channel_;  // ESP32 LEDC Channel (0-15)
uint8_t pwm_value_;    // Current duty (0-255)
```

**Erkenntnis:** Keine explizite `pwm_frequency` im ESP32 - wird über ESP-IDF LEDC API mit Standard 5000Hz konfiguriert. Resolution ist 8-bit (0-255).

#### D. ValveActuator Position Tracking

**ValveActuator** ([valve_actuator.h:40-43](El%20Trabajante/src/services/actuator/actuator_drivers/valve_actuator.h#L40-L43)):
```cpp
uint8_t current_position_;   // 0-255 (0%=closed, 255=open)
uint8_t target_position_;    // Target for proportional valves
bool is_moving_;             // Movement in progress
uint32_t transition_time_ms_; // Full stroke time
```

**Erkenntnis:** Position-Tracking existiert, wird aber NICHT im Status-Payload gesendet!

#### E. Status-Payload (was der ESP32 sendet)

**buildStatusPayload** ([actuator_manager.cpp:748-768](El%20Trabajante/src/services/actuator/actuator_manager.cpp#L748-L768)):
```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_1",
  "subzone_id": "subzone_a",
  "ts": 1704067200,
  "gpio": 5,
  "type": "pump",
  "state": true,
  "pwm": 0,
  "runtime_ms": 45000,      // ⭐ Current session runtime (nicht total!)
  "emergency": "normal"
}
```

**NICHT im Payload:**
- ❌ `accumulated_runtime_ms` (total runtime)
- ❌ `switch_cycles` / Aktivierungsanzahl
- ❌ `valve_position` (für Ventile)
- ❌ `pwm_frequency`
- ❌ Hardware-Limits

---

### 8.2 Server-Analyse: Persistierung

#### A. ActuatorConfig Model ([actuator.py:17-169](El%20Servador/god_kaiser_server/src/db/models/actuator.py#L17-L169))

**Relevante JSON-Felder:**
```python
safety_constraints: Mapped[Optional[dict]] = mapped_column(
    JSON,
    nullable=True,
    doc="Safety constraints (max_runtime, cooldown_period, emergency_stop_priority)",
)

actuator_metadata: Mapped[dict] = mapped_column(
    JSON,
    default=dict,
    nullable=False,
    doc="Additional actuator metadata",  # ⭐ ERWEITERBAR!
)
```

**Erkenntnis:** `actuator_metadata` ist der ideale Ort für Instance Config - keine Migration nötig!

#### B. ActuatorState Model ([actuator.py:172-298](El%20Servador/god_kaiser_server/src/db/models/actuator.py#L172-L298))

```python
runtime_seconds: Mapped[int] = mapped_column(
    Integer,
    default=0,
    nullable=False,
    doc="Total runtime since last activation (seconds)",  # ⭐ Session-basiert
)

state_metadata: Mapped[Optional[dict]] = mapped_column(
    JSON,
    nullable=True,
    doc="Additional state metadata (warnings, errors, etc.)",  # ⭐ ERWEITERBAR!
)
```

**NICHT vorhanden:**
- ❌ `total_switch_cycles` (muss in metadata oder neues Feld)
- ❌ `first_activated_at` (für Lifecycle)
- ❌ `lifecycle_percentage`

#### C. API Schema ([actuator.py:127-191](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L127-L191))

**ActuatorConfigCreate akzeptiert:**
```python
metadata: Optional[Dict[str, Any]] = Field(None, description="Custom metadata")
```

**Erkenntnis:** Metadata wird bereits akzeptiert und in `actuator_metadata` gespeichert!

#### D. Empfehlung: Option A (JSON erweitern)

**Für V1 - Keine DB-Migration nötig!**

```python
# actuator_metadata erweitern:
{
  # Bestehende Felder (PWM-spezifisch)
  "pwm_frequency": 5000,
  "pwm_resolution": 8,

  # NEU: Instance Config
  "instanceConfig": {
    "connectedLoad": {
      "type": "Wasserpumpe",
      "model": "Gardena 3000/4",
      "voltage": 12,
      "voltageType": "DC",
      "power": 60,
      "inductive": true,
      "inrushMultiplier": 3
    },
    "location": "Gewächshaus 1, Regal 3",
    "wiring": {
      "cableSection": 1.5,
      "cableLength": 5,
      "fuseRating": 10
    },
    "installedAt": "2025-01-01T00:00:00Z",
    "maintenanceIntervalDays": 365,
    "tags": ["bewässerung", "zone-a"]
  },

  # NEU: Operational Data (Server-tracked)
  "operationalData": {
    "totalSwitchCycles": 1234,
    "firstActivatedAt": "2025-01-01T10:00:00Z",
    "lastMaintenanceAt": "2025-06-01T00:00:00Z"
  }
}
```

---

### 8.3 TypeScript Interfaces

#### ActuatorHardwareSpec (Type-Level Defaults)

```typescript
// types/index.ts - HINZUFÜGEN

/**
 * Hardware specifications for an actuator TYPE
 * These are manufacturer/design limits for this category of actuator
 */
export interface ActuatorHardwareSpec {
  // ══════════════════════════════════════════════════════════════
  // ELECTRICAL RATINGS
  // ══════════════════════════════════════════════════════════════

  /** Supported voltage range */
  voltage: {
    min: number           // e.g., 5
    max: number           // e.g., 24
    unit: 'V'
    type: 'DC' | 'AC' | 'DC/AC'
  }

  /** Maximum switching/load current */
  maxCurrent: {
    value: number         // e.g., 10
    unit: 'A' | 'mA'
  }

  /** Maximum switching/load power */
  maxPower: {
    value: number         // e.g., 250
    unit: 'W'
  }

  /** Suitable for inductive loads (motors, solenoids) */
  inductiveLoadRated: boolean

  /** PWM specifications (only for PWM-capable actuators) */
  pwm?: {
    frequencyRange: [number, number]  // e.g., [1000, 25000]
    defaultFrequency: number          // e.g., 5000
    resolution: 8 | 10 | 12           // ESP32: typically 8
  }

  // ══════════════════════════════════════════════════════════════
  // MECHANICAL / LIFETIME
  // ══════════════════════════════════════════════════════════════

  /** Expected lifetime in switching cycles (for relays) */
  ratedCycles?: number    // e.g., 100000

  /** Typical switching time in ms */
  switchingTimeMs?: number

  /** Operating temperature range */
  temperatureRange?: {
    min: number           // e.g., -10
    max: number           // e.g., +50
    unit: '°C'
  }
}
```

#### ActuatorInstanceConfig (User-Eingabe pro Instanz)

```typescript
/**
 * User-provided configuration for a SPECIFIC actuator instance
 * Stored in server actuator_metadata.instanceConfig
 */
export interface ActuatorInstanceConfig {
  // ══════════════════════════════════════════════════════════════
  // CONNECTED LOAD (Was ist angeschlossen?)
  // ══════════════════════════════════════════════════════════════

  connectedLoad?: {
    /** Type/description of connected device */
    type: string              // "Wasserpumpe", "LED Strip", "Heizstab"

    /** Manufacturer and model */
    model?: string            // "Gardena 3000/4"

    /** Operating voltage */
    voltage: number           // 12
    voltageType: 'DC' | 'AC'

    /** Power consumption */
    power: number             // 60

    /** Current draw (auto-calculated: P/V if not provided) */
    current?: number

    /** Is it an inductive load? */
    inductive: boolean

    /** Inrush current multiplier for motors (typically 3-8x) */
    inrushMultiplier?: number
  }

  // ══════════════════════════════════════════════════════════════
  // INSTALLATION (Wo und wie installiert?)
  // ══════════════════════════════════════════════════════════════

  /** Physical location description */
  location?: string           // "Gewächshaus 1, Regal 3"

  /** Wiring information */
  wiring?: {
    cableSection: number      // mm² (0.75, 1.5, 2.5)
    cableLength: number       // meters
    fuseRating?: number       // Amperes
  }

  // ══════════════════════════════════════════════════════════════
  // MAINTENANCE
  // ══════════════════════════════════════════════════════════════

  installedAt?: string        // ISO date
  lastMaintenanceAt?: string  // ISO date
  maintenanceIntervalDays?: number
  maintenanceNotes?: string

  // ══════════════════════════════════════════════════════════════
  // TAGS
  // ══════════════════════════════════════════════════════════════

  tags?: string[]             // ["bewässerung", "zone-a", "kritisch"]
}
```

#### ActuatorOperationalData (Automatisch getrackt)

```typescript
/**
 * Operational data tracked by Server
 * Stored in server actuator_metadata.operationalData or state_metadata
 */
export interface ActuatorOperationalData {
  // ══════════════════════════════════════════════════════════════
  // RUNTIME TRACKING
  // ══════════════════════════════════════════════════════════════

  /** Total accumulated runtime in seconds */
  totalRuntimeSeconds: number

  /** Total switching cycles (ON→OFF transitions) */
  totalSwitchCycles: number

  /** Current session runtime (from WebSocket) */
  currentSessionSeconds?: number

  // ══════════════════════════════════════════════════════════════
  // TIMESTAMPS
  // ══════════════════════════════════════════════════════════════

  lastActivatedAt?: string
  lastDeactivatedAt?: string
  firstActivatedAt?: string   // For lifecycle calculation

  // ══════════════════════════════════════════════════════════════
  // ERROR TRACKING
  // ══════════════════════════════════════════════════════════════

  errorCount: number
  lastError?: string
  lastErrorAt?: string

  // ══════════════════════════════════════════════════════════════
  // HEALTH STATUS (Calculated in Frontend)
  // ══════════════════════════════════════════════════════════════

  healthStatus: 'good' | 'warning' | 'critical' | 'unknown'
  healthWarnings: string[]
  estimatedRemainingCycles?: number
  lifecyclePercentUsed?: number
  daysUntilMaintenance?: number
}
```

---

### 8.4 Registry-Erweiterung

#### Erweiterte ActuatorTypeConfig

```typescript
// actuatorDefaults.ts - ERWEITERN

export interface ActuatorTypeConfig {
  // ══════════════════════════════════════════════════════════════
  // BESTEHENDE FELDER
  // ══════════════════════════════════════════════════════════════

  label: string
  icon: string
  description: string
  category: ActuatorCategoryId
  isPwm: boolean
  defaultValue: number
  maxRuntimeSeconds: number
  cooldownSeconds: number
  supportsAuxGpio: boolean
  supportsInvertedLogic: boolean

  // ══════════════════════════════════════════════════════════════
  // NEU: V4 Additions
  // ══════════════════════════════════════════════════════════════

  /** Supported commands for this type */
  supportedCommands: ('ON' | 'OFF' | 'PWM' | 'TOGGLE')[]

  /** Does this type track runtime? */
  supportsRuntimeTracking: boolean

  /** Valid value range */
  valueRange: { min: number; max: number }

  // ══════════════════════════════════════════════════════════════
  // NEU: HARDWARE SPECS
  // ══════════════════════════════════════════════════════════════

  /** Hardware specifications for this actuator type */
  hardwareSpec: ActuatorHardwareSpec

  // ══════════════════════════════════════════════════════════════
  // NEU: INSTANCE CONFIG REQUIREMENTS
  // ══════════════════════════════════════════════════════════════

  instanceConfigRequirements: {
    /** Required fields when adding */
    required: (keyof ActuatorInstanceConfig)[]
    /** Recommended fields */
    recommended: (keyof ActuatorInstanceConfig)[]
    /** Default values for connectedLoad */
    connectedLoadDefaults: Partial<ActuatorInstanceConfig['connectedLoad']>
  }

  // ══════════════════════════════════════════════════════════════
  // NEU: UI CONFIGURATION
  // ══════════════════════════════════════════════════════════════

  ui: {
    showHardwareInfo: boolean
    showOperationalData: boolean
    showLifecycleWarning: boolean
    showMaintenanceInfo: boolean
  }
}
```

#### Alle 4 Types komplett

```typescript
export const ACTUATOR_TYPE_CONFIG: Record<string, ActuatorTypeConfig> = {
  // ═══════════════════════════════════════════════════════════════
  // PUMP - Wasserpumpe mit RuntimeProtection
  // ═══════════════════════════════════════════════════════════════
  pump: {
    // Basis
    label: 'Pumpe',
    icon: 'Droplet',
    description: 'Wasserpumpe mit RuntimeProtection. Automatische Abschaltung nach max. Laufzeit.',
    category: 'pump',
    isPwm: false,
    defaultValue: 0,

    // Safety (ESP32 defaults)
    maxRuntimeSeconds: 3600,  // 1h
    cooldownSeconds: 30,

    // Features
    supportsAuxGpio: false,
    supportsInvertedLogic: true,
    supportedCommands: ['ON', 'OFF', 'TOGGLE'],
    supportsRuntimeTracking: true,
    valueRange: { min: 0, max: 1 },

    // Hardware Specs (typisches Relais-Modul)
    hardwareSpec: {
      voltage: { min: 5, max: 24, unit: 'V', type: 'DC' },
      maxCurrent: { value: 10, unit: 'A' },
      maxPower: { value: 250, unit: 'W' },
      inductiveLoadRated: true,
      ratedCycles: 100000,
      switchingTimeMs: 10,
      temperatureRange: { min: -10, max: 50, unit: '°C' },
    },

    // Instance Config Requirements
    instanceConfigRequirements: {
      required: [],  // Name kommt über Basis-Config
      recommended: ['connectedLoad', 'location'],
      connectedLoadDefaults: {
        type: 'Wasserpumpe',
        voltage: 12,
        voltageType: 'DC',
        power: 60,
        inductive: true,
        inrushMultiplier: 3,
      },
    },

    // UI Config
    ui: {
      showHardwareInfo: true,
      showOperationalData: true,
      showLifecycleWarning: true,
      showMaintenanceInfo: true,
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // VALVE - Magnetventil/Kugelventil
  // ═══════════════════════════════════════════════════════════════
  valve: {
    label: 'Ventil',
    icon: 'Zap',
    description: 'Magnetventil oder Kugelventil. Unterstützt aux_gpio für H-Bridge Direction.',
    category: 'valve',
    isPwm: false,
    defaultValue: 0,

    maxRuntimeSeconds: 0,  // Valves can stay open
    cooldownSeconds: 0,

    supportsAuxGpio: true,
    supportsInvertedLogic: true,
    supportedCommands: ['ON', 'OFF', 'TOGGLE'],
    supportsRuntimeTracking: false,
    valueRange: { min: 0, max: 1 },

    hardwareSpec: {
      voltage: { min: 12, max: 24, unit: 'V', type: 'DC' },
      maxCurrent: { value: 2, unit: 'A' },
      maxPower: { value: 50, unit: 'W' },
      inductiveLoadRated: true,  // Solenoid valves are inductive
      ratedCycles: 500000,       // Valves typically last longer
      switchingTimeMs: 50,       // Slower than relays
      temperatureRange: { min: 0, max: 60, unit: '°C' },
    },

    instanceConfigRequirements: {
      required: [],
      recommended: ['connectedLoad', 'location'],
      connectedLoadDefaults: {
        type: 'Magnetventil',
        voltage: 12,
        voltageType: 'DC',
        power: 15,
        inductive: true,
      },
    },

    ui: {
      showHardwareInfo: true,
      showOperationalData: true,
      showLifecycleWarning: true,
      showMaintenanceInfo: false,
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // RELAY - Allzweck-Relais
  // ═══════════════════════════════════════════════════════════════
  relay: {
    label: 'Relais',
    icon: 'Power',
    description: 'Allzweck-Relais für Beleuchtung, Heizung, etc.',
    category: 'relay',
    isPwm: false,
    defaultValue: 0,

    maxRuntimeSeconds: 0,
    cooldownSeconds: 0,

    supportsAuxGpio: false,
    supportsInvertedLogic: true,
    supportedCommands: ['ON', 'OFF', 'TOGGLE'],
    supportsRuntimeTracking: false,
    valueRange: { min: 0, max: 1 },

    hardwareSpec: {
      voltage: { min: 5, max: 250, unit: 'V', type: 'DC/AC' },  // Can switch AC!
      maxCurrent: { value: 10, unit: 'A' },
      maxPower: { value: 2500, unit: 'W' },  // 250V * 10A
      inductiveLoadRated: true,
      ratedCycles: 100000,
      switchingTimeMs: 10,
      temperatureRange: { min: -20, max: 70, unit: '°C' },
    },

    instanceConfigRequirements: {
      required: [],
      recommended: ['connectedLoad'],
      connectedLoadDefaults: {
        type: 'Verbraucher',
        voltage: 230,
        voltageType: 'AC',
        power: 100,
        inductive: false,
      },
    },

    ui: {
      showHardwareInfo: true,
      showOperationalData: false,  // Relays usually don't need runtime tracking
      showLifecycleWarning: true,
      showMaintenanceInfo: false,
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // PWM - Dimmbare Aktoren
  // ═══════════════════════════════════════════════════════════════
  pwm: {
    label: 'PWM',
    icon: 'Gauge',
    description: 'PWM-gesteuerte Aktoren (Lüfter, dimmbare LEDs). Wert 0-100%.',
    category: 'pwm',
    isPwm: true,
    defaultValue: 0,

    maxRuntimeSeconds: 0,
    cooldownSeconds: 0,

    supportsAuxGpio: false,
    supportsInvertedLogic: false,  // PWM doesn't support inverted
    supportedCommands: ['ON', 'OFF', 'PWM'],
    supportsRuntimeTracking: false,
    valueRange: { min: 0, max: 1 },  // 0.0 - 1.0 (100%)

    hardwareSpec: {
      voltage: { min: 3.3, max: 24, unit: 'V', type: 'DC' },
      maxCurrent: { value: 3, unit: 'A' },
      maxPower: { value: 75, unit: 'W' },
      inductiveLoadRated: false,  // PWM not ideal for motors
      pwm: {
        frequencyRange: [1000, 25000],
        defaultFrequency: 5000,
        resolution: 8,
      },
    },

    instanceConfigRequirements: {
      required: [],
      recommended: ['connectedLoad'],
      connectedLoadDefaults: {
        type: 'LED Strip',
        voltage: 12,
        voltageType: 'DC',
        power: 30,
        inductive: false,
      },
    },

    ui: {
      showHardwareInfo: true,
      showOperationalData: false,
      showLifecycleWarning: false,  // No switching cycles for PWM
      showMaintenanceInfo: false,
    },
  },
}
```

---

### 8.5 DB-Persistierung (Entscheidung)

**Empfehlung: Option A (JSON erweitern) für V1**

| Aspekt | Option A (JSON) | Option B (Neue Felder) |
|--------|-----------------|------------------------|
| Migration | ❌ Nicht nötig | ✅ Alembic Migration |
| Flexibilität | ✅ Sehr hoch | ❌ Starr |
| Queries | ⚠️ JSON-Queries | ✅ Native SQL |
| Validation | ⚠️ Pydantic | ✅ DB-Constraints |
| Aufwand V1 | ✅ ~30 min | ❌ ~2-3h |

**Server-Schema (keine Änderung an DB!):**

```python
# schemas/actuator.py - ActuatorConfigCreate erweitern

class ActuatorConfigCreate(ActuatorConfigBase):
    # ... bestehende Felder ...

    # Instance Config als Teil von metadata
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata including instanceConfig",
        json_schema_extra={
            "example": {
                "instanceConfig": {
                    "connectedLoad": {
                        "type": "Wasserpumpe",
                        "voltage": 12,
                        "voltageType": "DC",
                        "power": 60,
                        "inductive": True
                    },
                    "location": "Gewächshaus 1"
                }
            }
        }
    )
```

**Server: Operational Data Tracking (ActuatorState.state_metadata):**

```python
# In actuator_handler.py oder actuator_service.py

async def update_operational_data(esp_id: str, gpio: int, command: str):
    """Track switch cycles and runtime"""
    state = await get_actuator_state(esp_id, gpio)

    op_data = state.state_metadata.get("operationalData", {
        "totalSwitchCycles": 0,
        "totalRuntimeSeconds": 0,
        "firstActivatedAt": None,
        "lastActivatedAt": None,
    })

    if command == "ON":
        op_data["totalSwitchCycles"] += 1
        op_data["lastActivatedAt"] = datetime.utcnow().isoformat()
        if not op_data["firstActivatedAt"]:
            op_data["firstActivatedAt"] = op_data["lastActivatedAt"]

    state.state_metadata["operationalData"] = op_data
    await save_actuator_state(state)
```

---

### 8.6 UI-Erweiterungen

#### Add-Actuator-Modal - Neue Sektionen

```vue
<!-- ESPOrbitalLayout.vue Add-Modal erweitern -->

<template>
  <div class="add-actuator-form">
    <!-- Sektion 1: Basis (bestehend) -->
    <section class="form-section">
      <h4>Grundkonfiguration</h4>
      <!-- GPIO, Type, Name, Safety Settings -->
    </section>

    <!-- Sektion 2: Angeschlossene Last (NEU) -->
    <details class="form-section" :open="showLoadSection">
      <summary class="section-header">
        <span>Angeschlossene Last</span>
        <span class="badge">empfohlen</span>
      </summary>

      <div class="load-form">
        <!-- Gerätetyp -->
        <div class="form-group">
          <label>Gerätetyp</label>
          <input
            v-model="instanceConfig.connectedLoad.type"
            :placeholder="connectedLoadDefaults.type"
            class="form-input"
          />
        </div>

        <!-- Modell (optional) -->
        <div class="form-group">
          <label>Modell <span class="optional">(optional)</span></label>
          <input
            v-model="instanceConfig.connectedLoad.model"
            placeholder="z.B. Gardena 3000/4"
            class="form-input"
          />
        </div>

        <!-- Spannung -->
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Spannung</label>
            <input
              v-model.number="instanceConfig.connectedLoad.voltage"
              type="number"
              :placeholder="String(connectedLoadDefaults.voltage)"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label>Typ</label>
            <select v-model="instanceConfig.connectedLoad.voltageType" class="form-select">
              <option value="DC">DC</option>
              <option value="AC">AC</option>
            </select>
          </div>
        </div>

        <!-- Leistung -->
        <div class="form-group">
          <label>Leistung (Watt)</label>
          <input
            v-model.number="instanceConfig.connectedLoad.power"
            type="number"
            :placeholder="String(connectedLoadDefaults.power)"
            class="form-input"
          />
        </div>

        <!-- Induktive Last -->
        <div class="form-group checkbox">
          <label>
            <input
              type="checkbox"
              v-model="instanceConfig.connectedLoad.inductive"
            />
            Induktive Last (Motor, Magnetventil, Transformator)
          </label>
        </div>

        <!-- ⚠️ WARNUNGEN -->
        <div v-if="loadExceedsMax" class="alert alert-warning">
          <AlertTriangle class="w-4 h-4" />
          <span>
            Last ({{ instanceConfig.connectedLoad.power }}W) überschreitet
            Maximum ({{ hardwareSpec.maxPower.value }}W)!
          </span>
        </div>

        <div v-if="inductiveNotRated" class="alert alert-warning">
          <AlertTriangle class="w-4 h-4" />
          <span>
            Dieser Aktor-Typ ist nicht für induktive Lasten ausgelegt!
          </span>
        </div>
      </div>
    </details>

    <!-- Sektion 3: Installation (NEU, optional) -->
    <details class="form-section">
      <summary class="section-header">
        <span>Installation</span>
        <span class="badge badge-muted">optional</span>
      </summary>

      <div class="installation-form">
        <!-- Standort -->
        <div class="form-group">
          <label>Standort</label>
          <input
            v-model="instanceConfig.location"
            placeholder="z.B. Gewächshaus 1, Regal 3"
            class="form-input"
          />
        </div>

        <!-- Verkabelung -->
        <div class="form-row">
          <div class="form-group">
            <label>Kabelquerschnitt</label>
            <select v-model.number="instanceConfig.wiring.cableSection" class="form-select">
              <option :value="0.75">0.75 mm²</option>
              <option :value="1.5">1.5 mm²</option>
              <option :value="2.5">2.5 mm²</option>
              <option :value="4">4 mm²</option>
            </select>
          </div>
          <div class="form-group">
            <label>Kabellänge (m)</label>
            <input
              v-model.number="instanceConfig.wiring.cableLength"
              type="number"
              placeholder="5"
              class="form-input"
            />
          </div>
        </div>

        <!-- ⚠️ Spannungsabfall-Warnung -->
        <div v-if="voltageDropWarning" class="alert alert-info">
          <Info class="w-4 h-4" />
          <span>
            Spannungsabfall: ~{{ voltageDrop.toFixed(1) }}V
            ({{ voltageDropPercent.toFixed(1) }}%)
            <template v-if="voltageDropPercent > 5">
              - Größerer Querschnitt empfohlen!
            </template>
          </span>
        </div>
      </div>
    </details>
  </div>
</template>
```

**Validierungs-Logik:**

```typescript
// Computed properties für Add-Modal

const hardwareSpec = computed(() =>
  ACTUATOR_TYPE_CONFIG[selectedType.value]?.hardwareSpec
)

const connectedLoadDefaults = computed(() =>
  ACTUATOR_TYPE_CONFIG[selectedType.value]?.instanceConfigRequirements.connectedLoadDefaults || {}
)

const loadExceedsMax = computed(() => {
  const load = instanceConfig.value.connectedLoad?.power || 0
  const max = hardwareSpec.value?.maxPower?.value || Infinity
  return load > max
})

const inductiveNotRated = computed(() => {
  const inductive = instanceConfig.value.connectedLoad?.inductive
  const rated = hardwareSpec.value?.inductiveLoadRated
  return inductive && !rated
})

// Spannungsabfall-Berechnung (Kupfer: ρ = 0.0178 Ω·mm²/m)
const voltageDrop = computed(() => {
  const length = instanceConfig.value.wiring?.cableLength || 0
  const section = instanceConfig.value.wiring?.cableSection || 1.5
  const voltage = instanceConfig.value.connectedLoad?.voltage || 12
  const power = instanceConfig.value.connectedLoad?.power || 0

  if (!length || !power || !voltage) return 0

  const current = power / voltage
  const resistivity = 0.0178 // Kupfer
  const resistance = resistivity * (length * 2) / section // Hin + Rück
  return current * resistance
})

const voltageDropPercent = computed(() => {
  const voltage = instanceConfig.value.connectedLoad?.voltage || 12
  return voltage > 0 ? (voltageDrop.value / voltage) * 100 : 0
})

const voltageDropWarning = computed(() => voltageDropPercent.value > 3)
```

#### ActuatorSatellite - Hardware-Info Panel

```vue
<!-- ActuatorSatellite.vue erweitern -->

<template>
  <div class="actuator-satellite" :class="statusClass">
    <!-- Bestehender Content: Icon, Name, Status LED -->

    <!-- NEU: Hardware Info Panel (Hover/Expand) -->
    <div v-if="showHardwareInfo && typeConfig.ui.showHardwareInfo" class="hardware-panel">
      <!-- Angeschlossene Last -->
      <div v-if="connectedLoad" class="info-section">
        <h5>Angeschlossene Last</h5>
        <dl class="info-grid">
          <dt>Gerät</dt>
          <dd>{{ connectedLoad.type }} {{ connectedLoad.model || '' }}</dd>
          <dt>Leistung</dt>
          <dd>{{ connectedLoad.power }}W @ {{ connectedLoad.voltage }}V {{ connectedLoad.voltageType }}</dd>
          <dt>Auslastung</dt>
          <dd>
            <div class="utilization-bar">
              <div
                class="utilization-fill"
                :class="utilizationClass"
                :style="{ width: `${loadUtilization}%` }"
              />
            </div>
            <span>{{ loadUtilization.toFixed(0) }}%</span>
          </dd>
        </dl>
      </div>

      <!-- Betriebsdaten -->
      <div v-if="typeConfig.ui.showOperationalData && operationalData" class="info-section">
        <h5>Betriebsdaten</h5>
        <dl class="info-grid">
          <dt>Laufzeit</dt>
          <dd>{{ formatDuration(operationalData.totalRuntimeSeconds) }}</dd>
          <dt>Schaltzyklen</dt>
          <dd>
            {{ operationalData.totalSwitchCycles?.toLocaleString() || 0 }}
            <span v-if="hardwareSpec.ratedCycles" class="rated-cycles">
              / {{ hardwareSpec.ratedCycles.toLocaleString() }}
            </span>
          </dd>
        </dl>
      </div>

      <!-- Lifecycle Warning -->
      <div v-if="lifecycleWarning" class="lifecycle-alert" :class="lifecycleClass">
        <AlertTriangle class="w-4 h-4" />
        <span>{{ lifecycleWarning }}</span>
      </div>

      <!-- Maintenance Warning -->
      <div v-if="maintenanceWarning" class="maintenance-alert">
        <Wrench class="w-4 h-4" />
        <span>{{ maintenanceWarning }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Lifecycle-Berechnungen
const lifecyclePercentUsed = computed(() => {
  if (!hardwareSpec.value?.ratedCycles) return null
  const cycles = operationalData.value?.totalSwitchCycles || 0
  return (cycles / hardwareSpec.value.ratedCycles) * 100
})

const lifecycleWarning = computed(() => {
  const percent = lifecyclePercentUsed.value
  if (percent === null) return null
  if (percent > 90) return '⚠️ >90% Lebensdauer - Austausch einplanen!'
  if (percent > 75) return '⚠️ >75% Lebensdauer verbraucht'
  return null
})

const lifecycleClass = computed(() => {
  const percent = lifecyclePercentUsed.value
  if (percent === null) return ''
  if (percent > 90) return 'critical'
  if (percent > 75) return 'warning'
  return ''
})

const loadUtilization = computed(() => {
  const load = connectedLoad.value?.power || 0
  const max = hardwareSpec.value?.maxPower?.value || 1
  return Math.min((load / max) * 100, 100)
})

const utilizationClass = computed(() => {
  const util = loadUtilization.value
  if (util > 90) return 'critical'
  if (util > 75) return 'warning'
  return 'good'
})

const maintenanceWarning = computed(() => {
  const days = operationalData.value?.daysUntilMaintenance
  if (days === undefined || days === null) return null
  if (days <= 0) return '🔧 Wartung überfällig!'
  if (days <= 30) return `🔧 Wartung in ${days} Tagen`
  return null
})

function formatDuration(seconds: number): string {
  if (!seconds) return '0h'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 24) {
    const days = Math.floor(hours / 24)
    return `${days}d ${hours % 24}h`
  }
  return `${hours}h ${minutes}m`
}
</script>
```

---

### 8.7 Implementierungs-Checkliste (Hardware)

#### Types & Interfaces
- [ ] `ActuatorHardwareSpec` Interface zu `types/index.ts` hinzufügen
- [ ] `ActuatorInstanceConfig` Interface zu `types/index.ts` hinzufügen
- [ ] `ActuatorOperationalData` Interface zu `types/index.ts` hinzufügen

#### Registry
- [ ] `ActuatorTypeConfig` Interface in `actuatorDefaults.ts` erweitern
- [ ] `hardwareSpec` zu allen 4 Typen hinzufügen
- [ ] `instanceConfigRequirements` zu allen 4 Typen hinzufügen
- [ ] `ui` Config zu allen 4 Typen hinzufügen
- [ ] Helper-Funktion `getHardwareSpec(type)` hinzufügen

#### Add-Actuator-Modal
- [ ] "Angeschlossene Last" Sektion hinzufügen
- [ ] "Installation Details" Sektion hinzufügen
- [ ] `loadExceedsMax` Warnung implementieren
- [ ] `inductiveNotRated` Warnung implementieren
- [ ] `voltageDropWarning` Berechnung und Anzeige
- [ ] Default-Werte aus `connectedLoadDefaults` vorausfüllen

#### ActuatorSatellite
- [ ] Hardware-Info Panel (Hover/Expand) hinzufügen
- [ ] Auslastungs-Anzeige mit Progress-Bar
- [ ] Lifecycle-Warnung bei >75% / >90%
- [ ] Wartungs-Warnung
- [ ] `formatDuration()` Helper

#### Server (Optional für V1)
- [ ] `instanceConfig` Schema in Pydantic dokumentieren
- [ ] Operational Data Tracking im ActuatorState implementieren
- [ ] Switch-Cycle Counter bei ON-Commands inkrementieren

#### API
- [ ] `instanceConfig` in `createOrUpdate()` Request unterstützen
- [ ] `operationalData` in Status-Response einbinden

---

## 9. Code-Referenzen (ergänzt)

### ESP32 (Hardware-relevant)
| Datei | Beschreibung |
|-------|--------------|
| [actuator_types.h:38-61](El%20Trabajante/src/models/actuator_types.h#L38-L61) | ActuatorConfig struct |
| [actuator_types.h:32-36](El%20Trabajante/src/models/actuator_types.h#L32-L36) | RuntimeProtection struct |
| [actuator_manager.cpp:748-768](El%20Trabajante/src/services/actuator/actuator_manager.cpp#L748-L768) | buildStatusPayload |
| [pump_actuator.h:10-15](El%20Trabajante/src/services/actuator/actuator_drivers/pump_actuator.h#L10-L15) | PumpActuator RuntimeProtection |
| [valve_actuator.h:40-43](El%20Trabajante/src/services/actuator/actuator_drivers/valve_actuator.h#L40-L43) | ValveActuator Position Tracking |
| [pwm_actuator.h:32-33](El%20Trabajante/src/services/actuator/actuator_drivers/pwm_actuator.h#L32-L33) | PWMActuator Channel/Value |

### Server (Persistierung)
| Datei | Beschreibung |
|-------|--------------|
| [actuator.py:115-127](El%20Servador/god_kaiser_server/src/db/models/actuator.py#L115-L127) | safety_constraints + actuator_metadata JSON |
| [actuator.py:251-256](El%20Servador/god_kaiser_server/src/db/models/actuator.py#L251-L256) | runtime_seconds in ActuatorState |
| [actuator.py:273-277](El%20Servador/god_kaiser_server/src/db/models/actuator.py#L273-L277) | state_metadata JSON |
| [actuator.py:174-177](El%20Servador/god_kaiser_server/src/schemas/actuator.py#L174-L177) | metadata Field in Schema |

### Frontend (bestehende Patterns)
| Datei | Beschreibung |
|-------|--------------|
| [actuatorDefaults.ts:14-41](El%20Frontend/src/utils/actuatorDefaults.ts#L14-L41) | ActuatorTypeConfig Interface |
| [actuatorDefaults.ts:89-145](El%20Frontend/src/utils/actuatorDefaults.ts#L89-L145) | ACTUATOR_TYPE_CONFIG |
| [sensorDefaults.ts](El%20Frontend/src/utils/sensorDefaults.ts) | Referenz: Registry Pattern |

---

## 10. Offene Fragen (ergänzt)

| Frage | Status | Entscheidung |
|-------|--------|--------------|
| Wo Instance Config speichern? | ✅ Entschieden | `actuator_metadata.instanceConfig` |
| Operational Data tracken? | ⏳ V1 Optional | Server-side in `state_metadata` |
| DB-Migration nötig? | ✅ Nein | JSON-Felder reichen für V1 |
| Switch Cycles vom ESP32 holen? | ❌ Nicht möglich | ESP32 trackt intern, exponiert nicht |
| Valve Position anzeigen? | ⏳ V2 | ESP32 müsste Payload erweitern |
| PWM Frequency konfigurierbar? | ⏳ V2 | Server-seitig, ESP32 nutzt Default 5kHz |

---

---

## 11. Erweiterte Sicherheits-Warnungen (Add-Modal)

### 11.1 Inrush Current Warnung

**Problem:** Motoren und induktive Lasten haben beim Einschalten einen **3-8x höheren Strom** als im Normalbetrieb. Wenn der Einschaltstrom das Relais-Rating überschreitet, kann das Relais verschweißen.

**Implementierung:**

```typescript
// Computed Property für Add-Modal

/**
 * Warnung wenn Einschaltstrom das Relais-Maximum überschreitet
 *
 * Formel: Inrush = (P / V) * Multiplier
 * Beispiel: 60W Pumpe @ 12V mit 6x Inrush = 5A * 6 = 30A Einschaltstrom!
 */
const inrushExceedsMax = computed(() => {
  const load = instanceConfig.value.connectedLoad
  if (!load || !load.inductive || !load.inrushMultiplier) return false

  const normalCurrent = load.power / load.voltage
  const inrushCurrent = normalCurrent * load.inrushMultiplier
  const maxCurrent = hardwareSpec.value?.maxCurrent?.value || Infinity

  return inrushCurrent > maxCurrent
})

const inrushCurrentValue = computed(() => {
  const load = instanceConfig.value.connectedLoad
  if (!load) return 0
  const normalCurrent = load.power / load.voltage
  return normalCurrent * (load.inrushMultiplier || 1)
})
```

**UI-Warnung:**

```vue
<div v-if="inrushExceedsMax" class="alert alert-danger">
  <AlertTriangle class="w-4 h-4" />
  <div>
    <strong>Einschaltstrom zu hoch!</strong>
    <p>
      Einschaltstrom ~{{ inrushCurrentValue.toFixed(1) }}A überschreitet
      Relais-Maximum ({{ hardwareSpec.maxCurrent.value }}A).
    </p>
    <p class="text-sm">
      Empfehlung: Softstart-Modul verwenden oder stärkeres Relais wählen.
    </p>
  </div>
</div>
```

---

### 11.2 Sicherungs-Warnung

**Problem:** Wenn die Sicherung zu klein dimensioniert ist, löst sie bei Dauerlast aus. Wenn sie zu groß ist, schützt sie nicht richtig.

**Implementierung:**

```typescript
/**
 * Sicherungs-Validierung
 *
 * Regeln:
 * - Sicherung sollte 1.25x - 1.5x des Nennstroms sein
 * - Bei induktiven Lasten: Sicherung sollte Inrush-Strom berücksichtigen
 */
const fuseWarning = computed(() => {
  const load = instanceConfig.value.connectedLoad
  const wiring = instanceConfig.value.wiring

  if (!load || !wiring?.fuseRating) return null

  const normalCurrent = load.power / load.voltage
  const fuse = wiring.fuseRating

  // Sicherung zu klein für Normalbetrieb
  if (normalCurrent > fuse * 0.8) {
    return {
      type: 'danger',
      message: `Sicherung (${fuse}A) zu klein für Dauerlast (${normalCurrent.toFixed(1)}A)!`,
      recommendation: `Empfohlen: ${Math.ceil(normalCurrent * 1.25)}A Sicherung`
    }
  }

  // Sicherung könnte bei Einschaltstrom auslösen
  if (load.inductive && load.inrushMultiplier) {
    const inrushCurrent = normalCurrent * load.inrushMultiplier
    if (inrushCurrent > fuse * 1.5) {
      return {
        type: 'warning',
        message: `Sicherung könnte bei Einschaltstrom (~${inrushCurrent.toFixed(0)}A) auslösen`,
        recommendation: `Träge Sicherung (T) oder Motorschutzschalter empfohlen`
      }
    }
  }

  // Sicherung zu groß (kein Schutz)
  if (fuse > normalCurrent * 3) {
    return {
      type: 'info',
      message: `Sicherung (${fuse}A) ist überdimensioniert für ${normalCurrent.toFixed(1)}A Last`,
      recommendation: `Bei Kurzschluss möglicherweise kein ausreichender Schutz`
    }
  }

  return null
})
```

**UI-Warnung:**

```vue
<div v-if="fuseWarning" class="alert" :class="`alert-${fuseWarning.type}`">
  <component :is="fuseWarning.type === 'danger' ? AlertTriangle : Info" class="w-4 h-4" />
  <div>
    <strong>{{ fuseWarning.message }}</strong>
    <p class="text-sm">{{ fuseWarning.recommendation }}</p>
  </div>
</div>
```

---

### 11.3 Kabelquerschnitt-Warnung

**Problem:** Zu dünne Kabel können überhitzen und sind brandgefährlich.

**Implementierung:**

```typescript
/**
 * Kabelquerschnitt-Empfehlung basierend auf Strom
 *
 * Faustregeln (Kupfer, Einzelader, 30°C):
 * - 0.75mm² → max 6A
 * - 1.5mm² → max 10A
 * - 2.5mm² → max 16A
 * - 4mm² → max 25A
 */
const CABLE_RATINGS: Record<number, number> = {
  0.75: 6,
  1.5: 10,
  2.5: 16,
  4: 25,
}

const cableWarning = computed(() => {
  const load = instanceConfig.value.connectedLoad
  const wiring = instanceConfig.value.wiring

  if (!load || !wiring?.cableSection) return null

  const current = load.power / load.voltage
  const maxCurrent = CABLE_RATINGS[wiring.cableSection] || 10

  if (current > maxCurrent) {
    // Finde empfohlenen Querschnitt
    const recommended = Object.entries(CABLE_RATINGS)
      .find(([_, max]) => current <= max * 0.8)?.[0] || '4+'

    return {
      type: 'danger',
      message: `Kabel (${wiring.cableSection}mm²) für ${current.toFixed(1)}A unterdimensioniert!`,
      recommendation: `Mindestens ${recommended}mm² empfohlen`
    }
  }

  if (current > maxCurrent * 0.8) {
    return {
      type: 'warning',
      message: `Kabel (${wiring.cableSection}mm²) nahe am Limit für ${current.toFixed(1)}A`,
      recommendation: `Größerer Querschnitt für Sicherheitsreserve empfohlen`
    }
  }

  return null
})
```

---

### 11.4 Implementierungs-Checkliste (Warnungen)

- [ ] `inrushExceedsMax` computed in ESPOrbitalLayout.vue
- [ ] `inrushCurrentValue` computed in ESPOrbitalLayout.vue
- [ ] `fuseWarning` computed in ESPOrbitalLayout.vue
- [ ] `cableWarning` computed in ESPOrbitalLayout.vue
- [ ] `CABLE_RATINGS` Konstante exportieren
- [ ] UI-Warnungen im Add-Modal integrieren (3 Alert-Boxen)
- [ ] Danger/Warning/Info Styling konsistent mit Design-System

---

## 12. Error/Log-System (Vollständige Dokumentation)

### 12.1 ESP32 Error Codes (Verifiziert aus error_codes.h)

**Quelle:** [error_codes.h](El%20Trabajante/src/models/error_codes.h)

#### A. Actuator Error Codes (1050-1053)

| Code | Konstante | ESP32 Trigger | Server-Handling | Frontend-Message |
|------|-----------|---------------|-----------------|------------------|
| 1050 | `ERROR_ACTUATOR_SET_FAILED` | `actuator_manager.cpp:357-362` - controlActuator/controlActuatorBinary return false | Logged to command history | "Aktor-Status konnte nicht gesetzt werden" |
| 1051 | `ERROR_ACTUATOR_INIT_FAILED` | `actuator_manager.cpp:237-253` - Driver.begin() failed | Logged with error_message | "Aktor-Initialisierung fehlgeschlagen" |
| 1052 | `ERROR_ACTUATOR_NOT_FOUND` | `actuator_manager.cpp:340-346` - findActuator() returns null | Logged to command history | "Aktor nicht gefunden" |
| 1053 | `ERROR_ACTUATOR_CONFLICT` | `actuator_manager.cpp:205-211` - GPIO conflict with sensor | Logged with error_message | "GPIO-Konflikt mit Sensor" |

#### B. GPIO Error Codes (1001-1006)

| Code | Konstante | ESP32 Trigger | Server-Handling | Frontend-Message |
|------|-----------|---------------|-----------------|------------------|
| 1001 | `ERROR_GPIO_RESERVED` | `gpio_manager.cpp` - System-reserved pin | Rejected with error | "GPIO ist vom System reserviert" |
| 1002 | `ERROR_GPIO_CONFLICT` | `gpio_manager.cpp` - Pin already in use | Rejected with error | "GPIO wird bereits verwendet" |
| 1003 | `ERROR_GPIO_INIT_FAILED` | `gpio_manager.cpp` - Hardware init failed | Logged as error | "GPIO-Initialisierung fehlgeschlagen" |

#### C. PWM Error Codes (1030-1032)

| Code | Konstante | ESP32 Trigger | Server-Handling | Frontend-Message |
|------|-----------|---------------|-----------------|------------------|
| 1030 | `ERROR_PWM_INIT_FAILED` | `pwm_actuator.cpp` - LEDC init failed | Logged as error | "PWM-Controller konnte nicht initialisiert werden" |
| 1031 | `ERROR_PWM_CHANNEL_FULL` | `pwm_actuator.cpp` - All 16 channels used | Rejected with error | "Alle PWM-Kanäle belegt (max. 16)" |
| 1032 | `ERROR_PWM_SET_FAILED` | `pwm_actuator.cpp` - Duty cycle set failed | Logged as error | "PWM-Wert konnte nicht gesetzt werden" |

#### D. Application Error Codes (4020-4022)

| Code | Konstante | ESP32 Trigger | Server-Handling | Frontend-Message |
|------|-----------|---------------|-----------------|------------------|
| 4020 | `ERROR_COMMAND_INVALID` | `actuator_manager.cpp:563-565` - Unknown command | Response: success=false | "Unbekannter Befehl" |
| 4021 | `ERROR_COMMAND_PARSE_FAILED` | JSON parsing failed | Response: success=false | "Befehl konnte nicht verarbeitet werden" |
| 4022 | `ERROR_COMMAND_EXEC_FAILED` | `actuator_manager.cpp:567-569` - Execution failed | Response: success=false | "Befehlsausführung fehlgeschlagen" |

---

### 12.2 ESP32 Alert Types (Verifiziert aus actuator_manager.cpp)

**Quelle:** [actuator_manager.cpp:824-843](El%20Trabajante/src/services/actuator/actuator_manager.cpp#L824-L843)

| Alert Type | Severity | ESP32 Trigger | MQTT Topic | Server Event | Frontend State Update |
|------------|----------|---------------|------------|--------------|----------------------|
| `emergency_stop` | critical | `emergencyStopAll()` / `emergencyStopActuator()` | `.../actuator/{gpio}/alert` | `actuator_alert` | `emergency_stopped=true, state=false` |
| `runtime_protection` | warning | `processActuatorLoops()` timeout detection (Line 495-510) | `.../actuator/{gpio}/alert` | `actuator_alert` | `emergency_stopped=true, state=false` |
| `safety_violation` | critical | (Server-side generated) | `.../actuator/{gpio}/alert` | `actuator_alert` | `emergency_stopped=true, state=false` |
| `hardware_error` | error | (Driver-specific failures) | `.../actuator/{gpio}/alert` | `actuator_alert` | `state=false` |

**Alert Payload Struktur (ESP32):**
```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "ts": 1733000000,
  "gpio": 25,
  "alert_type": "emergency_stop",
  "message": "Actuator stopped"
}
```

---

### 12.3 Server Error Handling

**Quellen:**
- [actuator_response_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py)
- [actuator_alert_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py)

#### A. MQTT → WebSocket Event Mapping

| MQTT Topic | Handler | WebSocket Event | Payload Transformation |
|------------|---------|-----------------|------------------------|
| `.../actuator/{gpio}/response` | `ActuatorResponseHandler` | `actuator_response` | Direct pass-through + timestamp |
| `.../actuator/{gpio}/alert` | `ActuatorAlertHandler` | `actuator_alert` | Adds `severity` from mapping |
| `.../actuator/{gpio}/status` | `ActuatorHandler` | `actuator_status` | Direct pass-through |

#### B. Alert Severity Mapping (Server-defined)

**Quelle:** [actuator_alert_handler.py:44-49](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_alert_handler.py#L44-L49)

```python
ALERT_SEVERITY = {
    "emergency_stop": "critical",
    "runtime_protection": "warning",
    "safety_violation": "critical",
    "hardware_error": "error",
}
```

#### C. WebSocket Broadcast Payloads

**actuator_response (Line 141-149):**
```python
await ws_manager.broadcast("actuator_response", {
    "esp_id": esp_id_str,
    "gpio": gpio,
    "command": command,
    "value": value,
    "success": success,
    "message": message,
    "timestamp": payload.get("ts", 0)
})
```

**actuator_alert (Line 177-185):**
```python
await ws_manager.broadcast("actuator_alert", {
    "esp_id": esp_id_str,
    "gpio": gpio,
    "alert_type": alert_type,
    "severity": severity,
    "message": message,
    "zone_id": zone_id,
    "timestamp": payload.get("ts", 0)
})
```

---

### 12.4 Frontend Error Display

**Quelle:** [esp.ts:1064-1095](El%20Frontend/src/stores/esp.ts#L1064-L1095)

#### A. Existierende Handler

| Handler | Status | State Updates |
|---------|--------|---------------|
| `handleActuatorStatus()` | ✅ Existiert | Updates `state`, `pwm_value` |
| `handleActuatorAlert()` | ✅ Existiert | Sets `emergency_stopped=true`, `state=false` |
| `handleActuatorResponse()` | ❌ **FEHLT** | Should show Toast, update state |

#### B. handleActuatorAlert Implementation (Zeile 1064-1095)

```typescript
function handleActuatorAlert(message: { data: Record<string, unknown> }): void {
  const data = message.data
  const espId = data.esp_id as string || data.device_id as string
  const gpio = data.gpio as number
  const alertType = data.alert_type as string

  // ... validation ...

  // Emergency alerts set emergency_stopped flag
  if (alertType === 'emergency_stop' || alertType === 'runtime_protection' || alertType === 'safety_violation') {
    actuator.emergency_stopped = true
    actuator.state = false
  }

  console.info(`[ESP Store] Actuator alert: ${espId} GPIO ${gpio} - ${alertType}`)
}
```

**FEHLEND:**
- ❌ Toast-Notification für User
- ❌ Alert-Banner in UI
- ❌ handleActuatorResponse() Handler

---

### 12.5 ACTUATOR_ERROR_MAP (Vollständig)

```typescript
// types/index.ts oder utils/errorCodes.ts

/**
 * Vollständige Error-Code-Map für Actuator-System
 *
 * Quelle: ESP32 error_codes.h + Server API + Safety Service
 */
export const ACTUATOR_ERROR_MAP: Record<number, {
  code: number
  key: string
  source: 'esp32' | 'server' | 'safety'
  severity: 'error' | 'warning' | 'info'
  message: string
  userMessage: string
  recovery?: string
}> = {
  // ══════════════════════════════════════════════════════════════
  // ESP32 ACTUATOR ERRORS (1050-1053)
  // ══════════════════════════════════════════════════════════════

  1050: {
    code: 1050,
    key: 'ACTUATOR_SET_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'Failed to set actuator state',
    userMessage: 'Aktor-Status konnte nicht gesetzt werden',
    recovery: 'ESP32 neustarten oder GPIO prüfen'
  },

  1051: {
    code: 1051,
    key: 'ACTUATOR_INIT_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'Failed to initialize actuator',
    userMessage: 'Aktor-Initialisierung fehlgeschlagen',
    recovery: 'GPIO-Konfiguration prüfen'
  },

  1052: {
    code: 1052,
    key: 'ACTUATOR_NOT_FOUND',
    source: 'esp32',
    severity: 'error',
    message: 'Actuator not configured',
    userMessage: 'Aktor nicht gefunden',
    recovery: 'Aktor neu konfigurieren'
  },

  1053: {
    code: 1053,
    key: 'ACTUATOR_CONFLICT',
    source: 'esp32',
    severity: 'error',
    message: 'GPIO conflict with sensor',
    userMessage: 'GPIO-Konflikt mit einem Sensor',
    recovery: 'Anderen GPIO wählen'
  },

  // ══════════════════════════════════════════════════════════════
  // GPIO ERRORS (1001-1006)
  // ══════════════════════════════════════════════════════════════

  1001: {
    code: 1001,
    key: 'GPIO_RESERVED',
    source: 'esp32',
    severity: 'error',
    message: 'GPIO reserved by system',
    userMessage: 'GPIO ist vom System reserviert',
    recovery: 'Anderen GPIO wählen (siehe GPIO-Belegung)'
  },

  1002: {
    code: 1002,
    key: 'GPIO_CONFLICT',
    source: 'esp32',
    severity: 'error',
    message: 'GPIO already in use',
    userMessage: 'GPIO wird bereits verwendet',
    recovery: 'Anderen GPIO wählen'
  },

  1003: {
    code: 1003,
    key: 'GPIO_INIT_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'GPIO initialization failed',
    userMessage: 'GPIO-Initialisierung fehlgeschlagen',
    recovery: 'ESP32 neustarten'
  },

  // ══════════════════════════════════════════════════════════════
  // PWM ERRORS (1030-1032)
  // ══════════════════════════════════════════════════════════════

  1030: {
    code: 1030,
    key: 'PWM_INIT_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'PWM controller initialization failed',
    userMessage: 'PWM-Controller konnte nicht initialisiert werden',
    recovery: 'ESP32 neustarten'
  },

  1031: {
    code: 1031,
    key: 'PWM_CHANNEL_FULL',
    source: 'esp32',
    severity: 'error',
    message: 'All PWM channels in use',
    userMessage: 'Alle PWM-Kanäle belegt (max. 16)',
    recovery: 'Anderen PWM-Aktor entfernen'
  },

  1032: {
    code: 1032,
    key: 'PWM_SET_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'Failed to set PWM value',
    userMessage: 'PWM-Wert konnte nicht gesetzt werden',
    recovery: 'GPIO-Konfiguration prüfen'
  },

  // ══════════════════════════════════════════════════════════════
  // COMMAND ERRORS (4020-4022)
  // ══════════════════════════════════════════════════════════════

  4020: {
    code: 4020,
    key: 'COMMAND_INVALID',
    source: 'esp32',
    severity: 'warning',
    message: 'Invalid command',
    userMessage: 'Unbekannter Befehl',
    recovery: 'Gültige Befehle: ON, OFF, PWM, TOGGLE'
  },

  4021: {
    code: 4021,
    key: 'COMMAND_PARSE_FAILED',
    source: 'esp32',
    severity: 'warning',
    message: 'Command parse failed',
    userMessage: 'Befehl konnte nicht verarbeitet werden',
    recovery: 'Befehlsformat prüfen'
  },

  4022: {
    code: 4022,
    key: 'COMMAND_EXEC_FAILED',
    source: 'esp32',
    severity: 'error',
    message: 'Command execution failed',
    userMessage: 'Befehlsausführung fehlgeschlagen',
    recovery: 'Aktor-Status prüfen'
  },
}

/**
 * Get user-friendly error message
 */
export function getErrorMessage(code: number): string {
  return ACTUATOR_ERROR_MAP[code]?.userMessage || `Unbekannter Fehler (${code})`
}

/**
 * Get error recovery suggestion
 */
export function getErrorRecovery(code: number): string | undefined {
  return ACTUATOR_ERROR_MAP[code]?.recovery
}

/**
 * Get error severity for toast styling
 */
export function getErrorSeverity(code: number): 'error' | 'warning' | 'info' {
  return ACTUATOR_ERROR_MAP[code]?.severity || 'error'
}
```

---

### 12.6 ACTUATOR_ALERT_MAP (Vollständig)

```typescript
/**
 * Alert Types vom ESP32/Server
 *
 * Quelle: actuator_alert_handler.py ALERT_SEVERITY mapping
 */
export const ACTUATOR_ALERT_MAP: Record<string, {
  type: string
  severity: 'critical' | 'error' | 'warning' | 'info'
  icon: string
  message: string
  autoDismiss: boolean
  dismissAfterMs?: number
  stateUpdate?: {
    emergency_stopped?: boolean
    state?: boolean
    pwm_value?: number
  }
}> = {
  'emergency_stop': {
    type: 'emergency_stop',
    severity: 'critical',
    icon: 'AlertOctagon',
    message: 'NOTFALL-STOPP aktiviert',
    autoDismiss: false,
    stateUpdate: { emergency_stopped: true, state: false, pwm_value: 0 }
  },

  'runtime_protection': {
    type: 'runtime_protection',
    severity: 'warning',
    icon: 'Clock',
    message: 'Max. Laufzeit erreicht - automatisch abgeschaltet',
    autoDismiss: true,
    dismissAfterMs: 10000,
    stateUpdate: { emergency_stopped: true, state: false, pwm_value: 0 }
  },

  'safety_violation': {
    type: 'safety_violation',
    severity: 'critical',
    icon: 'ShieldAlert',
    message: 'Sicherheitsverletzung - Aktor gestoppt',
    autoDismiss: false,
    stateUpdate: { emergency_stopped: true, state: false, pwm_value: 0 }
  },

  'hardware_error': {
    type: 'hardware_error',
    severity: 'error',
    icon: 'XCircle',
    message: 'Hardware-Fehler erkannt',
    autoDismiss: false,
    stateUpdate: { state: false, pwm_value: 0 }
  },

  'cooldown_active': {
    type: 'cooldown_active',
    severity: 'info',
    icon: 'Timer',
    message: 'Abkühlzeit aktiv - bitte warten',
    autoDismiss: true,
    dismissAfterMs: 5000
  },

  'activation_limit': {
    type: 'activation_limit',
    severity: 'warning',
    icon: 'AlertTriangle',
    message: 'Max. Aktivierungen pro Stunde erreicht',
    autoDismiss: true,
    dismissAfterMs: 8000
  },
}

/**
 * Get alert config by type
 */
export function getAlertConfig(alertType: string) {
  return ACTUATOR_ALERT_MAP[alertType] || {
    type: alertType,
    severity: 'warning',
    icon: 'AlertCircle',
    message: `Alert: ${alertType}`,
    autoDismiss: true,
    dismissAfterMs: 6000
  }
}
```

---

### 12.7 Implementierungs-Checkliste (Error/Log)

#### Types & Constants
- [ ] `ACTUATOR_ERROR_MAP` in `types/index.ts` oder `utils/errorCodes.ts`
- [ ] `ACTUATOR_ALERT_MAP` in `types/index.ts` oder `utils/errorCodes.ts`
- [ ] `getErrorMessage()` Helper
- [ ] `getErrorRecovery()` Helper
- [ ] `getErrorSeverity()` Helper
- [ ] `getAlertConfig()` Helper

#### WebSocket Handler
- [ ] `handleActuatorResponse()` implementieren in `esp.ts`
- [ ] Handler in `wsUnsubscribers` registrieren
- [ ] WebSocket Filter um `'actuator_response'` erweitern

#### Toast Integration
- [ ] Toast bei Command-Success (grün, 3s)
- [ ] Toast bei Command-Failure (rot, 6s) mit Recovery-Hinweis
- [ ] Toast bei Alert (nach Severity: critical=rot/∞, warning=orange/5s, info=blau/3s)

#### Alert Banner
- [ ] Emergency-Stop Banner in ActuatorSatellite.vue
- [ ] Runtime-Protection Warning anzeigen
- [ ] Banner dismissable nach Severity

---

## 13. Datenfluss-Diagramme

### 13.1 Error Flow (ESP32 → Frontend)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ERROR FLOW (Command Failure)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ESP32: controlActuator() failed                                            │
│      ↓                                                                      │
│  errorTracker.trackError(ERROR_ACTUATOR_SET_FAILED, ...)                   │
│      ↓                                                                      │
│  publishActuatorResponse(command, success=false, "Command failed")         │
│      ↓                                                                      │
│  MQTT Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/response              │
│      ↓                                                                      │
│  Server: ActuatorResponseHandler.handle_actuator_response()                │
│      ↓                                                                      │
│  Log to command history (success=false, error_message=message)             │
│      ↓                                                                      │
│  WebSocket: broadcast("actuator_response", {success: false, ...})          │
│      ↓                                                                      │
│  Frontend: handleActuatorResponse()                                         │
│      ↓                                                                      │
│  Toast: "Befehl fehlgeschlagen: {message}" (error, 6s)                     │
│      ↓                                                                      │
│  State: Rollback optimistic update, fetchDevice(esp_id)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Alert Flow (ESP32 → Frontend)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ALERT FLOW (Emergency Stop)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ESP32: processActuatorLoops() → runtime > max_runtime_ms                  │
│      ↓                                                                      │
│  emergencyStopActuator(gpio)                                               │
│      ↓                                                                      │
│  publishActuatorAlert(gpio, "runtime_protection", "Max runtime exceeded")  │
│      ↓                                                                      │
│  MQTT Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/alert                 │
│      ↓                                                                      │
│  Server: ActuatorAlertHandler.handle_actuator_alert()                      │
│      ↓                                                                      │
│  Determine severity: ALERT_SEVERITY["runtime_protection"] = "warning"      │
│      ↓                                                                      │
│  Log to command history (command_type="ALERT_RUNTIME_PROTECTION")          │
│      ↓                                                                      │
│  Update actuator state: state="off", error_message=message                 │
│      ↓                                                                      │
│  WebSocket: broadcast("actuator_alert", {severity: "warning", ...})        │
│      ↓                                                                      │
│  Frontend: handleActuatorAlert()                                            │
│      ↓                                                                      │
│  State: actuator.emergency_stopped = true, actuator.state = false          │
│      ↓                                                                      │
│  Toast: "Max. Laufzeit erreicht - automatisch abgeschaltet" (warning, 10s) │
│      ↓                                                                      │
│  Banner: Orange warning banner (dismissable after 10s)                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.3 Command Success Flow (Vollständig)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       COMMAND SUCCESS FLOW (ON Command)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User: Click "EIN" Button                                                   │
│      ↓                                                                      │
│  ActuatorControl.vue: sendCommand('ON')                                    │
│      ↓ isLoading = true                                                    │
│  actuatorsApi.sendCommand(espId, gpio, { command: 'ON' })                  │
│      ↓ POST /v1/actuators/{esp_id}/{gpio}/command                          │
│  Server: SafetyService.validate_actuator_command()                         │
│      ↓ ✅ Validation passed                                                │
│  Server: MQTT Publish → kaiser/god/esp/{esp_id}/actuator/{gpio}/command    │
│      ↓                                                                      │
│  ESP32: handleActuatorCommand()                                            │
│      ↓                                                                      │
│  controlActuatorBinary(gpio, true) → success=true                          │
│      ↓                                                                      │
│  publishActuatorResponse(command, success=true, "Command executed")        │
│      ↓                                                                      │
│  MQTT Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/response              │
│      ↓                                                                      │
│  Server: ActuatorResponseHandler → WebSocket broadcast                     │
│      ↓                                                                      │
│  Frontend: handleActuatorResponse()                                         │
│      ↓                                                                      │
│  State: actuator.state = true, actuator.last_command = now()               │
│      ↓ isLoading = false                                                   │
│  Toast: "Pumpe 1: ON ausgeführt" (success, 3s)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 14. Test-Szenarien

### 14.1 Error-Handling Tests

| Szenario | Trigger | Erwartetes Verhalten | Verifizierung |
|----------|---------|----------------------|---------------|
| ESP offline | Command zu offline ESP | Toast "ESP nicht erreichbar" | Server-Log prüfen |
| GPIO conflict | Actuator auf belegtem GPIO | Toast "GPIO-Konflikt" + Recovery | Error 1002 in Log |
| PWM channels full | 17. PWM-Aktor hinzufügen | Toast "Alle Kanäle belegt" | Error 1031 in Response |
| Unknown command | Manuell ungültigen Command senden | Toast "Unbekannter Befehl" | Error 4020 in Response |
| Actuator not found | Command zu nicht-konfiguriertem GPIO | Toast "Aktor nicht gefunden" | Error 1052 in Response |

### 14.2 Alert-Handling Tests

| Szenario | Trigger | Erwartetes Verhalten | Verifizierung |
|----------|---------|----------------------|---------------|
| Emergency Stop | `POST /emergency_stop` | Banner + Toast + State Update | `emergency_stopped=true` |
| Runtime exceeded | Pumpe läuft > `max_runtime_ms` | Warning Toast + Auto-Off | Aktor ist aus |
| Manual emergency | UI Emergency-Stop Button | Banner (critical, nicht dismissable) | State + DB-Log |
| Clear emergency | Emergency aufheben | Banner verschwindet | `emergency_stopped=false` |

### 14.3 Safety-Rejection Tests

| Szenario | Trigger | Erwartetes Verhalten | Verifizierung |
|----------|---------|----------------------|---------------|
| Command während Emergency | ON während emergency_stopped | Toast "Emergency Stop aktiv" | Command nicht ausgeführt |
| Value out of range | PWM value > 1.0 | Server clampt zu 1.0, Warning | Clamped value in Log |
| Disabled actuator | Command zu deaktiviertem Aktor | Toast "Aktor deaktiviert" | Command rejected |
| Cooldown active | Schnelles ON/OFF/ON | Toast "Abkühlzeit aktiv" | Timing prüfen |

### 14.4 Integration Tests (End-to-End)

- [ ] **Happy Path:** User → Click ON → ESP32 führt aus → Response → Toast "Erfolg"
- [ ] **Failure Path:** User → Click ON → ESP32 Fehler → Response (fail) → Toast "Fehler" + Recovery
- [ ] **Alert Path:** ESP32 timeout → Alert → Server broadcast → Frontend Banner + Toast
- [ ] **Recovery Path:** Emergency Stop → Clear → Actuator wieder steuerbar

---

**Plan Version:** 5.0
**Letzte Aktualisierung:** 2026-01-09
**Verifiziert durch:** Codebase-Analyse (Claude Opus 4.5)

---

### Änderungshistorie

| Version | Datum | Änderungen |
|---------|-------|------------|
| 4.0 | 2026-01-09 | Initial V4 mit Hardware/Instance Config |
| 5.0 | 2026-01-09 | + Section 11 (Sicherheits-Warnungen), + Section 12 (Error/Log-System), + Section 13 (Datenfluss), + Section 14 (Test-Szenarien) |
