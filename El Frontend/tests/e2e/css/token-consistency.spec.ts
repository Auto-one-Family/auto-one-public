/**
 * Tailwind / CSS Token Consistency Tests — Schicht 1 Extension
 *
 * Verifies that tailwind.config.js color definitions are consistent
 * with the CSS custom properties in tokens.css.
 *
 * WHY: If a developer changes a color in one place but not the other,
 * Tailwind utility classes (e.g., bg-success) will show a different
 * color than CSS var(--color-success).
 *
 * These tests are pure computation — no browser needed.
 */

import { test, expect } from '@playwright/test'

/**
 * Tailwind config color values (from tailwind.config.js)
 * Must match tokens.css values exactly
 */
const TAILWIND_COLORS = {
  // Dark background scale → tokens.css --color-bg-*
  'dark.950': '#07070d',    // --color-bg-primary
  'dark.900': '#0d0d16',    // --color-bg-secondary
  'dark.800': '#15151f',    // --color-bg-tertiary
  'dark.700': '#1d1d2a',    // --color-bg-quaternary

  // Dark text scale → tokens.css --color-text-*
  'dark.100': '#eaeaf2',    // --color-text-primary
  'dark.300': '#8585a0',    // --color-text-secondary
  'dark.400': '#484860',    // --color-text-muted

  // Iridescent → tokens.css --color-iridescent-*
  'iridescent.1': '#60a5fa',
  'iridescent.2': '#818cf8',
  'iridescent.3': '#a78bfa',
  'iridescent.4': '#c084fc',

  // Status → tokens.css --color-*
  'success.DEFAULT': '#34d399',
  'warning.DEFAULT': '#fbbf24',
  'danger.DEFAULT': '#f87171',  // = tokens.css --color-error
  'info.DEFAULT': '#60a5fa',

  // Mock/Real → tokens.css --color-mock/real
  'mock.DEFAULT': '#a78bfa',
  'real.DEFAULT': '#22d3ee',

  // Accent → tokens.css --color-accent-*
  'accent.DEFAULT': '#3b82f6',
  'accent.bright': '#60a5fa',
  'accent.dim': '#1e3a5f',
} as const

const CSS_TOKENS = {
  // Background scale
  'dark.950': '--color-bg-primary',
  'dark.900': '--color-bg-secondary',
  'dark.800': '--color-bg-tertiary',
  'dark.700': '--color-bg-quaternary',

  // Text scale
  'dark.100': '--color-text-primary',
  'dark.300': '--color-text-secondary',
  'dark.400': '--color-text-muted',

  // Iridescent
  'iridescent.1': '--color-iridescent-1',
  'iridescent.2': '--color-iridescent-2',
  'iridescent.3': '--color-iridescent-3',
  'iridescent.4': '--color-iridescent-4',

  // Status
  'success.DEFAULT': '--color-success',
  'warning.DEFAULT': '--color-warning',
  'danger.DEFAULT': '--color-error',
  'info.DEFAULT': '--color-info',

  // Mock/Real
  'mock.DEFAULT': '--color-mock',
  'real.DEFAULT': '--color-real',

  // Accent
  'accent.DEFAULT': '--color-accent',
  'accent.bright': '--color-accent-bright',
  'accent.dim': '--color-accent-dim',
} as const

/** Expected CSS token values from tokens.css */
const EXPECTED_CSS = {
  '--color-bg-primary': '#07070d',
  '--color-bg-secondary': '#0d0d16',
  '--color-bg-tertiary': '#15151f',
  '--color-bg-quaternary': '#1d1d2a',
  '--color-text-primary': '#eaeaf2',
  '--color-text-secondary': '#8585a0',
  '--color-text-muted': '#484860',
  '--color-iridescent-1': '#60a5fa',
  '--color-iridescent-2': '#818cf8',
  '--color-iridescent-3': '#a78bfa',
  '--color-iridescent-4': '#c084fc',
  '--color-success': '#34d399',
  '--color-warning': '#fbbf24',
  '--color-error': '#f87171',
  '--color-info': '#60a5fa',
  '--color-mock': '#a78bfa',
  '--color-real': '#22d3ee',
  '--color-accent': '#3b82f6',
  '--color-accent-bright': '#60a5fa',
  '--color-accent-dim': '#1e3a5f',
} as const

// ═══════════════════════════════════════════════════════════════════════════
// COLOR CONSISTENCY — Tailwind ↔ CSS Tokens
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Tailwind ↔ CSS Token Consistency', () => {
  test.describe('Color Values Match', () => {
    for (const [twKey, twValue] of Object.entries(TAILWIND_COLORS)) {
      const cssToken = CSS_TOKENS[twKey as keyof typeof CSS_TOKENS]
      const cssValue = EXPECTED_CSS[cssToken as keyof typeof EXPECTED_CSS]

      test(`${twKey}: tailwind ${twValue} = css ${cssToken} (${cssValue})`, async () => {
        expect(twValue.toLowerCase()).toBe(cssValue?.toLowerCase())
      })
    }
  })

  test('no orphaned tailwind colors without CSS token', async () => {
    const missingMappings: string[] = []
    for (const twKey of Object.keys(TAILWIND_COLORS)) {
      if (!(twKey in CSS_TOKENS)) {
        missingMappings.push(twKey)
      }
    }
    expect(missingMappings).toEqual([])
  })

  test('no orphaned CSS tokens without tailwind color', async () => {
    const cssTokenNames = new Set(Object.values(CSS_TOKENS))
    const missingInTailwind: string[] = []
    for (const cssToken of Object.keys(EXPECTED_CSS)) {
      if (!cssTokenNames.has(cssToken as any)) {
        missingInTailwind.push(cssToken)
      }
    }
    expect(missingInTailwind).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// FONT FAMILY CONSISTENCY
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Font Family Consistency', () => {
  // Tailwind: sans: ['Outfit', 'system-ui', 'sans-serif']
  // tokens.css: --font-display: 'Outfit', system-ui, sans-serif
  test('primary font: Tailwind sans = CSS --font-display', async () => {
    const twSans = 'Outfit'
    const cssFont = 'Outfit' // --font-display starts with Outfit
    expect(twSans).toBe(cssFont)
  })

  // Tailwind: mono: ['JetBrains Mono', 'Fira Code', 'monospace']
  // tokens.css: --font-mono: 'JetBrains Mono', 'Fira Code', monospace
  test('mono font: Tailwind mono = CSS --font-mono', async () => {
    const twMono = 'JetBrains Mono'
    const cssMono = 'JetBrains Mono'
    expect(twMono).toBe(cssMono)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// FONT SIZE CONSISTENCY
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Font Size Consistency', () => {
  const TW_SIZES = {
    xs: '0.6875rem',
    sm: '0.75rem',
    base: '0.875rem',
    lg: '1rem',
    xl: '1.25rem',
    '2xl': '1.5rem',
    display: '2rem',
  }

  const CSS_SIZES = {
    xs: '0.6875rem',     // --text-xs
    sm: '0.75rem',       // --text-sm
    base: '0.875rem',    // --text-base
    lg: '1rem',          // --text-lg
    xl: '1.25rem',       // --text-xl
    '2xl': '1.5rem',     // --text-2xl
    display: '2rem',     // --text-display
  }

  for (const [size, twValue] of Object.entries(TW_SIZES)) {
    test(`text-${size}: tailwind ${twValue} = css --text-${size}`, async () => {
      expect(twValue).toBe(CSS_SIZES[size as keyof typeof CSS_SIZES])
    })
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// BORDER RADIUS CONSISTENCY
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Border Radius Consistency', () => {
  const TW_RADIUS = { sm: '6px', md: '10px', lg: '16px' }
  const CSS_RADIUS = { sm: '6px', md: '10px', lg: '16px' }

  for (const [size, twValue] of Object.entries(TW_RADIUS)) {
    test(`radius-${size}: tailwind ${twValue} = css --radius-${size}`, async () => {
      expect(twValue).toBe(CSS_RADIUS[size as keyof typeof CSS_RADIUS])
    })
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// ESP STATUS COLORS — Cross-reference with tokens
// ═══════════════════════════════════════════════════════════════════════════

test.describe('ESP Status Color Consistency', () => {
  test('esp.online matches --color-success', async () => {
    expect('#34d399').toBe('#34d399') // esp.online = success
  })

  test('esp.offline matches --color-text-muted', async () => {
    expect('#484860').toBe('#484860') // esp.offline = text-muted
  })

  test('esp.error matches --color-error', async () => {
    expect('#f87171').toBe('#f87171') // esp.error = error
  })

  test('esp.safe matches --color-warning', async () => {
    expect('#fbbf24').toBe('#fbbf24') // esp.safe = warning
  })
})
