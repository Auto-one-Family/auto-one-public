/**
 * Zone Store
 *
 * Handles zone entity CRUD (T13-R1) and WebSocket events for zone/subzone
 * assignment and device scope/context changes (T13-R2).
 *
 * Server-centric architecture:
 * ESP32 → MQTT (kaiser/{esp_id}/zone/ack) → Server → WS (zone_assignment) → this store
 * ESP32 → MQTT (kaiser/{esp_id}/subzone/ack) → Server → WS (subzone_assignment) → this store
 * Frontend → REST → Server → WS (device_scope_changed / device_context_changed) → this store
 *
 * Cross-store dependency: Uses useEspStore() for devices state.
 * The WS dispatcher in esp.store.ts delegates zone events here.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import {
  formatZoneAckError,
  formatZoneAckRemoved,
  formatZoneAckSuccess,
  formatSubzoneAckError,
  formatSubzoneAckSuccess,
  formatSubzoneRemoved,
} from '@/domain/zone/ackPresentation'
import { zonesApi } from '@/api/zones'
import type { ESPDevice } from '@/api/esp'
import type {
  ZoneEntity, ZoneEntityCreate, ZoneEntityUpdate, ZoneStatus,
} from '@/types'

const logger = createLogger('ZoneStore')

/** Payload shape for zone_assignment WebSocket events */
interface ZoneAssignmentPayload {
  esp_id?: string
  device_id?: string
  status: 'zone_assigned' | 'zone_removed' | 'error'
  zone_id?: string | null
  zone_name?: string | null
  master_zone_id?: string | null
  kaiser_id?: string | null
  timestamp?: number
  message?: string
  /** Brückengrund (MQTT/Firmware), nicht Intent-Outcome-Code */
  reason_code?: string | null
}

/** Payload shape for subzone_assignment WebSocket events */
interface SubzoneAssignmentPayload {
  esp_id?: string
  device_id?: string
  subzone_id?: string
  status: 'subzone_assigned' | 'subzone_removed' | 'error'
  timestamp?: number
  error_code?: string
  message?: string
  /** Brückengrund (MQTT/Firmware), nicht Intent-Outcome-Code */
  reason_code?: string | null
}

type DevicePatchFn = (device: ESPDevice) => ESPDevice
type ApplyDevicePatch = (espId: string, patchFn: DevicePatchFn) => boolean

function patchDeviceDomainByConfig(
  device: ESPDevice,
  payload: Record<string, unknown>,
  patchType: 'scope' | 'context',
): { nextDevice: ESPDevice; patched: boolean } {
  const configType = String(payload.config_type || '').toLowerCase()
  const configId = payload.config_id as string | undefined
  const gpio = payload.gpio as number | undefined

  if (configType === 'sensor' && Array.isArray(device.sensors)) {
    const sensors = (device.sensors as unknown as Array<Record<string, unknown>>).map((sensor) => ({ ...sensor }))
    const idx = sensors.findIndex((sensor) => {
      if (configId && typeof sensor.config_id === 'string') return sensor.config_id === configId
      if (gpio !== undefined && typeof sensor.gpio === 'number') return sensor.gpio === gpio
      return false
    })
    if (idx < 0) return { nextDevice: device, patched: false }

    const target = sensors[idx]
    if (patchType === 'scope') {
      if (payload.device_scope !== undefined) target.device_scope = payload.device_scope
      if (payload.assigned_zones !== undefined) target.assigned_zones = payload.assigned_zones
    } else {
      if (payload.active_zone_id !== undefined) target.active_zone_id = payload.active_zone_id
      if (payload.active_subzone_id !== undefined) target.active_subzone_id = payload.active_subzone_id
      if (payload.context_source !== undefined) target.context_source = payload.context_source
      if (payload.context_since !== undefined) target.context_since = payload.context_since
    }
    return { nextDevice: { ...device, sensors: sensors as unknown as ESPDevice['sensors'] }, patched: true }
  }

  if (configType === 'actuator' && Array.isArray(device.actuators)) {
    const actuators = (device.actuators as unknown as Array<Record<string, unknown>>).map((actuator) => ({ ...actuator }))
    const idx = actuators.findIndex((actuator) => {
      if (configId && typeof actuator.config_id === 'string') return actuator.config_id === configId
      if (gpio !== undefined && typeof actuator.gpio === 'number') return actuator.gpio === gpio
      return false
    })
    if (idx < 0) return { nextDevice: device, patched: false }

    const target = actuators[idx]
    if (patchType === 'scope') {
      if (payload.device_scope !== undefined) target.device_scope = payload.device_scope
      if (payload.assigned_zones !== undefined) target.assigned_zones = payload.assigned_zones
    } else {
      if (payload.active_zone_id !== undefined) target.active_zone_id = payload.active_zone_id
      if (payload.active_subzone_id !== undefined) target.active_subzone_id = payload.active_subzone_id
      if (payload.context_source !== undefined) target.context_source = payload.context_source
      if (payload.context_since !== undefined) target.context_since = payload.context_since
    }
    return { nextDevice: { ...device, actuators: actuators as unknown as ESPDevice['actuators'] }, patched: true }
  }

  return { nextDevice: device, patched: false }
}

export const useZoneStore = defineStore('zone', () => {

  // =========================================================================
  // Zone Entity State (T13-R1)
  // =========================================================================

  const zoneEntities = ref<ZoneEntity[]>([])
  const isLoadingZones = ref(false)

  // =========================================================================
  // Zone Entity Getters
  // =========================================================================

  const activeZones = computed(() =>
    zoneEntities.value.filter(z => z.status === 'active'),
  )

  const archivedZones = computed(() =>
    zoneEntities.value.filter(z => z.status === 'archived'),
  )

  // =========================================================================
  // Zone Entity Actions
  // =========================================================================

  async function fetchZoneEntities(status?: ZoneStatus): Promise<void> {
    isLoadingZones.value = true
    try {
      const response = await zonesApi.listZoneEntities(status)
      zoneEntities.value = response.zones
    } catch (e) {
      logger.error('Failed to fetch zone entities', e)
    } finally {
      isLoadingZones.value = false
    }
  }

  async function createZone(data: ZoneEntityCreate): Promise<ZoneEntity> {
    const zone = await zonesApi.createZoneEntity(data)
    zoneEntities.value.push(zone)
    return zone
  }

  async function updateZone(zoneId: string, data: ZoneEntityUpdate): Promise<void> {
    const updated = await zonesApi.updateZoneEntity(zoneId, data)
    const index = zoneEntities.value.findIndex(z => z.zone_id === zoneId)
    if (index !== -1) {
      zoneEntities.value[index] = updated
    }
  }

  async function archiveZone(zoneId: string): Promise<void> {
    const archived = await zonesApi.archiveZoneEntity(zoneId)
    const index = zoneEntities.value.findIndex(z => z.zone_id === zoneId)
    if (index !== -1) {
      zoneEntities.value[index] = archived
    }
  }

  async function reactivateZone(zoneId: string): Promise<void> {
    const reactivated = await zonesApi.reactivateZoneEntity(zoneId)
    const index = zoneEntities.value.findIndex(z => z.zone_id === zoneId)
    if (index !== -1) {
      zoneEntities.value[index] = reactivated
    }
  }

  async function deleteZoneEntity(zoneId: string): Promise<void> {
    await zonesApi.deleteZoneEntity(zoneId)
    zoneEntities.value = zoneEntities.value.filter(z => z.zone_id !== zoneId)
  }

  // =========================================================================
  // Zone Assignment Handler (existing)
  // =========================================================================

  /**
   * Handle zone_assignment WebSocket event.
   * Updates device zone fields when server confirms zone assignment/removal.
   *
   * Server payload (from zone_ack_handler.py):
   * {
   *   esp_id: string,
   *   status: "zone_assigned" | "zone_removed" | "error",
   *   zone_id: string,
   *   zone_name?: string,
   *   kaiser_id?: string,
   *   master_zone_id?: string,
   *   timestamp: number,
   *   message?: string
   * }
   */
  function handleZoneAssignment(
    message: { data: Record<string, unknown> },
    applyDevicePatch: ApplyDevicePatch,
    getDeviceSnapshot: (espId: string) => ESPDevice | null,
  ): void {
    const data = message.data as unknown as ZoneAssignmentPayload
    const espId = data.esp_id || data.device_id

    if (!espId) {
      logger.warn('zone_assignment missing esp_id')
      return
    }

    const snapshot = getDeviceSnapshot(espId)
    if (!snapshot) {
      logger.debug(`Zone assignment for unknown device: ${espId}`)
      return
    }

    const toast = useToast()

    if (data.status === 'zone_assigned') {
      // DEFENSIVE: only update fields that are DEFINED in the event
      const updates: Partial<ESPDevice> = {}

      if (data.zone_id !== undefined) updates.zone_id = data.zone_id
      if (data.zone_name !== undefined) updates.zone_name = data.zone_name
      if (data.master_zone_id !== undefined) updates.master_zone_id = data.master_zone_id
      if (data.kaiser_id !== undefined) updates.kaiser_id = data.kaiser_id

      applyDevicePatch(espId, (device) => ({ ...device, ...updates }))
      logger.info(`Zone confirmed: ${espId} → ${data.zone_id}${data.zone_name ? ` (${data.zone_name})` : ''} (reactivity triggered)`)

      const deviceName = snapshot.name || espId
      const zoneName = data.zone_name || data.zone_id || 'Zone'
      const { title, bridgeLine } = formatZoneAckSuccess({
        deviceName,
        zoneName,
        reasonCode: data.reason_code,
      })
      toast.success(bridgeLine ? `${title}\n${bridgeLine}` : title)
    } else if (data.status === 'zone_removed') {
      // Capture zone name before clearing fields
      const deviceName = snapshot.name || espId
      const zoneName = snapshot.zone_name || snapshot.zone_id || 'Zone'

      // Clear zone fields on removal. kaiser_id remains unchanged (WP2-F24)
      applyDevicePatch(espId, (device) => ({
        ...device,
        zone_id: undefined,
        zone_name: undefined,
        master_zone_id: undefined,
      }))
      logger.info(`Zone removed: ${espId}`)
      const removed = formatZoneAckRemoved({ deviceName, zoneName, reasonCode: data.reason_code })
      toast.success(removed.bridgeLine ? `${removed.title}\n${removed.bridgeLine}` : removed.title)
    } else if (data.status === 'error') {
      logger.error(`Zone assignment error for ${espId}: ${data.message}`)
      const err = formatZoneAckError({ message: data.message, reasonCode: data.reason_code })
      toast.error(err.bridgeLine ? `${err.headline}\n${err.bridgeLine}` : err.headline)
    } else {
      logger.warn(`Unknown zone_assignment status: ${data.status}`)
    }
  }

  // =========================================================================
  // Subzone Assignment Handler (existing)
  // =========================================================================

  /**
   * Handle subzone_assignment WebSocket event.
   * Updates device subzone fields when server confirms subzone assignment/removal.
   *
   * Server payload (from subzone_ack_handler.py):
   * {
   *   esp_id: string,
   *   subzone_id: string,
   *   status: "subzone_assigned" | "subzone_removed" | "error",
   *   timestamp: number,
   *   error_code?: string,
   *   message?: string
   * }
   */
  /**
   * @returns true if devices should be refreshed (subzone_assigned or subzone_removed)
   */
  function handleSubzoneAssignment(
    message: { data: Record<string, unknown> },
    applyDevicePatch: ApplyDevicePatch,
    getDeviceSnapshot: (espId: string) => ESPDevice | null,
  ): boolean {
    const toast = useToast()
    const data = message.data as unknown as SubzoneAssignmentPayload
    const espId = data.esp_id || data.device_id

    if (!espId) {
      logger.warn('subzone_assignment missing esp_id')
      return false
    }

    const snapshot = getDeviceSnapshot(espId)
    if (!snapshot) {
      logger.debug(`Subzone assignment for unknown device: ${espId}`)
      return false
    }

    if (data.status === 'subzone_assigned') {
      const patched = applyDevicePatch(espId, (device) => {
        if (data.subzone_id === undefined) return device
        return { ...device, subzone_id: data.subzone_id }
      })
      logger.info(`Subzone confirmed: ${espId} → ${data.subzone_id}`)
      const ok = formatSubzoneAckSuccess({
        deviceLabel: snapshot.name || espId,
        reasonCode: data.reason_code,
      })
      toast.success(ok.bridgeLine ? `${ok.title}\n${ok.bridgeLine}` : ok.title)
      // Delta patch reicht in der Regel aus; nur fallback-refresh wenn Patch nicht möglich.
      return !patched
    } else if (data.status === 'subzone_removed') {
      const patched = applyDevicePatch(espId, (device) => ({
        ...device,
        subzone_id: undefined,
        subzone_name: undefined,
      }))
      logger.info(`Subzone removed: ${espId}`)
      const rem = formatSubzoneRemoved({
        deviceLabel: snapshot.name || espId,
        reasonCode: data.reason_code,
      })
      toast.success(rem.bridgeLine ? `${rem.title}\n${rem.bridgeLine}` : rem.title)
      // Delta patch reicht in der Regel aus; nur fallback-refresh wenn Patch nicht möglich.
      return !patched
    } else if (data.status === 'error') {
      logger.error(`Subzone assignment error for ${espId}: ${data.message}`)
      const se = formatSubzoneAckError({
        message: data.message,
        reasonCode: data.reason_code,
        errorCode: data.error_code,
      })
      const parts = [se.headline, se.bridgeLine, se.errorCodeLine].filter(Boolean) as string[]
      toast.error(parts.join('\n'))
    } else {
      logger.warn(`Unknown subzone_assignment status: ${data.status}`)
    }
    return false
  }

  // =========================================================================
  // Device Scope & Context WS Handlers (T13-R2)
  // =========================================================================

  /**
   * Handle device_scope_changed WebSocket event.
   * Returns true when a delta patch was applied.
   */
  function handleDeviceScopeChanged(
    message: { data: Record<string, unknown> },
    applyDevicePatch: ApplyDevicePatch,
    getDeviceSnapshot: (espId: string) => ESPDevice | null,
  ): boolean {
    try {
      const toast = useToast()
      const data = message.data
      const configType = data.config_type as string || 'device'
      const espId = data.esp_id as string || ''
      const fallbackDeviceId = data.device_id as string || ''
      const resolvedEspId = espId || fallbackDeviceId

      if (!resolvedEspId) return false
      if (!getDeviceSnapshot(resolvedEspId)) return false

      let patchedByDomain = false
      const patched = applyDevicePatch(resolvedEspId, (device) => {
        const result = patchDeviceDomainByConfig(device, data, 'scope')
        patchedByDomain = result.patched
        return result.nextDevice
      })

      logger.info(`Device scope changed: ${configType} on ${espId}`, data)
      toast.info(`Geräte-Scope aktualisiert${espId ? ` (${espId})` : ''}`)
      return patched && patchedByDomain
    } catch (e) {
      logger.error('Error handling device_scope_changed', e)
      return false
    }
  }

  /**
   * Handle device_context_changed WebSocket event.
   * Returns true when a delta patch was applied.
   */
  function handleDeviceContextChanged(
    message: { data: Record<string, unknown> },
    applyDevicePatch: ApplyDevicePatch,
    getDeviceSnapshot: (espId: string) => ESPDevice | null,
  ): boolean {
    try {
      const toast = useToast()
      const data = message.data
      const configType = data.config_type as string || 'device'
      const activeZone = data.active_zone_id as string || ''
      const espId = data.esp_id as string || data.device_id as string || ''

      if (!espId) return false
      if (!getDeviceSnapshot(espId)) return false

      let patchedByDomain = false
      const patched = applyDevicePatch(espId, (device) => {
        const result = patchDeviceDomainByConfig(device, data, 'context')
        patchedByDomain = result.patched
        return result.nextDevice
      })

      logger.info(`Device context changed: ${configType} → zone ${activeZone}`, data)
      toast.info(`Geräte-Kontext aktualisiert${activeZone ? ` (Zone: ${activeZone})` : ''}`)
      return patched && patchedByDomain
    } catch (e) {
      logger.error('Error handling device_context_changed', e)
      return false
    }
  }

  return {
    // Zone Entity State
    zoneEntities,
    isLoadingZones,
    // Zone Entity Getters
    activeZones,
    archivedZones,
    // Zone Entity Actions
    fetchZoneEntities,
    createZone,
    updateZone,
    archiveZone,
    reactivateZone,
    deleteZoneEntity,
    // Zone/Subzone Assignment WS Handlers (existing)
    handleZoneAssignment,
    handleSubzoneAssignment,
    // Device Scope/Context WS Handlers (T13-R2)
    handleDeviceScopeChanged,
    handleDeviceContextChanged,
  }
})
