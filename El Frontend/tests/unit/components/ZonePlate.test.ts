/**
 * ZonePlate Component Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ZonePlate from '@/components/dashboard/ZonePlate.vue'
import DeviceMiniCard from '@/components/dashboard/DeviceMiniCard.vue'

// lucide-vue-next is mocked globally in tests/setup.ts

// Mock the ESP store entirely to avoid WebSocket initialization
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    getDeviceId: (d: any) => d.device_id || d.esp_id || '',
    isMock: (id: string) => id.includes('MOCK'),
    devices: [],
  }),
}))

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    crossEspConnections: [],
  }),
}))

vi.mock('@/shared/stores', () => ({
  useDragStateStore: () => ({
    isDraggingEspCard: false,
    isAnyDragActive: false,
  }),
}))

vi.mock('@/shared/stores/ui.store', () => ({
  useUiStore: () => ({
    showConfirmDialog: vi.fn(),
    showContextMenu: vi.fn(),
    hideContextMenu: vi.fn(),
  }),
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
  }),
}))

const now = new Date().toISOString()
const oldTs = new Date(Date.now() - 600000).toISOString() // 10 min ago

const mockDevices = [
  {
    device_id: 'ESP_001', name: 'ESP 1', status: 'online', connected: true,
    last_heartbeat: now, last_seen: now,
    sensors: [{ gpio: 4, sensor_type: 'DS18B20' }], actuators: [{ gpio: 16, actuator_type: 'relay' }],
    sensor_count: 1, actuator_count: 1, subzone_id: 'sub_1', subzone_name: 'Bewässerung',
  },
  {
    device_id: 'ESP_002', name: 'ESP 2', status: 'offline', connected: false,
    last_heartbeat: oldTs, last_seen: oldTs,
    sensors: [{ gpio: 5, sensor_type: 'DHT22' }, { gpio: 6, sensor_type: 'BH1750' }], actuators: [],
    sensor_count: 2, actuator_count: 0, subzone_id: null, subzone_name: null,
  },
]

function mountPlate(overrides: Record<string, unknown> = {}) {
  return mount(ZonePlate, {
    props: { zoneId: 'zone_1', zoneName: 'Zone 1', devices: mockDevices as any, ...overrides },
    global: { plugins: [createPinia()] },
  })
}

describe('ZonePlate', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('renders zone name', () => {
    const w = mountPlate({ zoneName: 'Gewächshaus A' })
    expect(w.text()).toContain('Gewächshaus A')
  })

  it('shows ESP count and online/total', () => {
    const w = mountPlate()
    expect(w.text()).toContain('2 ESPs')
    expect(w.text()).toContain('1/2 Online')
  })

  it('shows ESP count and online stats in header', () => {
    const w = mountPlate()
    // Slim header: "2 ESPs · 1/2 Online" (meta pills removed in Block 2 redesign)
    expect(w.text()).toContain('2 ESPs')
    expect(w.text()).toContain('1/2 Online')
  })

  it('renders device wrappers for each device', () => {
    const w = mountPlate()
    const wrappers = w.findAll('.zone-plate__device-wrapper')
    expect(wrappers).toHaveLength(2)
  })

  it('renders subzone label', () => {
    const w = mountPlate()
    expect(w.text()).toContain('Bewässerung')
  })

  it('forwards device-delete from card as zone-level device-delete event', async () => {
    const w = mountPlate()
    const card = w.findComponent(DeviceMiniCard)
    card.vm.$emit('device-delete', 'ESP_001')
    await w.vm.$nextTick()

    expect(w.emitted('device-delete')).toBeTruthy()
    expect(w.emitted('device-delete')?.[0]).toEqual(['ESP_001'])
  })

  it('has healthy class when all online', () => {
    const allOnline = [{ ...mockDevices[0] }]
    const w = mountPlate({ devices: allOnline })
    expect(w.find('.zone-plate--healthy').exists()).toBe(true)
  })

  it('handles empty devices', () => {
    const w = mountPlate({ devices: [] })
    expect(w.text()).toContain('0 ESPs')
    expect(w.text()).toContain('- Leer')
  })
})
