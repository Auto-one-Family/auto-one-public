import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  isTerminalOpsStatus,
  normalizeOpsStatus,
  type OpsExternalStatus,
  type OpsLifecycleEntry,
  type OpsLifecycleRisk,
  type OpsLifecycleScope,
  type OpsLifecycleStatus,
} from '@/types/ops-lifecycle'

interface StartLifecycleInput {
  id?: string
  scope: OpsLifecycleScope
  title: string
  risk: OpsLifecycleRisk
  execution_id?: string
  plugin_id?: string
  correlation_id?: string
  summary?: string
  details?: Record<string, unknown>
}

interface UpdateLifecycleInput {
  id: string
  status: OpsLifecycleStatus
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

export const useOpsLifecycleStore = defineStore('opsLifecycle', () => {
  const entries = ref<OpsLifecycleEntry[]>([])

  const sortedEntries = computed(() =>
    [...entries.value].sort((a, b) => {
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    }),
  )

  const runningHighRiskEntries = computed(() =>
    sortedEntries.value.filter((entry) =>
      entry.risk === 'high' && !isTerminalOpsStatus(entry.status),
    ),
  )

  const recentTerminalEntries = computed(() =>
    sortedEntries.value
      .filter((entry) => isTerminalOpsStatus(entry.status))
      .slice(0, 10),
  )

  function findById(id: string): OpsLifecycleEntry | undefined {
    return entries.value.find((entry) => entry.id === id)
  }

  function findByExecutionId(executionId: string): OpsLifecycleEntry | undefined {
    return entries.value.find((entry) => entry.execution_id === executionId)
  }

  function startLifecycle(input: StartLifecycleInput): string {
    const now = new Date().toISOString()
    const id = input.id ?? `ops_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const existing = findById(id)
    if (existing) {
      existing.updated_at = now
      existing.summary = input.summary ?? existing.summary
      existing.details = input.details ?? existing.details
      return id
    }

    entries.value.unshift({
      id,
      scope: input.scope,
      title: input.title,
      status: 'initiated',
      risk: input.risk,
      initiated_at: now,
      updated_at: now,
      execution_id: input.execution_id,
      plugin_id: input.plugin_id,
      correlation_id: input.correlation_id,
      summary: input.summary,
      details: input.details,
    })
    return id
  }

  function updateLifecycle(input: UpdateLifecycleInput): void {
    const target = findById(input.id)
    if (!target) return
    const now = new Date().toISOString()
    target.status = input.status
    target.updated_at = now
    target.started_at = input.started_at ?? target.started_at
    target.execution_id = input.execution_id ?? target.execution_id
    target.plugin_id = input.plugin_id ?? target.plugin_id
    target.correlation_id = input.correlation_id ?? target.correlation_id
    target.summary = input.summary ?? target.summary
    target.reason_code = input.reason_code ?? target.reason_code
    target.reason_text = input.reason_text ?? target.reason_text
    target.details = input.details ?? target.details

    if (isTerminalOpsStatus(input.status)) {
      target.finished_at = input.finished_at ?? now
    }
  }

  function updateByExecutionId(
    executionId: string,
    status: OpsExternalStatus,
    input?: Omit<UpdateLifecycleInput, 'id' | 'status'>,
  ): void {
    const target = findByExecutionId(executionId)
    if (!target) return
    updateLifecycle({
      id: target.id,
      status: normalizeOpsStatus(status),
      ...input,
    })
  }

  function markRunning(id: string, summary?: string): void {
    updateLifecycle({ id, status: 'running', started_at: new Date().toISOString(), summary })
  }

  function markPartial(id: string, summary?: string): void {
    updateLifecycle({ id, status: 'partial', summary })
  }

  function markSuccess(id: string, summary?: string): void {
    updateLifecycle({ id, status: 'success', finished_at: new Date().toISOString(), summary })
  }

  function markFailed(id: string, reasonText: string, reasonCode?: string): void {
    updateLifecycle({
      id,
      status: 'failed',
      finished_at: new Date().toISOString(),
      reason_text: reasonText,
      reason_code: reasonCode,
    })
  }

  function clearOldTerminalEntries(maxEntries: number = 50): void {
    const active = entries.value.filter((entry) => !isTerminalOpsStatus(entry.status))
    const terminal = entries.value
      .filter((entry) => isTerminalOpsStatus(entry.status))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, maxEntries)
    entries.value = [...active, ...terminal]
  }

  return {
    entries,
    sortedEntries,
    runningHighRiskEntries,
    recentTerminalEntries,
    startLifecycle,
    updateLifecycle,
    updateByExecutionId,
    findById,
    findByExecutionId,
    markRunning,
    markPartial,
    markSuccess,
    markFailed,
    clearOldTerminalEntries,
  }
})
