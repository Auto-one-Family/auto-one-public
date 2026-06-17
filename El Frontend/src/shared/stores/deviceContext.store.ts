/**
 * Device Context Store (T13-R2 / Auftrag 6.7)
 *
 * Holds active zone/subzone context for mobile and multi_zone devices.
 * Context is fetched per-device via GET /device-context/{config_type}/{config_id}
 * and kept up-to-date via the device_context_changed WebSocket event.
 *
 * Only relevant for device_scope !== 'zone_local' (< 5% of devices).
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { deviceContextApi } from '@/api/device-context'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type { DeviceContextResponse } from '@/types'

const logger = createLogger('DeviceContextStore')

export const useDeviceContextStore = defineStore('deviceContext', () => {
  /** Map: config_id → DeviceContextResponse */
  const contexts = ref<Map<string, DeviceContextResponse>>(new Map())

  /** Whether initial bulk load has completed */
  const isLoaded = ref(false)

  /**
   * Load contexts for a list of non-zone_local sensors/actuators.
   * Called once on MonitorView mount. Individual failures are silently skipped.
   */
  async function loadContextsForDevices(
    devices: Array<{ configType: 'sensor' | 'actuator'; configId: string }>
  ): Promise<void> {
    const results = await Promise.allSettled(
      devices.map(async (d) => {
        const ctx = await deviceContextApi.getContext(d.configType, d.configId)
        if (ctx.active_zone_id) {
          contexts.value.set(d.configId, ctx)
        }
      })
    )
    const failed = results.filter(r => r.status === 'rejected').length
    if (failed > 0) {
      logger.warn(`Failed to load ${failed}/${devices.length} device contexts`)
    }
    isLoaded.value = true
  }

  /**
   * Set active zone context for a sensor or actuator (PUT API call).
   */
  async function setContext(
    configType: 'sensor' | 'actuator',
    configId: string,
    activeZoneId: string | null,
    activeSubzoneId: string | null = null,
  ): Promise<void> {
    const toast = useToast()
    try {
      const response = await deviceContextApi.setContext(configType, configId, {
        active_zone_id: activeZoneId,
        active_subzone_id: activeSubzoneId,
      })
      contexts.value.set(configId, response)
      toast.success(activeZoneId ? 'Zone-Kontext gesetzt' : 'Zone-Kontext entfernt')
    } catch (e) {
      logger.error('Failed to set device context', e)
      toast.error('Zone konnte nicht gewechselt werden')
      throw e
    }
  }

  /**
   * Clear active context (DELETE API call).
   */
  async function clearContext(
    configType: 'sensor' | 'actuator',
    configId: string,
  ): Promise<void> {
    const toast = useToast()
    try {
      await deviceContextApi.clearContext(configType, configId)
      contexts.value.delete(configId)
      toast.success('Zone-Kontext entfernt')
    } catch (e) {
      logger.error('Failed to clear device context', e)
      toast.error('Zone-Kontext konnte nicht entfernt werden')
      throw e
    }
  }

  /**
   * Handle device_context_changed WebSocket event.
   * Updates local store only — no API call.
   */
  function handleContextChanged(payload: {
    config_type: 'sensor' | 'actuator'
    config_id: string
    active_zone_id: string | null
    active_subzone_id: string | null
    context_source?: string
    context_since?: string | null
  }): void {
    if (payload.active_zone_id) {
      contexts.value.set(payload.config_id, {
        success: true,
        config_type: payload.config_type,
        config_id: payload.config_id,
        active_zone_id: payload.active_zone_id,
        active_subzone_id: payload.active_subzone_id ?? null,
        context_source: payload.context_source ?? 'manual',
        context_since: payload.context_since ?? new Date().toISOString(),
      })
    } else {
      contexts.value.delete(payload.config_id)
    }
  }

  /**
   * Get active zone ID for a given config_id (or null if no context).
   */
  function getActiveZoneId(configId: string): string | null {
    return contexts.value.get(configId)?.active_zone_id ?? null
  }

  /**
   * Get full context for a given config_id (or null).
   */
  function getContext(configId: string): DeviceContextResponse | null {
    return contexts.value.get(configId) ?? null
  }

  function $reset(): void {
    contexts.value.clear()
    isLoaded.value = false
  }

  return {
    contexts,
    isLoaded,
    loadContextsForDevices,
    setContext,
    clearContext,
    handleContextChanged,
    getActiveZoneId,
    getContext,
    $reset,
  }
})
