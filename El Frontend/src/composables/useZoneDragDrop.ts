/**
 * useZoneDragDrop Composable
 *
 * Handles zone drag & drop operations with:
 * - Optimistic UI updates
 * - API calls for zone assignment
 * - Error handling with rollback
 * - Toast notifications
 */

import { ref, computed } from 'vue'

// =============================================================================
// Constants (CONSISTENCY fix: Replace magic strings with exported constants)
// =============================================================================

/**
 * Zone ID for unassigned devices.
 * Used throughout the drag-drop system to identify devices without zone assignment.
 * Export this constant and use it instead of hardcoded '__unassigned__' strings.
 */
export const ZONE_UNASSIGNED = '__unassigned__' as const

/**
 * Display name for unassigned zone.
 */
export const ZONE_UNASSIGNED_DISPLAY_NAME = 'Nicht zugewiesen' as const
import { zonesApi } from '@/api/zones'
import { useEspStore } from '@/stores/esp'
import { useToast } from './useToast'
import type { ESPDevice } from '@/api/esp'
import { createLogger } from '@/utils/logger'

const logger = createLogger('ZoneDragDrop')

interface ZoneDropEvent {
  device: ESPDevice
  fromZoneId: string | null
  toZoneId: string
}

interface ZoneGrouping {
  zoneId: string
  zoneName: string
  devices: ESPDevice[]
}

/**
 * History entry for undo/redo
 */
interface ZoneHistoryEntry {
  deviceId: string
  deviceName: string
  fromZoneId: string | null
  fromZoneName: string | null
  toZoneId: string | null
  toZoneName: string | null
  timestamp: number
}

export function useZoneDragDrop() {
  const espStore = useEspStore()
  const toast = useToast()

  // State
  const isProcessing = ref(false)
  const lastError = ref<string | null>(null)
  const processingDeviceId = ref<string | null>(null)

  // Undo/Redo History (max 20 entries)
  const MAX_HISTORY = 20
  const undoStack = ref<ZoneHistoryEntry[]>([])
  const redoStack = ref<ZoneHistoryEntry[]>([])

  // Computed properties for undo/redo availability
  const canUndo = computed(() => undoStack.value.length > 0 && !isProcessing.value)
  const canRedo = computed(() => redoStack.value.length > 0 && !isProcessing.value)

  /**
   * Generate zone_name from zone_id (reverse of the normal flow)
   * Used for display when only zone_id is available
   * "zelt_1" -> "Zelt 1", "gewaechshaus_nord" -> "Gewaechshaus Nord"
   */
  function zoneIdToDisplayName(zoneId: string): string {
    if (!zoneId) return ''
    return zoneId
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  /**
   * Generate technical zone_id from human-readable zone_name
   * Mirrors server-side logic
   * "Zelt 1" -> "zelt_1", "Gewächshaus Nord" -> "gewaechshaus_nord"
   */
  function generateZoneId(zoneName: string): string {
    if (!zoneName) return ''
    let zoneId = zoneName.toLowerCase()
    // Replace German umlauts
    zoneId = zoneId.replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    // Replace spaces and special chars with underscores
    zoneId = zoneId.replace(/[^a-z0-9]+/g, '_')
    // Remove leading/trailing underscores
    zoneId = zoneId.replace(/^_+|_+$/g, '')
    return zoneId
  }

  /**
   * Add entry to undo stack (clears redo stack)
   */
  function pushToHistory(entry: ZoneHistoryEntry) {
    undoStack.value.push(entry)
    // Limit history size
    if (undoStack.value.length > MAX_HISTORY) {
      undoStack.value.shift()
    }
    // Clear redo stack on new action
    redoStack.value = []
  }

  /**
   * Group devices by zone
   * Returns array of zone groups including an "unassigned" group
   * ALWAYS includes the ZONE_UNASSIGNED group (even if empty) as a drop target
   */
  function groupDevicesByZone(devices: ESPDevice[]): ZoneGrouping[] {
    const zoneMap = new Map<string, ZoneGrouping>()

    // ALWAYS create unassigned group as drop target (even if empty)
    zoneMap.set(ZONE_UNASSIGNED, {
      zoneId: ZONE_UNASSIGNED,
      zoneName: ZONE_UNASSIGNED_DISPLAY_NAME,
      devices: []
    })

    // Group devices
    for (const device of devices) {
      const zoneId = device.zone_id || ZONE_UNASSIGNED
      const zoneName = device.zone_name || (zoneId !== ZONE_UNASSIGNED ? zoneIdToDisplayName(zoneId) : ZONE_UNASSIGNED_DISPLAY_NAME) || zoneId

      if (!zoneMap.has(zoneId)) {
        zoneMap.set(zoneId, {
          zoneId,
          zoneName,
          devices: []
        })
      }

      zoneMap.get(zoneId)!.devices.push(device)
    }

    // Convert to array and sort (unassigned last)
    const groups = Array.from(zoneMap.values())
    groups.sort((a, b) => {
      if (a.zoneId === ZONE_UNASSIGNED) return 1
      if (b.zoneId === ZONE_UNASSIGNED) return -1
      return (a.zoneName ?? '').localeCompare(b.zoneName ?? '')
    })

    return groups
  }

  /**
   * Get all unique zones from devices
   */
  function getAvailableZones(devices: ESPDevice[]): { zoneId: string; zoneName: string }[] {
    const zones = new Map<string, string>()

    for (const device of devices) {
      if (device.zone_id) {
        const zoneName = device.zone_name || zoneIdToDisplayName(device.zone_id)
        zones.set(device.zone_id, zoneName)
      }
    }

    return Array.from(zones.entries())
      .map(([zoneId, zoneName]) => ({ zoneId, zoneName }))
      .sort((a, b) => (a.zoneName ?? '').localeCompare(b.zoneName ?? ''))
  }

  /**
   * Handle device drop - assign device to new zone
   * Makes single API call to zonesApi.assignZone() which handles DB + MQTT
   */
  async function handleDeviceDrop(event: ZoneDropEvent): Promise<boolean> {
    const { device, fromZoneId, toZoneId } = event
    const deviceId = device.device_id || device.esp_id || ''

    // Skip if dropping to same zone
    if (fromZoneId === toZoneId) {
      return true
    }

    // Skip if dropping to unassigned (use removeZone instead)
    if (toZoneId === ZONE_UNASSIGNED) {
      return handleRemoveFromZone(device)
    }

    isProcessing.value = true
    processingDeviceId.value = deviceId
    lastError.value = null

    try {
      // Single API call - handles DB update and MQTT publish
      const response = await zonesApi.assignZone(deviceId, {
        zone_id: toZoneId,
        zone_name: zoneIdToDisplayName(toZoneId)
      })

      if (!response.success) {
        throw new Error(response.message || 'Zone-Zuweisung fehlgeschlagen')
      }

      // Refresh store from server to get updated data
      await espStore.fetchAll()

      // Success toast
      const deviceName = device.name || deviceId
      const zoneName = zoneIdToDisplayName(toZoneId)
      const isSimulation = espStore.isMock(deviceId)
      toast.info(`${isSimulation ? '[Simulation] ' : ''}Zuweisungsauftrag akzeptiert: "${deviceName}" → "${zoneName}"`, {
        dedupeKey: `zone-assign-accepted:${deviceId}:${toZoneId}`,
      })

      // Record in history for undo
      pushToHistory({
        deviceId,
        deviceName,
        fromZoneId: fromZoneId,
        fromZoneName: fromZoneId ? zoneIdToDisplayName(fromZoneId) : null,
        toZoneId: toZoneId,
        toZoneName: zoneName,
        timestamp: Date.now()
      })

      logger.debug(`Assigned ${deviceId} → ${toZoneId}`)
      return true

    } catch (error) {
      logger.error(`Failed to assign ${deviceId} to ${toZoneId}`, error)

      // Refresh store to ensure consistent state
      await espStore.fetchAll()

      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage

      // Error toast with retry action
      toast.error(`Zone-Zuweisung fehlgeschlagen: ${errorMessage}`, {
        duration: 8000,
        actions: [
          {
            label: 'Erneut versuchen',
            variant: 'primary',
            onClick: async () => { await handleDeviceDrop(event) }
          }
        ]
      })

      return false

    } finally {
      isProcessing.value = false
      processingDeviceId.value = null
    }
  }

  /**
   * Remove device from zone (assign to unassigned)
   * Makes single API call to zonesApi.removeZone() which handles DB + MQTT
   */
  async function handleRemoveFromZone(device: ESPDevice): Promise<boolean> {
    const deviceId = device.device_id || device.esp_id || ''

    if (!device.zone_id) {
      // Already unassigned
      return true
    }

    isProcessing.value = true
    processingDeviceId.value = deviceId
    lastError.value = null

    // Store original zone info for toast message
    const originalZoneId = device.zone_id
    const originalZoneName = device.zone_name

    try {
      // Single API call - handles DB update and MQTT publish
      const response = await zonesApi.removeZone(deviceId)

      if (!response.success) {
        throw new Error(response.message || 'Zone-Entfernung fehlgeschlagen')
      }

      // Refresh store from server to get updated data
      await espStore.fetchAll()

      // Success toast
      const deviceName = device.name || deviceId
      const zoneName = originalZoneName || zoneIdToDisplayName(originalZoneId)
      const isSimulation = espStore.isMock(deviceId)
      toast.info(`${isSimulation ? '[Simulation] ' : ''}Entfernungsauftrag akzeptiert: "${deviceName}" aus "${zoneName}"`, {
        dedupeKey: `zone-remove-accepted:${deviceId}:${originalZoneId}`,
      })

      // Record in history for undo
      pushToHistory({
        deviceId,
        deviceName,
        fromZoneId: originalZoneId,
        fromZoneName: zoneName,
        toZoneId: null,
        toZoneName: null,
        timestamp: Date.now()
      })

      logger.info(`Successfully removed ${deviceId} from zone`)
      return true

    } catch (error) {
      logger.error('Failed to remove zone', error)

      // Refresh store to ensure consistent state
      await espStore.fetchAll()

      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage

      // Error toast with retry action
      toast.error(`Zone-Entfernung fehlgeschlagen: ${errorMessage}`, {
        duration: 8000,
        actions: [
          {
            label: 'Erneut versuchen',
            variant: 'primary',
            onClick: async () => { await handleRemoveFromZone(device) }
          }
        ]
      })

      return false

    } finally {
      isProcessing.value = false
      processingDeviceId.value = null
    }
  }

  /**
   * Undo the last zone assignment
   * Reverses the last operation by assigning device back to previous zone
   */
  async function undo(): Promise<boolean> {
    if (!canUndo.value) return false

    const entry = undoStack.value.pop()
    if (!entry) return false

    isProcessing.value = true
    processingDeviceId.value = entry.deviceId
    lastError.value = null

    try {
      // Reverse the operation: assign back to fromZoneId
      if (entry.fromZoneId) {
        // Was assigned to a zone, assign back
        const response = await zonesApi.assignZone(entry.deviceId, {
          zone_id: entry.fromZoneId,
          zone_name: entry.fromZoneName || zoneIdToDisplayName(entry.fromZoneId)
        })
        if (!response.success) {
          throw new Error(response.message || 'Undo fehlgeschlagen')
        }
      } else {
        // Was unassigned, remove zone
        const response = await zonesApi.removeZone(entry.deviceId)
        if (!response.success) {
          throw new Error(response.message || 'Undo fehlgeschlagen')
        }
      }

      // Refresh store
      await espStore.fetchAll()

      // Push to redo stack
      redoStack.value.push(entry)

      // Success toast
      const targetZone = entry.fromZoneName || 'Nicht zugewiesen'
      toast.success(`Rückgängig: "${entry.deviceName}" → "${targetZone}"`)

      logger.debug(`Undo: ${entry.deviceId} → ${entry.fromZoneId || 'unassigned'}`)
      return true

    } catch (error) {
      logger.error('Undo failed', error)

      // Put entry back on undo stack
      undoStack.value.push(entry)

      // Refresh store to ensure consistent state
      await espStore.fetchAll()

      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage
      toast.error(`Rückgängig fehlgeschlagen: ${errorMessage}`)

      return false

    } finally {
      isProcessing.value = false
      processingDeviceId.value = null
    }
  }

  /**
   * Redo the last undone zone assignment
   * Re-applies the previously undone operation
   */
  async function redo(): Promise<boolean> {
    if (!canRedo.value) return false

    const entry = redoStack.value.pop()
    if (!entry) return false

    isProcessing.value = true
    processingDeviceId.value = entry.deviceId
    lastError.value = null

    try {
      // Re-apply the original operation: assign to toZoneId
      if (entry.toZoneId) {
        // Was assigned to a zone
        const response = await zonesApi.assignZone(entry.deviceId, {
          zone_id: entry.toZoneId,
          zone_name: entry.toZoneName || zoneIdToDisplayName(entry.toZoneId)
        })
        if (!response.success) {
          throw new Error(response.message || 'Wiederherstellen fehlgeschlagen')
        }
      } else {
        // Was removed from zone
        const response = await zonesApi.removeZone(entry.deviceId)
        if (!response.success) {
          throw new Error(response.message || 'Wiederherstellen fehlgeschlagen')
        }
      }

      // Refresh store
      await espStore.fetchAll()

      // Push back to undo stack
      undoStack.value.push(entry)

      // Success toast
      const targetZone = entry.toZoneName || 'Nicht zugewiesen'
      toast.success(`Wiederherstellen: "${entry.deviceName}" → "${targetZone}"`)

      logger.debug(`Redo: ${entry.deviceId} → ${entry.toZoneId || 'unassigned'}`)
      return true

    } catch (error) {
      logger.error('Redo failed', error)

      // Put entry back on redo stack
      redoStack.value.push(entry)

      // Refresh store to ensure consistent state
      await espStore.fetchAll()

      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler'
      lastError.value = errorMessage
      toast.error(`Wiederherstellen fehlgeschlagen: ${errorMessage}`)

      return false

    } finally {
      isProcessing.value = false
      processingDeviceId.value = null
    }
  }

  /**
   * Clear undo/redo history
   */
  function clearHistory() {
    undoStack.value = []
    redoStack.value = []
  }

  return {
    // State
    isProcessing,
    lastError,
    processingDeviceId,

    // Undo/Redo State
    canUndo,
    canRedo,
    undoStack,
    redoStack,

    // Methods
    groupDevicesByZone,
    getAvailableZones,
    handleDeviceDrop,
    handleRemoveFromZone,
    generateZoneId,
    zoneIdToDisplayName,

    // Undo/Redo Methods
    undo,
    redo,
    clearHistory
  }
}
