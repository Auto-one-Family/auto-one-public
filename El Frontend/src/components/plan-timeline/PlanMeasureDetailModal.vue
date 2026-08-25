<script setup lang="ts">
/**
 * Read-only detail dialog for a planned plant measure on the Zeitstrahl.
 */

import { computed } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import BaseBadge from '@/shared/design/primitives/BaseBadge.vue'
import type { PlanMeasureMarker } from '@/components/plan-timeline/planMeasureMarkers'
import { getPlantEventStatusLabel, getPlantPhaseLabel } from '@/components/plants/plantLabels'
import { formatDateTime } from '@/utils/formatters'
import type { PlantEventStatus } from '@/types'

interface Props {
  open: boolean
  marker: PlanMeasureMarker | null
  plantLabel?: string | null
  batchLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  plantLabel: null,
  batchLabel: null,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const statusLabel = computed(() => {
  if (!props.marker) return null
  return getPlantEventStatusLabel(props.marker.eventStatus as PlantEventStatus)
})

function close(): void {
  emit('update:open', false)
}
</script>

<template>
  <BaseModal
    :open="open"
    title="Maßnahme"
    max-width="max-w-md"
    @update:open="emit('update:open', $event)"
  >
    <div v-if="marker" class="measure-detail">
      <div class="measure-detail__row">
        <span class="measure-detail__key">Art</span>
        <span class="measure-detail__value">{{ marker.label }}</span>
      </div>
      <div class="measure-detail__row">
        <span class="measure-detail__key">Status</span>
        <span class="measure-detail__value">
          <BaseBadge v-if="statusLabel" variant="warning">
            {{ statusLabel }}
          </BaseBadge>
          <span v-else>Eingetragen</span>
        </span>
      </div>
      <div class="measure-detail__row">
        <span class="measure-detail__key">Zeitpunkt</span>
        <span class="measure-detail__value">
          {{ formatDateTime(new Date(marker.timestampMs).toISOString()) }}
        </span>
      </div>
      <div v-if="marker.windowStartMs && marker.windowEndMs" class="measure-detail__row">
        <span class="measure-detail__key">Zeitraum</span>
        <span class="measure-detail__value">
          {{ formatDateTime(new Date(marker.windowStartMs).toISOString()) }}
          –
          {{ formatDateTime(new Date(marker.windowEndMs).toISOString()) }}
        </span>
      </div>
      <div v-if="marker.phase" class="measure-detail__row">
        <span class="measure-detail__key">Phase</span>
        <span class="measure-detail__value">{{ getPlantPhaseLabel(marker.phase) }}</span>
      </div>
      <div v-if="marker.zoneId" class="measure-detail__row">
        <span class="measure-detail__key">Zone</span>
        <span class="measure-detail__value">{{ marker.zoneId }}</span>
      </div>
      <div v-if="plantLabel" class="measure-detail__row">
        <span class="measure-detail__key">Pflanze</span>
        <span class="measure-detail__value">{{ plantLabel }}</span>
      </div>
      <div v-if="batchLabel" class="measure-detail__row">
        <span class="measure-detail__key">Batch</span>
        <span class="measure-detail__value">{{ batchLabel }}</span>
      </div>
      <div class="measure-detail__row measure-detail__row--block">
        <span class="measure-detail__key">Notiz</span>
        <p class="measure-detail__notes">
          {{ marker.notes?.trim() || '—' }}
        </p>
      </div>
      <div class="measure-detail__actions">
        <button
          type="button"
          class="measure-detail__close"
          aria-label="Dialog schließen"
          @click="close"
        >
          Schließen
        </button>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.measure-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.measure-detail__row {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: var(--space-2);
  align-items: start;
}

.measure-detail__row--block {
  grid-template-columns: 1fr;
}

.measure-detail__key {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.measure-detail__value {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.measure-detail__notes {
  margin: 0;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: pre-wrap;
}

.measure-detail__actions {
  display: flex;
  justify-content: flex-end;
}

.measure-detail__close {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.measure-detail__close:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.03);
}
</style>
