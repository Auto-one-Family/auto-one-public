import { computed } from 'vue'
import type {
  LogicRule,
  SensorCondition,
  ActuatorAction,
  HysteresisCondition,
  TimeCondition,
  CompoundCondition,
  SensorDiffCondition,
} from '@/types/logic'
import { getSensorLabel, getSensorUnit } from '@/utils/sensorDefaults'

// German operator labels for human-readable rule summary
const OPERATOR_LABELS: Record<string, string> = {
  '>': 'über',
  '>=': 'mindestens',
  '<': 'unter',
  '<=': 'höchstens',
  '==': 'gleich',
  '!=': 'ungleich',
  between: 'zwischen',
}

// German command labels for actuator actions
const COMMAND_LABELS: Record<string, string> = {
  ON: 'AN',
  OFF: 'AUS',
  PWM: 'PWM',
  TOGGLE: 'umschalten',
}

const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function formatTimeRange(tc: TimeCondition): string {
  const sm = tc.start_minute ?? 0
  const em = tc.end_minute ?? 0
  const range = `${String(tc.start_hour).padStart(2, '0')}:${String(sm).padStart(2, '0')}–${String(tc.end_hour).padStart(2, '0')}:${String(em).padStart(2, '0')} Uhr`
  if (tc.days_of_week && tc.days_of_week.length > 0 && tc.days_of_week.length < 7) {
    const days = tc.days_of_week.map(d => DAY_NAMES[d] ?? `Tag ${d}`).join(', ')
    return `${range}, ${days}`
  }
  return `Täglich ${range}`
}

function buildReadableText(rule: LogicRule): string {
  const sensorConditions = rule.conditions.filter(
    c => c.type === 'sensor' || c.type === 'sensor_threshold'
  ) as SensorCondition[]

  const firstAction = rule.actions.find(
    a => a.type === 'actuator' || a.type === 'actuator_command'
  ) as ActuatorAction | undefined

  const actionSuffix = firstAction
    ? ` → Aktor ${COMMAND_LABELS[firstAction.command] ?? firstAction.command}`
    : ''

  if (sensorConditions.length === 0) {
    const hc = rule.conditions.find(c => c.type === 'hysteresis') as HysteresisCondition | undefined
    if (hc) {
      const unit = hc.sensor_type ? getSensorUnit(hc.sensor_type) : ''
      const unitStr = unit && unit !== 'raw' ? ` ${unit}` : ''
      if (hc.activate_above != null && hc.deactivate_below != null) {
        return `Einschalten ab ${hc.activate_above}${unitStr}, Ausschalten ab ${hc.deactivate_below}${unitStr}${actionSuffix}`
      }
      if (hc.activate_below != null && hc.deactivate_above != null) {
        return `Einschalten unter ${hc.activate_below}${unitStr}, Ausschalten über ${hc.deactivate_above}${unitStr}${actionSuffix}`
      }
      const hysteresisLabel = hc.sensor_type ? getSensorLabel(hc.sensor_type) : 'Sensor'
      return `${hysteresisLabel} Hysterese${actionSuffix}`
    }

    const tc = rule.conditions.find(c => c.type === 'time_window' || c.type === 'time') as TimeCondition | undefined
    if (tc) {
      return `${formatTimeRange(tc)}${actionSuffix}`
    }

    const dc = rule.conditions.find(c => c.type === 'sensor_diff') as SensorDiffCondition | undefined
    if (dc) {
      const opLabel = OPERATOR_LABELS[dc.operator] ?? dc.operator
      return `Sensordifferenz ${opLabel} ${dc.value}${actionSuffix}`
    }

    const cc = rule.conditions.find(c => c.type === 'compound') as CompoundCondition | undefined
    if (cc) {
      const logicWord = cc.logic === 'OR' ? 'ODER' : 'UND'
      return `Kombinierte Bedingung (${logicWord}, ${cc.conditions.length} Teile)${actionSuffix}`
    }

    return 'Regel noch unvollständig — füge eine Bedingung und eine Aktion hinzu.'
  }

  const firstCond = sensorConditions[0]
  const label = getSensorLabel(firstCond.sensor_type)
  const rawUnit = getSensorUnit(firstCond.sensor_type)
  const unitStr = rawUnit && rawUnit !== 'raw' ? ` ${rawUnit}` : ''

  let condPart: string
  if (
    firstCond.operator === 'between' &&
    firstCond.min !== undefined &&
    firstCond.max !== undefined
  ) {
    condPart = `Wenn ${label} zwischen ${firstCond.min} und ${firstCond.max}${unitStr}`
  } else {
    const opLabel = OPERATOR_LABELS[firstCond.operator] ?? firstCond.operator
    condPart = `Wenn ${label} ${opLabel} ${firstCond.value}${unitStr}`
  }

  const extraCount = sensorConditions.length - 1
  if (extraCount > 0) {
    const logicWord = rule.logic_operator === 'OR' ? 'oder' : 'und'
    condPart += ` (${logicWord} ${extraCount} weitere)`
  }

  return firstAction ? `${condPart}${actionSuffix}` : condPart
}

/**
 * Non-reactive variant of buildReadableText for use in v-for template expressions
 * and other non-setup contexts. Delegates to the same logic as useRuleReadableText.
 */
export function getRuleReadableText(rule: LogicRule): string {
  return buildReadableText(rule)
}

/**
 * Generates a human-readable German summary of a LogicRule.
 * Used by RuleCard (list view) and LogicView (editor preview).
 */
export function useRuleReadableText(ruleGetter: () => LogicRule | null) {
  return computed(() => {
    const rule = ruleGetter()
    if (!rule) return ''
    return buildReadableText(rule)
  })
}
