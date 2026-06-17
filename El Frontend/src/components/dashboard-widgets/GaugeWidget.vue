<script setup lang="ts">
/**
 * GaugeWidget — Gauge widget for dashboard
 *
 * AUT-247: Thin wrapper around SensorTile (displayMode='gauge') for the
 * regular sensor case. The zone_avg / tile-spot / tile-zone-avg paths
 * (Monitor L1 zone-tile compact panel) keep their dedicated rendering
 * because they aggregate across multiple sensors of a zone, which is a
 * different data model than SensorTile's single-sensor contract.
 *
 * Existing dashboard JSONs continue to load unchanged.
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useEspStore } from '@/stores/esp'
import GaugeChart from '@/components/charts/GaugeChart.vue'
import SensorTile from './SensorTile.vue'
import {
  SENSOR_TYPE_CONFIG,
  getSensorUnit,
  aggregateZoneSensors,
  getAggCategoryGaugeRange,
  getSensorAggCategory,
  type AggCategory,
} from '@/utils/sensorDefaults'
import { tokens } from '@/utils/cssTokens'
import type { GaugeThreshold } from '@/components/charts/types'
import { useSensorId } from '@/composables/useSensorId'
import { useZoneDragDrop } from '@/composables/useZoneDragDrop'

/** Monitor L1 zone-tile: gauge = spot sensor vs Ø row above */
const GAUGE_TILE_SPOT_TOOLTIP =
  'Messwert eines Sensors in dieser Zone (Auswahl nach Priorität). Das Zonenmittel (Ø) steht in der KPI-Zeile darüber.'

const GAUGE_TILE_SPOT_ARIA =
  'Repräsentativ: ein Sensor in der Zone. Zonenmittel siehe KPI-Zeile oben.'

const GAUGE_TILE_ZONE_AVG_TOOLTIP =
  'Zonenmittel (Ø) aus derselben Aggregation wie die KPI-Zeile oben (Kategorie gemittelt, veraltete Werte ausgeschlossen).'

const GAUGE_TILE_ZONE_AVG_ARIA =
  'Zonenmittel wie KPI-Zeile oben, gleiche Berechnung pro Kategorie.'

interface Props {
  sensorId?: string
  zoneId?: string
  /** `zone_avg`: Wert aus aggregateZoneSensors(); `sensor`: einzelner Sensor */
  valueSource?: 'sensor' | 'zone_avg'
  /** Kategorie für valueSource === 'zone_avg' */
  aggCategory?: AggCategory
  /** When true (compact zone-tile panel), show Repräsentativ label + tooltip */
  tileSpotSemantics?: boolean
  /** Compact zone-tile: Gauge zeigt Zonenmittel wie KPI-Zeile */
  tileZoneAvgSemantics?: boolean
  title?: string
  yMin?: number
  yMax?: number
  warnLow?: number
  warnHigh?: number
  alarmLow?: number
  alarmHigh?: number
  showThresholds?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  tileSpotSemantics: false,
  tileZoneAvgSemantics: false,
  valueSource: 'sensor',
})
const emit = defineEmits<{
  'update:config': [config: { sensorId: string }]
}>()

const espStore = useEspStore()
const { groupDevicesByZone } = useZoneDragDrop()

// ── Zone-AVG path detection ─────────────────────────────────────────────────

const isZoneTileMode = computed(() => props.tileSpotSemantics || props.tileZoneAvgSemantics)
const isZoneAvgPath = computed(() => props.valueSource === 'zone_avg' && !!props.zoneId)

// ── Sensor parsing (used both for zone_avg category resolution and SensorTile delegation)

const localSensorId = ref(props.sensorId || '')
watch(() => props.sensorId, (v) => { if (v) localSensorId.value = v })
const { sensorType: parsedSensorType } = useSensorId(localSensorId)

// ── Zone aggregation (for zone_avg + tile-zone-avg) ─────────────────────────

const zoneGroupDevices = computed(() => {
  if (!props.zoneId) return []
  const groups = groupDevicesByZone(espStore.devices as any[])
  const g = groups.find(x => x.zoneId === props.zoneId)
  return g?.devices ?? []
})

const zoneAggregation = computed(() => aggregateZoneSensors(zoneGroupDevices.value))

const resolvedAggCategory = computed<AggCategory | null>(() => {
  if (props.aggCategory) return props.aggCategory
  if (isZoneAvgPath.value && parsedSensorType.value) {
    const c = getSensorAggCategory(parsedSensorType.value)
    return c === 'other' ? null : c
  }
  return null
})

const effectiveZoneAvgRow = computed(() => {
  if (!isZoneAvgPath.value) return null
  const cat = resolvedAggCategory.value
  if (!cat) return null
  return zoneAggregation.value.sensorTypes.find(st => st.type === cat) ?? null
})

const useZoneAvgChannel = computed(
  () => isZoneAvgPath.value && !!effectiveZoneAvgRow.value && effectiveZoneAvgRow.value.count > 0,
)

// ── Display unit / range / thresholds for zone-avg path ─────────────────────

const sensorTypeDefaults = computed(() => {
  if (!parsedSensorType.value) return null
  return SENSOR_TYPE_CONFIG[parsedSensorType.value] ?? null
})

const aggGaugeRange = computed(() => {
  const cat = resolvedAggCategory.value
  if (!cat) return null
  return getAggCategoryGaugeRange(cat)
})

const effectiveMin = computed(() => {
  if (props.yMin != null) return props.yMin
  if (useZoneAvgChannel.value && aggGaugeRange.value) return aggGaugeRange.value.min
  return sensorTypeDefaults.value?.min ?? 0
})
const effectiveMax = computed(() => {
  if (props.yMax != null) return props.yMax
  if (useZoneAvgChannel.value && aggGaugeRange.value) return aggGaugeRange.value.max
  return sensorTypeDefaults.value?.max ?? 100
})

const displayUnit = computed(() => {
  if (useZoneAvgChannel.value && effectiveZoneAvgRow.value) {
    return effectiveZoneAvgRow.value.unit
  }
  const t = parsedSensorType.value
  if (!t) return ''
  const resolved = getSensorUnit(t)
  return resolved !== 'raw' ? resolved : ''
})

const gaugeChartValue = computed(() => {
  if (useZoneAvgChannel.value && effectiveZoneAvgRow.value) {
    return effectiveZoneAvgRow.value.avg
  }
  return 0
})

const gaugeThresholds = computed<GaugeThreshold[]>(() => {
  const hasThresholds = props.warnLow != null || props.warnHigh != null
    || props.alarmLow != null || props.alarmHigh != null

  if (!hasThresholds) {
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

// ── Adaptive gauge size (only used for zone-avg path) ──────────────────────

const widgetEl = ref<HTMLElement | null>(null)
const gaugeSize = ref<'sm' | 'md'>('md')
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (widgetEl.value && useZoneAvgChannel.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        gaugeSize.value = entry.contentRect.height < 90 ? 'sm' : 'md'
      }
    })
    resizeObserver.observe(widgetEl.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

function onTileUpdate(cfg: { sensorId?: string }) {
  if (cfg.sensorId) emit('update:config', { sensorId: cfg.sensorId })
}
</script>

<template>
  <!-- Zone-AVG path (Monitor L1 zone-tile, aggregated value): keep dedicated rendering -->
  <div
    v-if="isZoneTileMode || useZoneAvgChannel"
    ref="widgetEl"
    class="gauge-widget"
    :class="{
      'gauge-widget--tile-spot': props.tileSpotSemantics,
      'gauge-widget--tile-zone-avg': props.tileZoneAvgSemantics,
    }"
    :title="props.tileSpotSemantics ? GAUGE_TILE_SPOT_TOOLTIP : (props.tileZoneAvgSemantics ? GAUGE_TILE_ZONE_AVG_TOOLTIP : undefined)"
    :role="isZoneTileMode ? 'group' : undefined"
    :aria-label="props.tileSpotSemantics ? GAUGE_TILE_SPOT_ARIA : (props.tileZoneAvgSemantics ? GAUGE_TILE_ZONE_AVG_ARIA : undefined)"
  >
    <span
      v-if="props.tileSpotSemantics"
      class="gauge-widget__spot-label"
      :title="GAUGE_TILE_SPOT_TOOLTIP"
      aria-hidden="true"
    >Repräsentativ</span>
    <span
      v-if="props.tileZoneAvgSemantics"
      class="gauge-widget__zone-avg-label"
      :title="GAUGE_TILE_ZONE_AVG_TOOLTIP"
      aria-hidden="true"
    >Zonenmittel</span>
    <div v-if="useZoneAvgChannel" class="gauge-widget__chart">
      <GaugeChart
        :value="gaugeChartValue"
        :unit="displayUnit"
        :min="effectiveMin"
        :max="effectiveMax"
        :thresholds="gaugeThresholds"
        :size="gaugeSize"
      />
    </div>
    <div
      v-else-if="isZoneAvgPath"
      class="gauge-widget__empty gauge-widget__empty--zone-avg"
    >
      <p>Keine Sensordaten</p>
    </div>
    <!-- Tile-spot fallback: delegate to SensorTile -->
    <SensorTile
      v-else
      :sensor-id="props.sensorId"
      :zone-id="props.zoneId"
      :title="props.title"
      display-mode="gauge"
      hide-mode-toggle
      :y-min="props.yMin"
      :y-max="props.yMax"
      :warn-low="props.warnLow"
      :warn-high="props.warnHigh"
      :alarm-low="props.alarmLow"
      :alarm-high="props.alarmHigh"
      :show-thresholds="props.showThresholds"
      @update:config="onTileUpdate"
    />
  </div>

  <!-- Standard single-sensor path: delegate fully to SensorTile -->
  <SensorTile
    v-else
    :sensor-id="props.sensorId"
    :zone-id="props.zoneId"
    :title="props.title"
    display-mode="gauge"
    hide-mode-toggle
    :y-min="props.yMin"
    :y-max="props.yMax"
    :warn-low="props.warnLow"
    :warn-high="props.warnHigh"
    :alarm-low="props.alarmLow"
    :alarm-high="props.alarmHigh"
    :show-thresholds="props.showThresholds"
    @update:config="onTileUpdate"
  />
</template>

<style scoped>
.gauge-widget {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-widget--tile-spot,
.gauge-widget--tile-zone-avg {
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  min-height: 0;
}

.gauge-widget__spot-label,
.gauge-widget__zone-avg-label {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  line-height: 1.1;
  margin-bottom: var(--space-1);
}

.gauge-widget__zone-avg-label {
  color: var(--color-text-secondary);
}

.gauge-widget__chart {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
