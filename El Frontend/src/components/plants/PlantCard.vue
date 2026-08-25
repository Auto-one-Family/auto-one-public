<script setup lang="ts">
/**
 * PlantCard — compact draggable plant tile for the structure / D&D view.
 *
 * Used inside PlantSubzoneArea in PlantsView structure mode (AUT-1160 C2).
 * Visual pattern: same glass panel / hover-lift as DeviceSummaryCard /
 * UnassignedDropBar device cards.
 */

import { computed } from 'vue'
import { Sprout } from 'lucide-vue-next'
import type { Plant } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

interface Props {
  plant: Plant
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'open', plant: Plant): void
}>()

const ageDays = computed((): number | null => {
  if (!props.plant.planting_date) return null
  const planted = Date.parse(props.plant.planting_date)
  if (Number.isNaN(planted)) return null
  return Math.max(0, Math.floor((Date.now() - planted) / (1000 * 60 * 60 * 24)))
})

const phaseLabel = computed(() => PLANT_PHASE_LABELS[props.plant.phase] ?? props.plant.phase)

function handleClick(): void {
  emit('open', props.plant)
}
</script>

<template>
  <div class="plant-card" @click="handleClick">
    <div class="plant-card__header">
      <Sprout class="plant-card__icon" />
      <span class="plant-card__qr">{{ plant.qr_code || '—' }}</span>
    </div>
    <div class="plant-card__genotype" :title="plant.genotype_label">
      {{ plant.genotype_label }}
    </div>
    <div class="plant-card__meta">
      <span class="plant-card__phase">{{ phaseLabel }}</span>
      <span v-if="ageDays !== null" class="plant-card__age">{{ ageDays }}d</span>
    </div>
  </div>
</template>

<style scoped>
.plant-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: grab;
  transition: all var(--transition-fast);
  min-height: 80px;
  user-select: none;
}

.plant-card:hover {
  border-color: var(--color-accent-dim);
  background: var(--color-bg-secondary);
  transform: translateY(-1px);
  box-shadow: var(--elevation-raised);
}

.plant-card:active {
  cursor: grabbing;
  transform: none;
}

/* Touch: always show clickable affordance */
@media (hover: none) {
  .plant-card {
    border-color: var(--color-accent-dim);
  }
}

.plant-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.plant-card__icon {
  width: 12px;
  height: 12px;
  color: var(--color-success);
  flex-shrink: 0;
}

.plant-card__qr {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plant-card__genotype {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plant-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: auto;
}

.plant-card__phase {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  padding: 1px var(--space-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.plant-card__age {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}
</style>
