/**
 * AUT-1399 [M-5-Nachschärfung]: Mess-Bindung (sensor_diff umgewidmet)
 * — Speicherung nur measure_bindings; Kante erzeugt keinen condition_ref.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import RuleFlowEditor from '@/components/rules/RuleFlowEditor.vue'
import type { LogicRule, LogicCondition, LogicAction, ActuatorAction } from '@/types/logic'
import type { MeasureBinding } from '@/types/measureBinding'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        device_id: 'ESP_FLOW',
        id: 'uuid-flow',
        name: 'Nachfüll-ESP',
        sensors: [
          { gpio: 14, sensor_type: 'flow', name: 'Durchflusssensor', config_id: 'cfg-flow' },
        ],
      },
    ],
    getDeviceId: (d: { device_id?: string; esp_id?: string; id?: string }) =>
      d.device_id || d.esp_id || d.id || '',
  }),
}))

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    pushToHistory: vi.fn(),
    isValidConnection: () => ({ valid: true }),
    isRuleActive: () => false,
    undo: vi.fn(),
    redo: vi.fn(),
    canUndo: false,
    canRedo: false,
  }),
}))

interface GraphToRuleDataResult {
  conditions: LogicCondition[]
  actions: LogicAction[]
  logic_operator: 'AND' | 'OR'
  conditionNodeIds: string[]
  actionNodeIds: string[]
  measure_bindings: MeasureBinding[]
}

interface ExposedEditor {
  graphToRuleData: () => GraphToRuleDataResult
  loadFromRuleData: (ruleData: {
    conditions: LogicCondition[]
    actions: LogicAction[]
    logic_operator?: string
  }) => void
  addEdgeForTest: (sourceId: string, targetId: string) => void
}

function baseRule(overrides: Partial<LogicRule> = {}): LogicRule {
  return {
    id: 'rule-mb',
    name: 'Frischwasser',
    enabled: true,
    conditions: [
      {
        type: 'sensor',
        esp_id: 'ESP_FLOW',
        gpio: 27,
        sensor_type: 'liquid_level',
        operator: '==',
        value: 0,
      },
    ],
    actions: [
      {
        type: 'actuator',
        esp_id: 'ESP_FLOW',
        gpio: 25,
        command: 'ON',
        value: 1,
      },
    ],
    logic_operator: 'AND',
    priority: 100,
    cooldown_seconds: 0,
    created_at: '',
    updated_at: '',
    rule_metadata: {
      measure_bindings: [
        {
          sensor_refs: [{ esp_id: 'ESP_FLOW', gpio: 14, sensor_type: 'flow' }],
          hooks: ['on_start', 'on_complete'],
          formula_id: 'difference',
          formula_params: {},
          output_target: 'execution_metadata',
        },
      ],
    },
    ...overrides,
  }
}

describe('RuleFlowEditor measure binding (AUT-1399)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should persist Mess-Bindung only in measure_bindings — never trigger_conditions/sensor_diff condition', async () => {
    const wrapper = mount(RuleFlowEditor, {
      props: { rule: baseRule() },
      attachTo: document.body,
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor
    const data = vm.graphToRuleData()

    expect(data.measure_bindings).toHaveLength(1)
    expect(data.measure_bindings[0].sensor_refs[0]?.sensor_type).toBe('flow')
    expect(data.measure_bindings[0].formula_id).toBe('difference')

    // Negativ: kein sensor_diff in conditions / kein Trigger-Pfad
    expect(data.conditions.every((c) => c.type !== 'sensor_diff')).toBe(true)
    expect(JSON.stringify(data.conditions)).not.toContain('sensor_diff')
    expect(data).not.toHaveProperty('trigger_conditions')

    wrapper.unmount()
  })

  it('should not create condition_refs when Mess-Bindung node is edge-connected to an action', async () => {
    const wrapper = mount(RuleFlowEditor, {
      props: { rule: baseRule() },
      attachTo: document.body,
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor

    // Nach Load: measure-0 + action-0 (ruleToGraph)
    vm.addEdgeForTest('measure-0', 'action-0')
    await flushPromises()

    const data = vm.graphToRuleData()
    const act = data.actions.find((a) => a.type === 'actuator') as ActuatorAction
    expect(act).toBeTruthy()
    // Explizit: gezogene Kante erzeugt KEINEN condition_ref
    expect(act.condition_refs == null || act.condition_refs.length === 0).toBe(true)
    expect(data.conditions.every((c) => c.type !== 'sensor_diff')).toBe(true)
    expect(data.measure_bindings).toHaveLength(1)
    expect(data.conditionNodeIds).not.toContain('measure-0')

    // Kontrast: echte Sensor-Bedingung → Aktion DARF refs erzeugen
    vm.addEdgeForTest('cond-0', 'action-0')
    await flushPromises()
    const withCondEdge = vm.graphToRuleData()
    const act2 = withCondEdge.actions.find((a) => a.type === 'actuator') as ActuatorAction
    expect(act2.condition_refs).toEqual([0])
    // Mess-Bindung bleibt trotzdem außerhalb conditions
    expect(withCondEdge.conditions.every((c) => c.type !== 'sensor_diff')).toBe(true)
    expect(withCondEdge.measure_bindings).toHaveLength(1)

    wrapper.unmount()
  })

  it('should exclude sensor_diff from conditionNodeIds so edges cannot become condition_refs', async () => {
    const wrapper = mount(RuleFlowEditor, {
      props: { rule: baseRule() },
      attachTo: document.body,
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor
    const data = vm.graphToRuleData()

    expect(data.measure_bindings).toHaveLength(1)
    expect(data.conditionNodeIds.some((id) => id.startsWith('measure'))).toBe(false)
    // Real sensor condition remains a condition
    expect(data.conditions.some((c) => c.type === 'sensor')).toBe(true)
    expect(data.conditions.some((c) => c.type === 'sensor_diff')).toBe(false)

    wrapper.unmount()
  })
})
