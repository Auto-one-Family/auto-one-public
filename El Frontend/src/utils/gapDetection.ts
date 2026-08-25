import type { SensorDataResolution } from '@/types'

// =============================================================================
// Types
// =============================================================================

export interface GapDataPoint {
  timestamp: Date
  value: number | null
  minValue?: number | null
  maxValue?: number | null
  _gap?: boolean
}

export interface GapInfo {
  startTime: Date
  endTime: Date
  durationMs: number
}

export type GapMarkingMode = 'auto' | 'hatched' | 'off'

// =============================================================================
// Resolution ↔ Milliseconds mapping
// =============================================================================

const RESOLUTION_MS: Record<string, number> = {
  '1m': 60_000,
  '5m': 300_000,
  '1h': 3_600_000,
  '1d': 86_400_000,
}

export function resolutionToMs(
  resolution: SensorDataResolution | string | null | undefined,
): number {
  if (!resolution) return 0
  return RESOLUTION_MS[resolution] ?? 0
}

// =============================================================================
// Expected interval computation
// =============================================================================

const SPARSE_POINT_THRESHOLD = 5
const DEFAULT_GAP_MULTIPLIER = 3
const AGGREGATED_GAP_MULTIPLIER = 1.5

/**
 * Gap-detection multiplier for a given resolution (AUT-837 S3 / AUT-723 OQ-5).
 *
 * Aggregated buckets (1m/5m/1h/1d) have an exact server-side cadence, so a
 * single missing bucket (= 2x interval) must be flagged -> 1.5.
 * Raw data has jittery, median-derived intervals -> 3 avoids false positives.
 */
export function gapMultiplierForResolution(
  resolution: SensorDataResolution | string | null | undefined,
): number {
  return resolutionToMs(resolution) > 0
    ? AGGREGATED_GAP_MULTIPLIER
    : DEFAULT_GAP_MULTIPLIER
}

/**
 * Determines the expected interval between data points.
 *
 * For sparse data (< 5 points), the median is unreliable so we
 * prefer the resolution bucket size when available.
 * For normal data, we take the larger of median and resolution
 * to avoid false-positive gap detection on aggregated data.
 */
export function computeExpectedInterval(
  medianMs: number,
  resolution: SensorDataResolution | string | null | undefined,
  pointCount: number,
): number {
  const resMs = resolutionToMs(resolution)
  if (pointCount < SPARSE_POINT_THRESHOLD && resMs > 0) {
    return resMs
  }
  return Math.max(medianMs, resMs)
}

// =============================================================================
// Median interval
// =============================================================================

/**
 * Calculates median interval from sorted data points.
 * Returns 0 if fewer than 2 points.
 */
export function calculateMedianInterval(
  points: Array<{ timestamp: Date }>,
): number {
  if (points.length < 2) return 0
  const intervals: number[] = []
  for (let i = 1; i < points.length; i++) {
    intervals.push(
      points[i].timestamp.getTime() - points[i - 1].timestamp.getTime(),
    )
  }
  intervals.sort((a, b) => a - b)
  return intervals[Math.floor(intervals.length / 2)]
}

// =============================================================================
// Gap detection
// =============================================================================

/**
 * Finds all gaps in the data where consecutive real data points
 * are separated by more than `expectedIntervalMs * multiplier`.
 */
export function detectGaps(
  points: Array<{ timestamp: Date; value: number | null }>,
  expectedIntervalMs: number,
  multiplier: number = DEFAULT_GAP_MULTIPLIER,
): GapInfo[] {
  if (points.length < 2 || expectedIntervalMs <= 0) return []
  const threshold = expectedIntervalMs * multiplier
  const gaps: GapInfo[] = []

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const curr = points[i]
    if (prev.value === null || curr.value === null) continue

    const timeDiff = curr.timestamp.getTime() - prev.timestamp.getTime()
    if (timeDiff > threshold) {
      gaps.push({
        startTime: prev.timestamp,
        endTime: curr.timestamp,
        durationMs: timeDiff,
      })
    }
  }
  return gaps
}

// =============================================================================
// Gap marker insertion
// =============================================================================

/**
 * Inserts null gap markers where time between consecutive points
 * exceeds expectedIntervalMs * multiplier.
 *
 * Inserts TWO markers per gap (after last valid point + before next)
 * to create a clean visual line break. Markers are tagged with `_gap: true`.
 */
export function insertGapMarkers(
  points: GapDataPoint[],
  expectedIntervalMs: number,
  multiplier: number = DEFAULT_GAP_MULTIPLIER,
): GapDataPoint[] {
  if (points.length < 2 || expectedIntervalMs <= 0) return points
  const threshold = expectedIntervalMs * multiplier
  const result: GapDataPoint[] = [points[0]]

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const curr = points[i]
    const timeDiff = curr.timestamp.getTime() - prev.timestamp.getTime()

    if (timeDiff > threshold && prev.value !== null) {
      result.push({
        timestamp: new Date(prev.timestamp.getTime() + 1),
        value: null,
        _gap: true,
      })
      result.push({
        timestamp: new Date(curr.timestamp.getTime() - 1),
        value: null,
        _gap: true,
      })
    }
    result.push(curr)
  }
  return result
}

// =============================================================================
// Helpers
// =============================================================================

export function countRealDataPoints(points: GapDataPoint[]): number {
  return points.filter((p) => p.value !== null && !p._gap).length
}

export function formatGapDuration(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} Min`
  if (ms < 86_400_000) {
    const h = Math.floor(ms / 3_600_000)
    const m = Math.round((ms % 3_600_000) / 60_000)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }
  const d = Math.floor(ms / 86_400_000)
  const h = Math.round((ms % 86_400_000) / 3_600_000)
  return h > 0 ? `${d}d ${h}h` : `${d}d`
}

export function formatTimeShort(date: Date): string {
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

/**
 * AUT-837 E1: L3 x-axis max is the last sample timestamp, never wall clock.
 */
export function lastFiniteSampleX(
  datasets: Array<{ data?: Array<{ x?: number | string | Date | null }> }>,
): number | null {
  let max = Number.NEGATIVE_INFINITY
  for (const dataset of datasets) {
    for (const point of dataset.data ?? []) {
      const raw = point?.x
      const x =
        typeof raw === 'number'
          ? raw
          : raw instanceof Date
            ? raw.getTime()
            : typeof raw === 'string'
              ? new Date(raw).getTime()
              : Number.NaN
      if (Number.isFinite(x) && x > max) max = x
    }
  }
  return Number.isFinite(max) ? max : null
}
