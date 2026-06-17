<script setup lang="ts">
/**
 * ComponentInventoryView — Flat Hardware Inventory (Komponenten-Tab)
 *
 * Unified view for all sensors, actuators, and ESPs in a single searchable,
 * filterable, sortable table. Replaces the former zone-grouped SensorsView.
 * Route: /sensors (unchanged for backward compatibility).
 *
 * This view is the Komponenten-Tab (Wissensdatenbank/Inventar). It does NOT host
 * SensorConfigPanel or ActuatorConfigPanel. Full device configuration (thresholds,
 * subzone, calibration, alerts, runtime) is in HardwareView (Route /hardware).
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Search, Filter, X, Columns,
  Package, Upload, ClipboardList, Sprout, Plus, Printer,
} from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useInventoryStore, INVENTORY_COLUMNS } from '@/shared/stores/inventory.store'
import type { ComponentItem } from '@/shared/stores/inventory.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { usePlantsStore } from '@/shared/stores/plants.store'
import InventoryTable from '@/components/inventory/InventoryTable.vue'
import DeviceDetailPanel from '@/components/inventory/DeviceDetailPanel.vue'
import PlantDetailPanel from '@/components/plants/PlantDetailPanel.vue'
import PlantCreateModal from '@/components/plants/PlantCreateModal.vue'
import { PLANT_PHASES, type Plant } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import { plantsApi } from '@/api/plants'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import EmergencyStopButton from '@/components/safety/EmergencyStopButton.vue'
import { useToast } from '@/composables/useToast'
import { multispeqApi } from '@/api/multispeq'
import type {
  MultispeqImportResponse,
  NeedsReviewSnapshot,
} from '@/api/multispeq'
import { formatDateTime } from '@/utils/formatters'

const route = useRoute()
const espStore = useEspStore()
const store = useInventoryStore()
const zoneStore = useZoneStore()
const plantsStore = usePlantsStore()
const toast = useToast()

// =============================================================================
// Tab Navigation
// =============================================================================
type TabKey = 'inventory' | 'plants' | 'audits'
const activeTab = ref<TabKey>(
  ((): TabKey => {
    const q = route.query.tab as string | undefined
    if (q === 'audits') return 'audits'
    if (q === 'plants') return 'plants'
    return 'inventory'
  })(),
)

const tabs: Array<{ key: TabKey; label: string; icon: typeof Package }> = [
  { key: 'inventory', label: 'Inventar', icon: Package },
  { key: 'plants', label: 'Pflanzen', icon: Sprout },
  { key: 'audits', label: 'Audits', icon: ClipboardList },
]

function selectTab(key: TabKey): void {
  activeTab.value = key
  if (key === 'audits' || key === 'plants') {
    // Lazy-load plants for the assignment dropdown / inventory
    if (plantsStore.plants.length === 0 && !plantsStore.isLoading) {
      void plantsStore.fetchPlants()
    }
    if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
      void zoneStore.fetchZoneEntities()
    }
  }
}

// =============================================================================
// MultispeQ Audit Upload Form
// =============================================================================
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 // 10 MB

interface UploadFormState {
  file: File | null
  device_serial: string
  zone_id: string
  subzone_id: string
  calibration_date: string
  dry_run: boolean
}

function createEmptyForm(): UploadFormState {
  return {
    file: null,
    device_serial: '',
    zone_id: '',
    subzone_id: '',
    calibration_date: new Date().toISOString().slice(0, 10),
    dry_run: false,
  }
}

const uploadForm = ref<UploadFormState>(createEmptyForm())
const isUploading = ref(false)
const uploadError = ref<string | null>(null)
const lastResult = ref<MultispeqImportResponse | null>(null)
const needsReviewSnapshots = ref<NeedsReviewSnapshot[]>([])

const availableZones = computed(() => zoneStore.activeZones)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  uploadForm.value.file = file
  uploadError.value = null
}

function validateForm(): string | null {
  const form = uploadForm.value
  if (!form.file) return 'Bitte eine Datei auswaehlen.'
  if (form.file.size > MAX_FILE_SIZE_BYTES) {
    return `Datei zu gross (${(form.file.size / 1024 / 1024).toFixed(1)} MB). Maximal 10 MB erlaubt.`
  }
  if (!form.device_serial.trim()) return 'Device Serial ist erforderlich.'
  if (!form.zone_id) return 'Zone ist erforderlich.'
  if (!form.calibration_date) return 'Kalibrierungsdatum ist erforderlich.'
  return null
}

async function handleUpload(): Promise<void> {
  uploadError.value = null
  const validationMessage = validateForm()
  if (validationMessage) {
    uploadError.value = validationMessage
    return
  }

  const form = uploadForm.value
  isUploading.value = true
  try {
    const result = await multispeqApi.importMeasurement({
      file: form.file as File,
      device_serial: form.device_serial.trim(),
      zone_id: form.zone_id,
      subzone_id: form.subzone_id || undefined,
      calibration_date: form.calibration_date,
      dry_run: form.dry_run,
    })

    lastResult.value = result
    needsReviewSnapshots.value = result.needs_review_snapshots ?? []

    if (form.dry_run) {
      toast.info(
        `Vorschau: ${result.imported} Messungen wuerden importiert, ${result.skipped_duplicates} Duplikate uebersprungen`,
      )
    } else if (result.needs_review > 0) {
      toast.warning(
        `${result.imported} Messungen importiert, ${result.needs_review} ohne Pflanzenzuordnung`,
      )
    } else {
      toast.success(
        `${result.imported} Messungen importiert, ${result.skipped_duplicates} Duplikate uebersprungen`,
      )
    }

    if (result.errors.length > 0) {
      toast.error(`${result.errors.length} Fehler beim Import`, { duration: 8000 })
    }
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Upload fehlgeschlagen'
    uploadError.value = message
    toast.error(message)
  } finally {
    isUploading.value = false
  }
}

function resetUploadForm(): void {
  uploadForm.value = createEmptyForm()
  uploadError.value = null
  lastResult.value = null
  needsReviewSnapshots.value = []
}

async function handleAssignPlant(snapshotId: string, plantId: string): Promise<void> {
  if (!plantId) return
  try {
    await multispeqApi.assignPlant(snapshotId, plantId)
    needsReviewSnapshots.value = needsReviewSnapshots.value.filter(
      (s) => s.id !== snapshotId,
    )
    toast.success('Pflanze zugeordnet')
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Zuordnung fehlgeschlagen'
    toast.error(message)
  }
}

function onAssignChange(snapshotId: string, event: Event): void {
  const select = event.target as HTMLSelectElement
  void handleAssignPlant(snapshotId, select.value)
}

// =============================================================================
// Plants Tab — Filters, Detail Panel, Create Modal
// =============================================================================
const plantZoneFilter = ref<string>('')
const plantPhaseFilter = ref<string>('')
const plantBatchFilter = ref<string>('')

const filteredPlants = computed<Plant[]>(() => {
  let list = plantsStore.plants
  if (plantZoneFilter.value) {
    list = list.filter((p) => p.zone_id === plantZoneFilter.value)
  }
  if (plantPhaseFilter.value) {
    list = list.filter((p) => p.phase === plantPhaseFilter.value)
  }
  if (plantBatchFilter.value.trim()) {
    const needle = plantBatchFilter.value.trim().toLowerCase()
    list = list.filter((p) => (p.batch ?? '').toLowerCase().includes(needle))
  }
  return list
})

const plantZoneOptions = computed(() => zoneStore.activeZones)

function getZoneNameForPlant(plant: Plant): string {
  if (!plant.zone_id) return '—'
  const zone = zoneStore.zoneEntities.find((z) => z.zone_id === plant.zone_id)
  return zone?.name ?? plant.zone_id
}

function getPlantAgeDays(plant: Plant): string {
  if (!plant.planting_date) return '—'
  const planted = Date.parse(plant.planting_date)
  if (Number.isNaN(planted)) return '—'
  const days = Math.max(0, Math.floor((Date.now() - planted) / (1000 * 60 * 60 * 24)))
  return `${days}`
}

function getPlantPhi2Display(_plant: Plant): string {
  // Per-row Phi2 needs measurements which are loaded lazily in the detail
  // panel — keep the column lightweight here. The detail panel shows the
  // last value with timestamp.
  return '—'
}

function getPlantSubzoneLabel(plant: Plant): string {
  return plant.subzone_id ?? '—'
}

const isPlantDetailOpen = ref(false)
const selectedPlant = ref<Plant | null>(null)

function openPlantPanel(plant: Plant): void {
  selectedPlant.value = plant
  isPlantDetailOpen.value = true
}

function closePlantPanel(): void {
  isPlantDetailOpen.value = false
}

const showCreatePlantModal = ref(false)

function openCreatePlantModal(): void {
  showCreatePlantModal.value = true
}

async function onPlantCreated(plantId: string): Promise<void> {
  // Refresh the list and open the detail panel for the new plant
  await plantsStore.fetchPlants()
  const created = plantsStore.plants.find((p) => p.id === plantId)
  if (created) openPlantPanel(created)
}

async function downloadQRForPlant(plant: Plant): Promise<void> {
  try {
    await plantsApi.downloadQRCode(plant.id, `${plant.qr_code || 'plant-' + plant.id}.png`)
    toast.success('QR-Label heruntergeladen')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'QR-Download fehlgeschlagen')
  }
}

function resetPlantFilters(): void {
  plantZoneFilter.value = ''
  plantPhaseFilter.value = ''
  plantBatchFilter.value = ''
}

// =============================================================================
// Column Selector
// =============================================================================
const showColumnSelector = ref(false)

// =============================================================================
// Search debounce
// =============================================================================
const searchInput = ref(store.searchQuery)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

watch(searchInput, (val) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    store.searchQuery = val
    store.currentPage = 1
  }, 300)
})

// =============================================================================
// Filter visibility
// =============================================================================
const showFilters = ref(false)

const activeFilterCount = computed(() => {
  let count = 0
  if (store.typeFilter !== 'all') count++
  if (store.statusFilter !== 'all') count++
  if (store.scopeFilter !== 'all') count++
  if (store.zoneFilter.length > 0) count += store.zoneFilter.length
  return count
})

// =============================================================================
// Lifecycle
// =============================================================================
onMounted(async () => {
  await espStore.fetchAll()

  // Deep-link: ?focus=sensorId → open detail panel
  const focusParam = route.query.focus as string | undefined
  if (focusParam) {
    // Wait for store to populate
    setTimeout(() => {
      const item = store.allComponents.find(c => c.id === focusParam)
      if (item) store.openDetail(item.id)
    }, 200)
  }

  // Legacy: ?sensor={espId}-gpio{gpio} → open detail panel
  const sensorParam = route.query.sensor as string | undefined
  if (sensorParam) {
    const match = sensorParam.match(/^(.+)-gpio(\d+)$/)
    if (match) {
      const syntheticId = `${match[1]}_gpio${match[2]}`
      setTimeout(() => {
        const item = store.allComponents.find(c => c.id === syntheticId)
        if (item) store.openDetail(item.id)
      }, 200)
    }
  }

  // If audits/plants tab pre-selected via URL, eagerly load deps
  if (activeTab.value === 'audits' || activeTab.value === 'plants') {
    void plantsStore.fetchPlants()
    void zoneStore.fetchZoneEntities()
  }
})

// =============================================================================
// Detail Panel
// =============================================================================
const selectedItem = computed(() =>
  store.selectedDeviceId
    ? store.allComponents.find(c => c.id === store.selectedDeviceId) ?? null
    : null
)

function handleSelect(item: ComponentItem) {
  store.openDetail(item.id)
}

// =============================================================================
// Zone filter toggle
// =============================================================================
function toggleZoneFilter(zone: string) {
  const idx = store.zoneFilter.indexOf(zone)
  if (idx === -1) {
    store.zoneFilter = [...store.zoneFilter, zone]
  } else {
    store.zoneFilter = store.zoneFilter.filter(z => z !== zone)
  }
  store.currentPage = 1
}
</script>

<template>
  <div class="h-full overflow-auto">
    <!-- Tab Navigation -->
    <nav class="sensors-tabs" aria-label="Sensoren-Bereiche">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        :class="['sensors-tabs__tab', { 'sensors-tabs__tab--active': activeTab === tab.key }]"
        @click="selectTab(tab.key)"
      >
        <component :is="tab.icon" class="sensors-tabs__icon" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <!-- Inventory Tab -->
    <div v-if="activeTab === 'inventory'">
    <!-- Header -->
    <div class="inventory-header">
      <div class="inventory-header__title-row">
        <h1 class="inventory-header__title">
          <Package class="w-5 h-5" />
          Komponenten-Inventar
        </h1>
        <div class="inventory-header__actions">
          <EmergencyStopButton />
        </div>
      </div>

      <!-- Search + Filter Bar -->
      <div class="inventory-toolbar">
        <!-- Search -->
        <div class="inventory-search">
          <Search class="inventory-search__icon" />
          <input
            v-model="searchInput"
            class="inventory-search__input"
            type="text"
            placeholder="Suche nach Name, Typ, Zone, Hersteller..."
          />
          <button
            v-if="searchInput"
            class="inventory-search__clear"
            @click="searchInput = ''; store.searchQuery = ''"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Type Filter -->
        <div class="inventory-filter-group">
          <button
            v-for="opt in [
              { value: 'all', label: 'Alle' },
              { value: 'sensor', label: 'Sensoren' },
              { value: 'actuator', label: 'Aktoren' },
            ]"
            :key="opt.value"
            :class="['inventory-chip', { 'inventory-chip--active': store.typeFilter === opt.value }]"
            @click="store.typeFilter = opt.value as 'all' | 'sensor' | 'actuator'; store.currentPage = 1"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- Filter Toggle -->
        <button
          :class="['inventory-toolbar__btn', { 'inventory-toolbar__btn--active': showFilters }]"
          @click="showFilters = !showFilters"
        >
          <Filter class="w-4 h-4" />
          <span>Filter</span>
          <span v-if="activeFilterCount > 0" class="inventory-toolbar__badge">{{ activeFilterCount }}</span>
        </button>

        <!-- Column Selector -->
        <div class="inventory-col-selector">
          <button
            class="inventory-toolbar__btn"
            @click="showColumnSelector = !showColumnSelector"
          >
            <Columns class="w-4 h-4" />
            <span>Spalten</span>
          </button>
          <Transition name="fade">
            <div v-if="showColumnSelector" class="inventory-col-dropdown">
              <label
                v-for="col in INVENTORY_COLUMNS"
                :key="col.key"
                class="inventory-col-dropdown__item"
              >
                <input
                  type="checkbox"
                  :checked="store.visibleColumns.includes(col.key)"
                  @change="store.toggleColumn(col.key)"
                />
                <span>{{ col.label }}</span>
              </label>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Expanded Filters -->
      <Transition name="slide">
        <div v-if="showFilters" class="inventory-filters">
          <!-- Zone Filter -->
          <div class="inventory-filters__group">
            <label class="inventory-filters__label">Zone</label>
            <div class="inventory-filters__chips">
              <button
                v-for="zone in store.availableZones"
                :key="zone"
                :class="['inventory-chip', { 'inventory-chip--active': store.zoneFilter.includes(zone) }]"
                @click="toggleZoneFilter(zone)"
              >
                {{ zone }}
              </button>
            </div>
          </div>

          <!-- Status Filter -->
          <div class="inventory-filters__group">
            <label class="inventory-filters__label">Status</label>
            <div class="inventory-filters__chips">
              <button
                v-for="opt in [
                  { value: 'all', label: 'Alle' },
                  { value: 'online', label: 'Online' },
                  { value: 'offline', label: 'Offline' },
                  { value: 'maintenance_due', label: 'Wartung fällig' },
                ]"
                :key="opt.value"
                :class="['inventory-chip', { 'inventory-chip--active': store.statusFilter === opt.value }]"
                @click="store.statusFilter = opt.value as 'all' | 'online' | 'offline' | 'maintenance_due'; store.currentPage = 1"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <!-- Scope Filter (only when non-local scope devices exist) -->
          <div v-if="store.hasNonLocalScope" class="inventory-filters__group">
            <label class="inventory-filters__label">Scope</label>
            <div class="inventory-filters__chips">
              <button
                v-for="opt in [
                  { value: 'all', label: 'Alle' },
                  { value: 'zone_local', label: 'Lokal' },
                  { value: 'multi_zone', label: 'Multi-Zone' },
                  { value: 'mobile', label: 'Mobil' },
                ]"
                :key="opt.value"
                :class="['inventory-chip', { 'inventory-chip--active': store.scopeFilter === opt.value }]"
                @click="store.scopeFilter = opt.value as 'all' | 'zone_local' | 'multi_zone' | 'mobile'; store.currentPage = 1"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <!-- Clear -->
          <div v-if="activeFilterCount > 0" class="inventory-filters__clear">
            <button class="btn-ghost text-sm" @click="store.resetFilters(); showFilters = false">
              <X class="w-4 h-4 mr-1" />
              Alle Filter zurücksetzen
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- Summary Bar -->
    <div class="inventory-summary">
      <span>{{ store.totalCount }} Komponenten</span>
      <span v-if="store.searchQuery || activeFilterCount > 0" class="text-dark-400">
        (gefiltert aus {{ store.allComponents.length }})
      </span>
    </div>

    <!-- Table -->
    <InventoryTable @select="handleSelect" />

    <!-- Detail SlideOver -->
    <SlideOver
      :open="store.isDetailOpen"
      :title="selectedItem?.name || 'Details'"
      width="lg"
      @close="store.closeDetail()"
    >
      <DeviceDetailPanel
        v-if="selectedItem"
        :item="selectedItem"
      />
    </SlideOver>
    </div>

    <!-- Plants Tab (Pflanzen-Inventar) -->
    <div v-else-if="activeTab === 'plants'" class="plants-tab">
      <div class="plants-header">
        <h1 class="plants-header__title">
          <Sprout class="w-5 h-5" />
          Pflanzen-Inventar
        </h1>
        <button
          type="button"
          class="plants-btn plants-btn--primary"
          @click="openCreatePlantModal"
        >
          <Plus class="w-4 h-4" />
          <span>Neue Pflanze</span>
        </button>
      </div>

      <!-- Filter Chips -->
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
          <input
            v-model="plantBatchFilter"
            type="text"
            class="plants-filter__input"
            placeholder="z.B. 2026-NL-A"
          />
        </label>

        <button
          v-if="plantZoneFilter || plantPhaseFilter || plantBatchFilter"
          type="button"
          class="plants-btn plants-btn--ghost"
          @click="resetPlantFilters"
        >
          <X class="w-4 h-4" />
          <span>Filter zurücksetzen</span>
        </button>
      </div>

      <!-- Summary -->
      <div class="plants-summary">
        <span>{{ filteredPlants.length }} Pflanzen</span>
        <span
          v-if="plantZoneFilter || plantPhaseFilter || plantBatchFilter"
          class="plants-summary__hint"
        >
          (gefiltert aus {{ plantsStore.plants.length }})
        </span>
      </div>

      <!-- Loading / Error / Empty -->
      <div v-if="plantsStore.isLoading" class="plants-state">
        Lade Pflanzen...
      </div>
      <div v-else-if="plantsStore.error" class="plants-state plants-state--error">
        {{ plantsStore.error }}
      </div>
      <div v-else-if="filteredPlants.length === 0" class="plants-state">
        Keine Pflanzen gefunden.
      </div>

      <!-- Table -->
      <div v-else class="plants-table-wrap">
        <table class="plants-table">
          <thead>
            <tr>
              <th>QR-Code</th>
              <th>Genotyp</th>
              <th>Charge</th>
              <th>Phase</th>
              <th>Alter (Tage)</th>
              <th>Subzone</th>
              <th>Letztes Phi2</th>
              <th class="plants-table__actions-col">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="plant in filteredPlants"
              :key="plant.id"
              class="plants-table__row"
              @click="openPlantPanel(plant)"
            >
              <td class="plants-table__mono">{{ plant.qr_code || '—' }}</td>
              <td>{{ plant.genotype }}</td>
              <td>{{ plant.batch || '—' }}</td>
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

      <!-- Detail Panel -->
      <SlideOver
        :open="isPlantDetailOpen"
        :title="selectedPlant?.qr_code || selectedPlant?.genotype || 'Pflanze'"
        width="lg"
        @close="closePlantPanel"
      >
        <PlantDetailPanel v-if="selectedPlant" :plant="selectedPlant" />
      </SlideOver>

      <!-- Create Modal -->
      <PlantCreateModal
        :open="showCreatePlantModal"
        @close="showCreatePlantModal = false"
        @created="onPlantCreated"
      />
    </div>

    <!-- Audits Tab (MultispeQ Import) -->
    <div v-else-if="activeTab === 'audits'" class="audits-tab">
      <div class="audits-header">
        <h1 class="audits-header__title">
          <ClipboardList class="w-5 h-5" />
          MultispeQ-Audits
        </h1>
      </div>

      <!-- Upload Form -->
      <section class="audits-card">
        <h2 class="audits-card__title">
          <Upload class="w-4 h-4" />
          Messdatei importieren
        </h2>
        <form class="audits-form" @submit.prevent="handleUpload">
          <div class="audits-form__row">
            <label class="audits-form__field">
              <span class="audits-form__label">Datei (CSV oder JSON)</span>
              <input
                type="file"
                accept=".csv,.json"
                class="audits-form__input"
                required
                @change="onFileChange"
              />
              <span v-if="uploadForm.file" class="audits-form__hint">
                {{ uploadForm.file.name }} ({{ (uploadForm.file.size / 1024).toFixed(1) }} KB)
              </span>
            </label>
          </div>

          <div class="audits-form__row audits-form__row--two">
            <label class="audits-form__field">
              <span class="audits-form__label">Device Serial</span>
              <input
                v-model="uploadForm.device_serial"
                type="text"
                class="audits-form__input"
                placeholder="z.B. MQ-001"
                required
              />
            </label>

            <label class="audits-form__field">
              <span class="audits-form__label">Kalibrierungsdatum</span>
              <input
                v-model="uploadForm.calibration_date"
                type="date"
                class="audits-form__input"
                required
              />
            </label>
          </div>

          <div class="audits-form__row audits-form__row--two">
            <label class="audits-form__field">
              <span class="audits-form__label">Zone</span>
              <select v-model="uploadForm.zone_id" class="audits-form__input" required>
                <option value="">Zone auswaehlen...</option>
                <option
                  v-for="zone in availableZones"
                  :key="zone.zone_id"
                  :value="zone.zone_id"
                >
                  {{ zone.name }}
                </option>
              </select>
            </label>

            <label class="audits-form__field">
              <span class="audits-form__label">Subzone (optional)</span>
              <input
                v-model="uploadForm.subzone_id"
                type="text"
                class="audits-form__input"
                placeholder="z.B. north_bench"
              />
            </label>
          </div>

          <div class="audits-form__row">
            <label class="audits-form__checkbox">
              <input v-model="uploadForm.dry_run" type="checkbox" />
              <span>Vorschau (kein Import, nur Validierung)</span>
            </label>
          </div>

          <div v-if="uploadError" class="audits-form__error">
            {{ uploadError }}
          </div>

          <div class="audits-form__actions">
            <button
              type="button"
              class="audits-btn audits-btn--ghost"
              :disabled="isUploading"
              @click="resetUploadForm"
            >
              Zuruecksetzen
            </button>
            <button
              type="submit"
              class="audits-btn audits-btn--primary"
              :disabled="isUploading"
            >
              {{ isUploading ? 'Wird verarbeitet...' : (uploadForm.dry_run ? 'Vorschau' : 'Importieren') }}
            </button>
          </div>
        </form>
      </section>

      <!-- Result Summary -->
      <section v-if="lastResult" class="audits-card">
        <h2 class="audits-card__title">
          {{ uploadForm.dry_run || (lastResult && needsReviewSnapshots.length === 0 && lastResult.imported === 0) ? 'Vorschau-Ergebnis' : 'Import-Ergebnis' }}
        </h2>
        <div class="audits-result">
          <div class="audits-result__stat">
            <span class="audits-result__value">{{ lastResult.imported }}</span>
            <span class="audits-result__label">Importiert</span>
          </div>
          <div class="audits-result__stat">
            <span class="audits-result__value">{{ lastResult.skipped_duplicates }}</span>
            <span class="audits-result__label">Duplikate</span>
          </div>
          <div class="audits-result__stat audits-result__stat--warn">
            <span class="audits-result__value">{{ lastResult.needs_review }}</span>
            <span class="audits-result__label">Ohne Pflanze</span>
          </div>
          <div class="audits-result__stat audits-result__stat--error">
            <span class="audits-result__value">{{ lastResult.errors.length }}</span>
            <span class="audits-result__label">Fehler</span>
          </div>
        </div>
        <ul v-if="lastResult.warnings.length > 0" class="audits-result__messages">
          <li v-for="(w, i) in lastResult.warnings" :key="`w-${i}`" class="audits-result__warning">
            {{ w }}
          </li>
        </ul>
        <ul v-if="lastResult.errors.length > 0" class="audits-result__messages">
          <li v-for="(err, i) in lastResult.errors" :key="`e-${i}`" class="audits-result__error-item">
            {{ err }}
          </li>
        </ul>
      </section>

      <!-- Needs Review Snapshots -->
      <section v-if="needsReviewSnapshots.length > 0" class="audits-card">
        <h2 class="audits-card__title">
          Ohne Pflanzenzuordnung ({{ needsReviewSnapshots.length }})
        </h2>
        <p class="audits-card__hint">
          Ordne jeder Messung eine Pflanze zu, um die Auswertung zu vervollstaendigen.
        </p>
        <ul class="audits-needs-review">
          <li
            v-for="snapshot in needsReviewSnapshots"
            :key="snapshot.id"
            class="audits-needs-review__item"
          >
            <div class="audits-needs-review__meta">
              <span class="audits-needs-review__time">{{ formatDateTime(snapshot.timestamp) }}</span>
              <span
                v-if="snapshot.sensor_values.phi2 !== undefined"
                class="audits-needs-review__metric"
              >
                Phi2: {{ snapshot.sensor_values.phi2.toFixed(3) }}
              </span>
              <span
                v-if="snapshot.sensor_values.fv_fm !== undefined"
                class="audits-needs-review__metric"
              >
                Fv/Fm: {{ snapshot.sensor_values.fv_fm.toFixed(3) }}
              </span>
            </div>
            <select
              class="audits-form__input audits-needs-review__select"
              :disabled="plantsStore.isLoading"
              @change="onAssignChange(snapshot.id, $event)"
            >
              <option value="">Pflanze zuordnen...</option>
              <option
                v-for="plant in plantsStore.plants"
                :key="plant.id"
                :value="plant.id"
              >
                {{ plant.qr_code }} — {{ plant.genotype }}
              </option>
            </select>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* Header */
.inventory-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.inventory-header__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.inventory-header__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.inventory-header__actions {
  display: flex;
  gap: var(--space-2);
}

/* Toolbar */
.inventory-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.inventory-search {
  position: relative;
  flex: 1;
  min-width: 200px;
}

.inventory-search__icon {
  position: absolute;
  left: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: var(--color-text-muted);
  pointer-events: none;
}

.inventory-search__input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  padding-left: calc(var(--space-3) + 20px);
  padding-right: calc(var(--space-3) + 20px);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.inventory-search__input:focus {
  border-color: var(--color-accent);
}

.inventory-search__input::placeholder {
  color: var(--color-text-muted);
}

.inventory-search__clear {
  position: absolute;
  right: var(--space-2);
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
}

.inventory-search__clear:hover {
  color: var(--color-text-primary);
}

/* Filter group (type chips inline) */
.inventory-filter-group {
  display: flex;
  gap: var(--space-1);
}

/* Toolbar buttons */
.inventory-toolbar__btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.inventory-toolbar__btn:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.inventory-toolbar__btn--active {
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
}

.inventory-toolbar__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: var(--radius-full);
  background: var(--color-accent);
  color: white;
  font-size: var(--text-xxs);
  font-weight: 600;
}

/* Column Selector Dropdown */
.inventory-col-selector {
  position: relative;
}

.inventory-col-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: var(--z-sticky);
  margin-top: var(--space-1);
  padding: var(--space-2);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-floating);
  min-width: 180px;
}

.inventory-col-dropdown__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.inventory-col-dropdown__item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.inventory-col-dropdown__item input[type="checkbox"] {
  accent-color: var(--color-accent);
}

/* Chip */
.inventory-chip {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.inventory-chip:hover {
  border-color: var(--color-accent);
  color: var(--color-text-secondary);
}

.inventory-chip--active {
  background: rgba(139, 92, 246, 0.15);
  border-color: rgba(139, 92, 246, 0.4);
  color: var(--color-iridescent-3);
}

/* Expanded Filters */
.inventory-filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.inventory-filters__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.inventory-filters__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.inventory-filters__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.inventory-filters__clear {
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

/* Summary */
.inventory-summary {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

/* Transitions */
.slide-enter-active, .slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to, .slide-leave-from {
  max-height: 500px;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* =============================================================================
   Sensors-View Tab Navigation (Inventar | Audits)
   ============================================================================= */
.sensors-tabs {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--glass-bg-l1);
  -webkit-backdrop-filter: blur(var(--glass-blur-l1));
  backdrop-filter: blur(var(--glass-blur-l1));
  border: 1px solid var(--glass-border-l1);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-3);
}

.sensors-tabs__tab {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 36px;
}

.sensors-tabs__tab:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.02);
}

.sensors-tabs__tab--active {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.sensors-tabs__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* =============================================================================
   Audits Tab
   ============================================================================= */
.audits-tab {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.audits-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.audits-header__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.audits-card {
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

.audits-card__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.audits-card__hint {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

/* Form */
.audits-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.audits-form__row {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.audits-form__row--two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

.audits-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.audits-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.audits-form__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition-fast);
  min-height: 38px;
}

.audits-form__input:focus {
  border-color: var(--color-accent);
}

.audits-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.audits-form__checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.audits-form__checkbox input[type="checkbox"] {
  accent-color: var(--color-accent);
  width: 16px;
  height: 16px;
}

.audits-form__error {
  padding: var(--space-2) var(--space-3);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.audits-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.audits-btn {
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

.audits-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.audits-btn--primary {
  background: var(--color-accent);
  color: white;
}

.audits-btn--primary:not(:disabled):hover {
  background: var(--color-accent-bright);
}

.audits-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.audits-btn--ghost:not(:disabled):hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

/* Result */
.audits-result {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-2);
}

.audits-result__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.audits-result__stat--warn {
  border-color: rgba(251, 191, 36, 0.3);
}

.audits-result__stat--error {
  border-color: rgba(248, 113, 113, 0.3);
}

.audits-result__value {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--color-text-primary);
}

.audits-result__stat--warn .audits-result__value {
  color: var(--color-warning);
}

.audits-result__stat--error .audits-result__value {
  color: var(--color-error);
}

.audits-result__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.audits-result__messages {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  list-style: none;
  padding: 0;
  margin: 0;
}

.audits-result__warning {
  padding: var(--space-2);
  background: rgba(251, 191, 36, 0.08);
  border-left: 2px solid var(--color-warning);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.audits-result__error-item {
  padding: var(--space-2);
  background: rgba(248, 113, 113, 0.08);
  border-left: 2px solid var(--color-error);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

/* Needs Review */
.audits-needs-review {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  list-style: none;
  padding: 0;
  margin: 0;
}

.audits-needs-review__item {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.audits-needs-review__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.audits-needs-review__time {
  color: var(--color-text-secondary);
}

.audits-needs-review__metric {
  color: var(--color-text-muted);
  font-family: var(--font-mono, monospace);
}

.audits-needs-review__select {
  min-width: 240px;
}

@media (max-width: 640px) {
  .audits-needs-review__item {
    grid-template-columns: 1fr;
  }
  .audits-needs-review__select {
    min-width: 0;
    width: 100%;
  }
}

/* =============================================================================
   Plants Tab (Pflanzen-Inventar)
   ============================================================================= */
.plants-tab {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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

/* Filters */
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

/* Buttons */
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

/* Summary */
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

/* State (loading / empty / error) */
.plants-state {
  padding: var(--space-6);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.plants-state--error {
  color: var(--color-error);
  border-color: rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.06);
}

/* Table */
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

@media (max-width: 640px) {
  .plants-filters {
    flex-direction: column;
    align-items: stretch;
  }
  .plants-filter {
    min-width: 0;
  }
}
</style>
