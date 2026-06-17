# EventDetailsPanel.vue - Detailed Analysis

**File:** `El Frontend/src/components/system-monitor/EventDetailsPanel.vue`
**Total lines:** 1283
**Structure:** `<script setup>` (lines 1-335) | `<template>` (lines 337-596) | `<style scoped>` (lines 598-1282)

---

## 1. Template Sections (with line numbers)

| Section | Lines | Condition | Description |
|---------|-------|-----------|-------------|
| Backdrop (click-outside) | 339-344 | `v-if="!isMobile"` | Desktop-only transparent overlay |
| Panel root div | 347-595 | always | Fixed-position panel with swipe support |
| Mobile Drag Handle | 360-363 | `v-if="isMobile"` | Swipe-to-close grip |
| **HEADER** | 368-382 | always | Severity badge + title + close button |
| **ZUSAMMENFASSUNG** | 388-400 | always | Summary text with optional error icon |
| **DETAILS** (Zeitpunkt, Quelle, ESP-ID) | 405-434 | always | 2-column grid: Zeitpunkt, Quelle, ESP-ID, Zone, GPIO |
| **GERATESTATUS** (Heartbeat) | 439-505 | `v-if="showDeviceStatus && deviceMetrics"` | Metric cards: Speicher, Signal, Laufzeit, Sensoren, Aktoren |
| **SENSOR DATA** | 510-527 | `v-if="showSensorData && sensorData"` | Large sensor value display |
| **ERROR DETAILS** | 532-571 | `v-if="showErrorDetails && errorDetails"` | Error code, description, failures list |
| **TECHNISCHE DETAILS (JSON)** | 576-593 | always (collapsible) | Toggle button + JSON pre block |

---

## 2. Props

Defined at lines 54-59:

```typescript
interface Props {
  event: UnifiedEvent          // line 55 - the event object (imported from @/types/websocket-events)
  eventTypeLabels: Record<string, string>  // line 56 - label mapping for event types
}
```

**Note:** `eventTypeLabels` is declared but never used in the template or script. Only `event` is actively used.

---

## 3. Emitted Events

Defined at lines 61-63:

```typescript
const emit = defineEmits<{
  close: []    // line 62 - no payload
}>()
```

**Emitted from:**
- `handleClose()` (line 290) - close button click
- `handleTouchEnd()` (line 268) - swipe down > 150px
- `handleBackdropClick()` (line 303) - click on backdrop
- `handleKeydown()` (line 312) - ESC key press

---

## 4. All Action Buttons/Links with Handlers

| Element | Line(s) | CSS Class | Handler | Description |
|---------|---------|-----------|---------|-------------|
| Close button (X) | 379-381 | `panel-close` | `@click="handleClose"` | Top-right close button |
| ESP-ID copy | 420-423 | `detail-value detail-value--copyable` | `@click="copyEspId"` | Click to copy ESP-ID to clipboard |
| JSON toggle | 577-586 | `json-toggle` | `@click="toggleJson"` | Expand/collapse JSON section |
| JSON copy | 582-585 | `json-copy-btn` | `@click.stop="copyJson"` | Copy JSON to clipboard |
| Backdrop | 339-344 | `details-backdrop` | `@click="handleBackdropClick"` | Click-outside to close (desktop) |

---

## 5. CSS Classes for Buttons/Actions

### Close button (lines 727-745)
- `.panel-close` - 2.25rem square, rounded, transparent bg, border
- `.panel-close:hover` - brighter bg, rotate(90deg) animation

### Copyable value (lines 833-852)
- `.detail-value--copyable` - flex, space-between, pointer cursor
- `.detail-value--copyable:hover` - blue color (#60a5fa)
- `.detail-value--copyable .copy-icon` - opacity 0, shown on hover

### JSON toggle (lines 1095-1119)
- `.json-toggle` - full-width flex button, subtle bg
- `.json-toggle:hover` - slightly brighter bg
- `.json-toggle__label` - flex with gap, 0.875rem font

### JSON copy (lines 1121-1138)
- `.json-copy-btn` - small pill button, 0.75rem font
- `.json-copy-btn:hover` - brighter bg and text

---

## 6. Event Data Access Patterns

The component accesses event data through `props.event` (type `UnifiedEvent`):

### Direct event properties used:
| Property | Used at lines | Context |
|----------|--------------|---------|
| `event.severity` | 370, 372, 395 | Severity badge, icon |
| `event.event_type` | 95, 99, 375 | Section visibility, icon |
| `event.timestamp` | 412 | Formatted display |
| `event.source` | 416 | Source label |
| `event.esp_id` | 284, 418, 421 | Conditional display + copy |
| `event.zone_name` | 425, 427 | Zone display |
| `event.gpio` | 429, 431 | GPIO display |
| `event.error_code` | 112, 186 | Error detection + display |
| `event.message` | 189 | Fallback error message |
| `event.device_type` | 170 | Fallback sensor type |
| `event.data` | 89, 276, 590 | Raw data object, JSON display |

### Nested data access (via `eventData` computed, line 89):
- `data.status` (line 111) - error detection
- `data.heap_free`, `data.wifi_rssi`, `data.uptime`, `data.sensor_count`, `data.actuator_count` (lines 123-128) - device metrics
- `data.sensor_type`, `data.value`, `data.unit`, `data.quality`, `data.raw_mode` (lines 170-174) - sensor data
- `data.error_code`, `data.type`, `data.config_type`, `data.status`, `data.message`, `data.failed_count`, `data.failures` (lines 186-191) - error details

---

## 7. Best Insertion Points for New Buttons

### Target buttons:
1. **"Alle Events dieses Gerats"** - filter/show all events for this ESP
2. **"Server-Logs anzeigen"** - navigate to server logs view

### Recommended insertion point: After the DETAILS section, before conditional sections

**Primary recommendation: Lines 433-434 (inside the Details section, after the last detail-item)**

Insert a new row inside the `details-grid` div (which starts at line 409), after the GPIO detail-item (line 432) and before the closing `</div>` at line 433. This keeps action buttons contextually grouped with the event metadata.

```
Line 432:          </div>                          <!-- end GPIO detail-item -->
>>> INSERT NEW ACTION BUTTONS HERE (line 433) <<<
Line 433:        </div>                            <!-- end details-grid -->
Line 434:      </section>                          <!-- end Details section -->
```

Suggested template pattern:
```html
          <!-- Action Buttons -->
          <div class="detail-item detail-item--full detail-item--actions">
            <button v-if="event.esp_id" class="action-btn action-btn--device-events" @click="$emit('filter-device', event.esp_id)">
              Alle Events dieses Gerats
            </button>
            <button class="action-btn action-btn--server-logs" @click="$emit('show-server-logs', event)">
              Server-Logs anzeigen
            </button>
          </div>
```

**Why this location:**
- Inside the Details section where ESP-ID and metadata are already shown
- Uses existing `detail-item--full` pattern for full-width spanning (line 816-818)
- Visible for all event types (the Details section is always rendered)
- Before the conditional sections (device status, sensor data, errors) so buttons are consistently positioned
- After ESP-ID which provides context for "Alle Events dieses Gerats"

### Alternative insertion point: Lines 571-572 (after Error Details, before JSON)

This would place buttons after all content sections but before JSON. Advantage: buttons appear after all relevant info has been read. Disadvantage: button position varies depending on which sections are visible.

### Emit changes required:

New emits to add at line 62:
```typescript
const emit = defineEmits<{
  close: []
  'filter-device': [espId: string]
  'show-server-logs': [event: UnifiedEvent]
}>()
```

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total lines | 1283 |
| Script lines | 335 |
| Template lines | 259 (337-596) |
| Style lines | 684 (598-1282) |
| Props | 2 (`event`, `eventTypeLabels`) |
| Emits | 1 (`close`) |
| Action buttons | 4 (close, copy ESP-ID, toggle JSON, copy JSON) |
| Computed properties | 13 |
| Methods | 10 |
| Template sections | 7 (Header, Zusammenfassung, Details, Geratestatus, Sensor Data, Error Details, JSON) |
| Imports (lucide icons) | 15 |
| Child components | 1 (`RssiIndicator`) |
