<script setup lang="ts">
/**
 * SensorCardWidget — Sensor value card for dashboard
 *
 * AUT-247: Thin wrapper around SensorTile (displayMode='numeric').
 * Existing dashboard JSONs continue to load and render unchanged because
 * the prop signature and update:config emit are preserved 1:1.
 */
import SensorTile from './SensorTile.vue'

interface Props {
  sensorId?: string
  zoneId?: string
  title?: string
}

const props = defineProps<Props>()
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
    display-mode="numeric"
    hide-mode-toggle
    @update:config="onTileUpdate"
  />
</template>
