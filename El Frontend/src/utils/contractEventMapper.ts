export type ContractDataSource = 'audit_log' | 'sensor_data' | 'esp_health' | 'actuators'
export type ContractIssueType = 'unknown_event_type' | 'schema_mismatch'
export type ContractEventSeverity = 'info' | 'warning' | 'error' | 'critical'

type ContractValidationResult =
  | { kind: 'ok' }
  | { kind: 'unknown_event'; reason: string }
  | { kind: 'mismatch'; reason: string }

interface IntentContractInventoryItem {
  restEntrypoints: readonly string[]
  wsStartEvents: readonly string[]
  wsTerminalEvents: readonly string[]
  wsProgressEvents?: readonly string[]
}

export interface ContractIntegritySignal {
  eventType: 'contract_unknown_event' | 'contract_mismatch'
  severity: 'critical'
  message: string
  data: Record<string, unknown>
}

export interface IntegrationIssueSnapshot {
  isIntegrationIssue: boolean
  issueType?: ContractIssueType
  originalEventType?: string
  reason?: string
  operatorAction?: string
  correlationId?: string
  requestId?: string
  rawContext?: Record<string, unknown>
}

export const CONTRACT_OPERATOR_ACTION = 'Contract-Pruefung erforderlich'

export const WS_EVENT_TYPES = [
  'sensor_data',
  'sensor_health',
  'actuator_status',
  'actuator_response',
  'actuator_alert',
  'actuator_command',
  'actuator_command_failed',
  'esp_health',
  'config_response',
  'config_published',
  'config_failed',
  'sequence_started',
  'sequence_step',
  'sequence_completed',
  'sequence_error',
  'sequence_cancelled',
  'device_discovered',
  'device_rediscovered',
  'device_approved',
  'device_rejected',
  'device_online',
  'device_offline',
  'lwt_received',
  'zone_assignment',
  'subzone_assignment',
  'device_scope_changed',
  'device_context_changed',
  'sensor_config_deleted',
  'actuator_config_deleted',
  'notification_new',
  'notification_updated',
  'notification_unread_count',
  'intent_outcome',
  'intent_outcome_lifecycle',
  'plugin_execution_started',
  'plugin_execution_completed',
  'logic_execution',
  'conflict.arbitration',
  'system_event',
  'service_start',
  'service_stop',
  'emergency_stop',
  'error_event',
  'mqtt_error',
  'validation_error',
  'database_error',
  'login_success',
  'login_failed',
  'logout',
  'notification',
  'rule_degraded',
  'rule_recovered',
  'events_restored',
  'esp_reconnect_phase',
  'config_response_guard_replay',
  'calibration_session_started',
  'calibration_session_finalized',
  'calibration_session_applied',
  'calibration_session_rejected',
  'calibration_point_added',
  'calibration_point_rejected',
  'calibration_measurement_received',
  'calibration_measurement_failed',
  'contract_mismatch',
  'contract_unknown_event',
  'queue_pressure',
  'esp_diagnostics',
  'actuator_latched_offline',
  'plant_lifecycle_update',
] as const

export const WS_EVENT_TYPES_SET = new Set<string>(WS_EVENT_TYPES as readonly string[])

export const INTENT_CONTRACT_INVENTORY: Record<'actuator' | 'config' | 'sequence', IntentContractInventoryItem> = {
  actuator: {
    restEntrypoints: ['POST /api/v1/actuators/{espId}/{gpio}/command'],
    wsStartEvents: ['actuator_command'],
    wsTerminalEvents: ['actuator_response', 'actuator_command_failed'],
  },
  config: {
    restEntrypoints: [
      'POST /api/v1/sensors/{espId}/{gpio}',
      'POST /api/v1/actuators/{espId}/{gpio}',
      'PATCH /api/v1/esp/devices/{deviceId}',
    ],
    wsStartEvents: ['config_published'],
    wsTerminalEvents: ['config_response', 'config_failed'],
  },
  sequence: {
    restEntrypoints: ['SYSTEM_TRIGGERED (logic engine)'],
    wsStartEvents: ['sequence_started'],
    wsTerminalEvents: ['sequence_completed', 'sequence_error', 'sequence_cancelled'],
    wsProgressEvents: ['sequence_step'],
  },
}

const EVENT_TYPE_TO_DATASOURCE: Record<string, ContractDataSource> = {
  sensor_data: 'sensor_data',
  sensor_health: 'sensor_data',
  esp_health: 'esp_health',
  device_online: 'esp_health',
  device_offline: 'esp_health',
  lwt_received: 'esp_health',
  actuator_status: 'actuators',
  actuator_response: 'actuators',
  actuator_alert: 'actuators',
  actuator_command: 'actuators',
  actuator_command_failed: 'actuators',
  config_response: 'audit_log',
  config_published: 'audit_log',
  config_failed: 'audit_log',
  device_discovered: 'audit_log',
  device_rediscovered: 'audit_log',
  device_approved: 'audit_log',
  device_rejected: 'audit_log',
  zone_assignment: 'audit_log',
  subzone_assignment: 'audit_log',
  device_scope_changed: 'audit_log',
  device_context_changed: 'audit_log',
  sensor_config_deleted: 'audit_log',
  actuator_config_deleted: 'audit_log',
  notification_new: 'audit_log',
  notification_updated: 'audit_log',
  notification_unread_count: 'audit_log',
  intent_outcome: 'audit_log',
  intent_outcome_lifecycle: 'audit_log',
  plugin_execution_started: 'audit_log',
  plugin_execution_completed: 'audit_log',
  logic_execution: 'audit_log',
  'conflict.arbitration': 'audit_log',
  system_event: 'audit_log',
  service_start: 'audit_log',
  service_stop: 'audit_log',
  emergency_stop: 'audit_log',
  error_event: 'audit_log',
  mqtt_error: 'audit_log',
  validation_error: 'audit_log',
  database_error: 'audit_log',
  login_success: 'audit_log',
  login_failed: 'audit_log',
  logout: 'audit_log',
  notification: 'audit_log',
  rule_degraded: 'audit_log',
  rule_recovered: 'audit_log',
  events_restored: 'audit_log',
  esp_reconnect_phase: 'audit_log',
  config_response_guard_replay: 'audit_log',
  calibration_session_started: 'audit_log',
  calibration_session_finalized: 'audit_log',
  calibration_session_applied: 'audit_log',
  calibration_session_rejected: 'audit_log',
  calibration_point_added: 'audit_log',
  calibration_point_rejected: 'audit_log',
  calibration_measurement_received: 'audit_log',
  calibration_measurement_failed: 'audit_log',
  contract_mismatch: 'audit_log',
  contract_unknown_event: 'audit_log',
  queue_pressure: 'esp_health',
  esp_diagnostics: 'esp_health',
  actuator_latched_offline: 'actuators',
  plant_lifecycle_update: 'audit_log',
}

function hasStringField(data: Record<string, unknown>, field: string): boolean {
  return typeof data[field] === 'string' && String(data[field]).trim().length > 0
}

export function extractEspId(data: Record<string, unknown>): string | undefined {
  if (typeof data.esp_id === 'string') return data.esp_id
  if (typeof data.device_id === 'string') return data.device_id
  return undefined
}

export function extractCorrelationId(data: Record<string, unknown>): string | undefined {
  if (!hasStringField(data, 'correlation_id')) return undefined
  return data.correlation_id as string
}

export function extractRequestId(data: Record<string, unknown>): string | undefined {
  if (!hasStringField(data, 'request_id')) return undefined
  return data.request_id as string
}

export function getDataSourceForEventType(eventType: string): ContractDataSource | undefined {
  return EVENT_TYPE_TO_DATASOURCE[eventType]
}

function asNonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined
}

export function buildContractIntegritySignal(params: {
  kind: Extract<ContractValidationResult['kind'], 'unknown_event' | 'mismatch'>
  incomingEventType: string
  reason: string
  incomingData: Record<string, unknown>
  correlationId?: string
  requestId?: string
}): ContractIntegritySignal {
  const issueType: ContractIssueType = params.kind === 'unknown_event'
    ? 'unknown_event_type'
    : 'schema_mismatch'
  const eventType = params.kind === 'unknown_event'
    ? 'contract_unknown_event'
    : 'contract_mismatch'

  return {
    eventType,
    severity: 'critical',
    message: `Integrationsstoerung: ${params.reason}. ${CONTRACT_OPERATOR_ACTION}.`,
    data: {
      ...params.incomingData,
      original_event_type: params.incomingEventType,
      contract_issue: issueType,
      mismatch_reason: params.reason,
      operator_action: CONTRACT_OPERATOR_ACTION,
      correlation_id: params.correlationId,
      request_id: params.requestId,
      raw_context: {
        event_type: params.incomingEventType,
        payload: params.incomingData,
      },
    },
  }
}

export function extractIntegrationIssueSnapshot(event: {
  event_type: string
  data?: Record<string, unknown>
  correlation_id?: string
  request_id?: string
}): IntegrationIssueSnapshot {
  const data = event.data ?? {}
  const isContractIssue = event.event_type === 'contract_unknown_event' || event.event_type === 'contract_mismatch'
  const issueType = asNonEmptyString(data.contract_issue) as ContractIssueType | undefined

  if (!isContractIssue && !issueType) {
    return { isIntegrationIssue: false }
  }

  return {
    isIntegrationIssue: true,
    issueType,
    originalEventType: asNonEmptyString(data.original_event_type),
    reason: asNonEmptyString(data.mismatch_reason),
    operatorAction: asNonEmptyString(data.operator_action) ?? CONTRACT_OPERATOR_ACTION,
    correlationId: asNonEmptyString(event.correlation_id) ?? asNonEmptyString(data.correlation_id),
    requestId: asNonEmptyString(event.request_id) ?? asNonEmptyString(data.request_id),
    rawContext: typeof data.raw_context === 'object' && data.raw_context !== null
      ? (data.raw_context as Record<string, unknown>)
      : undefined,
  }
}

/**
 * Config-Reject-Snapshot aus terminalen Outcomes (AUT-134 PKG-04).
 * Wird befüllt, wenn:
 * - `intent_outcome` mit flow='config' und code='PAYLOAD_TOO_LARGE' eintrifft (ESP32 PKG-02), ODER
 * - `config_failed` mit reason_code='config_oversize' eintrifft (Server PKG-01).
 *
 * Read-only informational — kein Auto-Retry.
 */
export interface ConfigRejectSnapshot {
  espId: string
  reasonCode: string
  payloadSizeBytes: number | null
  budgetBytes: number | null
  correlationId: string | null
  timestamp: string
  source: 'intent_outcome' | 'config_failed'
}

function isTerminalIntentOutcome(data: Record<string, unknown>): boolean {
  if (data.is_final === true) return true
  const t = String(data.terminality ?? '')
  return t.includes('terminal')
}

function asNumberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

/**
 * Mapper: intent_outcome → ConfigRejectSnapshot, falls flow='config' und
 * code='PAYLOAD_TOO_LARGE'. Liefert null, wenn kein Reject-Match.
 *
 * Terminale Semantik: Nur terminal markierte Outcomes erzeugen einen Snapshot.
 */
export function extractConfigRejectFromIntentOutcome(
  data: Record<string, unknown>,
): ConfigRejectSnapshot | null {
  const flow = typeof data.flow === 'string' ? data.flow : ''
  if (flow !== 'config') return null
  const code = typeof data.code === 'string' ? data.code : ''
  if (code !== 'PAYLOAD_TOO_LARGE') return null
  if (!isTerminalIntentOutcome(data)) return null

  const espId = extractEspId(data)
  if (!espId) return null

  const correlationId = extractCorrelationId(data) ?? null
  const tsValue = data.timestamp
  const timestamp = typeof tsValue === 'string' && tsValue.trim().length > 0
    ? tsValue
    : new Date().toISOString()

  return {
    espId,
    reasonCode: code,
    payloadSizeBytes: asNumberOrNull(data.payload_size_bytes),
    budgetBytes: asNumberOrNull(data.budget_bytes),
    correlationId,
    timestamp,
    source: 'intent_outcome',
  }
}

/**
 * Mapper: config_failed → ConfigRejectSnapshot, falls reason_code='config_oversize'
 * (Server PKG-01). Liefert null, wenn kein Reject-Match.
 */
export function extractConfigRejectFromConfigFailed(
  data: Record<string, unknown>,
): ConfigRejectSnapshot | null {
  const reasonCode = typeof data.reason_code === 'string' ? data.reason_code : ''
  if (reasonCode !== 'config_oversize') return null

  const espId = extractEspId(data)
  if (!espId) return null

  const correlationId = extractCorrelationId(data) ?? null
  const tsValue = data.timestamp
  const timestamp = typeof tsValue === 'string' && tsValue.trim().length > 0
    ? tsValue
    : typeof tsValue === 'number' && Number.isFinite(tsValue)
    ? new Date(tsValue).toISOString()
    : new Date().toISOString()

  return {
    espId,
    reasonCode,
    payloadSizeBytes: asNumberOrNull(data.payload_size_bytes),
    budgetBytes: asNumberOrNull(data.budget_bytes),
    correlationId,
    timestamp,
    source: 'config_failed',
  }
}

export function inferFallbackSeverity(eventType: string, data: Record<string, unknown>): ContractEventSeverity {
  if (eventType === 'error_event' || eventType === 'actuator_alert') {
    return 'error'
  }

  if (eventType === 'esp_health') {
    const status = data.status as string
    if (status === 'offline') return 'error'
    if (status === 'timeout') return 'warning'
    return 'info'
  }

  if (eventType === 'sensor_health') {
    const status = data.status as string
    if (status === 'timeout' || status === 'stale') return 'warning'
    return 'info'
  }

  if (eventType === 'config_response') {
    const status = data.status as string
    if (status === 'failed') return 'error'
    return 'info'
  }

  if (eventType === 'device_rejected') {
    return 'warning'
  }

  if (eventType === 'actuator_response') {
    const success = data.success as boolean
    if (!success) return 'error'
    return 'info'
  }

  if (eventType === 'system_event') {
    const nestedType = String(data.event_type || '').toLowerCase()
    if (nestedType.includes('error') || nestedType.includes('fail')) return 'error'
    if (nestedType.includes('warn')) return 'warning'
    return 'info'
  }

  if (eventType === 'intent_outcome') {
    const sev = String(data.severity || '').toLowerCase()
    if (sev === 'critical') return 'critical'
    if (sev === 'error') return 'error'
    if (sev === 'warning') return 'warning'
    return 'info'
  }

  if (eventType === 'intent_outcome_lifecycle') {
    return 'info'
  }

  if (eventType === 'rule_degraded') {
    return 'warning'
  }

  if (eventType === 'rule_recovered') {
    return 'info'
  }

  if (eventType === 'events_restored') {
    return 'info'
  }

  return 'info'
}

function validateKnownEventSchema(eventType: string, data: Record<string, unknown>): string | null {
  if (eventType === 'actuator_command') {
    if (!hasStringField(data, 'esp_id')) return 'actuator_command ohne esp_id'
    if (typeof data.gpio !== 'number') return 'actuator_command mit ungueltigem gpio'
    if (!hasStringField(data, 'command')) return 'actuator_command ohne command'
  }

  if (eventType === 'actuator_response') {
    if (!extractEspId(data)) return 'actuator_response ohne esp_id/device_id'
    if (typeof data.gpio !== 'number') return 'actuator_response mit ungueltigem gpio'
    if (typeof data.success !== 'boolean') return 'actuator_response ohne success-Boolean'
    if (!hasStringField(data, 'command')) return 'actuator_response ohne command'
  }

  if (eventType === 'actuator_command_failed') {
    if (!hasStringField(data, 'esp_id')) return 'actuator_command_failed ohne esp_id'
    if (typeof data.gpio !== 'number') return 'actuator_command_failed mit ungueltigem gpio'
    if (!hasStringField(data, 'error')) return 'actuator_command_failed ohne error'
    if (!hasStringField(data, 'command')) return 'actuator_command_failed ohne command'
  }

  if (eventType === 'config_published') {
    if (!hasStringField(data, 'esp_id')) return 'config_published ohne esp_id'
    if (!Array.isArray(data.config_keys)) return 'config_published ohne config_keys[]'
  }

  if (eventType === 'config_response') {
    if (!extractEspId(data)) return 'config_response ohne esp_id/device_id'
    if (!hasStringField(data, 'status')) return 'config_response ohne status'
    if (!hasStringField(data, 'correlation_id')) return 'config_response ohne correlation_id (nicht finalisierbar)'
  }

  if (eventType === 'config_failed') {
    if (!hasStringField(data, 'esp_id')) return 'config_failed ohne esp_id'
    if (!hasStringField(data, 'error')) return 'config_failed ohne error'
    if (!hasStringField(data, 'correlation_id')) return 'config_failed ohne correlation_id (nicht finalisierbar)'
  }

  if (eventType === 'sequence_started') {
    if (!hasStringField(data, 'sequence_id')) return 'sequence_started ohne sequence_id'
  }

  if (eventType === 'sequence_step') {
    if (!hasStringField(data, 'sequence_id')) return 'sequence_step ohne sequence_id'
    if (typeof data.step !== 'number') return 'sequence_step ohne step-Nummer'
  }

  if (eventType === 'sequence_completed') {
    if (!hasStringField(data, 'sequence_id')) return 'sequence_completed ohne sequence_id'
    if (typeof data.success !== 'boolean') return 'sequence_completed ohne success-Boolean'
  }

  if (eventType === 'sequence_error') {
    if (!hasStringField(data, 'sequence_id')) return 'sequence_error ohne sequence_id'
    if (!hasStringField(data, 'message')) return 'sequence_error ohne message'
  }

  if (eventType === 'sequence_cancelled') {
    if (!hasStringField(data, 'sequence_id')) return 'sequence_cancelled ohne sequence_id'
  }

  if (eventType === 'intent_outcome') {
    if (!extractEspId(data)) return 'intent_outcome ohne esp_id/device_id'
    return null
  }

  if (eventType === 'intent_outcome_lifecycle') {
    if (!extractEspId(data)) return 'intent_outcome_lifecycle ohne esp_id/device_id'
    if (!hasStringField(data, 'event_type')) return 'intent_outcome_lifecycle ohne event_type'
    return null
  }

  if (eventType === 'subzone_assignment') {
    if (!extractEspId(data)) return 'subzone_assignment ohne esp_id/device_id'
    if (!hasStringField(data, 'status')) return 'subzone_assignment ohne status'
    return null
  }

  if (eventType === 'conflict.arbitration') {
    if (!hasStringField(data, 'trace_id')) return 'conflict.arbitration ohne trace_id'
    if (!hasStringField(data, 'actuator_key')) return 'conflict.arbitration ohne actuator_key'
    if (!hasStringField(data, 'winner_rule_id')) return 'conflict.arbitration ohne winner_rule_id'
    if (!hasStringField(data, 'loser_rule_id')) return 'conflict.arbitration ohne loser_rule_id'
    if (!hasStringField(data, 'arbitration_mode')) return 'conflict.arbitration ohne arbitration_mode'
    return null
  }

  if (eventType === 'sensor_config_deleted') {
    if (!extractEspId(data)) return 'sensor_config_deleted ohne esp_id'
    return null
  }

  if (eventType === 'actuator_config_deleted') {
    if (!extractEspId(data)) return 'actuator_config_deleted ohne esp_id'
    return null
  }

  if (eventType === 'events_restored') {
    if (!hasStringField(data, 'backup_id')) return 'events_restored ohne backup_id'
    if (typeof data.restored_count !== 'number') return 'events_restored ohne restored_count'
    return null
  }

  if (eventType === 'rule_degraded') {
    if (!hasStringField(data, 'rule_id')) return 'rule_degraded ohne rule_id'
    return null
  }

  if (eventType === 'rule_recovered') {
    if (!hasStringField(data, 'rule_id')) return 'rule_recovered ohne rule_id'
    return null
  }

  if (eventType === 'esp_reconnect_phase') {
    if (!hasStringField(data, 'esp_id')) return 'esp_reconnect_phase ohne esp_id'
    if (!hasStringField(data, 'phase')) return 'esp_reconnect_phase ohne phase'
    return null
  }

  if (eventType === 'config_response_guard_replay') {
    if (!extractEspId(data)) return 'config_response_guard_replay ohne esp_id/device_id'
    return null
  }

  if (
    eventType === 'notification_new' ||
    eventType === 'notification_updated' ||
    eventType === 'notification_unread_count' ||
    eventType === 'device_scope_changed' ||
    eventType === 'device_context_changed' ||
    eventType === 'plugin_execution_started' ||
    eventType === 'plugin_execution_completed'
  ) {
    return null
  }

  return null
}

export function validateContractEvent(eventType: string, data: Record<string, unknown>): ContractValidationResult {
  if (!WS_EVENT_TYPES_SET.has(eventType)) {
    return { kind: 'unknown_event', reason: `Unbekannter Event-Typ "${eventType}"` }
  }

  const mismatch = validateKnownEventSchema(eventType, data)
  if (mismatch) {
    return { kind: 'mismatch', reason: mismatch }
  }

  return { kind: 'ok' }
}
