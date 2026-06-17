<script setup lang="ts">
/**
 * MultiSensorChart Component
 *
 * Industrietaugliches Chart für Multi-Sensor-Analyse.
 * Kombiniert historische Daten mit Live-WebSocket-Updates.
 *
 * Features:
 * - Historische Daten aus API (wenn verfügbar)
 * - Live-Updates via WebSocket (Echtzeit-Daten)
 * - Fallback für Mock-ESPs ohne historische Daten
 * - Robustes Error-Handling mit Retry-Logik
 * - Automatische Daten-Aggregation für große Zeiträume
 * - Memory-effiziente Datenpunkt-Limitierung
 * - Zoom/Pan support via chartjs-plugin-zoom (8.0-A)
 * - Dual Y-axis for different units (8.0-B)
 *
 * Phase 4: Charts & Drag-Drop (Industrial-Grade)
 */

import { ref, computed, watch, onMounted, onUnmounted, shallowRef } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  Filler,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import zoomPlugin from 'chartjs-plugin-zoom'
import 'chartjs-adapter-date-fns'
import { RotateCcw } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { websocketService } from '@/services/websocket'
import type { ChartSensor, SensorReading, SensorDataResolution } from '@/types'
import { createLogger } from '@/utils/logger'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'
import { getAutoResolution, TIME_RANGE_MINUTES } from '@/utils/autoResolution'

const log = createLogger('MultiSensorChart')

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  Filler,
  zoomPlugin,
  annotationPlugin,
)

// =============================================================================
// Constants
// =============================================================================

/** Safety-cap: max data points per sensor after server-side aggregation */
const MAX_DATA_POINTS = 1000

/** Retry configuration */
const RETRY_CONFIG = {
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 10000,
} as const

/** Millisecond threshold to distinguish unix seconds from unix milliseconds */
const TIMESTAMP_MS_THRESHOLD = 1_000_000_000_000

/** Time range configurations */
const TIME_RANGES = {
  '1h': { ms: 60 * 60 * 1000, label: '1 Stunde' },
  '6h': { ms: 6 * 60 * 60 * 1000, label: '6 Stunden' },
  '24h': { ms: 24 * 60 * 60 * 1000, label: '24 Stunden' },
  '7d': { ms: 7 * 24 * 60 * 60 * 1000, label: '7 Tage' },
  '30d': { ms: 30 * 24 * 60 * 60 * 1000, label: '30 Tage' },
} as const

// =============================================================================
// Actuator Overlay Types (P8-A6c)
// =============================================================================

export interface ActuatorOverlayBlock {
  start: number  // timestamp ms
  end: number    // timestamp ms
  value: number | null  // 0.0–1.0 or null for stop
}

export interface ActuatorOverlayEvent {
  timestamp: number  // timestamp ms
  label: string
  isOn: boolean
}

export interface ActuatorOverlay {
  id: string
  label: string
  color: string
  blocks: ActuatorOverlayBlock[]
  events: ActuatorOverlayEvent[]
}

// =============================================================================
// Props & Emits
// =============================================================================

interface Props {
  /** Sensoren die angezeigt werden sollen */
  sensors: ChartSensor[]
  /** Zeitraum-Preset */
  timeRange?: '1h' | '6h' | '24h' | '7d' | '30d'
  /** Chart-Höhe in Pixeln */
  height?: number
  /** Auto-Refresh-Intervall in Sekunden (0 = deaktiviert) */
  refreshInterval?: number
  /** Y-Achse Minimum (undefined = auto) */
  yMin?: number
  /** Y-Achse Maximum (undefined = auto) */
  yMax?: number
  /** Live-Updates aktivieren */
  enableLiveUpdates?: boolean
  /** Actuator overlay data for correlation display (P8-A6c) */
  actuatorOverlays?: ActuatorOverlay[]
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '24h',
  height: 300,
  refreshInterval: 0,
  yMin: undefined,
  yMax: undefined,
  enableLiveUpdates: true,
  actuatorOverlays: () => [],
})

const emit = defineEmits<{
  /** Wird gefeuert wenn Daten geladen wurden */
  dataLoaded: [sensorId: string, pointCount: number]
  /** Wird gefeuert bei Fehlern */
  error: [message: string]
}>()

// =============================================================================
// State
// =============================================================================

/** Loading-State für initiales Laden */
const isLoading = ref(false)

/** Error-State mit Retry-Zähler */
const error = ref<{ message: string; retryCount: number } | null>(null)

/**
 * Sensor-Daten Map: sensorId → SensorReading[]
 * Verwendet shallowRef für Performance (Chart.js mutiert nicht)
 */
const sensorData = shallowRef<Map<string, SensorReading[]>>(new Map())

/** Live-Daten die via WebSocket empfangen wurden */
const liveDataPoints = ref<Map<string, SensorReading[]>>(new Map())

/** WebSocket-Subscription-IDs für Cleanup */
const wsSubscriptionIds = ref<string[]>([])

/** Refresh-Timer */
let refreshTimer: ReturnType<typeof setInterval> | null = null

/** Retry-Timer */
let retryTimer: ReturnType<typeof setTimeout> | null = null

/** Zoom state (8.0-A) */
const chartRef = ref<InstanceType<typeof Line> | null>(null)
const isZoomed = ref(false)
const timelineAnchorMs = ref(Date.now())
const isChartHoverActive = ref(false)


// =============================================================================
// Computed
// =============================================================================

/** Zeitraum in Millisekunden */
const timeRangeMs = computed(() => {
  return TIME_RANGES[props.timeRange]?.ms || TIME_RANGES['24h'].ms
})

const timelineStartMs = computed(() => timelineAnchorMs.value - timeRangeMs.value)
const timelineEndMs = computed(() => timelineAnchorMs.value)

/** Server-side aggregation resolution based on time range */
const currentResolution = computed<SensorDataResolution | undefined>(() => {
  const minutes = TIME_RANGE_MINUTES[props.timeRange] ?? 1440
  return getAutoResolution(minutes)
})

/** Zeitraum-Label für Anzeige */
const timeRangeLabel = computed(() => {
  return TIME_RANGES[props.timeRange]?.label || '24 Stunden'
})

const isCompactChart = computed(() => props.height <= 180)
const stateMinHeightPx = computed(() => {
  const sensorCount = Math.max(props.sensors.length, 1)
  const base = isCompactChart.value ? 92 : 112
  return base + Math.min((sensorCount - 1) * 8, 32)
})
const chartContainerHeightPx = computed(() => {
  const requested = Number.isFinite(props.height) ? props.height : 300
  return Math.max(stateMinHeightPx.value + 18, requested)
})

/** Kombinierte Daten: Historisch + Live */
const combinedData = computed(() => {
  const combined = new Map<string, SensorReading[]>()

  for (const sensor of props.sensors) {
    const historical = sensorData.value.get(sensor.id) || []
    const live = liveDataPoints.value.get(sensor.id) || []

    // Merge und sortiere nach Timestamp
    const merged = [...historical, ...live]
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

    // Dedupliziere (gleicher Timestamp = überspringen)
    const deduplicated: SensorReading[] = []
    let lastTimestamp = ''
    for (const reading of merged) {
      if (reading.timestamp !== lastTimestamp) {
        deduplicated.push(reading)
        lastTimestamp = reading.timestamp
      }
    }

    // Limitiere auf MAX_DATA_POINTS (behalte neueste)
    const limited = deduplicated.slice(-MAX_DATA_POINTS)
    combined.set(sensor.id, limited)
  }

  return combined
})

/** Prüft ob Live-Daten vorhanden sind */
const hasLiveData = computed(() => {
  for (const sensor of props.sensors) {
    const data = liveDataPoints.value.get(sensor.id) || []
    if (data.length > 0) return true
  }
  return false
})

/** Gesamtzahl der Datenpunkte */
const totalDataPoints = computed(() => {
  let total = 0
  for (const readings of combinedData.value.values()) {
    total += readings.length
  }
  return total
})

/** Shared sensor type config (if all sensors share the same type) */
const sharedSensorTypeConfig = computed(() => {
  if (props.sensors.length === 0) return null
  const types = new Set(props.sensors.map(s => s.sensorType).filter(Boolean))
  if (types.size !== 1) return null
  const type = [...types][0]
  return type ? SENSOR_TYPE_CONFIG[type] ?? null : null
})

// =============================================================================
// Dual Y-Axis (8.0-B)
// =============================================================================

/** Map units to sensor IDs */
const unitGroups = computed(() => {
  const groups = new Map<string, string[]>()
  for (const sensor of props.sensors) {
    const unit = sensor.unit || ''
    if (!groups.has(unit)) groups.set(unit, [])
    groups.get(unit)!.push(sensor.id)
  }
  return groups
})

/** Unique units across all sensors */
const uniqueUnits = computed(() => [...unitGroups.value.keys()])

/** Whether dual Y-axis is needed (>= 2 different units) */
const needsDualAxis = computed(() => uniqueUnits.value.length >= 2)

/** Whether actuator overlays are present (P8-A6c) */
const hasActuatorOverlays = computed(() =>
  (props.actuatorOverlays || []).some(o => o.blocks.length > 0)
)

/** Actuator switch-event annotations — max 20 most recent (P8-A6c) */
const actuatorAnnotations = computed(() => {
  const overlays = props.actuatorOverlays || []
  const allEvents: Array<{ timestamp: number; label: string; isOn: boolean; color: string }> = []
  for (const overlay of overlays) {
    for (const event of overlay.events) {
      if (!Number.isFinite(event.timestamp)) continue
      allEvents.push({ ...event, color: overlay.color })
    }
  }
  // Sort by timestamp, take last 20
  allEvents.sort((a, b) => a.timestamp - b.timestamp)
  const recent = allEvents.slice(-20)
  const annotations: Record<string, unknown> = {}
  for (let i = 0; i < recent.length; i++) {
    const e = recent[i]
    annotations[`act_evt_${i}`] = {
      type: 'line',
      scaleID: 'x',
      value: e.timestamp,
      borderColor: 'rgba(76, 175, 80, 0.5)',
      borderWidth: 1,
      borderDash: [4, 4],
      borderCapStyle: 'butt',
    }
  }
  return annotations
})

const hasActuatorAnnotations = computed(() => Object.keys(actuatorAnnotations.value).length > 0)

/**
 * Compute Y-axis range for sensors with a specific unit.
 * Returns suggestedMin/suggestedMax with 15% padding.
 */
function computeRangeForUnit(unit: string): { min: number | undefined; max: number | undefined } {
  const sensorIds = unitGroups.value.get(unit) || []
  let minVal = Infinity
  let maxVal = -Infinity

  for (const sensorId of sensorIds) {
    const readings = combinedData.value.get(sensorId) || []
    for (const reading of readings) {
      const value = reading.processed_value ?? reading.raw_value
      if (typeof value === 'number' && !isNaN(value)) {
        minVal = Math.min(minVal, value)
        maxVal = Math.max(maxVal, value)
      }
    }
  }

  if (minVal === Infinity) return { min: undefined, max: undefined }

  const range = maxVal - minVal
  const padding = range > 0 ? range * 0.15 : 1

  return {
    min: Math.floor((minVal - padding) * 10) / 10,
    max: Math.ceil((maxVal + padding) * 10) / 10,
  }
}

/** Berechne Y-Achsen-Bereich automatisch mit Puffer (global, for single-axis mode) */
const computedYRange = computed(() => {
  let minVal = Infinity
  let maxVal = -Infinity
  let valueCount = 0

  for (const [_sensorId, readings] of combinedData.value.entries()) {
    for (const reading of readings) {
      const value = reading.processed_value ?? reading.raw_value
      if (typeof value === 'number' && !isNaN(value)) {
        minVal = Math.min(minVal, value)
        maxVal = Math.max(maxVal, value)
        valueCount++
      }
    }
  }

  if (minVal === Infinity || maxVal === -Infinity) {
    return { min: undefined, max: undefined }
  }

  const range = maxVal - minVal
  const padding = range > 0 ? range * 0.15 : 1

  return {
    min: Math.floor((minVal - padding) * 10) / 10,
    max: Math.ceil((maxVal + padding) * 10) / 10,
  }
})

/** Chart-Daten im Chart.js Format */
const chartData = computed(() => {
  // Sensor datasets — rendered ABOVE actuator bars (order: 2)
  const sensorDatasets = props.sensors.map((sensor) => {
    const readings = combinedData.value.get(sensor.id) || []
    const unit = sensor.unit || ''
    const unitIndex = uniqueUnits.value.indexOf(unit)

    // Assign yAxisID: first unit → 'y' (left), second → 'y1' (right) (8.0-B)
    let yAxisID = 'y'
    if (needsDualAxis.value && unitIndex >= 1) {
      yAxisID = unitIndex === 1 ? 'y1' : 'y' // 3rd+ unit shares left axis
    }

    return {
      type: 'line' as const,
      label: sensor.name,
      data: readings.flatMap((r) => {
        const timestampMs = toTimestampMs(r.timestamp)
        if (timestampMs == null) return []
        return [{
          x: timestampMs,
          y: r.processed_value ?? r.raw_value ?? null,
        }]
      }),
      borderColor: sensor.color,
      backgroundColor: `${sensor.color}20`,
      borderWidth: 2,
      pointRadius: readings.length > 100 ? 0 : 2,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
      spanGaps: false, // AUT-837 S2: never interpolate across gaps (null values break the line)
      yAxisID,
      order: 2,
    }
  })

  // Actuator overlay datasets — rendered BEHIND sensor lines (order: 0) (P8-A6c)
  const actuatorDatasets = (props.actuatorOverlays || []).map((overlay) => ({
    type: 'bar' as const,
    label: `${overlay.label} (Status)`,
    data: overlay.blocks.map((block) => ({
      x: [block.start, block.end],
      y: 1,
    })),
    yAxisID: 'y-actuator',
    backgroundColor: overlay.blocks.map((block) =>
      block.value != null && block.value > 0
        ? `rgba(76, 175, 80, ${0.12 * block.value})`
        : 'transparent'
    ),
    barPercentage: 1.0,
    categoryPercentage: 1.0,
    borderSkipped: false as const,
    order: 0,
  }))

  return { datasets: [...actuatorDatasets, ...sensorDatasets] }
})

/** Chart.js Optionen */
const chartOptions = computed(() => {
  // Build Y-axis scales (8.0-B)
  const yScales: Record<string, any> = {}
  const safeActuatorAnnotations = hasActuatorAnnotations.value ? actuatorAnnotations.value : {}

  if (needsDualAxis.value) {
    // Left axis (first unit)
    const leftUnit = uniqueUnits.value[0]
    const leftRange = computeRangeForUnit(leftUnit)
    yScales.y = {
      type: 'linear' as const,
      position: 'left' as const,
      beginAtZero: false,
      ...(props.yMin != null ? { suggestedMin: props.yMin } : leftRange.min != null ? { suggestedMin: leftRange.min } : {}),
      ...(props.yMax != null ? { suggestedMax: props.yMax } : leftRange.max != null ? { suggestedMax: leftRange.max } : {}),
      title: {
        display: true,
        text: leftUnit,
        color: 'rgba(255, 255, 255, 0.5)',
        font: { size: 11 },
      },
      grid: { color: 'rgba(255, 255, 255, 0.05)' },
      ticks: { color: 'rgba(255, 255, 255, 0.5)' },
    }

    // Right axis (second unit)
    if (uniqueUnits.value.length >= 2) {
      const rightUnit = uniqueUnits.value[1]
      const rightRange = computeRangeForUnit(rightUnit)
      yScales.y1 = {
        type: 'linear' as const,
        position: 'right' as const,
        beginAtZero: false,
        ...(rightRange.min != null ? { suggestedMin: rightRange.min } : {}),
        ...(rightRange.max != null ? { suggestedMax: rightRange.max } : {}),
        title: {
          display: true,
          text: rightUnit,
          color: 'rgba(255, 255, 255, 0.5)',
          font: { size: 11 },
        },
        grid: { drawOnChartArea: false }, // No grid overlay from right axis
        ticks: { color: 'rgba(255, 255, 255, 0.5)' },
      }
    }
  } else {
    // Single axis (original behavior)
    yScales.y = {
      beginAtZero: false,
      ...(props.yMin != null ? { suggestedMin: props.yMin }
        : sharedSensorTypeConfig.value ? { suggestedMin: sharedSensorTypeConfig.value.min }
        : computedYRange.value.min != null ? { suggestedMin: computedYRange.value.min }
        : {}),
      ...(props.yMax != null ? { suggestedMax: props.yMax }
        : sharedSensorTypeConfig.value ? { suggestedMax: sharedSensorTypeConfig.value.max }
        : computedYRange.value.max != null ? { suggestedMax: computedYRange.value.max }
        : {}),
      grid: { color: 'rgba(255, 255, 255, 0.05)' },
      ticks: { color: 'rgba(255, 255, 255, 0.5)' },
    }
  }

  return {
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: {
        top: 4,
        right: isCompactChart.value ? 4 : 8,
        bottom: isCompactChart.value ? 22 : 8,
        left: 4,
      },
    },
    animation: {
      duration: 300,
    },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    onHover: (_event: unknown, activeElements: unknown[]) => {
      isChartHoverActive.value = activeElements.length > 0
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        titleColor: '#fff',
        bodyColor: '#fff',
        padding: isCompactChart.value ? 8 : 12,
        cornerRadius: 8,
        displayColors: !isCompactChart.value,
        callbacks: {
          title: (items: any[]) => {
            if (items.length === 0) return ''
            const date = new Date(items[0].parsed.x)
            if (isCompactChart.value) {
              return date.toLocaleString('de-DE', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })
            }
            return date.toLocaleString('de-DE', {
              day: '2-digit',
              month: '2-digit',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })
          },
          label: (item: any) => {
            // Actuator overlay datasets come first, then sensor datasets (P8-A6c)
            const actuatorCount = (props.actuatorOverlays || []).length
            const sensorIndex = item.datasetIndex - actuatorCount
            if (sensorIndex < 0) {
              // This is an actuator dataset — show status label
              const overlay = (props.actuatorOverlays || [])[item.datasetIndex]
              return overlay ? ` ${overlay.label}: aktiv` : ''
            }
            const sensor = props.sensors[sensorIndex]
            if (!sensor) return ''
            const value = item.parsed.y?.toFixed(2) ?? 'N/A'
            const avgSuffix = currentResolution.value ? ' (Ø)' : ''
            return ` ${sensor.name}: ${value} ${sensor.unit}${avgSuffix}`
          },
        },
        // Filter out transparent actuator bars from tooltip
        filter: (item: any) => {
          const actuatorCount = (props.actuatorOverlays || []).length
          if (item.datasetIndex < actuatorCount) {
            // Only show actuator tooltip if bar is visible (not transparent)
            const bg = item.element?.options?.backgroundColor
            return bg != null && bg !== 'transparent'
          }
          return true
        },
      },
      // Keep annotation plugin disabled unless we have valid entries.
      ...(hasActuatorAnnotations.value ? { annotation: { annotations: safeActuatorAnnotations } } : {}),
      // Zoom/Pan (8.0-A)
      zoom: {
        pan: {
          enabled: true,
          mode: 'x' as const,
        },
        zoom: {
          wheel: {
            enabled: true,
          },
          pinch: {
            enabled: true,
          },
          mode: 'x' as const,
          onZoom: () => { isZoomed.value = true },
        },
      },
    },
    scales: {
      x: {
        type: 'time' as const,
        min: timelineStartMs.value,
        max: timelineEndMs.value,
        time: {
          displayFormats: {
            second: 'HH:mm:ss',
            minute: 'HH:mm',
            hour: 'HH:mm',
            day: 'dd.MM',
          },
        },
        grid: {
          color: 'rgba(255, 255, 255, 0.05)',
        },
        ticks: {
          color: 'rgba(255, 255, 255, 0.5)',
          maxTicksLimit: isCompactChart.value ? 5 : 8,
          autoSkip: true,
          autoSkipPadding: isCompactChart.value ? 14 : 8,
          minRotation: isCompactChart.value ? 40 : 0,
          maxRotation: isCompactChart.value ? 40 : 0,
        },
      },
      ...yScales,
      // Hidden actuator axis (P8-A6c) — only added when overlays exist
      ...(hasActuatorOverlays.value ? {
        'y-actuator': {
          display: false,
          min: 0,
          max: 1,
        },
      } : {}),
    },
  }
})

// =============================================================================
// Zoom Controls (8.0-A)
// =============================================================================
function resetZoom() {
  const chart = chartRef.value?.chart as any
  if (chart?.resetZoom) {
    chart.resetZoom()
    isZoomed.value = false
  }
}

// =============================================================================
// Methods
// =============================================================================

function toTimestampMs(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value < TIMESTAMP_MS_THRESHOLD ? Math.trunc(value * 1000) : Math.trunc(value)
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    const numeric = Number(trimmed)
    if (Number.isFinite(numeric)) {
      return numeric < TIMESTAMP_MS_THRESHOLD ? Math.trunc(numeric * 1000) : Math.trunc(numeric)
    }
    const parsed = Date.parse(trimmed)
    return Number.isNaN(parsed) ? null : parsed
  }
  return null
}

function normalizeReadings(readings: SensorReading[]): SensorReading[] {
  const normalized = readings
    .map((reading) => {
      const timestampMs = toTimestampMs(reading.timestamp)
      if (timestampMs == null) return null
      return {
        ...reading,
        timestamp: new Date(timestampMs).toISOString(),
      }
    })
    .filter((reading): reading is SensorReading => reading !== null)
    .sort((a, b) => {
      const left = toTimestampMs(a.timestamp) ?? 0
      const right = toTimestampMs(b.timestamp) ?? 0
      return left - right
    })

  const deduplicated: SensorReading[] = []
  let lastTimestampMs: number | null = null

  for (const reading of normalized) {
    const timestampMs = toTimestampMs(reading.timestamp)
    if (timestampMs == null) continue

    if (timestampMs === lastTimestampMs && deduplicated.length > 0) {
      // Prefer latest value for identical timestamp
      deduplicated[deduplicated.length - 1] = reading
      continue
    }

    deduplicated.push(reading)
    lastTimestampMs = timestampMs
  }

  return deduplicated.slice(-MAX_DATA_POINTS)
}

function getLatestTimestampMs(dataBySensor: Map<string, SensorReading[]>): number | null {
  let latest: number | null = null
  for (const readings of dataBySensor.values()) {
    for (const reading of readings) {
      const timestampMs = toTimestampMs(reading.timestamp)
      if (timestampMs == null) continue
      if (latest == null || timestampMs > latest) {
        latest = timestampMs
      }
    }
  }
  return latest
}

/**
 * Lädt historische Daten für alle Sensoren.
 * Verwendet Retry-Logik bei Fehlern.
 */
async function fetchData(retryAttempt = 0): Promise<void> {
  log.debug('fetchData called', {
    sensorCount: props.sensors.length,
    sensors: props.sensors.map(s => s.id),
    timeRange: props.timeRange,
    retryAttempt,
  })

  if (props.sensors.length === 0) {
    log.debug('No sensors - skipping fetch')
    sensorData.value = new Map()
    return
  }

  // Nur beim ersten Versuch Loading anzeigen
  if (retryAttempt === 0) {
    isLoading.value = true
    error.value = null
  }

  const now = new Date()
  timelineAnchorMs.value = now.getTime()
  const startTime = new Date(now.getTime() - timeRangeMs.value)

  log.debug('Fetching data', {
    startTime: startTime.toISOString(),
    endTime: now.toISOString(),
  })

  try {
    const promises = props.sensors.map(async (sensor) => {
      // Skip sensors with invalid identifiers (prevents 422 from backend)
      if (!sensor.espId || sensor.gpio == null) {
        log.debug(`Skipping sensor ${sensor.id} — invalid espId or gpio`)
        return { id: sensor.id, readings: [] as SensorReading[], error: null }
      }
      try {
        log.debug(`Querying API for sensor ${sensor.id}`, {
          esp_id: sensor.espId,
          gpio: sensor.gpio,
          sensorType: sensor.sensorType,
        })
        const response = await sensorsApi.queryData({
          esp_id: sensor.espId,
          gpio: sensor.gpio,
          sensor_type: sensor.sensorType || undefined,
          start_time: startTime.toISOString(),
          end_time: now.toISOString(),
          limit: MAX_DATA_POINTS,
          resolution: currentResolution.value,
        })
        log.debug(`API response for ${sensor.id}`, {
          readingsCount: response.readings?.length ?? 0,
          response,
        })
        return { id: sensor.id, readings: response.readings, error: null }
      } catch (err) {
        // Einzelner Sensor-Fehler wird nicht als kritischer Fehler behandelt
        log.debug(`API ERROR for ${sensor.id}`, { error: err })
        return { id: sensor.id, readings: [], error: err }
      }
    })

    const results = await Promise.all(promises)
    const newData = new Map<string, SensorReading[]>()
    let successCount = 0

    results.forEach(({ id, readings }) => {
      const normalizedReadings = normalizeReadings(readings)
      newData.set(id, normalizedReadings)
      if (normalizedReadings.length > 0) {
        successCount++
        emit('dataLoaded', id, normalizedReadings.length)
      }
    })

    sensorData.value = newData
    const latestTimestamp = getLatestTimestampMs(newData)
    if (latestTimestamp != null) {
      timelineAnchorMs.value = Math.max(timelineAnchorMs.value, latestTimestamp)
    }

    log.debug('fetchData complete', {
      successCount,
      totalSensors: props.sensors.length,
      enableLiveUpdates: props.enableLiveUpdates,
    })

    // Kein Error wenn mindestens ein Sensor Daten hat oder Live-Updates aktiv sind
    if (successCount === 0 && !props.enableLiveUpdates) {
      // Keine historischen Daten - kein Error, nur Info
      log.debug('No historical data available - waiting for live updates')
    }

    error.value = null
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : 'Fehler beim Laden der Daten'
    log.debug('fetchData FAILED', { error: err, errorMessage })

    // Retry-Logik
    if (retryAttempt < RETRY_CONFIG.maxAttempts) {
      const delay = Math.min(
        RETRY_CONFIG.baseDelay * Math.pow(2, retryAttempt),
        RETRY_CONFIG.maxDelay
      )
      log.debug(`Retry ${retryAttempt + 1}/${RETRY_CONFIG.maxAttempts} in ${delay}ms`)

      error.value = {
        message: `${errorMessage} (Retry ${retryAttempt + 1}/${RETRY_CONFIG.maxAttempts}...)`,
        retryCount: retryAttempt + 1,
      }

      retryTimer = setTimeout(() => {
        fetchData(retryAttempt + 1)
      }, delay)
    } else {
      error.value = { message: errorMessage, retryCount: retryAttempt }
      emit('error', errorMessage)
    }
  } finally {
    if (retryAttempt === 0 || !error.value) {
      isLoading.value = false
    }
  }
}

/**
 * Manuelles Retry (User-initiated)
 */
function retry(): void {
  if (retryTimer) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
  fetchData(0)
}

/**
 * Richtet WebSocket-Subscriptions für Live-Updates ein.
 */
function setupWebSocketSubscriptions(): void {
  log.debug('setupWebSocketSubscriptions', {
    enableLiveUpdates: props.enableLiveUpdates,
    sensorCount: props.sensors.length,
  })

  if (!props.enableLiveUpdates || props.sensors.length === 0) {
    log.debug('WebSocket subscriptions skipped')
    return
  }

  // Cleanup vorheriger Subscriptions
  cleanupWebSocketSubscriptions()

  // Subscription für jeden Sensor
  for (const sensor of props.sensors) {
    const subscriptionId = websocketService.subscribe(
      {
        types: ['sensor_data'],
        esp_ids: [sensor.espId],
      },
      (message) => {
        handleSensorDataMessage(sensor, message)
      }
    )
    wsSubscriptionIds.value.push(subscriptionId)
    log.debug(`WebSocket subscription created`, {
      sensorId: sensor.id,
      espId: sensor.espId,
      gpio: sensor.gpio,
      subscriptionId,
    })
  }

  log.debug(`${wsSubscriptionIds.value.length} WebSocket subscriptions aktiv`)
}

/**
 * Verarbeitet eingehende Sensor-Daten via WebSocket.
 */
function handleSensorDataMessage(sensor: ChartSensor, message: any): void {
  const data = message.data

  // Prüfe ob die Daten zu diesem Sensor gehören (GPIO + sensor_type Match)
  if (data.gpio !== undefined && data.gpio !== sensor.gpio) {
    return
  }

  // Filter by sensor_type to prevent multi-value mixing (e.g., SHT31 temp vs humidity)
  if (sensor.sensorType && data.sensor_type && data.sensor_type !== sensor.sensorType) {
    return
  }

  log.debug(`WebSocket data received for ${sensor.id}`, { data, value: data.value ?? data.raw_value })

  // Erstelle SensorReading aus WebSocket-Daten
  const reading: SensorReading = {
    timestamp: new Date(
      toTimestampMs(data.timestamp) ?? Date.now()
    ).toISOString(),
    raw_value: data.raw_value ?? data.value ?? 0,
    processed_value: data.processed_value ?? null,
    unit: data.unit ?? sensor.unit,
    quality: data.quality ?? 'good',
  }

  // Füge zu Live-Daten hinzu
  const currentLive = liveDataPoints.value.get(sensor.id) || []
  const updatedLive = normalizeReadings([...currentLive, reading])

  // Erstelle neue Map für Reaktivität
  const newLiveData = new Map(liveDataPoints.value)
  newLiveData.set(sensor.id, updatedLive)
  liveDataPoints.value = newLiveData
  const readingTimestamp = toTimestampMs(reading.timestamp)
  if (readingTimestamp != null) {
    timelineAnchorMs.value = Math.max(timelineAnchorMs.value, readingTimestamp)
  }

  log.debug(`Live data updated for ${sensor.id}`, { totalPoints: updatedLive.length })
}

/**
 * Räumt WebSocket-Subscriptions auf.
 */
function cleanupWebSocketSubscriptions(): void {
  for (const id of wsSubscriptionIds.value) {
    websocketService.unsubscribe(id)
  }
  wsSubscriptionIds.value = []
}

/**
 * Setzt Live-Daten zurück.
 */
function clearLiveData(): void {
  liveDataPoints.value = new Map()
}

// =============================================================================
// Watchers
// =============================================================================

/**
 * Sensor-IDs als String für zuverlässige Watch-Erkennung.
 */
const sensorIdsString = computed(() => props.sensors.map(s => s.id).sort().join(','))

// Bei Sensor-Änderungen neu laden
watch(
  sensorIdsString,
  (newIds, oldIds) => {
    log.debug('sensorIdsString changed', { newIds, oldIds })
    clearLiveData()
    isZoomed.value = false
    fetchData()
    setupWebSocketSubscriptions()
  }
)

// Bei Zeitraum-Änderungen neu laden
watch(
  () => props.timeRange,
  () => {
    clearLiveData()
    isZoomed.value = false
    fetchData()
  }
)

// Bei Y-Achsen-Änderungen Chart aktualisieren (kein Reload nötig)
watch(
  () => [props.yMin, props.yMax],
  () => {
    // Chart.js aktualisiert automatisch durch computed
  }
)

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
  // Initiales Laden
  fetchData()

  // WebSocket-Subscriptions einrichten
  setupWebSocketSubscriptions()

  // Auto-Refresh einrichten
  if (props.refreshInterval > 0) {
    refreshTimer = setInterval(fetchData, props.refreshInterval * 1000)
  }
})

onUnmounted(() => {
  // Cleanup
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }

  if (retryTimer) {
    clearTimeout(retryTimer)
    retryTimer = null
  }

  cleanupWebSocketSubscriptions()
})
</script>

<template>
  <div class="multi-sensor-chart">
    <!-- Loading State (nur beim initialen Laden) -->
    <div
      v-if="isLoading && totalDataPoints === 0"
      class="multi-sensor-chart__loading"
      :style="{ minHeight: `${stateMinHeightPx}px` }"
    >
      <div class="multi-sensor-chart__spinner" />
      <span>Lade Sensordaten...</span>
    </div>

    <!-- Error State -->
    <div
      v-else-if="error && totalDataPoints === 0"
      class="multi-sensor-chart__error"
      :style="{ minHeight: `${stateMinHeightPx}px` }"
    >
      <span class="multi-sensor-chart__error-icon">&#9888;&#65039;</span>
      <span>{{ error.message }}</span>
      <button @click="retry" class="multi-sensor-chart__retry-btn">
        Erneut versuchen
      </button>
    </div>

    <!-- Empty State (keine Sensoren ausgewählt) -->
    <div
      v-else-if="sensors.length === 0"
      class="multi-sensor-chart__empty"
      :style="{ minHeight: `${stateMinHeightPx}px` }"
    >
      <span class="multi-sensor-chart__empty-icon">&#128202;</span>
      <span>Keine Sensoren ausgewählt</span>
      <span class="multi-sensor-chart__empty-hint">
        Ziehe einen Sensor hierher um Daten anzuzeigen
      </span>
    </div>

    <!-- No Data State (Sensoren ausgewählt, aber keine Daten) -->
    <div
      v-else-if="totalDataPoints === 0"
      class="multi-sensor-chart__no-data"
      :style="{ minHeight: `${stateMinHeightPx}px` }"
    >
      <span class="multi-sensor-chart__no-data-icon">&#128200;</span>
      <span>Noch keine Daten verfügbar</span>
      <span class="multi-sensor-chart__no-data-hint">
        <template v-if="enableLiveUpdates">
          Warte auf Live-Daten vom Sensor...
        </template>
        <template v-else>
          Keine historischen Daten für {{ timeRangeLabel }}
        </template>
      </span>
      <div v-if="enableLiveUpdates" class="multi-sensor-chart__live-indicator">
        <span class="multi-sensor-chart__live-dot" />
        Live-Updates aktiv
      </div>
    </div>

    <!-- Chart -->
    <div v-else class="multi-sensor-chart__container" :style="{ height: `${chartContainerHeightPx}px` }">
      <Line
        v-if="chartData.datasets.length > 0"
        ref="chartRef"
        :data="(chartData as any)"
        :options="(chartOptions as any)"
      />

      <!-- Loading Overlay (beim Refresh) -->
      <div v-if="isLoading" class="multi-sensor-chart__loading-overlay">
        <div class="multi-sensor-chart__spinner multi-sensor-chart__spinner--small" />
      </div>
    </div>

    <!-- Meta-Leiste unter dem Chart (kein Overlay über Daten/Tooltip) -->
    <div
      v-if="totalDataPoints > 0"
      :class="[
        'multi-sensor-chart__info',
        { 'multi-sensor-chart__info--compact': isCompactChart },
        { 'multi-sensor-chart__info--hidden': isCompactChart && isChartHoverActive },
      ]"
    >
      <button
        v-if="isZoomed"
        class="multi-sensor-chart__reset-zoom"
        title="Zoom zurücksetzen"
        @click="resetZoom"
      >
        <RotateCcw :size="12" />
      </button>
      <span class="multi-sensor-chart__info-points">
        {{ totalDataPoints }} Punkte
      </span>
      <span v-if="needsDualAxis" class="multi-sensor-chart__info-dual">
        2Y
      </span>
      <span v-if="enableLiveUpdates && hasLiveData" class="multi-sensor-chart__info-live">
        <span class="multi-sensor-chart__live-dot" />
        Live
      </span>
    </div>
  </div>
</template>

<style scoped>
.multi-sensor-chart {
  width: 100%;
  position: relative;
}

.multi-sensor-chart__container {
  position: relative;
  width: 100%;
}

/* States */
.multi-sensor-chart__loading,
.multi-sensor-chart__error,
.multi-sensor-chart__empty,
.multi-sensor-chart__no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 1.5rem 0.75rem;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  text-align: center;
  min-height: 100px;
}

.multi-sensor-chart__error {
  color: var(--color-error);
}

.multi-sensor-chart__error-icon,
.multi-sensor-chart__empty-icon,
.multi-sensor-chart__no-data-icon {
  font-size: 1.25rem;
  margin-bottom: 0.125rem;
}

.multi-sensor-chart__empty-hint,
.multi-sensor-chart__no-data-hint {
  font-size: 0.6875rem;
  opacity: 0.7;
  max-width: 180px;
  line-height: 1.3;
}

/* Retry Button */
.multi-sensor-chart__retry-btn {
  margin-top: 0.5rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.multi-sensor-chart__retry-btn:hover {
  border-color: var(--color-iridescent-1);
  background: rgba(167, 139, 250, 0.1);
}

/* Live Indicator */
.multi-sensor-chart__live-indicator {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.375rem;
  padding: 0.1875rem 0.4375rem;
  background: rgba(52, 211, 153, 0.1);
  border-radius: var(--radius-full);
  font-size: 0.5625rem;
  color: var(--color-success);
}

.multi-sensor-chart__live-dot {
  width: 5px;
  height: 5px;
  background: var(--color-success);
  border-radius: 50%;
  animation: pulse-live 2s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse-live {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.9); }
}

/* Info Badge */
.multi-sensor-chart__info {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.375rem;
  padding: 0.25rem 0.375rem;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: 0.625rem;
  color: var(--color-text-muted);
  backdrop-filter: blur(4px);
}

.multi-sensor-chart__info--compact {
  justify-content: flex-start;
  gap: 0.25rem;
  margin-top: 0.3125rem;
  padding: 0.1875rem 0.3125rem;
  font-size: 0.5625rem;
}

.multi-sensor-chart__info--hidden {
  opacity: 0;
  pointer-events: none;
}

.multi-sensor-chart__info-points {
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: -0.025em;
}

.multi-sensor-chart__info-dual {
  padding: 0 0.25rem;
  background: rgba(96, 165, 250, 0.2);
  border-radius: var(--radius-xs);
  color: var(--color-iridescent-1);
  font-weight: 600;
  font-size: 0.5rem;
}

.multi-sensor-chart__info-live {
  display: flex;
  align-items: center;
  gap: 0.1875rem;
  color: var(--color-success);
  font-weight: 500;
}

/* Zoom Reset (8.0-A) */
.multi-sensor-chart__reset-zoom {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1px solid rgba(133, 133, 160, 0.3);
  border-radius: var(--radius-xs);
  background: rgba(0, 0, 0, 0.4);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.multi-sensor-chart__reset-zoom:hover {
  border-color: var(--color-iridescent-1);
  color: var(--color-iridescent-1);
}

/* Loading Overlay */
.multi-sensor-chart__loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  border-radius: var(--radius-md);
  pointer-events: none;
}

/* Spinner */
.multi-sensor-chart__spinner {
  width: 1.5rem;
  height: 1.5rem;
  border: 2px solid var(--color-bg-tertiary);
  border-top-color: var(--color-iridescent-1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.multi-sensor-chart__spinner--small {
  width: 1rem;
  height: 1rem;
}

</style>
