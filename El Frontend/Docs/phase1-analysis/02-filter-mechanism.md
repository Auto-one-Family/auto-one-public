# 02 - Filter Mechanism Analysis

**Source file:** `El Frontend/src/views/SystemMonitorView.vue`
**Total lines:** 2336 (1250 script, 1086 template+style)

---

## 1. Filter State Variables

All filter state is defined in the `<script setup>` block within the "State" section (lines 153-232).

| Variable | Line | Type | Initial Value | Purpose |
|---|---|---|---|---|
| `activeTab` | 221 | `ref<TabId>` | `'events'` | Current tab ID (`'events' \| 'logs' \| 'database' \| 'mqtt'`) |
| `filterEspId` | 222 | `ref<string>` | `''` | ESP device ID text filter (empty = all) |
| `filterLevels` | 223 | `ref<Set<string>>` | `new Set(['info', 'warning', 'error', 'critical'])` | Active severity levels (all enabled by default) |
| `filterTimeRange` | 224 | `ref<'all' \| '1h' \| '6h' \| '24h' \| '7d' \| '30d' \| 'custom'>` | `'all'` | Time range preset |
| `customStartDate` | 227 | `ref<string \| undefined>` | `undefined` | Custom range start (ISO date string) |
| `customEndDate` | 228 | `ref<string \| undefined>` | `undefined` | Custom range end (ISO date string) |
| `selectedDataSources` | 192 | `ref<DataSource[]>` | `['audit_log', 'sensor_data', 'esp_health', 'actuators']` | Active data source categories |
| `isPaused` | 164 | `ref<boolean>` | `localStorage.getItem(PAUSE_STORAGE_KEY) === 'true'` | Live WebSocket pause toggle |

**Additional derived/supporting state:**

| Variable | Line | Type | Purpose |
|---|---|---|---|
| `eventLoadHours` | 179 | `ref<number \| null>` | Hours of history to load; `null` = ALL |
| `currentLimitPerSource` | 181 | `ref<number>` | Per-source limit for API calls (default 2000) |
| `paginationCursor` | 187 | `ref<string \| null>` | Cursor-based pagination (oldest_timestamp) |
| `hasMoreEvents` | 188 | `ref<boolean>` | Whether more events exist for infinite scroll |

---

## 2. How Filters Are Set

### 2.1 Direct Assignment Methods

| Mechanism | Line(s) | Trigger |
|---|---|---|
| `handleTabChange(tabId)` | 1055-1057 | MonitorTabs emits `update:active-tab` |
| `handleDataSourcesChange(sources)` | 1065-1068 | EventsTab emits `data-sources-change` |
| `togglePause()` | 1070-1078 | MonitorTabs emits `toggle-pause` |

### 2.2 Template Event Bindings (props/v-model pattern with EventsTab)

Lines 1325-1348 show EventsTab receives filters as props and emits updates:

```
@update:filter-esp-id="filterEspId = $event"          (line 1341)
@update:filter-levels="filterLevels = $event"          (line 1342)
@update:filter-time-range="filterTimeRange = $event"   (line 1343)
@update:custom-start-date="customStartDate = $event"   (line 1344)
@update:custom-end-date="customEndDate = $event"       (line 1345)
```

EventsTab uses a v-model-like pattern: it receives read-only props and emits `update:*` events to mutate parent state.

### 2.3 Watchers That Set Filters

| Watcher | Lines | What It Does |
|---|---|---|
| `watch(() => route.query.esp, ...)` | 1209-1211 | Sets `filterEspId` from URL query param `?esp=`. Has `{ immediate: true }` so it runs on mount. |
| URL params in `onMounted` | 1170-1181 | Sets `activeTab` from `?tab=` and `filterTimeRange` from `?timeRange=` |
| `watch(isPaused, ...)` | 167-169 | Persists pause state to localStorage |
| `watch(statisticsTimeRange, ...)` | 205-207 | Persists statistics time range to localStorage |

### 2.4 Debounced Reload Watcher

Lines 1216-1233: A watcher on `[selectedDataSources, filterLevels, filterEspId]` triggers a debounced (300ms) reload of historical events via `loadHistoricalEvents()` when on the events tab. This sends filters server-side via `buildServerFilterParams()` (lines 786-805).

---

## 3. How Filters Are Applied to Events

### 3.1 Client-Side Filtering: `filteredEvents` Computed (lines 248-321)

This is the central filtering pipeline. It processes `unifiedEvents.value` through sequential filters:

**Step 1 - Data Source Filter (lines 255-259):**
```
events.filter(e => !e.dataSource || selectedDataSources.value.includes(e.dataSource))
```
Events without `dataSource` always pass. Otherwise must match selected sources.

**Step 2 - Tab-based Source Filter (lines 262-266):**
- `'mqtt'` tab: only `source === 'mqtt' || source === 'esp'`
- `'logs'` tab: only `source === 'server'`
- `'events'` tab: no source filter (shows all)

**Step 3 - ESP ID Filter (lines 277-282):**
```
filterEspId.value ? events.filter(e => e.esp_id?.toLowerCase().includes(espFilter)) : pass
```
Case-insensitive substring match. Empty string = no filter.

**Step 4 - Severity Level Filter (lines 287-290):**
```
events.filter(e => !e.severity || filterLevels.value.has(e.severity))
```
Events without severity always pass.

**Step 5 - Time Range Filter (lines 295-318):**
- `'all'`: no filter
- `'custom'`: between `customStartDate` and `customEndDate`
- Presets (`'1h'`, `'6h'`, `'24h'`, `'7d'`, `'30d'`): relative to `Date.now()`

### 3.2 Server-Side Filtering: `buildServerFilterParams()` (lines 786-805)

Constructs parameters sent to `auditApi.getAggregatedEvents()`:
- `sources`: `selectedDataSources.value`
- `hours`: `eventLoadHours.value`
- `limitPerSource`: `currentLimitPerSource.value`
- `severity`: `Array.from(filterLevels.value)` (only when `audit_log` source is selected)
- `espIds`: `[filterEspId.value]` (only when non-empty)

This is a hybrid approach: server pre-filters on load, client filters the in-memory result for display.

---

## 4. Tab Communication Mechanism

### 4.1 EventsTab (lines 1325-1348)

Communication: **Props down, Events up** (no provide/inject).

**Props passed down:**

| Prop | Line | Source |
|---|---|---|
| `:filtered-events` | 1327 | `filteredEvents` computed |
| `:total-available-events` | 1328 | `totalAvailableEvents` ref |
| `:has-more-events` | 1329 | `hasMoreEvents` ref |
| `:is-loading-more` | 1330 | `isLoadingMore` ref |
| `:is-paused` | 1331 | `isPaused` ref |
| `:event-type-labels` | 1332 | `EVENT_TYPE_LABELS` constant |
| `:restored-event-ids` | 1333 | `restoredEventIds` ref |
| `:filter-esp-id` | 1334 | `filterEspId` ref |
| `:filter-levels` | 1335 | `filterLevels` ref |
| `:filter-time-range` | 1336 | `filterTimeRange` ref |
| `:unique-esp-ids` | 1337 | `uniqueEspIds` computed |
| `:custom-start-date` | 1338 | `customStartDate` ref |
| `:custom-end-date` | 1339 | `customEndDate` ref |

**Events emitted up:**

| Event | Line | Handler |
|---|---|---|
| `@data-sources-change` | 1340 | `handleDataSourcesChange` |
| `@update:filter-esp-id` | 1341 | Inline assignment |
| `@update:filter-levels` | 1342 | Inline assignment |
| `@update:filter-time-range` | 1343 | Inline assignment |
| `@update:custom-start-date` | 1344 | Inline assignment |
| `@update:custom-end-date` | 1345 | Inline assignment |
| `@load-more` | 1346 | `handleLoadMore` |
| `@select` | 1347 | `selectEvent` |

### 4.2 ServerLogsTab (lines 1351-1353)

**No props, no events.** ServerLogsTab is completely self-contained:
```html
<ServerLogsTab v-else-if="activeTab === 'logs'" />
```

It manages its own data fetching and filtering internally.

### 4.3 DatabaseTab (lines 1356-1358)

**No props, no events.** Self-contained.

### 4.4 MqttTrafficTab (lines 1361-1364)

**One prop:**
```html
<MqttTrafficTab v-show="activeTab === 'mqtt'" :esp-id="filterEspId || undefined" />
```
- Receives `filterEspId` as `:esp-id` prop (line 1363)
- Uses `v-show` instead of `v-if` so it keeps collecting MQTT messages even when not visible (line 1360 comment)

### 4.5 MonitorTabs (lines 1255-1264)

**Props:** `:active-tab`, `:event-counts`, `:is-paused`, `:is-admin`
**Events:** `@update:active-tab`, `@toggle-pause`, `@export`, `@open-cleanup-panel`

### 4.6 EventDetailsPanel (lines 1369-1374)

**Props:** `:event` (selectedEvent), `:event-type-labels`
**Events:** `@close`

### 4.7 No provide/inject

The entire SystemMonitorView uses exclusively the **props + emit** pattern. There is no `provide()` or `inject()` anywhere in this component.

---

## 5. URL Query Parameter Support

### 5.1 Supported Parameters

| Param | Read Location | Line(s) | Written? |
|---|---|---|---|
| `?tab=` | `onMounted` | 1170-1175 | No (read-only) |
| `?esp=` | Watcher with `immediate: true` | 1209-1211 | No (read-only) |
| `?timeRange=` | `onMounted` | 1176-1181 | No (read-only) |

### 5.2 How Parameters Are Read

**`?tab=`** (line 1170-1175):
```typescript
if (route.query.tab) {
  const tab = String(route.query.tab) as TabId
  if (['events', 'logs', 'database', 'mqtt'].includes(tab)) {
    activeTab.value = tab
  }
}
```
Read once in `onMounted`. Validated against allowed tab IDs.

**`?esp=`** (lines 1209-1211):
```typescript
watch(() => route.query.esp, (newEsp) => {
  filterEspId.value = newEsp ? String(newEsp) : ''
}, { immediate: true })
```
Reactive watcher with `immediate: true`. Responds to route changes (e.g., programmatic navigation from other views). This is the only query param that reacts to changes after mount.

**`?timeRange=`** (lines 1176-1181):
```typescript
if (route.query.timeRange) {
  const range = String(route.query.timeRange)
  if (['all', '1h', '6h', '24h', '7d', '30d', 'custom'].includes(range)) {
    filterTimeRange.value = range as typeof filterTimeRange.value
  }
}
```
Read once in `onMounted`. Validated against allowed values.

### 5.3 URL Parameters Are NOT Written Back

The component only reads URL query parameters. It never calls `router.push()` or `router.replace()` to sync filter state back to the URL. Filter changes made via the UI are not reflected in the URL.

---

## 6. Tab Switching Mechanism

### 6.1 User-Initiated Tab Switch

1. User clicks a tab in `MonitorTabs` component
2. `MonitorTabs` emits `update:active-tab` with the `TabId`
3. `SystemMonitorView` handles it via `@update:active-tab="handleTabChange"` (line 1260)
4. `handleTabChange(tabId)` (line 1055-1057) sets `activeTab.value = tabId`
5. Template conditionals render the correct tab:
   - `v-if="activeTab === 'events'"` (line 1326)
   - `v-else-if="activeTab === 'logs'"` (line 1352)
   - `v-else-if="activeTab === 'database'"` (line 1357)
   - `v-show="activeTab === 'mqtt'"` (line 1362) -- always mounted

### 6.2 Programmatic Tab Switch (from URL)

On mount (line 1170-1175), if `?tab=` query param exists, `activeTab` is set directly:
```typescript
activeTab.value = tab
```

### 6.3 Programmatic Tab Switch + Filter (Deep Linking)

To navigate to SystemMonitor with a specific tab and ESP filter from another view:
```typescript
router.push({ name: 'system-monitor', query: { tab: 'events', esp: 'ESP_12AB34CD' } })
```

- `?tab=` is read in `onMounted` (line 1170-1175)
- `?esp=` is read by the reactive watcher (line 1209-1211, `immediate: true`)
- Both apply before `loadHistoricalEvents()` is called (line 1192)

### 6.4 Mobile Auto-Scroll on Tab Switch

Lines 1236-1249: A watcher on `activeTab` scrolls the tab element into view on mobile:
```typescript
watch(activeTab, (newTab) => {
  if (isMobile.value) {
    nextTick(() => {
      document.querySelector(`[data-tab="${newTab}"]`)?.scrollIntoView(...)
    })
  }
})
```

### 6.5 Filter-Reload Interaction with Tabs

The debounced reload watcher (line 1226) only reloads when `activeTab.value === 'events'`:
```typescript
if (activeTab.value === 'events' && !isLoading.value) {
  loadHistoricalEvents()
}
```
Filter changes on other tabs do NOT trigger reloads.

---

## Summary

- **Filter ownership:** SystemMonitorView owns all filter state; child tabs receive read-only props and emit updates
- **Dual filtering:** Server-side (on API load) + client-side (`filteredEvents` computed)
- **Communication pattern:** Props down, events up (no provide/inject)
- **URL support:** Read-only for `?tab=`, `?esp=`, `?timeRange=`; not written back
- **Tab rendering:** `v-if`/`v-else-if` for events/logs/database; `v-show` for MQTT (stays mounted)
- **ServerLogsTab and DatabaseTab:** Fully self-contained, receive no filter props from parent
