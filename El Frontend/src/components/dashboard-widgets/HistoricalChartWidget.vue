<script setup lang="ts">
/**
 * HistoricalChartWidget — Historical sensor data over selectable time range
 *
 * AUT-247: Thin wrapper around SensorTile (displayMode='historic') with the
 * additional CSV-Export overlay button preserved (the export dialog is
 * widget-level, not part of the unified SensorTile).
 *
 * Existing dashboard JSONs continue to load unchanged.
 */
import { ref, computed, watch } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useZoneStore } from '@/shared/stores/zone.store'
import { Download } from 'lucide-vue-next'
import SensorTile from './SensorTile.vue'
import ExportCsvDialog from '@/components/dashboard-widgets/ExportCsvDialog.vue'
import type { MockSensor } from '@/types'
import { useSensorId } from '@/composables/useSensorId'

interface Props {
  sensorId?: string
  zoneId?: string
  title?: string
  timeRange?: '1h' | '6h' | '24h' | '7d' | '30d'
  showThresholds?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '24h',
  showThresholds: true,
})

const emit = defineEmits<{
  'update:config': [config: Record<string, any>]
}>()

const espStore = useEspStore()
const zoneStore = useZoneStore()
const showExportDialog = ref(false)

const localSensorId = ref(props.sensorId || '')
const localZoneId = ref<string | undefined>(props.zoneId)

watch(() => props.sensorId, (v) => { if (v) localSensorId.value = v })
watch(() => props.zoneId, (v) => { localZoneId.value = v })

const { espId: parsedEspId, gpio: parsedGpio, sensorType: parsedSensorType, isValid: sensorIdValid } = useSensorId(localSensorId)

const parsedSensor = computed(() => {
  if (!sensorIdValid.value) return null
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsedEspId.value)
  if (!device) return null
  return ((device.sensors as MockSensor[]) || []).find(s =>
    s.gpio === parsedGpio.value && (!parsedSensorType.value || s.sensor_type === parsedSensorType.value)
  ) ?? null
})

const resolvedSensorName = computed(() =>
  parsedSensor.value?.name || parsedSensorType.value || ''
)

const zoneNameFromContext = computed(() => {
  if (!localZoneId.value) return undefined
  return zoneStore.zoneEntities.find(z => z.zone_id === localZoneId.value)?.name
})

function onTileUpdate(cfg: { sensorId?: string; timeRange?: string }) {
  if (cfg.sensorId) {
    localSensorId.value = cfg.sensorId
    emit('update:config', { sensorId: cfg.sensorId })
  }
  if (cfg.timeRange) {
    emit('update:config', { timeRange: cfg.timeRange })
  }
}
</script>

<template>
  <div class="historical-widget">
    <button
      v-if="localSensorId && parsedSensor"
      class="historical-widget__export-btn"
      title="Als CSV exportieren"
      @click="showExportDialog = true"
    >
      <Download :size="14" />
    </button>

    <SensorTile
      :sensor-id="props.sensorId"
      :zone-id="props.zoneId"
      :title="props.title"
      display-mode="historic"
      hide-mode-toggle
      :time-range="props.timeRange"
      :show-thresholds="props.showThresholds"
      @update:config="onTileUpdate"
    />

    <ExportCsvDialog
      v-model:open="showExportDialog"
      :sensor-id="localSensorId"
      :sensor-name="resolvedSensorName"
      :zone-name="zoneNameFromContext"
    />
  </div>
</template>

<style scoped>
.historical-widget {
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
}

.historical-widget__export-btn {
  position: absolute;
  top: var(--space-1);
  right: var(--space-1);
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  min-width: 28px;
  min-height: 28px;
  padding: var(--space-1);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.15s, color 0.15s;
}

.historical-widget__export-btn:hover {
  opacity: 1;
  color: var(--color-accent);
}

@media (hover: none) {
  .historical-widget__export-btn {
    opacity: 0.8;
  }
}
</style>
