/**
 * Plugins Store (Phase 4C)
 *
 * Manages AutoOps plugin state: list, detail, execution, config updates.
 * Uses Setup Store pattern (Composition API).
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { pluginsApi } from '@/api/plugins'
import type { PluginDTO, PluginDetailDTO, PluginExecutionDTO, PluginExecutionStatusEvent } from '@/api/plugins'
import { useToast } from '@/composables/useToast'
import { useWebSocket } from '@/composables/useWebSocket'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'
import { normalizeOpsStatus } from '@/types/ops-lifecycle'
import type { WebSocketMessage } from '@/services/websocket'

export const usePluginsStore = defineStore('plugins', () => {
  // ======================== STATE ========================

  const plugins = ref<PluginDTO[]>([])
  const selectedPlugin = ref<PluginDetailDTO | null>(null)
  const executionHistory = ref<PluginExecutionDTO[]>([])
  const isLoading = ref(false)
  const isExecuting = ref(false)
  const executionLifecycleIds = ref<Record<string, string>>({})
  const isLifecycleMonitoring = ref(false)

  const EXECUTION_ACK_TIMEOUT_MS = 12_000
  const executionTimeouts = new Map<string, ReturnType<typeof setTimeout>>()
  const wsUnsubscribers: Array<() => void> = []

  // ======================== GETTERS ========================

  const enabledPlugins = computed(() =>
    plugins.value.filter((p) => p.is_enabled),
  )

  const disabledPlugins = computed(() =>
    plugins.value.filter((p) => !p.is_enabled),
  )

  const pluginsByCategory = computed(() => {
    const groups: Record<string, PluginDTO[]> = {}
    for (const plugin of plugins.value) {
      const cat = plugin.category || 'other'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(plugin)
    }
    return groups
  })

  /**
   * Plugin lookup by ID (for RuleFlowEditor plugin action config)
   */
  const pluginOptions = computed(() =>
    plugins.value.map((p) => ({
      value: p.plugin_id,
      label: p.display_name,
      disabled: !p.is_enabled,
    })),
  )

  // ======================== ACTIONS ========================

  const toast = useToast()
  const opsLifecycle = useOpsLifecycleStore()
  const { on } = useWebSocket({ autoConnect: true })

  function getExecutionId(execution: PluginExecutionDTO): string {
    return execution.execution_id ?? execution.id
  }

  function clearExecutionTimeout(executionId: string): void {
    const timeout = executionTimeouts.get(executionId)
    if (!timeout) return
    clearTimeout(timeout)
    executionTimeouts.delete(executionId)
  }

  function setExecutionAckTimeout(executionId: string, lifecycleId: string): void {
    clearExecutionTimeout(executionId)
    executionTimeouts.set(executionId, setTimeout(() => {
      const entry = opsLifecycle.findById(lifecycleId)
      if (!entry || entry.status !== 'initiated') {
        return
      }
      opsLifecycle.markFailed(
        lifecycleId,
        'Keine Running-Bestätigung innerhalb des Timeout-Fensters empfangen.',
        'plugin_status_timeout',
      )
    }, EXECUTION_ACK_TIMEOUT_MS))
  }

  function upsertHistoryExecution(execution: PluginExecutionDTO): void {
    const executionId = getExecutionId(execution)
    const idx = executionHistory.value.findIndex((item) => getExecutionId(item) === executionId)
    if (idx === -1) {
      executionHistory.value.unshift(execution)
      return
    }
    executionHistory.value[idx] = {
      ...executionHistory.value[idx],
      ...execution,
    }
  }

  function applyExecutionStatus(
    executionId: string,
    pluginId: string,
    rawStatus: string,
    payload: {
      message?: string
      started_at?: string
      updated_at?: string
      finished_at?: string
      error_code?: string | number
      error_message?: string
      correlation_id?: string
      progress_percent?: number
      step?: string
    },
  ): void {
    const lifecycleId = executionLifecycleIds.value[executionId]
      ?? opsLifecycle.startLifecycle({
        id: `plugin_exec_${executionId}`,
        scope: 'plugin_execute',
        title: `Plugin-Ausführung: ${pluginId}`,
        risk: 'high',
        execution_id: executionId,
        plugin_id: pluginId,
        summary: 'Status synchronisiert',
      })
    executionLifecycleIds.value[executionId] = lifecycleId

    const status = normalizeOpsStatus(rawStatus)
    opsLifecycle.updateLifecycle({
      id: lifecycleId,
      status,
      started_at: payload.started_at,
      finished_at: payload.finished_at,
      execution_id: executionId,
      plugin_id: pluginId,
      correlation_id: payload.correlation_id,
      reason_code: payload.error_code != null ? String(payload.error_code) : undefined,
      reason_text: payload.error_message,
      summary: payload.message,
      details: {
        updated_at: payload.updated_at,
        progress_percent: payload.progress_percent,
        step: payload.step,
      },
    })

    if (status === 'running') {
      clearExecutionTimeout(executionId)
    }
    if (status === 'success' || status === 'failed') {
      clearExecutionTimeout(executionId)
    }
  }

  async function fetchPlugins(): Promise<void> {
    isLoading.value = true
    try {
      plugins.value = await pluginsApi.list()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Plugins konnten nicht geladen werden')
    } finally {
      isLoading.value = false
    }
  }

  async function fetchPluginDetail(pluginId: string): Promise<void> {
    isLoading.value = true
    try {
      selectedPlugin.value = await pluginsApi.getDetail(pluginId)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Plugin-Details nicht verfügbar')
    } finally {
      isLoading.value = false
    }
  }

  async function executePlugin(
    pluginId: string,
    configOverrides?: Record<string, unknown>,
  ): Promise<PluginExecutionDTO | null> {
    isExecuting.value = true
    const lifecycleId = opsLifecycle.startLifecycle({
      scope: 'plugin_execute',
      title: `Plugin-Ausführung: ${pluginId}`,
      risk: 'high',
      plugin_id: pluginId,
      summary: 'Anfrage initiiert',
    })
    try {
      const execution = await pluginsApi.execute(pluginId, {
        config_overrides: configOverrides,
      })
      const executionId = getExecutionId(execution)
      executionLifecycleIds.value[executionId] = lifecycleId

      applyExecutionStatus(executionId, pluginId, execution.status, {
        message: execution.message ?? `Ausführung registriert (${execution.status})`,
        started_at: execution.started_at ?? undefined,
        updated_at: execution.updated_at ?? undefined,
        finished_at: execution.finished_at ?? undefined,
        error_code: execution.error_code ?? undefined,
        error_message: execution.error_message ?? undefined,
        correlation_id: execution.correlation_id ?? undefined,
        progress_percent: execution.progress_percent ?? undefined,
        step: execution.step ?? undefined,
      })

      // If backend only ACKs execute, enforce timeout guard for missing running state.
      if (normalizeOpsStatus(execution.status) === 'initiated') {
        setExecutionAckTimeout(executionId, lifecycleId)
      }

      toast.success(`Plugin '${pluginId}' gestartet (Execution-ID: ${executionId})`)
      upsertHistoryExecution(execution)

      // Refresh plugin list to update last_execution
      await fetchPlugins()

      return execution
    } catch (e) {
      opsLifecycle.markFailed(
        lifecycleId,
        e instanceof Error ? e.message : 'Plugin-Ausführung fehlgeschlagen',
        'plugin_execute_error',
      )
      toast.error(e instanceof Error ? e.message : 'Plugin-Ausführung fehlgeschlagen')
      return null
    } finally {
      isExecuting.value = false
    }
  }

  async function togglePlugin(pluginId: string, enabled: boolean): Promise<void> {
    const lifecycleId = opsLifecycle.startLifecycle({
      scope: 'plugin_toggle',
      title: `Plugin ${enabled ? 'aktivieren' : 'deaktivieren'}: ${pluginId}`,
      risk: 'high',
      plugin_id: pluginId,
      summary: 'Anfrage initiiert',
    })
    opsLifecycle.markRunning(lifecycleId, 'Plugin-Status wird aktualisiert')
    try {
      if (enabled) {
        await pluginsApi.enable(pluginId)
        toast.success(`Plugin '${pluginId}' aktiviert`)
      } else {
        await pluginsApi.disable(pluginId)
        toast.success(`Plugin '${pluginId}' deaktiviert`)
      }

      // Update local state
      const plugin = plugins.value.find((p) => p.plugin_id === pluginId)
      if (plugin) plugin.is_enabled = enabled
      opsLifecycle.markSuccess(lifecycleId, 'Plugin-Status aktualisiert')
    } catch (e) {
      opsLifecycle.markFailed(
        lifecycleId,
        e instanceof Error ? e.message : 'Plugin-Status konnte nicht geändert werden',
        'plugin_toggle_error',
      )
      toast.error(e instanceof Error ? e.message : 'Plugin-Status konnte nicht geändert werden')
    }
  }

  async function updateConfig(
    pluginId: string,
    config: Record<string, unknown>,
  ): Promise<void> {
    const lifecycleId = opsLifecycle.startLifecycle({
      scope: 'plugin_config',
      title: `Plugin-Konfiguration: ${pluginId}`,
      risk: 'high',
      plugin_id: pluginId,
      summary: 'Konfigurationsänderung initiiert',
    })
    opsLifecycle.markRunning(lifecycleId, 'Konfiguration wird gespeichert')
    try {
      await pluginsApi.updateConfig(pluginId, { config })
      toast.success('Plugin-Konfiguration gespeichert')

      // Update local state
      const plugin = plugins.value.find((p) => p.plugin_id === pluginId)
      if (plugin) plugin.config = config
      opsLifecycle.markSuccess(lifecycleId, 'Konfiguration gespeichert')
    } catch (e) {
      opsLifecycle.markFailed(
        lifecycleId,
        e instanceof Error ? e.message : 'Konfiguration konnte nicht gespeichert werden',
        'plugin_config_error',
      )
      toast.error(e instanceof Error ? e.message : 'Konfiguration konnte nicht gespeichert werden')
    }
  }

  async function fetchHistory(pluginId: string, limit: number = 50): Promise<void> {
    try {
      executionHistory.value = await pluginsApi.getHistory(pluginId, limit)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Ausführungshistorie nicht verfügbar')
    }
  }

  function handlePluginExecutionStatus(message: WebSocketMessage): void {
    const payload = message.data as Partial<PluginExecutionStatusEvent>
    if (!payload.execution_id || !payload.plugin_id || !payload.status) {
      return
    }
    applyExecutionStatus(payload.execution_id, payload.plugin_id, payload.status, {
      message: payload.message,
      started_at: payload.started_at,
      updated_at: payload.updated_at,
      finished_at: payload.finished_at,
      error_code: payload.error_code,
      error_message: payload.error_message,
      correlation_id: payload.correlation_id,
      progress_percent: payload.progress_percent,
      step: payload.step,
    })
  }

  function handlePluginExecutionStarted(message: { data: Record<string, unknown> }): void {
    const data = message.data
    const executionId = typeof data.execution_id === 'string' ? data.execution_id : ''
    const pluginId = typeof data.plugin_id === 'string' ? data.plugin_id : ''
    if (!executionId || !pluginId) return
    applyExecutionStatus(executionId, pluginId, 'running', {
      message: 'Ausführung gestartet',
      started_at: typeof data.started_at === 'string' ? data.started_at : new Date().toISOString(),
      updated_at: typeof data.updated_at === 'string' ? data.updated_at : new Date().toISOString(),
      correlation_id: typeof data.correlation_id === 'string' ? data.correlation_id : undefined,
    })
  }

  function handlePluginExecutionCompleted(message: { data: Record<string, unknown> }): void {
    const data = message.data
    const executionId = typeof data.execution_id === 'string' ? data.execution_id : ''
    const pluginId = typeof data.plugin_id === 'string' ? data.plugin_id : ''
    const status = typeof data.status === 'string' ? data.status : 'success'
    if (!executionId || !pluginId) return
    applyExecutionStatus(executionId, pluginId, status, {
      message: typeof data.message === 'string' ? data.message : undefined,
      finished_at: typeof data.finished_at === 'string' ? data.finished_at : new Date().toISOString(),
      updated_at: typeof data.updated_at === 'string' ? data.updated_at : new Date().toISOString(),
      error_message: typeof data.error_message === 'string' ? data.error_message : undefined,
      error_code: data.error_code as string | number | undefined,
      correlation_id: typeof data.correlation_id === 'string' ? data.correlation_id : undefined,
    })
  }

  function startLifecycleMonitoring(): void {
    if (isLifecycleMonitoring.value) return
    isLifecycleMonitoring.value = true
    wsUnsubscribers.push(on('plugin_execution_status', handlePluginExecutionStatus))
    wsUnsubscribers.push(on('plugin_execution_started', handlePluginExecutionStarted))
    wsUnsubscribers.push(on('plugin_execution_completed', handlePluginExecutionCompleted))
  }

  function stopLifecycleMonitoring(): void {
    wsUnsubscribers.forEach((unsubscribe) => unsubscribe())
    wsUnsubscribers.length = 0
    isLifecycleMonitoring.value = false
    executionTimeouts.forEach((timeout) => clearTimeout(timeout))
    executionTimeouts.clear()
  }

  async function reconcileRunningExecutions(): Promise<void> {
    try {
      const running = await pluginsApi.getRunningExecutions()
      running.forEach((execution) => {
        const executionId = getExecutionId(execution)
        applyExecutionStatus(executionId, execution.plugin_id, execution.status, {
          message: execution.message ?? 'Laufende Ausführung wiederhergestellt',
          started_at: execution.started_at ?? undefined,
          updated_at: execution.updated_at ?? undefined,
          finished_at: execution.finished_at ?? undefined,
          error_code: execution.error_code ?? undefined,
          error_message: execution.error_message ?? undefined,
          correlation_id: execution.correlation_id ?? undefined,
          progress_percent: execution.progress_percent ?? undefined,
          step: execution.step ?? undefined,
        })
      })
      return
    } catch {
      // Optional endpoint may not exist; fallback below.
    }

    await fetchPlugins()
    plugins.value.forEach((plugin) => {
      const lastExecution = plugin.last_execution
      if (!lastExecution) return
      const normalized = normalizeOpsStatus(lastExecution.status)
      if (normalized !== 'running' && normalized !== 'partial' && normalized !== 'initiated') {
        return
      }
      const executionId = getExecutionId(lastExecution)
      applyExecutionStatus(executionId, plugin.plugin_id, lastExecution.status, {
        message: 'Laufende Ausführung aus Plugin-Liste rekonstruiert',
        started_at: lastExecution.started_at ?? undefined,
        updated_at: lastExecution.updated_at ?? undefined,
        finished_at: lastExecution.finished_at ?? undefined,
        error_code: lastExecution.error_code ?? undefined,
        error_message: lastExecution.error_message ?? undefined,
        correlation_id: lastExecution.correlation_id ?? undefined,
        progress_percent: lastExecution.progress_percent ?? undefined,
        step: lastExecution.step ?? undefined,
      })
    })
  }

  return {
    // State
    plugins,
    selectedPlugin,
    executionHistory,
    isLoading,
    isExecuting,
    isLifecycleMonitoring,
    // Getters
    enabledPlugins,
    disabledPlugins,
    pluginsByCategory,
    pluginOptions,
    // Actions
    fetchPlugins,
    fetchPluginDetail,
    executePlugin,
    togglePlugin,
    updateConfig,
    fetchHistory,
    startLifecycleMonitoring,
    stopLifecycleMonitoring,
    reconcileRunningExecutions,
  }
})
