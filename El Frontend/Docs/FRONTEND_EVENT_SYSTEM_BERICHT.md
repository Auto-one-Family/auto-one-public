# Frontend Event-System - Analyse-Bericht

**Datum:** 2026-01-27
**Analyst:** Claude (KI-Agent)
**Scope:** Frontend-Anbindung (System Monitor, Toasts, Dashboard) - alle Event-Patterns

---

## Executive Summary

Das AutomationOne Frontend empfangt Events uber ein **dreischichtiges WebSocket-System** (Singleton Service -> Composable -> Pinia Store), das **14 definierte MessageTypes** kennt, von denen **10 aktiv gehandelt** werden. Der **ESP Store** ist der primaere Consumer und verteilt Updates reaktiv an Dashboard, System Monitor und Toasts. Die einzige aktive Korrelation ist **ESP-ID-basiert** -- das vollstaendig implementierte `correlation_id`-Feld im Backend wird **nirgends genutzt**. Zwei unabhaengige Toast-Systeme existieren parallel (Global + SystemMonitorView-lokal).

---

## 1. WebSocket-System

**Detail-Analyse:** [websocket-analysis.md](websocket-analysis.md)

### Architektur

```
Server (FastAPI WebSocket)
    |
WebSocketService (Singleton)         -- src/services/websocket.ts
    |
useWebSocket (Composable)            -- src/composables/useWebSocket.ts
    |
Pinia Stores / Vue Components        -- src/stores/esp.ts (primaerer Consumer)
```

### Verbindung

| Eigenschaft | Wert |
|-------------|------|
| URL | `ws[s]://{host}/api/v1/ws/realtime/{client_id}?token={jwt}` |
| Auth | JWT als Query-Parameter |
| Reconnect | Exponential Backoff (1s-30s), max 10 Versuche, +/-10% Jitter |
| Token-Refresh | Automatisch vor Reconnect wenn Token in <60s ablaeuft |
| Tab-Visibility | Reconnect bei Tab-Wechsel, Attempt-Counter -2 |

### Event-Distribution (Zwei parallele Mechanismen)

1. **Filter-basierte Subscriptions:** `subscribe(filters, callback)` mit AND-Logik (types, esp_ids, sensor_types, topicPattern)
2. **Typ-basierte Listener:** `on(type, callback)` fuer einzelne Event-Types

### 14 Definierte MessageTypes

| MessageType | Aktiv gehandelt | Server-Quelle |
|-------------|-----------------|---------------|
| `sensor_data` | Ja | sensor_handler.py |
| `actuator_status` | Ja | actuator_handler.py |
| `actuator_response` | **Nein** (definiert, nicht subscribed) | actuator_response_handler.py |
| `actuator_alert` | Ja | actuator_alert_handler.py |
| `esp_health` | Ja | heartbeat_handler.py |
| `sensor_health` | Ja | maintenance/sensor_health.py |
| `config_response` | Ja | config_handler.py |
| `zone_assignment` | Ja | zone_ack_handler.py |
| `device_discovered` | Ja | Discovery Phase |
| `device_approved` | Ja | Discovery Phase |
| `device_rejected` | Ja | Discovery Phase |
| `device_rediscovered` | **Nein** (ungenutzt) | Discovery Phase |
| `logic_execution` | **Nein** (Zukunft) | Logic Engine |
| `system_event` | **Nein** (Zukunft) | System |

---

## 2. System Monitor Event-Handling

**Detail-Analyse:** [system-monitor-analysis.md](system-monitor-analysis.md)

### Event-Quellen

| Quelle | API-Key | API-Endpoint | WebSocket? |
|--------|---------|--------------|------------|
| Audit-Logs | `audit_log` | `/audit/events/aggregated` | Ja (31 Event-Types) |
| Sensor-Daten | `sensor_data` | `/audit/events/aggregated` | Ja |
| ESP-Health | `esp_health` | `/audit/events/aggregated` | Ja |
| Aktoren | `actuators` | `/audit/events/aggregated` | Ja |
| Server-Logs | - | `/debug/logs` (Polling 3s) | Nein |
| MQTT Traffic | - | - | Ja (eigene Subscription) |

### Event-Transformation (Zwei Layer)

1. **WebSocket -> UnifiedEvent** (`SystemMonitorView.vue:421-455`): Extrahiert esp_id, gpio, severity, source; generiert deutsche Zusammenfassung
2. **API -> UnifiedEvent** (`SystemMonitorView.vue:1004-1049`): Normalisiert Timestamps zu UTC, mappt dataSource
3. **Display-Transformation** (`eventTransformer.ts`): 4 Kategorien (esp-status/blue, sensors/emerald, actuators/amber, system/violet)

### Filtering

| Filter | Server-seitig | Client-seitig | Persistenz |
|--------|---------------|---------------|------------|
| DataSource | `sources[]` | `selectedDataSources` | State |
| Severity | `severity[]` (nur audit_log) | `filterLevels` Set | State |
| ESP-ID | `espIds[]` | Substring-Match | State |
| Zeitraum | `hours` | Preset/Custom Date | State |

Debounce: 300ms vor API-Reload bei Filteraenderung.

### Pagination

Cursor-basiert (`before_timestamp`), kein Offset. Max 10.000 Events im Speicher. Infinite Scroll.

---

## 3. Toast-Notification-System

**Detail-Analyse:** [toast-analysis.md](toast-analysis.md)

### Zwei unabhaengige Systeme

| System | Datei | Verwendet von |
|--------|-------|---------------|
| **Global** (`useToast`) | `composables/useToast.ts` + `ToastContainer.vue` | ESP Store, ZoneDragDrop, ESPOrbitalLayout, SensorValueCard |
| **Lokal** | `SystemMonitorView.vue:233-419` | Nur SystemMonitorView (Backup-Restore) |

### Toast-Types (Global)

| Type | Icon | Farbe | Auto-Close |
|------|------|-------|------------|
| success | CheckCircle | Gruen (#34d399) | 5000ms |
| error | XCircle | Rot (#f87171) | 8000ms |
| warning | AlertTriangle | Amber (#fbbf24) | 5000ms |
| info | Info | Blau (#60a5fa) | 5000ms |

### 7 Automatische WebSocket-Toast-Trigger

| WebSocket-Event | Toast-Type | Nachricht |
|-----------------|------------|-----------|
| `esp_health` (source=lwt) | warning | "{name}: Verbindung unerwartet verloren" |
| `config_response` (success) | success | "{name}: {message}" |
| `config_response` (partial) | warning + error (Details) | Zusammenfassung + bis zu 3 Detail-Toasts |
| `config_response` (error) | error (Summary + Details) | Error-Code + bis zu 3 GPIO-Details |
| `device_discovered` | info | "Neues Geraet entdeckt: {id}" |
| `device_approved` | success | "Geraet {id} wurde genehmigt" |
| `device_rejected` | warning | "Geraet {id} wurde abgelehnt" |

### 32 Gesamte Toast-Trigger (5 Dateien)

- `stores/esp.ts`: 18 Aufrufe (WebSocket-Handler + REST-Responses)
- `useZoneDragDrop.ts`: 8 Aufrufe (Zone-Operationen mit Retry-Actions)
- `ESPOrbitalLayout.vue`: 14 Aufrufe (Sensor/Aktor CRUD)
- `SensorValueCard.vue`: 2 Aufrufe (On-Demand Messung)
- `SystemMonitorView.vue`: 1 Aufruf (lokales System, Backup-Restore)

### Bekannte Probleme

- **Kein Max-Limit** fuer sichtbare Toasts (unbegrenzt stackbar)
- **Keine Deduplizierung** (identische Nachrichten mehrfach moeglich)
- **Zwei separate Systeme** (Global vs. SystemMonitorView-lokal)

---

## 4. Dashboard Event-Integration

**Detail-Analyse:** [dashboard-analysis.md](dashboard-analysis.md)

### 9 Widgets/Sektionen

| Widget | Datenquelle | Update-Mechanismus |
|--------|-------------|-------------------|
| ActionBar (Status-Pillen) | `espStore` computed getters | Reaktiv via Store |
| Zone Groups + ESPOrbitalLayout | `espStore.devices` -> `zoneGroups` | WebSocket + reaktive Computed |
| Cross-ESP Connection Overlay | `logicStore.crossEspConnections` | WebSocket `logic_execution` |
| Component Sidebar | Statisch (Sensor/Aktor-Typen) | Kein Update noetig |
| Unassigned Drop Bar | `espStore.devices.filter(!zone_id)` | Reaktiv |
| Pending Devices Panel | `espStore.pendingDevices` | WebSocket `device_discovered/approved/rejected` |
| ESP Settings Popover | Einzelnes Device aus Store | Reaktiv |

### Datenfluss

```
REST API (onMounted)  ──> espStore.devices ──> DashboardView computed
WebSocket (live)      ──/                        |
                                                  ├── filteredEsps (Type + Status Filter)
                                                  ├── zoneGroups (groupDevicesByZone)
                                                  ├── onlineCount / offlineCount
                                                  └── problemMessage
```

### Status-Indikatoren

| Zustand | Linke Border-Farbe | Badge | Opacity |
|---------|-------------------|-------|---------|
| Online (Mock) | Purple | "Online" (gruen) | 100% |
| Online (Real) | Cyan | "Online" (gruen) | 100% |
| Offline | Grau | "Offline" (grau) | 70% |
| Safe Mode | Gelb (pulsierend) | "Sicherheitsmodus" (gelb) | 100% |
| Error | Rot | "Fehler" (rot) | 100% |
| Emergency Stop | Rot (pulsierend) | "E-STOP" (rot) | 100% |
| Orphaned Mock | Gelb (pulsierend) | "Verwaist" (gelb) | 100% |

### Kein Polling

Das Dashboard nutzt **ausschliesslich WebSocket-Events** fuer Live-Updates. Kein setInterval, kein Pull-to-Refresh. Bei WebSocket-Reconnect: Full `fetchAll()`.

---

## 5. Event-Korrelation

**Detail-Analyse:** [correlation-analysis.md](correlation-analysis.md)

### Aktuell implementiert

| Korrelations-Typ | Status | Wo |
|------------------|--------|-----|
| ESP-ID Filterung | **Ja** | SystemMonitor, SensorsView, MqttTrafficTab, WebSocket, Audit API |
| Deep-Link ESP -> gefilterter View | **Ja** | `useQueryFilters.ts` |
| Server-seitige ESP-Filterung | **Ja** | Audit API `esp_ids` Parameter |
| WebSocket ESP-Filterung | **Ja** | Client-seitig in websocket.ts |
| Cross-ESP Logic Visualisierung | **Ja** | logicStore + CrossEspConnectionOverlay |
| `correlation_id` Nutzung | **Nein** | Feld existiert end-to-end, aber **nie befuellt** |
| Event-Chain Darstellung | **Nein** | config_published -> config_response nicht verknuepft |
| Zeitfenster-Gruppierung | **Nein** | Kein visuelles Clustering |
| Log-zu-Audit Cross-Referenz | **Nein** | Kein gemeinsamer Identifier |

### Kritischer Befund: `correlation_id`

Die gesamte Infrastruktur existiert:
1. DB-Model mit Index (`audit_log.py:156`)
2. API gibt es zurueck (`audit.py:52,362,593,630`)
3. Frontend-Type definiert es (`audit.ts:29`)
4. DB-Column-Translator labelt es (`databaseColumnTranslator.ts:761-765`)

**Aber:** Der Server setzt `correlation_id` **nie** beim Erstellen von AuditLog-Eintraegen. Das Feature ist vollstaendig dormant.

---

## 6. UI-Patterns

**Detail-Analyse:** [ui-patterns-analysis.md](ui-patterns-analysis.md)

### Farb-System (4 Kategorien + 4 Severity-Level)

| Kategorie | Farbe | Hex | Verwendet fuer |
|-----------|-------|-----|---------------|
| esp-status | Blau | #3B82F6 | Heartbeat, Online/Offline, Discovery |
| sensors | Emerald | #10B981 | Sensor-Daten, Sensor-Health |
| actuators | Amber | #F59E0B | Aktor-Status, Alerts |
| system | Violet | #8B5CF6 | Config, Auth, Errors, Lifecycle |

| Severity | Background-Tint | Animation |
|----------|----------------|-----------|
| info | Transparent | - |
| warning | Amber 3% | - |
| error | Rot 4% | - |
| critical | Rot 6% | Pulse (2s infinite) |

### Event-Zeile (UnifiedEventList)

```
[3px Category-Bar + Glow] [Icon 32x32] [HH:MM:SS] [Type + Summary] [Meta-Pillen] [Severity-Icon]
```

### Detail-Panel (EventDetailsPanel)

- Glassmorphism: `rgba(15,15,20,0.95)` + `blur(20px)`
- Fixed bottom, `max-height: 65vh`
- Kategorie-getoenete Top-Border
- Sektionen: Zusammenfassung -> Details -> Original-JSON
- Schliessen: Klick-Aussen, Swipe (Mobile), ESC-Taste

### 11 Animationen

Badge-Pop, Critical-Pulse, Restored-Glow, Category-Bar-Glow, Toast-Slide, Progress-Bar, JSON-Collapse, Picker-Scale, Close-Rotate, Hover-Lift, Standard-Transitions.

### Dark-Theme Only

Hardcoded, kein Light-Mode. 4-stufiges Background-Layering (#0a0a0f -> #22222e). Glassmorphism durchgehend. Iridescent-Gradient fuer Akzente.

---

## 7. Korrelations-Matrix (Frontend <-> Backend)

### WebSocket-Events -> UI-Komponenten

| WS-Event | Backend-Handler | Dashboard | System Monitor | Toast |
|----------|-----------------|-----------|----------------|-------|
| `sensor_data` | SensorHandler | Sensor-Werte aktualisiert | Event in Liste | Nein |
| `esp_health` | HeartbeatHandler | ESP-Card Status/RSSI/Heap | Event in Liste | Nur bei LWT (warning) |
| `actuator_status` | ActuatorHandler | Aktor-State aktualisiert | Event in Liste | Nein |
| `actuator_alert` | AlertHandler | Emergency-Flag gesetzt | Event in Liste | Nein |
| `config_response` | ConfigHandler | GPIO-Status Refresh | Event in Liste | Ja (success/warning/error) |
| `zone_assignment` | ZoneAckHandler | Zone-ID aktualisiert | Event in Liste | Nein |
| `sensor_health` | SensorHealthJob | Stale-Flag gesetzt | Event in Liste | Nein |
| `device_discovered` | Discovery | Pending-Liste + | Event in Liste | info |
| `device_approved` | Discovery | fetchAll() Refresh | Event in Liste | success |
| `device_rejected` | Discovery | Pending entfernt | Event in Liste | warning |

### Fehlende Frontend-Darstellungen

| Backend-Event | Aktuell im Frontend? | Empfehlung |
|---------------|---------------------|------------|
| `actuator_response` | **Nein** (Type definiert, nicht subscribed) | In ESP Store subscriben |
| `logic_execution` | **Nein** (reserviert) | Event in System Monitor anzeigen |
| `system_event` | **Nein** (reserviert) | Event in System Monitor anzeigen |
| `device_rediscovered` | **Nein** (definiert, ungenutzt) | Toast + Event |
| Sensor-Data Normal | Nur Dashboard-Widget | Optional in Event-Liste |
| Actuator-Command (gesendet) | Nein (nur Response) | Event erstellen + anzeigen |
| Server-Log <-> Audit | Nicht verknuepft | Link "Zeige zugehoerige Logs" |

---

## 8. Empfehlungen fuer Verknuepfungen

### 8.1 Quick Wins

1. **`actuator_response` subscriben** -- Type ist definiert, Handler fehlt im ESP Store
2. **Toast-Deduplizierung** -- Identische Nachrichten innerhalb 2s zusammenfassen
3. **Toast-Max-Limit** -- z.B. max 5 sichtbare Toasts, aelteste entfernen
4. **ESP-Filter vom Dashboard vorausfuellen** -- Klick auf ESP-Card "Logs" Button fuellt bereits ESP-ID im System Monitor (teilweise implementiert via `?esp=`)
5. **SystemMonitorView lokalen Toast entfernen** -- Globales `useToast` stattdessen verwenden

### 8.2 Mittelfristig

1. **`correlation_id` aktivieren** -- Server muss beim Erstellen von AuditLog-Eintraegen eine UUID setzen (z.B. config_published + config_response teilen eine ID)
2. **Event-Chain Darstellung** -- "Zeige verwandte Events" Button im Detail-Panel, gefiltert nach `correlation_id`
3. **Config-Latenz anzeigen** -- Zeit zwischen config_published und config_response
4. **Emergency-Stop Gruppierung** -- Alle betroffenen Aktoren visuell gruppieren

### 8.3 Langfristig

1. **Vollstaendiges Event-Tracing** -- ESP -> MQTT -> Server -> DB -> Frontend mit durchgehender Trace-ID
2. **Timeline-Ansicht** -- Chronologische Darstellung von Event-Chains pro ESP
3. **Log-Audit Cross-Referenz** -- Gemeinsamer Identifier zwischen Server-Logs und Audit-Events
4. **DataSource-Farben vereinheitlichen** -- DataSourceSelector-Farben weichen von Event-Kategorie-Farben ab (Sensors: blau vs. emerald)

---

## 9. Code-Referenzen

| Bereich | Datei | Schluessel-Zeilen |
|---------|-------|-------------------|
| WebSocket Service | [websocket.ts](../src/services/websocket.ts) | L42-79 (Singleton), L114 (URL), L258-265 (Reconnect) |
| WebSocket Composable | [useWebSocket.ts](../src/composables/useWebSocket.ts) | L153-174 (Dual Handler) |
| ESP Store WS-Handler | [esp.ts](../src/stores/esp.ts) | L1321-1898 (10 Handler), L1992-2027 (Init) |
| Event Transformer | [eventTransformer.ts](../src/utils/eventTransformer.ts) | L83-115 (Kategorien), L171-429 (Transformationen) |
| Event Type Icons | [eventTypeIcons.ts](../src/utils/eventTypeIcons.ts) | L59-109 (31 Icon-Mappings) |
| System Monitor | [SystemMonitorView.vue](../src/views/SystemMonitorView.vue) | L54-98 (31 WS-Types), L421-455 (Transform) |
| Unified Event List | [UnifiedEventList.vue](../src/components/system-monitor/UnifiedEventList.vue) | L682-704 (Kategorie-CSS), L709-729 (Severity) |
| Event Details Panel | [EventDetailsPanel.vue](../src/components/system-monitor/EventDetailsPanel.vue) | L602-619 (Glassmorphism) |
| Toast System | [useToast.ts](../src/composables/useToast.ts) | L37-38 (Durations), L67 (Push) |
| Toast Container | [ToastContainer.vue](../src/components/common/ToastContainer.vue) | L297-317 (Animationen) |
| Dashboard | [DashboardView.vue](../src/views/DashboardView.vue) | L60-66 (Initial Load), L107-131 (Status Counts) |
| Audit API | [audit.ts](../src/api/audit.ts) | L283-331 (Aggregated Events), L29 (correlation_id) |
| correlation_id (DB) | [audit_log.py](../../El%20Servador/god_kaiser_server/src/db/models/audit_log.py) | L156 (Feld-Definition) |

---

## 10. Offene Fragen an Manager

1. **`correlation_id` Aktivierung** -- Soll das Backend beginnen, `correlation_id` zu setzen? Die gesamte Infrastruktur (DB-Index, API, Frontend-Type) ist bereits vorhanden.

2. **`actuator_response` Event** -- Der MessageType ist definiert aber nicht subscribed. Soll der ESP Store diesen Event handhaben? Was soll im UI passieren?

3. **Toast-System Konsolidierung** -- Soll das lokale Toast-System in SystemMonitorView durch das globale `useToast` ersetzt werden?

4. **Toast-Limits** -- Soll ein Maximum an sichtbaren Toasts eingefuehrt werden? Aktuell: unbegrenzt.

5. **DataSource-Farben** -- Die Farben im DataSourceSelector weichen von den Event-Kategorie-Farben ab (z.B. Sensors: blau im Selector, emerald in Events). Bewusste Designentscheidung oder zu vereinheitlichen?

6. **`logic_execution` und `system_event`** -- Wann werden diese reservierten MessageTypes implementiert?

7. **Light-Mode** -- Ist ein Light-Theme geplant, oder bleibt Dark-Only?

---

*Generiert am 2026-01-27. Basierend auf Code-Analyse ohne Code-Aenderungen.*
*Detail-Analysen: [websocket](websocket-analysis.md) | [system-monitor](system-monitor-analysis.md) | [toast](toast-analysis.md) | [dashboard](dashboard-analysis.md) | [correlation](correlation-analysis.md) | [ui-patterns](ui-patterns-analysis.md)*
