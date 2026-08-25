<script setup lang="ts">
/**
 * ZoneTileGaugeCluster — compact multi-gauge row for the Monitor L1 zone-tile.
 *
 * Renders the representative spot values of a sensor as equally-sized gauges
 * placed side by side (e.g. SHT31 → Temperatur + Luftfeuchte). For single-value
 * sensors it renders one gauge. There is intentionally NO sub-value toggle:
 *  - the zone-tile preview is read-only, and
 *  - a toggle button inside the clickable <button> tile bubbled its click up to
 *    the tile navigation (AUT zone-tile UX fix).
 *
 * Equal sizing: each gauge item is `flex: 1` within the cluster, and the parent
 * InlineDashboardPanel weights each widget cell by its gauge count, so every
 * gauge ends up with the same width — and thus the same arc size.
 */
import { computed } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useSensorId } from '@/composables/useSensorId'
import { useSensorThresholds } from '@/composables/useSensorThresholds'
import {
  getSensorConfig,
  getSensorUnit,
  getMultiValueDeviceConfigBySensorType,
} from '@/utils/sensorDefaults'
import { tokens } from '@/utils/cssTokens'
import GaugeChart from '@/components/charts/GaugeChart.vue'
import type { GaugeThreshold } from '@/components/charts/types'
import type { MockSensor } from '@/types'

interface Props {
  sensorId?: string
  zoneId?: string
  title?: string
  yMin?: number
  yMax?: number
  warnLow?: number
  warnHigh?: number
  alarmLow?: number
  alarmHigh?: number
  showThresholds?: boolean
}
const props = defineProps<Props>()

const espStore = useEspStore()

const sensorIdRef = computed(() => props.sensorId ?? '')
const { espId, gpio, sensorType: primaryType, isValid } = useSensorId(sensorIdRef)

const device = computed(() => {
  if (!isValid.value) return null
  return espStore.devices.find(d => espStore.getDeviceId(d) === espId.value) ?? null
})

// E2 priority chain: widget-override > configured sensor bounds > sensor-type fallback
// For the cluster we track the primary sensor's config_id to avoid one fetch per item.
const primaryConfigId = computed<string | null>(() => {
  const dev = device.value
  const pType = primaryType.value
  if (!dev || !pType || gpio.value == null) return null
  const sensors = (dev.sensors as MockSensor[]) || []
  return sensors.find(s => s.gpio === gpio.value && s.sensor_type === pType)?.config_id ?? null
})
const {
  configuredMin,
  configuredMax,
  configuredWarnLow,
  configuredWarnHigh,
  configuredAlarmLow,
  configuredAlarmHigh,
} = useSensorThresholds(primaryConfigId)

interface GaugeItem {
  sensorType: string
  label: string
  value: number
  unit: string
  min: number
  max: number
  decimals: number
  thresholds: GaugeThreshold[]
}

/**
 * Threshold ramp identical to SensorTile's gauge mode (alarmLow < warnLow <
 * warnHigh < alarmHigh). Only the gauge matching the configured sensorType gets
 * the configured thresholds; sibling gauges fall back to a plain "good" arc
 * because the widget config only carries one threshold set.
 * AUT-1104: widget-override props > configured zone boundaries (useSensorThresholds,
 * custom_thresholds > base warning/threshold, primary sensor only) > flat/no-zone.
 */
function buildThresholds(min: number, max: number, isPrimary: boolean): GaugeThreshold[] {
  const wLowSrc = props.warnLow ?? (isPrimary ? configuredWarnLow.value : null)
  const wHighSrc = props.warnHigh ?? (isPrimary ? configuredWarnHigh.value : null)
  const aLowSrc = props.alarmLow ?? (isPrimary ? configuredAlarmLow.value : null)
  const aHighSrc = props.alarmHigh ?? (isPrimary ? configuredAlarmHigh.value : null)
  const hasAny = wLowSrc != null || wHighSrc != null || aLowSrc != null || aHighSrc != null

  if (!isPrimary || !hasAny) {
    return [{ value: min, color: tokens.zoneNormalRing }]
  }

  const thresholds: GaugeThreshold[] = []
  const aLow = aLowSrc ?? min
  const wLow = wLowSrc ?? aLow
  const wHigh = wHighSrc ?? max
  const aHigh = aHighSrc ?? max

  if (aLow > min) thresholds.push({ value: min, color: tokens.statusAlarm })
  if (wLow > aLow) thresholds.push({ value: aLow, color: tokens.statusWarning })
  thresholds.push({ value: wLow, color: tokens.zoneNormalRing })
  if (aHigh > wHigh) {
    thresholds.push({ value: wHigh, color: tokens.statusWarning })
  } else {
    thresholds.push({ value: wHigh, color: tokens.statusAlarm })
  }
  if (aHigh < max && aHigh > wHigh) {
    thresholds.push({ value: aHigh, color: tokens.statusAlarm })
  }
  return thresholds
}

function buildItem(sType: string, sensors: MockSensor[], labelOverride?: string): GaugeItem {
  const match = sensors.find(s => s.gpio === gpio.value && s.sensor_type === sType) ?? null
  const cfg = getSensorConfig(sType)
  // E2: widget-override > configured sensor bounds (primary only) > sensor-type fallback
  const isPrimaryType = sType === primaryType.value
  const cfgMin = isPrimaryType ? configuredMin.value : null
  const cfgMax = isPrimaryType ? configuredMax.value : null
  const min = props.yMin ?? cfgMin ?? cfg?.min ?? 0
  const max = props.yMax ?? cfgMax ?? cfg?.max ?? 100
  const resolvedUnit = getSensorUnit(sType)
  const unit = resolvedUnit !== 'raw' ? resolvedUnit : (match?.unit || '')
  return {
    sensorType: sType,
    label: labelOverride || cfg?.label || sType,
    value: match?.raw_value ?? 0,
    unit,
    min,
    max,
    decimals: cfg?.decimals ?? 1,
    thresholds: buildThresholds(min, max, sType === primaryType.value),
  }
}

const gaugeItems = computed<GaugeItem[]>(() => {
  const dev = device.value
  const pType = primaryType.value
  if (!dev || gpio.value == null || !pType) return []

  const sensors = (dev.sensors as MockSensor[]) || []
  const mvDevice = getMultiValueDeviceConfigBySensorType(pType)

  if (mvDevice) {
    const items: GaugeItem[] = []
    for (const v of mvDevice.values) {
      const exists = sensors.some(s => s.gpio === gpio.value && s.sensor_type === v.sensorType)
      if (exists) items.push(buildItem(v.sensorType, sensors, v.label))
    }
    if (items.length > 0) return items
  }

  return [buildItem(pType, sensors)]
})

const REPRESENTATIVE_TOOLTIP =
  'Messwerte einzelner Sensoren in dieser Zone (repräsentativ). Das Zonenmittel (Ø) steht in der KPI-Zeile oben.'
const REPRESENTATIVE_ARIA = 'Repräsentative Sensor-Messwerte dieser Zone.'
</script>

<template>
  <div
    class="zt-gauge-cluster"
    role="group"
    :title="REPRESENTATIVE_TOOLTIP"
    :aria-label="REPRESENTATIVE_ARIA"
  >
    <div
      v-for="item in gaugeItems"
      :key="item.sensorType"
      class="zt-gauge-cluster__item"
    >
      <span class="zt-gauge-cluster__label" :title="item.label">{{ item.label }}</span>
      <div class="zt-gauge-cluster__chart">
        <GaugeChart
          :value="item.value"
          :unit="item.unit"
          :decimals="item.decimals"
          :min="item.min"
          :max="item.max"
          :thresholds="item.thresholds"
          size="sm"
        />
      </div>
    </div>
    <div v-if="gaugeItems.length === 0" class="zt-gauge-cluster__empty">
      Keine Sensordaten
    </div>
  </div>
</template>

<style scoped>
.zt-gauge-cluster {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  height: 100%;
  min-height: 0;
}

.zt-gauge-cluster__item {
  flex: 1 1 0;
  min-width: 72px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 0;
}

.zt-gauge-cluster__label {
  flex-shrink: 0;
  max-width: 100%;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  line-height: 1.1;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.zt-gauge-cluster__chart {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.zt-gauge-cluster__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-style: italic;
}
</style>
