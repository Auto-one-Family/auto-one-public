/**
 * AddSensorModal Component Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import AddSensorModal from '@/components/esp/AddSensorModal.vue'

// Mock ESP store
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [],
    getDeviceId: (d: any) => d.device_id || '',
    isMock: () => true,
    addSensor: vi.fn(),
    fetchGpioStatus: vi.fn(),
    fetchDevice: vi.fn(),
    getOneWireScanState: () => ({
      isScanning: false,
      scanResults: [],
      selectedRomCodes: [],
      scanError: null,
      lastScanTimestamp: null,
      lastScanPin: null,
    }),
    scanOneWireBus: vi.fn(),
    clearOneWireScan: vi.fn(),
    toggleRomSelection: vi.fn(),
    deselectAllOneWireDevices: vi.fn(),
    selectSpecificRomCodes: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(),
  }),
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
  }),
}))

describe('AddSensorModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not render when modelValue is false', () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: false, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    expect(wrapper.find('.modal-overlay').exists()).toBe(false)
  })

  it('renders when modelValue is true', () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    expect(wrapper.text()).toContain('Sensor hinzufügen')
  })

  it('shows sensor type dropdown', () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    expect(wrapper.text()).toContain('Sensor-Typ')
    expect(wrapper.find('select').exists()).toBe(true)
  })

  it('shows operating mode selection', () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    expect(wrapper.text()).toContain('Betriebsmodus')
  })

  it('emits update:modelValue on close button click', async () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    await wrapper.find('.modal-close-btn').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0]).toEqual([false])
  })

  it('emits update:modelValue on cancel button click', async () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    const cancelBtn = wrapper.findAll('button').find(b => b.text().includes('Abbrechen'))
    expect(cancelBtn).toBeDefined()
    await cancelBtn!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  it('shows OneWire scan section when DS18B20 selected', () => {
    const wrapper = mount(AddSensorModal, {
      props: { modelValue: true, espId: 'ESP_001' },
      global: { plugins: [createPinia()], stubs: { Teleport: true, GpioPicker: true } },
    })
    // Default sensor type is DS18B20
    expect(wrapper.text()).toContain('OneWire-Bus scannen')
  })
})
