<script setup lang="ts">
/**
 * PlantsView — Pflanzen-Inventar
 *
 * Standalone top-level view for the plant inventory. Previously hosted as the
 * "plants" tab inside SensorsView (AUT-221). Extracted to its own route
 * /plants as part of AUT-1159 [C1].
 *
 * C2 additions (AUT-1160):
 *  - View-mode toggle: "Tabelle" ↔ "Struktur"
 *  - Structure mode: nested Zone → Subzone → PlantCard with VueDraggable D&D
 *  - "Ohne Zone" and "Ohne Subzone" sections (Display-Deficit from B3)
 *  - Batch-Anlage-Formular (PlantBatchCreateModal)
 *  - Charge-Filter as select (from available batches in data)
 *  - Empty-state distinguishes "kein Bestand" from "keine Filtertreffer"
 *  - Undo/Redo for drag operations (usePlantDragDrop)
 *
 * Route: /plants
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Sprout, Plus, Printer, X, List, LayoutGrid, Undo2, Redo2 } from 'lucide-vue-next'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useEspStore } from '@/stores/esp'
import { useTankStore } from '@/shared/stores/tank.store'
import { usePlantDragDrop } from '@/composables/usePlantDragDrop'
import { plantsApi } from '@/api/plants'
import { PLANT_PHASES, type Plant } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import PlantDetailPanel from '@/components/plants/PlantDetailPanel.vue'
import PlantCreateModal from '@/components/plants/PlantCreateModal.vue'
import PlantBatchCreateModal from '@/components/plants/PlantBatchCreateModal.vue'
import TankCreateModal from '@/components/plants/TankCreateModal.vue'
import NutrientBatchCreateModal from '@/components/plants/NutrientBatchCreateModal.vue'
import TankIstSollPanel from '@/components/plants/TankIstSollPanel.vue'
import { TANK_DETAIL_QUERY_KEY } from '@/components/plants/tankIstSollFormat'
import PlantSubzoneArea from '@/components/plants/PlantSubzoneArea.vue'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import { useToast } from '@/composables/useToast'
import type { NutrientBatchEntryType } from '@/types'

const route = useRoute()

const plantsStore = usePlantsStore()
const zoneStore = useZoneStore()
const espStore = useEspStore()
const tankStore = useTankStore()
const toast = useToast()
const plantDragDrop = usePlantDragDrop()

// =============================================================================
// Tank Ist/Soll (AUT-1225 Q4) + AUT-1327 deep-link preselect (?tank=)
// =============================================================================
const selectedTankId = ref<string>('')

const tankSelectOptions = computed(() =>
  tankStore.tanks
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((tank) => ({ value: tank.id, label: `${tank.name} (${tank.zone_id})` })),
)

/** Apply Monitor stub deep-link: /plants?tank=<id> → dropdown + Ist/Soll panel. */
function applyTankDetailQuery(): void {
  const raw = route.query[TANK_DETAIL_QUERY_KEY]
  const tankId = Array.isArray(raw) ? raw[0] : raw
  if (typeof tankId === 'string' && tankId.length > 0) {
    selectedTankId.value = tankId
  }
}

watch(
  () => route.query[TANK_DETAIL_QUERY_KEY],
  () => {
    applyTankDetailQuery()
  },
  { immediate: true },
)

// =============================================================================
// View mode: "table" (default) | "structure" (nested D&D view)
// =============================================================================
const viewMode = ref<'table' | 'structure'>('table')

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
// Row helpers (table mode)
// =============================================================================
function getZoneNameForPlant(plant: Plant): string {
  if (!plant.parent_zone_id) return 'Kein Ort zugewiesen'
  return plant.zone_name ?? 'Ort ohne Namen'
}

function getPlantAgeDays(plant: Plant): string {
  if (!plant.planting_date) return '—'
  const planted = Date.parse(plant.planting_date)
  if (Number.isNaN(planted)) return '—'
  const days = Math.max(0, Math.floor((Date.now() - planted) / (1000 * 60 * 60 * 24)))
  return `${days}`
}

function getPlantPhi2Display(_plant: Plant): string {
  // Per-row Phi2 needs measurements which are loaded lazily in the detail panel
  return '—'
}

function getPlantSubzoneLabel(plant: Plant): string {
  if (plant.subzone_name) return plant.subzone_name
  return plant.subzone_id ? 'Ort ohne Namen' : 'Kein Ort zugewiesen'
}

// =============================================================================
// Structure mode: nested Zone → Subzone grouping
// =============================================================================

interface PlantSubzoneGroup {
  subzoneId: string | null  // null = "Zone-weit" group
  subzoneName: string
  plants: Plant[]
}

interface PlantZoneSection {
  zoneId: string | null  // null = "Ohne Zone" section
  zoneName: string
  /** Groups with a specific subzone_id */
  subzoneGroups: PlantSubzoneGroup[]
  /** Plants in this zone but without a subzone assignment */
  zonewidePlants: Plant[]
}

/**
 * Build zone/subzone sections from filteredPlants.
 * Handles all four assignment combinations:
 *   zone + subzone  → in named zone section, named subzone group
 *   zone + no sub   → in named zone section, "Zone-weit" group
 *   no zone + sub   → in "Ohne Zone" section, named subzone group (B3 case)
 *   no zone + no sub → in "Ohne Zone" section, "Kein Ort zugewiesen" group
 */
const plantZoneSections = computed((): PlantZoneSection[] => {
  const sectionMap = new Map<string | null, PlantZoneSection>()

  // Pre-populate sections for known active zones (ensures order)
  for (const zone of zoneStore.activeZones) {
    sectionMap.set(zone.zone_id, {
      zoneId: zone.zone_id,
      zoneName: zone.name,
      subzoneGroups: [],
      zonewidePlants: [],
    })
  }

  // Always have an "Ohne Zone" section (placed last via sort)
  sectionMap.set(null, {
    zoneId: null,
    zoneName: 'Ohne Zone',
    subzoneGroups: [],
    zonewidePlants: [],
  })

  // Distribute filtered plants
  for (const plant of filteredPlants.value) {
    const zoneId = plant.parent_zone_id ?? null

    // On-the-fly: parent zone exists but is not in the active-zone catalog
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

  // Sort subzone groups alphabetically within each section
  for (const section of sectionMap.values()) {
    section.subzoneGroups.sort((a, b) =>
      (a.subzoneName ?? '').localeCompare(b.subzoneName ?? ''),
    )
  }

  // Only include non-empty sections; "Ohne Zone" always last
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

// =============================================================================
// D&D handler (structure mode)
// =============================================================================
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

// =============================================================================
// Tank / Nutrient Ledger (AUT-1215)
// =============================================================================
const showTankCreateModal = ref(false)
const showLedgerModal = ref(false)
const ledgerDefaultEntryType = ref<NutrientBatchEntryType>('full_reset')
const ledgerInitialTankId = ref('')

function openTankCreateModal(): void {
  showTankCreateModal.value = true
}

function openLedgerModal(entryType: NutrientBatchEntryType = 'full_reset'): void {
  ledgerDefaultEntryType.value = entryType
  showLedgerModal.value = true
}

function onTankCreated(tankId: string): void {
  ledgerInitialTankId.value = tankId
  toast.success('Tank bereit — Bilanz-Eintrag möglich')
}

function onLedgerCreated(): void {
  // system_incident visibility is on plant detail (AUT-1214 read path)
}

// =============================================================================
// QR Download
// =============================================================================
async function downloadQRForPlant(plant: Plant): Promise<void> {
  try {
    await plantsApi.downloadQRCode(plant.plant_id, `${plant.qr_code || 'plant-' + plant.plant_id}.png`)
    toast.success('QR-Label heruntergeladen')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'QR-Download fehlgeschlagen')
  }
}

// =============================================================================
// Lifecycle
// =============================================================================
onMounted(() => {
  if (plantsStore.plants.length === 0 && !plantsStore.isLoading) {
    void plantsStore.fetchPlants()
  }
  if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
    void zoneStore.fetchZoneEntities()
  }
  // Devices needed for the PlantCreateModal subzone dropdown
  if (espStore.devices.length === 0) {
    void espStore.fetchAll()
  }
  // Tanks needed for the Ist/Soll tank selector (AUT-1225 Q4)
  if (tankStore.tanks.length === 0 && !tankStore.isLoading) {
    void tankStore.fetchTanks()
  }
})
</script>

<template>
  <div class="plants-view">
    <!-- ── Header ── -->
    <div class="plants-header">
      <h1 class="plants-header__title">
        <Sprout class="w-5 h-5" />
        Pflanzen-Inventar
      </h1>

      <div class="plants-header__actions">
        <!-- View-mode toggle -->
        <div class="plants-view-toggle">
          <button
            type="button"
            :class="['plants-view-toggle__btn', { 'plants-view-toggle__btn--active': viewMode === 'table' }]"
            title="Tabellenansicht"
            @click="viewMode = 'table'"
          >
            <List class="w-4 h-4" />
          </button>
          <button
            type="button"
            :class="['plants-view-toggle__btn', { 'plants-view-toggle__btn--active': viewMode === 'structure' }]"
            title="Struktur (Zonen/Subzonen)"
            @click="viewMode = 'structure'"
          >
            <LayoutGrid class="w-4 h-4" />
          </button>
        </div>

        <!-- Undo/Redo (structure mode only) -->
        <template v-if="viewMode === 'structure'">
          <button
            type="button"
            class="plants-btn plants-btn--ghost plants-btn--icon"
            :disabled="!plantDragDrop.canUndo.value"
            title="Rückgängig"
            @click="plantDragDrop.undo()"
          >
            <Undo2 class="w-4 h-4" />
          </button>
          <button
            type="button"
            class="plants-btn plants-btn--ghost plants-btn--icon"
            :disabled="!plantDragDrop.canRedo.value"
            title="Wiederherstellen"
            @click="plantDragDrop.redo()"
          >
            <Redo2 class="w-4 h-4" />
          </button>
        </template>

        <!-- N Pflanzen (batch) -->
        <button
          type="button"
          class="plants-btn plants-btn--ghost"
          @click="openBatchCreateModal"
        >
          <Plus class="w-4 h-4" />
          <span>N Pflanzen</span>
        </button>

        <!-- Tank / Bilanz (AUT-1215) -->
        <button
          type="button"
          class="plants-btn plants-btn--ghost"
          aria-label="Tank anlegen"
          @click="openTankCreateModal"
        >
          <Plus class="w-4 h-4" />
          <span>Tank</span>
        </button>
        <button
          type="button"
          class="plants-btn plants-btn--ghost"
          aria-label="Bilanz-Eintrag erfassen"
          @click="openLedgerModal('full_reset')"
        >
          <span>Bilanz</span>
        </button>
        <button
          type="button"
          class="plants-btn plants-btn--ghost"
          aria-label="Anlagen-Vorfall protokollieren"
          @click="openLedgerModal('system_incident')"
        >
          <span>Vorfall</span>
        </button>

        <!-- Neue Pflanze (single) -->
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

    <!-- ── Tank Ist/Soll (AUT-1225 Q4) ── -->
    <div class="flex flex-col gap-3">
      <div class="max-w-xs">
        <BaseSelect
          v-model="selectedTankId"
          :options="tankSelectOptions"
          label="Tank für Ist/Soll"
          placeholder="Tank wählen"
        />
      </div>
      <TankIstSollPanel v-if="selectedTankId" :tank-id="selectedTankId" />
    </div>

    <!-- ── Filter Bar ── -->
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

      <!-- Charge: select from available batches (Layout-Befund 4 fix) -->
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

    <!-- ── Summary ── -->
    <div class="plants-summary">
      <span>{{ filteredPlants.length }} Pflanzen</span>
      <span v-if="hasActiveFilters" class="plants-summary__hint">
        (gefiltert aus {{ plantsStore.plants.length }})
      </span>
    </div>

    <!-- ── Global Loading / Error ── -->
    <div v-if="plantsStore.isLoading" class="plants-state">
      Lade Pflanzen...
    </div>
    <div v-else-if="plantsStore.error" class="plants-state plants-state--error">
      {{ plantsStore.error }}
    </div>

    <!-- ── Empty states (only when not loading and no error) ── -->
    <template v-else-if="!hasAnyPlants">
      <!-- "Kein Bestand": no plants exist at all -->
      <div class="plants-state">
        <Sprout class="w-8 h-8 plants-state__icon" />
        <p>Noch keine Pflanzen angelegt.</p>
        <p class="plants-state__sub">
          Lege die erste Pflanze über „Neue Pflanze" an, oder erstelle gleich mehrere über „N Pflanzen".
        </p>
      </div>
    </template>
    <template v-else-if="!hasFilteredResults">
      <!-- "Keine Filtertreffer": plants exist but filter shows none -->
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

    <!-- ── TABLE MODE ── -->
    <template v-else-if="viewMode === 'table'">
      <div class="plants-table-wrap">
        <table class="plants-table">
          <thead>
            <tr>
              <th>QR-Code</th>
              <th>Genotyp</th>
              <th>Charge</th>
              <th>Phase</th>
              <th>Alter (Tage)</th>
              <th>Zone / Subzone</th>
              <th>Letztes Phi2</th>
              <th class="plants-table__actions-col">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="plant in filteredPlants"
              :key="plant.plant_id"
              class="plants-table__row"
              @click="openPlantPanel(plant)"
            >
              <td class="plants-table__mono">{{ plant.qr_code || '—' }}</td>
              <td>{{ plant.genotype_label }}</td>
              <td>{{ plant.batch_label || '—' }}</td>
              <td>{{ PLANT_PHASE_LABELS[plant.phase] ?? plant.phase }}</td>
              <td>{{ getPlantAgeDays(plant) }}</td>
              <td>
                <div>{{ getZoneNameForPlant(plant) }}</div>
                <div class="plants-table__sub">{{ getPlantSubzoneLabel(plant) }}</div>
              </td>
              <td>{{ getPlantPhi2Display(plant) }}</td>
              <td class="plants-table__actions" @click.stop>
                <button
                  type="button"
                  class="plants-table__action-btn"
                  title="QR-Label drucken"
                  @click="downloadQRForPlant(plant)"
                >
                  <Printer class="w-4 h-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ── STRUCTURE MODE ── -->
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
          <!-- Zone section header -->
          <div class="plants-zone-section__header">
            <span class="plants-zone-section__name">{{ section.zoneName }}</span>
            <span class="plants-zone-section__count">
              {{ section.subzoneGroups.reduce((n, g) => n + g.plants.length, 0) + section.zonewidePlants.length }}
            </span>
          </div>

          <!-- Named subzone containers (with D&D) -->
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

          <!-- "Zone-weit" or "Kein Ort zugewiesen" container -->
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

        <!-- Empty state for structure mode (all sections empty after filter) -->
        <div v-if="plantZoneSections.length === 0 && hasFilteredResults" class="plants-state">
          Keine Sektionen sichtbar. Filter zurücksetzen?
        </div>
      </div>
    </template>

    <!-- ── Detail Panel ── -->
    <SlideOver
      :open="isPlantDetailOpen"
      :title="selectedPlant?.qr_code || selectedPlant?.genotype_label || 'Pflanze'"
      width="lg"
      @close="closePlantPanel"
    >
      <PlantDetailPanel v-if="selectedPlant" :plant="selectedPlant" />
    </SlideOver>

    <!-- ── Create Modal (single) ── -->
    <PlantCreateModal
      :open="showCreatePlantModal"
      @close="showCreatePlantModal = false"
      @created="onPlantCreated"
    />

    <!-- ── Batch Create Modal ── -->
    <PlantBatchCreateModal
      :open="showBatchCreateModal"
      @close="showBatchCreateModal = false"
      @created="onBatchCreated"
    />

    <!-- ── Tank / Ledger (AUT-1215) ── -->
    <TankCreateModal
      :open="showTankCreateModal"
      @close="showTankCreateModal = false"
      @created="onTankCreated"
    />
    <NutrientBatchCreateModal
      :open="showLedgerModal"
      :default-entry-type="ledgerDefaultEntryType"
      :initial-tank-id="ledgerInitialTankId"
      @close="showLedgerModal = false"
      @created="onLedgerCreated"
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

/* ── Header ── */
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

/* ── View-mode toggle ── */
.plants-view-toggle {
  display: flex;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.plants-view-toggle__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-width: 36px;
  min-height: 36px;
}

.plants-view-toggle__btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-secondary);
}

.plants-view-toggle__btn--active {
  background: var(--color-bg-tertiary);
  color: var(--color-accent-bright);
}

/* ── Filters ── */
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

/* ── Buttons ── */
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

/* ── Summary ── */
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

/* ── State (loading / empty / error) ── */
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

/* ── Table ── */
.plants-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  -webkit-backdrop-filter: blur(var(--glass-blur-l2));
  backdrop-filter: blur(var(--glass-blur-l2));
}

.plants-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.plants-table thead th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--glass-border);
  white-space: nowrap;
}

.plants-table tbody td {
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--glass-border);
  vertical-align: top;
}

.plants-table__row {
  cursor: pointer;
  transition: background var(--transition-fast);
}

.plants-table__row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.plants-table__mono {
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  font-weight: 600;
}

.plants-table__sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.plants-table__actions-col {
  width: 1%;
  white-space: nowrap;
}

.plants-table__actions {
  text-align: right;
}

.plants-table__action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-width: 36px;
  min-height: 36px;
}

.plants-table__action-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
}

/* ── Structure mode ── */
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

/* "Ohne Zone" section gets a muted warning border to indicate display-deficit items */
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

/* ── Responsive ── */
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
