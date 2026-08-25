import { describe, it, expect } from 'vitest'
import {
  conditionRefsKey,
  detectIntraRuleActuatorConflicts,
} from '@/utils/intraRuleActuatorConflict'
import type { ActuatorAction, LogicAction } from '@/types/logic'

function actuator(
  command: 'ON' | 'OFF',
  refs?: number[] | null,
  gpio = 25,
): ActuatorAction {
  return {
    type: 'actuator',
    esp_id: 'esp-1',
    gpio,
    command,
    value: command === 'OFF' ? 0 : 1,
    ...(refs !== undefined ? { condition_refs: refs } : {}),
  }
}

describe('intraRuleActuatorConflict', () => {
  it('should map empty/null refs to global key', () => {
    expect(conditionRefsKey(null)).toBe('__global__')
    expect(conditionRefsKey([])).toBe('__global__')
    expect(conditionRefsKey(undefined)).toBe('__global__')
    expect(conditionRefsKey([2, 0, 1])).toBe('0,1,2')
  })

  it('should treat ON+OFF with different refs as routing pair (no warning)', () => {
    const actions: LogicAction[] = [
      actuator('ON', [0]),
      actuator('OFF', [1]),
    ]
    expect(detectIntraRuleActuatorConflicts(actions)).toEqual([])
  })

  it('should warn when ON+OFF share global gate', () => {
    const actions: LogicAction[] = [actuator('ON'), actuator('OFF')]
    const warnings = detectIntraRuleActuatorConflicts(actions)
    expect(warnings).toHaveLength(1)
    expect(warnings[0]).toContain('Intra-rule Konflikt')
    expect(warnings[0]).toContain('esp-1:25')
  })

  it('should warn when ON+OFF share the same condition_refs', () => {
    const actions: LogicAction[] = [
      actuator('ON', [0, 2]),
      actuator('OFF', [2, 0]),
    ]
    const warnings = detectIntraRuleActuatorConflicts(actions)
    expect(warnings).toHaveLength(1)
    expect(warnings[0]).toContain('0,2')
  })

  it('should ignore different GPIOs', () => {
    const actions: LogicAction[] = [
      actuator('ON', null, 25),
      actuator('OFF', null, 26),
    ]
    expect(detectIntraRuleActuatorConflicts(actions)).toEqual([])
  })
})
