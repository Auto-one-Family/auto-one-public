<script setup lang="ts">
/**
 * SubzonePlantPanel — Plant context for a subzone (AUT-252 Section C)
 *
 * Shows the active plant profile assigned to a subzone. Opened from
 * ZonePlate (HardwareView) via the leaf icon in the subzone hover actions.
 *
 * Soft-delete safe: filters out plants with `deleted_at != null`.
 */

import { computed, onMounted } from 'vue'
import { Leaf } from 'lucide-vue-next'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { EmptyState } from '@/shared/design/patterns'
import BaseSkeleton from '@/shared/design/primitives/BaseSkeleton.vue'
import PlantDetailPanel from '@/components/plants/PlantDetailPanel.vue'
import type { Plant } from '@/types'

interface Props {
  subzoneId: string
  subzoneName: string
}

const props = defineProps<Props>()

const plantsStore = usePlantsStore()

/** Active plant for this subzone (soft-delete safe). */
const activePlant = computed<Plant | null>(() => {
  return (
    plantsStore.plants.find(
      (p) => p.subzone_id === props.subzoneId && !p.deleted_at,
    ) ?? null
  )
})

onMounted(async () => {
  if (plantsStore.plants.length === 0) {
    await plantsStore.fetchPlants()
  }
})
</script>

<template>
  <div class="subzone-plant-panel">
    <div class="subzone-plant-panel__header">
      <Leaf class="subzone-plant-panel__icon" />
      <span class="subzone-plant-panel__title">{{ subzoneName }}</span>
    </div>

    <BaseSkeleton v-if="plantsStore.isLoading" text="Lade Pflanzendaten..." />

    <EmptyState
      v-else-if="!activePlant"
      :icon="Leaf"
      title="Kein aktives Pflanzenprofil"
      description="Dieser Subzone ist keine aktive Pflanze zugewiesen."
      :show-action="false"
    />

    <PlantDetailPanel
      v-else
      :plant="activePlant"
    />
  </div>
</template>

<style scoped>
.subzone-plant-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.subzone-plant-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.subzone-plant-panel__icon {
  width: 16px;
  height: 16px;
  color: var(--color-success);
  flex-shrink: 0;
}

.subzone-plant-panel__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}
</style>
