<script setup lang="ts">
/**
 * MonitorExpanded1hChart — reusable 1h Chart.js Line panel for Monitor expand.
 *
 * Extracted from MonitorView sensor-card expand (same query path, gap markers,
 * look & feel). Used by SensorCard expand and TankIstSollPanel compact metrics.
 */

import { computed, ref, watch } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  Filler,
} from 'chart.js'
import type { TooltipItem } from 'chart.js'
import 'chartjs-adapter-date-fns'
import { sensorsApi } from '@/api/sensors'
import type { SensorReading } from '@/types'
import {
  type GapDataPoint,
  calculateMedianInterval,
  computeExpectedInterval,
  insertGapMarkers,
} from '@/utils/gapDetection'
import { getChartColors } from '@/utils/chartColors'
import { tokens } from '@/utils/cssTokens'
import { formatDateTime, formatSensorValue } from '@/utils/formatters'
import { getSensorConfig } from '@/utils/sensorDefaults'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  Filler,
)

export interface ExpandedLivePoint {
  x: number
  y: number
}

interface Props {
  espId: string
  gpio: number
  sensorType?: string
  unit?: string
  /** Optional live sample newer than the API snapshot (Monitor WS tail). */
  liveSample?: ExpandedLivePoint | null
  /** "Zeitreihe anzeigen" — SensorCard + TankIstSollPanel (monitor-compact). */
  showDetailAction?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sensorType: undefined,
  unit: '',
  liveSample: null,
  showDetailAction: false,
})

const emit = defineEmits<{
  detail: []
}>()

const loading = ref(false)
const readings = ref<SensorReading[]>([])
const liveTail = ref<ExpandedLivePoint[]>([])

function chartColor(): string {
  const palette = getChartColors()
  if (palette.length === 0) return tokens.accent || tokens.info
  return palette[0] || tokens.accent || tokens.info
}

async function fetchChartData(): Promise<void> {
  loading.value = true
  readings.value = []
  liveTail.value = []
  try {
    const now = new Date()
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000)
    const response = await sensorsApi.queryData({
      esp_id: props.espId,
      gpio: props.gpio,
      sensor_type: props.sensorType || undefined,
      start_time: oneHourAgo.toISOString(),
      end_time: now.toISOString(),
      limit: 500,
    })
    readings.value = response.readings ?? []
  } catch {
    readings.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.espId, props.gpio, props.sensorType] as const,
  () => {
    void fetchChartData()
  },
  { immediate: true },
)

watch(
  () => props.liveSample,
  (sample) => {
    if (!sample) return

    const latestApiTs =
      readings.value.length > 0
        ? new Date(readings.value[readings.value.length - 1].timestamp).getTime()
        : 0

    if (sample.x <= latestApiTs) return

    const tail = liveTail.value
    const prev = tail[tail.length - 1]
    const isNearDuplicate =
      !!prev &&
      Math.abs(sample.x - prev.x) < 1000 &&
      Math.abs(sample.y - prev.y) < 0.0001
    if (isNearDuplicate) return

    liveTail.value = [...tail, sample].slice(-120)
  },
  { immediate: true },
)

const chartData = computed(() => {
  const apiPoints = readings.value
    .map((r) => ({
      x: new Date(r.timestamp).getTime(),
      y: r.processed_value ?? r.raw_value,
    }))
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  const combined = [...apiPoints, ...liveTail.value].sort((a, b) => a.x - b.x)

  if (!combined.length) return { datasets: [] }

  const gapPoints: GapDataPoint[] = combined.map((p) => ({
    timestamp: new Date(p.x),
    value: p.y,
  }))
  const medianMs = calculateMedianInterval(gapPoints)
  const expectedIntervalMs = computeExpectedInterval(medianMs, null, gapPoints.length)
  const withGaps = insertGapMarkers(gapPoints, expectedIntervalMs)
  const data = withGaps.map((p) => ({ x: p.timestamp.getTime(), y: p.value }))
  const color = chartColor()
  const unit = props.unit

  return {
    datasets: [
      {
        label: unit ? `Letzte Stunde (${unit})` : 'Letzte Stunde',
        data,
        borderColor: color,
        backgroundColor: `${color}20`,
        borderWidth: 2,
        pointRadius: combined.length > 100 ? 0 : 2,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: true,
        spanGaps: false,
      },
    ],
  }
})

const yAxisDecimals = computed(
  () => getSensorConfig(props.sensorType ?? '')?.decimals ?? 1,
)

const chartOptions = computed(() => {
  const unit = props.unit
  const color = chartColor()
  const decimals = yAxisDecimals.value

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tokens.backdropColor,
        borderColor: tokens.glassBorder,
        borderWidth: 1,
        titleFont: { family: 'JetBrains Mono', size: 11 },
        bodyFont: { family: 'JetBrains Mono', size: 12 },
        titleColor: tokens.textSecondary,
        bodyColor: tokens.textPrimary,
        padding: 10,
        callbacks: {
          title: (items: TooltipItem<'line'>[]) => {
            if (!items.length) return ''
            return formatDateTime(new Date(items[0].parsed.x ?? 0))
          },
          label: (item: TooltipItem<'line'>) =>
            ` ${formatSensorValue(item.parsed.y, unit, decimals)}`,
        },
      },
    },
    scales: {
      x: {
        type: 'time' as const,
        time: {
          displayFormats: { second: 'HH:mm:ss', minute: 'HH:mm', hour: 'HH:mm' },
        },
        grid: { color: tokens.glassBorder },
        ticks: {
          color: tokens.textMuted,
          font: { family: 'JetBrains Mono', size: 10 },
          maxTicksLimit: 6,
        },
        border: { display: false },
      },
      y: {
        grid: { color: tokens.glassBorder },
        ticks: {
          color,
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (val: string | number) =>
            formatSensorValue(Number(val), unit, decimals),
        },
        border: { display: false },
      },
    },
  }
})
</script>

<template>
  <div class="monitor-sensor-card__charts" @click.stop>
    <div class="monitor-sensor-card__1h-chart">
      <div v-if="loading" class="monitor-sensor-card__chart-loading">
        <div class="sensor-detail__spinner" />
        <span>Lade Daten...</span>
      </div>
      <div v-else-if="chartData.datasets.length > 0" class="monitor-expanded-1h-chart__canvas">
        <Line :data="chartData" :options="chartOptions" />
      </div>
      <div v-else class="monitor-sensor-card__chart-empty">
        Keine Daten der letzten Stunde
      </div>
    </div>
    <div v-if="showDetailAction" class="monitor-sensor-card__actions">
      <button
        type="button"
        class="monitor-sensor-card__detail-btn"
        @click.stop="emit('detail')"
      >
        <ChevronRight class="w-4 h-4" />
        <span>Zeitreihe anzeigen</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.monitor-sensor-card__charts {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
}

.monitor-sensor-card__1h-chart {
  min-height: 60px;
}

.monitor-expanded-1h-chart__canvas {
  height: 160px;
  width: 100%;
}

.monitor-sensor-card__chart-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-6);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.monitor-sensor-card__chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-style: italic;
}

.monitor-sensor-card__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.monitor-sensor-card__detail-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  width: fit-content;
}

.monitor-sensor-card__detail-btn:hover {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 6%, transparent);
}

.sensor-detail__spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid var(--color-bg-tertiary);
  border-top-color: var(--color-iridescent-1);
  border-radius: 50%;
  animation: monitor-expanded-spin 0.8s linear infinite;
}

@keyframes monitor-expanded-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
