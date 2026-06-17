<script setup lang="ts">
/**
 * DeviceHeaderBar Component
 *
 * Level 3 header: Shows device identity, zone context, and back navigation.
 * Used at the top of DeviceDetailView for contextual information
 * that the embedded ESPOrbitalLayout doesn't provide.
 */

import { computed } from 'vue'
import type { ESPDevice } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { ArrowLeft, MapPin } from 'lucide-vue-next'

interface Props {
  device: ESPDevice
  zoneName: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'back'): void
}>()

const espStore = useEspStore()

const deviceId = computed(() => espStore.getDeviceId(props.device))
const displayName = computed(() => props.device.name || deviceId.value)
const isMock = computed(() => espStore.isMock(deviceId.value))
const subzoneName = computed(() => props.device.subzone_name || null)
</script>

<template>
  <div class="device-header-bar">
    <button
      class="device-header-bar__back"
      title="Zurück zur Zone"
      @click="emit('back')"
    >
      <ArrowLeft class="w-4 h-4" />
    </button>

    <div class="device-header-bar__info">
      <h2 class="device-header-bar__name">{{ displayName }}</h2>
      <div class="device-header-bar__location">
        <MapPin class="w-3 h-3" />
        <span>{{ zoneName }}</span>
        <span v-if="subzoneName"> — {{ subzoneName }}</span>
      </div>
    </div>

    <span class="device-header-bar__badge" :class="isMock ? 'badge--mock' : 'badge--real'">
      {{ isMock ? 'MOCK' : 'REAL' }}
    </span>
  </div>
</template>

<style scoped>
.device-header-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.device-header-bar__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.device-header-bar__back:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-light);
  transform: translateX(-2px);
}

.device-header-bar__info {
  flex: 1;
  min-width: 0;
}

.device-header-bar__name {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-header-bar__location {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.device-header-bar__location :deep(svg) {
  flex-shrink: 0;
}

.device-header-bar__badge {
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  font-weight: 600;
  flex-shrink: 0;
}

.badge--mock {
  color: var(--color-mock);
  background: rgba(167, 139, 250, 0.12);
}

.badge--real {
  color: var(--color-real);
  background: rgba(34, 211, 238, 0.12);
}
</style>
