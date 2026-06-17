/**
 * useRuleDeployment Composable (AUT-248)
 *
 * Determines where a rule will be evaluated:
 *  - 'esp':    Rule runs on ESP hardware (offline-capable). Activated after a
 *              30-second connectivity-loss grace period on the device. Requires
 *              an offline-capable trigger (hysteresis, sensor_threshold with a
 *              convertible operator, or time_window-only) paired with a same-ESP
 *              actuator action. No server-only side effects.
 *  - 'server': Rule needs the server. No offline-capable trigger pair, OR the
 *              rule uses server-only constructs (notification / plugin / delay /
 *              compound condition / calibration-required sensor).
 *  - 'hybrid': Rule has BOTH an offline-capable trigger+actuator pair (same ESP)
 *              AND server-only side effects (notification, plugin, delay, or
 *              cross-ESP actuator).
 *
 * Detection mirrors ConfigPayloadBuilder._extract_offline_rule() fallback chain:
 *   1. hysteresis condition
 *   2. sensor / sensor_threshold with convertible operator (3a)
 *   3. time_window-only with binary ON actuator command (3d)
 *
 * Constraints mirrored from the server:
 *   - MAX_OFFLINE_RULES = 8 per ESP (offline_rule.h + config_builder.py)
 *   - CALIBRATION_REQUIRED_SENSOR_TYPES = { ph, ec, moisture, soil_moisture }
 *   - Convertible operators: >, >=, <, <= only (== / != / between → server)
 *   - OR-compound rules with 2+ conditions are not convertible (3b)
 *
 * The composable is purely client-side; no REST endpoints are added.
 *
 * @see El Servador/god_kaiser_server/src/services/config_builder.py
 *      _extract_offline_rule(), MAX_OFFLINE_RULES
 * @see El Trabajante/src/models/offline_rule.h MAX_OFFLINE_RULES
 * @see types/logic.ts for LogicRule, HysteresisCondition, SensorCondition, ActuatorAction
 */

import { computed, type ComputedRef, type Ref } from 'vue'
import type {
  LogicRule,
  LogicCondition,
  LogicAction,
  HysteresisCondition,
  SensorCondition,
  ActuatorAction,
  CompoundCondition,
} from '@/types/logic'

/** Where the rule will be evaluated. */
export type RuleDeploymentTarget = 'esp' | 'server' | 'hybrid'

/** Reason a rule cannot run offline (used for tooltips/diagnostics). */
export type ServerOnlyReason =
  | 'no_hysteresis'
  | 'cross_esp_action'
  | 'notification_action'
  | 'plugin_action'
  | 'delay_action'
  | 'compound_condition'
  | 'diagnostics_condition'
  | 'sensor_diff_condition'
  /** Sensor type requires calibration parameters — ESP32 only has raw ADC value. */
  | 'calibration_required_sensor'
  /** Operator (==, !=, between) cannot be expressed as activate_above/deactivate_below. */
  | 'unsupported_operator'
  /** OR-compound rule with 2+ conditions — not convertible to single ESP struct (3b). */
  | 'or_compound_rule'

export interface RuleDeploymentInfo {
  /** Final target: where will the rule be evaluated. */
  target: RuleDeploymentTarget
  /** ESP ID that owns the offline-capable part (if any). */
  offlineEspId: string | null
  /** True when at least one offline-capable trigger+actuator pair on the same ESP exists. */
  hasOfflineCapablePair: boolean
  /** True when at least one server-only action / construct exists. */
  hasServerOnlyAction: boolean
  /** Reasons why parts of the rule require the server. */
  serverOnlyReasons: ServerOnlyReason[]
}

/**
 * Sensor types that require calibration parameters on the server.
 * The ESP32 applyLocalConversion() delivers only the raw ADC value for these —
 * comparing against a physical-unit threshold would fire wrong actuator decisions.
 *
 * Mirrors ConfigPayloadBuilder.CALIBRATION_REQUIRED_SENSOR_TYPES.
 */
const CALIBRATION_REQUIRED_SENSOR_TYPES = new Set(['ph', 'ec', 'moisture', 'soil_moisture'])

/**
 * Threshold operators convertible to an ESP32 hysteresis struct
 * (activate_above / deactivate_below / activate_below / deactivate_above).
 * == / != / between cannot be expressed this way.
 *
 * Mirrors _extract_offline_rule() step 3a operator guard.
 */
const OFFLINE_CONVERTIBLE_OPERATORS: ReadonlySet<SensorCondition['operator']> = new Set([
  '>',
  '>=',
  '<',
  '<=',
])

/**
 * Recursively flatten LogicCondition tree (handles nested CompoundCondition).
 * Returns a flat list and populates disqualifying reason codes as a side-effect.
 */
function flattenConditions(
  conditions: LogicCondition[],
  reasons: Set<ServerOnlyReason>,
): LogicCondition[] {
  const out: LogicCondition[] = []
  for (const cond of conditions) {
    if (cond.type === 'compound') {
      reasons.add('compound_condition')
      out.push(...flattenConditions((cond as CompoundCondition).conditions, reasons))
    } else if (cond.type === 'diagnostics_status') {
      reasons.add('diagnostics_condition')
      out.push(cond)
    } else if (cond.type === 'sensor_diff') {
      reasons.add('sensor_diff_condition')
      out.push(cond)
    } else {
      out.push(cond)
    }
  }
  return out
}

/**
 * Pure helper: classify a single rule. Exported for unit testing.
 */
export function classifyRuleDeployment(rule: LogicRule | null): RuleDeploymentInfo {
  if (!rule) {
    return {
      target: 'server',
      offlineEspId: null,
      hasOfflineCapablePair: false,
      hasServerOnlyAction: false,
      serverOnlyReasons: ['no_hysteresis'],
    }
  }

  const reasons = new Set<ServerOnlyReason>()
  const flatConditions = flattenConditions(rule.conditions ?? [], reasons)

  // OR-compound with 2+ top-level conditions cannot be expressed as a single
  // offline rule struct on the ESP (server: _extract_offline_rule() step 3b).
  const isOrMultiCondition = rule.logic_operator === 'OR' && flatConditions.length > 1
  if (isOrMultiCondition) {
    reasons.add('or_compound_rule')
  }

  // Classify conditions by kind for the three fallback paths below.
  const hysteresisConditions = flatConditions.filter(
    (c): c is HysteresisCondition => c.type === 'hysteresis',
  )
  const sensorConditions = flatConditions.filter(
    (c): c is SensorCondition => c.type === 'sensor' || c.type === 'sensor_threshold',
  )
  const hasTimeCondition = flatConditions.some(
    (c) => c.type === 'time_window' || c.type === 'time',
  )

  // Inspect actions.
  const actuatorActions: ActuatorAction[] = []
  let hasServerOnlyAction = false

  for (const action of rule.actions ?? []) {
    const a = action as LogicAction
    if (a.type === 'actuator' || a.type === 'actuator_command') {
      actuatorActions.push(a as ActuatorAction)
    } else if (a.type === 'notification') {
      reasons.add('notification_action')
      hasServerOnlyAction = true
    } else if (a.type === 'plugin' || a.type === 'autoops_trigger') {
      reasons.add('plugin_action')
      hasServerOnlyAction = true
    } else if (a.type === 'delay') {
      reasons.add('delay_action')
      hasServerOnlyAction = true
    } else if (a.type === 'run_diagnostic') {
      reasons.add('plugin_action')
      hasServerOnlyAction = true
    }
  }

  // === Offline-capable pair detection ===
  // Mirrors _extract_offline_rule() fallback chain:
  //   Path 1: hysteresis + same-ESP actuator
  //   Path 2: sensor_threshold with convertible operator + same-ESP actuator (3a)
  //   Path 3: time_window-only + same-ESP ON actuator (3d)
  let offlineEspId: string | null = null
  let hasOfflineCapablePair = false
  let hasCrossEspActuator = false

  if (!isOrMultiCondition && actuatorActions.length > 0) {
    // Path 1: Hysteresis condition + same-ESP actuator
    if (hysteresisConditions.length > 0) {
      for (const hyst of hysteresisConditions) {
        for (const act of actuatorActions) {
          if (hyst.esp_id && act.esp_id && hyst.esp_id === act.esp_id) {
            hasOfflineCapablePair = true
            offlineEspId = hyst.esp_id
            break
          }
        }
        if (hasOfflineCapablePair) break
      }

      // Detect cross-ESP actuators relative to the offline-capable ESP.
      if (offlineEspId) {
        for (const act of actuatorActions) {
          if (act.esp_id && act.esp_id !== offlineEspId) {
            hasCrossEspActuator = true
            break
          }
        }
      } else if (hysteresisConditions[0]?.esp_id) {
        const triggerEsp = hysteresisConditions[0].esp_id
        for (const act of actuatorActions) {
          if (act.esp_id && act.esp_id !== triggerEsp) {
            hasCrossEspActuator = true
            break
          }
        }
      }
    }

    // Path 2: Sensor threshold → synthetic hysteresis (no hysteresis pair yet)
    if (!hasOfflineCapablePair && sensorConditions.length > 0) {
      for (const sensorCond of sensorConditions) {
        if (CALIBRATION_REQUIRED_SENSOR_TYPES.has(sensorCond.sensor_type)) {
          reasons.add('calibration_required_sensor')
          continue
        }
        if (!OFFLINE_CONVERTIBLE_OPERATORS.has(sensorCond.operator)) {
          reasons.add('unsupported_operator')
          continue
        }
        for (const act of actuatorActions) {
          if (act.esp_id && sensorCond.esp_id && act.esp_id === sensorCond.esp_id) {
            hasOfflineCapablePair = true
            offlineEspId = sensorCond.esp_id
            break
          }
        }
        if (hasOfflineCapablePair) break
      }
    }

    // Path 3: Time-window-only + same-ESP actuator with binary ON command (3d).
    // The actuator command must be ON (or PWM > 0) — OFF leaves time_window_target_state
    // as None on the server, which skips the offline rule.
    if (!hasOfflineCapablePair && hasTimeCondition) {
      const binaryOnActuator = actuatorActions.find(
        (a) => a.esp_id && (a.command === 'ON' || (typeof a.value === 'number' && a.value > 0)),
      )
      if (binaryOnActuator?.esp_id) {
        hasOfflineCapablePair = true
        offlineEspId = binaryOnActuator.esp_id
      }
    }
  }

  if (hasCrossEspActuator) {
    reasons.add('cross_esp_action')
    hasServerOnlyAction = true
  }

  // Add 'no_hysteresis' as the generic "no offline trigger found" reason when
  // no offline-capable pair could be formed and there are no hysteresis conditions.
  // Specific reasons (calibration_required_sensor, unsupported_operator, etc.)
  // are already in the set from the detection paths above.
  if (!hasOfflineCapablePair && hysteresisConditions.length === 0) {
    reasons.add('no_hysteresis')
  }

  // Resolve target.
  let target: RuleDeploymentTarget
  if (hasOfflineCapablePair && !hasServerOnlyAction) {
    target = 'esp'
  } else if (hasOfflineCapablePair && hasServerOnlyAction) {
    target = 'hybrid'
  } else {
    target = 'server'
  }

  return {
    target,
    offlineEspId,
    hasOfflineCapablePair,
    hasServerOnlyAction,
    serverOnlyReasons: Array.from(reasons),
  }
}

/**
 * Reactive composable wrapping {@link classifyRuleDeployment}.
 *
 * @param rule - Reactive ref to the rule (as edited in the canvas, or fetched).
 * @returns reactive deployment info derived from the rule.
 */
export function useRuleDeployment(
  rule: Ref<LogicRule | null>,
): {
  deployment: ComputedRef<RuleDeploymentInfo>
  target: ComputedRef<RuleDeploymentTarget>
  offlineEspId: ComputedRef<string | null>
  hasOfflineCapablePair: ComputedRef<boolean>
  hasServerOnlyAction: ComputedRef<boolean>
} {
  const deployment = computed<RuleDeploymentInfo>(() => classifyRuleDeployment(rule.value))

  return {
    deployment,
    target: computed(() => deployment.value.target),
    offlineEspId: computed(() => deployment.value.offlineEspId),
    hasOfflineCapablePair: computed(() => deployment.value.hasOfflineCapablePair),
    hasServerOnlyAction: computed(() => deployment.value.hasServerOnlyAction),
  }
}
