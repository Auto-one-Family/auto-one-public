<script setup lang="ts">
/**
 * SensorTile — Unified sensor widget (AUT-247)
 *
 * Replaces the four redundant sensor widgets (SensorCardWidget, GaugeWidget,
 * LineChartWidget, HistoricalChartWidget) with a single component plus an
 * internal display-mode toggle. The legacy widgets are kept as thin wrappers
 * so existing dashboard JSONs continue to render unchanged.
 *
 * Modes:
 *   - numeric:    current value + trend icon + quality dot (former SensorCardWidget)
 *   - gauge:      GaugeChart with color zones (former GaugeWidget)
 *   - sparkline:  60-point live buffer LiveLineChart (former LineChartWidget)
 *   - historic:   1h..30d historical chart (former HistoricalChartWidget)
 *
 * Multi-Value Sensors (SHT31, BME280):
 *   When the selected sensor belongs to a multi-value device, a sub-value
 *   picker (Tabs) lets the user switch between sibling sensor_types on the
 *   same ESP+GPIO pair (e.g. sht31_temp <-> sht31_humidity). Each switch
 *   re-emits `update:config` with a new sensorId so the WS subscription path
 *   (subscribe(esp_id, gpio, sensor_type)) stays unchanged.
 *
 * Mock Indicator (AUT-31): a small "MOCK" badge is shown when the underlying
 * ESP device is a mock device (espStore.isMock).
 */
import { ref, computed, watch } from 'vue'
import { Activity, TrendingUp, TrendingDown, Minus, Hash, Gauge as GaugeIcon, Activity as SparkIcon, BarChart3 } from 'lucide-vue-next'
import type { Component } from 'vue'

import { useEspStore } from '@/stores/esp'
import { useSensorId } from '@/composables/useSensorId'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { useSparklineCache } from '@/composables/useSparklineCache'
import { calculateTrend } from '@/utils/trendUtils'
import type { TrendDirection } from '@/utils/trendUtils'
import {
  SENSOR_TYPE_CONFIG,
  getSensorUnit,
  getMultiValueDeviceConfigBySensorType,
} from '@/utils/sensorDefaults'
import { tokens } from '@/utils/cssTokens'
import type { MockSensor } from '@/types'

import GaugeChart from '@/components/charts/GaugeChart.vue'
import type { GaugeThreshold } from '@/components/charts/types'
import LiveLineChart from '@/components/charts/LiveLineChart.vue'
import type { ChartDataPoint, ThresholdConfig } from '@/components/charts/LiveLineChart.vue'
import HistoricalChart from '@/components/charts/HistoricalChart.vue'

// ─── Props / Emits ──────────────────────────────────────────────────────────

export type SensorTileDisplayMode = 'numeric' | 'gauge' | 'sparkline' | 'historic'

interface SensorTileProps {
  /** "espId:gpio:sensorType" — same format used by all sensor widgets */
  sensorId?: string
  /** config_id for precise sensor matching (AUT-845) */
  configId?: string
  /** Zone scope for sensor picker (PA-02c) */
  zoneId?: string
  /** Title override (otherwise derived from sensor name) */
  title?: string

  /** Initial display mode. Default: 'numeric' */
  displayMode?: SensorTileDisplayMode
  /** Hide the internal mode-toggle pill bar (used by legacy wrappers) */
  hideModeToggle?: boolean

  // numeric mode
  showTrendIcon?: boolean
  showQualityDot?: boolean

  // gauge mode
  yMin?: number
  yMax?: number
  warnLow?: number
  warnHigh?: number
  alarmLow?: number
  alarmHigh?: number
  showThresholds?: boolean

  // sparkline mode
  liveBufferSize?: number

  // historic mode
  timeRange?: '1h' | '6h' | '24h' | '7d' | '30d'

  // shared
  unit?: string
  color?: string
}

const props = withDefaults(defineProps<SensorTileProps>(), {
  displayMode: 'numeric',
  hideModeToggle: false,
  showTrendIcon: true,
  showQualityDot: true,
  liveBufferSize: 60,
  timeRange: '1h',
  showThresholds: false,
})

const emit = defineEmits<{
  'update:config': [config: { sensorId?: string; displayMode?: SensorTileDisplayMode; timeRange?: string }]
}>()

// ─── Local state (survives render() one-shot props, see Bug 1b fix) ─────────

const localSensorId = ref(props.sensorId || '')
const localZoneId = ref<string | undefined>(props.zoneId)
const currentMode = ref<SensorTileDisplayMode>(props.displayMode)

watch(() => props.sensorId, (v) => { if (v) localSensorId.value = v })
watch(() => props.zoneId, (v) => { localZoneId.value = v })
watch(() => props.displayMode, (v) => { currentMode.value = v })

// ─── Stores / composables ───────────────────────────────────────────────────

const espStore = useEspStore()
const { sparklineCache, getSensorKey } = useSparklineCache(30)
const { espId: parsedEspId, gpio: parsedGpio, sensorType: parsedSensorType, isValid: sensorIdValid } = useSensorId(localSensorId)
const { flatSensorOptions: availableSensors } = useSensorOptions(localZoneId)

// ─── Sensor lookup ──────────────────────────────────────────────────────────

const currentDevice = computed(() => {
  if (!sensorIdValid.value) return null
  return espStore.devices.find(d => espStore.getDeviceId(d) === parsedEspId.value) ?? null
})

const currentSensor = computed<MockSensor | null>(() => {
  if (!currentDevice.value) return null
  return ((currentDevice.value.sensors as MockSensor[]) || []).find(s =>
    (props.configId != null && s.config_id === props.configId) ||
    (s.gpio === parsedGpio.value && (!parsedSensorType.value || s.sensor_type === parsedSensorType.value))
  ) ?? null
})

const isMockDevice = computed(() => {
  if (!parsedEspId.value) return false
  return espStore.isMock(parsedEspId.value)
})

// ─── Multi-Value sub-value picker ───────────────────────────────────────────

interface SubValueOption {
  sensorType: string
  label: string
  sensorId: string  // full "espId:gpio:sensorType"
}

/**
 * Sibling sensor_types on the same espId+gpio that belong to the same
 * multi-value device (e.g. sht31_temp + sht31_humidity).
 */
const subValueOptions = computed<SubValueOption[]>(() => {
  const sensor = currentSensor.value
  const device = currentDevice.value
  if (!sensor || !device || !parsedEspId.value || parsedGpio.value == null) return []

  const mvDevice = getMultiValueDeviceConfigBySensorType(sensor.sensor_type)
  if (!mvDevice) return []

  const siblingsOnSameGpio = ((device.sensors as MockSensor[]) || []).filter(s => s.gpio === parsedGpio.value)
  const result: SubValueOption[] = []
  for (const v of mvDevice.values) {
    const match = siblingsOnSameGpio.find(s => s.sensor_type === v.sensorType)
    if (match) {
      result.push({
        sensorType: v.sensorType,
        label: v.label,
        sensorId: `${parsedEspId.value}:${parsedGpio.value}:${v.sensorType}`,
      })
    }
  }
  return result
})

const hasSubValues = computed(() => subValueOptions.value.length > 1)

function selectSubValue(option: SubValueOption): void {
  if (option.sensorId === localSensorId.value) return
  localSensorId.value = option.sensorId
  liveBuffer.value = []  // reset live buffer on sub-value switch
  emit('update:config', { sensorId: option.sensorId })
}

// ─── Sensor properties ──────────────────────────────────────────────────────

const sensorType = computed(() => parsedSensorType.value || currentSensor.value?.sensor_type || null)

const decimals = computed(() => SENSOR_TYPE_CONFIG[sensorType.value ?? '']?.decimals ?? 1)

const displayUnit = computed(() => {
  if (props.unit) return props.unit
  const t = sensorType.value
  if (!t) return currentSensor.value?.unit || ''
  const resolved = getSensorUnit(t)
  return resolved !== 'raw' ? resolved : (currentSensor.value?.unit || '')
})

const sensorTypeDefaults = computed(() => sensorType.value ? (SENSOR_TYPE_CONFIG[sensorType.value] ?? null) : null)

const effectiveMin = computed(() => props.yMin ?? sensorTypeDefaults.value?.min ?? 0)
const effectiveMax = computed(() => props.yMax ?? sensorTypeDefaults.value?.max ?? 100)

// Snapshot sensor (Wave 1, MultispeQ) — suppress live indicators, scatter mode for historic.
const isSnapshot = computed(() => currentSensor.value?.sensor_kind === 'snapshot')

// ─── Quality dot ────────────────────────────────────────────────────────────

const qualityClass = computed(() => {
  const q = currentSensor.value?.quality
  if (q === 'good' || q === 'excellent') return 'sensor-tile__dot--good'
  if (q === 'fair') return 'sensor-tile__dot--warning'
  if (q === 'poor' || q === 'bad' || q === 'error') return 'sensor-tile__dot--alarm'
  return 'sensor-tile__dot--offline'
})

// ─── Trend (numeric mode) ───────────────────────────────────────────────────

const trend = computed<TrendDirection | undefined>(() => {
  const sensor = currentSensor.value
  if (!sensor || !sensorIdValid.value) return undefined
  const t = sensorType.value
  const key = getSensorKey(parsedEspId.value!, parsedGpio.value!, t ?? undefined)
  const points = sparklineCache.value.get(key)
  if (!points || points.length < 5) return undefined
  return calculateTrend(points, t || undefined).direction
})

const TREND_ICONS: Record<TrendDirection, Component> = {
  rising: TrendingUp,
  stable: Minus,
  falling: TrendingDown,
}
const TREND_TITLES: Record<TrendDirection, string> = {
  rising: 'Steigend',
  stable: 'Stabil',
  falling: 'Fallend',
}

// ─── Sparkline live buffer (sparkline mode) ─────────────────────────────────

const liveBuffer = ref<ChartDataPoint[]>([])

watch(
  () => currentSensor.value?.last_read,
  () => {
    if (currentMode.value !== 'sparkline') return
    const sensor = currentSensor.value
    if (!sensor || sensor.raw_value == null) return
    const point: ChartDataPoint = { timestamp: new Date(), value: sensor.raw_value }
    const buf = [...liveBuffer.value, point]
    const max = props.liveBufferSize ?? 60
    if (buf.length > max) buf.shift()
    liveBuffer.value = buf
  },
)

const sparkThresholds = computed<ThresholdConfig | undefined>(() => {
  if (!props.showThresholds) return undefined
  const t: ThresholdConfig = {}
  if (props.warnLow != null) t.warnLow = props.warnLow
  if (props.warnHigh != null) t.warnHigh = props.warnHigh
  if (props.alarmLow != null) t.alarmLow = props.alarmLow
  if (props.alarmHigh != null) t.alarmHigh = props.alarmHigh
  return Object.keys(t).length > 0 ? t : undefined
})

// ─── Gauge thresholds (gauge mode) ──────────────────────────────────────────

/**
 * Build GaugeThreshold[] from props in the same way GaugeWidget did.
 * Pattern: alarmLow < warnLow < warnHigh < alarmHigh.
 */
const gaugeThresholds = computed<GaugeThreshold[]>(() => {
  const hasAny = props.warnLow != null || props.warnHigh != null
    || props.alarmLow != null || props.alarmHigh != null

  if (!hasAny) {
    return [{ value: effectiveMin.value, color: tokens.statusGood }]
  }

  const thresholds: GaugeThreshold[] = []
  const min = effectiveMin.value
  const aLow = props.alarmLow ?? min
  const wLow = props.warnLow ?? aLow
  const wHigh = props.warnHigh ?? effectiveMax.value
  const aHigh = props.alarmHigh ?? effectiveMax.value

  if (aLow > min) thresholds.push({ value: min, color: tokens.statusAlarm })
  if (wLow > aLow) thresholds.push({ value: aLow, color: tokens.statusWarning })
  thresholds.push({ value: wLow, color: tokens.statusGood })
  if (aHigh > wHigh) {
    thresholds.push({ value: wHigh, color: tokens.statusWarning })
  } else {
    thresholds.push({ value: wHigh, color: tokens.statusAlarm })
  }
  if (aHigh < effectiveMax.value && aHigh > wHigh) {
    thresholds.push({ value: aHigh, color: tokens.statusAlarm })
  }
  return thresholds
})

// ─── Mode handling ──────────────────────────────────────────────────────────

interface ModeOption {
  mode: SensorTileDisplayMode
  label: string
  icon: Component
  title: string
}

const MODE_OPTIONS: ModeOption[] = [
  { mode: 'numeric', label: 'Zahl', icon: Hash, title: 'Aktueller Wert' },
  { mode: 'gauge', label: 'Gauge', icon: GaugeIcon, title: 'Gauge-Anzeige' },
  { mode: 'sparkline', label: 'Live', icon: SparkIcon, title: 'Live-Sparkline' },
  { mode: 'historic', label: 'Verlauf', icon: BarChart3, title: 'Historischer Verlauf' },
]

function setMode(mode: SensorTileDisplayMode): void {
  if (mode === currentMode.value) return
  currentMode.value = mode
  emit('update:config', { displayMode: mode })
}

function setTimeRange(range: SensorTileProps['timeRange']): void {
  if (!range) return
  emit('update:config', { timeRange: range })
}

// ─── Sensor selection (empty state) ─────────────────────────────────────────

function selectSensor(sensorId: string): void {
  localSensorId.value = sensorId
  liveBuffer.value = []
  emit('update:config', { sensorId })
}

// ─── Display name ───────────────────────────────────────────────────────────

const displayName = computed(() => {
  if (props.title) return props.title
  const sensor = currentSensor.value
  if (!sensor) return ''
  return sensor.name || sensor.sensor_type || ''
})

const HISTORIC_RANGES: Array<NonNullable<SensorTileProps['timeRange']>> = ['1h', '6h', '24h', '7d', '30d']
</script>

<template>
  <div class="sensor-tile">
    <!-- ── Empty state: sensor picker ───────────────────────────────────── -->
    <div v-if="!localSensorId || !currentSensor" class="sensor-tile__empty">
      <Activity class="sensor-tile__empty-icon" />
      <p class="sensor-tile__empty-hint">Wähle einen Sensor — das Widget zeigt den Live-Wert an.</p>
      <select
        class="sensor-tile__select"
        :value="localSensorId"
        @change="selectSensor(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>Sensor auswählen</option>
        <option v-for="s in availableSensors" :key="s.id" :value="s.id">{{ s.label }}</option>
      </select>
    </div>

    <!-- ── Active sensor: header + body ─────────────────────────────────── -->
    <template v-else>
      <!-- Header: name + mock badge + sub-value tabs + quality dot -->
      <div class="sensor-tile__header">
        <span class="sensor-tile__name" :title="displayName">{{ displayName }}</span>
        <span class="sensor-tile__header-right">
          <span
            v-if="isMockDevice"
            class="sensor-tile__mock-badge"
            title="Mock-Sensor (simuliertes Gerät, AUT-31)"
          >MOCK</span>
          <span
            v-if="isSnapshot"
            class="sensor-tile__snapshot-badge"
            title="Snapshot-Sensor (Punktmessung, kein Live-Stream)"
          >Snapshot</span>
          <component
            v-if="currentMode === 'numeric' && props.showTrendIcon && trend && !isSnapshot"
            :is="TREND_ICONS[trend]"
            class="sensor-tile__trend"
            :class="`sensor-tile__trend--${trend}`"
            :title="TREND_TITLES[trend]"
          />
          <span
            v-if="props.showQualityDot"
            :class="['sensor-tile__dot', qualityClass]"
            aria-label="Sensor-Qualität"
          />
        </span>
      </div>

      <!-- Sub-Value Picker (multi-value sensors only) -->
      <div v-if="hasSubValues" class="sensor-tile__subvalues" role="tablist" aria-label="Messwert auswählen">
        <button
          v-for="opt in subValueOptions"
          :key="opt.sensorType"
          type="button"
          role="tab"
          :class="['sensor-tile__subvalue', { 'sensor-tile__subvalue--active': sensorType === opt.sensorType }]"
          :aria-selected="sensorType === opt.sensorType"
          :title="opt.label"
          @click="selectSubValue(opt)"
        >{{ opt.label }}</button>
      </div>

      <!-- Mode toggle pill bar -->
      <div v-if="!props.hideModeToggle" class="sensor-tile__modes" role="tablist" aria-label="Anzeigeart">
        <button
          v-for="opt in MODE_OPTIONS"
          :key="opt.mode"
          type="button"
          role="tab"
          :class="['sensor-tile__mode', { 'sensor-tile__mode--active': currentMode === opt.mode }]"
          :aria-selected="currentMode === opt.mode"
          :title="opt.title"
          @click="setMode(opt.mode)"
        >
          <component :is="opt.icon" :size="12" aria-hidden="true" />
          <span class="sensor-tile__mode-label">{{ opt.label }}</span>
        </button>
      </div>

      <!-- Body: one of four visualizations -->
      <div class="sensor-tile__body" :data-mode="currentMode">
        <!-- numeric -->
        <div v-if="currentMode === 'numeric'" class="sensor-tile__numeric">
          <span class="sensor-tile__number">{{ (currentSensor.raw_value ?? 0).toFixed(decimals) }}</span>
          <span class="sensor-tile__unit">{{ displayUnit }}</span>
        </div>

        <!-- gauge -->
        <div v-else-if="currentMode === 'gauge'" class="sensor-tile__gauge">
          <GaugeChart
            :value="currentSensor.raw_value ?? 0"
            :unit="displayUnit"
            :min="effectiveMin"
            :max="effectiveMax"
            :thresholds="gaugeThresholds"
            size="md"
          />
        </div>

        <!-- sparkline (live) -->
        <div v-else-if="currentMode === 'sparkline'" class="sensor-tile__sparkline">
          <LiveLineChart
            :data="liveBuffer"
            height="100%"
            :unit="displayUnit"
            :sensor-type="currentSensor.sensor_type"
            :fill="true"
            :color="props.color"
            :y-min="props.yMin"
            :y-max="props.yMax"
            :show-thresholds="props.showThresholds"
            :thresholds="sparkThresholds"
          />
        </div>

        <!-- historic -->
        <div v-else-if="currentMode === 'historic'" class="sensor-tile__historic">
          <div class="sensor-tile__historic-ranges">
            <button
              v-for="r in HISTORIC_RANGES"
              :key="r"
              type="button"
              :class="['sensor-tile__range', { 'sensor-tile__range--active': props.timeRange === r }]"
              @click="setTimeRange(r)"
            >{{ r }}</button>
          </div>
          <div class="sensor-tile__historic-chart">
            <HistoricalChart
              :esp-id="parsedEspId!"
              :gpio="parsedGpio!"
              :sensor-type="currentSensor.sensor_type"
              :time-range="props.timeRange ?? '1h'"
              :unit="displayUnit"
              :show-thresholds="props.showThresholds"
              :scatter-mode="isSnapshot"
              height="100%"
            />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sensor-tile {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2);
  min-height: 0;
}

/* ── Header ──────────────────────────────────────────────────────────────── */
.sensor-tile__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-shrink: 0;
}

.sensor-tile__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-tile__header-right {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.sensor-tile__mock-badge {
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--color-mock-bg);
  color: var(--color-mock);
  letter-spacing: 0.04em;
}

.sensor-tile__snapshot-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  letter-spacing: 0.02em;
}

.sensor-tile__trend {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--color-text-muted);
}
.sensor-tile__trend--rising { color: var(--color-success); }
.sensor-tile__trend--falling { color: var(--color-warning); }
.sensor-tile__trend--stable { color: var(--color-text-muted); }

.sensor-tile__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sensor-tile__dot--good { background: var(--color-status-good); }
.sensor-tile__dot--warning { background: var(--color-status-warning); }
.sensor-tile__dot--alarm { background: var(--color-status-alarm); }
.sensor-tile__dot--offline { background: var(--color-status-offline); }

/* ── Sub-value picker (multi-value) ──────────────────────────────────────── */
.sensor-tile__subvalues {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.sensor-tile__subvalue {
  flex: 1;
  padding: 2px var(--space-1);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  min-height: 24px;
  transition: all var(--transition-fast);
}

.sensor-tile__subvalue:hover {
  color: var(--color-text-primary);
  border-color: var(--color-accent);
}

.sensor-tile__subvalue--active {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
  font-weight: 600;
}

/* ── Mode toggle pill bar ────────────────────────────────────────────────── */
.sensor-tile__modes {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.sensor-tile__mode {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex: 1;
  padding: 2px var(--space-1);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  min-height: 24px;
  transition: all var(--transition-fast);
}

.sensor-tile__mode:hover {
  color: var(--color-text-primary);
  border-color: var(--color-accent);
}

.sensor-tile__mode--active {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
  font-weight: 600;
}

.sensor-tile__mode-label {
  display: none;
}

/* Show labels when there's room (>= 220px tile width) */
@container (min-width: 220px) {
  .sensor-tile__mode-label {
    display: inline;
  }
}

/* ── Body wrappers ───────────────────────────────────────────────────────── */
.sensor-tile__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sensor-tile__numeric {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--space-1);
}

.sensor-tile__number {
  font-family: var(--font-mono);
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1;
}

.sensor-tile__unit {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.sensor-tile__gauge,
.sensor-tile__sparkline {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sensor-tile__historic {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sensor-tile__historic-ranges {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.sensor-tile__range {
  padding: 2px var(--space-1);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  min-height: 22px;
}

.sensor-tile__range--active {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
  font-weight: 600;
}

.sensor-tile__historic-chart {
  flex: 1;
  min-height: 0;
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
.sensor-tile__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-muted);
}

.sensor-tile__empty-icon {
  width: 24px;
  height: 24px;
  opacity: 0.3;
}

.sensor-tile__empty-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: center;
  margin: 0;
  padding: 0 var(--space-2);
}

.sensor-tile__select {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-xs);
  max-width: 200px;
}
</style>
