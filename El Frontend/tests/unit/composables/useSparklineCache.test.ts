/**
 * useSparklineCache — AUT-837 E1
 * Sample timestamps only; tab standby must not invent holes.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  resolveSensorSampleTimestampMs,
  useSparklineCache,
} from '@/composables/useSparklineCache'

const SECOND = 1000
const MINUTE = 60 * SECOND

function iso(ms: number): string {
  return new Date(ms).toISOString()
}

describe('resolveSensorSampleTimestampMs', () => {
  it('should prefer last_read over last_reading_at and never invent Date.now', () => {
    const lastRead = Date.UTC(2026, 7, 23, 10, 0, 0)
    const laterReading = Date.UTC(2026, 7, 23, 11, 0, 0)
    const before = Date.now()
    expect(resolveSensorSampleTimestampMs({
      last_read: iso(lastRead),
      last_reading_at: iso(laterReading),
    })).toBe(lastRead)
    const after = Date.now()
    expect(resolveSensorSampleTimestampMs({})).toBeNull()
    expect(after - before).toBeLessThan(MINUTE)
  })

  it('should return null when no sample timestamp exists', () => {
    expect(resolveSensorSampleTimestampMs({ last_read: null, last_reading_at: '' })).toBeNull()
  })
})

describe('getSparklineForDisplay', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should not invent holes between existing points when wall clock is far ahead', () => {
    const { sparklineCache, getSparklineForDisplay } = useSparklineCache()
    const t0 = Date.UTC(2026, 7, 23, 10, 0, 0)
    sparklineCache.value.set('esp-1-34-ec', [
      { timestamp: new Date(t0), value: 1200 },
      { timestamp: new Date(t0 + 10 * SECOND), value: 1202 },
      { timestamp: new Date(t0 + 20 * SECOND), value: 1198 },
    ])
    const wallClock = t0 + 5 * MINUTE
    expect(wallClock - t0).toBe(5 * MINUTE)

    const displayed = getSparklineForDisplay('esp-1-34-ec', 'continuous')
    expect(displayed).not.toBeNull()
    const gaps = displayed!.filter((p) => p.value === null)
    expect(gaps).toHaveLength(0)
  })

  it('should still gap a true missing on_demand sample beyond 120s', () => {
    const { sparklineCache, getSparklineForDisplay } = useSparklineCache()
    const t0 = Date.UTC(2026, 7, 23, 10, 0, 0)
    sparklineCache.value.set('esp-1-35-ph', [
      { timestamp: new Date(t0), value: 6.2 },
      { timestamp: new Date(t0 + 3 * MINUTE), value: 6.1 },
    ])
    const displayed = getSparklineForDisplay('esp-1-35-ph', 'on_demand')
    expect(displayed).not.toBeNull()
    expect(displayed!.some((p) => p.value === null)).toBe(true)
  })
})
