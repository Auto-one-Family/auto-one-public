# Dashboard Widgets — Katalog & Integration Guide

**Stand:** 2026-04-14  
**Verwaltung:** `useDashboardWidgets.ts` (Widget Registry, Props-Mapping, DOM-Management)  
**Config-UI:** `WidgetConfigPanel.vue` (SlideOver Panel mit Progressive Disclosure)

---

## Übersicht

Dashboard Widgets sind Vue 3 Komponenten für die Echtzeit-Daten-Visualisierung. Sie werden:
- In `useDashboardWidgets.ts` registriert (Widget-Typ ↔ Component Mapping)
- Via `createWidgetElement()` + `mountWidgetToElement()` DOM-agnostisch gerendert
- Über `WidgetConfigPanel.vue` per SlideOver konfiguriert
- In `dashboard.store.ts` (Pinia) persistiert

---

## Widget-Katalog (11 Typen)

| Widget-Type | Komponente | Kategorie | Größe (W×H) | Min-Größe | Beschreibung |
|-------------|-----------|-----------|------------|-----------|-------------|
| `line-chart` | LineChartWidget.vue | Sensoren | 6×4 | 4×3 | Live-Verlauf eines Sensors mit Y-Achsen-Defaults |
| `gauge` | GaugeWidget.vue | Sensoren | 3×3 | 2×3 | Kreisanzeige für aktuelle Messwerte |
| `sensor-card` | SensorCardWidget.vue | Sensoren | 3×2 | 2×2 | Kompakte Karte mit aktuellem Wert |
| `actuator-card` | ActuatorCardWidget.vue | Aktoren | 3×2 | 2×2 | Aktor-Status und Steuerung |
| `historical` | HistoricalChartWidget.vue | Sensoren | 6×4 | 6×4 | Zeitreihe mit historischen API-Daten |
| `multi-sensor` | MultiSensorWidget.vue | Sensoren | 8×5 | 6×4 | Mehrere Sensoren in einem Chart vergleichen |
| `actuator-runtime` | ActuatorRuntimeWidget.vue | Aktoren | 4×3 | 3×3 | Laufzeitstatistik eines Aktors |
| `esp-health` | ESPHealthWidget.vue | System | 6×3 | 4×3 | Health-Metriken eines ESP32 |
| `alarm-list` | AlarmListWidget.vue | System | 4×4 | 4×4 | Liste aktiver und vergangener Alarme |
| `statistics` | StatisticsWidget.vue | Sensoren | 4×3 | 3×2 | Min / Avg / Max / StdDev über Zeitraum |
| `fertigation-pair` | FertigationPairWidget.vue | Sensoren | 6×4 | 4×3 | Inflow vs. Runoff Vergleich (EC/pH) mit Trend |

---

## Widget Registry (useDashboardWidgets.ts)

### Registrierung

```typescript
// useDashboardWidgets.ts:84-96
const widgetComponentMap: Record<string, Component> = {
  'line-chart': LineChartWidget,
  'gauge': GaugeWidget,
  'sensor-card': SensorCardWidget,
  'actuator-card': ActuatorCardWidget,
  'historical': HistoricalChartWidget,
  'esp-health': ESPHealthWidget,
  'alarm-list': AlarmListWidget,
  'actuator-runtime': ActuatorRuntimeWidget,
  'multi-sensor': MultiSensorWidget,
  'statistics': StatisticsWidget,
  'fertigation-pair': FertigationPairWidget,
}
```

### Metadaten-Definition

```typescript
// useDashboardWidgets.ts:99-111
const WIDGET_TYPE_META: WidgetTypeMeta[] = [
  {
    type: 'line-chart',
    label: 'Linien-Chart',
    description: 'Live-Verlauf eines Sensors mit Y-Achsen-Defaults',
    icon: BarChart3,
    w: 6, h: 4,                    // GridStack Default-Größe
    minW: 4, minH: 3,              // GridStack Min-Größe
    category: 'Sensoren'            // Für Config-UI Grouping
  },
  // ... weitere 10 Widgets
]
```

### Default-Konfiguration

```typescript
// useDashboardWidgets.ts:114-126
const WIDGET_DEFAULT_CONFIGS: Record<string, Record<string, unknown>> = {
  'line-chart': { timeRange: '1h', showThresholds: false },
  'gauge': {},
  'sensor-card': {},
  'historical': { timeRange: '24h' },
  'multi-sensor': { dataSources: '' },
  'actuator-card': {},
  'actuator-runtime': {},
  'esp-health': {},
  'alarm-list': {},
  'statistics': { timeRange: '7d', showStdDev: true, showQuality: false },
  'fertigation-pair': { 
    sensorType: 'ec', 
    timeRange: '24h', 
    diffWarningThreshold: 0.5, 
    diffCriticalThreshold: 0.8 
  },
}
```

---

## Props-Interfaces (Kurzbeschreibung)

### Allgemein

```typescript
// Alle Widgets bekommen vom useDashboardWidgets-Composable diese Base-Props:
interface BaseWidgetProps {
  // Vom Config übermittelt:
  sensorId?: string              // LineChart, Gauge, SensorCard, Historical, Statistics
  actuatorId?: string            // ActuatorCard, ActuatorRuntime
  timeRange?: string             // LineChart, Historical, Statistics ('1h' | '6h' | '24h' | '7d' | '30d')
  zoneFilter?: string            // AlarmList, ESPHealth, ActuatorRuntime
  readOnly?: boolean             // ActuatorCard im Monitor-Context (kein Toggle)
  
  // Responsive Seite:
  zoneId?: string                // PA-02c Zone-Scoped Sensor-Filtering
  compactTileGaugeSemantics?: boolean  // L1 Zone-Tile Compact Mode
}
```

### Widget-spezifische Props

| Widget | Props | Quelle |
|--------|-------|--------|
| LineChartWidget | `sensorId`, `timeRange`, `showThresholds`, `yMin`, `yMax`, `color`, `warnLow`, `warnHigh`, `alarmLow`, `alarmHigh` | Config |
| GaugeWidget | `sensorId`, `valueSource` ('zone_avg' \| 'sensor'), `aggCategory`, `yMin`, `yMax`, `color`, `warnLow`, `warnHigh`, `alarmLow`, `alarmHigh` | Config |
| SensorCardWidget | `sensorId` | Config |
| ActuatorCardWidget | `actuatorId`, `readOnly` | Config + useDashboardWidgets |
| HistoricalChartWidget | `sensorId`, `timeRange`, `yMin`, `yMax`, `color`, `warnLow`, `warnHigh`, `alarmLow`, `alarmHigh` | Config |
| MultiSensorWidget | `dataSources`, `compareMode`, `compareSensorType`, `compareZoneId` | Config |
| ActuatorRuntimeWidget | `actuatorId`, `zoneFilter` | Config |
| ESPHealthWidget | `zoneFilter` | Config |
| AlarmListWidget | `zoneFilter`, `showOfflineOnly`, `maxItems`, `showResolved`, `actuatorFilter` | Config |
| StatisticsWidget | `sensorId`, `timeRange`, `showStdDev`, `showQuality` | Config |
| FertigationPairWidget | `inflowSensorId`, `runoffSensorId`, `sensorType`, `timeRange`, `diffWarningThreshold`, `diffCriticalThreshold`, `title`, `zoneLabel`, `referenceBands` | Config |

---

## Props-Mapping (useDashboardWidgets.ts:240-309)

```typescript
function mountWidgetToElement(
  widgetId: string,
  mountId: string,
  type: string,
  config: Record<string, any>  // Aus dashboard.store
): void {
  const WidgetComponent = widgetComponentMap[type]
  const mountEl = document.getElementById(mountId)
  
  // Props aus Config konstruieren
  const props: Record<string, any> = {}
  
  // Generische Sensor/Actuator Props
  if (config.sensorId) props.sensorId = config.sensorId
  if (config.actuatorId) props.actuatorId = config.actuatorId
  if (config.timeRange) props.timeRange = config.timeRange
  if (config.yMin != null) props.yMin = config.yMin
  if (config.yMax != null) props.yMax = config.yMax
  
  // Widget-spezifische Props
  if (config.showThresholds != null) props.showThresholds = config.showThresholds
  if (config.warnLow != null) props.warnLow = config.warnLow
  if (config.warnHigh != null) props.warnHigh = config.warnHigh
  
  // FertigationPairWidget Props (Zeile 276-283)
  if (config.inflowSensorId) props.inflowSensorId = config.inflowSensorId
  if (config.runoffSensorId) props.runoffSensorId = config.runoffSensorId
  if (config.sensorType) props.sensorType = config.sensorType
  if (config.diffWarningThreshold != null) props.diffWarningThreshold = config.diffWarningThreshold
  if (config.diffCriticalThreshold != null) props.diffCriticalThreshold = config.diffCriticalThreshold
  
  // Zone-Kontext (PA-02c)
  if (zoneId?.value) props.zoneId = zoneId.value
  
  // Event-Handler
  if (onConfigUpdate) props['onUpdate:config'] = (newConfig) => onConfigUpdate(widgetId, newConfig)
  
  // Mount via Vue's render()
  const vnode = h(WidgetComponent, props)
  if (appContext) vnode.appContext = appContext
  render(vnode, mountEl)
  mountedWidgets.set(widgetId, mountEl)
}
```

---

## Dashboard-Store Integration (dashboard.store.ts)

### Widget-Config-Format

```typescript
interface DashboardWidget {
  id: string                      // UUID oder generiert
  type: string                    // 'line-chart', 'gauge', etc.
  title: string                   // User-sichtbarer Titel
  config: Record<string, any>     // Widget-spezifische Config
  // GridStack-Attribute (wenn EditorView):
  x?: number
  y?: number
  w?: number
  h?: number
}

interface Dashboard {
  id: string
  title: string
  layout: 'grid' | 'compact'
  widgets: DashboardWidget[]
  // ... weitere Felder
}
```

### Config-Struktur pro Widget-Type

```typescript
// LineChart Config
{
  type: 'line-chart',
  config: {
    sensorId: 'sensor-uuid',
    timeRange: '24h',
    showThresholds: true,
    yMin: 0,
    yMax: 100,
    color: '#3b82f6',
    warnLow: 20,
    warnHigh: 80,
    alarmLow: 10,
    alarmHigh: 90
  }
}

// FertigationPair Config
{
  type: 'fertigation-pair',
  config: {
    inflowSensorId: 'sensor-uuid-1',
    runoffSensorId: 'sensor-uuid-2',
    sensorType: 'ec',
    timeRange: '24h',
    diffWarningThreshold: 0.5,
    diffCriticalThreshold: 0.8,
    title: 'Fertigation Control Zone A',
    referenceBands: [
      { label: 'Optimal', min: 0.1, max: 0.3 }
    ]
  }
}
```

---

## WidgetConfigPanel.vue — Config-UI

### Progressive Disclosure Layout (WidgetConfigPanel.vue:6-9)

```
Zone 1 (KERN) — Immer sichtbar:
  - Titel
  - Zonen-Filter (falls zutreffend)
  - Sensor/Aktor-Picker
  - Time Range

Zone 2 (DARSTELLUNG) — Collapsed Accordion:
  - Y-Achse Min/Max
  - Farbe
  - Schwellwerte (Warn/Alarm)

Zone 3 (ERWEITERT) — Collapsed Accordion:
  - Statistik-Optionen
  - Fertigation-spezifische Schwellwerte
```

### FertigationPair Config-Sektion (WidgetConfigPanel.vue:72-79)

```typescript
const isFertigationPair = computed(() =>
  props.widgetType === 'fertigation-pair'
)

const hasZone3 = computed(() =>
  hasStatisticsOptions.value || isFertigationPair.value
)
```

**UI-Pattern für Fertigation:**
```vue
<!-- In Zone 3 (ERWEITERT) -->
<div v-if="isFertigationPair" class="space-y-4">
  <!-- Inflow Sensor Picker -->
  <SensorSelectCombo
    v-model="localConfig.inflowSensorId"
    label="Inflow-Sensor (EC/pH)"
    :zone-filter="selectedSensorZone"
  />
  
  <!-- Runoff Sensor Picker -->
  <SensorSelectCombo
    v-model="localConfig.runoffSensorId"
    label="Runoff-Sensor (EC/pH)"
    :zone-filter="selectedSensorZone"
  />
  
  <!-- Sensor Type (EC or pH) -->
  <div>
    <label>Sensor-Typ</label>
    <select v-model="localConfig.sensorType">
      <option value="ec">EC (mS/cm)</option>
      <option value="ph">pH</option>
    </select>
  </div>
  
  <!-- Thresholds -->
  <NumberInput
    v-model.number="localConfig.diffWarningThreshold"
    label="Warn-Schwelle"
    :step="0.1"
  />
  <NumberInput
    v-model.number="localConfig.diffCriticalThreshold"
    label="Kritischer Schwelle"
    :step="0.1"
  />
</div>
```

---

## Neues Widget hinzufügen — Anleitung

### Schritt 1: Komponente erstellen

**Datei:** `El Frontend/src/components/dashboard-widgets/MyNewWidget.vue`

```vue
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { myApi } from '@/api/my-feature'
import { websocketService } from '@/services/websocket'
import { createLogger } from '@/utils/logger'

const log = createLogger('MyNewWidget')

// Props (typisiert)
interface Props {
  myPropId: string
  optionalSetting?: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:config': [config: Record<string, any>]
}>()

// State
const data = ref<DataType | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)

// Lifecycle
onMounted(async () => {
  await loadData()
  wsUnsubscriber = websocketService.on('my_event', handleUpdate)
})

onUnmounted(() => {
  if (wsUnsubscriber) wsUnsubscriber()
})

// Template mit Tailwind Dark-Mode
</script>

<template>
  <div class="rounded-lg border border-dark-700 bg-dark-800 p-4">
    <!-- Widget Content -->
  </div>
</template>
```

### Schritt 2: In useDashboardWidgets registrieren

**Datei:** `El Frontend/src/composables/useDashboardWidgets.ts`

```typescript
// Zeile 16: Import hinzufügen
import MyNewWidget from '@/components/dashboard-widgets/MyNewWidget.vue'

// Zeile 84-96: In widgetComponentMap
const widgetComponentMap: Record<string, Component> = {
  // ... existierende
  'my-new-widget': MyNewWidget,
}

// Zeile 99-111: In WIDGET_TYPE_META
const WIDGET_TYPE_META: WidgetTypeMeta[] = [
  // ... existierende
  {
    type: 'my-new-widget',
    label: 'Mein Widget',
    description: 'Beschreibung für Admin',
    icon: MyIcon,
    w: 4, h: 3,
    minW: 3, minH: 2,
    category: 'Meine Kategorie'
  },
]

// Zeile 114-126: Default-Config
const WIDGET_DEFAULT_CONFIGS: Record<string, Record<string, unknown>> = {
  // ... existierende
  'my-new-widget': { setting1: 'default', setting2: 100 },
}

// Zeile 276-283: Props-Mapping (falls nötig)
if (config.mySetting) props.mySetting = config.mySetting
```

### Schritt 3: Config-UI erweitern (optional)

**Datei:** `El Frontend/src/components/dashboard-widgets/WidgetConfigPanel.vue`

```typescript
// Line 44-100: Computed-Flag hinzufügen
const hasMyNewWidgetFields = computed(() =>
  props.widgetType === 'my-new-widget'
)

// Zone 3 (ERWEITERT) erweitern
const hasZone3 = computed(() =>
  hasStatisticsOptions.value || 
  isFertigationPair.value || 
  hasMyNewWidgetFields.value
)
```

```vue
<!-- In Zone 3 Section -->
<div v-if="hasMyNewWidgetFields" class="space-y-4">
  <TextInput
    v-model="localConfig.setting1"
    label="Setting 1"
  />
  <NumberInput
    v-model.number="localConfig.setting2"
    label="Setting 2"
  />
</div>
```

### Schritt 4: Tests schreiben

**Datei:** `El Frontend/src/components/dashboard-widgets/__tests__/MyNewWidget.spec.ts`

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MyNewWidget from '../MyNewWidget.vue'
import { createPinia } from 'pinia'

describe('MyNewWidget', () => {
  it('renders with props', () => {
    const wrapper = mount(MyNewWidget, {
      props: { myPropId: 'test-id' },
      global: { plugins: [createPinia()] }
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('emits update:config on setting change', async () => {
    const wrapper = mount(MyNewWidget, {
      props: { myPropId: 'test-id' }
    })
    // ... trigger change
    expect(wrapper.emitted('update:config')).toBeDefined()
  })
})
```

---

## Best Practices

### 1. Cleanup in onUnmounted (Speicherlecks vermeiden)

```typescript
const wsUnsubscriber: (() => void)[] = []

onMounted(() => {
  wsUnsubscriber.push(websocketService.on('event', handler))
})

onUnmounted(() => {
  wsUnsubscriber.forEach(unsub => unsub())
  wsUnsubscriber.length = 0  // Clear array
})
```

### 2. Error-State immer anzeigen

```vue
<template>
  <LoadingState v-if="isLoading" />
  <ErrorState v-else-if="error" :message="error" @retry="reload" />
  <div v-else><!-- Actual Content --></div>
</template>
```

### 3. Type-Safe Props & Config

```typescript
// RICHTIG
interface Props {
  sensorId: string
  timeRange?: '1h' | '24h' | '7d'
}

// FALSCH
interface Props {
  sensorId: any
  timeRange?: string
}
```

### 4. WebSocket Events unsubscribe

```typescript
// RICHTIG
const unsubscribe = websocketService.on('event', handler)
onUnmounted(() => unsubscribe())

// FALSCH (Memory Leak)
websocketService.on('event', handler)
// Kein Cleanup!
```

### 5. Chart.js Plugins registrieren

```typescript
// RICHTIG (einmal global, vor ChartJS.register)
import zoomPlugin from 'chartjs-plugin-zoom'
ChartJS.register(zoomPlugin)

// FALSCH (mehrfach, potenzielle Duplizierungen)
chart.register(zoomPlugin)
```

---

## Debugging

### Console-Ausgaben

```typescript
import { createLogger } from '@/utils/logger'
const log = createLogger('MyNewWidget')

log.debug('Widget mounted', { props: this.$props })
log.error('Failed to load data', error)
```

### Browser DevTools

1. **Vue DevTools:** Inspiziere Props, State, Emits
2. **Network Tab:** API-Requests überwachen
3. **Application Tab:** Store (Pinia) prüfen

### Common Pitfalls

| Problem | Lösung |
|---------|--------|
| Widget zeigt veraltete Daten | `watch()` auf Props; Ref-basiertes Re-Fetching |
| Memory Leak (steigende RAM) | Cleanup in `onUnmounted()` prüfen |
| WebSocket Events dupliziert | Doppelte `.on()` Aufrufe vermeiden |
| Props ändern → Widget nicht aktualisiert | `watch(props, ...)` oder Ref-Wrapper nutzen |
| TypeError bei WS-Update | Null-checks vor data access: `if (data && data.value)` |

---

## Referenzen

- **Composable:** `/El Frontend/src/composables/useDashboardWidgets.ts`
- **Config-UI:** `/El Frontend/src/components/dashboard-widgets/WidgetConfigPanel.vue`
- **Store:** `/El Frontend/src/stores/dashboard.ts` (Pinia)
- **Types:** `/El Frontend/src/types/index.ts` (WidgetTypeMeta, DashboardWidget, etc.)
- **Example (Fertigation):** `/El Frontend/src/components/dashboard-widgets/FertigationPairWidget.vue`
- **Integrationsref:** `/docs/analysen/konzept-fertigation-ux-integration-2026-04-14.md`
