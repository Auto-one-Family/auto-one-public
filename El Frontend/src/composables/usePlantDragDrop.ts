/**
 * usePlantDragDrop Composable
 *
 * Handles subzone drag & drop operations for plants.
 * Structural parallel to useZoneDragDrop:
 * - Calls plantsStore.updatePlant() instead of zonesApi
 * - Same undo/redo stack (MAX_HISTORY = 20)
 * - Same toast / dedupeKey patterns
 *
 * AUT-1160 C2 — Drag & Drop Verteilung.
 */

import { ref, computed } from 'vue'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useToast } from './useToast'
import type { Plant } from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('PlantDragDrop')

interface PlantHistoryEntry {
  plantId: string
  plantLabel: string
  fromSubzoneId: string | null
  fromSubzoneName: string | null
  toSubzoneId: string | null
  toSubzoneName: string | null
  fromZoneId: string | null
  toZoneId: string | null
  timestamp: number
}

export function usePlantDragDrop() {
  const plantsStore = usePlantsStore()
  const toast = useToast()

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const isProcessing = ref(false)
  const lastError = ref<string | null>(null)
  const processingPlantId = ref<string | null>(null)

  // Undo/Redo history — max 20 entries, same limit as useZoneDragDrop
  const MAX_HISTORY = 20
  const undoStack = ref<PlantHistoryEntry[]>([])
  const redoStack = ref<PlantHistoryEntry[]>([])

  const canUndo = computed(() => undoStack.value.length > 0 && !isProcessing.value)
  const canRedo = computed(() => redoStack.value.length > 0 && !isProcessing.value)

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------
  function pushToHistory(entry: PlantHistoryEntry): void {
    undoStack.value.push(entry)
    if (undoStack.value.length > MAX_HISTORY) {
      undoStack.value.shift()
    }
    // Any new action clears the redo stack
    redoStack.value = []
  }

  // ---------------------------------------------------------------------------
  // Core action: assign plant to (sub)zone via PATCH /v1/plants/{id}
  // ---------------------------------------------------------------------------
  /**
   * Assign a plant to a new subzone (and/or zone).
   * Call this when a plant is dropped onto a PlantSubzoneArea.
   */
  async function handlePlantSubzoneChange(
    plant: Plant,
    toSubzoneId: string | null,
    toZoneId: string | null,
    toSubzoneName?: string,
    fromSubzoneName?: string,
  ): Promise<boolean> {
    const fromSubzoneId = plant.subzone_id ?? null
    const fromZoneId = plant.parent_zone_id ?? null

    // No-op if same assignment
    if (fromSubzoneId === toSubzoneId && fromZoneId === toZoneId) {
      return true
    }

    isProcessing.value = true
    processingPlantId.value = plant.plant_id
    lastError.value = null

    const plantLabel = plant.qr_code || plant.genotype_label

    try {
      // AUT-1266: send only subzone_id — zone is derived server-side (read-only).
      await plantsStore.updatePlant(plant.plant_id, {
        subzone_id: toSubzoneId,
      })

      const targetLabel = toSubzoneName ?? toSubzoneId ?? 'Ohne Subzone'
      toast.info(`Zuweisung: "${plantLabel}" → "${targetLabel}"`, {
        dedupeKey: `plant-assign:${plant.plant_id}:${toSubzoneId ?? 'none'}`,
      })

      pushToHistory({
        plantId: plant.plant_id,
        plantLabel,
        fromSubzoneId,
        fromSubzoneName: fromSubzoneName ?? fromSubzoneId,
        toSubzoneId,
        toSubzoneName: toSubzoneName ?? toSubzoneId,
        fromZoneId,
        toZoneId,
        timestamp: Date.now(),
      })

      logger.debug(`Plant ${plant.plant_id} → subzone ${toSubzoneId ?? 'none'} / zone ${toZoneId ?? 'none'}`)
      return true
    } catch (error) {
      logger.error(`Failed to assign plant ${plant.plant_id}`, error)
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage
      toast.error(`Zuweisung fehlgeschlagen: ${errorMessage}`, {
        duration: 6000,
        actions: [
          {
            label: 'Erneut versuchen',
            variant: 'primary',
            onClick: async () => {
              await handlePlantSubzoneChange(plant, toSubzoneId, toZoneId, toSubzoneName, fromSubzoneName)
            },
          },
        ],
      })
      return false
    } finally {
      isProcessing.value = false
      processingPlantId.value = null
    }
  }

  /**
   * Convenience: remove plant from its current subzone (keeps zone assignment).
   */
  async function handleRemovePlantFromSubzone(
    plant: Plant,
    fromSubzoneName?: string,
  ): Promise<boolean> {
    return handlePlantSubzoneChange(
      plant,
      null,
      plant.parent_zone_id ?? null,
      'Ohne Subzone',
      fromSubzoneName,
    )
  }

  // ---------------------------------------------------------------------------
  // Undo / Redo — same pattern as useZoneDragDrop
  // ---------------------------------------------------------------------------
  async function undo(): Promise<boolean> {
    if (!canUndo.value) return false
    const entry = undoStack.value.pop()
    if (!entry) return false

    isProcessing.value = true
    processingPlantId.value = entry.plantId
    lastError.value = null

    try {
      await plantsStore.updatePlant(entry.plantId, {
        subzone_id: entry.fromSubzoneId,
      })
      redoStack.value.push(entry)
      const targetLabel = entry.fromSubzoneName ?? 'Ohne Subzone'
      toast.success(`Rückgängig: "${entry.plantLabel}" → "${targetLabel}"`)
      logger.debug(`Undo: Plant ${entry.plantId} → subzone ${entry.fromSubzoneId ?? 'none'}`)
      return true
    } catch (error) {
      undoStack.value.push(entry)
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage
      toast.error(`Rückgängig fehlgeschlagen: ${errorMessage}`)
      return false
    } finally {
      isProcessing.value = false
      processingPlantId.value = null
    }
  }

  async function redo(): Promise<boolean> {
    if (!canRedo.value) return false
    const entry = redoStack.value.pop()
    if (!entry) return false

    isProcessing.value = true
    processingPlantId.value = entry.plantId
    lastError.value = null

    try {
      await plantsStore.updatePlant(entry.plantId, {
        subzone_id: entry.toSubzoneId,
      })
      undoStack.value.push(entry)
      const targetLabel = entry.toSubzoneName ?? 'Ohne Subzone'
      toast.success(`Wiederherstellen: "${entry.plantLabel}" → "${targetLabel}"`)
      logger.debug(`Redo: Plant ${entry.plantId} → subzone ${entry.toSubzoneId ?? 'none'}`)
      return true
    } catch (error) {
      redoStack.value.push(entry)
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage
      toast.error(`Wiederherstellen fehlgeschlagen: ${errorMessage}`)
      return false
    } finally {
      isProcessing.value = false
      processingPlantId.value = null
    }
  }

  function clearHistory(): void {
    undoStack.value = []
    redoStack.value = []
  }

  return {
    // State
    isProcessing,
    lastError,
    processingPlantId,
    // Undo/Redo
    canUndo,
    canRedo,
    undoStack,
    redoStack,
    // Methods
    handlePlantSubzoneChange,
    handleRemovePlantFromSubzone,
    undo,
    redo,
    clearHistory,
  }
}
