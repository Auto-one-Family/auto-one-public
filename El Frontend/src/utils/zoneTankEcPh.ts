/**
 * Zone→Tank EC/pH resolution for Monitor L2 strip (AUT-1324).
 *
 * Pure helpers — no store/API. Reuses the existing device.tank_id linkage
 * (AUT-1223) and optional monitor-zone sensor snapshots already loaded in
 * MonitorView. No second Tank↔Sensor junction invented.
 */

import { getSensorAggCategory, type AggCategory } from '@/utils/sensorDefaults'
import type { IstSollMeasureKey } from '@/components/plants/tankIstSollFormat'

/** True for tank nutrient measures shown on the zone strip (AUT-1324/1325). */
export function isEcPhAggCategory(category: AggCategory): boolean {
  return category === 'ec' || category === 'ph'
}

/**
 * AUT-1537: measures that leave the subzone card when the ESP has tank_id.
 * EC/pH stay Dual-Display (strip + tile). Temperature goes to the compact tile only.
 * Humidity is intentionally not included (product question — stays on the subzone card).
 */
export function isTankRoutedAggCategory(category: AggCategory): boolean {
  return category === 'ec' || category === 'ph' || category === 'temperature'
}

/**
 * AUT-1537: membership-aware subzone filter.
 * Hide EC/pH + Messbox temperature only when the sensor's ESP has `device.tank_id`.
 * Unassigned ESPs keep EC/pH + temp as subzone cards. Humidity never routed.
 * `devices` omitted/empty → no membership proof → keep all (never fall back to type-hide).
 */
export function filterOutEcPhSensors<
  T extends { sensor_type: string; esp_id?: string },
>(sensors: T[], devices: ZoneTankDeviceLike[] = []): T[] {
  const tankAssignedIds = new Set<string>()
  for (const device of devices) {
    if (!device.tank_id) continue
    const id = deviceIdOf(device)
    if (id) tankAssignedIds.add(id)
  }

  return sensors.filter((sensor) => {
    if (!isTankRoutedAggCategory(getSensorAggCategory(sensor.sensor_type))) return true
    if (!sensor.esp_id) return true
    return !tankAssignedIds.has(sensor.esp_id)
  })
}

/** Minimal tank shape needed for the strip. */
export interface ZoneTankLike {
  id: string
  name: string
  zone_id: string
}

/** Minimal device shape (ESPDevice subset). */
export interface ZoneTankDeviceLike {
  device_id?: string
  esp_id?: string
  tank_id?: string | null
  sensors?: Array<{
    sensor_type: string
    gpio: number
    raw_value?: number | null
    processed_value?: number | null
    operating_mode?: string | null
    last_read?: string | null
    last_reading_at?: string | null
  }>
}

/** Minimal monitor-zone sensor entry (SensorWithContext / SubzoneSensorEntry). */
export interface ZoneTankSensorLike {
  esp_id: string
  gpio: number
  sensor_type: string
  raw_value?: number | null
  operating_mode?: string | null
  last_read?: string | null
  last_reading_at?: string | null
}

export interface TankEcPhSensorRef {
  esp_id: string
  gpio: number
  sensor_type: string
  value: number | null
  /** AUT-837 E1: Wasserbox pH/EC must keep on_demand vs continuous for sparkline gaps. */
  operating_mode?: string | null
  /** Sample timestamp for live tail — never wall clock. */
  last_read?: string | null
}

export interface TankEcPhRow {
  tankId: string
  tankName: string
  ec: TankEcPhSensorRef | null
  ph: TankEcPhSensorRef | null
}

function deviceIdOf(device: ZoneTankDeviceLike): string {
  return device.device_id || device.esp_id || ''
}

/** Finite reading from one sensor — never borrowed from a sibling of the same AggCategory. */
function finiteSensorValue(
  sensor: { raw_value?: number | null; processed_value?: number | null },
): number | null {
  const value = sensor.processed_value ?? sensor.raw_value
  if (value === null || value === undefined || Number.isNaN(value)) return null
  return value
}

function sampleLastRead(
  sensor: { last_read?: string | null; last_reading_at?: string | null },
): string | null {
  return sensor.last_read ?? sensor.last_reading_at ?? null
}

/**
 * Device IDs assigned to a tank via existing `device.tank_id` (AUT-1223).
 */
export function deviceIdsForTank(
  devices: ZoneTankDeviceLike[],
  tankId: string,
): string[] {
  const ids: string[] = []
  for (const device of devices) {
    if (device.tank_id !== tankId) continue
    const id = deviceIdOf(device)
    if (id) ids.push(id)
  }
  return ids
}

/**
 * Find EC, pH, or Messbox temperature for a tank from already-loaded monitor
 * zone sensors, falling back to live device sensor lists (esp_id + gpio + type).
 */
export function resolveTankMeasureSensor(
  zoneSensors: ZoneTankSensorLike[],
  devices: ZoneTankDeviceLike[],
  assignedDeviceIds: string[],
  measureKey: IstSollMeasureKey,
): TankEcPhSensorRef | null {
  if (assignedDeviceIds.length === 0) return null
  const assigned = new Set(assignedDeviceIds)

  const fromZone = zoneSensors.find(
    (s) =>
      assigned.has(s.esp_id) &&
      getSensorAggCategory(s.sensor_type) === measureKey,
  )
  if (fromZone) {
    return {
      esp_id: fromZone.esp_id,
      gpio: fromZone.gpio,
      sensor_type: fromZone.sensor_type,
      value: finiteSensorValue(fromZone),
      operating_mode: fromZone.operating_mode ?? null,
      last_read: sampleLastRead(fromZone),
    }
  }

  // Fallback identity from espStore devices (still no API) — value from THIS sensor only
  for (const device of devices) {
    const id = deviceIdOf(device)
    if (!id || !assigned.has(id)) continue
    for (const sensor of device.sensors ?? []) {
      if (getSensorAggCategory(sensor.sensor_type) !== measureKey) continue
      return {
        esp_id: id,
        gpio: sensor.gpio,
        sensor_type: sensor.sensor_type,
        value: finiteSensorValue(sensor),
        operating_mode: sensor.operating_mode ?? null,
        last_read: sampleLastRead(sensor),
      }
    }
  }

  return null
}

/**
 * Build one EC/pH row per tank in the zone (supports 1..n tanks).
 */
export function buildTankEcPhRows(
  tanks: ZoneTankLike[],
  devices: ZoneTankDeviceLike[],
  zoneSensors: ZoneTankSensorLike[],
): TankEcPhRow[] {
  return tanks.map((tank) => {
    const assignedDeviceIds = deviceIdsForTank(devices, tank.id)
    return {
      tankId: tank.id,
      tankName: tank.name,
      ec: resolveTankMeasureSensor(zoneSensors, devices, assignedDeviceIds, 'ec'),
      ph: resolveTankMeasureSensor(zoneSensors, devices, assignedDeviceIds, 'ph'),
    }
  })
}
