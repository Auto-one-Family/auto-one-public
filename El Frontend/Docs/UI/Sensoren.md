# 📊 Sensoren - Vollständige UI-Dokumentation

## 🎯 SensorsView (`/sensors`) - Komplette UI-Dokumentation

Diese Dokumentation beschreibt die **SensorsView** Komponente (`/sensors`), die alle Sensoren aus allen ESP-Geräten in einer aggregierten Karten-Ansicht darstellt. Die Dokumentation ist so detailliert, dass ein Entwickler die komplette View basierend auf dieser Spezifikation nachbauen kann.

---

## 📋 **Sektion 1: Übersicht**

### **Route & Navigation**
- **Route**: `/sensors`
- **Zweck**: Zentralisierte Anzeige aller Sensoren aus allen ESP-Geräten in einer Grid-Ansicht
- **Live-Updates**: ✅ **Aktiviert** - Sensorwerte werden in Echtzeit über WebSocket aktualisiert
- **Navigation**: Erreichbar über Hauptmenü → "Sensors" oder direkt via URL
- **Authentifizierung**: Erfordert eingeloggten Benutzer

### **Datenquelle**
- **Primäre Daten**: Alle Mock-ESP Sensoren aggregiert aus `useMockEspStore`
- **Initial Load**: `mockEspStore.fetchAll()` beim Mount
- **Live-Updates**: WebSocket Messages vom Typ `sensor_data` und `esp_health`

---

## 📋 **Sektion 2: UI-Komponenten detailliert**

### **Layout-Struktur**
```
┌─────────────────────────────────────────────────────────┐
│ Header-Bereich mit Titel und Filter-Button             │
│ [Sensors] · Showing X of Y        [Filters ▼]          │
├─────────────────────────────────────────────────────────┤
│ Filter-Panel (ausklappbar, Slide-Transition)           │
│ ├ ESP-ID Search [___________] [×]                      │
│ ├ Sensor Type [DHT22] [LDR] [BME280] [DS18B20]         │
│ └ Quality [excellent] [good] [fair] [poor] [bad]       │
├─────────────────────────────────────────────────────────┤
│ Sensor-Karten Grid (Responsive)                        │
│ ┌─────────────────────────────────┐ ┌─────────────────────────────────┐ │
│ │ ESP_01 · GPIO 4                 │ │ ESP_02 · GPIO 5                 │ │
│ │ 🌡️ Temperature Sensor          │ │ 💡 Light Sensor                 │ │
│ │ ┌─────────────────────────────┐ │ │ ┌─────────────────────────────┐ │ │
│ │ │ 23.50°C                      │ │ │ │ 85.00%                      │ │ │
│ │ │ °C                           │ │ │ │ %                           │ │ │
│ │ └─────────────────────────────┘ │ │ └─────────────────────────────┘ │ │
│ │ 🟢 excellent                    │ │ 🟡 good                         │ │
│ └─────────────────────────────────┘ └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### **Header-Bereich (Zeilen 175-196)**
```vue
<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
  <div>
    <h1 class="text-xl md:text-2xl font-bold text-dark-100">Sensors</h1>
    <p class="text-dark-400 mt-1 text-sm md:text-base">
      All sensors across mock ESPs
      <span v-if="hasActiveFilters" class="text-blue-400">
        · Showing {{ filteredSensors.length }} of {{ allSensors.length }}
      </span>
    </p>
  </div>
  <button class="btn-secondary flex items-center gap-2 self-start sm:self-auto"
          @click="showFilters = !showFilters">
    <Filter class="w-4 h-4" />
    <span>Filters</span>
    <span v-if="hasActiveFilters" class="badge badge-info text-xs">
      {{ filterSensorType.length + filterQuality.length + (filterEspId ? 1 : 0) }}
    </span>
    <component :is="showFilters ? ChevronUp : ChevronDown" class="w-4 h-4" />
  </button>
</div>
```

**Header-Features:**
- **Titel**: "Sensors" (responsive Größe: `text-xl md:text-2xl`)
- **Beschreibung**: "All sensors across mock ESPs" + Filter-Status
- **Filter-Button**: `btn-secondary` mit Icon, Badge für aktive Filter-Anzahl
- **Responsive**: Stackt auf Mobile vertikal

### **Filter-Panel (Zeilen 199-275)**
```vue
<Transition name="slide">
  <div v-if="showFilters" class="card p-4">
    <div class="flex flex-col lg:flex-row gap-4">
      <!-- ESP ID Filter -->
      <div class="flex-1">
        <label class="label">ESP ID</label>
        <div class="relative">
          <input v-model="filterEspId" type="text" class="input pr-8"
                 placeholder="Search by ESP ID..." list="esp-ids" />
          <datalist id="esp-ids">
            <option v-for="id in availableEspIds" :key="id" :value="id" />
          </datalist>
          <button v-if="filterEspId" @click="filterEspId = ''">
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Sensor Type Filter -->
      <div class="flex-1">
        <label class="label">Sensor Type</label>
        <div class="flex flex-wrap gap-2">
          <button v-for="type in availableSensorTypes"
                  :class="filterSensorType.includes(type) ? 'active' : 'inactive'"
                  @click="toggleSensorType(type)">
            {{ type }}
          </button>
        </div>
      </div>

      <!-- Quality Filter -->
      <div class="flex-1">
        <label class="label">Quality</label>
        <div class="flex flex-wrap gap-2">
          <button v-for="quality in qualityLevels"
                  :class="filterQuality.includes(quality) ? 'active' : 'inactive'"
                  @click="toggleQuality(quality)">
            {{ quality }}
          </button>
        </div>
      </div>
    </div>

    <!-- Clear Filters -->
    <div v-if="hasActiveFilters" class="mt-4 pt-4 border-t border-dark-700">
      <button class="btn-ghost text-sm" @click="clearFilters">
        <X class="w-4 h-4 mr-1" /> Clear all filters
      </button>
    </div>
  </div>
</Transition>
```

**Filter-Features:**
- **ESP-ID Filter**: Text-Input mit Datalist für Autocomplete + Clear-Button
- **Sensor-Type Filter**: Toggle-Buttons für jeden verfügbaren Typ
- **Quality Filter**: Toggle-Buttons für alle Quality-Levels
- **Slide-Transition**: 200ms ease mit max-height Animation
- **Clear All**: Erscheint nur bei aktiven Filtern

### **Sensor-Karten Grid (Zeilen 305-337)**
```vue
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
  <div v-for="sensor in filteredSensors"
       :key="`${sensor.esp_id}-${sensor.gpio}`"
       :class="[
         'card hover:border-dark-600 transition-colors',
         updatedSensorKeys.has(`${sensor.esp_id}-${sensor.gpio}`) ? 'sensor-value--updated' : ''
       ]">

    <div class="card-header flex items-center gap-3">
      <div class="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center flex-shrink-0">
        <Gauge class="w-5 h-5 text-purple-400" />
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-medium text-dark-100 truncate">
          {{ sensor.name || `GPIO ${sensor.gpio}` }}
        </p>
        <p class="text-xs text-dark-400 truncate">
          {{ sensor.esp_id }} · {{ sensor.sensor_type }}
        </p>
      </div>
    </div>

    <div class="card-body">
      <div class="flex items-end justify-between gap-2">
        <div class="min-w-0">
          <p class="text-2xl md:text-3xl font-bold font-mono text-dark-100 truncate">
            {{ sensor.raw_value.toFixed(2) }}
          </p>
          <p class="text-sm text-dark-400">{{ sensor.unit }}</p>
        </div>
        <span :class="['badge flex-shrink-0', getQualityColor(sensor.quality)]">
          {{ sensor.quality }}
        </span>
      </div>
    </div>
  </div>
</div>
```

**Karten-Features:**
- **Grid-Layout**: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` (responsive)
- **Header**: Icon + Name/ESP-ID + Sensor-Type
- **Wert-Anzeige**: Große Zahl (2-3xl) + Einheit + Quality-Badge
- **Live-Update**: CSS-Animation bei WebSocket-Updates
- **Hover-Effect**: Border-Farbe ändert sich

---

## 📋 **Sektion 3: Interaktionen**

### **Filter-Interaktionen**
- **ESP-ID Search**: Substring-Match (case-insensitive)
- **Sensor-Type Toggle**: Mehrfachauswahl möglich, OR-Logik
- **Quality Toggle**: Mehrfachauswahl möglich, OR-Logik
- **Filter-Status**: Header zeigt "Showing X of Y" bei aktiven Filtern
- **Clear Filters**: Setzt alle Filter zurück, Panel bleibt offen

### **Live-Update Visual Feedback**
```css
.sensor-value--updated {
  animation: sensorUpdateHighlight 0.5s ease-out;
}

@keyframes sensorUpdateHighlight {
  0% {
    border-color: rgba(59, 130, 246, 0.5);
    background-color: rgba(59, 130, 246, 0.1);
  }
  100% {
    border-color: transparent;
    background-color: transparent;
  }
}
```

**Update-Mechanismus:**
- WebSocket empfängt `sensor_data` Message
- Sensor-Key (`${esp_id}-${gpio}`) wird zu `updatedSensorKeys` hinzugefügt
- CSS-Klasse `sensor-value--updated` wird angewendet
- Nach 500ms wird Key entfernt (Animation endet)

### **Responsive Behavior**
- **Mobile (< 640px)**: Single Column Grid, Header stackt vertikal
- **Tablet (640px - 1024px)**: 2 Column Grid
- **Desktop (> 1024px)**: 3 Column Grid, Filter-Panel horizontal

---

## 📋 **Sektion 4: Server-API Integration**

### **Store Integration**
```typescript
const mockEspStore = useMockEspStore()

// Reactive Daten
const allSensors = computed(() => {
  return mockEspStore.mockEsps.flatMap(esp =>
    esp.sensors.map(sensor => ({
      ...sensor,
      esp_id: esp.esp_id,
      esp_state: esp.system_state,
    }))
  )
})
```

### **WebSocket Integration**
```typescript
const { subscribe, unsubscribe } = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
})

// Subscription beim Mount
subscribe(
  {
    types: ['sensor_data', 'esp_health'],
  },
  (message: WebSocketMessage) => {
    handleWebSocketMessage(message)
  }
)
```

**WebSocket Message Handling:**
```typescript
function handleWebSocketMessage(message: WebSocketMessage) {
  const { type, data } = message

  if (type === 'sensor_data') {
    mockEspStore.updateSensorFromEvent(espId, gpio, {
      raw_value: data.value || data.raw_value || data.raw,
      quality: data.quality,
      unit: data.unit,
      last_read: new Date((data.timestamp as number) * 1000).toISOString(),
    })
  } else if (type === 'esp_health') {
    mockEspStore.updateEspFromEvent(espId, {
      connected: data.status === 'online' || data.status === 'connected',
    })
  }
}
```

### **API Endpoints**
- **Initial Load**: `debugApi.listMockEsps()` via `mockEspStore.fetchAll()`
- **WebSocket URL**: Automatisch über `useWebSocket` Composable
- **Keine direkten REST-API Calls** für Sensor-Daten (alles über WebSocket)

---

## 📋 **Sektion 5: Edge Cases & Error States**

### **Loading State (Zeilen 278-281)**
```vue
<div v-if="mockEspStore.isLoading" class="text-center py-12 text-dark-400">
  <div class="animate-spin w-8 h-8 border-2 border-dark-600 border-t-blue-500 rounded-full mx-auto mb-4" />
  Loading sensors...
</div>
```

### **Empty State - No Sensors (Zeilen 284-290)**
```vue
<div v-else-if="allSensors.length === 0" class="card p-8 md:p-12 text-center">
  <Thermometer class="w-12 h-12 text-dark-600 mx-auto mb-4" />
  <h3 class="text-lg font-medium text-dark-200 mb-2">No Sensors</h3>
  <p class="text-dark-400">
    Create a mock ESP and add sensors to see them here
  </p>
</div>
```

### **Empty State - No Filter Results (Zeilen 293-302)**
```vue
<div v-else-if="filteredSensors.length === 0 && hasActiveFilters" class="card p-8 md:p-12 text-center">
  <Filter class="w-12 h-12 text-dark-600 mx-auto mb-4" />
  <h3 class="text-lg font-medium text-dark-200 mb-2">No Matching Sensors</h3>
  <p class="text-dark-400 mb-4">
    No sensors match your current filters
  </p>
  <button class="btn-secondary" @click="clearFilters">
    Clear Filters
  </button>
</div>
```

### **Error Handling**
- **Verbindungsfehler**: Wird über `mockEspStore.error` behandelt
- **WebSocket-Fehler**: Automatische Reconnection über `useWebSocket`
- **Sensor-Update Fehler**: Silent fail (keine UI-Änderung bei fehlgeschlagenen Updates)

---

## 🎨 **Design-Spezifikationen**

### **Farben & Quality-Badges**
```typescript
function getQualityColor(quality: string): string {
  switch (quality) {
    case 'excellent':
    case 'good': return 'badge-success'    // 🟢 Grün
    case 'fair': return 'badge-info'       // 🔵 Blau
    case 'poor': return 'badge-warning'    // 🟡 Orange
    case 'bad':
    case 'stale': return 'badge-danger'    // 🔴 Rot
    default: return 'badge-gray'           // ⚪ Grau
  }
}
```

### **Icons & Visual Elements**
- **Sensor-Icon**: `Gauge` (von Lucide) in `w-5 h-5 text-purple-400`
- **Filter-Icon**: `Filter` für Button
- **Chevron**: `ChevronUp`/`ChevronDown` für Panel-Toggle
- **X-Icon**: Für Clear-Buttons

### **Typography**
- **Titel**: `font-bold text-xl md:text-2xl`
- **Sensor-Name**: `font-medium text-dark-100`
- **Sensor-Wert**: `font-bold font-mono text-2xl md:text-3xl`
- **Meta-Info**: `text-xs text-dark-400`

### **Spacing & Layout**
- **Grid-Gaps**: `gap-3 md:gap-4` (12px/16px)
- **Card-Padding**: Standard `card` class
- **Header-Gap**: `gap-4` zwischen Titel und Button

### **Animations**
- **Filter-Panel**: Slide-Transition (200ms ease)
- **Live-Updates**: 500ms Highlight-Animation
- **Hover-Effects**: `transition-colors` auf Cards

---

## 🔧 **Technische Details**

### **Vue-Komponenten Struktur**
```typescript
// Script Setup
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMockEspStore } from '@/stores/mockEsp'
import { useWebSocket } from '@/composables/useWebSocket'
import type { QualityLevel } from '@/types'
import type { WebSocketMessage } from '@/services/websocket'

// Template Struktur
<template>
  <div class="space-y-4 md:space-y-6">
    <!-- Header -->
    <!-- Filter Panel -->
    <!-- Loading/Empty/Error States -->
    <!-- Sensor Grid -->
  </div>
</template>
```

### **Reaktive Daten**
```typescript
// Filter State
const showFilters = ref(false)
const filterEspId = ref('')
const filterSensorType = ref<string[]>([])
const filterQuality = ref<QualityLevel[]>([])

// Computed Properties
const availableSensorTypes = computed(() => { /* ... */ })
const availableEspIds = computed(() => { /* ... */ })
const allSensors = computed(() => { /* ... */ })
const filteredSensors = computed(() => { /* ... */ })
const hasActiveFilters = computed(() => { /* ... */ })

// WebSocket
const updatedSensorKeys = ref<Set<string>>(new Set())
```

### **Methoden**
```typescript
// Filter Methods
function clearFilters()
function toggleSensorType(type: string)
function toggleQuality(quality: QualityLevel)

// WebSocket
function handleWebSocketMessage(message: WebSocketMessage)
```

### **CSS/SCSS (Scoped)**
```scss
/* Slide transition for filter panel */
.slide-enter-active, .slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-enter-from, .slide-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.slide-enter-to, .slide-leave-from {
  max-height: 500px;
}

/* Visual feedback for updated sensor values */
.sensor-value--updated {
  animation: sensorUpdateHighlight 0.5s ease-out;
}

@keyframes sensorUpdateHighlight {
  0% {
    border-color: rgba(59, 130, 246, 0.5);
    background-color: rgba(59, 130, 246, 0.1);
  }
  100% {
    border-color: transparent;
    background-color: transparent;
  }
}
```

### **Dependencies**
- **Vue 3**: Composition API, `<script setup>`
- **Stores**: `useMockEspStore` für Daten
- **Composables**: `useWebSocket` für Live-Updates
- **Icons**: Lucide Vue Next (`Thermometer`, `Gauge`, `Filter`, `X`, `ChevronDown`, `ChevronUp`)
- **Types**: `QualityLevel`, `WebSocketMessage`

### **Performance Optimizations**
- **Computed Filters**: Effiziente Filterung ohne DOM-Manipulation
- **Key-Based Updates**: WebSocket-Updates nur für geänderte Sensoren
- **Scoped Styles**: CSS-Isolation
- **Responsive Images**: Adaptive Icon-Größen

---

**Diese Dokumentation ermöglicht es einem Entwickler, die komplette SensorsView basierend auf dem analysierten Code in ca. 30-45 Minuten nachzubauen. Alle UI-Komponenten, Interaktionen, Datenflüsse und Edge-Cases sind detailliert spezifiziert.**
