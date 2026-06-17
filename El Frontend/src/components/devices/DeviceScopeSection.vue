<script setup lang="ts">
/**
 * DeviceScopeSection — Reusable device scope selector
 *
 * Used in SensorConfigPanel and ActuatorConfigPanel.
 * Allows configuring how a device relates to zones:
 * - zone_local (default): belongs to exactly one zone
 * - multi_zone: serves multiple zones (e.g., nutrient pump in tech room)
 * - mobile: physically moved between zones (e.g., handheld meter)
 *
 * For multi_zone/mobile: shows zone checkbox list + active zone dropdown.
 * Active zone change is immediate (API call), not deferred to Save.
 */

import { computed, watch } from 'vue'
import { Info } from 'lucide-vue-next'
import { deviceContextApi } from '@/api/device-context'
import { useToast } from '@/composables/useToast'
import type { DeviceScope, ZoneEntity } from '@/types'

interface Props {
  configId: string | null
  configType: 'sensor' | 'actuator'
  modelValue: DeviceScope
  assignedZones: string[]
  activeZoneId: string | null
  availableZones: ZoneEntity[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: DeviceScope]
  'update:assignedZones': [value: string[]]
  'update:activeZoneId': [value: string | null]
}>()

const toast = useToast()

const SCOPE_OPTIONS: { value: DeviceScope; label: string }[] = [
  { value: 'zone_local', label: 'Lokal' },
  { value: 'multi_zone', label: 'Multi-Zone' },
  { value: 'mobile', label: 'Mobil' },
]

const showZoneConfig = computed(() =>
  props.modelValue === 'multi_zone' || props.modelValue === 'mobile',
)

/** Only assigned zones are valid options for active zone dropdown */
const activeZoneOptions = computed(() =>
  props.availableZones.filter(z => props.assignedZones.includes(z.zone_id)),
)

function handleScopeChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as DeviceScope
  emit('update:modelValue', value)

  // Reset assigned zones when switching back to zone_local
  if (value === 'zone_local') {
    emit('update:assignedZones', [])
  }
}

function handleZoneToggle(zoneId: string, checked: boolean) {
  const current = [...props.assignedZones]
  if (checked && !current.includes(zoneId)) {
    current.push(zoneId)
  } else if (!checked) {
    const idx = current.indexOf(zoneId)
    if (idx !== -1) current.splice(idx, 1)
  }
  emit('update:assignedZones', current)
}

/** Active zone change is immediate — fires API call right away */
async function handleActiveZoneChange(event: Event) {
  const newZoneId = (event.target as HTMLSelectElement).value || null
  if (!props.configId) {
    toast.error('Sensor/Aktor muss zuerst gespeichert werden')
    return
  }
  try {
    await deviceContextApi.setContext(props.configType, props.configId, {
      active_zone_id: newZoneId,
    })
    emit('update:activeZoneId', newZoneId)
    toast.success('Aktive Zone gewechselt')
  } catch {
    toast.error('Aktive Zone konnte nicht gewechselt werden')
  }
}

// When assigned zones change, clear active zone if it's no longer in the list
watch(() => props.assignedZones, (zones) => {
  if (props.activeZoneId && !zones.includes(props.activeZoneId)) {
    emit('update:activeZoneId', null)
  }
})
</script>

<template>
  <div class="device-scope">
    <!-- Scope Selector -->
    <div class="device-scope__field">
      <label class="device-scope__label">Geräte-Scope</label>
      <select
        class="device-scope__select"
        :value="modelValue"
        :disabled="disabled"
        @change="handleScopeChange"
      >
        <option v-for="opt in SCOPE_OPTIONS" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
    </div>

    <!-- Zone configuration (only for multi_zone / mobile) -->
    <template v-if="showZoneConfig">
      <!-- Assigned Zones Checkboxes -->
      <div class="device-scope__field">
        <label class="device-scope__label">Zugewiesene Zonen</label>
        <div class="device-scope__zone-list">
          <label
            v-for="zone in availableZones"
            :key="zone.zone_id"
            class="device-scope__zone-item"
          >
            <input
              type="checkbox"
              :checked="assignedZones.includes(zone.zone_id)"
              :disabled="disabled"
              class="device-scope__checkbox"
              @change="handleZoneToggle(zone.zone_id, ($event.target as HTMLInputElement).checked)"
            />
            <span class="device-scope__zone-name">{{ zone.name }}</span>
          </label>
          <p v-if="availableZones.length === 0" class="device-scope__empty">
            Keine aktiven Zonen vorhanden
          </p>
        </div>
      </div>

      <!-- Active Zone Dropdown (immediate change) -->
      <div class="device-scope__field">
        <label class="device-scope__label">Aktuell aktiv</label>
        <select
          class="device-scope__select"
          :value="activeZoneId ?? ''"
          :disabled="disabled || !configId || activeZoneOptions.length === 0"
          @change="handleActiveZoneChange"
        >
          <option value="">— Keine aktive Zone —</option>
          <option
            v-for="zone in activeZoneOptions"
            :key="zone.zone_id"
            :value="zone.zone_id"
          >
            {{ zone.name }}
          </option>
        </select>
        <p class="device-scope__hint">
          <Info class="w-3 h-3" />
          Aktive Zone wird sofort gewechselt (ohne Speichern)
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.device-scope {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.device-scope__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.device-scope__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.device-scope__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.device-scope__select:focus {
  border-color: var(--color-accent);
}

.device-scope__select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.device-scope__zone-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  max-height: 200px;
  overflow-y: auto;
}

.device-scope__zone-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  cursor: pointer;
  font-size: var(--text-sm);
}

.device-scope__checkbox {
  accent-color: var(--color-accent);
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.device-scope__zone-name {
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-scope__empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  margin: 0;
}

.device-scope__hint {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  margin: 0;
}
</style>
