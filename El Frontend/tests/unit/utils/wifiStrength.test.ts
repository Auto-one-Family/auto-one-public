/**
 * WiFi Strength Unit Tests
 *
 * Tests for RSSI to WiFi signal strength conversion utilities.
 */

import { describe, it, expect } from 'vitest'
import {
  getWifiStrength,
  getWifiBars,
  getWifiLabel,
  getWifiQuality,
  isWifiHealthy,
  getWifiColorClass,
  formatRssiDetailed,
  type WifiQuality
} from '@/utils/wifiStrength'

// =============================================================================
// WIFI STRENGTH INFO
// =============================================================================

describe('getWifiStrength', () => {
  it('returns excellent (4 bars) for RSSI >= -50', () => {
    const info = getWifiStrength(-45)
    expect(info.bars).toBe(4)
    expect(info.label).toBe('Ausgezeichnet')
    expect(info.quality).toBe('excellent')
    expect(info.rssi).toBe(-45)
  })

  it('returns good (3 bars) for RSSI >= -60', () => {
    const info = getWifiStrength(-55)
    expect(info.bars).toBe(3)
    expect(info.label).toBe('Gut')
    expect(info.quality).toBe('good')
  })

  it('returns fair (2 bars) for RSSI >= -70', () => {
    const info = getWifiStrength(-65)
    expect(info.bars).toBe(2)
    expect(info.label).toBe('Akzeptabel')
    expect(info.quality).toBe('fair')
  })

  it('returns poor (1 bar) for RSSI >= -80', () => {
    const info = getWifiStrength(-75)
    expect(info.bars).toBe(1)
    expect(info.label).toBe('Schwach')
    expect(info.quality).toBe('poor')
  })

  it('returns none (1 bar) for RSSI < -80', () => {
    const info = getWifiStrength(-85)
    expect(info.bars).toBe(1)
    expect(info.label).toBe('Sehr schwach')
    expect(info.quality).toBe('none')
  })

  it('returns unknown for null RSSI', () => {
    const info = getWifiStrength(null)
    expect(info.bars).toBe(0)
    expect(info.label).toBe('Unbekannt')
    expect(info.quality).toBe('unknown')
    expect(info.rssi).toBe(null)
    expect(info.rssiFormatted).toBe('-')
  })

  it('returns unknown for undefined RSSI', () => {
    const info = getWifiStrength(undefined)
    expect(info.bars).toBe(0)
    expect(info.quality).toBe('unknown')
  })

  it('returns unknown for NaN RSSI', () => {
    const info = getWifiStrength(NaN)
    expect(info.bars).toBe(0)
    expect(info.quality).toBe('unknown')
  })

  it('includes colorVar for excellent', () => {
    const info = getWifiStrength(-45)
    expect(info.colorVar).toBe('--color-success')
  })

  it('includes colorVar for fair', () => {
    const info = getWifiStrength(-65)
    expect(info.colorVar).toBe('--color-warning')
  })

  it('includes colorVar for none', () => {
    const info = getWifiStrength(-85)
    expect(info.colorVar).toBe('--color-error')
  })

  it('formats RSSI string correctly', () => {
    const info = getWifiStrength(-65)
    expect(info.rssiFormatted).toBe('-65 dBm')
  })

  it('returns all required fields', () => {
    const info = getWifiStrength(-60)
    expect(info).toHaveProperty('bars')
    expect(info).toHaveProperty('label')
    expect(info).toHaveProperty('quality')
    expect(info).toHaveProperty('colorVar')
    expect(info).toHaveProperty('rssi')
    expect(info).toHaveProperty('rssiFormatted')
  })

  it('handles boundary value -50 as excellent', () => {
    const info = getWifiStrength(-50)
    expect(info.quality).toBe('excellent')
  })

  it('handles boundary value -60 as good', () => {
    const info = getWifiStrength(-60)
    expect(info.quality).toBe('good')
  })

  it('handles boundary value -70 as fair', () => {
    const info = getWifiStrength(-70)
    expect(info.quality).toBe('fair')
  })

  it('handles boundary value -80 as poor', () => {
    const info = getWifiStrength(-80)
    expect(info.quality).toBe('poor')
  })
})

// =============================================================================
// QUICK ACCESS FUNCTIONS
// =============================================================================

describe('getWifiBars', () => {
  it('returns bar count for RSSI', () => {
    expect(getWifiBars(-45)).toBe(4)
    expect(getWifiBars(-55)).toBe(3)
    expect(getWifiBars(-65)).toBe(2)
    expect(getWifiBars(-75)).toBe(1)
  })

  it('returns 0 bars for invalid RSSI', () => {
    expect(getWifiBars(null)).toBe(0)
    expect(getWifiBars(undefined)).toBe(0)
  })
})

describe('getWifiLabel', () => {
  it('returns German label for RSSI', () => {
    expect(getWifiLabel(-45)).toBe('Ausgezeichnet')
    expect(getWifiLabel(-55)).toBe('Gut')
    expect(getWifiLabel(-65)).toBe('Akzeptabel')
    expect(getWifiLabel(-75)).toBe('Schwach')
    expect(getWifiLabel(-85)).toBe('Sehr schwach')
  })

  it('returns Unbekannt for invalid RSSI', () => {
    expect(getWifiLabel(null)).toBe('Unbekannt')
  })
})

describe('getWifiQuality', () => {
  it('returns quality level for RSSI', () => {
    expect(getWifiQuality(-45)).toBe('excellent')
    expect(getWifiQuality(-55)).toBe('good')
    expect(getWifiQuality(-65)).toBe('fair')
    expect(getWifiQuality(-75)).toBe('poor')
    expect(getWifiQuality(-85)).toBe('none')
  })

  it('returns unknown for invalid RSSI', () => {
    expect(getWifiQuality(null)).toBe('unknown')
  })
})

// =============================================================================
// WIFI HEALTH CHECK
// =============================================================================

describe('isWifiHealthy', () => {
  it('returns true for excellent signal', () => {
    expect(isWifiHealthy(-45)).toBe(true)
  })

  it('returns true for good signal', () => {
    expect(isWifiHealthy(-55)).toBe(true)
  })

  it('returns true for fair signal', () => {
    expect(isWifiHealthy(-65)).toBe(true)
  })

  it('returns false for poor signal', () => {
    expect(isWifiHealthy(-75)).toBe(false)
  })

  it('returns false for none signal', () => {
    expect(isWifiHealthy(-85)).toBe(false)
  })

  it('returns false for unknown signal', () => {
    expect(isWifiHealthy(null)).toBe(false)
    expect(isWifiHealthy(undefined)).toBe(false)
  })
})

// =============================================================================
// CSS COLOR CLASS
// =============================================================================

describe('getWifiColorClass', () => {
  it('returns text-success for excellent', () => {
    expect(getWifiColorClass(-45)).toBe('text-success')
  })

  it('returns text-success for good', () => {
    expect(getWifiColorClass(-55)).toBe('text-success')
  })

  it('returns text-warning for fair', () => {
    expect(getWifiColorClass(-65)).toBe('text-warning')
  })

  it('returns text-warning for poor', () => {
    expect(getWifiColorClass(-75)).toBe('text-warning')
  })

  it('returns text-error for none', () => {
    expect(getWifiColorClass(-85)).toBe('text-error')
  })

  it('returns text-muted for unknown', () => {
    expect(getWifiColorClass(null)).toBe('text-muted')
    expect(getWifiColorClass(undefined)).toBe('text-muted')
  })
})

// =============================================================================
// DETAILED RSSI FORMATTING
// =============================================================================

describe('formatRssiDetailed', () => {
  it('formats RSSI with quality label for excellent', () => {
    expect(formatRssiDetailed(-45)).toBe('-45 dBm (Ausgezeichnet)')
  })

  it('formats RSSI with quality label for good', () => {
    expect(formatRssiDetailed(-55)).toBe('-55 dBm (Gut)')
  })

  it('formats RSSI with quality label for fair', () => {
    expect(formatRssiDetailed(-65)).toBe('-65 dBm (Akzeptabel)')
  })

  it('formats RSSI with quality label for poor', () => {
    expect(formatRssiDetailed(-75)).toBe('-75 dBm (Schwach)')
  })

  it('returns dash for null RSSI', () => {
    expect(formatRssiDetailed(null)).toBe('-')
  })

  it('returns dash for undefined RSSI', () => {
    expect(formatRssiDetailed(undefined)).toBe('-')
  })
})
