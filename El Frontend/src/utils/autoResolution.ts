import type { SensorDataResolution } from '@/types'

/**
 * Determines the optimal server-side aggregation resolution
 * based on the requested time range.
 *
 * Returns undefined for short ranges where raw data is sufficient.
 *
 * | Time Range  | Resolution | Expected Points |
 * |-------------|-----------|-----------------|
 * | <= 1h       | undefined | ~60-120 (raw)   |
 * | <= 6h       | 5m        | ~72             |
 * | <= 24h      | 1h        | ~24             |
 * | <= 7d       | 1h        | ~168            |
 * | > 7d        | 1d        | varies          |
 */
export function getAutoResolution(
  timeRangeMinutes: number
): SensorDataResolution | undefined {
  if (timeRangeMinutes <= 60) return undefined // Raw data
  if (timeRangeMinutes <= 360) return '5m'
  if (timeRangeMinutes <= 10080) return '1h' // Up to 7 days
  return '1d'
}

/**
 * Maps common time range labels to minutes.
 */
export const TIME_RANGE_MINUTES: Record<string, number> = {
  '1h': 60,
  '6h': 360,
  '24h': 1440,
  '7d': 10080,
  '30d': 43200,
}
