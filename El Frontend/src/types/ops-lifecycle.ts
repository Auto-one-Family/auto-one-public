export type OpsLifecycleStatus =
  | 'initiated'
  | 'running'
  | 'partial'
  | 'success'
  | 'failed'

export type OpsLifecycleRisk = 'low' | 'medium' | 'high'

export type OpsLifecycleScope =
  | 'plugin_execute'
  | 'plugin_toggle'
  | 'plugin_config'
  | 'loadtest_bulk_create'
  | 'loadtest_simulation'
  | 'system_config_save'
  | 'system_config_apply'

export type OpsExternalStatus =
  | 'queued'
  | 'accepted'
  | 'started'
  | 'running'
  | 'partial'
  | 'success'
  | 'completed'
  | 'done'
  | 'error'
  | 'failed'
  | 'failure'
  | 'timeout'
  | 'cancelled'
  | string

export interface OpsLifecycleEntry {
  id: string
  scope: OpsLifecycleScope
  title: string
  status: OpsLifecycleStatus
  risk: OpsLifecycleRisk
  initiated_at: string
  updated_at: string
  started_at?: string
  finished_at?: string
  execution_id?: string
  plugin_id?: string
  correlation_id?: string
  reason_code?: string
  reason_text?: string
  summary?: string
  details?: Record<string, unknown>
}

export function normalizeOpsStatus(status: OpsExternalStatus): OpsLifecycleStatus {
  const normalized = String(status || '').trim().toLowerCase()
  if (['started', 'running'].includes(normalized)) return 'running'
  if (['partial'].includes(normalized)) return 'partial'
  if (['success', 'completed', 'done'].includes(normalized)) return 'success'
  if (['error', 'failed', 'failure', 'timeout', 'cancelled'].includes(normalized)) return 'failed'
  return 'initiated'
}

export function isTerminalOpsStatus(status: OpsLifecycleStatus): boolean {
  return status === 'success' || status === 'failed'
}
