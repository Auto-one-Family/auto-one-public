/**
 * CSS Token Utilities
 *
 * Provides runtime access to CSS custom properties (design tokens)
 * for use in JavaScript contexts where CSS `var()` is not available
 * (e.g., Chart.js configuration objects, canvas drawing, etc.)
 *
 * All values are read from `document.documentElement` at call time,
 * so they respect runtime theme changes.
 */

function getStyle(): CSSStyleDeclaration {
  return getComputedStyle(document.documentElement)
}

/**
 * Read a CSS custom property value from :root.
 *
 * @param name - The CSS variable name including `--` prefix, e.g. `'--color-success'`
 * @returns The trimmed value string, e.g. `'rgb(52, 211, 153)'`
 *
 * @example
 * ```ts
 * import { getCssToken } from '@/utils/cssTokens'
 *
 * const successColor = getCssToken('--color-success')
 * const chartColor = getCssToken('--color-accent')
 * ```
 */
export function getCssToken(name: string, fallbacks: string[] = []): string {
  if (typeof document === 'undefined') return ''

  const style = getStyle()
  const primary = style.getPropertyValue(name).trim()
  if (primary) return primary

  for (const fallback of fallbacks) {
    const value = style.getPropertyValue(fallback).trim()
    if (value) return value
  }

  return ''
}

/**
 * Pre-defined token accessors for commonly used colors in charts and JS contexts.
 * These resolve at call time — safe to use in computed properties.
 *
 * Runtime fallback policy:
 * - Primary token from the requested semantic slot.
 * - If missing: semantic fallback chain (other tokens), never free hex literals.
 * - If still missing: empty string (consumer decides local behavior).
 */
export const tokens = {
  // Status colors
  get success() { return getCssToken('--color-success', ['--color-info']) },
  get warning() { return getCssToken('--color-warning', ['--color-info']) },
  get error() { return getCssToken('--color-error', ['--color-warning']) },
  get info() { return getCssToken('--color-info', ['--color-accent']) },

  // Accent
  get accent() { return getCssToken('--color-accent', ['--color-info']) },
  get accentBright() { return getCssToken('--color-accent-bright', ['--color-accent']) },

  // Device distinction
  get mock() { return getCssToken('--color-mock', ['--color-iridescent-3']) },
  get real() { return getCssToken('--color-real', ['--color-info']) },

  // Sensor status
  get statusGood() { return getCssToken('--color-status-good', ['--color-success']) },
  get statusWarning() { return getCssToken('--color-status-warning', ['--color-warning']) },
  get statusAlarm() { return getCssToken('--color-status-alarm', ['--color-error']) },
  get statusOffline() { return getCssToken('--color-status-offline', ['--color-text-muted']) },

  // Text
  get textPrimary() { return getCssToken('--color-text-primary', ['--color-text-secondary']) },
  get textSecondary() { return getCssToken('--color-text-secondary', ['--color-text-muted']) },
  get textMuted() { return getCssToken('--color-text-muted', ['--color-text-secondary']) },
  get textInverse() { return getCssToken('--color-text-inverse', ['--color-text-primary']) },

  // Backgrounds
  get bgPrimary() { return getCssToken('--color-bg-primary', ['--color-bg-secondary']) },
  get bgSecondary() { return getCssToken('--color-bg-secondary', ['--color-bg-tertiary']) },
  get bgTertiary() { return getCssToken('--color-bg-tertiary', ['--color-bg-secondary']) },
  get backdropColor() { return getCssToken('--backdrop-color', ['--color-bg-primary']) },

  // Threshold zone backgrounds
  get zoneAlarm() { return getCssToken('--color-zone-alarm', ['--color-error-bg']) },
  get zoneWarning() { return getCssToken('--color-zone-warning', ['--color-warning-bg']) },
  get zoneNormal() { return getCssToken('--color-zone-normal', ['--color-success-bg']) },

  // Glass
  get glassBorder() { return getCssToken('--glass-border', ['--color-border']) },

  // Chart gap overlay
  get chartGap() { return getCssToken('--color-chart-gap', ['--color-text-muted']) },
  get chartGapStroke() { return getCssToken('--color-chart-gap-stroke', ['--color-text-muted']) },
}
