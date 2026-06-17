<script setup lang="ts">
/**
 * ActuatorRuntimeWidget — KPI display + Gantt-style timeline chart
 *
 * Shows ON/OFF state, KPI metrics (runtime, duty cycle, cycles, avg cycle)
 * computed via server-side aggregation, and a horizontal bar timeline
 * of ON/OFF/ERROR/EMERGENCY intervals.
 * Data from GET /actuators/{esp_id}/{gpio}/history?include_aggregation=true
 * Min-size: 3x3
 */
import { computed, ref, shallowRef, onMounted, onUnmounted, watch } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  TimeScale,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import { Zap } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { formatRelativeTime } from '@/utils/formatters'
import { actuatorsApi } from '@/api/actuators'
import type { ActuatorHistoryEntry, ActuatorAggregation } from '@/api/actuators'
import {
  ACTUATOR_TIME_RANGE_MS,
  ACTUATOR_TIME_RANGE_LIMITS,
  isActuatorOn,
  type ActuatorTimeRange,
} from '@/composables/useActuatorHistory'
import type { MockActuator } from '@/types'
import { tokens } from '@/utils/cssTokens'

ChartJS.register(BarElement, CategoryScale, LinearScale, TimeScale, Tooltip)

interface Props {
  zoneFilter?: string | null
  actuatorFilter?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  zoneFilter: null,
  actuatorFilter: null,
})

interface ActuatorInfo {
  id: string
  espId: string
  gpio: number
  name: string
  state: boolean
  lastCommand: string | null
  espName: string
}

interface TimelineBlock {
  start: Date
  end: Date
  state: 'on' | 'off' | 'error' | 'emergency'
  duration: number
}

const espStore = useEspStore()
const selectedRange = ref<ActuatorTimeRange>('24h')
const isLoading = ref(false)
const error = ref<string | null>(null)
const aggregation = ref<ActuatorAggregation | null>(null)
const historyEntries = shallowRef<ActuatorHistoryEntry[]>([])

const actuators = computed<ActuatorInfo[]>(() => {
  const items: ActuatorInfo[] = []

  for (const device of espStore.devices) {
    if (props.zoneFilter && device.zone_id !== props.zoneFilter) continue

    const deviceId = espStore.getDeviceId(device)
    const acts = (device.actuators as MockActuator[]) || []

    for (const act of acts) {
      const id = `${deviceId}:${act.gpio}`
      if (props.actuatorFilter && id !== props.actuatorFilter) continue

      items.push({
        id,
        espId: deviceId,
        gpio: act.gpio,
        name: act.name || `${act.actuator_type} (GPIO ${act.gpio})`,
        state: act.state,
        lastCommand: act.last_command_at,
        espName: device.name || deviceId,
      })
    }
  }

  return items
})

const activeCount = computed(() => actuators.value.filter(a => a.state).length)

// Use first actuator for timeline/aggregation
const primaryActuator = computed(() => actuators.value[0] ?? null)

function formatRuntime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}min`
}

// Convert history entries into timeline blocks
function historyToBlocks(entries: ActuatorHistoryEntry[]): TimelineBlock[] {
  if (entries.length === 0) return []

  const sorted = [...entries].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  const blocks: TimelineBlock[] = []
  let onStart: Date | null = null
  const rangeEnd = new Date()

  for (const entry of sorted) {
    const ts = new Date(entry.timestamp)

    if (!entry.success) {
      if (onStart !== null) {
        blocks.push({
          start: onStart,
          end: ts,
          state: 'on',
          duration: (ts.getTime() - onStart.getTime()) / 1000,
        })
        onStart = null
      }
      const errorEnd = new Date(ts.getTime() + 60_000)
      blocks.push({ start: ts, end: errorEnd, state: 'error', duration: 60 })
      continue
    }

    const isOn = isActuatorOn(entry)
    const isEmergency = entry.command_type?.toLowerCase() === 'emergency_stop'
    const isOff = !isOn

    if (isOn) {
      if (onStart === null) {
        // Fill OFF gap
        if (blocks.length > 0) {
          const lastBlock = blocks[blocks.length - 1]
          if (lastBlock.end.getTime() < ts.getTime()) {
            blocks.push({
              start: lastBlock.end,
              end: ts,
              state: 'off',
              duration: (ts.getTime() - lastBlock.end.getTime()) / 1000,
            })
          }
        }
        onStart = ts
      }
    } else if (isOff && onStart !== null) {
      blocks.push({
        start: onStart,
        end: ts,
        state: 'on',
        duration: (ts.getTime() - onStart.getTime()) / 1000,
      })
      if (isEmergency) {
        const emergEnd = new Date(ts.getTime() + 60_000)
        blocks.push({ start: ts, end: emergEnd, state: 'emergency', duration: 60 })
      }
      onStart = null
    }
  }

  // Still ON at end of range
  if (onStart !== null) {
    blocks.push({
      start: onStart,
      end: rangeEnd,
      state: 'on',
      duration: (rangeEnd.getTime() - onStart.getTime()) / 1000,
    })
  }

  return blocks
}

function getBlockColor(state: TimelineBlock['state']): string {
  switch (state) {
    case 'on':
      return (tokens.success || tokens.info) + 'b3'
    case 'off':
      return (tokens.textMuted || tokens.textSecondary) + '33'
    case 'error':
      return (tokens.error || tokens.warning) + 'b3'
    case 'emergency':
      return (tokens.warning || tokens.info) + 'e6'
  }
}

const timelineBlocks = computed(() => historyToBlocks(historyEntries.value))

interface FloatingBarDataPoint { x: [number, number]; y: number }

// Chart.js typing for floating bars: the data points use {x: [start, end], y} format.
// vue-chartjs Bar expects ChartData<'bar'> which uses (number | [number, number] | null)[].
// We type our computed accurately and cast at the binding site to ChartData<'bar'>.
const chartData = computed<ChartData<'bar', FloatingBarDataPoint[]>>(() => {
  const blocks = timelineBlocks.value
  return {
    datasets: [
      {
        data: blocks.map((b): FloatingBarDataPoint => ({
          x: [b.start.getTime(), b.end.getTime()],
          y: 1,
        })),
        backgroundColor: blocks.map((b) => getBlockColor(b.state)),
        barPercentage: 1.0,
        categoryPercentage: 1.0,
        borderSkipped: false,
        borderRadius: 2,
      },
    ],
  }
})

const chartOptions = computed<ChartOptions<'bar'>>(() => ({
  indexAxis: 'y' as const,
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  scales: {
    x: {
      type: 'time' as const,
      min: Date.now() - ACTUATOR_TIME_RANGE_MS[selectedRange.value],
      max: Date.now(),
      time: {
        displayFormats: {
          minute: 'HH:mm',
          hour: 'HH:mm',
          day: 'dd.MM.',
        },
      },
      ticks: {
        autoSkip: true,
        maxTicksLimit: 8,
        color: tokens.textMuted,
        font: { family: 'JetBrains Mono', size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: { display: false },
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: (ctx: { dataIndex: number }) => {
          const block = timelineBlocks.value[ctx.dataIndex]
          if (!block) return ''
          const labels: Record<string, string> = {
            on: 'EIN', off: 'AUS', error: 'FEHLER', emergency: 'NOTAUS',
          }
          return `${labels[block.state]}: ${formatRuntime(block.duration)}`
        },
      },
    },
    legend: { display: false },
  },
}))

// Data fetching
async function loadHistory(): Promise<void> {
  const act = primaryActuator.value
  if (!act) return

  isLoading.value = true
  error.value = null

  try {
    const now = new Date()
    const startTime = new Date(now.getTime() - ACTUATOR_TIME_RANGE_MS[selectedRange.value])

    const response = await actuatorsApi.getHistory(act.espId, act.gpio, {
      limit: ACTUATOR_TIME_RANGE_LIMITS[selectedRange.value],
      start_time: startTime.toISOString(),
      end_time: now.toISOString(),
      include_aggregation: true,
    })

    historyEntries.value = response.entries
    aggregation.value = response.aggregation
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Fehler beim Laden'
    historyEntries.value = []
    aggregation.value = null
  } finally {
    isLoading.value = false
  }
}

// Auto-refresh
let refreshInterval: ReturnType<typeof setInterval> | null = null

function startRefresh(): void {
  stopRefresh()
  refreshInterval = setInterval(loadHistory, 60_000)
}

function stopRefresh(): void {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

watch(selectedRange, () => loadHistory())
watch(() => primaryActuator.value?.id, () => loadHistory())

onMounted(() => {
  loadHistory()
  startRefresh()
})

onUnmounted(() => {
  stopRefresh()
})
</script>

<template>
  <div class="runtime-widget">
    <template v-if="actuators.length > 0">
      <!-- Summary -->
      <div class="runtime-widget__summary">
        <span class="runtime-widget__count">
          <span class="runtime-widget__count-active">{{ activeCount }}</span>
          / {{ actuators.length }} aktiv
        </span>
      </div>

      <!-- Actuator List -->
      <div class="runtime-widget__list">
        <div
          v-for="act in actuators"
          :key="act.id"
          class="runtime-widget__item"
        >
          <div class="runtime-widget__header">
            <span
              :class="['runtime-widget__dot', act.state ? 'runtime-widget__dot--on' : 'runtime-widget__dot--off']"
            />
            <span class="runtime-widget__name">{{ act.name }}</span>
            <span
              :class="['runtime-widget__badge', act.state ? 'runtime-widget__badge--on' : '']"
            >
              {{ act.state ? 'EIN' : 'AUS' }}
            </span>
            <span v-if="act.lastCommand" class="runtime-widget__cmd">
              {{ formatRelativeTime(act.lastCommand) }}
            </span>
          </div>
        </div>
      </div>

      <!-- KPI Section (from primary actuator's server aggregation) -->
      <div v-if="aggregation" class="runtime-widget__kpis">
        <div class="runtime-widget__kpi-row">
          <span class="runtime-widget__kpi-label">Laufzeit</span>
          <span class="runtime-widget__kpi-value">{{ formatRuntime(aggregation.total_runtime_seconds) }}</span>
        </div>
        <div class="runtime-widget__kpi-row">
          <span class="runtime-widget__kpi-label">Duty Cycle</span>
          <span class="runtime-widget__kpi-value">{{ aggregation.duty_cycle_percent }}%</span>
        </div>
        <div class="runtime-widget__kpi-row">
          <span class="runtime-widget__kpi-label">Zyklen</span>
          <span class="runtime-widget__kpi-value">{{ aggregation.total_cycles }}</span>
        </div>
        <div class="runtime-widget__kpi-row">
          <span class="runtime-widget__kpi-label">Avg. Zyklus</span>
          <span class="runtime-widget__kpi-value">{{ formatRuntime(aggregation.avg_cycle_seconds) }}</span>
        </div>
        <div class="duty-bar">
          <div
            class="duty-bar__on"
            :style="{ width: Math.min(aggregation.duty_cycle_percent, 100) + '%' }"
          />
          <div class="duty-bar__off" />
        </div>
      </div>

      <!-- TimeRange Chips -->
      <div class="runtime-widget__range-bar">
        <button
          v-for="range in (['1h', '6h', '24h', '7d'] as ActuatorTimeRange[])"
          :key="range"
          :class="['runtime-widget__range-btn', { 'runtime-widget__range-btn--active': selectedRange === range }]"
          @click="selectedRange = range"
        >
          {{ range }}
        </button>
      </div>

      <!-- Timeline Chart -->
      <div class="runtime-widget__chart">
        <Bar
          v-if="timelineBlocks.length > 0"
          :data="(chartData as unknown as ChartData<'bar'>)"
          :options="chartOptions"
        />
        <div v-else-if="!isLoading" class="runtime-widget__no-data">
          Keine History-Daten im Zeitraum
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="runtime-widget__error">
        {{ error }}
      </div>
    </template>

    <!-- Empty State -->
    <div v-else class="runtime-widget__empty">
      <Zap class="w-6 h-6" style="opacity: 0.3" />
      <span>Keine Aktoren konfiguriert</span>
    </div>
  </div>
</template>

<style scoped>
.runtime-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.runtime-widget__summary {
  display: flex;
  align-items: center;
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.runtime-widget__count {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
}

.runtime-widget__count-active {
  color: var(--color-success);
}

.runtime-widget__list {
  overflow-y: auto;
  padding: var(--space-1) 0;
  flex-shrink: 0;
  max-height: 80px;
}

.runtime-widget__item {
  padding: 0 var(--space-2);
}

.runtime-widget__item + .runtime-widget__item {
  border-top: 1px solid var(--glass-border);
  padding-top: var(--space-1);
  margin-top: var(--space-1);
}

.runtime-widget__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.runtime-widget__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.runtime-widget__dot--on { background: var(--color-success); }
.runtime-widget__dot--off { background: var(--color-text-muted); opacity: 0.5; }

.runtime-widget__name {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-widget__badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-quaternary);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.runtime-widget__badge--on {
  background: var(--color-zone-normal, rgba(34, 197, 94, 0.15));
  color: var(--color-success);
}

.runtime-widget__cmd {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  opacity: 0.7;
  flex-shrink: 0;
}

/* KPI Section */
.runtime-widget__kpis {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-1) var(--space-2);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.runtime-widget__kpi-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.runtime-widget__kpi-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.runtime-widget__kpi-value {
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--color-text-primary);
}

/* Duty Cycle Bar */
.duty-bar {
  display: flex;
  height: 6px;
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-top: var(--space-1);
}

.duty-bar__on {
  background: var(--color-success);
  transition: width var(--transition-base);
}

.duty-bar__off {
  background: var(--color-text-muted);
  opacity: 0.15;
  flex: 1;
}

/* TimeRange Chips */
.runtime-widget__range-bar {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.runtime-widget__range-btn {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  font-weight: 500;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: var(--color-bg-tertiary);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.runtime-widget__range-btn:hover {
  color: var(--color-text-secondary);
  border-color: var(--glass-border);
}

.runtime-widget__range-btn--active {
  background: rgba(167, 139, 250, 0.12);
  color: var(--color-iridescent-1);
  border-color: var(--color-iridescent-1);
}

/* Timeline Chart */
.runtime-widget__chart {
  flex: 1;
  min-height: 48px;
  padding: 0 var(--space-2) var(--space-1);
  position: relative;
}

.runtime-widget__chart canvas {
  width: 100% !important;
  height: 100% !important;
}

.runtime-widget__no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  opacity: 0.6;
}

.runtime-widget__error {
  font-size: var(--text-xs);
  color: var(--color-error);
  padding: 0 var(--space-2) var(--space-1);
  flex-shrink: 0;
}

.runtime-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
