# 06 - UI Patterns Analysis

> Source files analyzed:
> - `El Frontend/src/components/system-monitor/EventDetailsPanel.vue` (lines 598-1282)
> - `El Frontend/src/components/system-monitor/UnifiedEventList.vue` (lines 592-1098)
> - `El Frontend/src/style.css` (lines 1-806)

---

## 1. Button Styles in EventDetailsPanel

### 1.1 Panel Close Button (line 727-745)

```css
.panel-close {
  width: 2.25rem;           /* 36px */
  height: 2.25rem;          /* 36px */
  border-radius: 0.5rem;    /* 8px */
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--color-text-muted);    /* #707080 */
  cursor: pointer;
  transition: all 0.2s ease;
}

/* Hover: rotate icon 90deg */
.panel-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);  /* #f0f0f5 */
  transform: rotate(90deg);
}
```

Mobile override at 768px (line 1217-1220): `width: 44px; height: 44px;` (WCAG touch target).

### 1.2 JSON Toggle Button (line 1095-1110)

```css
.json-toggle {
  width: 100%;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.15s;
}

.json-toggle:hover {
  background: rgba(255, 255, 255, 0.04);
}
```

### 1.3 JSON Copy Button (line 1121-1138)

```css
.json-copy-btn {
  padding: 0.375rem 0.625rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);    /* #b0b0c0 */
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.15s;
}

.json-copy-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);      /* #f0f0f5 */
}
```

### 1.4 Global Button Classes (style.css lines 130-209)

| Class | Background | Color | Hover Effect |
|-------|-----------|-------|-------------|
| `.btn-primary` | `linear-gradient(135deg, #60a5fa, #818cf8)` | white | `opacity: 0.9; translateY(-1px)` |
| `.btn-secondary` | `var(--color-bg-tertiary)` (#1a1a24) | `var(--color-text-primary)` | border-color `rgba(96, 165, 250, 0.3)` |
| `.btn-ghost` | transparent | `var(--color-text-secondary)` | bg tertiary, text primary |
| `.btn-danger` | `rgba(248, 113, 113, 0.2)` | `var(--color-error)` (#f87171) | bg alpha 0.3 |
| `.btn-success` | `var(--color-success)` (#34d399) | white | `brightness(1.1)` |
| `.btn-sm` | - | - | `px-3 py-1.5 text-xs` |
| `.btn-lg` | - | - | `px-6 py-3 text-base` |

Common `.btn` base: `inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all duration-200`.

---

## 2. Link Styles

### 2.1 Copyable Value Link (EventDetailsPanel lines 833-852)

```css
.detail-value--copyable {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: color 0.15s;
}

.detail-value--copyable:hover {
  color: #60a5fa;       /* iridescent-1 */
}

/* Hidden copy icon that appears on hover */
.detail-value--copyable .copy-icon {
  opacity: 0;
  transition: opacity 0.15s;
}
.detail-value--copyable:hover .copy-icon {
  opacity: 1;
}
```

### 2.2 Sidebar Links (style.css lines 374-400)

```css
.sidebar-link {
  /* flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200 */
  color: var(--color-text-secondary);    /* #b0b0c0 */
}
.sidebar-link:hover {
  background-color: var(--color-bg-tertiary);  /* #1a1a24 */
  color: var(--color-text-primary);            /* #f0f0f5 */
}
.sidebar-link-active {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border-left: 2px solid var(--color-iridescent-1);  /* #60a5fa */
}
```

---

## 3. Animation Patterns

### 3.1 Existing Animations Summary

| Name | File | Lines | Duration | Easing | Purpose |
|------|------|-------|----------|--------|---------|
| `pulse-subtle` | UnifiedEventList | 726-729 | 2s | ease-in-out | Critical severity background pulse |
| `restored-pulse` | UnifiedEventList | 1027-1034 | 2s | ease-out | Restored event highlight fade |
| `badge-pop` | UnifiedEventList | 1051-1063 | 0.3s | ease-out | Restored badge scale-in |
| `shimmer` | style.css | 775-782 | 4s | (default) | Water reflection sweep |
| `skeleton-loading` | style.css | 784-791 | 1.5s | (default) | Skeleton loading shimmer |
| `pulse-dot` | style.css | 793-800 | 2s | (default) | Live status dot pulse |
| `pulse` (Tailwind) | style.css | 804 | 3s | cubic-bezier(0.4, 0, 0.6, 1) | Slow pulse for live indicators |
| `slide` (Vue transition) | EventDetailsPanel | 1160-1176 | 0.2s | ease | JSON section expand/collapse |

### 3.2 Transition Patterns

**CSS Variable-Based (style.css lines 77-80):**
```css
--transition-fast: 150ms ease;
--transition-base: 200ms ease;
--transition-slow: 300ms ease;
```

**Commonly used inline transitions:**

| Property | Duration | Easing | Location |
|----------|----------|--------|----------|
| `all` | 0.2s | ease | EventDetailsPanel `.panel-close` (line 738), UnifiedEventList `.event-item` (line 660) |
| `all` | 0.15s | (none) | EventDetailsPanel `.json-toggle` (line 1105), `.json-copy-btn` (line 1132) |
| `color` | 0.15s | (none) | EventDetailsPanel `.detail-value--copyable` (line 838) |
| `opacity` | 0.15s | (none) | EventDetailsPanel `.copy-icon` (line 847) |
| `color` | 0.2s | ease | UnifiedEventList `.event-item__severity` (line 832) |
| `width` | 0.5s | ease | EventDetailsPanel `.metric-bar__fill` (line 908) |
| `transform` | 0.15s | ease-out | EventDetailsPanel `.details-panel` (line 610) |
| `opacity, background-color` | 0.2s | ease | EventDetailsPanel `.details-backdrop` (line 1261) |

### 3.3 Vue Transition: `slide`

EventDetailsPanel lines 1160-1176:
```css
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to,
.slide-leave-from {
  max-height: 500px;
}
```

---

## 4. Color Variables for Highlights

### 4.1 Global CSS Custom Properties (style.css lines 10-91)

**Background Colors:**
```
--color-bg-primary:     #0a0a0f
--color-bg-secondary:   #12121a
--color-bg-tertiary:    #1a1a24
--color-bg-quaternary:  #22222e
--color-bg-hover:       #22222e
```

**Text Colors:**
```
--color-text-primary:   #f0f0f5
--color-text-secondary: #b0b0c0
--color-text-muted:     #707080
```

**Status Colors:**
```
--color-success:  #34d399
--color-warning:  #fbbf24
--color-error:    #f87171
--color-info:     #60a5fa
```

**Iridescent Accent Colors:**
```
--color-iridescent-1: #60a5fa  (blue)
--color-iridescent-2: #818cf8  (indigo)
--color-iridescent-3: #a78bfa  (violet)
--color-iridescent-4: #c084fc  (purple)
```

**Glassmorphism:**
```
--glass-bg:           rgba(255, 255, 255, 0.03)
--glass-bg-light:     rgba(255, 255, 255, 0.05)
--glass-border:       rgba(255, 255, 255, 0.08)
--glass-border-hover: rgba(255, 255, 255, 0.15)
--glass-shadow:       0 8px 32px rgba(0, 0, 0, 0.3)
--glass-shadow-glow:  0 0 20px rgba(96, 165, 250, 0.3)
```

### 4.2 Category Colors (UnifiedEventList lines 682-704)

| Category | Solid | RGBA (bar glow) | RGBA (icon bg) | Lighter (icon text) |
|----------|-------|------------------|----------------|---------------------|
| esp-status | `#3b82f6` | `rgba(59, 130, 246, 0.4)` | `rgba(59, 130, 246, 0.12)` | `#60a5fa` |
| sensors | `#10b981` | `rgba(16, 185, 129, 0.4)` | `rgba(16, 185, 129, 0.12)` | `#34d399` |
| actuators | `#f59e0b` | `rgba(245, 158, 11, 0.4)` | `rgba(245, 158, 11, 0.12)` | `#fbbf24` |
| system | `#8b5cf6` | `rgba(139, 92, 246, 0.4)` | `rgba(139, 92, 246, 0.12)` | `#a78bfa` |

### 4.3 Severity Colors (UnifiedEventList lines 709-724, EventDetailsPanel lines 708-725)

| Severity | Background Tint | Badge BG | Badge Text | Badge Border |
|----------|----------------|----------|------------|-------------|
| info | none | `rgba(96, 165, 250, 0.15)` | `#60a5fa` | `rgba(96, 165, 250, 0.25)` |
| warning | `rgba(245, 158, 11, 0.03)` | `rgba(245, 158, 11, 0.15)` | `#fbbf24` | `rgba(245, 158, 11, 0.25)` |
| error | `rgba(239, 68, 68, 0.04)` | `rgba(239, 68, 68, 0.15)` | `#f87171` | `rgba(239, 68, 68, 0.25)` |
| critical | `rgba(239, 68, 68, 0.06)` + pulse | same as error | `#f87171` | same as error |

### 4.4 Highlight-Specific Colors

**Restored Event (UnifiedEventList lines 1016-1034):**
- Border: `var(--color-success, #22c55e)` (3px left)
- Background: `color-mix(in srgb, var(--color-success, #22c55e) 8%, transparent)`
- Hover: `color-mix(in srgb, var(--color-success, #22c55e) 12%, transparent)`
- Animation start: `color-mix(in srgb, var(--color-success, #22c55e) 20%, transparent)`
- Badge: solid `var(--color-success, #22c55e)` with white icon

**Metric Bar Status (EventDetailsPanel lines 911-913):**
- Good: `#22c55e`
- Warning: `#f59e0b`
- Critical: `#ef4444`

**Error Colors (EventDetailsPanel lines 764-772, 993-1003):**
- Error section bg: `rgba(239, 68, 68, 0.05)`, border: `rgba(239, 68, 68, 0.15)`
- Error details bg: `rgba(239, 68, 68, 0.03)`, border: `rgba(239, 68, 68, 0.12)`
- Error code badge bg: `rgba(239, 68, 68, 0.1)`, border: `rgba(239, 68, 68, 0.2)`, text: `#fca5a5`

---

## 5. Responsive Breakpoints

Three breakpoints are used consistently:

| Breakpoint | Width | Usage |
|-----------|-------|-------|
| **Large** | `max-width: 1024px` | Sidebar collapse (EventDetailsPanel backdrop line 1271: `left: 4rem`) |
| **Tablet** | `max-width: 768px` | Mobile layout (both components). Full-screen panel, single-column grids, hidden time column, larger touch targets (44px), swipe-to-close replaces click-outside |
| **Phone** | `max-width: 480px` | Compact layout. Reduced padding, smaller fonts, hidden severity icon, smaller restored badge |

**EventDetailsPanel breakpoints:**
- 768px (line 1188): full-screen panel, single-column details-grid and metric-grid, 44px close button, sensor value 2rem
- 480px (line 1227): reduced header padding, smaller title font, smaller severity badge, compact metric cards

**UnifiedEventList breakpoints:**
- 768px (line 845): 64px min-height, larger icon (2.5rem), hidden time, vertical meta
- 480px (line 870): 60px min-height, 2rem icon, smaller fonts, hidden severity icon

---

## 6. Recommended CSS for New Highlight Animation

Based on the established patterns, a new highlight animation for freshly arrived events should follow these conventions:

### Design Rationale

- Duration: **2s** (matches `restored-pulse` and `pulse-subtle`)
- Easing: **ease-out** (matches `restored-pulse` for highlight-then-fade)
- Color: Use `color-mix()` with CSS variable (matches `event-item--restored` pattern)
- Initial intensity: **15-20%** alpha, settling to **0%** (matches `restored-pulse` 20% -> 8% pattern but fading fully)
- Use a category-aware color via the existing category bar color or a neutral iridescent accent

### Recommended CSS

```css
/* New event highlight - uses the iridescent-1 blue as neutral "new" color */
.event-item--new {
  animation: new-event-highlight 2s ease-out;
}

@keyframes new-event-highlight {
  0% {
    background-color: rgba(96, 165, 250, 0.15);  /* --color-iridescent-1 at 15% */
    box-shadow: inset 0 0 20px rgba(96, 165, 250, 0.08);
  }
  100% {
    background-color: transparent;
    box-shadow: none;
  }
}
```

**Alternative: Category-aware highlight using `color-mix()`:**

```css
/* Category-aware new event highlight */
.event-item--new.event-item--category-esp-status {
  animation: new-highlight-blue 2s ease-out;
}
.event-item--new.event-item--category-sensors {
  animation: new-highlight-green 2s ease-out;
}
.event-item--new.event-item--category-actuators {
  animation: new-highlight-amber 2s ease-out;
}
.event-item--new.event-item--category-system {
  animation: new-highlight-violet 2s ease-out;
}

@keyframes new-highlight-blue {
  0% { background-color: rgba(59, 130, 246, 0.12); }
  100% { background-color: transparent; }
}
@keyframes new-highlight-green {
  0% { background-color: rgba(16, 185, 129, 0.12); }
  100% { background-color: transparent; }
}
@keyframes new-highlight-amber {
  0% { background-color: rgba(245, 158, 11, 0.12); }
  100% { background-color: transparent; }
}
@keyframes new-highlight-violet {
  0% { background-color: rgba(139, 92, 246, 0.12); }
  100% { background-color: transparent; }
}
```

**Key consistency notes:**
- 0.12 alpha matches the existing category icon background alpha (`rgba(X, X, X, 0.12)` at lines 746, 751, 756, 761)
- 2s ease-out matches the `restored-pulse` animation (line 1019)
- The animation should NOT interfere with severity tints (warning 0.03, error 0.04, critical 0.06) -- the highlight fades to `transparent`, allowing the severity background to remain
- For severity-critical events with `pulse-subtle`, the new-event animation should complete first (2s) before the infinite pulse continues, which works naturally since `animation` is overridden while `.event-item--new` is applied
