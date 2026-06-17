# UI Patterns Analysis: Event Display in AutomationOne Frontend

Research-only document. Covers all visual/UI patterns for event display across the system-monitor components.

---

## 1. Color System

### 1.1 Category Colors (4 categories)

Defined in `El Frontend/src/utils/eventTransformer.ts` (lines 7-11) and applied in `UnifiedEventList.vue` (lines 682-704).

| Category | Color Name | Hex | CSS Class | Used For |
|----------|-----------|-----|-----------|----------|
| **esp-status** | Blue | `#3B82F6` | `.event-item--category-esp-status` | Heartbeat, Online/Offline, LWT, Discovery, Approval |
| **sensors** | Emerald | `#10B981` | `.event-item--category-sensors` | Sensor data, sensor health |
| **actuators** | Amber | `#F59E0B` | `.event-item--category-actuators` | Actuator status, response, alerts |
| **system** | Violet | `#8B5CF6` | `.event-item--category-system` | Config, auth, errors, lifecycle (fallback) |

Each category has two visual applications:
- **Category bar** (3px left border with glow): `UnifiedEventList.vue` lines 682-704
- **Icon background + color**: `UnifiedEventList.vue` lines 745-763

Icon background uses 12% opacity of the category color. Icon text uses a lighter variant:
- Blue: bg `rgba(59,130,246,0.12)`, text `#60a5fa`
- Emerald: bg `rgba(16,185,129,0.12)`, text `#34d399`
- Amber: bg `rgba(245,158,11,0.12)`, text `#fbbf24`
- Violet: bg `rgba(139,92,246,0.12)`, text `#a78bfa`

### 1.2 Severity Colors

Applied as background tints on event rows (`UnifiedEventList.vue` lines 709-729) and as severity badge pills (`EventDetailsPanel.vue` lines 696-725).

| Severity | Background Tint | Badge BG | Badge Text | Badge Border | Icon Color |
|----------|----------------|----------|------------|-------------|------------|
| **info** | none | `rgba(96,165,250,0.15)` | `#60a5fa` | `rgba(96,165,250,0.25)` | muted |
| **warning** | `rgba(245,158,11,0.03)` | `rgba(245,158,11,0.15)` | `#fbbf24` | `rgba(245,158,11,0.25)` | `#fbbf24` |
| **error** | `rgba(239,68,68,0.04)` | `rgba(239,68,68,0.15)` | `#f87171` | `rgba(239,68,68,0.25)` | `#f87171` |
| **critical** | `rgba(239,68,68,0.06)` + pulse | same as error | same as error | same as error | `#f87171` |

### 1.3 DataSource Selector Icon Colors

Defined in `DataSourceSelector.vue` lines 591-609:

| Source | Icon BG | Icon Color |
|--------|---------|------------|
| System (audit) | `rgba(248,113,113,0.2)` | `#f87171` |
| Sensors | `rgba(96,165,250,0.2)` | `#60a5fa` |
| ESP-Status | `rgba(34,197,94,0.2)` | `#22c55e` |
| Actuators | `rgba(251,191,36,0.2)` | `#fbbf24` |

Note: These do NOT match the event category colors exactly (e.g., sensors are blue here but emerald in event items).

### 1.4 Global Theme Variables

Defined in `El Frontend/src/style.css` (lines 12-59):

```css
--color-bg-primary: #0a0a0f;
--color-bg-secondary: #12121a;
--color-bg-tertiary: #1a1a24;
--color-bg-quaternary: #22222e;
--color-text-primary: #f0f0f5;
--color-text-secondary: #b0b0c0;
--color-text-muted: #707080;
--color-iridescent-1: #60a5fa;  /* Blue */
--color-iridescent-2: #818cf8;  /* Indigo */
--color-iridescent-3: #a78bfa;  /* Violet */
--color-iridescent-4: #c084fc;  /* Purple */
--color-success: #34d399;
--color-warning: #fbbf24;
--color-error: #f87171;
--color-info: #60a5fa;
--glass-bg: rgba(255, 255, 255, 0.03);
--glass-bg-light: rgba(255, 255, 255, 0.05);
--glass-border: rgba(255, 255, 255, 0.08);
--glass-border-hover: rgba(255, 255, 255, 0.15);
--glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
--glass-shadow-glow: 0 0 20px rgba(96, 165, 250, 0.3);
```

### 1.5 RSSI Signal Quality Colors

Defined in `RssiIndicator.vue` lines 108-125:

| Quality | Bars | Color |
|---------|------|-------|
| Good (>-50 dBm) | 3-4 | `--color-success` (#22c55e) |
| Fair (-60 to -50) | 2 | `--color-warning` (#f59e0b) |
| Weak (-80 to -60) | 1 | `#fb923c` (orange) |
| Critical (<-80) | 0 | `--color-error` (#ef4444) |

### 1.6 Metric Bar Status Colors

In `EventDetailsPanel.vue` lines 911-913:

| Status | Color | Threshold |
|--------|-------|-----------|
| good | `#22c55e` | <50% heap used |
| warning | `#f59e0b` | 50-75% used |
| critical | `#ef4444` | >75% used |

### 1.7 Toast Type Colors

In `ToastContainer.vue` lines 130-173:

| Type | Left Border | Icon Color |
|------|-------------|------------|
| success | `--color-success` (#34d399) | `--color-success` |
| error | `--color-error` (#f87171) | `--color-error` |
| warning | `--color-warning` (#fbbf24) | `--color-warning` |
| info | `--color-iridescent-1` (#60a5fa) | `--color-iridescent-1` |

---

## 2. Event Row/Card Visual Patterns

### 2.1 Event Item (UnifiedEventList.vue, lines 652-663)

Structure (left to right):
```
[Category Bar 3px] [Icon 32x32] [Time monospace] [Content: Type + Summary] [Meta pills] [Severity Icon]
```

- **Height**: `min-height: 60px` (64px on mobile)
- **Padding**: `0.75rem 1.5rem` (left padding 0, handled by category bar)
- **Border**: `1px solid var(--glass-border)` bottom
- **Hover**: `background rgba(255,255,255,0.03)` + `inset box-shadow rgba(255,255,255,0.02)`
- **Transition**: `all 0.2s ease`
- **Cursor**: pointer

### 2.2 PreviewEventCard (PreviewEventCard.vue, lines 81-155)

Simpler card used in cleanup preview:
```
[Severity Dot 8px circle] [Event Info: device_id + type + message] [Relative Time]
```

- **Background**: `rgba(255,255,255,0.03)`
- **Border**: `1px solid rgba(255,255,255,0.08)`, radius `8px`
- **Hover**: bg `0.05`, border `0.15`
- **Compact mode**: smaller padding and font

### 2.3 Toast Notification (ToastContainer.vue, lines 115-127)

```
[3px Left Border (type color)] [Icon] [Content: message + actions] [Close X] [Progress Bar bottom]
```

- **Background**: `var(--color-bg-secondary)`
- **Border**: `1px solid var(--glass-border)`
- **Shadow**: `var(--glass-shadow)`
- **Border-radius**: `0.75rem`

---

## 3. Detail Panel Pattern (EventDetailsPanel.vue)

### 3.1 Glassmorphism Container (lines 602-619)

```css
background: rgba(15, 15, 20, 0.95);
backdrop-filter: blur(20px);
border-top: 1px solid rgba(255, 255, 255, 0.06);
box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03);
```

- **Position**: fixed bottom, `left: 16rem` (sidebar offset), `max-height: 65vh`
- **Category accent**: top border color changes per category (lines 626-640)
- **Header**: sticky, `rgba(15,15,20,0.98)` with `blur(12px)`

### 3.2 Sections

Each section (`panel-section`, lines 757-762):
```css
padding: 1rem;
border-radius: 0.75rem;
background: rgba(255, 255, 255, 0.02);
border: 1px solid rgba(255, 255, 255, 0.05);
```

Error section variant (line 764-772): red-tinted background and border.

**Section types by event:**
- **Heartbeat**: Header, Zusammenfassung, Gerätestatus (metric cards), JSON
- **Sensor**: Header, Zusammenfassung, Messwert-Details (large value display), JSON
- **Error**: Header, Zusammenfassung (red), Fehler-Details, JSON
- **Default**: Header, Zusammenfassung, Details grid, JSON

### 3.3 Metric Cards (lines 869-877)

```css
padding: 0.875rem;
border-radius: 0.625rem;
background: rgba(255, 255, 255, 0.03);
border: 1px solid rgba(255, 255, 255, 0.05);
```

Grid layout: 3-column for main metrics, 2-column for secondary.

### 3.4 Close Interactions

- **Desktop**: Click-outside via backdrop (`rgba(0,0,0,0.15)` with fade transition)
- **Mobile**: Swipe-to-close (drag handle + 150px threshold)
- **Keyboard**: ESC key
- **Close button**: rotate 90deg on hover (line 744)

---

## 4. Reusable Event-Related Components

| Component | File | Used By |
|-----------|------|---------|
| `UnifiedEventList` | `system-monitor/UnifiedEventList.vue` | `EventsTab.vue` |
| `EventDetailsPanel` | `system-monitor/EventDetailsPanel.vue` | `SystemMonitorView.vue` (parent) |
| `PreviewEventCard` | `system-monitor/PreviewEventCard.vue` | `CleanupPreview.vue` |
| `RssiIndicator` | `system-monitor/RssiIndicator.vue` | `UnifiedEventList.vue`, `EventDetailsPanel.vue` |
| `DataSourceSelector` | `system-monitor/DataSourceSelector.vue` | `EventsTab.vue` |
| `MonitorFilterPanel` | `system-monitor/MonitorFilterPanel.vue` | Legacy (replaced by DataSourceSelector in EventsTab) |
| `ToastContainer` | `common/ToastContainer.vue` | Global (Teleported to body) |

### Utility Modules

| Module | File | Purpose |
|--------|------|---------|
| `eventTransformer` | `utils/eventTransformer.ts` | Category detection, message transformation, formatting |
| `eventTypeIcons` | `utils/eventTypeIcons.ts` | 31 event types mapped to Lucide icons (single source of truth) |
| `errorCodeTranslator` | `utils/errorCodeTranslator.ts` | Severity label translation |

---

## 5. Badge/Pill Patterns

### 5.1 Severity Badge (EventDetailsPanel.vue, lines 696-725)

```css
display: inline-flex;
align-items: center;
gap: 0.375rem;
padding: 0.25rem 0.625rem;
border-radius: 9999px;          /* Full pill */
font-size: 0.6875rem;
font-weight: 700;
text-transform: uppercase;
letter-spacing: 0.03em;
```

Uses icon + text. Colors per severity (see Section 1.2).

### 5.2 Meta Pills (UnifiedEventList.vue, lines 813-827)

ESP-ID, GPIO, Error pills:
```css
font-size: 0.6875rem;
padding: 0.125rem 0.375rem;
border-radius: 0.25rem;
background-color: var(--color-bg-tertiary);
color: var(--color-text-muted);
font-family: monospace;
```

Error pill has red-tinted background: `color-mix(in srgb, var(--color-error) 15%, transparent)`.

### 5.3 Source Pills (DataSourceSelector.vue, lines 524-539)

Larger selection pills:
```css
padding: 0.5rem 0.875rem;
border-radius: 0.5rem;
font-size: 0.8125rem;
background: rgba(255, 255, 255, 0.04);
border: 1px solid rgba(255, 255, 255, 0.08);
```

Selected state: gradient background `rgba(96,165,250,0.15)` to `rgba(129,140,248,0.1)`, blue border.

### 5.4 Level Pills (DataSourceSelector.vue, lines 686-734)

```css
height: 2.25rem;
padding: 0 0.875rem;
border-radius: 0.5rem;
```

Active states use gradients matching severity colors with glow box-shadow (12px spread, 35% opacity).

### 5.5 Filter Chips (MonitorFilterPanel.vue, lines 273-345)

Full-round pills (`border-radius: 9999px`) with iridescent hover shine (`::before` pseudo-element). Active state uses `var(--gradient-iridescent)` with severity-specific overrides.

### 5.6 RAW Badge (EventDetailsPanel.vue, lines 965-973)

```css
font-size: 0.625rem;
font-weight: 700;
padding: 0.125rem 0.375rem;
border-radius: 0.25rem;
background: rgba(139, 92, 246, 0.15);  /* Violet */
color: #a78bfa;
text-transform: uppercase;
```

### 5.7 Error Status Badge (EventDetailsPanel.vue, lines 1037-1050)

```css
padding: 0.25rem 0.5rem;
border-radius: 0.25rem;
font-size: 0.75rem;
font-weight: 600;
background: rgba(239, 68, 68, 0.15);
color: #f87171;
```

### 5.8 Error Code Badge (EventDetailsPanel.vue, lines 993-1003)

```css
padding: 0.5rem 0.75rem;
border-radius: 0.5rem;
background: rgba(239, 68, 68, 0.1);
border: 1px solid rgba(239, 68, 68, 0.2);
font-family: monospace;
font-size: 0.875rem;
font-weight: 600;
color: #fca5a5;
```

---

## 6. Animations

### 6.1 Pulse (Critical severity)

`UnifiedEventList.vue` lines 726-729:
```css
@keyframes pulse-subtle {
  0%, 100% { background-color: rgba(239, 68, 68, 0.06); }
  50% { background-color: rgba(239, 68, 68, 0.08); }
}
/* Duration: 2s ease-in-out infinite */
```

### 6.2 Restored Event Pulse

`UnifiedEventList.vue` lines 1027-1033:
```css
@keyframes restored-pulse {
  0% { background-color: color-mix(in srgb, var(--color-success) 20%, transparent); }
  100% { background-color: color-mix(in srgb, var(--color-success) 8%, transparent); }
}
/* Duration: 2s ease-out (one-shot) */
```

### 6.3 Badge Pop

`UnifiedEventList.vue` lines 1051-1063:
```css
@keyframes badge-pop {
  0% { transform: scale(0); opacity: 0; }
  50% { transform: scale(1.2); }
  100% { transform: scale(1); opacity: 1; }
}
/* Duration: 0.3s ease-out */
```

### 6.4 Category Bar Glow

`UnifiedEventList.vue` lines 682-704: Each category bar has a `box-shadow: 0 0 8px` with 40% opacity of the category color.

### 6.5 Toast Slide Animations

`ToastContainer.vue` lines 297-317:
- **Enter**: `translateX(100%)` to `translateX(0)`, 0.3s ease-out
- **Leave**: `translateX(0)` to `translateX(100%)`, 0.2s ease-in
- **Move**: `transform 0.3s ease`

### 6.6 Toast Progress Bar

`ToastContainer.vue` lines 275-282:
```css
@keyframes toast-progress {
  from { width: 100%; }
  to { width: 0%; }
}
/* Duration: dynamic (toast.duration ms) */
```

### 6.7 JSON Section Slide

`EventDetailsPanel.vue` lines 1161-1176:
```css
.slide-enter-from, .slide-leave-to {
  opacity: 0; max-height: 0;
}
.slide-enter-to, .slide-leave-from {
  max-height: 500px;
}
/* Duration: 0.2s ease */
```

### 6.8 Picker Modal Scale

`DataSourceSelector.vue` lines 958-977:
- **Enter/Leave**: opacity 0 to 1, popover `scale(0.95)` to `scale(1)`, 0.2s ease-out

### 6.9 Close Button Rotation

`EventDetailsPanel.vue` line 744: `transform: rotate(90deg)` on hover.

### 6.10 Hover Lift

Multiple components use `transform: translateY(-1px)` on hover for interactive elements:
- `DataSourceSelector.vue` source pills (line 559)
- `MonitorFilterPanel.vue` filter chips (line 307)
- `DataSourceSelector.vue` picker apply button (line 950)

### 6.11 Standard Transitions

Most interactive elements use `transition: all 0.2s ease` for background, color, border, and box-shadow changes.

---

## 7. Dark Theme Considerations

The entire UI is **dark-theme only**. There is no light theme or theme toggle.

### Key Dark Theme Patterns

1. **Background layering** (darkest to lightest):
   - Primary: `#0a0a0f`
   - Secondary: `#12121a`
   - Tertiary: `#1a1a24`
   - Quaternary: `#22222e`

2. **Glassmorphism** used throughout:
   - Background: `rgba(255, 255, 255, 0.02-0.05)` with `backdrop-filter: blur()`
   - Borders: `rgba(255, 255, 255, 0.06-0.08)`, hover `0.15`
   - Inset highlights: `inset 0 1px 0 rgba(255, 255, 255, 0.03-0.04)`
   - Panel in `EventDetailsPanel.vue`: `rgba(15, 15, 20, 0.95)` with `blur(20px)`

3. **Text hierarchy**: `#f0f0f5` (primary) > `#b0b0c0` (secondary) > `#707080` (muted)

4. **Color saturation**: All category/severity colors are high-saturation on dark backgrounds. Backgrounds use very low opacity (2-6%) of accent colors for tints.

5. **Iridescent gradient**: `--gradient-iridescent` (blue > indigo > violet) used for active states, CTAs, and accent decorations.

6. **No `prefers-color-scheme` media query** found -- the dark theme is hardcoded.

7. **`color-scheme: dark`** is set on date inputs (`DataSourceSelector.vue` line 900) to ensure native form controls render in dark mode.

---

## File Reference Index

| File (absolute path) | Lines of Interest |
|---|---|
| `c:\...\El Frontend\src\style.css` | 12-59: CSS custom properties |
| `c:\...\El Frontend\src\utils\eventTransformer.ts` | 7-11: category docs, 83-115: category logic, 171-429: transformations |
| `c:\...\El Frontend\src\utils\eventTypeIcons.ts` | 59-109: icon map (31 types), 131-133: getEventIcon |
| `c:\...\El Frontend\src\components\system-monitor\UnifiedEventList.vue` | 652-663: event item base, 670-704: category bar+glow, 709-729: severity tints, 731-763: icon styling, 813-827: meta pills, 726-729: pulse anim, 1016-1097: restored highlighting |
| `c:\...\El Frontend\src\components\system-monitor\EventDetailsPanel.vue` | 602-640: glassmorphism panel, 696-725: severity badges, 857-922: metric cards, 924-973: sensor display, 975-1084: error details, 1086-1176: JSON section |
| `c:\...\El Frontend\src\components\system-monitor\PreviewEventCard.vue` | 80-155: card styles, 101-111: severity dots |
| `c:\...\El Frontend\src\components\system-monitor\RssiIndicator.vue` | 76-126: bar visualization, signal quality colors |
| `c:\...\El Frontend\src\components\system-monitor\DataSourceSelector.vue` | 446-1084: all styles, 514-609: source pills, 675-744: level pills, 746-827: time segmented |
| `c:\...\El Frontend\src\components\system-monitor\MonitorFilterPanel.vue` | 162-453: filter panel styles, 272-345: iridescent chips |
| `c:\...\El Frontend\src\components\common\ToastContainer.vue` | 102-328: toast styles, 284-317: animations |
