<script setup lang="ts">
/**
 * LiveDataPreview Component
 *
 * Shows real-time sensor value with quality badge and mini sparkline.
 * Subscribes to WebSocket sensor_data events filtered by espId + gpio.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { websocketService, type WebSocketMessage } from '@/services/websocket'
import { LiveLineChart, type ChartDataPoint } from '@/components/charts'
import { tokens } from '@/utils/cssTokens'
import { getSensorConfig } from '@/utils/sensorDefaults'

interface Props {
  /** ESP device ID */
  espId: string
  /** GPIO pin number */
  gpio: number
  /** Value unit suffix */
  unit?: string
  /** Sensor type for multi-value filtering (e.g. 'sht31_humidity') */
  sensorType?: string
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  sensorType: '',
})

const currentValue = ref<number | null>(null)
const quality = ref<string>('unknown')
const sparklineData = ref<ChartDataPoint[]>([])
const MAX_SPARKLINE_POINTS = 20

let subscriptionId: string | null = null

function handleMessage(msg: WebSocketMessage): void {
  const data = msg.data as {
    esp_id?: string
    device_id?: string
    gpio?: number
    value?: number
    quality?: string
    sensor_type?: string
  }

  const espId = data.esp_id || data.device_id
  const gpio = data.gpio

  if (espId !== props.espId || gpio !== props.gpio) return

  // Multi-value filter: only accept matching sensor_type (e.g. sht31_temp vs sht31_humidity)
  if (props.sensorType && data.sensor_type
      && data.sensor_type.toLowerCase() !== props.sensorType.toLowerCase()) return

  if (data.value !== undefined) {
    currentValue.value = data.value
    quality.value = data.quality ?? 'unknown'

    const point: ChartDataPoint = {
      timestamp: new Date(),
      value: data.value,
    }

    const newData = [...sparklineData.value, point]
    if (newData.length > MAX_SPARKLINE_POINTS) {
      newData.shift()
    }
    sparklineData.value = newData
  }
}

onMounted(() => {
  subscriptionId = websocketService.subscribe(
    { types: ['sensor_data'], esp_ids: [props.espId] },
    handleMessage,
  )
})

onUnmounted(() => {
  if (subscriptionId) {
    websocketService.unsubscribe(subscriptionId)
    subscriptionId = null
  }
})

const decimals = computed(() => getSensorConfig(props.sensorType)?.decimals ?? 2)

const formattedValue = computed(() => {
  if (currentValue.value === null) return null
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals.value,
    maximumFractionDigits: decimals.value,
  }).format(currentValue.value)
})

const QUALITY_COLORS: Record<string, string> = {
  excellent: 'var(--color-success)',
  good: 'var(--color-success)',
  fair: 'var(--color-status-warning)',
  poor: 'var(--color-status-warning)',
  bad: 'var(--color-error)',
  stale: 'var(--color-text-muted)',
  error: 'var(--color-error)',
  unknown: 'var(--color-text-muted)',
}
</script>

<template>
  <div class="live-preview" aria-live="polite" role="status">
    <div class="live-preview__value-row">
      <span class="live-preview__value" v-if="currentValue !== null">
        {{ formattedValue }}
      </span>
      <span class="live-preview__value live-preview__value--empty" v-else>
        --
      </span>
      <span v-if="unit" class="live-preview__unit">{{ unit }}</span>
      <span
        class="live-preview__quality"
        :style="{ color: QUALITY_COLORS[quality] }"
      >
        {{ quality }}
      </span>
    </div>

    <div class="live-preview__sparkline" v-if="sparklineData.length > 2">
      <LiveLineChart
        :data="sparklineData"
        :max-data-points="MAX_SPARKLINE_POINTS"
        height="60px"
        :show-grid="false"
        :fill="false"
        :color="tokens.accent"
      />
    </div>
  </div>
</template>

<style scoped>
.live-preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
}

.live-preview__value-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.live-preview__value {
  font-family: var(--font-mono);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1;
}

.live-preview__value--empty {
  color: var(--color-text-muted);
}

.live-preview__unit {
  font-family: var(--font-mono);
  font-size: var(--text-base);
  color: var(--color-text-muted);
}

.live-preview__quality {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  text-transform: uppercase;
  margin-left: auto;
}

.live-preview__sparkline {
  width: 100%;
}
</style>
