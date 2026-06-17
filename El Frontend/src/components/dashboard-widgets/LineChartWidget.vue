<script setup lang="ts">
/**
 * LineChartWidget — Live sparkline widget for dashboard
 *
 * AUT-247: Thin wrapper around SensorTile (displayMode='sparkline').
 * Existing dashboard JSONs continue to load and render unchanged.
 */
import SensorTile from './SensorTile.vue'

interface Props {
  sensorId?: string
  zoneId?: string
  title?: string
  showThresholds?: boolean
  yMin?: number
  yMax?: number
  color?: string
  warnLow?: number
  warnHigh?: number
  alarmLow?: number
  alarmHigh?: number
}

const props = withDefaults(defineProps<Props>(), {
  showThresholds: false,
})
const emit = defineEmits<{
  'update:config': [config: { sensorId: string }]
}>()

function onTileUpdate(cfg: { sensorId?: string }) {
  if (cfg.sensorId) emit('update:config', { sensorId: cfg.sensorId })
}
</script>

<template>
  <SensorTile
    :sensor-id="props.sensorId"
    :zone-id="props.zoneId"
    :title="props.title"
    display-mode="sparkline"
    hide-mode-toggle
    :show-thresholds="props.showThresholds"
    :y-min="props.yMin"
    :y-max="props.yMax"
    :color="props.color"
    :warn-low="props.warnLow"
    :warn-high="props.warnHigh"
    :alarm-low="props.alarmLow"
    :alarm-high="props.alarmHigh"
    @update:config="onTileUpdate"
  />
</template>
