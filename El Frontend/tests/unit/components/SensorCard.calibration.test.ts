/**
 * SensorCard calibration badge (AUT-1544)
 *
 * Same key chain as SensorConfigPanel.calibrationStatusSummary /
 * DeviceStatusPanel.calibrationStatusLabel:
 * metadata.calibrated_at ?? calibrated_at ?? derived.calibrated_at
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SensorCard from '@/components/devices/SensorCard.vue'
import type { SensorWithContext } from '@/composables/useZoneGrouping'

vi.mock('@/api/sensors', () => ({
  sensorsApi: { triggerMeasurement: vi.fn() },
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

function baseSensor(overrides: Partial<SensorWithContext> = {}): SensorWithContext {
  return {
    gpio: 34,
    sensor_type: 'ph',
    name: 'pH Tank',
    raw_value: 5.8,
    unit: 'pH',
    quality: 'good',
    esp_id: 'ESP_TEST_001',
    zone_id: 'zone-1',
    zone_name: 'Haus A',
    subzone_id: null,
    subzone_name: '',
    last_read: '2026-08-24T18:00:00.000Z',
    calibration: null,
    ...overrides,
  }
}

function mountCard(sensor: SensorWithContext) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(SensorCard, {
    props: { sensor, mode: 'monitor' },
    global: { plugins: [pinia] },
  })
}

describe('SensorCard — calibration badge (AUT-1544)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show Nicht kalibriert when the blob is missing', () => {
    const wrapper = mountCard(baseSensor({ calibration: null }))
    const badge = wrapper.get('.sensor-card__badge--calibration-missing')
    expect(badge.text()).toBe('Nicht kalibriert')
    expect(wrapper.text()).not.toContain('valid_until')
  })

  it('should show Kalibriert plus relative time from derived.calibrated_at', () => {
    const wrapper = mountCard(baseSensor({
      calibration: {
        derived: { calibrated_at: new Date(Date.now() - 5 * 60 * 1000).toISOString() },
      },
    }))
    const badge = wrapper.get('.sensor-card__badge--calibration')
    expect(badge.text()).toMatch(/^Kalibriert vor /)
    expect(badge.text()).not.toMatch(/initiated_by|valid_until/)
  })

  it('should prefer metadata.calibrated_at over top-level and derived', () => {
    const wrapper = mountCard(baseSensor({
      calibration: {
        metadata: { calibrated_at: new Date(Date.now() - 60 * 1000).toISOString() },
        calibrated_at: '1999-01-01T00:00:00.000Z',
        derived: { calibrated_at: '1999-01-01T00:00:00.000Z' },
      },
    }))
    expect(wrapper.get('.sensor-card__badge--calibration').text()).toBe('Kalibriert vor 1 Minute')
  })

  it('should fall back to top-level calibrated_at before derived', () => {
    const wrapper = mountCard(baseSensor({
      calibration: {
        calibrated_at: new Date(Date.now() - 60 * 1000).toISOString(),
        derived: { calibrated_at: '1999-01-01T00:00:00.000Z' },
      },
    }))
    expect(wrapper.get('.sensor-card__badge--calibration').text()).toBe('Kalibriert vor 1 Minute')
  })

  it('should show Kalibriert when only cell_factor exists', () => {
    const wrapper = mountCard(baseSensor({
      calibration: { derived: { cell_factor: 1.02 } },
    }))
    expect(wrapper.get('.sensor-card__badge--calibration').text()).toBe('Kalibriert')
  })
})
