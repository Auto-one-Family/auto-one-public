# 05 - Navigation & Deep-Linking Analysis

> Precise line-number analysis of URL query parameter sync, tab switching, and deep-linking in the System Monitor.

---

## 1. useQueryFilters Composable

**File:** `El Frontend/src/composables/useQueryFilters.ts`

### 1.1 Types (Lines 21-57)

| Type | Definition | Line |
|------|-----------|------|
| `MonitorCategory` | `'events' \| 'logs' \| 'database' \| 'mqtt'` | 21 |
| `SeverityLevel` | `'info' \| 'warning' \| 'error' \| 'critical'` | 22 |
| `TimeRange` | `'15m' \| '1h' \| '6h' \| '24h' \| '7d' \| 'custom'` | 23 |
| `MonitorFilters` | Interface with 10 fields | 25-46 |
| `UseQueryFiltersOptions` | Options: defaultCategory, defaultTimeRange, debounceMs, autoSync | 48-57 |

### 1.2 MonitorFilters Interface (Lines 25-46)

| Field | Type | Default (Line 63-74) | URL Param |
|-------|------|---------|-----------|
| `category` | `MonitorCategory` | `'events'` | `?category=` |
| `esp` | `string \| null` | `null` | `?esp=` |
| `level` | `SeverityLevel[]` | `[]` | `?level=` (comma-separated) |
| `timeRange` | `TimeRange` | `'1h'` | `?timeRange=` |
| `startTime` | `string \| null` | `null` | `?startTime=` (ISO string) |
| `endTime` | `string \| null` | `null` | `?endTime=` (ISO string) |
| `search` | `string` | `''` | `?search=` |
| `eventType` | `string \| null` | `null` | `?eventType=` |
| `table` | `string \| null` | `null` | `?table=` |
| `topicPattern` | `string \| null` | `null` | `?topicPattern=` |

### 1.3 Exported Functions

| Function | Signature | Line | Sync Behavior |
|----------|-----------|------|---------------|
| `syncFromURL()` | `(): void` | 141-174 | Reads `route.query` into `filters` reactive object |
| `syncToURL()` | `(): void` | 179-225 | Writes non-default filter values to URL via `router.replace()` |
| `syncToURLDebounced()` | `(): void` | 230-235 | Calls `syncToURL()` after `debounceMs` (default 300ms) |
| `resetFilters()` | `(): void` | 244-251 | Resets all filters except `category`, calls `syncToURL()` immediately |
| `setFilter(key, value)` | `<K>(key: K, value: MonitorFilters[K]): void` | 256-259 | Sets single filter, calls `syncToURLDebounced()` |
| `setCategory(cat, reset?)` | `(category: MonitorCategory, resetTabFilters?: boolean): void` | 264-275 | Sets category, optionally resets tab-specific filters (eventType, table, topicPattern), calls `syncToURL()` immediately |
| `toggleLevel(level)` | `(level: SeverityLevel): void` | 280-288 | Toggles severity in array, calls `syncToURLDebounced()` |
| `setEspFilter(espId)` | `(espId: string \| null): void` | 293-296 | Sets ESP filter, calls `syncToURL()` immediately |
| `setTimeRange(range, start?, end?)` | `(range: TimeRange, startTime?: string, endTime?: string): void` | 301-313 | Sets time range preset, clears custom bounds if not 'custom', calls `syncToURL()` immediately |
| `setSearch(query)` | `(query: string): void` | 318-321 | Sets search, calls `syncToURLDebounced()` |

### 1.4 Computed Properties

| Computed | Type | Line | Description |
|----------|------|------|-------------|
| `hasActiveFilters` | `boolean` | 330-340 | True if any filter differs from default (excludes `category`) |
| `activeFilterCount` | `number` | 345-355 | Count of non-default filter fields |
| `timeBounds` | `{ start: Date; end: Date }` | 360-393 | Calculates absolute Date objects from timeRange preset or custom bounds |

### 1.5 Lifecycle & URL Sync Mechanism

- **Line 400-406:** Watches `route.query` (deep) and calls `syncFromURL()` on any change (handles browser back/forward).
- **Line 409-413:** On mount, calls `syncFromURL()` if `autoSync` option is true (default).
- **Line 221-224:** `syncToURL()` uses `router.replace()` (not `push`) so URL updates do NOT create new history entries.

### 1.6 IMPORTANT: This Composable is NOT Used by SystemMonitorView

Despite being designed for SystemMonitorView (see docstring line 8-9), **SystemMonitorView.vue does NOT import or use `useQueryFilters`**. Instead, it implements its own manual query parameter handling:

- **Line 1170-1181 (SystemMonitorView):** Manual `route.query.tab` and `route.query.timeRange` reading in `onMounted`.
- **Line 1209-1211 (SystemMonitorView):** Dedicated watcher for `route.query.esp` with `immediate: true`.
- **No URL write-back:** SystemMonitorView never writes filter state back to the URL. Filter changes (ESP, levels, time range) are purely in-memory.

---

## 2. Router Configuration for /system-monitor

**File:** `El Frontend/src/router/index.ts`

### 2.1 Route Definition (Lines 73-77)

```typescript
{
  path: 'system-monitor',        // Line 73
  name: 'system-monitor',        // Line 74
  component: () => import('@/views/SystemMonitorView.vue'),  // Line 75
  meta: { requiresAdmin: true, title: 'System Monitor' },   // Line 76
}
```

- **Auth guard (line 170-172):** `requiresAdmin: true` means non-admin users are redirected to dashboard.
- **No explicit query params** defined in the route -- Vue Router passes all query params through freely.

### 2.2 Legacy Redirects to /system-monitor (Lines 60-108)

| Old Route | Redirect Target | Line |
|-----------|----------------|------|
| `/database` | `/system-monitor?tab=database` | 64 |
| `/logs` | `/system-monitor?tab=logs` | 70 |
| `/audit` | `/system-monitor?tab=events` | 83 |
| `/mqtt-log` | `/system-monitor?tab=mqtt` | 107 |

These redirects demonstrate that `?tab=` is the established query param for tab selection.

### 2.3 Supported Query Parameters (from SystemMonitorView reading)

| Param | Read Location (SystemMonitorView) | Values |
|-------|----------------------------------|--------|
| `tab` | Line 1170-1175 (`onMounted`) | `'events'`, `'logs'`, `'database'`, `'mqtt'` |
| `esp` | Line 1209-1211 (watcher, `immediate: true`) | Any ESP ID string (e.g. `ESP_D0B19C`) |
| `timeRange` | Line 1176-1181 (`onMounted`) | `'all'`, `'1h'`, `'6h'`, `'24h'`, `'7d'`, `'30d'`, `'custom'` |

**Note:** `category` from useQueryFilters is NOT used. SystemMonitorView uses `tab` instead.

---

## 3. Tab Switching Mechanism

### 3.1 Tab State

- **Line 221 (SystemMonitorView):** `const activeTab = ref<TabId>('events')` -- default tab is `'events'`.
- **TabId type (MonitorTabs.vue line 24):** `'events' | 'logs' | 'database' | 'mqtt'`

### 3.2 Programmatic Tab Change

- **Line 1055-1057 (SystemMonitorView):** `handleTabChange(tabId: TabId)` sets `activeTab.value = tabId`.
- **Line 1260 (template):** `@update:active-tab="handleTabChange"` binds MonitorTabs emit to handler.
- **Line 54 (MonitorTabs.vue):** Emits `'update:activeTab': [tab: TabId]`.

### 3.3 URL-to-Tab Sync (One-Way: URL -> State)

- **Line 1170-1175:** On mount, reads `route.query.tab` and sets `activeTab.value`.
- **No reverse sync:** Changing tabs programmatically does NOT update the URL. Tab state is ephemeral after initial load.

### 3.4 Tab Content Rendering (Lines 1325-1364)

| Tab | Component | Render Strategy | Line |
|-----|-----------|----------------|------|
| `events` | `<EventsTab>` | `v-if="activeTab === 'events'"` | 1326 |
| `logs` | `<ServerLogsTab>` | `v-else-if="activeTab === 'logs'"` | 1352 |
| `database` | `<DatabaseTab>` | `v-else-if="activeTab === 'database'"` | 1357 |
| `mqtt` | `<MqttTrafficTab>` | `v-show="activeTab === 'mqtt'"` | 1362 |

**Key difference:** MqttTrafficTab uses `v-show` (always mounted, hidden via CSS) so MQTT messages continue to accumulate even when the tab is not active. All other tabs use `v-if` (destroyed when not active).

### 3.5 Mobile Auto-Scroll on Tab Change (Lines 1236-1249)

When `isMobile` is true, a watcher on `activeTab` scrolls the selected tab button into view using `scrollIntoView({ behavior: 'smooth', inline: 'center' })`.

---

## 4. Existing Deep-Link Examples

### 4.1 ESPCard -> SystemMonitor (with ESP Filter)

**File:** `El Frontend/src/components/esp/ESPCard.vue`, Lines 878-886

```vue
<RouterLink
  :to="{
    path: '/system-monitor',
    query: {
      tab: 'events',
      esp: espId,
      timeRange: '1h'
    }
  }"
```

This navigates to `/system-monitor?tab=events&esp=ESP_XXXXX&timeRange=1h`.

**How it is consumed in SystemMonitorView:**
1. **Line 1170-1175:** `onMounted` reads `route.query.tab` -> sets `activeTab = 'events'`
2. **Line 1209-1211:** Watcher with `immediate: true` reads `route.query.esp` -> sets `filterEspId = 'ESP_XXXXX'`
3. **Line 1176-1181:** `onMounted` reads `route.query.timeRange` -> sets `filterTimeRange = '1h'`

### 4.2 Legacy Route Redirects

These are static redirects (no dynamic params), defined in `router/index.ts`:

| Source | Target URL | Line |
|--------|-----------|------|
| `/database` | `/system-monitor?tab=database` | 64 |
| `/logs` | `/system-monitor?tab=logs` | 70 |
| `/audit` | `/system-monitor?tab=events` | 83 |
| `/mqtt-log` | `/system-monitor?tab=mqtt` | 107 |

### 4.3 Sidebar Navigation

**File:** `El Frontend/src/components/layout/AppSidebar.vue`, Line 109

```vue
to="/system-monitor"
```

Plain navigation without query params (lands on default `events` tab).

---

## 5. How to Navigate to ServerLogsTab with Time-Range Filter from EventDetailsPanel

### 5.1 Current State

**EventDetailsPanel** (`El Frontend/src/components/system-monitor/EventDetailsPanel.vue`) does **not** contain any router navigation or links to ServerLogsTab. It has no imports of `useRouter` or `RouterLink`. It is a display-only panel that emits only a `close` event.

**ServerLogsTab** (`El Frontend/src/components/system-monitor/ServerLogsTab.vue`) does **not** accept any props from SystemMonitorView (line 1351-1353 shows it is rendered with zero props). It manages its own internal filter state (log level, search, time range) independently.

### 5.2 Required Changes for Deep-Link Navigation

To navigate from EventDetailsPanel to ServerLogsTab with a time-range filter, the following gaps must be bridged:

#### Gap 1: EventDetailsPanel has no navigation capability

EventDetailsPanel would need to either:
- (A) Emit a custom event (e.g., `@navigate-to-logs`) that SystemMonitorView handles, OR
- (B) Use `useRouter()` to push `/system-monitor?tab=logs&timeRange=...` directly.

**Option A is preferred** because SystemMonitorView already owns the `activeTab` state (line 221) and the event detail context.

#### Gap 2: SystemMonitorView does NOT write filter state to URL on tab change

When `handleTabChange('logs')` is called (line 1055-1057), it only sets `activeTab.value`. It does not update the URL. So even if we set query params, the ServerLogsTab would not receive them.

#### Gap 3: ServerLogsTab does not read external filter props

ServerLogsTab is rendered with zero props (line 1351-1353). It has its own internal `ref` state for filters. To accept an external time range, it would need:
- A new prop (e.g., `initialTimeRange`) or
- Read from `route.query` directly within the component.

### 5.3 Implementation Path (Minimal Changes)

The simplest path to enable "EventDetailsPanel -> ServerLogsTab with time filter":

1. **EventDetailsPanel:** Add a button/link that emits `@navigate-to-logs` with payload `{ startTime: string, endTime: string }` derived from the event timestamp.

2. **SystemMonitorView:** Handle the emit:
   ```
   // Pseudocode - line ~1370 area
   @navigate-to-logs="handleNavigateToLogs"
   ```
   The handler would:
   - Set `activeTab.value = 'logs'` (switches tab)
   - Update URL: `router.replace({ query: { tab: 'logs', startTime: ..., endTime: ... } })`

3. **ServerLogsTab:** Accept optional props `initialStartTime` and `initialEndTime`, or read from `route.query.startTime` / `route.query.endTime` on mount.

### 5.4 Query Parameter Schema for ServerLogsTab Deep-Link

Based on the existing patterns (ESPCard uses `tab`, `esp`, `timeRange`), the URL would be:

```
/system-monitor?tab=logs&startTime=2026-01-27T10:00:00Z&endTime=2026-01-27T10:05:00Z
```

Or using a preset:

```
/system-monitor?tab=logs&timeRange=1h
```

### 5.5 Key Line References Summary

| What | File | Line(s) |
|------|------|---------|
| `activeTab` state | SystemMonitorView.vue | 221 |
| Tab change handler | SystemMonitorView.vue | 1055-1057 |
| URL `tab` query read | SystemMonitorView.vue | 1170-1175 |
| URL `esp` query read | SystemMonitorView.vue | 1209-1211 |
| URL `timeRange` query read | SystemMonitorView.vue | 1176-1181 |
| ServerLogsTab render (no props) | SystemMonitorView.vue | 1351-1353 |
| EventDetailsPanel render | SystemMonitorView.vue | 1369-1374 |
| EventDetailsPanel emits only `close` | SystemMonitorView.vue | 1373 |
| ESPCard deep-link example | ESPCard.vue | 878-886 |
| useQueryFilters (unused by view) | useQueryFilters.ts | 113-442 |
| Router route definition | router/index.ts | 73-77 |
| Legacy redirects with `?tab=` | router/index.ts | 64, 70, 83, 107 |

---

## 6. useQueryFilters vs. SystemMonitorView: Two Separate Systems

There are currently **two independent query parameter systems** that are not connected:

1. **useQueryFilters composable** (lines 1-442): A fully-featured bidirectional URL<->state sync system with debouncing, time bounds computation, and filter manipulation helpers. Uses `?category=` for tabs.

2. **SystemMonitorView manual handling** (lines 1170-1211): Read-only URL consumption on mount. Uses `?tab=` for tabs. Never writes back to URL.

The useQueryFilters composable appears to have been written as an intended replacement but was never wired into SystemMonitorView. The SystemMonitorView instead uses its own `filterEspId`, `filterLevels`, `filterTimeRange` refs with manual `route.query` reading.

**Consequence:** Changes to filters within SystemMonitorView (e.g., selecting a different ESP, changing time range) are NOT reflected in the URL. Only the initial URL params on page load are consumed. Sharing a filtered URL or using browser back/forward does not preserve filter state changes made after mount.
