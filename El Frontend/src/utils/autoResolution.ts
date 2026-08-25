import type { SensorDataResolution } from '@/types'

/**
 * Determines the optimal server-side aggregation resolution
 * based on the requested time range.
 *
 * Returns undefined for short ranges where raw data is sufficient
 * (caller should omit `resolution` or send `raw`).
 *
 * | Time Range  | Resolution | Expected Points |
 * |-------------|-----------|-----------------|
 * | <= 1h       | undefined | ~60-120 (raw)   |
 * | <= 6h       | 5m        | ~72             |
 * | <= 12h      | 5m        | ~144            |
 * | <= 7d       | 1h        | ~168            |
 * | > 7d        | 1d        | varies          |
 *
 * Why this matters: GET /sensors/data defaults to raw + LIMIT <= 1000 (DESC).
 * Without aggregation, long windows only return the newest ~1000 rows — the chart
 * x-axis still spans the full range, so points pile up on the right edge.
 */
export function getAutoResolution(
  timeRangeMinutes: number
): SensorDataResolution | undefined {
  if (timeRangeMinutes <= 60) return undefined // Raw data
  if (timeRangeMinutes <= 720) return '5m' // Up to 12h
  if (timeRangeMinutes <= 10080) return '1h' // Up to 7 days
  return '1d'
}

/**
 * Resolution from an absolute time window (ISO strings or Date-compatible).
 * Prefer this over preset→resolution maps so custom ranges stay consistent.
 */
export function getAutoResolutionForWindow(
  startTime: string | number | Date,
  endTime: string | number | Date,
): SensorDataResolution | undefined {
  const startMs = new Date(startTime).getTime()
  const endMs = new Date(endTime).getTime()
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return undefined
  }
  const minutes = (endMs - startMs) / (60 * 1000)
  return getAutoResolution(minutes)
}

/**
 * Maps common time range labels to minutes.
 */
export const TIME_RANGE_MINUTES: Record<string, number> = {
  '1h': 60,
  '6h': 360,
  '12h': 720,
  '24h': 1440,
  '7d': 10080,
  '30d': 43200,
}
