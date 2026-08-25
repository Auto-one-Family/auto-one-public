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
import CrosshairPlugin from 'chartjs-plugin-crosshair'
import 'chartjs-adapter-date-fns'
import { RotateCcw } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { websocketService } from '@/services/websocket'
import type { ChartSensor, SensorReading, SensorDataResolution } from '@/types'
import { createLogger } from '@/utils/logger'
import { getSensorConfig } from '@/utils/sensorDefaults'
import {
  getAutoResolution,
  getAutoResolutionForWindow,
  TIME_RANGE_MINUTES,
} from '@/utils/autoResolution'
import { formatDateTime, formatNumber, formatSensorValue } from '@/utils/formatters'

const log = createLogger('MultiSensorChart')

type TimeRangeKey = '1h' | '6h' | '24h' | '7d' | '30d'

/** Ascending presets — zoom-out past full window steps to the next larger range */
const TIME_RANGE_ORDER: readonly TimeRangeKey[] = ['1h', '6h', '24h', '7d', '30d']

function nextLargerTimeRange(current: TimeRangeKey): TimeRangeKey | null {
  const idx = TIME_RANGE_ORDER.indexOf(current)
  if (idx < 0 || idx >= TIME_RANGE_ORDER.length - 1) return null
  return TIME_RANGE_ORDER[idx + 1] ?? null
}

function decimalsForSensorType(sensorType: string | undefined): number {
  if (!sensorType) return 2
  return getSensorConfig(sensorType)?.decimals ?? 2
}

function formatYAxisTick(value: string | number, unit = '', decimals = 2): string {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }
  return formatSensorValue(numeric, unit, decimals)
}

// Register Chart.js components.
// NOTE (AUT-912): CrosshairPlugin is intentionally NOT registered globally. It is attached
// per-instance via the <Line :plugins> prop only when crosshair sync is active (see
// `instancePlugins`). A global registration ran the plugin's `afterEvent`/`getOption` on
// EVERY chart in the app (gauge, boxplot, …); those charts have no `options.plugins.crosshair`
// once vue-chartjs reactively swaps their options, so `getOption()` dereferenced `undefined`
// and crashed on hover. Importing the module still registers the 'interpolate' interaction mode.
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

/** AUT-1329: debounce zoom/pan → visible-window refetch (plugin fires continuously). */
const ZOOM_REFETCH_DEBOUNCE_MS = 350

/** Difference mode (AUT-913 B3): max gap for the nearest-join of raw (<1h) readings. */
const DIFF_JOIN_TOLERANCE_MS = 10_000

/** Difference mode (AUT-913 B3): shown/emitted when difference is requested but not applicable. */
const COMPARISON_UNAVAILABLE_MESSAGE =
  'Differenz-Modus erfordert zwei Messpunkte mit gleicher Einheit.'

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
  /** Total component height in pixels (header + chart canvas + info bar) */
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
  /**
   * Crosshair sync group (AUT-912). When set, hovering this chart draws a synced
   * vertical crosshair + interpolated tooltips on every chart sharing the same group.
   * Undefined = no cross-chart sync (native 'index' tooltip only).
   */
  syncGroup?: number | string
  /**
   * Comparison mode for exactly two same-unit sensors (AUT-913 B3).
   * 'overlay' = parallel lines (default, unchanged behaviour),
   * 'difference' = a single Δ(t) line (sensor[1] − sensor[0]) on its own Δ axis.
   * Falls back to 'overlay' when difference is not applicable.
   */
  comparisonMode?: 'overlay' | 'difference'
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '24h',
  height: 300,
  refreshInterval: 0,
  yMin: undefined,
  yMax: undefined,
  enableLiveUpdates: true,
  actuatorOverlays: () => [],
  comparisonMode: 'overlay',
})

const emit = defineEmits<{
  /** Wird gefeuert wenn Daten geladen wurden */
  dataLoaded: [sensorId: string, pointCount: number]
  /** Wird gefeuert bei Fehlern */
  error: [message: string]
  /** AUT-913 B3: difference requested but not applicable (≠2 sensors or differing units) */
  'comparison-mode-unavailable': [reason: string]
  /** AUT-913 B3: v-model:comparison-mode support (toggle drives the parent's value) */
  'update:comparisonMode': [mode: 'overlay' | 'difference']
  /**
   * Zoom-out past the loaded window expands the time preset (v-model:time-range).
   * Parent should bind so chips/config stay in sync; chart also tracks an internal effective range.
   */
  'update:timeRange': [range: TimeRangeKey]
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

/**
 * AUT-1329: visible (zoomed) X window for resolution + refetch.
 * null = full effectiveTimeRange preset (not zoomed).
 */
const viewWindowMs = ref<{ start: number; end: number } | null>(null)

/** Debounce timer for zoom/pan → /sensors/data refetch */
let zoomRefetchTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Effective loaded window. Starts from prop; wheel-zoom-out at full view steps to the next preset.
 * Kept independently so a brief parent re-render with a stale timeRange cannot shrink it.
 */
const effectiveTimeRange = ref<TimeRangeKey>(props.timeRange)

/**
 * Bumps on every loaded-window change so <Line> remounts and chartjs-plugin-zoom
 * cannot keep a corrupted/inverted X scale (symptom: time labels run backwards).
 * Same idea as HistoricalChart discarding zoom when the range changes.
 */
const chartEpoch = ref(0)

/** Prevent trackpad inertia from chaining 24h→7d→30d in one gesture */
let expandLockUntilMs = 0

const chartInstanceKey = computed(
  () => `${effectiveTimeRange.value}:${chartEpoch.value}`,
)

/**
 * Comparison-mode local state (AUT-913 B3). Initialised from the prop and kept in sync, so the
 * inline toggle works standalone AND when controlled via v-model:comparison-mode from a parent.
 */
const comparisonModeLocal = ref<'overlay' | 'difference'>(props.comparisonMode)
watch(() => props.comparisonMode, (mode) => { comparisonModeLocal.value = mode })


// =============================================================================
// Computed
// =============================================================================

/** Zeitraum in Millisekunden */
const timeRangeMs = computed(() => {
  return TIME_RANGES[effectiveTimeRange.value]?.ms || TIME_RANGES['24h'].ms
})

const timelineStartMs = computed(() => timelineAnchorMs.value - timeRangeMs.value)
const timelineEndMs = computed(() => timelineAnchorMs.value)

/** X-domain shown/fetched: visible zoom window, else full preset window */
const queryStartMs = computed(() => viewWindowMs.value?.start ?? timelineStartMs.value)
const queryEndMs = computed(() => viewWindowMs.value?.end ?? timelineEndMs.value)

/**
 * Server-side aggregation from the *visible* window when zoomed (AUT-1329),
 * otherwise from the loaded preset — same helper as HistoricalChart / MonitorView.
 */
const currentResolution = computed<SensorDataResolution | undefined>(() => {
  if (viewWindowMs.value) {
    return getAutoResolutionForWindow(viewWindowMs.value.start, viewWindowMs.value.end)
  }
  const minutes = TIME_RANGE_MINUTES[effectiveTimeRange.value] ?? 1440
  return getAutoResolution(minutes)
})

/** Zeitraum-Label für Anzeige */
const timeRangeLabel = computed(() => {
  return TIME_RANGES[effectiveTimeRange.value]?.label || '24 Stunden'
})

function decimalsForUnit(unit: string): number {
  const match = props.sensors.find((s) => s.unit === unit)
  return decimalsForSensorType(match?.sensorType)
}

const isCompactChart = computed(() => props.height <= 180)
const stateMinHeightPx = computed(() => {
  const sensorCount = Math.max(props.sensors.length, 1)
  const base = isCompactChart.value ? 92 : 112
  return base + Math.min((sensorCount - 1) * 8, 32)
})
/**
 * Total component height (comparison-mode header + chart canvas + info bar).
 * Applied as an explicit height on the root so the flex layout below has a
 * definite size to distribute regardless of the embedding context, and so it
 * never exceeds what the caller measured as available — the dashboard-widget
 * host clips overflow (AUT-1103, follow-up to AUT-1062 which fixed the same
 * class of bug for the canvas-only height).
 */
const rootHeightPx = computed(() => (Number.isFinite(props.height) ? props.height : 300))

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
  return type ? getSensorConfig(type) : null
})

// =============================================================================
// Comparison Mode — overlay vs. difference (AUT-913 B3)
// =============================================================================

/** Difference is only meaningful for exactly two sensors that share one non-empty unit. */
const differenceAvailable = computed(() => {
  if (props.sensors.length !== 2) return false
  const unitA = props.sensors[0].unit || ''
  const unitB = props.sensors[1].unit || ''
  return unitA !== '' && unitA === unitB
})

/** Effective mode: difference only when requested AND applicable, otherwise overlay. */
const effectiveComparisonMode = computed<'overlay' | 'difference'>(() =>
  comparisonModeLocal.value === 'difference' && differenceAvailable.value ? 'difference' : 'overlay'
)

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
/** Include aggregated bucket extremes so Y-scale is not clamped to the Ø-line alone. */
function extendRangeFromReading(
  reading: SensorReading,
  minVal: number,
  maxVal: number,
): { minVal: number; maxVal: number } {
  let nextMin = minVal
  let nextMax = maxVal
  const avg = reading.processed_value ?? reading.raw_value
  if (typeof avg === 'number' && Number.isFinite(avg)) {
    nextMin = Math.min(nextMin, avg)
    nextMax = Math.max(nextMax, avg)
  }
  if (typeof reading.min_value === 'number' && Number.isFinite(reading.min_value)) {
    nextMin = Math.min(nextMin, reading.min_value)
  }
  if (typeof reading.max_value === 'number' && Number.isFinite(reading.max_value)) {
    nextMax = Math.max(nextMax, reading.max_value)
  }
  return { minVal: nextMin, maxVal: nextMax }
}

function readingsHaveMinMaxBand(readings: SensorReading[]): boolean {
  return currentResolution.value != null
    && readings.some((r) => typeof r.min_value === 'number' && typeof r.max_value === 'number')
}

function computeRangeForUnit(unit: string): { min: number | undefined; max: number | undefined } {
  const sensorIds = unitGroups.value.get(unit) || []
  let minVal = Infinity
  let maxVal = -Infinity

  for (const sensorId of sensorIds) {
    const readings = combinedData.value.get(sensorId) || []
    for (const reading of readings) {
      ;({ minVal, maxVal } = extendRangeFromReading(reading, minVal, maxVal))
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

  for (const [_sensorId, readings] of combinedData.value.entries()) {
    for (const reading of readings) {
      ;({ minVal, maxVal } = extendRangeFromReading(reading, minVal, maxVal))
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
  // AUT-913 B3: difference mode renders a single Δ(t) line instead of parallel sensor lines.
  if (effectiveComparisonMode.value === 'difference') {
    const a = props.sensors[0]
    const b = props.sensors[1]
    const aggregated = currentResolution.value != null
    // Bucket-Key-Join (not index-based): fehlende Buckets → null statt Versatz.
    const deltaPoints = joinForDifference(
      combinedData.value.get(a.id) || [],
      combinedData.value.get(b.id) || [],
      aggregated,
    ).slice(-MAX_DATA_POINTS)

    return {
      datasets: [{
        type: 'line' as const,
        label: `Δ ${getSensorConfig(a.sensorType)?.label ?? a.sensorType}`,
        data: deltaPoints,
        borderColor: b.color,
        backgroundColor: `${b.color}20`,
        borderWidth: 2,
        pointRadius: deltaPoints.length > 100 ? 0 : 2,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: false,
        spanGaps: false, // AUT-837 S2: never interpolate across gaps (null Δ breaks the line)
        interpolate: props.syncGroup != null,
        yAxisID: 'yDelta',
        order: 2,
      }],
    }
  }

  // Sensor datasets — rendered ABOVE actuator bars (order: 2).
  // Aggregated windows: HistoricalChart pattern — Min/Max band + Ø line.
  const sensorDatasets: Record<string, unknown>[] = []
  for (const sensor of props.sensors) {
    const readings = combinedData.value.get(sensor.id) || []
    const unit = sensor.unit || ''
    const unitIndex = uniqueUnits.value.indexOf(unit)

    // Assign yAxisID: 1st unit → 'y' (left), 2nd → 'y1' (right), 3rd → 'y2' (right, offset).
    // 4th+ unit shares left axis. (8.0-B / AUT-911 B1-G3: pH/EC/TDS = 3 units)
    let yAxisID = 'y'
    if (needsDualAxis.value && unitIndex >= 1) {
      yAxisID = unitIndex === 1 ? 'y1' : unitIndex === 2 ? 'y2' : 'y'
    }

    const points = (pickY: (r: SensorReading) => number | null | undefined) =>
      readings.flatMap((r) => {
        const timestampMs = toTimestampMs(r.timestamp)
        if (timestampMs == null) return []
        const y = pickY(r)
        return [{ x: timestampMs, y: typeof y === 'number' && Number.isFinite(y) ? y : null }]
      })

    const hasBand = readingsHaveMinMaxBand(readings)
    if (hasBand) {
      sensorDatasets.push({
        type: 'line' as const,
        label: `${sensor.name} Max`,
        metaKind: 'sensor-max',
        metaSensorId: sensor.id,
        data: points((r) => r.max_value),
        borderColor: 'transparent',
        backgroundColor: `${sensor.color}18`,
        borderWidth: 0,
        pointRadius: 0,
        pointHoverRadius: 0,
        tension: 0,
        fill: '+1',
        spanGaps: false,
        yAxisID,
        order: 3,
      })
      sensorDatasets.push({
        type: 'line' as const,
        label: `${sensor.name} Min`,
        metaKind: 'sensor-min',
        metaSensorId: sensor.id,
        data: points((r) => r.min_value),
        borderColor: 'transparent',
        backgroundColor: 'transparent',
        borderWidth: 0,
        pointRadius: 0,
        pointHoverRadius: 0,
        tension: 0,
        fill: false,
        spanGaps: false,
        yAxisID,
        order: 3,
      })
    }

    sensorDatasets.push({
      type: 'line' as const,
      label: sensor.name,
      metaKind: 'sensor-avg',
      metaSensorId: sensor.id,
      data: points((r) => r.processed_value ?? r.raw_value),
      borderColor: sensor.color,
      backgroundColor: hasBand ? 'transparent' : `${sensor.color}20`,
      borderWidth: 2,
      pointRadius: readings.length > 100 ? 0 : 2,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
      spanGaps: false, // AUT-837 S2: never interpolate across gaps (null values break the line)
      // AUT-912: chartjs-plugin-crosshair only reads series whose dataset has `interpolate`,
      // so the synced crosshair tooltip can show every reading at the hovered X. Sync-off keeps
      // the native 'index' tooltip (which ignores this flag).
      interpolate: props.syncGroup != null,
      yAxisID,
      order: 2,
    })
  }

  // Actuator overlay datasets — rendered BEHIND sensor lines (order: 0) (P8-A6c)
  const actuatorDatasets = (props.actuatorOverlays || []).map((overlay) => ({
    type: 'bar' as const,
    label: `${overlay.label} (Status)`,
    metaKind: 'actuator',
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

  if (effectiveComparisonMode.value === 'difference') {
    // AUT-913 B3: single Δ axis. Title is always 'Δ <unit>' (never empty — leeres Label ist ein Bug).
    const diffType = props.sensors[0].sensorType
    const diffUnit = getSensorConfig(diffType)?.unit ?? props.sensors[0].unit
    yScales.yDelta = {
      type: 'linear' as const,
      position: 'left' as const,
      beginAtZero: false,
      title: {
        display: true,
        text: `Δ ${diffUnit}`,
        color: 'rgba(255, 255, 255, 0.5)',
        font: { size: 11 },
      },
      grid: { drawOnChartArea: false },
      ticks: {
        color: 'rgba(255, 255, 255, 0.5)',
        callback: (val: string | number) =>
          formatYAxisTick(val, diffUnit, decimalsForSensorType(diffType)),
      },
    }
  } else if (needsDualAxis.value) {
    // Left axis (first unit)
    const leftUnit = uniqueUnits.value[0]
    const leftRange = computeRangeForUnit(leftUnit)
    const leftDecimals = decimalsForUnit(leftUnit)
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
      ticks: {
        color: 'rgba(255, 255, 255, 0.5)',
        callback: (val: string | number) => formatYAxisTick(val, leftUnit, leftDecimals),
      },
    }

    // Right axis (second unit)
    if (uniqueUnits.value.length >= 2) {
      const rightUnit = uniqueUnits.value[1]
      const rightRange = computeRangeForUnit(rightUnit)
      const rightDecimals = decimalsForUnit(rightUnit)
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
        ticks: {
          color: 'rgba(255, 255, 255, 0.5)',
          callback: (val: string | number) => formatYAxisTick(val, rightUnit, rightDecimals),
        },
      }
    }

    // Third axis (third unit) — right, offset (AUT-911 B1-G3: e.g. pH / EC / TDS = 3 units)
    if (uniqueUnits.value.length >= 3) {
      const thirdUnit = uniqueUnits.value[2]
      const thirdRange = computeRangeForUnit(thirdUnit)
      const thirdDecimals = decimalsForUnit(thirdUnit)
      yScales.y2 = {
        type: 'linear' as const,
        position: 'right' as const,
        offset: true, // shift away from y1 so both right axes stay readable
        beginAtZero: false,
        ...(thirdRange.min != null ? { suggestedMin: thirdRange.min } : {}),
        ...(thirdRange.max != null ? { suggestedMax: thirdRange.max } : {}),
        title: {
          display: true,
          text: thirdUnit,
          color: 'rgba(255, 255, 255, 0.5)',
          font: { size: 11 },
        },
        grid: { drawOnChartArea: false },
        ticks: {
          color: 'rgba(255, 255, 255, 0.5)',
          callback: (val: string | number) => formatYAxisTick(val, thirdUnit, thirdDecimals),
        },
      }
    }
  } else {
    // Single axis (original behavior)
    const singleUnit = uniqueUnits.value[0] ?? props.sensors[0]?.unit ?? ''
    const singleDecimals = decimalsForUnit(singleUnit)
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
      ticks: {
        color: 'rgba(255, 255, 255, 0.5)',
        callback: (val: string | number) => formatYAxisTick(val, singleUnit, singleDecimals),
      },
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
      // AUT-912: 'interpolate' (chartjs-plugin-crosshair) shows every series at the synced
      // X position across charts; falls back to native 'index' when no syncGroup is set.
      mode: (props.syncGroup != null ? 'interpolate' : 'index') as 'index',
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
            return formatDateTime(new Date(items[0].parsed.x))
          },
          label: (item: any) => {
            const metaKind = item.dataset?.metaKind as string | undefined
            if (metaKind === 'actuator') {
              const overlay = (props.actuatorOverlays || [])[item.datasetIndex]
              return overlay ? ` ${overlay.label}: aktiv` : ''
            }
            // Min/Max band datasets are filtered out; avg line carries the tooltip.
            const sensorId = item.dataset?.metaSensorId as string | undefined
            const sensor = props.sensors.find((s) => s.id === sensorId)
            if (!sensor) return ''
            const rawY = item.parsed.y
            if (typeof rawY !== 'number' || !Number.isFinite(rawY)) {
              return ` ${sensor.name}: N/A`
            }
            const decimals = decimalsForSensorType(sensor.sensorType)
            const value = formatSensorValue(rawY, sensor.unit, decimals)
            // Aggregated buckets: show Ø plus bucket min–max (HistoricalChart hover pattern)
            if (currentResolution.value) {
              const ts = typeof item.parsed.x === 'number' ? item.parsed.x : Number(item.parsed.x)
              const reading = (combinedData.value.get(sensor.id) || []).find(
                (r) => toTimestampMs(r.timestamp) === ts,
              )
              const minV = reading?.min_value
              const maxV = reading?.max_value
              if (
                typeof minV === 'number' && Number.isFinite(minV)
                && typeof maxV === 'number' && Number.isFinite(maxV)
              ) {
                const lo = formatNumber(minV, decimals)
                const hi = formatNumber(maxV, decimals)
                return ` ${sensor.name}: ${value} (Ø, ${lo}–${hi} ${sensor.unit})`
              }
              return ` ${sensor.name}: ${value} (Ø)`
            }
            return ` ${sensor.name}: ${value}`
          },
        },
        // Hide band edges + transparent actuator bars from tooltip
        filter: (item: any) => {
          const metaKind = item.dataset?.metaKind as string | undefined
          if (metaKind === 'sensor-min' || metaKind === 'sensor-max') return false
          if (metaKind === 'actuator') {
            const bg = item.element?.options?.backgroundColor
            return bg != null && bg !== 'transparent'
          }
          return true
        },
      },
      // Keep annotation plugin disabled unless we have valid entries.
      ...(hasActuatorAnnotations.value ? { annotation: { annotations: safeActuatorAnnotations } } : {}),
      // Zoom/Pan (8.0-A). Zoom-out past the loaded window is handled by
      // handleChartWheelCapture (not the plugin) so the X window can expand + refetch.
      zoom: {
        pan: {
          enabled: true,
          mode: 'x' as const,
          onPanComplete: ({ chart }: { chart: ZoomPanChart }) => {
            handleVisibleXWindowChanged(chart)
          },
        },
        zoom: {
          wheel: {
            enabled: true,
          },
          pinch: {
            enabled: true,
          },
          mode: 'x' as const,
          onZoom: () => {
            isZoomed.value = true
          },
          onZoomComplete: ({ chart }: { chart: ZoomPanChart }) => {
            handleVisibleXWindowChanged(chart)
          },
        },
      },
      // Cross-chart crosshair sync (AUT-912) — only active when syncGroup is set.
      // crosshair's own box-zoom is disabled so chartjs-plugin-zoom stays the single zoom engine (B2-G4).
      ...(props.syncGroup != null ? {
        crosshair: {
          line: { color: 'rgba(255, 255, 255, 0.35)', width: 1 },
          sync: { enabled: true, group: props.syncGroup, suppressTooltips: false },
          zoom: { enabled: false },
          snap: { enabled: true },
        },
      } : {}),
    },
    scales: {
      x: {
        type: 'time' as const,
        // Fixed query window — first paint uses the loaded preset; while zoomed,
        // keep the visible window so data refetch does not jump back to the full preset.
        min: queryStartMs.value,
        max: queryEndMs.value,
        time: {
          displayFormats: {
            second: 'HH:mm:ss',
            minute: 'HH:mm',
            hour: 'HH:mm',
            day: 'dd.MM.',
          },
        },
        grid: {
          color: 'rgba(255, 255, 255, 0.05)',
        },
        ticks: {
          color: 'rgba(255, 255, 255, 0.7)',
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

/**
 * AUT-912: per-instance crosshair plugin. Attached ONLY while a syncGroup is set, so the
 * plugin's hover/sync hooks never touch other chart types (no global registration). When the
 * group toggles off the array empties and vue-chartjs re-creates the chart without the plugin
 * (native 'index' behaviour, no leftover window 'sync-event' listeners).
 */
const instancePlugins = computed(() => (props.syncGroup != null ? [CrosshairPlugin] : []))

// =============================================================================
// Zoom Controls (8.0-A)
// =============================================================================

type ZoomPanChart = {
  scales?: { x?: { min: number; max: number } }
  resetZoom?: () => void
}

function clearVisibleWindow(): void {
  viewWindowMs.value = null
  isZoomed.value = false
  if (zoomRefetchTimer) {
    clearTimeout(zoomRefetchTimer)
    zoomRefetchTimer = null
  }
}

/**
 * AUT-1329: after zoom/pan, derive resolution from the visible X window and
 * debounced-refetch /sensors/data (same getAutoResolutionForWindow as MonitorView).
 */
function scheduleVisibleWindowRefetch(startMs: number, endMs: number): void {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return
  viewWindowMs.value = { start: startMs, end: endMs }
  if (zoomRefetchTimer) clearTimeout(zoomRefetchTimer)
  zoomRefetchTimer = setTimeout(() => {
    zoomRefetchTimer = null
    void fetchData(0, { silent: true })
  }, ZOOM_REFETCH_DEBOUNCE_MS)
}

function handleVisibleXWindowChanged(chart: ZoomPanChart): void {
  const xScale = chart.scales?.x
  if (!xScale) return
  // Guard: corrupted zoom can invert min/max → time axis runs backwards
  if (xScale.min > xScale.max) {
    chart.resetZoom?.()
    clearVisibleWindow()
    void fetchData(0, { silent: true })
    return
  }
  const span = xScale.max - xScale.min
  if (!(span > 0) || !Number.isFinite(span)) return

  const zoomedIn = span < timeRangeMs.value * 0.995
  isZoomed.value = zoomedIn
  if (!zoomedIn) {
    // Back at full loaded window — drop visible override and reload preset resolution
    if (viewWindowMs.value) {
      clearVisibleWindow()
      void fetchData(0, { silent: true })
    }
    return
  }
  scheduleVisibleWindowRefetch(xScale.min, xScale.max)
}

function expandTimeRange(): boolean {
  const next = nextLargerTimeRange(effectiveTimeRange.value)
  if (!next) return false
  log.debug('expandTimeRange on zoom-out', {
    from: effectiveTimeRange.value,
    to: next,
  })
  clearVisibleWindow()
  effectiveTimeRange.value = next
  emit('update:timeRange', next)
  return true
}

/**
 * Capture-phase wheel handler: at the full loaded window, zoom-out expands the
 * time preset and refetches. While zoomed-in, the event reaches chartjs-plugin-zoom.
 */
function handleChartWheelCapture(event: WheelEvent): void {
  if (event.deltaY <= 0) return
  if (isZoomed.value) return
  if (isLoading.value) return

  const now = Date.now()
  if (now < expandLockUntilMs) {
    event.preventDefault()
    event.stopPropagation()
    return
  }

  if (!nextLargerTimeRange(effectiveTimeRange.value)) return

  event.preventDefault()
  event.stopPropagation()
  expandLockUntilMs = now + 750
  expandTimeRange()
}

function resetZoom() {
  const chart = chartRef.value?.chart as { resetZoom?: () => void } | undefined
  if (chart?.resetZoom) {
    chart.resetZoom()
  }
  clearVisibleWindow()
  void fetchData(0, { silent: true })
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

/**
 * AUT-913 B3: join two reading series into Δ(t) = value(B) − value(A).
 * Aggregated (server-bucketed) series are joined by exact bucket-timestamp KEY — a missing bucket
 * becomes null (a real gap), never an index-shifted offset. Raw (<1h) series have unaligned
 * timestamps, so they use a monotonic nearest-join bounded by DIFF_JOIN_TOLERANCE_MS.
 */
function joinForDifference(
  readingsA: SensorReading[],
  readingsB: SensorReading[],
  aggregated: boolean,
): Array<{ x: number; y: number | null }> {
  const toPoints = (readings: SensorReading[]) =>
    readings
      .map((r) => {
        const t = toTimestampMs(r.timestamp)
        const raw = r.processed_value ?? r.raw_value
        const v = typeof raw === 'number' && Number.isFinite(raw) ? raw : null
        return t == null ? null : { t, v }
      })
      .filter((p): p is { t: number; v: number | null } => p !== null)

  const pointsA = toPoints(readingsA)
  const pointsB = toPoints(readingsB)

  if (aggregated) {
    // Bucket-Key-Join (not index-based): fehlende Buckets → null statt Versatz.
    const mapA = new Map<number, number | null>(pointsA.map((p) => [p.t, p.v] as [number, number | null]))
    const mapB = new Map<number, number | null>(pointsB.map((p) => [p.t, p.v] as [number, number | null]))
    const keys = [...new Set([...mapA.keys(), ...mapB.keys()])].sort((x, y) => x - y)
    return keys.map((t) => {
      const va = mapA.get(t)
      const vb = mapB.get(t)
      return { x: t, y: va != null && vb != null ? vb - va : null }
    })
  }

  // Raw nearest-join: A is the base series; advance a pointer monotonically over the sorted B series.
  const result: Array<{ x: number; y: number | null }> = []
  let j = 0
  for (const pa of pointsA) {
    while (
      j + 1 < pointsB.length &&
      Math.abs(pointsB[j + 1].t - pa.t) <= Math.abs(pointsB[j].t - pa.t)
    ) {
      j++
    }
    const nearest = pointsB[j]
    const withinTolerance = nearest != null && Math.abs(nearest.t - pa.t) <= DIFF_JOIN_TOLERANCE_MS
    const y = withinTolerance && pa.v != null && nearest.v != null ? nearest.v - pa.v : null
    result.push({ x: pa.t, y })
  }
  return result
}

/** AUT-913 B3: inline toggle handler — local state + v-model emit (ignores an unavailable difference). */
function setComparisonMode(mode: 'overlay' | 'difference'): void {
  if (mode === 'difference' && !differenceAvailable.value) return
  if (comparisonModeLocal.value === mode) return
  comparisonModeLocal.value = mode
  emit('update:comparisonMode', mode)
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
async function fetchData(
  retryAttempt = 0,
  opts: { silent?: boolean } = {},
): Promise<void> {
  log.debug('fetchData called', {
    sensorCount: props.sensors.length,
    sensors: props.sensors.map(s => s.id),
    timeRange: props.timeRange,
    retryAttempt,
    visibleWindow: viewWindowMs.value,
    resolution: currentResolution.value,
  })

  if (props.sensors.length === 0) {
    log.debug('No sensors - skipping fetch')
    sensorData.value = new Map()
    return
  }

  // Nur beim ersten Versuch Loading anzeigen (Zoom-Refetch: silent)
  if (retryAttempt === 0 && !opts.silent) {
    isLoading.value = true
    error.value = null
  }

  const now = new Date()
  let startTime: Date
  let endTime: Date
  if (viewWindowMs.value) {
    // AUT-1329: refetch the visible zoom window (not the full preset)
    startTime = new Date(viewWindowMs.value.start)
    endTime = new Date(viewWindowMs.value.end)
  } else {
    timelineAnchorMs.value = now.getTime()
    endTime = now
    startTime = new Date(now.getTime() - timeRangeMs.value)
  }

  // Same resolution for every series in this fetch → aligned buckets for Differenz
  const resolution = currentResolution.value

  log.debug('Fetching data', {
    startTime: startTime.toISOString(),
    endTime: endTime.toISOString(),
    resolution: resolution ?? 'raw',
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
          end_time: endTime.toISOString(),
          limit: MAX_DATA_POINTS,
          resolution,
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
    // Do not drift the preset anchor while a zoomed visible window is active
    if (latestTimestamp != null && !viewWindowMs.value) {
      timelineAnchorMs.value = Math.max(timelineAnchorMs.value, latestTimestamp)
    }

    log.debug('fetchData complete', {
      successCount,
      totalSensors: props.sensors.length,
      enableLiveUpdates: props.enableLiveUpdates,
      timeRange: effectiveTimeRange.value,
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
        fetchData(retryAttempt + 1, opts)
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
    clearVisibleWindow()
    fetchData()
    setupWebSocketSubscriptions()
  }
)

/**
 * Parent timeRange → effective only when the parent value actually changes
 * (config chip / dashboard persist). Do not shrink an expanded window just
 * because a stale identical prop is re-delivered on unrelated re-renders.
 */
watch(
  () => props.timeRange,
  (range, previous) => {
    if (range === effectiveTimeRange.value) return
    if (range === previous) return
    effectiveTimeRange.value = range
  }
)

// Effective window change → reload, then remount chart so zoom state cannot
// keep an inverted X scale from the previous window.
watch(
  effectiveTimeRange,
  () => {
    clearLiveData()
    clearVisibleWindow()
    void fetchData().then(() => {
      chartEpoch.value += 1
    })
  }
)

// Bei Y-Achsen-Änderungen Chart aktualisieren (kein Reload nötig)
watch(
  () => [props.yMin, props.yMax],
  () => {
    // Chart.js aktualisiert automatisch durch computed
  }
)

// AUT-913 B3: tell the parent when a requested difference cannot be shown (chart falls back to overlay).
watch(
  [comparisonModeLocal, differenceAvailable],
  ([mode, available]) => {
    if (mode === 'difference' && !available) {
      emit('comparison-mode-unavailable', COMPARISON_UNAVAILABLE_MESSAGE)
    }
  },
  { immediate: true }
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
  if (zoomRefetchTimer) {
    clearTimeout(zoomRefetchTimer)
    zoomRefetchTimer = null
  }
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
  <div class="multi-sensor-chart" :style="{ height: `${rootHeightPx}px` }">
    <!-- Comparison-mode toggle (AUT-913 B3) — only for exactly two sensors -->
    <!-- Vergleichsmodus + Zoom-Reset (wie HistoricalChart: Reset immer sichtbar wenn gezoomt) -->
    <div
      v-if="sensors.length === 2 || isZoomed"
      class="multi-sensor-chart__header"
      :class="{ 'multi-sensor-chart__header--reset-only': sensors.length !== 2 }"
    >
      <div
        v-if="sensors.length === 2"
        class="multi-sensor-chart__segment"
        role="group"
        aria-label="Vergleichsmodus"
      >
        <button
          type="button"
          class="multi-sensor-chart__segment-btn"
          :class="{ 'is-active': comparisonModeLocal === 'overlay' }"
          :aria-pressed="comparisonModeLocal === 'overlay'"
          @click="setComparisonMode('overlay')"
        >
          Überlagert
        </button>
        <button
          type="button"
          class="multi-sensor-chart__segment-btn"
          :class="{ 'is-active': comparisonModeLocal === 'difference' }"
          :aria-pressed="comparisonModeLocal === 'difference'"
          :disabled="!differenceAvailable"
          :title="differenceAvailable ? undefined : COMPARISON_UNAVAILABLE_MESSAGE"
          @click="setComparisonMode('difference')"
        >
          Differenz
        </button>
      </div>
      <div class="multi-sensor-chart__header-right">
        <button
          v-if="isZoomed"
          type="button"
          class="multi-sensor-chart__reset-zoom"
          title="Zoom zurücksetzen"
          aria-label="Zoom zurücksetzen"
          @click="resetZoom"
        >
          <RotateCcw :size="14" />
        </button>
      </div>
    </div>

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
    <div
      v-else
      class="multi-sensor-chart__container"
      @wheel.capture="handleChartWheelCapture"
    >
      <Line
        v-if="chartData.datasets.length > 0"
        :key="chartInstanceKey"
        ref="chartRef"
        :data="(chartData as any)"
        :options="(chartOptions as any)"
        :plugins="(instancePlugins as any)"
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
  display: flex;
  flex-direction: column;
  position: relative;
  /* Height comes from the inline rootHeightPx binding (explicit px, not %) so
     it never depends on an ancestor having a definite height. Clipped as a
     last resort if header + info (flex-shrink:0) alone would exceed it. */
  overflow: hidden;
}

/* Fills the remaining space after header/info — prevents header+chart+info from
   together exceeding the host height and getting clipped by its overflow:hidden
   (AUT-1103 follow-up to AUT-1062, which only removed the old fixed-px floor). */
.multi-sensor-chart__container {
  flex: 1;
  min-height: 0;
  position: relative;
  width: 100%;
}

/* Comparison-mode toggle (AUT-913 B3) + zoom reset */
.multi-sensor-chart__header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: 28px;
  margin-bottom: 0.375rem;
}

.multi-sensor-chart__header--reset-only {
  justify-content: flex-end;
}

.multi-sensor-chart__header-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
}

.multi-sensor-chart__segment {
  display: inline-flex;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.multi-sensor-chart__segment-btn {
  padding: 0.25rem 0.625rem;
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}

.multi-sensor-chart__segment-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.multi-sensor-chart__segment-btn.is-active {
  background: rgba(167, 139, 250, 0.18);
  color: var(--color-iridescent-1);
  font-weight: 600;
}

.multi-sensor-chart__segment-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
  flex-shrink: 0;
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

/* Zoom Reset — aligned with HistoricalChart */
.multi-sensor-chart__reset-zoom {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  min-width: 28px;
  min-height: 28px;
  border: 1px solid rgba(133, 133, 160, 0.3);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
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
