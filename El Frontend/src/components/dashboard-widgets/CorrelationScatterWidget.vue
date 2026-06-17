<script setup lang="ts">
/**
 * CorrelationScatterWidget — MultispeQ Korrelation x_sensor vs y_metadata.
 *
 * Datenquelle: REST API GET /sensors/multispeq/correlation
 *   Response: [{ x, y, label, metadata_phase }]
 *
 * Optional: Lineare Regressionslinie (Least-Squares, ohne externes Plugin).
 *
 * AUT-220
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import {
  Chart,
  ScatterController,
  LineController,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Title,
} from 'chart.js'
import { Loader2, AlertTriangle, GitCompareArrows } from 'lucide-vue-next'
import { multispeqApi, type CorrelationPoint } from '@/api/multispeq'
import { getSensorLabel } from '@/utils/sensorDefaults'

// Register Chart.js components (idempotent)
Chart.register(
  ScatterController,
  LineController,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Title,
)

// ─── Props ──────────────────────────────────────────────────────────────────

interface ScatterConfig {
  x_sensor_type?: string
  y_metadata_key?: string
  date_range?: '7d' | '30d' | '90d' | 'season'
  show_regression_line?: boolean
}

interface Props {
  config?: ScatterConfig
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  config: () => ({}),
})

// ─── Effective config ───────────────────────────────────────────────────────

const xSensorType = computed<string>(() => props.config?.x_sensor_type ?? 'ppfd')
const yMetadataKey = computed<string>(() => props.config?.y_metadata_key ?? 'yield_g')
const dateRange = computed<'7d' | '30d' | '90d' | 'season'>(
  () => props.config?.date_range ?? '30d',
)
const showRegression = computed<boolean>(() => props.config?.show_regression_line ?? false)

// ─── Labels ─────────────────────────────────────────────────────────────────

const DATE_RANGE_LABELS: Record<string, string> = {
  '7d': '7 Tage',
  '30d': '30 Tage',
  '90d': '90 Tage',
  'season': 'Saison',
}

const xLabel = computed(() => getSensorLabel(xSensorType.value))
const yLabel = computed(() => yMetadataKey.value)
const dateRangeLabel = computed(() => DATE_RANGE_LABELS[dateRange.value] ?? dateRange.value)
const headerTitle = computed(() => props.title || `${xLabel.value} vs ${yLabel.value}`)

// ─── State ──────────────────────────────────────────────────────────────────

const data = ref<CorrelationPoint[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

const chartCanvas = ref<HTMLCanvasElement | null>(null)
const chartInstance = shallowRef<Chart | null>(null)

// ─── Linear Regression (Least-Squares) ──────────────────────────────────────

interface RegressionResult {
  slope: number
  intercept: number
}

function linearRegression(points: { x: number; y: number }[]): RegressionResult | null {
  const n = points.length
  if (n < 2) return null
  const sumX = points.reduce((s, p) => s + p.x, 0)
  const sumY = points.reduce((s, p) => s + p.y, 0)
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0)
  const sumXX = points.reduce((s, p) => s + p.x * p.x, 0)
  const denominator = n * sumXX - sumX * sumX
  if (denominator === 0) return null
  const slope = (n * sumXY - sumX * sumY) / denominator
  const intercept = (sumY - slope * sumX) / n
  if (!Number.isFinite(slope) || !Number.isFinite(intercept)) return null
  return { slope, intercept }
}

// ─── Fetch ──────────────────────────────────────────────────────────────────

async function fetchCorrelation(): Promise<void> {
  isLoading.value = true
  error.value = null
  try {
    const result = await multispeqApi.getCorrelation(
      xSensorType.value,
      yMetadataKey.value,
      dateRange.value,
    )
    data.value = Array.isArray(result) ? result : []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Korrelation konnte nicht geladen werden'
    data.value = []
  } finally {
    isLoading.value = false
  }
}

// ─── Chart lifecycle ────────────────────────────────────────────────────────

function destroyChart(): void {
  if (chartInstance.value) {
    chartInstance.value.destroy()
    chartInstance.value = null
  }
}

function renderChart(): void {
  if (!chartCanvas.value || data.value.length === 0) {
    destroyChart()
    return
  }

  const points = data.value
    .filter(d => Number.isFinite(d.x) && Number.isFinite(d.y))
    .map(d => ({ x: d.x, y: d.y }))

  const datasets: Record<string, unknown>[] = [
    {
      type: 'scatter',
      label: headerTitle.value,
      data: points,
      backgroundColor: 'rgba(234, 179, 8, 0.7)',
      borderColor: '#eab308',
      pointRadius: 4,
      pointHoverRadius: 6,
    },
  ]

  // Optional: regression line as separate dataset
  if (showRegression.value && points.length >= 2) {
    const reg = linearRegression(points)
    if (reg) {
      const xs = points.map(p => p.x)
      const minX = Math.min(...xs)
      const maxX = Math.max(...xs)
      const linePoints = [
        { x: minX, y: reg.slope * minX + reg.intercept },
        { x: maxX, y: reg.slope * maxX + reg.intercept },
      ]
      datasets.push({
        type: 'line',
        label: 'Regression',
        data: linePoints,
        borderColor: '#f87171',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0,
        order: 0,
      })
    }
  }

  destroyChart()

  chartInstance.value = new Chart(chartCanvas.value, {
    type: 'scatter',
    data: { datasets: datasets as never },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: showRegression.value,
          labels: { color: 'rgba(176, 176, 192, 0.9)' },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const idx = ctx.dataIndex
              const dsIdx = ctx.datasetIndex
              if (dsIdx !== 0) {
                // Regression line
                const yVal = ctx.parsed.y ?? 0
                return `Regression: y = ${yVal.toFixed(2)}`
              }
              const entry = data.value[idx]
              if (!entry) return ''
              const phaseStr = entry.metadata_phase ? ` (${entry.metadata_phase})` : ''
              return `${entry.label}${phaseStr}: ${xLabel.value}=${entry.x}, ${yLabel.value}=${entry.y}`
            },
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          title: {
            display: true,
            text: xLabel.value,
            color: 'rgba(176, 176, 192, 0.9)',
          },
          ticks: { color: 'rgba(176, 176, 192, 0.9)' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        y: {
          title: {
            display: true,
            text: yLabel.value,
            color: 'rgba(176, 176, 192, 0.9)',
          },
          ticks: { color: 'rgba(176, 176, 192, 0.9)' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
        },
      },
    },
  })
}

// ─── Watchers ───────────────────────────────────────────────────────────────

watch([xSensorType, yMetadataKey, dateRange], () => {
  void fetchCorrelation()
})

watch([data, showRegression], () => {
  renderChart()
}, { deep: true })

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await fetchCorrelation()
  renderChart()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <div class="scatter-widget">
    <!-- Header -->
    <div class="scatter-widget__header">
      <span class="scatter-widget__title">{{ headerTitle }}</span>
      <span class="scatter-widget__range">{{ dateRangeLabel }}</span>
    </div>

    <!-- Loading -->
    <div v-if="isLoading && data.length === 0" class="scatter-widget__state">
      <Loader2 :size="24" class="scatter-widget__spinner" />
      <span>Korrelation wird geladen…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scatter-widget__state scatter-widget__state--error">
      <AlertTriangle :size="20" />
      <span>{{ error }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="data.length === 0" class="scatter-widget__state">
      <GitCompareArrows :size="24" />
      <span>Noch keine MultispeQ-Daten — CSV im Audits-Tab hochladen</span>
    </div>

    <!-- Chart -->
    <div v-else class="scatter-widget__chart">
      <canvas ref="chartCanvas" />
    </div>
  </div>
</template>

<style scoped>
.scatter-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--space-3);
  gap: var(--space-2);
}

.scatter-widget__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  flex-shrink: 0;
}

.scatter-widget__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scatter-widget__range {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  flex-shrink: 0;
}

.scatter-widget__state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--space-4);
}

.scatter-widget__state--error {
  color: var(--color-error);
}

.scatter-widget__spinner {
  animation: scatter-spin 1s linear infinite;
}

@keyframes scatter-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.scatter-widget__chart {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.scatter-widget__chart canvas {
  width: 100% !important;
  height: 100% !important;
}
</style>
