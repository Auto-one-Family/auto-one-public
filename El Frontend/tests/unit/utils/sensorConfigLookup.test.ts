import { describe, it, expect } from 'vitest'
import type { MockSensor } from '@/types'
import {
  collectStoreSensors,
  findSensorByConfigId,
  isConfigId,
  listSensorsByGpio,
  resolveMonitorDeepLink,
  resolveStoredSensorConfigId,
} from '@/utils/sensorConfigLookup'

function sensor(partial: Partial<MockSensor> & Pick<MockSensor, 'gpio' | 'sensor_type' | 'config_id'>): MockSensor {
  return {
    name: null,
    raw_value: null,
    unit: '',
    quality: 'good',
    raw_mode: true,
    last_read: null,
    ...partial,
  }
}

const TEMP_ID = '11111111-1111-4111-8111-111111111111'
const HUM_ID = '22222222-2222-4222-8222-222222222222'
const EC_ID = '33333333-3333-4333-8333-333333333333'

const sht31 = [
  sensor({ config_id: TEMP_ID, gpio: 0, sensor_type: 'sht31_temp', name: 'Luft' }),
  sensor({ config_id: HUM_ID, gpio: 0, sensor_type: 'sht31_humidity', name: 'Luft' }),
]

const analog = [
  sensor({ config_id: EC_ID, gpio: 34, sensor_type: 'ec', name: 'Zufluss' }),
]

describe('sensorConfigLookup', () => {
  it('should treat UUID as config_id', () => {
    expect(isConfigId(TEMP_ID)).toBe(true)
    expect(isConfigId('ESP_1-gpio0')).toBe(false)
    expect(isConfigId('ESP_1:0:sht31_temp')).toBe(false)
  })

  it('should match store row by config_id, not first gpio=0', () => {
    expect(findSensorByConfigId(sht31, HUM_ID)?.sensor_type).toBe('sht31_humidity')
    expect(listSensorsByGpio(sht31, 0)).toHaveLength(2)
  })

  it('should open monitor deep-link on config_id', () => {
    const hit = resolveMonitorDeepLink(TEMP_ID, sht31)
    expect(hit.kind).toBe('hit')
    if (hit.kind === 'hit') expect(hit.sensor.sensor_type).toBe('sht31_temp')
  })

  it('should not silent-first-hit a gpio=0 URL with multiple configs', () => {
    const hit = resolveMonitorDeepLink('ESP_ABC-gpio0', sht31)
    expect(hit.kind).toBe('ambiguous')
    if (hit.kind === 'ambiguous') expect(hit.sensors.map((s) => s.config_id)).toEqual([TEMP_ID, HUM_ID])
  })

  it('should resolve a unique gpio URL to that config_id', () => {
    const hit = resolveMonitorDeepLink('ESP_ABC-gpio34', analog)
    expect(hit.kind).toBe('hit')
    if (hit.kind === 'hit') expect(hit.sensor.config_id).toBe(EC_ID)
  })

  it('should store widget picker as config_id and refuse gpio=0 first-hit', () => {
    expect(resolveStoredSensorConfigId(EC_ID, analog)).toBe(EC_ID)
    expect(resolveStoredSensorConfigId('ESP_1:34:ec', analog)).toBe(EC_ID)
    expect(resolveStoredSensorConfigId('ESP_1:0:sht31_temp', sht31)).toBe(TEMP_ID)
    expect(resolveStoredSensorConfigId('ESP_1:0', sht31)).toBeUndefined()
  })

  it('should resolve a legacy gpio deep-link to the named ESP when pins collide', () => {
    const otherEc = sensor({
      config_id: '44444444-4444-4444-8444-444444444444',
      gpio: 34,
      sensor_type: 'ec',
      name: 'Zelt 2',
    })
    const store = collectStoreSensors([
      { device_id: 'ESP_A', sensors: analog },
      { device_id: 'ESP_B', sensors: [otherEc] },
    ])

    const hit = resolveMonitorDeepLink('ESP_A-gpio34', store)
    expect(hit.kind).toBe('hit')
    if (hit.kind === 'hit') expect(hit.sensor.config_id).toBe(EC_ID)

    const other = resolveMonitorDeepLink('ESP_B-gpio34', store)
    expect(other.kind).toBe('hit')
    if (other.kind === 'hit') expect(other.sensor.config_id).toBe(otherEc.config_id)
  })

  it('should resolve a stored widget id to the named ESP when pins collide', () => {
    const otherEcId = '44444444-4444-4444-8444-444444444444'
    const store = collectStoreSensors([
      { device_id: 'ESP_1', sensors: analog },
      { device_id: 'ESP_2', sensors: [sensor({ config_id: otherEcId, gpio: 34, sensor_type: 'ec' })] },
    ])

    expect(resolveStoredSensorConfigId('ESP_1:34:ec', store)).toBe(EC_ID)
    expect(resolveStoredSensorConfigId('ESP_2:34:ec', store)).toBe(otherEcId)
    expect(resolveStoredSensorConfigId('ESP_MISSING:34:ec', store)).toBeUndefined()
  })
})
