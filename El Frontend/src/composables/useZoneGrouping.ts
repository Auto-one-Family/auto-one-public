/**
 * useZoneGrouping Composable
 *
 * Extracts zone→subzone grouping logic for sensors and actuators.
 * Shared between SensorsView (CRUD) and MonitorView (read-only).
 *
 * Input: espStore.devices (reactive)
 * Output: sensorsByZone, actuatorsByZone (computed ZoneGroup arrays with subzone nesting)
 *
 * Optional subzoneResolver: Map from `${espId}-${gpio}` to { subzoneId, subzoneName }
 * for GPIO-based subzone resolution (fallback when monitor-data endpoint unavailable).
 */

import { computed, type Ref } from 'vue'
import { useEspStore } from '@/stores/esp'
import { ZONE_UNASSIGNED } from '@/composables/useZoneDragDrop'
export { ZONE_UNASSIGNED }
import type { QualityLevel } from '@/types'
import type { SubzoneResolved } from '@/composables/useSubzoneResolver'

// =============================================================================
// Exported Interfaces
// =============================================================================

export interface SensorWithContext {
  gpio: number
  sensor_type: string
  name: string | null
  raw_value: number
  unit: string
  quality: QualityLevel
  config_id?: string
  esp_id: string
  esp_state?: string
  zone_id: string | null
  zone_name: string
  subzone_id: string | null
  subzone_name: string
  last_read?: string | null
  last_event_at?: string | null
  is_stale?: boolean
  interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'VIRTUAL' | null
  device_scope?: 'zone_local' | 'multi_zone' | 'mobile' | null
  assigned_zones?: string[]
  /** Active zone from device_active_context (mobile sensors) */
  active_zone_id?: string | null
  /** When the active context was set (ISO DateTime) */
  context_since?: string | null
  /** Sensor operating mode — 'continuous' | 'on_demand' | 'scheduled' | 'paused' */
  operating_mode?: string | null
  /** AUT-299: UUID of the linked temperature sensor config for ATC. Null = no sensor linked. */
  temp_sensor_config_id?: string | null
  /** AUT-299: Last measurement metadata (e.g. temp_source, temp_compensation_value for EC/pH) */
  metadata?: Record<string, unknown> | null
}

export interface ActuatorWithContext {
  gpio: number
  actuator_type: string
  /** Original ESP32 hardware type (relay, pump, valve, pwm) before server normalization */
  hardware_type?: string | null
  name: string | null
  state: boolean
  pwm_value: number
  emergency_stopped: boolean
  esp_id: string
  esp_state?: string
  zone_id: string | null
  zone_name: string
  subzone_id: string | null
  subzone_name: string
  last_seen?: string | null
  last_command_at?: string | null
  device_scope?: 'zone_local' | 'multi_zone' | 'mobile' | null
  assigned_zones?: string[]
  /** Active zone from device_active_context (mobile actuators) */
  active_zone_id?: string | null
  /** When the active context was set (ISO DateTime) */
  context_since?: string | null
}

export interface SubzoneGroup {
  subzoneId: string | null
  subzoneName: string
  sensors: SensorWithContext[]
}

export interface ZoneGroup {
  zoneId: string | null
  zoneName: string
  subzones: SubzoneGroup[]
  sensorCount: number
  mockSensorCount: number
}

/** Checks whether an ESP ID belongs to a mock/simulated device */
export function isMockEspId(espId: string): boolean {
  return espId.startsWith('ESP_MOCK_') || espId.startsWith('MOCK_')
}

export interface ActuatorSubzoneGroup {
  subzoneId: string | null
  subzoneName: string
  actuators: ActuatorWithContext[]
}

export interface ActuatorZoneGroup {
  zoneId: string | null
  zoneName: string
  subzones: ActuatorSubzoneGroup[]
  actuatorCount: number
}

// =============================================================================
// Filter Options
// =============================================================================

export interface ZoneGroupingFilters {
  filterEspId?: Ref<string>
  filterSensorType?: Ref<string[]>
  filterQuality?: Ref<string[]>
  filterActuatorType?: Ref<string[]>
  filterState?: Ref<string[]>
}

export interface ZoneGroupingOptions {
  filters?: ZoneGroupingFilters
  /** GPIO→Subzone Map for fallback (key: `${espId}-${gpio}`) */
  subzoneResolver?: Ref<Map<string, SubzoneResolved>>
}

const SUBZONE_NONE = '__none__'

// =============================================================================
// Composable
// =============================================================================

export function useZoneGrouping(options?: ZoneGroupingOptions | ZoneGroupingFilters) {
  const filters = options && 'filters' in options ? options.filters : (options as ZoneGroupingFilters | undefined)
  const subzoneResolver = options && 'subzoneResolver' in options ? options.subzoneResolver : undefined
  const espStore = useEspStore()

  // ── All sensors with zone/subzone context ──
  const allSensors = computed((): SensorWithContext[] => {
    const resolver = subzoneResolver?.value
    return espStore.devices.flatMap(esp => {
      const sensors = esp.sensors as {
        gpio: number; sensor_type: string; name: string | null;
        raw_value: number; unit: string; quality: QualityLevel;
        config_id?: string; last_read?: string | null; last_event_at?: string | null;
        interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'VIRTUAL' | null
      }[] | undefined
      if (!sensors) return []
      const espId = espStore.getDeviceId(esp)
      const zoneId = esp.zone_id || null
      const zoneName = esp.zone_name || (zoneId ?? '')
      return sensors.map(sensor => {
        let subzoneId: string | null
        let subzoneName: string
        if (resolver) {
          const key = `${espId}-${sensor.gpio}`
          const resolved = resolver.get(key)
          subzoneId = resolved?.subzoneId ?? null
          subzoneName = resolved?.subzoneName ?? (subzoneId ?? '')
        } else {
          subzoneId = esp.subzone_id || null
          subzoneName = esp.subzone_name || (subzoneId ?? '')
        }
        return {
          ...sensor,
          esp_id: espId,
          esp_state: esp.system_state,
          zone_id: zoneId,
          zone_name: zoneName,
          subzone_id: subzoneId,
          subzone_name: subzoneName,
        }
      })
    })
  })

  // ── Filtered sensors ──
  const filteredSensors = computed(() => {
    return allSensors.value.filter(sensor => {
      if (filters?.filterEspId?.value && !sensor.esp_id.toLowerCase().includes(filters.filterEspId.value.toLowerCase())) {
        return false
      }
      if (filters?.filterSensorType?.value?.length && !filters.filterSensorType.value.includes(sensor.sensor_type)) {
        return false
      }
      if (filters?.filterQuality?.value?.length && !filters.filterQuality.value.includes(sensor.quality)) {
        return false
      }
      return true
    })
  })

  // ── Group sensors by zone → subzone ──
  const sensorsByZone = computed((): ZoneGroup[] => {
    const zoneMap = new Map<string | null, Map<string | null, SensorWithContext[]>>()
    for (const sensor of filteredSensors.value) {
      const zId = sensor.zone_id || ZONE_UNASSIGNED
      const szId = sensor.subzone_id ?? SUBZONE_NONE
      if (!zoneMap.has(zId)) {
        zoneMap.set(zId, new Map())
      }
      const subMap = zoneMap.get(zId)!
      if (!subMap.has(szId)) {
        subMap.set(szId, [])
      }
      subMap.get(szId)!.push(sensor)
    }
    const result: ZoneGroup[] = []
    for (const [zoneId, subMap] of zoneMap) {
      const subzones: SubzoneGroup[] = []
      let total = 0
      let mockTotal = 0
      for (const [szId, sensors] of subMap) {
        const subzoneName: string = szId === SUBZONE_NONE
          ? (zoneId === ZONE_UNASSIGNED ? '' : 'Keine Subzone')
          : (sensors[0]?.subzone_name || szId || '')
        subzones.push({
          subzoneId: szId === SUBZONE_NONE ? null : szId,
          subzoneName,
          sensors,
        })
        total += sensors.length
        mockTotal += sensors.filter(s => isMockEspId(s.esp_id)).length
      }
      subzones.sort((a, b) => {
        if (a.subzoneId === null) return 1
        if (b.subzoneId === null) return -1
        return (a.subzoneName || '').localeCompare(b.subzoneName || '')
      })
      result.push({
        zoneId: zoneId === ZONE_UNASSIGNED ? null : zoneId,
        zoneName: zoneId === ZONE_UNASSIGNED ? 'Nicht zugewiesen' : (filteredSensors.value.find(s => s.zone_id === zoneId)?.zone_name || zoneId || ''),
        subzones,
        sensorCount: total,
        mockSensorCount: mockTotal,
      })
    }
    result.sort((a, b) => {
      if (a.zoneId === null) return 1
      if (b.zoneId === null) return -1
      return (a.zoneName || '').localeCompare(b.zoneName || '')
    })
    return result
  })

  // ── All actuators with zone/subzone context ──
  const allActuators = computed((): ActuatorWithContext[] => {
    const resolver = subzoneResolver?.value
    return espStore.devices.flatMap(esp => {
      const actuators = esp.actuators as {
        gpio: number; actuator_type: string; name: string | null;
        state: boolean; pwm_value: number; emergency_stopped: boolean
      }[] | undefined
      if (!actuators) return []
      const espId = espStore.getDeviceId(esp)
      const zoneId = esp.zone_id || null
      const zoneName = esp.zone_name || (zoneId ?? '')
      return actuators.map(actuator => {
        let subzoneId: string | null
        let subzoneName: string
        if (resolver) {
          const key = `${espId}-${actuator.gpio}`
          const resolved = resolver.get(key)
          subzoneId = resolved?.subzoneId ?? null
          subzoneName = resolved?.subzoneName ?? (subzoneId ?? '')
        } else {
          subzoneId = esp.subzone_id || null
          subzoneName = esp.subzone_name || (subzoneId ?? '')
        }
        return {
          ...actuator,
          esp_id: espId,
          esp_state: esp.system_state,
          last_seen: esp.last_seen ?? null,
          last_command_at: (actuator as any).last_command_at ?? null,
          zone_id: zoneId,
          zone_name: zoneName,
          subzone_id: subzoneId,
          subzone_name: subzoneName,
        }
      })
    })
  })

  // ── Filtered actuators ──
  const filteredActuators = computed(() => {
    return allActuators.value.filter(actuator => {
      if (filters?.filterEspId?.value && !actuator.esp_id.toLowerCase().includes(filters.filterEspId.value.toLowerCase())) {
        return false
      }
      if (filters?.filterActuatorType?.value?.length && !filters.filterActuatorType.value.includes(actuator.actuator_type)) {
        return false
      }
      if (filters?.filterState?.value?.length) {
        const matchesOn = filters.filterState.value.includes('on') && actuator.state && !actuator.emergency_stopped
        const matchesOff = filters.filterState.value.includes('off') && !actuator.state && !actuator.emergency_stopped
        const matchesEmergency = filters.filterState.value.includes('emergency') && actuator.emergency_stopped
        if (!matchesOn && !matchesOff && !matchesEmergency) {
          return false
        }
      }
      return true
    })
  })

  // ── Group actuators by zone → subzone ──
  const actuatorsByZone = computed((): ActuatorZoneGroup[] => {
    const zoneMap = new Map<string | null, Map<string | null, ActuatorWithContext[]>>()
    for (const actuator of filteredActuators.value) {
      const zId = actuator.zone_id || ZONE_UNASSIGNED
      const szId = actuator.subzone_id ?? SUBZONE_NONE
      if (!zoneMap.has(zId)) {
        zoneMap.set(zId, new Map())
      }
      const subMap = zoneMap.get(zId)!
      if (!subMap.has(szId)) {
        subMap.set(szId, [])
      }
      subMap.get(szId)!.push(actuator)
    }
    const result: ActuatorZoneGroup[] = []
    for (const [zoneId, subMap] of zoneMap) {
      const subzones: ActuatorSubzoneGroup[] = []
      let total = 0
      for (const [szId, actuators] of subMap) {
        const subzoneName: string = szId === SUBZONE_NONE
          ? (zoneId === ZONE_UNASSIGNED ? '' : 'Keine Subzone')
          : (actuators[0]?.subzone_name || szId || '')
        subzones.push({
          subzoneId: szId === SUBZONE_NONE ? null : szId,
          subzoneName,
          actuators,
        })
        total += actuators.length
      }
      subzones.sort((a, b) => {
        if (a.subzoneId === null) return 1
        if (b.subzoneId === null) return -1
        return (a.subzoneName || '').localeCompare(b.subzoneName || '')
      })
      result.push({
        zoneId: zoneId === ZONE_UNASSIGNED ? null : zoneId,
        zoneName: zoneId === ZONE_UNASSIGNED ? 'Nicht zugewiesen' : (filteredActuators.value.find(a => a.zone_id === zoneId)?.zone_name || zoneId || ''),
        subzones,
        actuatorCount: total,
      })
    }
    result.sort((a, b) => {
      if (a.zoneId === null) return 1
      if (b.zoneId === null) return -1
      return (a.zoneName || '').localeCompare(b.zoneName || '')
    })
    return result
  })

  return {
    allSensors,
    filteredSensors,
    sensorsByZone,
    allActuators,
    filteredActuators,
    actuatorsByZone,
  }
}
