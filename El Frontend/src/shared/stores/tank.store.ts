/**
 * Tank Store (AUT-1215 / AUT-1223 Q3)
 *
 * Server (GET /v1/tanks) is the source of truth — fetchTanks() must be called
 * to populate the list for device↔tank assignment dropdowns. localStorage is
 * kept only as an offline cache so the ledger form can re-select a tank
 * created earlier in the session before the next fetch completes; it is
 * NEVER the source of truth on its own.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { tanksApi } from '@/api/tanks'
import type {
  NutrientBatch,
  NutrientBatchCreate,
  Tank,
  TankCreate,
  TankUpdate,
} from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('TankStore')
const STORAGE_KEY = 'autoone.known_tanks.v1'

function loadFromStorage(): Tank[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (t): t is Tank =>
        !!t &&
        typeof t === 'object' &&
        typeof (t as Tank).id === 'string' &&
        typeof (t as Tank).zone_id === 'string' &&
        typeof (t as Tank).name === 'string',
    )
  } catch {
    return []
  }
}

function saveToStorage(tanks: Tank[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tanks))
  } catch (e) {
    logger.warn('Failed to persist known tanks', e)
  }
}

export const useTankStore = defineStore('tanks', () => {
  const tanks = ref<Tank[]>(loadFromStorage())
  const isSubmitting = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  /** Most recently created ledger entry (for UI feedback). */
  const lastBatch = ref<NutrientBatch | null>(null)

  const tanksByZone = computed(() => {
    const map = new Map<string, Tank[]>()
    for (const tank of tanks.value) {
      const list = map.get(tank.zone_id) ?? []
      list.push(tank)
      map.set(tank.zone_id, list)
    }
    return map
  })

  function rememberTank(tank: Tank): void {
    const idx = tanks.value.findIndex((t) => t.id === tank.id)
    if (idx >= 0) {
      tanks.value[idx] = tank
    } else {
      tanks.value = [...tanks.value, tank]
    }
    saveToStorage(tanks.value)
  }

  function tanksForZone(zoneId: string): Tank[] {
    return tanks.value
      .filter((t) => t.zone_id === zoneId)
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  /**
   * Fetch all tanks from the server (GET /v1/tanks) and replace local state.
   * This is the source of truth for assignment dropdowns (AUT-1223 Q3) —
   * localStorage must never be used instead of this fetch.
   */
  async function fetchTanks(): Promise<Tank[]> {
    isLoading.value = true
    error.value = null
    try {
      const serverTanks = await tanksApi.listTanks()
      tanks.value = serverTanks
      saveToStorage(serverTanks)
      return serverTanks
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Tanks konnten nicht geladen werden'
      logger.error('Failed to fetch tanks', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function createTank(data: TankCreate): Promise<Tank> {
    isSubmitting.value = true
    error.value = null
    try {
      const tank = await tanksApi.createTank(data)
      rememberTank(tank)
      return tank
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Tank konnte nicht angelegt werden'
      logger.error('Failed to create tank', e)
      throw e
    } finally {
      isSubmitting.value = false
    }
  }

  /** Partial update via PATCH /tanks/{id} (AUT-1388 — Nennwert + Frischwasser). */
  async function updateTank(tankId: string, data: TankUpdate): Promise<Tank> {
    isSubmitting.value = true
    error.value = null
    try {
      const tank = await tanksApi.updateTank(tankId, data)
      rememberTank(tank)
      return tank
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Tank konnte nicht aktualisiert werden'
      logger.error('Failed to update tank', e)
      throw e
    } finally {
      isSubmitting.value = false
    }
  }

  async function assignSubzones(
    tankId: string,
    subzoneConfigIds: string[],
  ): Promise<void> {
    for (const subzoneConfigId of subzoneConfigIds) {
      await tanksApi.assignSubzone(tankId, { subzone_config_id: subzoneConfigId })
    }
  }

  async function createBatch(
    tankId: string,
    data: NutrientBatchCreate,
  ): Promise<NutrientBatch> {
    isSubmitting.value = true
    error.value = null
    try {
      const batch = await tanksApi.createBatch(tankId, data)
      lastBatch.value = batch
      return batch
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Bilanz-Eintrag konnte nicht gespeichert werden'
      logger.error('Failed to create ledger entry', e)
      throw e
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    tanks,
    tanksByZone,
    isSubmitting,
    isLoading,
    error,
    lastBatch,
    rememberTank,
    tanksForZone,
    fetchTanks,
    createTank,
    updateTank,
    assignSubzones,
    createBatch,
  }
})
