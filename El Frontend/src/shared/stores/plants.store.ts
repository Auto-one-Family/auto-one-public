/**
 * Plants Store
 *
 * Plant inventory + lifecycle state for the Pflanzen-Tab in SensorsView
 * (AUT-221) and for the MultispeQ snapshot assignment dropdown (AUT-213).
 *
 * Server endpoints: AUT-221 / AUT-222 (`/v1/plants`).
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { plantsApi } from '@/api/plants'
import type {
  Plant,
  PlantCreate,
  PlantLifecycleEvent,
  PlantLifecycleEventCreate,
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

  async function fetchLifecycleEvents(plantId: string): Promise<PlantLifecycleEvent[]> {
    // The dedicated endpoint lives in `GET /v1/plants/{id}` — pull the embedded
    // list out instead of duplicating an HTTP round-trip.
    const plant = await plantsApi.getById(plantId)
    if (selectedPlant.value?.id === plantId) {
      selectedPlant.value = plant
    }
    return plant.lifecycle_events ?? []
  }

  async function addLifecycleEvent(
    plantId: string,
    event: PlantLifecycleEventCreate,
  ): Promise<PlantLifecycleEvent> {
    const created = await plantsApi.addLifecycleEvent(plantId, event)
    if (selectedPlant.value?.id === plantId) {
      const events = selectedPlant.value.lifecycle_events ?? []
      selectedPlant.value = {
        ...selectedPlant.value,
        lifecycle_events: [created, ...events],
      }
    }
    return created
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
    const index = plants.value.findIndex(p => p.id === plantId)
    if (index !== -1) {
      plants.value[index] = { ...plants.value[index], ...updated }
    }
    if (selectedPlant.value?.id === plantId) {
      selectedPlant.value = { ...selectedPlant.value, ...updated }
    }
    return updated
  }

  async function deletePlant(plantId: string): Promise<void> {
    await plantsApi.delete(plantId)
    plants.value = plants.value.filter(p => p.id !== plantId)
    if (selectedPlant.value?.id === plantId) {
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
