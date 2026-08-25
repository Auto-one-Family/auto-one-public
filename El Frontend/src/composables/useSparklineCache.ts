/**
 * useSparklineCache Composable
 *
 * Shared sparkline data cache for sensor live data.
 * Extracts identical logic from MonitorView and SensorsView.
 *
 * Watches espStore.devices and caches recent data points per sensor
 * with 5-second deduplication.
 *
 * Supports loading initial historical data from API to avoid empty
 * sparklines on first render.
 */

import { ref, watch } from 'vue'
import { useEspStore } from '@/stores/esp'
import { sensorsApi } from '@/api/sensors'
import {
  calculateMedianInterval,
  computeExpectedInterval,
  insertGapMarkers,
} from '@/utils/gapDetection'
import type { ChartDataPoint } from '@/components/charts/types'
export type { ChartDataPoint }

const DEFAULT_MAX_POINTS = 30
const DEDUP_INTERVAL_MS = 5000
const MAX_CONCURRENT_REQUESTS = 5
const ON_DEMAND_GAP_THRESHOLD_MS = 120_000
const MIN_DISPLAY_POINTS = 2

export interface SensorIdentifier {
  esp_id: string
  gpio: number
  sensor_type?: string
}

export interface SparklineLiveSensor {
  gpio: number
  sensor_type?: string
  raw_value: number
  last_read?: string | null
  last_reading_at?: string | null
}

/**
 * AUT-837 E1: sparkline / live-tail X is the sample timestamp, never Date.now.
 * last_event_at is receive-time and is not a sample.
 */
export function resolveSensorSampleTimestampMs(
  sensor: {
    last_read?: string | Date | null
    last_reading_at?: string | Date | null
  },
): number | null {
  for (const raw of [sensor.last_read, sensor.last_reading_at]) {
    if (raw == null || raw === '') continue
    const ms = raw instanceof Date ? raw.getTime() : new Date(raw).getTime()
    if (Number.isFinite(ms)) return ms
  }
  return null
}

export function useSparklineCache(maxPoints: number = DEFAULT_MAX_POINTS) {
  const espStore = useEspStore()

  const sparklineCache = ref<Map<string, ChartDataPoint[]>>(new Map())
  const initialLoadInFlight = ref(false)
  const loadedKeys = new Set<string>()

  function getSensorKey(espId: string, gpio: number, sensorType?: string): string {
    return sensorType ? `${espId}-${gpio}-${sensorType}` : `${espId}-${gpio}`
  }

  /**
   * Load initial historical data for a list of sensors.
   * Throttled to MAX_CONCURRENT_REQUESTS parallel API calls.
   * Skips sensors that already have cached data.
   */
  async function loadInitialData(sensors: SensorIdentifier[]): Promise<void> {
    const toLoad = sensors.filter(s => {
      const key = getSensorKey(s.esp_id, s.gpio, s.sensor_type)
      return !loadedKeys.has(key) && !(sparklineCache.value.get(key)?.length)
    })

    if (toLoad.length === 0) return

    initialLoadInFlight.value = true

    try {
      // Process in batches of MAX_CONCURRENT_REQUESTS
      for (let i = 0; i < toLoad.length; i += MAX_CONCURRENT_REQUESTS) {
        const batch = toLoad.slice(i, i + MAX_CONCURRENT_REQUESTS)

        const results = await Promise.allSettled(
          batch.map(s =>
            sensorsApi.queryData({
              esp_id: s.esp_id,
              gpio: s.gpio,
              sensor_type: s.sensor_type,
              limit: maxPoints,
            }).then(response => ({ sensor: s, response }))
          )
        )

        for (const result of results) {
          if (result.status !== 'fulfilled') continue

          const { sensor, response } = result.value
          const key = getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type)
          loadedKeys.add(key)

          if (!response.readings?.length) continue

          // Convert readings to ChartDataPoints, chronological order (oldest first)
          const historicalPoints: ChartDataPoint[] = response.readings
            .map(r => ({
              timestamp: new Date(r.timestamp),
              value: r.raw_value,
            }))
            .sort((a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )

          // Merge with any WS points that arrived during the fetch
          const existing = sparklineCache.value.get(key) || []
          const merged = mergeAndDeduplicate(historicalPoints, existing, maxPoints)
          sparklineCache.value.set(key, merged)
        }
      }
    } finally {
      initialLoadInFlight.value = false
    }
  }

  /**
   * Merge historical and live points, removing duplicates within DEDUP_INTERVAL_MS.
   * Returns chronologically sorted array, capped at maxPoints.
   */
  function mergeAndDeduplicate(
    historical: ChartDataPoint[],
    live: ChartDataPoint[],
    max: number
  ): ChartDataPoint[] {
    if (live.length === 0) return historical.slice(-max)
    if (historical.length === 0) return live.slice(-max)

    // Combine and sort chronologically
    const all = [...historical, ...live].sort((a, b) =>
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )

    // Deduplicate: skip points too close in time with same value
    const deduped: ChartDataPoint[] = [all[0]]
    for (let i = 1; i < all.length; i++) {
      const prev = deduped[deduped.length - 1]
      const curr = all[i]
      const timeDiff = new Date(curr.timestamp).getTime() - new Date(prev.timestamp).getTime()
      if (curr.value !== prev.value || timeDiff > DEDUP_INTERVAL_MS) {
        deduped.push(curr)
      }
    }

    return deduped.slice(-max)
  }

  watch(
    () => espStore.devices,
    () => {
      for (const device of espStore.devices) {
        const deviceId = espStore.getDeviceId(device)
        const sensors = (device.sensors as SparklineLiveSensor[] | undefined) || []
        for (const s of sensors) {
          if (typeof s.raw_value !== 'number') continue
          const sampleMs = resolveSensorSampleTimestampMs(s)
          if (sampleMs == null) continue
          const key = getSensorKey(deviceId, s.gpio, s.sensor_type)
          const existing = sparklineCache.value.get(key) || []
          const lastPoint = existing[existing.length - 1]
          const lastMs = lastPoint ? new Date(lastPoint.timestamp).getTime() : Number.NaN
          // Same or older sample timestamp: tab standby / store refresh must not append.
          if (lastPoint && Number.isFinite(lastMs) && sampleMs <= lastMs) continue
          if (!lastPoint || s.raw_value !== lastPoint.value ||
              sampleMs - lastMs > DEDUP_INTERVAL_MS) {
            const updated = [...existing, { timestamp: new Date(sampleMs), value: s.raw_value }]
            if (updated.length > maxPoints) updated.shift()
            sparklineCache.value.set(key, updated)
          }
        }
      }
    },
    { deep: true }
  )

  /**
   * Returns display-ready sparkline data for a sensor.
   * For on_demand/scheduled sensors: inserts null gaps between distant points
   * so Chart.js breaks the line instead of drawing misleading connections.
   * Returns null when insufficient data (< MIN_DISPLAY_POINTS real values).
   */
  function getSparklineForDisplay(
    key: string,
    operatingMode?: string | null
  ): ChartDataPoint[] | null {
    const points = sparklineCache.value.get(key)
    if (!points || points.length < MIN_DISPLAY_POINTS) return null

    const isSporadic = operatingMode === 'on_demand' || operatingMode === 'scheduled'
    if (!isSporadic) {
      // AUT-837 S4: continuous sensors break the line at data gaps too.
      // Same canonical utils as the charts (median-based raw heuristic, x3).
      const gapPoints = points.map((p) => ({
        timestamp: p.timestamp instanceof Date ? p.timestamp : new Date(p.timestamp),
        value: p.value,
      }))
      const medianMs = calculateMedianInterval(gapPoints)
      const expectedMs = computeExpectedInterval(medianMs, null, gapPoints.length)
      return insertGapMarkers(gapPoints, expectedMs)
    }

    const result: ChartDataPoint[] = [points[0]]
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1]
      const curr = points[i]
      const gap = new Date(curr.timestamp).getTime() - new Date(prev.timestamp).getTime()
      if (gap > ON_DEMAND_GAP_THRESHOLD_MS) {
        const midTime = new Date(
          new Date(prev.timestamp).getTime() + gap / 2
        )
        result.push({ timestamp: midTime, value: null })
      }
      result.push(curr)
    }
    return result
  }

  function hasMinSparklineData(key: string, minPoints = MIN_DISPLAY_POINTS): boolean {
    const points = sparklineCache.value.get(key)
    return !!points && points.length >= minPoints
  }

  return {
    sparklineCache,
    getSensorKey,
    loadInitialData,
    initialLoadInFlight,
    getSparklineForDisplay,
    hasMinSparklineData,
  }
}
