# ⚙️ ActuatorsView - Vollständige UI-Dokumentation

## 🎯 Übersicht

Die **ActuatorsView** (`/actuators`) ist die zentrale Steuerungsoberfläche für alle Aktoren im System. Sie ermöglicht es Operatoren, Aktoren aus allen ESPs gleichzeitig zu überwachen und zu steuern, mit Fokus auf Sicherheit, Live-Status-Anzeigen und Bulk-Operationen.

### **Route:** `/actuators`
### **Zweck:** Alle Aktoren aus allen ESPs zentral steuern
### **Kritische Funktion:** Emergency-Stop für alle Aktoren systemweit

---

## 🔍 Layout & Design

### **Header-Bereich**
- **Emergency-Stop Button**: Groß, rot, mit AlertTriangle-Icon
- **Filter-Button**: Zeigt aktive Filter mit Badge-Count
- **Responsive Design**: Flexibles Layout für Mobile/Desktop

### **Status-Indikatoren**
- **🟢 ON (grün)**: Aktive Aktoren mit `state: true`
- **🔴 OFF (rot)**: Inaktive Aktoren mit `state: false`
- **🟡 PWM (gelb)**: Aktoren mit PWM-Werten zwischen 0.0-1.0
- **🔴 E-STOP**: Emergency-gestoppte Aktoren (höchste Priorität)

### **Karten/Grid-Layout**
```text
┌─────────────────────────────────────────────────────────┐
│ [Emergency Stop] [Filters: 2] [Showing 12 of 15]       │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ │ ESP_01          │ │ ESP_02          │ │ ESP_03          │
│ │ Relay GPIO 12   │ │ LED GPIO 13     │ │ Motor GPIO 14   │
│ │ [ON/OFF Toggle] │ │ PWM: [█░░░░░]   │ │ [OFF] Timer 5m  │
│ │ ⚡ ACTIVE       │ │ 🔆 0.7          │ │ ⏰ Scheduled     │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘
└─────────────────────────────────────────────────────────┘
```

### **Quick Stats**
- **Active (ON)**: Anzahl aktiver Aktoren (grüne Badge)
- **Inactive (OFF)**: Anzahl inaktiver Aktoren (graue Badge)
- **Emergency Stop**: Anzahl emergency-gestoppter Aktoren (rote Badge)

---

## 🎮 Interaktive Elemente

### **Toggle-Buttons**
```vue
<button
  class="btn-secondary btn-sm flex-shrink-0 touch-target"
  :disabled="actuator.emergency_stopped"
  @click="toggleActuator(actuator.esp_id, actuator.gpio, actuator.state)"
>
  {{ actuator.state ? 'Turn OFF' : 'Turn ON' }}
</button>
```

**Funktionen:**
- **Sofortige Schaltung**: ON/OFF mit optimistischen Updates
- **WebSocket-Confirmation**: Live-State-Update via `actuator_status`
- **Disabled bei E-Stop**: Button deaktiviert während Emergency-Stop
- **Touch-optimized**: Große Touch-Targets für mobile Geräte

### **Emergency-Stop**
```vue
<button class="btn-danger flex items-center gap-2" @click="emergencyStopAll">
  <AlertTriangle class="w-4 h-4" />
  <span class="hidden sm:inline">Emergency Stop All</span>
  <span class="sm:hidden">E-Stop All</span>
</button>
```

**Sicherheitsfeatures:**
- **Bestätigungsdialog**: `confirm('Trigger emergency stop on ALL mock ESPs?')`
- **Systemweiter Stop**: Alle ESPs werden gleichzeitig gestoppt
- **Audit-Logging**: Grund für Emergency-Stop wird gespeichert

### **Filter-System**
- **ESP ID Filter**: Text-Suche mit Datalist-Autocomplete
- **Actuator Type Filter**: Mehrfachauswahl mit Toggle-Buttons
- **State Filter**: ON/OFF/Emergency-Stop Filter
- **Responsive**: Collapsible Filter-Panel mit Slide-Animation

---

## 🔌 Server-Kommunikation

### **WebSocket Integration**
```typescript
// Subscription für Live-Updates
subscribe(
  {
    types: ['actuator_status', 'esp_health'],
  },
  (message: WebSocketMessage) => {
    handleWebSocketMessage(message)
  }
)
```

**Message Types:**
- **`actuator_status`**: Live-State-Updates für Aktoren
- **`esp_health`**: ESP-Verbindungsstatus für UI-Feedback

### **REST API Endpunkte**

#### **Einzel-Aktor Steuerung**
```typescript
// Mock-ESP Debug API (für Testing)
POST /debug/mock-esp/{espId}/actuators/{gpio}
{
  "state": boolean,
  "pwm_value": number,  // 0.0-1.0
  "publish": boolean    // MQTT-Publish triggern
}
```

#### **Emergency Stop**
```typescript
POST /api/v1/actuators/emergency_stop
{
  "esp_id": "optional",    // null = alle ESPs
  "gpio": "optional",      // null = alle Aktoren
  "reason": "string"       // Audit-Log Grund
}
```

#### **Production API** (Real ESPs)
```typescript
POST /api/v1/actuators/{esp_id}/{gpio}/command
{
  "command": "ON|OFF|PWM|TOGGLE",
  "value": 0.0-1.0,
  "duration": 0              // Sekunden (0 = unbegrenzt)
}
```

### **Optimistische Updates**
```typescript
async function toggleActuator(espId: string, gpio: number, currentState: boolean) {
  // 1. Sofortige UI-Änderung (optimistisch)
  mockEspStore.updateActuatorFromEvent(espId, gpio, {
    state: !currentState,
    last_command: new Date().toISOString(),
  })

  // 2. API-Call im Hintergrund
  try {
    await mockEspStore.setActuatorState(espId, gpio, !currentState)
  } catch (error) {
    // 3. Rollback bei Fehler
    mockEspStore.updateActuatorFromEvent(espId, gpio, {
      state: currentState,  // Ursprünglicher State zurück
    })
  }
}
```

---

## 🔄 User-Flows & Funktionen

### **Schnellzugriff-Workflow**
1. **Übersicht laden**: Alle Aktoren aus allen ESPs anzeigen
2. **Status scannen**: Visuelle Indikatoren für ON/OFF/E-Stop
3. **Direkte Steuerung**: Toggle-Button klicken für sofortige Schaltung
4. **Live-Feedback**: WebSocket-Updates bestätigen erfolgreiche Ausführung

### **Filter-Workflow**
1. **Filter aktivieren**: ESP-ID, Type oder State filtern
2. **Ergebnisse anzeigen**: "Showing X of Y" Counter
3. **Bulk-Operationen**: Gefilterte Aktoren gemeinsam steuern
4. **Filter zurücksetzen**: Alle Filter mit einem Klick löschen

### **Emergency-Stop Workflow**
1. **Kritischer Zustand**: Emergency-Stop Button klicken
2. **Bestätigung**: Sicherheitsdialog mit Warnung
3. **Systemweiter Stop**: Alle Aktoren werden sofort gestoppt
4. **Audit-Trail**: Emergency-Stop wird geloggt mit User und Grund

### **Sicherheitsfeatures**
- **Bestätigungsdialoge**: Für alle kritischen Aktionen
- **Rollback-Mechanismus**: UI-Zustand wird bei API-Fehlern zurückgesetzt
- **Emergency-Stop Priority**: Höchste Priorität, kann normale Steuerung überschreiben
- **Audit-Logging**: Alle Aktionen werden mit User und Timestamp geloggt

---

## 🔧 Technische Implementierung

### **Store Management**
```typescript
// Pinia Store für Mock-ESP Management
export const useMockEspStore = defineStore('mockEsp', () => {
  const mockEsps = ref<MockESP[]>([])

  // WebSocket Event Handler
  function updateActuatorFromEvent(
    espId: string,
    gpio: number,
    updates: Partial<MockESP['actuators'][0]>
  ) {
    const esp = mockEsps.value.find(e => e.esp_id === espId)
    if (!esp) return

    const actuatorIndex = esp.actuators.findIndex(a => a.gpio === gpio)
    if (actuatorIndex !== -1) {
      esp.actuators[actuatorIndex] = {
        ...esp.actuators[actuatorIndex],
        ...updates,
      }
    }
  }

  return {
    mockEsps,
    updateActuatorFromEvent,
    setActuatorState,
    emergencyStop,
  }
})
```

### **WebSocket Subscription**
```typescript
// Live-Updates für alle Aktoren
const { subscribe, unsubscribe } = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
})

onMounted(async () => {
  // Initial Load
  await mockEspStore.fetchAll()

  // WebSocket für Live-Updates
  subscribe(
    { types: ['actuator_status', 'esp_health'] },
    handleWebSocketMessage
  )
})
```

### **Computed Properties für Filter**
```typescript
// Gefilterte Aktoren basierend auf aktiven Filtern
const filteredActuators = computed(() => {
  return allActuators.value.filter(actuator => {
    // ESP ID Filter (Substring-Match)
    if (filterEspId.value &&
        !actuator.esp_id.toLowerCase().includes(filterEspId.value.toLowerCase())) {
      return false
    }

    // Actuator Type Filter
    if (filterActuatorType.value.length > 0 &&
        !filterActuatorType.value.includes(actuator.actuator_type)) {
      return false
    }

    // State Filter (ON/OFF/Emergency)
    if (filterState.value.length > 0) {
      const matchesOn = filterState.value.includes('on') &&
                       actuator.state && !actuator.emergency_stopped
      const matchesOff = filterState.value.includes('off') &&
                        !actuator.state && !actuator.emergency_stopped
      const matchesEmergency = filterState.value.includes('emergency') &&
                              actuator.emergency_stopped

      if (!matchesOn && !matchesOff && !matchesEmergency) {
        return false
      }
    }

    return true
  })
})
```

### **Data Structures**
```typescript
interface MockActuator {
  gpio: number
  actuator_type: string
  name: string | null
  state: boolean              // true = ON, false = OFF
  pwm_value: number          // 0.0-1.0 für PWM-Kontrolle
  emergency_stopped: boolean // Emergency-Stop Status
  last_command: string | null // ISO Timestamp
}

interface ActuatorCommand {
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE'
  value: number    // 0.0-1.0
  duration: number // Sekunden (0 = unbegrenzt)
}
```

---

## 🎨 Design-Spezifikationen

### **Status-Farben & Icons**
- **🟢 Active (ON)**: `text-green-400`, `bg-green-500/20`, `border-green-500/50`
- **🔴 Inactive (OFF)**: `text-dark-400`, `bg-dark-700`, `border-dark-600`
- **🔴 Emergency Stop**: `text-red-400`, `bg-red-500/20`, `border-red-500/30`
- **⚡ Active Icon**: Power-Icon für aktive Aktoren
- **⏰ Timer Icon**: Uhr-Symbol für geplante Aktionen

### **Emergency-Button Styling**
```css
.btn-danger {
  @apply bg-red-600 hover:bg-red-700 text-white border-red-600;
}

.btn-danger:hover {
  @apply bg-red-700 shadow-lg;
}
```

### **Responsive Breakpoints**
- **Mobile (< 640px)**: Einzelne Spalte, kompakte Buttons
- **Tablet (640px - 1024px)**: Zwei Spalten, mittlere Buttons
- **Desktop (> 1024px)**: Drei Spalten, volle Buttons

### **Animations & Transitions**
- **Filter Panel**: Slide-Animation beim Ein-/Ausblenden
- **Loading States**: Spinner während API-Calls
- **Hover Effects**: Subtile Border-Highlights bei Hover

---

## 📱 Mobile-Optimierung

### **Touch-Targets**
- **Minimale Größe**: 44x44px für alle interaktiven Elemente
- **Touch-Classes**: `touch-target` für bessere Mobile-Erfahrung
- **Swipe-Gesten**: Navigation zwischen verschiedenen Views

### **Responsive Layout**
```vue
<!-- Responsive Grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
  <!-- Actuator Cards -->
</div>

<!-- Responsive Header -->
<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
  <!-- Header Content -->
</div>
```

---

## 🔒 Sicherheit & Validierung

### **API Validation**
- **Safety Service**: Alle Commands werden vor Ausführung validiert
- **Value Ranges**: PWM-Werte werden auf 0.0-1.0 begrenzt
- **Emergency Priority**: Emergency-Stop überschreibt alle anderen Commands
- **Audit Logging**: Alle Aktionen werden mit User-Kontext geloggt

### **Error Handling**
```typescript
try {
  await mockEspStore.setActuatorState(espId, gpio, newState)
} catch (error) {
  // Rollback optimistischer Update
  mockEspStore.updateActuatorFromEvent(espId, gpio, {
    state: currentState,
  })

  // User Feedback
  showToast('Failed to toggle actuator', 'error')
}
```

### **Offline-Handling**
- **Connection Status**: ESP-Verbindungsstatus wird angezeigt
- **Queued Commands**: Commands werden bei Offline-ESPs queued
- **Retry Logic**: Automatische Wiederholung bei temporären Fehlern

---

## 🧪 Testing & Debugging

### **Mock-ESP Integration**
```typescript
// Mock-ESP Store für Entwicklung/Testing
const mockEspStore = useMockEspStore()

// Alle ESPs mit Mock-Aktoren laden
await mockEspStore.fetchAll()

// Einzelnen Aktor steuern
await mockEspStore.setActuatorState('ESP_01', 12, true)
```

### **WebSocket Testing**
```typescript
// WebSocket Events simulieren für Testing
mockEspStore.updateActuatorFromEvent('ESP_01', 12, {
  state: true,
  pwm_value: 0.8,
  last_command: new Date().toISOString(),
})
```

---

## 🚀 Performance-Optimierungen

### **Lazy Loading**
- **Virtuelle Scrolling**: Für große Anzahl von Aktoren
- **Paged API**: Server-seitige Pagination für 1000+ Aktoren
- **Debounced Filters**: Filter-Änderungen werden debounced

### **WebSocket Optimization**
- **Selective Subscriptions**: Nur relevante Event-Types abonnieren
- **Batch Updates**: Mehrere Updates in einem Event bündeln
- **Connection Pooling**: Wiederverwendung von WebSocket-Verbindungen

---

## 📋 Implementierungs-Checkliste

### **✅ Abgeschlossen**
- [x] ActuatorsView Component mit vollem Layout
- [x] Filter-System (ESP-ID, Type, State)
- [x] Emergency-Stop Funktionalität
- [x] WebSocket Live-Updates
- [x] Optimistische Updates mit Rollback
- [x] Responsive Design
- [x] Touch-Optimierung
- [x] Error Handling & Safety Features

### **🔄 Integration Points**
- [x] Mock-ESP Store Integration
- [x] WebSocket Service Integration
- [x] Toast Notification System
- [x] Audit Logging Integration

### **🎯 Kritische Features**
- [x] **Emergency-Stop**: Systemweiter Stop aller Aktoren
- [x] **Live-Status**: WebSocket-Updates für alle Aktoren
- [x] **Safety Validation**: Server-seitige Command-Validierung
- [x] **Audit Trail**: Vollständige Logging aller Aktionen

---

**Diese Dokumentation ermöglicht es einem Entwickler, die komplette ActuatorsView von Grund auf neu zu implementieren, inklusive aller Sicherheitsfeatures, Live-Updates und User-Experience-Optimierungen.**
