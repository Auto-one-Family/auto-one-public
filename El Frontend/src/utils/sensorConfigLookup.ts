/**
 * Store-config_id lookup — docks to matchSensorToEvent / sensorsMatchForLiveMerge.
 * Not a fourth identity: equality is sensor.config_id === id.
 * MQTT topics may stay gpio-keyed (transport).
 */
import { parseSensorId } from '@/composables/useSensorId'
import type { MockSensor } from '@/types'

const CONFIG_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const LEGACY_MONITOR_GPIO_RE = /^(.+)-gpio(\d+)$/

export interface DeviceSensorHost {
  sensors?: MockSensor[] | unknown
  device_id?: string
  esp_id?: string
}

type LookupSensor = MockSensor & { esp_id?: string }

/** Host ESP id recorded by collectStoreSensors (preserves sensor object identity). */
const sensorHostEspIds = new WeakMap<MockSensor, string>()

function hostEspId(device: DeviceSensorHost): string {
  return device.device_id || device.esp_id || ''
}

function sensorEspId(sensor: MockSensor): string | undefined {
  return sensorHostEspIds.get(sensor) || (sensor as LookupSensor).esp_id
}

/** When a host id is known, legacy keys must match that ESP — not just gpio. */
function matchesLegacyEsp(sensor: MockSensor, espId: string): boolean {
  const tagged = sensorEspId(sensor)
  if (!tagged) return true
  return tagged === espId
}

export type MonitorDeepLinkHit =
  | { kind: 'hit'; sensor: MockSensor }
  | { kind: 'ambiguous'; sensors: MockSensor[] }
  | { kind: 'miss' }

export function isConfigId(value: string | undefined | null): boolean {
  return !!value && CONFIG_ID_RE.test(value)
}

export function collectStoreSensors(devices: DeviceSensorHost[]): MockSensor[] {
  const out: MockSensor[] = []
  for (const device of devices) {
    const hostId = hostEspId(device)
    const sensors = (device.sensors as MockSensor[] | undefined) ?? []
    for (const sensor of sensors) {
      if (hostId) sensorHostEspIds.set(sensor, hostId)
      out.push(sensor)
    }
  }
  return out
}

export function findSensorByConfigId(
  sensors: MockSensor[],
  configId: string,
): MockSensor | undefined {
  return sensors.find((sensor) => sensor.config_id === configId)
}

export function listSensorsByGpio(sensors: MockSensor[], gpio: number): MockSensor[] {
  return sensors.filter((sensor) => sensor.gpio === gpio)
}

/**
 * AUT-1533: Deep-link is config_id. Legacy `{espId}-gpio{n}` only resolves
 * when that pin has exactly one store row on the named ESP — no silent
 * first-hit on gpio=0, and no cross-ESP pin collision.
 */
export function resolveMonitorDeepLink(
  sensorId: string,
  sensors: MockSensor[],
): MonitorDeepLinkHit {
  const byConfigId = findSensorByConfigId(sensors, sensorId)
  if (byConfigId) return { kind: 'hit', sensor: byConfigId }

  const match = sensorId.match(LEGACY_MONITOR_GPIO_RE)
  if (!match) return { kind: 'miss' }

  const espId = match[1]
  const gpio = parseInt(match[2], 10)
  const onPin = listSensorsByGpio(sensors, gpio).filter((sensor) =>
    matchesLegacyEsp(sensor, espId),
  )
  if (onPin.length === 1) return { kind: 'hit', sensor: onPin[0] }
  if (onPin.length > 1) return { kind: 'ambiguous', sensors: onPin }
  return { kind: 'miss' }
}

/**
 * AUT-1525: stored widget id → config_id when unique on the named ESP.
 * gpio-key with multiple gpio=0 rows does not pick the first hit.
 */
export function resolveStoredSensorConfigId(
  storedId: string,
  sensors: MockSensor[],
): string | undefined {
  if (!storedId) return undefined
  const direct = findSensorByConfigId(sensors, storedId)
  if (direct?.config_id) return direct.config_id

  const parsed = parseSensorId(storedId)
  if (!parsed.isValid || parsed.gpio == null) return undefined
  const candidates = sensors.filter((sensor) => {
    if (sensor.gpio !== parsed.gpio) return false
    if (parsed.sensorType && sensor.sensor_type !== parsed.sensorType) return false
    if (parsed.espId && !matchesLegacyEsp(sensor, parsed.espId)) return false
    return true
  })
  if (candidates.length === 1) return candidates[0].config_id
  return undefined
}

export function findStoreSensorByStoredId(
  storedId: string,
  sensors: MockSensor[],
): MockSensor | undefined {
  const configId = resolveStoredSensorConfigId(storedId, sensors)
  if (!configId) return undefined
  return findSensorByConfigId(sensors, configId)
}
