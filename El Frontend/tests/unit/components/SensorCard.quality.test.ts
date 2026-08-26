/**
 * SensorCard quality labels (AUT-1564)
 *
 * Existing Card copy only. quality==critical must not look good.
 * "Kritisch" stays Inbox-Schwellenwert — Card alarm uses Alarm.
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
    last_read: new Date().toISOString(),
    calibration: null,
    temp_sensor_config_id: null,
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

describe('SensorCard — quality labels (AUT-1564)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show Alarm for leftover quality critical, not OK or Kritisch', () => {
    const wrapper = mountCard(baseSensor({ quality: 'critical' }))
    const badge = wrapper.get('.status-badge__label')
    expect(badge.text()).toBe('Alarm')
    expect(wrapper.text()).not.toContain('Kritisch')
  })

  it('should show Alarm for quality error, not Kritisch', () => {
    const wrapper = mountCard(baseSensor({ quality: 'error' }))
    expect(wrapper.get('.status-badge__label').text()).toBe('Alarm')
    expect(wrapper.text()).not.toContain('Kritisch')
  })

  it('should hide the quality badge when quality is good', () => {
    const wrapper = mountCard(baseSensor({ quality: 'good' }))
    expect(wrapper.find('.status-badge__label').exists()).toBe(false)
  })
})
