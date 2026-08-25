/**
 * Monitor L1 zone-tile — lead sensor pick for Zoneinsight (24h stats), aligned with legacy auto-gauge priority.
 */
import type { ESPDevice } from '@/api/esp'
import { getSensorAggCategory, getZoneTileSensorPriority } from '@/utils/sensorDefaults'

export function pickZoneLeadTemperatureSensor(
  devices: ESPDevice[],
  zoneId: string,
  getDeviceId: (d: ESPDevice) => string,
): { espId: string; gpio: number; sensorType: string } | null {
  const found: { espId: string; gpio: number; sensorType: string }[] = []
  for (const device of devices) {
    if (device.zone_id !== zoneId) continue
    const espId = getDeviceId(device)
    for (const s of (device.sensors || []) as { gpio: number; sensor_type: string }[]) {
      if (getSensorAggCategory(s.sensor_type) !== 'temperature') continue
      found.push({ espId, gpio: s.gpio, sensorType: s.sensor_type })
    }
  }
  if (found.length === 0) return null
  // Priority first; then stable tie-break (espId/gpio) so WS device reshuffles
  // do not flip the 24h-stats lead sensor and re-trigger fetches.
  found.sort((a, b) => {
    const byPriority =
      getZoneTileSensorPriority(a.sensorType) - getZoneTileSensorPriority(b.sensorType)
    if (byPriority !== 0) return byPriority
    const byEsp = a.espId.localeCompare(b.espId)
    if (byEsp !== 0) return byEsp
    return a.gpio - b.gpio
  })
  return found[0] ?? null
}
