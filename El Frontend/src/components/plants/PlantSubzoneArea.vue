<script setup lang="ts">
/**
 * PlantSubzoneArea — subzone container with VueDraggable for plant tiles.
 *
 * Same visual philosophy as SubzoneArea.vue (AUT-252): glass panel,
 * 2px accent left border, MapPin header, count badge.
 * Adapted for Plant entities: renders PlantCard tiles instead of device cards,
 * acts as a VueDraggable drop target for cross-subzone plant moves.
 *
 * Parent (PlantsView) handles the actual API call via 'plant-dropped' emit.
 *
 * AUT-1160 C2 — genestete Darstellung + Drag & Drop.
 */

import { ref, watch } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { MapPin } from 'lucide-vue-next'
import type { Plant } from '@/types'
import PlantCard from './PlantCard.vue'

interface Props {
  /** null = "Zone-weit" / "Ohne Subzone" group */
  subzoneId: string | null
  subzoneName: string
  /** null = "Ohne Zone" group */
  zoneId: string | null
  plants: Plant[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'plant-dropped', payload: {
    plant: Plant
    toSubzoneId: string | null
    toZoneId: string | null
    toSubzoneName: string
  }): void
  (e: 'open-plant', plant: Plant): void
}>()

// Sync local copy from props (same pattern as UnassignedDropBar.localDevices)
const localPlants = ref<Plant[]>([...props.plants])

watch(
  () => props.plants,
  (newPlants) => {
    localPlants.value = [...newPlants]
  },
  { deep: true },
)

function handleChange(event: {
  added?: { element: Plant; newIndex: number }
  removed?: { element: Plant; oldIndex: number }
  moved?: { element: Plant; newIndex: number; oldIndex: number }
}): void {
  // Only react to cross-list additions (the drop target receiving a plant)
  const added = event?.added
  if (!added) return

  emit('plant-dropped', {
    plant: added.element,
    toSubzoneId: props.subzoneId,
    toZoneId: props.zoneId,
    toSubzoneName: props.subzoneName,
  })
}

function handleOpenPlant(plant: Plant): void {
  emit('open-plant', plant)
}
</script>

<template>
  <div class="plant-subzone-area">
    <!-- Header: mirrors SubzoneArea.vue header structure -->
    <div class="plant-subzone-area__header">
      <MapPin class="plant-subzone-area__icon" />
      <span class="plant-subzone-area__label">{{ subzoneName }}</span>
      <span class="plant-subzone-area__count">{{ localPlants.length }}</span>
    </div>

    <!-- VueDraggable plant grid — group="plants" shared with all PlantSubzoneArea instances -->
    <VueDraggable
      v-model="localPlants"
      class="plant-subzone-area__grid"
      group="plants"
      :animation="150"
      ghost-class="plant-subzone-area__ghost"
      :force-fallback="true"
      :fallback-on-body="true"
      :delay-on-touch-only="true"
      :delay="300"
      :fallback-tolerance="5"
      :touch-start-threshold="3"
      @change="handleChange"
    >
      <PlantCard
        v-for="plant in localPlants"
        :key="plant.plant_id"
        :plant="plant"
        @open="handleOpenPlant"
      />

      <!-- Drop hint when empty -->
      <div v-if="localPlants.length === 0" class="plant-subzone-area__empty-hint">
        <MapPin class="w-3 h-3" />
        <span>Pflanzen hierher ziehen</span>
      </div>
    </VueDraggable>
  </div>
</template>

<style scoped>
/* SubzoneArea.vue visual parity: glass panel + left accent border */
.plant-subzone-area {
  background: var(--glass-bg-light, var(--glass-bg));
  border: 1px solid var(--glass-border);
  border-left: 2px solid var(--color-accent-dim);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

/* Header mirrors SubzoneArea.vue header */
.plant-subzone-area__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.plant-subzone-area__icon {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.plant-subzone-area__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  font-weight: 500;
  flex: 1;
}

.plant-subzone-area__count {
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

/* Grid: minmax(160px) so cards wrap nicely */
.plant-subzone-area__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-2);
  min-height: 64px;
}

/* Empty / drop hint */
.plant-subzone-area__empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  padding: var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  grid-column: 1 / -1;
  opacity: 0.5;
}

/* Ghost style during drag (global because VueDraggable adds class to body) */
:global(.plant-subzone-area__ghost) {
  opacity: 0.35;
  border-style: dashed;
}
</style>
