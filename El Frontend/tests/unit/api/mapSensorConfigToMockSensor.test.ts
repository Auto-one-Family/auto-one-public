import { describe, it, expect } from 'vitest'
import { mapSensorConfigToMockSensor } from '@/api/esp'
import type { SensorConfigResponse } from '@/types'

function baseConfig(overrides: Partial<SensorConfigResponse> = {}): SensorConfigResponse {
  return {
    id: 'cfg-ph-1',
    esp_id: 'ESP_TEST_001',
    gpio: 34,
    sensor_type: 'ph',
    name: 'pH Tank',
    enabled: true,
    interval_ms: 30000,
    processing_mode: 'pi_enhanced',
    calibration: null,
    threshold_min: null,
    threshold_max: null,
    warning_min: null,
    warning_max: null,
    metadata: null,
    device_scope: 'zone_local',
    assigned_zones: null,
    created_at: '2026-08-22T10:00:00.000Z',
    updated_at: '2026-08-22T10:00:00.000Z',
    ...overrides,
  }
}

describe('mapSensorConfigToMockSensor', () => {
  it('should pass calibration, derived.calibrated_at and temp_sensor_config_id through', () => {
    const mapped = mapSensorConfigToMockSensor(baseConfig({
      calibration: {
        slope: -59.16,
        derived: { calibrated_at: '2026-08-22T11:00:00.000Z' },
      },
      temp_sensor_config_id: 'temp-cfg-9',
      calibration_interval_days: 30,
    }))

    expect(mapped.calibration).toEqual({
      slope: -59.16,
      derived: { calibrated_at: '2026-08-22T11:00:00.000Z' },
    })
    expect(mapped.temp_sensor_config_id).toBe('temp-cfg-9')
    expect(mapped.calibration_interval_days).toBe(30)
    expect((mapped.calibration?.derived as { calibrated_at?: string })?.calibrated_at)
      .toBe('2026-08-22T11:00:00.000Z')
  })

  it('should keep calibration null when the config has none', () => {
    const mapped = mapSensorConfigToMockSensor(baseConfig())

    expect(mapped.calibration).toBeNull()
    expect(mapped.temp_sensor_config_id).toBeNull()
    expect(mapped.calibration_interval_days).toBeNull()
    expect(mapped.mount_height_cm).toBeNull()
    expect(mapped.mount_medium).toBeNull()
    expect(mapped.mount_angle_deg).toBeNull()
  })

  it('should pass AUT-1555 mount fields through from the loaded config', () => {
    const mapped = mapSensorConfigToMockSensor(baseConfig({
      mount_height_cm: 30,
      mount_medium: 'canopy',
      mount_angle_deg: 45,
    }))

    expect(mapped.mount_height_cm).toBe(30)
    expect(mapped.mount_medium).toBe('canopy')
    expect(mapped.mount_angle_deg).toBe(45)
  })

  it('should not invent ATC provenance on the card mapper (AUT-1561)', () => {
    const mapped = mapSensorConfigToMockSensor(baseConfig({
      temp_sensor_config_id: 'temp-cfg-9',
      metadata: { temp_source: 'default_25', temp_compensation_value: 25 },
    }))

    expect(mapped.temp_sensor_config_id).toBe('temp-cfg-9')
    expect(mapped.metadata).toBeUndefined()
  })
})
