<script setup lang="ts">
/**
 * LiveLineChart Component
 *
 * Generic line chart for live data visualization.
 * Design-token-consistent dark theme, responsive, with live update support.
 */

import { computed, watch, shallowRef } from 'vue'
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
import 'chartjs-adapter-date-fns'
import { tokens } from '@/utils/cssTokens'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  TimeScale
)

import type { ChartDataPoint } from './types'
export type { ChartDataPoint }

export interface ThresholdConfig {
  alarmLow?: number
  warnLow?: number
  warnHigh?: number
  alarmHigh?: number
}

interface Props {
  /** Initial data points */
  data?: ChartDataPoint[]
  /** Maximum data points before oldest are removed */
  maxDataPoints?: number
  /** Chart accent color (CSS var or hex) */
  color?: string
  /** Show grid lines */
  showGrid?: boolean
  /** Container height */
  height?: string
  /** Y-axis unit suffix */
  unit?: string
  /** Show area fill under line */
  fill?: boolean
  /** Threshold lines for annotation overlay */
  thresholds?: ThresholdConfig
  /** Whether to show threshold lines */
  showThresholds?: boolean
  /** Compact/sparkline mode: hides axes, tooltips, grid for minimal inline display */
  compact?: boolean
  /** Sensor type key for automatic Y-axis range from SENSOR_TYPE_CONFIG */
  sensorType?: string
  /** Explicit Y-axis minimum (overrides sensorType lookup) */
  yMin?: number
  /** Explicit Y-axis maximum (overrides sensorType lookup) */
  yMax?: number
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  maxDataPoints: 50,
  color: tokens.accent,
  showGrid: true,
  height: '200px',
  unit: '',
  fill: true,
  thresholds: undefined,
  showThresholds: false,
  compact: false,
  sensorType: undefined,
  yMin: undefined,
  yMax: undefined,
})

const sensorRange = computed(() => {
  const config = props.sensorType ? SENSOR_TYPE_CONFIG[props.sensorType] : undefined
  const min = props.yMin ?? config?.min
  const max = props.yMax ?? config?.max
  return {
    min: Number.isFinite(min) ? min : undefined,
    max: Number.isFinite(max) ? max : undefined,
  }
})

/**
 * IQR-based Y-domain: a single outlier peak does not collapse normal variation.
 * Compact sparklines use hard min/max (clipped); non-compact uses suggestedMin/Max (expandable).
 */
const dynamicYBounds = computed(() => {
  const values = dataBuffer.value
    .map(point => point.value)
    .filter((value): value is number => Number.isFinite(value))

  if (values.length === 0) return null

  const sorted = [...values].sort((a, b) => a - b)
  const n = sorted.length
  const q1 = sorted[Math.floor(n * 0.25)]
  const q3 = sorted[Math.min(Math.ceil(n * 0.75), n - 1)]
  const iqr = q3 - q1
  const fence = Math.max(iqr * 1.5, 0.1)

  const dataMin = q1 - fence
  const dataMax = q3 + fence
  const dataSpan = dataMax - dataMin
  const rangeSpan = sensorRange.value.min != null && sensorRange.value.max != null
    ? Math.max(sensorRange.value.max - sensorRange.value.min, 0)
    : 0

  const minVisualSpan = Math.max(rangeSpan * 0.03, 0.2)
  const targetSpan = Math.max(dataSpan, minVisualSpan)
  const padding = targetSpan * 0.15

  let min = dataMin - padding
  let max = dataMax + padding

  if (dataSpan < minVisualSpan) {
    const extra = (minVisualSpan - dataSpan) / 2
    min -= extra
    max += extra
  }

  if (sensorRange.value.min != null) min = Math.max(min, sensorRange.value.min)
  if (sensorRange.value.max != null) max = Math.min(max, sensorRange.value.max)

  if (max <= min) {
    const center = values[values.length - 1] ?? dataMin
    min = center - minVisualSpan / 2
    max = center + minVisualSpan / 2
  }

  return { min, max }
})

const compactYBounds = computed(() => {
  if (!props.compact) return null
  return dynamicYBounds.value
})

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

type LineAnnotationConfig = {
  type: 'line'
  yMin: number
  yMax: number
  borderColor?: string
  borderWidth?: number
  borderDash?: number[]
  borderCapStyle?: CanvasLineCap
}

function sanitizeLineAnnotation(raw: unknown): LineAnnotationConfig | null {
  if (!raw || typeof raw !== 'object') return null
  const config = raw as Record<string, unknown>
  if (config.type !== 'line') return null

  const yMin = toFiniteNumber(config.yMin)
  const yMax = toFiniteNumber(config.yMax)
  if (yMin == null || yMax == null) return null

  const borderWidth = toFiniteNumber(config.borderWidth)
  const safeBorderDash = Array.isArray(config.borderDash)
    ? config.borderDash
      .map(toFiniteNumber)
      .filter((val): val is number => val != null && val >= 0)
    : undefined

  const annotation: LineAnnotationConfig = {
    type: 'line',
    yMin,
    yMax,
    borderCapStyle: 'butt',
  }

  if (typeof config.borderColor === 'string') annotation.borderColor = config.borderColor
  if (borderWidth != null) annotation.borderWidth = borderWidth
  if (safeBorderDash && safeBorderDash.length > 0) annotation.borderDash = safeBorderDash

  return annotation
}

function sanitizeThresholdAnnotations(raw: Record<string, unknown>): Record<string, LineAnnotationConfig> {
  const safe: Record<string, LineAnnotationConfig> = {}
  for (const [key, value] of Object.entries(raw)) {
    const annotation = sanitizeLineAnnotation(value)
    if (annotation) safe[key] = annotation
  }
  return safe
}

// Internal data buffer
const dataBuffer = shallowRef<ChartDataPoint[]>([...props.data])

// Watch for prop changes
watch(() => props.data, (newData) => {
  dataBuffer.value = [...newData].slice(-props.maxDataPoints)
}, { deep: true })

const chartData = computed(() => ({
  labels: dataBuffer.value.map(d =>
    d.timestamp instanceof Date ? d.timestamp : new Date(d.timestamp)
  ),
  datasets: [{
    data: dataBuffer.value.map(d => d.value),
    borderColor: props.color,
    backgroundColor: props.fill
      ? `${props.color}1a`  // 10% opacity
      : 'transparent',
    borderWidth: props.compact ? 1.5 : 2,
    pointRadius: 0,
    pointHitRadius: props.compact ? 0 : 8,
    tension: props.compact ? 0.2 : 0.3,
    cubicInterpolationMode: 'monotone' as const,
    fill: props.fill,
    spanGaps: false,
  }],
}))

/** Build annotation config for threshold lines */
const thresholdAnnotations = computed(() => {
  if (!props.showThresholds || !props.thresholds) return {}

  const annotations: Record<string, any> = {}
  const t = props.thresholds
  const alarmLow = toFiniteNumber(t.alarmLow)
  const warnLow = toFiniteNumber(t.warnLow)
  const warnHigh = toFiniteNumber(t.warnHigh)
  const alarmHigh = toFiniteNumber(t.alarmHigh)

  if (alarmLow != null) {
    annotations.alarmLow = {
      type: 'line',
      yMin: alarmLow,
      yMax: alarmLow,
      borderColor: 'rgba(239, 68, 68, 0.5)',
      borderWidth: 1,
      borderDash: [4, 4],
      borderCapStyle: 'butt',
    }
  }
  if (warnLow != null) {
    annotations.warnLow = {
      type: 'line',
      yMin: warnLow,
      yMax: warnLow,
      borderColor: 'rgba(234, 179, 8, 0.4)',
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
      borderColor: 'rgba(234, 179, 8, 0.4)',
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
      borderColor: 'rgba(239, 68, 68, 0.5)',
      borderWidth: 1,
      borderDash: [4, 4],
      borderCapStyle: 'butt',
    }
  }

  return annotations
})

const safeThresholdAnnotations = computed(() => sanitizeThresholdAnnotations(thresholdAnnotations.value))
const hasResolvedAnnotations = computed(() => Object.keys(safeThresholdAnnotations.value).length > 0)

const chartOptions = computed(() => {
  const isCompact = props.compact

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: isCompact ? 0 : 300 },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: { display: false },
      tooltip: isCompact
        ? { enabled: false }
        : {
            backgroundColor: 'rgba(7, 7, 13, 0.9)',
            borderColor: 'rgba(133, 133, 160, 0.3)',
            borderWidth: 1,
            titleFont: { family: 'JetBrains Mono', size: 11 },
            bodyFont: { family: 'JetBrains Mono', size: 12 },
            titleColor: tokens.textSecondary,
            bodyColor: tokens.textPrimary,
            padding: 8,
            callbacks: {
              label: (ctx: any) => `${ctx.parsed.y}${props.unit ? ' ' + props.unit : ''}`,
            },
          },
      ...(!isCompact && hasResolvedAnnotations.value
        ? { annotation: { annotations: safeThresholdAnnotations.value } }
        : {}),
    },
    scales: {
      x: {
        type: 'time' as const,
        time: {
          displayFormats: {
            millisecond: 'HH:mm:ss',
            second: 'HH:mm:ss',
            minute: 'HH:mm',
            hour: 'HH:mm',
            day: 'dd.MM',
          },
        },
        display: !isCompact,
        grid: {
          display: !isCompact && props.showGrid,
          color: 'rgba(29, 29, 42, 0.8)',
        },
        ticks: {
          color: tokens.textMuted,
          font: { family: 'JetBrains Mono', size: 10 },
          maxTicksLimit: 6,
          autoSkip: true,
          maxRotation: 0,
        },
        border: { display: false },
      },
      y: {
        display: !isCompact,
        ...(isCompact && compactYBounds.value
          ? { min: compactYBounds.value.min, max: compactYBounds.value.max }
          : {}),
        ...(!isCompact && dynamicYBounds.value
          ? { suggestedMin: dynamicYBounds.value.min, suggestedMax: dynamicYBounds.value.max }
          : {}),
        ...(!isCompact && !dynamicYBounds.value && sensorRange.value.min != null
          ? { suggestedMin: sensorRange.value.min }
          : {}),
        ...(!isCompact && !dynamicYBounds.value && sensorRange.value.max != null
          ? { suggestedMax: sensorRange.value.max }
          : {}),
        grid: {
          display: !isCompact && props.showGrid,
          color: 'rgba(29, 29, 42, 0.8)',
        },
        ticks: {
          color: tokens.textMuted,
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (val: any) => `${val}${props.unit ? ' ' + props.unit : ''}`,
        },
        border: { display: false },
      },
    },
  }
})

/**
 * Add a single data point (for live updates).
 * Removes oldest point if maxDataPoints exceeded.
 */
function addDataPoint(point: ChartDataPoint): void {
  const newBuffer = [...dataBuffer.value, point]
  if (newBuffer.length > props.maxDataPoints) {
    newBuffer.shift()
  }
  dataBuffer.value = newBuffer
}

/**
 * Clear all data points.
 */
function clear(): void {
  dataBuffer.value = []
}

defineExpose({ addDataPoint, clear })
</script>

<template>
  <div class="live-line-chart" :style="{ height }">
    <Line
      :data="chartData"
      :options="chartOptions"
      :plugins="hasResolvedAnnotations ? [annotationPlugin] : []"
    />
  </div>
</template>

<style scoped>
.live-line-chart {
  position: relative;
  width: 100%;
}
</style>
