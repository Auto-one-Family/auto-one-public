/**
 * Logic Store
 *
 * Manages Cross-ESP automation rules and provides connection data
 * for visualization in ConnectionLines component.
 *
 * @see El Servador/god_kaiser_server/src/services/logic_engine.py
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { logicApi } from '@/api/logic'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import type { LogicRuleCreate, LogicRuleUpdate, RuleBulkQuickUpdateRequest, RuleBulkQuickUpdateResponse } from '@/api/logic'
import { extractConnections, extractEspIdsFromRule } from '@/types/logic'
import { createLogger } from '@/utils/logger'
import type {
  LogicRule,
  LogicConnection,
  ExecutionHistoryItem,
  ActuatorAction,
  RuleLifecycleState,
  RuleIntentLifecycle,
} from '@/types/logic'
import { websocketService, type WebSocketMessage } from '@/services/websocket'
import { useEspStore } from '@/stores/esp'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { extractCorrelationId, extractRequestId, validateContractEvent } from '@/utils/contractEventMapper'

const logger = createLogger('LogicStore')

/**
 * Logic Execution Event from WebSocket.
 * Matches server broadcast: logic_engine.py broadcast_logic_execution()
 */
interface LogicExecutionEvent {
  rule_id: string
  rule_name: string
  trigger: {
    type?: string
    esp_id?: string
    gpio?: number
    sensor_type?: string
    value?: number
    rule_id?: string
  }
  action: {
    esp_id: string
    gpio: number
    command: string
  }
  success: boolean
  timestamp: number
  correlation_id?: string
  request_id?: string
  error_code?: string
  error?: string
}

interface SequenceCompletedEvent {
  sequence_id: string
  rule_id?: string
  rule_name?: string
  success: boolean
  error_code?: string
  error?: string
}

interface SequenceErrorEvent {
  sequence_id: string
  rule_id?: string
  rule_name?: string
  error_code?: string
  message: string
}

interface SequenceCancelledEvent {
  sequence_id: string
  rule_id?: string
  rule_name?: string
  reason?: string
}

export interface ConflictArbitrationEvent {
  trace_id: string
  actuator_key: string
  winner_rule_id: string
  loser_rule_id: string
  competing_rules: string[]
  arbitration_mode: 'first_wins' | 'priority'
  resolution: string
  winner_priority?: number
  loser_priority?: number
  command?: string
  message?: string
  timestamp?: string
}

export const useLogicStore = defineStore('logic', () => {
  // =============================================================================
  // State
  // =============================================================================
  const rules = ref<LogicRule[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /** Currently active rule executions (for visual feedback) */
  const activeExecutions = ref<Map<string, number>>(new Map())

  /** Rules triggered within the last 30 seconds (AUT-625) */
  const TRIGGERED_TIMEOUT_MS = 30_000
  const triggeredRules = ref<Map<string, number>>(new Map())

  /** Recent execution history from WebSocket */
  const recentExecutions = ref<LogicExecutionEvent[]>([])
  const recentConflictArbitrations = ref<ConflictArbitrationEvent[]>([])

  /** Merged execution history (REST + WebSocket) */
  const executionHistory = ref<ExecutionHistoryItem[]>([])
  const isLoadingHistory = ref(false)
  const historyLoaded = ref(false)
  const ruleLifecycleByRuleId = ref<Record<string, RuleIntentLifecycle>>({})
  const lifecycleTransitions = ref<RuleIntentLifecycle[]>([])

  /** WebSocket subscription ID */
  let wsSubscriptionId: string | null = null

  // =============================================================================
  // Getters
  // =============================================================================

  /** All connections extracted from rules (for visualization) */
  const connections = computed<LogicConnection[]>(() => {
    return rules.value.flatMap((rule) => extractConnections(rule))
  })

  /** Only cross-ESP connections (for dashboard overlay) */
  const crossEspConnections = computed<LogicConnection[]>(() => {
    return connections.value.filter((conn) => conn.isCrossEsp)
  })

  /** Only enabled rules */
  const enabledRules = computed(() => {
    return rules.value.filter((rule) => rule.enabled)
  })

  /** Rules that are currently in degraded state (target ESP offline) */
  const degradedRules = computed(() => rules.value.filter((r) => !!r.degraded_since))

  /** Rule count */
  const ruleCount = computed(() => rules.value.length)

  /** Enabled rule count */
  const enabledCount = computed(() => enabledRules.value.length)

  const terminalLifecycleStates = new Set<RuleLifecycleState>([
    'terminal_success',
    'terminal_failed',
    'terminal_conflict',
    'terminal_integration_issue',
  ])

  const lifecycleByReasonCode = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = {}
    Object.values(ruleLifecycleByRuleId.value).forEach((entry) => {
      if (!entry.terminal_reason_code) return
      counts[entry.terminal_reason_code] = (counts[entry.terminal_reason_code] ?? 0) + 1
    })
    return counts
  })

  function toIso(tsMs = Date.now()): string {
    return new Date(tsMs).toISOString()
  }

  function asString(value: unknown): string | undefined {
    if (typeof value !== 'string') return undefined
    const trimmed = value.trim()
    return trimmed.length > 0 ? trimmed : undefined
  }

  function resolveRuleIdByName(ruleName?: string): string | undefined {
    if (!ruleName) return undefined
    return rules.value.find((rule) => rule.name === ruleName)?.id
  }

  function inferConflictReason(text?: string): { code?: string; message?: string } {
    if (!text) return {}
    const normalized = text.toLowerCase()
    if (normalized.includes('priority')) {
      return { code: 'conflict_priority_lost', message: 'Prioritaetskonflikt: Regel wurde von hoeherer Prioritaet uebersteuert.' }
    }
    if (normalized.includes('cooldown')) {
      return { code: 'conflict_cooldown_blocked', message: 'Konflikt: Regel wurde durch Cooldown blockiert.' }
    }
    if (normalized.includes('interlock') || normalized.includes('safety') || normalized.includes('not-aus')) {
      return { code: 'conflict_safety_interlock', message: 'Konflikt: Safety-Interlock blockiert die Ausfuehrung.' }
    }
    if (normalized.includes('locked') || normalized.includes('lock')) {
      return { code: 'conflict_target_locked', message: 'Konflikt: Ziel ist durch eine andere Regel gesperrt.' }
    }
    return {}
  }

  function upsertLifecycle(entry: RuleIntentLifecycle): RuleIntentLifecycle {
    const existing = ruleLifecycleByRuleId.value[entry.rule_id]
    if (existing) {
      const prevTs = Date.parse(existing.updated_at)
      const nextTs = Date.parse(entry.updated_at)
      if (!Number.isNaN(prevTs) && !Number.isNaN(nextTs) && nextTs < prevTs) {
        return existing
      }
    }

    ruleLifecycleByRuleId.value = {
      ...ruleLifecycleByRuleId.value,
      [entry.rule_id]: entry,
    }
    lifecycleTransitions.value.unshift(entry)
    if (lifecycleTransitions.value.length > 500) lifecycleTransitions.value.pop()
    return entry
  }

  function setRuleLifecycle(params: {
    ruleId: string
    state: RuleLifecycleState
    intentId?: string
    correlationId?: string
    requestId?: string
    terminalReasonCode?: string
    terminalReasonText?: string
    actionOutcomes?: Record<string, unknown>[]
    updatedAt?: string
  }): RuleIntentLifecycle {
    const next: RuleIntentLifecycle = {
      rule_id: params.ruleId,
      intent_id: params.intentId,
      correlation_id: params.correlationId,
      request_id: params.requestId,
      state: params.state,
      terminal_reason_code: params.terminalReasonCode,
      terminal_reason_text: params.terminalReasonText,
      updated_at: params.updatedAt ?? toIso(),
      action_outcomes: params.actionOutcomes,
    }
    return upsertLifecycle(next)
  }

  function getRuleLifecycle(ruleId: string): RuleIntentLifecycle | null {
    return ruleLifecycleByRuleId.value[ruleId] ?? null
  }

  function applyAccepted(ruleId: string, intentId?: string, correlationId?: string, requestId?: string): void {
    setRuleLifecycle({
      ruleId,
      intentId,
      correlationId,
      requestId,
      state: 'accepted',
    })
  }

  function applyPendingActivation(ruleId: string, intentId?: string, correlationId?: string, requestId?: string): void {
    setRuleLifecycle({
      ruleId,
      intentId,
      correlationId,
      requestId,
      state: 'pending_activation',
    })
  }

  function applyPendingExecution(ruleId: string, intentId?: string, correlationId?: string, requestId?: string): void {
    setRuleLifecycle({
      ruleId,
      intentId,
      correlationId,
      requestId,
      state: 'pending_execution',
    })
  }

  function applyTerminalLifecycle(params: {
    ruleId: string
    intentId?: string
    correlationId?: string
    requestId?: string
    success: boolean
    reasonCode?: string
    reasonText?: string
    actionOutcomes?: Record<string, unknown>[]
    integrationIssue?: boolean
  }): void {
    const inferredConflict = inferConflictReason(params.reasonCode || params.reasonText)
    const reasonCode = params.reasonCode ?? inferredConflict.code
    const reasonText = params.reasonText ?? inferredConflict.message

    let state: RuleLifecycleState
    if (params.integrationIssue) {
      state = 'terminal_integration_issue'
    } else if (params.success) {
      state = 'terminal_success'
    } else if (reasonCode?.startsWith('conflict_')) {
      state = 'terminal_conflict'
    } else {
      state = 'terminal_failed'
    }

    setRuleLifecycle({
      ruleId: params.ruleId,
      intentId: params.intentId,
      correlationId: params.correlationId,
      requestId: params.requestId,
      state,
      terminalReasonCode: reasonCode,
      terminalReasonText: reasonText,
      actionOutcomes: params.actionOutcomes,
    })
  }

  // =============================================================================
  // Actions
  // =============================================================================

  /**
   * Fetch all rules from server
   */
  async function fetchRules(params?: {
    enabled?: boolean
    page?: number
    page_size?: number
  }): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await logicApi.getRules(params)
      rules.value = response.data || []
      logger.debug('Fetched rules', { count: rules.value.length })
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Laden der Logic Rules'))
      logger.error('fetchRules error', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch a single rule by ID
   */
  async function fetchRule(ruleId: string): Promise<LogicRule | null> {
    isLoading.value = true
    error.value = null

    try {
      const rule = await logicApi.getRule(ruleId)
      // Update in list if exists, otherwise add
      const index = rules.value.findIndex((r) => r.id === ruleId)
      if (index !== -1) {
        rules.value[index] = rule
      } else {
        rules.value.push(rule)
      }
      return rule
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, `Fehler beim Laden der Regel ${ruleId}`))
      logger.error('fetchRule error', err)
      return null
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Toggle rule enabled/disabled
   */
  async function toggleRule(ruleId: string): Promise<boolean> {
    error.value = null

    try {
      // Find current state to toggle
      const currentRule = rules.value.find((r) => r.id === ruleId)
      const newEnabled = currentRule ? !currentRule.enabled : true

      const response = await logicApi.toggleRule(ruleId, newEnabled)
      // Update local state
      const rule = rules.value.find((r) => r.id === ruleId)
      if (rule) {
        rule.enabled = response.enabled
      }
      const correlationId = asString((response as unknown as Record<string, unknown>).correlation_id)
      const requestId = asString((response as unknown as Record<string, unknown>).request_id)
      applyAccepted(ruleId, undefined, correlationId, requestId)
      applyPendingActivation(ruleId, undefined, correlationId, requestId)
      logger.info('Rule toggled', { ruleId, enabled: response.enabled })
      return response.enabled
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Umschalten der Regel'))
      logger.error('toggleRule error', err)
      throw err
    }
  }

  /**
   * Test rule evaluation without executing actions
   */
  async function testRule(ruleId: string): Promise<boolean> {
    error.value = null

    try {
      const response = await logicApi.testRule(ruleId)
      logger.info('Rule test completed', { ruleId, wouldTrigger: response.would_trigger })
      return response.would_trigger
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Testen der Regel'))
      logger.error('testRule error', err)
      throw err
    }
  }

  /**
   * Create a new rule and add it to the store
   */
  async function createRule(data: LogicRuleCreate): Promise<LogicRule> {
    error.value = null

    try {
      const created = await logicApi.createRule(data)
      rules.value.push(created)
      applyAccepted(created.id)
      applyPendingActivation(created.id)
      logger.info('Rule created', { id: created.id, name: created.name })
      return created
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Erstellen der Regel'))
      logger.error('createRule error', err)
      throw err
    }
  }

  /**
   * Update an existing rule and sync the store
   */
  async function updateRule(ruleId: string, data: LogicRuleUpdate): Promise<LogicRule> {
    error.value = null

    try {
      const updated = await logicApi.updateRule(ruleId, data)
      const index = rules.value.findIndex((r) => r.id === ruleId)
      if (index !== -1) {
        rules.value[index] = updated
      }
      applyAccepted(ruleId)
      applyPendingActivation(ruleId)
      logger.info('Rule updated', { id: ruleId })
      return updated
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Aktualisieren der Regel'))
      logger.error('updateRule error', err)
      throw err
    }
  }

  /**
   * AUT-1148 (S3): Bulk quick-field update for marked rules (Gruppenkarten-Schnellfeld).
   *
   * Thin wrapper around the single S0 bulk endpoint — the ONLY save path for the
   * group-card quick-field (Fix-Philosophie: kein zweiter, paralleler Save-Aufruf).
   *
   * Unlike updateRule(), the bulk response returns only per-rule {success, error} —
   * no full rule bodies — so only the trivially-safe `active` field can be patched
   * optimistically here. Threshold/hysteresis/time fields are NOT reconstructed
   * client-side (that would duplicate LogicService._patch_quick_field_conditions);
   * syncing the full rule cache after a bulk edit is a page-wiring concern (S4).
   */
  async function bulkQuickUpdateRules(
    request: RuleBulkQuickUpdateRequest,
  ): Promise<RuleBulkQuickUpdateResponse> {
    error.value = null

    try {
      const response = await logicApi.bulkQuickUpdateRules(request)
      if (request.active !== undefined) {
        const successfulIds = new Set(
          response.results.filter((r) => r.success).map((r) => r.rule_id)
        )
        rules.value = rules.value.map((r) =>
          successfulIds.has(r.id) ? { ...r, enabled: request.active! } : r
        )
      }
      logger.info('Bulk quick-update applied', {
        ids: request.ids,
        successCount: response.results.filter((r) => r.success).length,
      })
      return response
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Bulk-Update der Regeln'))
      logger.error('bulkQuickUpdateRules error', err)
      throw err
    }
  }

  /**
   * Delete a rule and remove it from the store
   */
  async function deleteRule(ruleId: string): Promise<void> {
    error.value = null

    try {
      await logicApi.deleteRule(ruleId)
      rules.value = rules.value.filter((r) => r.id !== ruleId)
      logger.info('Rule deleted', { id: ruleId })
    } catch (err) {
      error.value = formatUiApiError(toUiApiError(err, 'Fehler beim Löschen der Regel'))
      logger.error('deleteRule error', err)
      throw err
    }
  }

  /**
   * Get connections for a specific ESP (either as source or target)
   */
  function getConnectionsForEsp(espId: string): LogicConnection[] {
    return connections.value.filter(
      (conn) => conn.sourceEspId === espId || conn.targetEspId === espId
    )
  }

  /**
   * Get connections where ESP is the source (sensor triggers action)
   */
  function getOutgoingConnections(espId: string): LogicConnection[] {
    return connections.value.filter((conn) => conn.sourceEspId === espId)
  }

  /**
   * Get connections where ESP is the target (receives action)
   */
  function getIncomingConnections(espId: string): LogicConnection[] {
    return connections.value.filter((conn) => conn.targetEspId === espId)
  }

  /**
   * Get rule by ID
   */
  function getRuleById(ruleId: string): LogicRule | undefined {
    return rules.value.find((r) => r.id === ruleId)
  }

  /**
   * Get all rules that reference at least one sensor or actuator in the given zone.
   * Zone mapping is derived from espStore.devices (device.zone_id).
   * Rules without any ESP in devices are excluded (unknown zone).
   */
  function getRulesForZone(zoneId: string): LogicRule[] {
    if (!zoneId) return []

    const espStore = useEspStore()
    const devices = espStore.devices

    return rules.value.filter((rule) => {
      const espIds = extractEspIdsFromRule(rule)
      if (espIds.size === 0) return false

      for (const espId of espIds) {
        const device = devices.find((d) => espStore.getDeviceId(d) === espId)
        if (device?.zone_id === zoneId) return true
      }
      return false
    }).sort((a, b) => {
      const prio = (a.priority ?? 0) - (b.priority ?? 0)
      return prio !== 0 ? prio : (a.name ?? '').localeCompare(b.name ?? '')
    })
  }

  /**
   * Get zone names for a rule (via referenced ESPs).
   * Used for L1 Monitor Zone-Badge — answers "Where?" per 5-second rule.
   */
  function getZonesForRule(rule: LogicRule): string[] {
    const espStore = useEspStore()
    const devices = espStore.devices
    const espIds = extractEspIdsFromRule(rule)
    const zoneNames = new Set<string>()

    for (const espId of espIds) {
      const device = devices.find((d) => espStore.getDeviceId(d) === espId)
      const name = device?.zone_name ?? device?.zone_id ?? null
      if (name) zoneNames.add(name)
    }

    return [...zoneNames].sort((a, b) => a.localeCompare(b))
  }

  /**
   * Get all rules that target a specific actuator (via esp_id + gpio in actions).
   * Filters on action-level: type 'actuator' or 'actuator_command' with matching esp_id + gpio.
   * Sorted by priority (lower = higher priority).
   */
  function getRulesForActuator(espId: string, gpio: number): LogicRule[] {
    return rules.value
      .filter(rule =>
        rule.actions.some(action =>
          (action.type === 'actuator' || action.type === 'actuator_command') &&
          (action as ActuatorAction).esp_id === espId &&
          (action as ActuatorAction).gpio === gpio
        )
      )
      .sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0))
  }

  /**
   * Get the most recent execution for a specific actuator.
   * Uses getRulesForActuator() to find relevant rule IDs,
   * then filters executionHistory by those IDs, sorted DESC by triggered_at.
   */
  function getLastExecutionForActuator(espId: string, gpio: number): ExecutionHistoryItem | null {
    const actuatorRules = getRulesForActuator(espId, gpio)
    if (actuatorRules.length === 0) return null

    const ruleIds = new Set(actuatorRules.map(r => r.id))

    return executionHistory.value
      .filter(exec => ruleIds.has(exec.rule_id))
      .sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime())
      [0] ?? null
  }

  /**
   * Clear error state
   */
  function clearError(): void {
    error.value = null
  }

  function getRuleLifecycleState(ruleId: string): RuleLifecycleState | null {
    return ruleLifecycleByRuleId.value[ruleId]?.state ?? null
  }

  function getLifecycleEntry(ruleId: string): RuleIntentLifecycle | null {
    return getRuleLifecycle(ruleId)
  }

  function isTerminalLifecycle(ruleId: string): boolean {
    const state = getRuleLifecycleState(ruleId)
    if (!state) return false
    return terminalLifecycleStates.has(state)
  }

  // =============================================================================
  // Execution History (REST + WebSocket merge)
  // =============================================================================

  /**
   * Load execution history from REST API and merge with WebSocket events.
   * Deduplicates by ID, sorts descending by triggered_at, limits to 50 entries.
   */
  async function loadExecutionHistory(ruleId?: string): Promise<void> {
    isLoadingHistory.value = true

    try {
      const params: { rule_id?: string; limit?: number } = { limit: 50 }
      if (ruleId) params.rule_id = ruleId

      const response = await logicApi.getExecutionHistory(params)
      const restEntries = response.entries || []

      for (const entry of restEntries) {
        const conflict = inferConflictReason(entry.error_message)
        if (entry.success) {
          applyTerminalLifecycle({
            ruleId: entry.rule_id,
            intentId: entry.intent_id,
            correlationId: entry.correlation_id,
            requestId: entry.request_id,
            success: true,
            actionOutcomes: entry.action_outcomes,
          })
        } else {
          applyTerminalLifecycle({
            ruleId: entry.rule_id,
            intentId: entry.intent_id,
            correlationId: entry.correlation_id,
            requestId: entry.request_id,
            success: false,
            reasonCode: entry.terminal_reason_code ?? conflict.code,
            reasonText: entry.terminal_reason_text ?? entry.error_message ?? conflict.message,
            actionOutcomes: entry.action_outcomes,
          })
        }
      }

      // Merge with existing entries: REST entries as base, deduplicate by id
      const merged = new Map<string, ExecutionHistoryItem>()

      // Add REST entries first
      for (const entry of restEntries) {
        merged.set(entry.id, entry)
      }

      // Add existing entries (may include prior REST loads)
      for (const entry of executionHistory.value) {
        if (!merged.has(entry.id)) {
          merged.set(entry.id, entry)
        }
      }

      // Sort descending by triggered_at, limit to 50
      executionHistory.value = Array.from(merged.values())
        .sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime())
        .slice(0, 50)

      historyLoaded.value = true
      logger.debug('Execution history loaded', { count: executionHistory.value.length })
    } catch (err) {
      logger.error('loadExecutionHistory error', err)
    } finally {
      isLoadingHistory.value = false
    }
  }

  // =============================================================================
  // WebSocket Integration
  // =============================================================================

  function addExecutionHistoryEntry(entry: ExecutionHistoryItem): void {
    executionHistory.value.unshift(entry)
    if (executionHistory.value.length > 50) executionHistory.value.pop()
  }

  function handleLogicExecutionEvent(message: WebSocketMessage): void {
    if (message.type !== 'logic_execution') return
    const event = message.data as unknown as LogicExecutionEvent
    if (!event.rule_id) return

    const contractCheck = validateContractEvent('logic_execution', event as unknown as Record<string, unknown>)
    if (contractCheck.kind !== 'ok') {
      applyTerminalLifecycle({
        ruleId: event.rule_id,
        success: false,
        integrationIssue: true,
        reasonCode: 'integration_contract_mismatch',
        reasonText: contractCheck.reason,
      })
      return
    }

    const correlationId = extractCorrelationId(event as unknown as Record<string, unknown>) ?? event.correlation_id
    const requestId = extractRequestId(event as unknown as Record<string, unknown>) ?? event.request_id
    const intentId = correlationId ?? `logic_execution:${event.rule_id}:${event.timestamp}`
    const triggeredAt = new Date(event.timestamp * 1000).toISOString()
    const conflict = inferConflictReason(event.error_code || event.error)

    applyPendingExecution(event.rule_id, intentId, correlationId, requestId)
    applyTerminalLifecycle({
      ruleId: event.rule_id,
      intentId,
      correlationId,
      requestId,
      success: event.success,
      reasonCode: event.error_code ?? conflict.code,
      reasonText: event.error ?? conflict.message,
      actionOutcomes: [{ esp_id: event.action.esp_id, gpio: event.action.gpio, command: event.action.command }],
    })

    recentExecutions.value.unshift(event)
    if (recentExecutions.value.length > 20) recentExecutions.value.pop()

    if (historyLoaded.value) {
      addExecutionHistoryEntry({
        id: `ws-${event.rule_id}-${event.timestamp}`,
        rule_id: event.rule_id,
        rule_name: event.rule_name,
        triggered_at: triggeredAt,
        trigger_reason:
          event.trigger.sensor_type != null
            ? `${event.trigger.sensor_type} = ${event.trigger.value}`
            : event.trigger.type === 'timer'
              ? 'Zeitbasierter Trigger'
              : (event.trigger.type ?? 'Unbekannter Trigger'),
        actions_executed: [{ esp_id: event.action.esp_id, gpio: event.action.gpio, command: event.action.command }],
        success: event.success,
        execution_time_ms: 0,
        intent_id: intentId,
        correlation_id: correlationId,
        request_id: requestId,
        lifecycle_state: event.success ? 'terminal_success' : (conflict.code ? 'terminal_conflict' : 'terminal_failed'),
        terminal_reason_code: event.success ? undefined : (event.error_code ?? conflict.code),
        terminal_reason_text: event.success ? undefined : (event.error ?? conflict.message),
        updated_at: toIso(),
        action_outcomes: [{ esp_id: event.action.esp_id, gpio: event.action.gpio, command: event.action.command }],
      })
    }

    activeExecutions.value.set(event.rule_id, Date.now())
    setTimeout(() => activeExecutions.value.delete(event.rule_id), 150)

    triggeredRules.value.set(event.rule_id, Date.now())
    setTimeout(() => triggeredRules.value.delete(event.rule_id), TRIGGERED_TIMEOUT_MS)

    const rule = rules.value.find((r) => r.id === event.rule_id)
    if (rule) {
      rule.last_triggered = triggeredAt
      rule.execution_count = (rule.execution_count ?? 0) + 1
      rule.last_execution_success = event.success
    }
  }

  function handleSequenceEvent(message: WebSocketMessage): void {
    if (
      message.type !== 'sequence_started' &&
      message.type !== 'sequence_step' &&
      message.type !== 'sequence_completed' &&
      message.type !== 'sequence_error' &&
      message.type !== 'sequence_cancelled'
    ) {
      return
    }

    const data = message.data as Record<string, unknown>
    const ruleId =
      asString(data.rule_id) ??
      resolveRuleIdByName(asString(data.rule_name))
    if (!ruleId) return

    const requestId = extractRequestId(data)
    const sequenceId = asString(data.sequence_id)
    const intentId = sequenceId ?? `sequence:${ruleId}:${Date.now()}`

    if (message.type === 'sequence_started' || message.type === 'sequence_step') {
      applyPendingExecution(ruleId, intentId, sequenceId, requestId)
      return
    }

    if (message.type === 'sequence_completed') {
      const completed = data as unknown as SequenceCompletedEvent
      const success = Boolean(completed.success)
      const conflict = inferConflictReason(completed.error_code || completed.error)
      applyTerminalLifecycle({
        ruleId,
        intentId,
        correlationId: sequenceId,
        requestId,
        success,
        reasonCode: completed.error_code ?? conflict.code,
        reasonText: completed.error ?? conflict.message,
      })
      return
    }

    if (message.type === 'sequence_error') {
      const errored = data as unknown as SequenceErrorEvent
      const conflict = inferConflictReason(errored.error_code || errored.message)
      applyTerminalLifecycle({
        ruleId,
        intentId,
        correlationId: sequenceId,
        requestId,
        success: false,
        reasonCode: errored.error_code ?? conflict.code,
        reasonText: errored.message ?? conflict.message,
      })
      return
    }

    const cancelled = data as unknown as SequenceCancelledEvent
    const conflict = inferConflictReason(cancelled.reason)
    applyTerminalLifecycle({
      ruleId,
      intentId,
      correlationId: sequenceId,
      requestId,
      success: false,
      reasonCode: conflict.code ?? 'sequence_cancelled',
      reasonText: cancelled.reason ?? conflict.message ?? 'Sequenz wurde abgebrochen.',
    })
  }

  function handleConflictArbitrationEvent(message: WebSocketMessage): void {
    if (message.type !== 'conflict.arbitration') return
    const event = message.data as Record<string, unknown>
    const contractCheck = validateContractEvent('conflict.arbitration', event)
    if (contractCheck.kind !== 'ok') return

    const traceId = asString(event.trace_id)
    const actuatorKey = asString(event.actuator_key)
    const winnerRuleId = asString(event.winner_rule_id)
    const loserRuleId = asString(event.loser_rule_id)
    const arbitrationMode = asString(event.arbitration_mode)
    if (!traceId || !actuatorKey || !winnerRuleId || !loserRuleId || !arbitrationMode) return
    if (arbitrationMode !== 'first_wins' && arbitrationMode !== 'priority') return

    const next: ConflictArbitrationEvent = {
      trace_id: traceId,
      actuator_key: actuatorKey,
      winner_rule_id: winnerRuleId,
      loser_rule_id: loserRuleId,
      competing_rules: Array.isArray(event.competing_rules)
        ? event.competing_rules.filter((value): value is string => typeof value === 'string')
        : [winnerRuleId, loserRuleId],
      arbitration_mode: arbitrationMode,
      resolution: asString(event.resolution) ?? arbitrationMode,
      winner_priority: typeof event.winner_priority === 'number' ? event.winner_priority : undefined,
      loser_priority: typeof event.loser_priority === 'number' ? event.loser_priority : undefined,
      command: asString(event.command),
      message: asString(event.message),
      timestamp: asString(event.timestamp),
    }

    const withoutDuplicate = recentConflictArbitrations.value.filter(
      (item) => item.trace_id !== next.trace_id,
    )
    recentConflictArbitrations.value = [next, ...withoutDuplicate].slice(0, 20)

    // AUT-123 / B-TOAST-02: finalize the losing actuator's pending intent so it
    // does not stay in `pending` forever. The loser's command never reached
    // the device — close it as terminal_failed with reason `conflict_arbitration`.
    // actuator_key format from server (conflict_manager.py): "esp_id:gpio"
    // (zone-scoped variants may use "esp_id:gpio:zone_id"; we take the first two).
    const keyParts = actuatorKey.split(':')
    if (keyParts.length >= 2) {
      const loserEspId = keyParts[0]
      const loserGpio = Number.parseInt(keyParts[1], 10)
      if (loserEspId && Number.isFinite(loserGpio)) {
        try {
          const actuatorStore = useActuatorStore()
          actuatorStore.finalizeConflictLoserIntent(loserEspId, loserGpio, traceId)
        } catch (err) {
          logger.warn('Failed to finalize conflict loser intent', {
            err,
            actuator_key: actuatorKey,
            loser_rule_id: loserRuleId,
            trace_id: traceId,
          })
        }
      }
    }
  }

  function handleRuleDegradedEvent(message: WebSocketMessage): void {
    if (message.type !== 'rule_degraded') return
    const data = message.data as Record<string, unknown>
    const ruleId = asString(data.rule_id)
    if (!ruleId) return

    const rule = rules.value.find((r) => r.id === ruleId)
    if (rule) {
      rule.degraded_since = typeof data.degraded_since === 'string' ? data.degraded_since : new Date().toISOString()
      rule.degraded_reason = typeof data.degraded_reason === 'string'
        ? data.degraded_reason
        : typeof data.reason === 'string'
          ? data.reason
          : 'Unbekannt'
      if (typeof data.is_critical === 'boolean') rule.is_critical = data.is_critical
    }

    logger.warn('Rule degraded', { ruleId, reason: data.degraded_reason })
  }

  function handleRuleRecoveredEvent(message: WebSocketMessage): void {
    if (message.type !== 'rule_recovered') return
    const data = message.data as Record<string, unknown>
    const ruleId = asString(data.rule_id)
    if (!ruleId) return

    const rule = rules.value.find((r) => r.id === ruleId)
    if (rule) {
      rule.degraded_since = null
      rule.degraded_reason = null
    }

    logger.info('Rule recovered', { ruleId })
  }

  function handleLifecycleEvents(message: WebSocketMessage): void {
    handleLogicExecutionEvent(message)
    handleSequenceEvent(message)
    handleConflictArbitrationEvent(message)
    handleRuleDegradedEvent(message)
    handleRuleRecoveredEvent(message)
  }

  /** Cleanup function for WebSocket reconnect callback */
  let removeOnConnect: (() => void) | null = null

  /**
   * Subscribe to WebSocket for logic execution events.
   */
  function subscribeToWebSocket(): void {
    if (wsSubscriptionId) return // Already subscribed

    wsSubscriptionId = websocketService.subscribe(
      {
        types: [
          'logic_execution',
          'sequence_started',
          'sequence_step',
          'sequence_completed',
          'sequence_error',
          'sequence_cancelled',
          'conflict.arbitration',
          'rule_degraded',
          'rule_recovered',
        ],
      },
      handleLifecycleEvents
    )

    removeOnConnect = websocketService.onConnect(() => {
      fetchRules().catch((err) => logger.warn('Post-reconnect rule refresh failed', { err }))
    })

    logger.debug('Subscribed to WebSocket for logic lifecycle events')
  }

  /**
   * Unsubscribe from WebSocket.
   */
  function unsubscribeFromWebSocket(): void {
    if (wsSubscriptionId) {
      websocketService.unsubscribe(wsSubscriptionId)
      wsSubscriptionId = null
      logger.debug('Unsubscribed from WebSocket')
    }
    if (removeOnConnect) {
      removeOnConnect()
      removeOnConnect = null
    }
  }

  /**
   * Check if a rule is currently active (just executed, 150ms flash).
   */
  function isRuleActive(ruleId: string): boolean {
    return activeExecutions.value.has(ruleId)
  }

  /**
   * Check if a rule was triggered within the last 30 seconds (AUT-625).
   */
  function isRuleTriggered(ruleId: string): boolean {
    return triggeredRules.value.has(ruleId)
  }

  /**
   * Check if a connection is currently active (rule just executed).
   */
  function isConnectionActive(connection: LogicConnection): boolean {
    return activeExecutions.value.has(connection.ruleId)
  }

  // =============================================================================
  // UNDO/REDO — Command Pattern (Phase 2, Schritt 10)
  // =============================================================================

  interface RuleHistoryEntry {
    nodes: any[]
    edges: any[]
    metadata?: {
      priority?: number
      cooldown_seconds?: number
      max_dose_ml_per_day?: number
    }
    timestamp: number
  }

  const history = ref<RuleHistoryEntry[]>([])
  const historyIndex = ref(-1)
  const MAX_HISTORY = 50

  /** Can undo? */
  const canUndo = computed(() => historyIndex.value > 0)

  /** Can redo? */
  const canRedo = computed(() => historyIndex.value < history.value.length - 1)

  /**
   * Push a snapshot to history.
   * Called after every graph change in the rule editor.
   */
  function pushToHistory(
    nodes: any[],
    edges: any[],
    metadata?: { priority?: number; cooldown_seconds?: number; max_dose_ml_per_day?: number }
  ) {
    // Discard any "future" entries if we undid something and then changed
    history.value = history.value.slice(0, historyIndex.value + 1)

    history.value.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
      metadata: metadata ? JSON.parse(JSON.stringify(metadata)) : undefined,
      timestamp: Date.now(),
    })

    // Trim to max size
    if (history.value.length > MAX_HISTORY) {
      history.value.shift()
    }

    historyIndex.value = history.value.length - 1
  }

  /**
   * Undo — returns the previous graph state.
   */
  function undo(): RuleHistoryEntry | null {
    if (!canUndo.value) return null
    historyIndex.value--
    return history.value[historyIndex.value]
  }

  /**
   * Redo — returns the next graph state.
   */
  function redo(): RuleHistoryEntry | null {
    if (!canRedo.value) return null
    historyIndex.value++
    return history.value[historyIndex.value]
  }

  /**
   * Clear history (e.g., when switching rules).
   */
  function clearHistory() {
    history.value = []
    historyIndex.value = -1
  }

  // =============================================================================
  // CONNECTION VALIDATION (Phase 2, Schritt 10)
  // =============================================================================

  /**
   * Validate whether a connection between two node types is allowed.
   *
   * Rules:
   * 1. Sensor → Condition: ALLOWED
   * 2. Sensor → Action: NOT ALLOWED (must go through condition)
   * 3. Condition → Condition: ALLOWED (AND/OR chaining)
   * 4. Condition → Action: ALLOWED
   * 5. Action → anything: NOT ALLOWED (action is terminal)
   * 6. No self-loops
   * 7. Time → Condition: ALLOWED
   * 8. Time → Action: ALLOWED
   */
  function isValidConnection(
    sourceNodeType: string | undefined,
    _targetNodeType: string | undefined,
    sourceId: string,
    targetId: string
  ): { valid: boolean; reason?: string } {
    // No self-loops
    if (sourceId === targetId) {
      return { valid: false, reason: 'Selbst-Schleifen sind nicht erlaubt' }
    }

    // Action nodes cannot be sources (actuator, notification have no outgoing connections)
    if (sourceNodeType === 'actuator' || sourceNodeType === 'notification') {
      return { valid: false, reason: 'Aktions-Knoten können keine Verbindung starten' }
    }

    // AUT-1318 (R-S4): Condition → Action direct is ALLOWED (= routing edge → condition_refs).
    // Logic-node path remains valid for flat/grouped semantics (D4 when refs absent).
    // AUT-1399: sensor_diff (Mess-Bindung) may connect visually, but RuleFlowEditor
    // excludes it from CONDITION_NODE_TYPES — edges never become condition_refs.
    // _targetNodeType kept for API symmetry with getConnectionValidationMessage.

    // Everything else is allowed
    return { valid: true }
  }

  /**
   * Get validation message for connection.
   */
  function getConnectionValidationMessage(
    sourceNodeType: string | undefined,
    targetNodeType: string | undefined,
    sourceId: string,
    targetId: string
  ): string {
    const result = isValidConnection(sourceNodeType, targetNodeType, sourceId, targetId)
    return result.reason || ''
  }

  // =============================================================================
  // Return
  // =============================================================================
  return {
    // State
    rules,
    isLoading,
    error,
    activeExecutions,
    recentExecutions,
    recentConflictArbitrations,
    ruleLifecycleByRuleId,
    lifecycleTransitions,

    // Getters
    connections,
    crossEspConnections,
    enabledRules,
    degradedRules,
    ruleCount,
    enabledCount,
    lifecycleByReasonCode,

    // Actions
    fetchRules,
    fetchRule,
    createRule,
    updateRule,
    bulkQuickUpdateRules,
    deleteRule,
    toggleRule,
    testRule,
    getConnectionsForEsp,
    getOutgoingConnections,
    getIncomingConnections,
    getRuleById,
    getRulesForZone,
    getZonesForRule,
    getRulesForActuator,
    getLastExecutionForActuator,
    clearError,
    getRuleLifecycleState,
    getLifecycleEntry,
    isTerminalLifecycle,

    // Execution History
    executionHistory,
    isLoadingHistory,
    historyLoaded,
    loadExecutionHistory,

    // WebSocket
    subscribeToWebSocket,
    unsubscribeFromWebSocket,
    isRuleActive,
    isRuleTriggered,
    isConnectionActive,

    // Undo/Redo (Phase 2)
    history,
    historyIndex,
    canUndo,
    canRedo,
    pushToHistory,
    undo,
    redo,
    clearHistory,

    // Connection Validation (Phase 2)
    isValidConnection,
    getConnectionValidationMessage,
  }
})
