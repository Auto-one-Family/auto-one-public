/**
 * WiFi Strength Utility
 *
 * Converts RSSI (dBm) values to human-readable signal strength indicators.
 * Provides bar counts, German labels, and quality levels for UI display.
 */

// =============================================================================
// TYPES
// =============================================================================

export type WifiQuality = 'excellent' | 'good' | 'fair' | 'poor' | 'none' | 'unknown'

export interface WifiStrengthInfo {
  /** Number of signal bars (0-4) */
  bars: number
  /** German label for the signal quality */
  label: string
  /** Quality level for conditional styling */
  quality: WifiQuality
  /** CSS color variable name */
  colorVar: string
  /** Original RSSI value */
  rssi: number | null
  /** Formatted RSSI string */
  rssiFormatted: string
}

// =============================================================================
// THRESHOLDS
// =============================================================================

/**
 * RSSI thresholds for signal quality.
 * Based on common WiFi signal strength standards:
 * - >= -50 dBm: Excellent (4 bars)
 * - >= -60 dBm: Good (3 bars)
 * - >= -70 dBm: Fair (2 bars)
 * - >= -80 dBm: Poor (1 bar)
 * - < -80 dBm: Very poor (0-1 bars)
 */
const THRESHOLDS = {
  excellent: -50,
  good: -60,
  fair: -70,
  poor: -80,
}

// =============================================================================
// PUBLIC API
// =============================================================================

/**
 * Get comprehensive WiFi strength information from RSSI value.
 *
 * @param rssi - WiFi signal strength in dBm (typically -30 to -90)
 * @returns WifiStrengthInfo object with all display properties
 *
 * @example
 * const wifi = getWifiStrength(-65)
 * // wifi.bars = 3
 * // wifi.label = "Gut"
 * // wifi.quality = "good"
 */
export function getWifiStrength(rssi: number | null | undefined): WifiStrengthInfo {
  // Handle null/undefined/invalid values
  if (rssi === null || rssi === undefined || isNaN(rssi)) {
    return {
      bars: 0,
      label: 'Unbekannt',
      quality: 'unknown',
      colorVar: '--color-text-muted',
      rssi: null,
      rssiFormatted: '-',
    }
  }

  // Determine quality level and properties
  let bars: number
  let label: string
  let quality: WifiQuality
  let colorVar: string

  if (rssi >= THRESHOLDS.excellent) {
    bars = 4
    label = 'Ausgezeichnet'
    quality = 'excellent'
    colorVar = '--color-success'
  } else if (rssi >= THRESHOLDS.good) {
    bars = 3
    label = 'Gut'
    quality = 'good'
    colorVar = '--color-success'
  } else if (rssi >= THRESHOLDS.fair) {
    bars = 2
    label = 'Akzeptabel'
    quality = 'fair'
    colorVar = '--color-warning'
  } else if (rssi >= THRESHOLDS.poor) {
    bars = 1
    label = 'Schwach'
    quality = 'poor'
    colorVar = '--color-warning'
  } else {
    bars = 1
    label = 'Sehr schwach'
    quality = 'none'
    colorVar = '--color-error'
  }

  return {
    bars,
    label,
    quality,
    colorVar,
    rssi,
    rssiFormatted: `${rssi} dBm`,
  }
}

/**
 * Get just the number of bars for a quick display.
 *
 * @example
 * const bars = getWifiBars(-65) // Returns 3
 */
export function getWifiBars(rssi: number | null | undefined): number {
  return getWifiStrength(rssi).bars
}

/**
 * Get the German label for the signal quality.
 *
 * @example
 * const label = getWifiLabel(-65) // Returns "Gut"
 */
export function getWifiLabel(rssi: number | null | undefined): string {
  return getWifiStrength(rssi).label
}

/**
 * Get the quality level for conditional styling.
 *
 * @example
 * const quality = getWifiQuality(-65) // Returns "good"
 */
export function getWifiQuality(rssi: number | null | undefined): WifiQuality {
  return getWifiStrength(rssi).quality
}

/**
 * Check if WiFi signal is considered healthy (fair or better).
 */
export function isWifiHealthy(rssi: number | null | undefined): boolean {
  const { quality } = getWifiStrength(rssi)
  return quality === 'excellent' || quality === 'good' || quality === 'fair'
}

/**
 * Get CSS color class based on signal quality.
 *
 * @example
 * const colorClass = getWifiColorClass(-65) // Returns "text-success"
 */
export function getWifiColorClass(rssi: number | null | undefined): string {
  const { quality } = getWifiStrength(rssi)

  switch (quality) {
    case 'excellent':
    case 'good':
      return 'text-success'
    case 'fair':
    case 'poor':
      return 'text-warning'
    case 'none':
      return 'text-error'
    default:
      return 'text-muted'
  }
}

/**
 * Format RSSI with quality indicator for detailed display.
 *
 * @example
 * formatRssiDetailed(-65) // Returns "-65 dBm (Gut)"
 */
export function formatRssiDetailed(rssi: number | null | undefined): string {
  const info = getWifiStrength(rssi)
  if (info.rssi === null) return '-'
  return `${info.rssiFormatted} (${info.label})`
}
