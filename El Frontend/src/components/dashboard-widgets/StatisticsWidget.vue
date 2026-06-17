<script setup lang="ts">
/**
 * StatisticsWidget — KPI card showing Min/Avg/Max/StdDev from Stats-Endpoint
 *
 * Data source: REST API (sensorsApi.getStats), NOT WebSocket.
 * Unit is resolved from SENSOR_TYPE_CONFIG, not from the API response.
 */
import { ref, computed, watch } from 'vue'
import { sensorsApi } from '@/api/sensors'
import { useEspStore } from '@/stores/esp'
import { useSensorId } from '@/composables/useSensorId'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'
import { formatNumber } from '@/utils/formatters'
import type { MockSensor, SensorStats } from '@/types'
import { Loader2, AlertTriangle, BarChart3 } from 'lucide-vue-next'

interface Props {
  sensorId?: string
  timeRange?: string
  showStdDev?: boolean
  showQuality?: boolean
  title?: string
  zoneId?: string
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '7d',
  showStdDev: true,
  showQuality: false,
})

// Centralized sensorId parsing (getter fallback for optional prop)
const { espId, gpio, sensorType } = useSensorId(() => props.sensorId ?? '')

// Resolve sensor instance from store for sensor_kind / alert_config lookups (Wave 1)
const espStore = useEspStore()
const resolvedSensor = computed<MockSensor | null>(() => {
  if (!espId.value || gpio.value === null || !sensorType.value) return null
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === espId.value)
  if (!device) return null
  return ((device.sensors as MockSensor[]) || []).find(s =>
    s.gpio === gpio.value && s.sensor_type === sensorType.value
  ) ?? null
})

// Wave 1: Snapshot-Sensoren (MultispeQ) → Badge anzeigen, kein Live-Stream
const isSnapshot = computed(() => resolvedSensor.value?.sensor_kind === 'snapshot')

// Wave 1: alert_config.custom_thresholds als Override für Schwellenwerte.
// Falls vorhanden, hat custom_thresholds Vorrang vor sensor.thresholds.
interface ThresholdSet {
  warning_min?: number | null
  warning_max?: number | null
  critical_min?: number | null
  critical_max?: number | null
}
const effectiveThresholds = computed<ThresholdSet | null>(() => {
  const sensor = resolvedSensor.value as (MockSensor & {
    alert_config?: { custom_thresholds?: ThresholdSet | null } | null
    thresholds?: ThresholdSet | null
  }) | null
  if (!sensor) return null
  const custom = sensor.alert_config?.custom_thresholds
  if (custom && (
    custom.warning_min != null ||
    custom.warning_max != null ||
    custom.critical_min != null ||
    custom.critical_max != null
  )) {
    return custom
  }
  return sensor.thresholds ?? null
})

// Unit from SENSOR_TYPE_CONFIG (NOT from API response)
const unit = computed(() => {
  if (!sensorType.value) return ''
  return SENSOR_TYPE_CONFIG[sensorType.value]?.unit ?? ''
})

// Decimals from SENSOR_TYPE_CONFIG
const decimals = computed(() => {
  if (!sensorType.value) return 1
  return SENSOR_TYPE_CONFIG[sensorType.value]?.decimals ?? 1
})

// Sensor label for header fallback
const sensorLabel = computed(() => {
  if (!sensorType.value) return ''
  return SENSOR_TYPE_CONFIG[sensorType.value]?.label ?? sensorType.value
})

// Time range calculation
const TIME_RANGE_MS: Record<string, number> = {
  '1h':  1 * 60 * 60 * 1000,
  '6h':  6 * 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
  '7d':  7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
}

const TIME_RANGE_LABELS: Record<string, string> = {
  '1h': '1 Stunde',
  '6h': '6 Stunden',
  '24h': '24 Stunden',
  '7d': '7 Tage',
  '30d': '30 Tage',
}

// State
const stats = ref<SensorStats | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)

// Fetch stats via watch (NOT watchEffect — avoid async cleanup race)
watch(
  [espId, gpio, sensorType, () => props.timeRange],
  async () => {
    if (!espId.value || gpio.value === null || !sensorType.value) {
      stats.value = null
      return
    }

    isLoading.value = true
    error.value = null

    try {
      const now = new Date()
      const rangeMs = TIME_RANGE_MS[props.timeRange] ?? TIME_RANGE_MS['7d']
      const startTime = new Date(now.getTime() - rangeMs).toISOString()
      const endTime = now.toISOString()

      const response = await sensorsApi.getStats(espId.value, gpio.value, {
        start_time: startTime,
        end_time: endTime,
        sensor_type: sensorType.value,
      })
      stats.value = response.stats
    } catch {
      error.value = 'Statistiken konnten nicht geladen werden'
      stats.value = null
    } finally {
      isLoading.value = false
    }
  },
  { immediate: true }
)

// KPI items for template iteration
const kpiItems = computed(() => {
  if (!stats.value) return []
  const items = [
    { label: 'Min', value: stats.value.min_value },
    { label: 'Avg', value: stats.value.avg_value },
    { label: 'Max', value: stats.value.max_value },
  ]
  if (props.showStdDev) {
    items.push({ label: 'StdDev', value: stats.value.std_dev })
  }
  return items
})

// Quality distribution grouped for display
const qualityGroups = computed(() => {
  if (!stats.value || !props.showQuality) return null
  const dist = stats.value.quality_distribution
  const total = Object.values(dist).reduce((sum, v) => sum + v, 0)
  if (total === 0) return null

  const good = (dist.excellent ?? 0) + (dist.good ?? 0)
  const fair = dist.fair ?? 0
  const bad = (dist.poor ?? 0) + (dist.bad ?? 0) + (dist.stale ?? 0) + (dist.error ?? 0)

  return {
    good: { count: good, pct: Math.round((good / total) * 100) },
    fair: { count: fair, pct: Math.round((fair / total) * 100) },
    bad: { count: bad, pct: Math.round((bad / total) * 100) },
    total,
  }
})

function fmt(value: number | null): string {
  return formatNumber(value, decimals.value, '\u2014')
}
</script>

<template>
  <div class="statistics-widget">
    <!-- No sensor configured -->
    <div v-if="!sensorId" class="statistics-widget__empty">
      <BarChart3 :size="24" />
      <span>Sensor auswählen{{ props.title ? ` für ${props.title}` : '' }}</span>
    </div>

    <!-- Loading -->
    <div v-else-if="isLoading && !stats" class="statistics-widget__loading">
      <Loader2 :size="24" class="statistics-widget__spinner" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="statistics-widget__error">
      <AlertTriangle :size="20" />
      <span>{{ error }}</span>
    </div>

    <!-- Stats content -->
    <template v-else-if="stats">
      <!-- Header -->
      <div class="statistics-widget__header">
        <span class="statistics-widget__title">
          {{ title || sensorLabel }}
          <span
            v-if="isSnapshot"
            class="statistics-widget__snapshot-badge"
            title="Snapshot-Sensor (Punktmessungen)"
          >Snapshot</span>
        </span>
        <span class="statistics-widget__range">{{ TIME_RANGE_LABELS[timeRange] ?? timeRange }}</span>
      </div>

      <!-- KPI Grid -->
      <div
        class="statistics-widget__grid"
        :style="{ gridTemplateColumns: `repeat(${kpiItems.length}, 1fr)` }"
      >
        <div
          v-for="kpi in kpiItems"
          :key="kpi.label"
          class="statistics-widget__kpi"
        >
          <span class="statistics-widget__kpi-value">{{ fmt(kpi.value) }}</span>
          <span class="statistics-widget__kpi-unit">{{ unit }}</span>
          <span class="statistics-widget__kpi-label">{{ kpi.label }}</span>
        </div>
      </div>

      <!-- Footer: Count + Threshold-Hinweis -->
      <div class="statistics-widget__footer">
        <span class="statistics-widget__count">
          {{ formatNumber(stats.reading_count, 0) }} Messwerte
        </span>
        <span
          v-if="effectiveThresholds"
          class="statistics-widget__thresholds"
          :title="`Schwellen: warn ${effectiveThresholds.warning_min ?? '—'}/${effectiveThresholds.warning_max ?? '—'}, crit ${effectiveThresholds.critical_min ?? '—'}/${effectiveThresholds.critical_max ?? '—'}`"
        >
          Schwellen aktiv
        </span>
      </div>

      <!-- Quality distribution (optional) -->
      <div v-if="qualityGroups" class="statistics-widget__quality">
        <div class="statistics-widget__quality-bar">
          <div
            v-if="qualityGroups.good.pct > 0"
            class="statistics-widget__quality-seg statistics-widget__quality-seg--good"
            :style="{ width: qualityGroups.good.pct + '%' }"
          />
          <div
            v-if="qualityGroups.fair.pct > 0"
            class="statistics-widget__quality-seg statistics-widget__quality-seg--fair"
            :style="{ width: qualityGroups.fair.pct + '%' }"
          />
          <div
            v-if="qualityGroups.bad.pct > 0"
            class="statistics-widget__quality-seg statistics-widget__quality-seg--bad"
            :style="{ width: qualityGroups.bad.pct + '%' }"
          />
        </div>
        <span class="statistics-widget__quality-label">
          {{ qualityGroups.good.pct }}% gut
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.statistics-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--space-3);
  gap: var(--space-2);
}

.statistics-widget__empty,
.statistics-widget__loading,
.statistics-widget__error {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.statistics-widget__error {
  color: var(--color-error);
}

.statistics-widget__spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.statistics-widget__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}

.statistics-widget__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.statistics-widget__range {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.statistics-widget__grid {
  display: grid;
  gap: var(--space-2);
  flex: 1;
  align-content: center;
}

.statistics-widget__kpi {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.statistics-widget__kpi-value {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.statistics-widget__kpi-unit {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.statistics-widget__kpi-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.statistics-widget__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.statistics-widget__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.statistics-widget__thresholds {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

.statistics-widget__snapshot-badge {
  display: inline-block;
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 0 var(--space-1);
  margin-left: var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  letter-spacing: 0.02em;
  vertical-align: middle;
}

.statistics-widget__quality {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.statistics-widget__quality-bar {
  display: flex;
  height: 6px;
  border-radius: var(--radius-xs);
  overflow: hidden;
  background: var(--color-bg-tertiary);
}

.statistics-widget__quality-seg {
  height: 100%;
  transition: width 0.3s ease;
}

.statistics-widget__quality-seg--good {
  background: var(--color-success);
}

.statistics-widget__quality-seg--fair {
  background: var(--color-warning);
}

.statistics-widget__quality-seg--bad {
  background: var(--color-error);
}

.statistics-widget__quality-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
