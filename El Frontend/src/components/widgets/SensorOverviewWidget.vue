<script setup lang="ts">
/**
 * SensorOverviewWidget Component
 *
 * Live line chart showing recent sensor readings via WebSocket.
 * User can select which sensor to display from a dropdown.
 * Span: 2x1 (wide widget).
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Thermometer } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { tokens } from '@/utils/cssTokens'
import { websocketService, type WebSocketMessage } from '@/services/websocket'
import { LiveLineChart, type ChartDataPoint } from '@/components/charts'
import WidgetCard from './WidgetCard.vue'

const espStore = useEspStore()

/** Currently selected sensor key: "espId:gpio" */
const selectedSensor = ref<string>('')

/** Sensor data buffer for chart */
const chartData = ref<ChartDataPoint[]>([])

const MAX_DATA_POINTS = 30

/** Build sensor options from all devices */
const sensorOptions = computed(() => {
  const options: Array<{ value: string; label: string; unit: string }> = []

  for (const device of espStore.devices) {
    const sensors = (device.sensors as Array<{ gpio: number; sensor_type: string; unit?: string }>) ?? []
    const deviceId = device.device_id || device.esp_id || ''

    for (const sensor of sensors) {
      const key = `${deviceId}:${sensor.gpio}`
      const label = `${device.name || deviceId} - ${sensor.sensor_type} (GPIO ${sensor.gpio})`
      options.push({
        value: key,
        label,
        unit: sensor.unit ?? '',
      })
    }
  }

  return options
})

/** Auto-select first sensor if none selected */
watch(sensorOptions, (opts) => {
  if (!selectedSensor.value && opts.length > 0) {
    selectedSensor.value = opts[0].value
  }
}, { immediate: true })

/** Get unit for selected sensor */
const selectedUnit = computed(() => {
  const opt = sensorOptions.value.find(o => o.value === selectedSensor.value)
  return opt?.unit ?? ''
})

/** Reset chart data when sensor selection changes */
watch(selectedSensor, () => {
  chartData.value = []
})

/** WebSocket subscription ID */
let subscriptionId: string | null = null

function handleSensorMessage(msg: WebSocketMessage): void {
  const data = msg.data as {
    esp_id?: string
    device_id?: string
    gpio?: number
    value?: number
    sensor_type?: string
  }

  const espId = data.esp_id || data.device_id
  const gpio = data.gpio
  const value = data.value

  if (!espId || gpio === undefined || value === undefined) return

  const key = `${espId}:${gpio}`
  if (key !== selectedSensor.value) return

  const point: ChartDataPoint = {
    timestamp: new Date(),
    value: typeof value === 'number' ? value : parseFloat(String(value)),
  }

  const newData = [...chartData.value, point]
  if (newData.length > MAX_DATA_POINTS) {
    newData.shift()
  }
  chartData.value = newData
}

onMounted(() => {
  subscriptionId = websocketService.subscribe(
    { types: ['sensor_data'] },
    handleSensorMessage,
  )
})

onUnmounted(() => {
  if (subscriptionId) {
    websocketService.unsubscribe(subscriptionId)
    subscriptionId = null
  }
})
</script>

<template>
  <WidgetCard
    title="Sensor Live"
    :icon="Thermometer"
    span="2x1"
  >
    <template #actions>
      <select
        v-model="selectedSensor"
        class="sensor-widget__select"
        aria-label="Sensor auswählen"
      >
        <option value="" disabled>Sensor wählen...</option>
        <option
          v-for="opt in sensorOptions"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
    </template>

    <div class="sensor-widget__chart">
      <LiveLineChart
        v-if="chartData.length > 0"
        :data="chartData"
        :max-data-points="MAX_DATA_POINTS"
        :unit="selectedUnit"
        height="160px"
        :color="tokens.accent"
      />
      <div v-else class="sensor-widget__empty">
        <span class="sensor-widget__empty-text">
          {{ selectedSensor ? 'Warte auf Daten...' : 'Sensor auswählen' }}
        </span>
      </div>
    </div>

    <template #footer>
      <span>{{ chartData.length }} Datenpunkte</span>
    </template>
  </WidgetCard>
</template>

<style scoped>
.sensor-widget__select {
  padding: 2px 6px;
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  max-width: 200px;
  appearance: none;
  -webkit-appearance: none;
}

.sensor-widget__select:hover {
  border-color: var(--color-accent);
}

.sensor-widget__select:focus {
  outline: none;
  border-color: var(--color-accent);
}

.sensor-widget__select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.sensor-widget__chart {
  min-height: 160px;
}

.sensor-widget__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
}

.sensor-widget__empty-text {
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}
</style>
