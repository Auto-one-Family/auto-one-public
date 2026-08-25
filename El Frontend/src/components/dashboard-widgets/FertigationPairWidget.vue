<script setup lang="ts">
/**
 * FertigationPairWidget Component
 *
 * Dashboard widget for displaying inflow vs. runoff sensor pairs (EC/pH).
 * Shows KPI cards, difference with color-coding, and embedded historical chart.
 *
 * Props support configurability for thresholds and time range.
 * Uses Tailwind CSS with design tokens for styling.
 */

import { ref, computed, watch } from 'vue'
import { TrendingUp, TrendingDown, AlertCircle, Droplet, Activity } from 'lucide-vue-next'
import { useFertigationKPIs } from '@/composables/useFertigationKPIs'
import MultiSensorChart from '@/components/charts/MultiSensorChart.vue'
import type { ChartSensor, MockSensor } from '@/types'
import { getSensorConfig } from '@/utils/sensorDefaults'
import { formatNumber } from '@/utils/formatters'
import { tokens } from '@/utils/cssTokens'
import { useEspStore } from '@/stores/esp'
import {
  collectStoreSensors,
  findStoreSensorByStoredId,
} from '@/utils/sensorConfigLookup'

// =============================================================================
// Props
// =============================================================================

interface ReferenceBand {
  label: string
  min: number
  max: number
  color?: string
}

interface Props {
  /** Inflow sensor configuration ID or identifier */
  inflowSensorId: string
  /** Runoff sensor configuration ID or identifier */
  runoffSensorId: string
  /** Sensor type: 'ec' or 'ph' */
  sensorType: 'ec' | 'ph'
  /** Warning threshold for difference (e.g., 0.5 mS/cm for EC) */
  diffWarningThreshold?: number
  /** Critical threshold for difference (e.g., 0.8 mS/cm for EC) */
  diffCriticalThreshold?: number
  /** Time range for embedded chart */
  timeRange?: '1h' | '6h' | '24h' | '7d' | '30d'
  /** Widget title (defaults to "EC Fertigation" or "pH Fertigation") */
  title?: string
  /** Optional zone/subzone context for labeling */
  zoneLabel?: string
  /** Reference bands for context (e.g., ideal pH 6.0-7.0) */
  referenceBands?: ReferenceBand[]
}

const props = withDefaults(defineProps<Props>(), {
  diffWarningThreshold: 0.5,
  diffCriticalThreshold: 0.8,
  timeRange: '24h',
  zoneLabel: undefined,
  referenceBands: () => [],
})

const defaultTitle = computed(() => {
  return props.sensorType === 'ec' ? 'EC Fertigation' : 'pH Fertigation'
})

// =============================================================================
// Composable
// =============================================================================

const inflowSensorIdRef = ref(props.inflowSensorId)
const runoffSensorIdRef = ref(props.runoffSensorId)
const timeRangeRef = ref(props.timeRange)
const diffWarningRef = ref(props.diffWarningThreshold)
const diffCriticalRef = ref(props.diffCriticalThreshold)

const { kpi, isLoading, error, reload } = useFertigationKPIs({
  inflowSensorId: inflowSensorIdRef,
  runoffSensorId: runoffSensorIdRef,
  timeRange: timeRangeRef,
  diffWarningThreshold: diffWarningRef,
  diffCriticalThreshold: diffCriticalRef,
})

// Watch props for changes
watch(() => props.inflowSensorId, (newVal) => {
  inflowSensorIdRef.value = newVal
})

watch(() => props.runoffSensorId, (newVal) => {
  runoffSensorIdRef.value = newVal
})

watch(() => props.timeRange, (newVal) => {
  if (newVal) timeRangeRef.value = newVal
})

// =============================================================================
// Computed
// =============================================================================

const sensorConfig = computed(() => {
  return getSensorConfig(props.sensorType)
})

/** AUT-913 B3: comparison mode for the embedded chart (inflow vs. runoff share one unit). */
const comparisonMode = ref<'overlay' | 'difference'>('overlay')

const differenceClass = computed(() => {
  const baseClasses = ['text-5xl font-bold font-mono']

  if (kpi.value.healthStatus === 'alarm') {
    return [...baseClasses, 'text-danger-500']
  }
  if (kpi.value.healthStatus === 'warning') {
    return [...baseClasses, 'text-warning-500']
  }
  return [...baseClasses, 'text-success-500']
})

const healthColorClass = computed(() => {
  switch (kpi.value.healthStatus) {
    case 'alarm':
      return 'bg-danger-500/20 border-danger-500/40'
    case 'warning':
      return 'bg-warning-500/20 border-warning-500/40'
    case 'ok':
      return 'bg-success-500/20 border-success-500/40'
    default:
      return 'bg-gray-500/10 border-gray-500/30'
  }
})

const trendIcon = computed(() => {
  if (kpi.value.differenceTrend === 'up') return TrendingUp
  if (kpi.value.differenceTrend === 'down') return TrendingDown
  return Activity
})

const espStore = useEspStore()

function toChartSensor(storedId: string, role: 'Inflow' | 'Runoff', color: string): ChartSensor | null {
  const sensors = collectStoreSensors(espStore.devices)
  const sensor = findStoreSensorByStoredId(storedId, sensors)
  if (!sensor) return null
  const host = espStore.devices.find((device) =>
    ((device.sensors as MockSensor[] | undefined) ?? []).some((candidate) =>
      sensor.config_id
        ? candidate.config_id === sensor.config_id
        : candidate === sensor,
    ),
  )
  if (!host) return null
  return {
    id: `${role.toLowerCase()}_${sensor.config_id ?? storedId}`,
    espId: espStore.getDeviceId(host),
    gpio: sensor.gpio,
    sensorType: sensor.sensor_type,
    name: role,
    color,
    unit: sensorConfig.value?.unit || sensor.unit || '',
  }
}

const chartSensors = computed<ChartSensor[]>(() => {
  const inflow = toChartSensor(inflowSensorIdRef.value, 'Inflow', tokens.success)
  const runoff = toChartSensor(runoffSensorIdRef.value, 'Runoff', tokens.error)
  return [inflow, runoff].filter((row): row is ChartSensor => row != null)
})

const valueDecimals = computed(() => sensorConfig.value?.decimals ?? 2)

const formattedDifference = computed(() => {
  if (kpi.value.difference === null) return '-'
  return formatNumber(kpi.value.difference, valueDecimals.value)
})

const formattedInflowValue = computed(() => {
  if (kpi.value.inflowValue === null) return '-'
  return formatNumber(kpi.value.inflowValue, valueDecimals.value)
})

const formattedRunoffValue = computed(() => {
  if (kpi.value.runoffValue === null) return '-'
  return formatNumber(kpi.value.runoffValue, valueDecimals.value)
})

// =============================================================================
// Template
// =============================================================================
</script>

<template>
  <div class="fertigation-widget rounded-lg border border-dark-700 bg-dark-800 p-6 shadow-lg">
    <!-- Header -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h3 class="text-lg font-semibold text-dark-50">
          {{ title || defaultTitle }}
        </h3>
        <p v-if="zoneLabel" class="mt-1 text-xs text-dark-400">{{ zoneLabel }}</p>
      </div>
      <button
        @click="reload"
        :disabled="isLoading"
        class="rounded-md bg-dark-700 p-2 text-dark-300 transition hover:bg-dark-600 disabled:opacity-50"
        :data-testid="`fertigation-reload-${sensorType}`"
      >
        <Activity class="h-5 w-5" />
      </button>
    </div>

    <!-- Error state -->
    <div
      v-if="error && !isLoading"
      class="mb-4 flex gap-3 rounded-md bg-danger-500/10 p-3 text-danger-400"
    >
      <AlertCircle class="h-5 w-5 flex-shrink-0" />
      <p class="text-sm">{{ error }}</p>
    </div>

    <!-- KPI Cards Row -->
    <div class="mb-6 grid grid-cols-2 gap-4">
      <!-- Inflow Card -->
      <div
        class="flex flex-col gap-2 rounded-lg bg-dark-700 p-4"
        :data-testid="`fertigation-inflow-kpi-${sensorType}`"
      >
        <div class="flex items-center gap-2">
          <Droplet class="h-4 w-4 text-info-400" />
          <span class="text-xs font-medium uppercase text-dark-400">Inflow</span>
        </div>
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-bold text-info-300">
            {{ formattedInflowValue }}
          </span>
          <span class="text-xs text-dark-500">{{ sensorConfig?.unit || '' }}</span>
        </div>
        <p class="text-xs text-dark-500">
          {{ kpi.lastInflowTime ? new Date(kpi.lastInflowTime).toLocaleTimeString('de-DE') : 'Keine Daten' }}
        </p>
      </div>

      <!-- Runoff Card -->
      <div
        class="flex flex-col gap-2 rounded-lg bg-dark-700 p-4"
        :data-testid="`fertigation-runoff-kpi-${sensorType}`"
      >
        <div class="flex items-center gap-2">
          <Droplet class="h-4 w-4 text-warning-400" />
          <span class="text-xs font-medium uppercase text-dark-400">Runoff</span>
        </div>
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-bold text-warning-300">
            {{ formattedRunoffValue }}
          </span>
          <span class="text-xs text-dark-500">{{ sensorConfig?.unit || '' }}</span>
        </div>
        <p class="text-xs text-dark-500">
          {{ kpi.lastRunoffTime ? new Date(kpi.lastRunoffTime).toLocaleTimeString('de-DE') : 'Keine Daten' }}
        </p>
      </div>
    </div>

    <!-- Difference Section -->
    <div
      class="mb-6 rounded-lg border-2 p-6 text-center transition-colors"
      :class="healthColorClass"
      :data-testid="`fertigation-${sensorType}-diff-value`"
    >
      <div class="mb-2 flex items-center justify-between">
        <p class="text-xs font-medium uppercase text-dark-400">Differenz (Runoff - Inflow)</p>
        <!-- Staleness Indicator Badge -->
        <span
          v-if="kpi.stalenessSeconds !== null && kpi.stalenessSeconds > 60"
          class="inline-block rounded-full px-2 py-1 text-xs font-medium transition-colors"
          :class="[
            kpi.stalenessSeconds > 300
              ? 'bg-danger-500/30 text-danger-300'
              : 'bg-warning-500/30 text-warning-300',
          ]"
        >
          {{ Math.round(kpi.stalenessSeconds) }}s stale
        </span>
      </div>
      <div class="flex items-center justify-center gap-3">
        <div :class="differenceClass">
          {{ formattedDifference }}
        </div>
        <div class="flex flex-col gap-1">
          <span class="text-xs text-dark-400">{{ sensorConfig?.unit || '' }}</span>
          <component
            :is="trendIcon"
            :class="[
              'h-5 w-5',
              kpi.differenceTrend === 'up' ? 'text-danger-400' : 'text-success-400',
            ]"
          />
        </div>
      </div>
      <p v-if="kpi.healthReason" class="mt-3 text-xs text-dark-300">
        {{ kpi.healthReason }}
      </p>
    </div>

    <!-- Data Quality Indicator -->
    <div class="mb-6 flex items-center gap-2 rounded-md bg-dark-700 p-3">
      <Activity class="h-4 w-4 text-dark-500" />
      <span class="text-xs text-dark-400">
        <span v-if="kpi.dataQuality === 'good'" class="text-success-400">
          Beide Sensoren aktiv
        </span>
        <span v-else-if="kpi.dataQuality === 'degraded'" class="text-warning-400">
          Nur ein Sensor aktiv
        </span>
        <span v-else class="text-danger-400">
          Keine Sensordaten
        </span>
      </span>
    </div>

    <!-- Reference Bands (optional) -->
    <div v-if="referenceBands.length > 0" class="mb-6 space-y-2">
      <p class="text-xs font-medium uppercase text-dark-400">Referenzbereiche</p>
      <div class="space-y-1">
        <div
          v-for="band in referenceBands"
          :key="band.label"
          class="flex items-center justify-between gap-2 rounded-md bg-dark-700 p-2 text-xs"
        >
          <span class="text-dark-300">{{ band.label }}</span>
          <span class="text-dark-500">
            {{ formatNumber(band.min, valueDecimals) }} – {{ formatNumber(band.max, valueDecimals) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Historical Chart -->
    <div class="space-y-2">
      <p class="text-xs font-medium uppercase text-dark-400">Zeitreihe</p>
      <MultiSensorChart
        v-model:comparison-mode="comparisonMode"
        v-model:time-range="timeRangeRef"
        :sensors="chartSensors"
        :height="300"
        :enable-live-updates="true"
      />
    </div>
  </div>
</template>

<style scoped>
.fertigation-widget {
  container-type: inline-size;
}

@media (max-width: 640px) {
  .fertigation-widget :deep(.stat-card) {
    gap: 0.75rem;
  }
}
</style>
