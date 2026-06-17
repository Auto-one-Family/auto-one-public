/**
 * Zone Colors Utility
 *
 * Provides consistent, deterministic color assignment for zones based on ID hash.
 * Uses token-bound colors from the design system.
 */

import { getCssToken, tokens } from '@/utils/cssTokens'

// =============================================================================
// TYPES
// =============================================================================

export interface ZoneColorInfo {
  /** Primary color (resolved CSS color) */
  primary: string
  /** RGB values for CSS rgba() usage */
  rgb: string
  /** Background with opacity for containers */
  background: string
  /** Border color */
  border: string
  /** Hover border color */
  borderHover: string
}

// =============================================================================
// COLOR PALETTE
// =============================================================================

/**
 * Zone color palette using design system colors.
 * Order designed for visual distinction between adjacent zones.
 */
const ZONE_COLOR_TOKENS = [
  '--color-iridescent-1',
  '--color-success',
  '--color-iridescent-3',
  '--color-real',
  '--color-warning',
  '--color-iridescent-4',
  '--color-iridescent-2',
  '--color-accent',
] as const

const DEFAULT_ZONE_COLOR_TOKEN = '--color-text-muted'

function toRgbChannels(value: string): string | null {
  const hexMatch = value.trim().match(/^#([0-9a-fA-F]{6})$/)
  if (hexMatch) {
    const hex = hexMatch[1]
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    return `${r}, ${g}, ${b}`
  }

  const rgbMatch = value.trim().match(/^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})/i)
  if (rgbMatch) {
    return `${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}`
  }

  return null
}

function resolveTokenColor(tokenName: string): { primary: string; rgb: string } {
  const primary =
    getCssToken(tokenName, [DEFAULT_ZONE_COLOR_TOKEN]) ||
    tokens.textMuted ||
    tokens.textSecondary

  const rgb = toRgbChannels(primary) ?? ''
  return { primary, rgb }
}

function toColorAlpha(primary: string, rgb: string, alphaPercent: number): string {
  if (rgb) {
    return `rgba(${rgb}, ${alphaPercent / 100})`
  }
  return `color-mix(in srgb, ${primary} ${alphaPercent}%, transparent)`
}

// =============================================================================
// HASH FUNCTION
// =============================================================================

/**
 * Simple hash function for consistent color assignment.
 * Same zone ID always gets the same color.
 */
function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32-bit integer
  }
  return Math.abs(hash)
}

// =============================================================================
// PUBLIC API
// =============================================================================

/**
 * Get color information for a zone ID.
 * Returns consistent colors based on zone ID hash.
 *
 * @param zoneId - The zone identifier (null for unassigned)
 * @returns ZoneColorInfo object with all color variants
 *
 * @example
 * const color = getZoneColor('zone_tent_1')
 * // Use in Vue template:
 * // :style="{ borderColor: color.primary }"
 * // :style="{ background: color.background }"
 */
export function getZoneColor(zoneId: string | null | undefined): ZoneColorInfo {
  if (!zoneId) {
    const defaultColor = resolveTokenColor(DEFAULT_ZONE_COLOR_TOKEN)
    return {
      primary: defaultColor.primary,
      rgb: defaultColor.rgb,
      background: toColorAlpha(defaultColor.primary, defaultColor.rgb, 5),
      border: toColorAlpha(defaultColor.primary, defaultColor.rgb, 20),
      borderHover: toColorAlpha(defaultColor.primary, defaultColor.rgb, 40),
    }
  }

  const colorIndex = hashString(zoneId) % ZONE_COLOR_TOKENS.length
  const color = resolveTokenColor(ZONE_COLOR_TOKENS[colorIndex])

  return {
    primary: color.primary,
    rgb: color.rgb,
    background: toColorAlpha(color.primary, color.rgb, 5),
    border: toColorAlpha(color.primary, color.rgb, 20),
    borderHover: toColorAlpha(color.primary, color.rgb, 40),
  }
}

/**
 * Get just the RGB string for a zone (for CSS variable usage).
 *
 * @example
 * :style="{ '--zone-color-rgb': getZoneColorRGB('zone_1') }"
 */
export function getZoneColorRGB(zoneId: string | null | undefined): string {
  return getZoneColor(zoneId).rgb
}

/**
 * Get color by index (for manual assignment).
 * Useful when you want predictable color order.
 */
export function getZoneColorByIndex(index: number): ZoneColorInfo {
  const safeIndex = Math.abs(index) % ZONE_COLOR_TOKENS.length
  const color = resolveTokenColor(ZONE_COLOR_TOKENS[safeIndex])

  return {
    primary: color.primary,
    rgb: color.rgb,
    background: toColorAlpha(color.primary, color.rgb, 5),
    border: toColorAlpha(color.primary, color.rgb, 20),
    borderHover: toColorAlpha(color.primary, color.rgb, 40),
  }
}

/**
 * Get all available zone colors (for color picker UI).
 */
export function getAllZoneColors(): Array<{ hex: string; rgb: string }> {
  return ZONE_COLOR_TOKENS.map((tokenName) => {
    const color = resolveTokenColor(tokenName)
    return { hex: color.primary, rgb: color.rgb }
  })
}

/**
 * Check if a zone has a custom color assigned.
 * (Currently always returns false as we use hash-based assignment)
 */
export function hasCustomColor(_zoneId: string): boolean {
  return false
}
