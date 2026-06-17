/**
 * useSensorOptions — Centralized zone-grouped sensor options for dashboard widgets
 *
 * Replaces per-widget seen-Set dedup logic with a single composable.
 * Groups sensors by Zone → Subzone → Sensor for <optgroup> rendering.
 */
import { computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { useEspStore } from '@/stores/esp'
import type { MockSensor } from '@/types'

export interface SensorOption {
  label: string       // "SHT31 Temperatur" or sensor_name
  value: string       // "ESP_472204:0:sht31_temp"
  sensorType: string
  espId: string
  gpio: number
  /** Sensor config UUID for alert-config API lookup */
  configId?: string
}

export interface SensorSubgroup {
  label: string              // Subzone name or ""
  subzoneId: string | null
  options: SensorOption[]
}

export interface SensorOptionGroup {
  label: string              // Zone name or "Nicht zugewiesen"
  zoneId: string | null
  subgroups: SensorSubgroup[]
}

/**
 * Flat sensor list item (backward-compatible with widget empty-state dropdowns)
 */
export interface FlatSensorOption {
  id: string
  label: string
}

interface UseSensorOptionsReturn {
  /** Sensors grouped by Zone → Subzone */
  groupedSensorOptions: ComputedRef<SensorOptionGroup[]>
  /** Flat deduplicated sensor list (for widgets that only need id+label) */
  flatSensorOptions: ComputedRef<FlatSensorOption[]>
}

export function useSensorOptions(
  filterZoneId?: Ref<string | undefined>,
): UseSensorOptionsReturn {
  const espStore = useEspStore()

  const groupedSensorOptions = computed<SensorOptionGroup[]>(() => {
    const seen = new Set<string>()
    const zoneMap = new Map<string | null, {
      zoneName: string
      subzoneMap: Map<string | null, { subzoneName: string; options: SensorOption[] }>
    }>()

    for (const device of espStore.devices) {
      // Zone filter
      if (filterZoneId?.value && device.zone_id !== filterZoneId.value) continue

      const deviceId = espStore.getDeviceId(device)
      const zoneId = device.zone_id || null
      const zoneName = device.zone_name || 'Nicht zugewiesen'

      // Resolve subzone names from device.subzones
      const deviceSubzones = (device as any).subzones as Array<{ id: string; name: string }> | undefined

      if (!zoneMap.has(zoneId)) {
        zoneMap.set(zoneId, { zoneName, subzoneMap: new Map() })
      }
      const zoneEntry = zoneMap.get(zoneId)!

      for (const s of (device.sensors as MockSensor[]) || []) {
        const sensorId = `${deviceId}:${s.gpio}:${s.sensor_type}`
        if (seen.has(sensorId)) continue
        seen.add(sensorId)

        const subzoneId = s.subzone_id || null
        let subzoneName = ''
        if (subzoneId && deviceSubzones) {
          const sz = deviceSubzones.find(sz => sz.id === subzoneId)
          subzoneName = sz?.name || subzoneId
        }

        if (!zoneEntry.subzoneMap.has(subzoneId)) {
          zoneEntry.subzoneMap.set(subzoneId, { subzoneName, options: [] })
        }

        zoneEntry.subzoneMap.get(subzoneId)!.options.push({
          label: s.name || s.sensor_type,
          value: sensorId,
          sensorType: s.sensor_type,
          espId: deviceId,
          gpio: s.gpio,
          configId: s.config_id,
        })
      }
    }

    // Build sorted result
    const groups: SensorOptionGroup[] = []

    // Sort zones: named zones alphabetically, "Nicht zugewiesen" last
    const sortedZoneEntries = [...zoneMap.entries()].sort((a, b) => {
      if (a[0] === null) return 1
      if (b[0] === null) return -1
      return (a[1].zoneName).localeCompare(b[1].zoneName)
    })

    for (const [zoneId, { zoneName, subzoneMap }] of sortedZoneEntries) {
      // Sort subzones: named subzones alphabetically, null-subzone last
      const sortedSubzones = [...subzoneMap.entries()].sort((a, b) => {
        if (a[0] === null) return 1
        if (b[0] === null) return -1
        return a[1].subzoneName.localeCompare(b[1].subzoneName)
      })

      const subgroups: SensorSubgroup[] = sortedSubzones.map(([szId, { subzoneName, options }]) => ({
        label: subzoneName,
        subzoneId: szId,
        options: options.sort((a, b) => a.sensorType.localeCompare(b.sensorType)),
      }))

      groups.push({
        label: zoneName,
        zoneId,
        subgroups,
      })
    }

    return groups
  })

  const flatSensorOptions = computed<FlatSensorOption[]>(() => {
    const result: FlatSensorOption[] = []
    for (const group of groupedSensorOptions.value) {
      for (const subgroup of group.subgroups) {
        for (const opt of subgroup.options) {
          result.push({ id: opt.value, label: opt.label })
        }
      }
    }
    return result
  })

  return {
    groupedSensorOptions,
    flatSensorOptions,
  }
}
