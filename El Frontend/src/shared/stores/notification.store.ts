/**
 * Notification Store
 *
 * Handles notification, error_event, and system_event WebSocket events.
 * Shows toast notifications for server-side events.
 *
 * Server-centric architecture:
 * Server (logic engine, system monitor) → WS (notification) → this store
 * Server (error tracker) → WS (error_event) → this store
 * Server (system events) → WS (system_event) → this store
 *
 * Cross-store dependency: Receives devices array from esp.store.ts via dispatcher.
 */

import { defineStore } from 'pinia'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type { ESPDevice } from '@/api/esp'

const logger = createLogger('NotificationStore')

export const useNotificationStore = defineStore('notification', () => {

  /**
   * Handle notification WebSocket event.
   * Shows toast from server notifications (logic rules, system).
   */
  function handleNotification(message: { data: Record<string, unknown> }): void {
    const data = message.data
    const title = data.title as string || 'Benachrichtigung'
    const msg = data.message as string || ''
    const priority = data.priority as string || 'normal'

    const toast = useToast()
    const toastType = priority === 'high' ? 'warning' : 'info'
    toast.show({ message: `${title}: ${msg}`, type: toastType, persistent: priority === 'high' })
  }

  /**
   * Handle error_event WebSocket event.
   * Shows toast with troubleshooting info.
   * Server: error_tracker → WS: error_event
   */
  function handleErrorEvent(
    message: { data: Record<string, unknown> },
    devices: ESPDevice[],
    getDeviceId: (d: ESPDevice) => string,
  ): void {
    const data = message.data
    const espId = data.esp_id as string || data.source_id as string
    const severity = data.severity as string || 'error'
    const title = data.title as string | undefined
    const msg = data.message as string || 'Unbekannter Fehler'
    const errorCode = data.error_code as number | undefined
    const userActionRequired = data.user_action_required as boolean | undefined
    const troubleshooting = data.troubleshooting as string[] | undefined

    const toast = useToast()
    const deviceName = espId
      ? (devices.find(d => getDeviceId(d) === espId)?.name || espId)
      : 'System'

    // Use title (short) if available, otherwise fall back to message
    const displayTitle = title || msg
    const displayMsg = userActionRequired
      ? `${deviceName}: ${displayTitle} — Handlungsbedarf`
      : `${deviceName}: ${displayTitle}${errorCode ? ` (${errorCode})` : ''}`

    // Build action for troubleshooting details if available
    const actions: Array<{ label: string; onClick: () => void; variant?: 'primary' | 'secondary' }> = []
    if (troubleshooting && troubleshooting.length > 0) {
      actions.push({
        label: 'Details',
        variant: 'secondary',
        onClick: () => {
          // Emit a custom event so the SystemMonitor can show the ErrorDetailsModal
          window.dispatchEvent(new CustomEvent('show-error-details', {
            detail: {
              error_code: errorCode,
              title: title || `Fehler ${errorCode}`,
              description: msg,
              severity,
              troubleshooting,
              user_action_required: userActionRequired ?? false,
              esp_id: espId,
              esp_name: deviceName,
              docs_link: data.docs_link as string | null | undefined,
              context: data.context as Record<string, unknown> | undefined,
              timestamp: data.timestamp as string | undefined,
            },
          }))
        },
      })
    }

    toast.show({
      message: `Echtzeit · ${displayMsg}`,
      type: severity === 'critical' ? 'error' : severity === 'warning' ? 'warning' : severity === 'info' ? 'info' : 'error',
      persistent: severity === 'critical' || severity === 'error',
      actions: actions.length > 0 ? actions : undefined,
    })

    logger.info(`Error event: ${deviceName} - ${errorCode || 'N/A'} - ${severity}`)
  }

  /**
   * Handle system_event WebSocket event.
   * Shows info toast for system events.
   */
  function handleSystemEvent(message: { data: Record<string, unknown> }): void {
    const data = message.data
    const msg = data.message as string || 'System-Ereignis'

    const toast = useToast()
    toast.info(msg)
  }

  return {
    handleNotification,
    handleErrorEvent,
    handleSystemEvent,
  }
})
