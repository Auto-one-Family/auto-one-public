/**
 * AUT-1305 Teil 1: UND/ODER Stabilitaet
 *
 * Belegt, dass mehrere Bedingungen unter EINEM Operator-Node (logic_operator
 * AND/OR) im RuleFlowEditor-Roundtrip (rule -> ruleToGraph -> graphToRuleData,
 * inkl. simuliertem Save+Reload) zuverlaessig kombinieren: keine verlorenen
 * Bedingungen, kein verlorener AND/OR-Wert, Toggle ueber updateNodeData bleibt
 * stabil.
 *
 * @see El Frontend/src/components/rules/RuleFlowEditor.vue (ruleToGraph, graphToRuleData)
 * @see El Servador/god_kaiser_server/src/services/logic_engine.py:1063-1064
 *   (Server wrapt flache trigger_conditions[] + logic_operator als compound AND/OR)
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
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void
  loadFromRuleData: (ruleData: { conditions: LogicCondition[]; actions: LogicAction[]; logic_operator?: string }) => void
}

function buildRule(logicOperator: 'AND' | 'OR', conditionCount: number): LogicRule {
  const sensorTypes = ['pH', 'EC', 'DS18B20']
  const conditions: SensorCondition[] = Array.from({ length: conditionCount }, (_, i) => ({
    type: 'sensor',
    esp_id: `esp-${i}`,
    gpio: i + 1,
    sensor_type: sensorTypes[i] || 'DS18B20',
    operator: '>',
    value: 10 + i,
  }))

  const action: ActuatorAction = {
    type: 'actuator',
    esp_id: 'esp-actuator',
    gpio: 99,
    command: 'ON',
    value: 1.0,
  }

  return {
    id: 'rule-1',
    name: 'Test-Regel',
    enabled: true,
    conditions,
    logic_operator: logicOperator,
    actions: [action],
    priority: 5,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

describe('RuleFlowEditor AND/OR-Stabilitaet (AUT-1305)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it.each([
    ['AND', 2],
    ['AND', 3],
    ['OR', 2],
    ['OR', 3],
  ] as const)(
    'roundtrip erhaelt %s-Operator und alle %i Bedingungen unter EINEM Operator-Node (rule -> graph -> rule)',
    async (logicOperator, conditionCount) => {
      const rule = buildRule(logicOperator, conditionCount)

      const wrapper = mount(RuleFlowEditor, { props: { rule } })
      await flushPromises()

      const vm = wrapper.vm as unknown as ExposedEditor
      const graphData = vm.graphToRuleData()

      // Keine verlorenen/verdoppelten Bedingungen.
      expect(graphData.conditions).toHaveLength(conditionCount)
      expect(graphData.conditionNodeIds).toHaveLength(conditionCount)
      // Jede Bedingung hat einen eigenen Node (kein Konflations-/Verlust-Bug).
      expect(new Set(graphData.conditionNodeIds).size).toBe(conditionCount)

      // Der AND/OR-Operator bleibt exakt erhalten.
      expect(graphData.logic_operator).toBe(logicOperator)

      // Kein Datenverlust: jeder urspruengliche sensor_type taucht wieder auf
      // (Reihenfolge ist fuer AND/OR-Semantik irrelevant, daher sortierter Vergleich).
      const originalTypes = rule.conditions.map((c) => (c as SensorCondition).sensor_type).sort()
      const roundtripTypes = (graphData.conditions as SensorCondition[])
        .map((c) => c.sensor_type)
        .sort()
      expect(roundtripTypes).toEqual(originalTypes)

      // ---- Zweite Runde: simuliert Save -> Server-Antwort -> Reload -> erneutes Speichern ----
      const reloadedRule: LogicRule = {
        ...rule,
        conditions: graphData.conditions,
        logic_operator: graphData.logic_operator,
        actions: graphData.actions,
      }
      await wrapper.setProps({ rule: reloadedRule })
      await flushPromises()

      const graphData2 = vm.graphToRuleData()
      expect(graphData2.conditions).toHaveLength(conditionCount)
      expect(graphData2.logic_operator).toBe(logicOperator)
      expect(
        (graphData2.conditions as SensorCondition[]).map((c) => c.sensor_type).sort()
      ).toEqual(originalTypes)
    }
  )

  it('AND->OR Toggle am Operator-Node (RuleConfigPanel-Pfad via updateNodeData) bleibt beim naechsten Speichern erhalten', async () => {
    const rule = buildRule('AND', 3)
    const wrapper = mount(RuleFlowEditor, { props: { rule } })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor

    // Der Operator-Node hat beim Aufbau aus rule.conditions immer die deterministische ID
    // 'logic-0' (ruleToGraph erzeugt IMMER genau einen Operator-Node fuer die gesamte Regel).
    vm.updateNodeData('logic-0', { operator: 'OR' })
    await flushPromises()

    const graphData = vm.graphToRuleData()
    expect(graphData.logic_operator).toBe('OR')
    // Die 3 Bedingungen bleiben durch den reinen Operator-Toggle unberuehrt.
    expect(graphData.conditions).toHaveLength(3)
  })

  it('pH-Senken-Pfad (einfache Hysterese ohne Operator-Node-Kombination) bleibt beim Roundtrip unberuehrt', async () => {
    // AUT-1305 Deliverable: bestaetigt, dass der bestehende einfache Hysterese-Pfad
    // (1 Bedingung, kein zusaetzlicher Operator-Kombinationsfall) durch diese Aenderung
    // nicht angefasst wird — reiner Bestandsschutz-Test, kein neuer Regler.
    const rule: LogicRule = {
      id: 'rule-ph-down',
      name: 'pH-Senken',
      enabled: true,
      conditions: [
        {
          type: 'hysteresis',
          esp_id: 'esp-ph',
          gpio: 3,
          sensor_type: 'pH',
          activate_above: 6.5,
          deactivate_below: 6.0,
        },
      ],
      logic_operator: 'AND',
      actions: [
        {
          type: 'actuator',
          esp_id: 'esp-pump',
          gpio: 11,
          command: 'ON',
          value: 1.0,
          dose_ml: 5,
        },
      ],
      priority: 5,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    const wrapper = mount(RuleFlowEditor, { props: { rule } })
    await flushPromises()

    const vm = wrapper.vm as unknown as ExposedEditor
    const graphData = vm.graphToRuleData()

    expect(graphData.conditions).toHaveLength(1)
    expect(graphData.conditions[0]).toMatchObject({
      type: 'hysteresis',
      activate_above: 6.5,
      deactivate_below: 6.0,
    })
    expect(graphData.actions[0]).toMatchObject({ type: 'actuator', dose_ml: 5 })
  })
})
