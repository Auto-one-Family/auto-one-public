/**
 * Logic Types for Cross-ESP Automation Rules
 *
 * Server API: /v1/logic/rules
 * @see El Servador/god_kaiser_server/src/schemas/logic.py
 */

import { formatDeadbandEdge } from '@/utils/planDeadbandDisplay'
import { getSensorLabel, getSensorUnit } from '@/utils/sensorDefaults'

// =============================================================================
// Rule Group Catalog (AUT-1145 / AUT-1147 / AUT-1173)
// =============================================================================

/**
 * Fixed group catalog — single source of truth shared with the server.
 * Server-side: El Servador/god_kaiser_server/src/db/models/logic.py:33-40
 * Frontend NEVER derives the group itself; it reads what the server sends.
 *
 * AUT-1173 (TAX-5, Variante C): Messgröße als Primärachse (9 Werte, 1:1 gespiegelt
 * von AggCategory in utils/sensorDefaults.ts) + "sicherheit" als feste Ausnahme +
 * "zeitplan"/"sonstiges". "klima"/"alarm"/"dosierung" entfallen als eigene Gruppen.
 */
export const RULE_GROUP_CATALOG = [
  'ph',
  'ec',
  'bodenfeuchte',
  'luftfeuchte',
  'temperatur',
  'co2',
  'luftdruck',
  'licht',
  'durchfluss',
  'zeitplan',
  'sicherheit',
  'sonstiges',
] as const

export type RuleGroup = typeof RULE_GROUP_CATALOG[number]

// =============================================================================
// Plan Subscription Catalogs (AUT-1243, mirrors AUT-1232 server model)
// =============================================================================

/**
 * Plan-domain catalog mirrored from the server (PLAN_DOMAINS in
 * db/models/plan_segment.py). nutrient_solution + climate (AUT-1239/1240).
 */
export const PLAN_DOMAIN_CATALOG = ['nutrient_solution', 'climate'] as const

export type PlanDomain = typeof PLAN_DOMAIN_CATALOG[number]

/**
 * Plan-measure catalog — nutrient (AUT-1232) + climate targets (AUT-1239).
 * VPD is never a stored measure (derived overlay only).
 */
export const PLAN_MEASURE_CATALOG = [
  'target_ec',
  'target_ph',
  'target_temperature',
  'target_humidity',
] as const

export type PlanMeasure = typeof PLAN_MEASURE_CATALOG[number]

/** Measures editable per plan domain (UI filter for segment editor). */
export const PLAN_MEASURES_BY_DOMAIN: Record<PlanDomain, readonly PlanMeasure[]> = {
  nutrient_solution: ['target_ec', 'target_ph'],
  climate: ['target_temperature', 'target_humidity'],
}

export function defaultMeasureForDomain(domain: PlanDomain | string): PlanMeasure {
  if (domain === 'climate') return 'target_temperature'
  return 'target_ec'
}

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
  /** AUT-1115: Wait for settle_seconds after the last execution of this other rule before evaluating. */
  settle_after_rule_id?: string | null
  /** AUT-1115: Settle window in seconds, evaluated against settle_after_rule_id's last execution. */
  settle_seconds?: number | null
  /** AO-4 (AUT-993): Max total dose ml per rolling 24h across all executions (undefined = unlimited). */
  max_dose_ml_per_day?: number
  max_executions_per_hour?: number
  /** AUT-993 (B8): Max executions per rolling 24h window (undefined or 0 = unlimited). */
  max_executions_per_day?: number
  last_triggered?: string
  execution_count?: number
  last_execution_success?: boolean | null
  /** AUT-111: Rule is safety-critical (visual emphasis + escalation) */
  is_critical?: boolean
  /** AUT-111: Escalation behaviour when rule is degraded */
  escalation_policy?: EscalationPolicy | null
  /** AUT-1113: Free-form rule metadata (e.g. AUT-1112 chemistry dose_config, AUT-1116 paired_rule_id). */
  rule_metadata?: Record<string, unknown>
  /** AUT-1116: Non-blocking hints (e.g. paired-rule deadband overlap). HTTP 2xx regardless — never a reject. */
  warnings?: string[]
  /** AUT-111: ISO timestamp since when the rule is in degraded state */
  degraded_since?: string | null
  /** AUT-111: Human-readable reason for degradation */
  degraded_reason?: string | null
  /**
   * AUT-1145: Effective display group (server-derived or user override).
   * Always one of RULE_GROUP_CATALOG. Server guarantees a non-null value in
   * LogicRuleResponse; optional here for backward-compat with existing mocks.
   */
  rule_group?: RuleGroup
  /**
   * AUT-1232/AUT-1243: Opt-in plan subscription — when true, the rule may
   * read its setpoint from plan_segment@now instead of a static value
   * (engine wiring is AUT-1233/T3). Default false — existing rules stay
   * on their static setpoints.
   */
  follows_plan?: boolean
  /** AUT-1232: Zone for the plan subscription (mandatory when follows_plan is true). */
  plan_zone_id?: string | null
  /** AUT-1232: Optional subzone_config scope for the plan subscription. */
  plan_subzone_config_id?: string | null
  /** AUT-1232: Plan domain (see PLAN_DOMAIN_CATALOG). */
  plan_domain?: PlanDomain | null
  /** AUT-1232: Plan measure (see PLAN_MEASURE_CATALOG). */
  plan_measure?: PlanMeasure | null
  created_at: string
  updated_at: string
}

// =============================================================================
// Condition Types
// =============================================================================

export type LogicCondition = SensorCondition | TimeCondition | HysteresisCondition | CompoundCondition | DiagnosticsCondition | SensorDiffCondition | NotRunningCondition

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
  /** AO-3 (AUT-994): When true, condition evaluates false if the sensor value is stale (on_demand/scheduled sensors; age > measurement_freshness_hours). */
  require_fresh_data?: boolean
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

/** AUT-1245 / AUT-1333: Idle-Interlock — True wenn Sequenz/Aktor nicht läuft. */
export interface NotRunningCondition {
  type: 'not_running'
  target: 'sequence' | 'actuator'
  /** Logic-Rule-UUID wenn target=sequence */
  rule_id?: string
  /** Device-UUID (nicht ESP_XXXX) wenn target=actuator */
  esp_id?: string
  gpio?: number
}

// =============================================================================
// Action Types
// =============================================================================

export type LogicAction = ActuatorAction | NotificationAction | DelayAction | PluginAction | DiagnosticsAction | SequenceAction

/**
 * AUT-1317 (R-S2): optional per-action condition binding.
 * Absent/null/[] → legacy global rule gate. Non-empty → per-action gate.
 * condition_op default at evaluate-time = rule.logic_operator (not LX-02 group).
 */
export interface ActionConditionRouting {
  condition_refs?: number[] | null
  condition_op?: 'AND' | 'OR' | null
}

export interface ActuatorAction extends ActionConditionRouting {
  type: 'actuator' | 'actuator_command'
  esp_id: string
  gpio: number
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE'
  value?: number // For PWM (0.0-1.0)
  duration?: number // Max runtime per execution in seconds (0 = unlimited, device safety limit as fallback)
  duration_seconds?: number // Backend field name (alias for duration)
  /** AO-2 (AUT-991): Target dose volume in ml. Server resolves to duration_seconds via ceil(dose_ml / flow_rate_ml_s). */
  dose_ml?: number
  /** AUT-1317: routed OFF + this flag → action-level cooldown bypass (not rule-wide hysteresis OFF). */
  is_safety_critical?: boolean
}

export interface NotificationAction extends ActionConditionRouting {
  type: 'notification'
  channel: 'email' | 'webhook' | 'websocket'
  target: string
  message_template: string
}

export interface DelayAction extends ActionConditionRouting {
  type: 'delay'
  seconds: number
}

export interface PluginAction extends ActionConditionRouting {
  type: 'plugin' | 'autoops_trigger'
  plugin_id: string
  config?: Record<string, unknown>
}

export interface DiagnosticsAction extends ActionConditionRouting {
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
  /** AUT-1390: FE-Intent Modus — am Step persistiert (List[Any] server-seitig). */
  dose_mode?: 'duration' | 'ml' | 'target_optimal'
}

export interface SequenceAction extends ActionConditionRouting {
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
  /** AUT-1281: Ziel-Dosis in ml fuer diesen Schritt (Pumpen-Aktor). Server-Roundtrip via
   * SequenceStepServer.action.dose_ml (ActuatorAction) — Server rechnet ceil(ml/flow_rate). */
  dose_ml?: number
  /**
   * AUT-1390: FE-Intent Dosier-Modus am Sequenz-Schritt (duration | ml | target_optimal).
   * Roundtrip am Step (neben action) — kein Server-Dosier-Pfad, nur Anzeige/Intent.
   */
  dose_mode?: 'duration' | 'ml' | 'target_optimal'
  /** AUT-1306: Server-Felder nur Roundtrip-Preserve (kein UI; Pure-Pause bleibt delay_seconds). */
  delay_before_seconds?: number
  delay_after_seconds?: number
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
      const st = hc.sensor_type
      if (hc.activate_above != null && hc.deactivate_below != null) {
        return `${label} Ein >${formatDeadbandEdge(hc.activate_above, st)}, Aus <${formatDeadbandEdge(hc.deactivate_below, st)}`
      }
      if (hc.activate_below != null && hc.deactivate_above != null) {
        return `${label} Ein <${formatDeadbandEdge(hc.activate_below, st)}, Aus >${formatDeadbandEdge(hc.deactivate_above, st)}`
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
 * Recursively find the first condition of one of the given types, descending
 * into compound conditions. Returns null if no matching condition exists.
 */
function findCondition(conditions: LogicCondition[], types: string[]): LogicCondition | null {
  for (const cond of conditions) {
    if (types.includes(cond.type)) return cond
    if (cond.type === 'compound') {
      const nested = findCondition((cond as CompoundCondition).conditions, types)
      if (nested) return nested
    }
  }
  return null
}

// =============================================================================
// Quick-Field Condition Inspection (AUT-1148, S3 — Gruppenkarten-Schnellfeld)
// =============================================================================
//
// Used to compute the Schnittmengen-Logik (which quick-fields apply to ALL
// currently marked rules) and to read each rule's current value for the
// "gemischt" comparison. Server is the sole write-side authority for how a
// bulk quick-field edit is applied (LogicService._patch_quick_field_conditions);
// these helpers only READ existing condition values for display purposes.

/** True if the rule has a time-window condition (Zeiten quick-field applies). */
export function hasTimeWindowCondition(rule: LogicRule): boolean {
  return findCondition(rule.conditions, ['time_window', 'time']) !== null
}

/** True if the rule has a plain sensor-threshold condition (single-value Schwellwert). */
export function hasSimpleThresholdCondition(rule: LogicRule): boolean {
  return findCondition(rule.conditions, ['sensor', 'sensor_threshold']) !== null
}

/** True if the rule has a hysteresis condition (on/off-value-pair Schwellwert). */
export function hasHysteresisCondition(rule: LogicRule): boolean {
  return findCondition(rule.conditions, ['hysteresis']) !== null
}

/** Current value of the rule's plain sensor-threshold condition, or null if none. */
export function getSimpleThresholdValue(rule: LogicRule): number | null {
  const found = findCondition(rule.conditions, ['sensor', 'sensor_threshold']) as SensorCondition | null
  return found ? found.value : null
}

/** Current on/off values of the rule's hysteresis condition, or nulls if none. */
export function getHysteresisValues(rule: LogicRule): { on: number | null; off: number | null } {
  const found = findCondition(rule.conditions, ['hysteresis']) as HysteresisCondition | null
  if (!found) return { on: null, off: null }
  return {
    on: found.activate_above ?? found.activate_below ?? null,
    off: found.deactivate_below ?? found.deactivate_above ?? null,
  }
}

export interface TimeWindowValues {
  startHour: number
  startMinute: number
  endHour: number
  endMinute: number
  daysOfWeek: number[]
}

/** Current values of the rule's time-window condition, or null if none. */
export function getTimeWindowValues(rule: LogicRule): TimeWindowValues | null {
  const found = findCondition(rule.conditions, ['time_window', 'time']) as TimeCondition | null
  if (!found) return null
  return {
    startHour: found.start_hour,
    startMinute: found.start_minute ?? 0,
    endHour: found.end_hour,
    endMinute: found.end_minute ?? 0,
    daysOfWeek: found.days_of_week ?? [],
  }
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
