<script setup lang="ts">
/**
 * SubzoneArea Component
 *
 * Tinted background area within ZoneDetailView that visually groups
 * DeviceSummaryCards by subzone. Solid accent border left, MapPin icon,
 * device count badge.
 */

import { computed } from 'vue'
import type { ESPDevice } from '@/api/esp'
import { MapPin, Sprout } from 'lucide-vue-next'
import type { Plant } from '@/types'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

interface Props {
  subzoneId: string
  subzoneName: string
  devices: ESPDevice[]
}

const props = defineProps<Props>()

/**
 * AUT-252: Header-Klick oeffnet das Pflanzen-Panel (Wissensdatenbank-Vernetzung).
 * Konsumenten (z. B. ZoneDetailView) reagieren via @click="openSubzonePanel(subzoneId)".
 */
const emit = defineEmits<{
  (e: 'click'): void
}>()

// AUT-252 Sektion C: Pflanzenprofil-Chip im Header
// Liefert die der Subzone zugeordnete Pflanze (soft-deleted ausgeschlossen).
// Datenquelle: plantsStore (bereits in App geladen via Pflanzen-Tab/MultispeQ).
// Kein neues Side-Panel — nur visueller Hinweis.
const plantsStore = usePlantsStore()

const subzonePlant = computed<Plant | null>(() => {
  if (!props.subzoneId) return null
  const found = plantsStore.plants.find(
    (p) => p.subzone_id === props.subzoneId && !p.deleted_at,
  )
  return found ?? null
})

const plantPhaseLabel = computed<string>(() => {
  const plant = subzonePlant.value
  if (!plant) return ''
  return PLANT_PHASE_LABELS[plant.phase] ?? plant.phase
})

function handleHeaderClick(): void {
  emit('click')
}

function handleHeaderKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('click')
  }
}
</script>

<template>
  <div class="subzone-area">
    <div
      class="subzone-area__header subzone-area__header--clickable"
      role="button"
      tabindex="0"
      :aria-label="`Pflanzen-Detail fuer Subzone ${subzoneName} oeffnen`"
      @click="handleHeaderClick"
      @keydown="handleHeaderKeydown"
    >
      <MapPin class="subzone-area__icon" />
      <div class="subzone-area__label">{{ subzoneName }}</div>
      <!-- AUT-252 Sektion C: Pflanzenprofil-Chip (nur wenn Pflanze zugeordnet) -->
      <span
        v-if="subzonePlant"
        class="subzone-area__plant-chip"
        :title="`Pflanze: ${subzonePlant.genotype} — Phase: ${plantPhaseLabel}`"
      >
        <Sprout class="subzone-area__plant-chip-icon" aria-hidden="true" />
        <span class="subzone-area__plant-chip-name">{{ subzonePlant.genotype }}</span>
        <span class="subzone-area__plant-chip-phase">{{ plantPhaseLabel }}</span>
      </span>
      <span class="subzone-area__count">{{ devices.length }}</span>
    </div>
    <div class="subzone-area__grid grid-auto-sm">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.subzone-area {
  background: var(--glass-bg-light);
  border: 1px solid var(--glass-border);
  border-left: 2px solid var(--color-accent-dim);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.subzone-area__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

/* AUT-252: Klickbarer Header zum Oeffnen des Pflanzen-Panels */
.subzone-area__header--clickable {
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  margin: calc(-1 * var(--space-1)) calc(-1 * var(--space-2)) var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.subzone-area__header--clickable:hover {
  background: var(--glass-bg);
}

.subzone-area__header--clickable:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.subzone-area__icon {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.subzone-area__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  font-weight: 500;
  flex: 1;
}

.subzone-area__count {
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  padding: 1px 6px;
  flex-shrink: 0;
}

/* AUT-252 Sektion C: Pflanzenprofil-Chip im Header */
.subzone-area__plant-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 1px var(--space-2);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  flex-shrink: 0;
  max-width: 220px;
}

.subzone-area__plant-chip-icon {
  width: 12px;
  height: 12px;
  color: var(--color-success);
  flex-shrink: 0;
}

.subzone-area__plant-chip-name {
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.subzone-area__plant-chip-phase {
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--color-text-muted);
  font-size: 9px;
}

.subzone-area__grid {
  gap: var(--space-4);
}
</style>
