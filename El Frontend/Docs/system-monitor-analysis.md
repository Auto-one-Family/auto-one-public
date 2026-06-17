# System Monitor Event Handling - Complete Analysis

> Generated: 2026-01-27 | Research-only analysis of the SystemMonitorView and related components.

---

## 1. Event Sources Aggregated

The System Monitor aggregates events from **4 data sources** plus **live WebSocket events**:

| Data Source | API Key | Description | Origin |
|---|---|---|---|
| **Audit Log** | `audit_log` | System events, config responses, errors, auth events | PostgreSQL `audit_log` table |
| **Sensor Data** | `sensor_data` | Sensor readings and health | PostgreSQL `sensor_data` table |
| **ESP Health** | `esp_health` | Device status, heartbeats, online/offline | PostgreSQL ESP device records |
| **Actuators** | `actuators` | Actuator command history, status changes | PostgreSQL actuator tables |
| **WebSocket (Live)** | N/A | Real-time events from God-Kaiser server | WebSocket broadcast |

**File:** `El Frontend/src/views/SystemMonitorView.vue`, lines 191-192
Default selection: `['audit_log', 'sensor_data', 'esp_health', 'actuators']` (all sources).

### 31 WebSocket Event Types Subscribed

Defined at lines 54-98 in `SystemMonitorView.vue` as `ALL_EVENT_TYPES`:

- **Sensor/Actuator:** `sensor_data`, `sensor_health`, `actuator_status`, `actuator_response`, `actuator_alert`, `esp_health`
- **Configuration:** `config_response`, `config_published`, `config_failed`
- **Device Lifecycle:** `device_discovered`, `device_rediscovered`, `device_approved`, `device_rejected`, `device_online`, `device_offline`, `lwt_received`
- **System:** `zone_assignment`, `logic_execution`, `system_event`, `service_start`, `service_stop`, `emergency_stop`
- **Errors:** `error_event`, `mqtt_error`, `validation_error`, `database_error`
- **Auth:** `login_success`, `login_failed`, `logout`
- **Notifications:** `notification`
- **Special:** `events_restored` (handled separately, line 1189)

---

## 2. Event Transformation

Two transformation layers exist:

### 2.1 WebSocket-to-UnifiedEvent (`SystemMonitorView.vue`, lines 421-455)

Function `transformToUnifiedEvent(wsMessage)` extracts:
- `esp_id` via `extractEspId()` (checks `data.esp_id` then `data.device_id`)
- `gpio` from `data.gpio`
- `error_code` from `data.error_code`
- `severity` via `determineSeverity()` (server-centric: uses `data.severity` first, type-based fallback)
- `source` via `determineSource()` (maps event types to: `user`, `logic`, `mqtt`, `esp`, `server`)
- `dataSource` via `determineDataSource()` (maps event type to one of 4 DataSource values)
- `message` via `generateGermanMessage()` (server-centric: uses `data.message` first, type-specific German fallback)
- Unique ID: `${Date.now()}_${random}` (line 437)
- Tags `_sourceType: 'websocket'`

### 2.2 API-to-UnifiedEvent (`SystemMonitorView.vue`, lines 1004-1049)

Function `transformAggregatedEventToUnified(apiEvent)` maps:
- `source`: `audit_log` -> `server`, `sensor_data`/`esp_health`/`actuators` -> `esp`
- `event_type`: derived from `apiEvent.source` or `metadata.event_type`
- `dataSource`: kept as-is from API response
- Timestamp normalized to UTC via `normalizeToUTCIso()` (appends 'Z' if missing, line 992-998)
- Tags `_sourceType: 'server'`

### 2.3 Display Transformation (`El Frontend/src/utils/eventTransformer.ts`)

Function `transformEventMessage(event)` returns a `TransformedMessage` with:
- `title` (uppercase English, e.g., "HEARTBEAT")
- `titleDE` (German label, e.g., "Verbindungsstatus")
- `summary` (one-liner for list display)
- `description` (multi-line for detail panel)
- `icon` (Lucide icon name)
- `category` (for color coding)

**4 categories** (line 20): `esp-status` (blue), `sensors` (emerald), `actuators` (amber), `system` (violet).

Used by `UnifiedEventList.vue` line 303: `getTransformedMessage(event).summary` for display text.

---

## 3. Filtering

### 3.1 Client-Side Filters (computed `filteredEvents`, lines 248-321)

Applied in order:
1. **DataSource filter** (lines 255-259): Events without `dataSource` always shown. Others must match `selectedDataSources`.
2. **Tab filter** (lines 262-266): `mqtt` tab shows `source === 'mqtt' || 'esp'`; `logs` tab shows `source === 'server'`.
3. **ESP ID filter** (lines 277-282): Case-insensitive substring match on `e.esp_id`.
4. **Severity filter** (lines 287-290): Events without severity always shown. Others must be in `filterLevels` Set.
5. **Time range filter** (lines 295-318): Supports preset ranges (`1h`, `6h`, `24h`, `7d`, `30d`) and custom date range.

### 3.2 Server-Side Filters (sent with API call)

Built by `buildServerFilterParams()` (lines 786-805):
- `sources`: Selected data sources
- `hours`: Time range (null = all events)
- `limitPerSource`: Default 2000
- `severity`: Only when `audit_log` is included
- `espIds`: If ESP filter is set

### 3.3 Filter Change Handling

A watcher (lines 1217-1233) debounces changes to `selectedDataSources`, `filterLevels`, `filterEspId` with 300ms delay and triggers `loadHistoricalEvents()` reload.

---

## 4. Sorting and Deduplication

### Sorting
Events are sorted by timestamp **newest first** (descending) after every load:
- `loadHistoricalEvents()`: line 945-947
- `handleLoadMore()`: line 845-847

```typescript
unifiedEvents.value.sort((a, b) =>
  new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
)
```

New WebSocket events are prepended via `unshift()` (line 353), maintaining newest-first order.

### Deduplication
By event ID using a `Set`:
- `loadHistoricalEvents()`: lines 930-931
- `handleLoadMore()`: lines 838-839

```typescript
const existingIds = new Set(unifiedEvents.value.map(e => e.id))
const newEvents = historicalEvents.filter(e => !existingIds.has(e.id))
```

WebSocket events get unique IDs (`${Date.now()}_${random}`), so they never duplicate. API events use server-provided IDs (e.g., `audit_{uuid}`).

### Safety Limit
`MAX_EVENTS = 10000` (line 49). If exceeded, oldest events are trimmed via `slice(0, MAX_EVENTS)`.

---

## 5. Pagination Mechanism

**Cursor-based infinite scroll** (not offset-based):

| State Variable | Purpose |
|---|---|
| `paginationCursor` (ref, line 187) | `oldest_timestamp` from last API response |
| `hasMoreEvents` (ref, line 188) | Whether more events exist on server |
| `isLoadingMore` (ref, line 180) | Loading guard |
| `currentLimitPerSource` (ref, line 181) | Events per source per request (default: 2000) |
| `totalAvailableEvents` (ref, line 184) | Total count across all sources |

### Flow:
1. **Initial load** (`loadHistoricalEvents()`, line 875): Resets cursor to `null`, calls `getAggregatedEvents()`.
2. **Load more** (`handleLoadMore()`, line 813): Passes `beforeTimestamp: paginationCursor.value` to load older events.
3. **API response** updates `hasMoreEvents`, `paginationCursor`, `totalAvailableEvents` from `response.pagination`.

API endpoint: `GET /api/v1/audit/events/aggregated` with query params `before_timestamp`, `limit_per_source`, `sources[]`, `severity[]`, `esp_ids[]`.

**File:** `El Frontend/src/api/audit.ts`, lines 283-331.

---

## 6. Visual Representation

### 6.1 Category Colors (left border bar)

Determined by `getEventCategory()` in `eventTransformer.ts` (lines 83-115):

| Category | Color | Events |
|---|---|---|
| `esp-status` | Blue `#3B82F6` | `esp_health`, `device_online/offline`, `lwt_received`, `device_discovered/rediscovered/approved/rejected` |
| `sensors` | Emerald `#10B981` | `sensor_data`, `sensor_health` |
| `actuators` | Amber `#F59E0B` | `actuator_status`, `actuator_response`, `actuator_alert` |
| `system` | Violet `#8B5CF6` | Everything else (config, auth, errors, lifecycle) |

**File:** `UnifiedEventList.vue`, lines 682-704 (CSS).

### 6.2 Severity Overlay (background tint + right icon)

| Severity | Background Tint | Icon |
|---|---|---|
| `info` | None | `Info` |
| `warning` | Amber 3% | `AlertTriangle` |
| `error` | Red 4% | `AlertCircle` |
| `critical` | Red 6% + pulse animation | `AlertOctagon` |

**File:** `UnifiedEventList.vue`, lines 709-729 (CSS), lines 271-278 (icon selection).

### 6.3 Event Item Layout

Each event row shows (left to right):
1. **Category bar** (3px colored left border)
2. **Event type icon** (category-colored background)
3. **Timestamp** (HH:MM:SS, hidden on mobile)
4. **Content**: event type label (uppercase, muted) + summary message
5. **Meta badges**: RSSI indicator (heartbeats only), ESP ID, GPIO, error code
6. **Severity icon** (right side)

### 6.4 Special Visual Elements

- **Date separators**: "Heute", "Gestern", or formatted date (e.g., "22. Januar 2026")
- **Server lifecycle separators**: Green "Server gestartet" / Orange "Server gestoppt" lines
- **Restored event highlighting**: Green left border + pulsing green background + rotate icon badge
- **Virtual scroll sticky date header**: Always-visible date at top during virtual scrolling

### 6.5 Separate Tab Visualizations

| Tab | Component | Visualization |
|---|---|---|
| Events | `EventsTab.vue` + `UnifiedEventList.vue` | Unified event stream with categories/severity |
| Server Logs | `ServerLogsTab.vue` | Expandable log entries with level colors, polling-based |
| Database | `DatabaseTab.vue` | Database-specific view |
| MQTT Traffic | `MqttTrafficTab.vue` | Real-time MQTT message stream with topic filter |

---

## 7. API Endpoints Called

### 7.1 On Mount (line 1164-1199)

| Call | Endpoint | When |
|---|---|---|
| `loadHistoricalEvents()` | `GET /api/v1/audit/events/aggregated` | Immediately |
| `loadStatistics()` | `GET /api/v1/audit/statistics?time_range={range}` | Immediately (non-blocking) |
| `espStore.fetchAll()` | `GET /api/v1/esp/devices` | Immediately (for ESP count) |

### 7.2 On Filter Change (debounced 300ms, lines 1217-1233)

| Trigger | Endpoint |
|---|---|
| DataSource, severity, or ESP ID change | `GET /api/v1/audit/events/aggregated` (full reload) |

### 7.3 On User Action

| Action | Endpoint |
|---|---|
| Load more (infinite scroll) | `GET /api/v1/audit/events/aggregated?before_timestamp={cursor}` |
| Resume from pause | `GET /api/v1/audit/events/aggregated` (full reload) |
| Cleanup success | `GET /api/v1/audit/events/aggregated` + `GET /api/v1/audit/statistics` |
| Events restored (via WS) | `GET /api/v1/audit/events/aggregated` + `GET /api/v1/audit/statistics` |

### 7.4 ServerLogsTab Endpoints

| Call | Endpoint | When |
|---|---|---|
| Query logs | `GET /api/v1/debug/logs` | On mount + polling (3s interval) |
| List files | `GET /api/v1/debug/logs/files` | On mount |
| Statistics | `GET /api/v1/debug/logs/statistics` | Via LogManagementPanel |
| Cleanup | `POST /api/v1/debug/logs/cleanup` | Admin action |
| Delete file | `DELETE /api/v1/debug/logs/{filename}` | Admin action |

### 7.5 Audit Admin Endpoints (CleanupPanel)

| Call | Endpoint |
|---|---|
| Retention status | `GET /api/v1/audit/retention/status` |
| Retention config | `GET /api/v1/audit/retention/config` |
| Update retention | `PUT /api/v1/audit/retention/config` |
| Run cleanup | `POST /api/v1/audit/retention/cleanup` |
| List backups | `GET /api/v1/audit/backups` |
| Restore backup | `POST /api/v1/audit/backups/{id}/restore` |
| Delete backup | `DELETE /api/v1/audit/backups/{id}` |

---

## 8. WebSocket Usage for Live Updates

**Yes**, the System Monitor uses WebSocket extensively for real-time updates.

### Connection

```typescript
const { on } = useWebSocket({ autoConnect: true })
```
**File:** `SystemMonitorView.vue`, line 241.

### Subscription (lines 1184-1189)

All 31 event types from `ALL_EVENT_TYPES` are subscribed via individual `on()` calls:

```typescript
ALL_EVENT_TYPES.forEach(eventType => {
  wsUnsubscribers.push(on(eventType, handleWebSocketMessage))
})
wsUnsubscribers.push(on('events_restored', handleEventsRestored))
```

### Live Event Flow

1. WebSocket message arrives -> `handleWebSocketMessage()` (line 348)
2. If paused (`isPaused.value`), message is **discarded** (line 349)
3. `transformToUnifiedEvent()` converts to `UnifiedEvent`
4. Event prepended to `unifiedEvents` array via `unshift()` (line 353)
5. Safety trim if exceeds `MAX_EVENTS` (10000)

### Pause/Resume Behavior

- **Pause**: WebSocket stays connected, but incoming messages are silently dropped (line 349)
- **Resume**: Triggers full `loadHistoricalEvents()` reload to catch missed events (line 1076)
- Pause state persisted to `localStorage` key `systemMonitor.isPaused` (line 163)

### MqttTrafficTab WebSocket

The MQTT tab has its **own independent** WebSocket subscription (uses `v-show` instead of `v-if` to keep collecting messages even when tab is not active, line 1361).

**File:** `MqttTrafficTab.vue`, subscribes to the same event types but maintains its own message buffer (max 1000 messages).

### Cleanup via `onUnmounted` (lines 1201-1204)

All WebSocket subscriptions are properly unsubscribed on component destruction.

---

## File Reference

| File | Purpose |
|---|---|
| `El Frontend/src/views/SystemMonitorView.vue` | Main orchestrator (1250 lines script, 1100 lines style) |
| `El Frontend/src/components/system-monitor/EventsTab.vue` | Events tab container with DataSourceSelector + UnifiedEventList |
| `El Frontend/src/components/system-monitor/UnifiedEventList.vue` | Event list with virtual scrolling, date separators, category/severity styling |
| `El Frontend/src/components/system-monitor/ServerLogsTab.vue` | Server log viewer with polling, expand/collapse, CSV export |
| `El Frontend/src/components/system-monitor/MqttTrafficTab.vue` | Live MQTT traffic viewer with topic filter |
| `El Frontend/src/components/system-monitor/DatabaseTab.vue` | Database tab |
| `El Frontend/src/components/system-monitor/DataSourceSelector.vue` | Filter UI for data sources, ESP ID, severity, time range |
| `El Frontend/src/components/system-monitor/EventDetailsPanel.vue` | Slide-up detail panel for selected event |
| `El Frontend/src/components/system-monitor/CleanupPanel.vue` | Retention config + backup management |
| `El Frontend/src/components/system-monitor/MonitorTabs.vue` | Tab bar with live toggle, export, cleanup actions |
| `El Frontend/src/components/system-monitor/RssiIndicator.vue` | WiFi signal strength indicator |
| `El Frontend/src/utils/eventTransformer.ts` | Event category detection + German message transformation |
| `El Frontend/src/utils/errorCodeTranslator.ts` | Error code category detection |
| `El Frontend/src/api/audit.ts` | Audit API client (aggregated events, statistics, retention, backups) |
| `El Frontend/src/api/logs.ts` | Server logs API client (query, files, cleanup) |
| `El Frontend/src/types/websocket-events.ts` | WebSocket event type definitions + UnifiedEvent interface |
| `El Frontend/src/composables/useWebSocket.ts` | WebSocket composable (connection management) |
| `El Frontend/src/services/websocket.ts` | WebSocket singleton service |
