import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useDeviceContextStore } from '@/shared/stores/deviceContext.store'
import { useZoneDragDrop, ZONE_UNASSIGNED } from '@/composables'
import { aggregateZoneSensors } from '@/utils/sensorDefaults'
import { getESPStatus } from '@/composables/useESPStatus'
import { ZONE_STALE_THRESHOLD_MS } from '@/utils/formatters'
import { zonesApi } from '@/api/zones'
import type { MockSensor, MockActuator, ZoneListEntry } from '@/types'

// ---------------------------------------------------------------------------
// Exported Types
// ---------------------------------------------------------------------------

export type ZoneHealthStatus = 'ok' | 'warning' | 'alarm' | 'empty'

export type ZoneAggregation = ReturnType<typeof aggregateZoneSensors>

export interface ZoneKPI {
  zoneId: string
  zoneName: string
  sensorCount: number
  actuatorCount: number
  activeSensors: number
  activeActuators: number
  alarmCount: number
  aggregation: ZoneAggregation
  /** Newest sensor reading timestamp across all devices in this zone */
  lastActivity: string | null
  /** Computed zone health status */
  healthStatus: ZoneHealthStatus
  /** Human-readable reason for the health status (empty for 'ok') */
  healthReason: string
  /** Number of online ESP devices in this zone */
  onlineDevices: number
  /** Total ESP devices in this zone */
  totalDevices: number
  /** Number of mobile sensors "visiting" this zone from other ESPs (6.7) */
  mobileGuestCount: number
}

// ---------------------------------------------------------------------------
// Exported Constant
// ---------------------------------------------------------------------------

export const HEALTH_STATUS_CONFIG: Record<ZoneHealthStatus, { label: string; colorClass: string }> = {
  ok: { label: 'Alles OK', colorClass: 'zone-status--ok' },
  warning: { label: 'Warnung', colorClass: 'zone-status--warning' },
  alarm: { label: 'Alarm', colorClass: 'zone-status--alarm' },
  empty: { label: 'Leer', colorClass: 'zone-status--empty' },
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

function getZoneHealthStatus(
  alarmCount: number,
  activeSensors: number,
  sensorCount: number,
  onlineDevices: number,
  totalDevices: number,
  emergencyStoppedCount: number,
): { status: ZoneHealthStatus; reason: string } {
  // Empty zone: no devices at all — neutral status, not alarm
  if (totalDevices === 0) {
    return { status: 'empty', reason: 'Keine Geräte zugeordnet' }
  }
  const offlineDevices = totalDevices - onlineDevices
  // Red: all devices offline OR no active sensors when sensors exist
  if (totalDevices > 0 && onlineDevices === 0) {
    return { status: 'alarm', reason: `${totalDevices === 1 ? 'Gerät' : `Alle ${totalDevices} Geräte`} offline` }
  }
  if (sensorCount > 0 && activeSensors === 0) {
    return { status: 'alarm', reason: 'Keine Sensoren aktiv' }
  }
  // Yellow: some alarms OR some sensors offline OR emergency-stopped actuators
  // (matches ZonePlate warning logic in HardwareView for consistency)
  const reasons: string[] = []
  if (offlineDevices > 0) reasons.push(`${offlineDevices} ${offlineDevices === 1 ? 'Gerät' : 'Geräte'} offline`)
  if (alarmCount > 0) reasons.push(`${alarmCount} ${alarmCount === 1 ? 'Sensor' : 'Sensoren'} fehlerhaft`)
  else if (sensorCount > 0 && activeSensors < sensorCount) reasons.push(`${sensorCount - activeSensors} ${sensorCount - activeSensors === 1 ? 'Sensor' : 'Sensoren'} inaktiv`)
  if (emergencyStoppedCount > 0) reasons.push(`${emergencyStoppedCount} Not-Aus aktiv`)
  if (reasons.length > 0) return { status: 'warning', reason: reasons.join(', ') }
  // Green: everything OK
  return { status: 'ok', reason: '' }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export interface UseZoneKPIsOptions {
  filter?: Ref<string | null>
}

export function useZoneKPIs(options: UseZoneKPIsOptions = {}) {
  const espStore = useEspStore()
  const deviceContextStore = useDeviceContextStore()
  const { groupDevicesByZone } = useZoneDragDrop()

  // Zone list from API (includes empty zones from ZoneContext)
  const allZones = ref<ZoneListEntry[]>([])
  const zoneApiDegraded = ref(false)
  const lastZoneApiSuccessAt = ref<number | null>(null)

  let lastZoneFetch = 0
  const ZONE_FETCH_COOLDOWN_MS = 30_000

  async function fetchAllZones(): Promise<void> {
    try {
      const response = await zonesApi.getAllZones()
      allZones.value = response.zones
      zoneApiDegraded.value = false
      lastZoneApiSuccessAt.value = Date.now()
    } catch {
      allZones.value = []
      zoneApiDegraded.value = true
    }
  }

  async function fetchAllZonesGuarded(): Promise<void> {
    const now = Date.now()
    if (allZones.value.length > 0 && now - lastZoneFetch < ZONE_FETCH_COOLDOWN_MS) {
      return
    }
    lastZoneFetch = now
    await fetchAllZones()
  }

  // -------------------------------------------------------------------------
  // computeZoneKPIs
  // -------------------------------------------------------------------------

  function computeZoneKPIs(): ZoneKPI[] {
    const groups = groupDevicesByZone(espStore.devices)
    const deviceZoneMap = new Map<string, ZoneKPI>()

    // Track mobile sensors that should be counted in their active zone (6.7)
    const mobileGuestCounts = new Map<string, number>()
    const mobileSensorsAwayFromHome = new Map<string, number>()

    // First pass: identify mobile sensors with active contexts
    for (const group of groups) {
      if (group.zoneId === ZONE_UNASSIGNED) continue
      for (const device of group.devices) {
        const sensors = (device.sensors as MockSensor[]) || []
        for (const sensor of sensors) {
          const s = sensor as MockSensor & { config_id?: string; device_scope?: string }
          if (s.device_scope === 'mobile' && s.config_id) {
            const activeZoneId = deviceContextStore.getActiveZoneId(s.config_id)
            if (activeZoneId && activeZoneId !== group.zoneId) {
              mobileGuestCounts.set(activeZoneId, (mobileGuestCounts.get(activeZoneId) ?? 0) + 1)
              mobileSensorsAwayFromHome.set(group.zoneId, (mobileSensorsAwayFromHome.get(group.zoneId) ?? 0) + 1)
            }
          }
        }
      }
    }

    for (const group of groups) {
      if (group.zoneId === ZONE_UNASSIGNED) continue

      let sensorCount = 0
      let actuatorCount = 0
      let activeSensors = 0
      let activeActuators = 0
      let alarmCount = 0
      let emergencyStoppedCount = 0
      let newestTimestamp: string | null = null
      let onlineDevices = 0

      for (const device of group.devices) {
        const sensors = (device.sensors as MockSensor[]) || []
        const actuators = (device.actuators as MockActuator[]) || []

        sensorCount += sensors.length
        actuatorCount += actuators.length
        activeSensors += sensors.filter(s => s.quality !== 'error' && s.quality !== 'stale').length
        activeActuators += actuators.filter(a => a.state).length
        alarmCount += sensors.filter(s => s.quality === 'error' || s.quality === 'bad').length
        emergencyStoppedCount += actuators.filter(a => (a as any).emergency_stopped).length

        const status = getESPStatus(device as any)
        if (status === 'online' || status === 'stale') {
          onlineDevices++
        }

        for (const sensor of sensors) {
          const ts = (sensor as any).last_read || (sensor as any).last_reading_at
          if (ts) {
            const parsed = new Date(ts).getTime()
            if (!isNaN(parsed) && parsed > 1577836800000 && parsed < 4102444800000) {
              if (!newestTimestamp || ts > newestTimestamp) {
                newestTimestamp = ts
              }
            }
          }
        }

        if (!newestTimestamp) {
          const deviceTs = (device as any).last_seen || (device as any).last_heartbeat
          if (deviceTs && (!newestTimestamp || deviceTs > newestTimestamp)) {
            newestTimestamp = deviceTs
          }
        }
      }

      // Adjust sensor counts for mobile sensors (6.7):
      const awayCount = mobileSensorsAwayFromHome.get(group.zoneId) ?? 0
      const guestCount = mobileGuestCounts.get(group.zoneId) ?? 0
      sensorCount = sensorCount - awayCount + guestCount

      const aggregation = aggregateZoneSensors(group.devices)
      const totalDevices = group.devices.length
      const health = getZoneHealthStatus(alarmCount, activeSensors, sensorCount, onlineDevices, totalDevices, emergencyStoppedCount)

      deviceZoneMap.set(group.zoneId, {
        zoneId: group.zoneId,
        zoneName: group.zoneName,
        sensorCount,
        actuatorCount,
        activeSensors,
        activeActuators,
        alarmCount,
        aggregation,
        lastActivity: newestTimestamp,
        healthStatus: health.status,
        healthReason: health.reason,
        onlineDevices,
        totalDevices,
        mobileGuestCount: guestCount,
      })
    }

    // Merge empty zones from Zone-API (zones without devices)
    for (const apiZone of allZones.value) {
      if (!deviceZoneMap.has(apiZone.zone_id)) {
        const guestCount = mobileGuestCounts.get(apiZone.zone_id) ?? 0
        const health = getZoneHealthStatus(0, 0, 0, 0, 0, 0)
        deviceZoneMap.set(apiZone.zone_id, {
          zoneId: apiZone.zone_id,
          zoneName: apiZone.zone_name || apiZone.zone_id,
          sensorCount: guestCount,
          actuatorCount: 0,
          activeSensors: 0,
          activeActuators: 0,
          alarmCount: 0,
          aggregation: aggregateZoneSensors([]),
          lastActivity: null,
          healthStatus: health.status,
          healthReason: health.reason,
          onlineDevices: 0,
          totalDevices: 0,
          mobileGuestCount: guestCount,
        })
      }
    }

    return Array.from(deviceZoneMap.values())
  }

  // -------------------------------------------------------------------------
  // Reactive state
  // -------------------------------------------------------------------------

  const zoneKPIs = ref<ZoneKPI[]>(computeZoneKPIs())
  let kpiDebounceTimer: ReturnType<typeof setTimeout> | null = null

  // Debounced re-compute on device data changes (WS sensor_data events)
  watch(
    () => espStore.devices,
    () => {
      if (kpiDebounceTimer) clearTimeout(kpiDebounceTimer)
      kpiDebounceTimer = setTimeout(() => {
        zoneKPIs.value = computeZoneKPIs()
      }, 300)
    },
    { deep: true },
  )

  // Immediate re-compute on zone changes (rare, should not be delayed)
  watch(allZones, () => {
    zoneKPIs.value = computeZoneKPIs()
  })

  // Filtered KPIs (excludes empty zones, applies optional zone filter)
  const filteredZoneKPIs = computed(() => {
    const nonEmpty = zoneKPIs.value.filter(z => z.totalDevices > 0)
    if (!options.filter?.value) return nonEmpty
    return nonEmpty.filter(z => z.zoneId === options.filter!.value)
  })

  /** Check if a zone's last activity is stale (>60s ago) */
  function isZoneStale(lastActivity: string | null): boolean {
    if (!lastActivity) return true
    const then = new Date(lastActivity).getTime()
    // Sanity: invalid or unreasonable timestamps (before 2020 or after 2100) are stale
    if (isNaN(then) || then < 1577836800000 || then > 4102444800000) return true
    const age = Date.now() - then
    return age > ZONE_STALE_THRESHOLD_MS
  }

  // Load zones on mount
  onMounted(() => {
    fetchAllZonesGuarded()
  })

  // Cleanup debounce timer
  onUnmounted(() => {
    if (kpiDebounceTimer) {
      clearTimeout(kpiDebounceTimer)
      kpiDebounceTimer = null
    }
  })

  return {
    zoneKPIs,
    filteredZoneKPIs,
    isZoneStale,
    allZones,
    fetchAllZonesGuarded,
    zoneApiDegraded,
    lastZoneApiSuccessAt,
  }
}
