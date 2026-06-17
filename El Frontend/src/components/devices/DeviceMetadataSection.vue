<script setup lang="ts">
/**
 * DeviceMetadataSection — Reusable metadata form for sensor/actuator config panels
 *
 * Three visual groups:
 * 1. Manufacturer & Product (manufacturer, model, datasheet_url, serial_number)
 * 2. Installation & Maintenance (dates, location, interval, next maintenance)
 * 3. Notes (free text)
 *
 * Emits update:metadata for v-model:metadata binding.
 */
import { computed } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import type { DeviceMetadata } from '@/types/device-metadata'
import { getNextMaintenanceDate, isMaintenanceOverdue } from '@/types/device-metadata'

interface Props {
  metadata: DeviceMetadata
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:metadata': [metadata: DeviceMetadata]
}>()

const nextMaintenance = computed(() => getNextMaintenanceDate(props.metadata))
const maintenanceOverdue = computed(() => isMaintenanceOverdue(props.metadata))

const nextMaintenanceDisplay = computed(() => {
  if (!nextMaintenance.value) return null
  return nextMaintenance.value.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
})

function update<K extends keyof DeviceMetadata>(field: K, value: DeviceMetadata[K]) {
  emit('update:metadata', { ...props.metadata, [field]: value })
}

function onInput(field: keyof DeviceMetadata, event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  update(field, target.value)
}

function onNumberInput(field: keyof DeviceMetadata, event: Event) {
  const target = event.target as HTMLInputElement
  const val = target.value ? Number(target.value) : undefined
  update(field, val as DeviceMetadata[keyof DeviceMetadata])
}
</script>

<template>
  <div class="device-metadata">
    <!-- Group 1: Manufacturer & Product -->
    <div class="device-metadata__group">
      <h4 class="device-metadata__group-title">Hersteller & Produkt</h4>
      <div class="device-metadata__row">
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Hersteller</label>
          <input
            class="device-metadata__input"
            :value="metadata.manufacturer"
            placeholder="z.B. Sensirion, Dallas"
            @input="onInput('manufacturer', $event)"
          />
        </div>
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Modell</label>
          <input
            class="device-metadata__input"
            :value="metadata.model"
            placeholder="z.B. SHT31, DS18B20"
            @input="onInput('model', $event)"
          />
        </div>
      </div>
      <div class="device-metadata__row">
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Datenblatt-URL</label>
          <input
            class="device-metadata__input"
            type="url"
            :value="metadata.datasheet_url"
            placeholder="https://..."
            @input="onInput('datasheet_url', $event)"
          />
        </div>
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Seriennummer</label>
          <input
            class="device-metadata__input"
            :value="metadata.serial_number"
            placeholder="Optional"
            @input="onInput('serial_number', $event)"
          />
        </div>
      </div>
      <div class="device-metadata__row">
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Firmware-Version</label>
          <input
            class="device-metadata__input"
            :value="metadata.firmware_version"
            placeholder="z.B. 1.2.3"
            @input="onInput('firmware_version', $event)"
          />
        </div>
        <div class="device-metadata__field device-metadata__field--half" />
      </div>
    </div>

    <!-- Group 2: Installation & Maintenance -->
    <div class="device-metadata__group">
      <h4 class="device-metadata__group-title">Installation & Wartung</h4>
      <div class="device-metadata__row">
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Installationsdatum</label>
          <input
            class="device-metadata__input"
            type="date"
            :value="metadata.installation_date"
            @input="onInput('installation_date', $event)"
          />
        </div>
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Einbauort</label>
          <input
            class="device-metadata__input"
            :value="metadata.installation_location"
            placeholder="z.B. Gewächshaus A, Rack 3"
            @input="onInput('installation_location', $event)"
          />
        </div>
      </div>
      <div class="device-metadata__row">
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Letzte Wartung</label>
          <input
            class="device-metadata__input"
            type="date"
            :value="metadata.last_maintenance"
            @input="onInput('last_maintenance', $event)"
          />
        </div>
        <div class="device-metadata__field device-metadata__field--half">
          <label class="device-metadata__label">Wartungsintervall (Tage)</label>
          <input
            class="device-metadata__input"
            type="number"
            min="0"
            :value="metadata.maintenance_interval_days"
            placeholder="z.B. 90"
            @input="onNumberInput('maintenance_interval_days', $event)"
          />
        </div>
      </div>

      <!-- Next maintenance (computed, read-only) -->
      <div v-if="nextMaintenanceDisplay" class="device-metadata__maintenance-info">
        <AlertTriangle
          v-if="maintenanceOverdue"
          class="w-4 h-4 text-warning-400"
        />
        <span :class="maintenanceOverdue ? 'device-metadata__maintenance--overdue' : ''">
          Nächste Wartung: {{ nextMaintenanceDisplay }}
          <template v-if="maintenanceOverdue"> (überfällig)</template>
        </span>
      </div>
    </div>

    <!-- Group 3: Notes -->
    <div class="device-metadata__group">
      <h4 class="device-metadata__group-title">Notizen</h4>
      <div class="device-metadata__field">
        <textarea
          class="device-metadata__input device-metadata__textarea"
          :value="metadata.notes"
          rows="3"
          placeholder="Freitext-Notizen zum Gerät..."
          @input="onInput('notes', $event)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.device-metadata {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.device-metadata__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.device-metadata__group-title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.device-metadata__row {
  display: flex;
  gap: var(--space-3);
}

.device-metadata__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.device-metadata__field--half {
  flex: 1;
  min-width: 0;
}

.device-metadata__label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.device-metadata__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-family: var(--font-body);
  transition: border-color var(--transition-fast);
}

.device-metadata__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.device-metadata__input::placeholder {
  color: var(--color-text-muted);
}

.device-metadata__textarea {
  resize: vertical;
  min-height: 60px;
}

.device-metadata__maintenance-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
  border-radius: var(--radius-sm);
}

.device-metadata__maintenance--overdue {
  color: var(--color-warning);
  font-weight: 500;
}
</style>
