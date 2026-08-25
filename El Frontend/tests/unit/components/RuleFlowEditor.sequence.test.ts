/**
 * AUT-1306 C5: Sequenz-Roundtrip bleibt 1 sequence-Aktion mit geordneten Schritten.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import RuleFlowEditor from '@/components/rules/RuleFlowEditor.vue'
import type {
  LogicRule,
  SensorCondition,
  SequenceAction,
  LogicCondition,
  LogicAction,
} from '@/types/logic'

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
}

interface ExposedEditor {
  graphToRuleData: () => GraphToRuleDataResult
  loadFromRuleData: (ruleData: {
    conditions: LogicCondition[]
    actions: LogicAction[]
    logic_operator?: string
  }) => void
}

function buildSequenceRule(): LogicRule {
  const condition: SensorCondition = {
    type: 'sensor',
    esp_id: 'esp-1',
    gpio: 1,
    sensor_type: 'pH',
    operator: '<',
    value: 6.0,
  }

  const sequence: SequenceAction = {
    type: 'sequence',
    abort_on_failure: true,
    max_duration_seconds: 300,
    steps: [
      {
        name: 'Pumpe A',
        action: {
          type: 'actuator',
          esp_id: 'esp-pump',
          gpio: 12,
          command: 'ON',
          value: 1.0,
          duration_seconds: 5,
          dose_ml: 9,
        },
        delay_before_seconds: 2,
      },
      { name: 'Mischzeit', delay_seconds: 30, on_failure: 'abort' },
      {
        name: 'Pumpe B',
        action: {
          type: 'actuator',
          esp_id: 'esp-pump',
          gpio: 16,
          command: 'ON',
          value: 1.0,
          duration_seconds: 5,
        },
        delay_after_seconds: 1,
      },
    ],
  }

  return {
    id: 'seq-rule-1',
    name: 'Sequenz-Test',
    enabled: true,
    priority: 50,
    cooldown_seconds: 0,
    logic_operator: 'AND',
    conditions: [condition],
    actions: [sequence],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

describe('<RuleFlowEditor> sequence', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should roundtrip one sequence action with ordered steps and dose_ml', async () => {
    const rule = buildSequenceRule()
    const wrapper = mount(RuleFlowEditor, { props: { rule } })
    await flushPromises()

    const editor = wrapper.vm as unknown as ExposedEditor
    const first = editor.graphToRuleData()
    expect(first.actions).toHaveLength(1)
    expect(first.actions[0].type).toBe('sequence')

    const seq = first.actions[0] as SequenceAction
    expect(seq.steps).toHaveLength(3)
    expect(seq.steps[0].action).toMatchObject({ type: 'actuator', gpio: 12, dose_ml: 9 })
    expect(seq.steps[0].delay_before_seconds).toBe(2)
    expect(seq.steps[1].delay_seconds).toBe(30)
    expect(seq.steps[2].action).toMatchObject({ type: 'actuator', gpio: 16 })
    expect(seq.steps[2].delay_after_seconds).toBe(1)

    // Reload via setProps (Save → Server → Reload) — still exactly one sequence action
    await wrapper.setProps({
      rule: {
        ...rule,
        conditions: first.conditions,
        actions: first.actions,
        logic_operator: first.logic_operator,
      },
    })
    await flushPromises()

    const second = editor.graphToRuleData()
    expect(second.actions.filter((a) => a.type === 'sequence')).toHaveLength(1)
    const again = second.actions[0] as SequenceAction
    expect(
      again.steps.map((s) =>
        s.delay_seconds != null ? s.delay_seconds : (s.action as { gpio?: number } | undefined)?.gpio,
      ),
    ).toEqual([12, 30, 16])
    expect(again.steps[0].action).toMatchObject({ dose_ml: 9 })
    expect(again.steps[0].delay_before_seconds).toBe(2)
  })
})
