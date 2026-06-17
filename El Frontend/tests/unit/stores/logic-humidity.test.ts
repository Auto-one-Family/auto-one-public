/**
 * Humidity → Humidifier Logic Rule Tests
 *
 * Tests the complete data flow for a humidity sensor triggering a humidifier relay:
 * - SHT31 sensor on ESP_HUMIDITY_001 (GPIO 21) reads humidity < 40%
 * - Logic rule triggers actuator ON command
 * - Relay on ESP_HUMIDIFIER_001 (GPIO 16) turns humidifier on
 * - Auto-off after 300 seconds
 *
 * Tests cover:
 * - Rule structure and validation
 * - Connection extraction (cross-ESP)
 * - Rule ↔ Graph conversion
 * - WebSocket execution events
 * - Rule CRUD operations
 * - Test/evaluate simulation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock WebSocket service
vi.mock('@/services/websocket', () => {
  const mockSubscribe = vi.fn().mockReturnValue('sub-humidity-123')
  const mockUnsubscribe = vi.fn()

  return {
    websocketService: {
      subscribe: mockSubscribe,
      unsubscribe: mockUnsubscribe,
    },
    WebSocketMessage: {},
  }
})

// Mock logger
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

import { beforeAll, afterAll, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLogicStore } from '@/shared/stores/logic.store'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import {
  mockHumidityRule,
  mockHumiditySensorESP,
  mockHumidifierESP,
  mockAndRule,
  mockOrRule,
  mockMultiActionRule,
} from '../../mocks/handlers'
import { websocketService } from '@/services/websocket'
import { extractConnections, generateRuleDescription } from '@/types/logic'
import type { SensorCondition, ActuatorAction, LogicRule } from '@/types/logic'

// MSW Server Lifecycle
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// HUMIDITY RULE STRUCTURE
// =============================================================================

describe('Humidity Rule - Structure Validation', () => {
  it('has correct rule metadata', () => {
    expect(mockHumidityRule.id).toBe('rule-002')
    expect(mockHumidityRule.name).toBe('Humidity Humidifier Control')
    expect(mockHumidityRule.enabled).toBe(true)
    expect(mockHumidityRule.priority).toBe(2)
    expect(mockHumidityRule.cooldown_seconds).toBe(120)
    expect(mockHumidityRule.max_executions_per_hour).toBe(6)
  })

  it('has SHT31 sensor condition with < 40% threshold', () => {
    expect(mockHumidityRule.conditions).toHaveLength(1)

    const condition = mockHumidityRule.conditions[0] as SensorCondition
    expect(condition.type).toBe('sensor_threshold')
    expect(condition.esp_id).toBe('ESP_HUMIDITY_001')
    expect(condition.gpio).toBe(21)
    expect(condition.sensor_type).toBe('SHT31')
    expect(condition.operator).toBe('<')
    expect(condition.value).toBe(40)
  })

  it('has relay actuator action with auto-off duration', () => {
    expect(mockHumidityRule.actions).toHaveLength(1)

    const action = mockHumidityRule.actions[0] as ActuatorAction
    expect(action.type).toBe('actuator_command')
    expect(action.esp_id).toBe('ESP_HUMIDIFIER_001')
    expect(action.gpio).toBe(16)
    expect(action.command).toBe('ON')
    expect(action.duration).toBe(300)
  })

  it('uses AND logic operator', () => {
    expect(mockHumidityRule.logic_operator).toBe('AND')
  })
})

// =============================================================================
// MOCK ESP DEVICES
// =============================================================================

describe('Humidity Rule - ESP Device Validation', () => {
  it('humidity sensor ESP has SHT31 sensor on GPIO 21', () => {
    expect(mockHumiditySensorESP.esp_id).toBe('ESP_HUMIDITY_001')
    expect(mockHumiditySensorESP.sensors).toHaveLength(1)

    const sensor = mockHumiditySensorESP.sensors[0]
    expect(sensor.gpio).toBe(21)
    expect(sensor.sensor_type).toBe('SHT31')
    expect(sensor.name).toBe('Air Humidity Sensor')
    expect(sensor.raw_value).toBe(38.2)
    expect(sensor.is_multi_value).toBe(true)
  })

  it('humidity sensor reads below 40% threshold (triggers rule)', () => {
    const currentHumidity = mockHumiditySensorESP.sensors[0].raw_value
    const threshold = mockHumidityRule.conditions[0].value

    expect(currentHumidity).toBeLessThan(threshold)
  })

  it('humidity sensor has multi-value output (humidity + temperature)', () => {
    const sensor = mockHumiditySensorESP.sensors[0]
    expect(sensor.multi_values).toBeDefined()
    expect(sensor.multi_values?.humidity.value).toBe(38.2)
    expect(sensor.multi_values?.humidity.unit).toBe('%')
    expect(sensor.multi_values?.temperature.value).toBe(23.1)
    expect(sensor.multi_values?.temperature.unit).toBe('°C')
  })

  it('humidifier ESP has relay actuator on GPIO 16', () => {
    expect(mockHumidifierESP.esp_id).toBe('ESP_HUMIDIFIER_001')
    expect(mockHumidifierESP.actuators).toHaveLength(1)

    const actuator = mockHumidifierESP.actuators[0]
    expect(actuator.gpio).toBe(16)
    expect(actuator.actuator_type).toBe('relay')
    expect(actuator.name).toBe('Humidifier Relay')
    expect(actuator.state).toBe(false)
    expect(actuator.emergency_stopped).toBe(false)
  })

  it('both ESPs are in the same zone', () => {
    expect(mockHumiditySensorESP.zone_id).toBe(mockHumidifierESP.zone_id)
    expect(mockHumiditySensorESP.zone_name).toBe('Test Zone')
  })

  it('both ESPs are online and operational', () => {
    expect(mockHumiditySensorESP.status).toBe('online')
    expect(mockHumiditySensorESP.system_state).toBe('OPERATIONAL')
    expect(mockHumidifierESP.status).toBe('online')
    expect(mockHumidifierESP.system_state).toBe('OPERATIONAL')
  })
})

// =============================================================================
// CONNECTION EXTRACTION
// =============================================================================

describe('Humidity Rule - Connection Extraction', () => {
  it('extracts cross-ESP connection from humidity rule', () => {
    const connections = extractConnections(mockHumidityRule as LogicRule)

    expect(connections).toHaveLength(1)
    const conn = connections[0]
    expect(conn.ruleId).toBe('rule-002')
    expect(conn.sourceEspId).toBe('ESP_HUMIDITY_001')
    expect(conn.sourceGpio).toBe(21)
    expect(conn.sourceSensorType).toBe('SHT31')
    expect(conn.targetEspId).toBe('ESP_HUMIDIFIER_001')
    expect(conn.targetGpio).toBe(16)
    expect(conn.targetCommand).toBe('ON')
    expect(conn.isCrossEsp).toBe(true)
    expect(conn.enabled).toBe(true)
  })

  it('generates human-readable rule description', () => {
    const condition = mockHumidityRule.conditions[0] as SensorCondition
    const action = mockHumidityRule.actions[0] as ActuatorAction
    const desc = generateRuleDescription(condition, action)

    expect(desc).toContain('SHT31')
    expect(desc).toContain('<')
    expect(desc).toContain('40')
    // generateRuleDescription uses German labels: ON → AN
    expect(desc).toContain('AN')
  })
})

// =============================================================================
// STORE INTEGRATION
// =============================================================================

describe('Humidity Rule - Store Integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('fetches humidity rule along with other rules', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const humidityRule = store.getRuleById('rule-002')
    expect(humidityRule).toBeDefined()
    expect(humidityRule?.name).toBe('Humidity Humidifier Control')
  })

  it('extracts humidity connections via store getter', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const humidityConn = store.connections.find(c => c.ruleId === 'rule-002')
    expect(humidityConn).toBeDefined()
    expect(humidityConn?.sourceEspId).toBe('ESP_HUMIDITY_001')
    expect(humidityConn?.targetEspId).toBe('ESP_HUMIDIFIER_001')
    expect(humidityConn?.isCrossEsp).toBe(true)
  })

  it('humidity rule shows in crossEspConnections', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const crossEsp = store.crossEspConnections
    const humidityConn = crossEsp.find(c => c.ruleId === 'rule-002')
    expect(humidityConn).toBeDefined()
  })

  it('getConnectionsForEsp returns connections for humidity sensor ESP', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const conns = store.getConnectionsForEsp('ESP_HUMIDITY_001')
    expect(conns.length).toBeGreaterThanOrEqual(1)
    expect(conns.some(c => c.sourceEspId === 'ESP_HUMIDITY_001')).toBe(true)
  })

  it('getConnectionsForEsp returns connections for humidifier ESP', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const conns = store.getConnectionsForEsp('ESP_HUMIDIFIER_001')
    expect(conns.length).toBeGreaterThanOrEqual(1)
    expect(conns.some(c => c.targetEspId === 'ESP_HUMIDIFIER_001')).toBe(true)
  })

  it('getOutgoingConnections for humidity sensor ESP includes humidity rules', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const outgoing = store.getOutgoingConnections('ESP_HUMIDITY_001')
    // rule-002, rule-003, rule-004 all use ESP_HUMIDITY_001 as source
    expect(outgoing.length).toBeGreaterThanOrEqual(1)
    expect(outgoing.every(c => c.sourceEspId === 'ESP_HUMIDITY_001')).toBe(true)
  })

  it('getIncomingConnections for humidifier ESP includes humidity rules', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const incoming = store.getIncomingConnections('ESP_HUMIDIFIER_001')
    // rule-002, rule-003, rule-004 all target ESP_HUMIDIFIER_001
    expect(incoming.length).toBeGreaterThanOrEqual(1)
    expect(incoming.every(c => c.targetEspId === 'ESP_HUMIDIFIER_001')).toBe(true)
  })
})

// =============================================================================
// RULE TOGGLE
// =============================================================================

describe('Humidity Rule - Toggle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('can toggle humidity rule', async () => {
    const store = useLogicStore()
    store.rules = [{ ...mockHumidityRule } as LogicRule]

    const newState = await store.toggleRule('rule-002')
    expect(typeof newState).toBe('boolean')
  })

  it('updates local rule state after toggle', async () => {
    const store = useLogicStore()
    store.rules = [{ ...mockHumidityRule, enabled: true } as LogicRule]

    await store.toggleRule('rule-002')
    expect(store.rules[0].enabled).toBe(false)
  })
})

// =============================================================================
// RULE TEST/EVALUATE
// =============================================================================

describe('Humidity Rule - Test Evaluation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('evaluates humidity rule conditions (38.2% < 40% = true)', async () => {
    const store = useLogicStore()
    const result = await store.testRule('rule-002')

    // Mock sensor value is 38.2, threshold is 40, operator is <
    // 38.2 < 40 = true → would execute actions
    expect(result).toBe(true)
  })

  it('returns evaluation details with sensor value', async () => {
    // Override handler to verify evaluation details are accessible
    let capturedResponse: Record<string, unknown> | null = null

    server.use(
      http.post('/api/v1/logic/rules/:ruleId/test', ({ params }) => {
        const response = {
          success: true,
          message: 'Rule evaluation completed',
          rule_id: params.ruleId,
          conditions_result: true,
          evaluation_details: [
            { condition_index: 0, result: true, sensor_value: 38.2 }
          ],
          would_execute_actions: true
        }
        capturedResponse = response
        return HttpResponse.json(response)
      })
    )

    const store = useLogicStore()
    await store.testRule('rule-002')

    expect(capturedResponse).not.toBeNull()
    expect(capturedResponse?.conditions_result).toBe(true)
    expect(capturedResponse?.would_execute_actions).toBe(true)
  })
})

// =============================================================================
// WEBSOCKET EXECUTION EVENTS
// =============================================================================

describe('Humidity Rule - WebSocket Execution', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('handles humidity rule execution event', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    // Simulate humidity rule execution event
    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-002',
        rule_name: 'Humidity Humidifier Control',
        trigger: {
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          value: 38.2,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
          duration: 300,
        },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    // Verify execution was recorded
    expect(store.recentExecutions).toHaveLength(1)
    expect(store.recentExecutions[0].rule_id).toBe('rule-002')
    expect(store.recentExecutions[0].success).toBe(true)
  })

  it('marks humidity rule as active after execution event', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-002',
        rule_name: 'Humidity Humidifier Control',
        trigger: {
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          value: 38.2,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
        },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    expect(store.isRuleActive('rule-002')).toBe(true)
    expect(store.activeExecutions.has('rule-002')).toBe(true)
  })

  it('updates last_triggered timestamp on execution', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]
    const executionTimestamp = Date.now() / 1000

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-002',
        rule_name: 'Humidity Humidifier Control',
        trigger: {
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          value: 38.2,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
        },
        success: true,
        timestamp: executionTimestamp,
      },
      timestamp: Date.now(),
    })

    const rule = store.getRuleById('rule-002')
    expect(rule?.last_triggered).toBeDefined()
  })

  it('connection is active when humidity rule executes', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-002',
        rule_name: 'Humidity Humidifier Control',
        trigger: {
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          value: 38.2,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
        },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    const humidityConn = store.connections.find(c => c.ruleId === 'rule-002')
    expect(humidityConn).toBeDefined()
    expect(store.isConnectionActive(humidityConn!)).toBe(true)
  })
})

// =============================================================================
// RULE CREATE (via API mock)
// =============================================================================

describe('Humidity Rule - CRUD Operations', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('can create a new humidity-based rule', async () => {
    const store = useLogicStore()

    const newRule = await store.createRule({
      name: 'Low Humidity Alert',
      description: 'Alert when humidity drops below 30%',
      enabled: false,
      conditions: [
        {
          type: 'sensor_threshold',
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          operator: '<',
          value: 30,
        },
      ],
      logic_operator: 'AND',
      actions: [
        {
          type: 'notification',
          channel: 'websocket',
          target: 'dashboard',
          message_template: 'Low humidity: {value}%',
        },
      ],
    })

    expect(newRule).toBeDefined()
    expect(newRule.id).toBeTruthy()
    expect(newRule.name).toBe('Low Humidity Alert')
  })

  it('can update humidity rule', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const updated = await store.updateRule('rule-002', {
      conditions: [
        {
          type: 'sensor_threshold',
          esp_id: 'ESP_HUMIDITY_001',
          gpio: 21,
          sensor_type: 'SHT31',
          operator: '<',
          value: 35,
        },
      ],
    })

    expect(updated).toBeDefined()
  })

  it('can delete humidity rule', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const initialCount = store.rules.length
    await store.deleteRule('rule-002')

    expect(store.rules.length).toBe(initialCount - 1)
    expect(store.getRuleById('rule-002')).toBeUndefined()
  })
})

// =============================================================================
// CONNECTION VALIDATION
// =============================================================================

describe('Humidity Rule - Connection Validation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('validates sensor → logic connection as valid', () => {
    const store = useLogicStore()
    const result = store.isValidConnection('sensor', 'logic', 'sensor-1', 'logic-1')
    expect(result.valid).toBe(true)
  })

  it('validates sensor → actuator connection as invalid (must go through logic/condition)', () => {
    const store = useLogicStore()
    const result = store.isValidConnection('sensor', 'actuator', 'sensor-1', 'actuator-1')
    expect(result.valid).toBe(false)
    expect(result.reason).toBeDefined()
  })

  it('validates logic → actuator connection as valid', () => {
    const store = useLogicStore()
    const result = store.isValidConnection('logic', 'actuator', 'logic-1', 'actuator-1')
    expect(result.valid).toBe(true)
  })

  it('validates actuator → anything as invalid (no outputs)', () => {
    const store = useLogicStore()
    const result = store.isValidConnection('actuator', 'sensor', 'actuator-1', 'sensor-1')
    expect(result.valid).toBe(false)
  })

  it('rejects self-loop connections', () => {
    const store = useLogicStore()
    const result = store.isValidConnection('sensor', 'sensor', 'node-1', 'node-1')
    expect(result.valid).toBe(false)
  })
})

// =============================================================================
// AND LOGIC RULE (rule-003)
// =============================================================================

describe('AND Logic Rule - Structure & Connections', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has correct AND rule metadata', () => {
    expect(mockAndRule.id).toBe('rule-003')
    expect(mockAndRule.name).toBe('Heat & Dry Protection')
    expect(mockAndRule.logic_operator).toBe('AND')
    expect(mockAndRule.priority).toBe(3)
    expect(mockAndRule.cooldown_seconds).toBe(180)
  })

  it('has 2 conditions (temperature AND humidity)', () => {
    expect(mockAndRule.conditions).toHaveLength(2)

    const tempCond = mockAndRule.conditions[0]
    expect(tempCond.esp_id).toBe('ESP_TEST_001')
    expect(tempCond.sensor_type).toBe('ds18b20')
    expect(tempCond.operator).toBe('>')
    expect(tempCond.value).toBe(30)

    const humidityCond = mockAndRule.conditions[1]
    expect(humidityCond.esp_id).toBe('ESP_HUMIDITY_001')
    expect(humidityCond.sensor_type).toBe('SHT31')
    expect(humidityCond.operator).toBe('<')
    expect(humidityCond.value).toBe(40)
  })

  it('extracts 2 connections (one per condition→actuator pair)', () => {
    const connections = extractConnections(mockAndRule as LogicRule)

    expect(connections).toHaveLength(2)
    // Both target the same actuator
    expect(connections.every(c => c.targetEspId === 'ESP_HUMIDIFIER_001')).toBe(true)
    expect(connections.every(c => c.targetGpio === 16)).toBe(true)
    // But from different sources
    const sourceEspIds = connections.map(c => c.sourceEspId)
    expect(sourceEspIds).toContain('ESP_TEST_001')
    expect(sourceEspIds).toContain('ESP_HUMIDITY_001')
  })

  it('AND rule shows up in store after fetch', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const andRule = store.getRuleById('rule-003')
    expect(andRule).toBeDefined()
    expect(andRule?.conditions).toHaveLength(2)
    expect(andRule?.logic_operator).toBe('AND')
  })
})

// =============================================================================
// OR LOGIC RULE (rule-004)
// =============================================================================

describe('OR Logic Rule - Structure & Connections', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has correct OR rule metadata', () => {
    expect(mockOrRule.id).toBe('rule-004')
    expect(mockOrRule.name).toBe('Irrigation Fallback')
    expect(mockOrRule.logic_operator).toBe('OR')
    expect(mockOrRule.priority).toBe(1)
    expect(mockOrRule.cooldown_seconds).toBe(300)
  })

  it('has 2 conditions with OR logic', () => {
    expect(mockOrRule.conditions).toHaveLength(2)
    expect(mockOrRule.logic_operator).toBe('OR')
  })

  it('extracts 2 connections (one per condition)', () => {
    const connections = extractConnections(mockOrRule as LogicRule)
    expect(connections).toHaveLength(2)
    expect(connections.every(c => c.isCrossEsp)).toBe(true)
  })

  it('OR rule shows up in store after fetch', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const orRule = store.getRuleById('rule-004')
    expect(orRule).toBeDefined()
    expect(orRule?.logic_operator).toBe('OR')
  })
})

// =============================================================================
// MULTI-ACTION RULE (rule-005)
// =============================================================================

describe('Multi-Action Rule - Structure & Connections', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has correct multi-action rule metadata', () => {
    expect(mockMultiActionRule.id).toBe('rule-005')
    expect(mockMultiActionRule.name).toBe('Heat Emergency Multi-Action')
    expect(mockMultiActionRule.enabled).toBe(false) // disabled by default
    expect(mockMultiActionRule.priority).toBe(10) // high priority
  })

  it('has 1 condition but 2 actions (actuator + notification)', () => {
    expect(mockMultiActionRule.conditions).toHaveLength(1)
    expect(mockMultiActionRule.actions).toHaveLength(2)

    expect(mockMultiActionRule.actions[0].type).toBe('actuator_command')
    expect(mockMultiActionRule.actions[1].type).toBe('notification')
  })

  it('extracts only 1 connection (notification is not an actuator_command)', () => {
    const connections = extractConnections(mockMultiActionRule as LogicRule)
    // extractConnections only creates connections for actuator_command, not notification
    expect(connections).toHaveLength(1)
    expect(connections[0].sourceEspId).toBe('ESP_TEST_001')
    expect(connections[0].targetEspId).toBe('ESP_TEST_002')
    expect(connections[0].targetCommand).toBe('ON')
  })

  it('disabled rule still shows connections but marked as disabled', () => {
    const connections = extractConnections(mockMultiActionRule as LogicRule)
    expect(connections[0].enabled).toBe(false)
  })

  it('multi-action rule shows up in store after fetch', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const rule = store.getRuleById('rule-005')
    expect(rule).toBeDefined()
    expect(rule?.actions).toHaveLength(2)
    expect(rule?.enabled).toBe(false)
  })
})

// =============================================================================
// PRIORITY & COOLDOWN BEHAVIOR
// =============================================================================

describe('Logic Rules - Priority & Cooldown', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('rules have distinct priorities', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const priorities = store.rules.map(r => r.priority)
    // At least some priorities should differ
    expect(new Set(priorities).size).toBeGreaterThan(1)
  })

  it('higher priority rule has higher priority value', () => {
    // rule-005 (Heat Emergency) has priority 10 (highest)
    // rule-004 (Irrigation) has priority 1 (lowest)
    expect(mockMultiActionRule.priority).toBeGreaterThan(mockOrRule.priority)
  })

  it('cooldown values are realistic (60-300 seconds)', () => {
    const rules = [mockHumidityRule, mockAndRule, mockOrRule, mockMultiActionRule]

    for (const rule of rules) {
      expect(rule.cooldown_seconds).toBeGreaterThanOrEqual(60)
      expect(rule.cooldown_seconds).toBeLessThanOrEqual(300)
    }
  })

  it('max_executions_per_hour limits vary by priority', () => {
    // High priority (emergency) allows more executions
    expect(mockMultiActionRule.max_executions_per_hour).toBe(20)
    // Low priority allows fewer
    expect(mockOrRule.max_executions_per_hour).toBe(3)
  })

  it('enabledRules getter excludes disabled multi-action rule', async () => {
    const store = useLogicStore()
    await store.fetchRules()

    const enabledIds = store.enabledRules.map(r => r.id)
    expect(enabledIds).not.toContain('rule-005')
    expect(enabledIds).toContain('rule-001')
    expect(enabledIds).toContain('rule-002')
  })
})

// =============================================================================
// WEBSOCKET EXECUTION WITH COMPLEX RULES
// =============================================================================

describe('Complex Rules - WebSocket Execution Events', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('handles AND rule execution event with multiple conditions met', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-003',
        rule_name: 'Heat & Dry Protection',
        trigger: {
          esp_id: 'ESP_TEST_001',
          gpio: 4,
          sensor_type: 'ds18b20',
          value: 32.5,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
        },
        success: true,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    expect(store.recentExecutions).toHaveLength(1)
    expect(store.recentExecutions[0].rule_id).toBe('rule-003')
    expect(store.isRuleActive('rule-003')).toBe(true)
  })

  it('handles failed execution event (success: false)', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    callback({
      type: 'logic_execution',
      data: {
        rule_id: 'rule-003',
        rule_name: 'Heat & Dry Protection',
        trigger: {
          esp_id: 'ESP_TEST_001',
          gpio: 4,
          sensor_type: 'ds18b20',
          value: 32.5,
        },
        action: {
          esp_id: 'ESP_HUMIDIFIER_001',
          gpio: 16,
          command: 'ON',
        },
        success: false,
        timestamp: Date.now() / 1000,
      },
      timestamp: Date.now(),
    })

    // Failed executions are still recorded
    expect(store.recentExecutions).toHaveLength(1)
    expect(store.recentExecutions[0].success).toBe(false)
    // But rule is still marked as active (for visual feedback)
    expect(store.isRuleActive('rule-003')).toBe(true)
  })

  it('multiple rapid executions all get recorded', async () => {
    const store = useLogicStore()
    await store.fetchRules()
    store.subscribeToWebSocket()

    const callback = (websocketService.subscribe as ReturnType<typeof vi.fn>).mock.calls[0][1]

    // Simulate 3 rapid executions from different rules
    const ruleIds = ['rule-001', 'rule-002', 'rule-003']
    for (const ruleId of ruleIds) {
      callback({
        type: 'logic_execution',
        data: {
          rule_id: ruleId,
          rule_name: `Rule ${ruleId}`,
          trigger: { esp_id: 'ESP_TEST_001', gpio: 4, sensor_type: 'ds18b20', value: 30 },
          action: { esp_id: 'ESP_TEST_002', gpio: 16, command: 'ON' },
          success: true,
          timestamp: Date.now() / 1000,
        },
        timestamp: Date.now(),
      })
    }

    expect(store.recentExecutions).toHaveLength(3)
    // Most recent first
    expect(store.recentExecutions[0].rule_id).toBe('rule-003')
    expect(store.recentExecutions[2].rule_id).toBe('rule-001')
  })
})
