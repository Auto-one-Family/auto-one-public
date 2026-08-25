import { describe, expect, it } from 'vitest'
import {
  buildTankEcPhRows,
  deviceIdsForTank,
  filterOutEcPhSensors,
  isEcPhAggCategory,
  isTankRoutedAggCategory,
  resolveTankMeasureSensor,
} from '@/utils/zoneTankEcPh'

describe('zoneTankEcPh', () => {
  const tanks = [
    { id: 'tank-a', name: 'Nährlösung A', zone_id: 'zone-1' },
    { id: 'tank-b', name: 'Nährlösung B', zone_id: 'zone-1' },
  ]

  const devices = [
    {
      device_id: 'esp-1',
      tank_id: 'tank-a',
      sensors: [
        { sensor_type: 'ec', gpio: 34, raw_value: 1200 },
        { sensor_type: 'ph', gpio: 35, raw_value: 6.2 },
      ],
    },
    {
      device_id: 'esp-2',
      tank_id: 'tank-b',
      sensors: [
        { sensor_type: 'ec', gpio: 34, raw_value: 900 },
        { sensor_type: 'ph', gpio: 35, raw_value: 5.8 },
      ],
    },
    {
      device_id: 'esp-climate',
      tank_id: null,
      sensors: [{ sensor_type: 'temperature', gpio: 4, raw_value: 22 }],
    },
  ]

  const zoneSensors = [
    { esp_id: 'esp-1', gpio: 34, sensor_type: 'ec', raw_value: 1210 },
    { esp_id: 'esp-1', gpio: 35, sensor_type: 'ph', raw_value: 6.25 },
    { esp_id: 'esp-2', gpio: 34, sensor_type: 'ec', raw_value: 910 },
    { esp_id: 'esp-2', gpio: 35, sensor_type: 'ph', raw_value: 5.85 },
  ]

  describe('deviceIdsForTank', () => {
    it('should return device ids linked via tank_id', () => {
      expect(deviceIdsForTank(devices, 'tank-a')).toEqual(['esp-1'])
      expect(deviceIdsForTank(devices, 'tank-b')).toEqual(['esp-2'])
    })

    it('should return empty list when no device is assigned', () => {
      expect(deviceIdsForTank(devices, 'tank-missing')).toEqual([])
    })
  })

  describe('resolveTankMeasureSensor', () => {
    it('should prefer monitor zone sensor values over device snapshot', () => {
      const ec = resolveTankMeasureSensor(zoneSensors, devices, ['esp-1'], 'ec')
      expect(ec).toEqual({
        esp_id: 'esp-1',
        gpio: 34,
        sensor_type: 'ec',
        value: 1210,
        operating_mode: null,
        last_read: null,
      })
    })

    it('should fall back to device sensors when zone sensors lack the measure', () => {
      const ec = resolveTankMeasureSensor([], devices, ['esp-1'], 'ec')
      expect(ec).toMatchObject({
        esp_id: 'esp-1',
        gpio: 34,
        sensor_type: 'ec',
        value: 1200,
      })
    })

    it('should return null when tank has no assigned devices', () => {
      expect(resolveTankMeasureSensor(zoneSensors, devices, [], 'ph')).toBeNull()
    })

    it('should resolve Messbox temperature via agg category (AUT-1537)', () => {
      const sensors = [
        { esp_id: 'esp-1', gpio: 0, sensor_type: 'sht31_temp', raw_value: 21.4 },
      ]
      const temp = resolveTankMeasureSensor(sensors, devices, ['esp-1'], 'temperature')
      expect(temp).toEqual({
        esp_id: 'esp-1',
        gpio: 0,
        sensor_type: 'sht31_temp',
        value: 21.4,
        operating_mode: null,
        last_read: null,
      })
    })

    it('should keep Ist value on the same Messbox temp as identity when sht31 and ds18b20 coexist', () => {
      const sensors = [
        { esp_id: 'esp-1', gpio: 0, sensor_type: 'sht31_temp', raw_value: 21.4 },
        { esp_id: 'esp-1', gpio: 4, sensor_type: 'ds18b20', raw_value: 18.0 },
      ]
      const dualTempDevices = [
        {
          device_id: 'esp-1',
          tank_id: 'tank-a',
          sensors: [
            { sensor_type: 'ds18b20', gpio: 4, processed_value: 18.0 },
            { sensor_type: 'sht31_temp', gpio: 0, processed_value: 21.4 },
          ],
        },
      ]
      const temp = resolveTankMeasureSensor(sensors, dualTempDevices, ['esp-1'], 'temperature')
      expect(temp).toEqual({
        esp_id: 'esp-1',
        gpio: 0,
        sensor_type: 'sht31_temp',
        value: 21.4,
        operating_mode: null,
        last_read: null,
      })
    })

    it('should not borrow a sibling temp value when the identified fallback sensor has none', () => {
      const dualTempDevices = [
        {
          device_id: 'esp-1',
          tank_id: 'tank-a',
          sensors: [
            { sensor_type: 'sht31_temp', gpio: 0, raw_value: null },
            { sensor_type: 'ds18b20', gpio: 4, processed_value: 18.0 },
          ],
        },
      ]
      const temp = resolveTankMeasureSensor([], dualTempDevices, ['esp-1'], 'temperature')
      expect(temp).toEqual({
        esp_id: 'esp-1',
        gpio: 0,
        sensor_type: 'sht31_temp',
        value: null,
        operating_mode: null,
        last_read: null,
      })
    })

    it('should pass operating_mode and last_read for Wasserbox pH/EC (AUT-837 E1)', () => {
      const sensors = [
        {
          esp_id: 'esp-1',
          gpio: 35,
          sensor_type: 'ph',
          raw_value: 6.2,
          operating_mode: 'on_demand',
          last_read: '2026-08-23T12:00:00.000Z',
        },
      ]
      const ph = resolveTankMeasureSensor(sensors, devices, ['esp-1'], 'ph')
      expect(ph).toEqual({
        esp_id: 'esp-1',
        gpio: 35,
        sensor_type: 'ph',
        value: 6.2,
        operating_mode: 'on_demand',
        last_read: '2026-08-23T12:00:00.000Z',
      })
    })
  })

  describe('buildTankEcPhRows', () => {
    it('should build one labeled row per tank for multi-tank zones', () => {
      const rows = buildTankEcPhRows(tanks, devices, zoneSensors)
      expect(rows).toHaveLength(2)
      expect(rows[0].tankName).toBe('Nährlösung A')
      expect(rows[0].ec?.value).toBe(1210)
      expect(rows[0].ph?.value).toBe(6.25)
      expect(rows[1].tankName).toBe('Nährlösung B')
      expect(rows[1].ec?.value).toBe(910)
      expect(rows[1].ph?.value).toBe(5.85)
    })

    it('should support a single-tank zone without mixing foreign sensors', () => {
      const rows = buildTankEcPhRows([tanks[0]], devices, zoneSensors)
      expect(rows).toHaveLength(1)
      expect(rows[0].ec?.esp_id).toBe('esp-1')
      expect(rows[0].ph?.esp_id).toBe('esp-1')
    })

    it('should leave measures null when tank has no EC/pH device', () => {
      const orphanTank = [{ id: 'tank-empty', name: 'Leer', zone_id: 'zone-1' }]
      const rows = buildTankEcPhRows(orphanTank, devices, zoneSensors)
      expect(rows[0].ec).toBeNull()
      expect(rows[0].ph).toBeNull()
    })
  })

  describe('filterOutEcPhSensors (AUT-1537 membership)', () => {
    it('should recognize ec/ph strip categories (not temperature)', () => {
      expect(isEcPhAggCategory('ec')).toBe(true)
      expect(isEcPhAggCategory('ph')).toBe(true)
      expect(isEcPhAggCategory('temperature')).toBe(false)
    })

    it('should route temperature with EC/pH when the ESP has tank_id', () => {
      expect(isTankRoutedAggCategory('ec')).toBe(true)
      expect(isTankRoutedAggCategory('ph')).toBe(true)
      expect(isTankRoutedAggCategory('temperature')).toBe(true)
      expect(isTankRoutedAggCategory('humidity')).toBe(false)
    })

    it('should keep all sensors when no device is tank-assigned', () => {
      const mixed = [
        { esp_id: 'esp-1', sensor_type: 'sht31_temp', gpio: 0 },
        { esp_id: 'esp-1', sensor_type: 'sht31_humidity', gpio: 0 },
        { esp_id: 'esp-1', sensor_type: 'ec', gpio: 34 },
        { esp_id: 'esp-1', sensor_type: 'ph', gpio: 35 },
        { esp_id: 'esp-1', sensor_type: 'vpd', gpio: 6 },
      ]
      const unassigned = [{ device_id: 'esp-1', tank_id: null }]
      const filtered = filterOutEcPhSensors(mixed, unassigned)
      expect(filtered.map((s) => s.sensor_type)).toEqual([
        'sht31_temp',
        'sht31_humidity',
        'ec',
        'ph',
        'vpd',
      ])
    })

    it('should hide EC/pH and Messbox temp of a tank-assigned ESP, keep humidity', () => {
      const mixed = [
        { esp_id: 'esp-1', sensor_type: 'sht31_temp', gpio: 0 },
        { esp_id: 'esp-1', sensor_type: 'sht31_humidity', gpio: 0 },
        { esp_id: 'esp-1', sensor_type: 'ec', gpio: 34 },
        { esp_id: 'esp-1', sensor_type: 'ph', gpio: 35 },
        { esp_id: 'esp-1', sensor_type: 'vpd', gpio: 6 },
      ]
      const assigned = [{ device_id: 'esp-1', tank_id: 'tank-a' }]
      const filtered = filterOutEcPhSensors(mixed, assigned)
      expect(filtered.map((s) => s.sensor_type)).toEqual(['sht31_humidity', 'vpd'])
    })

    it('should hide ds18b20 of an assigned ESP and leave an unassigned neighbor intact', () => {
      const mixed = [
        { esp_id: 'esp-tank', sensor_type: 'ds18b20', gpio: 4 },
        { esp_id: 'esp-tank', sensor_type: 'ec', gpio: 34 },
        { esp_id: 'esp-free', sensor_type: 'ec', gpio: 34 },
        { esp_id: 'esp-free', sensor_type: 'sht31_temp', gpio: 0 },
      ]
      const devices = [
        { device_id: 'esp-tank', tank_id: 'tank-a' },
        { device_id: 'esp-free', tank_id: null },
      ]
      const filtered = filterOutEcPhSensors(mixed, devices)
      expect(filtered.map((s) => `${s.esp_id}:${s.sensor_type}`)).toEqual([
        'esp-free:ec',
        'esp-free:sht31_temp',
      ])
    })

    it('should keep all sensors when devices are omitted (no type-hide fallback)', () => {
      const mixed = [
        { sensor_type: 'ec', gpio: 34 },
        { sensor_type: 'ph', gpio: 35 },
        { sensor_type: 'sht31_temp', gpio: 0 },
      ]
      expect(filterOutEcPhSensors(mixed).map((s) => s.sensor_type)).toEqual([
        'ec',
        'ph',
        'sht31_temp',
      ])
    })
  })
})
