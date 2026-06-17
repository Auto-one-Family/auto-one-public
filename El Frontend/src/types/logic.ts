/**
 * Logic Types for Cross-ESP Automation Rules
 *
 * Server API: /v1/logic/rules
 * @see El Servador/god_kaiser_server/src/schemas/logic.py
 */

import { getSensorLabel, getSensorUnit } from '@/utils/sensorDefaults'

// =============================================================================
// Logic Rule Types
// =============================================================================

export interface EscalationPolicy {
  notify_after_minutes?: number
  notify_channels?: ('email' | 'webhook' | 'websocket')[]
  auto_disable_after_minutes?: number
  [key: string]: unknown
}

export interface LogicRule {
  id: string
  name: string
  description?: string
  enabled: boolean
  conditions: LogicCondition[]
  logic_operator: 'AND' | 'OR'
  actions: LogicAction[]
  priority: number
  cooldown_seconds?: number
  max_executions_per_hour?: number
  last_triggered?: string
  execution_count?: number
  last_execution_success?: boolean | null
  /** AUT-111: Rule is safety-critical (visual emphasis + escalation) */
  is_critical?: boolean
  /** AUT-111: Escalation behaviour when rule is degraded */
  escalation_policy?: EscalationPolicy | null
  /** AUT-111: ISO timestamp since when the rule is in degraded state */
  degraded_since?: string | null
  /** AUT-111: Human-readable reason for degradation */
  degraded_reason?: string | null
  created_at: string
  updated_at: string
}

// =============================================================================
// Condition Types
// =============================================================================

export type LogicCondition = SensorCondition | TimeCondition | HysteresisCondition | CompoundCondition | DiagnosticsCondition | SensorDiffCondition

export interface SensorCondition {
  type: 'sensor' | 'sensor_threshold'
  esp_id: string
  gpio: number
  sensor_type: string
  operator: '>' | '>=' | '<' | '<=' | '==' | '!=' | 'between'
  value: number
  min?: number // For 'between' operator
  max?: number // For 'between' operator
  subzone_id?: string | null // Phase 2.4: optional subzone filter
}

export interface TimeCondition {
  type: 'time_window' | 'time'
  start_hour: number
  start_minute?: number
  end_hour: number
  end_minute?: number
  days_of_week?: number[] // 0 = Monday, 6 = Sunday (ISO 8601 / Python weekday())
  timezone?: string // IANA timezone name (e.g. "Europe/Berlin"). Absent = UTC.
}

export interface HysteresisCondition {
  type: 'hysteresis'
  esp_id: string
  gpio: number
  sensor_type?: string
  activate_above?: number
  deactivate_below?: number
  activate_below?: number
  deactivate_above?: number
}

export interface CompoundCondition {
  type: 'compound'
  logic: 'AND' | 'OR'
  conditions: LogicCondition[]
}

export interface DiagnosticsCondition {
  type: 'diagnostics_status'
  check_name: string
  expected_status: 'healthy' | 'warning' | 'critical' | 'error'
  operator?: '==' | '!='
}

export interface SensorDiffCondition {
  type: 'sensor_diff'
  sensor_a_id: string
  sensor_b_id: string
  operator: '>' | '>=' | '<' | '<=' | '==' | '!='
  value: number
  consecutive_count?: number
}

// =============================================================================
// Action Types
// =============================================================================

export type LogicAction = ActuatorAction | NotificationAction | DelayAction | PluginAction | DiagnosticsAction | SequenceAction

export interface ActuatorAction {
  type: 'actuator' | 'actuator_command'
  esp_id: string
  gpio: number
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE'
  value?: number // For PWM (0.0-1.0)
  duration?: number // Max runtime per execution in seconds (0 = unlimited, device safety limit as fallback)
  duration_seconds?: number // Backend field name (alias for duration)
}

export interface NotificationAction {
  type: 'notification'
  channel: 'email' | 'webhook' | 'websocket'
  target: string
  message_template: string
}

export interface DelayAction {
  type: 'delay'
  seconds: number
}

export interface PluginAction {
  type: 'plugin' | 'autoops_trigger'
  plugin_id: string
  config?: Record<string, unknown>
}

export interface DiagnosticsAction {
  type: 'run_diagnostic'
  check_name?: string // Optional — omit for full diagnostic
}

export interface SequenceStepServer {
  name?: string
  delay_seconds?: number
  action?: ActuatorAction | DelayAction
  delay_before_seconds?: number
  delay_after_seconds?: number
  timeout_seconds?: number
  on_failure?: 'abort' | 'continue'
}

export interface SequenceAction {
  type: 'sequence'
  steps: SequenceStepServer[]
  abort_on_failure?: boolean
  max_duration_seconds?: number
  description?: string
}

// Editor-intern: Schritt-Entwurf im Node-Data
export interface SequenceStepDraft {
  stepType: 'actuator' | 'delay'
  name?: string
  // actuator
  espId?: string
  gpio?: number
  command?: string
  duration?: number
  // delay
  seconds?: number
  onFailure?: 'abort' | 'continue'
}

// =============================================================================
// Connection Types (for Visualization)
// =============================================================================

/**
 * Represents a visual connection between a sensor and actuator
 * Used by ConnectionLines component to draw logic rule visualizations
 */
export interface LogicConnection {
  ruleId: string
  ruleName: string
  ruleDescription: string // Human-readable: "Temp > 25°C → Lüfter AN"
  sourceEspId: string
  sourceGpio: number
  sourceSensorType: string
  targetEspId: string
  targetGpio: number
  targetCommand: string
  enabled: boolean
  priority: number
  isCrossEsp: boolean // true if source and target are on different ESPs
}

// =============================================================================
// API Response Types
// =============================================================================

export interface LogicRulesResponse {
  success: boolean
  data: LogicRule[]
  pagination: {
    page: number
    page_size: number
    total_items: number
    total_pages: number
    has_next: boolean
    has_previous?: boolean
    has_prev?: boolean
  }
}

export interface ExecutionHistoryResponse {
  success: boolean
  entries: ExecutionHistoryItem[]
  total_count: number
  success_rate: number | null
}

export interface ExecutionHistoryItem {
  id: string
  rule_id: string
  rule_name: string
  triggered_at: string
  trigger_reason: string
  actions_executed: Record<string, unknown>[]
  success: boolean
  error_message?: string
  execution_time_ms: number
  intent_id?: string
  correlation_id?: string
  request_id?: string
  lifecycle_state?: RuleLifecycleState
  terminal_reason_code?: string
  terminal_reason_text?: string
  updated_at?: string
  action_outcomes?: Record<string, unknown>[]
}

export type RuleLifecycleState =
  | 'accepted'
  | 'pending_activation'
  | 'pending_execution'
  | 'terminal_success'
  | 'terminal_failed'
  | 'terminal_conflict'
  | 'terminal_integration_issue'

export interface RuleIntentLifecycle {
  rule_id: string
  intent_id?: string
  correlation_id?: string
  request_id?: string
  state: RuleLifecycleState
  terminal_reason_code?: string
  terminal_reason_text?: string
  updated_at: string
  action_outcomes?: Record<string, unknown>[]
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Format all conditions of a rule into a short readable string.
 *
 * Examples:
 *  - "Temperatur > 28°C"
 *  - "Temperatur > 28°C UND 06:00–20:00"
 *  - "Temperatur Ein >28, Aus <25"
 *
 * Uses getSensorLabel/getSensorUnit from sensorDefaults for readable labels + units.
 * Note: sensorDefaults only has a type-only import from @/types (erased at runtime),
 * so no circular dependency at runtime.
 */
/** @deprecated Use getRuleReadableText from @/composables/useRuleReadableText — all callpoints migrated (AUT-661) */
export function formatConditionShort(rule: LogicRule): string {
  if (!rule.conditions?.length) return 'Keine Bedingung'

  const parts = rule.conditions.map(cond => {
    if (cond.type === 'sensor' || cond.type === 'sensor_threshold') {
      const sc = cond as SensorCondition
      const label = getSensorLabel(sc.sensor_type) || sc.sensor_type
      const unit = getSensorUnit(sc.sensor_type)
      if (sc.operator === 'between') {
        return `${label} ${sc.min ?? '?'}–${sc.max ?? '?'}${unit}`
      }
      const op = sc.operator === '>=' ? '≥' : sc.operator === '<=' ? '≤' : sc.operator
      return `${label} ${op} ${sc.value}${unit}`
    }
    if (cond.type === 'hysteresis') {
      const hc = cond as HysteresisCondition
      const label = hc.sensor_type ? getSensorLabel(hc.sensor_type) : 'Hysterese'
      if (hc.activate_above != null && hc.deactivate_below != null) {
        return `${label} Ein >${hc.activate_above}, Aus <${hc.deactivate_below}`
      }
      if (hc.activate_below != null && hc.deactivate_above != null) {
        return `${label} Ein <${hc.activate_below}, Aus >${hc.deactivate_above}`
      }
      return `${label} (Hysterese)`
    }
    if (cond.type === 'time_window' || cond.type === 'time') {
      const tc = cond as TimeCondition
      const startMinute = tc.start_minute ?? 0
      const endMinute = tc.end_minute ?? 0
      return `${String(tc.start_hour).padStart(2, '0')}:${String(startMinute).padStart(2, '0')}–${String(tc.end_hour).padStart(2, '0')}:${String(endMinute).padStart(2, '0')}`
    }
    if (cond.type === 'compound') {
      return '[Komplex]'
    }
    return `[${cond.type}]`
  })

  const op = rule.logic_operator === 'OR' ? ' ODER ' : ' UND '
  return parts.join(op)
}

/**
 * Generate human-readable description from condition and action
 */
export function generateRuleDescription(
  condition: SensorCondition,
  action: ActuatorAction
): string {
  const opMap: Record<string, string> = {
    '>': '>',
    '>=': '≥',
    '<': '<',
    '<=': '≤',
    '==': '=',
    '!=': '≠',
    between: '↔',
  }
  const op = opMap[condition.operator] || condition.operator
  const cmd =
    action.command === 'ON'
      ? 'AN'
      : action.command === 'OFF'
        ? 'AUS'
        : action.command

  return `${condition.sensor_type} ${op} ${condition.value} → ${cmd}`
}

/**
 * Extract all LogicConnections from a LogicRule
 * Creates one connection per sensor-actuator pair in the rule
 */
export function extractConnections(rule: LogicRule): LogicConnection[] {
  const connections: LogicConnection[] = []

  // Get all sensor conditions (including nested in compound conditions)
  const sensorConditions = extractSensorConditions(rule.conditions)

  // Get all actuator actions
  const actuatorActions = rule.actions.filter(
    (a): a is ActuatorAction =>
      a.type === 'actuator' || a.type === 'actuator_command'
  )

  // Create connection for each sensor→actuator pair
  for (const condition of sensorConditions) {
    for (const action of actuatorActions) {
      connections.push({
        ruleId: rule.id,
        ruleName: rule.name,
        ruleDescription: generateRuleDescription(condition, action),
        sourceEspId: condition.esp_id,
        sourceGpio: condition.gpio,
        sourceSensorType: condition.sensor_type,
        targetEspId: action.esp_id,
        targetGpio: action.gpio,
        targetCommand: action.command,
        enabled: rule.enabled,
        priority: rule.priority,
        isCrossEsp: condition.esp_id !== action.esp_id,
      })
    }
  }

  return connections
}

/**
 * Recursively extract all SensorConditions from condition tree.
 * Includes hysteresis conditions (mapped to SensorCondition for linked-rules display).
 * @public Exported for unit testing (D4).
 */
export function extractSensorConditions(conditions: LogicCondition[]): SensorCondition[] {
  const result: SensorCondition[] = []

  for (const cond of conditions) {
    if (cond.type === 'sensor' || cond.type === 'sensor_threshold') {
      result.push(cond as SensorCondition)
    } else if (cond.type === 'hysteresis') {
      const hCond = cond as HysteresisCondition
      result.push({
        type: 'sensor',
        esp_id: hCond.esp_id,
        gpio: hCond.gpio,
        sensor_type: hCond.sensor_type ?? '',
        operator: '>',
        value: hCond.activate_above ?? hCond.activate_below ?? 0,
      } as SensorCondition)
    } else if (cond.type === 'compound') {
      result.push(...extractSensorConditions((cond as CompoundCondition).conditions))
    }
  }

  return result
}

/**
 * Extract all ESP IDs referenced by a rule (conditions + actions).
 * Used for zone-based rule filtering (getRulesForZone).
 * Covers: SensorCondition, HysteresisCondition, ActuatorAction.
 */
export function extractEspIdsFromRule(rule: LogicRule): Set<string> {
  const espIds = new Set<string>()

  // From conditions: SensorCondition, HysteresisCondition (recursive in compound)
  function collectFromConditions(conditions: LogicCondition[]): void {
    for (const cond of conditions) {
      if (cond.type === 'sensor' || cond.type === 'sensor_threshold') {
        espIds.add((cond as SensorCondition).esp_id)
      } else if (cond.type === 'hysteresis') {
        espIds.add((cond as HysteresisCondition).esp_id)
      } else if (cond.type === 'compound') {
        collectFromConditions((cond as CompoundCondition).conditions)
      }
    }
  }
  collectFromConditions(rule.conditions)

  // From actions: ActuatorAction
  for (const action of rule.actions) {
    if (action.type === 'actuator' || action.type === 'actuator_command') {
      espIds.add((action as ActuatorAction).esp_id)
    }
  }

  return espIds
}
