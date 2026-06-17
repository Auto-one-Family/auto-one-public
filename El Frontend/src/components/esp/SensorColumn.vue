<script setup lang="ts">
/**
 * SensorColumn Component
 *
 * Extracted from ESPOrbitalLayout: Renders the left column of sensor satellites.
 * Handles sensor selection and multi-row layout for >5 sensors.
 *
 * Used in:
 * - ESPOrbitalLayout (left column)
 * - Future: DeviceDetailView standalone sensor panel
 */

import { computed } from 'vue'
import { Plus } from 'lucide-vue-next'
import SensorSatellite from './SensorSatellite.vue'
import type { QualityLevel } from '@/types'

/** Sensor data shape from device.sensors array */
export interface SensorItem {
  /** Sensor config UUID from database (unique identifier for multi-value sensors) */
  config_id?: string
  gpio: number
  sensor_type: string
  name: string | null
  raw_value: number | null
  processed_value?: number | null
  unit: string
  quality: string
  device_type?: string | null
  multi_values?: Record<string, any> | null
  is_multi_value?: boolean
  i2c_address?: number | null
  interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'VIRTUAL' | null
  device_scope?: 'zone_local' | 'multi_zone' | 'mobile' | null
  assigned_zones?: string[] | null
}

interface Props {
  espId: string
  sensors: SensorItem[]
  selectedGpio?: number | null
  showConnections?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedGpio: null,
  showConnections: true,
})

const emit = defineEmits<{
  'sensor-click': [payload: { configId?: string; gpio: number; sensorType: string }]
}>()

/** Deterministic sort: sensor_type alphabetical, then i2c_address */
const sortedSensors = computed(() =>
  [...props.sensors].sort((a, b) => {
    const typeCompare = (a.sensor_type || '').localeCompare(b.sensor_type || '')
    if (typeCompare !== 0) return typeCompare
    return (a.i2c_address || 0) - (b.i2c_address || 0)
  })
)

/** Use multi-row layout when >5 sensors */
const useMultiRow = computed(() => props.sensors.length > 5)
</script>

<template>
  <div
    :class="[
      'sensor-column',
      {
        'sensor-column--multi-row': useMultiRow,
        'sensor-column--empty': sensors.length === 0,
      }
    ]"
  >
    <SensorSatellite
      v-for="(sensor, idx) in sortedSensors"
      :key="sensor.config_id || `sensor-${sensor.gpio}-${sensor.sensor_type}`"
      :esp-id="espId"
      :gpio="sensor.gpio"
      :sensor-type="sensor.sensor_type"
      :name="sensor.name"
      :value="sensor.processed_value ?? sensor.raw_value ?? 0"
      :quality="(sensor.quality as QualityLevel)"
      :unit="sensor.unit"
      :device-type="sensor.device_type"
      :multi-values="sensor.multi_values"
      :is-multi-value="sensor.is_multi_value"
      :i2c-address="sensor.i2c_address"
      :interface-type="sensor.interface_type"
      :device-scope="sensor.device_scope"
      :assigned-zones="sensor.assigned_zones ?? undefined"
      :selected="selectedGpio === sensor.gpio"
      :show-connections="showConnections"
      class="sensor-column__satellite"
      :style="{ animationDelay: `${idx * 60}ms` }"
      @click="emit('sensor-click', { configId: sensor.config_id, gpio: sensor.gpio, sensorType: sensor.sensor_type })"
    />

    <!-- Empty state -->
    <div v-if="sensors.length === 0" class="sensor-column__empty-slot">
      <Plus class="w-3 h-3" />
      <span>Sensors</span>
    </div>
  </div>
</template>

<style scoped>
.sensor-column {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  align-items: stretch;
  width: 120px;
  flex-shrink: 0;
}

.sensor-column--empty {
  width: 56px;
}

/* Multi-column mode (>5 sensors) = 2 columns side by side */
.sensor-column--multi-row {
  display: grid;
  grid-template-columns: repeat(2, 120px);
  gap: 0.375rem;
  width: auto;
}

.sensor-column__satellite {
  position: relative !important;
  transform: none !important;
  width: 100%;
  animation: satellite-appear 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes satellite-appear {
  from { opacity: 0; transform: translateY(8px) scale(0.95); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.sensor-column__empty-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.75rem 0.5rem;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: rgba(255, 255, 255, 0.2);
  font-size: 0.5625rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  min-height: 56px;
}

.sensor-column__empty-slot:hover {
  border-color: rgba(96, 165, 250, 0.2);
  color: rgba(255, 255, 255, 0.35);
}
</style>
