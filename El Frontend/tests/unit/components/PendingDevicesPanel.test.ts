/**
 * PendingDevicesPanel Component Tests
 *
 * Block 3: Updated for SlideOver-based panel (was popover).
 * Tests tab switching, empty states, device list, search, and actions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PendingDevicesPanel from '@/components/esp/PendingDevicesPanel.vue'

// Mock the ESP store
const mockFetchPendingDevices = vi.fn()
const mockApproveDevice = vi.fn()
const mockRejectDevice = vi.fn()
const mockDeleteDevice = vi.fn()

let mockDevices: any[] = []
let mockPendingDevices: any[] = []
let mockIsPendingLoading = false

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: mockDevices,
    pendingDevices: mockPendingDevices,
    isPendingLoading: mockIsPendingLoading,
    fetchPendingDevices: mockFetchPendingDevices,
    approveDevice: mockApproveDevice,
    rejectDevice: mockRejectDevice,
    deleteDevice: mockDeleteDevice,
    getDeviceId: (d: any) => d?.device_id || d?.esp_id || '',
    isMock: (id: string) => id.startsWith('MOCK_'),
    mockDevices: [],
    realDevices: [],
    unassignedDevices: [],
  }),
}))

vi.mock('@/shared/stores/ui.store', () => ({
  useUiStore: () => ({
    confirm: vi.fn().mockResolvedValue(true),
    openContextMenu: vi.fn(),
    pushModal: vi.fn(),
    popModal: vi.fn(),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('@/composables/useZoneDragDrop', () => ({
  useZoneDragDrop: () => ({
    groupDevicesByZone: (devices: any[]) => {
      const grouped: Record<string, any> = {}
      for (const d of devices) {
        const zId = d.zone_id || '__UNASSIGNED__'
        const zName = d.zone_name || 'Nicht zugewiesen'
        if (!grouped[zId]) grouped[zId] = { zoneId: zId, zoneName: zName, devices: [] }
        grouped[zId].devices.push(d)
      }
      return Object.values(grouped)
    },
  }),
  ZONE_UNASSIGNED: '__UNASSIGNED__',
}))

vi.mock('@/composables/useESPStatus', () => ({
  getESPStatus: () => 'online',
  getESPStatusDisplay: () => ({ text: 'Online', color: 'var(--color-success)' }),
}))

vi.mock('@/utils/wifiStrength', () => ({
  getWifiStrength: () => ({
    quality: 'good',
    label: 'Gut',
    bars: 3,
  }),
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

// Stub child components
vi.mock('@/components/modals/RejectDeviceModal.vue', () => ({
  default: {
    name: 'RejectDeviceModal',
    template: '<div class="reject-modal-stub" />',
    props: ['open', 'deviceId'],
  },
}))

vi.mock('@/shared/design/primitives/SlideOver.vue', () => ({
  default: {
    name: 'SlideOver',
    template: '<div class="slide-over-stub" v-if="open"><slot /></div>',
    props: ['open', 'title', 'width'],
    emits: ['close'],
  },
}))

const sampleDevices = [
  {
    device_id: 'ESP_001',
    name: 'Gewächshaus ESP',
    zone_id: 'zone-1',
    zone_name: 'Echt',
    sensors: [{ gpio: 4, sensor_type: 'sht31_temp' }],
    status: 'online',
  },
  {
    device_id: 'ESP_002',
    name: null,
    zone_id: 'zone-1',
    zone_name: 'Echt',
    sensors: [],
    status: 'offline',
  },
]

const samplePendingDevices = [
  {
    device_id: 'ESP_NEW_001',
    ip_address: '192.168.1.50',
    wifi_rssi: -55,
    discovered_at: new Date().toISOString(),
    last_seen: new Date().toISOString(),
  },
  {
    device_id: 'ESP_NEW_002',
    ip_address: '192.168.1.51',
    wifi_rssi: -72,
    discovered_at: new Date().toISOString(),
    last_seen: new Date().toISOString(),
  },
]

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(PendingDevicesPanel, {
    props: {
      isOpen: false,
      ...props,
    },
    global: {
      plugins: [createPinia()],
    },
  })
}

describe('PendingDevicesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockDevices = []
    mockPendingDevices = []
    mockIsPendingLoading = false
    mockFetchPendingDevices.mockClear()
    mockApproveDevice.mockClear()
    mockRejectDevice.mockClear()
    mockDeleteDevice.mockClear()
  })

  describe('visibility', () => {
    it('does NOT render panel content when isOpen=false', () => {
      const w = mountPanel({ isOpen: false })
      expect(w.find('.slide-over-stub').exists()).toBe(false)
    })

    it('renders panel when isOpen=true', () => {
      const w = mountPanel({ isOpen: true })
      expect(w.find('.slide-over-stub').exists()).toBe(true)
    })
  })

  describe('tab switching', () => {
    it('starts on the devices tab', () => {
      const w = mountPanel({ isOpen: true })
      const tabs = w.findAll('.device-panel__tab')
      expect(tabs[0].classes()).toContain('device-panel__tab--active')
      expect(tabs[0].text()).toContain('Geräte')
    })

    it('switches to pending tab on click', async () => {
      const w = mountPanel({ isOpen: true })
      const tabs = w.findAll('.device-panel__tab')
      await tabs[1].trigger('click')

      const updatedTabs = w.findAll('.device-panel__tab')
      expect(updatedTabs[1].classes()).toContain('device-panel__tab--active')
    })

    it('switches to info tab on click', async () => {
      const w = mountPanel({ isOpen: true })
      const tabs = w.findAll('.device-panel__tab')
      await tabs[2].trigger('click')

      const updatedTabs = w.findAll('.device-panel__tab')
      expect(updatedTabs[2].classes()).toContain('device-panel__tab--active')
    })

    it('info tab shows connection guide content', async () => {
      const w = mountPanel({ isOpen: true })
      const tabs = w.findAll('.device-panel__tab')
      await tabs[2].trigger('click')

      expect(w.text()).toContain('ESP32 verbinden')
      expect(w.text()).toContain('Firmware flashen')
    })
  })

  describe('empty state', () => {
    it('shows devices empty state when no devices (default tab)', () => {
      mockDevices = []
      const w = mountPanel({ isOpen: true })
      expect(w.find('.device-panel__empty').exists()).toBe(true)
      expect(w.text()).toContain('Keine Geräte vorhanden')
    })

    it('shows pending empty state when on pending tab and no pending devices', async () => {
      mockPendingDevices = []
      mockIsPendingLoading = false
      const w = mountPanel({ isOpen: true })
      await w.findAll('.device-panel__tab')[1].trigger('click')
      expect(w.text()).toContain('Keine neuen Geräte')
    })
  })

  describe('device list (Geräte tab)', () => {
    it('renders device rows when devices exist in zones', () => {
      mockDevices = sampleDevices
      const w = mountPanel({ isOpen: true })
      const devices = w.findAll('.device-panel__device')
      expect(devices).toHaveLength(2)
    })

    it('displays device names', () => {
      mockDevices = sampleDevices
      const w = mountPanel({ isOpen: true })
      expect(w.text()).toContain('Gewächshaus ESP')
      expect(w.text()).toContain('ESP_002')
    })

    it('displays zone group headers', () => {
      mockDevices = sampleDevices
      const w = mountPanel({ isOpen: true })
      expect(w.find('.device-panel__zone-title').text()).toBe('Echt')
    })

    it('shows config and delete buttons for each device', () => {
      mockDevices = [sampleDevices[0]]
      const w = mountPanel({ isOpen: true })
      expect(w.find('.device-panel__btn--config').exists()).toBe(true)
      expect(w.find('.device-panel__btn--delete').exists()).toBe(true)
    })

    it('emits open-esp-config when config button is clicked', async () => {
      mockDevices = [sampleDevices[0]]
      const w = mountPanel({ isOpen: true })
      await w.find('.device-panel__btn--config').trigger('click')
      expect(w.emitted('open-esp-config')).toBeTruthy()
    })
  })

  describe('search', () => {
    it('renders search field on devices tab', () => {
      const w = mountPanel({ isOpen: true })
      expect(w.find('.device-panel__search-input').exists()).toBe(true)
    })

    it('filters devices by name', async () => {
      mockDevices = sampleDevices
      const w = mountPanel({ isOpen: true })
      const input = w.find('.device-panel__search-input')
      await input.setValue('Gewächshaus')
      const devices = w.findAll('.device-panel__device')
      expect(devices).toHaveLength(1)
      expect(w.text()).toContain('Gewächshaus ESP')
    })

    it('shows no-results state when search matches nothing', async () => {
      mockDevices = sampleDevices
      const w = mountPanel({ isOpen: true })
      const input = w.find('.device-panel__search-input')
      await input.setValue('xyz-not-found')
      expect(w.text()).toContain('Keine Treffer')
    })

    it('shows clear button when search has value', async () => {
      const w = mountPanel({ isOpen: true })
      const input = w.find('.device-panel__search-input')
      await input.setValue('test')
      expect(w.find('.device-panel__search-clear').exists()).toBe(true)
    })
  })

  describe('pending device list', () => {
    it('renders pending device cards', async () => {
      mockPendingDevices = samplePendingDevices
      const w = mountPanel({ isOpen: true })
      await w.findAll('.device-panel__tab')[1].trigger('click')
      const devices = w.findAll('.device-panel__pending-device')
      expect(devices).toHaveLength(2)
    })

    it('displays pending device IDs', async () => {
      mockPendingDevices = samplePendingDevices
      const w = mountPanel({ isOpen: true })
      await w.findAll('.device-panel__tab')[1].trigger('click')
      expect(w.text()).toContain('ESP_NEW_001')
      expect(w.text()).toContain('ESP_NEW_002')
    })

    it('displays IP addresses', async () => {
      mockPendingDevices = samplePendingDevices
      const w = mountPanel({ isOpen: true })
      await w.findAll('.device-panel__tab')[1].trigger('click')
      expect(w.text()).toContain('192.168.1.50')
      expect(w.text()).toContain('192.168.1.51')
    })

    it('shows approve and reject buttons', async () => {
      mockPendingDevices = [samplePendingDevices[0]]
      const w = mountPanel({ isOpen: true })
      await w.findAll('.device-panel__tab')[1].trigger('click')
      expect(w.find('.device-panel__btn--approve').exists()).toBe(true)
      expect(w.find('.device-panel__btn--reject').exists()).toBe(true)
    })
  })
})
