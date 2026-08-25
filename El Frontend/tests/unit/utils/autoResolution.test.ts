import { describe, it, expect } from 'vitest'
import {
  getAutoResolution,
  getAutoResolutionForWindow,
  TIME_RANGE_MINUTES,
} from '@/utils/autoResolution'

describe('getAutoResolution', () => {
  it('should use raw for ranges up to 1h', () => {
    expect(getAutoResolution(60)).toBeUndefined()
    expect(getAutoResolution(TIME_RANGE_MINUTES['1h'])).toBeUndefined()
  })

  it('should use 5m for 6h and 12h windows', () => {
    expect(getAutoResolution(TIME_RANGE_MINUTES['6h'])).toBe('5m')
    expect(getAutoResolution(TIME_RANGE_MINUTES['12h'])).toBe('5m')
  })

  it('should use 1h for 24h and 7d windows', () => {
    expect(getAutoResolution(TIME_RANGE_MINUTES['24h'])).toBe('1h')
    expect(getAutoResolution(TIME_RANGE_MINUTES['7d'])).toBe('1h')
  })

  it('should use 1d beyond 7d', () => {
    expect(getAutoResolution(TIME_RANGE_MINUTES['30d'])).toBe('1d')
  })
})

describe('getAutoResolutionForWindow', () => {
  it('should derive resolution from absolute start/end (custom ranges)', () => {
    const end = new Date('2026-07-24T12:00:00.000Z')
    const start7d = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000)
    expect(getAutoResolutionForWindow(start7d, end)).toBe('1h')

    const start30d = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000)
    expect(getAutoResolutionForWindow(start30d.toISOString(), end.toISOString())).toBe('1d')
  })

  it('should return undefined for invalid or empty windows', () => {
    expect(getAutoResolutionForWindow('invalid', 'also-invalid')).toBeUndefined()
    const t = '2026-07-24T12:00:00.000Z'
    expect(getAutoResolutionForWindow(t, t)).toBeUndefined()
  })

  it('should not fall back to raw for long custom windows', () => {
    // Regression: Monitor DETAIL_RESOLUTION mapped custom → raw (LIMIT 1000 DESC truncates)
    const end = Date.parse('2026-07-24T12:00:00.000Z')
    const start = end - 7 * 24 * 60 * 60 * 1000
    expect(getAutoResolutionForWindow(start, end)).toBe('1h')
  })
})
