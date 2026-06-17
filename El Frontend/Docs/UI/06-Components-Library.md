# Frontend Components Library - Dokumentation

**Erstellt:** 2025-12-19
**Letztes Update:** 2025-12-23 (Vollständige Synchronisation mit Code)
**Status:** ✅ Vollständig implementiert
**Total Components:** 27 Komponenten kategorisiert

---

## Übersicht

| Kategorie | Anzahl | Komponenten |
|-----------|--------|-------------|
| **Common** | 11 | Badge, Button, Card, EmptyState, ErrorState, Input, LoadingState, Modal, Select, Spinner, Toggle |
| **Layout** | 3 | MainLayout, AppHeader, AppSidebar |
| **ESP** | 6 | ESPCard, ESPOrbitalLayout, SensorSatellite, ActuatorSatellite, SensorValueCard, ConnectionLines |
| **Dashboard** | 1 | StatCard |
| **Database** | 6 | DataTable, FilterPanel, Pagination, RecordDetailModal, SchemaInfoPanel, TableSelector |
| **Zones** | 1 | ZoneAssignmentPanel |
| **Total** | **27** | |

---

## 1. Common Components (11)

### 1.1 Badge

**Datei:** `src/components/common/Badge.vue`
**Zweck:** Status-Label (MOCK, REAL, Online, Error, Quality-Level, etc.)

**Props:**
```typescript
interface Props {
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'gray' | 'purple' | 'orange' | 'mock' | 'real' | 'neutral'
  size?: 'sm' | 'md' | 'lg'
  pulse?: boolean          // Pulsing Animation für Online-Status
  dot?: boolean            // Farbiger Punkt vor Text
  bordered?: boolean       // Border für mock/real variants
}
```

**Beispiel:**
```vue
<Badge variant="mock" size="sm">MOCK</Badge>
<Badge variant="success" dot pulse>Online</Badge>
<Badge variant="danger">ERROR</Badge>
```

**Varianten:**
- `success` - Grün (Online, Good, Active)
- `warning` - Orange (Caution, Poor Quality)
- `danger` - Rot (Error, E-Stop, Critical)
- `info` - Blau (Info, Fair Quality)
- `mock` - Lila mit Border (Mock Hardware)
- `real` - Cyan mit Border (Real Hardware)
- `gray` - Grau (Inactive, Neutral)

---

### 1.2 Button

**Datei:** `src/components/common/Button.vue`
**Zweck:** Versatiles Button-Element mit Loading-State

**Props:**
```typescript
interface Props {
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean        // Zeigt Spinner und disabled
  fullWidth?: boolean
  type?: 'button' | 'submit' | 'reset'
}
```

**Beispiel:**
```vue
<Button variant="primary" :loading="isSubmitting">Speichern</Button>
<Button variant="danger" size="sm">Löschen</Button>
<Button variant="ghost">Abbrechen</Button>
```

**Features:**
- Iridescent Gradient für Primary-Variant
- Integrierter Spinner bei Loading
- 44px min-height (Touch-Target)

---

### 1.3 Card

**Datei:** `src/components/common/Card.vue`
**Zweck:** Container mit Special Effects

**Props:**
```typescript
interface Props {
  hoverable?: boolean      // Hover-Lift Animation
  noPadding?: boolean
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'mock' | 'real'
  glass?: boolean          // Glass Morphism Effekt
  shimmer?: boolean        // Water Reflection Shimmer
  iridescent?: boolean     // Iridescent Border
}
```

**Slots:**
- `header` - Card Header
- `default` - Card Body
- `footer` - Card Footer

**Beispiel:**
```vue
<Card glass hoverable>
  <template #header>Titel</template>
  <p>Inhalt</p>
  <template #footer>Actions</template>
</Card>
```

---

### 1.4 EmptyState

**Datei:** `src/components/common/EmptyState.vue`
**Zweck:** "Keine Daten" Zustand mit Call-to-Action

**Props:**
```typescript
interface Props {
  icon?: Component         // Lucide Icon
  title: string
  description?: string
  actionText?: string
  showAction?: boolean
}
```

**Emits:**
- `action` - Action Button geklickt

**Beispiel:**
```vue
<EmptyState
  :icon="Plus"
  title="Keine Sensoren"
  description="Fügen Sie einen Sensor hinzu"
  action-text="Sensor hinzufügen"
  @action="showAddModal = true"
/>
```

---

### 1.5 ErrorState

**Datei:** `src/components/common/ErrorState.vue`
**Zweck:** Fehler-Banner mit Retry + Dismiss

**Props:**
```typescript
interface Props {
  message: string | string[] | unknown
  title?: string           // Default: 'Ein Fehler ist aufgetreten'
  showRetry?: boolean      // Default: true
  showDismiss?: boolean    // Default: false
  retryText?: string       // Default: 'Erneut versuchen'
}
```

**Emits:**
- `retry` - Retry Button geklickt
- `dismiss` - Dismiss Button geklickt

**Beispiel:**
```vue
<ErrorState
  v-if="error"
  :message="error"
  show-dismiss
  @retry="fetchData"
  @dismiss="clearError"
/>
```

---

### 1.6 Input

**Datei:** `src/components/common/Input.vue`
**Zweck:** Form Input mit Label, Error, Helper Text

**Props:**
```typescript
interface Props {
  modelValue: string | number
  type?: 'text' | 'email' | 'password' | 'number' | 'search' | 'tel' | 'url'
  label?: string
  placeholder?: string
  disabled?: boolean
  required?: boolean
  error?: string
  helper?: string
  clearable?: boolean      // X-Button zum Leeren
  id?: string              // Auto-generiert wenn nicht angegeben
  min?: number             // Für number inputs
  max?: number
  step?: number
}
```

**Emits:**
- `update:modelValue` - v-model Support

**Beispiel:**
```vue
<Input
  v-model="email"
  type="email"
  label="E-Mail"
  placeholder="user@example.com"
  :error="emailError"
  clearable
/>
```

---

### 1.7 LoadingState

**Datei:** `src/components/common/LoadingState.vue`
**Zweck:** Spinner + Text beim Laden

**Props:**
```typescript
interface Props {
  text?: string           // Default: 'Lädt...'
  fullHeight?: boolean
  size?: 'sm' | 'md' | 'lg'
}
```

**Beispiel:**
```vue
<LoadingState v-if="isLoading" text="Lade ESP-Geräte..." />
```

---

### 1.8 Modal

**Datei:** `src/components/common/Modal.vue`
**Zweck:** Dialog Modal mit Glassmorphism

**Props:**
```typescript
interface Props {
  open: boolean
  title: string
  maxWidth?: string        // Default: 'max-w-md'
  showClose?: boolean      // Default: true
  closeOnOverlay?: boolean // Default: true
  closeOnEscape?: boolean  // Default: true
}
```

**Emits:**
- `update:open` - v-model Support
- `close` - Modal geschlossen

**Slots:**
- `default` - Modal Body
- `footer` - Modal Footer

**Beispiel:**
```vue
<Modal v-model:open="showModal" title="Sensor hinzufügen">
  <form>...</form>
  <template #footer>
    <Button @click="submit">Speichern</Button>
  </template>
</Modal>
```

**Features:**
- Teleport zu Body
- Body Scroll Lock
- Escape & Overlay Close

---

### 1.9 Select

**Datei:** `src/components/common/Select.vue`
**Zweck:** Dropdown Select mit Label

**Props:**
```typescript
interface SelectOption {
  value: string | number
  label: string
  disabled?: boolean
}

interface Props {
  modelValue: string | number
  options: SelectOption[]
  label?: string
  placeholder?: string
  disabled?: boolean
  required?: boolean
  error?: string
  helper?: string
  id?: string
}
```

**Emits:**
- `update:modelValue` - v-model Support

**Beispiel:**
```vue
<Select
  v-model="sensorType"
  :options="sensorTypeOptions"
  label="Sensor-Typ"
  placeholder="Wählen..."
/>
```

---

### 1.10 Spinner

**Datei:** `src/components/common/Spinner.vue`
**Zweck:** Animierter Lade-Spinner

**Props:**
```typescript
interface Props {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  color?: string          // Border-Color Klasse
  label?: string          // Accessibility Label
  center?: boolean        // Zentrieren im Container
}
```

**Beispiel:**
```vue
<Spinner size="lg" label="Wird geladen..." center />
```

---

### 1.11 Toggle

**Datei:** `src/components/common/Toggle.vue`
**Zweck:** Switch Toggle mit Label

**Props:**
```typescript
interface Props {
  modelValue: boolean
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  label?: string
  description?: string
  activeColor?: 'blue' | 'green' | 'red' | 'orange' | 'purple'
}
```

**Emits:**
- `update:modelValue` - v-model Support

**Beispiel:**
```vue
<Toggle
  v-model="autoHeartbeat"
  label="Auto-Heartbeat"
  description="Automatisch alle 60s senden"
  active-color="green"
/>
```

---

## 2. Layout Components (3)

### 2.1 MainLayout

**Datei:** `src/components/layout/MainLayout.vue`
**Zweck:** Root-Layout mit Header, Sidebar, Content

**Features:**
- Responsive Sidebar (Mobile: Slide-out, Desktop: Fixed)
- Header mit Hamburger Menu
- RouterView für Content
- Mobile Overlay

**Struktur:**
```
MainLayout
├── Transition (mobile overlay)
├── AppSidebar (navigation)
└── div (main content)
    ├── AppHeader (toolbar)
    └── main > RouterView
```

---

### 2.2 AppHeader

**Datei:** `src/components/layout/AppHeader.vue`
**Zweck:** Application Header

**Emits:**
- `toggle-sidebar` - Hamburger Menu geklickt

**Features:**
- Dynamischer Page Title aus Route Meta
- Server Connection Status
- User Menu Dropdown
- Logout Funktion
- Mobile Hamburger

---

### 2.3 AppSidebar

**Datei:** `src/components/layout/AppSidebar.vue`
**Zweck:** Collapsible Navigation Sidebar

**Props:**
```typescript
interface Props {
  isOpen: boolean    // Mobile Sidebar Visibility
}
```

**Emits:**
- `close` - Sidebar sollte schließen (Mobile)

**Features:**
- Collapsible Navigation Groups
- Admin-Only Sections (via authStore)
- LocalStorage Persistence für Collapsed State
- Auto-Expand bei Active Route
- Iridescent Active State

**Navigation Struktur:**
1. **Main** - Dashboard
2. **Geräte** - Alle ESPs, Sensoren, Aktoren
3. **Automation** - Regeln
4. **Monitoring** - MQTT Live, Server Logs
5. **Administration** (Admin-only) - Benutzer, Datenbank, System, Last-Tests

---

## 3. ESP Components (6)

### 3.1 ESPCard

**Datei:** `src/components/esp/ESPCard.vue`
**Zweck:** ESP Device Card in Grid View

**Props:**
```typescript
interface Props {
  esp: ESPDevice
}
```

**Emits:**
- `heartbeat` - Heartbeat Button (Mock)
- `toggleSafeMode` - Safe Mode Toggle (Mock)
- `delete` - Delete Button (Mock)

**Features:**
- Mock/Real Visual Distinction (Purple vs Cyan Border)
- Status Indicators (Online/Offline/Error)
- System State Badges (SAFE_MODE, ERROR)
- Emergency Stop Indicator
- Device Stats: Zone, Sensors, Actuators, Uptime, Heap
- Auto-Heartbeat Indicator

---

### 3.2 ESPOrbitalLayout

**Datei:** `src/components/esp/ESPOrbitalLayout.vue`
**Zweck:** Orbital Visualisierung von Sensors/Actuators um ESP

**Props:**
```typescript
interface Props {
  device: ESPDevice
  showConnections?: boolean   // Default: true
  compactMode?: boolean       // Default: false
}
```

**Emits:**
- `sensorClick` - Sensor Satellite geklickt
- `actuatorClick` - Actuator Satellite geklickt

**Features:**
- Kreisförmige Anordnung: Sensoren links (180°-360°), Aktoren rechts (0°-180°)
- Dynamischer Orbital-Radius basierend auf Item-Anzahl
- Responsive: Mobile = Linear, Desktop = Orbital
- Position Tracking für ConnectionLines
- Selection State für Satellites

---

### 3.3 SensorSatellite

**Datei:** `src/components/esp/SensorSatellite.vue`
**Zweck:** Sensor als Orbit-Karte

**Props:**
```typescript
interface Props {
  espId: string
  gpio: number
  sensorType: string
  name?: string | null
  value: number
  quality: QualityLevel
  unit: string
  selected?: boolean
  showConnections?: boolean
}
```

**Emits:**
- `click` - Satellite geklickt
- `showConnections` - Sensor hat Verbindungen

**Features:**
- Sensor Icon basierend auf Typ (Thermometer, Droplet, Zap, etc.)
- Live Value Display mit Unit
- Quality Indicator (farbcodiert)
- Connection Indicator Dot
- Hover Lift Animation
- Glass Morphism Styling

---

### 3.4 ActuatorSatellite

**Datei:** `src/components/esp/ActuatorSatellite.vue`
**Zweck:** Aktor als Orbit-Karte

**Props:**
```typescript
interface Props {
  espId: string
  gpio: number
  actuatorType: string
  name?: string | null
  state: boolean
  pwmValue?: number
  emergencyStopped?: boolean
  selected?: boolean
  showConnections?: boolean
}
```

**Emits:**
- `click` - Satellite geklickt
- `showConnections` - Actuator hat Verbindungen

**Features:**
- Actuator Icon basierend auf Typ (Power, Waves, Fan, etc.)
- Status Display: ON/OFF oder PWM Percentage
- Emergency Stop Indicator (pulsing Animation)
- Quality Color basierend auf State

---

### 3.5 SensorValueCard

**Datei:** `src/components/esp/SensorValueCard.vue`
**Zweck:** Sensor Value Display mit Details

**Props:**
```typescript
interface Props {
  sensor: Sensor
  editable?: boolean
  compact?: boolean
}
```

**Emits:**
- `edit` - Edit angefordert
- `remove` - Remove angefordert

**Features:**
- Display Name oder Sensor Type Label
- Raw und Processed Value Support
- Quality Badge (farbcodiert)
- Subzone Badge
- Expandable Technical Details
- Edit/Remove Actions (wenn editable)

---

### 3.6 ConnectionLines

**Datei:** `src/components/esp/ConnectionLines.vue`
**Zweck:** SVG Verbindungslinien für Logic Rules

**Props:**
```typescript
interface Connection {
  from: string   // sensor/actuator ID
  to: string
  type: 'logic' | 'cross-esp' | 'internal'
  ruleName?: string
}

interface Position {
  x: number
  y: number
}

interface Props {
  connections: Connection[]
  positions: Record<string, Position>
  showTooltips?: boolean
  hoveredConnection?: Connection | null
}
```

**Emits:**
- `connectionHover` - Connection Hover Event
- `connectionClick` - Connection Click Event

**Features:**
- Smooth Quadratic Curve Lines
- Line Types mit verschiedenen Styles:
  - Grün solid (Logic, 3px)
  - Iridescent solid (Cross-ESP, 2px)
  - Dashed (Internal, 1.5px)
- Arrow Markers für Logic
- Tooltips mit Rule Name
- Hover Enlargement

---

## 4. Dashboard Components (1)

### 4.1 StatCard

**Datei:** `src/components/dashboard/StatCard.vue`
**Zweck:** KPI-Karte mit Icon und Trend

**Props:**
```typescript
interface Trend {
  direction: 'up' | 'down'
  value: number
}

interface Props {
  title: string
  value: number | string
  subtitle?: string
  icon: Component          // Lucide Icon
  iconColor?: string       // Default: 'text-iridescent-1'
  iconBgColor?: string     // Default: 'bg-iridescent-1/10'
  trend?: Trend
  loading?: boolean
  highlighted?: boolean    // Iridescent Border
}
```

**Beispiel:**
```vue
<StatCard
  title="ESP-Geräte"
  :value="12"
  subtitle="8 online"
  :icon="Cpu"
  :trend="{ direction: 'up', value: 5 }"
/>
```

---

## 5. Database Components (6)

### 5.1 DataTable

**Datei:** `src/components/database/DataTable.vue`
**Zweck:** Dynamische Datentabelle

**Props:**
```typescript
interface Props {
  columns: ColumnSchema[]
  data: Record<string, unknown>[]
  loading?: boolean
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
}
```

**Emits:**
- `sort` - Column Header Sort Click
- `rowClick` - Row Click mit Record Data

**Features:**
- Max 8 sichtbare Columns (PK first, JSON last)
- Smart Value Formatting (DateTime, Boolean, JSON, Masked)
- Sort Indicators
- Row Hover Effect
- Eye Icon für Row Detail

---

### 5.2 FilterPanel

**Datei:** `src/components/database/FilterPanel.vue`
**Zweck:** Dynamische Filter-UI

**Props:**
```typescript
interface Props {
  columns: ColumnSchema[]
  currentFilters: Record<string, unknown>
}
```

**Emits:**
- `apply` - Filter anwenden
- `clear` - Alle Filter löschen

**Features:**
- Add/Remove Filter Rows dynamisch
- Type-aware Operators (=, >=, <=, contains, after, before)
- Type-specific Inputs
- Active Filter Badge Counter

---

### 5.3 Pagination

**Datei:** `src/components/database/Pagination.vue`
**Zweck:** Pagination Controls

**Props:**
```typescript
interface Props {
  page: number
  totalPages: number
  totalCount: number
  pageSize: number
}
```

**Emits:**
- `pageChange` - Page Nummer geändert
- `pageSizeChange` - Page Size geändert

**Features:**
- Results Info Display
- Page Size Selector (25, 50, 100, 200, 500)
- First/Prev/Next/Last Buttons
- Ellipsis für große Page Ranges

---

### 5.4 RecordDetailModal

**Datei:** `src/components/database/RecordDetailModal.vue`
**Zweck:** Full-Screen Record Detail View

**Props:**
```typescript
interface Props {
  tableName: string
  record: Record<string, unknown>
}
```

**Emits:**
- `close` - Modal schließen
- `navigateToForeignKey` - FK Navigation

**Features:**
- Key-Value Pair Display
- Value Type Coloring
- Automatic FK Detection (fields ending with _id)
- FK Navigation Buttons
- Copy to Clipboard

---

### 5.5 SchemaInfoPanel

**Datei:** `src/components/database/SchemaInfoPanel.vue`
**Zweck:** DB Schema Information Display

**Props:**
```typescript
interface Props {
  schema: TableSchema | null
}
```

**Features:**
- Collapsible Schema View
- Column Details: PK, FK, Type, Nullable
- Type Icons und Colors
- Primary Key Display im Header

---

### 5.6 TableSelector

**Datei:** `src/components/database/TableSelector.vue`
**Zweck:** Table Selection Dropdown

**Props:**
```typescript
interface Props {
  tables: TableSchema[]
  selectedTable: string | null
  loading?: boolean
}
```

**Emits:**
- `select` - Table ausgewählt

**Features:**
- Alphabetisch sortierte Table Liste
- Row Count Formatting (M, K)
- Quick Stats bei Selection

---

## 6. Zone Components (1)

### 6.1 ZoneAssignmentPanel

**Datei:** `src/components/zones/ZoneAssignmentPanel.vue`
**Zweck:** Zone Zuweisung für ESP

**Props:**
```typescript
interface Props {
  espId: string
  currentZoneId?: string
  currentZoneName?: string
  currentMasterZoneId?: string
}
```

**Emits:**
- `zone-updated` - Zone erfolgreich zugewiesen
- `zone-error` - Fehler bei Zone Operation

**Features:**
- Simple Zone Name Input
- Save/Assign Button
- Remove Button (wenn Zone zugewiesen)
- Reset Button (bei Änderung)
- Status Badges
- Error/Success Message Banners

---

## 7. Component Usage Matrix

| Komponente | Views | Häufigkeit |
|------------|-------|------------|
| LoadingState | DashboardView, DevicesView, DeviceDetailView, DatabaseExplorerView, LogViewerView, SystemConfigView, AuditLogView | 10+ |
| EmptyState | DashboardView, DevicesView, DeviceDetailView | 8+ |
| ErrorState | DevicesView | 5+ |
| Badge | DevicesView, DeviceDetailView, SensorsView, ActuatorsView | 15+ |
| Button | Alle Views mit Forms | 20+ |
| Card | DeviceDetailView, DashboardView, LogicView | 10+ |
| Modal | DevicesView, DeviceDetailView, UserManagementView | 8+ |
| Input | DevicesView, DeviceDetailView, UserManagementView, LoginView | 15+ |
| Select | DevicesView, DeviceDetailView, DatabaseExplorerView | 10+ |
| ESPCard | DevicesView | Mock ESP Cards |
| ESPOrbitalLayout | DevicesView | Orbital Visualization |
| StatCard | DashboardView | 4 KPI Cards |
| DataTable | DatabaseExplorerView | DB Records |
| ZoneAssignmentPanel | DeviceDetailView | Zone Assignment |

---

## 8. Design Patterns

### Props mit TypeScript

```typescript
interface Props {
  modelValue?: string
  disabled?: boolean
}

withDefaults(defineProps<Props>(), {
  modelValue: '',
  disabled: false,
})
```

### Emits mit TypeScript

```typescript
interface Emits {
  'update:modelValue': [value: string]
  change: [value: string]
}

defineEmits<Emits>()
```

### Composition API Pattern

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const internalValue = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  internalValue.value = val
})

const handleChange = (value: string) => {
  emit('update:modelValue', value)
  emit('change', value)
}
</script>
```

---

## 9. CSS Variablen

```css
/* Colors */
--color-iridescent-1: #60A5FA  /* Blue accent */
--color-iridescent-2: #A78BFA  /* Purple accent */
--color-iridescent-3: #EC4899  /* Pink accent */

--color-mock: #A78BFA          /* Purple - Mock Hardware */
--color-real: #22D3EE          /* Cyan - Real Hardware */

/* Glass Effect */
--glass-bg: rgba(30, 41, 59, 0.8)
--glass-border: rgba(148, 163, 184, 0.1)
--glass-blur: 12px

/* Dark Theme */
--color-bg-primary: #0F172A
--color-bg-secondary: #1E293B
--color-bg-tertiary: #334155
```

---

## 10. Best Practices

### Do's ✅

- ✅ Verwende `Badge` für Status-Anzeige
- ✅ Verwende `LoadingState` während API-Calls
- ✅ Verwende `EmptyState` mit aussagekräftigem Text
- ✅ Props mit TypeScript interfaces definieren
- ✅ Emits korrekt typisieren
- ✅ Scoped Styles verwenden
- ✅ Accessibility (aria-labels, color-contrast)
- ✅ Mobile-responsive Design

### Don'ts ❌

- ❌ Keine Inline-Styles (außer Debug)
- ❌ Keine Props als `any` typisieren
- ❌ Keine globalen CSS Styles
- ❌ Keine hardcodierten Farben (use CSS vars)
- ❌ Keine Magic Numbers

---

**Dokumentation erstellt:** 2025-12-19
**Letzte Aktualisierung:** 2025-12-23
**Version:** 2.0 (Vollständige Synchronisation mit Code)
