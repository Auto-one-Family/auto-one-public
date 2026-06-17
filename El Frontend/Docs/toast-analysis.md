# Toast Notification System - Complete Analysis

> Generated: 2026-01-27

---

## 1. Architecture Overview

The frontend has **two independent toast systems**:

1. **Global Toast System** (`useToast` composable + `ToastContainer.vue`) -- used by most components
2. **Local Toast in SystemMonitorView** -- a standalone inline implementation with its own styles

### File Locations

| File | Purpose |
|------|---------|
| `El Frontend/src/composables/useToast.ts` | Composable (singleton state, API) |
| `El Frontend/src/components/common/ToastContainer.vue` | Renderer (bottom-right, stacked) |
| `El Frontend/src/App.vue` (lines 6, 25) | Mounts `<ToastContainer />` globally |
| `El Frontend/src/composables/index.ts` (line 17) | Re-exports `useToast` |
| `El Frontend/src/views/SystemMonitorView.vue` (lines 233-419, 1415-1428, 2218-2334) | Separate local toast implementation |

---

## 2. Toast Types and Visual Properties

### Global System (`useToast`)

| Type | Icon (lucide-vue-next) | Border-left color | Icon color | Progress bar color | aria-live |
|------|------------------------|-------------------|------------|-------------------|-----------|
| `success` | `CheckCircle` | `--color-success` / `#34d399` | `--color-success` / `#34d399` | `--color-success` / `#34d399` | `polite` |
| `error` | `XCircle` | `--color-error` / `#f87171` | `--color-error` / `#f87171` | `--color-error` / `#f87171` | `assertive` |
| `warning` | `AlertTriangle` | `--color-warning` / `#fbbf24` | `--color-warning` / `#fbbf24` | `--color-warning` / `#fbbf24` | `polite` |
| `info` | `Info` | `--color-iridescent-1` / `#60a5fa` | `--color-iridescent-1` / `#60a5fa` | `--color-iridescent-1` / `#60a5fa` | `polite` |

Visual: Each toast has a 3px colored left border, glass-morphism background (`--color-bg-secondary`, `--glass-border`, `--glass-shadow`), rounded corners (0.75rem), and an animated progress bar at the bottom.

### SystemMonitorView Local Toast

| Type | Icon | Border color | Background |
|------|------|-------------|------------|
| `success` | `CheckCircle` | `rgba(34, 197, 94, 0.4)` | Gradient green |
| `error` | (none rendered) | `rgba(248, 113, 113, 0.4)` | Gradient red |
| `info` | (none rendered) | `rgba(96, 165, 250, 0.4)` | Gradient blue |

This local toast is centered at the bottom of the viewport, not stacked, and does not support `warning` type.

---

## 3. Auto-Close Durations

### Global System Defaults (`useToast.ts` lines 37-38)

| Type | Default Duration |
|------|-----------------|
| `error` | **8000ms** (`ERROR_DURATION`) |
| `success`, `warning`, `info` | **5000ms** (`DEFAULT_DURATION`) |
| Any type with `persistent: true` | **Never** (manual dismiss only) |

Duration can be overridden per-call via the `duration` option.

### SystemMonitorView Local Toast

All types: **6000ms** (hardcoded, line 411).

---

## 4. All Places That Trigger Toasts

### A. `El Frontend/src/stores/esp.ts`

| Line | Type | Event/Trigger | Message (German) |
|------|------|---------------|------------------|
| 490 | `warning` | OneWire scan finds 0 devices | `Keine OneWire-Geraete auf GPIO {pin} gefunden` |
| 494 | `success` | OneWire scan finds devices | `{count} OneWire-Geraet(e) auf GPIO {pin} gefunden` |
| 520 | `error` | OneWire scan failure | `OneWire-Scan fehlgeschlagen: {msg}` |
| 722 | `success` | Device approved (REST API call) | `Geraet {id} wurde genehmigt` |
| 730 | `error` | Device approval failure | `Fehler beim Genehmigen: {error}` |
| 756 | `info` | Device rejected (REST API call) | `Geraet {id} wurde abgelehnt` |
| 761 | `error` | Device rejection failure | `Fehler beim Ablehnen: {error}` |
| 1383 | `warning` | LWT (Last Will) -- ESP unexpected disconnect (WebSocket) | `{name}: Verbindung unerwartet verloren` |
| 1693 | `success` | Config response: success (WebSocket) | `{name}: {message}` |
| 1700 | `warning` | Config response: partial_success (WebSocket) | `{name}: {count} konfiguriert, {failed} fehlgeschlagen` |
| 1710 | `error` | Config response: partial failure details (WebSocket) | `GPIO {gpio} ({type}): {error}` (up to 3) |
| 1727 | `error` | Config response: full error (WebSocket) | `{name}: {error_code} - {message}` |
| 1737 | `error` | Config response: failure details (WebSocket) | `GPIO {gpio}: {detail}` (up to 3) |
| 1754 | `error` | Config response: legacy failed_item (WebSocket) | `GPIO {gpio}: {type}` |
| 1850 | `info` | Device discovered (WebSocket) | `Neues Geraet entdeckt: {id}` |
| 1872 | `success` | Device approved (WebSocket) | `Geraet {id} wurde genehmigt` |
| 1897 | `warning` | Device rejected (WebSocket) | `Geraet {id} wurde abgelehnt` |

### B. `El Frontend/src/composables/useZoneDragDrop.ts`

| Line | Type | Event/Trigger | Message |
|------|------|---------------|---------|
| 218 | `success` | Zone assignment success | `"{name}" wurde zu "{zone}" zugewiesen` |
| 244 | `error` | Zone assignment failure (with Retry action) | `Zone-Zuweisung fehlgeschlagen: {msg}` |
| 297 | `success` | Zone removal success | `"{name}" wurde aus "{zone}" entfernt` |
| 323 | `error` | Zone removal failure (with Retry action) | `Zone-Entfernung fehlgeschlagen: {msg}` |
| 383 | `success` | Undo success | `Rueckgaengig: "{name}" -> "{zone}"` |
| 399 | `error` | Undo failure | `Rueckgaengig fehlgeschlagen: {msg}` |
| 450 | `success` | Redo success | `Wiederherstellen: "{name}" -> "{zone}"` |
| 466 | `error` | Redo failure | `Wiederherstellen fehlgeschlagen: {msg}` |

### C. `El Frontend/src/components/esp/ESPOrbitalLayout.vue`

| Line | Type | Event/Trigger | Message |
|------|------|---------------|---------|
| 322 | `warning` | No OneWire devices selected for add | `Bitte waehle mindestens ein neues Geraet aus` |
| 358 | `success` | DS18B20 sensors added (all OK) | `{count} DS18B20-Sensor(en) erfolgreich hinzugefuegt` |
| 360 | `warning` | DS18B20 sensors added (partial) | `{ok} erfolgreich, {fail} fehlgeschlagen` |
| 362 | `error` | DS18B20 sensors added (all failed) | `Alle {count} Sensor(en) fehlgeschlagen` |
| 535 | `success` | Actuator added | `Aktor "{label}" auf GPIO {gpio} hinzugefuegt` |
| 550 | `error` | Actuator add GPIO conflict (409) | `GPIO {gpio} nicht verfuegbar: {msg}` |
| 558 | `error` | Actuator add config error code | `{friendlyMsg}: {detail}` |
| 563 | `error` | Actuator add generic error | `Fehler beim Hinzufuegen des Aktors: {msg}` |
| 847 | `success` | Multi-value sensor added | `{label} auf GPIO {gpio} hinzugefuegt ({count} Messwerte)` |
| 859 | `success` | Single-value sensor added | `Sensor "{label}" auf GPIO {gpio} hinzugefuegt` |
| 878 | `error` | Sensor add GPIO conflict (409) | `GPIO {gpio} nicht verfuegbar: {info}` |
| 882 | `error` | Sensor add GPIO conflict (other) | `GPIO-Konflikt: {msg}` |
| 887 | `error` | Sensor add generic error | `Fehler beim Hinzufuegen des Sensors: {msg}` |
| 1010 | `success` | Sensor updated | `Sensor "{label}" (GPIO {gpio}) aktualisiert` |
| 1076 | `error` | Sensor delete blocked (non-mock) | `Sensor loeschen ist nur fuer Mock ESPs verfuegbar` |
| 1094 | `success` | Sensor removed | `Sensor "{label}" (GPIO {gpio}) entfernt` |

### D. `El Frontend/src/components/esp/SensorValueCard.vue`

| Line | Type | Event/Trigger | Message |
|------|------|---------------|---------|
| 83 | `success` | Measurement triggered | `Messung gestartet fuer GPIO {gpio}` |
| 93 | `error` | Measurement trigger failure | `{errorMessage}` |

### E. `El Frontend/src/views/SystemMonitorView.vue` (local toast, not useToast)

| Line | Type | Event/Trigger | Message |
|------|------|---------------|---------|
| 380 | `success` | WebSocket `events_restored` from backup restore | `{message}` |

---

## 5. WebSocket Events That Automatically Trigger Toasts

All handled in `El Frontend/src/stores/esp.ts`:

| WebSocket Event Type | Toast Type | Line | Description |
|---------------------|-----------|------|-------------|
| `esp_health` (source=`lwt`) | `warning` | 1383 | ESP unexpected disconnect (Last Will & Testament) |
| `config_response` (status=`success`) | `success` | 1693 | Config applied successfully |
| `config_response` (status=`partial_success`) | `warning` + `error` (details) | 1700, 1710 | Partial config failure |
| `config_response` (status=error) | `error` (summary + details) | 1727, 1737, 1754 | Full config failure |
| `device_discovered` | `info` | 1850 | New ESP device discovered |
| `device_approved` | `success` | 1872 | Device approved (by another client) |
| `device_rejected` | `warning` | 1897 | Device rejected |

---

## 6. Toast Stacking/Grouping Behavior

### Stacking
- **Global system:** Toasts stack vertically in a flex-column layout with `gap: 0.75rem` (line 110, ToastContainer.vue).
- New toasts are appended at the bottom of the stack (`state.toasts.push(toast)`, useToast.ts line 67).
- Vue `<TransitionGroup name="toast">` provides smooth enter/leave/move animations.

### Grouping
- **No deduplication or grouping.** Identical messages can appear multiple times simultaneously.
- The only grouping-like behavior is the `MAX_DETAIL_TOASTS = 3` limit in `handleConfigResponse` (esp.ts line 1690), which caps detail toasts for config failures to 3 items.

### Animations
- **Enter:** Slide in from right (translateX 100% -> 0), 0.3s ease-out
- **Leave:** Slide out to right (translateX 0 -> 100%), 0.2s ease-in
- **Move:** Smooth reflow transition (0.3s ease)

---

## 7. Toast Actions (Buttons/Links)

The `ToastAction` interface (useToast.ts lines 13-17):

```typescript
interface ToastAction {
  label: string
  onClick: () => void | Promise<void>
  variant?: 'primary' | 'secondary'  // default: 'secondary'
}
```

When an action button is clicked, `onClick()` is awaited, then the toast is dismissed automatically (ToastContainer.vue line 39-44).

### Places using actions:

| File | Line | Label | Variant | Action |
|------|------|-------|---------|--------|
| `useZoneDragDrop.ts` | 247-252 | `"Erneut versuchen"` | `primary` | Retries zone assignment |
| `useZoneDragDrop.ts` | 325-330 | `"Erneut versuchen"` | `primary` | Retries zone removal |

Both are Retry buttons on zone operation failures with 8000ms duration.

### Action Button Styling
- **primary:** Blue background (`--color-iridescent-1`), white text, hover transitions to purple
- **secondary:** Semi-transparent background (10% white), border, muted text

---

## 8. Maximum Visible Toasts

**There is no explicit limit.** The `state.toasts` array grows unbounded. All toasts in the array are rendered.

The only implicit limits are:
- Auto-dismiss removes toasts after their duration expires
- `MAX_DETAIL_TOASTS = 3` in config response handling limits detail sub-toasts
- The container has `max-width: 400px` but no `max-height` or overflow constraint

---

## 9. Toast API Reference

### Import
```typescript
import { useToast } from '@/composables/useToast'
const toast = useToast()
```

### Methods

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `show` | `show(options: ToastOptions): string` | Toast ID | Low-level: show with full options |
| `success` | `success(message: string, options?): string` | Toast ID | Shorthand for type='success' |
| `error` | `error(message: string, options?): string` | Toast ID | Shorthand for type='error' (8s default) |
| `warning` | `warning(message: string, options?): string` | Toast ID | Shorthand for type='warning' |
| `info` | `info(message: string, options?): string` | Toast ID | Shorthand for type='info' |
| `dismiss` | `dismiss(id: string): void` | void | Remove specific toast by ID |
| `clear` | `clear(): void` | void | Remove all toasts |
| `toasts` | `ComputedRef<Toast[]>` | reactive list | Read-only reactive toast list |

### ToastOptions Interface (useToast.ts lines 19-25)
```typescript
interface ToastOptions {
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
  duration?: number        // ms, default 5000 (8000 for error)
  persistent?: boolean     // if true, no auto-dismiss, no progress bar
  actions?: ToastAction[]  // optional action buttons
}
```

### Singleton Pattern
The state is a module-level `reactive()` object (line 41). All calls to `useToast()` share the same state. This means any component can add/dismiss toasts and the `ToastContainer` (mounted once in `App.vue`) renders them all.

---

## 10. Observations and Notes

1. **Two independent toast systems coexist:** The `SystemMonitorView` has its own local toast (centered, single-toast, 3 types) that does not use the global `useToast` composable. This is a potential refactoring target.

2. **No max toast limit:** Under rapid-fire conditions (e.g., many config failures), the screen could fill with toasts. The `MAX_DETAIL_TOASTS = 3` cap in config responses partially mitigates this.

3. **No deduplication:** The same message can appear multiple times if triggered repeatedly.

4. **Accessibility:** Global toasts use `role="alert"` and `aria-live` (assertive for errors, polite for others). The SystemMonitorView local toast lacks these attributes.

5. **Mobile responsive:** On screens under 480px, the global toast container spans full width. The SystemMonitorView toast adjusts at 640px.

6. **Language:** All toast messages are in German.
