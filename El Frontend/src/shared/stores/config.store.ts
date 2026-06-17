/**
 * Config Store
 *
 * Handles config lifecycle WebSocket events.
 * Mirrors server-side config_publisher and config_ack_handler.
 *
 * Server-centric architecture:
 * Frontend → REST (POST /esp/{id}/config) → Server → MQTT → ESP32
 * ESP32 → MQTT (kaiser/{esp_id}/config/response) → Server → WS (config_response) → this store
 * Server → WS (config_published) → this store (config sent to ESP via MQTT)
 * Server → WS (config_failed) → this store (MQTT publish failed)
 *
 * Cross-store dependency: Receives devices array from esp.store.ts via dispatcher.
 *
 * TOAST DEDUPLICATION NOTE:
 * actuator.store handles config_response/config_failed intent-lifecycle and emits terminal
 * toasts via waitForConfigTerminal() in SensorConfigPanel / ActuatorConfigPanel.
 * To avoid double-toasts, config.store checks if actuator.store has a tracked intent for
 * the correlation_id. When a tracked intent exists the panel already emits the terminal
 * toast — this store suppresses the generic toast in that case.
 * Partial_success detail toasts and offline-rules-stripped warnings are always shown.
 * config_published generic toast is handled exclusively by actuator.store.
 */

import { defineStore } from 'pinia'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import { extractCorrelationId } from '@/utils/contractEventMapper'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import type { ESPDevice } from '@/api/esp'
import type { ConfigResponseExtended, ConfigFailure } from '@/types'
import type { OfflineRuleStrippedEntry } from '@/types/websocket-events'

const logger = createLogger('ConfigStore')

export const useConfigStore = defineStore('config', () => {

  /**
   * Returns true when actuator.store has a tracked (pending or terminal) config intent
   * for the given correlation_id. In that case the panel's waitForConfigTerminal will
   * emit the terminal toast and this store must not emit a duplicate.
   */
  function hasTrackedConfigIntent(correlationId: string | null | undefined): boolean {
    if (!correlationId) return false
    try {
      const actStore = useActuatorStore()
      const snapshot = actStore.getIntentSnapshot()
      return snapshot.some(
        (i) => i.intentType === 'config' && i.correlationId === correlationId,
      )
    } catch {
      return false
    }
  }

  /**
   * Handle config_response WebSocket event.
   * Shows toast notification when ESP confirms config changes.
   *
   * DEDUP POLICY:
   * - When actuator.store has a tracked intent for this correlation_id, the panel's
   *   waitForConfigTerminal will emit the terminal toast → we suppress the generic toast here.
   * - partial_success and error detail failures arrays are always shown as operator detail.
   *
   * Phase 4: Extended to handle partial_success and failures array
   * - Max 3 detail toasts for individual failures
   * - Additional failures logged to console
   */
  function handleConfigResponse(
    message: { data: Record<string, unknown> },
    devices: ESPDevice[],
    getDeviceId: (d: ESPDevice) => string,
    refreshGpioStatus: (espId: string) => void,
  ): void {
    const data = message.data as unknown as ConfigResponseExtended
    const toast = useToast()

    if (!data.esp_id) return

    const correlationId = extractCorrelationId(message.data)
    const isTracked = hasTrackedConfigIntent(correlationId)
    const deviceName = devices.find(d => getDeviceId(d) === data.esp_id)?.name || data.esp_id
    const MAX_DETAIL_TOASTS = 3

    if (data.status === 'success') {
      if (!isTracked) {
        // Only emit toast when no intent is tracked (headless / reconnect config push).
        // When a panel is open, waitForConfigTerminal in the panel emits the success toast.
        const msg = data.message || 'Konfiguration gespeichert'
        toast.success(
          `${deviceName}: ${msg}`,
          { duration: 4000 },
        )
      }
      logger.info(`Config success: ${data.esp_id} - ${data.config_type} (${data.count})`)
    } else if (data.status === 'partial_success') {
      // Phase 4: Partial success — always show (operator info with detail breakdown)
      toast.warning(
        `${deviceName}: ${data.count} konfiguriert, ${data.failed_count || 0} fehlgeschlagen`,
        { duration: 6000 },
      )
      logger.warn(`Config partial_success: ${data.esp_id} - ${data.count} OK, ${data.failed_count} failed`)

      // Show detail toasts for individual failures (max 3)
      if (data.failures && data.failures.length > 0) {
        const toShow = data.failures.slice(0, MAX_DETAIL_TOASTS)
        toShow.forEach((failure: ConfigFailure) => {
          toast.error(
            `GPIO ${failure.gpio} (${failure.type}): ${failure.error}${failure.detail ? ` - ${failure.detail}` : ''}`,
            { duration: 8000 },
          )
        })

        if (data.failures.length > MAX_DETAIL_TOASTS) {
          const remaining = data.failures.slice(MAX_DETAIL_TOASTS)
          logger.warn(`${remaining.length} additional failures (not shown in toast):`)
          remaining.forEach((failure: ConfigFailure) => {
            logger.warn(`  - GPIO ${failure.gpio} (${failure.type}): ${failure.error} - ${failure.detail || 'No details'}`)
          })
        }
      }
    } else {
      // Full error — only emit generic error toast when no intent is tracked.
      // When a panel is open, waitForConfigTerminal in the panel emits the error toast.
      if (!isTracked) {
        toast.error(
          `${deviceName}: ${data.error_code || 'CONFIG_ERROR'} - ${data.message || 'Konfiguration fehlgeschlagen'}`,
          { duration: 6000 },
        )
      }
      logger.error(`Config error: ${data.esp_id} - ${data.error_code}`)

      // Phase 4: Detail failure toasts are always shown (operator context)
      if (data.failures && data.failures.length > 0) {
        const toShow = data.failures.slice(0, MAX_DETAIL_TOASTS)
        toShow.forEach((failure: ConfigFailure) => {
          toast.error(
            `GPIO ${failure.gpio}: ${failure.detail || failure.error}`,
            { duration: 8000 },
          )
        })

        if (data.failures.length > MAX_DETAIL_TOASTS) {
          const remaining = data.failures.slice(MAX_DETAIL_TOASTS)
          logger.error(`${remaining.length} additional failures:`)
          remaining.forEach((failure: ConfigFailure) => {
            logger.error(`  - GPIO ${failure.gpio}: ${failure.error} - ${failure.detail || 'No details'}`)
          })
        }
      } else if (data.failed_item) {
        // Legacy: Single failed_item (backward compatibility)
        const item = data.failed_item
        toast.error(
          `GPIO ${item.gpio || 'N/A'}: ${item.sensor_type || item.actuator_type || 'Unknown'}`,
          { duration: 8000 },
        )
      }
    }

    // Refresh GPIO status after config change
    refreshGpioStatus(data.esp_id)
  }

  /**
   * Handle config_published WebSocket event.
   * Shows operator warning when offline rules were stripped (AUT-132).
   *
   * DEDUP NOTE: actuator.store already handles config_published and emits the
   * non-terminal "config gesendet" / "gequeued" info-toast. We only emit here
   * for the offline-rules-stripped warning (diagnostic info not covered by actuator.store).
   */
  function handleConfigPublished(
    message: { data: Record<string, unknown> },
    devices: ESPDevice[],
    getDeviceId: (d: ESPDevice) => string,
  ): void {
    const data = message.data
    const espId = data.esp_id as string
    if (!espId) return

    const toast = useToast()
    const deviceName = devices.find(d => getDeviceId(d) === espId)?.name || espId

    const diagnostics = data.offline_rules_diagnostics as {
      stripped_count?: number
      stripped_rules?: Array<Partial<OfflineRuleStrippedEntry>>
    } | undefined
    if (diagnostics && (diagnostics.stripped_count ?? 0) > 0) {
      const count = diagnostics.stripped_count!
      const examples = (diagnostics.stripped_rules ?? []).slice(0, 2)
        .map(r => {
          const gpioStr = r.actuator_gpio != null ? `GPIO ${r.actuator_gpio}` : 'GPIO ?'
          const detail = r.reason_detail
            ? ` [${r.reason_detail.substring(0, 80)}${r.reason_detail.length > 80 ? '…' : ''}]`
            : ''
          const hint = r.resolution_hint ? ` → ${r.resolution_hint}` : ''
          return `${r.rule_name ?? 'Regel'} (${gpioStr}: ${r.reason_code ?? '?'}${detail}${hint})`
        })
        .join('; ')
      const suffix = examples ? ` — ${examples}` : ''
      logger.warn(`AUT-132: ${count} Offline-Regel(n) nicht gesendet für ${espId}${suffix}`)
      toast.warning(
        `${deviceName}: ${count} Offline-Regel${count > 1 ? 'n' : ''} nicht gesendet${suffix}`,
        { duration: 8000 },
      )
    }
  }

  /**
   * Handle config_failed WebSocket event.
   * Notifies that config publishing failed (MQTT-level publish failure, not ESP response).
   *
   * DEDUP NOTE: actuator.store handles config_failed intent finalization and will emit
   * a terminal toast via waitForConfigTerminal. We suppress the generic toast here when
   * a tracked intent exists to avoid double-toasting.
   */
  function handleConfigFailed(
    message: { data: Record<string, unknown> },
    devices: ESPDevice[],
    getDeviceId: (d: ESPDevice) => string,
  ): void {
    const data = message.data
    const espId = data.esp_id as string
    const error = (data.error as string) || 'Unbekannter Fehler'
    const reason = typeof data.reason_code === 'string' ? data.reason_code : null
    const generation = typeof data.generation === 'number' ? data.generation : null
    if (!espId) return

    const correlationId = extractCorrelationId(data)
    const isTracked = hasTrackedConfigIntent(correlationId)

    if (isTracked) {
      // Panel's waitForConfigTerminal will emit the terminal error toast.
      logger.info(`Config failed suppressed in config.store (tracked intent): ${espId}`)
      return
    }

    const toast = useToast()
    const deviceName = devices.find(d => getDeviceId(d) === espId)?.name || espId
    const reasonDetail = reason ? ` (Grund: ${reason})` : ''
    const generationDetail = generation ? ` [Gen ${generation}]` : ''
    toast.error(
      `Konfiguration für ${deviceName} fehlgeschlagen${reasonDetail}${generationDetail}: ${error}`,
      { persistent: true },
    )
  }

  return {
    handleConfigResponse,
    handleConfigPublished,
    handleConfigFailed,
  }
})
