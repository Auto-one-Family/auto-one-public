/**
 * MSW Request Handlers
 *
 * Mock API responses for testing.
 * These handlers intercept HTTP requests and return mock responses.
 *
 * API Endpoints Reference: .claude/reference/api/REST_ENDPOINTS.md
 */

import { http, HttpResponse } from 'msw'

// =============================================================================
// Mock Data
// =============================================================================

const mockUser = {
  id: 1,
  username: 'testuser',
  email: 'test@example.com',
  full_name: 'Test User',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

const mockTokens = {
  access_token: 'mock-access-token-12345',
  refresh_token: 'mock-refresh-token-67890',
  token_type: 'bearer',
  expires_in: 3600
}

const mockESPDevice = {
  esp_id: 'ESP_TEST_001',
  device_id: 'ESP_TEST_001',
  name: 'Test ESP',
  zone_id: 'zone_1',
  zone_name: 'Test Zone',
  status: 'online',
  is_mock: true,
  system_state: 'OPERATIONAL',
  heap_free: 128000,
  wifi_rssi: -65,
  uptime: 3600,
  last_heartbeat: new Date().toISOString(),
  last_seen: new Date().toISOString(),
  connected: true,
  sensors: [],
  actuators: [],
  sensor_count: 0,
  actuator_count: 0,
  hardware_type: 'MOCK_ESP32',
  auto_heartbeat: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

const mockSensor = {
  gpio: 4,
  sensor_type: 'ds18b20',
  name: 'Temperature Sensor',
  subzone_id: null,
  raw_value: 23.5,
  processed_value: 23.5,
  unit: '°C',
  quality: 'excellent' as const,
  data_source: 'mock' as const,
  raw_mode: true,
  last_read: new Date().toISOString(),
  read_interval_ms: 30_000,
  operating_mode: 'continuous',
  timeout_seconds: 180,
  is_stale: false,
  stale_reason: undefined,
  is_multi_value: false,
  device_type: null,
  multi_values: null
}

const mockActuator = {
  gpio: 16,
  actuator_type: 'relay',
  name: 'Pump Relay',
  state: false,
  pwm_value: 0,
  emergency_stopped: false,
  last_command: null,
  operating_mode: 'auto' as const,
  runtime_seconds: 0,
  safety_timeout_ms: 3_600_000,
}

const mockPendingDevice = {
  device_id: 'ESP_PENDING_001',
  discovered_at: new Date().toISOString(),
  last_seen: new Date().toISOString(),
  ip_address: '192.168.1.101',
  zone_id: null,
  heap_free: 120000,
  wifi_rssi: -70,
  sensor_count: 0,
  actuator_count: 0,
  heartbeat_count: 1,
  hardware_type: 'ESP32_WROOM'
}

const mockGpioStatus = {
  available: [5, 12, 13, 14, 15, 17, 18, 19, 23, 25, 26, 27, 32, 33],
  reserved: [
    { gpio: 4, owner: 'sensor' as const, component: 'ds18b20', name: 'Temperature', id: 'uuid-1', source: 'database' as const },
    { gpio: 16, owner: 'actuator' as const, component: 'relay', name: 'Pump', id: 'uuid-2', source: 'database' as const }
  ],
  system: [0, 1, 2, 3, 6, 7, 8, 9, 10, 11, 21, 22],
  total_available: 14,
  total_reserved: 2,
  total_system: 12,
  last_esp_report: new Date().toISOString()
}

// Humidity sensor ESP with SHT31
const mockHumiditySensorESP = {
  esp_id: 'ESP_HUMIDITY_001',
  device_id: 'ESP_HUMIDITY_001',
  name: 'Humidity Sensor',
  zone_id: 'zone_1',
  zone_name: 'Test Zone',
  status: 'online',
  is_mock: true,
  system_state: 'OPERATIONAL',
  heap_free: 135000,
  wifi_rssi: -58,
  uptime: 7200,
  last_heartbeat: new Date().toISOString(),
  last_seen: new Date().toISOString(),
  connected: true,
  sensors: [
    {
      gpio: 21,
      sensor_type: 'SHT31',
      name: 'Air Humidity Sensor',
      subzone_id: null,
      raw_value: 38.2,
      processed_value: 38.2,
      unit: '%',
      quality: 'excellent' as const,
      data_source: 'mock' as const,
      raw_mode: true,
      last_read: new Date().toISOString(),
      read_interval_ms: 30_000,
      operating_mode: 'continuous',
      timeout_seconds: 180,
      is_stale: false,
      stale_reason: undefined,
      is_multi_value: true,
      device_type: null,
      multi_values: {
        humidity: { value: 38.2, unit: '%', quality: 'excellent' },
        temperature: { value: 23.1, unit: '°C', quality: 'excellent' }
      }
    }
  ],
  actuators: [],
  sensor_count: 1,
  actuator_count: 0,
  hardware_type: 'MOCK_ESP32',
  auto_heartbeat: true,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z'
}

// Humidifier relay ESP
const mockHumidifierESP = {
  esp_id: 'ESP_HUMIDIFIER_001',
  device_id: 'ESP_HUMIDIFIER_001',
  name: 'Humidifier Controller',
  zone_id: 'zone_1',
  zone_name: 'Test Zone',
  status: 'online',
  is_mock: true,
  system_state: 'OPERATIONAL',
  heap_free: 140000,
  wifi_rssi: -62,
  uptime: 5400,
  last_heartbeat: new Date().toISOString(),
  last_seen: new Date().toISOString(),
  connected: true,
  sensors: [],
  actuators: [
    {
      gpio: 16,
      actuator_type: 'relay',
      name: 'Humidifier Relay',
      state: false,
      pwm_value: 0,
      emergency_stopped: false,
      last_command: null,
      operating_mode: 'auto' as const,
      runtime_seconds: 0,
      safety_timeout_ms: 3_600_000,
    }
  ],
  sensor_count: 0,
  actuator_count: 1,
  hardware_type: 'MOCK_ESP32',
  auto_heartbeat: true,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z'
}

// =============================================================================
// Auth Handlers
// =============================================================================

const authHandlers = [
  // GET /auth/status - Check setup status
  http.get('/api/v1/auth/status', () => {
    return HttpResponse.json({
      setup_required: false,
      user_count: 1
    })
  }),

  // POST /auth/login - Login
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = await request.json() as { username: string; password: string }

    if (body.username === 'testuser' && body.password === 'password123') {
      return HttpResponse.json({
        tokens: mockTokens,
        user: mockUser
      })
    }

    return HttpResponse.json(
      { detail: 'Invalid username or password' },
      { status: 401 }
    )
  }),

  // POST /auth/setup - Initial setup
  http.post('/api/v1/auth/setup', async ({ request }) => {
    const body = await request.json() as {
      username: string
      email: string
      password: string
      full_name?: string
    }

    return HttpResponse.json({
      tokens: mockTokens,
      user: {
        ...mockUser,
        username: body.username,
        email: body.email,
        full_name: body.full_name || null
      }
    })
  }),

  // POST /auth/refresh - Refresh tokens
  // Server returns: { tokens: { access_token, refresh_token, ... } }
  http.post('/api/v1/auth/refresh', async ({ request }) => {
    const body = await request.json() as { refresh_token: string }

    if (body.refresh_token === 'mock-refresh-token-67890') {
      return HttpResponse.json({
        tokens: {
          access_token: 'mock-access-token-renewed',
          refresh_token: 'mock-refresh-token-renewed',
          token_type: 'bearer',
          expires_in: 3600
        }
      })
    }

    return HttpResponse.json(
      { detail: 'Invalid refresh token' },
      { status: 401 }
    )
  }),

  // GET /auth/me - Get current user
  http.get('/api/v1/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (authHeader?.startsWith('Bearer mock-')) {
      return HttpResponse.json(mockUser)
    }

    return HttpResponse.json(
      { detail: 'Not authenticated' },
      { status: 401 }
    )
  }),

  // POST /auth/logout - Logout
  http.post('/api/v1/auth/logout', () => {
    return HttpResponse.json({ message: 'Logged out successfully' })
  })
]

// =============================================================================
// ESP Device Handlers
// =============================================================================

const allMockDevices = [mockESPDevice, mockHumiditySensorESP, mockHumidifierESP]
const mockDevicesById: Record<string, typeof mockESPDevice> = {
  'ESP_TEST_001': mockESPDevice,
  'ESP_HUMIDITY_001': mockHumiditySensorESP,
  'ESP_HUMIDIFIER_001': mockHumidifierESP,
}

const espHandlers = [
  // GET /esp/devices - Get all devices (applies dynamic overrides)
  http.get('/api/v1/esp/devices', () => {
    const devices = allMockDevices.map(d => {
      const id = d.esp_id || d.device_id
      return applyDeviceOverrides(d, id)
    })
    return HttpResponse.json({
      data: devices,
      total: devices.length
    })
  }),

  // GET /esp/devices/pending - Get pending devices
  http.get('/api/v1/esp/devices/pending', () => {
    return HttpResponse.json({
      data: [],
      total: 0
    })
  }),

  // GET /esp/devices/:id - Get single device (applies dynamic overrides)
  http.get('/api/v1/esp/devices/:espId', ({ params }) => {
    const { espId } = params
    const baseDevice = mockDevicesById[espId as string]

    if (baseDevice) {
      const device = applyDeviceOverrides(baseDevice, espId as string)
      return HttpResponse.json(device)
    }

    return HttpResponse.json(
      { detail: 'Device not found' },
      { status: 404 }
    )
  }),

  // PATCH /esp/devices/:id - Update device
  http.patch('/api/v1/esp/devices/:espId', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as Record<string, unknown>
    const device = mockDevicesById[espId as string]

    if (device) {
      return HttpResponse.json({
        ...device,
        ...body
      })
    }

    return HttpResponse.json(
      { detail: 'Device not found' },
      { status: 404 }
    )
  }),

  // DELETE /esp/devices/:id - Delete device
  http.delete('/api/v1/esp/devices/:espId', ({ params }) => {
    const { espId } = params

    if (mockDevicesById[espId as string] || (espId as string).startsWith('ESP_MOCK')) {
      return HttpResponse.json({ message: 'Device deleted' })
    }

    return HttpResponse.json(
      { detail: 'Device not found' },
      { status: 404 }
    )
  }),

  // POST /esp/devices/:id/approve - Approve pending device
  http.post('/api/v1/esp/devices/:espId/approve', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as { name?: string; zone_id?: string; zone_name?: string }

    return HttpResponse.json({
      success: true,
      message: 'Device approved',
      device_id: espId,
      status: 'approved',
      approved_by: 'testuser',
      approved_at: new Date().toISOString(),
      name: body.name,
      zone_id: body.zone_id
    })
  }),

  // POST /esp/devices/:id/reject - Reject pending device
  http.post('/api/v1/esp/devices/:espId/reject', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as { reason: string }

    return HttpResponse.json({
      success: true,
      message: 'Device rejected',
      device_id: espId,
      status: 'rejected',
      rejection_reason: body.reason,
      cooldown_until: new Date(Date.now() + 5 * 60 * 1000).toISOString()
    })
  }),

  // GET /esp/devices/:id/gpio-status - Get GPIO status
  http.get('/api/v1/esp/devices/:espId/gpio-status', () => {
    return HttpResponse.json(mockGpioStatus)
  })
]

// =============================================================================
// Sensor Handlers
// =============================================================================

const sensorHandlers = [
  // GET /sensors/data - Get sensor data
  http.get('/api/v1/sensors/data', ({ request }) => {
    const url = new URL(request.url)
    const espId = url.searchParams.get('esp_id')
    const gpio = url.searchParams.get('gpio')

    return HttpResponse.json({
      success: true,
      esp_id: espId,
      gpio: Number(gpio),
      sensor_type: 'ds18b20',
      readings: [
        {
          timestamp: new Date().toISOString(),
          raw_value: 23.5,
          processed_value: 23.5,
          unit: '°C',
          quality: 'excellent'
        }
      ],
      count: 1
    })
  }),

  // PUT /sensors/:espId/:gpio - Create or update sensor
  http.put('/api/v1/sensors/:espId/:gpio', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as {
      sensor_type: string
      name?: string
      subzone_id?: string
    }

    return HttpResponse.json({
      id: 'sensor-uuid-1234',
      esp_id: espId,
      gpio: Number(gpio),
      sensor_type: body.sensor_type,
      name: body.name || 'New Sensor',
      subzone_id: body.subzone_id || null,
      raw_value: 0,
      processed_value: 0,
      quality: 'excellent',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  })
]

// =============================================================================
// Actuator Handlers
// =============================================================================

const actuatorHandlers = [
  // POST /v1/actuators/:espId/:gpio - Create or update actuator config (Real-ESP)
  http.post('/api/v1/actuators/:espId/:gpio', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as Record<string, unknown>

    return HttpResponse.json({
      id: 1,
      esp_id: espId,
      gpio: Number(gpio),
      actuator_type: body.actuator_type || 'relay',
      name: body.name || null,
      enabled: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),

  // POST /v1/actuators/:espId/:gpio/command - Send actuator command
  http.post('/api/v1/actuators/:espId/:gpio/command', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as {
      command: string
      value?: number
    }

    return HttpResponse.json({
      success: true,
      esp_id: espId,
      gpio: Number(gpio),
      command: body.command,
      value: body.value || 0,
      correlation_id: '00000000-0000-4000-8000-000000000099',
      command_sent: true,
      acknowledged: false,
      safety_warnings: []
    })
  }),

  // POST /v1/actuators/emergency_stop - Emergency stop all actuators (note: underscore not hyphen)
  http.post('/api/v1/actuators/emergency_stop', async ({ request }) => {
    const body = await request.json() as { reason?: string; esp_id?: string; gpio?: number }

    return HttpResponse.json({
      success: true,
      message: 'Emergency stop executed',
      reason: body.reason || 'manual',
      devices_stopped: 2,
      actuators_stopped: 5,
      timestamp: new Date().toISOString(),
      details: []
    })
  })
]

// =============================================================================
// OneWire Handlers
// =============================================================================

const oneWireHandlers = [
  // POST /onewire/:espId/scan - Scan OneWire bus
  http.post('/api/v1/onewire/:espId/scan', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as { pin?: number }

    return HttpResponse.json({
      success: true,
      esp_id: espId,
      pin: body.pin || 4,
      devices: [
        { rom_code: '28FF1234567890AB', family: 0x28, is_configured: false },
        { rom_code: '28FF0987654321CD', family: 0x28, is_configured: true }
      ],
      found_count: 2,
      scan_time_ms: 150
    })
  })
]

// =============================================================================
// Zone Handlers
// =============================================================================

const zoneHandlers = [
  // POST /zone/devices/:id/assign - Assign device to zone
  http.post('/api/v1/zone/devices/:espId/assign', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as { zone_id: string; zone_name?: string }

    return HttpResponse.json({
      success: true,
      message: 'Zone assigned successfully',
      device_id: espId,
      zone_id: body.zone_id,
      zone_name: body.zone_name || body.zone_id,
      mqtt_topic: `kaiser/god/esp/${espId}/config/zone`,
      mqtt_sent: true
    })
  }),

  // POST /zone/devices/:id/remove - Remove device from zone
  http.post('/api/v1/zone/devices/:espId/remove', ({ params }) => {
    const { espId } = params

    return HttpResponse.json({
      success: true,
      message: 'Zone removed successfully',
      device_id: espId,
      mqtt_topic: `kaiser/god/esp/${espId}/config/zone`,
      mqtt_sent: true
    })
  })
]

// =============================================================================
// Logic Handlers
// =============================================================================

const mockLogicRule = {
  id: 'rule-001',
  name: 'Temperature Fan Control',
  description: 'Turn on fan when temperature exceeds 25°C',
  enabled: true,
  conditions: [
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_TEST_001',
      gpio: 4,
      sensor_type: 'ds18b20',
      operator: '>',
      value: 25
    }
  ],
  logic_operator: 'AND',
  actions: [
    {
      type: 'actuator_command',
      esp_id: 'ESP_TEST_002',
      gpio: 16,
      command: 'ON'
    }
  ],
  priority: 1,
  cooldown_seconds: 60,
  max_executions_per_hour: 10,
  last_triggered: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

// Humidity → Humidifier logic rule
const mockHumidityRule = {
  id: 'rule-002',
  name: 'Humidity Humidifier Control',
  description: 'Turn on humidifier when air humidity drops below 40%',
  enabled: true,
  conditions: [
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_HUMIDITY_001',
      gpio: 21,
      sensor_type: 'SHT31',
      operator: '<',
      value: 40
    }
  ],
  logic_operator: 'AND',
  actions: [
    {
      type: 'actuator_command',
      esp_id: 'ESP_HUMIDIFIER_001',
      gpio: 16,
      command: 'ON',
      duration: 300
    }
  ],
  priority: 2,
  cooldown_seconds: 120,
  max_executions_per_hour: 6,
  last_triggered: null,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z'
}

// AND rule: Temperature > 30°C AND Humidity < 40% → Humidifier ON
const mockAndRule = {
  id: 'rule-003',
  name: 'Heat & Dry Protection',
  description: 'Turn on humidifier when temperature is high AND humidity is low',
  enabled: true,
  conditions: [
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_TEST_001',
      gpio: 4,
      sensor_type: 'ds18b20',
      operator: '>',
      value: 30
    },
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_HUMIDITY_001',
      gpio: 21,
      sensor_type: 'SHT31',
      operator: '<',
      value: 40
    }
  ],
  logic_operator: 'AND',
  actions: [
    {
      type: 'actuator_command',
      esp_id: 'ESP_HUMIDIFIER_001',
      gpio: 16,
      command: 'ON',
      duration: 600
    }
  ],
  priority: 3,
  cooldown_seconds: 180,
  max_executions_per_hour: 4,
  last_triggered: null,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z'
}

// OR rule: Soil moisture low OR manual trigger → Irrigation ON
const mockOrRule = {
  id: 'rule-004',
  name: 'Irrigation Fallback',
  description: 'Water plants when soil is dry OR manual trigger received',
  enabled: true,
  conditions: [
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_TEST_001',
      gpio: 4,
      sensor_type: 'ds18b20',
      operator: '<',
      value: 20
    },
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_HUMIDITY_001',
      gpio: 21,
      sensor_type: 'SHT31',
      operator: '<',
      value: 25
    }
  ],
  logic_operator: 'OR',
  actions: [
    {
      type: 'actuator_command',
      esp_id: 'ESP_HUMIDIFIER_001',
      gpio: 16,
      command: 'ON',
      duration: 120
    }
  ],
  priority: 1,
  cooldown_seconds: 300,
  max_executions_per_hour: 3,
  last_triggered: null,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z'
}

// Multi-Action rule: Temperature > 35°C → Fan ON + Alert
const mockMultiActionRule = {
  id: 'rule-005',
  name: 'Heat Emergency Multi-Action',
  description: 'Emergency response: activate fan and send alert when critically hot',
  enabled: false,
  conditions: [
    {
      type: 'sensor_threshold',
      esp_id: 'ESP_TEST_001',
      gpio: 4,
      sensor_type: 'ds18b20',
      operator: '>',
      value: 35
    }
  ],
  logic_operator: 'AND',
  actions: [
    {
      type: 'actuator_command',
      esp_id: 'ESP_TEST_002',
      gpio: 16,
      command: 'ON'
    },
    {
      type: 'notification',
      channel: 'websocket',
      target: 'dashboard',
      message_template: 'CRITICAL: Temperature {value}°C exceeds 35°C!'
    }
  ],
  priority: 10,
  cooldown_seconds: 60,
  max_executions_per_hour: 20,
  last_triggered: null,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z'
}

const allMockRules = [mockLogicRule, mockHumidityRule, mockAndRule, mockOrRule, mockMultiActionRule]
const mockRulesById: Record<string, typeof mockLogicRule> = {
  'rule-001': mockLogicRule,
  'rule-002': mockHumidityRule,
  'rule-003': mockAndRule as typeof mockLogicRule,
  'rule-004': mockOrRule as typeof mockLogicRule,
  'rule-005': mockMultiActionRule as typeof mockLogicRule,
}

// =============================================================================
// Dynamic Mock State (for test manipulation)
// =============================================================================

/**
 * Mutable state map that tests can manipulate to simulate device status changes.
 * MSW handlers read from this map, so tests can do:
 *   setMockDeviceStatus('ESP_TEST_001', 'offline')
 *   await store.fetchAll()
 *   expect(store.devices[0].status).toBe('offline')
 */
const mockDeviceState = new Map<string, Partial<typeof mockESPDevice>>()

/** Set mock device overrides. Handler merges these into the base device. */
function setMockDeviceStatus(espId: string, status: string, extras?: Record<string, unknown>): void {
  mockDeviceState.set(espId, { status, ...extras } as Partial<typeof mockESPDevice>)
}

/** Reset all dynamic mock state. Call in afterEach. */
function resetMockState(): void {
  mockDeviceState.clear()
}

/** Apply dynamic overrides to a device */
function applyDeviceOverrides<T extends Record<string, unknown>>(device: T, espId: string): T {
  const overrides = mockDeviceState.get(espId)
  if (overrides) {
    return { ...device, ...overrides }
  }
  return device
}

const logicHandlers = [
  // GET /logic/rules - Get all rules
  http.get('/api/v1/logic/rules', () => {
    return HttpResponse.json({
      success: true,
      data: allMockRules,
      pagination: {
        page: 1,
        page_size: 50,
        total_items: allMockRules.length,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      }
    })
  }),

  // POST /logic/rules - Create a new rule
  http.post('/api/v1/logic/rules', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    const newRule = {
      id: `rule-${Date.now()}`,
      ...body,
      priority: (body.priority as number) ?? 1,
      cooldown_seconds: (body.cooldown_seconds as number) ?? 60,
      max_executions_per_hour: (body.max_executions_per_hour as number) ?? 10,
      last_triggered: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(newRule, { status: 201 })
  }),

  // GET /logic/rules/:id - Get single rule
  http.get('/api/v1/logic/rules/:ruleId', ({ params }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      return HttpResponse.json(rule)
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  }),

  // PUT /logic/rules/:id - Update a rule
  http.put('/api/v1/logic/rules/:ruleId', async ({ params, request }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      const body = await request.json() as Record<string, unknown>
      return HttpResponse.json({
        ...rule,
        ...body,
        updated_at: new Date().toISOString(),
      })
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  }),

  // PATCH /logic/rules/:id - Partial update a rule
  http.patch('/api/v1/logic/rules/:ruleId', async ({ params, request }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      const body = await request.json() as Record<string, unknown>
      return HttpResponse.json({
        ...rule,
        ...body,
        updated_at: new Date().toISOString(),
      })
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  }),

  // DELETE /logic/rules/:id - Delete a rule
  http.delete('/api/v1/logic/rules/:ruleId', ({ params }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      return new HttpResponse(null, { status: 204 })
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  }),

  // POST /logic/rules/:id/toggle - Toggle rule
  http.post('/api/v1/logic/rules/:ruleId/toggle', ({ params }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      return HttpResponse.json({
        success: true,
        message: 'Rule toggled',
        rule_id: ruleId,
        rule_name: rule.name,
        enabled: !rule.enabled,
        previous_state: rule.enabled,
      })
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  }),

  // POST /logic/rules/:id/test - Test rule
  http.post('/api/v1/logic/rules/:ruleId/test', ({ params }) => {
    const { ruleId } = params
    const rule = mockRulesById[ruleId as string]

    if (rule) {
      // Simulate evaluation based on rule conditions
      const conditionsResult = ruleId === 'rule-002'
        ? mockHumiditySensorESP.sensors[0].raw_value < 40
        : true

      return HttpResponse.json({
        success: true,
        rule_id: ruleId,
        rule_name: rule.name,
        would_trigger: conditionsResult,
        condition_results: rule.conditions.map((cond, idx) => ({
          condition_index: idx,
          condition_type: cond.type,
          result: conditionsResult,
          details: `Evaluated condition ${idx}`,
          actual_value: ruleId === 'rule-002' ? 38.2 : 26.5,
        })),
        action_results: rule.actions.map((action, idx) => ({
          action_index: idx,
          action_type: action.type,
          would_execute: conditionsResult,
          details: `Would execute action ${idx}`,
          dry_run: true,
        })),
        dry_run: true,
      })
    }

    return HttpResponse.json(
      { detail: 'Rule not found' },
      { status: 404 }
    )
  })
]

// =============================================================================
// Database Handlers (Debug DB Explorer)
// =============================================================================

/** Inline type for mock table schema */
interface TableSchemaForMock {
  table_name: string
  columns: Array<{
    name: string
    type: string
    nullable: boolean
    primary_key: boolean
    foreign_key?: string | null
  }>
  row_count: number
  primary_key: string
}

const mockTableSchema: TableSchemaForMock = {
  table_name: 'esp_devices',
  columns: [
    { name: 'id', type: 'uuid', nullable: false, primary_key: true },
    { name: 'esp_id', type: 'string', nullable: false, primary_key: false },
    { name: 'name', type: 'string', nullable: true, primary_key: false },
    { name: 'status', type: 'string', nullable: false, primary_key: false },
    { name: 'created_at', type: 'datetime', nullable: false, primary_key: false }
  ],
  row_count: 5,
  primary_key: 'id'
}

const mockTableData = {
  success: true,
  table_name: 'esp_devices',
  data: [
    { id: 'uuid-1', esp_id: 'ESP_TEST_001', name: 'Test ESP', status: 'online', created_at: '2026-01-01T00:00:00Z' },
    { id: 'uuid-2', esp_id: 'ESP_TEST_002', name: 'Second ESP', status: 'offline', created_at: '2026-01-02T00:00:00Z' }
  ],
  total_count: 2,
  page: 1,
  page_size: 50,
  total_pages: 1
}

const databaseHandlers = [
  // GET /debug/db/tables - List all tables
  http.get('/api/v1/debug/db/tables', () => {
    return HttpResponse.json({
      success: true,
      tables: [mockTableSchema]
    })
  }),

  // GET /debug/db/:table/schema - Get table schema
  http.get('/api/v1/debug/db/:table/schema', ({ params }) => {
    const { table } = params

    if (table === 'esp_devices') {
      return HttpResponse.json(mockTableSchema)
    }

    return HttpResponse.json(
      { detail: `Table '${table}' not found` },
      { status: 404 }
    )
  }),

  // GET /debug/db/:table - Query table data
  http.get('/api/v1/debug/db/:table', ({ params, request }) => {
    const { table } = params
    const url = new URL(request.url)
    const page = Number(url.searchParams.get('page')) || 1
    const pageSize = Number(url.searchParams.get('page_size')) || 50

    if (table === 'esp_devices') {
      return HttpResponse.json({
        ...mockTableData,
        page,
        page_size: pageSize
      })
    }

    return HttpResponse.json(
      { detail: `Table '${table}' not found` },
      { status: 404 }
    )
  }),

  // GET /debug/db/:table/:recordId - Get single record
  http.get('/api/v1/debug/db/:table/:recordId', ({ params }) => {
    const { table, recordId } = params

    if (table === 'esp_devices' && recordId === 'uuid-1') {
      return HttpResponse.json({
        success: true,
        table_name: 'esp_devices',
        record: mockTableData.data[0]
      })
    }

    return HttpResponse.json(
      { detail: 'Record not found' },
      { status: 404 }
    )
  })
]

// =============================================================================
// Audit Handlers
// =============================================================================

const auditHandlers = [
  // GET /audit/statistics - Get audit statistics
  http.get('/api/v1/audit/statistics', () => {
    return HttpResponse.json({
      total_events: 100,
      events_by_type: {
        sensor_data: 50,
        actuator_command: 30,
        system_event: 20
      },
      problems: []
    })
  })
]

// =============================================================================
// Debug/Mock ESP Handlers
// =============================================================================

const debugHandlers = [
  // POST /debug/mock-esp - Create mock ESP
  http.post('/api/v1/debug/mock-esp', async ({ request }) => {
    const body = await request.json() as {
      esp_id?: string
      name?: string
      zone_id?: string
      zone_name?: string
      auto_heartbeat?: boolean
    }

    const espId = body.esp_id || `ESP_MOCK_${Date.now()}`

    return HttpResponse.json({
      esp_id: espId,
      device_id: espId,
      name: body.name || null,
      zone_id: body.zone_id || null,
      zone_name: body.zone_name || null,
      status: 'online',
      system_state: 'OPERATIONAL',
      connected: true,
      auto_heartbeat: body.auto_heartbeat ?? true,
      heap_free: 128000,
      wifi_rssi: -65,
      uptime: 0,
      sensors: [],
      actuators: [],
      created_at: new Date().toISOString()
    })
  }),

  // GET /debug/mock-esp - List all mock ESPs (with dynamic state overrides)
  http.get('/api/v1/debug/mock-esp', () => {
    const device = applyDeviceOverrides(mockESPDevice, mockESPDevice.device_id)
    return HttpResponse.json({
      success: true,
      data: [device],
      total: 1
    })
  }),

  // GET /debug/mock-esp/:id - Get single mock ESP (with dynamic state overrides)
  http.get('/api/v1/debug/mock-esp/:espId', ({ params }) => {
    const { espId } = params

    if (espId === 'ESP_TEST_001' || (espId as string).startsWith('ESP_MOCK')) {
      const device = applyDeviceOverrides({
        ...mockESPDevice,
        esp_id: espId,
        device_id: espId
      }, espId as string)
      return HttpResponse.json(device)
    }

    return HttpResponse.json(
      { detail: 'Mock ESP not found' },
      { status: 404 }
    )
  }),

  // DELETE /debug/mock-esp/:id - Delete mock ESP
  http.delete('/api/v1/debug/mock-esp/:espId', ({ params }) => {
    const { espId } = params

    if (espId === 'ESP_NOT_FOUND') {
      return HttpResponse.json(
        { detail: 'Mock ESP not found' },
        { status: 404 }
      )
    }

    return HttpResponse.json({
      message: `Mock ESP ${espId} deleted`
    })
  }),

  // POST /debug/mock-esp/:id/sensors - Add sensor to mock ESP
  http.post('/api/v1/debug/mock-esp/:espId/sensors', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as {
      gpio: number
      sensor_type: string
      name?: string
    }

    return HttpResponse.json({
      success: true,
      message: 'Sensor added',
      esp_id: espId,
      sensor: {
        gpio: body.gpio,
        sensor_type: body.sensor_type,
        name: body.name || 'New Sensor',
        raw_value: 0,
        quality: 'excellent'
      }
    })
  }),

  // DELETE /debug/mock-esp/:id/sensors/:gpio - Remove sensor
  http.delete('/api/v1/debug/mock-esp/:espId/sensors/:gpio', ({ params }) => {
    const { espId, gpio } = params

    return HttpResponse.json({
      success: true,
      message: `Sensor on GPIO ${gpio} removed from ${espId}`
    })
  }),

  // POST /debug/mock-esp/:id/actuators - Add actuator to mock ESP
  http.post('/api/v1/debug/mock-esp/:espId/actuators', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as {
      gpio: number
      actuator_type: string
      name?: string
    }

    return HttpResponse.json({
      success: true,
      message: 'Actuator added',
      esp_id: espId,
      actuator: {
        gpio: body.gpio,
        actuator_type: body.actuator_type,
        name: body.name || 'New Actuator',
        state: false,
        pwm_value: 0
      }
    })
  }),

  // POST /debug/mock-esp/:id/state - Set mock ESP state
  http.post('/api/v1/debug/mock-esp/:espId/state', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as {
      state: string
      reason?: string
    }

    return HttpResponse.json({
      success: true,
      message: `State changed to ${body.state}`,
      esp_id: espId,
      system_state: body.state,
      reason: body.reason
    })
  }),

  // POST /debug/mock-esp/:id/heartbeat - Trigger heartbeat
  http.post('/api/v1/debug/mock-esp/:espId/heartbeat', ({ params }) => {
    const { espId } = params

    return HttpResponse.json({
      success: true,
      message: 'Heartbeat sent',
      esp_id: espId,
      timestamp: new Date().toISOString()
    })
  }),

  // POST /debug/mock-esp/:id/sensors/:gpio/value - Set sensor value
  http.post('/api/v1/debug/mock-esp/:espId/sensors/:gpio/value', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as {
      raw_value: number
      quality?: string
      publish?: boolean
    }

    return HttpResponse.json({
      success: true,
      message: 'Sensor value updated',
      esp_id: espId,
      gpio: Number(gpio),
      raw_value: body.raw_value,
      quality: body.quality || 'excellent'
    })
  }),

  // POST /debug/mock-esp/:id/actuators/:gpio/state - Set actuator state
  http.post('/api/v1/debug/mock-esp/:espId/actuators/:gpio/state', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as {
      state: boolean
      pwm_value?: number
    }

    return HttpResponse.json({
      success: true,
      message: 'Actuator state updated',
      esp_id: espId,
      gpio: Number(gpio),
      state: body.state,
      pwm_value: body.pwm_value || 0
    })
  }),

  // POST /debug/mock-esp/:id/emergency-stop - Emergency stop for mock ESP
  http.post('/api/v1/debug/mock-esp/:espId/emergency-stop', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as { reason?: string }

    return HttpResponse.json({
      success: true,
      message: 'Emergency stop executed',
      esp_id: espId,
      reason: body.reason || 'manual'
    })
  }),

  // POST /debug/mock-esp/:id/clear-emergency - Clear emergency for mock ESP
  http.post('/api/v1/debug/mock-esp/:espId/clear-emergency', ({ params }) => {
    const { espId } = params

    return HttpResponse.json({
      success: true,
      message: 'Emergency cleared',
      esp_id: espId
    })
  }),

  // POST /debug/mock-esp/:id/auto-heartbeat - Set auto-heartbeat
  http.post('/api/v1/debug/mock-esp/:espId/auto-heartbeat', async ({ params, request }) => {
    const { espId } = params
    const body = await request.json() as {
      enabled: boolean
      interval_seconds?: number
    }

    return HttpResponse.json({
      success: true,
      message: body.enabled ? 'Auto-heartbeat enabled' : 'Auto-heartbeat disabled',
      esp_id: espId,
      auto_heartbeat: body.enabled,
      interval_seconds: body.interval_seconds || 30
    })
  }),

  // POST /debug/mock-esp/:id/actuators/:gpio - Set actuator state (sendActuatorCommand for Mock)
  http.post('/api/v1/debug/mock-esp/:espId/actuators/:gpio', async ({ params, request }) => {
    const { espId, gpio } = params
    const body = await request.json() as {
      state?: boolean
      pwm_value?: number
      command?: string
      publish?: boolean
    }

    return HttpResponse.json({
      success: true,
      message: 'Actuator command executed',
      esp_id: espId,
      gpio: Number(gpio),
      state: body.state,
      pwm_value: body.pwm_value || 0
    })
  })
]

// =============================================================================
// Plugin Handlers
// =============================================================================

const mockPlugin = {
  plugin_id: 'health_check',
  display_name: 'Health Check',
  description: 'System health validation',
  category: 'monitoring',
  is_enabled: true,
  config: { include_containers: true, alert_on_degraded: false },
  config_schema: {
    include_containers: { type: 'boolean', default: true, label: 'Container prüfen' },
    alert_on_degraded: { type: 'boolean', default: false, label: 'Alert bei Degraded' },
  },
  capabilities: ['validate', 'monitor'],
  last_execution: {
    id: 'exec-001',
    plugin_id: 'health_check',
    started_at: '2026-03-01T10:00:00Z',
    finished_at: '2026-03-01T10:00:05Z',
    status: 'success',
    triggered_by: 'manual',
    result: { success: true, summary: 'All checks passed' },
    error_message: null,
    duration_seconds: 5.0,
  },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

const mockPluginDisabled = {
  plugin_id: 'system_cleanup',
  display_name: 'System Cleanup',
  description: 'Maintenance and cleanup operations',
  category: 'maintenance',
  is_enabled: false,
  config: { max_log_age_days: 30, dry_run: false },
  config_schema: {
    max_log_age_days: { type: 'integer', default: 30, label: 'Max Log-Alter (Tage)' },
    dry_run: { type: 'boolean', default: false, label: 'Nur simulieren' },
  },
  capabilities: ['cleanup', 'validate'],
  last_execution: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const mockPluginWithSelect = {
  plugin_id: 'esp_configurator',
  display_name: 'ESP Configurator',
  description: 'Autonomous ESP32 configuration',
  category: 'automation',
  is_enabled: true,
  config: { device_mode: 'mock', auto_heartbeat: true },
  config_schema: {
    device_mode: { type: 'select', options: ['mock', 'real', 'hybrid'], default: 'mock', label: 'Geräte-Modus' },
    auto_heartbeat: { type: 'boolean', default: true, label: 'Auto-Heartbeat' },
  },
  capabilities: ['configure', 'validate'],
  last_execution: {
    id: 'exec-002',
    plugin_id: 'esp_configurator',
    started_at: '2026-03-01T11:00:00Z',
    finished_at: '2026-03-01T11:00:10Z',
    status: 'error',
    triggered_by: 'logic_rule',
    result: null,
    error_message: 'Connection timeout',
    duration_seconds: 10.0,
  },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
}

const allMockPlugins = [mockPlugin, mockPluginDisabled, mockPluginWithSelect]

const mockExecution = {
  id: 'exec-new-001',
  plugin_id: 'health_check',
  started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(),
  status: 'success',
  triggered_by: 'manual',
  result: { success: true, summary: 'All checks passed' },
  error_message: null,
  duration_seconds: 3.2,
}

const pluginHandlers = [
  // GET /plugins - List all plugins
  http.get('/api/v1/plugins', () => {
    return HttpResponse.json(allMockPlugins)
  }),

  // GET /plugins/:id - Get plugin detail
  http.get('/api/v1/plugins/:pluginId', ({ params }) => {
    const { pluginId } = params
    const plugin = allMockPlugins.find(p => p.plugin_id === pluginId)

    if (plugin) {
      return HttpResponse.json({
        ...plugin,
        recent_executions: plugin.last_execution ? [plugin.last_execution] : [],
      })
    }

    return HttpResponse.json({ detail: 'Plugin not found' }, { status: 404 })
  }),

  // POST /plugins/:id/execute - Execute plugin
  http.post('/api/v1/plugins/:pluginId/execute', ({ params }) => {
    const { pluginId } = params
    const plugin = allMockPlugins.find(p => p.plugin_id === pluginId)

    if (!plugin) {
      return HttpResponse.json({ detail: 'Plugin not found' }, { status: 404 })
    }
    if (!plugin.is_enabled) {
      return HttpResponse.json({ detail: 'Plugin is disabled' }, { status: 400 })
    }

    return HttpResponse.json({ ...mockExecution, plugin_id: pluginId })
  }),

  // PUT /plugins/:id/config - Update config
  http.put('/api/v1/plugins/:pluginId/config', async ({ params, request }) => {
    const { pluginId } = params
    const body = await request.json() as { config: Record<string, unknown> }

    return HttpResponse.json({
      plugin_id: pluginId,
      config: body.config,
      updated_at: new Date().toISOString(),
    })
  }),

  // POST /plugins/:id/enable - Enable plugin
  http.post('/api/v1/plugins/:pluginId/enable', ({ params }) => {
    const { pluginId } = params
    return HttpResponse.json({ plugin_id: pluginId, is_enabled: true })
  }),

  // POST /plugins/:id/disable - Disable plugin
  http.post('/api/v1/plugins/:pluginId/disable', ({ params }) => {
    const { pluginId } = params
    return HttpResponse.json({ plugin_id: pluginId, is_enabled: false })
  }),

  // GET /plugins/:id/history - Execution history
  http.get('/api/v1/plugins/:pluginId/history', ({ params }) => {
    const { pluginId } = params
    const plugin = allMockPlugins.find(p => p.plugin_id === pluginId)

    if (!plugin) {
      return HttpResponse.json({ detail: 'Plugin not found' }, { status: 404 })
    }

    return HttpResponse.json(
      plugin.last_execution ? [plugin.last_execution] : [],
    )
  }),
]

// =============================================================================
// Export All Handlers
// =============================================================================

export const handlers = [
  ...authHandlers,
  ...espHandlers,
  ...sensorHandlers,
  ...actuatorHandlers,
  ...oneWireHandlers,
  ...zoneHandlers,
  ...logicHandlers,
  ...databaseHandlers,
  ...auditHandlers,
  ...debugHandlers,
  ...pluginHandlers,
]

// =============================================================================
// Export Mock Data (for use in tests)
// =============================================================================

export {
  mockUser,
  mockTokens,
  mockESPDevice,
  mockSensor,
  mockActuator,
  mockPendingDevice,
  mockGpioStatus,
  mockLogicRule,
  mockHumidityRule,
  mockAndRule,
  mockOrRule,
  mockMultiActionRule,
  mockHumiditySensorESP,
  mockHumidifierESP,
  mockTableSchema,
  mockTableData,
  // Dynamic state helpers
  mockDeviceState,
  setMockDeviceStatus,
  resetMockState,
  // Plugin mock data
  mockPlugin,
  mockPluginDisabled,
  mockPluginWithSelect,
}
