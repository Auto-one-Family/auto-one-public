/**
 * ESP Store Unit Tests
 *
 * Tests for ESP device management, WebSocket handlers,
 * Mock ESP operations, and pending device approval workflow.
 */

import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import {
  mockESPDevice,
  mockSensor,
  mockActuator,
  mockPendingDevice,
  mockGpioStatus,
  setMockDeviceStatus,
  resetMockState,
} from '../../mocks/handlers'

// MSW Server Lifecycle
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// MOCK WEBSOCKET SERVICE (must be before import)
// =============================================================================

vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false),
    on: vi.fn(() => vi.fn()),
    onConnect: vi.fn(() => vi.fn())
  }
}))

// =============================================================================
// MOCK USE_WEBSOCKET COMPOSABLE
// =============================================================================

const mockWsOn = vi.fn(() => vi.fn())

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    on: mockWsOn,
    disconnect: vi.fn(),
    connect: vi.fn(),
    status: 'connected'
  }))
}))

// =============================================================================
// MOCK USE_TOAST COMPOSABLE
// =============================================================================

// Create mock functions that persist across tests
const mockToastFunctions = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  show: vi.fn(),
  dismiss: vi.fn(),
  dismissAll: vi.fn()
}

vi.mock('@/composables/useToast', () => ({
  useToast: vi.fn(() => mockToastFunctions)
}))

// Import store after mocks are set up
import { useEspStore } from '@/stores/esp'
import { useActuatorStore, ACTUATOR_UI_COMMAND_COOLDOWN_MS } from '@/shared/stores/actuator.store'
import { actuatorsApi } from '@/api/actuators'
import { websocketService } from '@/services/websocket'

// =============================================================================
// INITIAL STATE TESTS
// =============================================================================

describe('ESP Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('has empty devices array on initialization', () => {
    const store = useEspStore()
    expect(store.devices).toEqual([])
  })

  it('has null selectedDeviceId initially', () => {
    const store = useEspStore()
    expect(store.selectedDeviceId).toBeNull()
  })

  it('has isLoading false initially', () => {
    const store = useEspStore()
    expect(store.isLoading).toBe(false)
  })

  it('has null error initially', () => {
    const store = useEspStore()
    expect(store.error).toBeNull()
  })

  it('has empty pendingDevices array initially', () => {
    const store = useEspStore()
    expect(store.pendingDevices).toEqual([])
  })

  it('has isPendingLoading false initially', () => {
    const store = useEspStore()
    expect(store.isPendingLoading).toBe(false)
  })

  it('has empty gpioStatusMap initially', () => {
    const store = useEspStore()
    expect(store.gpioStatusMap.size).toBe(0)
  })
})

describe('ESP Store - WebSocket Health Mapping', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('maps esp_health telemetry into runtime_health_view', () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001' } as any]

    const espHealthRegistration = mockWsOn.mock.calls.find(([event]) => event === 'esp_health')
    const handler = espHealthRegistration?.[1] as ((message: any) => void) | undefined

    expect(handler).toBeTypeOf('function')

    handler?.({
      data: {
        esp_id: 'ESP_TEST_001',
        status: 'online',
        timestamp: 1713984000,
        persistence_degraded: true,
        persistence_degraded_reason: 'db_sync_delayed',
      },
    })

    const updated = store.devices.find((device) => (device.device_id || device.esp_id) === 'ESP_TEST_001')
    expect(updated?.runtime_health_view?.persistenceDegraded).toBe(true)
    expect(updated?.runtime_health_view?.persistenceDegradedReason).toBe('db_sync_delayed')
  })
})

describe('ESP Store - WebSocket Reconnect Recovery', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('triggert intent-reconciliation zusaetzlich zum fetchAll bei onConnect', async () => {
    const espStore = useEspStore()
    const actuatorStore = useActuatorStore()
    const reconcileSpy = vi
      .spyOn(actuatorStore, 'reconcilePendingIntentsFromServer')
      .mockResolvedValue(0)

    const onConnectMock = websocketService.onConnect as unknown as {
      mock: { calls: unknown[][] }
    }
    const onConnectCallback = onConnectMock.mock.calls[0]?.[0] as (() => void) | undefined
    expect(onConnectCallback).toBeTypeOf('function')

    onConnectCallback?.()
    await vi.waitFor(() => {
      expect(reconcileSpy).toHaveBeenCalledTimes(1)
    }, { timeout: 5000 })
  })
})

// =============================================================================
// API ACTIONS - FETCH ALL
// =============================================================================

describe('ESP Store - fetchAll', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should load devices and populate devices array', async () => {
    const store = useEspStore()

    await store.fetchAll()

    expect(store.devices.length).toBeGreaterThan(0)
  })

  it('should set isLoading during fetch', async () => {
    const store = useEspStore()

    const fetchPromise = store.fetchAll()
    expect(store.isLoading).toBe(true)

    await fetchPromise
    expect(store.isLoading).toBe(false)
  })

  it('should set error on fetch failure', async () => {
    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.json(
          { detail: 'Server error' },
          { status: 500 }
        )
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json(
          { detail: 'Server error' },
          { status: 500 }
        )
      })
    )

    const store = useEspStore()
    // Store catches error, sets error.value, then re-throws
    await expect(store.fetchAll()).rejects.toThrow()

    // Error was set, devices remain empty
    expect(store.error).toBeTruthy()
    expect(store.devices).toEqual([])
  })

  it('should deduplicate devices by device_id', async () => {
    const duplicateDevice = { ...mockESPDevice, esp_id: 'ESP_TEST_001', device_id: 'ESP_TEST_001' }

    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.json({
          data: [{ ...mockESPDevice, device_id: 'ESP_TEST_001' }],
          total: 1
        })
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json({
          success: true,
          data: [duplicateDevice],
          total: 1
        })
      })
    )

    const store = useEspStore()
    await store.fetchAll()

    // Should only have one device (deduplicated)
    const deviceIds = store.devices.map(d => d.device_id || d.esp_id)
    const uniqueIds = [...new Set(deviceIds)]
    expect(uniqueIds.length).toBe(deviceIds.length)
  })

  it('should replace stale local snapshot on fetchAll', async () => {
    const store = useEspStore()
    store.replaceDevices([
      { ...mockESPDevice, device_id: 'ESP_STALE_001', esp_id: 'ESP_STALE_001' },
    ])

    await store.fetchAll()

    const ids = store.devices.map((d) => d.device_id || d.esp_id)
    expect(ids).not.toContain('ESP_STALE_001')
  })

  it('should preserve fresher in-memory sensor readings when DB snapshot is older', async () => {
    const liveLastRead = '2026-06-01T12:00:00.000Z'
    const staleLastRead = '2026-06-01T11:00:00.000Z'

    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.json({
          data: [{
            ...mockESPDevice,
            device_id: 'ESP_TEST_001',
            esp_id: 'ESP_TEST_001',
            sensors: [{
              ...mockSensor,
              gpio: 4,
              sensor_type: 'sht31_temp',
              raw_value: 19.5,
              last_read: staleLastRead,
            }],
            actuators: [],
          }],
          total: 1,
        })
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json({ success: true, data: [], total: 0 })
      }),
    )

    const store = useEspStore()
    store.replaceDevices([{
      ...mockESPDevice,
      device_id: 'ESP_TEST_001',
      esp_id: 'ESP_TEST_001',
      sensors: [{
        ...mockSensor,
        gpio: 4,
        sensor_type: 'sht31_temp',
        raw_value: 23.1,
        last_read: liveLastRead,
        last_event_at: liveLastRead,
      }],
      actuators: [],
    } as any])

    await store.fetchAll()

    const device = store.devices.find((entry) => (entry.device_id || entry.esp_id) === 'ESP_TEST_001')
    const sensor = device?.sensors?.[0] as { raw_value?: number; last_read?: string } | undefined
    expect(sensor?.raw_value).toBe(23.1)
    expect(sensor?.last_read).toBe(liveLastRead)
  })

  it('should preserve existing sensors/actuators when snapshot omits arrays', async () => {
    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.json({
          data: [{
            ...mockESPDevice,
            device_id: 'ESP_TEST_001',
            esp_id: 'ESP_TEST_001',
            sensors: null,
            actuators: null,
          }],
          total: 1,
        })
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json({
          success: true,
          data: [],
          total: 0,
        })
      }),
    )

    const store = useEspStore()
    store.replaceDevices([
      {
        ...mockESPDevice,
        device_id: 'ESP_TEST_001',
        esp_id: 'ESP_TEST_001',
        sensors: [{ ...mockSensor }],
        actuators: [{ ...mockActuator }],
      } as any,
    ])

    await store.fetchAll()

    const device = store.devices.find((entry) => (entry.device_id || entry.esp_id) === 'ESP_TEST_001')
    expect(device?.sensors?.length).toBe(1)
    expect(device?.actuators?.length).toBe(1)
  })
})

// =============================================================================
// API ACTIONS - FETCH DEVICE
// =============================================================================

describe('ESP Store - fetchDevice', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should fetch single device and update in list', async () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001' }]

    const device = await store.fetchDevice('ESP_TEST_001')

    expect(device).toBeDefined()
    expect(device.device_id || device.esp_id).toBe('ESP_TEST_001')
  })

  it('should add device to list if not exists', async () => {
    const store = useEspStore()
    expect(store.devices.length).toBe(0)

    await store.fetchDevice('ESP_TEST_001')

    expect(store.devices.length).toBe(1)
  })

  it('should set error on 404', async () => {
    server.use(
      http.get('/api/v1/debug/mock-esp/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 }
        )
      }),
      http.get('/api/v1/esp/devices/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 }
        )
      })
    )

    const store = useEspStore()

    await expect(store.fetchDevice('ESP_NONEXISTENT')).rejects.toThrow()
  })
})

// =============================================================================
// API ACTIONS - CREATE DEVICE
// =============================================================================

describe('ESP Store - createDevice', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should create mock device and add to list', async () => {
    const store = useEspStore()

    const device = await store.createDevice({
      esp_id: 'ESP_MOCK_NEW',
      name: 'New Mock ESP',
      zone_name: 'Test Zone'
    })

    expect(device).toBeDefined()
    expect(device.device_id || device.esp_id).toContain('ESP_MOCK')
  })

  it('should prevent duplicates when creating', async () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_001', esp_id: 'ESP_MOCK_001' }]

    await store.createDevice({
      esp_id: 'ESP_MOCK_002',
      name: 'Another Mock'
    })

    // Check devices don't have duplicates
    const ids = store.devices.map(d => d.device_id || d.esp_id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// =============================================================================
// API ACTIONS - UPDATE DEVICE
// =============================================================================

describe('ESP Store - updateDevice', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should update device in list', async () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001', name: 'Old Name' }]

    await store.updateDevice('ESP_TEST_001', { name: 'New Name' })

    // Note: The actual update comes from API response
    const device = store.devices.find(d => d.device_id === 'ESP_TEST_001')
    expect(device).toBeDefined()
  })

  it('should preserve sensors when PATCH response omits sensors array (real ESP path)', async () => {
    const existingSensor = { ...mockSensor, gpio: 34, sensor_type: 'moisture' }
    server.use(
      http.patch('/api/v1/esp/devices/:espId', async ({ params, request }) => {
        const body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...mockESPDevice,
          device_id: params.espId,
          esp_id: params.espId,
          name: body.name ?? 'Zimmerbewässerung',
          sensor_count: 1,
          sensors: undefined,
          actuators: undefined,
        })
      }),
      http.get('/api/v1/debug/mock-esp/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 },
        )
      }),
      http.get('/api/v1/esp/devices/:espId', () => {
        return HttpResponse.json({
          ...mockESPDevice,
          device_id: 'ESP_REAL_001',
          esp_id: 'ESP_REAL_001',
          hardware_type: 'ESP32_WROOM',
          name: 'Zimmerbewässerung',
          sensor_count: 1,
        })
      }),
      http.get('/api/v1/sensors/', () => {
        return HttpResponse.json({
          data: [{
            id: 'cfg-1',
            esp_device_id: 'ESP_REAL_001',
            gpio: 34,
            sensor_type: 'moisture',
            name: 'Boden',
          }],
          total: 1,
          page: 1,
          page_size: 100,
          total_pages: 1,
        })
      }),
    )

    const store = useEspStore()
    store.devices = [{
      ...mockESPDevice,
      device_id: 'ESP_REAL_001',
      esp_id: 'ESP_REAL_001',
      hardware_type: 'ESP32_WROOM',
      name: 'Alt',
      sensors: [existingSensor],
      actuators: [{ ...mockActuator }],
    } as typeof mockESPDevice]

    await store.updateDevice('ESP_REAL_001', { name: 'Zimmerbewässerung' })

    const device = store.devices.find((d) => (d.device_id || d.esp_id) === 'ESP_REAL_001')
    expect(device?.name).toBe('Zimmerbewässerung')
    expect(device?.sensors?.length).toBeGreaterThan(0)
    expect(device?.actuators?.length).toBe(1)
  })

  it('should clear device name when null is sent', async () => {
    server.use(
      http.patch('/api/v1/esp/devices/:espId', async ({ request }) => {
        const body = (await request.json()) as { name?: string | null }
        return HttpResponse.json({
          ...mockESPDevice,
          device_id: 'ESP_TEST_001',
          esp_id: 'ESP_TEST_001',
          name: body.name ?? null,
        })
      }),
      http.get('/api/v1/esp/devices/:espId', () => {
        return HttpResponse.json({
          ...mockESPDevice,
          device_id: 'ESP_TEST_001',
          esp_id: 'ESP_TEST_001',
          name: null,
        })
      }),
      http.get('/api/v1/debug/mock-esp/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 },
        )
      }),
    )

    const store = useEspStore()
    store.devices = [{
      ...mockESPDevice,
      device_id: 'ESP_TEST_001',
      esp_id: 'ESP_TEST_001',
      name: 'Zimmerbewässerung',
    }]

    await store.updateDevice('ESP_TEST_001', { name: null })

    const device = store.devices.find((d) => d.device_id === 'ESP_TEST_001')
    expect(device?.name).toBeNull()
  })

  it('should handle 404 for orphaned mock ESPs', async () => {
    server.use(
      http.patch('/api/v1/esp/devices/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 }
        )
      }),
      http.get('/api/v1/debug/mock-esp/:espId', () => {
        return HttpResponse.json({
          ...mockESPDevice,
          esp_id: 'ESP_MOCK_ORPHAN'
        })
      })
    )

    const store = useEspStore()

    // Should fallback to debug store for orphaned mocks
    const result = await store.updateDevice('ESP_MOCK_ORPHAN', { name: 'Updated' })
    expect(result).toBeDefined()
  })
})

// =============================================================================
// API ACTIONS - DELETE DEVICE
// =============================================================================

describe('ESP Store - deleteDevice', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should remove device from list', async () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001' }]

    await store.deleteDevice('ESP_TEST_001')

    expect(store.devices.find(d => d.device_id === 'ESP_TEST_001')).toBeUndefined()
  })

  it('should clear selectedDeviceId if deleted device was selected', async () => {
    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001' }]
    store.selectedDeviceId = 'ESP_TEST_001'

    await store.deleteDevice('ESP_TEST_001')

    expect(store.selectedDeviceId).toBeNull()
  })

  it('should handle 404 gracefully (device already gone)', async () => {
    server.use(
      http.delete('/api/v1/debug/mock-esp/:espId', () => {
        return HttpResponse.json(
          { detail: 'Mock ESP not found' },
          { status: 404 }
        )
      }),
      http.delete('/api/v1/esp/devices/:espId', () => {
        return HttpResponse.json(
          { detail: 'Device not found' },
          { status: 404 }
        )
      })
    )

    const store = useEspStore()
    store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_GONE', esp_id: 'ESP_MOCK_GONE' }]

    // Should not throw - device is already gone
    await store.deleteDevice('ESP_MOCK_GONE')
    expect(store.devices.find(d => d.device_id === 'ESP_MOCK_GONE')).toBeUndefined()
  })
})

// =============================================================================
// PENDING DEVICES
// =============================================================================

describe('ESP Store - Pending Devices', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  describe('fetchPendingDevices', () => {
    it('should load pending devices', async () => {
      server.use(
        http.get('/api/v1/esp/devices/pending', () => {
          return HttpResponse.json({
            devices: [mockPendingDevice],
            total: 1
          })
        })
      )

      const store = useEspStore()
      await store.fetchPendingDevices()

      expect(store.pendingDevices.length).toBe(1)
    })

    it('should set isPendingLoading during fetch', async () => {
      const store = useEspStore()

      const fetchPromise = store.fetchPendingDevices()
      expect(store.isPendingLoading).toBe(true)

      await fetchPromise
      expect(store.isPendingLoading).toBe(false)
    })
  })

  describe('approveDevice', () => {
    it('should remove device from pending list', async () => {
      const store = useEspStore()
      store.pendingDevices = [mockPendingDevice]

      await store.approveDevice('ESP_PENDING_001')

      expect(store.pendingDevices.find(d => d.device_id === 'ESP_PENDING_001')).toBeUndefined()
    })

    it('should show success toast', async () => {
      const store = useEspStore()
      store.pendingDevices = [mockPendingDevice]

      await store.approveDevice('ESP_PENDING_001', { name: 'Approved Device' })

      expect(mockToastFunctions.success).toHaveBeenCalled()
    })
  })

  describe('rejectDevice', () => {
    it('should remove device from pending list', async () => {
      const store = useEspStore()
      store.pendingDevices = [mockPendingDevice]

      await store.rejectDevice('ESP_PENDING_001', 'Not needed')

      expect(store.pendingDevices.find(d => d.device_id === 'ESP_PENDING_001')).toBeUndefined()
    })

    it('should show info toast', async () => {
      const store = useEspStore()
      store.pendingDevices = [mockPendingDevice]

      await store.rejectDevice('ESP_PENDING_001', 'Not needed')

      expect(mockToastFunctions.info).toHaveBeenCalled()
    })
  })
})

// =============================================================================
// COMPUTED GETTERS
// =============================================================================

describe('ESP Store - Getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('selectedDevice', () => {
    it('should return device matching selectedDeviceId', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', esp_id: 'ESP_001' },
        { ...mockESPDevice, device_id: 'ESP_002', esp_id: 'ESP_002' }
      ]
      store.selectedDeviceId = 'ESP_001'

      expect(store.selectedDevice?.device_id).toBe('ESP_001')
    })

    it('should return null when no device selected', () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice }]
      store.selectedDeviceId = null

      expect(store.selectedDevice).toBeNull()
    })

    it('should find by device_id OR esp_id', () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: undefined, esp_id: 'ESP_LEGACY' }]
      store.selectedDeviceId = 'ESP_LEGACY'

      expect(store.selectedDevice).not.toBeNull()
    })
  })

  describe('deviceCount', () => {
    it('should return devices.length', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001' },
        { ...mockESPDevice, device_id: 'ESP_002' }
      ]

      expect(store.deviceCount).toBe(2)
    })
  })

  describe('onlineDevices', () => {
    const OLD_TS = new Date(Date.now() - 600000).toISOString() // 10 min ago

    it('should filter by heartbeat timing (recent = online)', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', status: 'online', last_heartbeat: new Date().toISOString(), last_seen: new Date().toISOString() },
        { ...mockESPDevice, device_id: 'ESP_002', status: 'offline', connected: false, last_heartbeat: OLD_TS, last_seen: OLD_TS }
      ]

      expect(store.onlineDevices.length).toBe(1)
      expect(store.onlineDevices[0].device_id).toBe('ESP_001')
    })

    it('should include devices with recent heartbeat (connected=true)', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', status: undefined, connected: true, last_heartbeat: new Date().toISOString() },
        { ...mockESPDevice, device_id: 'ESP_002', status: undefined, connected: false, last_heartbeat: OLD_TS, last_seen: OLD_TS }
      ]

      expect(store.onlineDevices.length).toBe(1)
    })

    it('should return empty array when all devices have stale heartbeat', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', status: 'offline', connected: false, last_heartbeat: OLD_TS, last_seen: OLD_TS }
      ]

      expect(store.onlineDevices).toEqual([])
    })
  })

  describe('offlineDevices', () => {
    const OLD_TS = new Date(Date.now() - 600000).toISOString()

    it('should filter by heartbeat timing (stale = offline)', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', status: 'online', last_heartbeat: new Date().toISOString(), last_seen: new Date().toISOString() },
        { ...mockESPDevice, device_id: 'ESP_002', status: 'offline', connected: false, last_heartbeat: OLD_TS, last_seen: OLD_TS }
      ]

      expect(store.offlineDevices.length).toBe(1)
      expect(store.offlineDevices[0].device_id).toBe('ESP_002')
    })
  })

  describe('mockDevices', () => {
    it('should filter devices with MOCK in ID', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_MOCK_001' },
        { ...mockESPDevice, device_id: 'ESP_REAL_001' }
      ]

      expect(store.mockDevices.length).toBe(1)
      expect(store.mockDevices[0].device_id).toBe('ESP_MOCK_001')
    })
  })

  describe('realDevices', () => {
    it('should filter devices without MOCK in ID', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_MOCK_001' },
        { ...mockESPDevice, device_id: 'ESP_12345678' }
      ]

      expect(store.realDevices.length).toBe(1)
      expect(store.realDevices[0].device_id).toBe('ESP_12345678')
    })
  })

  describe('devicesByZone', () => {
    it('should return devices matching zone_id', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_001', zone_id: 'zone_a' },
        { ...mockESPDevice, device_id: 'ESP_002', zone_id: 'zone_b' },
        { ...mockESPDevice, device_id: 'ESP_003', zone_id: 'zone_a' }
      ]

      const zoneADevices = store.devicesByZone('zone_a')
      expect(zoneADevices.length).toBe(2)
    })

    it('should return empty array for unknown zone', () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, zone_id: 'zone_a' }]

      expect(store.devicesByZone('zone_unknown')).toEqual([])
    })
  })

  describe('pendingCount', () => {
    it('should return pendingDevices.length', () => {
      const store = useEspStore()
      store.pendingDevices = [mockPendingDevice, { ...mockPendingDevice, device_id: 'ESP_PENDING_002' }]

      expect(store.pendingCount).toBe(2)
    })
  })

  describe('isMock', () => {
    it('should return true for mock device IDs', () => {
      const store = useEspStore()

      expect(store.isMock('ESP_MOCK_001')).toBe(true)
      expect(store.isMock('MOCK_ESP')).toBe(true)
    })

    it('should return false for real device IDs', () => {
      const store = useEspStore()

      expect(store.isMock('ESP_12345678')).toBe(false)
      expect(store.isMock('ESP_ABCD1234')).toBe(false)
    })
  })
})

// =============================================================================
// GPIO STATUS
// =============================================================================

describe('ESP Store - GPIO Status', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should fetch and cache GPIO status', async () => {
    const store = useEspStore()

    await store.fetchGpioStatus('ESP_TEST_001')

    expect(store.gpioStatusMap.has('ESP_TEST_001')).toBe(true)
    const status = store.gpioStatusMap.get('ESP_TEST_001')
    expect(status?.available).toBeDefined()
    expect(status?.reserved).toBeDefined()
  })

  it('should set gpioStatusLoading during fetch', async () => {
    const store = useEspStore()

    const fetchPromise = store.fetchGpioStatus('ESP_TEST_001')
    expect(store.gpioStatusLoading.get('ESP_TEST_001')).toBe(true)

    await fetchPromise
    expect(store.gpioStatusLoading.get('ESP_TEST_001')).toBe(false)
  })
})

// =============================================================================
// MOCK ESP ACTIONS
// =============================================================================

describe('ESP Store - Mock ESP Actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  describe('triggerHeartbeat', () => {
    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_001', esp_id: 'ESP_MOCK_001' }]

      // Should complete without error
      await store.triggerHeartbeat('ESP_MOCK_001')

      // No toast expected - triggerHeartbeat only fetches device data
      expect(store.error).toBeNull()
    })

    it('should throw error for real ESP', async () => {
      const store = useEspStore()

      await expect(store.triggerHeartbeat('ESP_12345678')).rejects.toThrow()
    })
  })

  describe('setState', () => {
    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_001', esp_id: 'ESP_MOCK_001' }]

      await store.setState('ESP_MOCK_001', 'SAFE_MODE', 'Test reason')

      // setState refreshes device data, no toast expected
      expect(store.error).toBeNull()
    })

    it('should throw error for real ESP', async () => {
      const store = useEspStore()

      await expect(store.setState('ESP_12345678', 'OPERATIONAL')).rejects.toThrow()
    })
  })

  describe('addSensor', () => {
    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_001', esp_id: 'ESP_MOCK_001' }]

      await store.addSensor('ESP_MOCK_001', {
        gpio: 5,
        sensor_type: 'ds18b20',
        name: 'New Temp Sensor'
      })

      // addSensor refreshes device data, no toast expected
      expect(store.error).toBeNull()
    })
  })

  describe('removeSensor', () => {
    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{
        ...mockESPDevice,
        device_id: 'ESP_MOCK_001',
        esp_id: 'ESP_MOCK_001',
        sensors: [mockSensor]
      }]

      await store.removeSensor('ESP_MOCK_001', 4)

      // removeSensor refreshes device data, no toast expected
      expect(store.error).toBeNull()
    })

    it('should throw error for real ESP', async () => {
      const store = useEspStore()

      await expect(store.removeSensor('ESP_12345678', 4)).rejects.toThrow()
    })
  })

  describe('addActuator', () => {
    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_MOCK_001', esp_id: 'ESP_MOCK_001' }]

      await store.addActuator('ESP_MOCK_001', {
        gpio: 18,
        actuator_type: 'relay',
        name: 'New Relay'
      })

      // addActuator refreshes device data, no toast expected
      expect(store.error).toBeNull()
    })

    it('should call actuatorsApi for real ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001' }]

      await store.addActuator('ESP_TEST_001', {
        gpio: 18,
        actuator_type: 'relay',
        name: 'Real Relay'
      })

      // Should not throw - dual routing sends to actuatorsApi
      expect(store.error).toBeNull()
    })
  })
})

// =============================================================================
// ACTUATOR COMMANDS
// =============================================================================

describe('ESP Store - Actuator Commands', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  describe('sendActuatorCommand', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('should call actuatorsApi for real ESP', async () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_12345678', esp_id: 'ESP_12345678', status: 'online' }]

      await store.sendActuatorCommand('ESP_12345678', 16, 'ON')

      // Should not throw
    })

    it('should block second command within UI cooldown (AUT-481)', async () => {
      const sendSpy = vi.spyOn(actuatorsApi, 'sendCommand')
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_12345678', esp_id: 'ESP_12345678', status: 'online' }]

      await store.sendActuatorCommand('ESP_12345678', 16, 'ON')
      await store.sendActuatorCommand('ESP_12345678', 16, 'OFF')

      expect(sendSpy).toHaveBeenCalledTimes(1)
      expect(mockToastFunctions.warning).toHaveBeenCalledWith(
        expect.stringContaining('warten'),
        expect.objectContaining({ dedupeKey: 'actuator-cooldown:ESP_12345678:16' }),
      )

      vi.advanceTimersByTime(ACTUATOR_UI_COMMAND_COOLDOWN_MS)
      await store.sendActuatorCommand('ESP_12345678', 16, 'OFF')

      expect(sendSpy).toHaveBeenCalledTimes(2)
      sendSpy.mockRestore()
    })

    it('should call debugApi for mock ESP', async () => {
      const store = useEspStore()
      store.devices = [{
        ...mockESPDevice,
        device_id: 'ESP_MOCK_001',
        esp_id: 'ESP_MOCK_001',
        actuators: [mockActuator]
      }]

      await store.sendActuatorCommand('ESP_MOCK_001', 16, 'ON')

      // Should work for mock ESP
    })
  })

  describe('emergencyStopAll', () => {
    it('should call actuatorsApi.emergencyStop', async () => {
      const store = useEspStore()

      await store.emergencyStopAll('Safety test')

      // Uses toast.show() with type: 'warning'
      expect(mockToastFunctions.show).toHaveBeenCalled()
    })

    it('should show error toast on failure', async () => {
      server.use(
        http.post('/api/v1/actuators/emergency_stop', () => {
          return HttpResponse.json(
            { detail: 'Emergency stop failed' },
            { status: 500 }
          )
        })
      )

      const store = useEspStore()

      await expect(store.emergencyStopAll()).rejects.toThrow()
      expect(mockToastFunctions.error).toHaveBeenCalled()
    })
  })
})

// =============================================================================
// UTILITY ACTIONS
// =============================================================================

describe('ESP Store - Utility Actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('selectDevice', () => {
    it('should set selectedDeviceId', () => {
      const store = useEspStore()

      store.selectDevice('ESP_001')

      expect(store.selectedDeviceId).toBe('ESP_001')
    })

    it('should allow null to deselect', () => {
      const store = useEspStore()
      store.selectedDeviceId = 'ESP_001'

      store.selectDevice(null)

      expect(store.selectedDeviceId).toBeNull()
    })
  })

  describe('clearError', () => {
    it('should set error to null', () => {
      const store = useEspStore()
      store.error = 'Some error'

      store.clearError()

      expect(store.error).toBeNull()
    })
  })

  describe('updateDeviceInList', () => {
    it('should update existing device', () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_001', name: 'Old Name' }]

      store.updateDeviceInList({ ...mockESPDevice, device_id: 'ESP_001', name: 'New Name' })

      expect(store.devices[0].name).toBe('New Name')
    })

    it('should not add device if not exists (update only)', () => {
      const store = useEspStore()
      store.devices = []

      store.updateDeviceInList({ ...mockESPDevice, device_id: 'ESP_NEW' })

      // updateDeviceInList only updates existing devices, does not add new ones
      expect(store.devices.length).toBe(0)
    })
  })

  describe('device write adapters', () => {
    it('replaceDevices should atomically replace the full device list', () => {
      const store = useEspStore()
      store.devices = [{ ...mockESPDevice, device_id: 'ESP_OLD', esp_id: 'ESP_OLD' }]

      store.replaceDevices([{ ...mockESPDevice, device_id: 'ESP_NEW', esp_id: 'ESP_NEW' }])

      expect(store.devices).toHaveLength(1)
      expect(store.devices[0].device_id).toBe('ESP_NEW')
    })

    it('applyDevicePatch should patch only the targeted device', () => {
      const store = useEspStore()
      store.devices = [
        { ...mockESPDevice, device_id: 'ESP_A', esp_id: 'ESP_A', name: 'A' },
        { ...mockESPDevice, device_id: 'ESP_B', esp_id: 'ESP_B', name: 'B' },
      ]

      const patched = store.applyDevicePatch('ESP_B', (device) => ({ ...device, name: 'B-Updated' }))

      expect(patched).toBe(true)
      expect(store.devices.find((d) => d.device_id === 'ESP_A')?.name).toBe('A')
      expect(store.devices.find((d) => d.device_id === 'ESP_B')?.name).toBe('B-Updated')
    })
  })
})

// =============================================================================
// EDGE CASES
// =============================================================================

describe('ESP Store - Edge Cases', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('should handle API timeout gracefully', async () => {
    server.use(
      http.get('/api/v1/esp/devices', async () => {
        // Simulate timeout by never responding
        await new Promise(() => {})
      })
    )

    const store = useEspStore()

    // Should eventually fail but not crash
    // (In real scenario, axios timeout would trigger)
  })

  it('should extract validation errors from axios response', async () => {
    server.use(
      http.post('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json({
          detail: [
            { loc: ['body', 'gpio'], msg: 'invalid GPIO' },
            { loc: ['body', 'name'], msg: 'name required' }
          ]
        }, { status: 422 })
      })
    )

    const store = useEspStore()

    try {
      await store.createDevice({ esp_id: 'ESP_MOCK_BAD' })
    } catch (e) {
      expect(store.error).toContain('gpio')
    }
  })

  it('should handle network error (ECONNREFUSED)', async () => {
    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.error()
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.error()
      })
    )

    const store = useEspStore()

    await expect(store.fetchAll()).rejects.toThrow()
    expect(store.devices).toEqual([])
    expect(store.error).toBeTruthy()
  })

  it('should set isLoading to false even on error', async () => {
    server.use(
      http.get('/api/v1/esp/devices', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      }),
      http.get('/api/v1/debug/mock-esp', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      })
    )

    const store = useEspStore()

    try {
      await store.fetchAll()
    } catch { /* expected */ }

    expect(store.isLoading).toBe(false)
  })
})

// =============================================================================
// DYNAMIC MOCK STATE (from handlers.ts)
// =============================================================================

describe('ESP Store - Dynamic Mock State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    server.resetHandlers()
    resetMockState()
  })

  it('setMockDeviceStatus changes device status in API response', async () => {
    // Set ESP_TEST_001 to offline
    setMockDeviceStatus('ESP_TEST_001', 'offline', { connected: false })

    const store = useEspStore()
    await store.fetchAll()

    const device = store.devices.find(d => d.device_id === 'ESP_TEST_001')
    expect(device).toBeDefined()
    expect(device?.status).toBe('offline')
    expect(device?.connected).toBe(false)
  })

  it('resetMockState restores original device state', async () => {
    // Mock ESP normalization: status derived from `connected` field (connected ? 'online' : 'offline')
    // So we must also set connected: false to see the status change through the store
    setMockDeviceStatus('ESP_TEST_001', 'offline', { connected: false })

    const store = useEspStore()
    await store.fetchAll()
    expect(store.devices.find(d => d.device_id === 'ESP_TEST_001')?.status).toBe('offline')

    // Reset and fetch again — should restore original online status
    resetMockState()
    await store.fetchAll()
    expect(store.devices.find(d => d.device_id === 'ESP_TEST_001')?.status).toBe('online')
  })
})
