<script setup lang="ts">
/**
 * ZoneDetailView Component
 *
 * Level 2: Shows all devices of a single zone in a spacious grid.
 * Background shifts to --color-bg-secondary for "closer" depth perception.
 *
 * Features:
 * - Subzone grouping via SubzoneArea
 * - DeviceSummaryCards in auto-fill grid
 * - Cross-ESP connection count badge
 * - VueDraggable for subzone reassignment
 */

import { computed } from 'vue'
import type { ESPDevice } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useLogicStore } from '@/shared/stores/logic.store'
import { ArrowLeft } from 'lucide-vue-next'
import SubzoneArea from './SubzoneArea.vue'
import DeviceSummaryCard from './DeviceSummaryCard.vue'

interface Props {
  zoneId: string
  zoneName: string
  devices: ESPDevice[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'device-click', payload: { deviceId: string; originRect: DOMRect }): void
  (e: 'back'): void
  (e: 'heartbeat', deviceId: string): void
  (e: 'delete', deviceId: string): void
  (e: 'settings', device: ESPDevice): void
}>()

const espStore = useEspStore()
const logicStore = useLogicStore()

/** Total sensor/actuator counts */
const totalSensors = computed(() =>
  props.devices.reduce((sum, d) => {
    const sensors = d.sensors as any[] | undefined
    return sum + (sensors?.length ?? d.sensor_count ?? 0)
  }, 0)
)

const totalActuators = computed(() =>
  props.devices.reduce((sum, d) => {
    const actuators = d.actuators as any[] | undefined
    return sum + (actuators?.length ?? d.actuator_count ?? 0)
  }, 0)
)

/** Cross-ESP connections in this zone */
const crossEspCount = computed(() => {
  // Count connections where at least one device is in this zone
  return logicStore.crossEspConnections.filter(conn => {
    const sourceDevice = espStore.devices.find(d => espStore.getDeviceId(d) === conn.sourceEspId)
    const targetDevice = espStore.devices.find(d => espStore.getDeviceId(d) === conn.targetEspId)
    return sourceDevice?.zone_id === props.zoneId || targetDevice?.zone_id === props.zoneId
  }).length
})

/** Subzone grouping */
interface SubzoneGroup {
  subzoneId: string | null
  subzoneName: string
  devices: ESPDevice[]
}

const subzoneGroups = computed((): SubzoneGroup[] => {
  const groups = new Map<string | null, SubzoneGroup>()

  for (const device of props.devices) {
    const szId = device.subzone_id || null
    if (!groups.has(szId)) {
      groups.set(szId, {
        subzoneId: szId,
        subzoneName: device.subzone_name || (szId ? szId : ''),
        devices: [],
      })
    }
    groups.get(szId)!.devices.push(device)
  }

  const result = Array.from(groups.values())
  result.sort((a, b) => {
    if (a.subzoneId === null) return 1
    if (b.subzoneId === null) return -1
    return (a.subzoneName ?? '').localeCompare(b.subzoneName ?? '')
  })
  return result
})

const subzonedGroups = computed(() =>
  subzoneGroups.value.filter(g => g.subzoneId !== null)
)
const unsubzonedDevices = computed(() => {
  const group = subzoneGroups.value.find(g => g.subzoneId === null)
  return group?.devices || []
})

function isMock(device: ESPDevice): boolean {
  return espStore.isMock(espStore.getDeviceId(device))
}
</script>

<template>
  <div class="zone-detail-view">
    <!-- Back Navigation Strip -->
    <nav class="zone-detail-view__nav" aria-label="Zoom-Navigation">
      <button class="zone-detail-view__back" @click="emit('back')">
        <ArrowLeft class="zone-detail-view__back-icon" />
        <span>Übersicht</span>
      </button>
      <span class="zone-detail-view__nav-sep">/</span>
      <span class="zone-detail-view__nav-current">{{ zoneName }}</span>
    </nav>

    <!-- Zone Header -->
    <div class="zone-detail-view__header">
      <h2 class="zone-detail-view__title">{{ zoneName }}</h2>
      <div class="zone-detail-view__meta">
        <span>{{ devices.length }} Geräte</span>
        <span>· {{ totalSensors }} Sensoren</span>
        <span>· {{ totalActuators }} Aktoren</span>
      </div>
      <RouterLink
        v-if="crossEspCount > 0"
        to="/logic"
        class="zone-detail-view__cross-esp-badge"
      >
        {{ crossEspCount }} Cross-ESP Regeln aktiv
      </RouterLink>
    </div>

    <!-- Subzone areas -->
    <SubzoneArea
      v-for="group in subzonedGroups"
      :key="group.subzoneId ?? '__none'"
      :subzone-id="group.subzoneId!"
      :subzone-name="group.subzoneName"
      :devices="group.devices"
    >
      <DeviceSummaryCard
        v-for="device in group.devices"
        :key="espStore.getDeviceId(device)"
        :device="device"
        :is-mock="isMock(device)"
        @click="(p) => emit('device-click', p)"
        @heartbeat="(id) => emit('heartbeat', id)"
        @settings="(d) => emit('settings', d)"
      />
    </SubzoneArea>

    <!-- Devices without subzone -->
    <div v-if="unsubzonedDevices.length > 0" class="zone-detail-view__unsubzoned">
      <div class="zone-detail-view__grid grid-auto-sm">
        <DeviceSummaryCard
          v-for="device in unsubzonedDevices"
          :key="espStore.getDeviceId(device)"
          :device="device"
          :is-mock="isMock(device)"
          @click="(p) => emit('device-click', p)"
          @heartbeat="(id) => emit('heartbeat', id)"
          @settings="(d) => emit('settings', d)"
        />
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="devices.length === 0" class="zone-detail-view__empty">
      <p>Keine Geräte in dieser Zone.</p>
      <p class="text-sm">Ziehe Geräte hierher, um sie zuzuweisen.</p>
    </div>
  </div>
</template>

<style scoped>
.zone-detail-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  background: linear-gradient(180deg, var(--color-bg-level-2), rgba(13, 13, 22, 0.8));
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  min-height: 300px;
}

/* Back Navigation Strip */
.zone-detail-view__nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  margin-bottom: var(--space-1);
}

.zone-detail-view__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: var(--text-sm);
  font-weight: 500;
}

.zone-detail-view__back:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-light);
  transform: translateX(-2px);
}

.zone-detail-view__back-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.zone-detail-view__nav-sep {
  color: var(--color-text-muted);
  opacity: 0.4;
}

.zone-detail-view__nav-current {
  color: var(--color-text-primary);
  font-weight: 600;
}

/* Header */
.zone-detail-view__header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.zone-detail-view__title {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  position: relative;
  padding-bottom: 6px;
}

/* Iridescent underline accent */
.zone-detail-view__title::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 60px;
  height: 2px;
  background: var(--gradient-iridescent);
  border-radius: 1px;
}

.zone-detail-view__meta {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  display: flex;
  gap: var(--space-1);
}

.zone-detail-view__cross-esp-badge {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-accent-bright);
  background: rgba(96, 165, 250, 0.08);
  border: 1px solid rgba(96, 165, 250, 0.15);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.zone-detail-view__cross-esp-badge:hover {
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-iridescent-2);
}

/* Device grids */
.zone-detail-view__grid {
  gap: var(--space-4);
}

.zone-detail-view__unsubzoned {
  margin-top: var(--space-2);
}

/* Empty state */
.zone-detail-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
  text-align: center;
  color: var(--color-text-muted);
  background: var(--glass-bg);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.zone-detail-view__empty p {
  margin: 0;
}

.zone-detail-view__empty .text-sm {
  font-size: var(--text-sm);
  opacity: 0.7;
  margin-top: var(--space-2);
}

/* Mobile */
@media (max-width: 640px) {
  .zone-detail-view {
    padding: var(--space-4);
  }

  .zone-detail-view__header {
    flex-direction: column;
    gap: var(--space-1);
  }

  .zone-detail-view__cross-esp-badge {
    margin-left: 0;
  }

  .zone-detail-view__grid {
    grid-template-columns: 1fr;
  }
}
</style>
