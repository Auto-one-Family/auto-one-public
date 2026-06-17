/**
 * Composable: useFertigationKPIs
 *
 * Calculates KPIs for fertigation sensor pairs (inflow vs. runoff).
 * Supports EC and pH measurements with configurable thresholds.
 *
 * Pattern: useZoneKPIs.ts (Reactive Refs, Cleanup, WebSocket Listeners)
 */

import { ref, watch, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { sensorsApi } from '@/api/sensors'
import { websocketService } from '@/services/websocket'
import type { WebSocketMessage } from '@/services/websocket'
import { createLogger } from '@/utils/logger'

const log = createLogger('useFertigationKPIs')

/** Align with `sensor_handler.py` WS broadcast: primary field is `value` (display/processed). */
function numericFromSensorWsPayload(data: Record<string, unknown>): number | null {
  const candidates = [data.value, data.processed_value, data.reading_value]
  for (const c of candidates) {
    if (c === undefined || c === null) continue
    if (typeof c === 'number' && Number.isFinite(c)) return c
    if (typeof c === 'string') {
      const n = Number(c)
      if (Number.isFinite(n)) return n
    }
  }
  return null
}

/**
 * WS `sensor_data` uses raw ESP `timestamp` (sec or ms) or ISO string from some paths.
 * Mirror logic in `sensor.store.ts` normalizeRawTimestamp / server branch.
 */
function isoTimeFromSensorWsPayload(data: Record<string, unknown>): string | null {
  const ts = data.timestamp
  if (ts == null) return null
  if (typeof ts === 'string') {
    const d = new Date(ts)
    return Number.isNaN(d.getTime()) ? null : d.toISOString()
  }
  if (typeof ts === 'number' && Number.isFinite(ts)) {
    const ms = ts > 1e10 ? ts : ts * 1000
    if (ms < 946684800000 || ms > 4102444800000) return null
    return new Date(ms).toISOString()
  }
  return null
}

// =============================================================================
// Types
// =============================================================================

export type FertigationHealthStatus = 'ok' | 'warning' | 'alarm'

export interface FertigationKPIOptions {
  inflowSensorId: Ref<string>
  runoffSensorId: Ref<string>
  timeRange?: Ref<'1h' | '6h' | '24h' | '7d' | '30d'>
  diffWarningThreshold?: Ref<number>  // e.g., 0.5 mS/cm for EC
  diffCriticalThreshold?: Ref<number> // e.g., 0.8 mS/cm for EC
}

export interface FertigationKPI {
  /** Inflow sensor value (latest) */
  inflowValue: number | null
  /** Runoff sensor value (latest) */
  runoffValue: number | null
  /** Difference = runoff - inflow */
  difference: number | null
  /** Difference trend over last N readings: 'up' | 'down' | 'stable' | null */
  differenceTrend: 'up' | 'down' | 'stable' | null
  /** Health status based on thresholds */
  healthStatus: FertigationHealthStatus
  /** Human-readable reason for status (empty for 'ok') */
  healthReason: string
  /** Last measurement time (ISO string) for inflow */
  lastInflowTime: string | null
  /** Last measurement time (ISO string) for runoff */
  lastRunoffTime: string | null
  /** Staleness: time difference between inflow and runoff readings in seconds */
  stalenessSeconds: number | null
  /** Data quality: are both sensors producing data? */
  dataQuality: 'good' | 'degraded' | 'error'
}

// =============================================================================
// Composable
// =============================================================================

export function useFertigationKPIs(options: FertigationKPIOptions) {
  const {
    inflowSensorId,
    runoffSensorId,
    diffWarningThreshold = ref(0.5),
    diffCriticalThreshold = ref(0.8),
  } = options

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  const kpi = ref<FertigationKPI>({
    inflowValue: null,
    runoffValue: null,
    difference: null,
    differenceTrend: null,
    healthStatus: 'ok',
    healthReason: '',
    lastInflowTime: null,
    lastRunoffTime: null,
    stalenessSeconds: null,
    dataQuality: 'error',
  })

  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Track last N differences for trend calculation
  const recentDifferences = ref<number[]>([])
  const DIFFERENCE_HISTORY_SIZE = 10

  // WebSocket unsubscriber functions
  const wsUnsubscribers: (() => void)[] = []

  // -------------------------------------------------------------------------
  // Helper: Calculate trend from recent differences
  // -------------------------------------------------------------------------

  function calculateTrend(diffs: number[]): 'up' | 'down' | 'stable' | null {
    if (diffs.length < 3) return null

    const recent = diffs.slice(-5)
    const firstHalf = recent.slice(0, Math.floor(recent.length / 2))
    const secondHalf = recent.slice(Math.floor(recent.length / 2))

    const avgFirst = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length
    const avgSecond = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length

    const diff = avgSecond - avgFirst
    const threshold = 0.05 // 5% of typical value as stability margin

    if (Math.abs(diff) < threshold) return 'stable'
    return diff > 0 ? 'up' : 'down'
  }

  // -------------------------------------------------------------------------
  // Helper: Calculate health status
  // -------------------------------------------------------------------------

  function calculateHealthStatus(
    difference: number | null,
    dataQuality: 'good' | 'degraded' | 'error',
    stalenessSeconds: number | null,
  ): { status: FertigationHealthStatus; reason: string } {
    if (dataQuality === 'error') {
      return { status: 'alarm', reason: 'Keine Sensordaten verfügbar' }
    }

    if (dataQuality === 'degraded') {
      return { status: 'warning', reason: 'Nur ein Sensor liefert Daten' }
    }

    if (difference === null) {
      return { status: 'alarm', reason: 'Differenz kann nicht berechnet werden' }
    }

    const staleness = stalenessSeconds || 0
    if (staleness > 300) {
      return { status: 'warning', reason: `Messungen sind ${staleness}s auseinander` }
    }

    const absDiff = Math.abs(difference)
    if (absDiff >= diffCriticalThreshold.value) {
      return {
        status: 'alarm',
        reason: `Differenz ${absDiff.toFixed(2)} über kritischem Schwellwert (${diffCriticalThreshold.value})`,
      }
    }

    if (absDiff >= diffWarningThreshold.value) {
      return {
        status: 'warning',
        reason: `Differenz ${absDiff.toFixed(2)} über Warnschwelle (${diffWarningThreshold.value})`,
      }
    }

    return { status: 'ok', reason: '' }
  }

  // -------------------------------------------------------------------------
  // Load initial data from API
  // -------------------------------------------------------------------------

  async function loadInitialData(): Promise<void> {
    if (!inflowSensorId.value || !runoffSensorId.value) {
      error.value = 'Sensor IDs nicht konfiguriert'
      return
    }

    isLoading.value = true
    error.value = null

    try {
      // Query both sensors' latest data
      const [inflowData, runoffData] = await Promise.all([
        sensorsApi.queryData({
          sensor_config_id: inflowSensorId.value,
          limit: 100,
        }),
        sensorsApi.queryData({
          sensor_config_id: runoffSensorId.value,
          limit: 100,
        }),
      ])

      // Extract latest values from readings array
      const inflowReading = (inflowData.readings && inflowData.readings.length > 0)
        ? inflowData.readings[inflowData.readings.length - 1]
        : null

      const runoffReading = (runoffData.readings && runoffData.readings.length > 0)
        ? runoffData.readings[runoffData.readings.length - 1]
        : null

      updateKPIFromReadings(inflowReading, runoffReading)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Fehler beim Laden der Daten'
      log.error('Failed to load initial fertigation data', e)
    } finally {
      isLoading.value = false
    }
  }

  // -------------------------------------------------------------------------
  // Update KPI from sensor readings
  // -------------------------------------------------------------------------

  function updateKPIFromReadings(
    inflowReading: any | null,
    runoffReading: any | null,
  ): void {
    const inflowValue = inflowReading?.processed_value ?? null
    const runoffValue = runoffReading?.processed_value ?? null
    const lastInflowTime = inflowReading?.timestamp ?? null
    const lastRunoffTime = runoffReading?.timestamp ?? null

    // Determine data quality
    let dataQuality: 'good' | 'degraded' | 'error' = 'error'
    if (inflowValue !== null && runoffValue !== null) {
      dataQuality = 'good'
    } else if (inflowValue !== null || runoffValue !== null) {
      dataQuality = 'degraded'
    }

    // Calculate difference
    let difference: number | null = null
    if (inflowValue !== null && runoffValue !== null) {
      difference = runoffValue - inflowValue
      recentDifferences.value.push(difference)
      if (recentDifferences.value.length > DIFFERENCE_HISTORY_SIZE) {
        recentDifferences.value.shift()
      }
    }

    // Calculate staleness (difference between measurement times)
    let stalenessSeconds: number | null = null
    if (lastInflowTime && lastRunoffTime) {
      const inflowMs = new Date(lastInflowTime).getTime()
      const runoffMs = new Date(lastRunoffTime).getTime()
      if (!isNaN(inflowMs) && !isNaN(runoffMs)) {
        stalenessSeconds = Math.abs(runoffMs - inflowMs) / 1000
      }
    }

    // Calculate trend
    const differenceTrend = calculateTrend(recentDifferences.value)

    // Calculate health
    const health = calculateHealthStatus(difference, dataQuality, stalenessSeconds)

    kpi.value = {
      inflowValue,
      runoffValue,
      difference,
      differenceTrend,
      healthStatus: health.status,
      healthReason: health.reason,
      lastInflowTime,
      lastRunoffTime,
      stalenessSeconds,
      dataQuality,
    }
  }

  // -------------------------------------------------------------------------
  // WebSocket listeners for real-time updates
  // -------------------------------------------------------------------------

  function setupWebSocketListeners(): void {
    // Listen for sensor_data events for inflow sensor
    wsUnsubscribers.push(
      websocketService.on('sensor_data', (msg: WebSocketMessage) => {
        const data = msg.data
        if (data && data.config_id === inflowSensorId.value) {
          // Trigger partial update (only update inflow side)
          const nextVal = numericFromSensorWsPayload(data)
          if (nextVal !== null) kpi.value.inflowValue = nextVal
          const nextT = isoTimeFromSensorWsPayload(data)
          if (nextT) kpi.value.lastInflowTime = nextT

          // Recalculate difference and health
          if (kpi.value.inflowValue !== null && kpi.value.runoffValue !== null) {
            const newDiff = kpi.value.runoffValue - kpi.value.inflowValue
            recentDifferences.value.push(newDiff)
            if (recentDifferences.value.length > DIFFERENCE_HISTORY_SIZE) {
              recentDifferences.value.shift()
            }
            kpi.value.difference = newDiff
            kpi.value.differenceTrend = calculateTrend(recentDifferences.value)
          }

          // Recalculate staleness
          if (kpi.value.lastInflowTime && kpi.value.lastRunoffTime) {
            const inflowMs = new Date(kpi.value.lastInflowTime).getTime()
            const runoffMs = new Date(kpi.value.lastRunoffTime).getTime()
            if (!isNaN(inflowMs) && !isNaN(runoffMs)) {
              kpi.value.stalenessSeconds = Math.abs(runoffMs - inflowMs) / 1000

              // Divergence detection: warn if timestamp difference > 5s
              if (kpi.value.stalenessSeconds > 5) {
                log.warn(
                  `Divergence detected on inflow update: staleness ${kpi.value.stalenessSeconds.toFixed(1)}s`,
                  {
                    inflowTime: kpi.value.lastInflowTime,
                    runoffTime: kpi.value.lastRunoffTime,
                    stalenessSeconds: kpi.value.stalenessSeconds,
                  }
                )
              }
            }
          }

          // Recalculate data quality
          if (kpi.value.inflowValue !== null && kpi.value.runoffValue !== null) {
            kpi.value.dataQuality = 'good'
          } else if (kpi.value.inflowValue !== null || kpi.value.runoffValue !== null) {
            kpi.value.dataQuality = 'degraded'
          }

          // Recalculate health
          const health = calculateHealthStatus(
            kpi.value.difference,
            kpi.value.dataQuality,
            kpi.value.stalenessSeconds,
          )
          kpi.value.healthStatus = health.status
          kpi.value.healthReason = health.reason
        }
      })
    )

    // Listen for sensor_data events for runoff sensor
    wsUnsubscribers.push(
      websocketService.on('sensor_data', (msg: WebSocketMessage) => {
        const data = msg.data
        if (data && data.config_id === runoffSensorId.value) {
          // Trigger partial update (only update runoff side)
          const nextVal = numericFromSensorWsPayload(data)
          if (nextVal !== null) kpi.value.runoffValue = nextVal
          const nextT = isoTimeFromSensorWsPayload(data)
          if (nextT) kpi.value.lastRunoffTime = nextT

          // Recalculate difference and health
          if (kpi.value.inflowValue !== null && kpi.value.runoffValue !== null) {
            const newDiff = kpi.value.runoffValue - kpi.value.inflowValue
            recentDifferences.value.push(newDiff)
            if (recentDifferences.value.length > DIFFERENCE_HISTORY_SIZE) {
              recentDifferences.value.shift()
            }
            kpi.value.difference = newDiff
            kpi.value.differenceTrend = calculateTrend(recentDifferences.value)
          }

          // Recalculate staleness
          if (kpi.value.lastInflowTime && kpi.value.lastRunoffTime) {
            const inflowMs = new Date(kpi.value.lastInflowTime).getTime()
            const runoffMs = new Date(kpi.value.lastRunoffTime).getTime()
            if (!isNaN(inflowMs) && !isNaN(runoffMs)) {
              kpi.value.stalenessSeconds = Math.abs(runoffMs - inflowMs) / 1000

              // Divergence detection: warn if timestamp difference > 5s
              if (kpi.value.stalenessSeconds > 5) {
                log.warn(
                  `Divergence detected on runoff update: staleness ${kpi.value.stalenessSeconds.toFixed(1)}s`,
                  {
                    inflowTime: kpi.value.lastInflowTime,
                    runoffTime: kpi.value.lastRunoffTime,
                    stalenessSeconds: kpi.value.stalenessSeconds,
                  }
                )
              }
            }
          }

          // Recalculate data quality
          if (kpi.value.inflowValue !== null && kpi.value.runoffValue !== null) {
            kpi.value.dataQuality = 'good'
          } else if (kpi.value.inflowValue !== null || kpi.value.runoffValue !== null) {
            kpi.value.dataQuality = 'degraded'
          }

          // Recalculate health
          const health = calculateHealthStatus(
            kpi.value.difference,
            kpi.value.dataQuality,
            kpi.value.stalenessSeconds,
          )
          kpi.value.healthStatus = health.status
          kpi.value.healthReason = health.reason
        }
      })
    )
  }

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  onMounted(() => {
    loadInitialData()
    setupWebSocketListeners()
  })

  onUnmounted(() => {
    for (const unsub of wsUnsubscribers) {
      unsub()
    }
    wsUnsubscribers.length = 0
  })

  // Watch for sensor ID changes → refetch
  watch([inflowSensorId, runoffSensorId], () => {
    recentDifferences.value = []
    loadInitialData()
  })

  return { kpi, isLoading, error, reload: loadInitialData }
}