# ServerLogsTab.vue - Detailed Analysis

**File:** `El Frontend/src/components/system-monitor/ServerLogsTab.vue` (1345 lines)
**API Client:** `El Frontend/src/api/logs.ts` (183 lines)

---

## 1. Existing Filters

### 1.1 State Variables (lines 108-113)

| Variable | Type | Default | Line | Purpose |
|----------|------|---------|------|---------|
| `selectedFile` | `ref('')` | `''` (empty string) | 109 | Selects which log file to query |
| `selectedLevel` | `ref<LogLevel \| ''>('')` | `''` | 110 | Filters by log level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `moduleFilter` | `ref('')` | `''` | 111 | Filters by Python module name |
| `searchQuery` | `ref('')` | `''` | 112 | Free-text search within log messages |
| `page` | `ref(1)` | `1` | 113 | Current pagination page |

### 1.2 UI Elements (Template)

| Filter | Element | Line(s) | Behavior |
|--------|---------|---------|----------|
| **File Selector** | `<select v-model="selectedFile">` | 378-382 | Dropdown of available log files. Auto-selects current file on mount (line 149-152). Change triggers `watch` on line 366-369 which resets page and reloads. |
| **Level Selector** | `<select v-model="selectedLevel" @change="applyFilters">` | 385-389 | Dropdown with options: Alle, Debug, Info, Warnung, Fehler, Kritisch (lines 51-58). Change calls `applyFilters()`. |
| **Module Filter** | `<input v-model="moduleFilter" @keyup.enter="applyFilters">` | 392-398 | Text input, placeholder "Modul...", width 8rem. Only applies on Enter key. Hidden on mobile (CSS line 1308). |
| **Search** | `<input v-model="searchQuery" @keyup.enter="applyFilters">` | 403-409 | Text input with Search icon, placeholder "Suchen...", applies on Enter key. |

### 1.3 Computed Query Parameters (lines 130-137)

```typescript
const currentQueryParams = computed<LogQueryParams>(() => ({
  level: selectedLevel.value || undefined,
  module: moduleFilter.value || undefined,
  search: searchQuery.value || undefined,
  file: selectedFile.value || undefined,
  page: page.value,
  page_size: PAGE_SIZE,   // constant = 100 (line 48)
}))
```

---

## 2. Props

**The component accepts NO props.** It is a self-contained `<script setup>` component with no `defineProps()` call anywhere in the file.

---

## 3. API Call Parameters

### 3.1 Endpoint

All log queries go to **`GET /debug/logs`** (logs.ts line 126).
Log file listing goes to **`GET /debug/logs/files`** (logs.ts line 106).

### 3.2 Parameters Sent by ServerLogsTab

The `currentQueryParams` computed property (lines 130-137) builds the following parameters:

| Parameter | Sent? | Source | API Support (logs.ts) |
|-----------|-------|--------|-----------------------|
| `level` | Yes | `selectedLevel` | Yes (line 116) |
| `module` | Yes | `moduleFilter` | Yes (line 117) |
| `search` | Yes | `searchQuery` | Yes (line 118) |
| `file` | Yes | `selectedFile` | Yes (line 121) |
| `page` | Yes | `page` | Yes (line 122) |
| `page_size` | Yes | `PAGE_SIZE` (100) | Yes (line 123) |
| **`start_time`** | **NO** | Not in component | Yes (line 119) |
| **`end_time`** | **NO** | Not in component | Yes (line 120) |

### 3.3 LogQueryParams Interface (logs.ts lines 51-60)

```typescript
export interface LogQueryParams {
  level?: LogLevel
  module?: string
  search?: string
  start_time?: string    // <-- SUPPORTED in API client but UNUSED by component
  end_time?: string      // <-- SUPPORTED in API client but UNUSED by component
  file?: string
  page?: number
  page_size?: number
}
```

---

## 4. Missing Parameters Analysis

### 4.1 `start_time` / `end_time`

- **API client (logs.ts):** SUPPORTED. Defined in `LogQueryParams` (lines 55-56) and serialized to query string (lines 119-120).
- **ServerLogsTab.vue:** NOT USED. No state variable, no UI element, not included in `currentQueryParams`.
- **Server endpoint:** Presumably supported (the API client serializes them), but not exercised from the frontend.

### 4.2 `esp_id`

- **API client (logs.ts):** NOT DEFINED in `LogQueryParams`. No `esp_id` field exists.
- **ServerLogsTab.vue:** NOT USED. No state variable, no UI element.
- **Server endpoint (`/debug/logs`):** Unknown -- would need server-side verification. Server logs are file-based (god_kaiser.log), not database-based, so ESP-ID filtering would require text search within log messages rather than a structured field.

**Summary:** `start_time` and `end_time` are wired in the API client but never used. `esp_id` does not exist at any layer.

---

## 5. Deep-Link Possibilities

### 5.1 Current State: No Deep-Link Support

The component:
- Accepts **no props** (Section 2).
- Reads **no route query parameters** (no `useRoute()` import, no route-related code).
- Has **no `defineExpose()`** to allow parent components to set filters programmatically.
- Is rendered as a tab inside the System Monitor view -- tab selection is handled by the parent, but filter state within the tab is entirely internal.

### 5.2 Conclusion

**Deep-linking to ServerLogsTab with pre-set filters is NOT possible** in the current implementation. There is no mechanism to pass initial filter values from outside (neither via props, route params, nor an exposed API).

---

## 6. Changes Needed for Time-Window and ESP-ID Filtering

### 6.1 Add `start_time` / `end_time` Support (Low Effort)

The API client already supports these parameters. Changes needed only in `ServerLogsTab.vue`:

1. **New state variables** (after line 112):
   ```typescript
   const startTime = ref('')
   const endTime = ref('')
   ```

2. **Add to `currentQueryParams`** (inside computed, lines 130-137):
   ```typescript
   start_time: startTime.value || undefined,
   end_time: endTime.value || undefined,
   ```

3. **UI elements** in the toolbar filters section (after line 410):
   - Two `<input type="datetime-local">` fields for start/end time.

### 6.2 Add `esp_id` Support (Medium Effort)

Requires changes at multiple layers:

1. **API client (`logs.ts`):**
   - Add `esp_id?: string` to `LogQueryParams` interface (after line 56).
   - Add serialization: `if (params.esp_id) queryParams.set('esp_id', params.esp_id)` (after line 120).

2. **Server endpoint (`/debug/logs`):**
   - Add `esp_id` query parameter to the endpoint.
   - Implementation would likely filter log lines by searching for the ESP ID string within the message text (since server logs are file-based, not structured by ESP).

3. **ServerLogsTab.vue:**
   - New state variable: `const espIdFilter = ref('')`
   - Add to `currentQueryParams`: `esp_id: espIdFilter.value || undefined`
   - New UI input element in toolbar.

### 6.3 Add Deep-Link / Props Support (Required for Correlation)

To enable opening ServerLogsTab with pre-set filters (e.g., from an event correlation link):

1. **Add props to component:**
   ```typescript
   const props = defineProps<{
     initialLevel?: LogLevel | ''
     initialSearch?: string
     initialStartTime?: string
     initialEndTime?: string
     initialEspId?: string
   }>()
   ```

2. **Initialize state from props** in `onMounted` (before line 357):
   ```typescript
   if (props.initialLevel) selectedLevel.value = props.initialLevel
   if (props.initialSearch) searchQuery.value = props.initialSearch
   // etc.
   ```

3. **Alternative: Route query params.** The parent System Monitor view could read route query like `?tab=logs&level=ERROR&start_time=...` and pass them as props to `ServerLogsTab`.

---

## 7. Additional Observations

- **Polling:** 3-second interval (line 47), toggled via Play/Pause button (lines 197-210). Polling reloads current page only (does not reset to page 1).
- **Page size:** Fixed at 100 entries (line 48), not user-configurable.
- **Filter application:** Level change triggers immediately via `@change`. Module and Search require Enter key. File change triggers via `watch` (line 366).
- **No debounce:** Filters are not debounced; each Enter keystroke triggers an immediate API call.
- **Export:** CSV export (lines 280-305) exports only currently loaded logs, not all matching logs on the server.
- **LogManagementPanel:** Rendered via Teleport (line 636-642), handles file cleanup. Separate component at `./LogManagementPanel.vue`.
