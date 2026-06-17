<script setup lang="ts">
/**
 * SensorHistoryView
 *
 * Historical sensor data visualization with time-range selection,
 * sensor picker, and multi-line chart. Uses existing sensorsApi.queryData().
 *
 * Route: /sensor-history
 */

import { ref, computed, watch } from 'vue'
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
import { BarChart3, Download } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { useEspStore } from '@/stores/esp'
import type { SensorReading } from '@/types'
import TimeRangeSelector, { type TimePreset } from '@/components/charts/TimeRangeSelector.vue'

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

const espStore = useEspStore()

const CHART_COLORS = [
  '#a78bfa', '#34d399', '#f97316', '#3b82f6',
  '#ec4899', '#facc15', '#06b6d4', '#f43f5e',
]

// State
const selectedPreset = ref<TimePreset>('24h')
const startTime = ref(new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString())
const endTime = ref(new Date().toISOString())

const selectedEspId = ref('')
const selectedGpio = ref<number | null>(null)
const selectedSensorType = ref('')

const readings = ref<SensorReading[]>([])
const isLoading = ref(false)
const errorMsg = ref('')

const availableDevices = computed(() => espStore.devices)

function onRangeChange(payload: { start: string; end: string }) {
  startTime.value = payload.start
  endTime.value = payload.end
  if (selectedEspId.value) fetchData()
}

async function fetchData() {
  if (!selectedEspId.value) return
  isLoading.value = true
  errorMsg.value = ''
  try {
    const query: Record<string, unknown> = {
      esp_id: selectedEspId.value,
      start_time: startTime.value,
      end_time: endTime.value,
      limit: 1000,
    }
    if (selectedGpio.value !== null) query.gpio = selectedGpio.value
    if (selectedSensorType.value) query.sensor_type = selectedSensorType.value

    const response = await sensorsApi.queryData(query as Parameters<typeof sensorsApi.queryData>[0])
    readings.value = response.readings ?? []
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : 'Fehler beim Laden'
    readings.value = []
  } finally {
    isLoading.value = false
  }
}

watch([selectedEspId, selectedGpio, selectedSensorType], () => {
  if (selectedEspId.value) fetchData()
})

// Group readings by sensor_type (or unit as fallback) for separate datasets
const groupedReadings = computed(() => {
  const groups = new Map<string, { unit: string; readings: SensorReading[] }>()
  for (const r of readings.value) {
    const key = (r as SensorReading & { sensor_type?: string }).sensor_type || r.unit || 'unknown'
    if (!groups.has(key)) {
      groups.set(key, { unit: r.unit ?? '', readings: [] })
    }
    groups.get(key)!.readings.push(r)
  }
  return groups
})

const uniqueUnits = computed(() => {
  const units = new Set<string>()
  for (const group of groupedReadings.value.values()) {
    units.add(group.unit)
  }
  return [...units]
})

// Chart data — one dataset per sensor_type, with separate Y-axis per unit
const chartData = computed(() => {
  const groups = groupedReadings.value
  const units = uniqueUnits.value
  const datasets = [...groups.entries()].map(([sensorType, group], idx) => {
    const colorIdx = idx % CHART_COLORS.length
    const yAxisID = units.length > 1
      ? (units.indexOf(group.unit) === 0 ? 'y' : 'y1')
      : 'y'
    return {
      label: `${sensorType}${group.unit ? ' (' + group.unit + ')' : ''}`,
      data: group.readings.map(r => ({
        x: new Date(r.timestamp).getTime(),
        y: r.processed_value ?? r.raw_value,
      })),
      borderColor: CHART_COLORS[colorIdx],
      backgroundColor: `${CHART_COLORS[colorIdx]}20`,
      borderWidth: 2,
      pointRadius: group.readings.length > 200 ? 0 : 2,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
      yAxisID,
    }
  })
  return { datasets }
})

const chartOptions = computed(() => {
  const units = uniqueUnits.value
  const hasMultipleDatasets = groupedReadings.value.size > 1
  const hasDualAxis = units.length > 1

  const scales: Record<string, unknown> = {
    x: {
      type: 'time' as const,
      time: {
        displayFormats: { second: 'HH:mm:ss', minute: 'HH:mm', hour: 'HH:mm', day: 'dd.MM' },
      },
      grid: { color: 'rgba(29,29,42,0.8)' },
      ticks: { color: '#484860', font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 8 },
      border: { display: false },
    },
    y: {
      position: 'left' as const,
      grid: { color: 'rgba(29,29,42,0.8)' },
      ticks: {
        color: CHART_COLORS[0],
        font: { family: 'JetBrains Mono', size: 10 },
        callback: (val: string | number) => {
          const unit = units[0] ?? ''
          return `${val}${unit ? ' ' + unit : ''}`
        },
      },
      border: { display: false },
      title: hasDualAxis ? {
        display: true,
        text: units[0] ?? '',
        color: CHART_COLORS[0],
        font: { family: 'JetBrains Mono', size: 10 },
      } : undefined,
    },
  }

  if (hasDualAxis) {
    scales.y1 = {
      position: 'right' as const,
      grid: { drawOnChartArea: false },
      ticks: {
        color: CHART_COLORS[1],
        font: { family: 'JetBrains Mono', size: 10 },
        callback: (val: string | number) => {
          const unit = units[1] ?? ''
          return `${val}${unit ? ' ' + unit : ''}`
        },
      },
      border: { display: false },
      title: {
        display: true,
        text: units[1] ?? '',
        color: CHART_COLORS[1],
        font: { family: 'JetBrains Mono', size: 10 },
      },
    }
  }

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: {
        display: hasMultipleDatasets,
        labels: {
          color: '#8585a0',
          font: { family: 'JetBrains Mono', size: 11 },
          boxWidth: 12,
          padding: 12,
        },
      },
      tooltip: {
        backgroundColor: 'rgba(7,7,13,0.92)',
        borderColor: 'rgba(133,133,160,0.3)',
        borderWidth: 1,
        titleFont: { family: 'JetBrains Mono', size: 11 },
        bodyFont: { family: 'JetBrains Mono', size: 12 },
        titleColor: '#8585a0',
        bodyColor: '#eaeaf2',
        padding: 10,
        callbacks: {
          title: (items: TooltipItem<'line'>[]) => {
            if (!items.length) return ''
            const x = items[0].parsed.x ?? 0
            return new Date(x).toLocaleString('de-DE')
          },
          label: (item: TooltipItem<'line'>) => {
            const label = item.dataset.label ?? 'Sensor'
            return ` ${label}: ${item.parsed.y?.toFixed(2)}`
          },
        },
      },
    },
    scales,
  }
})

function exportCsv() {
  if (!readings.value.length) return
  const header = 'timestamp,raw_value,processed_value,unit,quality'
  const rows = readings.value.map(r =>
    `${r.timestamp},${r.raw_value},${r.processed_value ?? ''},${r.unit ?? ''},${r.quality}`
  )
  const csv = [header, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sensor-data_${selectedEspId.value}_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="sensor-history">
    <!-- Header -->
    <div class="sensor-history__header">
      <BarChart3 :size="20" class="sensor-history__icon" />
      <h2 class="sensor-history__title">Sensor-Zeitreihen</h2>
    </div>

    <!-- Controls -->
    <div class="sensor-history__controls">
      <!-- Sensor selection -->
      <div class="sensor-history__filters">
        <div class="sensor-history__field">
          <label class="sensor-history__label">ESP-Geraet</label>
          <select v-model="selectedEspId" class="sensor-history__select">
            <option value="" disabled>Bitte waehlen</option>
            <option
              v-for="device in availableDevices"
              :key="espStore.getDeviceId(device)"
              :value="espStore.getDeviceId(device)"
            >
              {{ device.name || espStore.getDeviceId(device) }}
            </option>
          </select>
        </div>

        <div class="sensor-history__field">
          <label class="sensor-history__label">GPIO (optional)</label>
          <input
            v-model.number="selectedGpio"
            type="number"
            min="0"
            max="39"
            placeholder="Alle"
            class="sensor-history__input"
          />
        </div>

        <div class="sensor-history__field">
          <label class="sensor-history__label">Sensortyp (optional)</label>
          <input
            v-model="selectedSensorType"
            type="text"
            placeholder="z.B. temperature"
            class="sensor-history__input"
          />
        </div>
      </div>

      <!-- Time range -->
      <TimeRangeSelector
        v-model="selectedPreset"
        @range-change="onRangeChange"
      />
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="sensor-history__status">
      <div class="sensor-history__spinner" />
      <span>Lade Sensordaten...</span>
    </div>

    <!-- Error -->
    <div v-else-if="errorMsg" class="sensor-history__status sensor-history__status--error">
      {{ errorMsg }}
    </div>

    <!-- Empty -->
    <div v-else-if="!selectedEspId" class="sensor-history__status">
      Waehle ein ESP-Geraet um Daten anzuzeigen.
    </div>

    <div v-else-if="readings.length === 0 && !isLoading" class="sensor-history__status">
      Keine Daten fuer den gewaehlten Zeitraum.
    </div>

    <!-- Chart -->
    <div v-else class="sensor-history__chart-wrap">
      <div class="sensor-history__chart-header">
        <span class="sensor-history__point-count">
          {{ readings.length }} Datenpunkte
          <template v-if="groupedReadings.size > 1"> · {{ groupedReadings.size }} Sensortypen</template>
        </span>
        <button class="sensor-history__export-btn" @click="exportCsv">
          <Download :size="14" /> CSV Export
        </button>
      </div>
      <div class="sensor-history__chart" style="height: 400px">
        <Line :data="chartData" :options="(chartOptions as any)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sensor-history {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 960px;
  margin: 0 auto;
}

.sensor-history__header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.sensor-history__icon {
  color: var(--color-iridescent-1);
}

.sensor-history__title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.sensor-history__controls {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 1rem;
}

.sensor-history__filters {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.sensor-history__field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
  min-width: 140px;
}

.sensor-history__label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.sensor-history__select,
.sensor-history__input {
  padding: 0.5rem 0.625rem;
  font-size: 0.8125rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color 0.15s;
}

.sensor-history__select:focus,
.sensor-history__input:focus {
  border-color: var(--color-iridescent-1);
}

.sensor-history__select {
  color-scheme: dark;
}

/* Status states */
.sensor-history__status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  text-align: center;
}

.sensor-history__status--error {
  color: var(--color-error);
}

.sensor-history__spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid var(--color-bg-tertiary);
  border-top-color: var(--color-iridescent-1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Chart area */
.sensor-history__chart-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sensor-history__chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sensor-history__point-count {
  font-size: 0.6875rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-muted);
}

.sensor-history__export-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.6875rem;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.sensor-history__export-btn:hover {
  border-color: var(--color-iridescent-1);
  color: var(--color-text-primary);
}

.sensor-history__chart {
  position: relative;
  width: 100%;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 0.75rem;
}
</style>
