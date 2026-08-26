/**
 * SensorCard ATC badges (AUT-1561)
 *
 * Existing badge only. Hide when no compensation value.
 * No new badge system. No auto-ATC.
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
    temp_sensor_config_id: 'temp-cfg-9',
    metadata: null,
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

describe('SensorCard — ATC badges (AUT-1561)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should hide ATC badges when the card has no compensation value', () => {
    const wrapper = mountCard(baseSensor({
      metadata: { temp_source: 'default_25' },
    }))
    expect(wrapper.find('.sensor-card__badge--atc-fallback').exists()).toBe(false)
    expect(wrapper.find('.sensor-card__badge--atc-cached').exists()).toBe(false)
    expect(wrapper.find('.sensor-card__badge--atc-read-failed').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('ATC:')
  })

  it('should hide ATC badges when metadata is missing after FK-only mapper data', () => {
    const wrapper = mountCard(baseSensor({
      temp_sensor_config_id: 'temp-cfg-9',
      metadata: null,
    }))
    expect(wrapper.find('.sensor-card__badge--atc-fallback').exists()).toBe(false)
    expect(wrapper.find('.sensor-card__badge--atc-cached').exists()).toBe(false)
    expect(wrapper.find('.sensor-card__badge--atc-read-failed').exists()).toBe(false)
  })

  it('should show the existing fallback badge when the compensation value is present', () => {
    const wrapper = mountCard(baseSensor({
      metadata: { temp_source: 'default_25', temp_compensation_value: 25 },
    }))
    const badge = wrapper.get('.sensor-card__badge--atc-fallback')
    expect(badge.text()).toContain('ATC: Fallback 25°C')
    expect(wrapper.find('.sensor-card__badge--atc-cached').exists()).toBe(false)
  })

  it('should show the existing cached badge when the compensation value is present', () => {
    const wrapper = mountCard(baseSensor({
      metadata: { temp_source: 'cached_temp', temp_compensation_value: 22.4 },
    }))
    expect(wrapper.get('.sensor-card__badge--atc-cached').text()).toBe('~T')
  })
})
