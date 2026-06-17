# MockEspView - UI Dokumentation

> ⚠️ **VERALTET - Stand 23.12.2025**
>
> Diese Dokumentation bezieht sich auf die **alte** `MockEspView`. Diese wurde refactored zu:
>
> | Alt | Neu | Route |
> |-----|-----|-------|
> | `MockEspView` | **`DevicesView`** | `/devices` |
> | `MockEspDetailView` | **`DeviceDetailView`** | `/devices/:espId` |
>
> **Für aktuelle Dokumentation siehe:**
> - [02-Individual-Views-Summary.md](02-Individual-Views-Summary.md) - DevicesView & DeviceDetailView
> - [VIEW_QUICK_REFERENCE.md](VIEW_QUICK_REFERENCE.md) - Schnellreferenz
>
> Die alte Route `/mock-esp` funktioniert weiterhin (Redirect zu `/devices`).

---

**Erstellt:** 2025-12-19
**Status:** ⚠️ VERALTET - Redirect zu DevicesView
**Priorität:** 🟢 Legacy

---

## 1. Metadaten (Legacy)

| Attribut | Wert |
|----------|------|
| **Route** | `/mock-esp` → **Redirect zu `/devices`** |
| **Datei** | `src/views/MockEspView.vue` → **Jetzt `DevicesView.vue`** |
| **Auth erforderlich** | ✅ Login (nicht mehr Admin-only) |
| **Admin erforderlich** | ❌ |
| **Status** | ⚠️ Legacy - Redirect |
| **Komponenten** | ESPCard, ESPOrbitalLayout, LoadingState, EmptyState, ErrorState |
| **Stores** | `useEspStore` (Unified Store, ersetzt `useMockEspStore`) |
| **WebSocket** | ✅ Live-Updates via esp_health, sensor_data, actuator_status |

---

## 2. Zweck & Kontext

Diese View ist das **Verwaltungs-Dashboard für alle Mock-ESP32-Geräte** im System. Sie ermöglicht es Testern, virtuelle ESP-Geräte zu erstellen, zu filtern und zu löschen, ohne echte Hardware zu benötigen. Dies ist die Basis für die gesamte Mock-Hardware-Testinfrastruktur.

**Kritisch für:**
- Mock-Hardware-Simulation
- End-to-End Testing
- Entwicklung von ESP-abhängigen Features (Sensoren, Aktoren)
- Lastests ohne echte Hardware

---

## 3. UI-Layout (ASCII-Wireframe)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header]                                                            │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ H1: "ESP-Geräte"                                               │  │
│ │ Subtitle: "Mock-ESP32-Geräte erstellen und verwalten"          │  │
│ │                                                     [🔄 Refresh] │  │
│ │                                                [➕ Mock ESP erstellen] │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ [Error Alert - if error exists]                                    │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ ⚠️ Error message with [Retry] [Dismiss] buttons                │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ [Filter Bar]                                                        │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ Typ:                                                            │  │
│ │   [Alle (12)]  [Mock (8)]  [Real (4)]                          │  │
│ │                                                                │  │
│ │ Status:                                                         │  │
│ │   [Alle]  [Online (11)]  [Offline (1)]                         │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ [Main Content - ESP Grid]                                          │
│ ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────┐   │
│ │ [ESPCard #1]         │  │ [ESPCard #2]         │  │ [ESP #3] │   │
│ │ ESP_MOCK_A1B2C3      │  │ ESP_MOCK_D4E5F6      │  │ ESP_REA_ │   │
│ │ ✓ Online · MOCK      │  │ ⚠ Safe Mode · MOCK   │  │ ✓ Online │   │
│ │ 5 Sensors · 3 Actuators│  │ 2 Sensors · 1 Actuator│ │ 8 Sensors│   │
│ │                      │  │                      │  │ 4 Actuators│   │
│ │ [❤️ HB] [🛡️ Safe] [🗑️]│  │ [❤️ HB] [🛡️ Safe] [🗑️]│  │ [💬 Edit] │   │
│ └──────────────────────┘  └──────────────────────┘  │ [🗑️ Delete]│   │
│ ┌──────────────────────┐  ┌──────────────────────┐  └──────────┘   │
│ │ [ESPCard #4]         │  │ [ESPCard #5]         │                  │
│ │ ...                  │  │ ...                  │                  │
│ └──────────────────────┘  └──────────────────────┘                  │
│                                                                     │
│ [Modal Overlay - when Create button clicked]                       │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ 📝 Mock ESP erstellen                                          [X] │
│ ├────────────────────────────────────────────────────────────────┤  │
│ │                                                                │  │
│ │ Label: "ESP ID"                                               │  │
│ │ [ESP_MOCK_XXXXXX] [🔄 Generate]  Format: ESP_MOCK_XXXXXX     │  │
│ │                                                                │  │
│ │ Label: "Zone (optional)"                                      │  │
│ │ [Eingabe: z.B. gewächshaus]                                   │  │
│ │                                                                │  │
│ │ ☑️ Auto-Heartbeat aktivieren                                   │  │
│ │                                                                │  │
│ │ Label: "Heartbeat-Intervall (Sekunden)" [IF auto_heartbeat]   │  │
│ │ [60] ← Min: 5, Max: 300                                       │  │
│ │                                                                │  │
│ ├────────────────────────────────────────────────────────────────┤  │
│ │ [Abbrechen]              [Erstellen]                          │  │
│ └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Datenquellen

### 4.1 API-Endpoints

| Endpoint | Methode | Zweck | Wann aufgerufen |
|----------|---------|-------|-----------------|
| `/debug/mock-esp` | GET | Liste aller Mock-ESPs abrufen | Bei Mount (`mockEspStore.fetchAll()`) |
| `/debug/mock-esp` | POST | Neues Mock-ESP erstellen | Klick auf "Mock ESP erstellen" + "Erstellen" im Modal |
| `/debug/mock-esp/{espId}` | DELETE | Mock-ESP löschen | Klick auf Delete-Button + Bestätigung |

### 4.2 Pinia Stores

| Store | Verwendete Properties/Actions |
|-------|-----|
| `mockEspStore` | `mockEsps` (State), `isLoading`, `error`, `fetchAll()`, `create()`, `remove()`, `triggerHeartbeat()`, `setState()` |

### 4.3 WebSocket

❌ Nicht verwendet

---

## 5. UI-Komponenten

### 5.1 Verwendete Komponenten

| Komponente | Pfad | Zweck |
|------------|------|-------|
| `ESPCard` | `src/components/esp/ESPCard.vue` | Einzelne ESP-Geräte anzeigen (Status, Sensoren, Aktoren, Actions) |
| `LoadingState` | `src/components/common/LoadingState.vue` | Loading-Spinner wenn Daten geladen werden |
| `EmptyState` | `src/components/common/EmptyState.vue` | Leere Liste mit CTA "Mock ESP erstellen" |
| `ErrorState` | `src/components/common/ErrorState.vue` | Fehler-Banner mit [Retry] [Dismiss] Buttons |

### 5.2 Komponenten-Hierarchie

```
MockEspView.vue (root)
├── Header (inline)
├── ErrorState (conditional)
├── Filter Bar (inline)
├── LoadingState (conditional)
├── EmptyState (conditional)
├── Grid von ESPCard (v-for)
│   └── ESPCard (child)
│       ├── Status Indicator
│       ├── ESP-ID + Badge (Mock/Real)
│       ├── Sensor/Actuator Count
│       └── Action Buttons (HB, Safe-Mode, Delete)
└── Modal Overlay (Teleport to body)
    └── Create Form
        ├── ESP-ID Input + Generate Button
        ├── Zone Input
        ├── Auto-Heartbeat Checkbox
        ├── Heartbeat Interval Input (conditional)
        └── Buttons: Cancel, Create
```

---

## 6. User-Interaktionen

| Aktion | UI-Element | Resultat |
|--------|------------|----------|
| **Seite laden** | (Auto) | `mockEspStore.fetchAll()` → ESPs laden |
| **Klick [Refresh]** | Button (Header) | `mockEspStore.fetchAll()` → ESPs neuladen |
| **Klick [Mock ESP erstellen]** | Button (Header) | Modal öffnet sich mit Generator für ESP-ID |
| **Klick [🔄]** | Button (Modal) | Neue ESP-ID generiert: `ESP_MOCK_XXXXXX` |
| **Input ESP-ID** | Textfeld (Modal) | `newEsp.esp_id` aktualisiert |
| **Input Zone** | Textfeld (Modal) | `newEsp.zone_id` aktualisiert |
| **Toggle Auto-Heartbeat** | Checkbox (Modal) | `newEsp.auto_heartbeat` toggled, Interval-Input conditional |
| **Input Heartbeat Interval** | Number Input (Modal) | `newEsp.heartbeat_interval_seconds` aktualisiert |
| **Klick [Abbrechen]** | Button (Modal) | Modal schließt sich, kein API-Call |
| **Klick [Erstellen]** | Button (Modal) | `mockEspStore.create(newEsp)` → POST `/debug/mock-esp` |
| **Typ-Filter** | Toggle Buttons | `filterType` aktualisiert → `filteredEsps` gefiltert |
| **Status-Filter** | Toggle Buttons | `filterStatus` aktualisiert → `filteredEsps` gefiltert |
| **Klick [❤️ HB] auf Card** | Button (ESPCard) | `mockEspStore.triggerHeartbeat(espId)` → MQTT Heartbeat auslösen |
| **Klick [🛡️ Safe] auf Card** | Button (ESPCard) | `mockEspStore.setState(espId, newState)` → OPERATIONAL ↔ SAFE_MODE toggled |
| **Klick [🗑️] auf Card** | Button (ESPCard) | Bestätigungs-Dialog → `mockEspStore.remove(espId)` → DELETE `/debug/mock-esp/{espId}` |

---

## 7. Aktuelle Implementierung

### 7.1 Was funktioniert ✅

- ✅ **ESP-List laden** - Store ruft GET `/debug/mock-esp` auf, ESPs werden in Grid angezeigt
- ✅ **Typ-Filter** - Toggle zwischen Alle/Mock/Real
- ✅ **Status-Filter** - Toggle zwischen Alle/Online/Offline
- ✅ **Filter-Counts** - Badges zeigen Anzahl pro Filter
- ✅ **ESP-ID Generator** - Generiert zufällige ID im Format `ESP_MOCK_XXXXXX`
- ✅ **Modal Create-Form** - Form für neues ESP mit Validierung
- ✅ **Auto-Heartbeat Config** - Toggle + Interval-Input (5-300 Sekunden)
- ✅ **Delete mit Bestätigung** - `confirm()` Dialog vor Löschen
- ✅ **Error Handling** - ErrorState zeigt Fehler mit Retry-Option
- ✅ **Loading States** - LoadingState spinner bei Datenladeung
- ✅ **Empty State** - EmptyState mit CTA "Mock ESP erstellen"
- ✅ **Heartbeat Trigger** - Button um Heartbeat manuell auszulösen
- ✅ **Safe-Mode Toggle** - Button um ESP zwischen OPERATIONAL und SAFE_MODE zu wechseln

### 7.2 Was fehlt / ist Placeholder ❌

- ❌ **Config Export/Import** - Kein Button um Mock-ESP-Config zu exportieren (z.B. JSON)
- ❌ **Bulk Operations** - Kein Bulk-Delete, Bulk-State-Change
- ❌ **Search** - Keine Such-Funktion für ESPs nach ID
- ❌ **Sorting** - Keine Sortierungs-Optionen (nach Status, Sensor-Count, etc.)
- ❌ **Pagination** - Keine Pagination wenn > 20 ESPs (GridView wird voll)
- ❌ **CSV Import** - Kein Button um Mock-ESPs aus CSV zu importieren
- ❌ **Duplicate ESP** - Kein "Duplicate" Button um ESP mit allen Sensoren/Aktoren zu klonen
- ❌ **Tag/Label System** - Keine Tags um ESPs zu kategorisieren

### 7.3 Bekannte Bugs 🐛

- 🐛 **Filter Reset nicht sichtbar** - Button "Filter zurücksetzen" nur sichtbar wenn keine Ergebnisse (sollte immer sichtbar sein)
- 🐛 **Modal kann außer-ESPCard angeklickt werden** - Kann irgendwo außerhalb des Modal klicken um zu schließen (gewollt? prüfen)

---

## 8. Geplante Erweiterungen

| Feature | Priorität | Abhängigkeiten | Details |
|---------|-----------|----------------|---------|
| **Config Export (JSON/YAML)** | Hoch | Keine | Einen "Download Config" Button hinzufügen pro ESP. Format: JSON mit esp_id, sensors[], actuators[], zone_id |
| **Bulk Import (CSV)** | Mittel | CSV Parser Library | Button zum Hochladen von CSV mit Mock-ESP-Definitionen. Format: esp_id,zone_id,sensor_count,actuator_count |
| **Search Bar** | Mittel | Keine | Suchfeld um ESPs nach ID zu suchen (client-side) |
| **Sorting** | Mittel | Keine | Dropdown: "Sort by: Status, Sensors, Actuators, Created Date" |
| **Pagination** | Mittel | Keine | Wenn > 20 ESPs, Pagination hinzufügen (20 pro Seite) |
| **Duplicate ESP** | Niedrig | Keine | Button um ESP zu klonen mit allen Sensoren/Aktoren |
| **Tag System** | Niedrig | Backend-API ändern | Tags hinzufügen um ESPs zu kategorisieren (z.B. "Test-Gruppe-1") |
| **Advanced Filters** | Niedrig | Keine | Filter nach Sensor-Type, Actuator-Type |

---

## 9. API-Payload-Beispiele

### 9.1 GET /debug/mock-esp

**Response 200:**
```json
[
  {
    "esp_id": "ESP_MOCK_A1B2C3",
    "hardware_type": "MOCK_ESP32_DEV",
    "connected": true,
    "system_state": "OPERATIONAL",
    "zone_id": "gewächshaus",
    "auto_heartbeat": true,
    "heartbeat_interval_seconds": 60,
    "sensors": [
      {
        "gpio": 34,
        "sensor_type": "temperature",
        "name": "Temperatur",
        "quality_level": 10,
        "raw_value": 25.5,
        "pi_enhanced": true
      }
    ],
    "actuators": [
      {
        "gpio": 25,
        "actuator_type": "pump",
        "name": "Pumpe",
        "state": false,
        "emergency_stopped": false
      }
    ],
    "last_heartbeat": "2025-12-19T10:30:00Z",
    "created_at": "2025-12-19T08:00:00Z",
    "updated_at": "2025-12-19T10:30:00Z"
  }
]
```

### 9.2 POST /debug/mock-esp

**Request:**
```json
{
  "esp_id": "ESP_MOCK_X1Y2Z3",
  "zone_id": "grow_room_a",
  "auto_heartbeat": true,
  "heartbeat_interval_seconds": 60,
  "sensors": [],
  "actuators": []
}
```

**Response 201:**
```json
{
  "esp_id": "ESP_MOCK_X1Y2Z3",
  "hardware_type": "MOCK_ESP32_DEV",
  "connected": true,
  "system_state": "OPERATIONAL",
  "zone_id": "grow_room_a",
  "auto_heartbeat": true,
  "heartbeat_interval_seconds": 60,
  "sensors": [],
  "actuators": [],
  "last_heartbeat": null,
  "created_at": "2025-12-19T10:35:00Z",
  "updated_at": "2025-12-19T10:35:00Z"
}
```

### 9.3 DELETE /debug/mock-esp/{espId}

**Response 204:** No Content

---

## 10. Code-Referenzen

| Datei | Zeilen | Beschreibung |
|-------|--------|--------------|
| `src/views/MockEspView.vue` | 1-124 | Hauptlogik und Template |
| `src/components/esp/ESPCard.vue` | - | Kind-Komponente für einzelne ESP-Anzeige |
| `src/stores/mockEsp.ts` | - | Pinia Store mit fetchAll(), create(), remove(), etc. |
| `src/types/index.ts` | - | Type-Definitionen für MockESP, MockESPCreate, MockSystemState |
| `src/api/debug.ts` | - | API-Funktionen für `/debug/mock-esp` |

---

## 11. Verifiziert

- [x] Route korrekt (`/mock-esp`)
- [x] Alle API-Calls dokumentiert (GET, POST, DELETE)
- [x] Alle Komponenten aufgelistet (ESPCard, LoadingState, EmptyState, ErrorState)
- [x] Wireframes aktuell (ASCII-Layout entspricht tatsächlicher UI)
- [x] Filter-Logik dokumentiert (Typ + Status)
- [x] Modal-Flow dokumentiert
- [x] Fehlerfall dokumentiert (ErrorState)
- [x] Leerer-Fall dokumentiert (EmptyState)
- [x] Loading-Fall dokumentiert (LoadingState)

---

## 12. Next Steps (für Ausbau)

**Für zukünftige Entwicklung (zz. Basis für Mock-ESP Erweiterung):**

1. **Config Management** - Export/Import von Mock-ESP-Konfigurationen
2. **Batch Operations** - Mehrere ESPs gleichzeitig verwalten
3. **Template System** - Vordefinierte Mock-ESP-Templates (z.B. "Temperatur-Sensor Setup")
4. **Simulation Advanced** - ESP-Verhalten simulieren (z.B. Verbindungsabbruch, Fehler)
5. **MockEspDetailView Integration** - Detail-View für einzelnes ESP (Sensoren/Aktoren konfigurieren)

