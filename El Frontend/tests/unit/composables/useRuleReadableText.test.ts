import { describe, it, expect } from 'vitest'
import { getRuleReadableText } from '@/composables/useRuleReadableText'
import type { LogicRule, ActuatorAction, SensorCondition } from '@/types/logic'

function baseRule(overrides: Partial<LogicRule>): LogicRule {
  return {
    id: 'r1',
    name: 'Test',
    enabled: true,
    conditions: [],
    actions: [],
    logic_operator: 'AND',
    priority: 100,
    cooldown_seconds: 0,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('useRuleReadableText (AUT-1318)', () => {
  it('should list each routed action with its condition refs', () => {
    const c0: SensorCondition = {
      type: 'sensor',
      esp_id: 'e',
      gpio: 27,
      sensor_type: 'liquid_level',
      operator: '==',
      value: 0,
    }
    const c1: SensorCondition = {
      type: 'sensor',
      esp_id: 'e',
      gpio: 17,
      sensor_type: 'liquid_level',
      operator: '==',
      value: 1,
    }
    const on: ActuatorAction = {
      type: 'actuator',
      esp_id: 'e',
      gpio: 25,
      command: 'ON',
      value: 1,
      condition_refs: [0],
    }
    const off: ActuatorAction = {
      type: 'actuator',
      esp_id: 'e',
      gpio: 25,
      command: 'OFF',
      value: 0,
      condition_refs: [1],
    }
    const text = getRuleReadableText(
      baseRule({ conditions: [c0, c1], actions: [off, on] }),
    )
    expect(text).toContain('→ Aktor GPIO 25 AUS')
    expect(text).toContain('→ Aktor GPIO 25 AN')
    expect(text).toContain(';')
  })

  it('should list all legacy actuators in the suffix', () => {
    const c0: SensorCondition = {
      type: 'sensor',
      esp_id: 'e',
      gpio: 1,
      sensor_type: 'pH',
      operator: '>',
      value: 7,
    }
    const on: ActuatorAction = {
      type: 'actuator',
      esp_id: 'e',
      gpio: 25,
      command: 'ON',
      value: 1,
    }
    const off: ActuatorAction = {
      type: 'actuator',
      esp_id: 'e',
      gpio: 26,
      command: 'OFF',
      value: 0,
    }
    const text = getRuleReadableText(
      baseRule({ conditions: [c0], actions: [on, off] }),
    )
    expect(text).toContain('GPIO 25 AN')
    expect(text).toContain('GPIO 26 AUS')
  })
})
