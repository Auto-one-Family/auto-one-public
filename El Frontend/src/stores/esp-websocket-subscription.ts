/**
 * ESP Store WebSocket subscription contract (P0-A).
 *
 * useWebSocket with filters.types drops any message type not listed here before
 * dispatching to ws.on() handlers. This list MUST match every ws.on('…') in
 * esp.store initWebSocket (same types, no extras that handlers depend on).
 *
 * When adding a handler in esp.ts, append the type here.
 */
import type { MessageType } from '@/types'

export type RealtimeMutationType = 'replace' | 'patch' | 'refresh'

/** Message types registered via ws.on() in esp.store.ts initWebSocket */
export const ESP_STORE_WS_ON_HANDLER_TYPES = [
  'actuator_alert',
  'actuator_command',
  'logic_execution',
  'actuator_command_failed',
  'actuator_config_deleted',
  'actuator_response',
  'actuator_status',
  'config_failed',
  'config_published',
  'config_response',
  'config_response_guard_replay',
  'device_approved',
  'device_context_changed',
  'device_discovered',
  'device_rediscovered',
  'device_rejected',
  'device_scope_changed',
  'esp_health',
  'esp_reconnect_phase',
  'error_event',
  'intent_outcome',
  'intent_outcome_lifecycle',
  'notification',
  'notification_new',
  'notification_updated',
  'notification_unread_count',
  'sensor_config_deleted',
  'sensor_data',
  'sensor_health',
  'sequence_cancelled',
  'sequence_completed',
  'sequence_error',
  'sequence_started',
  'sequence_step',
  'subzone_assignment',
  'system_event',
  'zone_assignment',
] as const satisfies readonly MessageType[]

/** Filter list passed to useWebSocket — identical set to handler types */
export const ESP_STORE_WS_SUBSCRIPTION_TYPES: MessageType[] = [
  ...ESP_STORE_WS_ON_HANDLER_TYPES,
]

/**
 * Explicit mutation contract for every WS type consumed by the esp store.
 * - replace: full-entity replacement from snapshot payload
 * - patch: targeted in-place delta on a bounded entity
 * - refresh: fallback full refresh via fetchAll/fetchDevice
 */
export const ESP_STORE_WS_MUTATION_CONTRACT: Record<
  (typeof ESP_STORE_WS_ON_HANDLER_TYPES)[number],
  RealtimeMutationType
> = {
  actuator_alert: 'patch',
  actuator_command: 'patch',
  actuator_command_failed: 'patch',
  actuator_config_deleted: 'patch',
  actuator_response: 'patch',
  actuator_status: 'patch',
  config_failed: 'patch',
  config_published: 'patch',
  config_response: 'patch',
  config_response_guard_replay: 'patch',
  device_approved: 'refresh',
  device_context_changed: 'patch',
  device_discovered: 'patch',
  device_rediscovered: 'patch',
  device_rejected: 'patch',
  device_scope_changed: 'patch',
  esp_health: 'patch',
  esp_reconnect_phase: 'patch',
  error_event: 'patch',
  intent_outcome: 'patch',
  intent_outcome_lifecycle: 'patch',
  logic_execution: 'patch',
  notification: 'patch',
  notification_new: 'patch',
  notification_updated: 'patch',
  notification_unread_count: 'patch',
  sensor_config_deleted: 'patch',
  sensor_data: 'patch',
  sensor_health: 'patch',
  sequence_cancelled: 'patch',
  sequence_completed: 'patch',
  sequence_error: 'patch',
  sequence_started: 'patch',
  sequence_step: 'patch',
  subzone_assignment: 'patch',
  system_event: 'patch',
  zone_assignment: 'patch',
}
