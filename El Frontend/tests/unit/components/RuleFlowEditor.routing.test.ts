/**
 * AUT-1318 (R-S4): Canvas edges carry condition_refs semantics.
 * Round-trip: rule with refs → ruleToGraph → graphToRuleData preserves refs.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import RuleFlowEditor from '@/components/rules/RuleFlowEditor.vue'
import type { LogicRule, SensorCondition, ActuatorAction, LogicCondition, LogicAction } from '@/types/logic'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [],
    getDeviceId: (d: { esp_id?: string; id?: string }) => d.esp_id || d.id || '',
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
}

interface ExposedEditor {
  graphToRuleData: () => GraphToRuleDataResult
  loadFromRuleData: (ruleData: {
    conditions: LogicCondition[]
    actions: LogicAction[]
    logic_operator?: string
  }) => void
}

function buildFall1Rule(): LogicRule {
  const conditions: SensorCondition[] = [
    {
      type: 'sensor',
      esp_id: 'esp-fw',
      gpio: 27,
      sensor_type: 'liquid_level',
      operator: '==',
      value: 0,
    },
    {
      type: 'sensor',
      esp_id: 'esp-fw',
      gpio: 17,
      sensor_type: 'liquid_level',
      operator: '==',
      value: 1,
    },
  ]
  const actions: ActuatorAction[] = [
    {
      type: 'actuator',
      esp_id: 'esp-fw',
      gpio: 25,
      command: 'ON',
      value: 1,
      condition_refs: [0],
    },
    {
      type: 'actuator',
      esp_id: 'esp-fw',
      gpio: 25,
      command: 'OFF',
      value: 0,
      condition_refs: [1],
      is_safety_critical: true,
    },
  ]
  return {
    id: 'frischwasser',
    name: 'Frischwasser',
    enabled: true,
    conditions,
    actions,
    logic_operator: 'AND',
    priority: 100,
    cooldown_seconds: 0,
    created_at: '',
    updated_at: '',
  }
}

describe('RuleFlowEditor routing (AUT-1318)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should round-trip condition_refs via Save→Reload graph path', async () => {
    const rule = buildFall1Rule()
    const wrapper = mount(RuleFlowEditor, {
      props: { rule },
      attachTo: document.body,
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor
    const first = vm.graphToRuleData()
    expect(first.actions).toHaveLength(2)

    const onAction = first.actions.find(
      (a) => a.type === 'actuator' && (a as ActuatorAction).command === 'ON',
    ) as ActuatorAction
    const offAction = first.actions.find(
      (a) => a.type === 'actuator' && (a as ActuatorAction).command === 'OFF',
    ) as ActuatorAction

    expect(onAction.condition_refs).toEqual([0])
    expect(offAction.condition_refs).toEqual([1])
    expect(offAction.is_safety_critical).toBe(true)

    // Simulate reload from saved payload
    vm.loadFromRuleData({
      conditions: first.conditions,
      actions: first.actions,
      logic_operator: first.logic_operator,
    })
    await flushPromises()

    const second = vm.graphToRuleData()
    const on2 = second.actions.find(
      (a) => a.type === 'actuator' && (a as ActuatorAction).command === 'ON',
    ) as ActuatorAction
    const off2 = second.actions.find(
      (a) => a.type === 'actuator' && (a as ActuatorAction).command === 'OFF',
    ) as ActuatorAction

    expect(on2.condition_refs).toEqual([0])
    expect(off2.condition_refs).toEqual([1])

    wrapper.unmount()
  })

  it('should keep legacy flat rules without condition_refs', async () => {
    const rule: LogicRule = {
      id: 'legacy',
      name: 'Legacy',
      enabled: true,
      conditions: [
        {
          type: 'sensor',
          esp_id: 'e',
          gpio: 1,
          sensor_type: 'pH',
          operator: '>',
          value: 7,
        },
      ],
      actions: [
        {
          type: 'actuator',
          esp_id: 'e',
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
    }

    const wrapper = mount(RuleFlowEditor, {
      props: { rule },
      attachTo: document.body,
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor
    const data = vm.graphToRuleData()
    expect(data.actions).toHaveLength(1)
    expect(data.actions[0].condition_refs == null || data.actions[0].condition_refs?.length === 0).toBe(true)

    wrapper.unmount()
  })
})
