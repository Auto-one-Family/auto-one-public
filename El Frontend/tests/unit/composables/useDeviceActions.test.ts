/**
 * useDeviceActions Composable Tests
 *
 * Tests for shared device logic: identity, WiFi, heartbeat, name editing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { ESPDevice } from '@/api/esp'

// Mock websocket service (required by ESP store)
vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false),
    on: vi.fn(() => vi.fn()),
    onConnect: vi.fn(() => vi.fn()),
    subscribe: vi.fn(() => 'sub-id'),
    unsubscribe: vi.fn(),
  },
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(),
  }),
}))

// Mock useWebSocket
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    on: vi.fn(() => vi.fn()),
    disconnect: vi.fn(),
    isConnected: { value: false },
    connectionStatus: { value: 'disconnected' },
  }),
}))

// Mock useToast
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), show: vi.fn(),
  }),
}))

import { useDeviceActions } from '@/composables/useDeviceActions'

// ── Test Data ────────────────────────────────────────────────────────

function createMockDevice(overrides: Partial<ESPDevice> = {}): ESPDevice {
  return {
    device_id: 'ESP_MOCK_001',
    esp_id: 'ESP_MOCK_001',
    name: 'Test Device',
    status: 'online',
    connected: true,
    wifi_rssi: -55,
    last_heartbeat: new Date().toISOString(),
    last_seen: new Date().toISOString(),
    sensors: [],
    actuators: [],
    sensor_count: 0,
    actuator_count: 0,
    ...overrides,
  } as ESPDevice
}

// ── Tests ────────────────────────────────────────────────────────────

describe('useDeviceActions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('Identity', () => {
    it('returns espId from device', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      expect(actions.espId.value).toBe('ESP_MOCK_001')
    })

    it('detects mock devices', () => {
      const device = createMockDevice({ device_id: 'ESP_MOCK_001' })
      const actions = useDeviceActions(() => device)
      expect(actions.isMock.value).toBe(true)
    })

    it('detects real devices', () => {
      const device = createMockDevice({ device_id: 'ESP_12345678', esp_id: 'ESP_12345678' })
      const actions = useDeviceActions(() => device)
      expect(actions.isMock.value).toBe(false)
    })

    it('returns display name', () => {
      const device = createMockDevice({ name: 'My ESP' })
      const actions = useDeviceActions(() => device)
      expect(actions.displayName.value).toBe('My ESP')
    })

    it('returns null for unnamed device', () => {
      const device = createMockDevice({ name: undefined })
      const actions = useDeviceActions(() => device)
      expect(actions.displayName.value).toBeNull()
    })

    it('detects online status', () => {
      const device = createMockDevice({ status: 'online', connected: true })
      const actions = useDeviceActions(() => device)
      expect(actions.isOnline.value).toBe(true)
    })

    it('detects offline status', () => {
      const device = createMockDevice({ status: 'offline', connected: false })
      const actions = useDeviceActions(() => device)
      expect(actions.isOnline.value).toBe(false)
    })

    it('treats stale heartbeat as not-online and marks state as Verzoegert', () => {
      const staleTs = new Date(Date.now() - 120_000).toISOString()
      const device = createMockDevice({
        device_id: 'ESP_REAL_001',
        esp_id: 'ESP_REAL_001',
        status: 'online',
        connected: true,
        last_seen: staleTs,
        last_heartbeat: staleTs,
      })
      const actions = useDeviceActions(() => device)
      expect(actions.isOnline.value).toBe(false)
      expect(actions.stateInfo.value.label).toBe('Verzögert')
    })

    it('returns state info for online device', () => {
      const device = createMockDevice({ status: 'online' })
      const actions = useDeviceActions(() => device)
      expect(actions.stateInfo.value.label).toBeDefined()
      expect(actions.stateInfo.value.variant).toBeDefined()
    })
  })

  describe('WiFi', () => {
    it('returns wifi info for good signal', () => {
      const device = createMockDevice({ wifi_rssi: -45 })
      const actions = useDeviceActions(() => device)
      expect(actions.wifiInfo.value.quality).toBe('excellent')
    })

    it('returns wifi info for weak signal', () => {
      const device = createMockDevice({ wifi_rssi: -80 })
      const actions = useDeviceActions(() => device)
      expect(['poor', 'fair']).toContain(actions.wifiInfo.value.quality)
    })

    it('returns wifi color class', () => {
      const device = createMockDevice({ wifi_rssi: -45 })
      const actions = useDeviceActions(() => device)
      expect(actions.wifiColorClass.value).toBe('wifi--good')
    })

    it('returns wifi tooltip with RSSI', () => {
      const device = createMockDevice({ wifi_rssi: -55 })
      const actions = useDeviceActions(() => device)
      expect(actions.wifiTooltip.value).toContain('-55 dBm')
    })

    it('returns no-data tooltip when no RSSI', () => {
      const device = createMockDevice({ wifi_rssi: undefined })
      const actions = useDeviceActions(() => device)
      expect(actions.wifiTooltip.value).toContain('Keine Telemetrie')
    })
  })

  describe('Heartbeat', () => {
    it('detects fresh heartbeat (< 2 min)', () => {
      const device = createMockDevice({ last_heartbeat: new Date().toISOString() })
      const actions = useDeviceActions(() => device)
      expect(actions.isHeartbeatFresh.value).toBe(true)
    })

    it('detects stale heartbeat (> 2 min)', () => {
      const old = new Date(Date.now() - 300_000).toISOString() // 5 min ago
      const device = createMockDevice({ last_heartbeat: old })
      const actions = useDeviceActions(() => device)
      expect(actions.isHeartbeatFresh.value).toBe(false)
    })

    it('returns heartbeat tooltip for mock', () => {
      const device = createMockDevice({ device_id: 'ESP_MOCK_001' })
      const actions = useDeviceActions(() => device)
      expect(actions.heartbeatTooltip.value).toContain('Klick')
    })

    it('is not loading initially', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      expect(actions.heartbeatLoading.value).toBe(false)
    })

    it('returns heartbeat text', () => {
      const device = createMockDevice({ last_heartbeat: new Date().toISOString() })
      const actions = useDeviceActions(() => device)
      expect(actions.heartbeatText.value).toBeDefined()
      expect(typeof actions.heartbeatText.value).toBe('string')
    })
  })

  describe('Name Editing', () => {
    it('starts not editing', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      expect(actions.isEditingName.value).toBe(false)
    })

    it('starts editing with current name', () => {
      const device = createMockDevice({ name: 'My Device' })
      const actions = useDeviceActions(() => device)
      actions.startEditName()
      expect(actions.isEditingName.value).toBe(true)
      expect(actions.editedName.value).toBe('My Device')
    })

    it('starts editing with empty string for unnamed', () => {
      const device = createMockDevice({ name: undefined })
      const actions = useDeviceActions(() => device)
      actions.startEditName()
      expect(actions.editedName.value).toBe('')
    })

    it('cancels editing', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      actions.startEditName()
      actions.cancelEditName()
      expect(actions.isEditingName.value).toBe(false)
    })

    it('clears error on cancel', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      actions.startEditName()
      actions.saveError.value = 'some error'
      actions.cancelEditName()
      expect(actions.saveError.value).toBeNull()
    })

    it('returns null on save when name unchanged', async () => {
      const device = createMockDevice({ name: 'Test' })
      const actions = useDeviceActions(() => device)
      actions.startEditName()
      actions.editedName.value = 'Test' // same as before
      const result = await actions.saveName()
      expect(result).toBeNull()
      expect(actions.isEditingName.value).toBe(false)
    })

    it('is not saving initially', () => {
      const device = createMockDevice()
      const actions = useDeviceActions(() => device)
      expect(actions.isSavingName.value).toBe(false)
    })
  })
})
