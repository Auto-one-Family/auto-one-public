<script setup lang="ts">
/**
 * ZoneConfigPanel — Zone Configuration SlideOver
 *
 * Shows zone information and configuration:
 * - Zone name (editable)
 * - Description
 * - Subzone list
 * - Statistics (ESP count, sensor count, actuator count)
 */

import { computed } from 'vue'
import { MapPin, Cpu, Activity, Zap } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import type { MockSensor, MockActuator } from '@/types'

interface Props {
  zoneId: string
  zoneName: string
}

const props = defineProps<Props>()

const espStore = useEspStore()

const zoneDevices = computed(() =>
  espStore.devices.filter(d => d.zone_id === props.zoneId)
)

const stats = computed(() => {
  let sensors = 0
  let actuators = 0
  let online = 0

  for (const device of zoneDevices.value) {
    const s = (device.sensors as MockSensor[]) || []
    const a = (device.actuators as MockActuator[]) || []
    sensors += s.length
    actuators += a.length
    if (device.status === 'online' || device.connected === true) online++
  }

  return {
    espCount: zoneDevices.value.length,
    onlineCount: online,
    sensorCount: sensors,
    actuatorCount: actuators,
  }
})

/** Unique subzones from devices */
const subzones = computed(() => {
  const subs = new Set<string>()
  for (const d of zoneDevices.value) {
    if (d.subzone_id) subs.add(d.subzone_id)
    if ((d as any).subzone_name) subs.add((d as any).subzone_name)
  }
  return Array.from(subs)
})
</script>

<template>
  <div class="zone-config">
    <!-- Zone Info -->
    <section class="zone-config__section">
      <h3 class="zone-config__section-title">Zone-Information</h3>

      <div class="zone-config__field">
        <label class="zone-config__label">Name</label>
        <div class="zone-config__value">{{ zoneName }}</div>
      </div>

      <div class="zone-config__field">
        <label class="zone-config__label">Zone-ID</label>
        <code class="zone-config__code">{{ zoneId }}</code>
      </div>
    </section>

    <!-- Statistics -->
    <section class="zone-config__section">
      <h3 class="zone-config__section-title">Statistiken</h3>

      <div class="zone-config__stats">
        <div class="zone-config__stat">
          <Cpu class="w-5 h-5" style="color: var(--color-info)" />
          <div>
            <span class="zone-config__stat-value">{{ stats.espCount }}</span>
            <span class="zone-config__stat-label">ESPs ({{ stats.onlineCount }} online)</span>
          </div>
        </div>

        <div class="zone-config__stat">
          <Activity class="w-5 h-5" style="color: var(--color-accent-bright)" />
          <div>
            <span class="zone-config__stat-value">{{ stats.sensorCount }}</span>
            <span class="zone-config__stat-label">Sensoren</span>
          </div>
        </div>

        <div class="zone-config__stat">
          <Zap class="w-5 h-5" style="color: var(--color-status-warning)" />
          <div>
            <span class="zone-config__stat-value">{{ stats.actuatorCount }}</span>
            <span class="zone-config__stat-label">Aktoren</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Subzones -->
    <section class="zone-config__section">
      <h3 class="zone-config__section-title">Subzonen ({{ subzones.length }})</h3>

      <div v-if="subzones.length === 0" class="zone-config__empty">
        Keine Subzonen definiert
      </div>

      <div v-else class="zone-config__subzone-list">
        <div v-for="sub in subzones" :key="sub" class="zone-config__subzone">
          <MapPin class="w-3.5 h-3.5" />
          <span>{{ sub }}</span>
        </div>
      </div>
    </section>

    <!-- Devices in this zone -->
    <section class="zone-config__section">
      <h3 class="zone-config__section-title">Geräte in dieser Zone</h3>

      <div class="zone-config__device-list">
        <div
          v-for="device in zoneDevices"
          :key="espStore.getDeviceId(device)"
          class="zone-config__device"
        >
          <span
            class="zone-config__device-dot"
            :class="device.status === 'online' || device.connected ? 'zone-config__device-dot--online' : 'zone-config__device-dot--offline'"
          />
          <span class="zone-config__device-name">{{ device.name || espStore.getDeviceId(device) }}</span>
          <span class="zone-config__device-id">{{ espStore.getDeviceId(device) }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.zone-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.zone-config__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--glass-border);
}

.zone-config__section:last-child { border-bottom: none; }

.zone-config__section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.zone-config__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.zone-config__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.zone-config__value {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.zone-config__code {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}

/* Stats */
.zone-config__stats {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.zone-config__stat {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.zone-config__stat div {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.zone-config__stat-value {
  font-family: var(--font-mono);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--color-text-primary);
}

.zone-config__stat-label {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Subzones */
.zone-config__empty {
  padding: var(--space-3);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.zone-config__subzone-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.zone-config__subzone {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

/* Devices */
.zone-config__device-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.zone-config__device {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.zone-config__device-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.zone-config__device-dot--online { background: var(--color-status-good); box-shadow: 0 0 4px rgba(34, 197, 94, 0.4); }
.zone-config__device-dot--offline { background: var(--color-status-offline); }

.zone-config__device-name {
  flex: 1;
  color: var(--color-text-primary);
  font-weight: 500;
}

.zone-config__device-id {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}
</style>
