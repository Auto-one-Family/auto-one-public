<script setup lang="ts">
/**
 * BoxplotWidget — MultispeQ Aggregat-Vergleich (Min/Q1/Median/Q3/Max) als Boxplot.
 *
 * Datenquelle: REST API GET /sensors/multispeq/aggregates
 *   Response: [{ group_label, min, q1, median, q3, max, n }]
 *
 * Nutzt @sgratzl/chartjs-chart-boxplot (BoxPlotController + BoxAndWiskers)
 * registriert in Chart.js.
 *
 * Anonymisierung: Wenn anonymize_labels=true, werden group_labels durch
 * "Standort A", "Standort B", ... ersetzt.
 *
 * AUT-220
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import {
  Chart,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  Title,
} from 'chart.js'
import { BoxPlotController, BoxAndWiskers } from '@sgratzl/chartjs-chart-boxplot'
import { Loader2, AlertTriangle, BarChart3 } from 'lucide-vue-next'
import { multispeqApi, type AggregateEntry } from '@/api/multispeq'
import { getSensorLabel } from '@/utils/sensorDefaults'

// Register Chart.js components + boxplot controller (idempotent)
Chart.register(CategoryScale, LinearScale, Tooltip, Legend, Title, BoxPlotController, BoxAndWiskers)

// ─── Props / Emits ──────────────────────────────────────────────────────────

interface BoxplotConfig {
  sensor_type?: string
  group_by?: 'zone_id' | 'subzone_id' | 'plant_id'
  date_range?: '7d' | '30d' | '90d' | 'season'
  anonymize_labels?: boolean
}

interface Props {
  config?: BoxplotConfig
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  config: () => ({}),
})

// ─── Effective config (with defaults) ───────────────────────────────────────

const sensorType = computed<string>(() => props.config?.sensor_type ?? 'phi2')
const groupBy = computed<'zone_id' | 'subzone_id' | 'plant_id'>(
  () => props.config?.group_by ?? 'zone_id',
)
const dateRange = computed<'7d' | '30d' | '90d' | 'season'>(
  () => props.config?.date_range ?? '30d',
)
const anonymizeLabels = computed<boolean>(() => props.config?.anonymize_labels ?? true)

// ─── Labels / Mappings ──────────────────────────────────────────────────────

const DATE_RANGE_LABELS: Record<string, string> = {
  '7d': '7 Tage',
  '30d': '30 Tage',
  '90d': '90 Tage',
  'season': 'Saison',
}

const sensorLabel = computed(() => getSensorLabel(sensorType.value))
const dateRangeLabel = computed(() => DATE_RANGE_LABELS[dateRange.value] ?? dateRange.value)

// ─── State ──────────────────────────────────────────────────────────────────

const data = ref<AggregateEntry[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

const chartCanvas = ref<HTMLCanvasElement | null>(null)
// shallowRef: Chart instance is non-reactive (avoid Vue tracking internal state)
const chartInstance = shallowRef<Chart | null>(null)

// ─── Anonymisation Helper ───────────────────────────────────────────────────

function buildAnonymizedLabels(entries: AggregateEntry[]): string[] {
  return entries.map((_, idx) => {
    // 0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA (rare for >26 groups)
    const letter = idx < 26
      ? String.fromCharCode(65 + idx)
      : `Gruppe ${idx + 1}`
    return `Standort ${letter}`
  })
}

// ─── Fetch ──────────────────────────────────────────────────────────────────

async function fetchAggregates(): Promise<void> {
  isLoading.value = true
  error.value = null
  try {
    const result = await multispeqApi.getAggregates(
      sensorType.value,
      groupBy.value,
      dateRange.value,
    )
    data.value = Array.isArray(result) ? result : []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Aggregate konnten nicht geladen werden'
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

  const labels = anonymizeLabels.value
    ? buildAnonymizedLabels(data.value)
    : data.value.map(d => d.group_label)

  const datasetData = data.value.map(d => ({
    min: d.min,
    q1: d.q1,
    median: d.median,
    q3: d.q3,
    max: d.max,
  }))

  // Recreate chart on every render (data shape changes)
  destroyChart()

  // Cast to any: chart.js boxplot type-extension requires registered type 'boxplot'
  // which TypeScript cannot resolve from declaration merging across packages.
  chartInstance.value = new Chart(chartCanvas.value, {
    type: 'boxplot' as never,
    data: {
      labels,
      datasets: [
        {
          label: sensorLabel.value,
          data: datasetData as never,
          backgroundColor: 'rgba(34, 197, 94, 0.3)',
          borderColor: '#22c55e',
          borderWidth: 1.5,
          outlierBackgroundColor: '#22c55e',
        } as never,
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            // Show n (sample count) in tooltip footer
            footer: (items: { dataIndex: number }[]) => {
              const idx = items[0]?.dataIndex
              if (idx == null) return ''
              const entry = data.value[idx]
              return entry ? `n = ${entry.n}` : ''
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: 'rgba(176, 176, 192, 0.9)' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        y: {
          ticks: { color: 'rgba(176, 176, 192, 0.9)' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
        },
      },
    },
  } as never)
}

// ─── Watchers ───────────────────────────────────────────────────────────────

watch([sensorType, groupBy, dateRange], () => {
  void fetchAggregates()
})

// Re-render when data changes or labels toggle
watch([data, anonymizeLabels], () => {
  renderChart()
}, { deep: true })

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await fetchAggregates()
  // Wait one tick so canvas is in DOM with size
  renderChart()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<template>
  <div class="boxplot-widget">
    <!-- Header -->
    <div class="boxplot-widget__header">
      <span class="boxplot-widget__title">
        {{ title || sensorLabel }}
      </span>
      <span class="boxplot-widget__range">{{ dateRangeLabel }}</span>
    </div>

    <!-- Loading -->
    <div v-if="isLoading && data.length === 0" class="boxplot-widget__state">
      <Loader2 :size="24" class="boxplot-widget__spinner" />
      <span>Aggregate werden geladen…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="boxplot-widget__state boxplot-widget__state--error">
      <AlertTriangle :size="20" />
      <span>{{ error }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="data.length === 0" class="boxplot-widget__state">
      <BarChart3 :size="24" />
      <span>Noch keine MultispeQ-Daten — CSV im Audits-Tab hochladen</span>
    </div>

    <!-- Chart -->
    <div v-else class="boxplot-widget__chart">
      <canvas ref="chartCanvas" />
    </div>
  </div>
</template>

<style scoped>
.boxplot-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--space-3);
  gap: var(--space-2);
}

.boxplot-widget__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  flex-shrink: 0;
}

.boxplot-widget__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.boxplot-widget__range {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  flex-shrink: 0;
}

.boxplot-widget__state {
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

.boxplot-widget__state--error {
  color: var(--color-error);
}

.boxplot-widget__spinner {
  animation: boxplot-spin 1s linear infinite;
}

@keyframes boxplot-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.boxplot-widget__chart {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.boxplot-widget__chart canvas {
  width: 100% !important;
  height: 100% !important;
}
</style>
