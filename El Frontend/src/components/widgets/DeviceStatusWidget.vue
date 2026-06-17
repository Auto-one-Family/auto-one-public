<script setup lang="ts">
/**
 * DeviceStatusWidget Component
 *
 * Doughnut chart showing online/offline/warning device distribution.
 * Reactive via ESP store - no extra WebSocket subscription needed.
 */

import { computed } from 'vue'
import { Cpu } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { tokens } from '@/utils/cssTokens'
import { GaugeChart } from '@/components/charts'
import { StatusBarChart, type StatusBarItem } from '@/components/charts'
import WidgetCard from './WidgetCard.vue'

const espStore = useEspStore()

const statusCounts = computed(() => {
  const devices = espStore.devices
  let online = 0
  let offline = 0
  let error = 0
  let other = 0

  for (const d of devices) {
    switch (d.status) {
      case 'online':
        online++
        break
      case 'offline':
        offline++
        break
      case 'error':
        error++
        break
      default:
        other++
    }
  }

  return { online, offline, error, other, total: devices.length }
})

const barData = computed<StatusBarItem[]>(() => [
  { label: 'Online', value: statusCounts.value.online, color: tokens.success },
  { label: 'Offline', value: statusCounts.value.offline, color: tokens.statusOffline },
  { label: 'Error', value: statusCounts.value.error, color: tokens.error },
  ...(statusCounts.value.other > 0
    ? [{ label: 'Andere', value: statusCounts.value.other, color: tokens.mock }]
    : []),
])

const onlinePercentage = computed(() =>
  statusCounts.value.total > 0
    ? Math.round((statusCounts.value.online / statusCounts.value.total) * 100)
    : 0
)
</script>

<template>
  <WidgetCard
    title="Device Status"
    :icon="Cpu"
  >
    <div class="device-status-widget">
      <div class="device-status-widget__gauge">
        <GaugeChart
          :value="onlinePercentage"
          :min="0"
          :max="100"
          unit="%"
          size="sm"
          :thresholds="[
            { value: 0, color: tokens.error },
            { value: 50, color: tokens.warning },
            { value: 80, color: tokens.success },
          ]"
        />
        <span class="device-status-widget__gauge-label">Online</span>
      </div>

      <div class="device-status-widget__bars">
        <StatusBarChart
          :data="barData"
          :horizontal="true"
          height="80px"
        />
      </div>
    </div>

    <template #footer>
      <span>{{ statusCounts.total }} Geräte gesamt</span>
    </template>
  </WidgetCard>
</template>

<style scoped>
.device-status-widget {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.device-status-widget__gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.device-status-widget__gauge-label {
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.device-status-widget__bars {
  flex: 1;
  min-width: 0;
}
</style>
