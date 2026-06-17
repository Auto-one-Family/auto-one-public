<script setup lang="ts">
/**
 * DeviceDetailView Component
 *
 * Level 3: Full device detail layout. Wraps ESPOrbitalLayout in a
 * full-width container that solves the overflow bug by providing
 * unlimited vertical space.
 *
 * Adds:
 * - DeviceHeaderBar with zone context and back navigation
 * - Full-width CSS overrides (no max-width constraints)
 * - Cross-ESP connection overlay (only visible on Level 3)
 *
 * Strategy: Re-uses ESPOrbitalLayout (compact-mode="true") to preserve
 * all existing functionality (sensor/actuator modals, drag-drop, inline
 * editing, OneWire scanning) without duplicating 3,913 lines of code.
 * The layout differences (wider columns, unlimited scroll) are handled
 * by CSS overrides on the wrapper.
 */

import { defineAsyncComponent } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import type { ESPDevice } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useLogicStore } from '@/shared/stores/logic.store'
import ESPOrbitalLayout from './ESPOrbitalLayout.vue'

const CrossEspConnectionOverlay = defineAsyncComponent(
  () => import('@/components/dashboard/CrossEspConnectionOverlay.vue')
)

interface Props {
  device: ESPDevice
  zoneId: string
  zoneName: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'settings', device: ESPDevice): void
  (e: 'delete', deviceId: string): void
  (e: 'heartbeat', deviceId: string): void
  (e: 'name-updated', payload: { deviceId: string; name: string | null }): void
  (e: 'sensor-click', payload: { espId: string; gpio: number; sensorType: string; configId?: string }): void
  (e: 'actuator-click', payload: { espId: string; gpio: number }): void
}>()

const espStore = useEspStore()
const logicStore = useLogicStore()

function handleHeartbeat(device: ESPDevice) {
  emit('heartbeat', espStore.getDeviceId(device))
}

function handleDelete(device: ESPDevice) {
  emit('delete', espStore.getDeviceId(device))
}

function handleSettings(device: ESPDevice) {
  emit('settings', device)
}

function handleNameUpdated(payload: { deviceId: string; name: string | null }) {
  emit('name-updated', payload)
}

function handleSensorClick(payload: { configId?: string; gpio: number; sensorType: string }) {
  emit('sensor-click', { espId: espStore.getDeviceId(props.device), ...payload })
}

function handleActuatorClick(gpio: number) {
  emit('actuator-click', { espId: espStore.getDeviceId(props.device), gpio })
}
</script>

<template>
  <div class="device-detail-view">
    <button class="device-detail-view__back" @click="emit('back')">
      <ArrowLeft class="w-4 h-4" />
      <span>Zurück</span>
    </button>

    <!-- Cross-ESP Connection Overlay (only on Level 3) -->
    <div class="device-detail-view__content">
      <CrossEspConnectionOverlay
        v-if="logicStore.crossEspConnections.length > 0"
        :show="true"
        :show-labels="true"
      />

      <!-- ESPOrbitalLayout in compact mode, full-width -->
      <ESPOrbitalLayout
        :device="device"
        :show-connections="true"
        :compact-mode="true"
        @heartbeat="handleHeartbeat"
        @delete="handleDelete"
        @settings="handleSettings"
        @name-updated="handleNameUpdated"
        @sensor-click="handleSensorClick"
        @actuator-click="handleActuatorClick"
      />
    </div>
  </div>
</template>

<style scoped>
.device-detail-view {
  background: linear-gradient(180deg, var(--color-bg-level-3), var(--color-bg-tertiary));
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4) var(--space-4);
  width: min(100%, 1700px);
  max-width: 1700px;
  margin-inline: auto;
}

.device-detail-view__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  margin-bottom: var(--space-2);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast);
}

.device-detail-view__back:hover {
  color: var(--color-text-secondary);
  border-color: var(--glass-border-hover);
}

.device-detail-view__content {
  position: relative;
  width: 100%;
}

/* Orbital layout overrides for full-page detail view */
.device-detail-view__content :deep(.esp-horizontal-layout) {
  margin-inline: auto;
}

.device-detail-view__content :deep(.esp-info-compact) {
  min-height: auto;
  height: auto;
}

/* Orbit shape — wide flat ellipse. Direct x/y overrides bypass the 1.3/0.75 formula
   and let the orbit fill available horizontal space without vertical scroll.
   Width  = 2 * orbit-radius-x + 260px
   Height = 2 * orbit-radius-y + 260px */
@media (max-height: 720px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 330px;
    --orbit-radius-y: 120px;
  }
}

@media (min-height: 721px) and (max-height: 780px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 380px;
    --orbit-radius-y: 135px;
  }
}

@media (min-height: 781px) and (max-height: 860px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 430px;
    --orbit-radius-y: 150px;
  }
}

@media (min-height: 861px) and (max-height: 960px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 470px;
    --orbit-radius-y: 165px;
  }
}

@media (min-height: 961px) and (max-width: 1700px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 510px;
    --orbit-radius-y: 182px;
  }
}

@media (min-width: 1701px) and (min-height: 961px) {
  .device-detail-view__content :deep(.esp-horizontal-layout) {
    --orbit-radius-x: 590px;
    --orbit-radius-y: 210px;
  }
}

@media (max-width: 1200px) {
  .device-detail-view {
    width: 100%;
    padding: var(--space-3);
  }
}
</style>
