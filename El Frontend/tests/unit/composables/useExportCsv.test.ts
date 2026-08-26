import { describe, it, expect } from 'vitest'
import {
  SENSOR_EXPORT_DEFAULT_COLUMNS,
  readingsToCsv,
} from '@/composables/useExportCsv'
import type { SensorReading } from '@/types'

function reading(overrides: Partial<SensorReading> = {}): SensorReading {
  return {
    timestamp: '2026-08-24T12:00:00.000Z',
    raw_value: 99,
    processed_value: 6.4,
    unit: 'pH',
    quality: 'good',
    sensor_type: 'ph',
    ...overrides,
  }
}

describe('useExportCsv (AUT-1546)', () => {
  it('should use the server-default column list as the only header', () => {
    expect([...SENSOR_EXPORT_DEFAULT_COLUMNS]).toEqual([
      'timestamp',
      'processed_value',
      'unit',
      'quality',
      'sensor_type',
    ])

    const csv = readingsToCsv([reading()], 'temperature')
    expect(csv.split('\n')[0]).toBe('timestamp,processed_value,unit,quality,sensor_type')
  })

  it('should not add mount columns — export rows are SensorData, not sensor_configs', () => {
    const header = SENSOR_EXPORT_DEFAULT_COLUMNS.join(',')
    expect(header).not.toContain('mount_height_cm')
    expect(header).not.toContain('mount_medium')
    expect(header).not.toContain('mount_angle_deg')
  })

  it('should keep quality and write processed_value, not raw_value', () => {
    const csv = readingsToCsv([reading({ raw_value: 512, processed_value: 6.4, quality: 'warning' })])
    const row = csv.split('\n')[1]

    expect(row).toBe('2026-08-24T12:00:00.000Z,6.4,pH,warning,ph')
    expect(row).not.toContain('512')
    expect(csv).not.toContain('firmware')
    expect(csv).not.toContain('site')
    expect(csv.split('\n')[0]).not.toContain('sensor_name')
    expect(csv.split('\n')[0]).not.toContain('zone')
  })

  it('should keep a quality cell when processed_value is empty', () => {
    const csv = readingsToCsv([
      reading({ processed_value: null, quality: 'error', sensor_type: null }),
    ], 'ec')
    const row = csv.split('\n')[1]

    expect(row).toBe('2026-08-24T12:00:00.000Z,,pH,error,ec')
  })
})
