/**
 * Formatter Utilities Unit Tests
 *
 * Tests for date, time, number, and value formatting utilities.
 */

import { describe, it, expect } from 'vitest'
import {
  formatNumber,
  formatInteger,
  formatSensorValue,
  formatPercent,
  formatUptime,
  formatUptimeShort,
  formatDuration,
  formatBytes,
  formatRssi,
  getRssiQuality,
  truncateId,
  formatEspId,
  formatBoolean,
  formatOnOff,
  formatEnabled,
  formatCount,
  formatDateTime,
  formatDate,
  formatTime
} from '@/utils/formatters'

// =============================================================================
// NUMBER FORMATTING
// =============================================================================

describe('formatNumber', () => {
  it('formats number with default 2 decimal places', () => {
    expect(formatNumber(23.456)).toBe('23,46')
  })

  it('formats number with specified decimal places', () => {
    expect(formatNumber(23.456, 1)).toBe('23,5')
    expect(formatNumber(23.456, 0)).toBe('23')
    expect(formatNumber(23.456, 3)).toBe('23,456')
  })

  it('returns fallback for null/undefined/NaN', () => {
    expect(formatNumber(null)).toBe('-')
    expect(formatNumber(undefined)).toBe('-')
    expect(formatNumber(NaN)).toBe('-')
  })

  it('uses custom fallback', () => {
    expect(formatNumber(null, 2, 'N/A')).toBe('N/A')
  })

  it('formats thousands with German separator', () => {
    expect(formatNumber(1234.56, 2)).toBe('1.234,56')
  })
})

describe('formatInteger', () => {
  it('formats integer without decimals', () => {
    expect(formatInteger(1234)).toBe('1.234')
  })

  it('rounds float to integer', () => {
    expect(formatInteger(1234.7)).toBe('1.235')
  })

  it('returns fallback for null/undefined', () => {
    expect(formatInteger(null)).toBe('-')
    expect(formatInteger(undefined)).toBe('-')
  })
})

describe('formatSensorValue', () => {
  it('formats value with unit', () => {
    expect(formatSensorValue(23.5, '°C', 1)).toBe('23,5 °C')
  })

  it('formats value without unit', () => {
    expect(formatSensorValue(42, '', 0)).toBe('42')
  })

  it('returns dash for invalid values', () => {
    expect(formatSensorValue(null)).toBe('-')
    expect(formatSensorValue(undefined)).toBe('-')
    expect(formatSensorValue(NaN)).toBe('-')
  })

  it('formats EC with de-DE thousands separator (AUT-26)', () => {
    expect(formatSensorValue(1234, 'µS/cm', 0)).toBe('1.234 µS/cm')
  })

  it('formats CO2 with de-DE thousands separator (AUT-26)', () => {
    expect(formatSensorValue(2500, 'ppm', 0)).toBe('2.500 ppm')
  })

  it('formats pH with comma decimal separator (AUT-26)', () => {
    expect(formatSensorValue(6.8, 'pH', 1)).toBe('6,8 pH')
  })

  it('formats small values correctly (AUT-26)', () => {
    expect(formatSensorValue(42, '°C', 1)).toBe('42,0 °C')
    expect(formatSensorValue(999, 'ppm', 0)).toBe('999 ppm')
  })
})

describe('formatPercent', () => {
  it('formats ratio (0-1) as percentage', () => {
    expect(formatPercent(0.85, 0)).toBe('85%')
  })

  it('formats percentage value (0-100) directly', () => {
    expect(formatPercent(85, 0)).toBe('85%')
  })

  it('formats with decimal places', () => {
    expect(formatPercent(0.8567, 1)).toBe('85,7%')
  })

  it('returns dash for invalid values', () => {
    expect(formatPercent(null)).toBe('-')
  })
})

// =============================================================================
// UPTIME / DURATION FORMATTING
// =============================================================================

describe('formatUptime', () => {
  it('formats seconds only', () => {
    expect(formatUptime(45)).toBe('45s')
  })

  it('formats minutes and seconds', () => {
    expect(formatUptime(125)).toBe('2m 5s')
  })

  it('formats hours, minutes, seconds', () => {
    expect(formatUptime(3661)).toBe('1h 1m 1s')
  })

  it('formats days, hours, minutes', () => {
    expect(formatUptime(90061)).toBe('1d 1h 1m')
  })

  it('returns dash for invalid values', () => {
    expect(formatUptime(null)).toBe('-')
    expect(formatUptime(undefined)).toBe('-')
  })

  it('handles negative values as zero', () => {
    expect(formatUptime(-10)).toBe('0s')
  })
})

describe('formatUptimeShort', () => {
  it('formats short uptime without seconds', () => {
    expect(formatUptimeShort(3661)).toBe('1h 1m')
  })

  it('formats days and hours', () => {
    expect(formatUptimeShort(90000)).toBe('1d 1h')
  })

  it('formats minutes only for short periods', () => {
    expect(formatUptimeShort(120)).toBe('2m')
  })
})

describe('formatDuration', () => {
  it('formats milliseconds', () => {
    expect(formatDuration(500)).toBe('500ms')
  })

  it('formats seconds', () => {
    expect(formatDuration(1500)).toBe('1,5s')
  })

  it('formats longer durations as uptime', () => {
    expect(formatDuration(65000)).toBe('1m 5s')
  })
})

// =============================================================================
// BYTE SIZE FORMATTING
// =============================================================================

describe('formatBytes', () => {
  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512,0 B')
  })

  it('formats kilobytes', () => {
    expect(formatBytes(1536)).toBe('1,5 KB')
  })

  it('formats megabytes', () => {
    expect(formatBytes(1048576)).toBe('1,0 MB')
  })

  it('returns 0 B for zero', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('returns dash for invalid values', () => {
    expect(formatBytes(null)).toBe('-')
    expect(formatBytes(-100)).toBe('-')
  })
})

// =============================================================================
// SIGNAL STRENGTH FORMATTING
// =============================================================================

describe('formatRssi', () => {
  it('formats excellent signal', () => {
    expect(formatRssi(-45)).toBe('-45 dBm (Ausgezeichnet)')
  })

  it('formats very good signal', () => {
    expect(formatRssi(-55)).toBe('-55 dBm (Sehr gut)')
  })

  it('formats good signal', () => {
    expect(formatRssi(-65)).toBe('-65 dBm (Gut)')
  })

  it('formats acceptable signal', () => {
    expect(formatRssi(-75)).toBe('-75 dBm (Akzeptabel)')
  })

  it('formats weak signal', () => {
    expect(formatRssi(-85)).toBe('-85 dBm (Schwach)')
  })

  it('returns dash for invalid values', () => {
    expect(formatRssi(null)).toBe('-')
  })
})

describe('getRssiQuality', () => {
  it('returns excellent for strong signal', () => {
    expect(getRssiQuality(-45)).toBe('excellent')
  })

  it('returns good for moderate signal', () => {
    expect(getRssiQuality(-55)).toBe('good')
  })

  it('returns fair for weak signal', () => {
    expect(getRssiQuality(-70)).toBe('fair')
  })

  it('returns poor for very weak signal', () => {
    expect(getRssiQuality(-85)).toBe('poor')
  })

  it('returns unknown for invalid values', () => {
    expect(getRssiQuality(null)).toBe('unknown')
  })
})

// =============================================================================
// ID FORMATTING
// =============================================================================

describe('truncateId', () => {
  it('truncates long IDs', () => {
    expect(truncateId('ESP_ABCDEF123456', 8)).toBe('ESP_ABCD...')
  })

  it('keeps short IDs unchanged', () => {
    expect(truncateId('ESP_001', 12)).toBe('ESP_001')
  })

  it('returns dash for null/undefined', () => {
    expect(truncateId(null)).toBe('-')
    expect(truncateId(undefined)).toBe('-')
  })
})

describe('formatEspId', () => {
  it('adds (Mock) indicator for mock devices', () => {
    expect(formatEspId('ESP_001', true)).toBe('ESP_001 (Mock)')
  })

  it('keeps ID unchanged for real devices', () => {
    expect(formatEspId('ESP_001', false)).toBe('ESP_001')
  })
})

// =============================================================================
// BOOLEAN FORMATTING
// =============================================================================

describe('formatBoolean', () => {
  it('formats true as Ja', () => {
    expect(formatBoolean(true)).toBe('Ja')
  })

  it('formats false as Nein', () => {
    expect(formatBoolean(false)).toBe('Nein')
  })

  it('returns dash for null/undefined', () => {
    expect(formatBoolean(null)).toBe('-')
    expect(formatBoolean(undefined)).toBe('-')
  })
})

describe('formatOnOff', () => {
  it('formats true as Ein', () => {
    expect(formatOnOff(true)).toBe('Ein')
  })

  it('formats false as Aus', () => {
    expect(formatOnOff(false)).toBe('Aus')
  })
})

describe('formatEnabled', () => {
  it('formats true as Aktiviert', () => {
    expect(formatEnabled(true)).toBe('Aktiviert')
  })

  it('formats false as Deaktiviert', () => {
    expect(formatEnabled(false)).toBe('Deaktiviert')
  })
})

// =============================================================================
// LIST FORMATTING
// =============================================================================

describe('formatCount', () => {
  it('uses singular for count of 1', () => {
    expect(formatCount(1, 'Sensor', 'Sensoren')).toBe('1 Sensor')
  })

  it('uses plural for count > 1', () => {
    expect(formatCount(5, 'Sensor', 'Sensoren')).toBe('5 Sensoren')
  })

  it('uses plural for count of 0', () => {
    expect(formatCount(0, 'Sensor', 'Sensoren')).toBe('0 Sensoren')
  })
})

// =============================================================================
// DATE/TIME FORMATTING
// =============================================================================

describe('formatDateTime', () => {
  it('formats ISO date string to German format', () => {
    // Use a fixed timestamp for consistent testing
    const result = formatDateTime('2024-12-15T14:30:00Z')
    // Should contain German date format components
    expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/)
    expect(result).toMatch(/\d{2}:\d{2}/)
  })

  it('returns dash for null/undefined', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
  })
})

describe('formatDate', () => {
  it('formats date without time', () => {
    const result = formatDate('2024-12-15T14:30:00Z')
    expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/)
    expect(result).not.toContain(':')
  })

  it('returns dash for invalid input', () => {
    expect(formatDate(null)).toBe('-')
  })
})

describe('formatTime', () => {
  it('formats time without seconds by default', () => {
    const result = formatTime('2024-12-15T14:30:45Z')
    expect(result).toMatch(/\d{2}:\d{2}/)
  })

  it('includes seconds when specified', () => {
    const result = formatTime('2024-12-15T14:30:45Z', true)
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('returns dash for invalid input', () => {
    expect(formatTime(null)).toBe('-')
  })
})
