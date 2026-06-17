<script setup lang="ts">
/**
 * ZoneAssignmentDropdown Component
 *
 * Alternative to drag & drop for zone assignment.
 * Compact dropdown showing current zone with option to change.
 * Uses existing useZoneDragDrop composable for API calls + undo/redo.
 */

import { computed } from 'vue'
import { MapPin } from 'lucide-vue-next'
import type { ESPDevice } from '@/api/esp'

interface ZoneOption {
  zoneId: string
  zoneName: string
}

interface Props {
  /** The ESP device to assign */
  device: ESPDevice
  /** Available zones to choose from */
  zones: ZoneOption[]
  /** Disable interaction */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  /** Emitted when zone selection changes */
  (e: 'zone-changed', deviceId: string, zoneId: string | null): void
}>()

const currentZoneName = computed(() => {
  if (!props.device.zone_id) return 'Nicht zugewiesen'
  const match = props.zones.find(z => z.zoneId === props.device.zone_id)
  return match?.zoneName ?? props.device.zone_name ?? props.device.zone_id
})

const deviceId = computed(() => props.device.device_id || props.device.esp_id || '')

function handleSelect(event: Event) {
  const target = event.target as HTMLSelectElement
  const value = target.value

  if (value === '__remove__') {
    emit('zone-changed', deviceId.value, null)
  } else if (value && value !== props.device.zone_id) {
    emit('zone-changed', deviceId.value, value)
  }

  // Reset select to current value (actual state update comes from parent)
  target.value = props.device.zone_id || ''
}
</script>

<template>
  <div
    class="zone-dropdown"
    :class="{ 'zone-dropdown--disabled': disabled }"
  >
    <MapPin class="zone-dropdown__icon" />
    <select
      class="zone-dropdown__select"
      :value="device.zone_id || ''"
      :disabled="disabled"
      :title="`Zone: ${currentZoneName}`"
      aria-label="Zone zuweisen"
      @change="handleSelect"
    >
      <option value="" disabled>
        Nicht zugewiesen
      </option>
      <option
        v-for="zone in zones"
        :key="zone.zoneId"
        :value="zone.zoneId"
      >
        {{ zone.zoneName }}
      </option>
      <option v-if="device.zone_id" value="__remove__">
        — Aus Zone entfernen
      </option>
    </select>
  </div>
</template>

<style scoped>
.zone-dropdown {
  display: flex;
  align-items: center;
  gap: 4px;
  max-width: 180px;
}

.zone-dropdown--disabled {
  opacity: 0.5;
  pointer-events: none;
}

.zone-dropdown__icon {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.zone-dropdown__select {
  flex: 1;
  min-width: 0;
  padding: 2px 4px;
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  appearance: none;
  -webkit-appearance: none;

  /* Truncate long zone names */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.zone-dropdown__select:hover {
  border-color: var(--glass-border);
  background: var(--color-bg-tertiary);
}

.zone-dropdown__select:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-tertiary);
}

.zone-dropdown__select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  padding: var(--space-1);
}
</style>
