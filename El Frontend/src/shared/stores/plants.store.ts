/**
 * Plants Store
 *
 * Plant inventory + lifecycle state for the Pflanzen-Tab in SensorsView
 * (AUT-221) and for the MultispeQ snapshot assignment dropdown (AUT-213).
 *
 * Server endpoints: AUT-221 / AUT-222 (`/v1/plants`).
 *
 * AUT-1178: uses plant_id (server PK) as the canonical identifier throughout.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { plantsApi } from '@/api/plants'
import type { PlantLifecycleEventsResult } from '@/api/plants'
import type {
  Plant,
  PlantCreate,
  PlantLifecycleEvent,
  PlantLifecycleEventCreate,
  PlantLifecycleEventStatusUpdate,
  PlantMeasurement,
  PlantUpdate,
} from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('PlantsStore')

export const usePlantsStore = defineStore('plants', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const plants = ref<Plant[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /** Currently focused plant (loaded via fetchPlantDetail). */
  const selectedPlant = ref<Plant | null>(null)
  const isLoadingDetail = ref(false)

  /** Phi2/Fv-Fm time series for the selected plant. */
  const measurements = ref<PlantMeasurement[]>([])
  const isLoadingMeasurements = ref(false)

  // ---------------------------------------------------------------------------
  // Actions — list
  // ---------------------------------------------------------------------------
  async function fetchPlants(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      plants.value = await plantsApi.getList()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Pflanzen konnten nicht geladen werden'
      logger.error('Failed to fetch plants', e)
    } finally {
      isLoading.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Actions — single plant
  // ---------------------------------------------------------------------------
  async function fetchPlantDetail(plantId: string): Promise<Plant | null> {
    isLoadingDetail.value = true
    try {
      const plant = await plantsApi.getById(plantId)
      selectedPlant.value = plant
      // Mirror lifecycle_events into a top-level cache so callers can re-render
      // without reaching into selectedPlant.
      return plant
    } catch (e) {
      logger.error(`Failed to fetch plant ${plantId}`, e)
      return null
    } finally {
      isLoadingDetail.value = false
    }
  }

  /**
   * Load lifecycle events for a plant via the dedicated endpoint.
   *
   * AUT-1181 (Befund 2): previously this called plantsApi.getById() and
   * tried to read the embedded lifecycle_events field, which the server does
   * NOT populate at the plant-detail endpoint.  Now calls the dedicated
   * GET /v1/plants/{id}/lifecycle-events endpoint directly.
   *
   * AUT-1211: also returns tank_incidents (system-wide tank incidents
   * affecting this plant), kept separate from the per-plant events.
   */
  async function fetchLifecycleEvents(plantId: string): Promise<PlantLifecycleEventsResult> {
    return plantsApi.getLifecycleEvents(plantId)
  }

  /**
   * AUT-1205: Plant.phase / nutrient_phase are re-derived on the server from
   * chronology after phase-axis writes. Refresh list + selectedPlant so the
   * inventory table does not keep a stale current-state column.
   */
  async function syncPlantCurrentPhaseState(plantId: string): Promise<void> {
    try {
      const plant = await plantsApi.getById(plantId)
      const index = plants.value.findIndex(p => p.plant_id === plantId)
      if (index !== -1) {
        const existing = plants.value[index]
        plants.value[index] = {
          ...existing,
          ...plant,
          // Detail endpoint does not embed lifecycle_events — keep any cache.
          lifecycle_events: existing.lifecycle_events ?? plant.lifecycle_events,
        }
      }
      if (selectedPlant.value?.plant_id === plantId) {
        selectedPlant.value = {
          ...selectedPlant.value,
          phase: plant.phase,
          nutrient_phase: plant.nutrient_phase,
        }
      }
    } catch (e) {
      logger.error(`Failed to sync phase state for plant ${plantId}`, e)
    }
  }

  async function addLifecycleEvent(
    plantId: string,
    event: PlantLifecycleEventCreate,
  ): Promise<PlantLifecycleEvent> {
    const created = await plantsApi.addLifecycleEvent(plantId, event)
    if (selectedPlant.value?.plant_id === plantId) {
      const events = selectedPlant.value.lifecycle_events ?? []
      selectedPlant.value = {
        ...selectedPlant.value,
        lifecycle_events: [created, ...events],
      }
    }
    // AUT-1205: only axis writes can move current phase columns.
    if (
      event.event_type === 'phase_changed' ||
      event.event_type === 'nutrient_phase_changed'
    ) {
      await syncPlantCurrentPhaseState(plantId)
    }
    return created
  }

  /** Change the truth status of an existing lifecycle event (AUT-1207). */
  async function updateLifecycleEventStatus(
    plantId: string,
    eventId: string,
    update: PlantLifecycleEventStatusUpdate,
  ): Promise<PlantLifecycleEvent> {
    const updated = await plantsApi.updateLifecycleEventStatus(plantId, eventId, update)
    // AUT-1205/1207/1208: status or field corrections re-derive axis state.
    await syncPlantCurrentPhaseState(plantId)
    return updated
  }

  async function fetchMeasurements(plantId: string, days = 90): Promise<PlantMeasurement[]> {
    isLoadingMeasurements.value = true
    try {
      const data = await plantsApi.getMeasurements(plantId, days)
      measurements.value = data
      return data
    } catch (e) {
      logger.error(`Failed to fetch measurements for ${plantId}`, e)
      measurements.value = []
      return []
    } finally {
      isLoadingMeasurements.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Actions — mutations
  // ---------------------------------------------------------------------------
  async function createPlant(data: PlantCreate): Promise<Plant> {
    const created = await plantsApi.create(data)
    plants.value = [created, ...plants.value]
    return created
  }

  async function updatePlant(plantId: string, data: PlantUpdate): Promise<Plant> {
    const updated = await plantsApi.update(plantId, data)
    const index = plants.value.findIndex(p => p.plant_id === plantId)
    if (index !== -1) {
      plants.value[index] = { ...plants.value[index], ...updated }
    }
    if (selectedPlant.value?.plant_id === plantId) {
      selectedPlant.value = { ...selectedPlant.value, ...updated }
    }
    return updated
  }

  async function deletePlant(plantId: string): Promise<void> {
    await plantsApi.delete(plantId)
    plants.value = plants.value.filter(p => p.plant_id !== plantId)
    if (selectedPlant.value?.plant_id === plantId) {
      selectedPlant.value = null
    }
  }

  // ---------------------------------------------------------------------------
  // Reset
  // ---------------------------------------------------------------------------
  function $reset(): void {
    plants.value = []
    isLoading.value = false
    error.value = null
    selectedPlant.value = null
    isLoadingDetail.value = false
    measurements.value = []
    isLoadingMeasurements.value = false
  }

  return {
    // state
    plants,
    isLoading,
    error,
    selectedPlant,
    isLoadingDetail,
    measurements,
    isLoadingMeasurements,
    // actions
    fetchPlants,
    fetchPlantDetail,
    fetchLifecycleEvents,
    addLifecycleEvent,
    updateLifecycleEventStatus,
    fetchMeasurements,
    createPlant,
    updatePlant,
    deletePlant,
    $reset,
  }
})

// Re-export the `Plant` type for legacy imports that did `import type { Plant }
// from '@/shared/stores/plants.store'` before the type moved to `@/types`.
export type { Plant } from '@/types'
