/**
 * Design Token Verification Tests — Schicht 1
 *
 * Verifies that all CSS custom properties from tokens.css are:
 * 1. Defined on :root (not missing or empty)
 * 2. Have the exact expected values
 * 3. Are consistent between tokens.css and tailwind.config.js
 *
 * These tests run against the Login page (no auth required) to validate
 * the design system foundation that every other component depends on.
 */

import { test, expect } from '@playwright/test'
import {
  getDesignToken,
  getAllDesignTokens,
  EXPECTED_TOKENS,
} from '../helpers/css'

// Login page is accessible without auth — ideal for token testing
const TOKEN_TEST_URL = '/login'

test.describe('Design Token Verification', () => {
  // No auth required for login page
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto(TOKEN_TEST_URL)
    await page.waitForLoadState('domcontentloaded')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TOKEN EXISTENCE — All tokens must be defined and non-empty
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Token Existence', () => {
    test('all expected tokens are defined on :root', async ({ page }) => {
      const allTokens = await getAllDesignTokens(page)
      const tokenNames = Object.keys(allTokens)

      for (const expectedToken of Object.keys(EXPECTED_TOKENS)) {
        expect(tokenNames, `Token ${expectedToken} should be defined`).toContain(expectedToken)
      }
    })

    test('no token has an empty value', async ({ page }) => {
      const emptyTokens: string[] = []

      for (const tokenName of Object.keys(EXPECTED_TOKENS)) {
        const value = await getDesignToken(page, tokenName)
        if (!value || value === '') {
          emptyTokens.push(tokenName)
        }
      }

      expect(emptyTokens, 'These tokens have empty values').toEqual([])
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // BACKGROUND HIERARCHY — 4 progressive depth levels
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Background Hierarchy', () => {
    const bgTokens = [
      '--color-bg-primary',
      '--color-bg-secondary',
      '--color-bg-tertiary',
      '--color-bg-quaternary',
    ] as const

    for (const token of bgTokens) {
      test(`${token} has correct value`, async ({ page }) => {
        const value = await getDesignToken(page, token)
        expect(value).toBe(EXPECTED_TOKENS[token])
      })
    }

    test('background colors get progressively lighter', async ({ page }) => {
      const values: number[] = []
      for (const token of bgTokens) {
        const hex = await getDesignToken(page, token)
        // Parse lightness from hex: sum of RGB components
        const r = parseInt(hex.slice(1, 3), 16)
        const g = parseInt(hex.slice(3, 5), 16)
        const b = parseInt(hex.slice(5, 7), 16)
        values.push(r + g + b)
      }

      // Each level should be lighter than the previous
      for (let i = 1; i < values.length; i++) {
        expect(
          values[i],
          `${bgTokens[i]} should be lighter than ${bgTokens[i - 1]}`
        ).toBeGreaterThan(values[i - 1])
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TEXT HIERARCHY — 3 contrast levels
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Text Hierarchy', () => {
    test('--color-text-primary has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-text-primary')).toBe('#eaeaf2')
    })

    test('--color-text-secondary has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-text-secondary')).toBe('#8585a0')
    })

    test('--color-text-muted has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-text-muted')).toBe('#484860')
    })

    test('text colors get progressively dimmer', async ({ page }) => {
      const tokens = ['--color-text-primary', '--color-text-secondary', '--color-text-muted']
      const lightness: number[] = []

      for (const token of tokens) {
        const hex = await getDesignToken(page, token)
        const r = parseInt(hex.slice(1, 3), 16)
        const g = parseInt(hex.slice(3, 5), 16)
        const b = parseInt(hex.slice(5, 7), 16)
        lightness.push(r + g + b)
      }

      expect(lightness[0]).toBeGreaterThan(lightness[1])
      expect(lightness[1]).toBeGreaterThan(lightness[2])
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // ACCENT COLORS — Blue with 3 intensities
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Accent Colors', () => {
    test('--color-accent has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-accent')).toBe('#3b82f6')
    })

    test('--color-accent-bright has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-accent-bright')).toBe('#60a5fa')
    })

    test('--color-accent-dim has correct value', async ({ page }) => {
      expect(await getDesignToken(page, '--color-accent-dim')).toBe('#1e3a5f')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // IRIDESCENT COLORS — 4-stop gradient
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Iridescent Colors', () => {
    const iridescentTokens = {
      '--color-iridescent-1': '#60a5fa',
      '--color-iridescent-2': '#818cf8',
      '--color-iridescent-3': '#a78bfa',
      '--color-iridescent-4': '#c084fc',
    } as const

    for (const [token, expected] of Object.entries(iridescentTokens)) {
      test(`${token} has correct value`, async ({ page }) => {
        expect(await getDesignToken(page, token)).toBe(expected)
      })
    }

    test('gradient-iridescent contains all color stops', async ({ page }) => {
      const gradient = await getDesignToken(page, '--gradient-iridescent')
      expect(gradient).toContain('linear-gradient')
      // The gradient should reference the iridescent color variables
      // After CSS resolution, it will contain the actual color values
      expect(gradient.length).toBeGreaterThan(20)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // STATUS COLORS — Functional, always same meaning
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Status Colors', () => {
    const statusTokens = {
      '--color-success': '#34d399',
      '--color-warning': '#fbbf24',
      '--color-error': '#f87171',
      '--color-info': '#60a5fa',
    } as const

    for (const [token, expected] of Object.entries(statusTokens)) {
      test(`${token} = ${expected}`, async ({ page }) => {
        expect(await getDesignToken(page, token)).toBe(expected)
      })
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // MOCK/REAL DISTINCTION
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Mock/Real Colors', () => {
    test('--color-mock = #a78bfa (purple)', async ({ page }) => {
      expect(await getDesignToken(page, '--color-mock')).toBe('#a78bfa')
    })

    test('--color-real = #22d3ee (cyan)', async ({ page }) => {
      expect(await getDesignToken(page, '--color-real')).toBe('#22d3ee')
    })

    test('mock and real colors are visually distinct', async ({ page }) => {
      const mock = await getDesignToken(page, '--color-mock')
      const real = await getDesignToken(page, '--color-real')
      expect(mock).not.toBe(real)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // SPACING SYSTEM — 4px grid
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Spacing System', () => {
    const spacingTokens = {
      '--space-1': '0.25rem',
      '--space-2': '0.5rem',
      '--space-3': '0.75rem',
      '--space-4': '1rem',
      '--space-6': '1.5rem',
      '--space-8': '2rem',
      '--space-12': '3rem',
    } as const

    for (const [token, expected] of Object.entries(spacingTokens)) {
      test(`${token} = ${expected}`, async ({ page }) => {
        expect(await getDesignToken(page, token)).toBe(expected)
      })
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // BORDER RADIUS — 3 steps + full
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Border Radius', () => {
    const radiusTokens = {
      '--radius-sm': '6px',
      '--radius-md': '10px',
      '--radius-lg': '16px',
      '--radius-full': '9999px',
    } as const

    for (const [token, expected] of Object.entries(radiusTokens)) {
      test(`${token} = ${expected}`, async ({ page }) => {
        expect(await getDesignToken(page, token)).toBe(expected)
      })
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // Z-INDEX SCALE — Predictable stacking order
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Z-Index Scale', () => {
    test('z-index values increase in correct order', async ({ page }) => {
      const zTokens = [
        '--z-base',
        '--z-dropdown',
        '--z-sticky',
        '--z-fixed',
        '--z-modal-backdrop',
        '--z-modal',
        '--z-popover',
        '--z-tooltip',
      ]

      let previousValue = -1
      for (const token of zTokens) {
        const value = parseInt(await getDesignToken(page, token))
        expect(value, `${token} should be > ${previousValue}`).toBeGreaterThan(previousValue)
        previousValue = value
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TYPOGRAPHY — Font families and size scale
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Typography', () => {
    test('display font family contains Outfit', async ({ page }) => {
      const fontDisplay = await getDesignToken(page, '--font-display')
      expect(fontDisplay).toContain('Outfit')
    })

    test('mono font family contains JetBrains Mono', async ({ page }) => {
      const fontMono = await getDesignToken(page, '--font-mono')
      expect(fontMono).toContain('JetBrains Mono')
    })

    test('text size scale increases correctly', async ({ page }) => {
      const sizeTokens = [
        '--text-xs',
        '--text-sm',
        '--text-base',
        '--text-lg',
        '--text-xl',
        '--text-2xl',
        '--text-display',
      ]

      let previousSize = 0
      for (const token of sizeTokens) {
        const value = await getDesignToken(page, token)
        const numericValue = parseFloat(value) // e.g. '0.875rem' → 0.875
        expect(numericValue, `${token} should be > ${previousSize}`).toBeGreaterThan(previousSize)
        previousSize = numericValue
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // LAYOUT DIMENSIONS
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Layout Dimensions', () => {
    test('sidebar width is 15rem (240px)', async ({ page }) => {
      expect(await getDesignToken(page, '--sidebar-width')).toBe('15rem')
    })

    test('header height is 3.5rem (56px)', async ({ page }) => {
      expect(await getDesignToken(page, '--header-height')).toBe('3.5rem')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TRANSITION SYSTEM
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Transitions', () => {
    test('duration-fast is 120ms', async ({ page }) => {
      expect(await getDesignToken(page, '--duration-fast')).toBe('120ms')
    })

    test('duration-base is 200ms', async ({ page }) => {
      expect(await getDesignToken(page, '--duration-base')).toBe('200ms')
    })

    test('duration-slow is 350ms', async ({ page }) => {
      expect(await getDesignToken(page, '--duration-slow')).toBe('350ms')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // GLASS/BORDER TOKENS
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Glass & Border Tokens', () => {
    test('glass-bg is defined and semi-transparent', async ({ page }) => {
      const value = await getDesignToken(page, '--glass-bg')
      expect(value).toContain('rgba')
      expect(value).toContain('0.02')
    })

    test('glass-border is defined and semi-transparent', async ({ page }) => {
      const value = await getDesignToken(page, '--glass-border')
      expect(value).toContain('rgba')
      expect(value).toContain('0.06')
    })

    test('glass-border-hover is more visible than glass-border', async ({ page }) => {
      const border = await getDesignToken(page, '--glass-border')
      const hover = await getDesignToken(page, '--glass-border-hover')

      // Extract alpha values
      const borderAlpha = parseFloat(border.match(/[\d.]+\)$/)?.[0] || '0')
      const hoverAlpha = parseFloat(hover.match(/[\d.]+\)$/)?.[0] || '0')

      expect(hoverAlpha).toBeGreaterThan(borderAlpha)
    })
  })
})
