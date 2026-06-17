/**
 * Logic Store Unit Tests
 *
 * Tests for Logic Store state management, API integration,
 * connection extraction, and WebSocket event handling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// =============================================================================
// MOCK WEBSOCKET SERVICE
// =============================================================================

// Mock functions must be created inside factory to avoid hoisting issues
vi.mock('@/services/websocket', () => {
  const mockSubscribe = vi.fn().mockReturnValue('sub-logic-123')
  const mockUnsubscribe = vi.fn()

  return {
    websocketService: {
      subscribe: mockSubscribe,
      unsubscribe: mockUnsubscribe,
    },
    WebSocketMessage: {},
  }
})

// =============================================================================
// MOCK LOGGER
// =============================================================================

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

// Mock esp store for getRulesForZone (logic store depends on devices + zone_id)
const mockEspDevices: { device_id?: string; esp_id?: string; zone_id?: string }[] = []
vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    get devices() {
      return mockEspDevices
    },
    getDeviceId: (d: { device_id?: string; esp_id?: string }) => d.device_id || d.esp_id || '',
  }),
}))

// Import after mocks are set up
import { beforeAll, afterAll, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLogicStore } from '@/shared/stores/logic.store'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import { mockLogicRule } from '../../mocks/handlers'
import { websocketService } from '@/services/websocket'

// MSW Server Lifecycle
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// INITIAL STATE
// =============================================================================

describe('Logic Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has empty rules array on initialization', () => {
    const store = useLogicStore()
    expect(store.rules).toEqual([])
  })

  it('has isLoading false initially', () => {
    const store = useLogicStore()
    expect(store.isLoading).toBe(false)
  })

  it('has null error initially', () => {
    const store = useLogicStore()
    expect(store.error).toBeNull()
  })

  it('has empty activeExecutions map initially', () => {
    const store = useLogicStore()
    expect(store.activeExecutions.size).toBe(0)
  })

  it('has empty recentExecutions array initially', () => {
    const store = useLogicStore()
    expect(store.recentExecutions).toEqual([])
  })
})

// =============================================================================
// COMPUTED GETTERS
// =============================================================================

describe('Logic Store - Computed Getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('connections', () => {
    it('returns empty array when no rules', () => {
      const store = useLogicStore()
      expect(store.connections).toEqual([])
    })

    it('extracts connections from rules', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      expect(store.connections.length).toBeGreaterThan(0)
      const conn = store.connections[0]
      expect(conn).toHaveProperty('ruleId')
      expect(conn).toHaveProperty('sourceEspId')
      expect(conn).toHaveProperty('targetEspId')
    })

    it('creates connection with correct data from mockLogicRule', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const conn = store.connections[0]
      expect(conn.ruleId).toBe('rule-001')
      expect(conn.ruleName).toBe('Temperature Fan Control')
      expect(conn.sourceEspId).toBe('ESP_TEST_001')
      expect(conn.sourceGpio).toBe(4)
      expect(conn.sourceSensorType).toBe('ds18b20')
      expect(conn.targetEspId).toBe('ESP_TEST_002')
      expect(conn.targetGpio).toBe(16)
      expect(conn.targetCommand).toBe('ON')
      expect(conn.enabled).toBe(true)
    })
  })

  describe('crossEspConnections', () => {
    it('returns empty array when no rules', () => {
      const store = useLogicStore()
      expect(store.crossEspConnections).toEqual([])
    })

    it('filters cross-ESP connections', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      // All 5 rules produce cross-ESP connections (7 total: rules with multiple conditions create multiple connections)
      expect(store.crossEspConnections.length).toBe(7)
      expect(store.crossEspConnections.every(c => c.isCrossEsp)).toBe(true)
      expect(store.crossEspConnections.every(c => c.sourceEspId !== c.targetEspId)).toBe(true)
    })

    it('excludes same-ESP connections', async () => {
      const store = useLogicStore()

      // Add same-ESP rule
      store.rules.push({
        id: 'rule-002',
        name: 'Same ESP Rule',
        enabled: true,
        conditions: [
          {
            type: 'sensor_threshold',
            esp_id: 'ESP_SAME',
            gpio: 4,
            sensor_type: 'ds18b20',
            operator: '>',
            value: 25,
          },
        ],
        logic_operator: 'AND',
        actions: [
          {
            type: 'actuator_command',
            esp_id: 'ESP_SAME',
            gpio: 16,
            command: 'ON',
          },
        ],
        priority: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })

      const crossEspConns = store.crossEspConnections
      const sameEspConn = store.connections.find((c) => c.sourceEspId === 'ESP_SAME')

      expect(sameEspConn).toBeDefined()
      expect(sameEspConn?.isCrossEsp).toBe(false)
      expect(crossEspConns.some((c) => c.sourceEspId === 'ESP_SAME')).toBe(false)
    })
  })

  describe('enabledRules', () => {
    it('returns only enabled rules', () => {
      const store = useLogicStore()

      store.rules = [
        { ...mockLogicRule, id: 'rule-1', enabled: true },
        { ...mockLogicRule, id: 'rule-2', enabled: false },
        { ...mockLogicRule, id: 'rule-3', enabled: true },
      ]

      expect(store.enabledRules.length).toBe(2)
      expect(store.enabledRules.every((r) => r.enabled)).toBe(true)
    })

    it('returns empty array when all rules disabled', () => {
      const store = useLogicStore()

      store.rules = [
        { ...mockLogicRule, id: 'rule-1', enabled: false },
        { ...mockLogicRule, id: 'rule-2', enabled: false },
      ]

      expect(store.enabledRules).toEqual([])
    })
  })

  describe('ruleCount', () => {
    it('returns 0 when no rules', () => {
      const store = useLogicStore()
      expect(store.ruleCount).toBe(0)
    })

    it('returns correct count of all rules', () => {
      const store = useLogicStore()

      store.rules = [
        { ...mockLogicRule, id: 'rule-1' },
        { ...mockLogicRule, id: 'rule-2' },
        { ...mockLogicRule, id: 'rule-3' },
      ]

      expect(store.ruleCount).toBe(3)
    })
  })

  describe('enabledCount', () => {
    it('returns 0 when no enabled rules', () => {
      const store = useLogicStore()
      store.rules = [{ ...mockLogicRule, enabled: false }]

      expect(store.enabledCount).toBe(0)
    })

    it('returns correct count of enabled rules', () => {
      const store = useLogicStore()

      store.rules = [
        { ...mockLogicRule, id: 'rule-1', enabled: true },
        { ...mockLogicRule, id: 'rule-2', enabled: false },
        { ...mockLogicRule, id: 'rule-3', enabled: true },
      ]

      expect(store.enabledCount).toBe(2)
    })
  })
})

// =============================================================================
// FETCH RULES
// =============================================================================

describe('Logic Store - fetchRules', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads rules from API on success', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    expect(store.rules.length).toBe(5)
    expect(store.rules[0].id).toBe('rule-001')
    expect(store.rules[0].name).toBe('Temperature Fan Control')
    expect(store.rules[1].id).toBe('rule-002')
    expect(store.rules[1].name).toBe('Humidity Humidifier Control')
    expect(store.rules[2].id).toBe('rule-003')
    expect(store.rules[3].id).toBe('rule-004')
    expect(store.rules[4].id).toBe('rule-005')
  })

  it('sets isLoading during fetch', async () => {
    const store = useLogicStore()

    const fetchPromise = store.fetchRules()
    expect(store.isLoading).toBe(true)

    await fetchPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears error on successful fetch', async () => {
    const store = useLogicStore()
    store.error = 'Previous error'

    await store.fetchRules()

    expect(store.error).toBeNull()
  })

  it('sets error on API failure', async () => {
    server.use(
      http.get('/api/v1/logic/rules', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      })
    )

    const store = useLogicStore()
    await store.fetchRules()

    expect(store.error).not.toBeNull()
    expect(store.error).toContain('Server error')
  })

  it('sets isLoading to false even on error', async () => {
    server.use(
      http.get('/api/v1/logic/rules', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      })
    )

    const store = useLogicStore()
    await store.fetchRules()

    expect(store.isLoading).toBe(false)
  })

  it('passes query parameters to API', async () => {
    let capturedParams: URLSearchParams | null = null

    server.use(
      http.get('/api/v1/logic/rules', ({ request }) => {
        capturedParams = new URL(request.url).searchParams
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 })
      })
    )

    const store = useLogicStore()
    await store.fetchRules({ enabled: true, page: 2, page_size: 25 })

    expect(capturedParams?.get('enabled')).toBe('true')
    expect(capturedParams?.get('page')).toBe('2')
    expect(capturedParams?.get('page_size')).toBe('25')
  })
})

// =============================================================================
// FETCH RULE
// =============================================================================

describe('Logic Store - fetchRule', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches single rule by ID', async () => {
    const store = useLogicStore()
    const rule = await store.fetchRule('rule-001')

    expect(rule).not.toBeNull()
    expect(rule?.id).toBe('rule-001')
  })

  it('adds new rule to list when not present', async () => {
    const store = useLogicStore()
    expect(store.rules.length).toBe(0)

    await store.fetchRule('rule-001')

    expect(store.rules.length).toBe(1)
    expect(store.rules[0].id).toBe('rule-001')
  })

  it('updates existing rule in list', async () => {
    const store = useLogicStore()

    // Add rule with old data
    store.rules = [{ ...mockLogicRule, name: 'Old Name' }]

    // Fetch updated rule
    await store.fetchRule('rule-001')

    expect(store.rules.length).toBe(1)
    expect(store.rules[0].name).toBe('Temperature Fan Control')
  })

  it('sets isLoading during fetch', async () => {
    const store = useLogicStore()

    const fetchPromise = store.fetchRule('rule-001')
    expect(store.isLoading).toBe(true)

    await fetchPromise
    expect(store.isLoading).toBe(false)
  })

  it('returns null and sets error on 404', async () => {
    server.use(
      http.get('/api/v1/logic/rules/:ruleId', () => {
        return HttpResponse.json({ detail: 'Rule not found' }, { status: 404 })
      })
    )

    const store = useLogicStore()
    const rule = await store.fetchRule('nonexistent')

    expect(rule).toBeNull()
    expect(store.error).not.toBeNull()
    expect(store.error).toContain('Rule not found')
  })

  it('clears error on successful fetch', async () => {
    const store = useLogicStore()
    store.error = 'Previous error'

    await store.fetchRule('rule-001')

    expect(store.error).toBeNull()
  })
})

// =============================================================================
// TOGGLE RULE
// =============================================================================

describe('Logic Store - toggleRule', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('toggles rule enabled state via API', async () => {
    const store = useLogicStore()
    store.rules = [{ ...mockLogicRule, enabled: true }]

    const newState = await store.toggleRule('rule-001')

    expect(newState).toBe(false)
  })

  it('updates local rule state after toggle', async () => {
    const store = useLogicStore()
    store.rules = [{ ...mockLogicRule, enabled: true }]

    await store.toggleRule('rule-001')

    expect(store.rules[0].enabled).toBe(false)
  })

  it('clears error on successful toggle', async () => {
    const store = useLogicStore()
    store.rules = [{ ...mockLogicRule }]
    store.error = 'Previous error'

    await store.toggleRule('rule-001')

    expect(store.error).toBeNull()
  })

  it('sets error and throws on API failure', async () => {
    server.use(
      http.post('/api/v1/logic/rules/:ruleId/toggle', () => {
        return HttpResponse.json({ detail: 'Toggle failed' }, { status: 500 })
      })
    )

    const store = useLogicStore()
    store.rules = [{ ...mockLogicRule }]

    await expect(store.toggleRule('rule-001')).rejects.toThrow()
    expect(store.error).not.toBeNull()
  })

  it('throws on 404 not found', async () => {
    server.use(
      http.post('/api/v1/logic/rules/:ruleId/toggle', () => {
        return HttpResponse.json({ detail: 'Rule not found' }, { status: 404 })
      })
    )

    const store = useLogicStore()

    await expect(store.toggleRule('nonexistent')).rejects.toThrow()
  })
})

// =============================================================================
// TEST RULE
// =============================================================================

describe('Logic Store - testRule', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns conditions_result from test API', async () => {
    const store = useLogicStore()
    const result = await store.testRule('rule-001')

    expect(typeof result).toBe('boolean')
  })

  it('clears error on successful test', async () => {
    const store = useLogicStore()
    store.error = 'Previous error'

    await store.testRule('rule-001')

    expect(store.error).toBeNull()
  })

  it('sets error and throws on API failure', async () => {
    server.use(
      http.post('/api/v1/logic/rules/:ruleId/test', () => {
        return HttpResponse.json({ detail: 'Test failed' }, { status: 500 })
      })
    )

    const store = useLogicStore()

    await expect(store.testRule('rule-001')).rejects.toThrow()
    expect(store.error).not.toBeNull()
  })

  it('throws on 404 not found', async () => {
    server.use(
      http.post('/api/v1/logic/rules/:ruleId/test', () => {
        return HttpResponse.json({ detail: 'Rule not found' }, { status: 404 })
      })
    )

    const store = useLogicStore()

    await expect(store.testRule('nonexistent')).rejects.toThrow()
  })
})

// =============================================================================
// CONNECTION HELPERS
// =============================================================================

describe('Logic Store - Connection Helpers', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('getConnectionsForEsp', () => {
    it('returns empty array when no connections', () => {
      const store = useLogicStore()
      expect(store.getConnectionsForEsp('ESP_001')).toEqual([])
    })

    it('returns connections where ESP is source', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const connections = store.getConnectionsForEsp('ESP_TEST_001')
      expect(connections.length).toBeGreaterThan(0)
      expect(connections.some((c) => c.sourceEspId === 'ESP_TEST_001')).toBe(true)
    })

    it('returns connections where ESP is target', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const connections = store.getConnectionsForEsp('ESP_TEST_002')
      expect(connections.length).toBeGreaterThan(0)
      expect(connections.some((c) => c.targetEspId === 'ESP_TEST_002')).toBe(true)
    })

    it('returns connections for both source and target roles', async () => {
      const store = useLogicStore()

      // Rule where ESP is both source and target in different connections
      store.rules = [
        {
          ...mockLogicRule,
          id: 'rule-multi',
          conditions: [
            {
              type: 'sensor_threshold',
              esp_id: 'ESP_MULTI',
              gpio: 4,
              sensor_type: 'ds18b20',
              operator: '>',
              value: 25,
            },
          ],
          actions: [
            {
              type: 'actuator_command',
              esp_id: 'ESP_TARGET_1',
              gpio: 16,
              command: 'ON',
            },
          ],
        },
        {
          ...mockLogicRule,
          id: 'rule-multi-2',
          conditions: [
            {
              type: 'sensor_threshold',
              esp_id: 'ESP_OTHER',
              gpio: 5,
              sensor_type: 'sht31',
              operator: '<',
              value: 30,
            },
          ],
          actions: [
            {
              type: 'actuator_command',
              esp_id: 'ESP_MULTI',
              gpio: 17,
              command: 'OFF',
            },
          ],
        },
      ]

      const connections = store.getConnectionsForEsp('ESP_MULTI')
      expect(connections.length).toBe(2)
      expect(connections.some((c) => c.sourceEspId === 'ESP_MULTI')).toBe(true)
      expect(connections.some((c) => c.targetEspId === 'ESP_MULTI')).toBe(true)
    })
  })

  describe('getOutgoingConnections', () => {
    it('returns only connections where ESP is source', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const outgoing = store.getOutgoingConnections('ESP_TEST_001')
      expect(outgoing.length).toBeGreaterThan(0)
      expect(outgoing.every((c) => c.sourceEspId === 'ESP_TEST_001')).toBe(true)
    })

    it('excludes connections where ESP is target', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const outgoing = store.getOutgoingConnections('ESP_TEST_002')
      expect(outgoing.length).toBe(0)
    })
  })

  describe('getIncomingConnections', () => {
    it('returns only connections where ESP is target', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const incoming = store.getIncomingConnections('ESP_TEST_002')
      expect(incoming.length).toBeGreaterThan(0)
      expect(incoming.every((c) => c.targetEspId === 'ESP_TEST_002')).toBe(true)
    })

    it('excludes connections where ESP is source', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const incoming = store.getIncomingConnections('ESP_TEST_001')
      expect(incoming.length).toBe(0)
    })
  })

  describe('getRuleById', () => {
    it('returns undefined when rule not found', () => {
      const store = useLogicStore()
      expect(store.getRuleById('nonexistent')).toBeUndefined()
    })

    it('finds rule by ID', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const rule = store.getRuleById('rule-001')
      expect(rule).toBeDefined()
      expect(rule?.id).toBe('rule-001')
    })
  })

  describe('getRulesForZone', () => {
    beforeEach(() => {
      mockEspDevices.length = 0
    })

    it('returns empty array when zoneId is empty', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      expect(store.getRulesForZone('')).toEqual([])
    })

    it('returns only rules with sensor/actuator in the given zone', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      mockEspDevices.push(
        { device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001', zone_id: 'zone_A' },
        { device_id: 'ESP_TEST_002', esp_id: 'ESP_TEST_002', zone_id: 'zone_A' },
        { device_id: 'ESP_HUMIDITY_001', esp_id: 'ESP_HUMIDITY_001', zone_id: 'zone_B' }
      )

      const rulesZoneA = store.getRulesForZone('zone_A')
      expect(rulesZoneA.map((r) => r.id)).toContain('rule-001')
      expect(rulesZoneA.length).toBeGreaterThanOrEqual(1)

      const rulesZoneB = store.getRulesForZone('zone_B')
      expect(rulesZoneB.map((r) => r.id)).toContain('rule-002')
    })

    it('excludes rules that do not match the zone', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      mockEspDevices.push(
        { device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001', zone_id: 'zone_A' },
        { device_id: 'ESP_TEST_002', esp_id: 'ESP_TEST_002', zone_id: 'zone_A' }
      )

      const rulesZoneC = store.getRulesForZone('zone_C')
      expect(rulesZoneC).toEqual([])
    })

    it('returns empty array when espStore.devices is empty', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      expect(mockEspDevices).toHaveLength(0)

      const rules = store.getRulesForZone('zone_A')
      expect(rules).toEqual([])
    })

    it('sorts rules by priority then name', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      mockEspDevices.push(
        { device_id: 'ESP_TEST_001', esp_id: 'ESP_TEST_001', zone_id: 'zone_A' },
        { device_id: 'ESP_TEST_002', esp_id: 'ESP_TEST_002', zone_id: 'zone_A' },
        { device_id: 'ESP_HUMIDITY_001', esp_id: 'ESP_HUMIDITY_001', zone_id: 'zone_A' },
        { device_id: 'ESP_HUMIDIFIER_001', esp_id: 'ESP_HUMIDIFIER_001', zone_id: 'zone_A' }
      )

      const rules = store.getRulesForZone('zone_A')
      expect(rules.length).toBeGreaterThanOrEqual(2)
      for (let i = 1; i < rules.length; i++) {
        const prev = rules[i - 1].priority ?? 0
        const curr = rules[i].priority ?? 0
        expect(curr).toBeGreaterThanOrEqual(prev)
      }
    })
  })

  describe('clearError', () => {
    it('resets error to null', () => {
      const store = useLogicStore()
      store.error = 'Some error'

      store.clearError()

      expect(store.error).toBeNull()
    })
  })
})

// =============================================================================
// WEBSOCKET INTEGRATION
// =============================================================================

describe('Logic Store - WebSocket Integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('subscribeToWebSocket', () => {
    it('calls websocketService.subscribe with correct filter', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      expect(websocketService.subscribe).toHaveBeenCalledWith(
        {
          types: [
            'logic_execution',
            'sequence_started',
            'sequence_step',
            'sequence_completed',
            'sequence_error',
            'sequence_cancelled',
            'conflict.arbitration',
            'rule_degraded',
            'rule_recovered',
          ],
        },
        expect.any(Function)
      )
    })

    it('does not subscribe twice if already subscribed', () => {
      const store = useLogicStore()

      store.subscribeToWebSocket()
      store.subscribeToWebSocket()

      expect(websocketService.subscribe).toHaveBeenCalledTimes(1)
    })
  })

  describe('unsubscribeFromWebSocket', () => {
    it('calls websocketService.unsubscribe', () => {
      const store = useLogicStore()

      store.subscribeToWebSocket()
      store.unsubscribeFromWebSocket()

      expect(websocketService.unsubscribe).toHaveBeenCalledWith('sub-logic-123')
    })

    it('does nothing if not subscribed', () => {
      const store = useLogicStore()

      store.unsubscribeFromWebSocket()

      expect(websocketService.unsubscribe).not.toHaveBeenCalled()
    })

    it('allows re-subscription after unsubscribe', () => {
      const store = useLogicStore()

      store.subscribeToWebSocket()
      store.unsubscribeFromWebSocket()
      vi.clearAllMocks()

      store.subscribeToWebSocket()

      expect(websocketService.subscribe).toHaveBeenCalledTimes(1)
    })
  })

  describe('handleLogicExecutionEvent', () => {
    it('adds event to recentExecutions', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
      const mockEvent = {
        type: 'logic_execution',
        data: {
          rule_id: 'rule-001',
          rule_name: 'Test Rule',
          trigger: {
            esp_id: 'ESP_001',
            gpio: 4,
            sensor_type: 'ds18b20',
            value: 26.5,
          },
          action: {
            esp_id: 'ESP_002',
            gpio: 16,
            command: 'ON',
          },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      }

      callback(mockEvent)

      expect(store.recentExecutions.length).toBe(1)
      expect(store.recentExecutions[0].rule_id).toBe('rule-001')
    })

    it('keeps only last 20 executions', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      // Add 25 events
      for (let i = 0; i < 25; i++) {
        callback({
          type: 'logic_execution',
          data: {
            rule_id: `rule-${i}`,
            rule_name: `Rule ${i}`,
            trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
            action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
            success: true,
            timestamp: Date.now() / 1000,
          },
          timestamp: Date.now(),
        })
      }

      expect(store.recentExecutions.length).toBe(20)
      expect(store.recentExecutions[0].rule_id).toBe('rule-24')
      expect(store.recentExecutions[19].rule_id).toBe('rule-5')
    })

    it('marks rule as active in activeExecutions map', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      callback({
        type: 'logic_execution',
        data: {
          rule_id: 'rule-001',
          rule_name: 'Test',
          trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
          action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      })

      expect(store.activeExecutions.has('rule-001')).toBe(true)
    })

    it('updates rule last_triggered if rule exists in store', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      store.subscribeToWebSocket()
      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      const eventTimestamp = Date.now() / 1000

      callback({
        type: 'logic_execution',
        data: {
          rule_id: 'rule-001',
          rule_name: 'Temperature Fan Control',
          trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 26 },
          action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
          success: true,
          timestamp: eventTimestamp,
        },
        timestamp: Date.now(),
      })

      const rule = store.getRuleById('rule-001')
      expect(rule?.last_triggered).toBeDefined()
    })

    it('maps successful execution to terminal_success lifecycle', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
      callback({
        type: 'logic_execution',
        data: {
          rule_id: 'rule-001',
          rule_name: 'Temperature Fan Control',
          trigger: { type: 'sensor', sensor_type: 'ds18b20', value: 26 },
          action: { esp_id: 'ESP_TEST_002', gpio: 16, command: 'ON' },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      })

      expect(store.getRuleLifecycleState('rule-001')).toBe('terminal_success')
    })

    it('maps conflict failures to terminal_conflict', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
      callback({
        type: 'sequence_error',
        data: {
          sequence_id: 'seq-1',
          rule_id: 'rule-001',
          message: 'cooldown blocked',
        },
        timestamp: Date.now(),
      })

      expect(store.getRuleLifecycleState('rule-001')).toBe('terminal_conflict')
      expect(store.getLifecycleEntry('rule-001')?.terminal_reason_code).toBe('conflict_cooldown_blocked')
    })

    it('ignores events without rule_id', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      callback({
        type: 'logic_execution',
        data: {
          rule_name: 'Test',
        },
        timestamp: Date.now(),
      })

      expect(store.recentExecutions.length).toBe(0)
    })

    it('ignores non-logic_execution events', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      callback({
        type: 'sensor_data',
        data: {},
        timestamp: Date.now(),
      })

      expect(store.recentExecutions.length).toBe(0)
    })
  })

  describe('handleConflictArbitrationEvent', () => {
    it('stores newest conflict arbitration event with trace id', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
      callback({
        type: 'conflict.arbitration',
        data: {
          trace_id: 'trace-123',
          actuator_key: 'ESP_TEST_001:16',
          winner_rule_id: 'rule-001',
          loser_rule_id: 'rule-002',
          arbitration_mode: 'priority',
          resolution: 'higher_priority_wins',
          competing_rules: ['rule-001', 'rule-002'],
        },
        timestamp: Date.now(),
      })

      expect(store.recentConflictArbitrations).toHaveLength(1)
      expect(store.recentConflictArbitrations[0].trace_id).toBe('trace-123')
      expect(store.recentConflictArbitrations[0].arbitration_mode).toBe('priority')
    })
  })

  describe('handleRuleDegradedEvent', () => {
    it('maps degraded reason from legacy reason field', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
      callback({
        type: 'rule_degraded',
        data: {
          rule_id: 'rule-001',
          degraded_since: '2026-04-23T08:00:00Z',
          reason: 'target_esp_offline:ESP_TEST_001',
          is_critical: true,
        },
        timestamp: Date.now(),
      })

      const updated = store.rules.find(rule => rule.id === 'rule-001')
      expect(updated?.degraded_reason).toBe('target_esp_offline:ESP_TEST_001')
      expect(updated?.is_critical).toBe(true)
    })
  })

  describe('isRuleActive', () => {
    it('returns false when rule not in activeExecutions', () => {
      const store = useLogicStore()
      expect(store.isRuleActive('rule-001')).toBe(false)
    })

    it('returns true when rule is active', () => {
      const store = useLogicStore()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      callback({
        type: 'logic_execution',
        data: {
          rule_id: 'rule-active',
          rule_name: 'Active Rule',
          trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
          action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      })

      expect(store.isRuleActive('rule-active')).toBe(true)
    })
  })

  describe('isConnectionActive', () => {
    it('returns false when connection rule not active', async () => {
      const store = useLogicStore()
      await store.fetchRules()

      const connection = store.connections[0]
      expect(store.isConnectionActive(connection)).toBe(false)
    })

    it('returns true when connection rule is active', async () => {
      const store = useLogicStore()
      await store.fetchRules()
      store.subscribeToWebSocket()

      const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

      callback({
        type: 'logic_execution',
        data: {
          rule_id: 'rule-001',
          rule_name: 'Test',
          trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
          action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      })

      const connection = store.connections[0]
      expect(store.isConnectionActive(connection)).toBe(true)
    })
  })
})

// =============================================================================
// ERROR RECOVERY - API FAILURES
// =============================================================================

describe('Logic Store - Error Recovery', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('createRule error handling', () => {
    it('sets error on 422 validation failure', async () => {
      server.use(
        http.post('/api/v1/logic/rules', () => {
          return HttpResponse.json({
            detail: [
              { loc: ['body', 'conditions'], msg: 'at least one condition required' },
              { loc: ['body', 'actions'], msg: 'at least one action required' },
            ]
          }, { status: 422 })
        })
      )

      const store = useLogicStore()

      await expect(store.createRule({
        name: 'Invalid Rule',
        conditions: [],
        logic_operator: 'AND',
        actions: [],
      })).rejects.toThrow()

      expect(store.error).toContain('conditions')
      expect(store.error).toContain('actions')
    })

    it('does not add rule to list on failure', async () => {
      server.use(
        http.post('/api/v1/logic/rules', () => {
          return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
        })
      )

      const store = useLogicStore()
      const initialCount = store.rules.length

      try {
        await store.createRule({ name: 'Failing Rule', conditions: [], logic_operator: 'AND', actions: [] })
      } catch { /* expected */ }

      expect(store.rules.length).toBe(initialCount)
    })
  })

  describe('updateRule error handling', () => {
    it('sets error on 404 when rule does not exist', async () => {
      server.use(
        http.put('/api/v1/logic/rules/:ruleId', () => {
          return HttpResponse.json({ detail: 'Rule not found' }, { status: 404 })
        })
      )

      const store = useLogicStore()

      await expect(store.updateRule('nonexistent', { name: 'Updated' })).rejects.toThrow()
      expect(store.error).toContain('Rule not found')
    })
  })

  describe('deleteRule error handling', () => {
    it('sets error on 500 server failure', async () => {
      server.use(
        http.delete('/api/v1/logic/rules/:ruleId', () => {
          return HttpResponse.json({ detail: 'Internal server error' }, { status: 500 })
        })
      )

      const store = useLogicStore()
      store.rules = [{ ...mockLogicRule }]

      await expect(store.deleteRule('rule-001')).rejects.toThrow()
      expect(store.error).toContain('Internal server error')
      // Rule should NOT be removed from local list on failure
      expect(store.rules.length).toBe(1)
    })
  })

  describe('error state management', () => {
    it('successful operation clears previous error', async () => {
      const store = useLogicStore()
      store.error = 'Previous error from failed operation'

      await store.fetchRules()

      expect(store.error).toBeNull()
    })

    it('clearError resets error independently', () => {
      const store = useLogicStore()
      store.error = 'Some error'

      store.clearError()

      expect(store.error).toBeNull()
    })

    it('multiple sequential errors replace each other', async () => {
      const store = useLogicStore()

      // First error
      server.use(
        http.get('/api/v1/logic/rules', () => {
          return HttpResponse.json({ detail: 'First error' }, { status: 500 })
        })
      )
      await store.fetchRules()
      expect(store.error).toContain('First error')

      // Reset handler
      server.resetHandlers()

      // Second error via different action
      server.use(
        http.post('/api/v1/logic/rules/:ruleId/toggle', () => {
          return HttpResponse.json({ detail: 'Second error' }, { status: 500 })
        })
      )

      store.rules = [{ ...mockLogicRule }]
      try {
        await store.toggleRule('rule-001')
      } catch { /* expected */ }

      expect(store.error).toContain('Second error')
    })
  })
})

// =============================================================================
// WEBSOCKET EDGE CASES
// =============================================================================

describe('Logic Store - WebSocket Edge Cases', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('handles duplicate execution events idempotently', () => {
    const store = useLogicStore()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
    const event = {
      type: 'logic_execution',
      data: {
        rule_id: 'rule-001',
        rule_name: 'Test',
        trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
        action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    }

    // Send same event twice
    callback(event)
    callback(event)

    // Both should be recorded (no dedup on execution events — they represent actual executions)
    expect(store.recentExecutions.length).toBe(2)
    // Active state should still be set
    expect(store.isRuleActive('rule-001')).toBe(true)
  })

  it('handles malformed execution event without crash', () => {
    const store = useLogicStore()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    // Missing rule_id — should be ignored silently
    callback({
      type: 'logic_execution',
      data: {
        rule_name: 'Broken Event',
        // no rule_id
      },
      timestamp: Date.now(),
    })

    expect(store.recentExecutions.length).toBe(0)
  })

  it('handles execution event with empty data object gracefully', () => {
    const store = useLogicStore()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    // Empty data object — rule_id is undefined → should be ignored
    callback({
      type: 'logic_execution',
      data: {},
      timestamp: Date.now(),
    })

    expect(store.recentExecutions.length).toBe(0)
  })

  it('execution for unknown rule still gets recorded', () => {
    const store = useLogicStore()
    // Do NOT fetch rules — rules list is empty
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-unknown-999',
        rule_name: 'Unknown Rule',
        trigger: { esp_id: 'ESP', gpio: 4, sensor_type: 'ds18b20', value: 25 },
        action: { esp_id: 'ESP', gpio: 16, command: 'ON' },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    // Execution is still recorded even though rule doesn't exist in store
    expect(store.recentExecutions.length).toBe(1)
    expect(store.isRuleActive('rule-unknown-999')).toBe(true)
  })
})

// =============================================================================
// UNDO/REDO
// =============================================================================

describe('Logic Store - Undo/Redo', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('pushToHistory stores snapshot', () => {
    const store = useLogicStore()
    const nodes = [{ id: 'n1', type: 'sensor' }]
    const edges = [{ id: 'e1', source: 'n1', target: 'n2' }]

    store.pushToHistory(nodes, edges)

    expect(store.history.length).toBe(1)
    expect(store.historyIndex).toBe(0)
  })

  it('pushToHistory stores metadata snapshot', () => {
    const store = useLogicStore()
    store.pushToHistory([{ id: 'n1' }], [], { priority: 7, cooldown_seconds: 120 })
    expect(store.history[0].metadata).toEqual({ priority: 7, cooldown_seconds: 120 })
  })

  it('can undo after 2 pushes', () => {
    const store = useLogicStore()

    store.pushToHistory([{ id: 'n1' }], [])
    store.pushToHistory([{ id: 'n1' }, { id: 'n2' }], [{ id: 'e1' }])

    expect(store.canUndo).toBe(true)
    const previous = store.undo()

    expect(previous).not.toBeNull()
    expect(previous!.nodes).toHaveLength(1)
    expect(store.historyIndex).toBe(0)
  })

  it('can redo after undo', () => {
    const store = useLogicStore()

    store.pushToHistory([{ id: 'n1' }], [])
    store.pushToHistory([{ id: 'n1' }, { id: 'n2' }], [])

    store.undo()
    expect(store.canRedo).toBe(true)

    const redone = store.redo()
    expect(redone).not.toBeNull()
    expect(redone!.nodes).toHaveLength(2)
  })

  it('cannot undo with only 1 entry', () => {
    const store = useLogicStore()
    store.pushToHistory([], [])

    expect(store.canUndo).toBe(false)
    expect(store.undo()).toBeNull()
  })

  it('cannot redo at latest entry', () => {
    const store = useLogicStore()
    store.pushToHistory([], [])

    expect(store.canRedo).toBe(false)
    expect(store.redo()).toBeNull()
  })

  it('clearHistory resets state', () => {
    const store = useLogicStore()
    store.pushToHistory([], [])
    store.pushToHistory([], [])

    store.clearHistory()

    expect(store.history.length).toBe(0)
    expect(store.historyIndex).toBe(-1)
  })

  it('discards future entries when pushing after undo', () => {
    const store = useLogicStore()

    store.pushToHistory([{ id: 'a' }], [])
    store.pushToHistory([{ id: 'b' }], [])
    store.pushToHistory([{ id: 'c' }], [])

    // Undo back to 'a'
    store.undo()
    store.undo()
    expect(store.historyIndex).toBe(0)

    // Push new state — 'b' and 'c' should be discarded
    store.pushToHistory([{ id: 'd' }], [])
    expect(store.history.length).toBe(2) // 'a' and 'd'
    expect(store.historyIndex).toBe(1)
  })

  it('limits history to MAX_HISTORY (50)', () => {
    const store = useLogicStore()

    for (let i = 0; i < 55; i++) {
      store.pushToHistory([{ id: `n${i}` }], [])
    }

    expect(store.history.length).toBe(50)
    // Latest entry should be n54
    expect(store.history[49].nodes[0].id).toBe('n54')
  })
})

// =============================================================================
// extractSensorConditions (D4 — N6 Fix Verifikation)
// =============================================================================

import { extractSensorConditions } from '@/types/logic'
import type { LogicCondition } from '@/types/logic'

describe('extractSensorConditions', () => {
  it('returns sensor conditions', () => {
    const conditions: LogicCondition[] = [
      { type: 'sensor', esp_id: 'ESP_1', gpio: 4, sensor_type: 'DS18B20', operator: '>', value: 25 } as LogicCondition,
    ]
    const refs = extractSensorConditions(conditions)
    expect(refs).toHaveLength(1)
    expect(refs[0]).toMatchObject({ esp_id: 'ESP_1', gpio: 4, sensor_type: 'DS18B20' })
  })

  it('includes hysteresis conditions (N6 fix — LinkedRulesSection must show hysteresis rules)', () => {
    const conditions: LogicCondition[] = [
      {
        type: 'hysteresis',
        esp_id: 'ESP_1',
        gpio: 0,
        sensor_type: 'sht31_humidity',
        activate_below: 45,
        deactivate_above: 55,
      } as LogicCondition,
    ]
    const refs = extractSensorConditions(conditions)
    expect(refs).toHaveLength(1)
    expect(refs[0]).toMatchObject({ esp_id: 'ESP_1', gpio: 0, sensor_type: 'sht31_humidity' })
  })

  it('recursively extracts from compound conditions', () => {
    const conditions: LogicCondition[] = [
      {
        type: 'compound',
        logic: 'AND',
        conditions: [
          { type: 'sensor', esp_id: 'ESP_2', gpio: 5, sensor_type: 'DS18B20', operator: '<', value: 10 } as LogicCondition,
          { type: 'hysteresis', esp_id: 'ESP_2', gpio: 6, sensor_type: 'sht31_temp', activate_above: 30, deactivate_below: 26 } as LogicCondition,
        ],
      } as LogicCondition,
    ]
    const refs = extractSensorConditions(conditions)
    expect(refs).toHaveLength(2)
  })

  it('returns empty array for time-only conditions', () => {
    const conditions: LogicCondition[] = [
      {
        type: 'time_window',
        start_hour: 6,
        start_minute: 30,
        end_hour: 22,
        end_minute: 15,
      } as LogicCondition,
    ]
    const refs = extractSensorConditions(conditions)
    expect(refs).toHaveLength(0)
  })

  it('does not regress on sensor_threshold type', () => {
    const conditions: LogicCondition[] = [
      { type: 'sensor_threshold', esp_id: 'ESP_3', gpio: 7, sensor_type: 'EC', operator: '>=', value: 1.5 } as LogicCondition,
    ]
    const refs = extractSensorConditions(conditions)
    expect(refs).toHaveLength(1)
  })
})
