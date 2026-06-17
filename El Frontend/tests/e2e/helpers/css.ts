/**
 * CSS Test Utilities for Playwright E2E Tests
 *
 * Provides helper functions for:
 * - Reading CSS custom properties (design tokens) from :root
 * - Computing and comparing CSS property values
 * - WCAG 2.1 AA color contrast ratio calculation
 * - Animation detection
 * - Viewport-specific assertions
 */

import type { Page, Locator } from '@playwright/test'

// ═══════════════════════════════════════════════════════════════════════════
// DESIGN TOKEN UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Read a single CSS custom property from :root
 *
 * @example
 * const bgColor = await getDesignToken(page, '--color-bg-primary')
 * // Returns: '#07070d' or 'rgb(7, 7, 13)' depending on browser
 */
export async function getDesignToken(page: Page, tokenName: string): Promise<string> {
  return page.evaluate((name: string) => {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  }, tokenName)
}

/**
 * Read all CSS custom properties from :root that match a prefix
 *
 * @example
 * const bgTokens = await getDesignTokensByPrefix(page, '--color-bg')
 * // Returns: { '--color-bg-primary': '#07070d', '--color-bg-secondary': '#0d0d16', ... }
 */
export async function getDesignTokensByPrefix(
  page: Page,
  prefix: string
): Promise<Record<string, string>> {
  return page.evaluate((pfx: string) => {
    const styles = getComputedStyle(document.documentElement)
    const result: Record<string, string> = {}
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          if (rule instanceof CSSStyleRule && rule.selectorText === ':root') {
            for (let i = 0; i < rule.style.length; i++) {
              const prop = rule.style[i]
              if (prop.startsWith(pfx)) {
                result[prop] = styles.getPropertyValue(prop).trim()
              }
            }
          }
        }
      } catch {
        // Cross-origin stylesheets cannot be accessed
      }
    }
    return result
  }, prefix)
}

/**
 * Read all CSS custom properties from :root
 */
export async function getAllDesignTokens(page: Page): Promise<Record<string, string>> {
  return getDesignTokensByPrefix(page, '--')
}

/**
 * Assert a CSS custom property has a specific value
 * Compares the computed value against the expected raw value
 */
export async function assertDesignToken(
  page: Page,
  tokenName: string,
  expectedValue: string
): Promise<void> {
  const actual = await getDesignToken(page, tokenName)
  if (actual !== expectedValue) {
    throw new Error(
      `Design token ${tokenName}: expected "${expectedValue}", got "${actual}"`
    )
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COMPUTED STYLE UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get a computed CSS property from a Playwright Locator
 *
 * @example
 * const bg = await getComputedStyleProp(page.locator('.card'), 'background-color')
 * // Returns: 'rgb(13, 13, 22)'
 */
export async function getComputedStyleProp(
  locator: Locator,
  property: string
): Promise<string> {
  return locator.evaluate((el: Element, prop: string) => {
    return getComputedStyle(el).getPropertyValue(prop).trim()
  }, property)
}

/**
 * Get multiple computed CSS properties from a Playwright Locator
 *
 * @example
 * const styles = await getComputedStyles(page.locator('.btn'), ['color', 'background-color', 'border-radius'])
 * // Returns: { color: 'rgb(255, 255, 255)', 'background-color': '...', 'border-radius': '10px' }
 */
export async function getComputedStyles(
  locator: Locator,
  properties: string[]
): Promise<Record<string, string>> {
  return locator.evaluate((el: Element, props: string[]) => {
    const styles = getComputedStyle(el)
    const result: Record<string, string> = {}
    for (const prop of props) {
      result[prop] = styles.getPropertyValue(prop).trim()
    }
    return result
  }, properties)
}

/**
 * Check if an element has a specific CSS class
 */
export async function hasClass(locator: Locator, className: string): Promise<boolean> {
  return locator.evaluate((el: Element, cls: string) => {
    return el.classList.contains(cls)
  }, className)
}

// ═══════════════════════════════════════════════════════════════════════════
// ANIMATION UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Check if an element has an active CSS animation
 *
 * @example
 * const isPulsing = await hasActiveAnimation(page.locator('.status-dot'))
 * expect(isPulsing).toBe(true)
 */
export async function hasActiveAnimation(locator: Locator): Promise<boolean> {
  return locator.evaluate((el: Element) => {
    const style = getComputedStyle(el)
    const name = style.animationName
    const duration = parseFloat(style.animationDuration)
    return name !== 'none' && name !== '' && duration > 0
  })
}

/**
 * Get the animation name of an element
 */
export async function getAnimationName(locator: Locator): Promise<string> {
  return locator.evaluate((el: Element) => {
    return getComputedStyle(el).animationName
  })
}

/**
 * Check if an element has a CSS transition defined
 */
export async function hasTransition(locator: Locator): Promise<boolean> {
  return locator.evaluate((el: Element) => {
    const style = getComputedStyle(el)
    const duration = style.transitionDuration
    // '0s' means no transition
    return duration !== '0s' && duration !== ''
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// COLOR UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Parse a CSS color string to an [R, G, B] tuple
 * Supports: rgb(r, g, b), rgba(r, g, b, a), #hex, #rrggbb
 *
 * @example
 * parseRGB('rgb(52, 211, 153)') // [52, 211, 153]
 * parseRGB('#34d399')           // [52, 211, 153]
 * parseRGB('rgba(52, 211, 153, 0.5)') // [52, 211, 153]
 */
export function parseRGB(value: string): [number, number, number] {
  // rgb/rgba format
  const rgbMatch = value.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/)
  if (rgbMatch) {
    return [parseInt(rgbMatch[1]), parseInt(rgbMatch[2]), parseInt(rgbMatch[3])]
  }

  // 6-digit hex
  const hex6Match = value.match(/^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/)
  if (hex6Match) {
    return [parseInt(hex6Match[1], 16), parseInt(hex6Match[2], 16), parseInt(hex6Match[3], 16)]
  }

  // 3-digit hex
  const hex3Match = value.match(/^#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$/)
  if (hex3Match) {
    return [
      parseInt(hex3Match[1] + hex3Match[1], 16),
      parseInt(hex3Match[2] + hex3Match[2], 16),
      parseInt(hex3Match[3] + hex3Match[3], 16),
    ]
  }

  throw new Error(`Cannot parse color: "${value}"`)
}

/**
 * Parse CSS alpha from rgba string
 * Returns 1 if not rgba
 */
export function parseAlpha(value: string): number {
  const match = value.match(/rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([\d.]+)\s*\)/)
  return match ? parseFloat(match[1]) : 1
}

/**
 * Calculate relative luminance of a color per WCAG 2.1
 * https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
 */
export function relativeLuminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((c) => {
    const sRGB = c / 255
    return sRGB <= 0.04045
      ? sRGB / 12.92
      : Math.pow((sRGB + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * Calculate WCAG 2.1 contrast ratio between two colors
 *
 * @returns Contrast ratio (1:1 to 21:1)
 *
 * WCAG 2.1 AA requirements:
 * - Normal text: ≥ 4.5:1
 * - Large text (≥18pt or ≥14pt bold): ≥ 3:1
 * - UI components & graphical objects: ≥ 3:1
 *
 * @example
 * const ratio = contrastRatio(parseRGB('#eaeaf2'), parseRGB('#07070d'))
 * expect(ratio).toBeGreaterThanOrEqual(4.5) // WCAG AA normal text
 */
export function contrastRatio(
  fg: [number, number, number],
  bg: [number, number, number]
): number {
  const l1 = relativeLuminance(fg)
  const l2 = relativeLuminance(bg)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * Check if two colors meet WCAG 2.1 AA contrast requirements
 */
export function meetsContrastAA(
  fg: [number, number, number],
  bg: [number, number, number],
  isLargeText = false
): boolean {
  const ratio = contrastRatio(fg, bg)
  return isLargeText ? ratio >= 3 : ratio >= 4.5
}

/**
 * Blend a semi-transparent RGBA color onto an opaque background
 * Useful for testing badge backgrounds that use rgba() on dark backgrounds
 */
export function blendColor(
  fg: [number, number, number],
  fgAlpha: number,
  bg: [number, number, number]
): [number, number, number] {
  return [
    Math.round(fg[0] * fgAlpha + bg[0] * (1 - fgAlpha)),
    Math.round(fg[1] * fgAlpha + bg[1] * (1 - fgAlpha)),
    Math.round(fg[2] * fgAlpha + bg[2] * (1 - fgAlpha)),
  ]
}

// ═══════════════════════════════════════════════════════════════════════════
// RESPONSIVE TESTING UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/** Standard viewport breakpoints matching the design system */
export const VIEWPORTS = {
  mobile: { width: 375, height: 667 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 720 },
  wide: { width: 1920, height: 1080 },
} as const

/**
 * Check if an element is visible in the viewport
 * (not just display:none but actually visible to the user)
 */
export async function isVisibleInViewport(locator: Locator): Promise<boolean> {
  return locator.evaluate((el: Element) => {
    const rect = el.getBoundingClientRect()
    const style = getComputedStyle(el)
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      parseFloat(style.opacity) > 0
    )
  })
}

/**
 * Get the actual rendered size of an element
 */
export async function getElementSize(
  locator: Locator
): Promise<{ width: number; height: number }> {
  return locator.evaluate((el: Element) => {
    const rect = el.getBoundingClientRect()
    return { width: rect.width, height: rect.height }
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// DESIGN TOKEN REFERENCE — Expected values from tokens.css
// ═══════════════════════════════════════════════════════════════════════════

/** Expected design token values (source of truth: src/styles/tokens.css) */
export const EXPECTED_TOKENS = {
  // Background hierarchy
  '--color-bg-primary': '#07070d',
  '--color-bg-secondary': '#0d0d16',
  '--color-bg-tertiary': '#15151f',
  '--color-bg-quaternary': '#1d1d2a',

  // Text hierarchy
  '--color-text-primary': '#eaeaf2',
  '--color-text-secondary': '#8585a0',
  '--color-text-muted': '#484860',

  // Accent
  '--color-accent': '#3b82f6',
  '--color-accent-bright': '#60a5fa',
  '--color-accent-dim': '#1e3a5f',

  // Iridescent
  '--color-iridescent-1': '#60a5fa',
  '--color-iridescent-2': '#818cf8',
  '--color-iridescent-3': '#a78bfa',
  '--color-iridescent-4': '#c084fc',

  // Status
  '--color-success': '#34d399',
  '--color-warning': '#fbbf24',
  '--color-error': '#f87171',
  '--color-info': '#60a5fa',

  // Mock/Real
  '--color-mock': '#a78bfa',
  '--color-real': '#22d3ee',

  // Spacing
  '--space-1': '0.25rem',
  '--space-2': '0.5rem',
  '--space-3': '0.75rem',
  '--space-4': '1rem',
  '--space-6': '1.5rem',
  '--space-8': '2rem',
  '--space-12': '3rem',

  // Radius
  '--radius-sm': '6px',
  '--radius-md': '10px',
  '--radius-lg': '16px',
  '--radius-full': '9999px',

  // Typography
  '--text-xs': '0.6875rem',
  '--text-sm': '0.75rem',
  '--text-base': '0.875rem',
  '--text-lg': '1rem',
  '--text-xl': '1.25rem',
  '--text-2xl': '1.5rem',
  '--text-display': '2rem',

  // Z-index
  '--z-base': '0',
  '--z-dropdown': '10',
  '--z-sticky': '20',
  '--z-fixed': '30',
  '--z-modal-backdrop': '40',
  '--z-modal': '50',
  '--z-popover': '60',
  '--z-tooltip': '70',

  // Layout
  '--sidebar-width': '15rem',
  '--header-height': '3.5rem',
} as const

/** RGB equivalents for hex color tokens (for toHaveCSS assertions) */
export const TOKEN_RGB = {
  '--color-bg-primary': 'rgb(7, 7, 13)',
  '--color-bg-secondary': 'rgb(13, 13, 22)',
  '--color-bg-tertiary': 'rgb(21, 21, 31)',
  '--color-bg-quaternary': 'rgb(29, 29, 42)',
  '--color-text-primary': 'rgb(234, 234, 242)',
  '--color-text-secondary': 'rgb(133, 133, 160)',
  '--color-text-muted': 'rgb(72, 72, 96)',
  '--color-accent': 'rgb(59, 130, 246)',
  '--color-accent-bright': 'rgb(96, 165, 250)',
  '--color-success': 'rgb(52, 211, 153)',
  '--color-warning': 'rgb(251, 191, 36)',
  '--color-error': 'rgb(248, 113, 113)',
  '--color-info': 'rgb(96, 165, 250)',
  '--color-mock': 'rgb(167, 139, 250)',
  '--color-real': 'rgb(34, 211, 238)',
} as const
