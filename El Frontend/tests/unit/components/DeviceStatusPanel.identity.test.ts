/**
 * DeviceStatusPanel identity chrome (AUT-1523)
 *
 * Aktor: Name einmal im Config-Input — Status-Kopf zeigt Typ, Meta nur espId.
 * Sensor: GPIO ist keine Identität (Meta leer).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import DeviceStatusPanel from '@/components/devices/DeviceStatusPanel.vue'

vi.mock('@/api/actuators', () => ({
  actuatorsApi: {
    get: vi.fn(async () => null),
    emergencyStop: vi.fn(),
  },
}))
vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    get: vi.fn(async () => null),
  },
}))
vi.mock('@/api/esp', () => ({
  espApi: { isMockEsp: () => false },
}))
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        device_id: 'ESP_AEAE64',
        name: 'Board',
        actuators: [{ gpio: 26, name: 'Nachfüllpumpe', state: false }],
      },
    ],
    getDeviceId: (d: { device_id?: string }) => d?.device_id || '',
    sendActuatorCommand: vi.fn(),
    emergencyStop: vi.fn(),
  }),
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

const stubs = {
  LinkedRulesSection: true,
  LiveDataPreview: true,
}

describe('DeviceStatusPanel — identity chrome (AUT-1523)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show actuator type and espId without GPIO or the custom name', async () => {
    const wrapper = mount(DeviceStatusPanel, {
      props: {
        espId: 'ESP_AEAE64',
        gpio: 26,
        mode: 'actuator',
        actuatorType: 'pump',
      },
      global: { plugins: [createPinia()], stubs },
    })
    await flushPromises()
    expect(wrapper.get('.status-panel__name').text()).toBe('Pumpe')
    expect(wrapper.get('.status-panel__meta').text()).toBe('ESP_AEAE64')
    expect(wrapper.get('.status-panel__meta').text()).not.toContain('GPIO')
    expect(wrapper.text()).not.toContain('Nachfüllpumpe')
  })

  it('should omit GPIO from the sensor identity line', async () => {
    const wrapper = mount(DeviceStatusPanel, {
      props: {
        espId: 'ESP_AEAE64',
        gpio: 4,
        mode: 'sensor',
        sensorType: 'temperature',
      },
      global: { plugins: [createPinia()], stubs },
    })
    await flushPromises()
    expect(wrapper.find('.status-panel__meta').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('GPIO')
    expect(wrapper.text()).not.toContain('ESP_AEAE64')
  })
})
