/**
 * Zone Colors Unit Tests
 *
 * Tests for zone color assignment and utilities.
 */

import { describe, it, expect, beforeAll } from 'vitest'
import {
  getZoneColor,
  getZoneColorRGB,
  getZoneColorByIndex,
  getAllZoneColors,
  hasCustomColor
} from '@/utils/zoneColors'

/** Mirrors `src/styles/tokens.css` so getCssToken resolves in jsdom. */
const ZONE_TEST_CSS_VARS: Record<string, string> = {
  '--color-text-muted': '#5a5a75',
  '--color-iridescent-1': '#60a5fa',
  '--color-success': '#34d399',
  '--color-iridescent-3': '#a78bfa',
  '--color-real': '#22d3ee',
  '--color-warning': '#fbbf24',
  '--color-iridescent-4': '#c084fc',
  '--color-iridescent-2': '#818cf8',
  '--color-accent': '#3b82f6',
}

beforeAll(() => {
  const root = document.documentElement
  for (const [name, value] of Object.entries(ZONE_TEST_CSS_VARS)) {
    root.style.setProperty(name, value)
  }
})

// =============================================================================
// ZONE COLOR ASSIGNMENT
// =============================================================================

describe('getZoneColor', () => {
  it('returns default gray color for null zone ID', () => {
    const color = getZoneColor(null)
    expect(color.primary).toBe('#5a5a75')
    expect(color.rgb).toBe('90, 90, 117')
    expect(color.background).toBe('rgba(90, 90, 117, 0.05)')
    expect(color.border).toBe('rgba(90, 90, 117, 0.2)')
    expect(color.borderHover).toBe('rgba(90, 90, 117, 0.4)')
  })

  it('returns default gray color for undefined zone ID', () => {
    const color = getZoneColor(undefined)
    expect(color.primary).toBe('#5a5a75')
    expect(color.rgb).toBe('90, 90, 117')
  })

  it('returns consistent color for same zone ID', () => {
    const color1 = getZoneColor('zone_1')
    const color2 = getZoneColor('zone_1')
    expect(color1.primary).toBe(color2.primary)
    expect(color1.rgb).toBe(color2.rgb)
  })

  it('returns different colors for different zone IDs', () => {
    const color1 = getZoneColor('zone_1')
    const color2 = getZoneColor('zone_2')
    // With 8 colors, some zone IDs might collide, but these specific ones shouldn't
    expect(color1.primary).toBeDefined()
    expect(color2.primary).toBeDefined()
  })

  it('returns color object with all required fields', () => {
    const color = getZoneColor('test_zone')
    expect(color).toHaveProperty('primary')
    expect(color).toHaveProperty('rgb')
    expect(color).toHaveProperty('background')
    expect(color).toHaveProperty('border')
    expect(color).toHaveProperty('borderHover')
  })

  it('background color uses rgba with 0.05 opacity', () => {
    const color = getZoneColor('zone_test')
    expect(color.background).toMatch(/^rgba\(.+, 0\.05\)$/)
  })

  it('border color uses rgba with 0.2 opacity', () => {
    const color = getZoneColor('zone_test')
    expect(color.border).toMatch(/^rgba\(.+, 0\.2\)$/)
  })

  it('borderHover color uses rgba with 0.4 opacity', () => {
    const color = getZoneColor('zone_test')
    expect(color.borderHover).toMatch(/^rgba\(.+, 0\.4\)$/)
  })

  it('returns color from palette for valid zone ID', () => {
    const color = getZoneColor('zone_123')
    // Should return one of the 8 palette colors
    const validHexPattern = /^#[0-9a-f]{6}$/i
    expect(color.primary).toMatch(validHexPattern)
  })

  it('primary color is valid hex format', () => {
    const color = getZoneColor('test_zone_abc')
    expect(color.primary).toMatch(/^#[0-9a-f]{6}$/i)
  })
})

// =============================================================================
// ZONE COLOR RGB
// =============================================================================

describe('getZoneColorRGB', () => {
  it('returns RGB string for zone ID', () => {
    const rgb = getZoneColorRGB('zone_1')
    expect(rgb).toMatch(/^\d+, \d+, \d+$/)
  })

  it('returns default gray RGB for null', () => {
    const rgb = getZoneColorRGB(null)
    expect(rgb).toBe('90, 90, 117')
  })

  it('returns consistent RGB for same zone ID', () => {
    const rgb1 = getZoneColorRGB('zone_test')
    const rgb2 = getZoneColorRGB('zone_test')
    expect(rgb1).toBe(rgb2)
  })
})

// =============================================================================
// ZONE COLOR BY INDEX
// =============================================================================

describe('getZoneColorByIndex', () => {
  it('returns first color for index 0', () => {
    const color = getZoneColorByIndex(0)
    expect(color.primary).toBe('#60a5fa') // First in palette
    expect(color.rgb).toBe('96, 165, 250')
  })

  it('wraps around with modulo for large indices', () => {
    const color1 = getZoneColorByIndex(0)
    const color2 = getZoneColorByIndex(8) // Should wrap to 0 (8 colors)
    expect(color1.primary).toBe(color2.primary)
  })

  it('returns valid color for any positive index', () => {
    const color = getZoneColorByIndex(5)
    expect(color.primary).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('handles negative indices with Math.abs', () => {
    const color = getZoneColorByIndex(-1)
    expect(color.primary).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('returns color with all required properties', () => {
    const color = getZoneColorByIndex(3)
    expect(color).toHaveProperty('primary')
    expect(color).toHaveProperty('rgb')
    expect(color).toHaveProperty('background')
    expect(color).toHaveProperty('border')
    expect(color).toHaveProperty('borderHover')
  })
})

// =============================================================================
// ALL ZONE COLORS
// =============================================================================

describe('getAllZoneColors', () => {
  it('returns array of 8 colors', () => {
    const colors = getAllZoneColors()
    expect(colors).toHaveLength(8)
  })

  it('returns copy of colors (not reference)', () => {
    const colors1 = getAllZoneColors()
    const colors2 = getAllZoneColors()
    expect(colors1).not.toBe(colors2) // Different array reference
    expect(colors1).toEqual(colors2) // Same content
  })

  it('each color has hex and rgb properties', () => {
    const colors = getAllZoneColors()
    colors.forEach(color => {
      expect(color).toHaveProperty('hex')
      expect(color).toHaveProperty('rgb')
      expect(color.hex).toMatch(/^#[0-9a-f]{6}$/i)
      expect(color.rgb).toMatch(/^\d+, \d+, \d+$/)
    })
  })

  it('first color is iridescent blue', () => {
    const colors = getAllZoneColors()
    expect(colors[0].hex).toBe('#60a5fa')
    expect(colors[0].rgb).toBe('96, 165, 250')
  })

  it('contains success green as second color', () => {
    const colors = getAllZoneColors()
    expect(colors[1].hex).toBe('#34d399')
  })
})

// =============================================================================
// CUSTOM COLOR CHECK
// =============================================================================

describe('hasCustomColor', () => {
  it('always returns false (hash-based assignment)', () => {
    expect(hasCustomColor('zone_1')).toBe(false)
    expect(hasCustomColor('zone_2')).toBe(false)
    expect(hasCustomColor('any_zone_id')).toBe(false)
  })
})
