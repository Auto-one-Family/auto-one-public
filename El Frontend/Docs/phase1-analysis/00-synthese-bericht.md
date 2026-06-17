# Phase 1 Analyse - Synthese-Bericht

**Datum:** 2026-01-27
**Zweck:** Implementierungsgrundlage für Event-Verknüpfung Quick Wins (Features 1.1, 1.2, 1.3)

---

## 1. Feature 1.1: "Alle Events dieses Geräts anzeigen" Button

### Implementierungs-Ort

- **Datei:** `EventDetailsPanel.vue`
- **Zeile:** 433 (nach letztem `detail-item`, vor `</div>` des `details-grid`)
- **Section:** DETAILS (Zeilen 405-434)

### Benötigte Änderungen

| Datei | Änderung | Zeilen |
|-------|----------|--------|
| `EventDetailsPanel.vue` | Neuen Emit `filter-device` hinzufügen | 61-63 |
| `EventDetailsPanel.vue` | Button-Template einfügen | 433 |
| `SystemMonitorView.vue` | Event-Listener `@filter-device` am EventDetailsPanel | 1369-1374 |
| `SystemMonitorView.vue` | Handler: `filterEspId` setzen + Panel schließen + Tab auf `events` | ~1055 |

### Code-Vorlage

**EventDetailsPanel.vue - Emit erweitern (Zeile 61-63):**
```typescript
const emit = defineEmits<{
  close: []
  'filter-device': [espId: string]
  'show-server-logs': [event: UnifiedEvent]
}>()
```

**EventDetailsPanel.vue - Button-Template (Zeile 433):**
```html
<!-- Action Buttons -->
<div v-if="event.esp_id" class="detail-item detail-item--full detail-item--actions">
  <button class="action-btn action-btn--filter" @click="emit('filter-device', event.esp_id!)">
    <Filter :size="14" />
    Alle Events dieses Geräts
  </button>
</div>
```

**SystemMonitorView.vue - Handler (Template Zeile ~1373):**
```html
<EventDetailsPanel
  :event="selectedEvent"
  :event-type-labels="EVENT_TYPE_LABELS"
  @close="selectedEvent = null"
  @filter-device="handleFilterDevice"
  @show-server-logs="handleShowServerLogs"
/>
```

```typescript
function handleFilterDevice(espId: string) {
  filterEspId.value = espId
  activeTab.value = 'events'
  selectedEvent.value = null  // Panel schließen
}
```

### CSS für Action-Button

Basierend auf `.json-copy-btn` Pattern (Zeile 1121-1138):
```css
.detail-item--actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 0.5rem;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.action-btn--filter:hover {
  border-color: rgba(96, 165, 250, 0.3);
  color: #60a5fa;
}
```

### Offene Fragen
- Keine. Alle Mechanismen existieren bereits (filterEspId, ESP-Filter-Watcher).

---

## 2. Feature 1.2: "Server-Logs anzeigen" Link

### Implementierungs-Ort

- **Datei (Button):** `EventDetailsPanel.vue`, Zeile 433 (gleiche Actions-Section wie 1.1)
- **Datei (Empfang):** `ServerLogsTab.vue` + `SystemMonitorView.vue`

### Benötigte Änderungen

| Datei | Änderung | Zeilen |
|-------|----------|--------|
| `EventDetailsPanel.vue` | Button/Link einfügen | 433 (zusammen mit 1.1) |
| `EventDetailsPanel.vue` | Emit `show-server-logs` hinzufügen | 61-63 (bereits in 1.1 definiert) |
| `SystemMonitorView.vue` | Event-Listener + Handler | ~1373, ~1060 |
| `SystemMonitorView.vue` | Neue State-Variablen für Log-Zeitfenster | ~228 |
| `SystemMonitorView.vue` | Props an ServerLogsTab übergeben | 1351-1353 |
| `ServerLogsTab.vue` | Props für `initialStartTime`/`initialEndTime` akzeptieren | Neue `defineProps` |
| `ServerLogsTab.vue` | Props in `currentQueryParams` einbinden | 130-137 |

### Code-Vorlage

**EventDetailsPanel.vue - Button (Zeile 433, nach Filter-Button):**
```html
<button class="action-btn action-btn--logs" @click="emit('show-server-logs', event)">
  <FileText :size="14" />
  Server-Logs ±30s
</button>
```

**SystemMonitorView.vue - State + Handler:**
```typescript
// Neue State-Variablen (~Zeile 228)
const logsStartTime = ref<string | undefined>()
const logsEndTime = ref<string | undefined>()

function handleShowServerLogs(event: UnifiedEvent) {
  const ts = new Date(event.timestamp).getTime()
  logsStartTime.value = new Date(ts - 30000).toISOString()
  logsEndTime.value = new Date(ts + 30000).toISOString()
  activeTab.value = 'logs'
  selectedEvent.value = null
}
```

**SystemMonitorView.vue - Props an ServerLogsTab (Zeile 1351-1353):**
```html
<ServerLogsTab
  v-else-if="activeTab === 'logs'"
  :initial-start-time="logsStartTime"
  :initial-end-time="logsEndTime"
/>
```

**ServerLogsTab.vue - Props akzeptieren:**
```typescript
const props = defineProps<{
  initialStartTime?: string
  initialEndTime?: string
}>()
```

**ServerLogsTab.vue - In currentQueryParams einbinden (Zeile 130-137):**
```typescript
const currentQueryParams = computed<LogQueryParams>(() => ({
  level: selectedLevel.value || undefined,
  module: moduleFilter.value || undefined,
  search: searchQuery.value || undefined,
  file: selectedFile.value || undefined,
  page: page.value,
  page_size: PAGE_SIZE,
  start_time: startTime.value || undefined,  // NEU
  end_time: endTime.value || undefined,       // NEU
}))
```
Plus State-Initialisierung aus Props im `onMounted`.

### API-Anpassung nötig?

- **`start_time`/`end_time`:** NEIN - bereits in `LogQueryParams` (logs.ts Zeilen 55-56) und API-Client (Zeilen 119-120) definiert. Nur im Component nicht genutzt.
- **`esp_id`:** JA, falls gewünscht - existiert weder in API-Client noch Server. Für Phase 1 nicht nötig (Zeitfenster reicht für Korrelation).

### Offene Fragen

- Soll der Log-Zeitfilter nach Tab-Wechsel zurück zu Events automatisch gelöscht werden? (Empfehlung: Ja, `logsStartTime`/`logsEndTime` beim Tab-Wechsel zurücksetzen)
- Soll der ESP-ID-Filter auch in den Logs-Tab übernommen werden? (Phase 2, erfordert Server-Änderung)

---

## 3. Feature 1.3: Event-Highlighting bei ESP-Filter

### Implementierungs-Ort

- **Datei:** `UnifiedEventList.vue`
- **Prop-Definition:** Zeile 53-58 (Props Interface)
- **Class-Binding:** Zeile 474-477 (Virtual Scroll) + Zeile 547-550 (Non-Virtual)
- **CSS:** Nach Zeile 1063 (nach `badge-pop` Keyframe)

### Benötigte Änderungen

| Datei | Änderung | Zeilen |
|-------|----------|--------|
| `UnifiedEventList.vue` | Prop `highlightedEspId` hinzufügen | 53-62 |
| `UnifiedEventList.vue` | CSS-Klasse `event-item--highlighted` in beiden Render-Pfaden | 474-477, 547-550 |
| `UnifiedEventList.vue` | CSS Animation + Styles | nach 1063 |
| `EventsTab.vue` | Prop `highlightedEspId` durchreichen | Prop-Binding |
| `SystemMonitorView.vue` | `highlightedEspId` Prop an EventsTab übergeben | 1325-1348 |

### Animation-Spezifikation

```css
/* ESP-Filter Highlight - nach Zeile 1063 */
.event-item--highlighted {
  animation: esp-highlight-pulse 2s ease-out;
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.2);
}

@keyframes esp-highlight-pulse {
  0% {
    background-color: rgba(96, 165, 250, 0.15);
  }
  100% {
    background-color: rgba(96, 165, 250, 0.04);
  }
}

.event-item--highlighted:hover {
  background-color: rgba(96, 165, 250, 0.08);
}

/* ESP-ID Badge innerhalb hervorgehobener Events */
.event-item--highlighted .event-item__esp {
  background-color: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}
```

### Trigger-Logik

- **Wann startet Animation?** Wenn `filterEspId` gesetzt wird (nicht leer)
- **Welche Events?** Alle Events wo `event.esp_id === filterEspId`
- **Wie lange?** 2s ease-out Fade (Animation), danach statischer leichter Tint (0.04 alpha)
- **Wann endet?** Wenn `filterEspId` geleert wird → Klasse entfällt → CSS Transition zurück

### Prop-Durchreichung

```
SystemMonitorView (filterEspId)
  → EventsTab (prop: highlightedEspId)
    → UnifiedEventList (prop: highlightedEspId)
      → :class="{ 'event-item--highlighted': highlightedEspId && event.esp_id === highlightedEspId }"
```

### Offene Fragen

- Soll ein Scroll-to-First-Match implementiert werden? (Empfehlung: Phase 2, da Virtual Scroll es komplex macht)
- Sollen Events die NICHT matchen abgedimmt werden? (Empfehlung: Nein, der Filter entfernt sie bereits aus der Liste)

---

## 4. Risiken & Abhängigkeiten

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| ServerLogsTab `v-if` zerstört Component bei Tab-Wechsel → Props gehen verloren | Hoch | Props im Parent (SystemMonitorView) halten, Component liest Props in `onMounted` |
| Virtual Scroll Mode fehlt `restored` Styling → könnte auch `highlighted` fehlen | Mittel | Explizit beide Render-Pfade (Zeile 474 + 547) aktualisieren |
| `start_time`/`end_time` API-Parameter vom Server nicht unterstützt | Niedrig | API-Client unterstützt sie bereits (logs.ts Zeile 119-120), Server-Endpoint prüfen |
| useQueryFilters Composable existiert aber wird nicht genutzt → Inkonsistenz | Info | Für Phase 1 ignorieren, Phase 2 könnte Migration beinhalten |

## 5. Zusammenfassung der Dateien-Änderungen

| Datei | Feature 1.1 | Feature 1.2 | Feature 1.3 |
|-------|:-----------:|:-----------:|:-----------:|
| `EventDetailsPanel.vue` | ✅ Emit + Button | ✅ Emit + Button | - |
| `SystemMonitorView.vue` | ✅ Handler | ✅ State + Handler + Props | ✅ Prop weiterreichen |
| `ServerLogsTab.vue` | - | ✅ Props + State-Init | - |
| `UnifiedEventList.vue` | - | - | ✅ Prop + CSS + Class |
| `EventsTab.vue` | - | - | ✅ Prop durchreichen |

**Gesamtumfang:** 5 Dateien, keine neuen Dateien, keine API-Server-Änderungen nötig.
