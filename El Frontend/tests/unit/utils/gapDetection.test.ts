/**
 * Gap Detection Unit Tests (AUT-837 S3 / AUT-723 OQ-5)
 *
 * Verifies the resolution-aware gap multiplier: aggregated buckets use 1.5
 * (single missing bucket is flagged), raw data keeps 3 (median jitter).
 */

import { describe, it, expect } from 'vitest'
import {
  type GapDataPoint,
  gapMultiplierForResolution,
  insertGapMarkers,
  detectGaps,
  computeExpectedInterval,
  calculateMedianInterval,
  resolutionToMs,
} from '@/utils/gapDetection'

const HOUR = 3_600_000

function hourlyPoints(hours: number[], base = Date.UTC(2026, 5, 12, 0, 0, 0)): GapDataPoint[] {
  return hours.map((h) => ({ timestamp: new Date(base + h * HOUR), value: 20 + h }))
}

describe('gapMultiplierForResolution', () => {
  it('returns 1.5 for aggregated resolutions', () => {
    expect(gapMultiplierForResolution('1m')).toBe(1.5)
    expect(gapMultiplierForResolution('5m')).toBe(1.5)
    expect(gapMultiplierForResolution('1h')).toBe(1.5)
    expect(gapMultiplierForResolution('1d')).toBe(1.5)
  })

  it('returns 3 for raw / unknown / missing resolution', () => {
    expect(gapMultiplierForResolution('raw')).toBe(3)
    expect(gapMultiplierForResolution(null)).toBe(3)
    expect(gapMultiplierForResolution(undefined)).toBe(3)
  })
})

describe('insertGapMarkers with 1h aggregation (AUT-723 OQ-5 regression)', () => {
  // Buckets 00,01,02, [03 missing], 04,05 — gap between 02 and 04 = 2h.
  const points = hourlyPoints([0, 1, 2, 4, 5])
  const expectedIntervalMs = computeExpectedInterval(
    calculateMedianInterval(points),
    '1h',
    points.length,
  )

  it('flags a single missing 1h bucket with the aggregated multiplier (1.5)', () => {
    const result = insertGapMarkers(points, expectedIntervalMs, gapMultiplierForResolution('1h'))
    expect(result.filter((p) => p._gap)).toHaveLength(2) // two markers per gap
  })

  it('old default multiplier (3) would have missed it — documents the fixed bug', () => {
    const result = insertGapMarkers(points, expectedIntervalMs)
    expect(result.filter((p) => p._gap)).toHaveLength(0)
  })

  it('does not flag contiguous 1h buckets', () => {
    const contiguous = hourlyPoints([0, 1, 2, 3, 4, 5])
    const interval = computeExpectedInterval(
      calculateMedianInterval(contiguous),
      '1h',
      contiguous.length,
    )
    const result = insertGapMarkers(contiguous, interval, gapMultiplierForResolution('1h'))
    expect(result.filter((p) => p._gap)).toHaveLength(0)
  })
})

describe('detectGaps consistency with insertGapMarkers', () => {
  it('reports the same single-bucket gap with the aggregated multiplier', () => {
    const points = hourlyPoints([0, 1, 2, 4, 5])
    const interval = computeExpectedInterval(calculateMedianInterval(points), '1h', points.length)
    const gaps = detectGaps(points, interval, gapMultiplierForResolution('1h'))
    expect(gaps).toHaveLength(1)
    expect(gaps[0].durationMs).toBe(2 * HOUR)
  })
})

describe('raw data keeps the conservative multiplier', () => {
  it('median jitter below 3x stays unflagged', () => {
    const base = Date.UTC(2026, 5, 12, 0, 0, 0)
    const offsets = [0, 30, 60, 90, 120, 195] // seconds; last diff 75s < 3x30s
    const points: GapDataPoint[] = offsets.map((s) => ({
      timestamp: new Date(base + s * 1000),
      value: 7,
    }))
    const interval = computeExpectedInterval(calculateMedianInterval(points), null, points.length)
    const result = insertGapMarkers(points, interval, gapMultiplierForResolution(null))
    expect(result.filter((p) => p._gap)).toHaveLength(0)
  })
})

describe('resolutionToMs', () => {
  it('maps known resolutions and falls back to 0', () => {
    expect(resolutionToMs('1h')).toBe(HOUR)
    expect(resolutionToMs('raw')).toBe(0)
    expect(resolutionToMs(null)).toBe(0)
  })
})
