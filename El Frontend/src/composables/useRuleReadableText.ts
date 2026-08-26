import { computed } from 'vue'
import type {
  LogicRule,
  LogicCondition,
  LogicAction,
  SensorCondition,
  ActuatorAction,
  HysteresisCondition,
  TimeCondition,
  CompoundCondition,
  SensorDiffCondition,
  NotificationAction,
  NotRunningCondition,
  SequenceAction,
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

function formatSensorCondition(sc: SensorCondition): string {
  const label = getSensorLabel(sc.sensor_type)
  const rawUnit = getSensorUnit(sc.sensor_type)
  const unitStr = rawUnit && rawUnit !== 'raw' ? ` ${rawUnit}` : ''
  if (sc.operator === 'between' && sc.min !== undefined && sc.max !== undefined) {
    return `${label} zwischen ${sc.min} und ${sc.max}${unitStr}`
  }
  const opLabel = OPERATOR_LABELS[sc.operator] ?? sc.operator
  return `${label} ${opLabel} ${sc.value}${unitStr}`
}

function formatConditionBrief(cond: LogicCondition | undefined, fallbackIndex: number): string {
  if (!cond) return `C${fallbackIndex}`
  if (cond.type === 'sensor' || cond.type === 'sensor_threshold') {
    return formatSensorCondition(cond as SensorCondition)
  }
  if (cond.type === 'hysteresis') {
    const hc = cond as HysteresisCondition
    const unit = hc.sensor_type ? getSensorUnit(hc.sensor_type) : ''
    const unitStr = unit && unit !== 'raw' ? ` ${unit}` : ''
    if (hc.activate_above != null && hc.deactivate_below != null) {
      return `Hysterese Ein>${hc.activate_above}${unitStr}/Aus<${hc.deactivate_below}${unitStr}`
    }
    if (hc.activate_below != null && hc.deactivate_above != null) {
      return `Hysterese Ein<${hc.activate_below}${unitStr}/Aus>${hc.deactivate_above}${unitStr}`
    }
    return 'Hysterese'
  }
  if (cond.type === 'time_window' || cond.type === 'time') {
    return formatTimeRange(cond as TimeCondition)
  }
  if (cond.type === 'sensor_diff') {
    const dc = cond as SensorDiffCondition
    const opLabel = OPERATOR_LABELS[dc.operator] ?? dc.operator
    return `Sensordifferenz ${opLabel} ${dc.value}`
  }
  if (cond.type === 'not_running') {
    const nr = cond as NotRunningCondition
    return nr.target === 'sequence' ? 'Sequenz läuft nicht' : `Aktor GPIO ${nr.gpio ?? '?'} läuft nicht`
  }
  if (cond.type === 'compound') {
    const cc = cond as CompoundCondition
    return `Kombiniert (${cc.logic}, ${cc.conditions.length})`
  }
  if (cond.type === 'diagnostics_status') {
    return 'Diagnose-Status'
  }
  return `C${fallbackIndex}`
}

function formatActionBrief(action: LogicAction): string {
  if (action.type === 'actuator' || action.type === 'actuator_command') {
    const aa = action as ActuatorAction
    const cmd = COMMAND_LABELS[aa.command] ?? aa.command
    return `Aktor GPIO ${aa.gpio} ${cmd}`
  }
  if (action.type === 'notification') {
    const na = action as NotificationAction
    return `Notification (${na.channel})`
  }
  if (action.type === 'delay') return `Delay ${action.seconds}s`
  if (action.type === 'sequence') {
    const sa = action as SequenceAction
    const n = sa.steps?.length ?? 0
    const stepLabel = n === 1 ? 'Schritt' : 'Schritte'
    return sa.description ? `Sequenz: ${sa.description} (${n} ${stepLabel})` : `Sequenz (${n} ${stepLabel})`
  }
  if (action.type === 'plugin' || action.type === 'autoops_trigger') return 'Plugin'
  if (action.type === 'run_diagnostic') return 'Diagnose'
  return 'Aktion'
}

function hasConditionRefs(action: LogicAction): boolean {
  return Array.isArray(action.condition_refs) && action.condition_refs.length > 0
}

function buildRoutedReadableText(rule: LogicRule): string {
  const clauses: string[] = []
  for (const action of rule.actions) {
    const actionText = formatActionBrief(action)
    if (hasConditionRefs(action)) {
      const refs = action.condition_refs as number[]
      const op = action.condition_op || rule.logic_operator
      const join = op === 'OR' ? ' oder ' : ' und '
      const condTexts = refs.map((i) => formatConditionBrief(rule.conditions[i], i))
      clauses.push(`Wenn ${condTexts.join(join)} → ${actionText}`)
    } else {
      clauses.push(`Wenn alle Bedingungen → ${actionText}`)
    }
  }
  return clauses.join('; ')
}

function buildLegacyActionSuffix(rule: LogicRule): string {
  const actuators = rule.actions.filter(
    (a) => a.type === 'actuator' || a.type === 'actuator_command',
  ) as ActuatorAction[]
  if (actuators.length === 0) {
    if (rule.actions.length === 0) return ''
    return ` → ${rule.actions.map(formatActionBrief).join(', ')}`
  }
  const parts = actuators.map((a) => {
    const cmd = COMMAND_LABELS[a.command] ?? a.command
    return actuators.length > 1 ? `GPIO ${a.gpio} ${cmd}` : `Aktor ${cmd}`
  })
  return ` → ${parts.join(', ')}`
}

function buildReadableText(rule: LogicRule): string {
  // AUT-1318: routed rules — one clause per action with its refs
  if (rule.actions.some(hasConditionRefs)) {
    return buildRoutedReadableText(rule)
  }

  const sensorConditions = rule.conditions.filter(
    c => c.type === 'sensor' || c.type === 'sensor_threshold'
  ) as SensorCondition[]

  const actionSuffix = buildLegacyActionSuffix(rule)

  if (sensorConditions.length === 0) {
    const hc = rule.conditions.find(c => c.type === 'hysteresis') as HysteresisCondition | undefined
    if (hc) {
      const unit = hc.sensor_type ? getSensorUnit(hc.sensor_type) : ''
      const unitStr = unit && unit !== 'raw' ? ` ${unit}` : ''

      // AUT: Sequence-Action ersetzt den direkten Aktor-Ein/Aus-Befehl — die Hysterese-Schwelle
      // ist dann nur noch der Ausloeser fuer die Sequenz, nicht mehr "Einschalten/Ausschalten".
      const seqAction = rule.actions.find(a => a.type === 'sequence') as SequenceAction | undefined
      if (seqAction) {
        const triggerLabel =
          hc.activate_below != null
            ? `unter ${hc.activate_below}${unitStr}`
            : hc.activate_above != null
              ? `über ${hc.activate_above}${unitStr}`
              : null
        const seqLabel = formatActionBrief(seqAction)
        return triggerLabel ? `${seqLabel} — Auslöser ${triggerLabel}` : seqLabel
      }

      if (hc.activate_above != null && hc.deactivate_below != null) {
        return `Einschalten ab ${hc.activate_above}${unitStr}, Ausschalten ab ${hc.deactivate_below}${unitStr}${actionSuffix}`
      }
      if (hc.activate_below != null && hc.deactivate_above != null) {
        return `Einschalten unter ${hc.activate_below}${unitStr}, Ausschalten über ${hc.deactivate_above}${unitStr}${actionSuffix}`
      }
      const hysteresisLabel = hc.sensor_type ? getSensorLabel(hc.sensor_type) : 'Sensor'
      return `${hysteresisLabel} Hysterese${actionSuffix}`
    }

    const timeConditions = rule.conditions.filter(
      c => c.type === 'time_window' || c.type === 'time'
    ) as TimeCondition[]
    if (timeConditions.length > 0) {
      const join = rule.logic_operator === 'OR' ? ' oder ' : ' und '
      return `${timeConditions.map(formatTimeRange).join(join)}${actionSuffix}`
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
  let condPart: string
  if (
    firstCond.operator === 'between' &&
    firstCond.min !== undefined &&
    firstCond.max !== undefined
  ) {
    condPart = `Wenn ${formatSensorCondition(firstCond)}`
  } else {
    condPart = `Wenn ${formatSensorCondition(firstCond)}`
  }

  const extraCount = sensorConditions.length - 1
  if (extraCount > 0) {
    const logicWord = rule.logic_operator === 'OR' ? 'oder' : 'und'
    condPart += ` (${logicWord} ${extraCount} weitere)`
  }

  return actionSuffix ? `${condPart}${actionSuffix}` : condPart
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
