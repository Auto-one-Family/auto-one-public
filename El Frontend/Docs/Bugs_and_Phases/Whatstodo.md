# Arbeitsanweisung: Bug-Fixes und Verbesserungen

> **Stand:** 2025-12-31
> **Status:** Analyse abgeschlossen - Fast alles implementiert

---

## Verhaltensweise und Standards

### Grundprinzipien

Wir arbeiten **immer konsistent** mit der vorhandenen Codebase auf **allerhöchstem industriellen Niveau**. Jede Implementierung muss folgende Kriterien erfüllen:

| Kriterium | Beschreibung |
|-----------|--------------|
| **Robust** | Fehlertoleranz, Error-Handling, Edge-Cases abgedeckt |
| **Echtzeit** | WebSocket-Integration, Live-Updates ohne Polling |
| **Wartbar** | Klare Struktur, dokumentiert, testbar |
| **Zukunftsfähig** | Erweiterbar, keine hardcodierten Werte |
| **Dynamisch anpassbar** | Konfigurierbar ohne Code-Änderungen |
| **Menschenverständlich** | Klare UI, lesbare Logs, verständliche Fehlermeldungen |
| **Server-Zentrisch** | Single Source of Truth auf Server, ESP32 als Datenlieferant |
| **Voll ausgestattet** | Alle Features implementiert, keine Stubs |

Konsistent mit vorhandener Codebase und patterns

### Dokumentations-Hierarchie

| Dokument | Zweck |
|----------|-------|
| `.claude/Hierarchy.md` | System verstehen - Architektur-Übersicht |
| `.claude/CLAUDE.md` | Orientierung - Quick Reference für alle Module |
| `.claude/CLAUDE_SERVER.md` | Server-spezifische Entwicklung |
| `.claude/CLAUDE_FRONTEND.md` | Frontend-spezifische Entwicklung |
| `El Trabajante/docs/` | ESP32 Firmware Dokumentation |

---

## Implementierungsstatus-Übersicht

| Phase | Beschreibung | Status | Offene Punkte |
|-------|--------------|--------|---------------|
| **Phase 1** | Dashboard, ESP-Geräte, DetailView | ✅ 100% | Undo/Redo implementiert |
| **Phase 2** | WebSocket Disconnect | ✅ 100% | Vollständig implementiert |
| **Phase 3** | Mock Sensor Flow | ✅ 100% | Debug-Logging aktiv |
| **Phase 4** | Datenbanken View | ✅ 100% | Alle Formatierungen vorhanden |
| **NEU** | Orbital Sensor Cards | ✅ 100% | `processed_value ?? raw_value` Fix angewandt |

---

## Phase 1: Dashboard, ESP-Geräte und DetailView

### Status: ✅ IMPLEMENTIERT

**"Unassigned" Zone ist vollständig implementiert:**

```typescript
// El Frontend/src/composables/useZoneDragDrop.ts:77-81
const zoneId = device.zone_id || '__unassigned__'
const zoneName = device.zone_name || 'Nicht zugewiesen'

// Zone wird IMMER erstellt, auch wenn leer!
if (!groups.has(zoneId)) {
  groups.set(zoneId, { zoneId, zoneName, devices: [] })
}
```

### Implementierte Features

| Feature | Datei | Zeilen |
|---------|-------|--------|
| `__unassigned__` Zone-Gruppierung | `useZoneDragDrop.ts` | 77-81 |
| Zone-Group Rendering (auch leer) | `ZoneGroup.vue` | VueDraggable mit empty state |
| WebSocket `zone_assignment` Handler | `esp.ts` | 727-752 |
| Drag & Drop Flow | `DashboardView.vue` | `onDeviceDropped()` |

### Implementiert

- [x] **Undo/Redo Pattern** für Zone-Assignments - History Stack implementiert
  - `useZoneDragDrop.ts`: `undo()`, `redo()`, `canUndo`, `canRedo`
  - Max 20 Einträge im History Stack
  - API-basiert mit Toast-Feedback

---

## Phase 2: WebSocket Disconnect bei Tab-Wechsel

### Status: ✅ VOLLSTÄNDIG IMPLEMENTIERT

**Alle kritischen Probleme wurden gelöst:**

| Problem | Lösung | Datei:Zeilen |
|---------|--------|--------------|
| Subscription-Queuing fehlt | `pendingSubscriptions` Queue | `websocket.ts:60-61, 435-439` |
| Token-Expiration-Handling | `shouldRefreshToken()` + Auto-Refresh | `websocket.ts:118-144` |
| Kein Exponential Backoff | `calculateBackoffDelay()` mit Cap | `websocket.ts:237-266` |
| Message Queue Limit | Max 1000 Nachrichten | `websocket.ts:544-548` |

### Zentrale WebSocket-Architektur

**Wichtige Erkenntnis:** Views brauchen KEINE explizite WebSocket-Integration!

```typescript
// El Frontend/src/stores/esp.ts:49-55
const ws = useWebSocket({
  autoConnect: true,      // ← Automatische Verbindung
  autoReconnect: true,    // ← Automatischer Reconnect
  filters: {
    types: ['esp_health', 'sensor_data', 'actuator_status', ...],
  },
})

// Zeile 795: Handler werden automatisch bei Store-Erstellung registriert
initWebSocket()
```

**Registrierte Handler (esp.ts:772-778):**
- `esp_health` → `handleEspHealth()`
- `sensor_data` → `handleSensorData()`
- `actuator_status` → `handleActuatorStatus()`
- `actuator_alert` → `handleActuatorAlert()`
- `config_response` → `handleConfigResponse()`
- `zone_assignment` → `handleZoneAssignment()`

### Warum DevicesView/DeviceDetailView funktionieren

Die Views nutzen `espStore.devices` (reactive ref). Wenn WebSocket-Events eintreffen:
1. `esp.ts` Handler aktualisieren `devices.value[index]`
2. Vue Reactivity propagiert Änderungen automatisch
3. Views re-rendern ohne explizite WebSocket-Subscription

---

## Phase 3: Mock Sensor Flow - Raw-Wert Konvertierung

### Status: ✅ VOLLSTÄNDIG IMPLEMENTIERT

**Debug-Logging ist aktiv in `sensor_handler.py`:**

```python
# El Servador/.../mqtt/handlers/sensor_handler.py:528-567

# 1. Sensor Type Normalisierung (Zeile 528-531)
logger.info(
    f"[Pi-Enhanced] Processing: esp_id={esp_id}, gpio={gpio}, "
    f"sensor_type='{sensor_type}' → normalized='{normalized_type}'"
)

# 2. Processor-Auswahl (Zeile 537-547)
logger.info(
    f"[Pi-Enhanced] Processor found: {type(processor).__name__} "
    f"for '{normalized_type}'"
)

# 3. Processing-Ergebnis (Zeile 562-567)
logger.info(
    f"[Pi-Enhanced] SUCCESS: esp_id={esp_id}, gpio={gpio}, "
    f"raw={raw_value} → processed={result.value} {result.unit}, quality={result.quality}"
)
```

### Payload-Kompatibilität

```python
# sensor_handler.py:160 - Akzeptiert beide Formate
raw_value = float(payload.get("raw", payload.get("raw_value")))
```

---

## Phase 4: Datenbanken View - Menschenverständlichkeit

### Status: ✅ VOLLSTÄNDIG IMPLEMENTIERT

| Feature | Datei | Zeilen |
|---------|-------|--------|
| UUID-Kurzformat + Tooltip | `DataTable.vue` | 63-75, 117-119 |
| Relative Zeitanzeige + Tooltip | `DataTable.vue` | 35-59, 92-104 |
| JSON Preview | `DataTable.vue` | 110-113 |
| Bytes/Uptime Formatierung | `formatters.ts` | 200-302 |

---

## NEU: Orbital Sensor Cards - Datenfluss-Analyse

### Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────────┐
│ DATENFLUSS: ESP STORE → ORBITAL LAYOUT → SENSOR SATELLITE          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. WebSocket Event: type='sensor_data'                             │
│     ↓                                                               │
│  2. esp.ts: handleSensorData() [Zeile 633-653]                      │
│     → sensor.raw_value = data.value                                 │
│     → sensor.quality = data.quality                                 │
│     → sensor.unit = data.unit                                       │
│     ↓                                                               │
│  3. espStore.devices[].sensors[] (reactive)                         │
│     ↓                                                               │
│  4. ESPOrbitalLayout.vue: sensors = props.device?.sensors           │
│     ↓                                                               │
│  5. SensorSatellite.vue:                                            │
│     → :value="sensor.raw_value"  ⚠️ PRÜFEN                          │
│     → :quality="sensor.quality"                                     │
│     → :unit="sensor.unit"                                           │
│     ↓                                                               │
│  6. formattedValue = formatNumber(props.value, decimals)            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Komponenten-Verknüpfung

| Komponente | Datei | Props/Data |
|------------|-------|------------|
| **ESPOrbitalLayout** | `components/esp/ESPOrbitalLayout.vue` | `device: ESPDevice` |
| **SensorSatellite** | `components/esp/SensorSatellite.vue` | `value: number`, `quality`, `unit` |
| **SensorValueCard** | `components/esp/SensorValueCard.vue` | `sensor: Sensor` (vollständiges Objekt) |

### ⚠️ Potentielles Problem: `processed_value` vs `raw_value`

**SensorValueCard.vue** (korrekte Implementierung):
```typescript
// Zeile 65-67
const displayValue = computed(() =>
  props.sensor.processed_value ?? props.sensor.raw_value
)
```

**SensorSatellite.vue** (mögliches Problem):
```typescript
// Zeile 92-94 - Nutzt nur props.value direkt
const formattedValue = computed(() =>
  formatNumber(props.value, sensorConfig.value.decimals)
)
```

**ESPOrbitalLayout.vue** (Zeile 637):
```vue
<SensorSatellite
  :value="sensor.raw_value"  <!-- ⚠️ Nur raw_value, nicht processed_value -->
  ...
/>
```

### Analyse-Ergebnis

**Für Mock ESPs:** Kein Problem, da `raw_value` = `processed_value` (Server schreibt beide gleich)

**Für echte ESPs mit Pi-Enhanced Processing:**
- Wenn `raw_value` ≠ `processed_value` (z.B. ADC-Wert vs. °C)
- Orbital Cards zeigen falschen Wert!

### Empfehlung

**Option A: ESPOrbitalLayout.vue anpassen** (minimal invasiv):
```vue
<SensorSatellite
  :value="sensor.processed_value ?? sensor.raw_value"
  ...
/>
```

**Option B: SensorSatellite.vue anpassen** (konsistent mit SensorValueCard):
```typescript
// Neues Prop hinzufügen
interface Props {
  rawValue: number
  processedValue?: number
  // ...
}

const displayValue = computed(() =>
  props.processedValue ?? props.rawValue
)
```

### Aktuelle Implementierung - Status

| Komponente | Nutzt processed_value? | Status |
|------------|------------------------|--------|
| SensorValueCard.vue | ✅ Ja (Zeile 65-67) | Korrekt |
| SensorSatellite.vue | ✅ Via Props | Korrekt (erhält processed_value ?? raw_value) |
| ESPOrbitalLayout.vue | ✅ Ja (Zeile 637) | **GEFIXT** - `processed_value ?? raw_value` |

---

## Zusammenfassung

### Was wurde implementiert

| Feature | Status | Verantwortliche Dateien |
|---------|--------|------------------------|
| Unassigned Zone | ✅ | `useZoneDragDrop.ts`, `ZoneGroup.vue` |
| WebSocket Subscription Queue | ✅ | `websocket.ts:60-61, 435-439` |
| Token Expiration Handling | ✅ | `websocket.ts:118-144` |
| Exponential Backoff | ✅ | `websocket.ts:237-266` |
| Message Queue Limit | ✅ | `websocket.ts:544-548` |
| ESP Store WebSocket Integration | ✅ | `esp.ts:49-55, 765-795` |
| Sensor Processing Debug-Logging | ✅ | `sensor_handler.py:528-567` |
| UUID-Kurzformat + Tooltip | ✅ | `DataTable.vue:63-75, 117-119` |
| Relative Zeitanzeige + Tooltip | ✅ | `DataTable.vue:35-59, 92-104` |
| Bytes/Uptime Formatierung | ✅ | `formatters.ts` |
| Orbital Layout Sensor Data | ✅ | `ESPOrbitalLayout.vue`, `SensorSatellite.vue` |
| processed_value in Orbital Cards | ✅ | `ESPOrbitalLayout.vue:637` |
| Undo/Redo Zone-Assignments | ✅ | `useZoneDragDrop.ts:330-491` |

### Was noch offen ist

**Alles erledigt!** Alle Tasks aus dieser Liste wurden implementiert.

---

## Nächste Schritte

### Erledigte Tasks (2025-12-31)

1. **processed_value Fix** - ✅ Implementiert
   - `ESPOrbitalLayout.vue:637`: `:value="sensor.processed_value ?? sensor.raw_value"`

2. **Undo/Redo Pattern** - ✅ Implementiert
   - `useZoneDragDrop.ts`: Vollständige History-Stack-Implementierung
   - `undo()`, `redo()`, `canUndo`, `canRedo`, `clearHistory()`
   - Max 20 Einträge, API-basiert mit Toast-Feedback

### Optionale Erweiterungen (Zukunft):

1. **Keyboard Shortcuts für Undo/Redo**
   - `Ctrl+Z` / `Ctrl+Y` im DashboardView
   - Event-Listener + Composable-Integration

2. **Performance-Optimierungen**
   - Virtual Scrolling für große Gerätelisten
   - Debounced WebSocket Updates

3. **UX-Verbesserungen**
   - Copy-to-Clipboard für UUIDs
   - Expandable JSON-Viewer im RecordDetailModal

---

**Letzte Aktualisierung:** 2025-12-31
**Alle Tasks erledigt von:** Claude Code
