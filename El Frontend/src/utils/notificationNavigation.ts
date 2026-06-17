import type { RouteLocationRaw } from 'vue-router'
import type { NotificationDTO } from '@/api/notifications'
import type { ESPDevice } from '@/api/esp'

/**
 * Kontextabhängige ESP-Navigation für Notification/Alert-Entry-Points.
 * - Zone verfügbar -> Monitor L2
 * - sonst -> Hardware mit openSettings
 */
export function buildEspContextRoute(
  notification: NotificationDTO,
  devices: ESPDevice[],
): RouteLocationRaw | null {
  const metadata = notification.metadata ?? {}
  const espId = typeof metadata.esp_id === 'string' ? metadata.esp_id : null
  if (!espId) return null

  const metadataZoneId = typeof metadata.zone_id === 'string' ? metadata.zone_id : null
  const deviceZoneId = devices.find(d => d.esp_id === espId)?.zone_id ?? null
  const resolvedZoneId = metadataZoneId || deviceZoneId

  if (resolvedZoneId) {
    return { path: `/monitor/${resolvedZoneId}` }
  }

  return {
    path: '/hardware',
    query: { openSettings: espId },
  }
}
