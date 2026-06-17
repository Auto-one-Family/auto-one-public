/**
 * Tests for ESPSettingsSheet accessibility and structure.
 * Verifies dialog role, ARIA attributes, section rendering.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ESPSettingsSheet from '@/components/esp/ESPSettingsSheet.vue'

const mockDevice = {
  device_id: 'ESP_001',
  esp_id: 'ESP_001',
  name: 'Test Device',
  status: 'online',
  connected: true,
  wifi_rssi: -45,
  heap_free: 98304,
  last_heartbeat: new Date().toISOString(),
  zone_id: null,
  zone_name: null,
  master_zone_id: null,
  hardware_type: 'ESP32',
  sensors: [],
  actuators: [],
}

// Mock all external dependencies
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [mockDevice],
    triggerHeartbeat: vi.fn(),
    deleteDevice: vi.fn(),
    updateDevice: vi.fn(),
    setAutoHeartbeat: vi.fn(),
  }),
}))

vi.mock('@/shared/stores', () => ({
  useUiStore: () => ({
    pushModal: vi.fn(),
    popModal: vi.fn(),
    confirm: vi.fn(),
  }),
}))

vi.mock('@/shared/stores/intentSignals.store', () => ({
  useIntentSignalsStore: () => ({
    getDisplayForEsp: vi.fn(() => null),
  }),
}))

vi.mock('@/api/esp', () => ({
  espApi: { isMockEsp: () => false },
}))

vi.mock('@/utils/wifiStrength', () => ({
  getWifiStrength: () => ({ quality: 'good', bars: 3, label: 'Gut' }),
}))

vi.mock('@/utils/formatters', () => ({
  formatRelativeTime: () => 'vor 5 Sek.',
  formatUptimeShort: () => '1h 30m',
  formatHeapSize: () => '96 KB',
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  }),
}))

function mountSheet(isOpen = true) {
  return mount(ESPSettingsSheet, {
    props: {
      device: mockDevice as any,
      isOpen,
    },
    global: {
      stubs: {
        Badge: { template: '<span class="badge"><slot /></span>' },
        ZoneAssignmentPanel: { template: '<div class="zone-panel" />' },
        SensorConfigPanel: { template: '<div class="sensor-panel" />' },
        ActuatorConfigPanel: { template: '<div class="actuator-panel" />' },
      },
    },
    attachTo: document.body,
  })
}

describe('ESPSettingsSheet', () => {
  it('renders dialog with role="dialog"', () => {
    const wrapper = mountSheet()
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.exists()).toBe(true)
    wrapper.unmount()
  })

  it('has aria-modal="true"', () => {
    const wrapper = mountSheet()
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('true')
    wrapper.unmount()
  })

  it('has aria-labelledby pointing to title', () => {
    const wrapper = mountSheet()
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.attributes('aria-labelledby')).toBe('sheet-title')

    const title = wrapper.find('#sheet-title')
    expect(title.exists()).toBe(true)
    expect(title.text()).toContain('Geräte-Einstellungen')
    wrapper.unmount()
  })

  it('close button has aria-label', () => {
    const wrapper = mountSheet()
    const closeBtn = wrapper.find('[aria-label="Schließen"]')
    expect(closeBtn.exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders identification section with device name', () => {
    const wrapper = mountSheet()
    expect(wrapper.text()).toContain('Identifikation')
    expect(wrapper.text()).toContain('Test Device')
    wrapper.unmount()
  })

  it('renders status section', () => {
    const wrapper = mountSheet()
    expect(wrapper.text()).toContain('Status')
    expect(wrapper.text()).toContain('Verbindung')
    wrapper.unmount()
  })

  it('renders zone section', () => {
    const wrapper = mountSheet()
    expect(wrapper.text()).toContain('Zone')
    wrapper.unmount()
  })

  it('does not render sensor config when no sensors', () => {
    const wrapper = mountSheet()
    expect(wrapper.text()).not.toContain('Sensor-Konfiguration')
    wrapper.unmount()
  })

  it('does not render actuator config when no actuators', () => {
    const wrapper = mountSheet()
    expect(wrapper.text()).not.toContain('Aktor-Konfiguration')
    wrapper.unmount()
  })

  it('does not render when closed', () => {
    const wrapper = mountSheet(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
