# UnifiedEventList.vue - Detailed Analysis

**File:** `El Frontend/src/components/system-monitor/UnifiedEventList.vue`
**Lines:** 1-1098 (415 script, 174 template, 506 style)

---

## 1. Props and Emitted Events

### Props (Lines 53-62)

```ts
interface Props {
  events: UnifiedEvent[]          // Full event array, sorted newest-first
  isPaused: boolean               // Controls empty-state message text
  eventTypeLabels: Record<string, string>  // Maps event_type keys to display labels
  restoredEventIds?: Set<string>  // IDs of events restored from backup (default: empty Set)
}
```

### Emits (Lines 64-66)

```ts
emit('select', event: UnifiedEvent)  // Fired on event item click
```

Only one emit: `select`. Triggered in `handleSelect()` (line 289-291), bound via `@click="handleSelect(event)"` on `.event-item` divs (lines 480, 554).

---

## 2. Template Structure - Event Item Rendering

### Two Rendering Modes

The component has two mutually exclusive rendering paths controlled by `shouldUseVirtualScroll` (line 84, threshold: 200 events):

#### Mode A: Virtual Scroll (lines 437-509)
- Sticky date header (`date-separator--sticky`, line 439)
- Spacer div with `height: totalHeight` (line 451)
- Visible window div with `translateY(offsetTop)` (line 455)
- Events rendered flat with inline date separators (line 459-469)
- **No restored badge** in virtual scroll mode (notable omission)
- **No lifecycle separator** in virtual scroll mode

#### Mode B: Non-Virtual / Grouped (lines 512-587)
- Events grouped by date via `eventsByDate` computed (line 210-235)
- Each group gets a `date-separator` (lines 519-526)
- Lifecycle separators for `service_start`/`service_stop` events (lines 531-542)
- Restored badge rendering (lines 557-559)
- Full event item with all features

### Event Item Structure (Non-Virtual, lines 545-584)

```
div.event-item
  :class="[
    `event-item--category-${getCategoryClass(event)}`,   // e.g. event-item--category-sensors
    `event-item--severity-${event.severity}`,            // e.g. event-item--severity-critical
    { 'event-item--restored': isRestoredEvent(event) }   // conditional restored class
  ]"
  :data-category="getCategoryClass(event)"
  :data-severity="event.severity"

  Children:
    div.event-item__restored-badge      (conditional: v-if isRestoredEvent)
      RotateCcw icon
    div.event-item__category-bar        (3px colored left border)
    div.event-item__icon                (category-colored icon box)
      component :is="getEventIcon(event.event_type)"
    div.event-item__time                (formatted HH:MM:SS)
    div.event-item__content
      span.event-item__type             (uppercase label)
      span.event-item__message          (transformed summary)
    div.event-item__meta
      RssiIndicator                     (conditional: heartbeat with wifi_rssi)
      span.event-item__esp              (conditional: event.esp_id)
      span.event-item__gpio             (conditional: event.gpio !== undefined)
      span.event-item__error            (conditional: event.error_code)
    component.event-item__severity      (severity icon: Info/AlertTriangle/AlertCircle/AlertOctagon)
```

### Virtual Scroll Event Item (lines 472-505)

Same structure but **without**:
- `event-item--restored` class (not in class binding, line 474-477)
- `event-item__restored-badge` element
- Lifecycle separators

---

## 3. All CSS Classes

### Container Classes
| Class | Line | Purpose |
|-------|------|---------|
| `.event-list-container` | 593 | Outer wrapper, `flex: 1`, `overflow: hidden` |
| `.monitor-empty` | 601 | Empty state centered layout |
| `.monitor-empty__title` | 612 | Empty state heading |
| `.monitor-empty__subtitle` | 619 | Empty state subtext |
| `.event-list` | 625 | Scrollable event container, `overflow-y: auto` |
| `.event-list--virtual` | 632 | Virtual scroll mode, `contain: layout paint` |
| `.event-list__spacer` | 640 | Virtual scroll total height placeholder |
| `.event-list__visible` | 644 | Virtual scroll visible window, `position: absolute`, `will-change: transform` |

### Event Item Classes
| Class | Line | Purpose |
|-------|------|---------|
| `.event-item` | 652 | Base event row, `min-height: 60px`, `cursor: pointer` |
| `.event-item:hover` | 665 | Hover effect: `rgba(255,255,255,0.03)` bg + inset box-shadow |
| `.event-item__category-bar` | 673 | 3px left border strip |
| `.event-item__icon` | 731 | 2rem icon box with rounded corners |
| `.event-item__time` | 775 | Monospace timestamp |
| `.event-item__content` | 783 | Flex column for type + message |
| `.event-item__type` | 791 | Uppercase small label |
| `.event-item__message` | 799 | Primary text, ellipsis overflow |
| `.event-item__meta` | 807 | Right-side metadata badges |
| `.event-item__esp` | 813 | ESP ID badge |
| `.event-item__gpio` | 813 | GPIO badge |
| `.event-item__error` | 813, 824 | Error code badge (red-tinted) |
| `.event-item__severity` | 829 | Right-side severity icon |
| `.event-item__restored-badge` | 1036 | Absolute-positioned green circle badge, top-right |

### Category Modifier Classes (Lines 682-704)
| Class | Color | Box-Shadow |
|-------|-------|------------|
| `.event-item--category-esp-status` | `#3b82f6` (Blue) | `rgba(59,130,246,0.4)` |
| `.event-item--category-sensors` | `#10b981` (Emerald) | `rgba(16,185,129,0.4)` |
| `.event-item--category-actuators` | `#f59e0b` (Amber) | `rgba(245,158,11,0.4)` |
| `.event-item--category-system` | `#8b5cf6` (Violet) | `rgba(139,92,246,0.4)` |

Each category also styles `.event-item__icon` background and color (lines 745-763):
- esp-status: `rgba(59,130,246,0.12)` bg, `#60a5fa` color
- sensors: `rgba(16,185,129,0.12)` bg, `#34d399` color
- actuators: `rgba(245,158,11,0.12)` bg, `#fbbf24` color
- system: `rgba(139,92,246,0.12)` bg, `#a78bfa` color

### Severity Modifier Classes (Lines 709-724)
| Class | Line | Background |
|-------|------|------------|
| `.event-item--severity-info` | 709 | None |
| `.event-item--severity-warning` | 713 | `rgba(245,158,11,0.03)` |
| `.event-item--severity-error` | 717 | `rgba(239,68,68,0.04)` |
| `.event-item--severity-critical` | 721 | `rgba(239,68,68,0.06)` + `pulse-subtle` animation |

Severity icon colors (lines 835-842):
- error/critical: `#f87171`
- warning: `#fbbf24`
- info: `var(--color-text-muted)`

### Date Separator Classes
| Class | Line | Purpose |
|-------|------|---------|
| `.event-date-group` | 906 | Flex column wrapper per date |
| `.date-separator` | 911 | Horizontal line + label + line |
| `.date-separator__line` | 919 | 1px horizontal rule |
| `.date-separator__label` | 925 | Calendar icon + date text |
| `.date-separator--sticky` | 942 | `position: sticky; top: 0; z-index: 10` with box-shadow |
| `.date-separator--inline` | 952 | `margin-top: 0.5rem` |

### Lifecycle Separator Classes
| Class | Line | Purpose |
|-------|------|---------|
| `.lifecycle-separator` | 959 | Flex row for server start/stop markers |
| `.lifecycle-separator__line` | 967 | Gradient line (transparent-current-transparent) |
| `.lifecycle-separator__label` | 979 | Bordered pill label |
| `.lifecycle-separator--start` | 995 | Green `rgba(34,197,94,0.6)` |
| `.lifecycle-separator--stop` | 1004 | Orange `rgba(251,146,60,0.6)` |

### Restored Event Classes
| Class | Line | Purpose |
|-------|------|---------|
| `.event-item--restored` | 1016 | 3px green left border, 8% green bg, `restored-pulse` animation |
| `.event-item--restored:hover` | 1023 | 12% green bg |
| `.event-item__restored-badge` | 1036 | Absolute circle, green bg, `badge-pop` animation |

---

## 4. Keyframe Animations (Exact CSS)

### `pulse-subtle` (Lines 726-729)
Applied to: `.event-item--severity-critical` (line 723)
```css
@keyframes pulse-subtle {
  0%, 100% { background-color: rgba(239, 68, 68, 0.06); }
  50% { background-color: rgba(239, 68, 68, 0.08); }
}
```
Duration: `2s ease-in-out infinite`

### `restored-pulse` (Lines 1027-1034)
Applied to: `.event-item--restored` (line 1019)
```css
@keyframes restored-pulse {
  0% {
    background-color: color-mix(in srgb, var(--color-success, #22c55e) 20%, transparent);
  }
  100% {
    background-color: color-mix(in srgb, var(--color-success, #22c55e) 8%, transparent);
  }
}
```
Duration: `2s ease-out` (one-shot, not infinite)

### `badge-pop` (Lines 1051-1063)
Applied to: `.event-item__restored-badge` (line 1048)
```css
@keyframes badge-pop {
  0% {
    transform: scale(0);
    opacity: 0;
  }
  50% {
    transform: scale(1.2);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}
```
Duration: `0.3s ease-out` (one-shot)

---

## 5. Scroll-to-Event Mechanism

**There is no scroll-to-event mechanism.** The component does not expose any method or ref to programmatically scroll to a specific event. Key observations:

- `containerRef` (line 76) references the scroll container but is not exposed via `defineExpose`
- No `scrollToEvent()` or `scrollIntoView()` function exists
- No `watch` on any "selected event" or "target event" prop
- The `handleScroll` function (line 284-287) only tracks `scrollTop` for virtual scroll calculations

### Virtual Scrolling Details

| Constant | Value | Line |
|----------|-------|------|
| `VIRTUAL_SCROLL_THRESHOLD` | 200 | 72 |
| `ITEM_HEIGHT` | 60px | 73 |
| `BUFFER_SIZE` | 10 items | 74 |

**Activation:** `shouldUseVirtualScroll` is `true` when `events.length > 200` (line 84).

**Visible range calculation** (lines 86-108):
- If not virtual: render all (`start: 0, end: events.length`)
- If virtual but `containerHeight === 0`: fallback renders up to 100 events (lines 97-100)
- Normal: `start = floor(scrollTop / 60) - 10`, `end = start + ceil(containerHeight / 60) + 20`

**Height measurement** (lines 338-368):
- Uses `requestAnimationFrame` instead of `nextTick`
- Retry logic: up to 5 retries with exponential backoff (50, 100, 200, 400, 800ms)
- Final fallback: `window.innerHeight * 0.6`
- `ResizeObserver` keeps `containerHeight` updated (lines 375-387)

**Re-measurement triggers:**
- `shouldUseVirtualScroll` becomes true (line 391-395)
- Event count changes by more than 50 (lines 399-408)

---

## 6. How to Add `highlightedEspId` Prop

### Approach

Adding a `highlightedEspId?: string | null` prop to visually highlight all events matching a specific ESP device would require changes in three areas:

### 6.1 Props Interface (Line 53-58)

Add to the `Props` interface:
```ts
highlightedEspId?: string | null
```
With default in `withDefaults` (line 60-62):
```ts
highlightedEspId: null
```

### 6.2 Template - Dynamic Class Binding

**Non-virtual mode (line 547-550):** Add to the class array:
```ts
{ 'event-item--highlighted': props.highlightedEspId && event.esp_id === props.highlightedEspId }
```

**Virtual scroll mode (line 474-477):** Same addition needed here. Currently virtual scroll mode lacks the restored class; the highlighted class should be added to both modes for consistency.

### 6.3 CSS - New Highlight Style

A new class `event-item--highlighted` would need to be added. Recommended placement: after the restored event section (after line 1063), following the same pattern. Suggested styling:

```css
.event-item--highlighted {
  background-color: rgba(59, 130, 246, 0.08);  /* Blue tint matching esp-status category */
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.2);
}

.event-item--highlighted:hover {
  background-color: rgba(59, 130, 246, 0.12);
}
```

Optionally, a keyframe animation for initial highlight appearance (similar to `restored-pulse`):
```css
@keyframes highlight-pulse {
  0% { background-color: rgba(59, 130, 246, 0.20); }
  100% { background-color: rgba(59, 130, 246, 0.08); }
}
```

### 6.4 ESP ID Badge Enhancement

The `.event-item__esp` badge (line 500/579) could also receive a highlight style:
```css
.event-item--highlighted .event-item__esp {
  background-color: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}
```

### 6.5 Scroll-to-First-Match (Optional)

Since no scroll mechanism exists, a `scrollToHighlighted()` method could be added:
- Watch `highlightedEspId` for changes
- Find first matching event index in `props.events`
- If virtual scroll: set `scrollTop = index * ITEM_HEIGHT` on `containerRef`
- If non-virtual: use `querySelector('[data-esp-id="..."]').scrollIntoView()`
- This would also require adding `data-esp-id` attributes to event items or exposing `containerRef` via `defineExpose`

### 6.6 Impact on Virtual Scroll Mode

The virtual scroll event item (lines 472-505) currently does NOT include:
- `event-item--restored` class
- `event-item__restored-badge` element

Any highlighted ESP feature should be added to BOTH rendering paths to ensure consistent behavior regardless of event count.

---

## 7. Additional Notes

### Helper Functions Used
| Function | Source | Line Used |
|----------|--------|-----------|
| `getEventIcon()` | `@/utils/eventTypeIcons` | 484, 563 |
| `getEventCategory()` | `@/utils/eventTransformer` | 297 |
| `transformEventMessage()` | `@/utils/eventTransformer` | 304 |

### Child Components
| Component | Source | Usage |
|-----------|--------|-------|
| `RssiIndicator` | `./RssiIndicator.vue` | Lines 495-499, 574-578 |

### Lucide Icons Imported (Lines 38-47)
`Activity`, `AlertTriangle`, `AlertCircle`, `AlertOctagon`, `Info`, `Server`, `Calendar`, `RotateCcw`

### Data Attributes on Event Items
- `data-category` (lines 478, 552) - category string value
- `data-severity` (lines 479, 553) - severity string value

These can be used for external DOM queries or CSS attribute selectors but are not currently used within the component itself.
