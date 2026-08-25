<script setup lang="ts">
/**
 * HistoricalChart — Time Series Chart with Threshold Lines
 *
 * Loads historical sensor data via API and renders a line chart
 * with optional threshold overlays using chartjs-plugin-annotation.
 *
 * Features:
 * - Optional time range chips: 1h, 6h, 24h, 7d, 30d (showRangeSelector)
 * - Zoom/Pan + Reset via chartjs-plugin-zoom (8.0-A)
 * - Threshold lines (alarmLow, warnLow, warnHigh, alarmHigh)
 * - Live data append via WebSocket sensor_data events
 * - Gap detection: line breaks when ESP was offline (8.0-C)
 * - Stats overlay: Min/Max/Avg from API + Avg annotation line (8.0-D)
 * - Hover readout in stats row (no floating Chart.js tooltip over the plot)
 */

import { ref, computed, watch, onMounted, shallowRef } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  TimeScale,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import zoomPlugin from 'chartjs-plugin-zoom'
import 'chartjs-adapter-date-fns'
import { RotateCcw, AlertTriangle } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { useEspStore } from '@/stores/esp'
import { tokens } from '@/utils/cssTokens'
import { getAutoResolution, TIME_RANGE_MINUTES } from '@/utils/autoResolution'
import { formatDateTime, formatNumber, formatSensorValue } from '@/utils/formatters'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'
import {
  type GapDataPoint,
  type GapInfo,
  type GapMarkingMode,
  calculateMedianInterval,
  computeExpectedInterval,
  insertGapMarkers,
  detectGaps,
  gapMultiplierForResolution,
  countRealDataPoints,
  formatGapDuration,
  formatTimeShort,
} from '@/utils/gapDetection'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  TimeScale,
  zoomPlugin
)

interface Props {
  espId: string
  gpio: number
  sensorType: string
  /** Time range */
  timeRange?: '1h' | '6h' | '24h' | '7d' | '30d'
  /** Chart accent color */
  color?: string
  /** Unit suffix */
  unit?: string
  /** Height */
  height?: string
  /** Threshold values for annotation lines */
  thresholds?: {
    alarmLow?: number
    warnLow?: number
    warnHigh?: number
    alarmHigh?: number
  }
  /** Show threshold lines */
  showThresholds?: boolean
  /** Gap marking mode: 'auto' (default), 'hatched', or 'off' */
  gapMarkingMode?: GapMarkingMode
  /**
   * Render as scatter plot (points only, no interpolated line) — used for
   * snapshot sensors (Wave 1, MultispeQ) where interpolation is misleading.
   */
  scatterMode?: boolean
  /**
   * Inline 1h/6h/24h/… chips. Sensor-Kachel steuert den Zeitraum über Widget-Config
   * und Zoom — dort false; Zoom-Reset bleibt unabhängig davon sichtbar.
   */
  showRangeSelector?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '1h',
  color: tokens.accent,
  unit: '',
  height: '300px',
  thresholds: () => ({}),
  showThresholds: true,
  gapMarkingMode: 'auto',
  scatterMode: false,
  showRangeSelector: true,
})

const espStore = useEspStore()
const loading = ref(true)
const error = ref<string | null>(null)

// Data buffer — allows null values for gap markers (8.0-C)
const dataBuffer = shallowRef<GapDataPoint[]>([])
const isAggregated = ref(false)
const responseResolution = ref<string | null>(null)

// Stats from API (8.0-D)
interface SensorStats {
  min: number
  max: number
  avg: number
  stdDev: number
  count: number
}
const stats = ref<SensorStats | null>(null)

/** Active hover point — shown in the stats row instead of a floating tooltip */
interface HoverPoint {
  timestamp: Date
  value: number
  minValue?: number
  maxValue?: number
}
const hoverPoint = ref<HoverPoint | null>(null)

// Zoom state (8.0-A)
const chartRef = ref<InstanceType<typeof Line> | null>(null)
const isZoomed = ref(false)

// Time range in minutes — uses shared TIME_RANGE_MINUTES from autoResolution

const selectedRange = ref(props.timeRange)

const yAxisDecimals = computed(() => SENSOR_TYPE_CONFIG[props.sensorType]?.decimals ?? 2)

/** Fill parent (Sensor-Kachel) instead of a fixed px canvas height */
const isFillHeight = computed(() => {
  const h = (props.height || '').trim()
  return h === '100%' || h === '100'
})

/**
 * Data-driven Y bounds: Y-axis is anchored to the actual measurement range,
 * not to threshold annotation positions. Thresholds use adjustScaleRange=false
 * so they cannot push the scale beyond the data range (AUT-1058).
 *
 * Primary source: API stats (min_value / max_value for the loaded time range).
 * Fallback: raw data points from dataBuffer.
 * Padding: 12% of data span (min 0.5 units) to give the curve visual room.
 */
const dataYBounds = computed<{ min: number; max: number } | null>(() => {
  if (
    stats.value != null &&
    Number.isFinite(stats.value.min) &&
    Number.isFinite(stats.value.max)
  ) {
    const span = stats.value.max - stats.value.min
    const padding = Math.max(span * 0.12, 0.5)
    return { min: stats.value.min - padding, max: stats.value.max + padding }
  }
  const values = dataBuffer.value
    .map(pt => pt.value)
    .filter((v): v is number => v != null && Number.isFinite(v))
  if (values.length === 0) return null
  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const span = dataMax - dataMin
  const padding = Math.max(span * 0.12, 0.5)
  return { min: dataMin - padding, max: dataMax + padding }
})

// Expected interval for gap detection (8.0-C / AUT-113)
let expectedIntervalMs = 0

function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

type AnnotationType = 'line' | 'box'
type AnnotationConfig = {
  type: AnnotationType
  yMin?: number
  yMax?: number
  value?: number
  borderColor?: string
  borderWidth?: number
  borderDash?: number[]
  borderCapStyle?: CanvasLineCap
  backgroundColor?: string
  label?: Record<string, unknown>
  /** Prevent annotation from expanding the Y-axis range (chartjs-plugin-annotation). */
  adjustScaleRange?: boolean
}

function sanitizeAnnotationLabel(raw: unknown): Record<string, unknown> | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const label = raw as Record<string, unknown>
  if (label.display !== true) return undefined

  const content = label.content
  const isStringArray = Array.isArray(content) && content.every((item) => typeof item === 'string')
  if (!(typeof content === 'string' || isStringArray)) return undefined

  const safe: Record<string, unknown> = {
    display: true,
    content,
  }

  if (typeof label.position === 'string') safe.position = label.position
  if (typeof label.color === 'string') safe.color = label.color
  if (typeof label.backgroundColor === 'string') safe.backgroundColor = label.backgroundColor
  if (label.font && typeof label.font === 'object') safe.font = label.font
  if (label.padding && typeof label.padding === 'object') safe.padding = label.padding

  return safe
}

function sanitizeAnnotationConfig(raw: unknown): AnnotationConfig | null {
  if (!raw || typeof raw !== 'object') return null
  const config = raw as Record<string, unknown>
  const type = config.type
  if (type !== 'line' && type !== 'box') return null

  const yMin = toFiniteNumber(config.yMin)
  const yMax = toFiniteNumber(config.yMax)
  const value = toFiniteNumber(config.value)

  if (type === 'line' && yMin == null && yMax == null && value == null) {
    return null
  }
  if (type === 'box' && (yMin == null || yMax == null)) {
    return null
  }

  const borderWidth = toFiniteNumber(config.borderWidth)
  const safeBorderDash = Array.isArray(config.borderDash)
    ? config.borderDash
      .map(toFiniteNumber)
      .filter((val): val is number => val != null && val >= 0)
    : undefined

  const annotation: AnnotationConfig = {
    type,
    ...(yMin != null ? { yMin } : {}),
    ...(yMax != null ? { yMax } : {}),
    ...(value != null ? { value } : {}),
    borderCapStyle: 'butt',
  }

  if (typeof config.borderColor === 'string') annotation.borderColor = config.borderColor
  if (typeof config.backgroundColor === 'string') annotation.backgroundColor = config.backgroundColor
  if (borderWidth != null) annotation.borderWidth = borderWidth
  if (safeBorderDash && safeBorderDash.length > 0) annotation.borderDash = safeBorderDash
  if (typeof config.adjustScaleRange === 'boolean') annotation.adjustScaleRange = config.adjustScaleRange
  const safeLabel = sanitizeAnnotationLabel(config.label)
  if (safeLabel) annotation.label = safeLabel

  return annotation
}

function sanitizeAnnotations(raw: Record<string, unknown>): Record<string, AnnotationConfig> {
  const safe: Record<string, AnnotationConfig> = {}
  for (const [key, value] of Object.entries(raw)) {
    const annotation = sanitizeAnnotationConfig(value)
    if (annotation) safe[key] = annotation
  }
  return safe
}

// Gap detection functions imported from @/utils/gapDetection (AUT-113)

// =============================================================================
// Load Historical Data + Stats
// =============================================================================
async function loadData() {
  // Guard: skip API call if required props are missing (prevents 422)
  if (!props.espId || !props.sensorType) {
    error.value = 'Widget-Konfiguration unvollständig'
    loading.value = false
    dataBuffer.value = []
    stats.value = null
    return
  }

  loading.value = true
  error.value = null
  clearHoverPoint()

  try {
    const minutes = TIME_RANGE_MINUTES[selectedRange.value] || 60
    const from = new Date(Date.now() - minutes * 60 * 1000).toISOString()
    const to = new Date().toISOString()

    // Auto-resolution: use server-side aggregation for longer time ranges
    const resolution = getAutoResolution(minutes)
    const limit = resolution ? 1000 : (selectedRange.value === '7d' ? 2000 : 1000)

    // Parallel: fetch data + stats (8.0-D)
    const [dataResponse, statsResponse] = await Promise.all([
      sensorsApi.queryData({
        esp_id: props.espId,
        gpio: props.gpio,
        sensor_type: props.sensorType,
        start_time: from,
        end_time: to,
        limit,
        resolution,
      }),
      sensorsApi.getStats(props.espId, props.gpio, {
        sensor_type: props.sensorType,
        start_time: from,
        end_time: to,
      }).catch(() => null), // Stats failure is non-critical
    ])

    responseResolution.value = dataResponse?.resolution ?? null
    isAggregated.value = resolution != null && dataResponse?.resolution !== 'raw'

    if (dataResponse && Array.isArray(dataResponse.readings)) {
      const rawPoints: GapDataPoint[] = dataResponse.readings.map((d) => {
        const val = d.processed_value != null ? d.processed_value : d.raw_value
        return {
          timestamp: new Date(d.timestamp),
          value: typeof val === 'number' ? val : parseFloat(String(val)),
          minValue: d.min_value ?? null,
          maxValue: d.max_value ?? null,
        }
      })

      // AUT-113: robust gap heuristic using max(median, resolution)
      const medianMs = calculateMedianInterval(rawPoints)
      expectedIntervalMs = computeExpectedInterval(
        medianMs,
        dataResponse.resolution,
        rawPoints.length,
      )

      if (props.gapMarkingMode !== 'off') {
        // AUT-837 S3: aggregated buckets use a tighter multiplier (1.5) so a
        // single missing bucket is already flagged as a gap.
        dataBuffer.value = insertGapMarkers(
          rawPoints,
          expectedIntervalMs,
          gapMultiplierForResolution(dataResponse.resolution),
        )
      } else {
        dataBuffer.value = rawPoints
      }
    } else {
      dataBuffer.value = []
      expectedIntervalMs = 0
    }

    // Extract stats (8.0-D) — stats are nested in response.stats
    if (statsResponse?.stats && typeof statsResponse.stats.avg_value === 'number') {
      stats.value = {
        min: statsResponse.stats.min_value ?? 0,
        max: statsResponse.stats.max_value ?? 0,
        avg: statsResponse.stats.avg_value,
        stdDev: statsResponse.stats.std_dev ?? 0,
        count: statsResponse.stats.reading_count ?? dataBuffer.value.length,
      }
    } else {
      stats.value = null
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || 'Daten konnten nicht geladen werden'
    dataBuffer.value = []
    stats.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

watch(
  () => props.timeRange,
  (range) => {
    if (range && range !== selectedRange.value) {
      selectedRange.value = range
    }
  },
)

watch(selectedRange, () => {
  isZoomed.value = false
  loadData()
})

// Watch for live sensor data updates and append
// Filter by sensor_type to avoid cross-updates on multi-value sensors (e.g., SHT31 temp vs humidity)
watch(
  () => {
    const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
    const sensors = (device?.sensors as any[]) || []
    const sensor = sensors.find(s => s.gpio === props.gpio && s.sensor_type === props.sensorType)
    return sensor?.last_read
  },
  () => {
    const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
    const sensors = (device?.sensors as any[]) || []
    const sensor = sensors.find(s => s.gpio === props.gpio && s.sensor_type === props.sensorType)
    if (sensor && typeof sensor.raw_value === 'number') {
      const newTimestamp = new Date(sensor.last_read || Date.now())
      const newValue = sensor.raw_value

      // Gap check for live append (8.0-C / AUT-113)
      const currentBuffer = dataBuffer.value
      const maxPoints = selectedRange.value === '7d' ? 2000 : 1000
      const newBuffer = [...currentBuffer]

      if (newBuffer.length > 0 && expectedIntervalMs > 0 && props.gapMarkingMode !== 'off') {
        const lastPoint = newBuffer[newBuffer.length - 1]
        if (lastPoint.value !== null) {
          const timeDiff = newTimestamp.getTime() - lastPoint.timestamp.getTime()
          if (timeDiff > expectedIntervalMs * 3) {
            newBuffer.push({ timestamp: new Date(lastPoint.timestamp.getTime() + 1), value: null, _gap: true })
            newBuffer.push({ timestamp: new Date(newTimestamp.getTime() - 1), value: null, _gap: true })
          }
        }
      }

      newBuffer.push({ timestamp: newTimestamp, value: newValue })
      if (newBuffer.length > maxPoints) newBuffer.shift()
      dataBuffer.value = newBuffer
    }
  }
)

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
// Format helper (8.0-D)
// =============================================================================
function formatStatValue(val: number): string {
  return formatNumber(val, yAxisDecimals.value)
}

function clearHoverPoint(): void {
  hoverPoint.value = null
}

function updateHoverFromElements(activeElements: Array<{ index: number; datasetIndex: number }>): void {
  if (!activeElements.length) {
    clearHoverPoint()
    return
  }
  const idx = activeElements[0].index
  const point = dataBuffer.value[idx]
  if (!point || point._gap || point.value == null || !Number.isFinite(point.value)) {
    clearHoverPoint()
    return
  }
  const next: HoverPoint = {
    timestamp: point.timestamp,
    value: point.value,
  }
  if (point.minValue != null && point.maxValue != null) {
    next.minValue = point.minValue
    next.maxValue = point.maxValue
  }
  const prev = hoverPoint.value
  if (
    prev
    && prev.value === next.value
    && prev.minValue === next.minValue
    && prev.maxValue === next.maxValue
    && +new Date(prev.timestamp) === +new Date(next.timestamp)
  ) {
    return
  }
  hoverPoint.value = next
}

// =============================================================================
// Gap overlay (AUT-113)
// =============================================================================

const realPointCount = computed(() => countRealDataPoints(dataBuffer.value))

const gapInfos = computed<GapInfo[]>(() => {
  if (props.gapMarkingMode === 'off' || expectedIntervalMs <= 0) return []
  const rawPoints = dataBuffer.value.filter((p) => !p._gap)
  // AUT-837 S3: same resolution-aware multiplier as insertGapMarkers above.
  return detectGaps(rawPoints, expectedIntervalMs, gapMultiplierForResolution(responseResolution.value))
})

function createHatchedPattern(): CanvasPattern | string {
  const fallback = tokens.chartGap || 'rgba(90, 90, 117, 0.10)'
  if (typeof document === 'undefined') return fallback
  const canvas = document.createElement('canvas')
  canvas.width = 10
  canvas.height = 10
  const ctx = canvas.getContext('2d')
  if (!ctx) return fallback
  ctx.strokeStyle = tokens.chartGapStroke || 'rgba(90, 90, 117, 0.25)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, 10)
  ctx.lineTo(10, 0)
  ctx.stroke()
  const pattern = ctx.createPattern(canvas, 'repeat')
  return pattern ?? fallback
}

// =============================================================================
// Chart Configuration
// =============================================================================
const chartData = computed(() => {
  const labels = dataBuffer.value.map(d => d.timestamp)
  const datasets: any[] = []

  // MIN/MAX band for aggregated data (rendered as filled area between min and max)
  const hasMinMax = isAggregated.value && dataBuffer.value.some(d => d.minValue != null)

  if (hasMinMax) {
    // Max line (upper bound of band)
    datasets.push({
      label: 'Max',
      data: dataBuffer.value.map(d => d.maxValue ?? d.value),
      borderColor: 'transparent',
      backgroundColor: `${props.color}10`,
      borderWidth: 0,
      pointRadius: 0,
      // AUT-1049: tension:0 — spline on band edges drew visible diagonal envelope lines
      tension: 0,
      fill: '+1', // Fill down to the next dataset (min)
      spanGaps: false,
      order: 2,
    })
    // Min line (lower bound of band)
    datasets.push({
      label: 'Min',
      data: dataBuffer.value.map(d => d.minValue ?? d.value),
      borderColor: 'transparent',
      backgroundColor: 'transparent',
      borderWidth: 0,
      pointRadius: 0,
      tension: 0,
      fill: false,
      spanGaps: false,
      order: 2,
    })
  }

  // Main avg line (always present).
  // Wave 1: Snapshot-Sensoren rendern als Scatter (nur Punkte, keine Interpolation).
  datasets.push({
    label: props.scatterMode ? 'Snapshot' : 'Avg',
    data: dataBuffer.value.map(d => d.value),
    borderColor: props.color,
    backgroundColor: props.scatterMode ? props.color : (hasMinMax ? 'transparent' : `${props.color}1a`),
    borderWidth: props.scatterMode ? 0 : 2,
    pointRadius: props.scatterMode ? 4 : 0,
    pointHoverRadius: props.scatterMode ? 6 : 4,
    pointBackgroundColor: props.color,
    pointBorderColor: props.color,
    pointHitRadius: 8,
    tension: props.scatterMode ? 0 : 0.3,
    showLine: !props.scatterMode,
    fill: props.scatterMode ? false : !hasMinMax,
    spanGaps: false, // Break line at null values (8.0-C)
    order: 0,
  })

  return { labels, datasets }
})

const resolvedAnnotations = computed(() => {
  const annotations: Record<string, any> = {}

  if (props.showThresholds && props.thresholds) {
    const alarmLow = toFiniteNumber(props.thresholds.alarmLow)
    const warnLow = toFiniteNumber(props.thresholds.warnLow)
    const warnHigh = toFiniteNumber(props.thresholds.warnHigh)
    const alarmHigh = toFiniteNumber(props.thresholds.alarmHigh)

    if (alarmLow != null) {
      annotations.alarmLow = {
        type: 'line',
        yMin: alarmLow,
        yMax: alarmLow,
        adjustScaleRange: false,
        borderColor: 'rgba(239, 68, 68, 0.6)',
        borderWidth: 1,
        borderDash: [4, 4],
        borderCapStyle: 'butt',
        label: {
          display: true,
          content: `Alarm \u2193 ${alarmLow}`,
          position: 'start',
          font: { size: 9, family: 'JetBrains Mono' },
          color: 'rgba(239, 68, 68, 0.8)',
          backgroundColor: 'transparent',
        },
      }
    }

    if (warnLow != null) {
      annotations.warnLow = {
        type: 'line',
        yMin: warnLow,
        yMax: warnLow,
        adjustScaleRange: false,
        borderColor: 'rgba(234, 179, 8, 0.5)',
        borderWidth: 1,
        borderDash: [4, 4],
        borderCapStyle: 'butt',
      }
    }

    if (warnHigh != null) {
      annotations.warnHigh = {
        type: 'line',
        yMin: warnHigh,
        yMax: warnHigh,
        adjustScaleRange: false,
        borderColor: 'rgba(234, 179, 8, 0.5)',
        borderWidth: 1,
        borderDash: [4, 4],
        borderCapStyle: 'butt',
      }
    }

    if (alarmHigh != null) {
      annotations.alarmHigh = {
        type: 'line',
        yMin: alarmHigh,
        yMax: alarmHigh,
        adjustScaleRange: false,
        borderColor: 'rgba(239, 68, 68, 0.6)',
        borderWidth: 1,
        borderDash: [4, 4],
        borderCapStyle: 'butt',
        label: {
          display: true,
          content: `Alarm \u2191 ${alarmHigh}`,
          position: 'start',
          font: { size: 9, family: 'JetBrains Mono' },
          color: 'rgba(239, 68, 68, 0.8)',
          backgroundColor: 'transparent',
        },
      }
    }
  }

  // Stats Avg annotation line (8.0-D) — subtler than thresholds
  const avgValue = toFiniteNumber(stats.value?.avg)
  if (avgValue != null) {
    annotations.avgLine = {
      type: 'line',
      yMin: avgValue,
      yMax: avgValue,
      adjustScaleRange: false,
      borderColor: 'rgba(176, 176, 192, 0.4)',
      borderWidth: 1,
      borderDash: [6, 3],
      borderCapStyle: 'butt',
      label: {
        display: true,
        content: `Avg: ${formatStatValue(avgValue)}${props.unit ? ' ' + props.unit : ''}`,
        position: 'end',
        font: { size: 9, family: 'JetBrains Mono' },
        color: 'rgba(176, 176, 192, 0.7)',
        backgroundColor: 'rgba(10, 10, 15, 0.6)',
        padding: { top: 2, bottom: 2, left: 4, right: 4 },
      },
    }
  }

  // VPD zone background bands (PB-01)
  // Only active when sensorType is 'vpd'. Box annotations do NOT affect
  // Y-axis scaling — Chart.js auto-scales to actual data range.
  if (props.sensorType === 'vpd') {
    annotations.vpdZoneLow = {
      type: 'box' as const,
      yMin: 0.0, yMax: 0.4,
      backgroundColor: 'rgba(239,68,68,0.08)',
      borderWidth: 0,
      label: { display: false },
    }
    annotations.vpdZoneSubLow = {
      type: 'box' as const,
      yMin: 0.4, yMax: 0.8,
      backgroundColor: 'rgba(234,179,8,0.08)',
      borderWidth: 0,
      label: { display: false },
    }
    annotations.vpdZoneOptimal = {
      type: 'box' as const,
      yMin: 0.8, yMax: 1.2,
      backgroundColor: 'rgba(34,197,94,0.10)',
      borderWidth: 0,
      label: { display: false },
    }
    annotations.vpdZoneSubHigh = {
      type: 'box' as const,
      yMin: 1.2, yMax: 1.6,
      backgroundColor: 'rgba(234,179,8,0.08)',
      borderWidth: 0,
      label: { display: false },
    }
    annotations.vpdZoneHigh = {
      type: 'box' as const,
      yMin: 1.6, yMax: 3.0,
      backgroundColor: 'rgba(239,68,68,0.08)',
      borderWidth: 0,
      label: { display: false },
    }
  }

  // AUT-113: Gap overlay annotations
  if (props.gapMarkingMode !== 'off') {
    const bg = props.gapMarkingMode === 'hatched'
      ? createHatchedPattern()
      : (tokens.chartGap || 'rgba(90, 90, 117, 0.10)')

    for (let i = 0; i < gapInfos.value.length; i++) {
      const gap = gapInfos.value[i]
      annotations[`gap_${i}`] = {
        type: 'box' as const,
        xMin: gap.startTime.getTime(),
        xMax: gap.endTime.getTime(),
        backgroundColor: bg,
        borderColor: tokens.chartGapStroke || 'rgba(90, 90, 117, 0.25)',
        borderWidth: 1,
        borderDash: [4, 4],
        label: {
          display: false,
          content: [
            `Lücke: ${formatGapDuration(gap.durationMs)}`,
            `${formatTimeShort(gap.startTime)} – ${formatTimeShort(gap.endTime)}`,
          ],
          position: 'center',
          font: { size: 9, family: 'JetBrains Mono' },
          color: tokens.textMuted || 'rgba(90, 90, 117, 0.8)',
          backgroundColor: 'rgba(7, 7, 13, 0.85)',
          padding: { top: 3, bottom: 3, left: 6, right: 6 },
        },
        enter(ctx: any) {
          ctx.element.label.options.display = true
          return true
        },
        leave(ctx: any) {
          ctx.element.label.options.display = false
          return true
        },
      }
    }
  }

  return annotations
})

const safeResolvedAnnotations = computed(() => sanitizeAnnotations(resolvedAnnotations.value))
const hasResolvedAnnotations = computed(() => Object.keys(safeResolvedAnnotations.value).length > 0)

const chartPlugins = computed(() => (
  hasResolvedAnnotations.value ? [annotationPlugin] : []
))

const chartOptions = computed(() => {
  const safeAnnotations = hasResolvedAnnotations.value ? safeResolvedAnnotations.value : {}

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index' as const, intersect: false },
    onHover: (_event: unknown, activeElements: Array<{ index: number; datasetIndex: number }>) => {
      updateHoverFromElements(activeElements)
    },
    plugins: {
      legend: { display: false },
      // Hover readout lives in the stats row — no floating overlay over the chart
      tooltip: {
        enabled: false,
        external: () => {},
      },
      // Keep annotation plugin/options disabled unless we have valid annotations.
      ...(hasResolvedAnnotations.value ? { annotation: { annotations: safeAnnotations } } : {}),
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
        display: true,
        time: {
          displayFormats: {
            minute: 'HH:mm',
            hour: 'HH:mm',
            day: 'dd.MM.',
          },
        },
        grid: { display: true, color: tokens.glassBorder },
        ticks: {
          color: tokens.textSecondary,
          font: { family: 'JetBrains Mono', size: 10 },
          maxTicksLimit: 8,
          autoSkip: true,
          maxRotation: 0,
        },
        border: { display: false },
      },
      y: {
        display: true,
        // Data-first Y bounds: anchor scale to actual measurements, not to
        // threshold positions. Threshold annotations use adjustScaleRange=false
        // so they are rendered as overlays without pushing the scale (AUT-1058).
        ...(dataYBounds.value
          ? { suggestedMin: dataYBounds.value.min, suggestedMax: dataYBounds.value.max }
          : {}),
        grid: { display: true, color: tokens.glassBorder },
        ticks: {
          color: tokens.textSecondary,
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (val: number | string) => {
            const num = typeof val === 'string' ? Number(val) : val
            if (!Number.isFinite(num)) return ''
            return formatSensorValue(num, props.unit, yAxisDecimals.value)
          },
        },
        border: { display: false },
      },
    },
  }
})
</script>

<template>
  <div
    class="historical-chart"
    :class="{ 'historical-chart--fill': isFillHeight }"
  >
    <!-- Zeitraum-Chips (optional) + Zoom-Reset (nur wenn gezoomt) -->
    <div
      v-if="showRangeSelector || isZoomed"
      class="historical-chart__header"
      :class="{ 'historical-chart__header--reset-only': !showRangeSelector }"
    >
      <div v-if="showRangeSelector" class="historical-chart__range-buttons">
        <button
          v-for="range in ['1h', '6h', '24h', '7d', '30d']"
          :key="range"
          type="button"
          :class="['historical-chart__range-btn', { 'historical-chart__range-btn--active': selectedRange === range }]"
          @click="selectedRange = range as any"
        >
          {{ range }}
        </button>
      </div>
      <div class="historical-chart__header-right">
        <button
          v-if="isZoomed"
          type="button"
          class="historical-chart__reset-zoom"
          title="Zoom zurücksetzen"
          aria-label="Zoom zurücksetzen"
          @click="resetZoom"
        >
          <RotateCcw :size="14" />
        </button>
      </div>
    </div>

    <!-- AUT-113: Sparse data warning -->
    <div
      v-if="!loading && !error && realPointCount > 0 && realPointCount < 5"
      class="historical-chart__sparse-banner"
    >
      <AlertTriangle :size="14" />
      <span>Wenige Datenpunkte ({{ realPointCount }}) — Darstellung kann ungenau sein</span>
    </div>

    <!-- Chart — fill mode uses flex growth; fixed mode keeps explicit height -->
    <div
      class="historical-chart__canvas"
      :style="isFillHeight ? undefined : { height }"
      @mouseleave="clearHoverPoint"
    >
      <div v-if="loading" class="historical-chart__loading">Lade Daten...</div>
      <div v-else-if="error" class="historical-chart__error">{{ error }}</div>
      <div v-else-if="dataBuffer.length === 0" class="historical-chart__empty">
        Keine Daten für den gewählten Zeitraum
      </div>
      <Line
        v-else
        ref="chartRef"
        :data="chartData"
        :options="chartOptions"
        :plugins="chartPlugins"
      />
    </div>

    <!-- Stats / Hover readout (8.0-D) — hover replaces summary, no floating tooltip -->
    <div
      v-if="!loading && (stats || hoverPoint)"
      class="historical-chart__stats"
      :class="{ 'historical-chart__stats--hover': hoverPoint }"
      :style="hoverPoint ? { '--hover-swatch': color } : undefined"
    >
      <template v-if="hoverPoint">
        <span class="historical-chart__stat historical-chart__stat--datetime">
          {{ formatDateTime(hoverPoint.timestamp) }}
        </span>
        <span class="historical-chart__stat historical-chart__stat--hover-avg">
          <span class="historical-chart__stat-swatch" aria-hidden="true" />
          <span class="historical-chart__stat-label">Avg</span>
          <span class="historical-chart__stat-value">
            {{ formatStatValue(hoverPoint.value) }}{{ unit ? ` ${unit}` : '' }}
          </span>
          <span
            v-if="hoverPoint.minValue != null && hoverPoint.maxValue != null"
            class="historical-chart__stat-range"
          >
            ({{ formatStatValue(hoverPoint.minValue) }}–{{ formatStatValue(hoverPoint.maxValue) }}{{ unit ? ` ${unit}` : '' }})
          </span>
        </span>
      </template>
      <template v-else-if="stats">
        <span class="historical-chart__stat">
          <span class="historical-chart__stat-label">Min</span>
          <span class="historical-chart__stat-value">{{ formatStatValue(stats.min) }}{{ unit ? ` ${unit}` : '' }}</span>
        </span>
        <span class="historical-chart__stat">
          <span class="historical-chart__stat-label">Avg</span>
          <span class="historical-chart__stat-value">{{ formatStatValue(stats.avg) }}{{ unit ? ` ${unit}` : '' }}</span>
        </span>
        <span class="historical-chart__stat">
          <span class="historical-chart__stat-label">Max</span>
          <span class="historical-chart__stat-value">{{ formatStatValue(stats.max) }}{{ unit ? ` ${unit}` : '' }}</span>
        </span>
        <span class="historical-chart__stat historical-chart__stat--meta">
          <span class="historical-chart__stat-label">&sigma;</span>
          <span class="historical-chart__stat-value">{{ formatStatValue(stats.stdDev) }}</span>
          <span class="historical-chart__stat-sep" aria-hidden="true">·</span>
          <span class="historical-chart__stat-value">{{ stats.count }} Punkte</span>
        </span>
      </template>
    </div>

    <!-- AUT-113: Gap info summary -->
    <div
      v-if="gapInfos.length > 0 && !loading && gapMarkingMode !== 'off'"
      class="historical-chart__gap-info"
    >
      <span class="historical-chart__gap-badge">
        {{ gapInfos.length }} {{ gapInfos.length === 1 ? 'Lücke' : 'Lücken' }} erkannt
      </span>
      <span class="historical-chart__gap-hint">
        Bereiche ohne Daten sind markiert
      </span>
    </div>
  </div>
</template>

<style scoped>
.historical-chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-height: 0;
}

/* Sensor-Kachel / GridStack: occupy full host, chart grows, stats stay compact */
.historical-chart--fill {
  height: 100%;
}

.historical-chart--fill .historical-chart__canvas {
  flex: 1 1 0;
  min-height: 0;
  height: auto;
}

.historical-chart--fill .historical-chart__canvas :deep(canvas) {
  max-height: 100%;
}

.historical-chart__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  min-height: 28px;
}

.historical-chart__header--reset-only {
  justify-content: flex-end;
}

.historical-chart__header-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
}

.historical-chart__range-buttons {
  display: flex;
  gap: 2px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.historical-chart__range-btn {
  padding: var(--space-1) var(--space-3);
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-mono);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.historical-chart__range-btn:hover {
  color: var(--color-text-secondary);
}

.historical-chart__range-btn--active {
  background: var(--color-accent);
  color: white;
}

.historical-chart__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.historical-chart__reset-zoom {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid rgba(133, 133, 160, 0.3);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.historical-chart__reset-zoom:hover {
  border-color: var(--color-iridescent-1);
  color: var(--color-iridescent-1);
}

.historical-chart__canvas {
  position: relative;
  width: 100%;
  min-height: 0;
}

.historical-chart__canvas :deep(canvas) {
  display: block;
}

.historical-chart__loading,
.historical-chart__error,
.historical-chart__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.historical-chart__error {
  color: var(--color-status-alarm);
}

/* Stats / hover readout (8.0-D) */
.historical-chart__stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
  min-height: 1.75rem;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-primary);
}

.historical-chart__stats--hover {
  gap: var(--space-4);
}

.historical-chart__stat {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.historical-chart__stat-label {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.historical-chart__stat-value {
  color: var(--color-text-primary);
  font-weight: 600;
}

.historical-chart__stat-range {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.historical-chart__stat-sep {
  color: var(--color-text-secondary);
  margin: 0 var(--space-1);
}

.historical-chart__stat--meta {
  margin-left: auto;
}

.historical-chart__stat--datetime {
  color: var(--color-text-primary);
  font-weight: 600;
}

.historical-chart__stat--hover-avg {
  gap: var(--space-2);
}

.historical-chart__stat-swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
  background: var(--hover-swatch, var(--color-iridescent-1));
}

/* AUT-113: Sparse data warning banner */
.historical-chart__sparse-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-warning);
}

/* AUT-113: Gap info summary */
.historical-chart__gap-info {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.historical-chart__gap-badge {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
}

.historical-chart__gap-hint {
  color: var(--color-text-muted);
}
</style>
