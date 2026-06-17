# CSS-Testkonzept — Playwright

> **297 Tests** über **15 Testdateien** · 5 Schichten · 6 Browser-Profile  
> **Validiert:** 297/297 passing (Chromium ✓ Firefox ✓ WebKit ✓)

## Architektur

```
┌─────────────────────────────────────────────────────┐
│  Schicht 5: Visual Regression (Screenshot-Diffs)    │  toHaveScreenshot()
├─────────────────────────────────────────────────────┤
│  Schicht 4: Accessibility & Kontrast (axe-core)     │  @axe-core/playwright
├─────────────────────────────────────────────────────┤
│  Schicht 3: Responsive Layout Tests                 │  Multi-Viewport
├─────────────────────────────────────────────────────┤
│  Schicht 2: CSS Property Assertions                 │  toHaveCSS + evaluate
├─────────────────────────────────────────────────────┤
│  Schicht 1: Design Token Verification               │  evaluate + getComputedStyle
└─────────────────────────────────────────────────────┘
```

## Schnellstart

```bash
# Voraussetzung: Dev-Server läuft
npm run dev

# Alle CSS-Tests (Chromium, schnell)
npm run test:css

# Alle CSS-Tests (alle 6 Browser)
npm run test:css:all

# Einzelne Schichten
npm run test:css:tokens      # Design Tokens prüfen
npm run test:css:a11y        # Accessibility + Kontrast
npm run test:css:responsive  # Responsive Layout
npm run test:css:visual      # Screenshot-Vergleiche

# Visual Baselines aktualisieren
npm run test:css:update-snapshots
```

## Testdateien

| Datei | Schicht | Tests | Beschreibung |
|-------|---------|-------|-------------|
| `design-tokens.spec.ts` | 1 | 31 | Alle CSS-Variablen aus tokens.css verifizieren |
| `token-consistency.spec.ts` | 1 | 38 | Tailwind ↔ CSS Token Synchronisation |
| `animations.spec.ts` | 2 | 9 | Keyframe-Existenz, Transitions, prefers-reduced-motion |
| `buttons.spec.ts` | 2 | 13 | Button-Varianten, Größen, Zustände |
| `badges.spec.ts` | 2 | 13 | Badge-Varianten, Farben, Rundung |
| `cards.spec.ts` | 2 | 12 | Card, Glass-Card, Sektionen |
| `status-indicators.spec.ts` | 2 | 18 | Status-Dots, Skeleton, Empty/Error States |
| `forms.spec.ts` | 2 | 13 | Inputs, Labels, Focus, Fehler-States |
| `glass-effects.spec.ts` | 2 | 16 | Glasmorphism, Animationen |
| `typography.spec.ts` | 2 | 21 | Fonts, Größenskala, Text-Utilities |
| `responsive-layout.spec.ts` | 3 | 18 | Sidebar, Grid, Breakpoints |
| `accessibility.spec.ts` | 4 | 11 | axe-core WCAG 2.1 AA Scanning |
| `color-contrast.spec.ts` | 4 | 22 | Manuelle Kontrast-Berechnung |
| `visual-regression.spec.ts` | 5 | 17 | Screenshot-Baselines (Chromium + Firefox) |
| `edge-cases.spec.ts` | 7 | 26 | Overflow, Z-Index, Tabellen, Tabs |

## Konfiguration

- **`playwright.css.config.ts`** — Standalone-Config für CSS-Tests (kein Backend nötig)
- **`playwright.config.ts`** — Haupt-Config mit Auth für E2E-Szenario-Tests

### Browser-Profile

| Profil | Device | Viewport |
|--------|--------|----------|
| chromium | Desktop Chrome | 1280×720 |
| firefox | Desktop Firefox | 1280×720 |
| webkit | Desktop Safari | 1280×720 |
| mobile-chrome | Pixel 7 | 412×915 |
| mobile-safari | iPhone 14 | 390×844 |
| tablet | iPad (gen 7) | 810×1080 |

## Entdeckte CSS-Probleme

### 🔴 Behoben
1. **Doppelte CSS-Datei:** `src/style.css` hatte andere Werte als `src/styles/tokens.css`  
   → `style.css` entfernt (war nirgends importiert)

### 🟡 Dokumentiert (WCAG)
2. **text-muted Kontrast:** `#484860` auf `#07070d` = 2.27:1 (unter WCAG AA 3:1)  
   → Empfehlung: Aufhellen auf mindestens `#5c5c78`
3. **White on Success Button:** `#ffffff` auf `#34d399` = 1.92:1 (unter WCAG AA)  
   → Empfehlung: Success-Farbe abdunkeln (#059669) oder dunklen Text verwenden
4. **Password Toggle ohne aria-label:** `button-name` axe-core Violation  
   → Empfehlung: `aria-label="Passwort anzeigen"` hinzufügen

## CSS Test Helper (`helpers/css.ts`)

Wichtige Utility-Funktionen:

```typescript
// Design Token aus :root lesen
const bg = await getDesignToken(page, '--color-bg-primary')

// Computed Style eines Elements
const color = await getComputedStyleProp(locator, 'color')

// WCAG Kontrastberechnung
const ratio = contrastRatio(parseRGB('#eaeaf2'), parseRGB('#07070d'))
expect(ratio).toBeGreaterThanOrEqual(4.5) // WCAG AA

// Animation prüfen
const isAnimated = await hasActiveAnimation(locator)

// Erwartete Token-Werte (Referenz)
import { EXPECTED_TOKENS, TOKEN_RGB } from '../helpers/css'
```

## Wichtige Hinweise

### Tailwind CSS Tree-Shaking
CSS-Klassen die auf der Testseite nicht verwendet werden, sind **nicht verfügbar** für injected Test-Elemente. Lösung: Inline-Styles mit `var()` verwenden statt CSS-Klassen.

```typescript
// ❌ Funktioniert NICHT (Klasse wird tree-shaken)
container.innerHTML = '<span class="badge-success">OK</span>'

// ✅ Funktioniert IMMER (CSS-Variablen sind global)
container.innerHTML = '<span style="color:var(--color-success);">OK</span>'
```

### Screenshot-Baselines
- Erstmalig: `npm run test:css:update-snapshots`
- Baselines werden in `tests/e2e/css/__screenshots__/` gespeichert
- Bei gewollten CSS-Änderungen: Baselines aktualisieren
- `maxDiffPixelRatio: 0.01` (1% Toleranz für Font-Rendering)
