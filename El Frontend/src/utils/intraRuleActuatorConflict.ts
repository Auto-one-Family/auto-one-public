/**
 * AUT-1318 (R-S4): Intra-rule ON+OFF on the same actuator GPIO.
 *
 * Routing pair (OK): opposing commands with different condition_refs keys.
 * Real conflict (warn): opposing commands with the same / empty refs key
 * (both under the global gate or the same per-action subset).
 *
 * Analog to inter-rule warnings in validator.py:_check_actuator_conflicts,
 * but scoped to a single rule's actions list.
 */

import type { ActuatorAction, LogicAction } from '@/types/logic'

const OPPOSING = new Set(['ON', 'OFF'])

function isActuator(action: LogicAction): action is ActuatorAction {
  return action.type === 'actuator' || action.type === 'actuator_command'
}

/** Stable key for comparing condition_refs sets (null/[] → global gate). */
export function conditionRefsKey(refs: number[] | null | undefined): string {
  if (!refs || refs.length === 0) return '__global__'
  return [...refs].sort((a, b) => a - b).join(',')
}

export function detectIntraRuleActuatorConflicts(actions: LogicAction[]): string[] {
  const warnings: string[] = []
  const byTarget = new Map<string, ActuatorAction[]>()

  for (const action of actions) {
    if (!isActuator(action)) continue
    if (!action.esp_id || !action.gpio) continue
    const key = `${action.esp_id}:${action.gpio}`
    const list = byTarget.get(key) ?? []
    list.push(action)
    byTarget.set(key, list)
  }

  for (const [target, group] of byTarget) {
    if (group.length < 2) continue

    const ons = group.filter((a) => String(a.command).toUpperCase() === 'ON')
    const offs = group.filter((a) => String(a.command).toUpperCase() === 'OFF')
    if (ons.length === 0 || offs.length === 0) continue

    // Compare every ON against every OFF on this target
    for (const on of ons) {
      for (const off of offs) {
        const onKey = conditionRefsKey(on.condition_refs)
        const offKey = conditionRefsKey(off.condition_refs)
        if (onKey === offKey) {
          const gateLabel =
            onKey === '__global__'
              ? 'demselben globalen Gate (keine/identische condition_refs)'
              : `denselben condition_refs [${onKey}]`
          warnings.push(
            `Intra-rule Konflikt: ${target} hat ON und OFF unter ${gateLabel}. ` +
              `Für Start/Stopp-Routing unterschiedliche condition_refs setzen.`,
          )
        }
        // Different keys → intentional routing pair; no warning.
        void OPPOSING
      }
    }
  }

  return warnings
}
