<script setup lang="ts">
/**
 * PlantsView — Pflanzen-Inventar
 *
 * Standalone top-level view for the plant inventory (AUT-1159).
 * Structure-only: Zone → Subzone → PlantCard with VueDraggable (AUT-1160).
 * Tank / Bilanz / Vorfall gehören nicht hierher (Nährlösungs-Tab).
 *
 * Route: /plants
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sprout, Plus, X, Undo2, Redo2 } from 'lucide-vue-next'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useEspStore } from '@/stores/esp'
import { usePlantDragDrop } from '@/composables/usePlantDragDrop'
import { PLANT_PHASES, type Plant } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import {
  TANK_DETAIL_QUERY_KEY,
  tankDetailHref,
} from '@/components/plants/tankIstSollFormat'
import PlantDetailPanel from '@/components/plants/PlantDetailPanel.vue'
import PlantCreateModal from '@/components/plants/PlantCreateModal.vue'
import PlantBatchCreateModal from '@/components/plants/PlantBatchCreateModal.vue'
import PlantSubzoneArea from '@/components/plants/PlantSubzoneArea.vue'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()

const plantsStore = usePlantsStore()
const zoneStore = useZoneStore()
const espStore = useEspStore()
const toast = useToast()
const plantDragDrop = usePlantDragDrop()

/** Legacy `/plants?tank=` bookmarks → Nährlösungs-Detail. */
function redirectLegacyTankQuery(): void {
  const raw = route.query[TANK_DETAIL_QUERY_KEY]
  const tankId = Array.isArray(raw) ? raw[0] : raw
  if (typeof tankId === 'string' && tankId.length > 0) {
    void router.replace(tankDetailHref(tankId))
  }
}

watch(
  () => route.query[TANK_DETAIL_QUERY_KEY],
  () => {
    redirectLegacyTankQuery()
  },
  { immediate: true },
)

// =============================================================================
// Filters
// =============================================================================
const plantZoneFilter = ref<string>('')
const plantPhaseFilter = ref<string>('')
const plantBatchFilter = ref<string>('')

const plantZoneOptions = computed(() => zoneStore.activeZones)

/** Distinct batches present in the full plant list (for the charge select). */
const availableBatches = computed((): string[] => {
  const seen = new Set<string>()
  const result: string[] = []
  for (const p of plantsStore.plants) {
    const b = p.batch_label?.trim()
    if (b && !seen.has(b)) {
      seen.add(b)
      result.push(b)
    }
  }
  return result.sort()
})

const filteredPlants = computed<Plant[]>(() => {
  let list = plantsStore.plants
  if (plantZoneFilter.value) {
    list = list.filter((p) => p.parent_zone_id === plantZoneFilter.value)
  }
  if (plantPhaseFilter.value) {
    list = list.filter((p) => p.phase === plantPhaseFilter.value)
  }
  if (plantBatchFilter.value) {
    list = list.filter((p) => p.batch_label === plantBatchFilter.value)
  }
  return list
})

const hasAnyPlants = computed(() => plantsStore.plants.length > 0)
const hasFilteredResults = computed(() => filteredPlants.value.length > 0)
const hasActiveFilters = computed(
  () => !!(plantZoneFilter.value || plantPhaseFilter.value || plantBatchFilter.value),
)

function resetPlantFilters(): void {
  plantZoneFilter.value = ''
  plantPhaseFilter.value = ''
  plantBatchFilter.value = ''
}

// =============================================================================
// Structure: nested Zone → Subzone grouping
// =============================================================================

interface PlantSubzoneGroup {
  subzoneId: string | null
  subzoneName: string
  plants: Plant[]
}

interface PlantZoneSection {
  zoneId: string | null
  zoneName: string
  subzoneGroups: PlantSubzoneGroup[]
  zonewidePlants: Plant[]
}

/**
 * Build zone/subzone sections from filteredPlants.
 *   zone + subzone  → named zone section, named subzone group
 *   zone + no sub   → named zone section, "Zone-weit"
 *   no zone + sub   → "Ohne Zone", named subzone group
 *   no zone + no sub → "Ohne Zone", "Kein Ort zugewiesen"
 */
const plantZoneSections = computed((): PlantZoneSection[] => {
  const sectionMap = new Map<string | null, PlantZoneSection>()

  for (const zone of zoneStore.activeZones) {
    sectionMap.set(zone.zone_id, {
      zoneId: zone.zone_id,
      zoneName: zone.name,
      subzoneGroups: [],
      zonewidePlants: [],
    })
  }

  sectionMap.set(null, {
    zoneId: null,
    zoneName: 'Ohne Zone',
    subzoneGroups: [],
    zonewidePlants: [],
  })

  for (const plant of filteredPlants.value) {
    const zoneId = plant.parent_zone_id ?? null

    if (zoneId !== null && !sectionMap.has(zoneId)) {
      sectionMap.set(zoneId, {
        zoneId,
        zoneName: plant.zone_name ?? 'Ort ohne Namen',
        subzoneGroups: [],
        zonewidePlants: [],
      })
    }

    const section = sectionMap.get(zoneId)!

    if (!plant.subzone_id) {
      section.zonewidePlants.push(plant)
    } else {
      const existing = section.subzoneGroups.find((g) => g.subzoneId === plant.subzone_id)
      if (existing) {
        existing.plants.push(plant)
      } else {
        section.subzoneGroups.push({
          subzoneId: plant.subzone_id,
          subzoneName: plant.subzone_name ?? 'Ort ohne Namen',
          plants: [plant],
        })
      }
    }
  }

  for (const section of sectionMap.values()) {
    section.subzoneGroups.sort((a, b) =>
      (a.subzoneName ?? '').localeCompare(b.subzoneName ?? ''),
    )
  }

  const sections = Array.from(sectionMap.values()).filter(
    (s) => s.subzoneGroups.length > 0 || s.zonewidePlants.length > 0,
  )
  sections.sort((a, b) => {
    if (a.zoneId === null) return 1
    if (b.zoneId === null) return -1
    return (a.zoneName ?? '').localeCompare(b.zoneName ?? '')
  })

  return sections
})

async function handlePlantDropped(payload: {
  plant: Plant
  toSubzoneId: string | null
  toZoneId: string | null
  toSubzoneName: string
}): Promise<void> {
  await plantDragDrop.handlePlantSubzoneChange(
    payload.plant,
    payload.toSubzoneId,
    payload.toZoneId,
    payload.toSubzoneName,
  )
}

// =============================================================================
// Detail Panel
// =============================================================================
const isPlantDetailOpen = ref(false)
const selectedPlant = ref<Plant | null>(null)

function openPlantPanel(plant: Plant): void {
  selectedPlant.value = plant
  isPlantDetailOpen.value = true
}

function closePlantPanel(): void {
  isPlantDetailOpen.value = false
}

// =============================================================================
// Create Modal (single)
// =============================================================================
const showCreatePlantModal = ref(false)

function openCreatePlantModal(): void {
  showCreatePlantModal.value = true
}

async function onPlantCreated(plantId: string): Promise<void> {
  await plantsStore.fetchPlants()
  const created = plantsStore.plants.find((p) => p.plant_id === plantId)
  if (created) openPlantPanel(created)
}

// =============================================================================
// Batch Create Modal
// =============================================================================
const showBatchCreateModal = ref(false)

function openBatchCreateModal(): void {
  showBatchCreateModal.value = true
}

async function onBatchCreated(count: number): Promise<void> {
  await plantsStore.fetchPlants()
  toast.success(`${count} Pflanzen im Inventar`)
}

onMounted(() => {
  if (plantsStore.plants.length === 0 && !plantsStore.isLoading) {
    void plantsStore.fetchPlants()
  }
  if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
    void zoneStore.fetchZoneEntities()
  }
  if (espStore.devices.length === 0) {
    void espStore.fetchAll()
  }
})
</script>

<template>
  <div class="plants-view">
    <div class="plants-header">
      <h1 class="plants-header__title">
        <Sprout class="w-5 h-5" />
        Pflanzen-Inventar
      </h1>

      <div class="plants-header__actions">
        <button
          type="button"
          class="plants-btn plants-btn--ghost plants-btn--icon"
          :disabled="!plantDragDrop.canUndo.value"
          title="Rückgängig"
          aria-label="Rückgängig"
          @click="plantDragDrop.undo()"
        >
          <Undo2 class="w-4 h-4" />
        </button>
        <button
          type="button"
          class="plants-btn plants-btn--ghost plants-btn--icon"
          :disabled="!plantDragDrop.canRedo.value"
          title="Wiederherstellen"
          aria-label="Wiederherstellen"
          @click="plantDragDrop.redo()"
        >
          <Redo2 class="w-4 h-4" />
        </button>

        <button
          type="button"
          class="plants-btn plants-btn--ghost"
          @click="openBatchCreateModal"
        >
          <Plus class="w-4 h-4" />
          <span>N Pflanzen</span>
        </button>

        <button
          type="button"
          class="plants-btn plants-btn--primary"
          @click="openCreatePlantModal"
        >
          <Plus class="w-4 h-4" />
          <span>Neue Pflanze</span>
        </button>
      </div>
    </div>

    <div class="plants-filters">
      <label class="plants-filter">
        <span class="plants-filter__label">Zone</span>
        <select v-model="plantZoneFilter" class="plants-filter__input">
          <option value="">Alle Zonen</option>
          <option
            v-for="zone in plantZoneOptions"
            :key="zone.zone_id"
            :value="zone.zone_id"
          >
            {{ zone.name }}
          </option>
        </select>
      </label>

      <label class="plants-filter">
        <span class="plants-filter__label">Phase</span>
        <select v-model="plantPhaseFilter" class="plants-filter__input">
          <option value="">Alle Phasen</option>
          <option
            v-for="phase in PLANT_PHASES"
            :key="phase"
            :value="phase"
          >
            {{ PLANT_PHASE_LABELS[phase] }}
          </option>
        </select>
      </label>

      <label class="plants-filter plants-filter--grow">
        <span class="plants-filter__label">Charge</span>
        <select v-model="plantBatchFilter" class="plants-filter__input">
          <option value="">Alle Chargen</option>
          <option
            v-for="batch in availableBatches"
            :key="batch"
            :value="batch"
          >
            {{ batch }}
          </option>
        </select>
      </label>

      <button
        v-if="hasActiveFilters"
        type="button"
        class="plants-btn plants-btn--ghost"
        @click="resetPlantFilters"
      >
        <X class="w-4 h-4" />
        <span>Filter zurücksetzen</span>
      </button>
    </div>

    <div class="plants-summary">
      <span>{{ filteredPlants.length }} Pflanzen</span>
      <span v-if="hasActiveFilters" class="plants-summary__hint">
        (gefiltert aus {{ plantsStore.plants.length }})
      </span>
    </div>

    <div v-if="plantsStore.isLoading" class="plants-state">
      Lade Pflanzen...
    </div>
    <div v-else-if="plantsStore.error" class="plants-state plants-state--error">
      {{ plantsStore.error }}
    </div>

    <template v-else-if="!hasAnyPlants">
      <div class="plants-state">
        <Sprout class="w-8 h-8 plants-state__icon" />
        <p>Noch keine Pflanzen angelegt.</p>
        <p class="plants-state__sub">
          Lege die erste Pflanze über „Neue Pflanze" an, oder erstelle gleich mehrere über „N Pflanzen".
        </p>
      </div>
    </template>
    <template v-else-if="!hasFilteredResults">
      <div class="plants-state">
        <p>Keine Pflanzen für die aktuellen Filter gefunden.</p>
        <button
          type="button"
          class="plants-btn plants-btn--ghost plants-state__reset-btn"
          @click="resetPlantFilters"
        >
          <X class="w-4 h-4" />
          Filter zurücksetzen
        </button>
      </div>
    </template>

    <template v-else>
      <div class="plants-structure">
        <div
          v-for="section in plantZoneSections"
          :key="section.zoneId ?? '__nozone__'"
          :class="[
            'plants-zone-section',
            { 'plants-zone-section--nozone': section.zoneId === null },
          ]"
        >
          <div class="plants-zone-section__header">
            <span class="plants-zone-section__name">{{ section.zoneName }}</span>
            <span class="plants-zone-section__count">
              {{ section.subzoneGroups.reduce((n, g) => n + g.plants.length, 0) + section.zonewidePlants.length }}
            </span>
          </div>

          <PlantSubzoneArea
            v-for="szGroup in section.subzoneGroups"
            :key="szGroup.subzoneId ?? '__no-subzone__'"
            :subzone-id="szGroup.subzoneId"
            :subzone-name="szGroup.subzoneName"
            :zone-id="section.zoneId"
            :plants="szGroup.plants"
            @plant-dropped="handlePlantDropped"
            @open-plant="openPlantPanel"
          />

          <PlantSubzoneArea
            v-if="section.zonewidePlants.length > 0 || section.subzoneGroups.length === 0"
            :subzone-id="null"
            :subzone-name="section.zoneId === null ? 'Kein Ort zugewiesen' : 'Zone-weit'"
            :zone-id="section.zoneId"
            :plants="section.zonewidePlants"
            @plant-dropped="handlePlantDropped"
            @open-plant="openPlantPanel"
          />
        </div>

        <div v-if="plantZoneSections.length === 0 && hasFilteredResults" class="plants-state">
          Keine Sektionen sichtbar. Filter zurücksetzen?
        </div>
      </div>
    </template>

    <SlideOver
      :open="isPlantDetailOpen"
      :title="selectedPlant?.qr_code || selectedPlant?.genotype_label || 'Pflanze'"
      width="lg"
      @close="closePlantPanel"
    >
      <PlantDetailPanel v-if="selectedPlant" :plant="selectedPlant" />
    </SlideOver>

    <PlantCreateModal
      :open="showCreatePlantModal"
      @close="showCreatePlantModal = false"
      @created="onPlantCreated"
    />

    <PlantBatchCreateModal
      :open="showBatchCreateModal"
      @close="showBatchCreateModal = false"
      @created="onBatchCreated"
    />
  </div>
</template>

<style scoped>
.plants-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  height: 100%;
  overflow: auto;
}

.plants-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.plants-header__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.plants-header__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.plants-filters {
  display: flex;
  gap: var(--space-3);
  align-items: end;
  flex-wrap: wrap;
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.plants-filter {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 180px;
}

.plants-filter--grow {
  flex: 1;
}

.plants-filter__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.plants-filter__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition-fast);
  min-height: 38px;
}

.plants-filter__input:focus {
  border-color: var(--color-accent);
}

.plants-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 38px;
  min-width: 44px;
  border: 1px solid transparent;
}

.plants-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plants-btn--primary {
  background: var(--color-accent);
  color: white;
}

.plants-btn--primary:not(:disabled):hover {
  background: var(--color-accent-bright);
}

.plants-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.plants-btn--ghost:not(:disabled):hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.plants-btn--icon {
  padding: var(--space-2);
}

.plants-summary {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.plants-summary__hint {
  color: var(--color-text-muted);
}

.plants-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-6);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.plants-state__icon {
  color: var(--color-text-muted);
  opacity: 0.4;
}

.plants-state__sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  max-width: 360px;
}

.plants-state__reset-btn {
  margin-top: var(--space-2);
}

.plants-state--error {
  color: var(--color-error);
  border-color: rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.06);
}

.plants-structure {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.plants-zone-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  -webkit-backdrop-filter: blur(var(--glass-blur-l2));
  backdrop-filter: blur(var(--glass-blur-l2));
}

.plants-zone-section--nozone {
  border-color: rgba(251, 191, 36, 0.25);
  background: rgba(251, 191, 36, 0.03);
}

.plants-zone-section__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--glass-border);
}

.plants-zone-section__name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

.plants-zone-section--nozone .plants-zone-section__name {
  color: var(--color-warning);
}

.plants-zone-section__count {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  padding: 1px 8px;
}

@media (max-width: 640px) {
  .plants-filters {
    flex-direction: column;
    align-items: stretch;
  }

  .plants-filter {
    min-width: 0;
  }

  .plants-header {
    flex-direction: column;
    align-items: stretch;
  }

  .plants-header__actions {
    justify-content: flex-end;
  }
}
</style>
