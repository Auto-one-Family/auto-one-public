<script setup lang="ts">
/**
 * ESPHealthWidget — ESP device health overview for dashboard
 *
 * Shows all ESPs with connection status, RSSI bars, uptime.
 * Click navigates to /hardware/:zoneId/:espId.
 * Min-size: 4x3
 */
import { computed } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useRouter } from 'vue-router'
import { Cpu, Wifi, WifiOff } from 'lucide-vue-next'
import type { ESPDevice } from '@/api/esp'
import { getESPStatus } from '@/composables/useESPStatus'

interface Props {
  zoneFilter?: string | null
  showOfflineOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  zoneFilter: null,
  showOfflineOnly: false,
})

const espStore = useEspStore()
const router = useRouter()

/** Check if device is online using shared status logic */
function isDeviceOnline(device: ESPDevice): boolean {
  return getESPStatus(device) === 'online'
}

const filteredDevices = computed(() => {
  let devices = [...espStore.devices]

  if (props.zoneFilter) {
    devices = devices.filter(d => d.zone_id === props.zoneFilter)
  }

  if (props.showOfflineOnly) {
    devices = devices.filter(d => !isDeviceOnline(d))
  }

  // Sort: offline first, then by name
  devices.sort((a, b) => {
    const aOnline = isDeviceOnline(a)
    const bOnline = isDeviceOnline(b)
    if (aOnline !== bOnline) return aOnline ? 1 : -1
    const aName = a.name || espStore.getDeviceId(a)
    const bName = b.name || espStore.getDeviceId(b)
    return aName.localeCompare(bName)
  })

  return devices
})

const summary = computed(() => {
  const all = espStore.devices
  const online = all.filter(d => isDeviceOnline(d)).length
  const offline = all.length - online
  const warning = all.filter(d => {
    const s = getESPStatus(d)
    return s === 'error' || s === 'safemode'
  }).length
  return { online, offline, warning, total: all.length }
})

function rssiLevel(rssi: number | null | undefined): number {
  if (rssi == null) return 0
  if (rssi >= -50) return 5
  if (rssi >= -60) return 4
  if (rssi >= -70) return 3
  if (rssi >= -80) return 2
  return 1
}

function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function navigateToDevice(device: ESPDevice) {
  const deviceId = espStore.getDeviceId(device)
  if (device.zone_id) {
    router.push({ name: 'hardware-esp', params: { zoneId: device.zone_id, espId: deviceId } })
  } else {
    router.push({ name: 'hardware', query: { openSettings: deviceId } })
  }
}
</script>

<template>
  <div class="esp-health-widget">
    <!-- Summary Bar -->
    <div class="esp-health-widget__summary">
      <span class="esp-health-widget__stat esp-health-widget__stat--online">{{ summary.online }} Online</span>
      <span class="esp-health-widget__sep">/</span>
      <span class="esp-health-widget__stat esp-health-widget__stat--offline">{{ summary.offline }} Offline</span>
      <span v-if="summary.warning > 0" class="esp-health-widget__sep">/</span>
      <span v-if="summary.warning > 0" class="esp-health-widget__stat esp-health-widget__stat--warning">{{ summary.warning }} Warning</span>
    </div>

    <!-- Device List -->
    <div v-if="filteredDevices.length > 0" class="esp-health-widget__list">
      <div
        v-for="device in filteredDevices"
        :key="espStore.getDeviceId(device)"
        class="esp-health-widget__device"
        @click="navigateToDevice(device)"
      >
        <span
          :class="['esp-health-widget__dot', isDeviceOnline(device) ? 'esp-health-widget__dot--online' : 'esp-health-widget__dot--offline']"
        />
        <span class="esp-health-widget__name">
          {{ device.name || espStore.getDeviceId(device) }}
          <span v-if="espStore.isMock(espStore.getDeviceId(device))" class="esp-health-widget__mock-badge">MOCK</span>
        </span>
        <span class="esp-health-widget__rssi" :title="`RSSI: ${device.wifi_rssi ?? '?'} dBm`">
          <component :is="isDeviceOnline(device) ? Wifi : WifiOff" class="w-3 h-3" />
          <span class="esp-health-widget__rssi-bars">
            <span
              v-for="i in 5"
              :key="i"
              :class="['esp-health-widget__rssi-bar', { 'esp-health-widget__rssi-bar--active': i <= rssiLevel(device.wifi_rssi) }]"
            />
          </span>
        </span>
        <span class="esp-health-widget__uptime">{{ formatUptime(device.uptime) }}</span>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="esp-health-widget__empty">
      <Cpu class="w-6 h-6" style="opacity: 0.3" />
      <span>Keine ESPs registriert</span>
    </div>
  </div>
</template>

<style scoped>
.esp-health-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.esp-health-widget__summary {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 600;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.esp-health-widget__stat--online { color: var(--color-success); }
.esp-health-widget__stat--offline { color: var(--color-text-muted); }
.esp-health-widget__stat--warning { color: var(--color-warning); }
.esp-health-widget__sep { color: var(--color-text-muted); opacity: 0.4; }

.esp-health-widget__list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-1) 0;
}

.esp-health-widget__device {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  cursor: pointer;
  transition: background var(--transition-fast);
  border-radius: var(--radius-sm);
  margin: 0 var(--space-1);
}

.esp-health-widget__device:hover {
  background: var(--glass-bg-light);
}

.esp-health-widget__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.esp-health-widget__dot--online { background: var(--color-success); }
.esp-health-widget__dot--offline { background: var(--color-text-muted); }

.esp-health-widget__name {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.esp-health-widget__mock-badge {
  font-size: var(--text-xxs);
  font-weight: 600;
  padding: 1px var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--color-bg-quaternary);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.esp-health-widget__rssi {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.esp-health-widget__rssi-bars {
  display: flex;
  align-items: flex-end;
  gap: 1px;
  height: 10px;
}

.esp-health-widget__rssi-bar {
  width: 2px;
  background: var(--color-bg-quaternary);
  border-radius: 1px;
}

.esp-health-widget__rssi-bar:nth-child(1) { height: 2px; }
.esp-health-widget__rssi-bar:nth-child(2) { height: 4px; }
.esp-health-widget__rssi-bar:nth-child(3) { height: 6px; }
.esp-health-widget__rssi-bar:nth-child(4) { height: 8px; }
.esp-health-widget__rssi-bar:nth-child(5) { height: 10px; }

.esp-health-widget__rssi-bar--active {
  background: var(--color-success);
}

.esp-health-widget__uptime {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 3em;
  text-align: right;
}

.esp-health-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
