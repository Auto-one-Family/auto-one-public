import type { ChartDataPoint } from '@/components/charts/types'

export type TrendDirection = 'rising' | 'stable' | 'falling'

export interface TrendResult {
  direction: TrendDirection
  slope: number
}

// Sensor-type-specific thresholds for trend detection
// Slope per data point at which the trend is considered "rising"
export const TREND_THRESHOLDS: Record<string, number> = {
  // Temperature: 0.2°C per point (at 5s interval = significant)
  ds18b20: 0.2,
  sht31_temp: 0.2,
  bme280_temp: 0.2,
  // pH: 0.05 per point (pH is logarithmic, 0.1 change is significant)
  ph: 0.05,
  // Humidity: 0.5% per point
  sht31_humidity: 0.5,
  bme280_humidity: 0.5,
  // EC: 2.0 µS/cm per point
  ec: 2.0,
  // Pressure: 0.5 hPa per point
  bme280_pressure: 0.5,
  // CO2: 5 ppm per point
  co2: 5,
  // Soil moisture: 0.5% per point
  moisture: 0.5,
  // Flow: 0.2 L/min per point
  flow: 0.2,
  // Light: 100 lux per point
  light: 100,
}

const DEFAULT_TREND_THRESHOLD = 0.1

/**
 * Calculate trend direction via linear regression (least squares).
 * Returns 'stable' with slope 0 when fewer than 5 data points.
 */
export function calculateTrend(
  points: ChartDataPoint[],
  sensorType?: string
): TrendResult {
  const valid = points.filter(p => p.value != null) as { value: number; timestamp: string | Date }[]
  if (valid.length < 5) return { direction: 'stable', slope: 0 }

  const threshold = sensorType != null ? (TREND_THRESHOLDS[sensorType] ?? DEFAULT_TREND_THRESHOLD) : DEFAULT_TREND_THRESHOLD
  const n = valid.length
  const values = valid.map(p => p.value)

  const meanX = (n - 1) / 2
  const meanY = values.reduce((a, b) => a + b, 0) / n

  let numerator = 0
  let denominator = 0
  for (let i = 0; i < n; i++) {
    numerator += (i - meanX) * (values[i] - meanY)
    denominator += (i - meanX) ** 2
  }

  const slope = denominator === 0 ? 0 : numerator / denominator
  const direction: TrendDirection =
    slope > threshold ? 'rising' :
    slope < -threshold ? 'falling' :
    'stable'

  return { direction, slope }
}
